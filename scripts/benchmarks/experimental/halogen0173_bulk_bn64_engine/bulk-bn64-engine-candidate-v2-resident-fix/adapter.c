/* Default-off, pinned native bulk BN64 experiment. Source-only delivery.
 * No module load/device-code replacement and no host text patch.
 * Registration passes through; launches use already registered native handles.
 * Root owns every eventual build, engine lifetime and equality/performance trial. */
#define _GNU_SOURCE
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
#include <sys/syscall.h>
#include <sys/uio.h>
#include <unistd.h>

typedef int hipError_t;
typedef struct ihipStream_t *hipStream_t;
typedef struct { uint32_t x,y,z; } dim3;
typedef dim3 uint3;
typedef int (*LaunchFn)(const void*,dim3,dim3,void**,size_t,hipStream_t);
typedef void (*RegisterFn)(void**,const void*,char*,const char*,unsigned,uint3*,uint3*,dim3*,dim3*,int*);
enum { R=81920,N=8192,E=512,C128=1152,C64=1792,GUARD=4096,INVALID=999 };
enum { I128,G128,D128,I64,G64,D64,FOLD,KERNELS };
enum { IDLE,ITEMS,GU,DN };
#define GU_ITEMS_BYTES ((size_t)5*C64*16)
#define DN_ITEMS_BYTES ((size_t)10*C64*16)
/* Latest host mapping is generated and independently checked in host-map.json. */
#define MODE_RVA UINT64_C(0x18fcca0)
#define FLAG_RVA UINT64_C(0x18fccd8)
#define ITEM_CALL_RVA UINT64_C(0x17d2e97)
#define GU_CALL_RVA UINT64_C(0x17d354a)
#define DN_CALL_RVA UINT64_C(0x17d43aa)
#define FOLD_CALL_RVA UINT64_C(0x17d462c)
static const uintptr_t descriptor_rva[KERNELS]={0x18f92b0,0x18f92d0,0x18f92d8,0x18f92a8,0x18f92b8,0x18f92c0,0x18f6bc0};
static const char *symbols[KERNELS]={
 "_ZN5q4moe13k_q4moe_itemsILi128EEEvPKiS2_S2_iPNS_4ItemES4_Pi",
 "_ZN5q4moe7k_q4moeILi1ELi0ELi128ENS_4TuneILi0ELi128EEELi1EEEvNS_4ArgsE",
 "_ZN5q4moe7k_q4moeILi1ELi2ELi128ENS_4TuneILi0ELi128EEELi2EEEvNS_4ArgsE",
 "_ZN5q4moe13k_q4moe_itemsILi64EEEvPKiS2_S2_iPNS_4ItemES4_Pi",
 "_ZN5q4moe7k_q4moeILi1ELi0ELi64ENS_4TuneILi0ELi128EEELi1EEEvNS_4ArgsE",
 "_ZN5q4moe7k_q4moeILi1ELi2ELi64ENS_4TuneILi0ELi128EEELi2EEEvNS_4ArgsE",
 "_ZN7halogen12_GLOBAL__N_115k_i4r_fold_rowsEPKtPKiiPKfPKDF16_S2_S6_Pt"};
typedef struct { uint64_t weight,packed,scale,stride; float codebook[16];
 uint64_t m0,m1,input,permutation,items,count,output; } ProjectionArgs;
typedef struct { uint64_t ids,prefix,raw; int32_t rows; uint32_t padding;
 uint64_t gu_items,dn_items,counts; } ItemArgs;
typedef struct { uint64_t dense,inverse; int32_t tokens; uint32_t padding;
 uint64_t weights,channel,residual,scalar,output; } FoldArgs;
_Static_assert(sizeof(ProjectionArgs)==152 && sizeof(ItemArgs)==56 && sizeof(FoldArgs)==64,"kernarg ABI");
_Static_assert(sizeof(dim3)==12 && sizeof(void*)==8,"native x86_64 HIP ABI");
static pthread_mutex_t mutex=PTHREAD_MUTEX_INITIALIZER;
static _Thread_local int nesting;
static int configured,fd=-1,memfd=-1,allocated,phase;
static _Atomic int disabled,fatal;
static pid_t owner,transaction_tid;
static uintptr_t main_base;
static void **native_module;
static const void *handles[KERNELS];
static void *gu_base,*dn_base,*gu_items,*dn_items;
static ItemArgs saved_items;
static ProjectionArgs saved_gu,saved_dn;
static int expected_gu,expected_dn;
static uint64_t started,committed,rolled_back,rejected,failures;
static size_t log_bytes;
static LaunchFn native_launch;
static int (*get_device)(int*),(*capturing)(hipStream_t,int*),(*allocate)(void**,size_t);
static int (*release)(void*),(*set_memory)(void*,int,size_t),(*copy_memory)(void*,const void*,size_t,int);
static int (*stream_sync)(hipStream_t);

static void *resolve(const char *name) { return dlsym(RTLD_NEXT,name); }
static void *required(const char *name) {
 void *p=resolve(name);if(!p){static const char msg[]="bulk_bn64: missing native HIP target\n";
  ssize_t written=write(2,msg,sizeof(msg)-1);(void)written;_exit(127);}return p;
}
static void audit(const char *event,int result) {
 if(fd<0 || log_bytes>=1024*1024)return;
 char line[384];int n=snprintf(line,sizeof(line),"{\"type\":\"%s\",\"result\":%d,\"phase\":%d,\"started\":%llu,\"committed\":%llu,\"rolled_back\":%llu,\"rejected\":%llu,\"failures\":%llu,\"private_item_bytes\":%zu}\n",
  event,result,phase,(unsigned long long)started,(unsigned long long)committed,
  (unsigned long long)rolled_back,(unsigned long long)rejected,(unsigned long long)failures,
  GU_ITEMS_BYTES+DN_ITEMS_BYTES+4*GUARD);
 if(n>0 && (size_t)n<sizeof(line) && write(fd,line,(size_t)n)==n)log_bytes+=(size_t)n;
}
static int find_main(struct dl_phdr_info *info,size_t length,void *unused) {
 (void)length;(void)unused;if(info->dlpi_name && *info->dlpi_name)return 0;
 main_base=info->dlpi_addr;return 1;
}
static int digest_region(const char *path,uint64_t offset,size_t bytes,const char *expected) {
 void *crypto=dlopen("libcrypto.so.3",RTLD_NOW|RTLD_LOCAL);FILE *f=NULL;void *ctx=NULL;int pass=0;
 void*(*ctx_new)(void)=NULL;void(*ctx_free)(void*)=NULL;const void*(*sha256)(void)=NULL;
 int(*init)(void*,const void*,void*)=NULL;int(*update)(void*,const void*,size_t)=NULL;
 int(*finish)(void*,unsigned char*,unsigned*)=NULL;unsigned char digest[32],buffer[65536];unsigned length=0;
 char hex[65];if(!crypto)goto out;
#define CRYPTO(fn,name) do { *(void**)(&fn)=dlsym(crypto,name);if(!fn)goto out; } while(0)
 CRYPTO(ctx_new,"EVP_MD_CTX_new");CRYPTO(ctx_free,"EVP_MD_CTX_free");CRYPTO(sha256,"EVP_sha256");
 CRYPTO(init,"EVP_DigestInit_ex");CRYPTO(update,"EVP_DigestUpdate");CRYPTO(finish,"EVP_DigestFinal_ex");
#undef CRYPTO
 f=fopen(path,"rb");if(!f || fseeko(f,(off_t)offset,SEEK_SET))goto out;
 ctx=ctx_new();if(!ctx || !init(ctx,sha256(),NULL))goto out;
 size_t remaining=bytes;
 while(remaining){size_t chunk=remaining<sizeof(buffer)?remaining:sizeof(buffer);
  if(fread(buffer,1,chunk,f)!=chunk || !update(ctx,buffer,chunk))goto out;
  remaining-=chunk;
 }
 if(!offset && fgetc(f)!=EOF)goto out;
 if(!finish(ctx,digest,&length)||length!=32)goto out;
 for(unsigned i=0;i<32;i++)snprintf(hex+2*i,3,"%02x",digest[i]);
 pass=!strcmp(hex,expected);
out:
 if(ctx&&ctx_free)ctx_free(ctx);
 if(f)fclose(f);
 if(crypto)dlclose(crypto);
 return pass;
}
/* The normal entrypoint asks this same pinned executable for resident bytes
 * before serving. Exclude only its exact argv[1] before claiming the log. */
static int resident_query(void) {
 char args[128];int probe_fd=open("/proc/self/cmdline",O_RDONLY|O_CLOEXEC);
 if(probe_fd<0)return 0;
 ssize_t bytes;do {bytes=read(probe_fd,args,sizeof(args));} while(bytes<0&&errno==EINTR);
 close(probe_fd);if(bytes<=0)return 0;
 char *end=memchr(args,0,(size_t)bytes);if(!end)return 0;
 size_t used=(size_t)(end-args)+1;static const char flag[]="--resident-gib";
 return (size_t)bytes-used>=sizeof(flag)&&!memcmp(args+used,flag,sizeof(flag));
}
__attribute__((constructor)) static void initialize(void) {
 int saved_errno=errno;const char *enable=getenv("ALLOY_BULK_BN64_ENABLE");char exe[4096];
 ssize_t length=readlink("/proc/self/exe",exe,sizeof(exe));
 static const char wanted[]="/usr/local/bin/flash_serve";
 if(!enable||strcmp(enable,"1")||length!=(ssize_t)(sizeof(wanted)-1)||memcmp(exe,wanted,sizeof(wanted)-1))goto out;
 if(resident_query())goto out;
 if(!digest_region("/proc/self/exe",0,26188824,"af4f07bbe3759206013eb6f1328095ca2105cfda5127c5b9a2ab93e1aea987b7") ||
    !digest_region("/proc/self/exe",339968,17765424,"18937428b544e8a5ef1dae31db97f36136e8cdeca90e6c49458ef831b822a039"))goto out;
 dl_iterate_phdr(find_main,NULL);owner=getpid();
 const char *path=getenv("ALLOY_BULK_BN64_LOG");if(!path||!main_base)goto out;
 fd=open(path,O_WRONLY|O_CREAT|O_EXCL|O_APPEND|O_CLOEXEC,0600);if(fd<0)goto out;
 memfd=open("/proc/self/mem",O_RDONLY|O_CLOEXEC);
 configured=1;audit("enabled_pinned_0173",0);
out: errno=saved_errno;
}
static int copy_host(void *dst,const void *src,size_t bytes) {
 if(!src)return 0;
 struct iovec local={dst,bytes},remote={(void*)src,bytes};
 if(syscall(SYS_process_vm_readv,getpid(),&local,1,&remote,1,0)==(ssize_t)bytes)return 1;
 return memfd>=0 && pread(memfd,dst,bytes,(off_t)(uintptr_t)src)==(ssize_t)bytes;
}
static int scalar_arguments(void **args,void *packed,int fold) {
 void *values[8];int count=fold?8:7;if(!copy_host(values,args,(size_t)count*sizeof(void*)))return 0;
 static const size_t offsets_items[]={0,8,16,24,32,40,48},offsets_fold[]={0,8,16,24,32,40,48,56};
 for(int i=0;i<count;i++){size_t offset=fold?offsets_fold[i]:offsets_items[i];size_t bytes=i==(fold?2:3)?4:8;
  if(!copy_host((unsigned char*)packed+offset,values[i],bytes))return 0;}
 return 1;
}
static int projection_arguments(void **args,ProjectionArgs *packed) {
 void *value=NULL;return copy_host(&value,args,sizeof(value))&&copy_host(packed,value,sizeof(*packed));
}
static void item_arguments(ItemArgs *a,void **args) {
 args[0]=&a->ids;args[1]=&a->prefix;args[2]=&a->raw;args[3]=&a->rows;
 args[4]=&a->gu_items;args[5]=&a->dn_items;args[6]=&a->counts;
}
static int shape(dim3 grid,dim3 block,unsigned gx,unsigned bx,size_t shared,hipStream_t stream) {
 return grid.x==gx && grid.y==1 && grid.z==1 && block.x==bx && block.y==1 && block.z==1 && !shared && !stream;
}
static int native_mode(void) {
 int32_t mode=0;unsigned char flag=0;
 return MODE_RVA && FLAG_RVA && copy_host(&mode,(void*)(main_base+MODE_RVA),4) &&
  copy_host(&flag,(void*)(main_base+FLAG_RVA),1) && mode==1 && flag==1;
}
static int ready_runtime(void) {
#define HIP_FN(fn,name) do { *(void**)(&fn)=resolve(name);if(!fn)return 0; } while(0)
 if(!get_device){HIP_FN(get_device,"hipGetDevice");HIP_FN(capturing,"hipStreamIsCapturing");
  HIP_FN(allocate,"hipMalloc");HIP_FN(release,"hipFree");HIP_FN(set_memory,"hipMemset");
  HIP_FN(copy_memory,"hipMemcpy");HIP_FN(stream_sync,"hipStreamSynchronize");}
#undef HIP_FN
 int device=-1,capture=-1;
 return get_device && capturing && allocate && release && set_memory && copy_memory && stream_sync &&
  !get_device(&device) && device==0 && !capturing(NULL,&capture) && capture==0;
}
static int arrays(void) {
 if(allocated)return 1;
 if(allocate(&gu_base,GU_ITEMS_BYTES+2*GUARD) || allocate(&dn_base,DN_ITEMS_BYTES+2*GUARD))goto failed;
 if(set_memory(gu_base,0xa5,GU_ITEMS_BYTES+2*GUARD) || set_memory(dn_base,0xa5,DN_ITEMS_BYTES+2*GUARD))goto failed;
 gu_items=(unsigned char*)gu_base+GUARD;dn_items=(unsigned char*)dn_base+GUARD;allocated=1;return 1;
failed:
 if(gu_base){release(gu_base);gu_base=NULL;}
 if(dn_base){release(dn_base);dn_base=NULL;}
 disabled=1;failures++;audit("allocation_failed_stock",INVALID);return 0;
}
static int histogram(const ItemArgs *a) {
 int32_t raw[E+2],ids[E],prefix[E+1];
 if(!a->ids||!a->prefix||!a->raw||!a->gu_items||!a->dn_items||!a->counts)return 0;
 if(stream_sync(NULL)||copy_memory(raw,(void*)(uintptr_t)a->raw,sizeof(raw),2)||
  copy_memory(ids,(void*)(uintptr_t)a->ids,sizeof(ids),2)||copy_memory(prefix,(void*)(uintptr_t)a->prefix,sizeof(prefix),2))return 0;
 int active=raw[E],total=raw[E+1],sum=0,segments=0,index=0,previous=-1;
 if(active<1||active>E||total!=R)return 0;
 for(int e=0;e<E;e++){int rows=raw[e];if(rows<0||rows>R)return 0;
  if(rows){if(index>=active||ids[index]!=e||e<=previous||prefix[index]!=sum)return 0;previous=e;index++;}
  if(sum>R-rows)return 0;
  sum+=rows;segments+=(rows+63)/64;
 }
 if(sum!=R||index!=active||prefix[active]!=R||segments>C64)return 0;
 expected_gu=5*segments;expected_dn=10*segments;return 1;
}
static int projection_prefix(const ProjectionArgs *a,int dn) {
 float codebook[16];for(int i=0;i<16;i++)codebook[i]=(float)(i-8);
 if(a->packed||a->scale!=(dn?UINT64_C(419430400):UINT64_C(838860800))||a->stride!=(dn?10:40)||
  memcmp(a->codebook,codebook,sizeof(codebook))||!a->weight||!a->m0||!a->input||!a->output)return 0;
 if(dn)return !a->m1&&!a->permutation&&a->input==saved_gu.output&&a->items==saved_items.dn_items&&a->count==saved_items.counts+4;
 return a->m1&&a->permutation&&a->items==saved_items.gu_items&&a->count==saved_items.counts;
}
static int guards(void) {
 unsigned char bytes[GUARD];void *bases[]={gu_base,dn_base};size_t spans[]={GU_ITEMS_BYTES,DN_ITEMS_BYTES};
 for(int i=0;i<2;i++)for(int end=0;end<2;end++){
  void *p=end?(unsigned char*)bases[i]+GUARD+spans[i]:bases[i];
  if(copy_memory(bytes,p,sizeof(bytes),2))return 0;
  for(size_t j=0;j<sizeof(bytes);j++)if(bytes[j]!=0xa5)return 0;}
 return 1;
}
/* On any interrupted transaction, restore native128 item/count state and the
 * already submitted projection prefix before any stock continuation can run.
 * Synchronization also protects an unexpected other-thread/other-stream launch. */
static int rollback(void) {
 if(!phase)return 0;
 dim3 one={1,1,1},block_items={512,1,1},block_projection={256,1,1};void *args[7];
 ItemArgs items=saved_items;item_arguments(&items,args);
 int result=native_launch(handles[I128],one,block_items,args,0,NULL);
 if(!result && phase>=GU){ProjectionArgs gu=saved_gu;void *ga[]={&gu};dim3 grid={5*C128,1,1};
  result=native_launch(handles[G128],grid,block_projection,ga,0,NULL);}
 if(!result && phase>=DN){ProjectionArgs dn=saved_dn;void *da[]={&dn};dim3 grid={10*C128,1,1};
  result=native_launch(handles[D128],grid,block_projection,da,0,NULL);}
 if(!result)result=stream_sync(NULL);
 disabled=1;rolled_back++;if(result){failures++;fatal=1;}
 audit(result?"rollback_failed_closed":"restored_stock_prefix",result);
 phase=IDLE;return result;
}
void __hipRegisterFunction(void **modules,const void *host,char *device,const char *name,unsigned limit,
 uint3 *tid,uint3 *bid,dim3 *bdim,dim3 *gdim,int *warp) {
 int saved_errno=errno;RegisterFn native=(RegisterFn)required("__hipRegisterFunction");
 errno=saved_errno;native(modules,host,device,name,limit,tid,bid,bdim,gdim,warp);int native_errno=errno;
 if(configured&&getpid()==owner&&name&&device&&limit==UINT32_MAX&&!tid&&!bid&&!bdim&&!gdim&&!warp){
  pthread_mutex_lock(&mutex);
  for(int i=0;i<KERNELS;i++)if(!strcmp(name,symbols[i])&&!strcmp(device,symbols[i])&&descriptor_rva[i]&&
   (uintptr_t)host==main_base+descriptor_rva[i]){
    if((native_module&&native_module!=modules)||(handles[i]&&handles[i]!=host))disabled=1;
    else {native_module=modules;handles[i]=host;}
  }
  pthread_mutex_unlock(&mutex);
 }
 errno=native_errno;
}
void __hipUnregisterFatBinary(void **modules) {
 typedef void(*F)(void**);F native=(F)required("__hipUnregisterFatBinary");int saved_errno=errno;
 if(configured&&getpid()==owner&&!nesting){pthread_mutex_lock(&mutex);nesting=1;
  if(modules==native_module){
   if(phase&&native_launch&&stream_sync&&rollback())_exit(127);
   disabled=1;memset(handles,0,sizeof(handles));
  }
  nesting=0;pthread_mutex_unlock(&mutex);}
 errno=saved_errno;native(modules);
}
hipError_t hipLaunchKernel(const void *fn,dim3 grid,dim3 block,void **args,size_t shared,hipStream_t stream) {
 int saved_errno=errno;LaunchFn native=(LaunchFn)required("hipLaunchKernel");
 const void *original_fn=fn;const dim3 original_grid=grid,original_block=block;
 void **const original_args=args;const size_t original_shared=shared;const hipStream_t original_stream=stream;
 if(!configured||getpid()!=owner||nesting){errno=saved_errno;return native(fn,grid,block,args,shared,stream);}
 pthread_mutex_lock(&mutex);nesting=1;native_launch=native;
 uintptr_t caller=(uintptr_t)__builtin_extract_return_addr(__builtin_return_address(0))-main_base;
 pid_t tid=(pid_t)syscall(SYS_gettid);int result=0,accepted=0,native_errno=saved_errno;
 if(fatal){result=INVALID;goto complete;}
 if(phase && (disabled || tid!=transaction_tid || !ready_runtime() || !native_mode())){
  result=rollback();if(result)goto complete;
 }
 if(!disabled && phase==IDLE && fn==handles[I128] && caller==ITEM_CALL_RVA &&
  shape(grid,block,1,512,shared,stream) && native_mode() && ready_runtime()){
  int registered=1;for(int i=0;i<KERNELS;i++)registered&=handles[i]!=NULL;
  ItemArgs item={0};
  if(registered && scalar_arguments(args,&item,0) && item.rows==R && histogram(&item) && arrays()){
   saved_items=item;transaction_tid=tid;started++;phase=ITEMS;
   item.gu_items=(uintptr_t)gu_items;item.dn_items=(uintptr_t)dn_items;void *replacement[7];item_arguments(&item,replacement);
   errno=saved_errno;result=native(handles[I64],grid,block,replacement,shared,stream);native_errno=errno;accepted=1;
   if(!result){int32_t counts[2];result=stream_sync(NULL);
    if(!result)result=copy_memory(counts,(void*)(uintptr_t)saved_items.counts,8,2);
    if(!result&&(counts[0]!=expected_gu||counts[1]!=expected_dn||!guards()))result=INVALID;}
  }
 } else if(!disabled && phase==ITEMS && fn==handles[G128] && caller==GU_CALL_RVA &&
  shape(grid,block,5*C128,256,shared,stream)){
  ProjectionArgs gu;
  if(projection_arguments(args,&gu)&&projection_prefix(&gu,0)){
   saved_gu=gu;gu.items=(uintptr_t)gu_items;void *replacement[]={&gu};dim3 candidate_grid=grid;candidate_grid.x=5*C64;
   phase=GU;errno=saved_errno;result=native(handles[G64],candidate_grid,block,replacement,shared,stream);native_errno=errno;accepted=1;
  }
 } else if(!disabled && phase==GU && fn==handles[D128] && caller==DN_CALL_RVA &&
  shape(grid,block,10*C128,256,shared,stream)){
  ProjectionArgs dn;
  if(projection_arguments(args,&dn)&&projection_prefix(&dn,1)){
   saved_dn=dn;dn.items=(uintptr_t)dn_items;void *replacement[]={&dn};dim3 candidate_grid=grid;candidate_grid.x=10*C64;
   phase=DN;errno=saved_errno;result=native(handles[D64],candidate_grid,block,replacement,shared,stream);native_errno=errno;accepted=1;
  }
 } else if(!disabled && phase==DN && fn==handles[FOLD] && caller==FOLD_CALL_RVA &&
  shape(grid,block,20480,256,shared,stream)){
  FoldArgs fold={0};
  if(scalar_arguments(args,&fold,1)&&fold.tokens==N&&fold.dense==saved_dn.output&&fold.channel==saved_dn.m0&&
   fold.inverse&&fold.weights&&fold.residual&&fold.scalar&&fold.output){
   errno=saved_errno;result=native(fn,grid,block,args,shared,stream);native_errno=errno;accepted=1;
   if(!result){committed++;phase=IDLE;audit("committed_native64_bulk",0);}
  }
 }
 if(accepted && !result)goto complete;
 if(phase){int rollback_result=rollback();if(rollback_result){result=rollback_result;goto complete;}}
 rejected++;errno=saved_errno;
 result=native(original_fn,original_grid,original_block,original_args,original_shared,original_stream);native_errno=errno;
complete:
 nesting=0;pthread_mutex_unlock(&mutex);errno=native_errno;return result;
}
/* Idle root-owned close, if used, is explicit. Process-exit reclamation is the
 * default, avoiding HIP calls after its destructor has torn down the runtime. */
int alloy_bulk_bn64_shutdown(void) {
 if(!configured||getpid()!=owner)return 0;
 pthread_mutex_lock(&mutex);nesting=1;disabled=1;int result=0;
 if(phase)result=rollback();
 if(!result&&allocated)result=stream_sync(NULL);
 if(!result&&gu_base){result=release(gu_base);if(!result)gu_base=NULL;}
 if(!result&&dn_base){result=release(dn_base);if(!result)dn_base=NULL;}
 if(!gu_base&&!dn_base)allocated=0;
 audit("explicit_shutdown",result);nesting=0;pthread_mutex_unlock(&mutex);return result;
}
__attribute__((destructor)) static void finish(void) {
 if(fd>=0){audit("process_summary",0);close(fd);fd=-1;}
 if(memfd>=0){close(memfd);memfd=-1;}
}
