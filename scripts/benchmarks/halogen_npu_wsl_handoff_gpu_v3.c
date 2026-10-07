/* Persistent staged Windows-NPU -> WSL-HIP row consumer, component v3.
 * Build: gcc -O2 -Wall -Wextra -Werror -D__HIP_PLATFORM_AMD__
 * -I<reviewed HIP include> halogen_npu_wsl_handoff_gpu_v3.c -ldl -lcrypto -o <new binary>
 * Run: BINARY ENGINE HSACO HIP_LIBRARY HIP_SHA SHARED_DIRECTORY
 * --pipe-rows MODEL_BINDING: HGNPIPE3 envelope, bounded JSON, exact5120 bytes.
 * Before dlopen/HIP, observe this main thread's kernel PID/TGID using only an
 * ephemeral filter on its private socket pair; close all probe FDs first.
 * Pipe mode uses no row file reads/writes/fsync; Windows retains diagnostics
 * after all timed exchanges. Optional file mode retains the historical path.
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
#include <stdarg.h>
#include <signal.h>
#include "halogen_kernel_pid_self.h"

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

#define PIPE_SCHEMA "halogen-npu-wsl-binary-pipe.v3"
static int pipe_mode=0;
static const char *model_binding="";
static char kernel_identity_json[2048]="null";
static int prepare_kernel_identity(unsigned long long starttime_ticks) {
    struct halogen_kernel_identity identity;
    if (!halogen_observe_kernel_identity(&identity)) return fail("own-socket-kernel-PID-observation",errno);
    char boot[64]={0},line[512],chain[512]={0};
    FILE *file=fopen("/proc/sys/kernel/random/boot_id","r");
    if (!file) return fail("kernel-PID-boot-open",errno);
    int got=fgets(boot,sizeof boot,file)!=NULL;
    int closed=fclose(file);
    if (!got || closed) return fail("kernel-PID-boot-read-close",errno);
    boot[strcspn(boot,"\r\n")]=0;
    if (strlen(boot)!=36 || strspn(boot,"0123456789abcdef-")!=36 ||
        boot[8]!='-' || boot[13]!='-' || boot[18]!='-' || boot[23]!='-') return fail("kernel-PID-boot-format",0);
    file=fopen("/proc/self/status","r");
    if (!file) return fail("kernel-PID-status-open",errno);
    unsigned count=0;size_t used=0;long last=0;
    while (fgets(line,sizeof line,file)) if (!strncmp(line,"NSpid:",6)) {
        char *p=line+6;
        while (*p) {
            while (*p==' ' || *p=='\t' || *p=='\n' || *p=='\r') p++;
            if (!*p) break;
            char *end=NULL;errno=0;long value=strtol(p,&end,10);
            if (errno || end==p || value<=0 || value>INT32_MAX || count>=32) {count=0;break;}
            int n=snprintf(chain+used,sizeof chain-used,"%s%ld",count?",":"",value);
            if (n<1 || (size_t)n>=sizeof chain-used) {count=0;break;}
            used+=(size_t)n;last=value;count++;p=end;
        }
        break;
    }
    int read_error=ferror(file);closed=fclose(file);
    if (!count || read_error || closed || last!=identity.namespace_tid ||
        native_starttime_ticks()!=starttime_ticks) return fail("kernel-PID-proc-chain-birth",0);
    int n=snprintf(kernel_identity_json,sizeof kernel_identity_json,
        "{\"kernel_pid\":%u,\"kernel_tgid\":%u,\"namespace_pid\":%ld,\"namespace_tid\":%ld,"
        "\"proc_pid_namespace_inode\":%llu,\"native_starttime_ticks\":%llu,\"boot_id\":\"%s\","
        "\"namespace_pids\":[%s],\"scope\":\"own-socket-only\",\"probe_fds_closed\":true,\"persistent_kernel_attachment\":false}",
        identity.kernel_pid,identity.kernel_tgid,identity.namespace_pid,identity.namespace_tid,
        identity.proc_pid_namespace_inode,starttime_ticks,boot,chain);
    return n>0 && (size_t)n<sizeof kernel_identity_json?1:fail("kernel-PID-identity-bound",0);
}
static int pipe_write(const void *data,size_t bytes) {
    const unsigned char *p=data;
    while (bytes) {
        ssize_t n=write(STDOUT_FILENO,p,bytes);
        if (n<0 && errno==EINTR) continue;
        if (n<=0) return fail("binary-pipe-write",errno);
        p+=n;bytes-=(size_t)n;
    }
    return 1; /* Pipes deliberately have no fsync/DrvFS operation. */
}
static uint32_t be32(const unsigned char *p) {
    return ((uint32_t)p[0]<<24)|((uint32_t)p[1]<<16)|((uint32_t)p[2]<<8)|p[3];
}
static void put32(unsigned char *p,uint32_t x) {
    p[0]=(unsigned char)(x>>24);p[1]=(unsigned char)(x>>16);p[2]=(unsigned char)(x>>8);p[3]=(unsigned char)x;
}
static int pipe_read_frame(char *metadata,void *payload,size_t *payload_bytes) {
    unsigned char prefix[16];
    if (!read_exact(STDIN_FILENO,prefix,sizeof prefix)) return 0;
    uint32_t header=be32(prefix+8),bytes=be32(prefix+12);
    if (memcmp(prefix,"HGNPIPE3",8) || !header || header>4096 || (bytes && bytes!=ROW_BYTES))
        return fail("binary-pipe-envelope-bound",0);
    if (!read_exact(STDIN_FILENO,metadata,header)) return 0;
    metadata[header]=0;
    if (memchr(metadata,0,header) || !read_exact(STDIN_FILENO,payload,bytes)) return fail("binary-pipe-frame-truncated-or-NUL",0);
    *payload_bytes=bytes;return 1;
}
static int pipe_control(const char *metadata,const char *kind,size_t bytes) {
    char expected[512];
    int n=snprintf(expected,sizeof expected,"{\"schema\":\"%s\",\"kind\":\"%s\",\"model_binding\":\"%s\"}",PIPE_SCHEMA,kind,model_binding);
    return !bytes && n>0 && (size_t)n<sizeof expected && !strcmp(metadata,expected);
}
static int emit_json(const void *payload,size_t bytes,const char *format,...) {
    char body[3584],metadata[4097];va_list args;
    va_start(args,format);int n=vsnprintf(body,sizeof body,format,args);va_end(args);
    if (n<2 || (size_t)n>=sizeof body || body[0]!='{') return fail("binary-pipe-reply-bound",0);
    int m;
    if (!pipe_mode) {
        m=snprintf(metadata,sizeof metadata,"{\"kernel_identity\":%s,%s",kernel_identity_json,body+1);
        return m>0 && m<=4096 && fputs(metadata,stdout)>=0;
    }
    m=snprintf(metadata,sizeof metadata,"{\"schema\":\"%s\",\"transport\":\"binary-pipe\",\"model_binding\":\"%s\",\"kernel_identity\":%s,%s",PIPE_SCHEMA,model_binding,kernel_identity_json,body+1);
    if (m<2 || m>4096 || (bytes && bytes!=ROW_BYTES)) return fail("binary-pipe-reply-envelope-bound",0);
    while (m && (metadata[m-1]=='\n' || metadata[m-1]=='\r')) metadata[--m]=0;
    unsigned char prefix[16];memcpy(prefix,"HGNPIPE3",8);put32(prefix+8,(uint32_t)m);put32(prefix+12,(uint32_t)bytes);
    return pipe_write(prefix,sizeof prefix) && pipe_write(metadata,(size_t)m) && pipe_write(payload,bytes);
}

int main(int argc,char **argv) {
    int init_barrier=0;
    if (argc<6) {fputs("ENGINE HSACO HIP_LIBRARY HIP_SHA SHARED_DIRECTORY [--init-barrier] [--pipe-rows MODEL_BINDING] required\n",stderr);return 2;}
    for (int arg=6;arg<argc;arg++) {
        if (!strcmp(argv[arg],"--init-barrier") && !init_barrier) init_barrier=1;
        else if (!strcmp(argv[arg],"--pipe-rows") && !pipe_mode && arg+1<argc) {
            pipe_mode=1;model_binding=argv[++arg];
            if (!valid_sha(model_binding)) return 2;
        } else return 2;
    }
    signal(SIGPIPE,SIG_IGN);
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
    if (!starttime_ticks || !prepare_kernel_identity(starttime_ticks)) goto cleanup;
    if (starttime_ticks)
        if (!emit_json(NULL,0,"{\"kind\":\"starting\",\"native_pid\":%ld,\"native_starttime_ticks\":%llu,\"clock_ticks_per_second\":%ld,\"monotonic_ms\":%.9f,\"GPU_context_not_yet_initialized\":true}\n",(long)getpid(),starttime_ticks,sysconf(_SC_CLK_TCK),monotonic_ms())) goto cleanup;
    if (init_barrier) {
        if (pipe_mode) {
            char release[4097];size_t bytes=0;
            if (!pipe_read_frame(release,input,&bytes) || !pipe_control(release,"init",bytes)) {
                fail("owned-GPU-init-release-required",0);goto cleanup;
            }
        } else {
            char release[16];
            if (!fgets(release,sizeof release,stdin) || strcmp(release,"init\n")) {fail("owned-GPU-init-release-required",0);goto cleanup;}
        }
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
    if (!emit_json(NULL,0,"{\"kind\":\"ready\",\"native_pid\":%ld,\"native_starttime_ticks\":%llu,\"clock_ticks_per_second\":%ld,\"monotonic_ms\":%.9f,\"setup_ms\":%.9f,\"gpu_arch\":\"gfx1151\",\"engine_sha256\":\"%s\",\"codeobject_sha256\":\"%s\",\"hip_sha256\":\"%s\",\"kernel\":\"%s\",\"table_bytes\":5120,\"destination_bytes\":5120,\"setup_token_h2d_bytes\":4}\n",(long)getpid(),starttime_ticks,sysconf(_SC_CLK_TCK),monotonic_ms(),monotonic_ms()-setup_start,ENGINE_SHA,CODE_SHA,argv[4],GATHER)) goto cleanup;
    while (1) {
        unsigned sequence=0;char expected[65]={0},path[4096]={0};struct stat row_identity;
        double started=0;
        if (pipe_mode) {
            char metadata[4097],binding[65]={0};size_t bytes=0;int used=0;
            if (!pipe_read_frame(metadata,input,&bytes)) goto cleanup;
            if (pipe_control(metadata,"quit",bytes)) {quit_seen=1;break;}
            if (sscanf(metadata,"{\"schema\":\"" PIPE_SCHEMA "\",\"kind\":\"row\",\"sequence\":%u,\"model_binding\":\"%64[0-9a-f]\",\"input_sha256\":\"%64[0-9a-f]\",\"input_bytes\":5120}%n",
                       &sequence,binding,expected,&used)!=3 || used!=(int)strlen(metadata) || bytes!=ROW_BYTES ||
                !valid_sha(binding) || strcmp(binding,model_binding) || !valid_sha(expected) || sequence!=consumed || consumed>=ROWS) {
                fail("consume-once-pipe-sequence-model-or-row-contract",0);goto cleanup;
            }
            consumed++;started=monotonic_ms();
            if (!hash_memory(input,ROW_BYTES,input_sha) || strcmp(input_sha,expected)) {fail("binary-NPU-row-SHA",0);goto cleanup;}
        } else {
            char command[128],extra;
            if (!fgets(command,sizeof command,stdin)) break;
            if (!strcmp(command,"quit\n")) {quit_seen=1;break;}
            if (!strchr(command,'\n') || sscanf(command,"%u %64s %c",&sequence,expected,&extra)!=2 ||
                !valid_sha(expected) || sequence!=consumed || consumed>=ROWS) {fail("consume-once-sequence-or-request-contract",0);goto cleanup;}
            consumed++;started=monotonic_ms();
            int n=snprintf(path,sizeof path,"%s/row-%03u-npu.u16",argv[5],sequence);
            if (n<0 || (size_t)n>=sizeof path) {fail("row-path-bound",0);goto cleanup;}
            if (!load_bytes(path,expected,input,ROW_BYTES,input_sha,&row_identity)) goto cleanup;
        }
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
        if (!pipe_mode && (!verify_again(path,expected,ROW_BYTES,&row_identity) || !publish_row(dirfd,sequence,readback))) goto cleanup;
        if (!emit_json(pipe_mode?readback:NULL,pipe_mode?ROW_BYTES:0,"{\"kind\":\"row\",\"sequence\":%u,\"passed\":true,\"native_pid\":%ld,\"native_starttime_ticks\":%llu,\"monotonic_start_ms\":%.9f,\"input_sha256\":\"%s\",\"output_sha256\":\"%s\",\"input_bytes\":5120,\"output_bytes\":5120,\"h2d_bytes\":10240,\"d2h_bytes\":5120,\"copies\":3,\"kernel_launches\":1,\"completion_waits\":1,\"exact_bytes\":true,\"gpu_kernel_event_ms\":%.9f,\"load_hash_ms\":%.9f,\"h2d_and_poison_ms\":%.9f,\"enqueue_wait_host_ms\":%.9f,\"readback_ms\":%.9f,\"consumer_total_ms\":%.9f,\"diagnostic_artifact_name\":\"row-%03u-gpu.u16\"}\n",sequence,(long)getpid(),starttime_ticks,started,input_sha,output_sha,gpu_ms,loaded-started,uploaded-loaded,finished-uploaded,read_back-finished,monotonic_ms()-started,sequence)) goto cleanup;
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
    if (!emit_json(NULL,0,"{\"kind\":\"closed\",\"passed\":%s,\"consumed_rows\":%u,\"launches\":%u,\"copies\":%u,\"allocations\":%u,\"frees\":%u,\"module_loads\":%u,\"module_unloads\":%u,\"cleanup_errors\":%u,\"error\":\"%s\",\"error_code\":%d}\n",passed?"true":"false",consumed,launches_ok,copies_ok,allocations_ok,free_ok,module_loads,module_unloads,cleanup_errors,error_reason?error_reason:"",error_code)) return 1;
    return passed?0:1;
}
