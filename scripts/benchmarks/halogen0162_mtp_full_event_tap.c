/* Research-only complete MTP forward timing. Original forward/wrapper always execute.
 * Build: gcc -O2 -Wall -Wextra -Werror -shared -fPIC -fno-optimize-sibling-calls
 *        halogen0162_mtp_full_event_tap.c -ldl -lcrypto -pthread -o libhalogen0162-mtp-full-event-tap.so
 * Root alone owns GPU launches. These are instrumented event brackets, not
 * exact uninstrumented latency, busy-kernel sums, or accepted-token timings.
 * Events precreate during an unarmed ordinary full-forward call. An exclusive harvest
 * file is published after response; one final-event wait covers the pool.
 */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <elf.h>
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <limits.h>
#include <link.h>
#include <math.h>
#include <openssl/evp.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

#if !defined(__x86_64__) || !defined(__linux__)
#error Linux x86-64 only
#endif
#define ENGINE_SHA "ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b"
#define FUNCTION_SHA "132f2da76d86694ffe5f120d61e304e57c685f3db72935c6d5e61bf7b0d5cc20"
#define ENTRY_RVA ((uintptr_t)0x17db310)
#define ENTRY_OFFSET ((off_t)0x17da310)
#define FUNCTION_BYTES ((size_t)(0x17dc289 - 0x17db310))
#define WRAPPER_RVA ((uintptr_t)0x17dcde0)
#define WRAPPER_OFFSET ((off_t)0x17dbde0)
#define WRAPPER_BYTES ((size_t)(0x17dcfb5 - 0x17dcde0))
#define WRAPPER_SHA "2c6dc2832f047253b7459303253da0199e35c6944afb629f381b42d47c986892"
#define ROUTER_RVA ((uintptr_t)0x18db4d8)
#define TRACE_LIMIT 128U
#define TRACE_BYTE_LIMIT ((size_t)262144)
static const char trace_prefix[] = "/tmp/alloy-mtp-full-event-tap-";
static const char arm_content[] = "full-events128-v1-ready\n";
static const char harvest_content[] = "full-events128-v1-harvest\n";
static const unsigned char entry_signature[32] = {
    0x55,0x41,0x57,0x41,0x56,0x41,0x55,0x41,0x54,0x53,0x48,0x81,0xec,0x98,0,0,
    0,0xb8,0xff,0xff,0xff,0xff,0x80,0xbf,0,0x09,0,0,0x01,0x0f,0x85,0x31
};
static const unsigned char wrapper_signature[32] = {
    0x41,0x56,0x53,0x50,0x89,0x74,0x24,0x04,0xb8,0xff,0xff,0xff,0xff,0x80,0xbf,0,
    0x09,0,0,0x01,0x0f,0x85,0x4f,0x01,0,0,0x89,0xd3,0x85,0xd2,0x0f,0x95
};
typedef int32_t (*head_fn)(void *,const int32_t *,int32_t,int32_t);
/* The native fourth argument is consumed as CL; preserve its complete value. */
typedef int32_t (*wrapper_fn)(void *,int32_t,int32_t,int32_t);
typedef int (*sync_fn)(void);
typedef int (*stream_sync_fn)(void *);
typedef int (*copy_fn)(void *,const void *,size_t,int);
typedef int (*copy_2d_fn)(void *,size_t,const void *,size_t,size_t,size_t,int);
typedef int (*event_create_fn)(void **, unsigned);
typedef int (*event_record_fn)(void *, void *);
typedef int (*event_one_fn)(void *);
typedef int (*event_elapsed_fn)(float *, void *, void *);
typedef int (*device_get_fn)(int *);
typedef int (*device_set_fn)(int);
/* ABI-only HIP dim3/opaque pointer definitions; no ROCm headers or linking. */
typedef struct { unsigned x,y,z; } hip_dim3;
typedef int (*launch_fn)(const void *,hip_dim3,hip_dim3,void **,size_t,void *);
typedef int (*copy_async_fn)(void *,const void *,size_t,int,void *);
typedef int (*set_async_fn)(void *,int,size_t,void *);
typedef int (*matmul_fn)(void *,void *,const void *,const void *,void *,const void *,void *,
    const void *,const void *,void *,void *,void *,const void *,void *,size_t,void *);

struct sample {
    void *start,*end;
    uint64_t cpu_ns,wrapper_ns;
    uintptr_t caller_rva,model,router;
    int32_t position,model_position,count,input_token,result,spec_n,spec_base,draft[3];
    uintptr_t wrapper_caller;int32_t wrapper_offset,wrapper_restore,wrapper_result;
    unsigned wrapper_present,wrapper_complete;
    unsigned kernels,lt_calls,copies,sets,syncs,sync_copies,sync_2d_copies,stream_syncs,native_events,nondefault,recorded;
};
static struct sample samples[TRACE_LIMIT];
static _Thread_local struct sample *active_sample;
struct wrapper_context {
    struct sample *sample;
    uintptr_t caller,model;
    int32_t token,offset,restore;
    unsigned forwards;
};
static _Thread_local struct wrapper_context *active_wrapper;
static head_fn original_head;
static wrapper_fn original_wrapper;
static uintptr_t engine_base,model_identity,router_identity;
static event_create_fn event_create;
static event_record_fn event_record;
static event_one_fn event_sync,event_destroy;
static event_elapsed_fn event_elapsed;
static device_get_fn device_get;
static device_set_fn device_set;
static sync_fn real_sync;
static stream_sync_fn real_stream_sync;
static copy_fn real_copy;
static copy_2d_fn real_copy_2d;
static event_record_fn real_native_event_record;
static launch_fn real_launch;
static copy_async_fn real_copy_async;
static set_async_fn real_set_async;
static matmul_fn real_matmul;
static pthread_once_t symbols_once=PTHREAD_ONCE_INIT;
static pthread_mutex_t trace_mutex=PTHREAD_MUTEX_INITIALIZER;
static _Atomic int pool_state,armed_once,harvested;
static unsigned trace_count,created_events,forward_calls,count1_calls,excluded_count_calls,limit_skipped_calls;
static unsigned wrapper_calls,wrapper_with_forward,wrapper_without_forward;
static int trace_dir=-1,trace_log=-1,device_ordinal=-1;
static size_t trace_bytes;
static const char *trace_error;
static pthread_t worker;

static _Noreturn void fatal(const char *reason) {
    dprintf(STDERR_FILENO,"[mtp-full-event-tap] fatal reason=%s errno=%d\n",reason,errno);
    _exit(79);
}
static int mapped_span(uintptr_t address,size_t bytes,const char *wanted) {
    if (!address || !bytes || bytes>UINTPTR_MAX-address) return 0;
    FILE *file=fopen("/proc/self/maps","re");
    if (!file) return 0;
    char line[4096],perms[5];unsigned long low,high;int found=0;
    while (fgets(line,sizeof line,file)) {
        if (sscanf(line,"%lx-%lx %4s",&low,&high,perms)!=3) continue;
        if (address>=low && address+bytes<=high &&
            (wanted?!strcmp(perms,wanted):perms[0]=='r')) {found=1;break;}
    }
    if (ferror(file) || fclose(file)) return 0;
    return found;
}
static int mapped_read(uintptr_t address,size_t bytes) { return mapped_span(address,bytes,NULL); }
static uint64_t word64(const unsigned char *object,size_t offset) {
    uint64_t value;memcpy(&value,object+offset,sizeof value);return value;
}
static int32_t word32(const unsigned char *object,size_t offset) {
    int32_t value;memcpy(&value,object+offset,sizeof value);return value;
}
static void resolve_symbols(void) {
    real_sync=(sync_fn)dlsym(RTLD_NEXT,"hipDeviceSynchronize");
    real_stream_sync=(stream_sync_fn)dlsym(RTLD_NEXT,"hipStreamSynchronize");
    real_copy=(copy_fn)dlsym(RTLD_NEXT,"hipMemcpy");
    real_copy_2d=(copy_2d_fn)dlsym(RTLD_NEXT,"hipMemcpy2D");
    real_native_event_record=(event_record_fn)dlsym(RTLD_NEXT,"hipEventRecord");
    real_launch=(launch_fn)dlsym(RTLD_NEXT,"hipLaunchKernel");
    real_copy_async=(copy_async_fn)dlsym(RTLD_NEXT,"hipMemcpyAsync");
    real_set_async=(set_async_fn)dlsym(RTLD_NEXT,"hipMemsetAsync");
    real_matmul=(matmul_fn)dlsym(RTLD_NEXT,"hipblasLtMatmul");
}
static void observe(unsigned *counter,void *stream) {
    if (active_sample) {(*counter)++;if(stream) active_sample->nondefault++;}
}
int hipDeviceSynchronize(void) {
    if (pthread_once(&symbols_once,resolve_symbols) || !real_sync) fatal("sync-symbol");
    if (active_sample) active_sample->syncs++;
    return real_sync();
}
int hipStreamSynchronize(void *stream) {
    if (pthread_once(&symbols_once,resolve_symbols) || !real_stream_sync) fatal("stream-sync-symbol");
    if (active_sample) observe(&active_sample->stream_syncs,stream);
    return real_stream_sync(stream);
}
int hipMemcpy(void *dst,const void *src,size_t bytes,int kind) {
    if (pthread_once(&symbols_once,resolve_symbols) || !real_copy) fatal("sync-copy-symbol");
    if (active_sample) active_sample->sync_copies++;
    return real_copy(dst,src,bytes,kind);
}
int hipEventRecord(void *event,void *stream) {
    if (pthread_once(&symbols_once,resolve_symbols) || !real_native_event_record) fatal("native-event-symbol");
    if (active_sample) observe(&active_sample->native_events,stream);
    return real_native_event_record(event,stream);
}
int hipMemcpy2D(void *dst,size_t dst_pitch,const void *src,size_t src_pitch,size_t width,size_t height,int kind) {
    if (pthread_once(&symbols_once,resolve_symbols) || !real_copy_2d) fatal("sync-copy2d-symbol");
    if (active_sample) active_sample->sync_2d_copies++;
    return real_copy_2d(dst,dst_pitch,src,src_pitch,width,height,kind);
}
int hipLaunchKernel(const void *function,hip_dim3 grid,hip_dim3 block,void **args,size_t shared,void *stream) {
    if (pthread_once(&symbols_once,resolve_symbols) || !real_launch) fatal("launch-symbol");
    if (active_sample) observe(&active_sample->kernels,stream);
    return real_launch(function,grid,block,args,shared,stream);
}
int hipMemcpyAsync(void *dst,const void *src,size_t bytes,int kind,void *stream) {
    if (pthread_once(&symbols_once,resolve_symbols) || !real_copy_async) fatal("copy-symbol");
    if (active_sample) observe(&active_sample->copies,stream);
    return real_copy_async(dst,src,bytes,kind,stream);
}
int hipMemsetAsync(void *dst,int value,size_t bytes,void *stream) {
    if (pthread_once(&symbols_once,resolve_symbols) || !real_set_async) fatal("set-symbol");
    if (active_sample) observe(&active_sample->sets,stream);
    return real_set_async(dst,value,bytes,stream);
}
int hipblasLtMatmul(void *handle,void *desc,const void *alpha,const void *a,void *a_desc,
    const void *b,void *b_desc,const void *beta,const void *c,void *c_desc,void *d,void *d_desc,
    const void *algo,void *workspace,size_t bytes,void *stream) {
    if (pthread_once(&symbols_once,resolve_symbols) || !real_matmul) fatal("matmul-symbol");
    if (active_sample) observe(&active_sample->lt_calls,stream);
    return real_matmul(handle,desc,alpha,a,a_desc,b,b_desc,beta,c,c_desc,d,d_desc,algo,workspace,bytes,stream);
}
static int append_bytes(int fd,const void *data,size_t bytes) {
    if (bytes>TRACE_BYTE_LIMIT-trace_bytes) return 0;
    const unsigned char *at=data;
    while (bytes) {
        ssize_t n=write(fd,at,bytes);
        if (n<0 && errno==EINTR) continue;
        if (n<=0) return 0;
        at+=n;bytes-=(size_t)n;trace_bytes+=(size_t)n;
    }
    return 1;
}
static int save_text(const char *name,const char *data,size_t bytes) {
    int fd=openat(trace_dir,name,O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC|O_NOFOLLOW,0600);
    if (fd<0) return 0;
    int ok=append_bytes(fd,data,bytes);
    if (fsync(fd)) ok=0;
    if (close(fd)) ok=0;
    return ok;
}
static void disable(const char *reason) {
    if (!trace_error) {
        trace_error=reason;
        /* Publish the reason only at post-response harvest; no hot-path write. */
    }
}
static int trigger(const char *name,const char *wanted,size_t bytes) {
    int fd=openat(trace_dir,name,O_RDONLY|O_CLOEXEC|O_NOFOLLOW);
    if (fd<0) return errno==ENOENT?0:-1;
    struct stat before,after;char content[64];
    int ok=bytes<sizeof content && !fstat(fd,&before) && S_ISREG(before.st_mode) && before.st_nlink==1 &&
        before.st_size==(off_t)bytes && pread(fd,content,sizeof content,0)==(ssize_t)bytes &&
        !memcmp(content,wanted,bytes) && !fstat(fd,&after) &&
        before.st_dev==after.st_dev && before.st_ino==after.st_ino && before.st_size==after.st_size &&
        before.st_mtim.tv_sec==after.st_mtim.tv_sec && before.st_mtim.tv_nsec==after.st_mtim.tv_nsec;
    if (close(fd)) ok=0;
    return ok?1:-1;
}
static uintptr_t router_pointer(void) {
    uintptr_t value;memcpy(&value,(void *)(engine_base+ROUTER_RVA),sizeof value);return value;
}
static int router_stream_zero(uintptr_t pointer) {
    return !pointer || (!word64((const unsigned char *)pointer,0x48));
}
static uint64_t elapsed_ns(struct timespec before,struct timespec after) {
    return (uint64_t)(after.tv_sec-before.tv_sec)*1000000000ULL +
        (uint64_t)(after.tv_nsec-before.tv_nsec);
}
static int destroy_pool(void) {
    int ok=1;
    for (unsigned i=0;i<TRACE_LIMIT;i++) {
        if (samples[i].start && event_destroy(samples[i].start)) {disable("event-destroy");ok=0;}
        if (samples[i].end && event_destroy(samples[i].end)) {disable("event-destroy");ok=0;}
        samples[i].start=samples[i].end=NULL;
    }
    return ok;
}
static void harvest(void) {
    if (pthread_mutex_lock(&trace_mutex)) return;
    atomic_store(&harvested,1);
    /* Freeze before waiting. No new sample can reuse events after this point. */
    if (!trace_count) disable("no-samples");
    if (device_set(device_ordinal)) disable("harvest-device");
    unsigned final_syncs=0;
    if (!trace_error) {
        if (!samples[trace_count-1].recorded) disable("final-event-missing");
        else {final_syncs=1;if(event_sync(samples[trace_count-1].end)) disable("final-event-sync");}
    }
    char buffer[131072];size_t used=0;
    int n=snprintf(buffer,sizeof buffer,
        "{\"schema\":1,\"calls\":%u,\"limit_reached\":%s,\"device\":%d,\"event_stream\":0,"
        "\"forward_calls\":%u,\"count1_calls\":%u,\"excluded_count_calls\":%u,\"limit_skipped_calls\":%u,"
        "\"wrapper_calls\":%u,\"wrapper_with_forward\":%u,\"wrapper_without_forward\":%u,"
        "\"post_request_final_event_syncs\":%u,\"per_call_syncs\":0,\"per_call_copies\":0,"
        "\"event_flags\":0,\"samples\":[\n",trace_count,trace_count==TRACE_LIMIT?"true":"false",
        device_ordinal,forward_calls,count1_calls,excluded_count_calls,limit_skipped_calls,
        wrapper_calls,wrapper_with_forward,wrapper_without_forward,final_syncs);
    if (n<=0 || n>=(int)sizeof buffer) disable("harvest-header");else used=(size_t)n;
    for (unsigned i=0;i<trace_count && !trace_error;i++) {
        float ms=0;
        if (!samples[i].recorded || samples[i].nondefault ||
            !samples[i].kernels || event_elapsed(&ms,samples[i].start,samples[i].end) ||
            !isfinite(ms) || ms<=0) {disable("event-elapsed-or-stream");break;}
        struct sample *s=&samples[i];
        n=snprintf(buffer+used,sizeof buffer-used,
            "%s{\"index\":%u,\"gpu_bracket_ms\":%.9g,\"cpu_forward_instrumented_ns\":%" PRIu64
            ",\"caller_rva\":\"0x%" PRIxPTR "\",\"model\":\"0x%" PRIxPTR
            "\",\"router_handle\":\"0x%" PRIxPTR "\",\"position\":%d,\"model_position\":%d,\"count\":%d,"
            "\"input_token\":%d,\"result\":%d,\"spec_n\":%d,\"spec_base\":%d,\"draft_cache\":[%d,%d,%d],"
            "\"wrapper_present\":%s,\"wrapper_complete\":%s,\"cpu_wrapper_instrumented_ns\":%" PRIu64 ","
            "\"wrapper_caller_rva\":\"0x%" PRIxPTR "\",\"wrapper_offset\":%d,\"wrapper_restore_low_byte\":%d,"
            "\"wrapper_result\":%d,\"kernel_launches\":%u,\"hipblaslt_calls\":%u,"
            "\"original_async_copies\":%u,\"original_async_sets\":%u,\"original_device_syncs\":%u,"
            "\"original_sync_copies\":%u,\"original_sync_2d_copies\":%u,\"original_stream_syncs\":%u,\"original_event_records\":%u,"
            "\"nondefault_stream_ops\":%u}\n",
            i?",":"",i,(double)ms,s->cpu_ns,s->caller_rva,s->model,s->router,s->position,s->model_position,
            s->count,s->input_token,s->result,s->spec_n,s->spec_base,s->draft[0],s->draft[1],s->draft[2],
            s->wrapper_present?"true":"false",s->wrapper_complete?"true":"false",s->wrapper_ns,
            s->wrapper_caller,s->wrapper_offset,s->wrapper_restore,s->wrapper_result,s->kernels,s->lt_calls,
            s->copies,s->sets,s->syncs,s->sync_copies,s->sync_2d_copies,s->stream_syncs,s->native_events,s->nondefault);
        if (n<=0 || (size_t)n>=sizeof buffer-used) {disable("harvest-budget");break;}
        used+=(size_t)n;
    }
    if (used && used+4<sizeof buffer) {
        memcpy(buffer+used,"]}\n",3);used+=3;
        if (!save_text("timings.json",buffer,used)) disable("timings-write");
    }
    int destroyed=destroy_pool();
    char complete[512];
    n=snprintf(complete,sizeof complete,
        "{\"schema\":1,\"passed\":%s,\"calls\":%u,\"created_events\":%u,\"events_destroyed\":%s,"
        "\"error\":%s%s%s,\"instrumented\":true}\n",trace_error?"false":"true",trace_count,created_events,
        destroyed?"true":"false",trace_error?"\"":"",trace_error?trace_error:"null",trace_error?"\"":"");
    if (n<=0 || n>=(int)sizeof complete || !save_text("complete.json",complete,(size_t)n))
        disable("complete-write");
    (void)pthread_mutex_unlock(&trace_mutex);
}
static void *harvest_worker(void *unused) {
    (void)unused;
    struct timespec began,now,delay={0,20000000};
    if (clock_gettime(CLOCK_MONOTONIC,&began)) return NULL;
    for (;;) {
        int requested=trigger("harvest",harvest_content,sizeof harvest_content-1);
        if (requested) {
            if (requested<0) {
                if (!pthread_mutex_lock(&trace_mutex)) {disable("harvest-content");(void)pthread_mutex_unlock(&trace_mutex);}
            }
            harvest();return NULL;
        }
        if (clock_gettime(CLOCK_MONOTONIC,&now) || now.tv_sec-began.tv_sec>1800) return NULL;
        (void)nanosleep(&delay,NULL);
    }
}
static void prepare_pool(void) {
    if (pthread_mutex_lock(&trace_mutex)) return;
    if (!atomic_load(&pool_state)) {
        if (trigger("armed",arm_content,sizeof arm_content-1)!=0) disable("armed-before-pool");
        if (pthread_once(&symbols_once,resolve_symbols) || !real_launch || !real_copy_async || !real_set_async || !real_matmul ||
            !real_sync || !real_copy || !real_copy_2d || !real_stream_sync || !real_native_event_record)
            disable("launch-symbols");
        event_create=(event_create_fn)dlsym(RTLD_NEXT,"hipEventCreateWithFlags");
        event_record=(event_record_fn)dlsym(RTLD_NEXT,"hipEventRecord");
        event_sync=(event_one_fn)dlsym(RTLD_NEXT,"hipEventSynchronize");
        event_destroy=(event_one_fn)dlsym(RTLD_NEXT,"hipEventDestroy");
        event_elapsed=(event_elapsed_fn)dlsym(RTLD_NEXT,"hipEventElapsedTime");
        device_get=(device_get_fn)dlsym(RTLD_NEXT,"hipGetDevice");
        device_set=(device_set_fn)dlsym(RTLD_NEXT,"hipSetDevice");
        if (!event_create || !event_record || !event_sync || !event_destroy || !event_elapsed || !device_get || !device_set)
            disable("event-symbols");
        if (!trace_error && (device_get(&device_ordinal) || device_ordinal!=0)) disable("prepare-device");
        for (unsigned i=0;i<TRACE_LIMIT && !trace_error;i++) {
            if (event_create(&samples[i].start,0)) {disable("event-create-start");break;}created_events++;
            if (event_create(&samples[i].end,0)) {disable("event-create-end");break;}created_events++;
        }
        if (!trace_error && pthread_create(&worker,NULL,harvest_worker,NULL)) disable("harvest-thread");
        if (!trace_error && pthread_detach(worker)) disable("harvest-detach");
        char ready[512];
        int n=snprintf(ready,sizeof ready,
            "{\"schema\":1,\"ready\":%s,\"created_events\":%u,\"device\":%d,\"event_flags\":0,"
            "\"before_arming\":true,\"error\":%s%s%s}\n",trace_error?"false":"true",created_events,device_ordinal,
            trace_error?"\"":"",trace_error?trace_error:"null",trace_error?"\"":"");
        if (n<=0 || n>=(int)sizeof ready || !save_text("prepared.json",ready,(size_t)n)) disable("prepared-write");
        atomic_store(&pool_state,trace_error?-1:1);
    }
    (void)pthread_mutex_unlock(&trace_mutex);
}
static int armed_locked(void) {
    if (trace_error || atomic_load(&harvested) || atomic_load(&pool_state)!=1) return 0;
    int arm=atomic_load(&armed_once)?1:trigger("armed",arm_content,sizeof arm_content-1);
    if (arm==1) atomic_store(&armed_once,1);else if(arm<0) disable("arm-content");
    return arm==1;
}
static int known_forward_caller(uintptr_t caller) {
    return caller==0x17dcc08 || caller==0x17dcd54 || caller==0x17dcf49 || caller==0x17de236;
}
static int known_wrapper_caller(uintptr_t caller) {
    return caller==0x172dd80 || caller==0x172df19 || caller==0x172e313 ||
        caller==0x173b688 || caller==0x173b6b6;
}
static int native_callbacks_absent(const unsigned char *model) {
    /* Exact native std::function manager guards for block/MLP/attention
     * callbacks. Preserve their native behavior but reject unproved scope. */
    return !word64(model,0x270) && !word64(model,0x2b0) &&
        !word64(model,0x2d0) && !word64(model,0x2f0);
}
static int32_t tapped_head(void *object,const int32_t *tokens,int32_t count,int32_t position) {
    int incoming_errno=errno;
    /* Pool creation is confined to the first ordinary unarmed forward. */
    if (!atomic_load(&pool_state)) prepare_pool();
    if (atomic_load(&pool_state)!=1 || atomic_load(&harvested)) {
        errno=incoming_errno;return original_head(object,tokens,count,position);
    }
    if (pthread_mutex_lock(&trace_mutex)) {errno=incoming_errno;return original_head(object,tokens,count,position);}
    if (!armed_locked()) {
        (void)pthread_mutex_unlock(&trace_mutex);errno=incoming_errno;
        return original_head(object,tokens,count,position);
    }
    forward_calls++;
    if (active_wrapper) active_wrapper->forwards++;
    if (count!=1) {
        excluded_count_calls++;
        (void)pthread_mutex_unlock(&trace_mutex);errno=incoming_errno;
        return original_head(object,tokens,count,position);
    }
    count1_calls++;
    if (trace_count>=TRACE_LIMIT) {
        limit_skipped_calls++;
        (void)pthread_mutex_unlock(&trace_mutex);errno=incoming_errno;
        return original_head(object,tokens,count,position);
    }
    uintptr_t model=(uintptr_t)object,caller=(uintptr_t)__builtin_return_address(0)-engine_base,router=router_pointer();
    int ok=known_forward_caller(caller);
    if (!model_identity && ok) {
        ok=mapped_read(model,0xb10) && (!router || mapped_read(router,0x50));
        if (ok) {model_identity=model;router_identity=router;}
    }
    /* The pinned callers pass an ordinary token array which the native ABI also
     * consumes. Avoid a /proc file read in every sampled wrapper duration. */
    ok=ok && model==model_identity && router==router_identity && router_stream_zero(router) && tokens;
    if (ok && !native_callbacks_absent(object)) {disable("native-callback-present");ok=0;}
    if (active_wrapper) ok=ok && caller==0x17dcf49 && active_wrapper->model==model &&
        active_wrapper->forwards==1 && known_wrapper_caller(active_wrapper->caller);
    else ok=ok && caller!=0x17dcf49;
    if (!ok) disable("entry-stream-model-or-wrapper-contract");
    struct sample *s=ok?&samples[trace_count++]:NULL;
    if (s) {
        s->caller_rva=caller;s->model=model;s->router=router;s->count=count;s->position=position;
        s->model_position=word32(object,0x220);memcpy(&s->input_token,tokens,sizeof s->input_token);
        s->spec_n=word32(object,0x18);s->spec_base=word32(object,0x1c);
        for(unsigned j=0;j<3;j++) s->draft[j]=word32(object,0x40+j*4);
        if (active_wrapper) {
            s->wrapper_present=1;s->wrapper_caller=active_wrapper->caller;
            s->wrapper_offset=active_wrapper->offset;s->wrapper_restore=active_wrapper->restore&255;
            active_wrapper->sample=s;
        }
        if (event_record(s->start,NULL)) {disable("start-event-record");s=NULL;}
    }
    struct timespec before={0},after={0};
    if (s && clock_gettime(CLOCK_MONOTONIC_RAW,&before)) {disable("cpu-clock-start");s=NULL;}
    active_sample=s;
    errno=incoming_errno;
    int32_t result=original_head(object,tokens,count,position);
    int result_errno=errno;
    active_sample=NULL;
    if (s) {
        s->result=result;
        if (clock_gettime(CLOCK_MONOTONIC_RAW,&after)) disable("cpu-clock-end");
        else s->cpu_ns=elapsed_ns(before,after);
        if (event_record(s->end,NULL)) disable("end-event-record");else s->recorded=1;
        if (s->nondefault || router_pointer()!=router || !router_stream_zero(router)) disable("executed-nondefault-stream");
        if (!native_callbacks_absent(object)) disable("native-callback-manager-changed");
    }
    if (pthread_mutex_unlock(&trace_mutex)) disable("mutex-unlock");
    errno=result_errno;return result;
}
static int32_t tapped_wrapper(void *object,int32_t token,int32_t offset,int32_t restore) {
    int incoming_errno=errno;
    if (atomic_load(&pool_state)!=1 || atomic_load(&harvested) || active_wrapper) {
        errno=incoming_errno;return original_wrapper(object,token,offset,restore);
    }
    if (pthread_mutex_lock(&trace_mutex)) {errno=incoming_errno;return original_wrapper(object,token,offset,restore);}
    int arm=armed_locked();
    if (arm) wrapper_calls++;
    (void)pthread_mutex_unlock(&trace_mutex);
    if (!arm) {errno=incoming_errno;return original_wrapper(object,token,offset,restore);}
    struct wrapper_context context={.caller=(uintptr_t)__builtin_return_address(0)-engine_base,
        .model=(uintptr_t)object,.token=token,.offset=offset,.restore=restore};
    struct timespec before={0},after={0};
    int clock_ok=!clock_gettime(CLOCK_MONOTONIC_RAW,&before);
    active_wrapper=&context;errno=incoming_errno;
    int32_t result=original_wrapper(object,token,offset,restore);
    int result_errno=errno;
    active_wrapper=NULL;
    if (clock_gettime(CLOCK_MONOTONIC_RAW,&after)) clock_ok=0;
    if (!pthread_mutex_lock(&trace_mutex)) {
        if (!known_wrapper_caller(context.caller) || !clock_ok) disable("wrapper-caller-or-clock");
        if (context.forwards) wrapper_with_forward++;else wrapper_without_forward++;
        if (context.sample) {
            context.sample->wrapper_ns=elapsed_ns(before,after);context.sample->wrapper_result=result;
            context.sample->wrapper_complete=1;
            if (context.forwards!=1 || result!=context.sample->result || token!=context.sample->input_token)
                disable("wrapper-forward-parity");
        }
        (void)pthread_mutex_unlock(&trace_mutex);
    }
    errno=result_errno;return result;
}

static void verify_hash(int fd, off_t offset, size_t bytes, const char *wanted) {
    EVP_MD_CTX *ctx = EVP_MD_CTX_new();
    if (!ctx || EVP_DigestInit_ex(ctx,EVP_sha256(),NULL) != 1) fatal("hash-init");
    unsigned char buffer[65536],digest[32]; unsigned length = 0;
    while (bytes) {
        size_t amount = bytes < sizeof buffer ? bytes : sizeof buffer;
        ssize_t got = pread(fd,buffer,amount,offset);
        if (got < 0 && errno == EINTR) continue;
        if (got <= 0 || EVP_DigestUpdate(ctx,buffer,(size_t)got) != 1) fatal("hash-read");
        offset += got; bytes -= (size_t)got;
    }
    if (EVP_DigestFinal_ex(ctx,digest,&length) != 1 || length != sizeof digest) fatal("hash-final");
    EVP_MD_CTX_free(ctx);
    char hex[65];
    for (size_t i=0;i<sizeof digest;i++) snprintf(hex+i*2,3,"%02x",digest[i]);
    if (strcmp(hex,wanted)) fatal("hash-mismatch");
}
struct site { uintptr_t entry,wrapper,base; int found,wrapper_found,globals_found; };
static int find_site(struct dl_phdr_info *info, size_t ignored, void *opaque) {
    (void)ignored;
    if (info->dlpi_name && *info->dlpi_name) return 0;
    struct site *site = opaque;
    if (ENTRY_RVA > UINTPTR_MAX-info->dlpi_addr) fatal("base-overflow");
    for (size_t i=0;i<info->dlpi_phnum;i++) {
        const Elf64_Phdr *p = &info->dlpi_phdr[i];
        if (p->p_type == PT_LOAD && p->p_flags == (PF_R|PF_X) &&
            p->p_vaddr <= ENTRY_RVA && ENTRY_RVA + FUNCTION_BYTES <= p->p_vaddr + p->p_filesz &&
            p->p_offset + ENTRY_RVA - p->p_vaddr == (uint64_t)ENTRY_OFFSET) {
            site->entry=info->dlpi_addr+ENTRY_RVA;site->base=info->dlpi_addr;site->found++;
        }
        if (p->p_type==PT_LOAD && p->p_flags==(PF_R|PF_X) &&
            p->p_vaddr<=WRAPPER_RVA && WRAPPER_RVA+WRAPPER_BYTES<=p->p_vaddr+p->p_filesz &&
            p->p_offset+WRAPPER_RVA-p->p_vaddr==(uint64_t)WRAPPER_OFFSET) {
            site->wrapper=info->dlpi_addr+WRAPPER_RVA;site->wrapper_found++;
        }
        if (p->p_type==PT_LOAD && p->p_flags==(PF_R|PF_W) &&
            p->p_vaddr<=ROUTER_RVA && ROUTER_RVA+sizeof(uintptr_t)<=p->p_vaddr+p->p_memsz)
            site->globals_found++;
    }
    return 1;
}
static void absolute_jump(unsigned char *at, uintptr_t target) {
    const unsigned char prefix[6] = {0xff,0x25,0,0,0,0};
    memcpy(at,prefix,sizeof prefix);memcpy(at+6,&target,sizeof target);
}
static uintptr_t install_hook(uintptr_t entry,const unsigned char *signature,size_t signature_bytes,
    size_t relocated,uintptr_t target) {
    long size=sysconf(_SC_PAGESIZE);
    if (size<=0 || ((unsigned long)size&((unsigned long)size-1))) fatal("page-size");
    uintptr_t page=entry&~((uintptr_t)size-1);unsigned char *thunk=NULL;
    if (entry+signature_bytes>page+(uintptr_t)size) fatal("entry-page");
    if (!mapped_span(page,(size_t)size,"r-xp")) fatal("entry-page-rx");
    for (unsigned i=0;i<256;i++) {
        uintptr_t distance=(uintptr_t)(i/2+1)*0x200000;
        if ((i&1)?page<distance:distance>UINTPTR_MAX-page) continue;
        uintptr_t candidate=(i&1)?page-distance:page+distance;
        void *area=mmap((void *)candidate,(size_t)size,PROT_READ|PROT_WRITE,
            MAP_PRIVATE|MAP_ANONYMOUS|MAP_FIXED_NOREPLACE,-1,0);
        if (area==MAP_FAILED) {if(errno==EEXIST)continue;fatal("thunk-map");}
        if (area!=(void *)candidate) {
            if (munmap(area,(size_t)size)) fatal("thunk-unmap");
            fatal("fixed-noreplace");
        }
        thunk=area;break;
    }
    if (!thunk) fatal("thunk-exhausted");
    absolute_jump(thunk,target);
    /* Complete position-independent instructions, proved against the pinned ELF. */
    memcpy(thunk+64,signature,relocated);absolute_jump(thunk+64+relocated,entry+relocated);
    if (mprotect(thunk,(size_t)size,PROT_READ|PROT_EXEC) ||
        !mapped_span((uintptr_t)thunk,(size_t)size,"r-xp")) fatal("thunk-rx");
    intptr_t relative=(intptr_t)((uintptr_t)thunk-(entry+5));
    if (relative<INT32_MIN || relative>INT32_MAX) fatal("jump-range");
    unsigned char jump[5]={0xe9};int32_t delta=(int32_t)relative;memcpy(jump+1,&delta,4);
    if (mprotect((void *)page,(size_t)size,PROT_READ|PROT_WRITE)) fatal("entry-rw");
    memcpy((void *)entry,jump,5);
    if (relocated>5) memset((unsigned char *)entry+5,0x90,relocated-5);
    __builtin___clear_cache((char *)entry,(char *)entry+relocated);
    if (mprotect((void *)page,(size_t)size,PROT_READ|PROT_EXEC) ||
        !mapped_span(page,(size_t)size,"r-xp")) fatal("entry-rx");

    return (uintptr_t)(thunk+64);
}
static int serving_process(void) {
    /* The pinned entrypoint first runs flash_serve --resident-gib to read its
     * checkpoint header. Only its subsequent --ck serving process owns a trace. */
    int fd=open("/proc/self/cmdline",O_RDONLY|O_CLOEXEC);
    char command[4096]; ssize_t bytes;
    if (fd<0) fatal("cmdline-open");
    do { bytes=read(fd,command,sizeof command); } while (bytes<0 && errno==EINTR);
    if (bytes<=0 || bytes>=(ssize_t)sizeof command || command[bytes-1] || close(fd))
        fatal("cmdline-read");
    const char *argument=memchr(command,0,(size_t)bytes);
    if (!argument || argument+1>=command+bytes) return 0;
    return !strcmp(argument+1,"--ck");
}
__attribute__((constructor)) static void install(void) {
    char name[4096]; ssize_t n = readlink("/proc/self/exe",name,sizeof name-1);
    if (n < 0 || n >= (ssize_t)sizeof name-1) fatal("executable-name");
    name[n]=0; const char *base=strrchr(name,'/');base=base?base+1:name;
    if (strcmp(base,"flash_serve")) return;
    if (!serving_process()) return;
    const char *mode=getenv("HALOGEN_MTP_FULL_EVENT_TAP"),*directory=getenv("HALOGEN_MTP_FULL_EVENT_TAP_DIR");
    if (!mode || strcmp(mode,"full-events128-v1") || !directory ||
        strncmp(directory,trace_prefix,sizeof trace_prefix - 1) ||
        strlen(directory) != sizeof trace_prefix - 1 + 32) fatal("configuration");
    for (const char *at=directory + sizeof trace_prefix - 1; *at; at++)
        if (!((*at>='0' && *at<='9') || (*at>='a' && *at<='f'))) fatal("trace-run-id");
    int fd=open("/proc/self/exe",O_RDONLY|O_CLOEXEC);struct stat before,after;
    if (fd<0 || fstat(fd,&before) || !S_ISREG(before.st_mode) || before.st_size<=ENTRY_OFFSET) fatal("executable-stat");
    Elf64_Ehdr eh;
    if (pread(fd,&eh,sizeof eh,0)!=(ssize_t)sizeof eh || memcmp(eh.e_ident,ELFMAG,SELFMAG) ||
        eh.e_ident[EI_CLASS]!=ELFCLASS64 || eh.e_ident[EI_DATA]!=ELFDATA2LSB ||
        eh.e_type!=ET_DYN || eh.e_machine!=EM_X86_64) fatal("elf-identity");
    verify_hash(fd,0,(size_t)before.st_size,ENGINE_SHA);
    verify_hash(fd,ENTRY_OFFSET,FUNCTION_BYTES,FUNCTION_SHA);
    verify_hash(fd,WRAPPER_OFFSET,WRAPPER_BYTES,WRAPPER_SHA);
    if (fstat(fd,&after) || before.st_dev!=after.st_dev || before.st_ino!=after.st_ino ||
        before.st_size!=after.st_size || before.st_mtim.tv_sec!=after.st_mtim.tv_sec ||
        before.st_mtim.tv_nsec!=after.st_mtim.tv_nsec || before.st_ctim.tv_sec!=after.st_ctim.tv_sec ||
        before.st_ctim.tv_nsec!=after.st_ctim.tv_nsec || close(fd)) fatal("executable-consistency");
    struct site site={0};
    if (dl_iterate_phdr(find_site,&site)!=1 || site.found!=1 || site.wrapper_found!=1 || site.globals_found!=1 ||
        !mapped_span(site.base+ROUTER_RVA,ROUTER_RVA+sizeof(uintptr_t)-ROUTER_RVA,"rw-p") ||
        !mapped_span(site.entry,FUNCTION_BYTES,"r-xp") || memcmp((void *)site.entry,entry_signature,sizeof entry_signature))
        fatal("entry-signature");
    if (!mapped_span(site.wrapper,WRAPPER_BYTES,"r-xp") ||
        memcmp((void *)site.wrapper,wrapper_signature,sizeof wrapper_signature)) fatal("wrapper-signature");
    engine_base=site.base;
    int tmp_dir=open("/tmp",O_RDONLY|O_DIRECTORY|O_CLOEXEC|O_NOFOLLOW);
    struct stat tmp_stat;
    if (tmp_dir<0 || fstat(tmp_dir,&tmp_stat) || !S_ISDIR(tmp_stat.st_mode)) fatal("tmp-directory");
    const char *trace_name=directory + sizeof "/tmp/" - 1;
    if (mkdirat(tmp_dir,trace_name,0700)) fatal("timing-mkdir");
    trace_dir=openat(tmp_dir,trace_name,O_RDONLY|O_DIRECTORY|O_CLOEXEC|O_NOFOLLOW);
    if (close(tmp_dir)) fatal("tmp-close");
    if (trace_dir<0) fatal("timing-directory");
    trace_log=openat(trace_dir,"activation.json",O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC|O_NOFOLLOW,0600);
    if (trace_log<0) fatal("trace-log");
    original_head=(head_fn)install_hook(site.entry,entry_signature,sizeof entry_signature,5,(uintptr_t)tapped_head);
    original_wrapper=(wrapper_fn)install_hook(site.wrapper,wrapper_signature,sizeof wrapper_signature,8,(uintptr_t)tapped_wrapper);

    /* Controller later adds two exclusive trigger files; six files total. */
    trace_bytes=sizeof arm_content+sizeof harvest_content-2;
    char header[1536];
    int header_n=snprintf(header,sizeof header,
        "{\"schema\":1,\"mode\":\"full-events128-v1\",\"engine_sha256\":\"%s\","
        "\"function_sha256\":\"%s\",\"entry_rva\":\"0x17db310\",\"limit\":128,"
        "\"wrapper_sha256\":\"%s\",\"wrapper_rva\":\"0x17dcde0\",\"count\":1,\"event_flags\":0,\"event_stream\":0,"
        "\"per_call_sync\":false,\"per_call_copy\":false,\"per_call_file_write\":false,"
        "\"native_callback_managers_required_zero\":[624,688,720,752],"
        "\"timing_scope\":\"instrumented stream0 complete MTP forward including input transforms/block/vocabulary projection/argmax/native sync and result copy; wrapper host duration separate; sampled-only sampler excluded\","
        "\"acceptance_scope\":\"unqualified speculative calls\",\"file_limit\":6,\"byte_limit\":262144}\n",
        ENGINE_SHA,FUNCTION_SHA,WRAPPER_SHA);
    if (header_n<=0 || header_n>=(int)sizeof header || !append_bytes(trace_log,header,(size_t)header_n) ||
        close(trace_log)) fatal("activation-log");
    trace_log=-1;
}
