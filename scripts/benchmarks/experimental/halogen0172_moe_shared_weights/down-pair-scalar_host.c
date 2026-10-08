/* Standalone synthetic MoE down component; no engine hooks/model weights.
 * Native authentic module vs paired component, same finite generated input.
 * This is algorithm feasibility, not serving rates or real-route coverage. */
#define _POSIX_C_SOURCE 200809L
#include <dlfcn.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

enum { ROWS=2560, WIDTH=640, EXPERTS=32, TASKS=31, GUARD=64, BATCH=8, REPS=9 };
static int (*Malloc)(void**,size_t),(*Free)(void*),(*Memcpy)(void*,const void*,size_t,int);
static int (*ModuleLoad)(void**,const char*),(*GetFunction)(void**,void*,const char*),(*Unload)(void*);
static int (*Launch)(void*,unsigned,unsigned,unsigned,unsigned,unsigned,unsigned,unsigned,void*,void**,void**);
static int (*Sync)(void),(*EventCreate)(void**,unsigned),(*EventRecord)(void*,void*);
static int (*EventSync)(void*),(*EventElapsed)(float*,void*,void*),(*EventDestroy)(void*);
static uint32_t rng=0x714a367bu;
static uint32_t random32(void) { rng=rng*1664525u+1013904223u;return rng; }
static int ok(int x,const char* s) { if(x){fprintf(stderr,"%s: %d\n",s,x);return 0;}return 1; }
#define HIP(expr) do { if(!ok((expr),#expr)) goto done; } while(0)
#define LOAD(name,sym) do { *(void**)(&name)=dlsym(lib,"hip" sym); if(!name){fprintf(stderr,"missing hip%s\n",sym);goto done;} } while(0)
static int timed(void* f,unsigned grid,void** args,void* start,void* end,float* ms) {
    if(!ok(EventRecord(start,NULL),"event start"))return 0;
    for(int i=0;i<BATCH;i++)if(!ok(Launch(f,grid,1,1,256,1,1,0,NULL,args,NULL),"launch"))return 0;
    if(!ok(EventRecord(end,NULL),"event end") || !ok(EventSync(end),"event wait"))return 0;
    if(!ok(EventElapsed(ms,start,end),"event elapsed"))return 0;
    *ms/=BATCH;return 1;
}
int main(int argc,char** argv) {
    if(argc!=3)return 2;
    void *lib=NULL,*moda=NULL,*modb=NULL,*fa=NULL,*fb=NULL,*start=NULL,*end=NULL;
    void *dw=NULL,*dx=NULL,*di=NULL,*dp=NULL,*da=NULL,*db=NULL;
    const size_t code_bytes=(size_t)EXPERTS*ROWS*320;
    const size_t weight_bytes=code_bytes+(size_t)EXPERTS*ROWS*10;
    const size_t input_bytes=(size_t)TASKS*WIDTH*2,output_bytes=(size_t)TASKS*ROWS*4;
    unsigned char* w=malloc(weight_bytes);uint16_t* x=malloc(input_bytes);
    unsigned char* a=malloc(output_bytes+GUARD),*b=malloc(output_bytes+GUARD);
    int ids[TASKS],pairs[TASKS*2],rc=1;
    if(!w||!x||!a||!b)goto done;
    for(size_t i=0;i<code_bytes;i++)w[i]=(unsigned char)(random32()>>24);
    for(size_t i=0;i<(size_t)EXPERTS*ROWS*5;i++) {
        uint16_t v=(uint16_t)(0x1400+(random32()>>20));memcpy(w+code_bytes+2*i,&v,2);
    }
    for(size_t i=0;i<input_bytes/2;i++)x[i]=(uint16_t)(0x3000+(random32()>>20))|((random32()&1u)<<15);
    lib=dlopen("/usr/local/lib/python3.12/site-packages/_rocm_sdk_core/lib/libamdhip64.so.7",RTLD_NOW|RTLD_LOCAL);
    if(!lib){fprintf(stderr,"dlopen: %s\n",dlerror());goto done;}
    LOAD(Malloc,"Malloc");LOAD(Free,"Free");LOAD(Memcpy,"Memcpy");LOAD(ModuleLoad,"ModuleLoad");
    LOAD(GetFunction,"ModuleGetFunction");LOAD(Unload,"ModuleUnload");LOAD(Launch,"ModuleLaunchKernel");
    LOAD(Sync,"DeviceSynchronize");LOAD(EventCreate,"EventCreateWithFlags");LOAD(EventRecord,"EventRecord");
    LOAD(EventSync,"EventSynchronize");LOAD(EventElapsed,"EventElapsedTime");LOAD(EventDestroy,"EventDestroy");
    HIP(Malloc(&dw,weight_bytes));HIP(Malloc(&dx,input_bytes));HIP(Malloc(&di,sizeof(ids)));
    HIP(Malloc(&dp,sizeof(pairs)));HIP(Malloc(&da,output_bytes+GUARD));HIP(Malloc(&db,output_bytes+GUARD));
    HIP(Memcpy(dw,w,weight_bytes,1));HIP(Memcpy(dx,x,input_bytes,1));
    HIP(ModuleLoad(&moda,argv[1]));HIP(ModuleLoad(&modb,argv[2]));
    HIP(GetFunction(&fa,moda,"_ZN7halogen12_GLOBAL__N_110k_i4r_rowsILi640EEEvPKhliPKDF16_iPKiPf"));
    HIP(GetFunction(&fb,modb,"alloy0172_moe_down_pair_v1"));
    HIP(EventCreate(&start,0));HIP(EventCreate(&end,0));
    for(int pattern=0;pattern<3;pattern++) {
        int pair_count=0,used[TASKS]={0};
        memset(pairs,0xff,sizeof(pairs));
        for(int i=0;i<TASKS;i++)ids[i]=pattern==0?i:(pattern==1?(i<20?i/2:i):i/2);
        for(int i=0;i<TASKS;i++)if(!used[i]) {
            int other=-1;for(int j=i+1;j<TASKS;j++)if(!used[j]&&ids[j]==ids[i]){other=j;break;}
            pairs[2*pair_count]=i;pairs[2*pair_count+1]=other;pair_count++;
            used[i]=1;if(other>=0)used[other]=1;
        }
        HIP(Memcpy(di,ids,sizeof(ids),1));HIP(Memcpy(dp,pairs,sizeof(pairs),1));
        int64_t span=(int64_t)code_bytes;int rows=ROWS,one=1,tasks=TASKS;
        void* aa[]={&dw,&span,&rows,&dx,&one,&di,&da};
        void* bb[]={&dw,&span,&dx,&di,&dp,&db,&rows,&tasks};
        for(int rep=0;rep<=REPS;rep++) {
            memset(a,0xa5,output_bytes+GUARD);memset(b,0xa5,output_bytes+GUARD);
            HIP(Memcpy(da,a,output_bytes+GUARD,1));HIP(Memcpy(db,b,output_bytes+GUARD,1));
            float ams=0,bms=0;
            if(rep%2==0) {
                if(!timed(fa,TASKS*(ROWS/64),aa,start,end,&ams))goto done;
                if(!timed(fb,pair_count*(ROWS/64),bb,start,end,&bms))goto done;
            } else {
                if(!timed(fb,pair_count*(ROWS/64),bb,start,end,&bms))goto done;
                if(!timed(fa,TASKS*(ROWS/64),aa,start,end,&ams))goto done;
            }
            HIP(Memcpy(a,da,output_bytes+GUARD,2));HIP(Memcpy(b,db,output_bytes+GUARD,2));
            size_t mismatches=0;float max_abs=0;size_t first=0;
            for(size_t i=0;i<output_bytes/4;i++) {
                uint32_t av,bv;float af,bf;memcpy(&av,a+4*i,4);memcpy(&bv,b+4*i,4);
                memcpy(&af,&av,4);memcpy(&bf,&bv,4);
                if(av!=bv){if(!mismatches)first=i;mismatches++;}
                float d=fabsf(af-bf);if(d>max_abs)max_abs=d;
                if(!isfinite(af)||!isfinite(bf)) {fprintf(stderr,"nonfinite\n");goto done;}
            }
            int guards=0;for(size_t i=output_bytes;i<output_bytes+GUARD;i++)guards+=(a[i]!=0xa5)+(b[i]!=0xa5);
            printf("{\"type\":\"pair\",\"pattern\":%d,\"rep\":%d,\"measured\":%s,\"order\":\"%s\",\"tasks\":%d,\"paired_tasks\":%d,\"native_ms\":%.9g,\"candidate_ms\":%.9g,\"compared_rows\":%zu,\"bit_mismatches\":%zu,\"max_abs\":%.9g,\"guard_corrupt_bytes\":%d}\n",pattern,rep,rep?"true":"false",rep%2?"BA":"AB",TASKS,2*(TASKS-pair_count),ams,bms,output_bytes/4,mismatches,max_abs,guards);
            fflush(stdout);
            if(mismatches||guards){float af,bf;memcpy(&af,a+4*first,4);memcpy(&bf,b+4*first,4);fprintf(stderr,"first mismatch %zu: %.9g != %.9g\n",first,af,bf);goto done;}
        }
    }
    rc=0;
done:
    if(Sync&&!ok(Sync(),"cleanup sync"))rc=1;
    if(start&&!ok(EventDestroy(start),"destroy start"))rc=1;
    if(end&&!ok(EventDestroy(end),"destroy end"))rc=1;
    if(moda&&!ok(Unload(moda),"unload native"))rc=1;
    if(modb&&!ok(Unload(modb),"unload candidate"))rc=1;
    void* allocs[]={dw,dx,di,dp,da,db};for(int i=0;i<6;i++)if(allocs[i]&&!ok(Free(allocs[i]),"free"))rc=1;
    free(w);free(x);free(a);free(b);
    if(lib)dlclose(lib);
    printf("{\"type\":\"cleanup\",\"passed\":%s,\"synthetic\":true,\"engine_requests\":0,\"NPU_executed\":false}\n",rc==0?"true":"false");
    return rc;
}
