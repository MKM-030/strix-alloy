/* Host-only cache/artifact/sequence contract. No HIP library or engine. */
#include <assert.h>
#include <stdlib.h>
#include <string.h>
#define HALOGEN_EMBEDDING_CACHE_CORE_ONLY 1
#include "../halogen0162_mtp_embedding_cache.c"

static unsigned copies,queries,native_calls;
static int pending;
static int allocate(void **p,size_t n) {*p=malloc(n);return !*p;}
static int release(void *p) {free(p);return 0;}
static int copy(void *a,const void *b,size_t n,int kind,void *stream) {
    assert(!stream && (kind==1 || kind==2 || kind==3));copies++;memcpy(a,b,n);return 0;
}
static int drain(void *stream) {assert(!stream);pending=0;return 0;}
static int event_create(void **p,unsigned flags) {assert(flags==2);*p=malloc(1);return !*p;}
static int event_record(void *p,void *stream) {assert(p && !stream);return 0;}
static int event_query(void *p) {assert(p);queries++;return pending;}
static int event_destroy(void *p) {free(p);return 0;}
static int launch(void *unused,const uint16_t *in,uint16_t *out) {
    (void)unused;native_calls++;memcpy(out,in,5120);return 0;
}
int main(void) {
    struct ecache_ops ops={1,allocate,release,copy,drain,event_create,event_record,event_query,event_destroy};
    struct ecache_state s={0};unsigned char gen[16]={1},model[32]={2},provenance[32]={3};
    uint16_t input[2560]={0x3f80},output[2560]={0};const uint16_t *ready=NULL;
    assert(!ecache_init(&s,&ops,gen,2));
    assert(ecache_lookup_ready(&s,17,&ready)==ECACHE_MISS && !ready && !copies);
    assert(ecache_apply(&s,17,input,output,launch,NULL)==ECACHE_MISS && native_calls==1);
    unsigned before=copies;
    pending=1;assert(ecache_lookup_ready(&s,17,&ready)==ECACHE_MISS && !ready && copies==before);
    pending=0;assert(ecache_lookup_ready(&s,17,&ready)==ECACHE_HIT && ready && copies==before);
    assert(!memcmp(ready,input,5120));
    struct ecache_branch branch={0};
    assert(!ecache_branch_step(&branch,ECACHE_BRANCH_GATHER));
    assert(!ecache_branch_step(&branch,ECACHE_BRANCH_RMS));
    assert(!ecache_branch_step(&branch,ECACHE_BRANCH_M1));
    assert(!ecache_branch_step(&branch,ECACHE_BRANCH_SEED));
    assert(branch.stage==4 && ecache_branch_step(&branch,ECACHE_BRANCH_SEED)==ECACHE_ERROR);
    struct ecache_branch bad={0};assert(ecache_branch_step(&bad,ECACHE_BRANCH_RMS)==ECACHE_ERROR);
    assert(ecache_branch_step(&bad,ECACHE_BRANCH_GATHER)==ECACHE_ERROR);
    struct ecache_artifact a={0},decoded={0};unsigned char bytes[ECACHE_ARTIFACT_MAX_BYTES];size_t extent=0;
    memcpy(a.generation,gen,16);memcpy(a.model_binding,model,32);memcpy(a.provenance,provenance,32);a.origin=1;
    assert(!ecache_export_rows(&s,&a));assert(a.count==1 && a.tokens[0]==17 && !memcmp(a.rows[0],input,5120));
    assert(!ecache_artifact_encode(&a,bytes,sizeof bytes,&extent));assert(extent==5256);
    assert(!ecache_artifact_decode(bytes,extent,gen,model,provenance,&decoded));
    assert(decoded.count==1 && decoded.origin==1 && decoded.tokens[0]==17 && !memcmp(decoded.rows[0],input,5120));
    bytes[28]=1;assert(ecache_artifact_decode(bytes,extent,gen,model,provenance,&decoded)==ECACHE_ERROR);bytes[28]=0;
    assert(ecache_artifact_decode(bytes,extent+1,gen,model,provenance,&decoded)==ECACHE_ERROR);
    unsigned char other[16]={4};assert(ecache_artifact_decode(bytes,extent,other,model,provenance,&decoded)==ECACHE_ERROR);
    a.count=2;a.tokens[1]=17;assert(ecache_artifact_encode(&a,bytes,sizeof bytes,&extent)==ECACHE_ERROR);
    a.count=1;a.rows[0][1]=0x7f80;assert(ecache_artifact_encode(&a,bytes,sizeof bytes,&extent)==ECACHE_ERROR);a.rows[0][1]=0;
    assert(!ecache_close(&s));memset(&s,0,sizeof s);assert(!ecache_init(&s,&ops,gen,2));
    assert(!ecache_import_rows(&s,&a));before=copies;
    assert(ecache_lookup_ready(&s,17,&ready)==ECACHE_HIT && copies==before);
    assert(ecache_lookup_ready(&s,18,&ready)==ECACHE_MISS && !ready && copies==before);
    /* The fixed consumer performs lookup only: misses never capture or evict. */
    unsigned victim=s.next_victim;uint64_t captures=s.stats.captures,evictions=s.stats.evictions;
    const uint16_t *fixed=s.entries[0].device;
    for (unsigned i=0;i<100;i++) {
        assert(ecache_lookup_ready(&s,17,&ready)==ECACHE_HIT && ready==fixed);
        assert(ecache_lookup_ready(&s,18,&ready)==ECACHE_MISS && !ready);
    }
    assert(copies==before && s.next_victim==victim && s.stats.captures==captures && s.stats.evictions==evictions &&
        !memcmp(fixed,a.rows[0],5120));
    assert(ecache_import_rows(&s,&a)==ECACHE_ERROR);assert(ecache_close(&s)==ECACHE_ERROR);
    memset(&s,0,sizeof s);assert(!ecache_init(&s,&ops,gen,2));assert(!ecache_import_rows(&s,&a));
    /* Capture misses remain original even if readiness changes after lookup. */
    before=native_calls;assert(ecache_capture_original(&s,17,input,output,launch,NULL)==ECACHE_MISS);
    assert(native_calls==before+1 && s.stats.hits==0 && s.stats.captures==1 && !memcmp(output,input,5120));
    pending=1;before=native_calls;captures=s.stats.captures;
    assert(ecache_capture_original(&s,17,input,output,launch,NULL)==ECACHE_MISS);
    assert(native_calls==before+1 && s.stats.captures==captures);
    pending=0;assert(!ecache_close(&s));
    /* Maximum-size external artifact and finite BF16 values round-trip. */
    a.count=64;a.origin=2;
    for (unsigned i=0;i<a.count;i++) {a.tokens[i]=(int32_t)i;a.rows[i][0]=0xbf80;a.rows[i][2559]=1;}
    a.tokens[63]=ECACHE_TOKEN_COUNT-1;
    assert(!ecache_artifact_encode(&a,bytes,sizeof bytes,&extent));assert(extent==ECACHE_ARTIFACT_MAX_BYTES);
    assert(!ecache_artifact_decode(bytes,extent,gen,model,provenance,&decoded));
    assert(decoded.count==64 && decoded.origin==2 && decoded.tokens[63]==ECACHE_TOKEN_COUNT-1 &&
        !memcmp(a.rows,decoded.rows,sizeof a.rows));
    assert(ecache_artifact_encode(&a,bytes,extent-1,&extent)==ECACHE_ERROR && !extent);
    assert(!ecache_artifact_encode(&a,bytes,sizeof bytes,&extent));
    unsigned offsets[]={8,12,16,24,28,112,132};
    for (unsigned i=0;i<sizeof offsets/sizeof offsets[0];i++) {
        unsigned char saved=bytes[offsets[i]];bytes[offsets[i]]=0xff;
        assert(ecache_artifact_decode(bytes,extent,gen,model,provenance,&decoded)==ECACHE_ERROR);
        bytes[offsets[i]]=saved;
    }
    unsigned char wrong[32]={9};
    assert(ecache_artifact_decode(bytes,extent,gen,wrong,provenance,&decoded)==ECACHE_ERROR);
    assert(ecache_artifact_decode(bytes,extent,gen,model,wrong,&decoded)==ECACHE_ERROR);
    assert(ecache_artifact_decode(bytes,127,gen,model,provenance,&decoded)==ECACHE_ERROR);
    bytes[136]=0x80;bytes[137]=0x7f;assert(ecache_artifact_decode(bytes,extent,gen,model,provenance,&decoded)==ECACHE_ERROR);
    bytes[136]=0x80;bytes[137]=0xbf;
    ecache_put32(bytes+128,ECACHE_TOKEN_COUNT);assert(ecache_artifact_decode(bytes,extent,gen,model,provenance,&decoded)==ECACHE_ERROR);
    ecache_put32(bytes+128,1);assert(ecache_artifact_decode(bytes,extent,gen,model,provenance,&decoded)==ECACHE_ERROR);
    a.count=0;assert(ecache_artifact_encode(&a,bytes,sizeof bytes,&extent)==ECACHE_ERROR);
    a.count=65;assert(ecache_artifact_encode(&a,bytes,sizeof bytes,&extent)==ECACHE_ERROR);
    assert(queries>0);return 0;
}
