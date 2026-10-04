/* Root-owned, isolated replay of the exact retained Halogen 0.16.2 gfx1151
 * kernel. This file contains NO replacement kernel or changed tensor arithmetic.
 * Build (root only, inside the pinned Linux environment):
 * gcc -O2 -Wall -Wextra -Werror -D__HIP_PLATFORM_AMD__ -I<reviewed-hip-include>
 *   halogen0162_hidden_rms_replay.c -ldl -lcrypto -o <new-replay-binary>
 * Usage (13 arguments; all files/root inputs are explicit):
 *   replay ENGINE HSACO HIP_LIBRARY HIP_SHA A_INPUT A_INPUT_SHA A_GAMMA
 *     A_GAMMA_SHA B_INPUT B_INPUT_SHA B_GAMMA B_GAMMA_SHA NEW_OUTPUT_DIRECTORY
 * Exactly two width10240/groups1 calls; each input/gamma/output is 20480 bytes.
 * Root provides frozen A/B fixtures, runtime/DXG mounts and external 22GiB
 * admission/18GiB watch/deadline. No engine, model, NPU, timing, or live D-wire
 * observation is implied. The full head and verifier remain unimplemented.
 * User args: pointers at offsets 0/8/16 and i32 width/groups at24/28. Let the
 * HIP module API populate all hidden ABI4 args (kernarg288, align8). Native
 * static LDS=1024; sharedBytes=0, defaultstream, grid1/block256, wave32.
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
#define TENSOR_BYTES ((size_t)20480)
#define WORDS ((size_t)10240)
#define ENGINE_SHA "ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b"
#define CODE_SHA "45941c0579dc3487d07978a50c85cbaa141bbb674b225e708e82d81397334a83"
#define KERNEL "_ZN7halogen12_GLOBAL__N_117k_rmsnorm_groupedEPKtS2_Ptii"

struct fixture {
    uint16_t input[WORDS], gamma[WORDS], output[WORDS];
    char input_sha[65], gamma_sha[65], output_sha[65];
    unsigned completed, nonfinite_output;
};
static struct fixture fixtures[2];
static const char *error_reason;
static unsigned launch_attempts, launches_ok, synchronizations_ok, copies_ok;
static unsigned cleanup_errors, allocations_ok, free_ok, module_loads, module_unloads;
static int error_code;

static int fail(const char *reason, int code) {
    if (!error_reason) { error_reason=reason; error_code=code; }
    return 0;
}
static int valid_sha(const char *s) {
    if (strlen(s)!=64) return 0;
    return strspn(s,"0123456789abcdef")==64;
}
static int hash_memory(const void *data,size_t length,char text[65]) {
    unsigned char digest[32]; unsigned n=0;
    if (!EVP_Digest(data,length,digest,&n,EVP_sha256(),NULL) || n!=32)
        return fail("sha256-memory",0);
    for (unsigned i=0;i<32;i++) sprintf(text+2*i,"%02x",digest[i]);
    text[64]=0; return 1;
}
static int open_regular(const char *path,size_t expected,size_t maximum) {
    if (path[0]!='/') {fail("input-path-not-absolute",0);return -1;}
    int fd=open(path,O_RDONLY|O_CLOEXEC|O_NOFOLLOW);
    if (fd<0) {fail("input-open",errno);return -1;}
    struct stat st;
    if (fstat(fd,&st) || !S_ISREG(st.st_mode) || st.st_size<=0 ||
        (uint64_t)st.st_size>maximum || (expected && (uint64_t)st.st_size!=expected)) {
        fail("input-file-contract",errno);close(fd);return -1;
    }
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
    unsigned char block[16384],digest[32]; unsigned n=0; char text[65];
    EVP_MD_CTX *ctx=EVP_MD_CTX_new(); int ok=ctx!=NULL;
    if (ok) ok=EVP_DigestInit_ex(ctx,EVP_sha256(),NULL)==1;
    while (ok) {
        ssize_t count=read(fd,block,sizeof block);
        if (count<0 && errno==EINTR) continue;
        if (count<0) {ok=0;break;}
        if (!count) break;
        ok=EVP_DigestUpdate(ctx,block,(size_t)count)==1;
    }
    if (ok) ok=EVP_DigestFinal_ex(ctx,digest,&n)==1 && n==32;
    EVP_MD_CTX_free(ctx);
    if (!ok) return fail("file-sha256",errno);
    for (unsigned i=0;i<32;i++) sprintf(text+2*i,"%02x",digest[i]);
    text[64]=0;
    return !strcmp(text,expected) || fail("file-sha256-mismatch",0);
}
static int load_fixture(struct fixture *f,const char *input,const char *input_sha,
                        const char *gamma,const char *gamma_sha) {
    if (!valid_sha(input_sha) || !valid_sha(gamma_sha)) return fail("fixture-sha-format",0);
    int fd=open_regular(input,TENSOR_BYTES,TENSOR_BYTES);
    if (fd<0) return 0;
    int ok=read_exact(fd,f->input,TENSOR_BYTES);close(fd);
    if (!ok || !hash_memory(f->input,TENSOR_BYTES,f->input_sha)) return 0;
    fd=open_regular(gamma,TENSOR_BYTES,TENSOR_BYTES);
    if (fd<0) return 0;
    ok=read_exact(fd,f->gamma,TENSOR_BYTES);close(fd);
    if (!ok || !hash_memory(f->gamma,TENSOR_BYTES,f->gamma_sha)) return 0;
    if (strcmp(f->input_sha,input_sha) || strcmp(f->gamma_sha,gamma_sha))
        return fail("fixture-sha256-mismatch",0);
    /* Exact raw-word reads; no tensor adjustment, casting or arithmetic. */
    for (size_t i=0;i<WORDS;i++) {
        if ((f->input[i]&0x7f80)==0x7f80 || (f->gamma[i]&0x7f80)==0x7f80)
            return fail("nonfinite-input-fixture",0);
        f->output[i]=0x7fc0; /* Poison only the initially unfilled output. */
    }
    return 1;
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
    void *library=NULL,*code=NULL,*device_input=NULL,*device_gamma=NULL,*device_output=NULL;
    hipModule_t module=NULL; hipFunction_t function=NULL;
    int runtime_version=0,driver_version=0,passed=0;
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
    outfd[0]=openat(dirfd,"A-hidden-rms-u16.bin",O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC|O_NOFOLLOW,0600);
    outfd[1]=openat(dirfd,"B-hidden-rms-u16.bin",O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC|O_NOFOLLOW,0600);
    if (reportfd<0 || outfd[0]<0 || outfd[1]<0) {fail("output-exclusive-create",errno);goto cleanup;}
    if (!valid_sha(argv[4])) {fail("runtime-sha-format",0);goto cleanup;}
    enginefd=open_regular(argv[1],ENGINE_BYTES,ENGINE_BYTES);
    codefd=open_regular(argv[2],CODE_BYTES,CODE_BYTES);
    runtimefd=open_regular(argv[3],0,128<<20);
    if (enginefd<0 || codefd<0 || runtimefd<0) goto cleanup;
    if (!hash_file(enginefd,ENGINE_SHA) || !hash_file(runtimefd,argv[4])) goto cleanup;
    code=malloc(CODE_BYTES);
    if (!code) {fail("host-code-allocation",errno);goto cleanup;}
    char code_sha[65];
    if (!read_exact(codefd,code,CODE_BYTES) || !hash_memory(code,CODE_BYTES,code_sha)) goto cleanup;
    if (strcmp(code_sha,CODE_SHA)) {fail("codeobject-sha256-mismatch",0);goto cleanup;}
    /* Bind the sealed raw ELF to the original engine's embedded payload bytes. */
    unsigned char block[16384]; size_t done=0;
    if (lseek(enginefd,CODE_OFFSET,SEEK_SET)!=CODE_OFFSET) {fail("engine-payload-seek",errno);goto cleanup;}
    while (done<CODE_BYTES) {
        size_t n=CODE_BYTES-done; if (n>sizeof block) n=sizeof block;
        if (!read_exact(enginefd,block,n)) goto cleanup;
        if (memcmp(block,(const unsigned char *)code+done,n)) {fail("engine-codeobject-byte-mismatch",0);goto cleanup;}
        done+=n;
    }
    if (!load_fixture(&fixtures[0],argv[5],argv[6],argv[7],argv[8]) ||
        !load_fixture(&fixtures[1],argv[9],argv[10],argv[11],argv[12])) goto cleanup;
    /* Native module API loads the original ELF; no compilation/JIT replacement. */
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
    HIP_OK(p_hipModuleGetFunction(&function,module,KERNEL),"hip-exact-symbol");
    HIP_OK(p_hipMalloc(&device_input,TENSOR_BYTES),"hip-input-allocation");allocations_ok++;
    HIP_OK(p_hipMalloc(&device_gamma,TENSOR_BYTES),"hip-gamma-allocation");allocations_ok++;
    HIP_OK(p_hipMalloc(&device_output,TENSOR_BYTES),"hip-output-allocation");allocations_ok++;
    for (unsigned i=0;i<2;i++) {
        struct fixture *f=&fixtures[i]; int32_t width=10240,groups=1;
        HIP_OK(p_hipMemcpy(device_input,f->input,TENSOR_BYTES,hipMemcpyHostToDevice),"hip-input-copy");copies_ok++;
        HIP_OK(p_hipMemcpy(device_gamma,f->gamma,TENSOR_BYTES,hipMemcpyHostToDevice),"hip-gamma-copy");copies_ok++;
        HIP_OK(p_hipMemcpy(device_output,f->output,TENSOR_BYTES,hipMemcpyHostToDevice),"hip-output-poison-copy");copies_ok++;
        void *args[5]={&device_input,&device_gamma,&device_output,&width,&groups};
        launch_attempts++;
        HIP_OK(p_hipModuleLaunchKernel(function,1,1,1,256,1,1,0,NULL,args,NULL),"hip-original-kernel-launch");launches_ok++;
        HIP_OK(p_hipDeviceSynchronize(),"hip-kernel-synchronize");synchronizations_ok++;
        HIP_OK(p_hipMemcpy(f->output,device_output,TENSOR_BYTES,hipMemcpyDeviceToHost),"hip-output-copy");copies_ok++;
        for (size_t j=0;j<WORDS;j++) f->nonfinite_output+=(f->output[j]&0x7f80)==0x7f80;
        if (f->nonfinite_output) {fail("nonfinite-or-unfilled-output",0);goto cleanup;}
        if (!hash_memory(f->output,TENSOR_BYTES,f->output_sha)) goto cleanup;
        f->completed=1;
    }
cleanup:
    if (device_output) {if (!p_hipFree || p_hipFree(device_output)!=hipSuccess) cleanup_errors++;else free_ok++;}
    if (device_gamma) {if (!p_hipFree || p_hipFree(device_gamma)!=hipSuccess) cleanup_errors++;else free_ok++;}
    if (device_input) {if (!p_hipFree || p_hipFree(device_input)!=hipSuccess) cleanup_errors++;else free_ok++;}
    if (module) {if (!p_hipModuleUnload || p_hipModuleUnload(module)!=hipSuccess) cleanup_errors++;else module_unloads++;}
    if (library && dlclose(library)) cleanup_errors++;
    if (enginefd>=0) close(enginefd);
    if (codefd>=0) close(codefd);
    if (runtimefd>=0) close(runtimefd);
    free(code);
    if (cleanup_errors) fail("hip-cleanup",(int)cleanup_errors);
    passed=!error_reason && fixtures[0].completed && fixtures[1].completed &&
        launch_attempts==2 && launches_ok==2 && synchronizations_ok==2 && copies_ok==8 &&
        allocations_ok==3 && free_ok==3 && module_loads==1 && module_unloads==1;
    if (passed) {
        if (!write_exact(outfd[0],fixtures[0].output,TENSOR_BYTES) ||
            !write_exact(outfd[1],fixtures[1].output,TENSOR_BYTES)) passed=0;
    }
    if (reportfd>=0) {
        char report[4096];
        int n=snprintf(report,sizeof report,
            "{\"schema\":\"halogen0162.hidden-rms-original-kernel-replay.v1\",\"passed\":%s,"
            "\"scope\":\"standalone original kernel; no full-head wire observation or timing claim\","
            "\"engine_sha256\":\"%s\",\"codeobject_sha256\":\"%s\",\"runtime_sha256\":\"%s\","
            "\"kernel_symbol\":\"%s\",\"host_identity_rva\":\"0x18d5160\",\"gpu_entry_rva\":\"0x22d200\","
            "\"descriptor_rva\":\"0x1f6cc0\",\"codeobject_engine_offset\":331776,\"codeobject_bytes\":17704408,"
            "\"runtime_version\":%d,\"driver_version\":%d,\"width\":10240,\"groups\":1,\"tensor_bytes\":20480,"
            "\"grid\":[1,1,1],\"block\":[256,1,1],\"shared_bytes\":0,\"default_stream\":true,"
            "\"static_lds_bytes\":1024,\"kernarg_bytes\":288,\"launch_attempts\":%u,\"launches_ok\":%u,"
            "\"synchronizations_ok\":%u,\"copies_ok\":%u,\"allocations_ok\":%u,\"free_ok\":%u,"
            "\"module_loads\":%u,\"module_unloads\":%u,\"cleanup_errors\":%u,\"error\":\"%s\",\"error_code\":%d,"
            "\"fixtures\":[{\"id\":\"A\",\"input_sha256\":\"%s\",\"raw_gamma_sha256\":\"%s\","
            "\"output_sha256\":\"%s\",\"completed\":%s,\"nonfinite_output\":%u},"
            "{\"id\":\"B\",\"input_sha256\":\"%s\",\"raw_gamma_sha256\":\"%s\","
            "\"output_sha256\":\"%s\",\"completed\":%s,\"nonfinite_output\":%u}]}\n",
            passed?"true":"false",ENGINE_SHA,CODE_SHA,valid_sha(argv[4])?argv[4]:"",KERNEL,
            runtime_version,driver_version,launch_attempts,launches_ok,synchronizations_ok,copies_ok,
            allocations_ok,free_ok,module_loads,module_unloads,cleanup_errors,error_reason?error_reason:"",error_code,
            fixtures[0].input_sha,fixtures[0].gamma_sha,fixtures[0].output_sha,fixtures[0].completed?"true":"false",fixtures[0].nonfinite_output,
            fixtures[1].input_sha,fixtures[1].gamma_sha,fixtures[1].output_sha,fixtures[1].completed?"true":"false",fixtures[1].nonfinite_output);
        if (n<0 || (size_t)n>=sizeof report || !write_exact(reportfd,report,(size_t)n)) passed=0;
    } else passed=0;
    for (unsigned i=0;i<2;i++) if (outfd[i]>=0 && close(outfd[i])) passed=0;
    if (reportfd>=0 && close(reportfd)) passed=0;
    if (dirfd>=0) close(dirfd);
    fprintf(stderr,"original-kernel replay passed=%d launches=%u completed=%u/%u cleanup_errors=%u error=%s code=%d\n",
            passed,launch_attempts,fixtures[0].completed,fixtures[1].completed,cleanup_errors,error_reason?error_reason:"",error_code);
    return passed?0:1;
}
