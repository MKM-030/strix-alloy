/* Source-only, fixed original-W preparation sibling screen, Halogen 0.16.2.
 * Root owns compiler, isolated HIP image, exclusive GPU, deadline, memory
 * reserve, process lifetime and stock restoration. No engine/provider hook.
 *
 * Usage (seven absolute Linux-path arguments):
 * ENGINE ORIGINAL_HSACO HIP_LIBRARY PACKED SIGNS SCALES NEW_OUTPUT_DIR
 * Native original HSACO only; no newly compiled GPU code and no model reads.
 * One excluded original oracle, one excluded candidate qualification. Require
 * every one of the 26,214,400 BF16 W words to match before any timing.
 * If exact: four excluded warmup pairs, sixteen balanced measured pairs.
 * One launch per arm; no primer, repeated-launch bracket, or retry. Every
 * launch writes poisoned own W, fully completes, and is read/checked exactly.
 * Host submission+full-completion wall and default-stream events are distinct.
 * Poison, readback/hash/validation, uploads and cold initialization are excluded.
 * This measures preparation ONLY; no GEMM/serving/Prefill/Decode/acceptance gain.
 *
 * Root build: gcc -O2 -Wall -Wextra -Werror -D__HIP_PLATFORM_AMD__
 *   -I<reviewed-hip-include> replay.c -ldl -lcrypto -o <new-binary>
 */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <math.h>
#include <openssl/evp.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>
#include <hip/hip_runtime_api.h>
#if !defined(__linux__) || !defined(__x86_64__)
#error Linux x86-64 only
#endif

#define ENGINE_BYTES ((size_t)26052768)
#define CODE_BYTES ((size_t)17704408)
#define CODE_OFFSET ((off_t)0x51000)
#define PACKED_BYTES ((size_t)13107200)
#define SIGNS_BYTES ((size_t)5120)
#define SCALES_BYTES ((size_t)20480)
#define W_BYTES ((size_t)52428800)
#define W_WORDS (W_BYTES/sizeof(uint16_t))
#define WARMUPS 4u
#define MEASURED 16u
#define PAIRS (WARMUPS+MEASURED)
#define RUNS (2u+2u*PAIRS)
#define ENGINE_SHA "ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b"
#define CODE_SHA "45941c0579dc3487d07978a50c85cbaa141bbb674b225e708e82d81397334a83"
#define HIP_SHA "6f3c9fe6b655a611e04a9a5a157cb46c425717e2873973f11a67bb6bbf6587b5"
#define PACKED_SHA "d27fc76fab0646ba5b675f9dd9137c342a39f70aa980acf62f6959f5fdf0245d"
#define SIGNS_SHA "0866b9d9d28380f5f6ea3fdc0fa78a5643db9629c8a3e0094eb01f5b3e33cd7c"
#define SCALES_SHA "dad8e70f72ce13f67692a184cac608e71986d740d43f72201ee52acc4146061e"
#define STOCK_SYMBOL "_ZN7halogen12_GLOBAL__N_113k_ht_deq_origILi4ELb1ELi16EEEvPKjiPKDF16_S5_Pti"
#define CANDIDATE_SYMBOL "_ZN7halogen12_GLOBAL__N_113k_ht_deq_origILi4ELb1ELi8EEEvPKjiPKDF16_S5_Pti"

struct pinned {
    const char *path,*sha;
    size_t bytes;
    struct stat identity;
    int fd;
    unsigned char *host;
};
struct run {
    unsigned arm,phase,pair,first_arm,attempted,completed,exact,timed;
    double host_ms;
    float event_ms;
    char sha[65];
    uint64_t mismatches;
    unsigned examples;
    size_t index[16];
    uint16_t original[16],candidate[16];
};
static struct run runs[RUNS];
static unsigned run_count,qualification_exact,pairs_completed;
static unsigned allocations_ok,free_ok,launch_attempts,launches_ok,copies_ok;
static unsigned poison_ok,pre_sync_ok,full_sync_ok,module_loads,module_unloads;
static unsigned event_creates,event_records,event_waits,event_elapsed,event_destroys;
static unsigned cleanup_sync_attempts,cleanup_sync_ok,cleanup_errors,file_close_errors;
static unsigned qualification_w_files_written;
static const char *error_reason;
static int error_code;

static int fail(const char *reason,int code) {
    if (!error_reason) {error_reason=reason;error_code=code;}
    return 0;
}
static int same_identity(const struct stat *a,const struct stat *b) {
    return a->st_dev==b->st_dev && a->st_ino==b->st_ino && a->st_size==b->st_size &&
        a->st_mtim.tv_sec==b->st_mtim.tv_sec && a->st_mtim.tv_nsec==b->st_mtim.tv_nsec &&
        a->st_ctim.tv_sec==b->st_ctim.tv_sec && a->st_ctim.tv_nsec==b->st_ctim.tv_nsec;
}
static int verify_identity(struct pinned *file) {
    struct stat current;
    return (fstat(file->fd,&current)==0 && same_identity(&file->identity,&current)) ||
        fail("input-file-identity-changed",errno);
}
static int open_pinned(struct pinned *file,size_t maximum) {
    if (file->path[0]!='/') return fail("absolute-input-path-required",0);
    file->fd=open(file->path,O_RDONLY|O_CLOEXEC|O_NOFOLLOW);
    if (file->fd<0) return fail("input-open",errno);
    if (fstat(file->fd,&file->identity) || !S_ISREG(file->identity.st_mode) ||
        file->identity.st_size<=0 || (uint64_t)file->identity.st_size>maximum ||
        (file->bytes && (uint64_t)file->identity.st_size!=file->bytes))
        return fail("input-regular-size-contract",errno);
    file->bytes=(size_t)file->identity.st_size;return 1;
}
static int read_exact(int fd,void *buffer,size_t bytes) {
    unsigned char *p=buffer;
    while (bytes) {
        ssize_t amount=read(fd,p,bytes);
        if (amount<0 && errno==EINTR) continue;
        if (amount<=0) return fail("input-read",errno);
        p+=amount;bytes-=(size_t)amount;
    }
    return 1;
}
static int save_qualification_w(int dirfd,unsigned arm,const void *data) {
    const char *name=arm?"candidate-W.u16":"original-W.u16";
    int fd=openat(dirfd,name,O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC|O_NOFOLLOW,0600);
    if (fd<0) return fail("qualification-w-exclusive-create",errno);
    const unsigned char *p=data;size_t remaining=W_BYTES;int ok=1;
    while (remaining) {
        ssize_t amount=write(fd,p,remaining);
        if (amount<0 && errno==EINTR) continue;
        if (amount<=0) {ok=fail("qualification-w-write",errno);break;}
        p+=amount;remaining-=(size_t)amount;
    }
    if (ok && fsync(fd)) ok=fail("qualification-w-fsync",errno);
    if (close(fd)) {file_close_errors++;ok=fail("qualification-w-close",errno);}
    if (ok) qualification_w_files_written++;
    return ok;
}
static int hash_memory(const void *data,size_t bytes,char sha[65]) {
    unsigned char digest[32];unsigned length=0;
    if (!EVP_Digest(data,bytes,digest,&length,EVP_sha256(),NULL) || length!=32)
        return fail("sha256-memory",0);
    for (unsigned i=0;i<32;i++) sprintf(sha+2*i,"%02x",digest[i]);
    sha[64]=0;return 1;
}
static int hash_file(struct pinned *file) {
    unsigned char block[16384],digest[32];unsigned length=0;char sha[65];
    EVP_MD_CTX *ctx=EVP_MD_CTX_new();int ok=ctx!=NULL;
    if (lseek(file->fd,0,SEEK_SET)!=0) ok=0;
    if (ok) ok=EVP_DigestInit_ex(ctx,EVP_sha256(),NULL)==1;
    while (ok) {
        ssize_t amount=read(file->fd,block,sizeof block);
        if (amount<0 && errno==EINTR) continue;
        if (amount<0) {ok=0;break;}
        if (!amount) break;
        ok=EVP_DigestUpdate(ctx,block,(size_t)amount)==1;
    }
    if (ok) ok=EVP_DigestFinal_ex(ctx,digest,&length)==1 && length==32;
    EVP_MD_CTX_free(ctx);
    if (!ok) return fail("sha256-file",errno);
    for (unsigned i=0;i<32;i++) sprintf(sha+2*i,"%02x",digest[i]);
    sha[64]=0;
    return (!strcmp(sha,file->sha) && verify_identity(file)) ||
        fail("input-sha256-mismatch",0);
}
static int load_pinned(struct pinned *file) {
    file->host=malloc(file->bytes);
    if (!file->host) return fail("host-input-allocation",errno);
    char sha[65];
    if (lseek(file->fd,0,SEEK_SET)!=0 || !read_exact(file->fd,file->host,file->bytes) ||
        !verify_identity(file) || !hash_memory(file->host,file->bytes,sha)) return 0;
    return !strcmp(sha,file->sha) || fail("loaded-input-sha256-mismatch",0);
}
static int verify_again(struct pinned *file) {
    struct stat current;
    int fd=open(file->path,O_RDONLY|O_CLOEXEC|O_NOFOLLOW);
    if (fd<0) return fail("input-reopen",errno);
    int ok=fstat(fd,&current)==0 && same_identity(&file->identity,&current);
    if (close(fd)) {file_close_errors++;ok=0;}
    if (!ok) return fail("input-path-identity-changed",errno);
    return hash_file(file);
}
static double elapsed_ms(struct timespec before,struct timespec after) {
    return (double)(after.tv_sec-before.tv_sec)*1000.0+
        (double)(after.tv_nsec-before.tv_nsec)/1000000.0;
}
static int exact_words(struct run *row,const uint16_t *oracle,const uint16_t *actual) {
    if (!hash_memory(actual,W_BYTES,row->sha)) return 0;
    for (size_t i=0;i<W_WORDS;i++) if (oracle[i]!=actual[i]) {
        row->mismatches++;
        if (row->examples<16) {
            unsigned j=row->examples++;row->index[j]=i;
            row->original[j]=oracle[i];row->candidate[j]=actual[i];
        }
    }
    row->exact=row->mismatches==0;
    return row->exact || fail(row->arm?"candidate-prepared-w-mismatch":"original-prepared-w-changed",0);
}
#define API(name,signature) typedef hipError_t (*name##_fn) signature; name##_fn p_##name=NULL
#define RESOLVE(name) do { *(void **)(&p_##name)=dlsym(library,#name); \
    if (!p_##name) {fail("missing-" #name,0);goto cleanup;} } while (0)
#define HIP_OK(expression,label) do {hipError_t result=(expression); \
    if (result!=hipSuccess) {fail(label,(int)result);goto cleanup;} } while (0)

int main(int argc,char **argv) {
    if (argc!=8) {
        fputs("Expected ENGINE ORIGINAL_HSACO HIP_LIBRARY PACKED SIGNS SCALES NEW_OUTPUT_DIR\n",stderr);
        return 2;
    }
    struct pinned files[6]={
        {.path=argv[1],.sha=ENGINE_SHA,.bytes=ENGINE_BYTES,.fd=-1},
        {.path=argv[2],.sha=CODE_SHA,.bytes=CODE_BYTES,.fd=-1},
        {.path=argv[3],.sha=HIP_SHA,.bytes=0,.fd=-1},
        {.path=argv[4],.sha=PACKED_SHA,.bytes=PACKED_BYTES,.fd=-1},
        {.path=argv[5],.sha=SIGNS_SHA,.bytes=SIGNS_BYTES,.fd=-1},
        {.path=argv[6],.sha=SCALES_SHA,.bytes=SCALES_BYTES,.fd=-1}};
    int dirfd=-1,reportfd=-1,files_rechecked=0,embedded_code_verified=0,passed=0;
    void *library=NULL,*device[4]={NULL,NULL,NULL,NULL};
    hipModule_t module=NULL;hipFunction_t function[2]={NULL,NULL};
    hipEvent_t events[2]={NULL,NULL};
    uint16_t *oracle=NULL,*readback=NULL;char oracle_sha[65]="";
    const size_t device_bytes[4]={PACKED_BYTES,SIGNS_BYTES,SCALES_BYTES,W_BYTES};
    const char *symbols[2]={STOCK_SYMBOL,CANDIDATE_SYMBOL};
    const unsigned blocks[2]={512,256};
    int k=2560,kfast=1,runtime_version=0,driver_version=0;
    double initialization_host_ms=0;
    struct timespec init_before,init_after;
    API(hipGetDeviceCount,(int *));
    API(hipGetDevicePropertiesR0600,(hipDeviceProp_t *,int));
    API(hipSetDevice,(int));
    API(hipRuntimeGetVersion,(int *));
    API(hipDriverGetVersion,(int *));
    API(hipModuleLoadData,(hipModule_t *,const void *));
    API(hipModuleGetFunction,(hipFunction_t *,hipModule_t,const char *));
    API(hipModuleLaunchKernel,(hipFunction_t,unsigned,unsigned,unsigned,unsigned,unsigned,unsigned,unsigned,hipStream_t,void **,void **));
    API(hipModuleUnload,(hipModule_t));
    API(hipMalloc,(void **,size_t));
    API(hipFree,(void *));
    API(hipMemcpy,(void *,const void *,size_t,hipMemcpyKind));
    API(hipMemset,(void *,int,size_t));
    API(hipDeviceSynchronize,(void));
    API(hipEventCreateWithFlags,(hipEvent_t *,unsigned));
    API(hipEventRecord,(hipEvent_t,hipStream_t));
    API(hipEventSynchronize,(hipEvent_t));
    API(hipEventElapsedTime,(float *,hipEvent_t,hipEvent_t));
    API(hipEventDestroy,(hipEvent_t));

    if (argv[7][0]!='/' || mkdir(argv[7],0700)) {
        fprintf(stderr,"Exclusive new output directory failed: errno=%d\n",errno);return 2;
    }
    dirfd=open(argv[7],O_RDONLY|O_DIRECTORY|O_CLOEXEC|O_NOFOLLOW);
    if (dirfd<0) {fail("output-directory-open",errno);goto cleanup;}
    reportfd=openat(dirfd,"timing.json",O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC|O_NOFOLLOW,0600);
    if (reportfd<0) {fail("output-exclusive-create",errno);goto cleanup;}
    if (clock_gettime(CLOCK_MONOTONIC_RAW,&init_before)) {fail("initialization-clock",errno);goto cleanup;}
    for (unsigned i=0;i<6;i++)
        if (!open_pinned(&files[i],i==2?(128u<<20):files[i].bytes)) goto cleanup;
    if (!hash_file(&files[0]) || !hash_file(&files[2])) goto cleanup;
    if (!load_pinned(&files[1])) goto cleanup;
    const unsigned char *code=files[1].host;
    if (memcmp(code,"\177ELF",4) || code[4]!=2 || code[5]!=1 || code[7]!=64 ||
        code[8]!=4 || code[18]!=224 || code[19]!=0 || code[48]!=0x4a ||
        code[49]!=0 || code[50]!=0 || code[51]!=0) {fail("gfx1151-hsa-abi4-code-header",0);goto cleanup;}
    unsigned char block[16384];size_t done=0;
    if (lseek(files[0].fd,CODE_OFFSET,SEEK_SET)!=CODE_OFFSET) {fail("embedded-code-seek",errno);goto cleanup;}
    while (done<CODE_BYTES) {
        size_t amount=CODE_BYTES-done;if (amount>sizeof block) amount=sizeof block;
        if (!read_exact(files[0].fd,block,amount)) goto cleanup;
        if (memcmp(block,code+done,amount)) {fail("original-code-not-exact-engine-code",0);goto cleanup;}
        done+=amount;
    }
    if (!verify_identity(&files[0])) goto cleanup;
    embedded_code_verified=1;
    for (unsigned i=3;i<6;i++) if (!load_pinned(&files[i])) goto cleanup;
    oracle=malloc(W_BYTES);readback=malloc(W_BYTES);
    if (!oracle || !readback) {fail("host-oracle-allocation",errno);goto cleanup;}
    if (!verify_again(&files[2])) goto cleanup;
    library=dlopen(files[2].path,RTLD_NOW|RTLD_LOCAL);
    if (!library) {fail("hip-dlopen",0);fputs(dlerror(),stderr);fputc('\n',stderr);goto cleanup;}
    RESOLVE(hipGetDeviceCount);RESOLVE(hipGetDevicePropertiesR0600);RESOLVE(hipSetDevice);
    RESOLVE(hipRuntimeGetVersion);RESOLVE(hipDriverGetVersion);RESOLVE(hipModuleLoadData);
    RESOLVE(hipModuleGetFunction);RESOLVE(hipModuleLaunchKernel);RESOLVE(hipModuleUnload);
    RESOLVE(hipMalloc);RESOLVE(hipFree);RESOLVE(hipMemcpy);RESOLVE(hipMemset);
    RESOLVE(hipDeviceSynchronize);RESOLVE(hipEventCreateWithFlags);RESOLVE(hipEventRecord);
    RESOLVE(hipEventSynchronize);RESOLVE(hipEventElapsedTime);RESOLVE(hipEventDestroy);
    int count=0;hipDeviceProp_t properties;memset(&properties,0,sizeof properties);
    HIP_OK(p_hipGetDeviceCount(&count),"hip-device-count");
    if (count!=1) {fail("exactly-one-gpu-required",count);goto cleanup;}
    HIP_OK(p_hipGetDevicePropertiesR0600(&properties,0),"hip-device-properties");
    if (strcmp(properties.gcnArchName,"gfx1151") || properties.warpSize!=32) {fail("gfx1151-wave32-required",0);goto cleanup;}
    HIP_OK(p_hipSetDevice(0),"hip-set-device");
    HIP_OK(p_hipRuntimeGetVersion(&runtime_version),"hip-runtime-version");
    HIP_OK(p_hipDriverGetVersion(&driver_version),"hip-driver-version");
    HIP_OK(p_hipModuleLoadData(&module,code),"hip-original-module-load");module_loads++;
    for (unsigned arm=0;arm<2;arm++)
        HIP_OK(p_hipModuleGetFunction(&function[arm],module,symbols[arm]),"hip-exact-export");
    for (unsigned i=0;i<4;i++) {
        HIP_OK(p_hipMalloc(&device[i],device_bytes[i]),"hip-owned-allocation");allocations_ok++;
        if (!device[i] || ((uintptr_t)device[i]&15)) {fail("owned-aligned-device-buffer",0);goto cleanup;}
        for (unsigned j=0;j<i;j++) if (device[i]==device[j]) {fail("owned-buffer-alias",0);goto cleanup;}
        if (i<3) {HIP_OK(p_hipMemcpy(device[i],files[i+3].host,device_bytes[i],hipMemcpyHostToDevice),"hip-fixed-input-upload");copies_ok++;}
    }
    HIP_OK(p_hipDeviceSynchronize(),"hip-upload-completion");
    if (clock_gettime(CLOCK_MONOTONIC_RAW,&init_after)) {fail("initialization-clock",errno);goto cleanup;}
    initialization_host_ms=elapsed_ms(init_before,init_after);
    if (!isfinite(initialization_host_ms) || initialization_host_ms<0) {fail("initialization-finite-time",0);goto cleanup;}

    /* Fixed launch order: excluded original, excluded candidate, then20 pairs.
     * Create timing events only after both full-W qualifications have passed. */
    for (unsigned sequence=0;sequence<RUNS;sequence++) {
        struct run *row=&runs[run_count++];
        unsigned ordinal=sequence<2?0:(sequence-2)/2;
        row->phase=sequence<2?0:(ordinal<WARMUPS?1:2);
        row->pair=ordinal;row->first_arm=ordinal&1u;
        row->arm=sequence<2?sequence:(row->first_arm^((sequence-2)&1u));
        row->timed=sequence>=2;
        if (sequence==2) {
            if (qualification_exact!=2) {fail("qualification-required-before-events",0);goto cleanup;}
            for (unsigned i=0;i<2;i++) {HIP_OK(p_hipEventCreateWithFlags(&events[i],0),"hip-event-create");event_creates++;}
        }
        /* Distinct arm poisons prevent common untouched bytes from passing the
         * original-oracle/candidate comparison. Every launch still overwrites
         * one own W; neither arm can inherit the preceding arm's contents. */
        HIP_OK(p_hipMemset(device[3],row->arm?0xa5:0xff,W_BYTES),"hip-untimed-w-poison");poison_ok++;
        HIP_OK(p_hipDeviceSynchronize(),"hip-untimed-pre-launch-completion");pre_sync_ok++;
        void *args[6]={&device[0],&k,&device[1],&device[2],&device[3],&kfast};
        struct timespec before,after;
        if (row->timed) {
            if (clock_gettime(CLOCK_MONOTONIC_RAW,&before)) {fail("single-clock-start",errno);goto cleanup;}
            HIP_OK(p_hipEventRecord(events[0],NULL),"hip-single-start-event");event_records++;
        }
        row->attempted=1;launch_attempts++;
        HIP_OK(p_hipModuleLaunchKernel(function[row->arm],20,80,1,blocks[row->arm],1,1,0,NULL,args,NULL),"hip-single-original-kernel-launch");launches_ok++;
        if (row->timed) {HIP_OK(p_hipEventRecord(events[1],NULL),"hip-single-end-event");event_records++;}
        HIP_OK(p_hipDeviceSynchronize(),"hip-full-launch-completion");full_sync_ok++;
        if (row->timed) {
            HIP_OK(p_hipEventSynchronize(events[1]),"hip-end-event-completion");event_waits++;
            if (clock_gettime(CLOCK_MONOTONIC_RAW,&after)) {fail("single-clock-end",errno);goto cleanup;}
            row->host_ms=elapsed_ms(before,after);
            HIP_OK(p_hipEventElapsedTime(&row->event_ms,events[0],events[1]),"hip-single-event-elapsed");event_elapsed++;
            if (!isfinite(row->host_ms) || row->host_ms<0 || !isfinite(row->event_ms) || row->event_ms<=0) {fail("single-finite-times-required",0);goto cleanup;}
        }
        HIP_OK(p_hipMemcpy(readback,device[3],W_BYTES,hipMemcpyDeviceToHost),"hip-untimed-full-w-readback");copies_ok++;
        row->completed=1;
        /* Preserve both excluded qualification outputs, including a mismatched
         * candidate, for root's independent complete-W recomputation. No timed
         * output is written. An artifact write failure prevents all timing. */
        if (sequence<2 && !save_qualification_w(dirfd,row->arm,readback)) goto cleanup;
        if (sequence==0) {
            memcpy(oracle,readback,W_BYTES);
            if (!hash_memory(oracle,W_BYTES,oracle_sha)) goto cleanup;
            memcpy(row->sha,oracle_sha,sizeof oracle_sha);row->exact=1;
        } else if (!exact_words(row,oracle,readback)) goto cleanup;
        if (sequence<2) qualification_exact++;
        else if (((sequence-2)&1u)==1) pairs_completed++;
    }
    for (unsigned i=0;i<6;i++) if (!verify_again(&files[i])) goto cleanup;
    files_rechecked=1;

cleanup:
    /* A failed enqueue can still own work. Drain before freeing any buffer. */
    if (launch_attempts || allocations_ok) {
        cleanup_sync_attempts++;
        if (!p_hipDeviceSynchronize || p_hipDeviceSynchronize()!=hipSuccess) cleanup_errors++;
        else cleanup_sync_ok++;
    }
    for (unsigned i=0;i<2;i++) if (events[i]) {
        if (!p_hipEventDestroy || p_hipEventDestroy(events[i])!=hipSuccess) cleanup_errors++;
        else event_destroys++;
    }
    for (unsigned i=0;i<4;i++) if (device[i]) {
        if (!p_hipFree || p_hipFree(device[i])!=hipSuccess) cleanup_errors++;
        else free_ok++;
    }
    if (module) {
        if (!p_hipModuleUnload || p_hipModuleUnload(module)!=hipSuccess) cleanup_errors++;
        else module_unloads++;
    }
    if (library && dlclose(library)) cleanup_errors++;
    for (unsigned i=0;i<6;i++) {
        if (files[i].fd>=0 && close(files[i].fd)) file_close_errors++;
        free(files[i].host);
    }
    free(oracle);free(readback);
    if (cleanup_errors) fail("hip-cleanup",(int)cleanup_errors);
    if (file_close_errors) fail("input-file-close",(int)file_close_errors);
    passed=!error_reason && files_rechecked && qualification_exact==2 && qualification_w_files_written==2 &&
        pairs_completed==PAIRS && run_count==RUNS && launch_attempts==RUNS &&
        launches_ok==RUNS && poison_ok==RUNS && pre_sync_ok==RUNS && full_sync_ok==RUNS &&
        copies_ok==3+RUNS && allocations_ok==4 && free_ok==4 &&
        module_loads==1 && module_unloads==1 && event_creates==2 && event_destroys==2 &&
        event_records==4*PAIRS && event_waits==2*PAIRS && event_elapsed==2*PAIRS &&
        cleanup_sync_attempts==1 && cleanup_sync_ok==1 && !cleanup_errors && !file_close_errors;
    if (!passed && !error_reason) fail("incomplete-fixed-screen-counters",0);
    if (reportfd>=0) {
        int written=dprintf(reportfd,
            "{\"schema\":\"halogen.prefill-deq.replay.v1\",\"passed\":%s,"
            "\"scope\":\"standalone selected-QKV original BF16 weight preparation only; no GEMM or serving benchmark\","
            "\"engine_sha256\":\"%s\",\"codeobject_sha256\":\"%s\",\"original_code_from_engine_verified\":%s,"
            "\"runtime_sha256\":\"%s\",\"runtime_version\":%d,\"driver_version\":%d,"
            "\"packed_sha256\":\"%s\",\"signs_sha256\":\"%s\",\"scales_sha256\":\"%s\","
            "\"packed_bytes\":13107200,\"signs_bytes\":5120,\"scales_bytes\":20480,"
            "\"original_symbol\":\"%s\",\"candidate_symbol\":\"%s\",\"oracle_sha256\":\"%s\","
            "\"N\":10240,\"K\":2560,\"descriptor_mode\":4,\"PRE\":1,\"KFAST\":1,"
            "\"grid\":[20,80,1],\"original_block\":[512,1,1],\"candidate_block\":[256,1,1],"
            "\"original_W16\":1,\"candidate_W16\":0,\"default_stream\":true,\"dynamic_shared_bytes\":0,"
            "\"static_lds_bytes_each\":65536,\"public_argument_count\":6,\"W_bytes\":52428800,"
            "\"W_words\":26214400,\"fixed_run_limit\":42,\"qualification_exact\":%u,"
            "\"qualification_W_files\":[\"original-W.u16\",\"candidate-W.u16\"],"
            "\"qualification_W_file_bytes_each\":52428800,\"qualification_W_files_written\":%u,"
            "\"timed_output_files_written\":0,"
            "\"warmup_pairs\":4,\"measured_pairs\":16,\"balanced_pair_order\":true,"
            "\"qualification_before_timing\":true,\"raw_equality_after_every_launch\":true,\"primer_launches\":0,"
            "\"original_poison_byte\":255,\"candidate_poison_byte\":165,"
            "\"initialization_host_ms\":%.12g,"
            "\"initialization_scope\":\"file and embedded-code verification, HIP/module setup, allocations, resident uploads and upload completion; qualification and timing excluded\","
            "\"host_timing_scope\":\"one launch plus start/end event submissions, full device completion and end-event completion\","
            "\"event_timing_scope\":\"one original prepared-W launch between default-stream events; no primer\","
            "\"timing_excludes\":\"poison and pre-launch completion, readback, exact comparison, hashes, files and cold initialization\","
            "\"run_count\":%u,\"pairs_completed\":%u,\"launch_attempts\":%u,\"launches_ok\":%u,"
            "\"poison_ok\":%u,\"pre_sync_ok\":%u,\"full_sync_ok\":%u,\"copies_ok\":%u,"
            "\"allocations_ok\":%u,\"free_ok\":%u,\"module_loads\":%u,\"module_unloads\":%u,"
            "\"event_creates\":%u,\"event_records\":%u,\"event_waits\":%u,\"event_elapsed\":%u,\"event_destroys\":%u,"
            "\"cleanup_sync_attempts\":%u,\"cleanup_sync_ok\":%u,\"cleanup_errors\":%u,\"file_close_errors\":%u,"
            "\"immutable_files_rechecked\":%s,\"gemm_qualified\":false,\"prefill_gain_claim\":false,"
            "\"decode_gain_claim\":false,\"acceptance_claim\":false,\"tolerance_adjustment\":false,"
            "\"error\":\"%s\",\"error_code\":%d,\"runs\":[",
            passed?"true":"false",ENGINE_SHA,CODE_SHA,embedded_code_verified?"true":"false",HIP_SHA,runtime_version,driver_version,
            PACKED_SHA,SIGNS_SHA,SCALES_SHA,STOCK_SYMBOL,CANDIDATE_SYMBOL,oracle_sha,
            qualification_exact,qualification_w_files_written,initialization_host_ms,run_count,pairs_completed,launch_attempts,launches_ok,
            poison_ok,pre_sync_ok,full_sync_ok,copies_ok,allocations_ok,free_ok,module_loads,module_unloads,
            event_creates,event_records,event_waits,event_elapsed,event_destroys,cleanup_sync_attempts,
            cleanup_sync_ok,cleanup_errors,file_close_errors,files_rechecked?"true":"false",
            error_reason?error_reason:"",error_code);
        if (written<0) {fail("report-write",errno);passed=0;}
        for (unsigned i=0;i<run_count;i++) {
            const struct run *row=&runs[i];
            if (dprintf(reportfd,"%s{\"sequence\":%u,\"arm\":\"%s\",\"phase\":\"%s\",\"pair\":%u,\"first_arm\":\"%s\",\"attempted\":%s,\"completed\":%s,\"exact\":%s,\"timed\":%s,\"measured\":%s,\"host_ms\":",
                i?",":"",i,row->arm?"candidate":"original",row->phase==0?"qualification":(row->phase==1?"warmup":"measured"),
                row->pair,row->first_arm?"candidate":"original",row->attempted?"true":"false",row->completed?"true":"false",
                row->exact?"true":"false",row->timed?"true":"false",row->phase==2 && row->exact?"true":"false")<0) {fail("report-write",errno);passed=0;}
            if (row->timed && row->completed && row->exact) {
                if (dprintf(reportfd,"%.12g,\"event_ms\":%.9g",row->host_ms,(double)row->event_ms)<0) {fail("report-write",errno);passed=0;}
            } else if (dprintf(reportfd,"null,\"event_ms\":null")<0) {fail("report-write",errno);passed=0;}
            if (dprintf(reportfd,",\"sha256\":\"%s\",\"word_mismatches\":%" PRIu64 ",\"mismatch_examples\":[",row->sha,row->mismatches)<0) {fail("report-write",errno);passed=0;}
            for (unsigned j=0;j<row->examples;j++)
                if (dprintf(reportfd,"%s{\"word_index\":%zu,\"original_u16\":%u,\"candidate_u16\":%u}",j?",":"",row->index[j],(unsigned)row->original[j],(unsigned)row->candidate[j])<0) {fail("report-write",errno);passed=0;}
            if (dprintf(reportfd,"]}")<0) {fail("report-write",errno);passed=0;}
        }
        if (dprintf(reportfd,"],\"timing_pairs\":[")<0) {fail("report-write",errno);passed=0;}
        unsigned pairs_written=0;
        for (unsigned i=0;i<PAIRS;i++) {
            unsigned a=2+2*i,b=a+1;
            if (b>=run_count || !runs[a].completed || !runs[b].completed ||
                !runs[a].exact || !runs[b].exact) continue;
            const struct run *original=runs[a].arm?&runs[b]:&runs[a];
            const struct run *candidate=runs[a].arm?&runs[a]:&runs[b];
            if (dprintf(reportfd,"%s{\"sequence\":%u,\"measured\":%s,\"first_arm\":\"%s\",\"original_gpu_ms\":%.9g,\"candidate_gpu_ms\":%.9g,\"original_host_enqueue_wait_ms\":%.12g,\"candidate_host_enqueue_wait_ms\":%.12g,\"original_output_sha256\":\"%s\",\"candidate_output_sha256\":\"%s\",\"outputs_byte_equal\":true,\"all_W_words_checked_each_arm\":26214400,\"single_launches\":2,\"priming_launches\":0}",
                pairs_written++?",":"",i,i>=WARMUPS?"true":"false",runs[a].first_arm?"candidate":"original",
                (double)original->event_ms,(double)candidate->event_ms,original->host_ms,candidate->host_ms,
                original->sha,candidate->sha)<0) {fail("report-write",errno);passed=0;}
        }
        if (dprintf(reportfd,"]}\n")<0 || fsync(reportfd)) {fail("report-fsync",errno);passed=0;}
        if (close(reportfd)) {fail("report-close",errno);passed=0;}
    }
    if (dirfd>=0 && close(dirfd)) {fail("output-directory-close",errno);passed=0;}
    fprintf(stderr,"prefill-deq passed=%d qualifications=%u pairs=%u/%u launches=%u/%u cleanup_errors=%u error=%s code=%d\n",
        passed,qualification_exact,pairs_completed,PAIRS,launches_ok,RUNS,cleanup_errors,error_reason?error_reason:"",error_code);
    return passed?0:1;
}
