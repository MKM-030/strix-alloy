/* Standalone host replay of original Halogen 0.16.2 Q8 FC kernels.
 * Root alone compiles/runs in the pinned Linux/HIP environment under the outer
 * 22 GiB admission / 18 GiB continuous reserve and deadline guard.
 * All FC inputs are explicit normalized BF16 words. In particular, a
 * CPU-prepared embedding input does not qualify native embedding RMS.
 * No replacement arithmetic, decoded FP32 weights, seed-add, head, acceptance
 * or speed claim is implemented here. Exact raw Q8 bytes are copied unchanged.
 *
 * Source contract: row-major Q8 store7/variant0, K=N=2560; each row contains
 * K unsigned codes followed by K/64 [FP16 scale, FP16 bias] pairs. Thus every
 * row is 2720 bytes and each matrix is 6963200 bytes. A/B embedding inputs are
 * 2560 BF16 words; A/B hidden inputs are four contiguous 2560-word streams.
 * HALOGEN_LQ8_WAVE is unset (native default1) or exactly1. Fixed original
 * k_lq8w<1,16,1>/<4,16,1> shaders launch grid160/block256, default stream,
 * dynamic/static LDS0, wave32. User args W/X/Y at0/8/16 and i64 K/N at24/32;
 * kernarg40/alignment8 has no hidden arguments. Native affine Q8 dequant
 * rounds decoded weights to BF16 before packed BF16 dot2 FP32 accumulation;
 * the final FC store is BF16 RNE. No CPU arithmetic implements a substitute.
 *
 * Build (root only): gcc -O2 -Wall -Wextra -Werror -D__HIP_PLATFORM_AMD__
 *   -I<reviewed-hip-include> halogen0162_fc_replay.c -ldl -lcrypto -o <new-binary>
 * Usage (17 arguments, absolute file paths, independently supplied SHA256s):
 *   replay ENGINE HSACO HIP_LIBRARY HIP_SHA E_WEIGHT E_WEIGHT_SHA H_WEIGHT
 *     H_WEIGHT_SHA A_E_INPUT A_E_SHA A_H_INPUT A_H_SHA B_E_INPUT B_E_SHA
 *     B_H_INPUT B_H_SHA NEW_OUTPUT_DIRECTORY
 */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <openssl/evp.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>
#include <hip/hip_runtime_api.h>

#if !defined(__linux__) || !defined(__x86_64__)
#error Linux x86-64 only
#endif
#define ENGINE_BYTES ((size_t)26052768)
#define CODE_BYTES ((size_t)17704408)
#define CODE_OFFSET ((off_t)0x51000)
#define WIDTH ((size_t)2560)
#define STREAMS ((size_t)4)
#define MAX_WORDS (WIDTH * STREAMS)
#define MAX_TENSOR_BYTES (MAX_WORDS * sizeof(uint16_t))
#define WEIGHT_ROW_BYTES ((size_t)2720)
#define WEIGHT_BYTES ((size_t)6963200)
#define ENGINE_SHA "ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b"
#define CODE_SHA "45941c0579dc3487d07978a50c85cbaa141bbb674b225e708e82d81397334a83"
#define KERNEL_EMBEDDING "_ZN7halogen12_GLOBAL__N_16k_lq8wILi1ELi16ELi1EEEvPKhPKtPtll"
#define KERNEL_HIDDEN "_ZN7halogen12_GLOBAL__N_16k_lq8wILi4ELi16ELi1EEEvPKhPKtPtll"

struct fixture {
    uint16_t input[MAX_WORDS], output[MAX_WORDS];
    size_t words;
    unsigned branch, streams, vectors_completed, output_copied;
    char input_sha[65], output_sha[65];
    unsigned completed, nonfinite_output;
    struct stat input_identity;
};
static struct fixture fixtures[4];
static const char *fixture_ids[4] = {"A-embedding", "A-hidden", "B-embedding", "B-hidden"};
static const char *output_names[4] = {"A-embedding-fc-u16.bin", "A-hidden-fc-u16.bin",
                                      "B-embedding-fc-u16.bin", "B-hidden-fc-u16.bin"};
static const char *error_reason;
static unsigned launch_attempts, launches_ok, synchronizations_ok, copies_ok;
static unsigned cleanup_errors, allocations_ok, free_ok, module_loads, module_unloads;
static int error_code;

static int fail(const char *reason, int code) {
    if (!error_reason) { error_reason=reason; error_code=code; }
    return 0;
}
static int valid_sha(const char *s) {
    return strlen(s)==64 && strspn(s,"0123456789abcdef")==64;
}
static int hash_memory(const void *data,size_t length,char text[65]) {
    unsigned char value[32]; unsigned n=0;
    if (!EVP_Digest(data,length,value,&n,EVP_sha256(),NULL) || n!=32)
        return fail("sha256-memory",0);
    for (unsigned i=0;i<32;i++) sprintf(text+2*i,"%02x",value[i]);
    text[64]=0; return 1;
}
static int same_identity(const struct stat *a,const struct stat *b) {
    return a->st_dev==b->st_dev && a->st_ino==b->st_ino && a->st_size==b->st_size &&
        a->st_mtim.tv_sec==b->st_mtim.tv_sec && a->st_mtim.tv_nsec==b->st_mtim.tv_nsec &&
        a->st_ctim.tv_sec==b->st_ctim.tv_sec && a->st_ctim.tv_nsec==b->st_ctim.tv_nsec;
}
static int open_regular(const char *path,size_t expected,size_t maximum,struct stat *identity) {
    if (path[0]!='/') {fail("input-path-not-absolute",0);return -1;}
    int fd=open(path,O_RDONLY|O_CLOEXEC|O_NOFOLLOW);
    if (fd<0) {fail("input-open",errno);return -1;}
    struct stat st;
    if (fstat(fd,&st) || !S_ISREG(st.st_mode) || st.st_size<=0 ||
        (uint64_t)st.st_size>maximum || (expected && (uint64_t)st.st_size!=expected)) {
        fail("input-file-contract",errno);close(fd);return -1;
    }
    if (identity) *identity=st;
    return fd;
}
static int read_exact(int fd,void *data,size_t bytes) {
    unsigned char *p=data;
    while (bytes) {
        ssize_t n=read(fd,p,bytes);
        if (n<0 && errno==EINTR) continue;
        if (n<=0) return fail("input-read",errno);
        p+=n;bytes-=(size_t)n;
    }
    return 1;
}
static int write_exact(int fd,const void *data,size_t bytes) {
    const unsigned char *p=data;
    while (bytes) {
        ssize_t n=write(fd,p,bytes);
        if (n<0 && errno==EINTR) continue;
        if (n<=0) return fail("output-write",errno);
        p+=n;bytes-=(size_t)n;
    }
    return fsync(fd)==0 || fail("output-fsync",errno);
}
static int hash_file(int fd,const char *expected) {
    unsigned char block[16384],value[32]; unsigned n=0; char text[65];
    EVP_MD_CTX *ctx=EVP_MD_CTX_new(); int ok=ctx!=NULL;
    if (lseek(fd,0,SEEK_SET)!=0) ok=0;
    if (ok) ok=EVP_DigestInit_ex(ctx,EVP_sha256(),NULL)==1;
    while (ok) {
        ssize_t count=read(fd,block,sizeof block);
        if (count<0 && errno==EINTR) continue;
        if (count<0) {ok=0;break;}
        if (!count) break;
        ok=EVP_DigestUpdate(ctx,block,(size_t)count)==1;
    }
    if (ok) ok=EVP_DigestFinal_ex(ctx,value,&n)==1 && n==32;
    EVP_MD_CTX_free(ctx);
    if (!ok) return fail("file-sha256",errno);
    for (unsigned i=0;i<32;i++) sprintf(text+2*i,"%02x",value[i]);
    text[64]=0;
    return !strcmp(text,expected) || fail("file-sha256-mismatch",0);
}
static int verify_identity(int fd,const struct stat *before) {
    struct stat after;
    return (fstat(fd,&after)==0 && same_identity(before,&after)) || fail("input-file-identity-changed",errno);
}
static int load_bytes(const char *path,const char *expected,void *data,size_t bytes,char actual[65],struct stat *identity) {
    if (!valid_sha(expected)) return fail("fixture-sha-format",0);
    struct stat before;
    int fd=open_regular(path,bytes,bytes,&before);
    if (fd<0) return 0;
    int ok=read_exact(fd,data,bytes) && verify_identity(fd,&before) && hash_memory(data,bytes,actual);
    if (ok && identity) *identity=before;
    if (close(fd)) ok=fail("input-close",errno);
    if (!ok) return 0;
    return !strcmp(actual,expected) || fail("fixture-sha256-mismatch",0);
}
static int load_fixture(struct fixture *f,unsigned branch,const char *path,const char *expected) {
    f->branch=branch; f->streams=branch?4:1; f->words=WIDTH*f->streams;
    if (!load_bytes(path,expected,f->input,f->words*sizeof(uint16_t),f->input_sha,&f->input_identity)) return 0;
    for (size_t i=0;i<f->words;i++) {
        if ((f->input[i]&0x7f80)==0x7f80) return fail("nonfinite-bf16-input",0);
        f->output[i]=0x7fc0; /* Poison the unfilled output only. */
    }
    return 1;
}
static int verify_again(const char *path,const char *expected,size_t bytes,const struct stat *identity) {
    struct stat current;
    int fd=open_regular(path,bytes,bytes,&current);
    if (fd<0) return 0;
    int ok=same_identity(identity,&current) || fail("input-path-identity-changed",0);
    if (ok) ok=hash_file(fd,expected) && verify_identity(fd,identity);
    if (close(fd)) ok=fail("input-close",errno);
    return ok;
}

#define API(name,rettype,signature) typedef rettype (*name##_fn) signature; name##_fn p_##name=NULL
#define RESOLVE(name) do { *(void **)(&p_##name)=dlsym(library,#name); \
    if (!p_##name) {fail("missing-" #name,0);goto cleanup;} } while (0)
#define HIP_OK(expression,label) do { hipError_t e=(expression); \
    if (e!=hipSuccess) {fail(label,(int)e);goto cleanup;} } while (0)

int main(int argc,char **argv) {
    if (argc!=18) {
        fputs("Expected ENGINE HSACO HIP_LIBRARY HIP_SHA E_WEIGHT E_WEIGHT_SHA H_WEIGHT H_WEIGHT_SHA A_E_INPUT A_E_SHA A_H_INPUT A_H_SHA B_E_INPUT B_E_SHA B_H_INPUT B_H_SHA NEW_OUTPUT_DIRECTORY\n",stderr);
        return 2;
    }
    int dirfd=-1,reportfd=-1,outfd[4]={-1,-1,-1,-1},enginefd=-1,codefd=-1,runtimefd=-1;
    void *library=NULL,*code=NULL,*weights[2]={NULL,NULL};
    void *device_input=NULL,*device_output=NULL,*device_weights[2]={NULL,NULL};
    hipModule_t module=NULL; hipFunction_t functions[2]={NULL,NULL};
    struct stat engine_identity,code_identity,runtime_identity,weight_identity[2];
    char weight_sha[2][65]={{0},{0}},code_sha[65]={0};
    int runtime_version=0,driver_version=0,passed=0,files_rechecked=0;
    unsigned output_files_written=0,file_close_errors=0;
    const char *wave=getenv("HALOGEN_LQ8_WAVE");
    const char *wave_binding=wave?(strcmp(wave,"1")?"rejected-non-one":"1"):"unset-native-default1";
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

    if (argv[17][0]!='/' || mkdir(argv[17],0700)) {
        fprintf(stderr,"Exclusive new output directory failed, errno=%d\n",errno);return 2;
    }
    dirfd=open(argv[17],O_DIRECTORY|O_RDONLY|O_CLOEXEC|O_NOFOLLOW);
    if (dirfd<0) {fail("output-directory-open",errno);goto cleanup;}
    reportfd=openat(dirfd,"replay.json",O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC|O_NOFOLLOW,0600);
    for (unsigned i=0;i<4;i++)
        outfd[i]=openat(dirfd,output_names[i],O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC|O_NOFOLLOW,0600);
    if (reportfd<0 || outfd[0]<0 || outfd[1]<0 || outfd[2]<0 || outfd[3]<0) {
        fail("output-exclusive-create",errno);goto cleanup;
    }
    if (wave && strcmp(wave,"1")) {fail("native-lq8-wave-default-or-one-required",0);goto cleanup;}
    if (!valid_sha(argv[4])) {fail("runtime-sha-format",0);goto cleanup;}
    enginefd=open_regular(argv[1],ENGINE_BYTES,ENGINE_BYTES,&engine_identity);
    codefd=open_regular(argv[2],CODE_BYTES,CODE_BYTES,&code_identity);
    runtimefd=open_regular(argv[3],0,128<<20,&runtime_identity);
    if (enginefd<0 || codefd<0 || runtimefd<0) goto cleanup;
    if (!hash_file(enginefd,ENGINE_SHA) || !verify_identity(enginefd,&engine_identity) ||
        !hash_file(runtimefd,argv[4]) || !verify_identity(runtimefd,&runtime_identity)) goto cleanup;
    code=malloc(CODE_BYTES);
    if (!code) {fail("host-code-allocation",errno);goto cleanup;}
    if (!read_exact(codefd,code,CODE_BYTES) || !verify_identity(codefd,&code_identity) ||
        !hash_memory(code,CODE_BYTES,code_sha)) goto cleanup;
    if (strcmp(code_sha,CODE_SHA)) {fail("codeobject-sha256-mismatch",0);goto cleanup;}
    /* Bind the sealed original raw ELF to the engine's embedded bytes. */
    unsigned char block[16384]; size_t done=0;
    if (lseek(enginefd,CODE_OFFSET,SEEK_SET)!=CODE_OFFSET) {fail("engine-payload-seek",errno);goto cleanup;}
    while (done<CODE_BYTES) {
        size_t n=CODE_BYTES-done; if (n>sizeof block) n=sizeof block;
        if (!read_exact(enginefd,block,n)) goto cleanup;
        if (memcmp(block,(const unsigned char *)code+done,n)) {fail("engine-codeobject-byte-mismatch",0);goto cleanup;}
        done+=n;
    }
    if (!verify_identity(enginefd,&engine_identity)) goto cleanup;
    for (unsigned i=0;i<2;i++) {
        weights[i]=malloc(WEIGHT_BYTES);
        if (!weights[i]) {fail("host-weight-allocation",errno);goto cleanup;}
        if (!load_bytes(argv[5+2*i],argv[6+2*i],weights[i],WEIGHT_BYTES,weight_sha[i],&weight_identity[i])) goto cleanup;
    }
    for (unsigned i=0;i<4;i++)
        if (!load_fixture(&fixtures[i],i%2,argv[9+2*i],argv[10+2*i])) goto cleanup;
    /* dlopen the pinned native HIP runtime; load the original ELF unchanged. */
    if (!verify_again(argv[3],argv[4],(size_t)runtime_identity.st_size,&runtime_identity)) goto cleanup;
    library=dlopen(argv[3],RTLD_NOW|RTLD_LOCAL);
    if (!library) {fail("hip-dlopen",0);fputs(dlerror(),stderr);fputc('\n',stderr);goto cleanup;}
    RESOLVE(hipGetDeviceCount);RESOLVE(hipGetDevicePropertiesR0600);RESOLVE(hipSetDevice);
    RESOLVE(hipRuntimeGetVersion);RESOLVE(hipDriverGetVersion);RESOLVE(hipModuleLoadData);
    RESOLVE(hipModuleGetFunction);RESOLVE(hipModuleLaunchKernel);RESOLVE(hipModuleUnload);
    RESOLVE(hipMalloc);RESOLVE(hipFree);RESOLVE(hipMemcpy);RESOLVE(hipDeviceSynchronize);
    int count=0; hipDeviceProp_t properties;
    memset(&properties,0,sizeof properties);
    HIP_OK(p_hipGetDeviceCount(&count),"hip-device-count");
    if (count!=1) {fail("exactly-one-gpu-required",count);goto cleanup;}
    HIP_OK(p_hipGetDevicePropertiesR0600(&properties,0),"hip-device-properties");
    if (strcmp(properties.gcnArchName,"gfx1151") || properties.warpSize!=32) {
        fail("gpu-gfx1151-wave32-required",0);goto cleanup;
    }
    HIP_OK(p_hipSetDevice(0),"hip-set-device");
    HIP_OK(p_hipRuntimeGetVersion(&runtime_version),"hip-runtime-version");
    HIP_OK(p_hipDriverGetVersion(&driver_version),"hip-driver-version");
    HIP_OK(p_hipModuleLoadData(&module,code),"hip-module-load");module_loads++;
    HIP_OK(p_hipModuleGetFunction(&functions[0],module,KERNEL_EMBEDDING),"hip-exact-embedding-symbol");
    HIP_OK(p_hipModuleGetFunction(&functions[1],module,KERNEL_HIDDEN),"hip-exact-hidden-symbol");
    for (unsigned i=0;i<2;i++) {
        HIP_OK(p_hipMalloc(&device_weights[i],WEIGHT_BYTES),"hip-weight-allocation");allocations_ok++;
        if ((uintptr_t)device_weights[i]&15) {fail("original-q8-weight-alignment16-required",0);goto cleanup;}
        HIP_OK(p_hipMemcpy(device_weights[i],weights[i],WEIGHT_BYTES,hipMemcpyHostToDevice),"hip-raw-q8-weight-copy");copies_ok++;
    }
    HIP_OK(p_hipMalloc(&device_input,MAX_TENSOR_BYTES),"hip-input-allocation");allocations_ok++;
    HIP_OK(p_hipMalloc(&device_output,MAX_TENSOR_BYTES),"hip-output-allocation");allocations_ok++;
    for (unsigned i=0;i<4;i++) {
        struct fixture *f=&fixtures[i]; int64_t k=2560,n=2560;
        size_t bytes=f->words*sizeof(uint16_t);
        HIP_OK(p_hipMemcpy(device_input,f->input,bytes,hipMemcpyHostToDevice),"hip-bf16-input-copy");copies_ok++;
        HIP_OK(p_hipMemcpy(device_output,f->output,bytes,hipMemcpyHostToDevice),"hip-output-poison-copy");copies_ok++;
        void *args[5]={&device_weights[f->branch],&device_input,&device_output,&k,&n};
        launch_attempts++;
        HIP_OK(p_hipModuleLaunchKernel(functions[f->branch],160,1,1,256,1,1,0,NULL,args,NULL),"hip-original-q8-fc-launch");launches_ok++;
        HIP_OK(p_hipDeviceSynchronize(),"hip-fc-synchronize");synchronizations_ok++;
        HIP_OK(p_hipMemcpy(f->output,device_output,bytes,hipMemcpyDeviceToHost),"hip-fc-output-copy");copies_ok++;
        f->output_copied=1;
        if (!hash_memory(f->output,bytes,f->output_sha)) goto cleanup;
        for (size_t j=0;j<f->words;j++) f->nonfinite_output+=(f->output[j]&0x7f80)==0x7f80;
        if (f->nonfinite_output) {fail("nonfinite-or-unfilled-fc-output",0);goto cleanup;}
        f->vectors_completed=f->streams; f->completed=1;
    }
    if (!verify_again(argv[1],ENGINE_SHA,ENGINE_BYTES,&engine_identity) ||
        !verify_again(argv[2],CODE_SHA,CODE_BYTES,&code_identity) ||
        !verify_again(argv[3],argv[4],(size_t)runtime_identity.st_size,&runtime_identity)) goto cleanup;
    for (unsigned i=0;i<2;i++)
        if (!verify_again(argv[5+2*i],argv[6+2*i],WEIGHT_BYTES,&weight_identity[i])) goto cleanup;
    for (unsigned i=0;i<4;i++)
        if (!verify_again(argv[9+2*i],argv[10+2*i],fixtures[i].words*sizeof(uint16_t),&fixtures[i].input_identity)) goto cleanup;
    files_rechecked=1;
cleanup:
    if (device_output) {if (!p_hipFree || p_hipFree(device_output)!=hipSuccess) cleanup_errors++;else free_ok++;}
    if (device_input) {if (!p_hipFree || p_hipFree(device_input)!=hipSuccess) cleanup_errors++;else free_ok++;}
    for (unsigned i=0;i<2;i++)
        if (device_weights[i]) {if (!p_hipFree || p_hipFree(device_weights[i])!=hipSuccess) cleanup_errors++;else free_ok++;}
    if (module) {if (!p_hipModuleUnload || p_hipModuleUnload(module)!=hipSuccess) cleanup_errors++;else module_unloads++;}
    if (library && dlclose(library)) cleanup_errors++;
    if (enginefd>=0 && close(enginefd)) file_close_errors++;
    if (codefd>=0 && close(codefd)) file_close_errors++;
    if (runtimefd>=0 && close(runtimefd)) file_close_errors++;
    free(code);free(weights[0]);free(weights[1]);
    if (cleanup_errors) fail("hip-cleanup",(int)cleanup_errors);
    if (file_close_errors) fail("input-file-close",(int)file_close_errors);
    /* Preserve every copied output even on a later fixture/cleanup failure. */
    for (unsigned i=0;i<4;i++) {
        if (outfd[i]>=0 && fixtures[i].output_copied) {
            if (write_exact(outfd[i],fixtures[i].output,fixtures[i].words*sizeof(uint16_t))) output_files_written++;
        }
        if (outfd[i]>=0 && close(outfd[i])) {file_close_errors++;fail("output-file-close",errno);}
    }
    if (dirfd>=0 && fsync(dirfd)) fail("output-directory-fsync",errno);
    passed=!error_reason && files_rechecked && fixtures[0].completed && fixtures[1].completed &&
        fixtures[2].completed && fixtures[3].completed && output_files_written==4 &&
        launch_attempts==4 && launches_ok==4 && synchronizations_ok==4 && copies_ok==14 &&
        allocations_ok==4 && free_ok==4 && module_loads==1 && module_unloads==1;
    if (reportfd>=0) {
        char report[12288];
        int n=snprintf(report,sizeof report,
            "{\"schema\":\"halogen0162.original-q8-fc-kernel-replay.v1\",\"passed\":%s,"
            "\"scope\":\"original FC kernels on explicit normalized BF16 inputs; no embedding-RMS/full-D/seed/head/acceptance/speed qualification\","
            "\"engine_sha256\":\"%s\",\"codeobject_sha256\":\"%s\",\"runtime_sha256\":\"%s\","
            "\"codeobject_engine_offset\":331776,\"codeobject_bytes\":17704408,"
            "\"runtime_version\":%d,\"driver_version\":%d,\"halogen_lq8_wave\":\"%s\","
            "\"kernel_selection_scope\":\"native default-or-one WAVE path; fixed M1/M4, K=N2560; exact registered symbols\","
            "\"kernels\":[{\"branch\":\"embedding\",\"symbol\":\"%s\",\"host_identity_rva\":\"0x18d6690\","
            "\"registration_rva\":\"0x184b596\",\"gpu_entry_rva\":\"0x2d1200\",\"descriptor_rva\":\"0x1fa340\",\"M\":1},"
            "{\"branch\":\"hidden\",\"symbol\":\"%s\",\"host_identity_rva\":\"0x18d66f0\","
            "\"registration_rva\":\"0x184b7be\",\"gpu_entry_rva\":\"0x2d7800\",\"descriptor_rva\":\"0x1fa640\",\"M\":4}],"
            "\"K\":2560,\"N\":2560,\"grid\":[160,1,1],\"block\":[256,1,1],\"shared_bytes\":0,\"default_stream\":true,"
            "\"static_lds_bytes\":0,\"wave_size\":32,\"kernarg_bytes\":40,\"kernarg_alignment\":8,\"hidden_arguments\":false,"
            "\"user_argument_offsets\":[0,8,16,24,32],\"user_argument_types\":[\"u8*\",\"u16*\",\"u16*\",\"i64\",\"i64\"],"
            "\"q8_layout\":\"store7/variant0; row K u8 codes then K/64 pairs[fp16scale,fp16bias]\","
            "\"q8_group_size\":64,\"weight_row_bytes\":2720,\"weight_bytes\":6963200,"
            "\"native_arithmetic\":\"affine dequant FMA; decoded-weight BF16 RNE; packed BF16 dot2 FP32 accumulation/reduction; output BF16 RNE\","
            "\"raw_weight_sha256\":{\"embedding\":\"%s\",\"hidden\":\"%s\"},\"raw_weights_copied_unchanged\":true,"
            "\"input_boundary\":\"explicit normalized BF16 words; caller records preparation provenance\","
            "\"embedding_rms_qualified\":false,\"full_D_parity_qualified\":false,\"seed_add_implemented\":false,"
            "\"full_head_qualified\":false,\"acceptance_claim\":false,\"speed_claim\":false,\"tolerance_adjustment\":false,"
            "\"arithmetic_fitting\":false,\"logical_calls\":4,\"launch_attempts\":%u,\"launches_ok\":%u,"
            "\"synchronizations_ok\":%u,\"copies_ok\":%u,\"allocations_ok\":%u,\"free_ok\":%u,"
            "\"module_loads\":%u,\"module_unloads\":%u,\"cleanup_errors\":%u,\"file_close_errors\":%u,"
            "\"immutable_files_rechecked\":%s,\"output_files_written\":%u,\"error\":\"%s\",\"error_code\":%d,\"fixtures\":[",
            passed?"true":"false",ENGINE_SHA,CODE_SHA,valid_sha(argv[4])?argv[4]:"",
            runtime_version,driver_version,wave_binding,KERNEL_EMBEDDING,KERNEL_HIDDEN,
            weight_sha[0],weight_sha[1],launch_attempts,launches_ok,synchronizations_ok,copies_ok,
            allocations_ok,free_ok,module_loads,module_unloads,cleanup_errors,file_close_errors,
            files_rechecked?"true":"false",output_files_written,error_reason?error_reason:"",error_code);
        size_t used=n>0?(size_t)n:sizeof report;
        for (unsigned i=0;i<4 && used<sizeof report;i++) {
            struct fixture *f=&fixtures[i];
            n=snprintf(report+used,sizeof report-used,
                "%s{\"id\":\"%s\",\"input_sha256\":\"%s\",\"output_sha256\":\"%s\",\"output_file\":\"%s\","
                "\"input_bytes\":%zu,\"output_bytes\":%zu,\"streams\":%u,\"vectors_completed\":%u,"
                "\"output_copied\":%s,\"completed\":%s,\"nonfinite_output\":%u}",
                i?",":"",fixture_ids[i],f->input_sha,f->output_sha,output_names[i],
                f->words*sizeof(uint16_t),f->words*sizeof(uint16_t),f->streams,f->vectors_completed,
                f->output_copied?"true":"false",f->completed?"true":"false",f->nonfinite_output);
            if (n<0 || (size_t)n>=sizeof report-used) used=sizeof report;else used+=(size_t)n;
        }
        if (used+4>=sizeof report) {fail("report-buffer-bound",0);passed=0;}
        else {
            memcpy(report+used,"]}\n",3);used+=3;
            if (!write_exact(reportfd,report,used)) passed=0;
        }
    } else passed=0;
    if (reportfd>=0 && close(reportfd)) {fail("report-file-close",errno);passed=0;}
    if (dirfd>=0 && close(dirfd)) {fail("output-directory-close",errno);passed=0;}
    fprintf(stderr,"original-q8-fc replay passed=%d launches=%u completed=%u/%u/%u/%u cleanup_errors=%u error=%s code=%d\n",
            passed,launch_attempts,fixtures[0].completed,fixtures[1].completed,fixtures[2].completed,fixtures[3].completed,
            cleanup_errors,error_reason?error_reason:"",error_code);
    return passed?0:1;
}
