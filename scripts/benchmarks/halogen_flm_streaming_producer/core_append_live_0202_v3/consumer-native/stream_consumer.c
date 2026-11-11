/* Default-off HDO2 consumer. No allocation, file open/read, wait or engine call
 * in this path. Build -mgeneral-regs-only -fno-builtin; cold owner qualifies
 * actual code identity and hook. Kernel scheduling cost still needs measurement.
 */
#include "stream_consumer.h"
_Static_assert(sizeof(struct hgn0202_stream_snapshot)==128,"relay snapshot");
_Static_assert(offsetof(struct hgn0202_stream_snapshot,r13)==96,"relay r13");
_Static_assert(offsetof(struct hgn0202_stream_snapshot,rflags)==120,"relay flags");
_Static_assert(sizeof(struct hgn0202_stream_stats)==136,"stats bytes");
__attribute__((visibility("hidden"))) uintptr_t hgn0202_stream_native_fallback;
__attribute__((visibility("hidden"))) uintptr_t hgn0202_stream_native_consume;

struct stream_state {
    unsigned enabled,bound,seen_request,ready_valid[HGN0202_STREAM_SLOTS],consumed;
    int fd;
    unsigned char lock;
    uintptr_t native_request;
    int32_t last_native_generated;
    uint64_t highest_request,last_authority_sequence,last_ready_sequence,consumed_generated;
    struct hgn0202_stream_packet authority,ready[HGN0202_STREAM_SLOTS];
    struct hgn0202_stream_stats stats,*shared;
};
static struct stream_state state;

static void copy_bytes(void *d,const void *s,size_t n) {
    volatile uint8_t *out=d;const volatile uint8_t *in=s;
    for(size_t i=0;i<n;++i)out[i]=in[i];
}
static int equal_bytes(const uint8_t *a,const uint8_t *b,size_t n) {
    unsigned different=0;for(size_t i=0;i<n;++i)different|=a[i]^b[i];return !different;
}
static uint32_t le32(const uint8_t *p) {
    return (uint32_t)p[0]|(uint32_t)p[1]<<8|(uint32_t)p[2]<<16|(uint32_t)p[3]<<24;
}
static uint64_t le64(const uint8_t *p) {return le32(p)|(uint64_t)le32(p+4)<<32;}
static int same_epoch(const struct hgn0202_stream_packet *a,const struct hgn0202_stream_packet *b) {
    return a->request_id==b->request_id && a->n_prompt==b->n_prompt && a->nonce==b->nonce &&
           equal_bytes(a->epoch,b->epoch,16);
}
static int same_prefix(const struct hgn0202_stream_packet *a,const struct hgn0202_stream_packet *b) {
    return same_epoch(a,b) && a->generated==b->generated && a->current_token==b->current_token &&
           equal_bytes(a->prefix_sha256,b->prefix_sha256,32);
}

int hgn0202_stream_decode(const uint8_t *w,size_t bytes,struct hgn0202_stream_packet *o) {
    if(!w||!o||bytes<HGN0202_STREAM_HEADER||bytes>HGN0202_STREAM_MAX_BYTES)return -1;
    if(w[0]!='H'||w[1]!='D'||w[2]!='O'||w[3]!='2'||w[4]!=2||w[5]||
       w[6]!=112||w[7]||le32(w+8)!=bytes||le32(w+28))return -1;
    uint32_t kind=le32(w+12),p=le32(w+24),count=le32(w+108);
    uint64_t id=le64(w+16),nonce=le64(w+48),g=le64(w+56),sequence=le64(w+96);
    int32_t current=(int32_t)le32(w+104);unsigned epoch_nonzero=0;
    for(unsigned i=0;i<16;++i)epoch_nonzero|=w[32+i];
    if(kind<HDO2_BEGIN||kind>HDO2_END||id>=UINT64_C(1)<<63||!p||
       p>HGN0202_STREAM_MAX_CONTEXT||g>HGN0202_STREAM_MAX_CONTEXT-p||!nonce||!sequence||
       !epoch_nonzero||count>HGN0202_STREAM_MAX_IDS||bytes!=112+4*count||
       (!g&&current!=-1)||(g&&(current<0||(uint32_t)current>=HGN0202_STREAM_HEAD_ROWS)))return -1;
    if(kind==HDO2_BEGIN&&(g||count||sequence!=1))return -1;
    if(kind==HDO2_AUTHORITY&&(!g||count!=1||(int32_t)le32(w+112)!=current))return -1;
    if(kind==HDO2_READY&&(!count||!g))return -1; /* seed G0 is never injected */
    if((kind==HDO2_CANCEL||kind==HDO2_END)&&count)return -1;
    for(uint32_t i=0;i<count;++i)if(le32(w+112+4*i)>=(kind==HDO2_READY?
       HGN0202_STREAM_SHARED_IDS:HGN0202_STREAM_HEAD_ROWS))return -1;
    o->kind=kind;o->n_prompt=p;o->count=count;o->request_id=id;o->nonce=nonce;
    o->generated=g;o->sequence=sequence;o->current_token=current;
    copy_bytes(o->epoch,w+32,16);copy_bytes(o->prefix_sha256,w+64,32);
    for(uint32_t i=0;i<count;++i)o->ids[i]=(int32_t)le32(w+112+4*i);
    return 1;
}

int hgn0202_stream_select(const struct hgn0202_stream_packet *authority,
                         const struct hgn0202_stream_packet *ready,
                         const struct hgn0202_stream_native_view *native,int32_t out[3]) {
    if(!authority||!ready||!native||!out||native->budget<=0||native->generated<1||
       authority->kind!=HDO2_AUTHORITY||ready->kind!=HDO2_READY||!same_prefix(authority,ready)||
       authority->request_id!=native->request_id||authority->n_prompt!=(uint32_t)native->n_prompt||
       authority->generated!=(uint32_t)native->generated||authority->current_token!=native->current_token||
       !ready->count||ready->count>3)return -1;
    unsigned count=ready->count;if(count>(uint32_t)native->budget)count=(uint32_t)native->budget;
    for(unsigned i=0;i<count;++i)if(ready->ids[i]<0||(uint32_t)ready->ids[i]>=HGN0202_STREAM_SHARED_IDS)return -1;
    for(unsigned i=0;i<count;++i) {
        out[i]=ready->ids[i];
    }
    return (int)count;
}

static void retire(void) {
    if(state.bound) {
        ++state.stats.retirements;
    }
    state.bound=0;state.consumed=0;
    for(unsigned i=0;i<4;++i)state.ready_valid[i]=0;
}
static void publish_stats(void) {
    if(!state.shared)return;
    uint64_t *d=(uint64_t *)state.shared;const uint64_t *s=(const uint64_t *)&state.stats;
    for(unsigned i=0;i<sizeof(state.stats)/8;++i)__atomic_store_n(d+i,__atomic_load_n(s+i,__ATOMIC_RELAXED),__ATOMIC_RELAXED);
}
int hgn0202_stream_configure(int fd,unsigned enabled,uintptr_t fallback,uintptr_t consume) {
    if(enabled>1||!fallback||!consume||(enabled&&fd<0))return 0;
    volatile uint8_t *p=(volatile uint8_t *)&state;for(size_t i=0;i<sizeof(state);++i)p[i]=0;
    state.fd=fd;state.enabled=enabled;hgn0202_stream_native_fallback=fallback;
    hgn0202_stream_native_consume=consume;return 1;
}
void hgn0202_stream_bind_stats(struct hgn0202_stream_stats *shared) {state.shared=shared;publish_stats();}
int hgn0202_stream_get_stats(struct hgn0202_stream_stats *out) {
    if(!out||__atomic_test_and_set(&state.lock,__ATOMIC_ACQUIRE))return 0;
    uint64_t *d=(uint64_t *)out;const uint64_t *s=(const uint64_t *)&state.stats;
    for(unsigned i=0;i<sizeof(state.stats)/8;++i)d[i]=__atomic_load_n(s+i,__ATOMIC_RELAXED);
    __atomic_clear(&state.lock,__ATOMIC_RELEASE);return 1;
}

static int native_view(const struct hgn0202_stream_snapshot *saved,struct hgn0202_stream_native_view *out) {
    if(!saved||!saved->r13) {
        return 0;
    }
    const uint8_t *frame=(const uint8_t *)saved+256;
    uintptr_t request=*(const uintptr_t *)(frame+0x178);if(!request)return 0;
    const uint8_t *r=(const uint8_t *)request;uintptr_t spec=*(const uintptr_t *)(r+0x10);
    if(spec!=(uintptr_t)saved->r13)return 0;
    out->request=request;out->speculative=spec;out->request_id=*(const uint64_t *)r;
    out->n_prompt=*(const int32_t *)(r+0x5c);out->generated=*(const int32_t *)(r+0x60);
    out->current_token=*(const int32_t *)(spec+0x244);out->budget=(int32_t)(uint32_t)saved->rsi;
    return out->request_id<UINT64_C(1)<<63&&out->n_prompt>0&&out->generated>=0;
}

static long receive_datagram(int fd,uint8_t *buffer,size_t capacity) {
#ifdef HGN0202_STREAM_TEST
    extern long hgn0202_stream_test_recv(int,uint8_t *,size_t);
    return hgn0202_stream_test_recv(fd,buffer,capacity);
#else
    register long nr __asm__("rax")=45;register long a0 __asm__("rdi")=fd;
    register void *a1 __asm__("rsi")=buffer;register size_t a2 __asm__("rdx")=capacity;
    register long a3 __asm__("r10")=0x40|0x20; /* MSG_DONTWAIT|MSG_TRUNC */
    register long a4 __asm__("r8")=0;register long a5 __asm__("r9")=0;
    __asm__ volatile("syscall":"+a"(nr):"D"(a0),"S"(a1),"d"(a2),"r"(a3),"r"(a4),"r"(a5):"rcx","r11","memory","cc");return nr;
#endif
}

static void admit(const struct hgn0202_stream_packet *p,const struct hgn0202_stream_native_view *n) {
    if(p->request_id!=n->request_id||p->n_prompt!=(uint32_t)n->n_prompt){++state.stats.rejected_datagrams;return;}
    if(p->kind==HDO2_BEGIN) {
        if((state.seen_request&&p->request_id<=state.highest_request)||state.bound) {
            ++state.stats.rejected_datagrams;return;
        }
        state.highest_request=p->request_id;state.seen_request=1;state.bound=1;
        copy_bytes(&state.authority,p,sizeof(*p));state.last_authority_sequence=1;state.last_ready_sequence=0;
        ++state.stats.begins;return;
    }
    if(!state.bound||!same_epoch(p,&state.authority)){++state.stats.rejected_datagrams;return;}
    if(p->kind==HDO2_CANCEL||p->kind==HDO2_END) {
        if(p->sequence>state.last_authority_sequence)retire();else ++state.stats.rejected_datagrams;return;
    }
    if(p->kind==HDO2_AUTHORITY) {
        if(p->sequence!=state.last_authority_sequence+1||p->generated!=state.authority.generated+1||
           p->generated>(uint32_t)n->generated) {
            ++state.stats.sequence_failures;retire();return;
        }
        copy_bytes(&state.authority,p,sizeof(*p));state.last_authority_sequence=p->sequence;++state.stats.authorities;
        for(unsigned i=0;i<4;++i)if(state.ready_valid[i]&&state.ready[i].generated<p->generated)state.ready_valid[i]=0;
        return;
    }
    if(p->kind==HDO2_READY) {
        if(p->sequence<=state.last_ready_sequence||p->generated<state.authority.generated||
           p->generated>state.authority.generated+3) {++state.stats.stale_readies;return;}
        state.last_ready_sequence=p->sequence;unsigned slot=(unsigned)(p->generated%4);
        copy_bytes(&state.ready[slot],p,sizeof(*p));state.ready_valid[slot]=1;++state.stats.readies;
    }
}

int hgn0202_stream_consume_snapshot(const struct hgn0202_stream_snapshot *saved) {
    if(!state.enabled)return -1;
    if(__atomic_test_and_set(&state.lock,__ATOMIC_ACQUIRE)) {
        __atomic_add_fetch(&state.stats.lock_busy,1,__ATOMIC_RELAXED);return -1;
    }
    ++state.stats.queries;int result=-1;struct hgn0202_stream_native_view n;
    if(!native_view(saved,&n))goto finish;
    if(state.native_request&&(state.native_request!=n.request||
       (state.bound&&(state.authority.request_id!=n.request_id||state.authority.n_prompt!=(uint32_t)n.n_prompt))||
       n.generated<state.last_native_generated))retire();
    state.native_request=n.request;state.last_native_generated=n.generated;
    uint8_t bytes[HGN0202_STREAM_MAX_BYTES];
    for(unsigned i=0;i<HGN0202_STREAM_DRAIN_LIMIT;++i) {
        long size=receive_datagram(state.fd,bytes,sizeof(bytes));if(size==-11)break;if(size==-4)continue;
        if(size<0){++state.stats.recv_errors;retire();break;}
        ++state.stats.datagrams;struct hgn0202_stream_packet p;
        if(size>(long)sizeof(bytes)||hgn0202_stream_decode(bytes,(size_t)size,&p)!=1){++state.stats.rejected_datagrams;continue;}
        admit(&p,&n);
    }
    if(!state.bound||n.generated<1||state.authority.generated!=(uint32_t)n.generated) {++state.stats.prefix_misses;goto finish;}
    if(state.authority.current_token!=n.current_token){++state.stats.current_misses;goto finish;}
    if(state.consumed&&state.consumed_generated==(uint32_t)n.generated){++state.stats.already_consumed;goto finish;}
    unsigned slot=(unsigned)n.generated%4;if(!state.ready_valid[slot])goto finish;
    int32_t ids[3];result=hgn0202_stream_select(&state.authority,&state.ready[slot],&n,ids);
    if(result>0) {
        uint8_t *frame=(uint8_t *)(uintptr_t)saved+256;
        for(int i=0;i<result;++i)((int32_t *)(frame+0x2a0))[i]=ids[i];
        *(int64_t *)(frame+0x480)=-1;frame[0x220]=0;frame[0xa0]=0;
        state.consumed=1;state.consumed_generated=(uint32_t)n.generated;state.ready_valid[slot]=0;
        ++state.stats.hits;state.stats.proposed_ids+=(uint64_t)result;
    } else ++state.stats.prefix_misses;
finish:
    if(result<0) {
        ++state.stats.native_fallbacks;
    }
    publish_stats();
    __atomic_clear(&state.lock,__ATOMIC_RELEASE);return result;
}
