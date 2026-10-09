/* Source-only owned complete device-predication component.
 * No engine/model hook. A stock128, B synchronized64, C nine-launch predicate path.
 * One transaction per arm; every candidate retirement is charged in host time.
 * All build/run/hardware/lifecycle actions remain root-owned. */
#define _POSIX_C_SOURCE 200809L
#include <dlfcn.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <signal.h>
#include <time.h>
#include <inttypes.h>
#include <unistd.h>

#define BN64_PREDICATION_ORACLE_LIBRARY
#include "oracle.c"

enum { N=8192, R=81920, EXPERTS=512, TOPK=10, WIDTH=2560, HIDDEN=640,
       GUARD=4096, CHUNK=4*1024*1024, BATCH=1, MEASURED_TRIADS=6 };
#define GU_CODE UINT64_C(838860800)
#define DN_CODE UINT64_C(419430400)
#define GU_BLOB (GU_CODE+UINT64_C(26214400))
#define DN_BLOB (DN_CODE+UINT64_C(13107200))
#define X_BYTES ((size_t)N*WIDTH*2)
#define GU_BYTES ((size_t)R*HIDDEN*2)
#define DN_BYTES ((size_t)R*WIDTH*2)
#define FINAL_BYTES X_BYTES
#define CAP64 (R/64+EXPERTS)
#define CAP128 (R/128+EXPERTS)
/* Retained proofs (relative to PREP):
 * prefill-bulk-moe-retile-scope-20261009/host-route-proof-v1.metadata-bounds.md
 * certifies GU 2560/1280 across all92 exact native epilogue triples;
 * host-route-proof-v1.fixture-abi.md pins DN/fold's 2560 FP16 channel words
 * (5120 bytes), with the original dense row/fold association unchanged. */
enum { GU_META0_BYTES=2560, GU_META1_BYTES=1280, DN_META_BYTES=5120 };

typedef struct { uint64_t weight, packed_offset, scale_offset, scale_stride;
    float codebook[16]; uint64_t metadata0,metadata1,input,permutation,items,count,output;
} ProjectionArgs;
typedef struct { uint64_t ids,prefix,raw; int32_t rows; uint32_t pad;
    uint64_t gu_items,dn_items,counts; } ItemArgs;
typedef struct { uint64_t dense,inverse; int32_t tokens; uint32_t pad;
    uint64_t route_weights,channel,residual,token_scalar,output; } FoldArgs;
typedef struct { int32_t expert,tile,start,rows; } Item;
_Static_assert(sizeof(void*)==8,"64-bit host ABI required");
_Static_assert(sizeof(int)==4,"native int32 fixture ABI required");
_Static_assert(sizeof(ProjectionArgs)==152 && offsetof(ProjectionArgs,metadata0)==0x60 &&
    offsetof(ProjectionArgs,input)==0x70 && offsetof(ProjectionArgs,output)==0x90,"projection ABI");
_Static_assert(sizeof(ItemArgs)==56 && offsetof(ItemArgs,gu_items)==32 &&
    offsetof(ItemArgs,counts)==48,"item ABI");
_Static_assert(sizeof(FoldArgs)==64 && offsetof(FoldArgs,route_weights)==24 &&
    offsetof(FoldArgs,output)==56,"fold ABI");
_Static_assert(sizeof(Item)==16,"native item ABI");

static int (*Malloc)(void**,size_t),(*Free)(void*),(*Memcpy)(void*,const void*,size_t,int);
static int (*Memset)(void*,int,size_t),(*ModuleLoad)(void**,const char*);
static int (*GetFunction)(void**,void*,const char*),(*Unload)(void*);
static int (*Launch)(void*,unsigned,unsigned,unsigned,unsigned,unsigned,unsigned,unsigned,void*,void**,void**);
static int (*StreamSync)(void*),(*EventCreate)(void**,unsigned),(*EventRecord)(void*,void*);
static int (*EventElapsed)(float*,void*,void*),(*EventDestroy)(void*);
typedef struct { const char *name; void *base,*p; size_t bytes; } Buffer;
enum { WG,WD,X,P,I,IDS,PREFIX,RAW,WEIGHTS,M0,M1,MD,RESIDUAL,TOKEN,GI128,DI128,COUNTS128,
       GU,DN,FINAL,REF_GU,REF_DN,REF_FINAL,GI64,DI64,COUNTS64,SELECT128,SELECT64,
       PRIVATE_RAW,PRIVATE_IDS,PRIVATE_PREFIX,STATE,POST,STICKY,VIEW_RAW,VIEW_IDS,VIEW_PREFIX,BUFFER_COUNT };
static Buffer b[BUFFER_COUNT];
static unsigned char *scratch,*other;
static int route_counts[EXPERTS],route_prefix[EXPERTS];
static int32_t host_raw[EXPERTS+2],host_ids[EXPERTS],host_prefix[EXPERTS+1];
static volatile sig_atomic_t interrupted;
static int pending,attempted_phase,transaction_retired,restoring,terminal_pending,last_launch_error;
static uint64_t epoch_counter,sticky_generation;
static void *native_functions[7],*custom_functions[2];
static ItemArgs original_items;
static ProjectionArgs original_gu,original_dn;
static FoldArgs original_fold;
enum { TX_ITEMS=1,TX_GU=2,TX_DN=3,TX_FOLD=4 };
static void signal_stop(int value) { interrupted=value; }
static int copy_owned(void *dst,const void *src,size_t bytes,int kind) {
    if(terminal_pending)return -1;
    pending=1;return Memcpy(dst,src,bytes,kind);
}
static int set_owned(void *dst,int byte,size_t bytes) {
    if(terminal_pending)return -1;
    pending=1;return Memset(dst,byte,bytes);
}
static int drain_owned(const char *why) {
    if(terminal_pending)return 0;
    int error=StreamSync(NULL);
    if(error){terminal_pending=1;fprintf(stderr,"%s: HIP %d; owned retirement unresolved\n",why,error);return 0;}
    pending=0;return 1;
}
static int ok(int err,const char *what) {
    if(err)fprintf(stderr,"%s: HIP %d\n",what,err);
    return !err;
}
#define HIP(e) do { if(!ok((e),#e))goto done; } while(0)
#define LOAD(name,sym) do { *(void**)(&name)=dlsym(lib,"hip" sym); if(!name){fprintf(stderr,"missing hip%s\n",sym);goto done;} } while(0)
static uint64_t ptr(int i) { return (uint64_t)(uintptr_t)b[i].p; }
static uint32_t mix(uint64_t x) { x^=x>>30;x*=UINT64_C(0xbf58476d1ce4e5b9);x^=x>>27;
    x*=UINT64_C(0x94d049bb133111eb);x^=x>>31;return (uint32_t)x; }

/* Entire code object is fingerprinted before dlopen/ModuleLoad. OpenSSL is used
 * only for host SHA256, resolved dynamically; no shell and no GPU initialization. */
static int pinned_module(const char *path) {
    static const unsigned char expected[32]={0x18,0x93,0x74,0x28,0xb5,0x44,0xe8,0xa5,
        0xef,0x1d,0xae,0x31,0xdb,0x97,0xf3,0x61,0x36,0xe8,0xcd,0xec,0xa9,0x0e,0x6c,0x49,
        0x45,0x8e,0xf8,0x31,0xb8,0x22,0xa0,0x39};
    void *crypto=dlopen("libcrypto.so.3",RTLD_NOW|RTLD_LOCAL);FILE *f=NULL;int pass=0;
    void*(*newctx)(void)=NULL;void(*freectx)(void*)=NULL;
    const void*(*sha256)(void)=NULL;int(*init)(void*,const void*,void*)=NULL;
    int(*update)(void*,const void*,size_t)=NULL;int(*final)(void*,unsigned char*,unsigned*)=NULL;
    void *ctx=NULL;unsigned char digest[32],header[64];unsigned n=0;size_t total=0;
    if(!crypto){fprintf(stderr,"libcrypto.so.3 required for pinned preflight\n");goto out;}
#define CRYPTO(dst,sym) do { *(void**)(&dst)=dlsym(crypto,sym);if(!dst)goto out; } while(0)
    CRYPTO(newctx,"EVP_MD_CTX_new");CRYPTO(freectx,"EVP_MD_CTX_free");CRYPTO(sha256,"EVP_sha256");
    CRYPTO(init,"EVP_DigestInit_ex");CRYPTO(update,"EVP_DigestUpdate");CRYPTO(final,"EVP_DigestFinal_ex");
#undef CRYPTO
    f=fopen(path,"rb");if(!f){perror(path);goto out;}
    if(fread(header,1,sizeof(header),f)!=sizeof(header) || memcmp(header,"\177ELF\2\1",6) ||
        header[18]!=0xe0 || header[19]!=0){fprintf(stderr,"not ELF64 little-endian AMDGPU\n");goto out;}
    rewind(f);ctx=newctx();if(!ctx||!init(ctx,sha256(),NULL))goto out;
    for(;;){size_t got=fread(scratch,1,CHUNK,f);
        if(got&&!update(ctx,scratch,got))goto out;
        total+=got;
        if(got<CHUNK){if(ferror(f))goto out;break;}}
    if(total!=17765424 || !final(ctx,digest,&n) || n!=32 || memcmp(digest,expected,32)) {
        fprintf(stderr,"code object size/SHA256 differs from audited ABI\n");goto out;}
    pass=1;
out:
    if(ctx&&freectx)freectx(ctx);
    if(f)fclose(f);
    if(crypto)dlclose(crypto);
    return pass;
}

static int allocate(int i,const char *name,size_t bytes) {
    b[i].name=name;b[i].bytes=bytes;
    if(bytes>SIZE_MAX-2*GUARD || !ok(Malloc(&b[i].base,bytes+2*GUARD),name))return 0;
    b[i].p=(unsigned char*)b[i].base+GUARD;
    return ok(set_owned(b[i].base,0xa5,bytes+2*GUARD),"initialize payload and guards");
}
/* Bounded host staging; no full weight or output duplicate on the host. */
static int fill_blob(int i,size_t packed,uint64_t seed) {
    for(size_t off=0;off<b[i].bytes;off+=CHUNK){size_t len=b[i].bytes-off;if(len>CHUNK)len=CHUNK;
        for(size_t k=0;k<len;k++) {size_t pos=off+k;
            if(pos<packed)scratch[k]=(unsigned char)(mix(seed+pos)>>24);
            else {uint16_t h=(uint16_t)(0x1000+(mix(seed+(pos-packed)/2)&0x3ff));
                scratch[k]=(unsigned char)(h>>(8*((pos-packed)&1)));}}
        if(!ok(copy_owned((unsigned char*)b[i].p+off,scratch,len,1),"initialize packed Q4/FP16 blob"))return 0;
    }return 1;
}
static int fill_half(int i,uint64_t seed,int kind) {
    for(size_t off=0;off<b[i].bytes;off+=CHUNK){size_t len=b[i].bytes-off;if(len>CHUNK)len=CHUNK;
        for(size_t k=0;k<len/2;k++){uint32_t h=mix(seed+off/2+k);uint16_t z;
            z=kind==0 ? (uint16_t)((0x3c80+(h&127))|((h>>16)&0x8000)) : (uint16_t)(0x3800+(h&255));
            memcpy(scratch+2*k,&z,2);}
        if(!ok(copy_owned((unsigned char*)b[i].p+off,scratch,len,1),"initialize BF16/FP16 operand"))return 0;
    }return 1;
}
static int fill_float(int i,float value) {
    for(size_t off=0;off<b[i].bytes;off+=CHUNK){size_t len=b[i].bytes-off;if(len>CHUNK)len=CHUNK;
        for(size_t k=0;k<len/4;k++)memcpy(scratch+4*k,&value,4);
        if(!ok(copy_owned((unsigned char*)b[i].p+off,scratch,len,1),"initialize FP32 operand"))return 0;
    }return 1;
}

static int prepare_routes(int pattern,int32_t *forward,int32_t *inverse,int *s64,int *s128) {
    int remaining[EXPERTS],target[EXPERTS],seen[EXPERTS]={0},raw[EXPERTS+2],ids[EXPERTS]={0},prefix[EXPERTS+1]={0};
    int32_t *routes=malloc((size_t)R*4);if(!routes)return 0;
    for(int e=0;e<EXPERTS;e++)target[e]=160;
    if(pattern){static const int boundary[]={1,15,16,17,31,32,33,47,48,49,63,64,65,79,80,81,
        95,96,97,111,112,113,127,128,129,159,160,161,255,256,257};
        int deficit=0;size_t m=sizeof(boundary)/sizeof(boundary[0]);
        for(size_t e=0;e<m;e++){deficit+=160-boundary[e];target[e]=boundary[e];}
        for(int e=(int)m;deficit>0;e=(e+1==EXPERTS?(int)m:e+1)){target[e]++;deficit--;}
        if(deficit<0){free(routes);return 0;}
    }
    memcpy(remaining,target,sizeof(target));
    for(int n=0;n<N;n++){int chosen[TOPK];
        if(!pattern)for(int j=0;j<TOPK;j++)chosen[j]=(TOPK*n+j)%EXPERTS;
        else for(int j=0;j<TOPK;j++){int best=-1;
            for(int e=0;e<EXPERTS;e++){int used=0;for(int z=0;z<j;z++)used|=chosen[z]==e;
                if(!used && remaining[e]>0 && (best<0||remaining[e]>remaining[best]))best=e;}
            if(best<0){free(routes);return 0;}
            chosen[j]=best;
        }
        for(int j=0;j<TOPK;j++){int e=chosen[j];routes[TOPK*n+j]=e;seen[e]++;remaining[e]--;}
    }
    int active=0,total=0;*s64=*s128=0;
    for(int e=0;e<EXPERTS;e++){if(seen[e]!=target[e]||remaining[e]||target[e]<0||target[e]>N){free(routes);return 0;}
        raw[e]=target[e];if(target[e]){ids[active]=e;prefix[active++]=total;}
        total+=target[e];*s64+=(target[e]+63)/64;*s128+=(target[e]+127)/128;}
    prefix[active]=total;raw[EXPERTS]=active;raw[EXPERTS+1]=total;
    memcpy(host_raw,raw,sizeof(raw));memcpy(host_ids,ids,sizeof(ids));memcpy(host_prefix,prefix,sizeof(prefix));
    if(total!=R||*s64>CAP64||*s128>CAP128){free(routes);return 0;}
    int cursor[EXPERTS],base=0;for(int e=0;e<EXPERTS;e++){
        route_counts[e]=target[e];route_prefix[e]=base;cursor[e]=base;base+=target[e];}
    for(int s=0;s<R;s++){int q=cursor[routes[s]]++;forward[q]=s;inverse[s]=q;}
    for(int s=0;s<R;s++)if(forward[inverse[s]]!=s){free(routes);return 0;}
    /* Stable expert sort: ascending expert, then original slot, identical for both BNs. */
    memset(scratch,0,EXPERTS*4);memcpy(scratch,ids,(size_t)active*4);
    int pass=ok(copy_owned(b[IDS].p,scratch,EXPERTS*4,1),"active expert IDs") &&
        ok(copy_owned(b[PREFIX].p,prefix,sizeof(prefix),1),"expert row prefixes") &&
        ok(copy_owned(b[RAW].p,raw,sizeof(raw),1),"histogram/bookkeeping") &&
        ok(copy_owned(b[P].p,forward,(size_t)R*4,1),"forward permutation") &&
        ok(copy_owned(b[I].p,inverse,(size_t)R*4,1),"inverse permutation");
    printf("{\"type\":\"routing\",\"pattern\":\"%s\",\"N\":%d,\"R\":%d,\"active_experts\":%d,\"segments128\":%d,\"segments64\":%d,\"ten_distinct_experts_per_token\":true,\"sorting_in_timing\":false,\"rotation_in_timing\":false}\n",
        pattern?"boundary_tails":"uniform512x160",N,R,active,*s128,*s64);
    free(routes);return pass;
}

static int guards(void) {
    for(int i=0;i<BUFFER_COUNT;i++){if(!b[i].base)continue;
        if(!ok(copy_owned(scratch,b[i].base,GUARD,2),"prefix guard read") ||
            !ok(copy_owned(other,(unsigned char*)b[i].p+b[i].bytes,GUARD,2),"suffix guard read"))return 0;
        for(size_t k=0;k<GUARD;k++)if(scratch[k]!=0xa5||other[k]!=0xa5){
            fprintf(stderr,"guard changed: %s byte %zu\n",b[i].name,k);return 0;}}
    return 1;
}
static int compare_half(int live,int reference,size_t *mismatch,size_t *nonfinite) {
    *mismatch=*nonfinite=0;size_t first=SIZE_MAX;uint16_t av0=0,bv0=0;
    for(size_t off=0;off<b[live].bytes;off+=CHUNK){size_t len=b[live].bytes-off;if(len>CHUNK)len=CHUNK;
        if(!ok(copy_owned(scratch,(unsigned char*)b[live].p+off,len,2),"live output chunk") ||
            !ok(copy_owned(other,(unsigned char*)b[reference].p+off,len,2),"reference output chunk"))return 0;
        for(size_t k=0;k<len;k+=2){uint16_t av,bv;memcpy(&av,scratch+k,2);memcpy(&bv,other+k,2);
            if(av!=bv){if(first==SIZE_MAX){first=(off+k)/2;av0=av;bv0=bv;}(*mismatch)++;}
            *nonfinite+=((av&0x7f80)==0x7f80)+((bv&0x7f80)==0x7f80);}}
    if(*mismatch)fprintf(stderr,"%s first mismatch word %zu: 0x%04x vs 0x%04x\n",b[live].name,first,av0,bv0);
    return 1;
}
static int capture(void) {
    return ok(copy_owned(b[REF_GU].p,b[GU].p,GU_BYTES,3),"retain full GU") &&
        ok(copy_owned(b[REF_DN].p,b[DN].p,DN_BYTES,3),"retain full DN") &&
        ok(copy_owned(b[REF_FINAL].p,b[FINAL].p,FINAL_BYTES,3),"retain full final");
}
static int check_items(int bn,int segments,int gi,int di,int ci,int read_counts) {
    int counts[2]={5*segments,10*segments};
    if(read_counts){int actual[2];if(!ok(copy_owned(actual,b[ci].p,8,2),"native item counts"))return 0;
        if(memcmp(actual,counts,sizeof(actual))){fprintf(stderr,"native count mismatch BN%d\n",bn);return 0;}}
    for(int dn=0;dn<2;dn++){int n=counts[dn],tiles=dn?10:5,index=dn?di:gi;
        if(!ok(copy_owned(scratch,b[index].p,(size_t)n*sizeof(Item),2),"item records"))return 0;
        Item *items=(Item*)scratch;int q=0;
        for(int e=0;e<EXPERTS;e++)for(int start=0;start<route_counts[e];start+=bn)for(int tile=0;tile<tiles;tile++){
            Item expected={e,tile,route_prefix[e]+start,route_counts[e]-start};if(expected.rows>bn)expected.rows=bn;
            if(q>=n || memcmp(&items[q],&expected,sizeof(expected))){fprintf(stderr,"native item mismatch BN%d index%d\n",bn,q);return 0;}
            q++;
        }
        if(q!=n)return 0;
    }return 1;
}
static int launch(void *f,unsigned grid,unsigned block,void *arg,size_t bytes) {
    void *extra[]={ (void*)(uintptr_t)1,arg,(void*)(uintptr_t)2,&bytes,(void*)(uintptr_t)3 };
    last_launch_error=-1;
    if(terminal_pending)return 0;
    pending=1;
    last_launch_error=Launch(f,grid,1,1,block,1,1,0,NULL,NULL,extra);
    return ok(last_launch_error,"packed-kernarg launch");
}

/* Root's sealed build supplies this digest; verify custom bytes before loading
 * HIP, alongside the fixed native fingerprint. Never infer it from a filename. */
static int pinned_custom(const char *path,const char *expected) {
    void *crypto=NULL,*ctx=NULL;FILE *f=NULL;int pass=0;
    void *(*newctx)(void)=NULL;void (*freectx)(void*)=NULL;
    const void *(*sha256)(void)=NULL;int (*init)(void*,const void*,void*)=NULL;
    int (*update)(void*,const void*,size_t)=NULL;int (*final)(void*,unsigned char*,unsigned*)=NULL;
    unsigned char digest[32],header[64];char hex[65];unsigned n=0;size_t total=0;
    if(strlen(expected)!=64)return 0;
    for(int i=0;i<64;i++)if(!((expected[i]>='0'&&expected[i]<='9') || (expected[i]>='a'&&expected[i]<='f')))return 0;
    crypto=dlopen("libcrypto.so.3",RTLD_NOW|RTLD_LOCAL);if(!crypto)goto out;
#define HASH_FN(dst,sym) do { *(void**)(&dst)=dlsym(crypto,sym);if(!dst)goto out; } while(0)
    HASH_FN(newctx,"EVP_MD_CTX_new");HASH_FN(freectx,"EVP_MD_CTX_free");HASH_FN(sha256,"EVP_sha256");
    HASH_FN(init,"EVP_DigestInit_ex");HASH_FN(update,"EVP_DigestUpdate");HASH_FN(final,"EVP_DigestFinal_ex");
#undef HASH_FN
    f=fopen(path,"rb");if(!f)goto out;
    if(fread(header,1,sizeof(header),f)!=sizeof(header) || memcmp(header,"\177ELF\2\1",6) ||
       header[18]!=0xe0 || header[19]!=0)goto out;
    rewind(f);ctx=newctx();if(!ctx||!init(ctx,sha256(),NULL))goto out;
    for(;;){size_t got=fread(scratch,1,CHUNK,f);total+=got;
        if(total>8*1024*1024 || (got&&!update(ctx,scratch,got)))goto out;
        if(got<CHUNK){if(ferror(f))goto out;break;}}
    if(!final(ctx,digest,&n)||n!=32)goto out;
    for(unsigned i=0;i<32;i++)snprintf(hex+2*i,3,"%02x",digest[i]);
    pass=!strcmp(hex,expected);
out:
    if(ctx&&freectx)freectx(ctx);
    if(f)fclose(f);
    if(crypto)dlclose(crypto);
    if(!pass)fprintf(stderr,"custom code object SHA256/ELF admission failed\n");
    return pass;
}

typedef struct { const char *name;uint64_t epoch;unsigned grid,block;int phase,error;
    size_t bytes;unsigned char args[152]; } Attempt;
static Attempt journal[12],recovery_journal[4];
static unsigned journal_count,recovery_count;
static uint64_t transaction_epoch;
static int submit(void *f,const char *name,int phase,unsigned grid,unsigned block,void *args,size_t bytes) {
    if(terminal_pending || (interrupted&&!restoring))return 0;
    if(bytes>sizeof(journal[0].args) || (!restoring && (phase<attempted_phase ||
       (phase==TX_DN&&attempted_phase<TX_GU) || (phase==TX_FOLD&&attempted_phase<TX_DN))))return 0;
    Attempt *entry;
    if(restoring){if(recovery_count>=4)return 0;entry=&recovery_journal[recovery_count++];}
    else {if(journal_count>=12)return 0;entry=&journal[journal_count++];attempted_phase=phase;}
    *entry=(Attempt){name,transaction_epoch,grid,block,phase,-1,bytes,{0}};
    memcpy(entry->args,args,bytes); /* Immutable attempted Args include failed calls. */
    int result=launch(f,grid,block,args,bytes);entry->error=last_launch_error;
    return result;
}
static int restore_attempted_prefix(void) {
    int phase=attempted_phase,pass=1;recovery_count=0;
    if(!drain_owned("pre-replay NULL-stream fence")){terminal_pending=1;return 0;}
    if(!phase)return 1;
    restoring=1;
    pass=submit(native_functions[0],"replay-items128",TX_ITEMS,1,512,&original_items,sizeof(original_items));
    if(pass&&phase>=TX_GU)pass=submit(native_functions[1],"replay-GU128",TX_GU,5*CAP128,256,&original_gu,sizeof(original_gu));
    if(pass&&phase>=TX_DN)pass=submit(native_functions[2],"replay-DN128",TX_DN,10*CAP128,256,&original_dn,sizeof(original_dn));
    if(pass&&phase>=TX_FOLD)pass=submit(native_functions[6],"replay-fold",TX_FOLD,(20*N+7)/8,256,&original_fold,sizeof(original_fold));
    restoring=0;
    if(!drain_owned("post-replay NULL-stream fence")){terminal_pending=1;return 0;}
    printf("{\"type\":\"recovery\",\"epoch\":%" PRIu64 ",\"attempted_phase\":%d,\"replay_attempts\":%u,\"restored_prefix\":%s,\"sample_invalid\":true}\n",
           transaction_epoch,phase,recovery_count,pass?"true":"false");
    transaction_retired=pass;
    return pass;
}
static int record_event(void *event,const char *label) {
    if(terminal_pending || (interrupted&&!restoring))return 0;
    pending=1;return ok(EventRecord(event,NULL),label);
}
static int raw_ns(uint64_t *value) {
    struct timespec now;if(clock_gettime(CLOCK_MONOTONIC_RAW,&now))return 0;
    *value=(uint64_t)now.tv_sec*UINT64_C(1000000000)+(uint64_t)now.tv_nsec;return 1;
}
static ProjectionArgs projection(int dn,int gi,int di,int ci) {
    ProjectionArgs a;memset(&a,0,sizeof(a));a.weight=ptr(dn?WD:WG);
    a.scale_offset=dn?DN_CODE:GU_CODE;a.scale_stride=dn?10:40;
    for(int j=0;j<16;j++)a.codebook[j]=(float)(j-8);
    a.metadata0=ptr(dn?MD:M0);a.metadata1=dn?0:ptr(M1);a.input=ptr(dn?GU:X);
    a.permutation=dn?0:ptr(P);a.items=ptr(dn?di:gi);a.count=ptr(ci)+(dn?4:0);
    a.output=ptr(dn?DN:GU);return a;
}
static void stock_snapshots(void) {
    original_items=(ItemArgs){ptr(IDS),ptr(PREFIX),ptr(RAW),R,0,ptr(GI128),ptr(DI128),ptr(COUNTS128)};
    original_gu=projection(0,GI128,DI128,COUNTS128);original_dn=projection(1,GI128,DI128,COUNTS128);
    original_fold=(FoldArgs){ptr(DN),ptr(I),N,0,ptr(WEIGHTS),ptr(MD),ptr(RESIDUAL),ptr(TOKEN),ptr(FINAL)};
}
static int legacy_histogram(uint64_t epoch,int *gu,int *dn) {
    int32_t raw[EXPERTS+2],ids[EXPERTS],prefix[EXPERTS+1];Bn64ValidationResult status;
    if(!drain_owned("legacy histogram decision fence") ||
       !ok(copy_owned(raw,b[RAW].p,sizeof(raw),2),"legacy raw D2H") ||
       !ok(copy_owned(ids,b[IDS].p,sizeof(ids),2),"legacy IDs D2H") ||
       !ok(copy_owned(prefix,b[PREFIX].p,sizeof(prefix),2),"legacy prefix D2H"))return 0;
    bn64_oracle_histogram(raw,ids,prefix,epoch,&status);
    if(status.failures){fprintf(stderr,"legacy histogram rejection 0x%x\n",status.failures);return 0;}
    *gu=(int)status.expected_gu;*dn=(int)status.expected_dn;return 1;
}
static int legacy_post(uint64_t epoch,int gu,int dn) {
    unsigned char guard_values[4][GUARD];const unsigned char *g[4];int32_t counts[2];Bn64ValidationResult status;
    const void *gpu[4]={b[GI64].base,(unsigned char*)b[GI64].p+b[GI64].bytes,
                       b[DI64].base,(unsigned char*)b[DI64].p+b[DI64].bytes};
    if(!drain_owned("legacy post decision fence"))return 0;
    /* Preserve adapter order: all four guards, then the 8-byte count pair. */
    for(int i=0;i<4;i++){g[i]=guard_values[i];if(!ok(copy_owned(guard_values[i],gpu[i],GUARD,2),"legacy guard D2H"))return 0;}
    if(!ok(copy_owned(counts,b[COUNTS64].p,sizeof(counts),2),"legacy counts D2H"))return 0;
    bn64_oracle_post(counts,gu,dn,g,epoch,&status);
    if(status.failures){fprintf(stderr,"legacy post rejection 0x%x\n",status.failures);return 0;}
    return 1;
}

enum Injection { INJ_NONE,INJ_ACTIVE_ZERO,INJ_ACTIVE_NEG,INJ_ACTIVE_OVER,INJ_TOTAL_LOW,INJ_TOTAL_HIGH,
    INJ_ROWS_NEG,INJ_ROWS_OVER,INJ_SUM_LOW,INJ_SUM_HIGH,INJ_ID_BAD,INJ_ID_NEG,INJ_ID_OVER,
    INJ_PREFIX_FIRST,INJ_PREFIX_MIDDLE,INJ_PREFIX_TERMINAL,
    INJ_GU_LOW,INJ_DN_HIGH,INJ_COUNTS_SWAP,INJ_COUNTS_NEG,INJ_COUNTS_MAX,
    INJ_GU_LEAD_FIRST,INJ_GU_LEAD_MIDDLE,INJ_GU_LEAD_LAST,
    INJ_GU_TRAIL_FIRST,INJ_GU_TRAIL_MIDDLE,INJ_GU_TRAIL_LAST,
    INJ_DN_LEAD_FIRST,INJ_DN_LEAD_MIDDLE,INJ_DN_LEAD_LAST,
    INJ_DN_TRAIL_FIRST,INJ_DN_TRAIL_MIDDLE,INJ_DN_TRAIL_LAST,
    INJ_EPOCH,INJ_STAGE,INJ_MAGIC,INJ_FIRST_FAILURE,INJ_EXPECTED,INJ_DUPLICATE_POST,
    INJ_STICKY_REUSE,INJ_COUNT };
static const char *injection_names[INJ_COUNT]={"accepted","active-zero","active-negative","active-over",
    "total-low","total-high","rows-negative","rows-over","sum-low","sum-high","id-bad","id-negative","id-over",
    "prefix-first","prefix-middle","prefix-terminal","GU-count-low","DN-count-high","counts-swapped","counts-negative","counts-max",
    "GU-lead-first","GU-lead-middle","GU-lead-last","GU-trail-first","GU-trail-middle","GU-trail-last",
    "DN-lead-first","DN-lead-middle","DN-lead-last","DN-trail-first","DN-trail-middle","DN-trail-last",
    "post-epoch-stale","state-stage-stale","state-magic-stale","first-stage-failure","expected-count-incoherent",
    "duplicate-post-consumed","sticky-valid-reuse"};
typedef struct {
    int32_t raw[EXPERTS+2],ids[EXPERTS],prefix[EXPERTS+1];
    int32_t private_raw[EXPERTS+2],private_ids[EXPERTS],private_prefix[EXPERTS+1];
    int32_t native128[2],raw64[2],selected128[2],selected64[2],generated64[2];
    Bn64ValidationResult state,post,prepared_state,before_post;
    unsigned char guard[4][GUARD];uint32_t sticky;uint64_t epoch,post_epoch;
    int injection,histogram_rejected;
} Expected;
static void mutate_histogram(Expected *e) {
    switch(e->injection){
    case INJ_ACTIVE_ZERO:e->raw[512]=0;break;
    case INJ_ACTIVE_NEG:e->raw[512]=-1;break;
    case INJ_ACTIVE_OVER:e->raw[512]=513;break;
    case INJ_TOTAL_LOW:e->raw[513]=R-1;break;
    case INJ_TOTAL_HIGH:e->raw[513]=R+1;break;
    case INJ_ROWS_NEG:e->raw[0]=-1;break;
    case INJ_ROWS_OVER:e->raw[0]=R+1;break;
    case INJ_SUM_LOW:e->raw[511]--;break;
    case INJ_SUM_HIGH:e->raw[511]++;break;
    case INJ_ID_BAD:e->ids[0]=1;break;
    case INJ_ID_NEG:e->ids[0]=-1;break;
    case INJ_ID_OVER:e->ids[0]=512;break;
    case INJ_PREFIX_FIRST:e->prefix[0]=1;break;
    case INJ_PREFIX_MIDDLE:e->prefix[256]++;break;
    case INJ_PREFIX_TERMINAL:e->prefix[512]--;break;
    default:break;
    }
}
static void mutate_state(Bn64ValidationResult *state,int injection) {
    switch(injection){
    case INJ_STAGE:state->stage=BN64_STAGE_CONSUMED;break;
    case INJ_MAGIC:state->magic^=1;break;
    case INJ_FIRST_FAILURE:state->failures|=BN64_BAD_ID;break;
    case INJ_EXPECTED:state->expected_gu++;break;
    default:break;
    }
}
static int expected_candidate(Expected *e,uint64_t epoch,int injection,int s64,int s128,uint32_t sticky) {
    memset(e,0,sizeof(*e));e->epoch=e->post_epoch=epoch;e->injection=injection;e->sticky=sticky;
    memcpy(e->raw,host_raw,sizeof(e->raw));memcpy(e->ids,host_ids,sizeof(e->ids));memcpy(e->prefix,host_prefix,sizeof(e->prefix));
    memset(e->guard,0xa5,sizeof(e->guard));e->native128[0]=5*s128;e->native128[1]=10*s128;
    mutate_histogram(e);
    Bn64Prepare64Args prepare={e->raw,e->ids,e->prefix,e->native128,epoch,e->private_raw,e->private_ids,e->private_prefix,
        e->raw64,e->selected128,e->selected64,&e->state,&e->post,&e->sticky};
    bn64p_oracle_prepare(&prepare,1);e->prepared_state=e->state;e->histogram_rejected=e->state.failures!=0;
    if(!e->histogram_rejected){e->raw64[0]=5*s64;e->raw64[1]=10*s64;}
    memcpy(e->generated64,e->raw64,sizeof(e->raw64));
    switch(injection){
    case INJ_GU_LOW:e->raw64[0]--;break;
    case INJ_DN_HIGH:e->raw64[1]++;break;
    case INJ_COUNTS_SWAP:{int32_t swap=e->raw64[0];e->raw64[0]=e->raw64[1];e->raw64[1]=swap;break;}
    case INJ_COUNTS_NEG:e->raw64[0]=-1;break;
    case INJ_COUNTS_MAX:e->raw64[1]=INT32_MAX;break;
    case INJ_EPOCH:e->post_epoch++;break;
    default:break;
    }
    if(injection>=INJ_GU_LEAD_FIRST&&injection<=INJ_DN_TRAIL_LAST){
        int k=injection-INJ_GU_LEAD_FIRST,which=k/3;size_t offset=(k%3==0)?0:(k%3==1?GUARD/2:GUARD-1);
        e->guard[which][offset]=0x17;
    }
    mutate_state(&e->state,injection);e->before_post=e->state;
    Bn64PostSelectArgs post={&e->state,e->post_epoch,e->raw64,e->native128,
        e->guard[0],e->guard[1],e->guard[2],e->guard[3],e->selected128,e->selected64,&e->post,&e->sticky};
    bn64p_oracle_post(&post,1);
    if(injection==INJ_DUPLICATE_POST)bn64p_oracle_post(&post,1);
    if(injection!=INJ_NONE && !e->post.failures){fprintf(stderr,"injection unexpectedly accepted by oracle\n");return 0;}
    return 1;
}

static uint32_t observed_sticky;
typedef struct { uint64_t host_ns;float gpu_ms;uint64_t epoch;int stock_fallback;
    Bn64ValidationResult state,post;int32_t raw64[2],selected128[2],selected64[2];uint32_t sticky; } Observation;
static Bn64Prepare64Args prepare_arguments(uint64_t epoch,int candidate_view) {
    return (Bn64Prepare64Args){b[candidate_view?VIEW_RAW:RAW].p,b[candidate_view?VIEW_IDS:IDS].p,
        b[candidate_view?VIEW_PREFIX:PREFIX].p,b[COUNTS128].p,epoch,b[PRIVATE_RAW].p,b[PRIVATE_IDS].p,
        b[PRIVATE_PREFIX].p,b[COUNTS64].p,b[SELECT128].p,b[SELECT64].p,b[STATE].p,b[POST].p,b[STICKY].p};
}
static Bn64PostSelectArgs post_arguments(uint64_t epoch) {
    return (Bn64PostSelectArgs){b[STATE].p,epoch,b[COUNTS64].p,b[COUNTS128].p,
        b[GI64].base,(unsigned char*)b[GI64].p+b[GI64].bytes,
        b[DI64].base,(unsigned char*)b[DI64].p+b[DI64].bytes,
        b[SELECT128].p,b[SELECT64].p,b[POST].p,b[STICKY].p};
}
static int upload_rejected_view(const Expected *e) {
    /* Original128 just completed on untouched stock-safe originals. */
    return drain_owned("original128 before rejected candidate view") &&
        ok(copy_owned(b[VIEW_RAW].p,e->raw,sizeof(e->raw),1),"candidate-only raw view") &&
        ok(copy_owned(b[VIEW_IDS].p,e->ids,sizeof(e->ids),1),"candidate-only ID view") &&
        ok(copy_owned(b[VIEW_PREFIX].p,e->prefix,sizeof(e->prefix),1),"candidate-only prefix view");
}
static void *item_guard(int which) {
    int buffer=which<2?GI64:DI64;
    return (which&1)?(unsigned char*)b[buffer].p+b[buffer].bytes:b[buffer].base;
}
static int inject_post(const Expected *e) {
    int injection=e->injection;
    if(injection>=INJ_GU_LOW&&injection<=INJ_COUNTS_MAX){
        int32_t actual[2];
        if(!drain_owned("count-injection completion") ||
           !ok(copy_owned(actual,b[COUNTS64].p,8,2),"generated counts before injection") ||
           memcmp(actual,e->generated64,8))return 0;
        return ok(copy_owned(b[COUNTS64].p,e->raw64,8,1),"candidate-only count injection");
    }
    if(injection>=INJ_GU_LEAD_FIRST&&injection<=INJ_DN_TRAIL_LAST){
        int k=injection-INJ_GU_LEAD_FIRST,which=k/3;size_t offset=k%3==0?0:(k%3==1?GUARD/2:GUARD-1);
        unsigned char bad=0x17;
        return drain_owned("guard-injection completion") &&
            ok(copy_owned((unsigned char*)item_guard(which)+offset,&bad,1,1),"candidate-only guard injection");
    }
    if(injection>=INJ_STAGE&&injection<=INJ_EXPECTED){
        Bn64ValidationResult actual;
        if(!drain_owned("state-injection completion") ||
           !ok(copy_owned(&actual,b[STATE].p,sizeof(actual),2),"prepared state before injection") ||
           memcmp(&actual,&e->prepared_state,sizeof(actual)))return 0;
        mutate_state(&actual,injection);
        return ok(copy_owned(b[STATE].p,&actual,sizeof(actual),1),"candidate-only state injection");
    }
    return 1;
}
static int retire_candidate(const Expected *e,Observation *out) {
    /* Six actual D2H calls/92 bytes, performed after a successful final fence.
     * Every oracle/status/count/freshness check below belongs to host timing. */
    if(!ok(copy_owned(&out->state,b[STATE].p,32,2),"retirement state D2H") ||
       !ok(copy_owned(&out->post,b[POST].p,32,2),"retirement post D2H") ||
       !ok(copy_owned(&out->sticky,b[STICKY].p,4,2),"retirement sticky D2H") ||
       !ok(copy_owned(out->raw64,b[COUNTS64].p,8,2),"retirement raw64 D2H") ||
       !ok(copy_owned(out->selected128,b[SELECT128].p,8,2),"retirement selected128 D2H") ||
       !ok(copy_owned(out->selected64,b[SELECT64].p,8,2),"retirement selected64 D2H"))return 0;
    if(memcmp(&out->state,&e->state,32) || memcmp(&out->post,&e->post,32) ||
       out->sticky!=e->sticky || memcmp(out->raw64,e->raw64,8) ||
       memcmp(out->selected128,e->selected128,8) || memcmp(out->selected64,e->selected64,8)){
        fprintf(stderr,"retirement oracle mismatch: %s epoch%" PRIu64 "\n",injection_names[e->injection],e->epoch);return 0;
    }
    if(out->state.stage!=BN64_STAGE_CONSUMED || out->post.epoch!=e->post_epoch ||
       out->post.stage!=BN64_STAGE_POST_ITEMS || out->post.magic!=BN64_RESULT_MAGIC)return 0;
    const int rejected=out->post.failures!=0 || out->sticky!=0;
    const int32_t zero[2]={0,0};
    if(rejected){
        if(out->sticky!=1 || !out->post.failures || memcmp(out->selected128,e->native128,8) ||
           memcmp(out->selected64,zero,8))return 0;
    } else if(memcmp(out->selected128,zero,8) || out->selected64[0]!=(int32_t)(5*e->state.segments) ||
              out->selected64[1]!=(int32_t)(10*e->state.segments) || out->selected64[0]<=0)return 0;
    /* Diagnostic expected_gu/dn may remain nonzero during a stale-state reject.
     * Never use those fields alone to identify the active projection branch. */
    out->stock_fallback=rejected;observed_sticky=out->sticky;
    return 1;
}
static int run_operation(int arm,int injection,int s64,int s128,void *begin,void *end,Observation *out,Expected *expected) {
    uint64_t started=0,finished=0;if(epoch_counter==UINT64_MAX)return 0;
    memset(out,0,sizeof(*out));transaction_epoch=++epoch_counter;out->epoch=transaction_epoch;
    attempted_phase=0;transaction_retired=0;journal_count=recovery_count=0;
    if(arm==2 && !expected_candidate(expected,transaction_epoch,injection,s64,s128,observed_sticky))return 0;
    if(!raw_ns(&started)||!record_event(begin,"full-operation GPU begin"))return 0;
    if(arm==0){
        if(!submit(native_functions[0],"items128",TX_ITEMS,1,512,&original_items,56) ||
           !submit(native_functions[1],"GU128",TX_GU,5*CAP128,256,&original_gu,152) ||
           !submit(native_functions[2],"DN128",TX_DN,10*CAP128,256,&original_dn,152) ||
           !submit(native_functions[6],"fold",TX_FOLD,(20*N+7)/8,256,&original_fold,64))return 0;
    } else if(arm==1){
        int gu=0,dn=0;ItemArgs items={ptr(IDS),ptr(PREFIX),ptr(RAW),R,0,ptr(GI64),ptr(DI64),ptr(COUNTS64)};
        ProjectionArgs gu_args=projection(0,GI64,DI64,COUNTS64),dn_args=projection(1,GI64,DI64,COUNTS64);
        if(!legacy_histogram(transaction_epoch,&gu,&dn) ||
           !submit(native_functions[3],"items64",TX_ITEMS,1,512,&items,56) ||
           !legacy_post(transaction_epoch,gu,dn) ||
           !submit(native_functions[4],"GU64",TX_GU,5*CAP64,256,&gu_args,152) ||
           !submit(native_functions[5],"DN64",TX_DN,10*CAP64,256,&dn_args,152) ||
           !submit(native_functions[6],"fold",TX_FOLD,(20*N+7)/8,256,&original_fold,64))return 0;
    } else {
        int bad_view=injection>=INJ_ACTIVE_ZERO&&injection<=INJ_PREFIX_TERMINAL;
        Bn64Prepare64Args prepare=prepare_arguments(transaction_epoch,bad_view);
        Bn64PostSelectArgs post=post_arguments(expected->post_epoch);
        ItemArgs items64={ptr(PRIVATE_IDS),ptr(PRIVATE_PREFIX),ptr(PRIVATE_RAW),R,0,ptr(GI64),ptr(DI64),ptr(COUNTS64)};
        ProjectionArgs gu128=projection(0,GI128,DI128,SELECT128),gu64=projection(0,GI64,DI64,SELECT64);
        ProjectionArgs dn128=projection(1,GI128,DI128,SELECT128),dn64=projection(1,GI64,DI64,SELECT64);
        if(!submit(native_functions[0],"items128",TX_ITEMS,1,512,&original_items,56) ||
           (bad_view&&!upload_rejected_view(expected)) ||
           !submit(custom_functions[0],"prepare64",TX_ITEMS,1,256,&prepare,sizeof(prepare)) ||
           !submit(native_functions[3],"items64",TX_ITEMS,1,512,&items64,56) || !inject_post(expected) ||
           !submit(custom_functions[1],"post-select",TX_ITEMS,1,256,&post,sizeof(post)))return 0;
        if(injection==INJ_DUPLICATE_POST &&
           !submit(custom_functions[1],"duplicate-post-select",TX_ITEMS,1,256,&post,sizeof(post)))return 0;
        if(!submit(native_functions[1],"GU128-predicated",TX_GU,5*CAP128,256,&gu128,152) ||
           !submit(native_functions[4],"GU64-predicated",TX_GU,5*CAP64,256,&gu64,152) ||
           !submit(native_functions[2],"DN128-predicated",TX_DN,10*CAP128,256,&dn128,152) ||
           !submit(native_functions[5],"DN64-predicated",TX_DN,10*CAP64,256,&dn64,152) ||
           !submit(native_functions[6],"fold",TX_FOLD,(20*N+7)/8,256,&original_fold,64))return 0;
    }
    if(!record_event(end,"full-operation GPU end"))return 0;
    if(!drain_owned("final operation NULL-stream completion")){terminal_pending=1;return 0;}
    if(arm==2&&!retire_candidate(expected,out))return 0;
    if(!raw_ns(&finished)||finished<started)return 0;
    out->host_ns=(finished-started)/BATCH;
    if(!ok(EventElapsed(&out->gpu_ms,begin,end),"full-operation GPU event elapsed"))return 0;
    out->gpu_ms/=BATCH;
    if(interrupted)return 0;
    transaction_retired=1;return 1;
}
static int clear_outputs(int arm) {
    const int poison=arm==0?0xa5:(arm==1?0x5a:0x3c);
    if(!ok(set_owned(b[GU].p,poison,GU_BYTES),"common clear GU") ||
       !ok(set_owned(b[DN].p,poison,DN_BYTES),"common clear DN") ||
       !ok(set_owned(b[FINAL].p,poison,FINAL_BYTES),"common clear final"))return 0;
    const int items[]={GI128,DI128,GI64,DI64,COUNTS128,COUNTS64};
    for(size_t i=0;i<sizeof(items)/sizeof(items[0]);i++)if(!ok(set_owned(b[items[i]].p,0xcd,b[items[i]].bytes),"common item/count poison"))return 0;
    /* Selected pairs/state/post are deliberately not host-reset per transaction.
     * The first custom kernel owns their fresh initialization and post poison. */
    return drain_owned("common setup complete before timing");
}
static int candidate_inputs_match(const Expected *e) {
    const int buffers[]={PRIVATE_RAW,PRIVATE_IDS,PRIVATE_PREFIX};
    const void *host[]={e->private_raw,e->private_ids,e->private_prefix};
    for(int k=0;k<3;k++)if(!ok(copy_owned(scratch,b[buffers[k]].p,b[buffers[k]].bytes,2),"private-input correctness read") ||
       memcmp(scratch,host[k],b[buffers[k]].bytes))return 0;
    if(e->histogram_rejected){
        for(int k=0;k<2;k++){int buffer=k?DI64:GI64;
            if(!ok(copy_owned(scratch,b[buffer].p,b[buffer].bytes,2),"safe-empty item no-write read"))return 0;
            for(size_t j=0;j<b[buffer].bytes;j++)if(scratch[j]!=0xcd)return 0;
        }
    }
    return 1;
}
static int restore_injected_guard(int injection) {
    if(injection<INJ_GU_LEAD_FIRST||injection>INJ_DN_TRAIL_LAST)return 1;
    int k=injection-INJ_GU_LEAD_FIRST,which=k/3;size_t offset=k%3==0?0:(k%3==1?GUARD/2:GUARD-1);
    unsigned char value=0,good=0xa5;void *where=(unsigned char*)item_guard(which)+offset;
    if(!ok(copy_owned(&value,where,1,2),"intentionally corrupt guard retained") || value!=0x17)return 0;
    return ok(copy_owned(where,&good,1,1),"restore only intentionally injected guard byte");
}
static int compare_outputs(size_t mismatch[3],size_t nonfinite[3]) {
    const int live[]={GU,DN,FINAL},ref[]={REF_GU,REF_DN,REF_FINAL};
    for(int k=0;k<3;k++)if(!compare_half(live[k],ref[k],&mismatch[k],&nonfinite[k]) || mismatch[k] || nonfinite[k])return 0;
    return 1;
}
static int verify_operation(int arm,int s64,int s128,const Expected *e,size_t mismatch[3],size_t nonfinite[3]) {
    if(arm==0&&!check_items(128,s128,GI128,DI128,COUNTS128,1))return 0;
    if(arm==1&&!check_items(64,s64,GI64,DI64,COUNTS64,1))return 0;
    if(arm==2){
        if(!check_items(128,s128,GI128,DI128,COUNTS128,1) || !candidate_inputs_match(e))return 0;
        if(!e->histogram_rejected && !check_items(64,s64,GI64,DI64,COUNTS64,
           !(e->injection>=INJ_GU_LOW&&e->injection<=INJ_COUNTS_MAX)))return 0;
        if(!restore_injected_guard(e->injection))return 0;
    }
    return compare_outputs(mismatch,nonfinite) && guards() && drain_owned("verification reads complete before reuse");
}
static int new_sticky_generation(void) {
    /* Reset is a new owned allocation, after explicit predecessor retirement;
     * never a transaction-time zero upload into a still-owned sticky word. */
    if(!drain_owned("sticky generation predecessor retirement"))return 0;
    if(b[STICKY].base){
        if(!ok(Free(b[STICKY].base),"release prior owned sticky generation")){terminal_pending=1;return 0;}
        b[STICKY].base=b[STICKY].p=NULL;
    }
    if(!allocate(STICKY,"sticky rejection",4) || !ok(set_owned(b[STICKY].p,0,4),"initialize new sticky generation") ||
       !drain_owned("new sticky generation initialization"))return 0;
    sticky_generation++;observed_sticky=0;
    printf("{\"type\":\"sticky-generation\",\"generation\":%" PRIu64 ",\"reset_by_new_allocation\":true}\n",sticky_generation);
    return 1;
}

static void print_journal(void) {
    for(unsigned i=0;i<journal_count;i++)printf("{\"type\":\"attempt\",\"epoch\":%" PRIu64 ",\"index\":%u,\"name\":\"%s\",\"phase\":%d,\"grid\":%u,\"block\":%u,\"arg_bytes\":%zu,\"hip_status\":%d}\n",
        journal[i].epoch,i,journal[i].name,journal[i].phase,journal[i].grid,journal[i].block,journal[i].bytes,journal[i].error);
    for(unsigned i=0;i<recovery_count;i++)printf("{\"type\":\"replay-attempt\",\"epoch\":%" PRIu64 ",\"index\":%u,\"name\":\"%s\",\"phase\":%d,\"hip_status\":%d}\n",
        recovery_journal[i].epoch,i,recovery_journal[i].name,recovery_journal[i].phase,recovery_journal[i].error);
}
static void print_observation(const char *pattern,int triad,const char *order,int measured,int arm,const Observation *out) {
    printf("{\"type\":\"operation\",\"pattern\":\"%s\",\"triad\":%d,\"order\":\"%s\",\"measured\":%s,\"arm\":\"%c\",\"epoch\":%" PRIu64 ",\"host_ns\":%" PRIu64 ",\"gpu_ms\":%.9g,\"operations_per_arm\":1,\"native_launches\":%d,\"custom_launches\":%d,\"decision_waits\":%d,\"retirement_waits\":1,\"retirement_D2H_calls\":%d,\"retirement_D2H_bytes\":%d,\"stock_fallback\":%s,\"GU_words\":%zu,\"DN_words\":%zu,\"final_words\":%zu,\"bit_mismatches\":[0,0,0],\"nonfinite_words\":[0,0,0],\"guards_passed\":true,\"retired_and_verified\":true}\n",
        pattern,triad,order,measured?"true":"false",'A'+arm,out->epoch,out->host_ns,out->gpu_ms,
        arm==2?7:4,arm==2?2:0,arm==1?2:0,arm==2?6:0,arm==2?92:0,
        out->stock_fallback?"true":"false",GU_BYTES/2,DN_BYTES/2,FINAL_BYTES/2);
}
static int correctness_episode(int injection,int s64,int s128,void *begin,void *end,int fresh_generation) {
    Expected expected;Observation observed;size_t mismatch[3]={0},nonfinite[3]={0};
    if(fresh_generation&&!new_sticky_generation())return 0;
    if(!clear_outputs(2) || !run_operation(2,injection,s64,s128,begin,end,&observed,&expected) ||
       !verify_operation(2,s64,s128,&expected,mismatch,nonfinite))return 0;
    printf("{\"type\":\"correctness\",\"case\":\"%s\",\"measured\":false,\"epoch\":%" PRIu64 ",\"sticky_generation\":%" PRIu64 ",\"post_failures\":%u,\"sticky\":%u,\"stock_fallback\":%s,\"GU_words\":%zu,\"DN_words\":%zu,\"final_words\":%zu,\"every_word_equal\":true,\"guards_passed\":true,\"retired_and_verified\":true}\n",
        injection_names[injection],observed.epoch,sticky_generation,observed.post.failures,observed.sticky,
        observed.stock_fallback?"true":"false",GU_BYTES/2,DN_BYTES/2,FINAL_BYTES/2);
    fflush(stdout);return 1;
}

/* One actual cleanup function serves main and the bounded CPU control checks.
 * A failed fence prohibits every device teardown call, even another fence. */
static int dispose_owned(void *begin,void *end,void *custom_module,void *module) {
    if(terminal_pending)return 0;
    if(StreamSync && pending && !drain_owned("final cleanup retirement"))return 0;
    if(begin && !ok(EventDestroy(begin),"destroy retired begin event"))return 0;
    if(end && !ok(EventDestroy(end),"destroy retired end event"))return 0;
    if(custom_module && !ok(Unload(custom_module),"unload retired custom module"))return 0;
    if(module && !ok(Unload(module),"unload retired native module"))return 0;
    for(int i=0;i<BUFFER_COUNT;i++)if(b[i].base){
        if(!ok(Free(b[i].base),"free retired guarded allocation"))return 0;
        b[i].base=b[i].p=NULL;
    }
    return 1;
}

static int mock_calls,mock_fences,mock_teardowns,mock_failure_one,mock_failure_two,mock_bad_fence;
static int mock_launch(void *f,unsigned gx,unsigned gy,unsigned gz,unsigned bx,unsigned by,unsigned bz,
                       unsigned shared,void *stream,void **params,void **extra) {
    (void)f;(void)gx;(void)gy;(void)gz;(void)bx;(void)by;(void)bz;(void)shared;(void)stream;(void)params;(void)extra;
    int call=mock_calls++;return call==mock_failure_one||call==mock_failure_two?17:0;
}
static int mock_fence(void *stream) { (void)stream;return mock_fences++==mock_bad_fence?7:0; }
static int mock_dispose(void *owner) { (void)owner;mock_teardowns++;return 0; }
static void mock_reset(void) {
    memset(b,0,sizeof(b));memset(journal,0,sizeof(journal));memset(recovery_journal,0,sizeof(recovery_journal));
    pending=attempted_phase=transaction_retired=restoring=terminal_pending=0;interrupted=0;
    journal_count=recovery_count=0;transaction_epoch=1;
    mock_calls=mock_fences=mock_teardowns=0;mock_failure_one=mock_failure_two=mock_bad_fence=-1;
    Launch=mock_launch;StreamSync=mock_fence;Free=mock_dispose;Unload=mock_dispose;EventDestroy=mock_dispose;
    for(int i=0;i<7;i++)native_functions[i]=(void*)(uintptr_t)(i+1);
    original_items=(ItemArgs){0};original_gu=(ProjectionArgs){0};original_dn=(ProjectionArgs){0};original_fold=(FoldArgs){0};
}
static int mock_prefix(int failure_step) {
    static const int phases[]={TX_ITEMS,TX_ITEMS,TX_ITEMS,TX_ITEMS,TX_GU,TX_GU,TX_DN,TX_DN,TX_FOLD};
    static const size_t bytes[]={56,112,56,96,152,152,152,152,64};unsigned char args[152]={0};
    mock_failure_one=failure_step;
    for(int i=0;i<9;i++){
        int pass=submit((void*)(uintptr_t)(i+1),"mock-C-step",phases[i],1,256,args,bytes[i]);
        if(i==failure_step)return !pass && journal_count==(unsigned)i+1 && attempted_phase==phases[i] &&
            journal[i].error==17 && pending;
        if(!pass)return 0;
    }
    return 0;
}
static int control_only(void) {
    int cases=0;
    for(int step=0;step<9;step++){
        mock_reset();if(!mock_prefix(step))return 1;
        int phase=attempted_phase;
        if(!restore_attempted_prefix() || terminal_pending || pending || recovery_count!=(unsigned)phase ||
           mock_fences!=2 || mock_calls!=step+1+phase)return 1;
        for(unsigned i=0;i<recovery_count;i++)if(recovery_journal[i].phase!=(int)i+1 || recovery_journal[i].error)return 1;
        cases++;
    }
    mock_reset();if(!mock_prefix(5))return 1;mock_bad_fence=0;
    int calls=mock_calls;
    if(restore_attempted_prefix() || !terminal_pending || mock_calls!=calls || recovery_count ||
       dispose_owned((void*)1,(void*)2,(void*)3,(void*)4) || mock_teardowns || mock_fences!=1 ||
       drain_owned("must-not-refence") || mock_fences!=1)return 1;
    cases++;
    mock_reset();if(!mock_prefix(6))return 1;mock_bad_fence=1;
    if(restore_attempted_prefix() || !terminal_pending || recovery_count!=3 ||
       dispose_owned((void*)1,(void*)2,(void*)3,(void*)4) || mock_teardowns || mock_fences!=2)return 1;
    cases++;
    mock_reset();if(!mock_prefix(5))return 1;mock_failure_two=7;
    if(restore_attempted_prefix() || terminal_pending || pending || recovery_count!=2 || mock_fences!=2)return 1;
    /* Failed replay with fence0 is terminal-drained; ordinary owner disposal is
     * safe, but it never establishes restored output or permits another arm. */
    b[0].base=(void*)5;
    if(!dispose_owned((void*)1,(void*)2,(void*)3,(void*)4) || mock_teardowns!=5)return 1;
    cases++;
    mock_reset();interrupted=SIGINT;unsigned char args[56]={0};
    if(submit((void*)1,"interrupted-before-submit",TX_ITEMS,1,512,args,sizeof(args)) ||
       journal_count || attempted_phase || pending || mock_calls || !dispose_owned(NULL,NULL,NULL,NULL) || mock_fences)return 1;
    cases++;
    printf("{\"type\":\"control-only\",\"passed\":true,\"cases\":%d,\"actual_host_control_functions\":true,\"HIP_loaded\":false,\"hardware_executed\":false}\n",cases);
    return 0;
}

#ifndef BN64_COMPONENT_HOST_LIBRARY
int main(int argc,char **argv) {
    int rc=1,cleanup_failed=0;void *lib=NULL,*module=NULL,*custom_module=NULL,*begin=NULL,*end=NULL;
    int32_t *forward=NULL,*inverse=NULL;int (*GetDevice)(int*)=NULL,(*IsCapturing)(void*,int*)=NULL;
    static const char *native_symbols[]={
      "_ZN5q4moe13k_q4moe_itemsILi128EEEvPKiS2_S2_iPNS_4ItemES4_Pi",
      "_ZN5q4moe7k_q4moeILi1ELi0ELi128ENS_4TuneILi0ELi128EEELi1EEEvNS_4ArgsE",
      "_ZN5q4moe7k_q4moeILi1ELi2ELi128ENS_4TuneILi0ELi128EEELi2EEEvNS_4ArgsE",
      "_ZN5q4moe13k_q4moe_itemsILi64EEEvPKiS2_S2_iPNS_4ItemES4_Pi",
      "_ZN5q4moe7k_q4moeILi1ELi0ELi64ENS_4TuneILi0ELi128EEELi1EEEvNS_4ArgsE",
      "_ZN5q4moe7k_q4moeILi1ELi2ELi64ENS_4TuneILi0ELi128EEELi2EEEvNS_4ArgsE",
      "_ZN7halogen12_GLOBAL__N_115k_i4r_fold_rowsEPKtPKiiPKfPKDF16_S2_S6_Pt"};
    const char *names[]={"GU weight blob","DN weight blob","transformed BF16 input","P","I","active IDs","prefixes","raw hist/bookkeeping",
      "route weights","GU metadata0","GU metadata1","DN/fold metadata","fold residual","fold token scalar","original128 GU items","original128 DN items","original128 counts",
      "GU output","DN output","final output","retained GU reference","retained DN reference","retained final reference",
      "private64 GU items","private64 DN items","raw64 counts","selected128 counts","selected64 counts",
      "private raw","private IDs","private prefixes","first-stage state","post status","sticky rejection","candidate-only raw view","candidate-only ID view","candidate-only prefix view"};
    const size_t sizes[]={GU_BLOB,DN_BLOB,X_BYTES,R*4,R*4,EXPERTS*4,(EXPERTS+1)*4,(EXPERTS+2)*4,R*4,
      GU_META0_BYTES,GU_META1_BYTES,DN_META_BYTES,X_BYTES,N*4,5*CAP64*16,10*CAP64*16,8,
      GU_BYTES,DN_BYTES,FINAL_BYTES,GU_BYTES,DN_BYTES,FINAL_BYTES,5*CAP64*16,10*CAP64*16,8,8,8,
      (EXPERTS+2)*4,EXPERTS*4,(EXPERTS+1)*4,32,32,4,(EXPERTS+2)*4,EXPERTS*4,(EXPERTS+1)*4};
    _Static_assert(sizeof(sizes)/sizeof(sizes[0])==BUFFER_COUNT,"allocation manifest count");
    _Static_assert(sizeof(names)/sizeof(names[0])==BUFFER_COUNT,"allocation name count");
    if(argc==2&&!strcmp(argv[1],"--control-only"))return control_only();
    if(argc!=5){fprintf(stderr,"usage: %s NATIVE_CODE_OBJECT CUSTOM_CODE_OBJECT HIP_LIBRARY CUSTOM_SHA256 | --control-only\n",argv[0]);return 2;}
    struct sigaction action;memset(&action,0,sizeof(action));action.sa_handler=signal_stop;sigemptyset(&action.sa_mask);
    if(sigaction(SIGINT,&action,NULL)||sigaction(SIGTERM,&action,NULL))return 2;
    scratch=malloc(CHUNK);other=malloc(CHUNK);forward=malloc((size_t)R*4);inverse=malloc((size_t)R*4);
    if(!scratch||!other||!forward||!inverse)goto done;
    if(!pinned_module(argv[1])||!pinned_custom(argv[2],argv[4]))goto done;
    size_t payload=0;for(int i=0;i<BUFFER_COUNT;i++)payload+=sizes[i];
    if(payload+(size_t)BUFFER_COUNT*2*GUARD>(size_t)3*1024*1024*1024){fprintf(stderr,"GPU budget exceeded\n");goto done;}
    printf("{\"type\":\"preflight\",\"code_object_sha256\":\"18937428b544e8a5ef1dae31db97f36136e8cdeca90e6c49458ef831b822a039\",\"custom_sha256\":\"%s\",\"gpu_allocation_bytes\":%zu,\"guarded_allocations\":%d,\"host_staging_bytes\":%zu,\"measured_triads_per_pattern\":6,\"warmup_triads_per_pattern\":1,\"operations_per_arm\":1,\"kernarg_bytes\":[56,152,64,112,96],\"synthetic\":true,\"engine_requests\":0,\"NPU_executed\":false}\n",
        argv[4],payload+(size_t)BUFFER_COUNT*2*GUARD,BUFFER_COUNT,(size_t)2*CHUNK+2*R*4+R*4+sizeof(Expected)+sizeof(Observation));
    lib=dlopen(argv[3],RTLD_NOW|RTLD_LOCAL);if(!lib){fprintf(stderr,"dlopen HIP: %s\n",dlerror());goto done;}
    LOAD(Malloc,"Malloc");LOAD(Free,"Free");LOAD(Memcpy,"Memcpy");LOAD(Memset,"Memset");LOAD(ModuleLoad,"ModuleLoad");
    LOAD(GetFunction,"ModuleGetFunction");LOAD(Unload,"ModuleUnload");LOAD(Launch,"ModuleLaunchKernel");
    LOAD(StreamSync,"StreamSynchronize");LOAD(EventCreate,"EventCreateWithFlags");LOAD(EventRecord,"EventRecord");
    LOAD(EventElapsed,"EventElapsedTime");LOAD(EventDestroy,"EventDestroy");LOAD(GetDevice,"GetDevice");LOAD(IsCapturing,"StreamIsCapturing");
    {int device=-1,capture=-1;HIP(GetDevice(&device));HIP(IsCapturing(NULL,&capture));if(device!=0||capture!=0)goto done;}
    for(int i=0;i<BUFFER_COUNT;i++)if(i!=STICKY&&!allocate(i,names[i],sizes[i]))goto done;
    if(!new_sticky_generation())goto done;
    if(!fill_blob(WG,GU_CODE,0x714a367b) || !fill_blob(WD,DN_CODE,0x91359a31) ||
       !fill_half(X,0x45678,0) || !fill_half(RESIDUAL,0x95432,0) ||
       !fill_half(M0,0x1234,1) || !fill_half(M1,0x1235,1) || !fill_half(MD,0x1236,1) ||
       !fill_float(WEIGHTS,0.1f) || !fill_float(TOKEN,0.01f) || !drain_owned("fixture allocation/initialization complete"))goto done;
    pending=1;HIP(ModuleLoad(&module,argv[1]));pending=1;HIP(ModuleLoad(&custom_module,argv[2]));
    for(int i=0;i<7;i++)HIP(GetFunction(&native_functions[i],module,native_symbols[i]));
    HIP(GetFunction(&custom_functions[0],custom_module,"bn64_validate_histogram_prepare64"));
    HIP(GetFunction(&custom_functions[1],custom_module,"bn64_validate_post_select"));
    HIP(EventCreate(&begin,0));HIP(EventCreate(&end,0));stock_snapshots();
    const char *orders[]={"ABC","ABC","ACB","BAC","BCA","CAB","CBA"};
    for(int pattern=0;pattern<2;pattern++){
        int s64=0,s128=0,reference_valid=0;const char *pattern_name=pattern?"boundary_tails":"uniform512x160";
        if(!prepare_routes(pattern,forward,inverse,&s64,&s128) || !drain_owned("route upload complete"))goto done;
        for(int triad=0;triad<=MEASURED_TRIADS;triad++)for(int position=0;position<3;position++){
            int arm=orders[triad][position]-'A';Observation observation;Expected expected;size_t mismatch[3]={0},nonfinite[3]={0};
            if(interrupted || !clear_outputs(arm) || !run_operation(arm,INJ_NONE,s64,s128,begin,end,&observation,&expected))goto done;
            if(!reference_valid){
                if(arm!=0 || !capture() || !drain_owned("reference D2D capture completion"))goto done;
                reference_valid=1;
            }
            if(!verify_operation(arm,s64,s128,&expected,mismatch,nonfinite))goto done;
            print_observation(pattern_name,triad,orders[triad],triad!=0,arm,&observation);fflush(stdout);
        }
    }
    /* Finite focused rejection cases share stock-safe original uniform routing.
     * Each isolated episode owns a new sticky allocation; the final sequence
     * deliberately reuses one generation across success/reject/valid-fallback. */
    {
        int s64=0,s128=0;Expected expected;Observation observation;size_t mismatch[3]={0},nonfinite[3]={0};
        if(!prepare_routes(0,forward,inverse,&s64,&s128) || !drain_owned("correctness route setup") ||
           !clear_outputs(0) || !run_operation(0,INJ_NONE,s64,s128,begin,end,&observation,&expected) ||
           !capture() || !drain_owned("correctness reference capture") ||
           !verify_operation(0,s64,s128,&expected,mismatch,nonfinite))goto done;
        for(int injection=INJ_ACTIVE_ZERO;injection<INJ_STICKY_REUSE;injection++)
            if(!correctness_episode(injection,s64,s128,begin,end,1))goto done;
        if(!correctness_episode(INJ_NONE,s64,s128,begin,end,1) ||
           !correctness_episode(INJ_GU_LOW,s64,s128,begin,end,0) ||
           !correctness_episode(INJ_STICKY_REUSE,s64,s128,begin,end,0))goto done;
    }
    rc=0;
done:
    if(rc && StreamSync && !terminal_pending && !transaction_retired && attempted_phase)
        if(!restore_attempted_prefix())cleanup_failed=1;
    if(rc)print_journal();
    if(terminal_pending)goto process_owned;
    if(!dispose_owned(begin,end,custom_module,module)){cleanup_failed=1;goto process_owned;}
    if(lib)dlclose(lib);
    free(scratch);free(other);free(forward);free(inverse);
    if(cleanup_failed)rc=1;
    printf("{\"type\":\"cleanup\",\"passed\":%s,\"all_explicit_owners_released\":true,\"synthetic\":true,\"engine_requests\":0,\"NPU_executed\":false}\n",rc==0?"true":"false");
    return rc;
process_owned:
    /* No HIP call, output read, replay, free, module/event teardown or DSO close
     * occurs after a failed completion fence. Root closes this isolated process. */
    fprintf(stderr,"component failed: explicit teardown stopped; root-owned process closure required\n");
    printf("{\"type\":\"cleanup\",\"passed\":false,\"process_owned_cleanup\":true,\"terminal_pending\":%s,\"synthetic\":true,\"engine_requests\":0,\"NPU_executed\":false}\n",terminal_pending?"true":"false");
    fflush(stdout);fflush(stderr);_Exit(1);
}
#endif
