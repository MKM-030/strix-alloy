/* Bounded source-only native GPU embedding-projection memoization candidate.
 * Root owns compilation, replay, all runtime/provider operations and live use.
 * Define HALOGEN_EMBEDDING_CACHE_CORE_ONLY to omit Linux interposition/detours.
 * Full-shim build (root only): gcc -O2 -std=c11 -Wall -Wextra -Werror -shared
 *   -fPIC -fno-optimize-sibling-calls <source> -ldl -lcrypto -pthread -o <new.so>
 * The default constructor performs no activation and installs no detours.
 * See halogen-mtp-embedding-cache-contract-20261005.md for the exact contract.
 */
#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include "halogen0162_mtp_embedding_cache.h"
#include <limits.h>
#include <string.h>

static int ecache_nonzero(const unsigned char *p,size_t n) {
    unsigned char bits=0;for (size_t i=0;i<n;i++) bits|=p[i];return bits!=0;
}
static int ecache_span(uintptr_t p,size_t n) {return p && n && n<=UINTPTR_MAX-p;}
static int ecache_disjoint(uintptr_t a,size_t na,uintptr_t b,size_t nb) {
    return ecache_span(a,na) && ecache_span(b,nb) && (a+na<=b || b+nb<=a);
}
static int ecache_fail(struct ecache_state *s) {
    atomic_store_explicit(&s->failed,1,memory_order_release);s->stats.failures++;return ECACHE_ERROR;
}
static int ecache_enter(struct ecache_state *s,int allow_failed) {
    if (!s) return 0;
    if (atomic_flag_test_and_set_explicit(&s->busy,memory_order_acquire)) {
        /* Only the flag is written here: stats/entries belong to the owner. */
        atomic_store_explicit(&s->failed,1,memory_order_release);return 0;
    }
    if (!s->initialized || (!allow_failed && atomic_load_explicit(&s->failed,memory_order_acquire))) {
        if (s->initialized && !s->stats.failures) s->stats.failures++;
        atomic_flag_clear_explicit(&s->busy,memory_order_release);return 0;
    }
    return 1;
}
static int ecache_leave(struct ecache_state *s,int result) {
    if (atomic_load_explicit(&s->failed,memory_order_acquire)) {
        if (!s->stats.failures) s->stats.failures++;
        result=ECACHE_ERROR;
    }
    atomic_flag_clear_explicit(&s->busy,memory_order_release);return result;
}
/* A failed drain retains the resources: freeing rows still in flight would
 * turn an operation error into a lifetime violation. Caller must fail stop. */
static int ecache_cleanup(struct ecache_state *s) {
    s->stats.stream_drains++;
    if (s->ops.stream_synchronize(NULL)) return ecache_fail(s);
    for (unsigned i=0;i<s->capacity;i++) s->entries[i].valid=0;
    int result=0;
    for (unsigned i=0;i<s->capacity;i++) {
        struct ecache_entry *e=&s->entries[i];
        if (e->event) {
            void *event=e->event;e->event=NULL;
            /* Invalid callback aliases are destroyed once, then fail closed. */
            for (unsigned j=i+1;j<s->capacity;j++) if (s->entries[j].event==event) s->entries[j].event=NULL;
            if (s->ops.event_destroy(event)) {ecache_fail(s);result=ECACHE_ERROR;}
            else s->stats.events_destroyed++;
        }
        if (e->device) {
            void *device=e->device;e->device=NULL;
            for (unsigned j=i+1;j<s->capacity;j++) if (s->entries[j].device==device) s->entries[j].device=NULL;
            if (s->ops.release(device)) {ecache_fail(s);result=ECACHE_ERROR;}
            else s->stats.frees++;
        }
    }
    s->initialized=0;return result;
}
int ecache_init(struct ecache_state *s,const struct ecache_ops *ops,const unsigned char generation[16],unsigned capacity) {
    if (!s || !ops || !generation || !ecache_nonzero(generation,16) || capacity<1 || capacity>ECACHE_MAX_ENTRIES ||
        ops->abi_version!=ECACHE_ABI_VERSION || !ops->allocate || !ops->release || !ops->copy_async ||
        !ops->stream_synchronize || !ops->event_create || !ops->event_record || !ops->event_query || !ops->event_destroy)
        return ECACHE_ERROR;
    /* Caller guarantees zeroed, never-active state; init is not a reset API. */
    if (s->initialized) return ECACHE_ERROR;
    memset(s,0,sizeof *s);s->ops=*ops;s->capacity=capacity;s->initialized=1;
    memcpy(s->generation,generation,16);atomic_init(&s->failed,0);s->busy=(atomic_flag)ATOMIC_FLAG_INIT;
    (void)atomic_flag_test_and_set_explicit(&s->busy,memory_order_acquire);
    int result=0;
    for (unsigned i=0;i<capacity;i++) {
        struct ecache_entry *e=&s->entries[i];
        if (s->ops.allocate(&e->device,ECACHE_ROW_BYTES)) {result=ecache_fail(s);break;}
        s->stats.allocations++;
        if (!ecache_span((uintptr_t)e->device,ECACHE_ROW_BYTES) || ((uintptr_t)e->device&1u)) {
            result=ecache_fail(s);break;
        }
        for (unsigned j=0;j<i;j++) if (!ecache_disjoint((uintptr_t)e->device,ECACHE_ROW_BYTES,
                (uintptr_t)s->entries[j].device,ECACHE_ROW_BYTES)) {result=ecache_fail(s);break;}
        if (result) break;
        if (s->ops.event_create(&e->event,2u)) {result=ecache_fail(s);break;}
        s->stats.events_created++;
        if (!e->event) {result=ecache_fail(s);break;}
        for (unsigned j=0;j<i;j++) if (e->event==s->entries[j].event) {result=ecache_fail(s);break;}
        if (result) break;
    }
    if (result) (void)ecache_cleanup(s);
    return ecache_leave(s,result);
}
static int ecache_ready(struct ecache_state *s,unsigned slot) {
    s->stats.event_queries++;int ready=s->ops.event_query(s->entries[slot].event);
    if (ready!=0 && ready!=1) return ecache_fail(s);
    return ready==0?1:0;
}
int ecache_apply(struct ecache_state *s,int32_t token,const uint16_t *input,uint16_t *output,
    ecache_launch_fn launch,void *opaque) {
    if (!ecache_enter(s,0)) return ECACHE_ERROR;
    s->stats.calls++;
    uintptr_t in=(uintptr_t)input,out=(uintptr_t)output;
    if (!launch || (in&1u) || (out&1u) || !ecache_disjoint(in,ECACHE_ROW_BYTES,out,ECACHE_ROW_BYTES))
        return ecache_leave(s,ecache_fail(s));
    for (unsigned i=0;i<s->capacity;i++) if (!ecache_disjoint(in,ECACHE_ROW_BYTES,
            (uintptr_t)s->entries[i].device,ECACHE_ROW_BYTES) || !ecache_disjoint(out,ECACHE_ROW_BYTES,
            (uintptr_t)s->entries[i].device,ECACHE_ROW_BYTES)) return ecache_leave(s,ecache_fail(s));
    unsigned slot=s->capacity;int pending_match=0,supported=token>=0 && (uint32_t)token<ECACHE_TOKEN_COUNT;
    if (supported) {
        for (unsigned i=0;i<s->capacity;i++) if (s->entries[i].valid && s->entries[i].token==token) {
            int ready=ecache_ready(s,i);
            if (ready<0) return ecache_leave(s,ECACHE_ERROR);
            if (!ready) {s->stats.pending_fallbacks++;pending_match=1;break;}
            if (atomic_load_explicit(&s->failed,memory_order_acquire)) return ecache_leave(s,ECACHE_ERROR);
            if (s->ops.copy_async(output,s->entries[i].device,ECACHE_ROW_BYTES,3,NULL))
                return ecache_leave(s,ecache_fail(s));
            s->stats.copy_enqueues++;s->stats.hits++;return ecache_leave(s,ECACHE_HIT);
        }
        if (!pending_match) {
            for (unsigned i=0;i<s->capacity;i++) if (!s->entries[i].valid) {slot=i;break;}
            if (slot==s->capacity) {
                for (unsigned offset=0;offset<s->capacity;offset++) {
                    unsigned i=(s->next_victim+offset)%s->capacity;int ready=ecache_ready(s,i);
                    if (ready<0) return ecache_leave(s,ECACHE_ERROR);
                    if (ready) {slot=i;break;}
                }
            }
        }
    }
    if (atomic_load_explicit(&s->failed,memory_order_acquire)) return ecache_leave(s,ECACHE_ERROR);
    s->stats.misses++;s->stats.original_calls++;
    if (launch(opaque,input,output)) return ecache_leave(s,ecache_fail(s));
    if (atomic_load_explicit(&s->failed,memory_order_acquire)) return ecache_leave(s,ECACHE_ERROR);
    if (slot<s->capacity) {
        struct ecache_entry *e=&s->entries[slot];unsigned evicted=e->valid;e->valid=0;
        if (s->ops.copy_async(e->device,output,ECACHE_ROW_BYTES,3,NULL))
            return ecache_leave(s,ecache_fail(s));
        s->stats.copy_enqueues++;
        if (s->ops.event_record(e->event,NULL)) return ecache_leave(s,ecache_fail(s));
        e->token=token;e->valid=1;s->next_victim=(slot+1)%s->capacity;
        s->stats.captures++;if (evicted) s->stats.evictions++;
    }
    return ecache_leave(s,ECACHE_MISS);
}
int ecache_reset(struct ecache_state *s,const unsigned char generation[16]) {
    if (!ecache_enter(s,0)) return ECACHE_ERROR;
    if (!generation || !ecache_nonzero(generation,16) || !memcmp(s->generation,generation,16))
        return ecache_leave(s,ecache_fail(s));
    s->stats.stream_drains++;
    if (s->ops.stream_synchronize(NULL)) return ecache_leave(s,ecache_fail(s));
    for (unsigned i=0;i<s->capacity;i++) s->entries[i].valid=0;
    memcpy(s->generation,generation,16);s->next_victim=0;s->stats.resets++;
    return ecache_leave(s,0);
}
int ecache_close(struct ecache_state *s) {
    if (!ecache_enter(s,1)) return ECACHE_ERROR;
    return ecache_leave(s,ecache_cleanup(s));
}

#ifndef HALOGEN_EMBEDDING_CACHE_CORE_ONLY
#ifndef HALOGEN_EMBEDDING_CACHE_ENABLE_NATIVE_CANDIDATE
#define HALOGEN_EMBEDDING_CACHE_ENABLE_NATIVE_CANDIDATE 0
#endif
#include <dlfcn.h>
#include <elf.h>
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <link.h>
#include <openssl/evp.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>

#if !defined(__x86_64__) || !defined(__linux__)
#error Linux x86-64 only for native detours; core-only replay has no platform detours
#endif
#define ENGINE_BYTES ((off_t)26052768)
#define ENGINE_SHA "ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b"
#define HEAD_RVA ((uintptr_t)0x17db310)
#define HEAD_OFFSET ((off_t)0x17da310)
#define HEAD_BYTES ((size_t)(0x17dc289-0x17db310))
#define HEAD_SHA "132f2da76d86694ffe5f120d61e304e57c685f3db72935c6d5e61bf7b0d5cc20"
#define FC_RVA ((uintptr_t)0x178cf90)
#define FC_OFFSET ((off_t)0x178bf90)
#define FC_BYTES ((size_t)(0x178efa7-0x178cf90))
#define FC_SHA "f8f9d77041011251d11d0b97d7298926aa053d5435310826a00c408e5bff24e9"
#define E_RETURN_RVA ((uintptr_t)0x17db548)
#define H_RETURN_RVA ((uintptr_t)0x17db663)
#define LAUNCH_RETURN_RVA ((uintptr_t)0x17fdba0)
#define E_KERNEL_RVA ((uintptr_t)0x18d6690)
#define H_KERNEL_RVA ((uintptr_t)0x18d66f0)
#define H_INPUT_RVA ((uintptr_t)0x18db210)
#define H_OUTPUT_RVA ((uintptr_t)0x18db228)
#define WIRE_RVA ((uintptr_t)0x18dccc0)
#define WIRE_GUARD_RVA ((uintptr_t)0x18dccc8)
#define MODEL_BYTES ((size_t)0xb10)
#define DESCRIPTOR_BYTES ((size_t)0x78)
#define TABLE_BYTES ((size_t)ECACHE_TOKEN_COUNT*ECACHE_ROW_BYTES)
#define WEIGHT_BYTES ((size_t)6963200)
static const unsigned char head_signature[32]={
    0x55,0x41,0x57,0x41,0x56,0x41,0x55,0x41,0x54,0x53,0x48,0x81,0xec,0x98,0,0,
    0,0xb8,0xff,0xff,0xff,0xff,0x80,0xbf,0,0x09,0,0,0x01,0x0f,0x85,0x31
};
static const unsigned char fc_signature[32]={
    0x55,0x41,0x57,0x41,0x56,0x41,0x55,0x41,0x54,0x53,0x48,0x83,0xec,0x48,0x4c,0x89,
    0xcb,0x45,0x89,0xc5,0x89,0xcd,0x49,0x89,0xd6,0x49,0x89,0xf7,0x49,0x89,0xfc,0x4c
};
static const unsigned char e_call[5]={0xe8,0x48,0x1a,0xfb,0xff};
static const unsigned char h_call[5]={0xe8,0x2d,0x19,0xfb,0xff};
typedef int32_t (*head_fn)(void *,const int32_t *,int32_t,int32_t);
typedef void (*fc_fn)(void *,const uint16_t *,uint16_t *,int32_t,int32_t,int64_t);
typedef struct {unsigned x,y,z;} hip_dim3;
typedef int (*launch_fn)(const void *,hip_dim3,hip_dim3,void **,size_t,void *);
typedef int (*reset_fn)(void);
typedef int (*context_fn)(void *);
typedef int (*device_fn)(int);
struct binding {
    uintptr_t model,table,gamma,input,output,seed;
    unsigned char descriptor[DESCRIPTOR_BYTES];
    unsigned wire_guard;
    pthread_t thread;
};
struct head_context {
    uintptr_t model,tokens;
    int32_t token,position,outer_position,slot;
    unsigned e_calls,h_calls,phase,launches,launch_ok;
    int native_errno;
};
static struct ecache_state cache;
static struct binding bound;
static struct ecache_ops native_ops;
static head_fn original_head;
static fc_fn original_fc;
static launch_fn real_launch;
static reset_fn real_reset;
static context_fn real_ctx_destroy,real_ctx_set,real_ctx_push;
static int (*real_ctx_pop)(void **);
static device_fn real_set_device;
static uintptr_t engine_base;
static unsigned char run_generation[16];
static unsigned capacity=ECACHE_MAX_ENTRIES,bound_ready,in_flight;
static uint64_t head_calls,excluded_calls,eligible_calls,native_h_calls,retirements;
static int directory_fd=-1;
static _Atomic unsigned enabled,retired;
static pthread_mutex_t state_mutex=PTHREAD_MUTEX_INITIALIZER;
static pthread_once_t symbols_once=PTHREAD_ONCE_INIT;
static _Thread_local struct head_context *active;
static _Thread_local unsigned head_depth,internal_free;
static _Noreturn void fatal(const char *reason) {
    dprintf(STDERR_FILENO,"[mtp-embedding-cache] fatal reason=%s errno=%d\n",reason,errno);_exit(79);
}
static void lock_state(void) {if (pthread_mutex_lock(&state_mutex)) fatal("state-lock");}
static void unlock_state(void) {if (pthread_mutex_unlock(&state_mutex)) fatal("state-unlock");}
static uintptr_t pointer_at(const void *object,size_t offset) {
    uintptr_t value;memcpy(&value,(const unsigned char *)object+offset,sizeof value);return value;
}
static int32_t int32_at(const void *object,size_t offset) {
    int32_t value;memcpy(&value,(const unsigned char *)object+offset,sizeof value);return value;
}
static int mapped_span(uintptr_t address,size_t bytes,const char *wanted) {
    if (!ecache_span(address,bytes)) return 0;
    FILE *file=fopen("/proc/self/maps","re");if (!file) return 0;
    char line[4096],permissions[5];unsigned long low,high;int found=0;
    while (fgets(line,sizeof line,file)) {
        if (sscanf(line,"%lx-%lx %4s",&low,&high,permissions)!=3) continue;
        if (address>=low && address+bytes<=high &&
            (wanted?!strcmp(permissions,wanted):permissions[0]=='r')) {found=1;break;}
    }
    int bad=ferror(file);if (fclose(file)) bad=1;return bad?0:found;
}
static int normal_descriptor(const unsigned char *descriptor) {
    uintptr_t weight=pointer_at(descriptor,0x10);
    return !pointer_at(descriptor,0) && !pointer_at(descriptor,0x30) && ecache_span(weight,WEIGHT_BYTES) && !(weight&15u);
}
static int wire_D(void) {
    return *(const unsigned char *)(engine_base+WIRE_RVA)=='D' &&
        *(const unsigned char *)(engine_base+WIRE_GUARD_RVA)!=0;
}
static int known_head_caller(uintptr_t caller) {
    return caller==0x17dcc08 || caller==0x17dcd54 || caller==0x17dcf49 || caller==0x17de236;
}
static int valid_head_entry(void *model,const int32_t *tokens,int32_t count,int32_t position,uintptr_t caller) {
    return count==1 && position>=0 && known_head_caller(caller) && mapped_span((uintptr_t)model,MODEL_BYTES,NULL) &&
        mapped_span((uintptr_t)tokens,sizeof *tokens,NULL) && ((const unsigned char *)model)[0x900]==1 &&
        int32_at(tokens,0)>=0 && (uint32_t)int32_at(tokens,0)<ECACHE_TOKEN_COUNT &&
        int32_at(model,0x220)>=0 && int32_at(model,0xa0)>=0 && wire_D();
}
static int bound_live(void) {
    return bound_ready && mapped_span(bound.model,MODEL_BYTES,NULL) &&
        ((const unsigned char *)bound.model)[0x900]==1 && wire_D() &&
        *(const unsigned char *)(engine_base+WIRE_GUARD_RVA)==bound.wire_guard &&
        pointer_at((void *)bound.model,0x4f0)==bound.table && pointer_at((void *)bound.model,0xae8)==bound.gamma &&
        pointer_at((void *)bound.model,0x6c8)==bound.input && pointer_at((void *)bound.model,0xb00)==bound.output &&
        pointer_at((void *)bound.model,0x6d0)==bound.seed &&
        !memcmp((void *)(bound.model+0x908),bound.descriptor,DESCRIPTOR_BYTES);
}
static int context_live(const struct head_context *s) {
    return !atomic_load(&retired) && bound_live() && s->model==bound.model && pthread_equal(pthread_self(),bound.thread) &&
        mapped_span(s->tokens,sizeof(int32_t),NULL) && int32_at((void *)s->tokens,0)==s->token &&
        int32_at((void *)s->model,0x220)==s->outer_position && int32_at((void *)s->model,0xa0)==s->slot;
}
static void bind_model(const struct head_context *s) {
    bound.model=s->model;bound.table=pointer_at((void *)s->model,0x4f0);bound.gamma=pointer_at((void *)s->model,0xae8);
    bound.input=pointer_at((void *)s->model,0x6c8);bound.output=pointer_at((void *)s->model,0xb00);
    bound.seed=pointer_at((void *)s->model,0x6d0);bound.wire_guard=*(const unsigned char *)(engine_base+WIRE_GUARD_RVA);
    bound.thread=pthread_self();memcpy(bound.descriptor,(void *)(s->model+0x908),DESCRIPTOR_BYTES);
    if (!normal_descriptor(bound.descriptor) || !ecache_span(bound.table,TABLE_BYTES) || (bound.table&1u) ||
        !ecache_span(bound.gamma,ECACHE_ROW_BYTES) || (bound.gamma&1u) ||
        !ecache_disjoint(bound.input,ECACHE_ROW_BYTES,bound.output,ECACHE_ROW_BYTES) ||
        !ecache_disjoint(bound.input,ECACHE_ROW_BYTES,bound.seed,20480u) ||
        !ecache_disjoint(bound.output,ECACHE_ROW_BYTES,bound.seed,20480u)) fatal("generation-source-binding");
    bound_ready=1;
    if (!context_live(s)) fatal("generation-first-binding");
    internal_free++;
    int initialized=ecache_init(&cache,&native_ops,run_generation,capacity);
    internal_free--;
    if (initialized) fatal("cache-initialize");
}
static void resolve_symbols(void) {
    native_ops.abi_version=ECACHE_ABI_VERSION;
    native_ops.allocate=(int (*)(void **,size_t))dlsym(RTLD_NEXT,"hipMalloc");
    native_ops.release=(int (*)(void *))dlsym(RTLD_NEXT,"hipFree");
    native_ops.copy_async=(int (*)(void *,const void *,size_t,int,void *))dlsym(RTLD_NEXT,"hipMemcpyAsync");
    native_ops.stream_synchronize=(int (*)(void *))dlsym(RTLD_NEXT,"hipStreamSynchronize");
    native_ops.event_create=(int (*)(void **,unsigned))dlsym(RTLD_NEXT,"hipEventCreateWithFlags");
    native_ops.event_record=(int (*)(void *,void *))dlsym(RTLD_NEXT,"hipEventRecord");
    native_ops.event_destroy=(int (*)(void *))dlsym(RTLD_NEXT,"hipEventDestroy");
    real_launch=(launch_fn)dlsym(RTLD_NEXT,"hipLaunchKernel");
    real_reset=(reset_fn)dlsym(RTLD_NEXT,"hipDeviceReset");
    real_ctx_destroy=(context_fn)dlsym(RTLD_NEXT,"hipCtxDestroy");
    real_ctx_set=(context_fn)dlsym(RTLD_NEXT,"hipCtxSetCurrent");
    real_ctx_push=(context_fn)dlsym(RTLD_NEXT,"hipCtxPushCurrent");
    real_ctx_pop=(int (*)(void **))dlsym(RTLD_NEXT,"hipCtxPopCurrent");
    real_set_device=(device_fn)dlsym(RTLD_NEXT,"hipSetDevice");
}
static int (*real_event_query)(void *);
static int query_event(void *event) {
    if (!real_event_query) fatal("event-query-symbol");
    int result=real_event_query(event);return result==0?0:result==600?1:-1;
}
static void require_symbols(void) {
    if (pthread_once(&symbols_once,resolve_symbols)) fatal("symbols-once");
}
/* Interposition is observe-only except an impossible enabled generation route.
 * The five argument addresses are host-readable; pointed device values are
 * compared numerically and are never dereferenced on the CPU. */
int hipLaunchKernel(const void *function,hip_dim3 grid,hip_dim3 block,void **args,size_t shared,void *stream) {
    int incoming_errno=errno;uintptr_t address=(uintptr_t)__builtin_return_address(0);
    uintptr_t caller=address>=engine_base?address-engine_base:UINTPTR_MAX;
    require_symbols();if (!real_launch) fatal("launch-symbol");
    struct head_context *s=active;int valid=0;
    if (s && s->phase==1) {
        s->launches++;valid=s->launches==1 && caller==LAUNCH_RETURN_RVA &&
            (uintptr_t)function==engine_base+E_KERNEL_RVA && grid.x==160 && grid.y==1 && grid.z==1 &&
            block.x==256 && block.y==1 && block.z==1 && !shared && !stream &&
            mapped_span((uintptr_t)args,5*sizeof(void *),NULL);
        uintptr_t values[5]={0};
        if (valid) {
            memcpy(values,args,sizeof values);
            for (unsigned i=0;i<5;i++) if (!mapped_span(values[i],8,NULL)) valid=0;
        }
        if (valid) valid=pointer_at((void *)values[0],0)==pointer_at(bound.descriptor,0x10) &&
            pointer_at((void *)values[1],0)==bound.input && pointer_at((void *)values[2],0)==bound.output &&
            pointer_at((void *)values[3],0)==2560 && pointer_at((void *)values[4],0)==2560;
        if (!valid || !context_live(s)) fatal("original-m1-launch-contract");
    }
    errno=incoming_errno;int result=real_launch(function,grid,block,args,shared,stream);int result_errno=errno;
    if (s && s->phase==1) {if (valid && !result) s->launch_ok++;else fatal("original-m1-launch-result");}
    errno=result_errno;return result;
}
static int launch_original(void *opaque,const uint16_t *input,uint16_t *output) {
    struct head_context *s=opaque;s->phase=1;s->launches=0;s->launch_ok=0;
    errno=s->native_errno;
    original_fc((void *)(s->model+0x908),input,output,2560,1,2560);s->native_errno=errno;s->phase=0;
    if (s->launches!=1 || s->launch_ok!=1 || !context_live(s)) fatal("original-m1-completion");
    return 0;
}
__attribute__((noinline)) static void cached_fc(void *descriptor,const uint16_t *input,uint16_t *output,
    int32_t n,int32_t m,int64_t k) {
    int incoming_errno=errno;uintptr_t address=(uintptr_t)__builtin_return_address(0);
    uintptr_t caller=address>=engine_base?address-engine_base:UINTPTR_MAX;
    struct head_context *s=active;
    if (s && caller==E_RETURN_RVA) {
        s->e_calls++;
        if (s->e_calls!=1 || s->h_calls || descriptor!=(void *)(s->model+0x908) || n!=2560 || m!=1 || k!=2560 ||
            (uintptr_t)input!=bound.input || (uintptr_t)output!=bound.output || !context_live(s)) fatal("embedding-seam-contract");
        s->native_errno=incoming_errno;
        errno=incoming_errno;int result=ecache_apply(&cache,s->token,input,output,launch_original,s);
        if (result==ECACHE_ERROR || !context_live(s)) fatal("cache-apply");
        errno=result==ECACHE_MISS?s->native_errno:incoming_errno;return;
    }
    if (s && caller==H_RETURN_RVA) {s->h_calls++;native_h_calls++;}
    errno=incoming_errno;original_fc(descriptor,input,output,n,m,k);
}
__attribute__((noinline)) static int32_t cached_head(void *model,const int32_t *tokens,int32_t count,int32_t position) {
    int incoming_errno=errno;uintptr_t address=(uintptr_t)__builtin_return_address(0);
    uintptr_t caller=address>=engine_base?address-engine_base:UINTPTR_MAX;
    lock_state();head_calls++;in_flight++;
    if (in_flight!=1 || head_depth) fatal("overlapping-or-nested-head");
    unsigned use=atomic_load(&enabled) && !atomic_load(&retired) && valid_head_entry(model,tokens,count,position,caller);
    if (use) eligible_calls++;else excluded_calls++;
    unlock_state();head_depth++;
    struct head_context context={0};
    if (use) {
        context.model=(uintptr_t)model;context.tokens=(uintptr_t)tokens;context.token=int32_at(tokens,0);
        context.position=position;context.outer_position=int32_at(model,0x220);context.slot=int32_at(model,0xa0);
        if (!bound_ready) bind_model(&context);
        else if (!context_live(&context)) fatal("generation-mutated");
        active=&context;
    }
    errno=incoming_errno;int32_t result=original_head(model,tokens,count,position);int result_errno=errno;
    if (use && (context.e_calls>1 || context.h_calls>1 || (result>=0 && (context.e_calls!=1 || context.h_calls!=1)) ||
        !bound_live() || int32_at(model,0xa0)!=context.slot)) fatal("head-completion-contract");
    active=NULL;head_depth--;lock_state();in_flight--;unlock_state();errno=result_errno;return result;
}
/* Conservatively retire on ANY external GPU free/context switch/reset. This
 * also catches an allocation base different from a bound interior pointer.
 * It is not exhaustive HIP driver/context-reset coverage; owner must pin a
 * single immutable device/context generation and never bypass interposition.
 * Cache calls use RTLD_NEXT release directly. The TLS guard is belt-and-braces
 * for runtime-internal calls; active retirement is fail stop, never a late hit. */
static void retire_cache(void) {
    if (!atomic_load(&enabled) || internal_free) return;
    lock_state();
    if (in_flight) fatal("allocation-or-context-retired-in-head");
    if (bound_ready && !atomic_load(&retired)) {
        atomic_store(&retired,1);retirements++;
        internal_free++;
        if (cache.initialized && ecache_close(&cache)) fatal("retirement-close");
        internal_free--;
    }
    unlock_state();
}
int hipFree(void *pointer) {
    int incoming_errno=errno;require_symbols();if (!native_ops.release) fatal("free-symbol");
    retire_cache();errno=incoming_errno;return native_ops.release(pointer);
}
int hipDeviceReset(void) {
    int incoming_errno=errno;require_symbols();if (!real_reset) fatal("reset-symbol");
    retire_cache();errno=incoming_errno;return real_reset();
}
int hipCtxDestroy(void *context) {
    int incoming_errno=errno;require_symbols();if (!real_ctx_destroy) fatal("ctx-destroy-symbol");
    retire_cache();errno=incoming_errno;return real_ctx_destroy(context);
}
int hipCtxSetCurrent(void *context) {
    int incoming_errno=errno;require_symbols();if (!real_ctx_set) fatal("ctx-set-symbol");
    retire_cache();errno=incoming_errno;return real_ctx_set(context);
}
int hipCtxPushCurrent(void *context) {
    int incoming_errno=errno;require_symbols();if (!real_ctx_push) fatal("ctx-push-symbol");
    retire_cache();errno=incoming_errno;return real_ctx_push(context);
}
int hipCtxPopCurrent(void **context) {
    int incoming_errno=errno;require_symbols();if (!real_ctx_pop) fatal("ctx-pop-symbol");
    retire_cache();errno=incoming_errno;return real_ctx_pop(context);
}
int hipSetDevice(int device) {
    int incoming_errno=errno;require_symbols();if (!real_set_device) fatal("set-device-symbol");
    retire_cache();errno=incoming_errno;return real_set_device(device);
}
static int same_stat(const struct stat *a,const struct stat *b) {
    return a->st_dev==b->st_dev && a->st_ino==b->st_ino && a->st_size==b->st_size &&
        a->st_mode==b->st_mode && a->st_uid==b->st_uid && a->st_nlink==b->st_nlink &&
        a->st_mtim.tv_sec==b->st_mtim.tv_sec && a->st_mtim.tv_nsec==b->st_mtim.tv_nsec &&
        a->st_ctim.tv_sec==b->st_ctim.tv_sec && a->st_ctim.tv_nsec==b->st_ctim.tv_nsec;
}
static void verify_hash(int fd,off_t offset,size_t bytes,const char *wanted) {
    EVP_MD_CTX *ctx=EVP_MD_CTX_new();unsigned char block[65536],digest[32];unsigned length=0;
    if (!ctx || EVP_DigestInit_ex(ctx,EVP_sha256(),NULL)!=1) fatal("hash-init");
    while (bytes) {
        size_t amount=bytes<sizeof block?bytes:sizeof block;ssize_t n=pread(fd,block,amount,offset);
        if (n<0 && errno==EINTR) continue;
        if (n<=0 || (size_t)n>amount || EVP_DigestUpdate(ctx,block,(size_t)n)!=1) fatal("hash-read");
        offset+=n;bytes-=(size_t)n;
    }
    if (EVP_DigestFinal_ex(ctx,digest,&length)!=1 || length!=32) fatal("hash-final");
    EVP_MD_CTX_free(ctx);char hex[65];
    for (unsigned i=0;i<32;i++) snprintf(hex+2*i,3,"%02x",(unsigned)digest[i]);
    if (strcmp(hex,wanted)) fatal("hash-mismatch");
}
static int buffer_hash(const void *data,size_t bytes,const char *wanted) {
    EVP_MD_CTX *ctx=EVP_MD_CTX_new();unsigned char digest[32];unsigned length=0;char hex[65];
    int ok=ctx && EVP_DigestInit_ex(ctx,EVP_sha256(),NULL)==1 && EVP_DigestUpdate(ctx,data,bytes)==1 &&
        EVP_DigestFinal_ex(ctx,digest,&length)==1 && length==32;
    EVP_MD_CTX_free(ctx);if (!ok) return 0;
    for (unsigned i=0;i<32;i++) snprintf(hex+2*i,3,"%02x",(unsigned)digest[i]);
    return !strcmp(hex,wanted);
}
struct sites {uintptr_t base,head,fc;unsigned heads,fcs,globals,kernels;};
static int contained(const Elf64_Phdr *p,uintptr_t start,size_t bytes,int file) {
    uint64_t extent=file?p->p_filesz:p->p_memsz;
    return p->p_type==PT_LOAD && p->p_vaddr<=start && bytes<=extent && start-p->p_vaddr<=extent-bytes;
}
static int find_sites(struct dl_phdr_info *info,size_t ignored,void *opaque) {
    (void)ignored;if (info->dlpi_name && *info->dlpi_name) return 0;
    struct sites *sites=opaque;if (WIRE_GUARD_RVA+1>UINTPTR_MAX-info->dlpi_addr) fatal("base-overflow");
    sites->base=info->dlpi_addr;
    for (unsigned i=0;i<info->dlpi_phnum;i++) {
        const Elf64_Phdr *p=&info->dlpi_phdr[i];
        if (p->p_flags==(PF_R|PF_X) && contained(p,HEAD_RVA,HEAD_BYTES,1) &&
            p->p_offset+HEAD_RVA-p->p_vaddr==(uint64_t)HEAD_OFFSET) {sites->head=sites->base+HEAD_RVA;sites->heads++;}
        if (p->p_flags==(PF_R|PF_X) && contained(p,FC_RVA,FC_BYTES,1) &&
            p->p_offset+FC_RVA-p->p_vaddr==(uint64_t)FC_OFFSET) {sites->fc=sites->base+FC_RVA;sites->fcs++;}
        if (p->p_flags==(PF_R|PF_W) && contained(p,H_INPUT_RVA,WIRE_GUARD_RVA+1-H_INPUT_RVA,0)) sites->globals++;
        if ((p->p_flags&PF_R) && contained(p,E_KERNEL_RVA,H_KERNEL_RVA+8-E_KERNEL_RVA,0)) sites->kernels++;
    }
    return 1;
}
static void absolute_jump(unsigned char *at,uintptr_t target) {
    const unsigned char prefix[6]={0xff,0x25,0,0,0,0};memcpy(at,prefix,6);memcpy(at+6,&target,8);
}
struct detour {uintptr_t entry,page,trampoline;size_t page_size;unsigned char jump[5];};
static struct detour prepare_detour(uintptr_t entry,uintptr_t target,const unsigned char signature[32]) {
    long size=sysconf(_SC_PAGESIZE);
    if (size<=0 || ((unsigned long)size&((unsigned long)size-1))) fatal("page-size");
    struct detour detour={.entry=entry,.page=entry&~((uintptr_t)size-1),.page_size=(size_t)size};
    if (entry+32>detour.page+(uintptr_t)size || !mapped_span(detour.page,(size_t)size,"r-xp")) fatal("entry-page");
    unsigned char *thunk=NULL;
    for (unsigned i=0;i<256;i++) {
        uintptr_t distance=(uintptr_t)(i/2+1)*0x200000;
        if ((i&1)?detour.page<distance:distance>UINTPTR_MAX-detour.page) continue;
        uintptr_t candidate=(i&1)?detour.page-distance:detour.page+distance;
        void *area=mmap((void *)candidate,(size_t)size,PROT_READ|PROT_WRITE,
            MAP_PRIVATE|MAP_ANONYMOUS|MAP_FIXED_NOREPLACE,-1,0);
        if (area==MAP_FAILED) {if (errno==EEXIST) continue;fatal("thunk-map");}
        if (area!=(void *)candidate) {if (munmap(area,(size_t)size)) fatal("thunk-unmap");fatal("fixed-noreplace");}
        thunk=area;break;
    }
    if (!thunk) fatal("thunk-exhausted");
    absolute_jump(thunk,target);
    /* Whole non-RIP-relative push rbp; push r15; push r14 instructions only. */
    memcpy(thunk+64,signature,5);absolute_jump(thunk+69,entry+5);detour.trampoline=(uintptr_t)(thunk+64);
    if (mprotect(thunk,(size_t)size,PROT_READ|PROT_EXEC) || !mapped_span((uintptr_t)thunk,(size_t)size,"r-xp")) fatal("thunk-rx");
    int64_t relative=(int64_t)(uintptr_t)thunk-(int64_t)(entry+5);
    if (relative<INT32_MIN || relative>INT32_MAX) fatal("jump-range");
    detour.jump[0]=0xe9;int32_t delta=(int32_t)relative;memcpy(detour.jump+1,&delta,4);return detour;
}
static void patch_detour(const struct detour *detour) {
    if (mprotect((void *)detour->page,detour->page_size,PROT_READ|PROT_WRITE)) fatal("entry-rw");
    memcpy((void *)detour->entry,detour->jump,5);__builtin___clear_cache((char *)detour->entry,(char *)detour->entry+5);
    if (mprotect((void *)detour->page,detour->page_size,PROT_READ|PROT_EXEC) ||
        !mapped_span(detour->page,detour->page_size,"r-xp")) fatal("entry-rx");
}
static int write_all(int fd,const void *data,size_t bytes) {
    const unsigned char *at=data;
    while (bytes) {
        ssize_t n=write(fd,at,bytes);if (n<0 && errno==EINTR) continue;if (n<=0) return 0;
        at+=n;bytes-=(size_t)n;
    }
    return 1;
}
static void publish_file(const char *name,const char *data,size_t bytes) {
    int fd=openat(directory_fd,name,O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC|O_NOFOLLOW,0600);
    if (fd<0 || !write_all(fd,data,bytes) || fsync(fd) || close(fd) || fsync(directory_fd)) fatal("summary-publication");
}
static int serving_process(void) {
    int fd=open("/proc/self/cmdline",O_RDONLY|O_CLOEXEC);char command[4096];ssize_t bytes;
    if (fd<0) fatal("cmdline-open");
    do {bytes=read(fd,command,sizeof command);} while (bytes<0 && errno==EINTR);
    if (bytes<=0 || bytes>=(ssize_t)sizeof command || command[bytes-1] || close(fd)) fatal("cmdline-read");
    const char *argument=memchr(command,0,(size_t)bytes);
    return argument && argument+1<command+bytes && !strcmp(argument+1,"--ck");
}
__attribute__((constructor)) static void install(void) {
    const char *mode=getenv("HALOGEN_MTP_EMBEDDING_CACHE");if (!mode) return;
    if (strcmp(mode,"gpu64-v1")) fatal("cache-mode");
    char executable[4096];ssize_t length=readlink("/proc/self/exe",executable,sizeof executable-1);
    if (length<0 || length>=(ssize_t)sizeof executable-1) fatal("executable-name");
    executable[length]=0;const char *base=strrchr(executable,'/');base=base?base+1:executable;
    if (strcmp(base,"flash_serve") || !serving_process()) return;
    if (!HALOGEN_EMBEDDING_CACHE_ENABLE_NATIVE_CANDIDATE) fatal("native-live-admission-unqualified");
    const char *wire=getenv("HALOGEN_MTP_WIRE"),*wave=getenv("HALOGEN_LQ8_WAVE");
    const char *generation=getenv("HALOGEN_MTP_EMBEDDING_CACHE_GENERATION");
    const char *immutable=getenv("HALOGEN_MTP_EMBEDDING_CACHE_IMMUTABLE");
    const char *directory=getenv("HALOGEN_MTP_EMBEDDING_CACHE_DIR");
    const char *requested_capacity=getenv("HALOGEN_MTP_EMBEDDING_CACHE_CAPACITY");
    static const char prefix[]="/tmp/alloy-mtp-embedding-cache-";
    if (!wire || strcmp(wire,"D") || !wave || strcmp(wave,"1") || !generation || strlen(generation)!=32 ||
        !immutable || strcmp(immutable,"engine-single-generation-v1") || !directory ||
        strncmp(directory,prefix,sizeof prefix-1) || strlen(directory)!=sizeof prefix-1+32 ||
        strcmp(directory+sizeof prefix-1,generation) || getenv("HALOGEN_MTP_FC_QUALITY")) fatal("cache-configuration");
    for (unsigned i=0;i<32;i++) {
        int value=generation[i]>='0' && generation[i]<='9'?generation[i]-'0':
            generation[i]>='a' && generation[i]<='f'?generation[i]-'a'+10:-1;
        if (value<0) fatal("generation-hex");
        run_generation[i/2]|=(unsigned char)(value<<(i%2?0:4));
    }
    if (!ecache_nonzero(run_generation,16)) fatal("zero-generation");
    if (requested_capacity) {
        char *end=NULL;errno=0;unsigned long number=strtoul(requested_capacity,&end,10);
        if (errno || !*requested_capacity || !end || *end || number<1 || number>ECACHE_MAX_ENTRIES) fatal("cache-capacity");
        capacity=(unsigned)number;
    }
    int fd=open("/proc/self/exe",O_RDONLY|O_CLOEXEC);struct stat before,after;Elf64_Ehdr elf;
    if (fd<0 || fstat(fd,&before) || !S_ISREG(before.st_mode) || before.st_size!=ENGINE_BYTES ||
        pread(fd,&elf,sizeof elf,0)!=(ssize_t)sizeof elf || memcmp(elf.e_ident,ELFMAG,SELFMAG) ||
        elf.e_ident[EI_CLASS]!=ELFCLASS64 || elf.e_ident[EI_DATA]!=ELFDATA2LSB ||
        elf.e_type!=ET_DYN || elf.e_machine!=EM_X86_64) fatal("elf-identity");
    verify_hash(fd,0,(size_t)before.st_size,ENGINE_SHA);verify_hash(fd,HEAD_OFFSET,HEAD_BYTES,HEAD_SHA);
    verify_hash(fd,FC_OFFSET,FC_BYTES,FC_SHA);
    if (fstat(fd,&after) || !same_stat(&before,&after) || close(fd)) fatal("executable-consistency");
    struct sites sites={0};
    if (dl_iterate_phdr(find_sites,&sites)!=1 || sites.heads!=1 || sites.fcs!=1 || sites.globals!=1 || sites.kernels!=1 ||
        !mapped_span(sites.head,HEAD_BYTES,"r-xp") || !mapped_span(sites.fc,FC_BYTES,"r-xp") ||
        memcmp((void *)sites.head,head_signature,32) || memcmp((void *)sites.fc,fc_signature,32) ||
        memcmp((void *)(sites.base+E_RETURN_RVA-5),e_call,5) || memcmp((void *)(sites.base+H_RETURN_RVA-5),h_call,5) ||
        !mapped_span(sites.base+H_INPUT_RVA,WIRE_GUARD_RVA+1-H_INPUT_RVA,"rw-p") ||
        !mapped_span(sites.base+E_KERNEL_RVA,H_KERNEL_RVA+8-E_KERNEL_RVA,NULL) ||
        !buffer_hash((void *)sites.head,HEAD_BYTES,HEAD_SHA) || !buffer_hash((void *)sites.fc,FC_BYTES,FC_SHA)) fatal("native-sites");
    engine_base=sites.base;require_symbols();
    real_event_query=(int (*)(void *))dlsym(RTLD_NEXT,"hipEventQuery");native_ops.event_query=query_event;
    if (!native_ops.allocate || !native_ops.release || !native_ops.copy_async || !native_ops.stream_synchronize ||
        !native_ops.event_create || !native_ops.event_record || !native_ops.event_destroy || !real_event_query || !real_launch)
        fatal("cache-runtime-symbols");
    int tmp=open("/tmp",O_RDONLY|O_DIRECTORY|O_CLOEXEC|O_NOFOLLOW);struct stat status;
    if (tmp<0 || fstat(tmp,&status) || !S_ISDIR(status.st_mode)) fatal("tmp-directory");
    const char *name=directory+sizeof "/tmp/"-1;if (mkdirat(tmp,name,0700)) fatal("fresh-directory-required");
    directory_fd=openat(tmp,name,O_RDONLY|O_DIRECTORY|O_CLOEXEC|O_NOFOLLOW);
    if (close(tmp) || directory_fd<0 || fstat(directory_fd,&status) || !S_ISDIR(status.st_mode) ||
        status.st_uid!=geteuid() || (status.st_mode&0777)!=0700) fatal("owned-directory");
    struct detour head=prepare_detour(sites.head,(uintptr_t)cached_head,head_signature);
    struct detour fc=prepare_detour(sites.fc,(uintptr_t)cached_fc,fc_signature);
    original_head=(head_fn)head.trampoline;original_fc=(fc_fn)fc.trampoline;
    /* Install before work, never hot-patch/combine with another tap. */
    patch_detour(&head);patch_detour(&fc);
    char activation[2048];int bytes=snprintf(activation,sizeof activation,
        "{\"schema\":1,\"mode\":\"gpu64-v1\",\"engine_sha256\":\"" ENGINE_SHA "\","
        "\"head_sha256\":\"" HEAD_SHA "\",\"fc_dispatcher_sha256\":\"" FC_SHA "\","
        "\"generation\":\"%s\",\"capacity\":%u,\"row_bytes\":5120,\"device_bytes\":%u,"
        "\"default_stream\":true,\"pending_native_fallback\":true,\"miss_original_once\":true,"
        "\"gather_rms_unchanged\":true,\"hidden_fc_unchanged\":true,\"immutable_owner_contract\":true,"
        "\"integration_qualified\":false,\"arithmetic_qualified\":false,\"npu_qualified\":false,"
        "\"parity_qualified\":false,\"acceptance_qualified\":false,\"performance_qualified\":false,"
        "\"native_reset_interception_qualified\":false}\n",generation,capacity,capacity*ECACHE_ROW_BYTES);
    if (bytes<=0 || (size_t)bytes>=sizeof activation) fatal("activation-size");
    publish_file("activation.json",activation,(size_t)bytes);
    atomic_store(&enabled,1);
}
__attribute__((destructor)) static void finish(void) {
    if (!atomic_load(&enabled)) return;
    lock_state();if (in_flight || head_depth) fatal("exit-head-active");
    internal_free++;
    if (cache.initialized && ecache_close(&cache)) fatal("exit-cache-close");
    internal_free--;
    char result[4096];struct ecache_stats *s=&cache.stats;
    int bytes=snprintf(result,sizeof result,
        "{\"schema\":1,\"mode\":\"gpu64-v1\",\"head_calls\":%" PRIu64 ",\"eligible_calls\":%" PRIu64 ","
        "\"excluded_calls\":%" PRIu64 ",\"native_h_calls\":%" PRIu64 ",\"retirements\":%" PRIu64 ","
        "\"cache_calls\":%" PRIu64 ",\"hits\":%" PRIu64 ",\"misses\":%" PRIu64 ",\"original_m1_calls\":%" PRIu64 ","
        "\"captures\":%" PRIu64 ",\"pending_fallbacks\":%" PRIu64 ",\"evictions\":%" PRIu64 ",\"failures\":%" PRIu64 ","
        "\"copy_enqueues\":%" PRIu64 ",\"event_queries\":%" PRIu64 ",\"allocations\":%" PRIu64 ",\"frees\":%" PRIu64 ","
        "\"events_created\":%" PRIu64 ",\"events_destroyed\":%" PRIu64 ",\"stream_drains\":%" PRIu64 ",\"resets\":%" PRIu64 ","
        "\"integration_qualified\":false,\"arithmetic_qualified\":false,\"npu_qualified\":false,"
        "\"parity_qualified\":false,\"acceptance_qualified\":false,\"performance_qualified\":false,"
        "\"native_reset_interception_qualified\":false}\n",head_calls,eligible_calls,excluded_calls,native_h_calls,retirements,
        s->calls,s->hits,s->misses,s->original_calls,s->captures,s->pending_fallbacks,s->evictions,s->failures,
        s->copy_enqueues,s->event_queries,s->allocations,s->frees,s->events_created,s->events_destroyed,s->stream_drains,s->resets);
    if (bytes<=0 || (size_t)bytes>=sizeof result) fatal("result-size");
    publish_file("result.json",result,(size_t)bytes);
    atomic_store(&enabled,0);unlock_state();if (close(directory_fd)) fatal("directory-close");directory_fd=-1;
}
#endif
