#define _GNU_SOURCE
#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <link.h>
#include <pthread.h>
#include <poll.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <sys/syscall.h>
#include <time.h>
#include <unistd.h>

/* Exact installed x86-64 HIP ABI. Default-off diagnostic, never a kernel swap.
 * Events preserve the original stream. NULL-stream markers can wait on other
 * streams; elapsed values are instrumented stream brackets, not isolated kernel
 * durations or a GPU busy timeline. No arguments/tensor memory are inspected. */
typedef int hipError_t;
typedef struct ihipStream_t *hipStream_t;
typedef struct ihipEvent_t *hipEvent_t;
typedef struct ihipModuleSymbol_t *hipFunction_t;
typedef struct { uint32_t x,y,z; } dim3;
enum { POOL=512, PROBABILITY_DENOMINATOR=32, NOT_READY=600 };
enum { LAUNCH=1, TIMING=2, SNAPSHOT=3, MODULE_LAUNCH=4 };
#define MAX_BYTES (UINT64_C(32)*1024*1024)
struct header {
    char magic[8]; uint32_t version,header_size,record_size,clock_id;
    uint64_t main_base,max_bytes; uint32_t pid,pool;
    uint64_t denominator,seed;
};
/* Types1/4 describe all observed launches; type2 references a sampled launch
 * by sample_id and carries completed event timing. Type3 snapshots cumulative
 * counters: caller=seen, function=selected, stream=harvested, tid=pending,
 * sample_id=pool_full, shared=reentrant_skips, grid[0]=timing_disabled,
 * grid[1]=capture_skips, block[0]=created event handles. */
struct record {
    uint64_t sequence,start_ns,end_ns,caller,function,stream,tid,sample_id,shared;
    uint32_t grid[3],block[3],type;
    int32_t native_result,start_result,stop_result,query_result,elapsed_result;
    float elapsed_ms;
    uint32_t reserved;
};
_Static_assert(sizeof(struct header)==64,"header ABI");
_Static_assert(sizeof(struct record)==128,"record ABI");
_Static_assert(sizeof(dim3)==12 && sizeof(void*)==8,"HIP ABI");
_Static_assert(__BYTE_ORDER__==__ORDER_LITTLE_ENDIAN__,"little endian");
struct slot { hipEvent_t a,b; int pending; struct record record; };
static struct slot slots[POOL];
static pthread_mutex_t lock=PTHREAD_MUTEX_INITIALIZER;
static _Thread_local int nesting;
static _Atomic int enabled;
static _Atomic uint64_t reentrant_skips;
static int fd=-1, timing_disabled,created, destroyed, capture_skips,retired,deferred_cleanup;
static int wake_pipe[2]={-1,-1};
static const char *close_path;
static pid_t owner;
static uintptr_t base,begin[32],end[32]; static size_t ranges;
static uint64_t bytes,seq,seen,selected,harvested,pool_full;
static uint64_t rng=UINT64_C(0x79b2184e390f56a7);
static int (*event_create)(hipEvent_t*,unsigned);
static int (*event_record)(hipEvent_t,hipStream_t);
static int (*event_query)(hipEvent_t);
static int (*event_elapsed)(float*,hipEvent_t,hipEvent_t);
static int (*event_destroy)(hipEvent_t);
static int (*is_capturing)(hipStream_t,int*);
static int (*set_device)(int);
static int (*get_device)(int*);
static uint64_t sample_limit=8192;
static void *collector(void*);

static uint64_t now(void) {
    struct timespec t;
    if(clock_gettime(CLOCK_BOOTTIME,&t)) { atomic_store(&enabled,0); return 0; }
    return (uint64_t)t.tv_sec*UINT64_C(1000000000)+(uint64_t)t.tv_nsec;
}
static int find_main(struct dl_phdr_info *i,size_t n,void *p) {
    (void)n;(void)p;
    if(i->dlpi_name && *i->dlpi_name) return 0;
    base=i->dlpi_addr;
    for(unsigned j=0;j<i->dlpi_phnum;j++) {
        const ElfW(Phdr)*h=&i->dlpi_phdr[j];
        if(h->p_type==PT_LOAD && (h->p_flags&PF_X) && ranges<32) {
            begin[ranges]=base+h->p_vaddr;end[ranges]=begin[ranges]+h->p_memsz;ranges++;
        }
    }
    return 1;
}
static void append(struct record *r) {
    if(!atomic_load(&enabled)) return;
    if(bytes>MAX_BYTES-sizeof(*r)) {atomic_store(&enabled,0);return;}
    r->sequence=++seq;
    if(write(fd,r,sizeof(*r))!=(ssize_t)sizeof(*r)) {atomic_store(&enabled,0);return;}
    bytes+=sizeof(*r);
}
__attribute__((constructor)) static void initialize(void) {
    int saved=errno; char executable[4096];
    const char *path=getenv("HG0172_GPU_EVENTS_PATH");
    const char *expected="/usr/local/bin/flash_serve";
    ssize_t n=readlink("/proc/self/exe",executable,sizeof(executable));
    if(!path || n!=(ssize_t)strlen(expected) || memcmp(executable,expected,(size_t)n)) goto done;
    dl_iterate_phdr(find_main,NULL);if(!ranges) goto done;
    owner=getpid();fd=open(path,O_WRONLY|O_CREAT|O_EXCL|O_APPEND|O_CLOEXEC,0600);
    if(fd<0) goto done;
    struct header h={.magic={'H','G','G','E','0','1','7','2'},.version=1,.header_size=64,
        .record_size=128,.clock_id=CLOCK_BOOTTIME,.main_base=base,.max_bytes=MAX_BYTES,
        .pid=(uint32_t)owner,.pool=POOL,.denominator=PROBABILITY_DENOMINATOR,.seed=rng};
    if(write(fd,&h,sizeof(h))!=(ssize_t)sizeof(h)) goto done;
    if(pipe2(wake_pipe,O_CLOEXEC|O_NONBLOCK)) goto done;
    close_path=getenv("HG0172_GPU_EVENTS_CLOSE_PATH");
    bytes=sizeof(h);atomic_store(&enabled,1);
    pthread_t thread;
    if(pthread_create(&thread,NULL,collector,NULL)) {atomic_store(&enabled,0);goto done;}
    pthread_detach(thread);
done: errno=saved;
}
static void* target(const char *name) {
    void *p=dlsym(RTLD_NEXT,name);
    if(!p) { static const char m[]="gpu_events: missing native HIP target\n";
        ssize_t ignored=write(2,m,sizeof(m)-1);(void)ignored;_exit(127); }
    return p;
}
static int enter(void) {
    if(!atomic_load(&enabled)) return 0;
    if(getpid()!=owner) {atomic_store(&enabled,0);return 0;}
    if(nesting || pthread_mutex_trylock(&lock)) {atomic_fetch_add(&reentrant_skips,1);return 0;}
    nesting=1;return 1;
}
static void leave(void) {nesting=0;pthread_mutex_unlock(&lock);}
static void prepare_events(void) {
    event_create=dlsym(RTLD_NEXT,"hipEventCreateWithFlags");
    event_record=dlsym(RTLD_NEXT,"hipEventRecord");
    event_query=dlsym(RTLD_NEXT,"hipEventQuery");
    event_elapsed=dlsym(RTLD_NEXT,"hipEventElapsedTime");
    event_destroy=dlsym(RTLD_NEXT,"hipEventDestroy");
    is_capturing=dlsym(RTLD_NEXT,"hipStreamIsCapturing");
    get_device=dlsym(RTLD_NEXT,"hipGetDevice");
    if(!event_create||!event_record||!event_query||!event_elapsed||!event_destroy||!is_capturing||!get_device) {
        timing_disabled=1;return;
    }
    int device=-1;
    if(get_device(&device) || device!=0) {timing_disabled=1;return;}
    for(unsigned i=0;i<POOL;i++) {
        int a=event_create(&slots[i].a,0);if(!a) created++;
        int b=event_create(&slots[i].b,0);if(!b) created++;
        if(a||b) {timing_disabled=1;return;}
    }
}
static void harvest(void) {
    if(!event_query) return;
    for(unsigned i=0;i<POOL;i++) {
        struct slot*s=&slots[i];if(!s->pending) continue;
        struct record r=s->record;
        /* A failed stop/start marker is never reused: keep that slot until
         * process teardown. All remaining timing instrumentation is disabled. */
        if(r.start_result || r.stop_result) continue;
        r.query_result=event_query(s->a);
        if(!r.query_result) r.query_result=event_query(s->b);
        if(r.query_result==NOT_READY) continue;
        r.type=TIMING;r.elapsed_ms=0;
        r.elapsed_result=r.query_result ? -1 : event_elapsed(&r.elapsed_ms,s->a,s->b);
        if(r.query_result || r.elapsed_result) timing_disabled=1;
        append(&r);s->pending=0;harvested++;
    }
}
static void snapshot(void) {
    uint64_t pending=0;for(unsigned i=0;i<POOL;i++) pending+=slots[i].pending!=0;
    struct record r={.type=SNAPSHOT,.start_ns=now(),.caller=seen,.function=selected,
        .stream=harvested,.tid=pending,.sample_id=pool_full,.shared=atomic_load(&reentrant_skips),
        .grid={(uint32_t)timing_disabled,(uint32_t)capture_skips,0},.block={(uint32_t)created,(uint32_t)destroyed,0},
        .native_result=deferred_cleanup,.reserved=(uint32_t)retired};
    r.end_ns=r.start_ns;append(&r);
}
static struct slot *before_launch(struct record *r,uintptr_t caller,const void *fn,
        dim3 grid,dim3 block,size_t shared,hipStream_t stream,uint32_t type) {
    r->start_ns=now();r->caller=UINT64_MAX;
    for(unsigned i=0;i<ranges;i++) if(caller>=begin[i]&&caller<end[i]) {r->caller=caller-base;break;}
    r->function=(uintptr_t)fn;r->stream=(uintptr_t)stream;r->tid=(uint64_t)syscall(SYS_gettid);
    r->shared=shared;r->grid[0]=grid.x;r->grid[1]=grid.y;r->grid[2]=grid.z;
    r->block[0]=block.x;r->block[1]=block.y;r->block[2]=block.z;r->type=type;
    seen++;rng^=rng<<13;rng^=rng>>7;rng^=rng<<17;
    if(((rng>>59)&(PROBABILITY_DENOMINATOR-1)) || timing_disabled) return NULL;
    /* Check capture before creation/recording. This is not a graph profiler. */
    if(!is_capturing) is_capturing=dlsym(RTLD_NEXT,"hipStreamIsCapturing");
    int capture=0;
    if(!is_capturing || is_capturing(stream,&capture)) {timing_disabled=1;return NULL;}
    if(capture) {capture_skips++;return NULL;}
    if(selected>=sample_limit) return NULL;
    if(!event_create) prepare_events();
    if(timing_disabled) return NULL;
    int device=-1;
    if(get_device(&device) || device!=0) {timing_disabled=1;return NULL;}
    for(unsigned i=0;i<POOL;i++) if(!slots[i].pending) {
        struct slot*s=&slots[i];s->pending=1;r->sample_id=++selected;
        r->start_result=event_record(s->a,stream);
        if(r->start_result) timing_disabled=1;
        return s;
    }
    pool_full++;return NULL;
}
static void after_launch(struct record *r,struct slot*s,int result,hipStream_t stream) {
    r->native_result=result;r->end_ns=now();
    if(s) {
        r->stop_result=(r->start_result || result) ? -1 : event_record(s->b,stream);
        if(r->stop_result || result) timing_disabled=1;
        s->record=*r;
    }
    append(r);
}
#define CALLER ((uintptr_t)__builtin_extract_return_addr(__builtin_return_address(0)))
hipError_t hipLaunchKernel(const void* fn,dim3 grid,dim3 block,void** args,size_t shared,hipStream_t stream) {
    typedef int(*F)(const void*,dim3,dim3,void**,size_t,hipStream_t);
    int saved=errno;F f=(F)target("hipLaunchKernel");int observing=enter();
    struct record r={0};struct slot*s=observing?before_launch(&r,CALLER,fn,grid,block,shared,stream,LAUNCH):NULL;
    errno=saved;int result=f(fn,grid,block,args,shared,stream);int native_errno=errno;
    if(observing) {after_launch(&r,s,result,stream);leave();}errno=native_errno;return result;
}
hipError_t hipModuleLaunchKernel(hipFunction_t fn,unsigned gx,unsigned gy,unsigned gz,
        unsigned bx,unsigned by,unsigned bz,unsigned shared,hipStream_t stream,void** args,void** extra) {
    typedef int(*F)(hipFunction_t,unsigned,unsigned,unsigned,unsigned,unsigned,unsigned,unsigned,hipStream_t,void**,void**);
    int saved=errno;F f=(F)target("hipModuleLaunchKernel");int observing=enter();
    struct record r={0};dim3 grid={gx,gy,gz},block={bx,by,bz};
    struct slot*s=observing?before_launch(&r,CALLER,fn,grid,block,shared,stream,MODULE_LAUNCH):NULL;
    errno=saved;int result=f(fn,gx,gy,gz,bx,by,bz,shared,stream,args,extra);int native_errno=errno;
    if(observing) {after_launch(&r,s,result,stream);leave();}errno=native_errno;return result;
}
static void after_completion(int result) {
    /* Query/Elapsed return600 while pending and alter HIP thread-local error
     * state. Never call them from the engine's original thread. */
    if(!result && atomic_load(&enabled) && getpid()==owner && wake_pipe[1]>=0) {
        char byte=1;ssize_t ignored=write(wake_pipe[1],&byte,1);(void)ignored;
    }
}
static void *collector(void *unused) {
    (void)unused;
    /* No kernel launches, allocations, synchronization or tensor reads here.
     * All event handles belong to the engine's device0. */
    set_device=dlsym(RTLD_NEXT,"hipSetDevice");
    int device_set=0;
    for(;;) {
        struct pollfd p={.fd=wake_pipe[0],.events=POLLIN};
        int notified=poll(&p,1,200)>0 && (p.revents&POLLIN);
        int close_requested=close_path && !access(close_path,F_OK);
        if(!notified && !close_requested) continue;
        char buffer[1024];while(read(wake_pipe[0],buffer,sizeof(buffer))>0) {}
        pthread_mutex_lock(&lock);nesting=1;
        if(event_query) {
            if(!device_set) {
                if(!set_device || set_device(0)) timing_disabled=1;
                else device_set=1;
            }
            if(device_set) harvest();
            snapshot();
        }
        if(close_requested) {
            timing_disabled=1;
            /* Established idle close exports remaining/orphan dispositions.
             * HIP permits pending event destroy with deferred release. Never
             * reuse an orphan; final normal process exit reclaims the runtime. */
            for(unsigned i=0;i<POOL;i++) if(slots[i].pending) {
                struct record r=slots[i].record;r.type=TIMING;r.elapsed_ms=0;r.elapsed_result=-1;
                r.query_result=(r.start_result || !device_set || !event_query) ? -1 : event_query(slots[i].a);
                /* Conservatively retain every retired pair as deferred: a
                 * completed start does not establish a completed stop. */
                deferred_cleanup++;
                append(&r);slots[i].pending=0;retired++;
            }
            if(event_destroy && device_set) {
                for(unsigned i=0;i<POOL;i++) {
                    if(slots[i].a) {if(event_destroy(slots[i].a)) timing_disabled=2;else destroyed++;slots[i].a=NULL;}
                    if(slots[i].b) {if(event_destroy(slots[i].b)) timing_disabled=2;else destroyed++;slots[i].b=NULL;}
                }
                snapshot();atomic_store(&enabled,0);
                nesting=0;pthread_mutex_unlock(&lock);return NULL;
            }
            snapshot();atomic_store(&enabled,0);
            nesting=0;pthread_mutex_unlock(&lock);return NULL;
        }
        nesting=0;pthread_mutex_unlock(&lock);
    }
}
hipError_t hipDeviceSynchronize(void) {
    typedef int(*F)(void);int saved=errno;F f=(F)target("hipDeviceSynchronize");errno=saved;
    int result=f(),native_errno=errno;after_completion(result);errno=native_errno;return result;
}
hipError_t hipStreamSynchronize(hipStream_t stream) {
    typedef int(*F)(hipStream_t);int saved=errno;F f=(F)target("hipStreamSynchronize");errno=saved;
    int result=f(stream),native_errno=errno;after_completion(result);errno=native_errno;return result;
}
hipError_t hipMemcpy(void*dst,const void*src,size_t bytes_,int kind) {
    typedef int(*F)(void*,const void*,size_t,int);int saved=errno;F f=(F)target("hipMemcpy");errno=saved;
    int result=f(dst,src,bytes_,kind),native_errno=errno;after_completion(result);errno=native_errno;return result;
}
