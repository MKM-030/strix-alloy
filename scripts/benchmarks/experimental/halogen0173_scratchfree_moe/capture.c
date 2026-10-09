/* Default-off, one whole real N=3 FL capture. Forward stock dispatch unchanged.
 * Namespace and mount are independent of the phase-clock adapter. No candidate
 * module load, launch substitution, state-file write or destructor HIP call.
 * Root owns entry22GiB/runtime18GiB host-memory guards and process lifetime. */
#define _GNU_SOURCE
#ifdef ALLOY_FREESTANDING_LINUX
#include "linux_abi.h"
#else
#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <link.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/uio.h>
#include <unistd.h>
#endif
#include "mapped_pins.h"

typedef struct { uint32_t x,y,z; } Dim;
typedef int (*LaunchFn)(const void*,Dim,Dim,void**,size_t,void*);
typedef void (*RegisterFn)(void**,const void*,char*,const char*,unsigned,Dim*,Dim*,Dim*,Dim*,int*);
enum { TOKENS=3,TASKS=30,ROWS=2560,HALVES=640,COUNTERS=60,WIDTH=640,EXPERTS=512 };
static const char symbol[]="_ZN7halogen12_GLOBAL__N_115k_i4r_rows_fl_oEPKhlPKDF16_PKiPfPKfS4_PKtS9_PtPjS6_";
static const char engine_sha[]="af4f07bbe3759206013eb6f1328095ca2105cfda5127c5b9a2ab93e1aea987b7";
typedef struct {
 char magic[8];uint32_t version,tokens,experts,complete;int64_t scale_bytes;
} Header;
typedef struct {
 uint64_t w;int64_t scale_bytes;uint64_t x,ids,scratch,routes,metadata,residual,scalar,output,counters,map;
} Args;
_Static_assert(sizeof(Header)==32 && sizeof(Args)==96 && sizeof(Dim)==12,"native/schema ABI");
static pthread_mutex_t lock=PTHREAD_MUTEX_INITIALIZER;
static uintptr_t main_base;
static const void* fl_handle;
static int enabled,fd=-1;
static _Atomic int claimed;
static pthread_once_t launch_once=PTHREAD_ONCE_INIT;
static const char* capture_path;
static LaunchFn forward_launch;
static int (*get_device)(int*),(*get_capture)(void*,int*),(*sync_stream)(void*);
static int (*copy_memory)(void*,const void*,size_t,int),(*address_range)(void**,size_t*,void*);

static int nofault(void* dst,const void* src,size_t size) {
 struct iovec local={dst,size},remote={(void*)src,size};
 return src && process_vm_readv(getpid(),&local,1,&remote,1,0)==(ssize_t)size;
}
static int write_all(const void* data,size_t size) {
 const unsigned char* p=data;
 while(size){ssize_t n=write(fd,p,size);if(n<0&&errno==EINTR)continue;if(n<=0)return 0;p+=n;size-=(size_t)n;}return 1;
}
static int digest_engine(void) {
 void* crypto=dlopen("libcrypto.so.3",RTLD_NOW|RTLD_LOCAL);FILE* file=NULL;void* ctx=NULL;int pass=0;
 void*(*create)(void)=NULL;void(*destroy)(void*)=NULL;const void*(*sha)(void)=NULL;
 int(*init)(void*,const void*,void*)=NULL;int(*update)(void*,const void*,size_t)=NULL;
 int(*finish)(void*,unsigned char*,unsigned*)=NULL;
 unsigned char digest[32],buffer[65536];unsigned size=0;char hex[65];size_t total=0;
 if(!crypto)goto out;
#define CRYPTO(fn,sym) do{*(void**)(&fn)=dlsym(crypto,sym);if(!fn)goto out;}while(0)
 CRYPTO(create,"EVP_MD_CTX_new");CRYPTO(destroy,"EVP_MD_CTX_free");CRYPTO(sha,"EVP_sha256");
 CRYPTO(init,"EVP_DigestInit_ex");CRYPTO(update,"EVP_DigestUpdate");CRYPTO(finish,"EVP_DigestFinal_ex");
#undef CRYPTO
 file=fopen("/proc/self/exe","rb");ctx=create();if(!file||!ctx||!init(ctx,sha(),NULL))goto out;
 for(;;){size_t n=fread(buffer,1,sizeof(buffer),file);total+=n;if(n&&!update(ctx,buffer,n))goto out;
  if(n<sizeof(buffer)){if(ferror(file))goto out;break;}if(total>26188824)goto out;}
 if(total!=26188824||!finish(ctx,digest,&size)||size!=32)goto out;
 for(unsigned i=0;i<32;++i)snprintf(hex+2*i,3,"%02x",digest[i]);
 pass=!strcmp(hex,engine_sha);
out:if(ctx&&destroy)destroy(ctx);if(file)fclose(file);if(crypto)dlclose(crypto);return pass;
}
static int resident_query(void) {
 char args[512];FILE* file=fopen("/proc/self/cmdline","rb");if(!file)return 1;
 size_t n=fread(args,1,sizeof(args),file);fclose(file);size_t first=strnlen(args,n);
 return first<n&&n-first-1>=sizeof("--resident-gib")&&
  !memcmp(args+first+1,"--resident-gib",sizeof("--resident-gib"));
}
static int main_image(struct dl_phdr_info* info,size_t size,void* unused) {
 (void)size;(void)unused;if(info->dlpi_name&&*info->dlpi_name)return 0;main_base=info->dlpi_addr;return 1;
}
static int mapped_bytes(void) {
 unsigned char current[512];
 for(unsigned i=0;i<sizeof(mapped_pins)/sizeof(mapped_pins[0]);++i){const MappedPin* p=&mapped_pins[i];
  if(p->size>sizeof(current)||!nofault(current,(const void*)(main_base+p->rva),p->size)||
     memcmp(current,p->bytes,p->size))return 0;}
 return 1;
}
__attribute__((constructor)) static void configure(void) {
 const char* e=getenv("ALLOY0173_FL_CAPTURE_ENABLE");capture_path=getenv("ALLOY0173_FL_CAPTURE_PATH");
 if(!e||strcmp(e,"1")||!capture_path||capture_path[0]!='/'||resident_query())return;
 if(!digest_engine())return;
 dl_iterate_phdr(main_image,NULL);if(!mapped_bytes())return;enabled=1;
}
__attribute__((destructor)) static void close_file(void) {if(fd>=0)close(fd);}

__attribute__((visibility("default")))
void __hipRegisterFunction(void** module,const void* host,char* device,const char* name,unsigned limit,
 Dim* thread,Dim* block,Dim* block_dim,Dim* grid,int* warp) {
 RegisterFn next;*(void**)(&next)=dlsym(RTLD_NEXT,"__hipRegisterFunction");if(!next)_exit(127);
 next(module,host,device,name,limit,thread,block,block_dim,grid,warp);
 if(enabled&&name&&!strcmp(name,symbol)&&(uintptr_t)host==main_base+0x18f6b50u&&
    limit==UINT32_MAX&&!thread&&!block&&!block_dim&&!grid&&!warp)fl_handle=host;
}
static int targets(void) {
#define HIP(fn,sym) do{*(void**)(&fn)=dlsym(RTLD_NEXT,sym);if(!fn)return 0;}while(0)
 HIP(get_device,"hipGetDevice");HIP(get_capture,"hipStreamIsCapturing");HIP(sync_stream,"hipStreamSynchronize");
 HIP(copy_memory,"hipMemcpy");HIP(address_range,"hipMemGetAddressRange");
#undef HIP
 return 1;
}
static int span(uint64_t pointer,size_t bytes) {
 void* base=NULL;size_t size=0;if(!pointer||!bytes||pointer>UINT64_MAX-bytes)return 0;
 if(address_range(&base,&size,(void*)(uintptr_t)pointer))return 0;
 uintptr_t lo=(uintptr_t)base;
 return pointer>=lo&&pointer-lo<=size&&bytes<=size-(size_t)(pointer-lo);
}
static int copy(void* dst,uint64_t src,size_t bytes) {
 return span(src,bytes)&&copy_memory(dst,(const void*)(uintptr_t)src,bytes,2)==0;
}
static int unpack(Args* a,void** raw) {
 void* args[12];if(!nofault(args,raw,sizeof(args)))return 0;
 uint64_t words[12];for(unsigned i=0;i<12;++i)if(!nofault(&words[i],args[i],8))return 0;
 memcpy(a,words,sizeof(*a));
 return a->scale_bytes==INT64_C(0x19000000)&&a->w&&a->x&&a->ids&&a->scratch&&a->routes&&
  a->metadata&&a->residual&&a->scalar&&a->output&&a->counters&&a->map;
}
static int capture_before(const Args* a,Header* h) {
 int ids[TASKS],map[TASKS],remap[TASKS],selected[TASKS],unique=0,seen[TASKS]={0};
 unsigned before[COUNTERS];uint16_t input[TASKS*WIDTH],metadata[ROWS],residual[TOKENS*ROWS];
 float routes[TASKS],scalar[TOKENS];
 if(!span(a->w,(size_t)EXPERTS*ROWS*330)||
    !copy(ids,a->ids,sizeof(ids))||!copy(map,a->map,sizeof(map))||!copy(before,a->counters,sizeof(before)))return 0;
 for(unsigned i=0;i<COUNTERS;++i)if(before[i])return 0;
 for(unsigned i=0;i<TASKS;++i){
  if(ids[i]<0||ids[i]>=EXPERTS||map[i]<0||map[i]>=TASKS||seen[map[i]]++)return 0;
  int j=0;while(j<unique&&selected[j]!=ids[i])++j;
  if(j==unique)selected[unique++]=ids[i];remap[i]=j;
 }
 if(!copy(input,a->x,sizeof(input))||!copy(routes,a->routes,sizeof(routes))||
    !copy(metadata,a->metadata,sizeof(metadata))||!copy(residual,a->residual,sizeof(residual))||
    !copy(scalar,a->scalar,sizeof(scalar)))return 0;
 // Prove all required source slices before creating a partial payload.
 for(int j=0;j<unique;++j){uint64_t row=(uint64_t)selected[j]*ROWS;
  if(!span(a->w+row*320,ROWS*320)||!span(a->w+(uint64_t)a->scale_bytes+row*10,ROWS*10))return 0;}
 fd=open(capture_path,O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC|O_NOFOLLOW,0600);if(fd<0)return 0;
 *h=(Header){{'H','0','1','7','3','F','L','1'},1,TOKENS,(uint32_t)unique,0,(int64_t)unique*ROWS*320};
 if(!write_all(h,sizeof(*h)))return 0;
 // At most30 expert code slices + scale slices:25,344,000 bytes, no model-wide copy.
 unsigned char* slice=malloc(ROWS*320);if(!slice)return 0;int good=1;
 for(int j=0;j<unique&&good;++j){uint64_t row=(uint64_t)selected[j]*ROWS;
  good=copy(slice,a->w+row*320,ROWS*320)&&write_all(slice,ROWS*320);}
 for(int j=0;j<unique&&good;++j){uint64_t row=(uint64_t)selected[j]*ROWS;
  good=copy(slice,a->w+(uint64_t)a->scale_bytes+row*10,ROWS*10)&&write_all(slice,ROWS*10);}
 free(slice);if(!good)return 0;
 return write_all(input,sizeof(input))&&write_all(remap,sizeof(remap))&&write_all(routes,sizeof(routes))&&
  write_all(metadata,sizeof(metadata))&&write_all(residual,sizeof(residual))&&write_all(scalar,sizeof(scalar))&&
  write_all(map,sizeof(map))&&write_all(before,sizeof(before))&&write_all(selected,unique*sizeof(int));
}
static void resolve_launch(void) {
 *(void**)(&forward_launch)=dlsym(RTLD_NEXT,"hipLaunchKernel");if(!forward_launch)_exit(127);
}
__attribute__((visibility("default")))
int hipLaunchKernel(const void* f,Dim grid,Dim block,void** raw,size_t shared,void* stream) {
 pthread_once(&launch_once,resolve_launch);
 uintptr_t caller=(uintptr_t)__builtin_return_address(0);
 if(!enabled||claimed||f!=fl_handle||caller!=main_base+0x17d6209u||
    grid.x!=400*TOKENS||grid.y!=1||grid.z!=1||block.x!=256||block.y!=1||block.z!=1||shared||stream)
  return forward_launch(f,grid,block,raw,shared,stream);
 pthread_mutex_lock(&lock);
 if(claimed){pthread_mutex_unlock(&lock);return forward_launch(f,grid,block,raw,shared,stream);}
 claimed=1;int device=-1,capturing=-1,prepared=0;Args a;Header h;
 if(targets()&&!get_device(&device)&&device==0&&!get_capture(stream,&capturing)&&capturing==0&&
    unpack(&a,raw)&&!sync_stream(stream))prepared=capture_before(&a,&h);
 // Exactly one original submission in every path, with the original arguments.
 int result=forward_launch(f,grid,block,raw,shared,stream);
 if(prepared&&!result&&!sync_stream(stream)){
  uint16_t output[TOKENS*ROWS];unsigned after[COUNTERS];
  int good=copy(output,a.output,sizeof(output))&&copy(after,a.counters,sizeof(after));
  for(unsigned i=0;i<COUNTERS&&good;++i)if(after[i])good=0;
  if(good&&write_all(after,sizeof(after))&&write_all(output,sizeof(output))){
   uint32_t complete=1;
   if(pwrite(fd,&complete,4,20)==4&&!fsync(fd))fprintf(stderr,"alloy0173_fl_capture complete N=3 experts=%u\n",h.experts);
  }
 }
 if(fd>=0){close(fd);fd=-1;}
 pthread_mutex_unlock(&lock);return result;
}
