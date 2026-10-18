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
static int ecache_apply_internal(struct ecache_state *s,int32_t token,const uint16_t *input,uint16_t *output,
    ecache_launch_fn launch,void *opaque,int lookup_hits) {
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
            if (!lookup_hits) {slot=i;break;}
            if (atomic_load_explicit(&s->failed,memory_order_acquire)) return ecache_leave(s,ECACHE_ERROR);
            if (s->ops.copy_async(output,s->entries[i].device,ECACHE_ROW_BYTES,3,NULL))
                return ecache_leave(s,ecache_fail(s));
            s->stats.copy_enqueues++;s->stats.hits++;return ecache_leave(s,ECACHE_HIT);
        }
        if (!pending_match && slot==s->capacity) {
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
int ecache_apply(struct ecache_state *s,int32_t token,const uint16_t *input,uint16_t *output,
    ecache_launch_fn launch,void *opaque) {return ecache_apply_internal(s,token,input,output,launch,opaque,1);}
int ecache_capture_original(struct ecache_state *s,int32_t token,const uint16_t *input,uint16_t *output,
    ecache_launch_fn launch,void *opaque) {return ecache_apply_internal(s,token,input,output,launch,opaque,0);}
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

int ecache_lookup_ready(struct ecache_state *s,int32_t token,const uint16_t **row) {
    if (!row) return ECACHE_ERROR;
    *row=NULL;if (!ecache_enter(s,0)) return ECACHE_ERROR;
    if (token>=0 && (uint32_t)token<ECACHE_TOKEN_COUNT) {
        for (unsigned i=0;i<s->capacity;i++) if (s->entries[i].valid && s->entries[i].token==token) {
            int ready=ecache_ready(s,i);
            if (ready<0) return ecache_leave(s,ECACHE_ERROR);
            if (!ready) {s->stats.pending_fallbacks++;break;}
            *row=s->entries[i].device;return ecache_leave(s,ECACHE_HIT);
        }
    }
    return ecache_leave(s,ECACHE_MISS);
}
static int ecache_artifact_valid(const struct ecache_artifact *a) {
    if (!a || a->count<1 || a->count>ECACHE_MAX_ENTRIES || (a->origin!=1 && a->origin!=2) ||
        !ecache_nonzero(a->generation,16) || !ecache_nonzero(a->model_binding,32) || !ecache_nonzero(a->provenance,32)) return 0;
    for (unsigned i=0;i<a->count;i++) {
        if (a->tokens[i]<0 || (uint32_t)a->tokens[i]>=ECACHE_TOKEN_COUNT) return 0;
        for (unsigned j=0;j<i;j++) if (a->tokens[i]==a->tokens[j]) return 0;
        for (unsigned j=0;j<ECACHE_ROW_BYTES/2;j++) if ((a->rows[i][j]&0x7f80u)==0x7f80u) return 0;
    }
    return 1;
}
int ecache_import_rows(struct ecache_state *s,const struct ecache_artifact *a) {
    if (!ecache_enter(s,0)) return ECACHE_ERROR;
    if (!ecache_artifact_valid(a) || a->count>s->capacity || memcmp(a->generation,s->generation,16))
        return ecache_leave(s,ecache_fail(s));
    for (unsigned i=0;i<s->capacity;i++) if (s->entries[i].valid) return ecache_leave(s,ecache_fail(s));
    for (unsigned i=0;i<a->count;i++) {
        if (s->ops.copy_async(s->entries[i].device,a->rows[i],ECACHE_ROW_BYTES,1,NULL) ||
            s->ops.event_record(s->entries[i].event,NULL)) return ecache_leave(s,ecache_fail(s));
        s->stats.copy_enqueues++;
    }
    s->stats.stream_drains++;
    if (s->ops.stream_synchronize(NULL)) return ecache_leave(s,ecache_fail(s));
    for (unsigned i=0;i<a->count;i++) {s->entries[i].token=a->tokens[i];s->entries[i].valid=1;}
    return ecache_leave(s,0);
}
int ecache_export_rows(struct ecache_state *s,struct ecache_artifact *a) {
    if (!ecache_enter(s,0)) return ECACHE_ERROR;
    if (!a) return ecache_leave(s,ecache_fail(s));
    a->count=0;s->stats.stream_drains++;
    if (s->ops.stream_synchronize(NULL)) return ecache_leave(s,ecache_fail(s));
    for (unsigned i=0;i<s->capacity;i++) if (s->entries[i].valid) {
        unsigned at=a->count++;
        a->tokens[at]=s->entries[i].token;
        if (s->ops.copy_async(a->rows[at],s->entries[i].device,ECACHE_ROW_BYTES,2,NULL))
            return ecache_leave(s,ecache_fail(s));
        s->stats.copy_enqueues++;
    }
    s->stats.stream_drains++;
    if (s->ops.stream_synchronize(NULL)) return ecache_leave(s,ecache_fail(s));
    memcpy(a->generation,s->generation,16);
    if (a->count && !ecache_artifact_valid(a)) return ecache_leave(s,ecache_fail(s));
    return ecache_leave(s,0);
}
static uint32_t ecache_u32(const unsigned char *p) {
    return (uint32_t)p[0]|(uint32_t)p[1]<<8|(uint32_t)p[2]<<16|(uint32_t)p[3]<<24;
}
static void ecache_put32(unsigned char *p,uint32_t n) {
    for (unsigned i=0;i<4;i++) p[i]=(unsigned char)(n>>(8*i));
}
int ecache_artifact_encode(const struct ecache_artifact *a,unsigned char *bytes,size_t capacity_bytes,size_t *extent) {
    if (!extent) return ECACHE_ERROR;
    *extent=0;
    if (!ecache_artifact_valid(a) || !bytes) return ECACHE_ERROR;
    size_t n=ECACHE_ARTIFACT_HEADER_BYTES+a->count*ECACHE_ARTIFACT_RECORD_BYTES;
    if (capacity_bytes<n) return ECACHE_ERROR;
    memset(bytes,0,n);memcpy(bytes,"HGNERC01",8);ecache_put32(bytes+8,1);
    ecache_put32(bytes+12,128);ecache_put32(bytes+16,5120);ecache_put32(bytes+20,a->count);ecache_put32(bytes+24,a->origin);
    memcpy(bytes+32,a->generation,16);memcpy(bytes+48,a->model_binding,32);memcpy(bytes+80,a->provenance,32);
    for (unsigned i=0;i<a->count;i++) {
        unsigned char *p=bytes+128+i*ECACHE_ARTIFACT_RECORD_BYTES;ecache_put32(p,(uint32_t)a->tokens[i]);
        for (unsigned j=0;j<2560;j++) {p[8+2*j]=(unsigned char)a->rows[i][j];p[9+2*j]=(unsigned char)(a->rows[i][j]>>8);}
    }
    *extent=n;return 0;
}
int ecache_artifact_decode(const unsigned char *bytes,size_t extent,const unsigned char generation[16],
    const unsigned char model[32],const unsigned char provenance[32],struct ecache_artifact *a) {
    if (!bytes || !generation || !model || !provenance || !a || extent<128 || extent>ECACHE_ARTIFACT_MAX_BYTES ||
        memcmp(bytes,"HGNERC01",8) || ecache_u32(bytes+8)!=1 || ecache_u32(bytes+12)!=128 ||
        ecache_u32(bytes+16)!=5120 || ecache_u32(bytes+28) || ecache_nonzero(bytes+112,16) ||
        memcmp(bytes+32,generation,16) || memcmp(bytes+48,model,32) || memcmp(bytes+80,provenance,32)) return ECACHE_ERROR;
    unsigned count=ecache_u32(bytes+20);
    if (count<1 || count>ECACHE_MAX_ENTRIES || extent!=128+count*ECACHE_ARTIFACT_RECORD_BYTES) return ECACHE_ERROR;
    memset(a,0,sizeof *a);a->count=count;a->origin=ecache_u32(bytes+24);
    memcpy(a->generation,generation,16);memcpy(a->model_binding,model,32);memcpy(a->provenance,provenance,32);
    for (unsigned i=0;i<count;i++) {
        const unsigned char *p=bytes+128+i*ECACHE_ARTIFACT_RECORD_BYTES;
        if (ecache_u32(p+4) || ecache_u32(p)>=ECACHE_TOKEN_COUNT) return ECACHE_ERROR;
        a->tokens[i]=(int32_t)ecache_u32(p);
        for (unsigned j=0;j<2560;j++) a->rows[i][j]=(uint16_t)((unsigned)p[8+2*j]|(unsigned)p[9+2*j]<<8);
    }
    return ecache_artifact_valid(a)?0:ECACHE_ERROR;
}
int ecache_branch_step(struct ecache_branch *branch,unsigned step) {
    if (!branch || branch->failed || step>ECACHE_BRANCH_SEED || step!=branch->stage) {
        if (branch) branch->failed=1;
        return ECACHE_ERROR;
    }
    branch->stage++;return 0;
}

#ifndef HALOGEN_EMBEDDING_CACHE_CORE_ONLY
#ifndef HALOGEN_EMBEDDING_CACHE_ENABLE_NATIVE_CANDIDATE
#define HALOGEN_EMBEDDING_CACHE_ENABLE_NATIVE_CANDIDATE 0
#endif
#ifndef HALOGEN_EMBEDDING_CACHE_ENABLE_READY_CANDIDATE
#define HALOGEN_EMBEDDING_CACHE_ENABLE_READY_CANDIDATE 0
#endif
#ifndef HALOGEN_EMBEDDING_CACHE_ENABLE_CHECKED_COPY_CANDIDATE
#define HALOGEN_EMBEDDING_CACHE_ENABLE_CHECKED_COPY_CANDIDATE 0
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
#include <limits.h>
#include <sys/uio.h>

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
#define GATHER_RETURN_RVA ((uintptr_t)0x17db44e)
#define RMS_RETURN_RVA ((uintptr_t)0x17db51c)
#define SEED_RETURN_RVA ((uintptr_t)0x17dbb96)
#define GATHER_KERNEL_RVA ((uintptr_t)0x18d5b40)
#define RMS_KERNEL_RVA ((uintptr_t)0x18d5160)
#define SEED_KERNEL_RVA ((uintptr_t)0x18d5b58)
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
static const unsigned char gather_call[5]={0xe8,0xc2,0x83,0x0f,0x00};
static const unsigned char rms_call[5]={0xe8,0xf4,0x82,0x0f,0x00};
static const unsigned char seed_call[5]={0xe8,0x7a,0x7c,0x0f,0x00};
typedef int32_t (*head_fn)(void *,const int32_t *,int32_t,int32_t);
typedef void (*fc_fn)(void *,const uint16_t *,uint16_t *,int32_t,int32_t,int64_t);
typedef struct {unsigned x,y,z;} hip_dim3;
typedef int (*launch_fn)(const void *,hip_dim3,hip_dim3,void **,size_t,void *);
typedef int (*reset_fn)(void);
typedef int (*context_fn)(void *);
typedef int (*device_fn)(int);
struct binding {
    uintptr_t model,table,gamma,input,output,seed,device_tokens;
    unsigned char descriptor[DESCRIPTOR_BYTES];
    unsigned wire_guard;
    pthread_t thread;
};
struct head_context {
    uintptr_t model,tokens;
    int32_t token,position,outer_position,slot;
    unsigned e_calls,h_calls,phase,launches,launch_ok;
    const uint16_t *ready_row;
    struct ecache_branch branch;
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
static unsigned char model_binding[32],provenance_binding[32];
static struct ecache_artifact staged_rows;
static unsigned ready_mode,fixed_rows,artifact_exported;
static unsigned checked_copy_mode,fixed_import_synchronized;
static char generation_hex[33],model_hex[65],provenance_hex[65],import_sha[65];
static uint64_t ready_hits,native_fixed_misses,gather_skips,rms_skips,m1_skips,seed_rewrites;
static unsigned capacity=ECACHE_MAX_ENTRIES,bound_ready,in_flight;
static uint64_t head_calls,excluded_calls,eligible_calls,native_h_calls,retirements;
static int directory_fd=-1;
static _Atomic unsigned enabled,retired;
static pthread_mutex_t state_mutex=PTHREAD_MUTEX_INITIALIZER;
static pthread_once_t symbols_once=PTHREAD_ONCE_INIT;
static _Thread_local struct head_context *active;
static _Thread_local unsigned head_depth,internal_free;
static void maybe_harvest(void);
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
#define MAPPED_SPANS_MAX 8u
struct mapped_query {uintptr_t address;size_t bytes;const char *wanted;};
/* Fresh per-call checks retain single-VMA containment; no mapping is cached. */
static int mapped_spans(const struct mapped_query *queries,unsigned count) {
    if (!queries || !count || count>MAPPED_SPANS_MAX) return 0;
    for (unsigned i=0;i<count;i++)
        if (!ecache_span(queries[i].address,queries[i].bytes)) return 0;
    FILE *file=fopen("/proc/self/maps","re");if (!file) return 0;
    char line[4096],permissions[5];unsigned long low,high;unsigned found=0,all=(1u<<count)-1;
    while (fgets(line,sizeof line,file)) {
        if (sscanf(line,"%lx-%lx %4s",&low,&high,permissions)!=3) continue;
        for (unsigned i=0;i<count;i++) {
            const struct mapped_query *query=&queries[i];
            if (!(found&(1u<<i)) && query->address>=low && query->address+query->bytes<=high &&
                (query->wanted?!strcmp(permissions,query->wanted):permissions[0]=='r')) found|=1u<<i;
        }
        if (found==all) break;
    }
    int bad=ferror(file);if (fclose(file)) bad=1;return !bad && found==all;
}
static int mapped_span(uintptr_t address,size_t bytes,const char *wanted) {
    const struct mapped_query query={address,bytes,wanted};return mapped_spans(&query,1);
}
#define CHECKED_COPY_MAX_QUERIES 8u
#define CHECKED_COPY_MAX_BYTES (MODEL_BYTES+128u)
struct checked_copy_query {uintptr_t address;void *destination;size_t bytes;};
/* Runtime data contract only: current readable bytes may cross VMAs. No remote
 * pointer is dereferenced by the CPU. A partial/non-atomic read is never used
 * as a complete snapshot; exclusive immutable host ownership remains required. */
static int checked_copy(const struct checked_copy_query *queries,unsigned count) {
    if (!queries || !count || count>CHECKED_COPY_MAX_QUERIES) return 0;
    struct iovec local[CHECKED_COPY_MAX_QUERIES],remote[CHECKED_COPY_MAX_QUERIES];
    size_t total=0;
    for (unsigned i=0;i<count;i++) {
        if (!ecache_span(queries[i].address,queries[i].bytes) ||
            !ecache_span((uintptr_t)queries[i].destination,queries[i].bytes) ||
            queries[i].bytes>CHECKED_COPY_MAX_BYTES-total) return 0;
        local[i]=(struct iovec){queries[i].destination,queries[i].bytes};
        remote[i]=(struct iovec){(void *)queries[i].address,queries[i].bytes};
        total+=queries[i].bytes;
    }
    if (total>(size_t)SSIZE_MAX) return 0;
    int incoming_errno=errno;
    ssize_t copied=process_vm_readv(getpid(),local,count,remote,count,0);
    errno=incoming_errno;return copied==(ssize_t)total;
}
struct host_snapshot {
    unsigned char model[MODEL_BYTES];
    int32_t token;
    unsigned char wire,wire_guard;
};
static int known_head_caller(uintptr_t caller);
static int read_host_snapshot(uintptr_t model,uintptr_t tokens,struct host_snapshot *snapshot) {
    if (!snapshot) return 0;
    struct checked_copy_query queries[4]={
        {model,snapshot->model,MODEL_BYTES},
        {engine_base+WIRE_RVA,&snapshot->wire,1},
        {engine_base+WIRE_GUARD_RVA,&snapshot->wire_guard,1},
        {tokens,&snapshot->token,sizeof snapshot->token}
    };
    snapshot->token=0;return checked_copy(queries,tokens?4:3);
}
static int snapshot_bound_values_live(const struct host_snapshot *snapshot) {
    const unsigned char *model=snapshot->model;
    return bound_ready && model[0x900]==1 && snapshot->wire=='D' && snapshot->wire_guard!=0 &&
        snapshot->wire_guard==bound.wire_guard &&
        pointer_at(model,0x4f0)==bound.table && pointer_at(model,0xae8)==bound.gamma &&
        pointer_at(model,0x6c8)==bound.input && pointer_at(model,0xb00)==bound.output &&
        pointer_at(model,0x6d0)==bound.seed && pointer_at(model,0x730)==bound.device_tokens &&
        !memcmp(model+0x908,bound.descriptor,DESCRIPTOR_BYTES);
}
static int checked_head_entry(void *model,const int32_t *tokens,int32_t count,int32_t position,
        uintptr_t caller,struct host_snapshot *snapshot) {
    return tokens && count==1 && position>=0 && known_head_caller(caller) &&
        read_host_snapshot((uintptr_t)model,(uintptr_t)tokens,snapshot) &&
        snapshot->model[0x900]==1 && snapshot->token>=0 && (uint32_t)snapshot->token<ECACHE_TOKEN_COUNT &&
        int32_at(snapshot->model,0x220)>=0 && int32_at(snapshot->model,0xa0)>=0 &&
        snapshot->wire=='D' && snapshot->wire_guard!=0;
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
    const struct mapped_query queries[2]={{(uintptr_t)model,MODEL_BYTES,NULL},{(uintptr_t)tokens,sizeof *tokens,NULL}};
    return count==1 && position>=0 && known_head_caller(caller) && mapped_spans(queries,2) &&
        ((const unsigned char *)model)[0x900]==1 &&
        int32_at(tokens,0)>=0 && (uint32_t)int32_at(tokens,0)<ECACHE_TOKEN_COUNT &&
        int32_at(model,0x220)>=0 && int32_at(model,0xa0)>=0 && wire_D();
}
static int bound_values_live(void) {
    return bound_ready && ((const unsigned char *)bound.model)[0x900]==1 && wire_D() &&
        *(const unsigned char *)(engine_base+WIRE_GUARD_RVA)==bound.wire_guard &&
        pointer_at((void *)bound.model,0x4f0)==bound.table && pointer_at((void *)bound.model,0xae8)==bound.gamma &&
        pointer_at((void *)bound.model,0x6c8)==bound.input && pointer_at((void *)bound.model,0xb00)==bound.output &&
        pointer_at((void *)bound.model,0x6d0)==bound.seed &&
        (!ready_mode || pointer_at((void *)bound.model,0x730)==bound.device_tokens) &&
        !memcmp((void *)(bound.model+0x908),bound.descriptor,DESCRIPTOR_BYTES);
}
static int bound_live(void) {
    if (checked_copy_mode) {
        struct host_snapshot snapshot;
        return bound_ready && read_host_snapshot(bound.model,0,&snapshot) && snapshot_bound_values_live(&snapshot);
    }
    return bound_ready && mapped_span(bound.model,MODEL_BYTES,NULL) && bound_values_live();
}
static int context_live(const struct head_context *s) {
    if (checked_copy_mode) {
        struct host_snapshot snapshot;
        return !atomic_load(&retired) && bound_ready && s->tokens && s->model==bound.model &&
            pthread_equal(pthread_self(),bound.thread) && read_host_snapshot(s->model,s->tokens,&snapshot) &&
            snapshot_bound_values_live(&snapshot) && snapshot.token==s->token &&
            int32_at(snapshot.model,0x220)==s->outer_position && int32_at(snapshot.model,0xa0)==s->slot;
    }
    const struct mapped_query queries[2]={{bound.model,MODEL_BYTES,NULL},{s->tokens,sizeof(int32_t),NULL}};
    return !atomic_load(&retired) && bound_ready && mapped_spans(queries,2) && bound_values_live() &&
        s->model==bound.model && pthread_equal(pthread_self(),bound.thread) && int32_at((void *)s->tokens,0)==s->token &&
        int32_at((void *)s->model,0x220)==s->outer_position && int32_at((void *)s->model,0xa0)==s->slot;
}
static int head_completion_live(const struct head_context *s) {
    if (checked_copy_mode) {
        struct host_snapshot snapshot;
        return !atomic_load(&retired) && bound_ready && s->model==bound.model &&
            pthread_equal(pthread_self(),bound.thread) && read_host_snapshot(s->model,0,&snapshot) &&
            snapshot_bound_values_live(&snapshot) && int32_at(snapshot.model,0xa0)==s->slot;
    }
    return bound_live() && int32_at((void *)s->model,0xa0)==s->slot;
}
static void bind_model(const struct head_context *s,const struct host_snapshot *snapshot) {
    const unsigned char *model=checked_copy_mode?snapshot->model:(const unsigned char *)s->model;
    bound.model=s->model;bound.table=pointer_at(model,0x4f0);bound.gamma=pointer_at(model,0xae8);
    bound.input=pointer_at(model,0x6c8);bound.output=pointer_at(model,0xb00);
    bound.seed=pointer_at(model,0x6d0);
    bound.wire_guard=checked_copy_mode?snapshot->wire_guard:*(const unsigned char *)(engine_base+WIRE_GUARD_RVA);
    bound.device_tokens=pointer_at(model,0x730);
    bound.thread=pthread_self();memcpy(bound.descriptor,model+0x908,DESCRIPTOR_BYTES);
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
    if (ready_mode) {
        if (!ecache_span(bound.device_tokens,4)) fatal("device-token-binding");
        for (unsigned i=0;i<capacity;i++) {
            uintptr_t row=(uintptr_t)cache.entries[i].device;
            if (!ecache_disjoint(row,ECACHE_ROW_BYTES,bound.table,TABLE_BYTES) ||
                !ecache_disjoint(row,ECACHE_ROW_BYTES,bound.gamma,ECACHE_ROW_BYTES) ||
                !ecache_disjoint(row,ECACHE_ROW_BYTES,bound.input,ECACHE_ROW_BYTES) ||
                !ecache_disjoint(row,ECACHE_ROW_BYTES,bound.output,ECACHE_ROW_BYTES) ||
                !ecache_disjoint(row,ECACHE_ROW_BYTES,bound.seed,20480u) ||
                !ecache_disjoint(row,ECACHE_ROW_BYTES,bound.device_tokens,4) ||
                !ecache_disjoint(row,ECACHE_ROW_BYTES,pointer_at(bound.descriptor,0x10),WEIGHT_BYTES))
                fatal("ready-row-source-overlap");
        }
        if (fixed_rows) {
            if (ecache_import_rows(&cache,&staged_rows)) fatal("ready-row-import");
            /* Import drained the default stream before publishing valid rows.
             * fixed-v1 has no capture/eviction/write route after this point. */
            if (checked_copy_mode) fixed_import_synchronized=1;
        }
    }
}
static int lookup_fixed_ready(int32_t token,const uint16_t **row) {
    if (!row) return ECACHE_ERROR;
    *row=NULL;
    if (!checked_copy_mode || !ready_mode || !fixed_rows || !fixed_import_synchronized ||
        atomic_load(&retired) || !ecache_enter(&cache,0)) return ECACHE_ERROR;
    if (token>=0 && (uint32_t)token<ECACHE_TOKEN_COUNT) {
        for (unsigned i=0;i<cache.capacity;i++) if (cache.entries[i].valid && cache.entries[i].token==token) {
            *row=cache.entries[i].device;return ecache_leave(&cache,ECACHE_HIT);
        }
    }
    return ecache_leave(&cache,ECACHE_MISS);
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
static int checked_launch_arguments(void **args,uintptr_t *values,unsigned count,unsigned scalars32) {
    if (!values || !count || count>CHECKED_COPY_MAX_QUERIES || (scalars32&~((1u<<count)-1u))) return 0;
    uintptr_t sources[CHECKED_COPY_MAX_QUERIES];
    struct checked_copy_query vector={(uintptr_t)args,sources,count*sizeof *sources};
    if (!checked_copy(&vector,1)) return 0;
    struct checked_copy_query cells[CHECKED_COPY_MAX_QUERIES];
    memset(values,0,count*sizeof *values);
    for (unsigned i=0;i<count;i++)
        cells[i]=(struct checked_copy_query){sources[i],&values[i],(scalars32&(1u<<i))?4:8};
    return checked_copy(cells,count);
}
static int launch_arguments(void **args,uintptr_t *values,unsigned count,unsigned scalars32) {
    if (checked_copy_mode) return checked_launch_arguments(args,values,count,scalars32);
    if (!count || count>MAPPED_SPANS_MAX) return 0;
    if (!mapped_span((uintptr_t)args,count*sizeof(void *),NULL)) return 0;
    memcpy(values,args,count*sizeof(void *));
    struct mapped_query queries[MAPPED_SPANS_MAX];
    for (unsigned i=0;i<count;i++)
        queries[i]=(struct mapped_query){values[i],(scalars32&(1u<<i))?4:8,NULL};
    return mapped_spans(queries,count);
}
static uintptr_t launch_pointer_value(const uintptr_t *values,unsigned index) {
    return checked_copy_mode?values[index]:pointer_at((void *)values[index],0);
}
static int32_t launch_int32_value(const uintptr_t *values,unsigned index) {
    if (!checked_copy_mode) return int32_at((void *)values[index],0);
    int32_t value;memcpy(&value,&values[index],sizeof value);return value;
}
static int row_launch_shape(hip_dim3 grid,hip_dim3 block,size_t shared,void *stream) {
    return grid.x==1 && grid.y==1 && grid.z==1 && block.x==256 && block.y==1 && block.z==1 && !shared && !stream;
}
/* Only the armed ready branch skips exact gather/RMS/M1 launches. Device values
 * are compared numerically; the CPU never dereferences device allocations. */
int hipLaunchKernel(const void *function,hip_dim3 grid,hip_dim3 block,void **args,size_t shared,void *stream) {
    int incoming_errno=errno;uintptr_t address=(uintptr_t)__builtin_return_address(0);
    uintptr_t caller=address>=engine_base?address-engine_base:UINTPTR_MAX;
    require_symbols();if (!real_launch) fatal("launch-symbol");
    struct head_context *s=active;int valid=0;
    if (s && s->ready_row && (caller==GATHER_RETURN_RVA || caller==RMS_RETURN_RVA || caller==SEED_RETURN_RVA)) {
        uintptr_t values[5]={0};unsigned step=caller==GATHER_RETURN_RVA?ECACHE_BRANCH_GATHER:
            caller==RMS_RETURN_RVA?ECACHE_BRANCH_RMS:ECACHE_BRANCH_SEED;
        unsigned count=step==ECACHE_BRANCH_RMS?5:3;
        uintptr_t identity=step==ECACHE_BRANCH_GATHER?GATHER_KERNEL_RVA:
            step==ECACHE_BRANCH_RMS?RMS_KERNEL_RVA:SEED_KERNEL_RVA;
        valid=!s->phase && context_live(s) && (uintptr_t)function==engine_base+identity &&
            row_launch_shape(grid,block,shared,stream) && launch_arguments(args,values,count,step==ECACHE_BRANCH_RMS?24u:0);
        if (valid && step==ECACHE_BRANCH_GATHER) valid=launch_pointer_value(values,0)==bound.table &&
            launch_pointer_value(values,1)==bound.device_tokens && launch_pointer_value(values,2)==bound.input;
        if (valid && step==ECACHE_BRANCH_RMS) valid=launch_pointer_value(values,0)==bound.input &&
            launch_pointer_value(values,1)==bound.gamma && launch_pointer_value(values,2)==bound.input &&
            launch_int32_value(values,3)==2560 && launch_int32_value(values,4)==1;
        if (valid && step==ECACHE_BRANCH_SEED) {
            uintptr_t hidden=0,row=(uintptr_t)s->ready_row;
            if (checked_copy_mode) {
                const struct checked_copy_query query={engine_base+H_OUTPUT_RVA,&hidden,sizeof hidden};
                valid=checked_copy(&query,1);
            } else hidden=pointer_at((void *)(engine_base+H_OUTPUT_RVA),0);
            valid=valid && s->e_calls==1 && s->h_calls==1 && launch_pointer_value(values,0)==bound.output &&
                launch_pointer_value(values,1)==hidden && launch_pointer_value(values,2)==bound.seed &&
                ecache_disjoint(row,ECACHE_ROW_BYTES,hidden,ECACHE_ROW_BYTES) &&
                ecache_disjoint(row,ECACHE_ROW_BYTES,bound.seed,20480u);
        }
        if (!valid || ecache_branch_step(&s->branch,step)) fatal("ready-branch-launch-contract");
        if (step!=ECACHE_BRANCH_SEED) {
            if (step==ECACHE_BRANCH_GATHER) gather_skips++;else rms_skips++;
            errno=incoming_errno;return 0;
        }
        /* Keep model scratch/output and all native hidden/state pointers. The
         * launch API consumes this temporary host argument vector synchronously. */
        uintptr_t owned[3]={(uintptr_t)s->ready_row,values[1],values[2]};
        const uint16_t *ready=s->ready_row;
        void *rewritten[3];
        if (checked_copy_mode) {for (unsigned i=0;i<3;i++) rewritten[i]=&owned[i];}
        else {rewritten[0]=&ready;rewritten[1]=args[1];rewritten[2]=args[2];}
        errno=incoming_errno;int result=real_launch(function,grid,block,rewritten,shared,stream);int result_errno=errno;
        if (result) fatal("ready-seed-launch-result");
        seed_rewrites++;errno=result_errno;return result;
    }
    if (s && s->phase==1) {
        s->launches++;valid=s->launches==1 && caller==LAUNCH_RETURN_RVA &&
            (uintptr_t)function==engine_base+E_KERNEL_RVA && grid.x==160 && grid.y==1 && grid.z==1 &&
            block.x==256 && block.y==1 && block.z==1 && !shared && !stream &&
            args;
        uintptr_t values[5]={0};
        if (valid) valid=launch_arguments(args,values,5,0);
        if (valid) valid=launch_pointer_value(values,0)==pointer_at(bound.descriptor,0x10) &&
            launch_pointer_value(values,1)==bound.input && launch_pointer_value(values,2)==bound.output &&
            launch_pointer_value(values,3)==2560 && launch_pointer_value(values,4)==2560;
        if (!valid || !context_live(s)) fatal("original-m1-launch-contract");
        if (s->ready_row) {
            if (ecache_branch_step(&s->branch,ECACHE_BRANCH_M1)) fatal("ready-m1-sequence");
            s->launch_ok++;m1_skips++;errno=incoming_errno;return 0;
        }
        if (checked_copy_mode) {
            /* A native fixed miss submits exactly the values just checked,
             * without rereading its original host argument cells. */
            void *owned[5];for (unsigned i=0;i<5;i++) owned[i]=&values[i];
            errno=incoming_errno;int result=real_launch(function,grid,block,owned,shared,stream);
            int result_errno=errno;
            if (!result) s->launch_ok++;else fatal("original-m1-launch-result");
            errno=result_errno;return result;
        }
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
        if (s->ready_row || (ready_mode && fixed_rows)) {
            if (launch_original(s,input,output) || !context_live(s)) fatal("ready-dispatcher-completion");
            errno=s->native_errno;return;
        }
        errno=incoming_errno;int result=ready_mode?ecache_capture_original(&cache,s->token,input,output,launch_original,s):
            ecache_apply(&cache,s->token,input,output,launch_original,s);
        if (result==ECACHE_ERROR || !context_live(s)) fatal("cache-apply");
        errno=result==ECACHE_MISS?s->native_errno:incoming_errno;return;
    }
    if (s && caller==H_RETURN_RVA) {
        s->h_calls++;native_h_calls++;
        if (s->ready_row && (s->branch.stage!=3 || s->h_calls!=1)) fatal("ready-hidden-sequence");
    }
    errno=incoming_errno;original_fc(descriptor,input,output,n,m,k);
}
__attribute__((noinline)) static int32_t cached_head(void *model,const int32_t *tokens,int32_t count,int32_t position) {
    int incoming_errno=errno;uintptr_t address=(uintptr_t)__builtin_return_address(0);
    uintptr_t caller=address>=engine_base?address-engine_base:UINTPTR_MAX;
    lock_state();
    if (in_flight || head_depth) fatal("overlapping-or-nested-head");
    maybe_harvest();head_calls++;in_flight++;
    struct host_snapshot entry;
    unsigned use=atomic_load(&enabled) && !atomic_load(&retired) && !(ready_mode && !fixed_rows && artifact_exported) &&
        (checked_copy_mode?checked_head_entry(model,tokens,count,position,caller,&entry):
            valid_head_entry(model,tokens,count,position,caller));
    if (use) eligible_calls++;else excluded_calls++;
    unlock_state();head_depth++;
    struct head_context context={0};
    if (use) {
        const unsigned char *source_model=checked_copy_mode?entry.model:(const unsigned char *)model;
        context.model=(uintptr_t)model;context.tokens=(uintptr_t)tokens;
        context.token=checked_copy_mode?entry.token:int32_at(tokens,0);
        context.position=position;context.outer_position=int32_at(source_model,0x220);context.slot=int32_at(source_model,0xa0);
        if (!bound_ready) bind_model(&context,checked_copy_mode?&entry:NULL);
        else if (!context_live(&context)) fatal("generation-mutated");
        if (ready_mode) {
            int ready=checked_copy_mode?lookup_fixed_ready(context.token,&context.ready_row):
                ecache_lookup_ready(&cache,context.token,&context.ready_row);
            if (ready==ECACHE_ERROR) fatal("ready-lookup");
            if (ready==ECACHE_HIT) {ready_hits++;cache.stats.calls++;cache.stats.hits++;}
            else if (fixed_rows) {native_fixed_misses++;cache.stats.calls++;cache.stats.misses++;cache.stats.original_calls++;}
        }
        active=&context;
    }
    errno=incoming_errno;int32_t result=original_head(model,tokens,count,position);int result_errno=errno;
    if (use && (context.e_calls>1 || context.h_calls>1 || (result>=0 && (context.e_calls!=1 || context.h_calls!=1)) ||
        !head_completion_live(&context))) fatal("head-completion-contract");
    if (context.ready_row && (context.branch.stage!=4 || context.branch.failed || context.e_calls!=1 || context.h_calls!=1))
        fatal("ready-head-completion");
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
        atomic_store(&retired,1);fixed_import_synchronized=0;retirements++;
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
static void digest_hex(const void *data,size_t bytes,char hex[65]) {
    EVP_MD_CTX *ctx=EVP_MD_CTX_new();unsigned char digest[32];unsigned length=0;
    if (!ctx || EVP_DigestInit_ex(ctx,EVP_sha256(),NULL)!=1 || EVP_DigestUpdate(ctx,data,bytes)!=1 ||
        EVP_DigestFinal_ex(ctx,digest,&length)!=1 || length!=32) fatal("artifact-digest");
    EVP_MD_CTX_free(ctx);
    for (unsigned i=0;i<32;i++) snprintf(hex+2*i,3,"%02x",(unsigned)digest[i]);
}
static void parse_hex(const char *hex,unsigned char *bytes,size_t count) {
    if (!hex || strlen(hex)!=count*2) fatal("ready-binding-length");
    for (size_t i=0;i<count*2;i++) {
        int v=hex[i]>='0' && hex[i]<='9'?hex[i]-'0':hex[i]>='a' && hex[i]<='f'?hex[i]-'a'+10:-1;
        if (v<0) fatal("ready-binding-hex");
        bytes[i/2]=(unsigned char)((i%2?bytes[i/2]:0)|(v<<(i%2?0:4)));
    }
    if (!ecache_nonzero(bytes,count)) fatal("ready-zero-binding");
}
/* Pin every pathname component without following links. Identity and digest
 * validation cover both captured bytes and the same open file description. */
static int open_readonly_artifact(const char *path) {
    if (!path || path[0]!='/' || strlen(path)>=4096) fatal("ready-artifact-path");
    char copy[4096];strcpy(copy,path+1);int parent=open("/",O_RDONLY|O_DIRECTORY|O_CLOEXEC|O_NOFOLLOW);
    if (parent<0) fatal("ready-artifact-root");
    char *at=copy;
    for (;;) {
        char *slash=strchr(at,'/');if (slash) *slash=0;
        if (!*at || !strcmp(at,".") || !strcmp(at,"..")) fatal("ready-artifact-component");
        int next=openat(parent,at,O_RDONLY|O_CLOEXEC|O_NOFOLLOW|(slash?O_DIRECTORY:0));
        if (next<0 || close(parent)) fatal("ready-artifact-open");
        if (!slash) return next;
        parent=next;at=slash+1;
    }
}
static void load_artifact(const char *path,const char *sha) {
    unsigned char expected[32];parse_hex(sha,expected,32);strcpy(import_sha,sha);
    int fd=open_readonly_artifact(path);struct stat before,after;
    if (fstat(fd,&before) || !S_ISREG(before.st_mode) || before.st_uid!=geteuid() || before.st_nlink!=1 ||
        (before.st_mode&0222) || before.st_size<128 || before.st_size>(off_t)ECACHE_ARTIFACT_MAX_BYTES)
        fatal("ready-artifact-identity");
    unsigned char bytes[ECACHE_ARTIFACT_MAX_BYTES];size_t extent=(size_t)before.st_size,at=0;
    while (at<extent) {
        if (at>=sizeof bytes) fatal("ready-artifact-read-bound");
        size_t amount=sizeof bytes-at;if (amount>extent-at) amount=extent-at;
        ssize_t n=pread(fd,bytes+at,amount,(off_t)at);
        if (n<0 && errno==EINTR) continue;
        if (n<=0 || (size_t)n>amount) fatal("ready-artifact-read");
        at+=(size_t)n;
    }
    verify_hash(fd,0,extent,sha);
    if (!buffer_hash(bytes,extent,sha) || fstat(fd,&after) || !same_stat(&before,&after) || close(fd) ||
        ecache_artifact_decode(bytes,extent,run_generation,model_binding,provenance_binding,&staged_rows) ||
        staged_rows.count>capacity) fatal("ready-artifact-consistency");
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
        uintptr_t first_kernel=ready_mode?RMS_KERNEL_RVA:E_KERNEL_RVA;
        if ((p->p_flags&PF_R) && contained(p,first_kernel,H_KERNEL_RVA+8-first_kernel,0)) sites->kernels++;
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
static void export_ready_rows(void) {
    if (in_flight || head_depth || !ready_mode || fixed_rows || artifact_exported || !bound_ready || !cache.initialized ||
        atomic_load(&retired) || !bound_live() || !pthread_equal(pthread_self(),bound.thread)) fatal("ready-export-state");
    memset(&staged_rows,0,sizeof staged_rows);staged_rows.origin=1;
    memcpy(staged_rows.model_binding,model_binding,32);memcpy(staged_rows.provenance,provenance_binding,32);
    internal_free++;int result=ecache_export_rows(&cache,&staged_rows);internal_free--;
    unsigned char bytes[ECACHE_ARTIFACT_MAX_BYTES];size_t extent=0;
    if (result || !staged_rows.count || ecache_artifact_encode(&staged_rows,bytes,sizeof bytes,&extent)) fatal("ready-export-rows");
    char sha[65];digest_hex(bytes,extent,sha);
    publish_file("ready-rows.bin",(const char *)bytes,extent);
    char metadata[2048];int n=snprintf(metadata,sizeof metadata,
        "{\"schema\":1,\"artifact\":\"ready-rows.bin\",\"abi\":\"HGNERC01\",\"sha256\":\"%s\",\"bytes\":%zu,"
        "\"generation\":\"%s\",\"model_binding\":\"%s\",\"provenance\":\"%s\",\"origin\":1,\"count\":%u,\"row_bytes\":5120}\n",
        sha,extent,generation_hex,model_hex,provenance_hex,staged_rows.count);
    if (n<=0 || (size_t)n>=sizeof metadata) fatal("ready-export-metadata-size");
    publish_file("ready-rows.json",metadata,(size_t)n);
    n=snprintf(metadata,sizeof metadata,
        "{\"schema\":1,\"mode\":\"ready64-v1\",\"policy\":\"capture-v1\",\"generation\":\"%s\","
        "\"ready_hits\":%" PRIu64 ",\"gather_skips\":%" PRIu64 ",\"rms_skips\":%" PRIu64 ","
        "\"m1_skips\":%" PRIu64 ",\"seed_rewrites\":%" PRIu64 ",\"captures\":%" PRIu64 ","
        "\"misses\":%" PRIu64 ",\"evictions\":%" PRIu64 ",\"rows\":%u,\"artifact_sha256\":\"%s\","
        "\"arithmetic_qualified\":false,\"acceptance_qualified\":false,\"performance_qualified\":false}\n",
        generation_hex,ready_hits,gather_skips,rms_skips,m1_skips,seed_rewrites,cache.stats.captures,
        cache.stats.misses,cache.stats.evictions,staged_rows.count,sha);
    if (n<=0 || (size_t)n>=sizeof metadata) fatal("ready-export-result-size");
    publish_file("capture-result.json",metadata,(size_t)n);artifact_exported=1;
}
static void maybe_harvest(void) {
    if (!atomic_load(&enabled) || !ready_mode || fixed_rows) return;
    struct stat before,after;
    if (fstatat(directory_fd,"ready-export",&before,AT_SYMLINK_NOFOLLOW)) {
        if (errno==ENOENT) return;
        fatal("ready-export-trigger-stat");
    }
    if (artifact_exported || in_flight || head_depth || !S_ISREG(before.st_mode) || before.st_uid!=geteuid() ||
        before.st_nlink!=1 || (before.st_mode&0777)!=0600 || before.st_size!=33) fatal("ready-export-trigger-identity");
    int fd=openat(directory_fd,"ready-export",O_RDONLY|O_CLOEXEC|O_NOFOLLOW);char content[34]={0};
    if (fd<0 || fstat(fd,&after) || !same_stat(&before,&after) || pread(fd,content,33,0)!=33 ||
        memcmp(content,generation_hex,32) || content[32]!='\n' || fstat(fd,&after) || !same_stat(&before,&after) || close(fd))
        fatal("ready-export-trigger-content");
    export_ready_rows();
    if (unlinkat(directory_fd,"ready-export",0) || fsync(directory_fd)) fatal("ready-export-trigger-consume");
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
    ready_mode=!strcmp(mode,"ready64-v1");
    if (!ready_mode && strcmp(mode,"gpu64-v1")) fatal("cache-mode");
    char executable[4096];ssize_t length=readlink("/proc/self/exe",executable,sizeof executable-1);
    if (length<0 || length>=(ssize_t)sizeof executable-1) fatal("executable-name");
    executable[length]=0;const char *base=strrchr(executable,'/');base=base?base+1:executable;
    if (strcmp(base,"flash_serve") || !serving_process()) return;
    if (ready_mode?!HALOGEN_EMBEDDING_CACHE_ENABLE_READY_CANDIDATE:!HALOGEN_EMBEDDING_CACHE_ENABLE_NATIVE_CANDIDATE)
        fatal("native-live-admission-unqualified");
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
    strcpy(generation_hex,generation);
    if (requested_capacity) {
        char *end=NULL;errno=0;unsigned long number=strtoul(requested_capacity,&end,10);
        if (errno || !*requested_capacity || !end || *end || number<1 || number>ECACHE_MAX_ENTRIES) fatal("cache-capacity");
        capacity=(unsigned)number;
    }
    if (ready_mode) {
        const char *policy=getenv("HALOGEN_MTP_EMBEDDING_CACHE_READY_POLICY");
        const char *model=getenv("HALOGEN_MTP_EMBEDDING_CACHE_MODEL_BINDING");
        const char *provenance=getenv("HALOGEN_MTP_EMBEDDING_CACHE_PROVENANCE");
        const char *rows=getenv("HALOGEN_MTP_EMBEDDING_CACHE_READY_ROWS");
        const char *sha=getenv("HALOGEN_MTP_EMBEDDING_CACHE_READY_ROWS_SHA256");
        if (!policy || (strcmp(policy,"fixed-v1") && strcmp(policy,"capture-v1"))) fatal("ready-policy");
        fixed_rows=!strcmp(policy,"fixed-v1");parse_hex(model,model_binding,32);parse_hex(provenance,provenance_binding,32);
        strcpy(model_hex,model);strcpy(provenance_hex,provenance);
        if (fixed_rows) load_artifact(rows,sha);
        else if (rows || sha) fatal("capture-import-forbidden");
    }
    const char *host_validation=getenv("HALOGEN_MTP_EMBEDDING_CACHE_HOST_VALIDATION");
    if (host_validation && strcmp(host_validation,ECACHE_HOST_VALIDATION_MAPS) &&
        strcmp(host_validation,ECACHE_HOST_VALIDATION_CHECKED_COPY)) fatal("host-validation-policy");
    checked_copy_mode=host_validation && !strcmp(host_validation,ECACHE_HOST_VALIDATION_CHECKED_COPY);
    if (checked_copy_mode && (!ready_mode || !fixed_rows)) fatal("checked-copy-fixed-only");
    if (checked_copy_mode && !HALOGEN_EMBEDDING_CACHE_ENABLE_CHECKED_COPY_CANDIDATE)
        fatal("checked-copy-live-admission-unqualified");
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
        !mapped_span(sites.base+(ready_mode?RMS_KERNEL_RVA:E_KERNEL_RVA),
            H_KERNEL_RVA+8-(ready_mode?RMS_KERNEL_RVA:E_KERNEL_RVA),NULL) ||
        (ready_mode && (memcmp((void *)(sites.base+GATHER_RETURN_RVA-5),gather_call,5) ||
            memcmp((void *)(sites.base+RMS_RETURN_RVA-5),rms_call,5) ||
            memcmp((void *)(sites.base+SEED_RETURN_RVA-5),seed_call,5))) ||
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
    if (ready_mode) bytes=snprintf(activation,sizeof activation,
        "{\"schema\":1,\"mode\":\"ready64-v1\",\"policy\":\"%s\",\"host_validation\":\"%s\","
        "\"per_hit_event_query\":%s,\"engine_sha256\":\"" ENGINE_SHA "\","
        "\"head_sha256\":\"" HEAD_SHA "\",\"fc_dispatcher_sha256\":\"" FC_SHA "\",\"generation\":\"%s\","
        "\"model_binding\":\"%s\",\"provenance\":\"%s\",\"capacity\":%u,\"row_bytes\":5120,\"device_bytes\":%u,"
        "\"origin\":%u,\"imported_rows\":%u,\"import_sha256\":\"%s\",\"default_stream\":true,"
        "\"ready_direct_seed\":true,\"fc_dispatcher_retained\":true,\"hidden_fc_unchanged\":true,"
        "\"fixed_misses_native\":%s,\"immutable_owner_contract\":true,\"integration_qualified\":false,"
        "\"arithmetic_qualified\":false,\"npu_qualified\":false,\"parity_qualified\":false,"
        "\"acceptance_qualified\":false,\"performance_qualified\":false,\"native_reset_interception_qualified\":false}\n",
        fixed_rows?"fixed-v1":"capture-v1",checked_copy_mode?ECACHE_HOST_VALIDATION_CHECKED_COPY:ECACHE_HOST_VALIDATION_MAPS,
        checked_copy_mode?"false":"true",generation,model_hex,provenance_hex,capacity,capacity*ECACHE_ROW_BYTES,
        fixed_rows?staged_rows.origin:1,fixed_rows?staged_rows.count:0,import_sha,fixed_rows?"true":"false");
    if (bytes<=0 || (size_t)bytes>=sizeof activation) fatal("activation-size");
    publish_file("activation.json",activation,(size_t)bytes);
    atomic_store(&enabled,1);
}
__attribute__((destructor)) static void finish(void) {
    if (!atomic_load(&enabled)) return;
    lock_state();if (in_flight || head_depth) fatal("exit-head-active");
    if (ready_mode && !fixed_rows && !artifact_exported && cache.initialized && !atomic_load(&retired)) export_ready_rows();
    internal_free++;
    if (cache.initialized && ecache_close(&cache)) fatal("exit-cache-close");
    internal_free--;
    char result[4096];struct ecache_stats *s=&cache.stats;
    int bytes=snprintf(result,sizeof result,
        "{\"schema\":1,\"mode\":\"%s\",\"head_calls\":%" PRIu64 ",\"eligible_calls\":%" PRIu64 ","
        "\"excluded_calls\":%" PRIu64 ",\"native_h_calls\":%" PRIu64 ",\"retirements\":%" PRIu64 ","
        "\"cache_calls\":%" PRIu64 ",\"hits\":%" PRIu64 ",\"misses\":%" PRIu64 ",\"original_m1_calls\":%" PRIu64 ","
        "\"captures\":%" PRIu64 ",\"pending_fallbacks\":%" PRIu64 ",\"evictions\":%" PRIu64 ",\"failures\":%" PRIu64 ","
        "\"copy_enqueues\":%" PRIu64 ",\"event_queries\":%" PRIu64 ",\"allocations\":%" PRIu64 ",\"frees\":%" PRIu64 ","
        "\"events_created\":%" PRIu64 ",\"events_destroyed\":%" PRIu64 ",\"stream_drains\":%" PRIu64 ",\"resets\":%" PRIu64 ","
        "\"integration_qualified\":false,\"arithmetic_qualified\":false,\"npu_qualified\":false,"
        "\"parity_qualified\":false,\"acceptance_qualified\":false,\"performance_qualified\":false,"
        "\"native_reset_interception_qualified\":false}\n",ready_mode?"ready64-v1":"gpu64-v1",head_calls,eligible_calls,excluded_calls,native_h_calls,retirements,
        s->calls,s->hits,s->misses,s->original_calls,s->captures,s->pending_fallbacks,s->evictions,s->failures,
        s->copy_enqueues,s->event_queries,s->allocations,s->frees,s->events_created,s->events_destroyed,s->stream_drains,s->resets);
    if (bytes<=0 || (size_t)bytes>=sizeof result) fatal("result-size");
    publish_file("result.json",result,(size_t)bytes);
    if (ready_mode) {
        bytes=snprintf(result,sizeof result,
            "{\"schema\":1,\"mode\":\"ready64-v1\",\"policy\":\"%s\",\"generation\":\"%s\","
            "\"ready_hits\":%" PRIu64 ",\"native_fixed_misses\":%" PRIu64 ",\"gather_skips\":%" PRIu64 ","
            "\"rms_skips\":%" PRIu64 ",\"m1_skips\":%" PRIu64 ",\"seed_rewrites\":%" PRIu64 ","
            "\"artifact_exported\":%s,\"import_sha256\":\"%s\",\"performance_qualified\":false}\n",
            fixed_rows?"fixed-v1":"capture-v1",generation_hex,ready_hits,native_fixed_misses,gather_skips,rms_skips,m1_skips,
            seed_rewrites,artifact_exported?"true":"false",import_sha);
        if (bytes<=0 || (size_t)bytes>=sizeof result) fatal("ready-result-size");
        publish_file("ready-result.json",result,(size_t)bytes);
    }
    atomic_store(&enabled,0);unlock_state();if (close(directory_fd)) fatal("directory-close");directory_fd=-1;
}
#endif
