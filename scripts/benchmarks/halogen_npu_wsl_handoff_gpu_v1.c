/* Persistent staged Windows-NPU -> WSL-HIP row consumer, component v1.
 * Build: gcc -O2 -Wall -Wextra -Werror -D__HIP_PLATFORM_AMD__
 * -I<reviewed HIP include> halogen_npu_wsl_handoff_gpu_v1.c -ldl -lcrypto -o <new binary>
 * Run: BINARY ENGINE HSACO HIP_LIBRARY HIP_SHA SHARED_DIRECTORY
 * stdin: next_sequence sha256\n ; quit\n after 12 consume-once rows.
 * A request is sent only after row-NNN-npu.u16 has been fsynced and renamed.
 * The unchanged native k_embed_gather reads the uploaded NPU row as a one-row
 * table and emits a different, previously poisoned GPU allocation. Readback
 * must equal the exact NPU bytes. This is a GPU consumption/transfer proof;
 * no seed-add, full-D, head, native word parity, live swap, overlap or speed claim.
 * Root owns the outer deadline/job/reserve guardian, including blocked HIP.
 */
#define main unused_frozen_fc_replay_main
#include "halogen0162_fc_replay.c"
#undef main
#include <time.h>

#define ROW_BYTES ((size_t)5120)
#define ROWS 12u
#define GATHER "_ZN7halogen12_GLOBAL__N_114k_embed_gatherEPKtPKiPt"

static double monotonic_ms(void) {
    struct timespec t;
    if (clock_gettime(CLOCK_MONOTONIC,&t)) return -1;
    return (double)t.tv_sec*1000.0+(double)t.tv_nsec/1000000.0;
}
static unsigned long long native_starttime_ticks(void) {
    char text[4096];
    FILE *file=fopen("/proc/self/stat","r");
    if (!file) return 0;
    char *got=fgets(text,sizeof text,file);
    int closed=fclose(file);
    if (!got || closed) return 0;
    char *end=strrchr(text,')');
    if (!end || end[1]!=' ') return 0;
    char *save=NULL,*token=strtok_r(end+2," ",&save);
    for (unsigned field=3;token;field++,token=strtok_r(NULL," ",&save))
        if (field==22) return strtoull(token,NULL,10);
    return 0;
}
static int publish_row(int dirfd,unsigned sequence,const void *data) {
    char partial[64],target[64];
    snprintf(partial,sizeof partial,"row-%03u-gpu.u16.partial",sequence);
    snprintf(target,sizeof target,"row-%03u-gpu.u16",sequence);
    struct stat st;
    if (!fstatat(dirfd,target,&st,AT_SYMLINK_NOFOLLOW) || errno!=ENOENT)
        return fail("GPU-publication-already-exists",errno);
    int fd=openat(dirfd,partial,O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC|O_NOFOLLOW,0600);
    if (fd<0) return fail("GPU-publication-exclusive-open",errno);
    int ok=write_exact(fd,data,ROW_BYTES);
    if (close(fd)) ok=fail("GPU-publication-close",errno);
    if (ok && renameat(dirfd,partial,dirfd,target)) ok=fail("GPU-publication-rename",errno);
    /* DrvFS can reject directory fsync; row bytes are synchronously fsynced.
     * Do not describe directory durability as proven. */
    return ok;
}

int main(int argc,char **argv) {
    if (argc!=6 && (argc!=7 || strcmp(argv[6],"--init-barrier"))) {fputs("ENGINE HSACO HIP_LIBRARY HIP_SHA SHARED_DIRECTORY [--init-barrier] required\n",stderr);return 2;}
    int enginefd=-1,codefd=-1,runtimefd=-1,dirfd=-1,complete=0,quit_seen=0;
    void *library=NULL,*code=NULL,*table=NULL,*ids=NULL,*output=NULL;
    hipModule_t module=NULL;hipFunction_t gather=NULL;
    hipEvent_t begin=NULL,end=NULL;
    struct stat engine_identity,code_identity,runtime_identity;
    uint16_t input[WIDTH],readback[WIDTH],poison[WIDTH];int32_t zero=0;
    char code_sha[65]={0},input_sha[65]={0},output_sha[65]={0};
    unsigned consumed=0,event_creates=0,event_destroys=0;
    double setup_start=monotonic_ms();
    unsigned long long starttime_ticks=native_starttime_ticks();
    API(hipGetDeviceCount,hipError_t,(int *));
    API(hipGetDevicePropertiesR0600,hipError_t,(hipDeviceProp_t *,int));
    API(hipSetDevice,hipError_t,(int));
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
    setvbuf(stdout,NULL,_IOLBF,0);
    if (starttime_ticks)
        printf("{\"kind\":\"starting\",\"native_pid\":%ld,\"native_starttime_ticks\":%llu,\"clock_ticks_per_second\":%ld,\"monotonic_ms\":%.9f,\"GPU_context_not_yet_initialized\":true}\n",(long)getpid(),starttime_ticks,sysconf(_SC_CLK_TCK),monotonic_ms());
    if (argc==7) {
        char release[16];
        if (!fgets(release,sizeof release,stdin) || strcmp(release,"init\n")) {fail("owned-GPU-init-release-required",0);goto cleanup;}
    }
    if (!valid_sha(argv[4]) || argv[5][0]!='/' || !starttime_ticks) {fail("absolute-directory-runtime-pin-and-process-identity-required",0);goto cleanup;}
    dirfd=open(argv[5],O_DIRECTORY|O_RDONLY|O_CLOEXEC|O_NOFOLLOW);
    enginefd=open_regular(argv[1],ENGINE_BYTES,ENGINE_BYTES,&engine_identity);
    codefd=open_regular(argv[2],CODE_BYTES,CODE_BYTES,&code_identity);
    runtimefd=open_regular(argv[3],0,128<<20,&runtime_identity);
    if (dirfd<0 || enginefd<0 || codefd<0 || runtimefd<0) goto cleanup;
    if (!hash_file(enginefd,ENGINE_SHA) || !verify_identity(enginefd,&engine_identity) ||
        !hash_file(runtimefd,argv[4]) || !verify_identity(runtimefd,&runtime_identity)) goto cleanup;
    code=malloc(CODE_BYTES);
    if (!code) {fail("host-code-allocation",errno);goto cleanup;}
    if (!read_exact(codefd,code,CODE_BYTES) || !verify_identity(codefd,&code_identity) ||
        !hash_memory(code,CODE_BYTES,code_sha) || strcmp(code_sha,CODE_SHA)) {fail("sealed-codeobject-mismatch",0);goto cleanup;}
    if (lseek(enginefd,CODE_OFFSET,SEEK_SET)!=CODE_OFFSET) {fail("engine-seek",errno);goto cleanup;}
    unsigned char block[16384];size_t done=0;
    while (done<CODE_BYTES) {
        size_t n=CODE_BYTES-done;if (n>sizeof block) n=sizeof block;
        if (!read_exact(enginefd,block,n) || memcmp(block,(unsigned char *)code+done,n)) {fail("engine-codeobject-mismatch",0);goto cleanup;}
        done+=n;
    }
    library=dlopen(argv[3],RTLD_NOW|RTLD_LOCAL);
    if (!library) {fail("pinned-HIP-dlopen",0);goto cleanup;}
    RESOLVE(hipGetDeviceCount);RESOLVE(hipGetDevicePropertiesR0600);RESOLVE(hipSetDevice);
    RESOLVE(hipModuleLoadData);RESOLVE(hipModuleGetFunction);RESOLVE(hipModuleLaunchKernel);RESOLVE(hipModuleUnload);
    RESOLVE(hipMalloc);RESOLVE(hipFree);RESOLVE(hipMemcpy);RESOLVE(hipDeviceSynchronize);
    RESOLVE(hipEventCreateWithFlags);RESOLVE(hipEventRecord);RESOLVE(hipEventSynchronize);
    RESOLVE(hipEventElapsedTime);RESOLVE(hipEventDestroy);
    int count=0;hipDeviceProp_t properties;
    HIP_OK(p_hipGetDeviceCount(&count),"GPU-count");
    if (count!=1) {fail("exactly-one-GPU-required",count);goto cleanup;}
    HIP_OK(p_hipGetDevicePropertiesR0600(&properties,0),"GPU-properties");
    if (strcmp(properties.gcnArchName,"gfx1151") || properties.warpSize!=32) {fail("gfx1151-wave32-required",0);goto cleanup;}
    HIP_OK(p_hipSetDevice(0),"GPU-set");
    HIP_OK(p_hipModuleLoadData(&module,code),"original-module-load");module_loads++;
    HIP_OK(p_hipModuleGetFunction(&gather,module,GATHER),"original-gather-symbol");
    HIP_OK(p_hipMalloc(&table,ROW_BYTES),"NPU-row-table-allocation");allocations_ok++;
    HIP_OK(p_hipMalloc(&ids,sizeof zero),"zero-token-allocation");allocations_ok++;
    HIP_OK(p_hipMalloc(&output,ROW_BYTES),"GPU-destination-allocation");allocations_ok++;
    HIP_OK(p_hipMemcpy(ids,&zero,sizeof zero,hipMemcpyHostToDevice),"zero-token-upload");copies_ok++;
    HIP_OK(p_hipEventCreateWithFlags(&begin,0),"begin-event-create");event_creates++;
    HIP_OK(p_hipEventCreateWithFlags(&end,0),"end-event-create");event_creates++;
    for (size_t i=0;i<WIDTH;i++) poison[i]=0x7fc0;
    printf("{\"kind\":\"ready\",\"schema\":\"halogen-npu-wsl-gpu-consumer.v1\",\"native_pid\":%ld,\"native_starttime_ticks\":%llu,\"clock_ticks_per_second\":%ld,\"monotonic_ms\":%.9f,\"setup_ms\":%.9f,\"gpu_arch\":\"gfx1151\",\"engine_sha256\":\"%s\",\"codeobject_sha256\":\"%s\",\"hip_sha256\":\"%s\",\"kernel\":\"%s\",\"table_bytes\":5120,\"destination_bytes\":5120,\"setup_token_h2d_bytes\":4}\n",(long)getpid(),starttime_ticks,sysconf(_SC_CLK_TCK),monotonic_ms(),monotonic_ms()-setup_start,ENGINE_SHA,CODE_SHA,argv[4],GATHER);
    char command[128];
    while (fgets(command,sizeof command,stdin)) {
        if (!strcmp(command,"quit\n")) {quit_seen=1;break;}
        unsigned sequence=0;char expected[65]={0},extra;
        if (!strchr(command,'\n') || sscanf(command,"%u %64s %c",&sequence,expected,&extra)!=2 ||
            !valid_sha(expected) || sequence!=consumed || consumed>=ROWS) {fail("consume-once-sequence-or-request-contract",0);goto cleanup;}
        consumed++; /* A failed row is never retryable. */
        double started=monotonic_ms();
        char path[4096];int n=snprintf(path,sizeof path,"%s/row-%03u-npu.u16",argv[5],sequence);
        if (n<0 || (size_t)n>=sizeof path) {fail("row-path-bound",0);goto cleanup;}
        struct stat row_identity;
        if (!load_bytes(path,expected,input,ROW_BYTES,input_sha,&row_identity)) goto cleanup;
        for (size_t i=0;i<WIDTH;i++) if ((input[i]&0x7f80)==0x7f80) {fail("nonfinite-NPU-row",0);goto cleanup;}
        double loaded=monotonic_ms();
        HIP_OK(p_hipMemcpy(table,input,ROW_BYTES,hipMemcpyHostToDevice),"NPU-row-H2D");copies_ok++;
        HIP_OK(p_hipMemcpy(output,poison,ROW_BYTES,hipMemcpyHostToDevice),"destination-poison-H2D");copies_ok++;
        double uploaded=monotonic_ms();
        HIP_OK(p_hipEventRecord(begin,NULL),"gather-start-event");
        void *arguments[3]={&table,&ids,&output};launch_attempts++;
        HIP_OK(p_hipModuleLaunchKernel(gather,1,1,1,256,1,1,0,NULL,arguments,NULL),"original-gather-consuming-NPU-row");launches_ok++;
        HIP_OK(p_hipEventRecord(end,NULL),"gather-end-event");
        HIP_OK(p_hipEventSynchronize(end),"gather-completion-wait");synchronizations_ok++;
        float gpu_ms=0;
        HIP_OK(p_hipEventElapsedTime(&gpu_ms,begin,end),"gather-event-time");
        double finished=monotonic_ms();
        HIP_OK(p_hipMemcpy(readback,output,ROW_BYTES,hipMemcpyDeviceToHost),"GPU-output-D2H");copies_ok++;
        double read_back=monotonic_ms();
        if (!hash_memory(readback,ROW_BYTES,output_sha) || strcmp(input_sha,output_sha) || memcmp(input,readback,ROW_BYTES)) {fail("GPU-consumption-byte-parity",0);goto cleanup;}
        if (!verify_again(path,expected,ROW_BYTES,&row_identity) || !publish_row(dirfd,sequence,readback)) goto cleanup;
        printf("{\"kind\":\"row\",\"sequence\":%u,\"passed\":true,\"native_pid\":%ld,\"native_starttime_ticks\":%llu,\"monotonic_start_ms\":%.9f,\"input_sha256\":\"%s\",\"output_sha256\":\"%s\",\"input_bytes\":5120,\"output_bytes\":5120,\"h2d_bytes\":10240,\"d2h_bytes\":5120,\"copies\":3,\"kernel_launches\":1,\"completion_waits\":1,\"exact_bytes\":true,\"gpu_kernel_event_ms\":%.9f,\"load_hash_ms\":%.9f,\"h2d_and_poison_ms\":%.9f,\"enqueue_wait_host_ms\":%.9f,\"readback_ms\":%.9f,\"consumer_total_ms\":%.9f,\"output_file\":\"row-%03u-gpu.u16\"}\n",sequence,(long)getpid(),starttime_ticks,started,input_sha,output_sha,gpu_ms,loaded-started,uploaded-loaded,finished-uploaded,read_back-finished,monotonic_ms()-started,sequence);
    }
    if (!quit_seen || consumed!=ROWS) {fail("complete-12-rows-and-explicit-quit-required",0);goto cleanup;}
    if (!verify_again(argv[1],ENGINE_SHA,ENGINE_BYTES,&engine_identity) ||
        !verify_again(argv[2],CODE_SHA,CODE_BYTES,&code_identity) ||
        !verify_again(argv[3],argv[4],(size_t)runtime_identity.st_size,&runtime_identity)) goto cleanup;
    complete=1;
cleanup:
    if (begin) {if (!p_hipEventDestroy || p_hipEventDestroy(begin)!=hipSuccess) cleanup_errors++;else event_destroys++;}
    if (end) {if (!p_hipEventDestroy || p_hipEventDestroy(end)!=hipSuccess) cleanup_errors++;else event_destroys++;}
    if (output) {if (!p_hipFree || p_hipFree(output)!=hipSuccess) cleanup_errors++;else free_ok++;}
    if (ids) {if (!p_hipFree || p_hipFree(ids)!=hipSuccess) cleanup_errors++;else free_ok++;}
    if (table) {if (!p_hipFree || p_hipFree(table)!=hipSuccess) cleanup_errors++;else free_ok++;}
    if (module) {if (!p_hipModuleUnload || p_hipModuleUnload(module)!=hipSuccess) cleanup_errors++;else module_unloads++;}
    if (library && dlclose(library)) cleanup_errors++;
    if (enginefd>=0 && close(enginefd)) cleanup_errors++;
    if (codefd>=0 && close(codefd)) cleanup_errors++;
    if (runtimefd>=0 && close(runtimefd)) cleanup_errors++;
    if (dirfd>=0 && close(dirfd)) cleanup_errors++;
    free(code);
    int passed=complete && !error_reason && !cleanup_errors && free_ok==3 &&
        module_loads==1 && module_unloads==1 && event_creates==2 && event_destroys==2 &&
        launches_ok==ROWS && synchronizations_ok==ROWS && copies_ok==1+3*ROWS;
    printf("{\"kind\":\"closed\",\"passed\":%s,\"consumed_rows\":%u,\"launches\":%u,\"copies\":%u,\"allocations\":%u,\"frees\":%u,\"module_loads\":%u,\"module_unloads\":%u,\"cleanup_errors\":%u,\"error\":\"%s\",\"error_code\":%d}\n",passed?"true":"false",consumed,launches_ok,copies_ok,allocations_ok,free_ok,module_loads,module_unloads,cleanup_errors,error_reason?error_reason:"",error_code);
    return passed?0:1;
}
