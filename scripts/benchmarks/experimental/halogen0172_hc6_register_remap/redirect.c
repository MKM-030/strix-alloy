#define _GNU_SOURCE
#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <link.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>

/* Default-off, pinned Linux x86-64 HIP launch redirect. No argument/tensor reads,
 * synchronization, launch retry, event timing, or HIP destructor calls. */
typedef int hipError_t;
typedef struct ihipStream_t *hipStream_t;
typedef struct ihipModule_t *hipModule_t;
typedef struct ihipModuleSymbol_t *hipFunction_t;
typedef struct { uint32_t x,y,z; } dim3;
typedef int (*launch_fn)(const void*,dim3,dim3,void**,size_t,hipStream_t);
typedef unsigned char *(*sha256_fn)(const unsigned char*,size_t,unsigned char*);
_Static_assert(sizeof(void*)==8 && sizeof(dim3)==12,"installed HIP x86-64 ABI");
_Static_assert(__BYTE_ORDER__==__ORDER_LITTLE_ENDIAN__,"little endian stats ABI");
_Static_assert(ATOMIC_LLONG_LOCK_FREE==2,"statistics need lock-free 64-bit atomics");

static const char engine_path[]="/usr/local/bin/flash_serve";
static const char engine_sha[]="ac73b1df48510a34e0246a77bd984f1df0e02e5fa6cf1530d3d77c91d3c0e913";
static const char code_path[]="/candidate/hc6-register-remap.hsaco";
static const char code_sha[]="39053af36ed652892f7082af4eca5cd153b593260448b3c91a67f277cd0f1259";
static const char kernel_name[]=
    "_ZN7halogen12_GLOBAL__N_112k_hc6_fused3ILi3EEEvPtPKtPKfS4_iNS0_5LqGrpES2_liPKhS4_S2_PfPyySB_y";
enum { ENGINE_BYTES=26178504, CODE_BYTES=17765424 };
enum { OFF=0, ARMED=1, INITIALIZING=2, READY=3, FAILED=4 };
enum { NONE=0, CONFIG=1, STATS=2, CRYPTO=3, ENGINE_FILE=4, ENGINE_HASH=5,
       MAIN_IMAGE=6, SYMBOLS=7, CODE_FILE=8, CODE_HASH=9, MODULE_LOAD=10,
       FUNCTION_LOOKUP=11, CANDIDATE_ERROR=12 };
enum { HOOK_CALLS=0, ELIGIBLE=1, ATTEMPTS=2, STOCK_CALLS=3, INELIGIBLE=4,
       BUSY_REENTRANT=5, CANDIDATE_ERRORS=6, STOCK_ERRORS=7, STATE=8, REASON=9,
       LOAD_STATUS=10, LOOKUP_STATUS=11, LAST_CANDIDATE=12, LAST_STOCK=13,
       DEVICE_STATUS=14, DEVICE=15, CAPTURE_STATUS=16, CAPTURE_STATE=17,
       MODULE_LOADED=18, FUNCTION_RESOLVED=19, ENGINE_VERIFIED=20,
       CODE_VERIFIED=21, INIT_ATTEMPTS=22, DISABLED_AFTER_ERROR=23,
       FILE_BYTES=24, ELIGIBLE_STOCK=25, WORDS=29 };
struct statistics {
    char magic[8]; uint32_t version,bytes; uint64_t pid;
    _Atomic uint64_t word[WORDS];
};
_Static_assert(offsetof(struct statistics,word)==24 && sizeof(struct statistics)==256,
               "statistics wire ABI");

static struct statistics *stats;
static _Atomic unsigned state;
static _Atomic uintptr_t native_address;
static _Thread_local unsigned depth;
static pthread_mutex_t init_lock=PTHREAD_MUTEX_INITIALIZER;
static pid_t owner;
static uintptr_t main_base;
static int main_found;
static sha256_fn sha256;
static void *crypto_handle,*code_image;
static hipModule_t module;
static hipFunction_t function;
static int (*get_device)(int*);
static int (*is_capturing)(hipStream_t,int*);
static int (*module_load)(hipModule_t*,const void*);
static int (*module_function)(hipFunction_t*,hipModule_t,const char*);
static int (*module_launch)(hipFunction_t,unsigned,unsigned,unsigned,unsigned,
                            unsigned,unsigned,unsigned,hipStream_t,void**,void**);

static void put(unsigned field,uint64_t value) {
    if(stats) atomic_store_explicit(&stats->word[field],value,memory_order_relaxed);
}
static void status(unsigned field,int value) {put(field,(uint64_t)(int64_t)value);}
static void add(unsigned field) {
    if(stats) atomic_fetch_add_explicit(&stats->word[field],1,memory_order_relaxed);
}
static void set_state(unsigned value) {
    put(STATE,value);atomic_store_explicit(&state,value,memory_order_release);
}
static void fail(unsigned reason) {put(REASON,reason);set_state(FAILED);}
static int find_main(struct dl_phdr_info *info,size_t size,void *unused) {
    (void)size;(void)unused;
    if(info->dlpi_name && *info->dlpi_name) return 0;
    main_base=info->dlpi_addr;main_found=1;return 1;
}
static int digest_matches(const unsigned char *data,size_t bytes,const char *expected) {
    unsigned char digest[32];char hex[65];static const char digits[]="0123456789abcdef";
    if(!sha256 || !sha256(data,bytes,digest)) return 0;
    for(unsigned i=0;i<32;i++) {hex[2*i]=digits[digest[i]>>4];hex[2*i+1]=digits[digest[i]&15];}
    hex[64]=0;return !strcmp(hex,expected);
}

/* Hash/load an immutable anonymous copy, never a mutable file-backed mapping.
 * O_NOFOLLOW covers the leaf; fixed parent directories are launcher-owned.
 * fstat before/after detects replacement/size/time changes during the read. */
static void *sealed_copy(const char *path,size_t bytes,int engine) {
    int fd=open(path,O_RDONLY|O_CLOEXEC|O_NOFOLLOW);
    if(fd<0) return NULL;
    struct stat before,after,running;
    void *copy=MAP_FAILED;
    if(fstat(fd,&before) || !S_ISREG(before.st_mode) || before.st_size!=(off_t)bytes) goto done;
    if(engine && (stat("/proc/self/exe",&running) || before.st_dev!=running.st_dev ||
                   before.st_ino!=running.st_ino)) goto done;
    copy=mmap(NULL,bytes,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);
    if(copy==MAP_FAILED) goto done;
    size_t offset=0;
    while(offset<bytes) {
        ssize_t count=read(fd,(unsigned char*)copy+offset,bytes-offset);
        if(count<0 && errno==EINTR) continue;
        if(count<=0) goto bad;
        offset+=(size_t)count;
    }
    if(fstat(fd,&after) || before.st_dev!=after.st_dev || before.st_ino!=after.st_ino ||
       before.st_size!=after.st_size || before.st_mtim.tv_sec!=after.st_mtim.tv_sec ||
       before.st_mtim.tv_nsec!=after.st_mtim.tv_nsec || before.st_ctim.tv_sec!=after.st_ctim.tv_sec ||
       before.st_ctim.tv_nsec!=after.st_ctim.tv_nsec || mprotect(copy,bytes,PROT_READ)) goto bad;
    close(fd);return copy;
bad:
    munmap(copy,bytes);copy=MAP_FAILED;
done:
    close(fd);return NULL;
}
static int stats_path_valid(const char *path) {
    static const char prefix[]="/tmp/hc6-remap-";
    size_t length=strlen(path),start=sizeof(prefix)-1;
    return length>start+4 && length<4096 && !strncmp(path,prefix,start) &&
        !strchr(path+start,'/') && !strcmp(path+length-4,".bin");
}
static int create_stats(const char *path) {
    if(!stats_path_valid(path)) return 0;
    int fd=open(path,O_RDWR|O_CREAT|O_EXCL|O_CLOEXEC|O_NOFOLLOW,0600);
    if(fd<0) return 0;
    struct stat st;
    if(fstat(fd,&st) || !S_ISREG(st.st_mode) || ftruncate(fd,sizeof(*stats))) {close(fd);return 0;}
    void *mapped=mmap(NULL,sizeof(*stats),PROT_READ|PROT_WRITE,MAP_SHARED,fd,0);
    close(fd);
    if(mapped==MAP_FAILED) return 0;
    stats=mapped;memcpy(stats->magic,"HGHC6R01",8);stats->version=1;
    stats->bytes=sizeof(*stats);stats->pid=(uint64_t)owner;
    for(unsigned i=0;i<WORDS;i++) atomic_init(&stats->word[i],0);
    for(unsigned i=LOAD_STATUS;i<=CAPTURE_STATE;i++) status(i,-1);
    return 1;
}

__attribute__((constructor)) static void initialize(void) {
    int saved=errno;
    const char *path=getenv("HG0172_HC6_REMAP_CODE"),*hash=getenv("HG0172_HC6_REMAP_SHA");
    const char *stats_path=getenv("HG0172_HC6_REMAP_STATS"),*image_hash=getenv("HG0172_HC6_REMAP_ENGINE_SHA");
    if(!path && !hash && !stats_path && !image_hash) goto done;
    owner=getpid();
    if(stats_path && !create_stats(stats_path)) {fail(STATS);goto done;}
    if(!path || !hash || !stats_path || !image_hash || strcmp(path,code_path) ||
       strcmp(hash,code_sha) || strcmp(image_hash,engine_sha)) {fail(CONFIG);goto done;}
    char executable[4096];ssize_t length=readlink("/proc/self/exe",executable,sizeof(executable));
    if(length!=(ssize_t)strlen(engine_path) || memcmp(executable,engine_path,(size_t)length)) {
        fail(ENGINE_FILE);goto done;
    }
    crypto_handle=dlopen("/usr/lib/x86_64-linux-gnu/libcrypto.so.3",RTLD_NOW|RTLD_LOCAL);
    if(!crypto_handle || !(sha256=(sha256_fn)dlsym(crypto_handle,"SHA256"))) {fail(CRYPTO);goto done;}
    void *engine_image=sealed_copy(engine_path,ENGINE_BYTES,1);
    if(!engine_image) {fail(ENGINE_FILE);goto done;}
    int correct=digest_matches(engine_image,ENGINE_BYTES,engine_sha);
    munmap(engine_image,ENGINE_BYTES);
    if(!correct) {fail(ENGINE_HASH);goto done;}
    put(ENGINE_VERIFIED,1);
    dl_iterate_phdr(find_main,NULL);
    if(!main_found || main_base>UINTPTR_MAX-0x18f4778) {fail(MAIN_IMAGE);goto done;}
    get_device=dlsym(RTLD_NEXT,"hipGetDevice");
    is_capturing=dlsym(RTLD_NEXT,"hipStreamIsCapturing");
    module_load=dlsym(RTLD_NEXT,"hipModuleLoadData");
    module_function=dlsym(RTLD_NEXT,"hipModuleGetFunction");
    module_launch=dlsym(RTLD_NEXT,"hipModuleLaunchKernel");
    if(!get_device || !is_capturing || !module_load || !module_function || !module_launch) {
        fail(SYMBOLS);goto done;
    }
    set_state(ARMED);
done:
    errno=saved;
}
static launch_fn native_target(void) {
    uintptr_t address=atomic_load_explicit(&native_address,memory_order_acquire);
    if(!address) {
        void *found=dlsym(RTLD_NEXT,"hipLaunchKernel");
        /* The sealed installed engine/runtime requires this mandatory target.
         * No fabricated HIP result or second launch is a valid substitute. */
        if(!found) _exit(127);
        address=(uintptr_t)found;
        atomic_store_explicit(&native_address,address,memory_order_release);
    }
    return (launch_fn)address;
}
static int device_and_capture_ok(hipStream_t stream) {
    int device=-1,result=get_device(&device);
    status(DEVICE_STATUS,result);status(DEVICE,device);
    if(result || device!=0) return 0;
    int capture=-1;result=is_capturing(stream,&capture);
    status(CAPTURE_STATUS,result);status(CAPTURE_STATE,capture);
    return !result && capture==0;
}
static int prepare_module(void) {
    int ready;
    if(pthread_mutex_trylock(&init_lock)) {add(BUSY_REENTRANT);return 0;}
    if(atomic_load_explicit(&state,memory_order_acquire)==ARMED) {
        set_state(INITIALIZING);add(INIT_ATTEMPTS);
        code_image=sealed_copy(code_path,CODE_BYTES,0);
        if(!code_image) {fail(CODE_FILE);goto done;}
        put(FILE_BYTES,CODE_BYTES);
        if(!digest_matches(code_image,CODE_BYTES,code_sha)) {fail(CODE_HASH);goto done;}
        put(CODE_VERIFIED,1);
        int result=module_load(&module,code_image);status(LOAD_STATUS,result);
        if(result || !module) {fail(MODULE_LOAD);goto done;}
        put(MODULE_LOADED,1);
        result=module_function(&function,module,kernel_name);status(LOOKUP_STATUS,result);
        if(result || !function) {fail(FUNCTION_LOOKUP);goto done;}
        put(FUNCTION_RESOLVED,1);set_state(READY);
    }
done:
    ready=atomic_load_explicit(&state,memory_order_acquire)==READY;
    pthread_mutex_unlock(&init_lock);return ready;
}

#define CALLER ((uintptr_t)__builtin_extract_return_addr(__builtin_return_address(0)))
hipError_t hipLaunchKernel(const void *fn,dim3 grid,dim3 block,void **args,
                           size_t shared,hipStream_t stream) {
    int saved=errno;launch_fn stock=native_target();
    int owned=owner && getpid()==owner;
    if(owned) add(HOOK_CALLS);
    int eligible=owned && (uintptr_t)fn==main_base+0x18f4778 && CALLER==main_base+0x180e5ec &&
        grid.x==256 && grid.y==1 && grid.z==1 && block.x==256 && block.y==1 && block.z==1 &&
        shared==0 && stream==NULL && args!=NULL;
    if(owned) {if(eligible) add(ELIGIBLE);else add(INELIGIBLE);}
    unsigned nested=depth++;
    int candidate=0;
    unsigned current=atomic_load_explicit(&state,memory_order_acquire);
    if(eligible && nested) add(BUSY_REENTRANT);
    else if(eligible && current==INITIALIZING) add(BUSY_REENTRANT);
    else if(eligible && (current==ARMED || current==READY) && device_and_capture_ok(stream)) {
        candidate=current==READY || prepare_module();
        /* Loading can take time: recheck both conditions before dispatch.
         * A query still cannot exclude a concurrent capture-transition race. */
        if(candidate) candidate=device_and_capture_ok(stream) &&
            atomic_load_explicit(&state,memory_order_acquire)==READY;
    }
    int result,native_errno;
    errno=saved;
    if(candidate) {
        add(ATTEMPTS);
        result=module_launch(function,grid.x,grid.y,grid.z,block.x,block.y,block.z,
                             (unsigned)shared,stream,args,NULL);
        native_errno=errno;status(LAST_CANDIDATE,result);
        if(result) {add(CANDIDATE_ERRORS);put(DISABLED_AFTER_ERROR,1);fail(CANDIDATE_ERROR);}
        /* Once attempted, return that exact status. Never retry with stock. */
    } else {
        if(owned) {add(STOCK_CALLS);if(eligible) add(ELIGIBLE_STOCK);}
        result=stock(fn,grid,block,args,shared,stream);
        native_errno=errno;
        if(owned) {status(LAST_STOCK,result);if(result) add(STOCK_ERRORS);}
    }
    depth--;errno=native_errno;return result;
}

/* Module, immutable code image, libcrypto handle and stats mapping intentionally
 * remain live until normal process exit. No DSO destructor calls HIP or unloads
 * a module while submitted work could still reference it. */
