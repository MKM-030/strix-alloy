/* Source-only, root-owned partial-asset Q4 module diagnostic. NO engine hook.
 * Build plan (not executed): cc -std=c11 -O2 -Wall -Wextra -Werror host.c
 *   -ldl -lm -o <fresh-owned-directory>/q4-query-stage-component
 * Usage: host /absolute/native.hsaco /absolute/candidate.hsaco /absolute/input-dir
 * Input dir contains EXACTLY blob.bin and head-000..014.{query.bf16,logits.f32}.
 * Root records source/binary/runtime/module/input SHA256 pins independently,
 * reviews both module ABIs/float modes/resources, and owns the process deadline,
 * exclusive GPU/reserve checks, staging and run. No extra capture or serving.
 * No HIP headers: ABI pattern follows profiler-availability/tiny-hip-trace-host.c.
 * One excluded warmup pair plus three measured pairs PER head; arm order
 * alternates AB/BA. A=stock, B=query-LDS. All 34571 FP32 rows are compared on
 * EVERY pair: A vs captured, B vs A. No tolerance, winner-only or subset pass.
 * Events bracket each complete two-projection path; copies/readback/file I/O
 * are outside the event bracket. The monotonic host span includes enqueue/wait
 * for the entire pair. Guards follow each arm's complete reduced output.
 * JSONL contains only aggregate comparisons/timing/resource status, no payload
 * values or indices. Any parity failure gives a nonzero final exit status.
 */
#define _GNU_SOURCE
#include <dirent.h>
#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <float.h>
#include <inttypes.h>
#include <math.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

#if !defined(__linux__) || !defined(__x86_64__)
#error Linux x86-64 only
#endif
enum { HEADS=15, CORE_ROWS=32033, TAIL_ROWS=2538, ROWS=34571,
       WIDTH=2560, BLOCK=256, QUERY_BYTES=5120, GUARD_BYTES=64,
       MEASURED=3, INPUT_FILES=31, H2D=1, D2H=2 };
#define BLOB_BYTES ((size_t)49782304)
#define OUTPUT_BYTES ((size_t)ROWS*4u)
#define OUTPUT_ALLOCATION (OUTPUT_BYTES+GUARD_BYTES)
#define MODULE_MAX ((uint64_t)64u*1024u*1024u)
#define HIP_LIBRARY "/usr/local/lib/python3.12/site-packages/_rocm_sdk_core/lib/libamdhip64.so.7"
#define NATIVE_SYMBOL "_ZN7halogen12_GLOBAL__N_16k_lq4wILi1ELi16ELi1ELb1ELi0ELi0EEEvPKhPKtPvlllllS6_f"
#define CANDIDATE_SYMBOL "halogen0172_q4_query_lds_v1"
_Static_assert(CORE_ROWS+TAIL_ROWS==ROWS, "exact two-projection layout");
_Static_assert(64u+(size_t)ROWS*(1280u+160u)==BLOB_BYTES, "exact native blob extent");
_Static_assert(sizeof(void*)==8 && sizeof(int64_t)==8 && sizeof(uint32_t)==4,
               "sealed LP64 HIP argument ABI");
_Static_assert(sizeof(float)==4 && FLT_RADIX==2 && FLT_MANT_DIG==24,
               "FP32 output representation");
_Static_assert(__BYTE_ORDER__==__ORDER_LITTLE_ENDIAN__, "little endian only");

static int (*p_hipMalloc)(void**,size_t);
static int (*p_hipFree)(void*);
static int (*p_hipMemcpy)(void*,const void*,size_t,int);
static int (*p_hipModuleLoad)(void**,const char*);
static int (*p_hipModuleGetFunction)(void**,void*,const char*);
static int (*p_hipModuleLaunchKernel)(void*,unsigned,unsigned,unsigned,
                                    unsigned,unsigned,unsigned,unsigned,
                                    void*,void**,void**);
static int (*p_hipModuleUnload)(void*);
static int (*p_hipDeviceSynchronize)(void);
static int (*p_hipEventCreateWithFlags)(void**,unsigned);
static int (*p_hipEventRecord)(void*,void*);
static int (*p_hipEventSynchronize)(void*);
static int (*p_hipEventElapsedTime)(float*,void*,void*);
static int (*p_hipEventDestroy)(void*);

static const char *error_reason;
static int error_code, current_head=-1, current_round=-1;
static unsigned allocations,freed,modules_loaded,modules_unloaded;
static unsigned events_created,events_destroyed,cleanup_errors,file_close_errors;
static unsigned launch_attempts,launches_ok,pairs_completed,heads_completed;
static unsigned parity_failures,guard_failures,cleanup_sync_attempts,cleanup_sync_ok;
static int stdout_failed;

static int fail(const char *reason,int code) {
    if(!error_reason) {error_reason=reason;error_code=code;}
    return 0;
}
static int hip_ok(int code,const char *reason) {
    return code==0 || fail(reason,code);
}
static void close_file(int *fd) {
    if(*fd>=0) {
        if(close(*fd)) {file_close_errors++;fail("file-close",errno);}
        *fd=-1; /* Linux close errors must not be retried against a reused fd. */
    }
}
static int same_identity(const struct stat *a,const struct stat *b) {
    return a->st_dev==b->st_dev && a->st_ino==b->st_ino &&
        a->st_size==b->st_size && a->st_mtim.tv_sec==b->st_mtim.tv_sec &&
        a->st_mtim.tv_nsec==b->st_mtim.tv_nsec &&
        a->st_ctim.tv_sec==b->st_ctim.tv_sec &&
        a->st_ctim.tv_nsec==b->st_ctim.tv_nsec;
}
static int stable_fd(int fd,const struct stat *before) {
    struct stat after;
    if(fstat(fd,&after)) return fail("file-restat",errno);
    return same_identity(before,&after) || fail("file-identity-changed",0);
}

/* Walk every absolute path component with O_NOFOLLOW, including the parent
 * directories. Reject . and .. instead of resolving them through another path.
 */
static int open_absolute(const char *path,int directory) {
    if(!path || path[0]!='/' || strlen(path)>4095u || !path[1]) {
        fail("absolute-bounded-path-required",0);return -1;
    }
    char text[4096];memcpy(text,path,strlen(path)+1u);
    int parent=open("/",O_RDONLY|O_DIRECTORY|O_CLOEXEC|O_NOFOLLOW);
    if(parent<0) {fail("root-directory-open",errno);return -1;}
    char *save=NULL,*part=strtok_r(text+1,"/",&save);
    while(part) {
        char *next=strtok_r(NULL,"/",&save);
        if(!strcmp(part,".") || !strcmp(part,"..")) {
            fail("dot-path-component-rejected",0);close_file(&parent);return -1;
        }
        int flags=O_RDONLY|O_CLOEXEC|O_NOFOLLOW;
        if(next || directory) flags|=O_DIRECTORY;
        int child=openat(parent,part,flags);
        if(child<0) {
            fail("path-open-no-symlinks",errno);close_file(&parent);return -1;
        }
        close_file(&parent);
        if(error_reason) {close_file(&child);return -1;}
        parent=child;part=next;
    }
    return parent;
}
static int input_index(const char *name) {
    if(!strcmp(name,"blob.bin")) return 0;
    char wanted[64];
    for(unsigned h=0;h<HEADS;h++) {
        snprintf(wanted,sizeof wanted,"head-%03u.query.bf16",h);
        if(!strcmp(name,wanted)) return (int)(1u+2u*h);
        snprintf(wanted,sizeof wanted,"head-%03u.logits.f32",h);
        if(!strcmp(name,wanted)) return (int)(2u+2u*h);
    }
    return -1;
}
static size_t input_bytes(unsigned index) {
    return index==0 ? BLOB_BYTES : ((index&1u) ? QUERY_BYTES : OUTPUT_BYTES);
}
static int validate_inputs(int dirfd,struct stat identities[INPUT_FILES]) {
    /* dup() shares a directory offset; the final scan needs a fresh description. */
    int duplicate=openat(dirfd,".",O_RDONLY|O_DIRECTORY|O_CLOEXEC|O_NOFOLLOW);
    if(duplicate<0) return fail("input-directory-rescan-open",errno);
    DIR *directory=fdopendir(duplicate);
    if(!directory) {fail("input-directory-scan-open",errno);close_file(&duplicate);return 0;}
    unsigned seen[INPUT_FILES]={0},count=0;
    int ok=1;
    for(;;) {
        errno=0;struct dirent *entry=readdir(directory);
        if(!entry) {if(errno) ok=fail("input-directory-scan",errno);break;}
        if(!strcmp(entry->d_name,".") || !strcmp(entry->d_name,"..")) continue;
        int index=input_index(entry->d_name);
        if(index<0 || seen[index] || ++count>INPUT_FILES) {
            ok=fail("unexpected-input-filename",0);break;
        }
        struct stat st;
        if(fstatat(dirfd,entry->d_name,&st,AT_SYMLINK_NOFOLLOW)) {
            ok=fail("input-file-stat",errno);break;
        }
        if(!S_ISREG(st.st_mode) || st.st_size<0 ||
           (uint64_t)st.st_size!=(uint64_t)input_bytes((unsigned)index)) {
            ok=fail("input-file-type-or-exact-size",0);break;
        }
        identities[index]=st;seen[index]=1;
    }
    if(closedir(directory)) {file_close_errors++;ok=fail("input-directory-scan-close",errno);}
    if(ok && count!=INPUT_FILES) ok=fail("missing-input-files",0);
    return ok;
}
static int read_exact(int fd,void *data,size_t bytes) {
    unsigned char *p=data;
    while(bytes) {
        ssize_t n=read(fd,p,bytes);
        if(n<0 && errno==EINTR) continue;
        if(n<=0) return fail("input-read-exact",n<0 ? errno : 0);
        p+=n;bytes-=(size_t)n;
    }
    return 1;
}
static int read_input(int dirfd,const char *name,unsigned index,void *data,
                      const struct stat identities[INPUT_FILES]) {
    int fd=openat(dirfd,name,O_RDONLY|O_CLOEXEC|O_NOFOLLOW);
    if(fd<0) return fail("input-open-no-symlinks",errno);
    int ok=stable_fd(fd,&identities[index]) &&
        read_exact(fd,data,input_bytes(index)) && stable_fd(fd,&identities[index]);
    close_file(&fd);
    return ok && !error_reason;
}
static int open_module(const char *path,struct stat *identity) {
    int fd=open_absolute(path,0);if(fd<0) return -1;
    if(fstat(fd,identity)) {fail("module-stat",errno);close_file(&fd);return -1;}
    if(!S_ISREG(identity->st_mode) || identity->st_size<64 ||
       (uint64_t)identity->st_size>MODULE_MAX) {
        fail("bounded-regular-module-required",0);close_file(&fd);return -1;
    }
    unsigned char header[64];
    if(!read_exact(fd,header,sizeof header) || !stable_fd(fd,identity)) {
        close_file(&fd);return -1;
    }
    if(memcmp(header,"\177ELF",4) || header[4]!=2 || header[5]!=1 ||
       header[18]!=224 || header[19]!=0) {
        fail("little-endian-ELF64-AMDGPU-module-required",0);close_file(&fd);return -1;
    }
    return fd;
}
static int resolve(void *library,const char *name,void *destination,size_t bytes) {
    dlerror();void *symbol=dlsym(library,name);const char *error=dlerror();
    if(error || !symbol || bytes!=sizeof symbol) return fail("hip-symbol-resolution",0);
    memcpy(destination,&symbol,bytes);return 1;
}
#define LOAD(name) do {if(!resolve(library,#name,&p_##name,sizeof(p_##name))) goto cleanup;} while(0)
#define CHECK(call,label) do {if(!hip_ok((call),(label))) goto cleanup;} while(0)

static int launch_path(void *function,void *blob,void *query,void *output) {
    int64_t width=WIDTH,stride=160;
    const int64_t scale_base=64+(int64_t)ROWS*1280;
    void *optional=NULL;float beta=0.0f;
    for(unsigned projection=0;projection<2;projection++) {
        int64_t rows=projection ? TAIL_ROWS : CORE_ROWS;
        int64_t first=projection ? CORE_ROWS : 0;
        int64_t code_offset=64+first*1280;
        int64_t scale_offset=scale_base+first*160;
        void *target=(unsigned char*)output+(size_t)first*4u;
        void *arguments[10]={&blob,&query,&target,&width,&rows,&code_offset,
                              &scale_offset,&stride,&optional,&beta};
        launch_attempts++;
        int status=p_hipModuleLaunchKernel(function,(unsigned)((rows+15)/16),1,1,
                                           BLOCK,1,1,0,NULL,arguments,NULL);
        if(!hip_ok(status,projection ? "tail-projection-launch" : "core-projection-launch")) return 0;
        launches_ok++;
    }
    return 1;
}
struct difference {unsigned mismatches,nonfinite;double max_abs;};
static struct difference compare_bits(const uint32_t *actual,const uint32_t *expected) {
    struct difference result={0,0,0.0};
    for(unsigned i=0;i<ROWS;i++) {
        if(actual[i]==expected[i]) continue;
        result.mismatches++;
        float a,b;memcpy(&a,actual+i,4);memcpy(&b,expected+i,4);
        if(!isfinite(a) || !isfinite(b)) {result.nonfinite++;continue;}
        double difference=fabs((double)a-(double)b);
        if(difference>result.max_abs) result.max_abs=difference;
    }
    return result;
}
static unsigned corrupt_guard(const uint32_t *output) {
    const unsigned char *guard=(const unsigned char*)output+OUTPUT_BYTES;
    unsigned bad=0;
    for(unsigned i=0;i<GUARD_BYTES;i++) bad+=guard[i]!=0xa5u;
    return bad;
}
static void print_difference(const struct difference *difference) {
    printf("{\"compared_rows\":%u,\"bit_mismatches\":%u,\"max_abs\":",ROWS,difference->mismatches);
    if(difference->nonfinite) fputs("null",stdout);
    else printf("%.17g",difference->max_abs);
    printf(",\"nonfinite_mismatches\":%u}",difference->nonfinite);
}
static double host_ms(const struct timespec *a,const struct timespec *b) {
    return (double)(b->tv_sec-a->tv_sec)*1000.0+
        (double)(b->tv_nsec-a->tv_nsec)/1000000.0;
}
static void cleanup_hip(int code,const char *operation) {
    if(!code) return;
    cleanup_errors++;fail("hip-cleanup",code);
    printf("{\"type\":\"cleanup_error\",\"operation\":\"%s\",\"hip_status\":%d}\n",operation,code);
}

int main(int argc,char **argv) {
    int dirfd=-1,module_fd[2]={-1,-1},pending_work=0;
    void *library=NULL,*modules[2]={NULL,NULL},*functions[2]={NULL,NULL};
    void *device_blob=NULL,*device_query=NULL,*device_output[2]={NULL,NULL};
    void *events[3]={NULL,NULL,NULL};
    void *host_blob=NULL;
    uint32_t *captured=NULL,*poison=NULL,*observed[2]={NULL,NULL};
    unsigned char query[QUERY_BYTES];
    struct stat input_identity[INPUT_FILES],module_identity[2];
    const char *symbols[2]={NATIVE_SYMBOL,CANDIDATE_SYMBOL};
    int nominal_complete=0;
    if(signal(SIGPIPE,SIG_IGN)==SIG_ERR) {fail("ignore-sigpipe",errno);goto cleanup;}
    if(argc!=4) {fail("expected-native-candidate-input-directory-arguments",0);goto cleanup;}
    dirfd=open_absolute(argv[3],1);if(dirfd<0) goto cleanup;
    if(!validate_inputs(dirfd,input_identity)) goto cleanup;
    for(unsigned arm=0;arm<2;arm++) {
        module_fd[arm]=open_module(argv[1+arm],&module_identity[arm]);
        if(module_fd[arm]<0) goto cleanup;
    }
    host_blob=malloc(BLOB_BYTES);captured=malloc(OUTPUT_BYTES);
    poison=malloc(OUTPUT_ALLOCATION);
    observed[0]=malloc(OUTPUT_ALLOCATION);observed[1]=malloc(OUTPUT_ALLOCATION);
    if(!host_blob || !captured || !poison || !observed[0] || !observed[1]) {
        fail("bounded-host-allocation",errno);goto cleanup;
    }
    if(!read_input(dirfd,"blob.bin",0,host_blob,input_identity)) goto cleanup;
    for(unsigned i=0;i<ROWS;i++) poison[i]=UINT32_C(0x7fc0dead);
    memset((unsigned char*)poison+OUTPUT_BYTES,0xa5,GUARD_BYTES);
    library=dlopen(HIP_LIBRARY,RTLD_NOW|RTLD_LOCAL);
    if(!library) {fail("fixed-hip-library-dlopen",0);goto cleanup;}
    LOAD(hipMalloc);LOAD(hipFree);LOAD(hipMemcpy);LOAD(hipModuleLoad);
    LOAD(hipModuleGetFunction);LOAD(hipModuleLaunchKernel);LOAD(hipModuleUnload);
    LOAD(hipDeviceSynchronize);LOAD(hipEventCreateWithFlags);LOAD(hipEventRecord);
    LOAD(hipEventSynchronize);LOAD(hipEventElapsedTime);LOAD(hipEventDestroy);
    /* First bounded allocation establishes default device/context before loads. */
    CHECK(p_hipMalloc(&device_blob,BLOB_BYTES),"allocate-native-blob");allocations++;
    CHECK(p_hipMalloc(&device_query,QUERY_BYTES),"allocate-query");allocations++;
    for(unsigned arm=0;arm<2;arm++) {
        CHECK(p_hipMalloc(&device_output[arm],OUTPUT_ALLOCATION),"allocate-output-and-guard");allocations++;
    }
    if(((uintptr_t)device_blob&15u) || ((uintptr_t)device_query&15u) ||
       ((uintptr_t)device_output[0]&3u) || ((uintptr_t)device_output[1]&3u)) {
        fail("device-buffer-alignment",0);goto cleanup;
    }
    CHECK(p_hipMemcpy(device_blob,host_blob,BLOB_BYTES,H2D),"copy-native-blob-outside-timing");
    free(host_blob);host_blob=NULL;
    for(unsigned arm=0;arm<2;arm++) {
        char fd_path[64];snprintf(fd_path,sizeof fd_path,"/proc/self/fd/%d",module_fd[arm]);
        CHECK(p_hipModuleLoad(&modules[arm],fd_path),"load-validated-module-fd");modules_loaded++;
        if(!stable_fd(module_fd[arm],&module_identity[arm])) goto cleanup;
        CHECK(p_hipModuleGetFunction(&functions[arm],modules[arm],symbols[arm]),"get-exact-module-symbol");
    }
    for(unsigned i=0;i<3;i++) {
        CHECK(p_hipEventCreateWithFlags(&events[i],0u),"create-timing-event");events_created++;
    }
    printf("{\"type\":\"contract\",\"schema\":\"halogen0172.q4-query-stage-component.v1\","
           "\"scope\":\"partial_asset_component_diagnostic\",\"heads\":%u,\"rows\":%u,"
           "\"core_rows\":%u,\"tail_rows\":%u,\"blob_bytes\":%zu,\"query_bytes\":%u,"
           "\"output_bytes\":%zu,\"guard_bytes_per_arm\":%u,\"warmup_pairs_per_head\":1,"
           "\"measured_pairs_per_head\":%u,\"block\":256,\"dynamic_shared_bytes\":0,"
           "\"native_module_bytes\":%jd,\"candidate_module_bytes\":%jd,"
           "\"pin_verification\":\"root_owned\",\"live_serving_qualified\":false}\n",
           HEADS,ROWS,CORE_ROWS,TAIL_ROWS,BLOB_BYTES,QUERY_BYTES,OUTPUT_BYTES,GUARD_BYTES,
           MEASURED,(intmax_t)module_identity[0].st_size,(intmax_t)module_identity[1].st_size);
    if(fflush(stdout) || ferror(stdout)) {stdout_failed=1;fail("stdout-contract",errno);goto cleanup;}

    for(unsigned head=0;head<HEADS;head++) {
        current_head=(int)head;
        char name[64];
        snprintf(name,sizeof name,"head-%03u.query.bf16",head);
        if(!read_input(dirfd,name,1u+2u*head,query,input_identity)) goto cleanup;
        snprintf(name,sizeof name,"head-%03u.logits.f32",head);
        if(!read_input(dirfd,name,2u+2u*head,captured,input_identity)) goto cleanup;
        CHECK(p_hipMemcpy(device_query,query,QUERY_BYTES,H2D),"copy-query-outside-timing");
        unsigned head_parity_failures=0;
        double native_total=0.0,candidate_total=0.0,host_total=0.0;
        for(unsigned iteration=0;iteration<1u+MEASURED;iteration++) {
            current_round=(int)iteration-1;
            const unsigned first=(head+iteration)&1u,second=first^1u;
            for(unsigned arm=0;arm<2;arm++) {
                CHECK(p_hipMemcpy(device_output[arm],poison,OUTPUT_ALLOCATION,H2D),"poison-output-outside-timing");
            }
            struct timespec start,end;
            if(clock_gettime(CLOCK_MONOTONIC,&start)) {fail("monotonic-start",errno);goto cleanup;}
            pending_work=1;
            CHECK(p_hipEventRecord(events[0],NULL),"record-path-start");
            if(!launch_path(functions[first],device_blob,device_query,device_output[first])) goto cleanup;
            CHECK(p_hipEventRecord(events[1],NULL),"record-path-boundary");
            if(!launch_path(functions[second],device_blob,device_query,device_output[second])) goto cleanup;
            CHECK(p_hipEventRecord(events[2],NULL),"record-path-end");
            CHECK(p_hipEventSynchronize(events[2]),"wait-pair-completion");
            pending_work=0;
            if(clock_gettime(CLOCK_MONOTONIC,&end)) {fail("monotonic-end",errno);goto cleanup;}
            float first_ms=0.0f,second_ms=0.0f,pair_ms=0.0f;
            CHECK(p_hipEventElapsedTime(&first_ms,events[0],events[1]),"first-path-elapsed");
            CHECK(p_hipEventElapsedTime(&second_ms,events[1],events[2]),"second-path-elapsed");
            CHECK(p_hipEventElapsedTime(&pair_ms,events[0],events[2]),"pair-elapsed");
            double host_span=host_ms(&start,&end);
            if(!isfinite(first_ms) || !isfinite(second_ms) || !isfinite(pair_ms) ||
               first_ms<0.0f || second_ms<0.0f || pair_ms<0.0f || host_span<0.0) {
                fail("invalid-timing-aggregate",0);goto cleanup;
            }
            for(unsigned arm=0;arm<2;arm++) {
                CHECK(p_hipMemcpy(observed[arm],device_output[arm],OUTPUT_ALLOCATION,D2H),"read-output-after-completion");
            }
            struct difference native_capture=compare_bits(observed[0],captured);
            struct difference candidate_native=compare_bits(observed[1],observed[0]);
            unsigned native_guard=corrupt_guard(observed[0]),candidate_guard=corrupt_guard(observed[1]);
            double native_ms=first ? second_ms : first_ms;
            double candidate_ms=first ? first_ms : second_ms;
            int parity=native_capture.mismatches==0 && candidate_native.mismatches==0;
            if(!parity) {parity_failures++;head_parity_failures++;}
            pairs_completed++;
            printf("{\"type\":\"round\",\"head\":%u,\"round\":%d,\"measured\":%s,"
                   "\"order\":\"%s\",\"native_vs_capture\":",head,current_round,
                   iteration ? "true" : "false",first ? "BA" : "AB");
            print_difference(&native_capture);fputs(",\"candidate_vs_native\":",stdout);
            print_difference(&candidate_native);
            printf(",\"bitwise_equal\":%s,\"native_guard_corrupt_bytes\":%u,"
                   "\"candidate_guard_corrupt_bytes\":%u,\"native_gpu_ms\":%.9g,"
                   "\"candidate_gpu_ms\":%.9g,\"pair_gpu_ms\":%.9g,\"host_pair_ms\":%.9g}\n",
                   parity ? "true" : "false",native_guard,candidate_guard,
                   native_ms,candidate_ms,(double)pair_ms,host_span);
            if(fflush(stdout) || ferror(stdout)) {stdout_failed=1;fail("stdout-round",errno);goto cleanup;}
            if(native_guard || candidate_guard) {
                guard_failures++;fail("output-guard-corruption",0);goto cleanup;
            }
            if(iteration) {native_total+=native_ms;candidate_total+=candidate_ms;host_total+=host_span;}
        }
        heads_completed++;
        printf("{\"type\":\"head\",\"head\":%u,\"rows_per_comparison\":%u,"
               "\"pairs_compared\":4,\"parity_failure_pairs\":%u,\"all_pairs_bitwise_equal\":%s,"
               "\"measured_rounds\":3,\"native_mean_gpu_ms\":%.9g,"
               "\"candidate_mean_gpu_ms\":%.9g,\"mean_host_pair_ms\":%.9g}\n",
               head,ROWS,head_parity_failures,head_parity_failures ? "false" : "true",
               native_total/MEASURED,candidate_total/MEASURED,host_total/MEASURED);
        if(fflush(stdout) || ferror(stdout)) {stdout_failed=1;fail("stdout-head",errno);goto cleanup;}
    }
    for(unsigned arm=0;arm<2;arm++) if(!stable_fd(module_fd[arm],&module_identity[arm])) goto cleanup;
    {
        struct stat final_identity[INPUT_FILES];
        if(!validate_inputs(dirfd,final_identity)) goto cleanup;
        for(unsigned i=0;i<INPUT_FILES;i++) {
            if(!same_identity(&input_identity[i],&final_identity[i])) {
                fail("final-input-identity-changed",0);goto cleanup;
            }
        }
    }
    nominal_complete=1;
    if(parity_failures) fail("bitwise-parity-failure",0);

cleanup:
    if(pending_work && p_hipDeviceSynchronize) {
        cleanup_sync_attempts++;int status=p_hipDeviceSynchronize();
        if(!status) cleanup_sync_ok++;else cleanup_hip(status,"hipDeviceSynchronize");
    }
    for(unsigned i=0;i<3;i++) if(events[i] && p_hipEventDestroy) {
        int status=p_hipEventDestroy(events[i]);
        if(!status) {events_destroyed++;events[i]=NULL;}else cleanup_hip(status,"hipEventDestroy");
    }
    for(unsigned arm=0;arm<2;arm++) if(device_output[arm] && p_hipFree) {
        int status=p_hipFree(device_output[arm]);
        if(!status) {freed++;device_output[arm]=NULL;}else cleanup_hip(status,"hipFree-output");
    }
    if(device_query && p_hipFree) {
        int status=p_hipFree(device_query);
        if(!status) {freed++;device_query=NULL;}else cleanup_hip(status,"hipFree-query");
    }
    if(device_blob && p_hipFree) {
        int status=p_hipFree(device_blob);
        if(!status) {freed++;device_blob=NULL;}else cleanup_hip(status,"hipFree-blob");
    }
    for(unsigned arm=0;arm<2;arm++) if(modules[arm] && p_hipModuleUnload) {
        int status=p_hipModuleUnload(modules[arm]);
        if(!status) {modules_unloaded++;modules[arm]=NULL;}else cleanup_hip(status,"hipModuleUnload");
    }
    for(unsigned arm=0;arm<2;arm++) close_file(&module_fd[arm]);
    close_file(&dirfd);
    free(host_blob);free(captured);free(poison);free(observed[0]);free(observed[1]);
    if(library) {
        if(dlclose(library)) {cleanup_errors++;fail("hip-library-dlclose",0);}
        else library=NULL;
    }
    unsigned remaining_allocations=(device_blob!=NULL)+(device_query!=NULL)+
        (device_output[0]!=NULL)+(device_output[1]!=NULL);
    unsigned remaining_events=(events[0]!=NULL)+(events[1]!=NULL)+(events[2]!=NULL);
    unsigned remaining_modules=(modules[0]!=NULL)+(modules[1]!=NULL);
    int cleanup_complete=!cleanup_errors && !file_close_errors && !remaining_allocations &&
        !remaining_events && !remaining_modules && !library;
    int passed=nominal_complete && !error_reason && !parity_failures && !guard_failures &&
        cleanup_complete && !stdout_failed;
    printf("{\"type\":\"cleanup\",\"complete\":%s,\"diagnostic_passed\":%s,"
           "\"heads_completed\":%u,\"pairs_completed\":%u,\"parity_failure_pairs\":%u,"
           "\"guard_failure_pairs\":%u,\"launch_attempts\":%u,\"launches_ok\":%u,"
           "\"allocations\":%u,\"frees_ok\":%u,\"module_loads\":%u,\"module_unloads_ok\":%u,"
           "\"event_creates\":%u,\"event_destroys_ok\":%u,\"cleanup_sync_attempts\":%u,"
           "\"cleanup_sync_ok\":%u,\"cleanup_errors\":%u,\"file_close_errors\":%u,"
           "\"remaining_allocations\":%u,\"remaining_events\":%u,\"remaining_modules\":%u,"
           "\"error\":",cleanup_complete ? "true" : "false",passed ? "true" : "false",
           heads_completed,pairs_completed,parity_failures,guard_failures,launch_attempts,launches_ok,
           allocations,freed,modules_loaded,modules_unloaded,events_created,events_destroyed,
           cleanup_sync_attempts,cleanup_sync_ok,cleanup_errors,file_close_errors,
           remaining_allocations,remaining_events,remaining_modules);
    if(error_reason) printf("\"%s\"",error_reason);else fputs("null",stdout);
    printf(",\"error_code\":%d,\"last_head\":%d,\"last_round\":%d,"
           "\"scope\":\"partial_asset_component_diagnostic\",\"live_serving_qualified\":false}\n",
           error_code,current_head,current_round);
    if(fflush(stdout) || ferror(stdout)) return 1;
    return passed ? 0 : 1;
}
