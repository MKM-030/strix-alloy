/* Original Halogen 0.16.2 grouped RMS replay on two explicit embedding rows.
 * Reuses the reviewed hidden-RMS host scaffold; no replacement kernel or
 * changed tensor arithmetic. Root alone compiles/runs in its pinned image
 * under exclusive GPU ownership, 22 GiB admission / 18 GiB continuous reserve
 * and an owned deadline. No model, table gather, NPU, full-D/head/verifier,
 * acceptance or speed claim is implemented.
 *
 * Retained host 0x17db475..0x17db517 uses the same model+0x6c8 pointer for
 * input/output, raw gamma model+0xae8, width2560/groups1, grid1/block256,
 * default stream, dynamic shared0. Preserve that in-place pointer alias.
 * Exact kernel metadata: static LDS1024, wave32, kernarg288/alignment8;
 * public X/gamma/Y pointers at0/8/16, i32 width/groups at24/28. HIP fills
 * hidden ABI4 arguments through the normal module API (no manual extra pack).
 * Raw BF16 gamma is copied unchanged: the ORIGINAL shader widens it, adds1
 * in FP32, uses epsilonbits0x358637bd and rounds its final store BF16 RNE.
 *
 * Build (root only): gcc -O2 -Wall -Wextra -Werror -D__HIP_PLATFORM_AMD__
 *   -I<reviewed-hip-include> halogen0162_embedding_rms_replay.c -ldl -lcrypto
 *   -o <new-replay-binary>
 * Usage (13 arguments; absolute paths, independently supplied SHA256s):
 *   replay ENGINE HSACO HIP_LIBRARY HIP_SHA A_INPUT A_INPUT_SHA A_GAMMA
 *     A_GAMMA_SHA B_INPUT B_INPUT_SHA B_GAMMA B_GAMMA_SHA NEW_OUTPUT_DIRECTORY
 * Each input/raw-gamma/output is 2560 little-endian BF16 words (5120 bytes).
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
#define WORDS ((size_t)2560)
#define TENSOR_BYTES (WORDS * sizeof(uint16_t))
#define ENGINE_SHA "ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b"
#define CODE_SHA "45941c0579dc3487d07978a50c85cbaa141bbb674b225e708e82d81397334a83"
#define KERNEL "_ZN7halogen12_GLOBAL__N_117k_rmsnorm_groupedEPKtS2_Ptii"

struct fixture {
    uint16_t input[WORDS], gamma[WORDS], output[WORDS];
    char input_sha[65], gamma_sha[65], output_sha[65];
    struct stat input_identity, gamma_identity;
    unsigned completed, output_copied, nonfinite_output;
};
static struct fixture fixtures[2];
static const char *output_names[2]={"A-embedding-rms-u16.bin", "B-embedding-rms-u16.bin"};
static const char *error_reason;
static unsigned launch_attempts, launches_ok, synchronizations_ok, copies_ok;
static unsigned cleanup_errors, allocations_ok, free_ok, module_loads, module_unloads;
static int error_code;

static int fail(const char *reason,int code) {
    if (!error_reason) {error_reason=reason;error_code=code;}
    return 0;
}
static int valid_sha(const char *s) {
    return strlen(s)==64 && strspn(s,"0123456789abcdef")==64;
}
static int hash_memory(const void *data,size_t length,char text[65]) {
    unsigned char value[32];unsigned n=0;
    if (!EVP_Digest(data,length,value,&n,EVP_sha256(),NULL) || n!=32)
        return fail("sha256-memory",0);
    for (unsigned i=0;i<32;i++) sprintf(text+2*i,"%02x",value[i]);
    text[64]=0;return 1;
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
    unsigned char block[16384],value[32];unsigned n=0;char text[65];
    EVP_MD_CTX *ctx=EVP_MD_CTX_new();int ok=ctx!=NULL;
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
static int load_fixture(struct fixture *f,const char *input,const char *input_sha,const char *gamma,const char *gamma_sha) {
    if (!load_bytes(input,input_sha,f->input,TENSOR_BYTES,f->input_sha,&f->input_identity) ||
        !load_bytes(gamma,gamma_sha,f->gamma,TENSOR_BYTES,f->gamma_sha,&f->gamma_identity)) return 0;
    for (size_t i=0;i<WORDS;i++) {
        if ((f->input[i]&0x7f80)==0x7f80 || (f->gamma[i]&0x7f80)==0x7f80)
            return fail("nonfinite-input-fixture",0);
        f->output[i]=0x7fc0; /* Host-only poison; never overwrite the aliased GPU input. */
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
    if (argc!=14) {
        fputs("Expected ENGINE HSACO HIP_LIBRARY HIP_SHA A_INPUT A_INPUT_SHA A_GAMMA A_GAMMA_SHA B_INPUT B_INPUT_SHA B_GAMMA B_GAMMA_SHA NEW_OUTPUT_DIRECTORY\n",stderr);
        return 2;
    }
    int dirfd=-1,reportfd=-1,outfd[2]={-1,-1},enginefd=-1,codefd=-1,runtimefd=-1;
    void *library=NULL,*code=NULL,*device_tensor=NULL,*device_gamma=NULL;
    hipModule_t module=NULL;hipFunction_t function=NULL;
    struct stat engine_identity,code_identity,runtime_identity;
    int runtime_version=0,driver_version=0,passed=0,files_rechecked=0;
    unsigned output_files_written=0,file_close_errors=0;
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

    if (argv[13][0]!='/' || mkdir(argv[13],0700)) {
        fprintf(stderr,"Exclusive new output directory failed, errno=%d\n",errno);return 2;
    }
    dirfd=open(argv[13],O_DIRECTORY|O_RDONLY|O_CLOEXEC|O_NOFOLLOW);
    if (dirfd<0) {fail("output-directory-open",errno);goto cleanup;}
    reportfd=openat(dirfd,"replay.json",O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC|O_NOFOLLOW,0600);
    for (unsigned i=0;i<2;i++)
        outfd[i]=openat(dirfd,output_names[i],O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC|O_NOFOLLOW,0600);
    if (reportfd<0 || outfd[0]<0 || outfd[1]<0) {fail("output-exclusive-create",errno);goto cleanup;}
    if (!valid_sha(argv[4])) {fail("runtime-sha-format",0);goto cleanup;}
    enginefd=open_regular(argv[1],ENGINE_BYTES,ENGINE_BYTES,&engine_identity);
    codefd=open_regular(argv[2],CODE_BYTES,CODE_BYTES,&code_identity);
    runtimefd=open_regular(argv[3],0,128<<20,&runtime_identity);
    if (enginefd<0 || codefd<0 || runtimefd<0) goto cleanup;
    if (!hash_file(enginefd,ENGINE_SHA) || !verify_identity(enginefd,&engine_identity) ||
        !hash_file(runtimefd,argv[4]) || !verify_identity(runtimefd,&runtime_identity)) goto cleanup;
    code=malloc(CODE_BYTES);
    if (!code) {fail("host-code-allocation",errno);goto cleanup;}
    char code_sha[65];
    if (!read_exact(codefd,code,CODE_BYTES) || !verify_identity(codefd,&code_identity) ||
        !hash_memory(code,CODE_BYTES,code_sha)) goto cleanup;
    if (strcmp(code_sha,CODE_SHA)) {fail("codeobject-sha256-mismatch",0);goto cleanup;}
    /* Bind every retained shader byte to the sealed original engine payload. */
    unsigned char block[16384];size_t done=0;
    if (lseek(enginefd,CODE_OFFSET,SEEK_SET)!=CODE_OFFSET) {fail("engine-payload-seek",errno);goto cleanup;}
    while (done<CODE_BYTES) {
        size_t n=CODE_BYTES-done;if (n>sizeof block) n=sizeof block;
        if (!read_exact(enginefd,block,n)) goto cleanup;
        if (memcmp(block,(const unsigned char *)code+done,n)) {fail("engine-codeobject-byte-mismatch",0);goto cleanup;}
        done+=n;
    }
    if (!verify_identity(enginefd,&engine_identity) ||
        !load_fixture(&fixtures[0],argv[5],argv[6],argv[7],argv[8]) ||
        !load_fixture(&fixtures[1],argv[9],argv[10],argv[11],argv[12])) goto cleanup;
    if (!verify_again(argv[3],argv[4],(size_t)runtime_identity.st_size,&runtime_identity)) goto cleanup;
    library=dlopen(argv[3],RTLD_NOW|RTLD_LOCAL);
    if (!library) {fail("hip-dlopen",0);fputs(dlerror(),stderr);fputc('\n',stderr);goto cleanup;}
    RESOLVE(hipGetDeviceCount);RESOLVE(hipGetDevicePropertiesR0600);RESOLVE(hipSetDevice);
    RESOLVE(hipRuntimeGetVersion);RESOLVE(hipDriverGetVersion);RESOLVE(hipModuleLoadData);
    RESOLVE(hipModuleGetFunction);RESOLVE(hipModuleLaunchKernel);RESOLVE(hipModuleUnload);
    RESOLVE(hipMalloc);RESOLVE(hipFree);RESOLVE(hipMemcpy);RESOLVE(hipDeviceSynchronize);
    int count=0;hipDeviceProp_t properties;
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
    HIP_OK(p_hipModuleGetFunction(&function,module,KERNEL),"hip-exact-symbol");
    HIP_OK(p_hipMalloc(&device_tensor,TENSOR_BYTES),"hip-aliased-tensor-allocation");allocations_ok++;
    HIP_OK(p_hipMalloc(&device_gamma,TENSOR_BYTES),"hip-gamma-allocation");allocations_ok++;
    for (unsigned i=0;i<2;i++) {
        struct fixture *f=&fixtures[i];int32_t width=2560,groups=1;
        HIP_OK(p_hipMemcpy(device_tensor,f->input,TENSOR_BYTES,hipMemcpyHostToDevice),"hip-input-copy");copies_ok++;
        HIP_OK(p_hipMemcpy(device_gamma,f->gamma,TENSOR_BYTES,hipMemcpyHostToDevice),"hip-gamma-copy");copies_ok++;
        void *args[5]={&device_tensor,&device_gamma,&device_tensor,&width,&groups};
        launch_attempts++;
        HIP_OK(p_hipModuleLaunchKernel(function,1,1,1,256,1,1,0,NULL,args,NULL),"hip-original-kernel-launch");launches_ok++;
        HIP_OK(p_hipDeviceSynchronize(),"hip-kernel-synchronize");synchronizations_ok++;
        HIP_OK(p_hipMemcpy(f->output,device_tensor,TENSOR_BYTES,hipMemcpyDeviceToHost),"hip-output-copy");copies_ok++;
        f->output_copied=1;
        for (size_t j=0;j<WORDS;j++) f->nonfinite_output+=(f->output[j]&0x7f80)==0x7f80;
        if (!hash_memory(f->output,TENSOR_BYTES,f->output_sha)) goto cleanup;
        if (f->nonfinite_output) {fail("nonfinite-output",0);goto cleanup;}
        f->completed=1;
    }
    if (!verify_again(argv[1],ENGINE_SHA,ENGINE_BYTES,&engine_identity) ||
        !verify_again(argv[2],CODE_SHA,CODE_BYTES,&code_identity) ||
        !verify_again(argv[3],argv[4],(size_t)runtime_identity.st_size,&runtime_identity)) goto cleanup;
    for (unsigned i=0;i<2;i++) {
        if (!verify_again(argv[5+4*i],argv[6+4*i],TENSOR_BYTES,&fixtures[i].input_identity) ||
            !verify_again(argv[7+4*i],argv[8+4*i],TENSOR_BYTES,&fixtures[i].gamma_identity)) goto cleanup;
    }
    files_rechecked=1;
cleanup:
    if (device_gamma) {if (!p_hipFree || p_hipFree(device_gamma)!=hipSuccess) cleanup_errors++;else free_ok++;}
    if (device_tensor) {if (!p_hipFree || p_hipFree(device_tensor)!=hipSuccess) cleanup_errors++;else free_ok++;}
    if (module) {if (!p_hipModuleUnload || p_hipModuleUnload(module)!=hipSuccess) cleanup_errors++;else module_unloads++;}
    if (library && dlclose(library)) cleanup_errors++;
    if (enginefd>=0 && close(enginefd)) file_close_errors++;
    if (codefd>=0 && close(codefd)) file_close_errors++;
    if (runtimefd>=0 && close(runtimefd)) file_close_errors++;
    free(code);
    if (cleanup_errors) fail("hip-cleanup",(int)cleanup_errors);
    for (unsigned i=0;i<2;i++) {
        if (outfd[i]>=0 && fixtures[i].output_copied) {
            if (write_exact(outfd[i],fixtures[i].output,TENSOR_BYTES)) output_files_written++;
        }
        if (outfd[i]>=0 && close(outfd[i])) file_close_errors++;
        outfd[i]=-1;
    }
    if (file_close_errors) fail("file-close",(int)file_close_errors);
    passed=!error_reason && files_rechecked && fixtures[0].completed && fixtures[1].completed &&
        output_files_written==2 && launch_attempts==2 && launches_ok==2 && synchronizations_ok==2 && copies_ok==6 &&
        allocations_ok==2 && free_ok==2 && module_loads==1 && module_unloads==1;
    if (reportfd>=0) {
        char report[8192];
        int n=snprintf(report,sizeof report,
            "{\"schema\":\"halogen0162.embedding-rms-original-kernel-replay.v1\",\"passed\":%s,"
            "\"scope\":\"original in-place embedding RMS on explicit BF16 rows; no table-gather/full-D/head/acceptance/speed qualification\","
            "\"engine_sha256\":\"%s\",\"codeobject_sha256\":\"%s\",\"runtime_sha256\":\"%s\","
            "\"kernel_symbol\":\"%s\",\"host_identity_rva\":\"0x18d5160\",\"registration_rva\":\"0x1848906\","
            "\"gpu_entry_rva\":\"0x22d200\",\"descriptor_rva\":\"0x1f6cc0\","
            "\"embedding_host_launch_return_rva\":\"0x17db51c\",\"codeobject_engine_offset\":331776,\"codeobject_bytes\":17704408,"
            "\"runtime_version\":%d,\"driver_version\":%d,\"width\":2560,\"groups\":1,\"tensor_bytes\":5120,"
            "\"grid\":[1,1,1],\"block\":[256,1,1],\"shared_bytes\":0,\"default_stream\":true,"
            "\"static_lds_bytes\":1024,\"wave_size\":32,\"kernarg_bytes\":288,\"kernarg_alignment\":8,\"hidden_arguments\":true,"
            "\"user_argument_offsets\":[0,8,16,24,28],\"user_argument_types\":[\"u16*\",\"u16*\",\"u16*\",\"i32\",\"i32\"],"
            "\"input_output_alias\":true,\"raw_gamma_copied_unchanged\":true,\"epsilon_fp32_bits\":\"0x358637bd\","
            "\"native_arithmetic\":\"strided FP32 square FMA; LDS pairwise FP32 reduction; full width mean plus epsilon; native rsq; FP32 x*inverse then*(1+raw BF16 gamma); BF16 RNE store\","
            "\"table_gather_replayed\":false,\"full_D_parity_qualified\":false,\"full_head_qualified\":false,"
            "\"acceptance_claim\":false,\"speed_claim\":false,\"tolerance_adjustment\":false,\"arithmetic_fitting\":false,"
            "\"logical_calls\":2,\"launch_attempts\":%u,\"launches_ok\":%u,\"synchronizations_ok\":%u,\"copies_ok\":%u,"
            "\"allocations_ok\":%u,\"free_ok\":%u,\"module_loads\":%u,\"module_unloads\":%u,\"cleanup_errors\":%u,"
            "\"file_close_errors\":%u,\"immutable_files_rechecked\":%s,\"output_files_written\":%u,\"error\":\"%s\",\"error_code\":%d,"
            "\"fixtures\":[{\"id\":\"A\",\"input_sha256\":\"%s\",\"raw_gamma_sha256\":\"%s\",\"output_sha256\":\"%s\","
            "\"output_file\":\"A-embedding-rms-u16.bin\",\"input_bytes\":5120,\"gamma_bytes\":5120,\"output_bytes\":5120,"
            "\"output_copied\":%s,\"completed\":%s,\"nonfinite_output\":%u},"
            "{\"id\":\"B\",\"input_sha256\":\"%s\",\"raw_gamma_sha256\":\"%s\",\"output_sha256\":\"%s\","
            "\"output_file\":\"B-embedding-rms-u16.bin\",\"input_bytes\":5120,\"gamma_bytes\":5120,\"output_bytes\":5120,"
            "\"output_copied\":%s,\"completed\":%s,\"nonfinite_output\":%u}]}\n",
            passed?"true":"false",ENGINE_SHA,CODE_SHA,valid_sha(argv[4])?argv[4]:"",KERNEL,
            runtime_version,driver_version,launch_attempts,launches_ok,synchronizations_ok,copies_ok,
            allocations_ok,free_ok,module_loads,module_unloads,cleanup_errors,file_close_errors,
            files_rechecked?"true":"false",output_files_written,error_reason?error_reason:"",error_code,
            fixtures[0].input_sha,fixtures[0].gamma_sha,fixtures[0].output_sha,fixtures[0].output_copied?"true":"false",
            fixtures[0].completed?"true":"false",fixtures[0].nonfinite_output,
            fixtures[1].input_sha,fixtures[1].gamma_sha,fixtures[1].output_sha,fixtures[1].output_copied?"true":"false",
            fixtures[1].completed?"true":"false",fixtures[1].nonfinite_output);
        if (n<0 || (size_t)n>=sizeof report || !write_exact(reportfd,report,(size_t)n)) passed=0;
    } else passed=0;
    if (reportfd>=0 && close(reportfd)) passed=0;
    if (dirfd>=0 && close(dirfd)) passed=0;
    fprintf(stderr,"original embedding-RMS replay passed=%d launches=%u completed=%u/%u cleanup_errors=%u error=%s code=%d\n",
            passed,launch_attempts,fixtures[0].completed,fixtures[1].completed,cleanup_errors,error_reason?error_reason:"",error_code);
    return passed?0:1;
}
