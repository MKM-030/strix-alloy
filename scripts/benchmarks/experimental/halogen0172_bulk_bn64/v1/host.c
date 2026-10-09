/* Source-only isolated synthetic native bulk MoE pair. No engine/model hooks.
 * Timing boundary: native items + GU + dense-BF16 DN split2 + native bulk fold.
 * CPU routing and identical pretransformed input exclude rotation/sorting for BOTH.
 * Build/run are root-owned follow-up actions; this file does not authorize them. */
#define _POSIX_C_SOURCE 200809L
#include <dlfcn.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

enum { N=8192, R=81920, EXPERTS=512, TOPK=10, WIDTH=2560, HIDDEN=640,
       GUARD=4096, CHUNK=4*1024*1024, DEFAULT_REPS=3, MAX_REPS=7 };
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
/* Final minimum metadata extents are verified in the accompanying bounds note. */
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
static int (*Sync)(void),(*EventCreate)(void**,unsigned),(*EventRecord)(void*,void*);
static int (*EventSync)(void*),(*EventElapsed)(float*,void*,void*),(*EventDestroy)(void*);
typedef struct { const char *name; void *base,*p; size_t bytes; } Buffer;
enum { WG,WD,X,P,I,IDS,PREFIX,RAW,WEIGHTS,M0,M1,MD,RESIDUAL,TOKEN,GI,DI,COUNTS,
       GU,DN,FINAL,REF_GU,REF_DN,REF_FINAL,BUFFER_COUNT };
static Buffer b[BUFFER_COUNT];
static unsigned char *scratch,*other;
static int route_counts[EXPERTS],route_prefix[EXPERTS];
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
    return ok(Memset(b[i].base,0xa5,bytes+2*GUARD),"initialize payload and guards");
}
/* Bounded host staging; no full weight or output duplicate on the host. */
static int fill_blob(int i,size_t packed,uint64_t seed) {
    for(size_t off=0;off<b[i].bytes;off+=CHUNK){size_t len=b[i].bytes-off;if(len>CHUNK)len=CHUNK;
        for(size_t k=0;k<len;k++) {size_t pos=off+k;
            if(pos<packed)scratch[k]=(unsigned char)(mix(seed+pos)>>24);
            else {uint16_t h=(uint16_t)(0x1000+(mix(seed+(pos-packed)/2)&0x3ff));
                scratch[k]=(unsigned char)(h>>(8*((pos-packed)&1)));}}
        if(!ok(Memcpy((unsigned char*)b[i].p+off,scratch,len,1),"initialize packed Q4/FP16 blob"))return 0;
    }return 1;
}
static int fill_half(int i,uint64_t seed,int kind) {
    for(size_t off=0;off<b[i].bytes;off+=CHUNK){size_t len=b[i].bytes-off;if(len>CHUNK)len=CHUNK;
        for(size_t k=0;k<len/2;k++){uint32_t h=mix(seed+off/2+k);uint16_t z;
            z=kind==0 ? (uint16_t)((0x3c80+(h&127))|((h>>16)&0x8000)) : (uint16_t)(0x3800+(h&255));
            memcpy(scratch+2*k,&z,2);}
        if(!ok(Memcpy((unsigned char*)b[i].p+off,scratch,len,1),"initialize BF16/FP16 operand"))return 0;
    }return 1;
}
static int fill_float(int i,float value) {
    for(size_t off=0;off<b[i].bytes;off+=CHUNK){size_t len=b[i].bytes-off;if(len>CHUNK)len=CHUNK;
        for(size_t k=0;k<len/4;k++)memcpy(scratch+4*k,&value,4);
        if(!ok(Memcpy((unsigned char*)b[i].p+off,scratch,len,1),"initialize FP32 operand"))return 0;
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
    if(total!=R||*s64>CAP64||*s128>CAP128){free(routes);return 0;}
    int cursor[EXPERTS],base=0;for(int e=0;e<EXPERTS;e++){
        route_counts[e]=target[e];route_prefix[e]=base;cursor[e]=base;base+=target[e];}
    for(int s=0;s<R;s++){int q=cursor[routes[s]]++;forward[q]=s;inverse[s]=q;}
    for(int s=0;s<R;s++)if(forward[inverse[s]]!=s){free(routes);return 0;}
    /* Stable expert sort: ascending expert, then original slot, identical for both BNs. */
    memset(scratch,0,EXPERTS*4);memcpy(scratch,ids,(size_t)active*4);
    int pass=ok(Memcpy(b[IDS].p,scratch,EXPERTS*4,1),"active expert IDs") &&
        ok(Memcpy(b[PREFIX].p,prefix,sizeof(prefix),1),"expert row prefixes") &&
        ok(Memcpy(b[RAW].p,raw,sizeof(raw),1),"histogram/bookkeeping") &&
        ok(Memcpy(b[P].p,forward,(size_t)R*4,1),"forward permutation") &&
        ok(Memcpy(b[I].p,inverse,(size_t)R*4,1),"inverse permutation");
    printf("{\"type\":\"routing\",\"pattern\":\"%s\",\"N\":%d,\"R\":%d,\"active_experts\":%d,\"segments128\":%d,\"segments64\":%d,\"ten_distinct_experts_per_token\":true,\"sorting_in_timing\":false,\"rotation_in_timing\":false}\n",
        pattern?"boundary_tails":"uniform512x160",N,R,active,*s128,*s64);
    free(routes);return pass;
}

static int guards(void) {
    for(int i=0;i<BUFFER_COUNT;i++){if(!b[i].base)continue;
        if(!ok(Memcpy(scratch,b[i].base,GUARD,2),"prefix guard read") ||
            !ok(Memcpy(other,(unsigned char*)b[i].p+b[i].bytes,GUARD,2),"suffix guard read"))return 0;
        for(size_t k=0;k<GUARD;k++)if(scratch[k]!=0xa5||other[k]!=0xa5){
            fprintf(stderr,"guard changed: %s byte %zu\n",b[i].name,k);return 0;}}
    return 1;
}
static int compare_half(int live,int reference,size_t *mismatch,size_t *nonfinite) {
    *mismatch=*nonfinite=0;size_t first=SIZE_MAX;uint16_t av0=0,bv0=0;
    for(size_t off=0;off<b[live].bytes;off+=CHUNK){size_t len=b[live].bytes-off;if(len>CHUNK)len=CHUNK;
        if(!ok(Memcpy(scratch,(unsigned char*)b[live].p+off,len,2),"live output chunk") ||
            !ok(Memcpy(other,(unsigned char*)b[reference].p+off,len,2),"reference output chunk"))return 0;
        for(size_t k=0;k<len;k+=2){uint16_t av,bv;memcpy(&av,scratch+k,2);memcpy(&bv,other+k,2);
            if(av!=bv){if(first==SIZE_MAX){first=(off+k)/2;av0=av;bv0=bv;}(*mismatch)++;}
            *nonfinite+=((av&0x7f80)==0x7f80)+((bv&0x7f80)==0x7f80);}}
    if(*mismatch)fprintf(stderr,"%s first mismatch word %zu: 0x%04x vs 0x%04x\n",b[live].name,first,av0,bv0);
    return 1;
}
static int capture(void) {
    return ok(Memcpy(b[REF_GU].p,b[GU].p,GU_BYTES,3),"retain full GU") &&
        ok(Memcpy(b[REF_DN].p,b[DN].p,DN_BYTES,3),"retain full DN") &&
        ok(Memcpy(b[REF_FINAL].p,b[FINAL].p,FINAL_BYTES,3),"retain full final");
}
static int check_items(int bn,int segments) {
    int counts[2];if(!ok(Memcpy(counts,b[COUNTS].p,8,2),"native item counts"))return 0;
    if(counts[0]!=5*segments||counts[1]!=10*segments){fprintf(stderr,"native count mismatch BN%d\n",bn);return 0;}
    for(int dn=0;dn<2;dn++){int n=counts[dn],tiles=dn?10:5,index=dn?DI:GI;
        if(!ok(Memcpy(scratch,b[index].p,(size_t)n*sizeof(Item),2),"item records"))return 0;
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
    return ok(Launch(f,grid,1,1,block,1,1,0,NULL,NULL,extra),"native packed-kernarg launch");
}
static ProjectionArgs projection(int dn) {
    ProjectionArgs a;memset(&a,0,sizeof(a));a.weight=ptr(dn?WD:WG);
    a.scale_offset=dn?DN_CODE:GU_CODE;a.scale_stride=dn?10:40;
    for(int j=0;j<16;j++)a.codebook[j]=(float)(j-8);
    a.metadata0=ptr(dn?MD:M0);a.metadata1=dn?0:ptr(M1);a.input=ptr(dn?GU:X);
    a.permutation=dn?0:ptr(P);a.items=ptr(dn?DI:GI);a.count=ptr(COUNTS)+(dn?4:0);
    a.output=ptr(dn?DN:GU);return a;
}
static int timed_operation(void **functions,int bn,void *begin,void *end,float *ms) {
    int v=bn==128?0:1,capacity=bn==128?CAP128:CAP64;
    ItemArgs ia={ptr(IDS),ptr(PREFIX),ptr(RAW),R,0,ptr(GI),ptr(DI),ptr(COUNTS)};
    ProjectionArgs gu=projection(0),dn=projection(1);
    FoldArgs fold={ptr(DN),ptr(I),N,0,ptr(WEIGHTS),ptr(MD),ptr(RESIDUAL),ptr(TOKEN),ptr(FINAL)};
    if(!ok(EventRecord(begin,NULL),"operation begin"))return 0;
    if(!launch(functions[3*v],1,512,&ia,sizeof(ia)) ||
       !launch(functions[3*v+1],5*capacity,256,&gu,sizeof(gu)) ||
       !launch(functions[3*v+2],10*capacity,256,&dn,sizeof(dn)) ||
       !launch(functions[6],(20*N+7)/8,256,&fold,sizeof(fold)))return 0;
    return ok(EventRecord(end,NULL),"operation end") && ok(EventSync(end),"operation wait") &&
        ok(EventElapsed(ms,begin,end),"full-operation GPU event elapsed");
}
static int clear_outputs(int bn) {
    const int poison=bn==128?0xa5:0x5a;
    return ok(Memset(b[GU].p,poison,GU_BYTES),"clear GU") && ok(Memset(b[DN].p,poison,DN_BYTES),"clear DN") &&
        ok(Memset(b[FINAL].p,poison,FINAL_BYTES),"clear final") && ok(Memset(b[COUNTS].p,0xcd,8),"clear counts") &&
        ok(Memset(b[GI].p,0xcd,b[GI].bytes),"clear GU items") && ok(Memset(b[DI].p,0xcd,b[DI].bytes),"clear DN items");
}
int main(int argc,char **argv) {
    int rc=1,reps=DEFAULT_REPS;void *lib=NULL,*module=NULL,*begin=NULL,*end=NULL,*functions[7]={0};
    int32_t *forward=NULL,*inverse=NULL;int reference_valid=0;
    static const char *symbols[]={
      "_ZN5q4moe13k_q4moe_itemsILi128EEEvPKiS2_S2_iPNS_4ItemES4_Pi",
      "_ZN5q4moe7k_q4moeILi1ELi0ELi128ENS_4TuneILi0ELi128EEELi1EEEvNS_4ArgsE",
      "_ZN5q4moe7k_q4moeILi1ELi2ELi128ENS_4TuneILi0ELi128EEELi2EEEvNS_4ArgsE",
      "_ZN5q4moe13k_q4moe_itemsILi64EEEvPKiS2_S2_iPNS_4ItemES4_Pi",
      "_ZN5q4moe7k_q4moeILi1ELi0ELi64ENS_4TuneILi0ELi128EEELi1EEEvNS_4ArgsE",
      "_ZN5q4moe7k_q4moeILi1ELi2ELi64ENS_4TuneILi0ELi128EEELi2EEEvNS_4ArgsE",
      "_ZN7halogen12_GLOBAL__N_115k_i4r_fold_rowsEPKtPKiiPKfPKDF16_S2_S6_Pt"};
    const char *names[]={"GU weight blob","DN weight blob","transformed BF16 input","P","I","active IDs","prefixes","raw hist/bookkeeping",
      "route weights","GU metadata0","GU metadata1","DN/fold metadata","fold residual","fold token scalar","GU items","DN items","counts",
      "GU output","DN output","final output","retained GU reference","retained DN reference","retained final reference"};
    const size_t sizes[]={GU_BLOB,DN_BLOB,X_BYTES,R*4,R*4,EXPERTS*4,(EXPERTS+1)*4,(EXPERTS+2)*4,R*4,
      GU_META0_BYTES,GU_META1_BYTES,DN_META_BYTES,X_BYTES,N*4,5*CAP64*16,10*CAP64*16,8,
      GU_BYTES,DN_BYTES,FINAL_BYTES,GU_BYTES,DN_BYTES,FINAL_BYTES};
    if(argc<3||argc>4){fprintf(stderr,"usage: %s PINNED_CODE_OBJECT HIP_LIBRARY [reps1..7]\n",argv[0]);return 2;}
    if(argc==4){char *tail=NULL;long parsed=strtol(argv[3],&tail,10);
        if(!tail||*tail||parsed<1||parsed>MAX_REPS)return 2;
        reps=(int)parsed;
    }
    scratch=malloc(CHUNK);other=malloc(CHUNK);forward=malloc((size_t)R*4);inverse=malloc((size_t)R*4);
    if(!scratch||!other||!forward||!inverse)goto done;
    if(!pinned_module(argv[1]))goto done;
    size_t payload=0;for(int i=0;i<BUFFER_COUNT;i++)payload+=sizes[i];
    if(payload+(size_t)BUFFER_COUNT*2*GUARD>(size_t)3*1024*1024*1024){fprintf(stderr,"GPU budget exceeded\n");goto done;}
    printf("{\"type\":\"preflight\",\"code_object_sha256\":\"18937428b544e8a5ef1dae31db97f36136e8cdeca90e6c49458ef831b822a039\",\"gpu_allocation_bytes\":%zu,\"host_staging_bytes\":%d,\"reps\":%d,\"kernarg_bytes\":[56,152,64],\"exact_bit_contract\":true}\n",
        payload+(size_t)BUFFER_COUNT*2*GUARD,2*CHUNK+2*R*4,reps);
    lib=dlopen(argv[2],RTLD_NOW|RTLD_LOCAL);if(!lib){fprintf(stderr,"dlopen HIP: %s\n",dlerror());goto done;}
    LOAD(Malloc,"Malloc");LOAD(Free,"Free");LOAD(Memcpy,"Memcpy");LOAD(Memset,"Memset");LOAD(ModuleLoad,"ModuleLoad");
    LOAD(GetFunction,"ModuleGetFunction");LOAD(Unload,"ModuleUnload");LOAD(Launch,"ModuleLaunchKernel");
    LOAD(Sync,"DeviceSynchronize");LOAD(EventCreate,"EventCreateWithFlags");LOAD(EventRecord,"EventRecord");
    LOAD(EventSync,"EventSynchronize");LOAD(EventElapsed,"EventElapsedTime");LOAD(EventDestroy,"EventDestroy");
    for(int i=0;i<BUFFER_COUNT;i++)if(!allocate(i,names[i],sizes[i]))goto done;
    if(!fill_blob(WG,GU_CODE,0x714a367b) || !fill_blob(WD,DN_CODE,0x91359a31) ||
       !fill_half(X,0x45678,0) || !fill_half(RESIDUAL,0x95432,0) ||
       !fill_half(M0,0x1234,1) || !fill_half(M1,0x1235,1) || !fill_half(MD,0x1236,1) ||
       !fill_float(WEIGHTS,0.1f) || !fill_float(TOKEN,0.01f))goto done;
    HIP(ModuleLoad(&module,argv[1]));
    for(int i=0;i<7;i++)HIP(GetFunction(&functions[i],module,symbols[i]));
    HIP(EventCreate(&begin,0));HIP(EventCreate(&end,0));
    for(int pattern=0;pattern<2;pattern++){int s64=0,s128=0;
        if(!prepare_routes(pattern,forward,inverse,&s64,&s128))goto done;
        reference_valid=0;
        for(int rep=0;rep<=reps;rep++){float times[2]={0};size_t mismatches[3]={0},nonfinite[3]={0};
            int first=rep%2?64:128; /* rep0 is the one excluded paired warmup. */
            for(int pass=0;pass<2;pass++){int bn=pass?(first==128?64:128):first;
                if(!clear_outputs(bn) || !timed_operation(functions,bn,begin,end,&times[bn==128?0:1]) ||
                   !check_items(bn,bn==128?s128:s64) || !guards())goto done;
                if(bn==128 && !reference_valid){if(!capture())goto done;reference_valid=1;}
                else {int live[]={GU,DN,FINAL},ref[]={REF_GU,REF_DN,REF_FINAL};
                    for(int k=0;k<3;k++){size_t mm=0,nf=0;if(!compare_half(live[k],ref[k],&mm,&nf))goto done;
                        mismatches[k]+=mm;nonfinite[k]+=nf;}
                    if(bn==128 && !capture())goto done;
                }
            }
            printf("{\"type\":\"pair\",\"pattern\":\"%s\",\"rep\":%d,\"measured\":%s,\"order\":\"%s\",\"native128_ms\":%.9g,\"native64_ms\":%.9g,\"GU_words\":%zu,\"DN_words\":%zu,\"final_words\":%zu,\"bit_mismatches\":[%zu,%zu,%zu],\"nonfinite_words\":[%zu,%zu,%zu],\"guards_passed\":true}\n",
              pattern?"boundary_tails":"uniform512x160",rep,rep?"true":"false",first==128?"128_64":"64_128",times[0],times[1],
              GU_BYTES/2,DN_BYTES/2,FINAL_BYTES/2,mismatches[0],mismatches[1],mismatches[2],nonfinite[0],nonfinite[1],nonfinite[2]);
            fflush(stdout);
            for(int k=0;k<3;k++)if(mismatches[k]||nonfinite[k])goto done;
        }
    }
    rc=0;
done:
    if(Sync&&!ok(Sync(),"cleanup sync"))rc=1;
    if(begin&&!ok(EventDestroy(begin),"destroy begin"))rc=1;
    if(end&&!ok(EventDestroy(end),"destroy end"))rc=1;
    if(module&&!ok(Unload(module),"unload module"))rc=1;
    for(int i=0;i<BUFFER_COUNT;i++)if(b[i].base&&!ok(Free(b[i].base),"free guarded allocation"))rc=1;
    free(scratch);free(other);free(forward);free(inverse);if(lib)dlclose(lib);
    printf("{\"type\":\"cleanup\",\"passed\":%s,\"synthetic\":true,\"engine_requests\":0,\"NPU_executed\":false}\n",rc==0?"true":"false");return rc;
}
