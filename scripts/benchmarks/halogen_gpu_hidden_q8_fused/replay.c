/* Fixed, root-owned original-Q8 versus fused compact-Q8 GPU H comparison.
 * Source only. Root compiles/runs later in the pinned Linux/HIP image under its
 * exclusive GPU, owned-job, deadline and memory-reserve guard. No engine hook.
 *
 * Usage (11 arguments, absolute Linux paths):
 * ENGINE ORIGINAL_HSACO CANDIDATE_HSACO CANDIDATE_SHA HIP_LIBRARY HIP_SHA
 * RAW_H_WEIGHT CANDIDATE_H_WEIGHT A_H_INPUT B_H_INPUT NEW_OUTPUT_DIRECTORY
 * All original/weight/input/runtime hashes are fixed below; candidate hash is
 * independently supplied after root's offline code/metadata review.
 *
 * Both W arms use identical original Q8 store7/variant0,6,963,200 bytes.
 * Candidate fuses exact RNE packing and XOR reduction on original single-row geometry. X A/B are four2560
 * BF16 streams. Original grid160/candidate grid160, block256/wave32/LDS0,
 * default stream and unchanged five public arguments.
 *
 * Four warmup + sixteen measured pairs. Arm order alternates every pair;
 * A,B,B,A input sequence balances each input against both arm orders.
 * Each arm has one untimed same-arm primer into a separate resident scratch
 * output, immediately followed by a separately event-timed single launch.
 * Timed output poison precedes the primer; readback/hash follows the event
 * wait. Neither poison nor readback enters an event bracket. Exact frozen
 * output equality is required after every timed launch. Initialization and
 * excluded warmups remain separately reported. No head/token/acceptance claim.
 *
 * Build: gcc -O2 -Wall -Wextra -Werror -D__HIP_PLATFORM_AMD__
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
#define ORIGINAL_CODE_BYTES ((size_t)17704408)
#define ORIGINAL_CODE_OFFSET ((off_t)0x51000)
#define CANDIDATE_CODE_BYTES ((size_t)6352)
#define RAW_WEIGHT_BYTES ((size_t)6963200)
#define CANDIDATE_WEIGHT_BYTES ((size_t)6963200)
#define WIDTH 2560u
#define STREAMS 4u
#define WORDS ((size_t)WIDTH*STREAMS)
#define TENSOR_BYTES (WORDS*sizeof(uint16_t))
#define WARMUPS 4u
#define MEASURED 16u
#define PAIRS (WARMUPS+MEASURED)
#define ENGINE_SHA "ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b"
#define ORIGINAL_CODE_SHA "45941c0579dc3487d07978a50c85cbaa141bbb674b225e708e82d81397334a83"
#define HIP_SHA "6f3c9fe6b655a611e04a9a5a157cb46c425717e2873973f11a67bb6bbf6587b5"
#define RAW_WEIGHT_SHA "018511894df3996e3a2fcb1dff60860c45a808b65036fd38db472b6e985bdd3f"
#define CANDIDATE_WEIGHT_SHA "018511894df3996e3a2fcb1dff60860c45a808b65036fd38db472b6e985bdd3f"
#define ORIGINAL_SYMBOL "_ZN7halogen12_GLOBAL__N_16k_lq8wILi4ELi16ELi1EEEvPKhPKtPtll"
#define CANDIDATE_SYMBOL "halogen_gpu_hidden_q8_fused"

static const char *input_sha[2]={
    "bf43576e6a9d47efb9a15bcba42d74618ade2ea64b025e747d1c6960e2ddff34",
    "0a46c80b3de775d94eee31b1ca4b3927fe8368353f12f5a40314d88591a31711"};
static const char *output_sha[2]={
    "9a5ee795e87adaf5b1778dfc5e108789fbef4731b5d8d323bf6279435c743fcc",
    "cd2b863552798729181fe5670859f3f272ddd694370c2803b84271b3c456a138"};
static const char *output_name[2][2]={
    {"A-original-hidden-u16.bin","B-original-hidden-u16.bin"},
    {"A-candidate-hidden-u16.bin","B-candidate-hidden-u16.bin"}};
struct timing {
    unsigned label,first_arm,measured,completed;
    float original_ms,candidate_ms,sum_single_ms;
    double host_single_ms[2],host_pair_ms;
};
static struct timing timings[PAIRS];
static uint16_t inputs[2][WORDS],poison[WORDS],readback[2][WORDS];
static uint16_t saved_output[2][2][WORDS];
static unsigned output_available[2][2];
static const char *error_reason;
static int error_code;
static unsigned allocations_ok,free_ok,module_loads,module_unloads,copies_ok;
static unsigned launch_attempts,launches_ok,pairs_completed,outputs_equal;
static unsigned priming_launches,timed_launches;
static unsigned event_creates,event_records,event_waits,event_elapsed,event_destroys;
static unsigned cleanup_sync_attempts,cleanup_sync_ok,cleanup_errors,file_close_errors;

static int fail(const char *reason,int code) {
    if (!error_reason) {error_reason=reason;error_code=code;}
    return 0;
}
static int valid_sha(const char *value) {
    return strlen(value)==64 && strspn(value,"0123456789abcdef")==64;
}
static int hash_memory(const void *data,size_t bytes,char result[65]) {
    unsigned char digest[32];unsigned length=0;
    if (!EVP_Digest(data,bytes,digest,&length,EVP_sha256(),NULL) || length!=32)
        return fail("sha256-memory",0);
    for (unsigned i=0;i<32;i++) sprintf(result+2*i,"%02x",digest[i]);
    result[64]=0;return 1;
}
static int same_identity(const struct stat *a,const struct stat *b) {
    return a->st_dev==b->st_dev && a->st_ino==b->st_ino && a->st_size==b->st_size &&
        a->st_mtim.tv_sec==b->st_mtim.tv_sec && a->st_mtim.tv_nsec==b->st_mtim.tv_nsec &&
        a->st_ctim.tv_sec==b->st_ctim.tv_sec && a->st_ctim.tv_nsec==b->st_ctim.tv_nsec;
}
static int open_regular(const char *path,size_t exact,size_t maximum,struct stat *identity) {
    if (path[0]!='/') {fail("input-path-not-absolute",0);return -1;}
    int fd=open(path,O_RDONLY|O_CLOEXEC|O_NOFOLLOW);
    if (fd<0) {fail("input-open",errno);return -1;}
    struct stat st;
    if (fstat(fd,&st) || !S_ISREG(st.st_mode) || st.st_size<=0 ||
        (uint64_t)st.st_size>maximum || (exact && (uint64_t)st.st_size!=exact)) {
        fail("input-file-contract",errno);if(close(fd)) file_close_errors++;return -1;
    }
    *identity=st;return fd;
}
static int verify_identity(int fd,const struct stat *before) {
    struct stat after;
    return (fstat(fd,&after)==0 && same_identity(before,&after)) ||
        fail("input-file-identity-changed",errno);
}
static int read_exact(int fd,void *data,size_t bytes) {
    unsigned char *p=data;
    while(bytes) {
        ssize_t n=read(fd,p,bytes);
        if(n<0 && errno==EINTR) continue;
        if(n<=0) return fail("input-read",errno);
        p+=n;bytes-=(size_t)n;
    }
    return 1;
}
static int write_exact(int fd,const void *data,size_t bytes) {
    const unsigned char *p=data;
    while(bytes) {
        ssize_t n=write(fd,p,bytes);
        if(n<0 && errno==EINTR) continue;
        if(n<=0) return fail("output-write",errno);
        p+=n;bytes-=(size_t)n;
    }
    return fsync(fd)==0 || fail("output-fsync",errno);
}
static int hash_file(int fd,const char *expected) {
    unsigned char block[16384],digest[32];unsigned length=0;char actual[65];
    EVP_MD_CTX *ctx=EVP_MD_CTX_new();int ok=ctx!=NULL;
    if(lseek(fd,0,SEEK_SET)!=0) ok=0;
    if(ok) ok=EVP_DigestInit_ex(ctx,EVP_sha256(),NULL)==1;
    while(ok) {
        ssize_t n=read(fd,block,sizeof block);
        if(n<0 && errno==EINTR) continue;
        if(n<0) {ok=0;break;}
        if(!n) break;
        ok=EVP_DigestUpdate(ctx,block,(size_t)n)==1;
    }
    if(ok) ok=EVP_DigestFinal_ex(ctx,digest,&length)==1 && length==32;
    EVP_MD_CTX_free(ctx);
    if(!ok) return fail("sha256-file",errno);
    for(unsigned i=0;i<32;i++) sprintf(actual+2*i,"%02x",digest[i]);
    actual[64]=0;return !strcmp(actual,expected) || fail("file-sha256-mismatch",0);
}
static int load_bytes(const char *path,const char *expected,void *data,size_t bytes,
                      struct stat *identity) {
    int fd=open_regular(path,bytes,bytes,identity);if(fd<0) return 0;
    char actual[65];
    int ok=read_exact(fd,data,bytes) && verify_identity(fd,identity) &&
        hash_memory(data,bytes,actual);
    if(close(fd)) {file_close_errors++;ok=fail("input-close",errno);}
    if(!ok) return 0;
    return !strcmp(actual,expected) || fail("frozen-file-sha256-mismatch",0);
}
static int verify_again(const char *path,const char *expected,size_t bytes,
                        const struct stat *identity) {
    struct stat current;int fd=open_regular(path,bytes,bytes,&current);if(fd<0) return 0;
    int ok=same_identity(identity,&current) || fail("input-path-identity-changed",0);
    if(ok) ok=hash_file(fd,expected) && verify_identity(fd,identity);
    if(close(fd)) {file_close_errors++;ok=fail("input-close",errno);}
    return ok;
}
static int finite_bf16(const uint16_t *words,size_t count) {
    for(size_t i=0;i<count;i++)
        if((words[i]&0x7f80)==0x7f80) return fail("nonfinite-bf16",0);
    return 1;
}
static int code_header(const unsigned char *b,size_t bytes) {
    /* Raw little-endian ELF64 AMDGPU/HSA ABI4, gfx1151 machine identifier. */
    return (bytes>=64 && !memcmp(b,"\177ELF",4) && b[4]==2 && b[5]==1 &&
            b[7]==64 && b[8]==4 && b[18]==224 && b[19]==0 && b[48]==0x4a) ||
        fail("gfx1151-hsa-abi4-elf-required",0);
}
static double elapsed_ms(const struct timespec *a,const struct timespec *b) {
    return (double)(b->tv_sec-a->tv_sec)*1000.0+
        (double)(b->tv_nsec-a->tv_nsec)/1000000.0;
}
#define API(name,rettype,signature) typedef rettype (*name##_fn) signature; name##_fn p_##name=NULL
#define RESOLVE(name) do { *(void **)(&p_##name)=dlsym(library,#name); \
    if(!p_##name) {fail("missing-" #name,0);goto cleanup;} } while(0)
#define HIP_OK(expression,label) do {hipError_t e=(expression); \
    if(e!=hipSuccess) {fail(label,(int)e);goto cleanup;} } while(0)

int main(int argc,char **argv) {
    if(argc!=12) {
        fputs("Expected ENGINE ORIGINAL_HSACO CANDIDATE_HSACO CANDIDATE_SHA HIP_LIBRARY HIP_SHA RAW_H_WEIGHT CANDIDATE_H_WEIGHT A_H_INPUT B_H_INPUT NEW_OUTPUT_DIRECTORY\n",stderr);
        return 2;
    }
    int dirfd=-1,reportfd=-1,outfd[2][2]={{-1,-1},{-1,-1}};
    int enginefd=-1,codefd[2]={-1,-1},runtimefd=-1;
    void *library=NULL,*code[2]={NULL,NULL},*weights[2]={NULL,NULL};
    void *device_weights[2]={NULL,NULL},*device_inputs[2]={NULL,NULL},*device_outputs[2]={NULL,NULL};
    void *device_priming_outputs[2]={NULL,NULL};
    hipModule_t modules[2]={NULL,NULL};hipFunction_t functions[2]={NULL,NULL};
    hipEvent_t events[2]={NULL,NULL};
    struct stat engine_identity,code_identity[2],runtime_identity,weight_identity[2],input_identity[2];
    size_t code_bytes[2]={ORIGINAL_CODE_BYTES,0};
    const size_t weight_bytes[2]={RAW_WEIGHT_BYTES,CANDIDATE_WEIGHT_BYTES};
    const char *weight_sha[2]={RAW_WEIGHT_SHA,CANDIDATE_WEIGHT_SHA};
    const char *symbols[2]={ORIGINAL_SYMBOL,CANDIDATE_SYMBOL};
    const unsigned grids[2]={160,160};
    int runtime_version=0,driver_version=0,files_rechecked=0,passed=0;
    unsigned output_files_written=0;
    double initialization_host_ms=0;
    struct timespec init_start,init_end;
    API(hipGetDeviceCount,hipError_t,(int *));
    API(hipGetDevicePropertiesR0600,hipError_t,(hipDeviceProp_t *,int));
    API(hipSetDevice,hipError_t,(int));
    API(hipRuntimeGetVersion,hipError_t,(int *));
    API(hipDriverGetVersion,hipError_t,(int *));
    API(hipModuleLoadData,hipError_t,(hipModule_t *,const void *));
    API(hipModuleGetFunction,hipError_t,(hipFunction_t *,hipModule_t,const char *));
    API(hipModuleLaunchKernel,hipError_t,(hipFunction_t,unsigned,unsigned,unsigned,unsigned,unsigned,unsigned,unsigned,hipStream_t,void **,void **));
    API(hipModuleUnload,hipError_t,(hipModule_t));
    API(hipMalloc,hipError_t,(void **,size_t));
    API(hipFree,hipError_t,(void *));
    API(hipMemcpy,hipError_t,(void *,const void *,size_t,hipMemcpyKind));
    API(hipDeviceSynchronize,hipError_t,(void));
    API(hipEventCreateWithFlags,hipError_t,(hipEvent_t *,unsigned));
    API(hipEventRecord,hipError_t,(hipEvent_t,hipStream_t));
    API(hipEventSynchronize,hipError_t,(hipEvent_t));
    API(hipEventElapsedTime,hipError_t,(float *,hipEvent_t,hipEvent_t));
    API(hipEventDestroy,hipError_t,(hipEvent_t));

    if(argv[11][0]!='/' || mkdir(argv[11],0700)) {
        fprintf(stderr,"Exclusive new output directory failed, errno=%d\n",errno);return 2;
    }
    dirfd=open(argv[11],O_DIRECTORY|O_RDONLY|O_CLOEXEC|O_NOFOLLOW);
    if(dirfd<0) {fail("output-directory-open",errno);goto cleanup;}
    reportfd=openat(dirfd,"timing.json",O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC|O_NOFOLLOW,0600);
    for(unsigned arm=0;arm<2;arm++) for(unsigned label=0;label<2;label++)
        outfd[arm][label]=openat(dirfd,output_name[arm][label],O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC|O_NOFOLLOW,0600);
    if(reportfd<0 || outfd[0][0]<0 || outfd[0][1]<0 || outfd[1][0]<0 || outfd[1][1]<0) {
        fail("output-exclusive-create",errno);goto cleanup;
    }
    const char *wave=getenv("HALOGEN_LQ8_WAVE");
    if(wave && strcmp(wave,"1")) {fail("native-lq8-wave-default-or-one-required",0);goto cleanup;}
    if(!valid_sha(argv[4]) || strcmp(argv[6],HIP_SHA)) {fail("candidate-or-runtime-sha-contract",0);goto cleanup;}
    if(clock_gettime(CLOCK_MONOTONIC,&init_start)) {fail("initialization-clock",errno);goto cleanup;}
    enginefd=open_regular(argv[1],ENGINE_BYTES,ENGINE_BYTES,&engine_identity);
    codefd[0]=open_regular(argv[2],ORIGINAL_CODE_BYTES,ORIGINAL_CODE_BYTES,&code_identity[0]);
    codefd[1]=open_regular(argv[3],CANDIDATE_CODE_BYTES,CANDIDATE_CODE_BYTES,&code_identity[1]);
    runtimefd=open_regular(argv[5],0,128u<<20,&runtime_identity);
    if(enginefd<0 || codefd[0]<0 || codefd[1]<0 || runtimefd<0) goto cleanup;
    code_bytes[1]=(size_t)code_identity[1].st_size;
    if(!hash_file(enginefd,ENGINE_SHA) || !verify_identity(enginefd,&engine_identity) ||
       !hash_file(runtimefd,HIP_SHA) || !verify_identity(runtimefd,&runtime_identity)) goto cleanup;
    for(unsigned arm=0;arm<2;arm++) {
        code[arm]=malloc(code_bytes[arm]);if(!code[arm]) {fail("host-code-allocation",errno);goto cleanup;}
        char actual[65];
        if(!read_exact(codefd[arm],code[arm],code_bytes[arm]) ||
           !verify_identity(codefd[arm],&code_identity[arm]) ||
           !hash_memory(code[arm],code_bytes[arm],actual) ||
           !code_header(code[arm],code_bytes[arm])) goto cleanup;
        if(strcmp(actual,arm?argv[4]:ORIGINAL_CODE_SHA)) {fail("codeobject-sha256-mismatch",0);goto cleanup;}
    }
    /* Bind original code to every corresponding byte of the sealed engine. */
    unsigned char block[16384];size_t done=0;
    if(lseek(enginefd,ORIGINAL_CODE_OFFSET,SEEK_SET)!=ORIGINAL_CODE_OFFSET) {fail("engine-code-seek",errno);goto cleanup;}
    while(done<ORIGINAL_CODE_BYTES) {
        size_t n=ORIGINAL_CODE_BYTES-done;if(n>sizeof block) n=sizeof block;
        if(!read_exact(enginefd,block,n)) goto cleanup;
        if(memcmp(block,(const unsigned char *)code[0]+done,n)) {fail("engine-code-byte-mismatch",0);goto cleanup;}
        done+=n;
    }
    if(!verify_identity(enginefd,&engine_identity)) goto cleanup;
    for(unsigned arm=0;arm<2;arm++) {
        weights[arm]=malloc(weight_bytes[arm]);if(!weights[arm]) {fail("host-weight-allocation",errno);goto cleanup;}
        if(!load_bytes(argv[7+arm],weight_sha[arm],weights[arm],weight_bytes[arm],&weight_identity[arm])) goto cleanup;
    }
    for(unsigned label=0;label<2;label++)
        if(!load_bytes(argv[9+label],input_sha[label],inputs[label],TENSOR_BYTES,&input_identity[label]) ||
           !finite_bf16(inputs[label],WORDS)) goto cleanup;
    for(size_t i=0;i<WORDS;i++) poison[i]=0x7fc0;
    if(!verify_again(argv[5],HIP_SHA,(size_t)runtime_identity.st_size,&runtime_identity)) goto cleanup;
    library=dlopen(argv[5],RTLD_NOW|RTLD_LOCAL);
    if(!library) {fail("hip-dlopen",0);fputs(dlerror(),stderr);fputc('\n',stderr);goto cleanup;}
    RESOLVE(hipGetDeviceCount);RESOLVE(hipGetDevicePropertiesR0600);RESOLVE(hipSetDevice);
    RESOLVE(hipRuntimeGetVersion);RESOLVE(hipDriverGetVersion);RESOLVE(hipModuleLoadData);
    RESOLVE(hipModuleGetFunction);RESOLVE(hipModuleLaunchKernel);RESOLVE(hipModuleUnload);
    RESOLVE(hipMalloc);RESOLVE(hipFree);RESOLVE(hipMemcpy);RESOLVE(hipDeviceSynchronize);
    RESOLVE(hipEventCreateWithFlags);RESOLVE(hipEventRecord);RESOLVE(hipEventSynchronize);
    RESOLVE(hipEventElapsedTime);RESOLVE(hipEventDestroy);
    int count=0;hipDeviceProp_t properties;memset(&properties,0,sizeof properties);
    HIP_OK(p_hipGetDeviceCount(&count),"hip-device-count");
    if(count!=1) {fail("exactly-one-gpu-required",count);goto cleanup;}
    HIP_OK(p_hipGetDevicePropertiesR0600(&properties,0),"hip-device-properties");
    if(strcmp(properties.gcnArchName,"gfx1151") || properties.warpSize!=32) {fail("gfx1151-wave32-required",0);goto cleanup;}
    HIP_OK(p_hipSetDevice(0),"hip-set-device");
    HIP_OK(p_hipRuntimeGetVersion(&runtime_version),"hip-runtime-version");
    HIP_OK(p_hipDriverGetVersion(&driver_version),"hip-driver-version");
    for(unsigned arm=0;arm<2;arm++) {
        HIP_OK(p_hipModuleLoadData(&modules[arm],code[arm]),"hip-module-load");module_loads++;
        HIP_OK(p_hipModuleGetFunction(&functions[arm],modules[arm],symbols[arm]),"hip-exact-function");
        HIP_OK(p_hipMalloc(&device_weights[arm],weight_bytes[arm]),"hip-weight-allocation");allocations_ok++;
        HIP_OK(p_hipMalloc(&device_inputs[arm],TENSOR_BYTES),"hip-input-allocation");allocations_ok++;
        HIP_OK(p_hipMalloc(&device_outputs[arm],TENSOR_BYTES),"hip-output-allocation");allocations_ok++;
        HIP_OK(p_hipMalloc(&device_priming_outputs[arm],TENSOR_BYTES),"hip-priming-output-allocation");allocations_ok++;
        if(((uintptr_t)device_weights[arm]&15) || ((uintptr_t)device_inputs[arm]&15) ||
           ((uintptr_t)device_outputs[arm]&15) || ((uintptr_t)device_priming_outputs[arm]&15)) {
            fail("gpu-buffer-alignment16-required",0);goto cleanup;
        }
        HIP_OK(p_hipMemcpy(device_weights[arm],weights[arm],weight_bytes[arm],hipMemcpyHostToDevice),"hip-resident-weight-copy");copies_ok++;
        HIP_OK(p_hipMemcpy(device_inputs[arm],inputs[arm],TENSOR_BYTES,hipMemcpyHostToDevice),"hip-resident-input-copy");copies_ok++;
    }
    for(unsigned i=0;i<2;i++) {HIP_OK(p_hipEventCreateWithFlags(&events[i],0),"hip-event-create");event_creates++;}
    if(clock_gettime(CLOCK_MONOTONIC,&init_end)) {fail("initialization-clock",errno);goto cleanup;}
    initialization_host_ms=elapsed_ms(&init_start,&init_end);
    if(!isfinite(initialization_host_ms) || initialization_host_ms<0) {fail("initialization-finite-time",0);goto cleanup;}

    for(unsigned i=0;i<PAIRS;i++) {
        struct timing *row=&timings[i];
        unsigned label=(i^(i>>1))&1u,first=i&1u;
        row->label=label;row->first_arm=first;row->measured=i>=WARMUPS;
        int64_t k=2560,n=2560;void *x=device_inputs[label];
        void *args[2][5]={{&device_weights[0],&x,&device_outputs[0],&k,&n},
                         {&device_weights[1],&x,&device_outputs[1],&k,&n}};
        void *prime_args[2][5]={{&device_weights[0],&x,&device_priming_outputs[0],&k,&n},
                               {&device_weights[1],&x,&device_priming_outputs[1],&k,&n}};
        struct timespec pair_started,pair_finished;
        if(clock_gettime(CLOCK_MONOTONIC,&pair_started)) {fail("pair-clock-start",errno);goto cleanup;}
        for(unsigned order=0;order<2;order++) {
            unsigned arm=first^order;
            HIP_OK(p_hipMemcpy(device_outputs[arm],poison,TENSOR_BYTES,hipMemcpyHostToDevice),"hip-untimed-output-poison");copies_ok++;
            launch_attempts++;
            HIP_OK(p_hipModuleLaunchKernel(functions[arm],grids[arm],1,1,256,1,1,0,NULL,prime_args[arm],NULL),"hip-untimed-same-arm-primer");
            launches_ok++;priming_launches++;
            struct timespec started,finished;float single_ms=0;
            if(clock_gettime(CLOCK_MONOTONIC,&started)) {fail("single-clock-start",errno);goto cleanup;}
            HIP_OK(p_hipEventRecord(events[0],NULL),"hip-single-start");event_records++;
            launch_attempts++;
            HIP_OK(p_hipModuleLaunchKernel(functions[arm],grids[arm],1,1,256,1,1,0,NULL,args[arm],NULL),"hip-timed-single-launch");
            launches_ok++;timed_launches++;
            HIP_OK(p_hipEventRecord(events[1],NULL),"hip-single-end");event_records++;
            HIP_OK(p_hipEventSynchronize(events[1]),"hip-single-end-wait");event_waits++;
            if(clock_gettime(CLOCK_MONOTONIC,&finished)) {fail("single-clock-end",errno);goto cleanup;}
            row->host_single_ms[arm]=elapsed_ms(&started,&finished);
            HIP_OK(p_hipEventElapsedTime(&single_ms,events[0],events[1]),"hip-single-elapsed");event_elapsed++;
            if(!isfinite(single_ms) || single_ms<=0 || !isfinite(row->host_single_ms[arm]) ||
               row->host_single_ms[arm]<0) {fail("single-finite-times-required",0);goto cleanup;}
            if(arm) row->candidate_ms=single_ms;else row->original_ms=single_ms;
            /* Every timed output is fresh-poisoned and checked before another arm. */
            HIP_OK(p_hipMemcpy(readback[arm],device_outputs[arm],TENSOR_BYTES,hipMemcpyDeviceToHost),"hip-untimed-readback");copies_ok++;
            memcpy(saved_output[arm][label],readback[arm],TENSOR_BYTES);output_available[arm][label]=1;
            char actual[65];
            if(!hash_memory(readback[arm],TENSOR_BYTES,actual) || !finite_bf16(readback[arm],WORDS)) goto cleanup;
            if(strcmp(actual,output_sha[label])) {fail("frozen-original-output-sha256-mismatch",0);goto cleanup;}
            outputs_equal++;
        }
        if(memcmp(readback[0],readback[1],TENSOR_BYTES)) {fail("candidate-original-byte-mismatch",0);goto cleanup;}
        if(clock_gettime(CLOCK_MONOTONIC,&pair_finished)) {fail("pair-clock-end",errno);goto cleanup;}
        row->host_pair_ms=elapsed_ms(&pair_started,&pair_finished);
        row->sum_single_ms=row->original_ms+row->candidate_ms;
        if(!isfinite(row->host_pair_ms) || row->host_pair_ms<0 ||
           !isfinite(row->sum_single_ms) || row->sum_single_ms<=0) {fail("pair-finite-times-required",0);goto cleanup;}
        row->completed=1;pairs_completed++;
    }
    if(!verify_again(argv[1],ENGINE_SHA,ENGINE_BYTES,&engine_identity) ||
       !verify_again(argv[2],ORIGINAL_CODE_SHA,code_bytes[0],&code_identity[0]) ||
       !verify_again(argv[3],argv[4],code_bytes[1],&code_identity[1]) ||
       !verify_again(argv[5],HIP_SHA,(size_t)runtime_identity.st_size,&runtime_identity)) goto cleanup;
    for(unsigned arm=0;arm<2;arm++)
        if(!verify_again(argv[7+arm],weight_sha[arm],weight_bytes[arm],&weight_identity[arm])) goto cleanup;
    for(unsigned label=0;label<2;label++)
        if(!verify_again(argv[9+label],input_sha[label],TENSOR_BYTES,&input_identity[label])) goto cleanup;
    files_rechecked=1;

cleanup:
    /* Failed enqueue can still own stream work; drain before tensor/module free. */
    if(launch_attempts) {
        cleanup_sync_attempts++;
        if(!p_hipDeviceSynchronize || p_hipDeviceSynchronize()!=hipSuccess) cleanup_errors++;
        else cleanup_sync_ok++;
    }
    for(unsigned i=0;i<2;i++) if(events[i]) {
        if(!p_hipEventDestroy || p_hipEventDestroy(events[i])!=hipSuccess) cleanup_errors++;
        else event_destroys++;
    }
    for(unsigned arm=0;arm<2;arm++) {
        if(device_priming_outputs[arm]) {if(!p_hipFree || p_hipFree(device_priming_outputs[arm])!=hipSuccess) cleanup_errors++;else free_ok++;}
        if(device_outputs[arm]) {if(!p_hipFree || p_hipFree(device_outputs[arm])!=hipSuccess) cleanup_errors++;else free_ok++;}
        if(device_inputs[arm]) {if(!p_hipFree || p_hipFree(device_inputs[arm])!=hipSuccess) cleanup_errors++;else free_ok++;}
        if(device_weights[arm]) {if(!p_hipFree || p_hipFree(device_weights[arm])!=hipSuccess) cleanup_errors++;else free_ok++;}
        if(modules[arm]) {if(!p_hipModuleUnload || p_hipModuleUnload(modules[arm])!=hipSuccess) cleanup_errors++;else module_unloads++;}
        if(codefd[arm]>=0 && close(codefd[arm])) file_close_errors++;
        free(code[arm]);free(weights[arm]);
    }
    if(library && dlclose(library)) cleanup_errors++;
    if(enginefd>=0 && close(enginefd)) file_close_errors++;
    if(runtimefd>=0 && close(runtimefd)) file_close_errors++;
    if(cleanup_errors) fail("hip-cleanup",(int)cleanup_errors);
    if(file_close_errors) fail("input-file-close",(int)file_close_errors);
    for(unsigned arm=0;arm<2;arm++) for(unsigned label=0;label<2;label++) {
        if(outfd[arm][label]>=0) {
            if(output_available[arm][label] && write_exact(outfd[arm][label],saved_output[arm][label],TENSOR_BYTES)) output_files_written++;
            if(close(outfd[arm][label])) {file_close_errors++;fail("output-close",errno);}
        }
    }
    passed=!error_reason && files_rechecked && allocations_ok==8 && free_ok==8 &&
        module_loads==2 && module_unloads==2 && copies_ok==4+4*PAIRS &&
        launch_attempts==4*PAIRS && launches_ok==4*PAIRS && pairs_completed==PAIRS &&
        priming_launches==2*PAIRS && timed_launches==2*PAIRS &&
        outputs_equal==2*PAIRS && event_creates==2 && event_destroys==2 &&
        event_records==4*PAIRS && event_waits==2*PAIRS && event_elapsed==2*PAIRS &&
        cleanup_sync_attempts==1 && cleanup_sync_ok==1 && output_files_written==4 &&
        !cleanup_errors && !file_close_errors;
    if(!passed && !error_reason) fail("incomplete-replay-counters",0);
    if(reportfd>=0) {
        int count=dprintf(reportfd,
          "{\"schema\":\"halogen.gpu-hidden-q8-fused.replay.v1\",\"passed\":%s,"
          "\"scope\":\"standalone fixed M4 hidden FC; no full-head/token/acceptance/prefill claim\","
          "\"engine_sha256\":\"%s\",\"original_codeobject_sha256\":\"%s\","
          "\"candidate_codeobject_sha256\":\"%s\",\"candidate_codeobject_bytes\":%zu,"
          "\"runtime_sha256\":\"%s\",\"runtime_version\":%d,\"driver_version\":%d,"
          "\"raw_weight_sha256\":\"%s\",\"candidate_raw_weight_sha256\":\"%s\","
          "\"original_symbol\":\"%s\",\"candidate_symbol\":\"%s\","
          "\"input_sha256\":[\"%s\",\"%s\"],\"expected_output_sha256\":[\"%s\",\"%s\"],"
          "\"K\":2560,\"N\":2560,\"M\":4,\"original_grid\":[160,1,1],\"candidate_grid\":[160,1,1],\"block\":[256,1,1],"
          "\"default_stream\":true,\"dynamic_shared_bytes\":0,\"public_argument_count\":5,"
          "\"raw_weight_bytes\":6963200,\"candidate_raw_weight_bytes\":6963200,"
          "\"input_bytes_each\":20480,\"output_bytes_each\":20480,"
          "\"initialization_host_ms\":%.12g,\"initialization_scope\":\"file/hash checks, module load, resident allocation/upload and event creation; offline compilation excluded\","
          "\"timing_scope\":\"one resident same-arm-primed single launch per default-stream event bracket; host enqueue gaps and events included; primer, poison, readback, hashes and IO excluded\","
          "\"host_pair_scope\":\"both primers, poison, single enqueue/waits, readback and hash checks; not H-only latency\","
          "\"untimed_same_arm_primer_per_timed_launch\":true,\"separate_priming_output\":true,"
          "\"separately_timed_single_launches\":true,\"exact_hash_after_every_timed_launch\":true,"
          "\"warmup_pairs\":4,\"measured_pairs\":16,\"first_pair_is_warmup\":true,"
          "\"balanced_A_B_and_arm_order\":true,\"input_sequence\":\"A,B,B,A repeated\","
          "\"pairs_completed\":%u,\"outputs_equal\":%u,\"launch_attempts\":%u,\"launches_ok\":%u,\"priming_launches\":%u,\"timed_launches\":%u,"
          "\"copies_ok\":%u,\"allocations_ok\":%u,\"free_ok\":%u,"
          "\"module_loads\":%u,\"module_unloads\":%u,\"event_creates\":%u,\"event_records\":%u,"
          "\"event_waits\":%u,\"event_elapsed\":%u,\"event_destroys\":%u,"
          "\"cleanup_sync_attempts\":%u,\"cleanup_sync_ok\":%u,\"cleanup_errors\":%u,\"file_close_errors\":%u,"
          "\"immutable_files_rechecked\":%s,\"output_files_written\":%u,"
          "\"full_head_qualified\":false,\"acceptance_claim\":false,\"end_to_end_speed_claim\":false,"
          "\"prefill_gain_claim\":false,\"tolerance_adjustment\":false,\"arithmetic_fitting\":false,"
          "\"error\":\"%s\",\"error_code\":%d,\"timing_pairs\":[",
          passed?"true":"false",ENGINE_SHA,ORIGINAL_CODE_SHA,valid_sha(argv[4])?argv[4]:"",
          code_bytes[1],HIP_SHA,runtime_version,driver_version,RAW_WEIGHT_SHA,CANDIDATE_WEIGHT_SHA,
          ORIGINAL_SYMBOL,CANDIDATE_SYMBOL,input_sha[0],input_sha[1],output_sha[0],output_sha[1],
          initialization_host_ms,pairs_completed,outputs_equal,launch_attempts,launches_ok,priming_launches,timed_launches,copies_ok,
          allocations_ok,free_ok,module_loads,module_unloads,event_creates,event_records,event_waits,
          event_elapsed,event_destroys,cleanup_sync_attempts,cleanup_sync_ok,cleanup_errors,file_close_errors,
          files_rechecked?"true":"false",output_files_written,error_reason?error_reason:"",error_code);
        if(count<0) {fail("report-write",errno);passed=0;}
        unsigned written=0;
        for(unsigned i=0;i<PAIRS;i++) if(timings[i].completed) {
            struct timing *r=&timings[i];
            if(dprintf(reportfd,"%s{\"sequence\":%u,\"label\":\"%c\",\"first_arm\":\"%s\",\"measured\":%s,\"original_gpu_ms\":%.9g,\"candidate_gpu_ms\":%.9g,\"sum_single_gpu_ms\":%.9g,\"original_host_enqueue_wait_ms\":%.12g,\"candidate_host_enqueue_wait_ms\":%.12g,\"host_pair_elapsed_ms\":%.12g,\"outputs_byte_equal\":true,\"priming_launches\":2,\"timed_launches\":2,\"original_output_sha256\":\"%s\",\"candidate_output_sha256\":\"%s\"}",
                written++?",":"",i,r->label?'B':'A',r->first_arm?"candidate":"original",
                r->measured?"true":"false",(double)r->original_ms,(double)r->candidate_ms,
                (double)r->sum_single_ms,r->host_single_ms[0],r->host_single_ms[1],r->host_pair_ms,
                output_sha[r->label],output_sha[r->label])<0) {fail("report-write",errno);passed=0;}
        }
        if(dprintf(reportfd,"]}\n")<0 || fsync(reportfd)) {fail("report-fsync",errno);passed=0;}
        if(close(reportfd)) {fail("report-close",errno);passed=0;}
    }
    if(dirfd>=0 && close(dirfd)) {fail("output-directory-close",errno);passed=0;}
    fprintf(stderr,"gpu-hidden-q8-fused replay passed=%d pairs=%u/%u launches=%u copies=%u cleanup_errors=%u error=%s code=%d\n",
        passed,pairs_completed,PAIRS,launches_ok,copies_ok,cleanup_errors,error_reason?error_reason:"",error_code);
    return passed?0:1;
}
