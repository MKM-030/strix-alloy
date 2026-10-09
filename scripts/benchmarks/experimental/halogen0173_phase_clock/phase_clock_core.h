#ifndef HGN_PHASE_CLOCK_CORE_H
#define HGN_PHASE_CLOCK_CORE_H
/* No platform headers: the adapter is pinned to Linux x86-64 LP64. */
typedef unsigned char h_u8;
typedef unsigned int h_u32;
typedef unsigned long long h_u64;
typedef long long h_i64;

/* Numeric identity state shared with the Windows CPU-only pairing tests.
 * Decode requests move between objects; their signed ID survives every mover.
 * Prefill retains its original object/thread/stack ownership constraint. */
struct h_pair { h_u64 key, stack; h_i64 tid, native_start, request_id;
    h_u64 raw_start, pair_id; unsigned phase, valid; };
static int hgn_pair_identity(const struct h_pair *p,unsigned phase,h_u64 key,
                            h_u64 stack,h_i64 tid,h_i64 request_id) {
    return p->valid && p->phase==phase && (phase==2 ? p->request_id==request_id :
        (p->key==key && p->stack==stack && p->tid==tid));
}
static unsigned hgn_pair_lookup(const struct h_pair *p,unsigned count,unsigned phase,
    h_u64 key,h_u64 stack,h_i64 tid,h_i64 request_id,unsigned *free_slot,unsigned *matches) {
    unsigned i,found=count;*free_slot=count;*matches=0;
    for(i=0;i<count;++i){
        if(!p[i].valid){if(*free_slot==count)*free_slot=i;continue;}
        if(hgn_pair_identity(&p[i],phase,key,stack,tid,request_id)){
            if(found==count)found=i;++*matches;
        }
    }
    return found;
}

static int hgn_phase_delta(h_i64 native_start, h_u64 raw_start, h_u64 raw_end,
                          h_i64 native_expected, h_i64 *end_value) {
    h_u64 delta;
    if (native_start < 0 || native_expected != native_start || raw_end < raw_start)
        return 0;
    delta = raw_end - raw_start;
    if (delta > 0x7fffffffffffffffULL - (h_u64)native_start) return 0;
    *end_value = native_start + (h_i64)delta;
    return 1;
}

struct hgn_sha256 { h_u32 state[8]; h_u64 bytes; h_u32 used; h_u8 block[64]; };
static h_u32 hgn_rotr(h_u32 x, h_u32 n) { return (x >> n) | (x << (32-n)); }
static void hgn_sha_block(struct hgn_sha256 *s, const h_u8 *b) {
    static const h_u32 k[64] = {
      0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
      0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
      0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
      0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
      0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
      0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
      0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
      0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2 };
    h_u32 w[64],a,c,d,e,f,g,h,v,t1,t2,i;
    for(i=0;i<16;++i) w[i]=((h_u32)b[4*i]<<24)|((h_u32)b[4*i+1]<<16)|((h_u32)b[4*i+2]<<8)|b[4*i+3];
    for(i=16;i<64;++i) w[i]=w[i-16]+(hgn_rotr(w[i-15],7)^hgn_rotr(w[i-15],18)^(w[i-15]>>3))+
        w[i-7]+(hgn_rotr(w[i-2],17)^hgn_rotr(w[i-2],19)^(w[i-2]>>10));
    a=s->state[0];v=s->state[1];c=s->state[2];d=s->state[3];e=s->state[4];f=s->state[5];g=s->state[6];h=s->state[7];
    for(i=0;i<64;++i) {
        t1=h+(hgn_rotr(e,6)^hgn_rotr(e,11)^hgn_rotr(e,25))+((e&f)^((~e)&g))+k[i]+w[i];
        t2=(hgn_rotr(a,2)^hgn_rotr(a,13)^hgn_rotr(a,22))+((a&v)^(a&c)^(v&c));
        h=g;g=f;f=e;e=d+t1;d=c;c=v;v=a;a=t1+t2;
    }
    s->state[0]+=a;s->state[1]+=v;s->state[2]+=c;s->state[3]+=d;
    s->state[4]+=e;s->state[5]+=f;s->state[6]+=g;s->state[7]+=h;
}
static void hgn_sha_init(struct hgn_sha256 *s) {
    static const h_u32 initial[8]={0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19};
    h_u32 i;for(i=0;i<8;++i)s->state[i]=initial[i];s->bytes=0;s->used=0;
}
static void hgn_sha_update(struct hgn_sha256 *s,const h_u8 *b,h_u64 size) {
    h_u64 i;s->bytes+=size;
    for(i=0;i<size;++i) {s->block[s->used++]=b[i];if(s->used==64){hgn_sha_block(s,s->block);s->used=0;}}
}
static void hgn_sha_final(struct hgn_sha256 *s,h_u8 *digest) {
    h_u64 bits=s->bytes*8;h_u32 i;
    s->block[s->used++]=0x80;
    if(s->used>56){while(s->used<64)s->block[s->used++]=0;hgn_sha_block(s,s->block);s->used=0;}
    while(s->used<56)s->block[s->used++]=0;
    for(i=0;i<8;++i)s->block[63-i]=(h_u8)(bits>>(8*i));hgn_sha_block(s,s->block);
    for(i=0;i<32;++i)digest[i]=(h_u8)(s->state[i/4]>>(24-8*(i%4)));
}
#endif
