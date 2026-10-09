/* Root-owned whole-real-FL component. Reads a sealed private capture, runs the
 * byte-identical native device object and owner512, and requires every BF16 bit.
 * No synthetic generation, model/API call, launch hook or serving mutation. */
#define _POSIX_C_SOURCE 200809L
#ifdef ALLOY_FREESTANDING_LINUX
#include "linux_abi.h"
#else
#include <dlfcn.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#endif

enum { N=3,TASKS=30,ROWS=2560,WIDTH=640,COUNT=60,GUARD=64,BATCH=8,REPS=9 };
typedef struct {char magic[8];uint32_t version,tokens,experts,complete;int64_t scale_bytes;} Header;
_Static_assert(sizeof(Header)==32,"capture ABI");
typedef struct { void* base;void* data;size_t bytes; } Buffer;
static int (*Allocate)(void**,size_t),(*Release)(void*),(*Copy)(void*,const void*,size_t,int),(*Set)(void*,int,size_t);
static int (*ModuleLoad)(void**,const char*),(*GetFunction)(void**,void*,const char*),(*Unload)(void*);
static int (*Launch)(void*,unsigned,unsigned,unsigned,unsigned,unsigned,unsigned,unsigned,void*,void**,void**);
static int (*Sync)(void),(*EventCreate)(void**,unsigned),(*EventRecord)(void*,void*);
static int (*EventSync)(void*),(*EventElapsed)(float*,void*,void*),(*EventDestroy)(void*);
static int ok(int x,const char* s){if(x){fprintf(stderr,"%s: %d\n",s,x);return 0;}return 1;}
#define HIP(expr) do{if(!ok((expr),#expr))goto done;}while(0)
#define LOAD(fn,sym) do{*(void**)(&fn)=dlsym(lib,"hip" sym);if(!fn){fprintf(stderr,"missing hip%s\n",sym);goto done;}}while(0)
static int load_payload(FILE* file,void* buffer,size_t size){return fread(buffer,1,size,file)==size;}
static int allocate(Buffer* b,size_t bytes){b->bytes=bytes;
 if(!ok(Allocate(&b->base,bytes+2*GUARD),"allocate guarded"))return 0;b->data=(unsigned char*)b->base+GUARD;
 return ok(Set(b->base,0xa5,bytes+2*GUARD),"initialize guarded");}
static int guard(Buffer* b){unsigned char a[GUARD],z[GUARD];
 if(!ok(Copy(a,b->base,GUARD,2),"prefix guard")||!ok(Copy(z,(unsigned char*)b->data+b->bytes,GUARD,2),"suffix guard"))return 0;
 for(unsigned i=0;i<GUARD;++i)if(a[i]!=0xa5||z[i]!=0xa5)return 0;return 1;}
static int counters_zero(Buffer* b){unsigned counters[COUNT];
 if(!ok(Copy(counters,b->data,sizeof(counters),2),"counter state"))return 0;
 for(unsigned i=0;i<COUNT;++i)if(counters[i])return 0;return guard(b);}
static int timed(void* fn,unsigned grid,unsigned block,void** args,void* start,void* end,float* ms){
 if(!ok(EventRecord(start,NULL),"event start"))return 0;
 for(unsigned i=0;i<BATCH;++i)if(!ok(Launch(fn,grid,1,1,block,1,1,0,NULL,args,NULL),"component launch"))return 0;
 if(!ok(EventRecord(end,NULL),"event end")||!ok(EventSync(end),"event wait")||!ok(EventElapsed(ms,start,end),"event elapsed"))return 0;
 *ms/=BATCH;return 1;}
static size_t difference(const uint16_t* x,const uint16_t* y,size_t count){
 size_t n=0;for(size_t i=0;i<count;++i)n+=(x[i]!=y[i]);return n;}
__attribute__((visibility("default")))
int main(int argc,char** argv){
 if(argc!=4){fprintf(stderr,"usage: replay native.hsaco owner512.hsaco capture.flop\n");return 2;}
 Header header;FILE* file=NULL;void* lib=NULL,*native=NULL,*candidate=NULL,*nf=NULL,*cf=NULL,*start=NULL,*end=NULL;
 unsigned char* weights=NULL;uint16_t input[TASKS*WIDTH],metadata[ROWS],residual[N*ROWS],gold[N*ROWS],a[N*ROWS],b[N*ROWS];
 int ids[TASKS],map[TASKS],selected[TASKS];unsigned before[COUNT],after[COUNT];float routes[TASKS],scalar[N];
 Buffer w={0},x={0},i={0},r={0},m={0},z={0},s={0},p={0},oa={0},ob={0},sa={0},sb={0},ca={0},cb={0};int rc=1;
 file=fopen(argv[3],"rb");if(!file||!load_payload(file,&header,sizeof(header)))goto done;
 if(memcmp(header.magic,"H0173FL1",8)||header.version!=1||header.tokens!=N||header.complete!=1||
    header.experts<1||header.experts>TASKS||header.scale_bytes!=(int64_t)header.experts*ROWS*320)goto done;
 size_t weight_bytes=(size_t)header.experts*ROWS*330;
 weights=malloc(weight_bytes);if(!weights)goto done;
 if(!load_payload(file,weights,weight_bytes)||!load_payload(file,input,sizeof(input))||
    !load_payload(file,ids,sizeof(ids))||!load_payload(file,routes,sizeof(routes))||
    !load_payload(file,metadata,sizeof(metadata))||!load_payload(file,residual,sizeof(residual))||
    !load_payload(file,scalar,sizeof(scalar))||!load_payload(file,map,sizeof(map))||
    !load_payload(file,before,sizeof(before))||!load_payload(file,selected,header.experts*sizeof(int))||
    !load_payload(file,after,sizeof(after))||!load_payload(file,gold,sizeof(gold))||fgetc(file)!=EOF)goto done;
 fclose(file);file=NULL;
 int seen[TASKS]={0};for(unsigned j=0;j<TASKS;++j){
  if(ids[j]<0||ids[j]>=(int)header.experts||map[j]<0||map[j]>=TASKS||seen[map[j]]++)goto done;}
 for(unsigned j=0;j<header.experts;++j){if(selected[j]<0||selected[j]>=512)goto done;
  for(unsigned k=0;k<j;++k)if(selected[j]==selected[k])goto done;}
 for(unsigned j=0;j<COUNT;++j)if(before[j]||after[j])goto done;
 // No HIP call occurs until the complete captured operation is parsed above.
 lib=dlopen("/usr/local/lib/python3.12/site-packages/_rocm_sdk_core/lib/libamdhip64.so.7",RTLD_NOW|RTLD_LOCAL);
 if(!lib){fprintf(stderr,"dlopen: %s\n",dlerror());goto done;}
 LOAD(Allocate,"Malloc");LOAD(Release,"Free");LOAD(Copy,"Memcpy");LOAD(Set,"Memset");
 LOAD(ModuleLoad,"ModuleLoad");LOAD(GetFunction,"ModuleGetFunction");LOAD(Unload,"ModuleUnload");
 LOAD(Launch,"ModuleLaunchKernel");LOAD(Sync,"DeviceSynchronize");LOAD(EventCreate,"EventCreateWithFlags");
 LOAD(EventRecord,"EventRecord");LOAD(EventSync,"EventSynchronize");LOAD(EventElapsed,"EventElapsedTime");LOAD(EventDestroy,"EventDestroy");
#define BUFFER(name,bytes) do{if(!allocate(&name,bytes))goto done;}while(0)
 BUFFER(w,weight_bytes);BUFFER(x,sizeof(input));BUFFER(i,sizeof(ids));BUFFER(r,sizeof(routes));BUFFER(m,sizeof(metadata));
 BUFFER(z,sizeof(residual));BUFFER(s,sizeof(scalar));BUFFER(p,sizeof(map));BUFFER(oa,sizeof(gold));BUFFER(ob,sizeof(gold));
 BUFFER(sa,(size_t)TASKS*ROWS*4);BUFFER(sb,(size_t)TASKS*ROWS*4);BUFFER(ca,sizeof(before));BUFFER(cb,sizeof(before));
#undef BUFFER
 HIP(Copy(w.data,weights,weight_bytes,1));HIP(Copy(x.data,input,sizeof(input),1));HIP(Copy(i.data,ids,sizeof(ids),1));
 HIP(Copy(r.data,routes,sizeof(routes),1));HIP(Copy(m.data,metadata,sizeof(metadata),1));HIP(Copy(z.data,residual,sizeof(residual),1));
 HIP(Copy(s.data,scalar,sizeof(scalar),1));HIP(Copy(p.data,map,sizeof(map),1));HIP(Copy(ca.data,before,sizeof(before),1));HIP(Copy(cb.data,before,sizeof(before),1));
 HIP(ModuleLoad(&native,argv[1]));HIP(ModuleLoad(&candidate,argv[2]));
 HIP(GetFunction(&nf,native,"_ZN7halogen12_GLOBAL__N_115k_i4r_rows_fl_oEPKhlPKDF16_PKiPfPKfS4_PKtS9_PtPjS6_"));
 HIP(GetFunction(&cf,candidate,"alloy0173_moe_fl_owner512_v1"));HIP(EventCreate(&start,0));HIP(EventCreate(&end,0));
 void* aa[]={&w.data,&header.scale_bytes,&x.data,&i.data,&sa.data,&r.data,&m.data,&z.data,&s.data,&oa.data,&ca.data,&p.data};
 void* bb[]={&w.data,&header.scale_bytes,&x.data,&i.data,&sb.data,&r.data,&m.data,&z.data,&s.data,&ob.data,&cb.data,&p.data};
 // Authentic native replay must first reproduce the actual stock engine output.
 HIP(Launch(nf,400*N,1,1,256,1,1,0,NULL,aa,NULL));HIP(Sync());HIP(Copy(a,oa.data,sizeof(a),2));
 size_t native_capture_diff=difference(a,gold,N*ROWS);
 printf("{\"type\":\"capture_reference\",\"tokens\":%d,\"experts\":%u,\"compared_bf16\":%d,\"bit_mismatches\":%zu,\"counter_zero\":%s}\n",
  N,header.experts,N*ROWS,native_capture_diff,counters_zero(&ca)?"true":"false");fflush(stdout);
 if(native_capture_diff||!counters_zero(&ca)||!guard(&sa)||!guard(&oa))goto done;
 HIP(Launch(cf,20*N,1,1,512,1,1,0,NULL,bb,NULL));HIP(Sync());HIP(Copy(b,ob.data,sizeof(b),2));
 size_t candidate_diff=difference(b,gold,N*ROWS);
 printf("{\"type\":\"candidate_reference\",\"compared_bf16\":%d,\"bit_mismatches\":%zu,\"guards\":%s,\"counter_zero\":%s}\n",
  N*ROWS,candidate_diff,(guard(&sb)&&guard(&ob))?"true":"false",counters_zero(&cb)?"true":"false");fflush(stdout);
 if(candidate_diff||!guard(&sb)||!guard(&ob)||!counters_zero(&cb))goto done;
 for(unsigned rep=0;rep<=REPS;++rep){
  float ams=0,bms=0;
  if(rep&1){if(!timed(cf,20*N,512,bb,start,end,&bms)||!timed(nf,400*N,256,aa,start,end,&ams))goto done;}
  else{if(!timed(nf,400*N,256,aa,start,end,&ams)||!timed(cf,20*N,512,bb,start,end,&bms))goto done;}
  HIP(Copy(a,oa.data,sizeof(a),2));HIP(Copy(b,ob.data,sizeof(b),2));
  size_t ad=difference(a,gold,N*ROWS),bd=difference(b,gold,N*ROWS);
  int guards=guard(&sa)&&guard(&sb)&&guard(&oa)&&guard(&ob)&&counters_zero(&ca)&&counters_zero(&cb);
  printf("{\"type\":\"pair\",\"rep\":%u,\"measured\":%s,\"order\":\"%s\",\"batch\":%d,\"native_ms\":%.9g,\"candidate_ms\":%.9g,\"native_bit_mismatches\":%zu,\"candidate_bit_mismatches\":%zu,\"guards_and_counters\":%s}\n",
   rep,rep?"true":"false",(rep&1)?"BA":"AB",BATCH,ams,bms,ad,bd,guards?"true":"false");fflush(stdout);
  if(ad||bd||!guards)goto done;
 }
 // Candidate scratch is an intentionally supplied ABI buffer and must be unused.
 unsigned char* untouched=malloc(sb.bytes);if(!untouched)goto done;
 int untouched_ok=ok(Copy(untouched,sb.data,sb.bytes,2),"candidate scratch readback");
 for(size_t j=0;j<sb.bytes&&untouched_ok;++j)if(untouched[j]!=0xa5)untouched_ok=0;
 free(untouched);if(!untouched_ok)goto done;rc=0;
done:
 if(file)fclose(file);if(Sync&&!ok(Sync(),"cleanup synchronize"))rc=1;
 if(start&&!ok(EventDestroy(start),"destroy start"))rc=1;if(end&&!ok(EventDestroy(end),"destroy end"))rc=1;
 if(native&&!ok(Unload(native),"unload native"))rc=1;if(candidate&&!ok(Unload(candidate),"unload candidate"))rc=1;
 Buffer* buffers[]={&w,&x,&i,&r,&m,&z,&s,&p,&oa,&ob,&sa,&sb,&ca,&cb};
 for(unsigned j=0;j<sizeof(buffers)/sizeof(buffers[0]);++j)if(buffers[j]->base&&!ok(Release(buffers[j]->base),"free buffer"))rc=1;
 free(weights);if(lib)dlclose(lib);
 printf("{\"type\":\"cleanup\",\"passed\":%s,\"actual_captured_operation\":true,\"synthetic_inputs\":false,\"engine_requests\":0,\"NPU_executed\":false}\n",rc?"false":"true");
 return rc;
}
