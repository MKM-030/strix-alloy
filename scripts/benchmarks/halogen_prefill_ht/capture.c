/* Source-only, default-off frozen ordinary Prefill HT capture for Halogen0.16.2.
 * Observer only: original FC and packed helper always forward exactly once.
 * No candidate calls, GPU allocations, writes to tensor data, or timing claims.
 * Root owns build, review, pinned receipt, allocation lifetime and engine lifecycle.
 * See README.md before activation. Linux x86-64/SysV ABI only.
 */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <elf.h>
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <limits.h>
#include <link.h>
#include <openssl/evp.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

#if !defined(__linux__) || !defined(__x86_64__)
#error Linux x86-64 only
#endif
#define ENGINE_SHA "ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b"
#define ENGINE_BYTES ((off_t)26052768)
#define FC_RVA ((uintptr_t)0x178cf90)
#define FC_OFFSET ((off_t)0x178bf90)
#define FC_BYTES ((size_t)8215)
#define FC_SHA "f8f9d77041011251d11d0b97d7298926aa053d5435310826a00c408e5bff24e9"
#define PACKED_RVA ((uintptr_t)0x17f8280)
#define PACKED_OFFSET ((off_t)0x17f7280)
#define PACKED_BYTES ((size_t)2913)
#define PACKED_SHA "0624974055273bd4dee85357d971b3a4b32930d96c03bcd833b0fd2d860e48f3"
#define ORDINARY_QKV_RETURN ((uintptr_t)0x1791400)
#define FC_PACKED_RETURN ((uintptr_t)0x178cfc0)
#define LT_RETURN ((uintptr_t)0x18c68ec)
#define ROUTER_RVA ((uintptr_t)0x18db4d8)
#define CAPACITY_RVA ((uintptr_t)0x18dcf28)
#define ROTATED_RVA ((uintptr_t)0x18dcf30)
#define PARTIAL_RVA ((uintptr_t)0x18dcf38)
#define DESC_BYTES ((size_t)0x78)
#define X_BYTES ((size_t)41943040)
#define Y_BYTES ((size_t)167772160)
#define SIGNS_BYTES ((size_t)5120)
#define SCALES_BYTES ((size_t)20480)
#define PACKED_LIMIT ((size_t)67108864)
#define TRACE_BYTE_LIMIT ((size_t)314572800)
#define TRACE_FILE_LIMIT 16U
#define LAUNCH_LIMIT 16U
static const char trace_prefix[]="/tmp/alloy-prefill-ht-capture-";
static const char arm_content[]="ordinary-qkv8192-v1-ready\n";
static const char harvest_content[]="ordinary-qkv8192-v1-harvest\n";
static const unsigned char fc_signature[32]={
    0x55,0x41,0x57,0x41,0x56,0x41,0x55,0x41,0x54,0x53,0x48,0x83,0xec,0x48,0x4c,0x89,
    0xcb,0x45,0x89,0xc5,0x89,0xcd,0x49,0x89,0xd6,0x49,0x89,0xf7,0x49,0x89,0xfc,0x4c
};
static const unsigned char packed_signature[32]={
    0x55,0x41,0x57,0x41,0x56,0x41,0x55,0x41,0x54,0x53,0x48,0x81,0xec,0xe8,0,0,
    0,0x44,0x89,0xcd,0x45,0x89,0xc1,0x48,0x89,0x54,0x24,0x28,0x48,0x89,0x74,0x24
};
typedef void (*fc_fn)(void *,const void *,void *,int,int,int64_t);
typedef bool (*packed_fn)(void *,const void *,void *,bool,int,int,int64_t);
typedef int (*sync_fn)(void);
typedef int (*copy_fn)(void *,const void *,size_t,int);
typedef int (*range_fn)(void **,size_t *,void *);
typedef struct {unsigned x,y,z;} hip_dim3;
typedef int (*launch_fn)(const void *,hip_dim3,hip_dim3,void **,size_t,void *);
typedef int (*matmul_fn)(void *,void *,const void *,const void *,void *,const void *,void *,
    const void *,const void *,void *,void *,void *,const void *,void *,size_t,void *);
struct receipt {
    char tensor[128],checkpoint_sha[65],index_sha[65];
    unsigned store,variant,mode;
    size_t packed_bytes;
};
struct fc_scope {
    void *descriptor;const void *x;void *y;
    int n,m;int64_t k;
    uintptr_t caller;
    struct fc_scope *previous;
};
struct launch_record {
    uintptr_t caller,function,stream;hip_dim3 grid,block;
    size_t shared;int result;
};
struct sample {
    unsigned reserved,completed,inputs_ready,output_ready,packed_calls,nested_calls;
    unsigned observer_syncs,observer_copies,launches,lt_calls,nondefault_streams;
    int original_result,lt_result;
    uintptr_t descriptor,x,y,packed,signs,scales,diagnostic_name,fc_caller,packed_caller;
    uintptr_t router_before,router_after,rotated_before,rotated_after,partial_before,partial_after;
    uint64_t capacity_before,capacity_after;
    uintptr_t lt_handle,lt_desc,lt_a,lt_b,lt_c,lt_d,lt_algorithm,lt_workspace,lt_stream;
    size_t lt_workspace_bytes;
    uintptr_t allocation_base_before[5],allocation_base_after[5];
    size_t allocation_bytes_before[5],allocation_bytes_after[5];
    unsigned allocation_snapshot_before,allocation_snapshot_after,observer_range_queries;
    unsigned char descriptor_before[DESC_BYTES],descriptor_after[DESC_BYTES];
    unsigned char *staging,*packed_host,*signs_host,*scales_host,*x_host,*y_host;
    struct launch_record launch[LAUNCH_LIMIT];
    const char *error;
};
static struct receipt receipt;
static struct sample sample;
static fc_fn original_fc;
static packed_fn original_packed;
static sync_fn hip_sync;
static copy_fn hip_copy;
static range_fn hip_range;
static launch_fn real_launch;
static matmul_fn real_matmul;
static uintptr_t engine_base;
static int trace_dir=-1;
static unsigned trace_files,fc_in_flight,matching_fc_calls;
static size_t trace_bytes;
static char receipt_sha[65];
static const char *trace_error;
static _Thread_local struct fc_scope *active_fc;
static _Thread_local struct sample *active_sample;
static _Thread_local unsigned packed_depth;
static pthread_once_t symbols_once=PTHREAD_ONCE_INIT;
static pthread_mutex_t trace_mutex=PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t trace_idle=PTHREAD_COND_INITIALIZER;
static _Atomic int initialized,armed_once,harvested;

static _Noreturn void fatal(const char *reason) {
    dprintf(STDERR_FILENO,"[prefill-ht-capture] fatal reason=%s errno=%d\n",reason,errno);
    _exit(79);
}
static void disable(const char *reason) {if (!trace_error) trace_error=reason;}
static void sample_error(const char *reason) {if (!sample.error) sample.error=reason;}
static int mapped_span(uintptr_t address,size_t bytes,const char *wanted) {
    if (!address || !bytes || bytes>UINTPTR_MAX-address) return 0;
    FILE *file=fopen("/proc/self/maps","re");
    if (!file) return 0;
    char line[4096],perms[5];unsigned long low,high;int found=0;
    while (fgets(line,sizeof line,file)) {
        if (sscanf(line,"%lx-%lx %4s",&low,&high,perms)!=3) continue;
        if (address>=low && address+bytes<=high &&
            (wanted?!strcmp(perms,wanted):perms[0]=='r')) {found=1;break;}
    }
    int failed=ferror(file);
    if (fclose(file)) failed=1;
    return failed?0:found;
}
static int mapped_read(uintptr_t p,size_t bytes) {return mapped_span(p,bytes,NULL);}
static uint64_t u64_at(const void *p,size_t offset) {
    uint64_t v;memcpy(&v,(const unsigned char *)p+offset,sizeof v);return v;
}
static uint32_t u32_at(const void *p,size_t offset) {
    uint32_t v;memcpy(&v,(const unsigned char *)p+offset,sizeof v);return v;
}
static int is_sha(const char *p) {
    if (!p || strlen(p)!=64) return 0;
    for (unsigned i=0;i<64;i++) if (!((p[i]>='0' && p[i]<='9') || (p[i]>='a' && p[i]<='f'))) return 0;
    return 1;
}
static int buffer_hash(const void *data,size_t bytes,char hex[65]) {
    unsigned char digest[32];unsigned n=0;
    if (EVP_Digest(data,bytes,digest,&n,EVP_sha256(),NULL)!=1 || n!=sizeof digest) return 0;
    for (size_t i=0;i<sizeof digest;i++) snprintf(hex+i*2,3,"%02x",(unsigned)digest[i]);
    return 1;
}
static int append_bytes(int fd,const void *data,size_t bytes) {
    if (trace_bytes>TRACE_BYTE_LIMIT || bytes>TRACE_BYTE_LIMIT-trace_bytes) return 0;
    const unsigned char *at=data;
    while (bytes) {
        ssize_t n=write(fd,at,bytes);
        if (n<0 && errno==EINTR) continue;
        if (n<=0) return 0;
        at+=n;bytes-=(size_t)n;trace_bytes+=(size_t)n;
    }
    return 1;
}
static int save_file(const char *name,const void *data,size_t bytes) {
    if (trace_files>=TRACE_FILE_LIMIT || trace_bytes>TRACE_BYTE_LIMIT || bytes>TRACE_BYTE_LIMIT-trace_bytes) return 0;
    int fd=openat(trace_dir,name,O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC|O_NOFOLLOW,0600);
    if (fd<0) return 0;
    trace_files++;
    struct stat st;
    int ok=!fstat(fd,&st) && S_ISREG(st.st_mode) && st.st_uid==geteuid() && st.st_nlink==1 &&
        (st.st_mode&0777)==0600 && st.st_size==0 && append_bytes(fd,data,bytes);
    if (fsync(fd)) ok=0;
    if (close(fd)) ok=0;
    return ok;
}
static int stable_stat(const struct stat *a,const struct stat *b) {
    return a->st_dev==b->st_dev && a->st_ino==b->st_ino && a->st_size==b->st_size &&
        a->st_mtim.tv_sec==b->st_mtim.tv_sec && a->st_mtim.tv_nsec==b->st_mtim.tv_nsec &&
        a->st_ctim.tv_sec==b->st_ctim.tv_sec && a->st_ctim.tv_nsec==b->st_ctim.tv_nsec;
}
static int owned_read(const char *name,char *out,size_t cap,size_t *bytes) {
    int fd=openat(trace_dir,name,O_RDONLY|O_CLOEXEC|O_NOFOLLOW);
    if (fd<0) return errno==ENOENT?0:-1;
    struct stat a,b;
    int ok=!fstat(fd,&a) && S_ISREG(a.st_mode) && a.st_uid==geteuid() && a.st_nlink==1 &&
        (a.st_mode&0777)==0600 && a.st_size>0 && (uint64_t)a.st_size<cap;
    ssize_t got=-1;
    if (ok) {do {got=pread(fd,out,(size_t)a.st_size+1,0);} while (got<0 && errno==EINTR);}
    if (!ok || got!=a.st_size || fstat(fd,&b) || !stable_stat(&a,&b)) ok=0;
    if (close(fd)) ok=0;
    if (!ok) return -1;
    *bytes=(size_t)got;out[*bytes]=0;return 1;
}
static int trigger(const char *name,const char *wanted,size_t bytes) {
    char text[64];size_t got=0;int status=owned_read(name,text,sizeof text,&got);
    if (status!=1) return status;
    return got==bytes && !memcmp(text,wanted,bytes)?1:-1;
}
static int load_receipt(void) {
    char text[1024],canonical[1024],hash[65];size_t bytes=0;int end=0;
    if (owned_read("tensor.receipt",text,sizeof text,&bytes)!=1 ||
        !buffer_hash(text,bytes,hash) || strcmp(hash,receipt_sha)) return 0;
    struct receipt candidate={0};
    int got=sscanf(text,
        "schema=ordinary-qkv8192-v1\ntensor=%127[A-Za-z0-9_.]\nstore=%u\nvariant=%u\nmode=%u\n"
        "N=10240\nK=2560\npacked_bytes=%zu\ncheckpoint_sha256=%64[0-9a-f]\nindex_sha256=%64[0-9a-f]\n%n",
        candidate.tensor,&candidate.store,&candidate.variant,&candidate.mode,&candidate.packed_bytes,
        candidate.checkpoint_sha,candidate.index_sha,&end);
    if (got!=7 || end!=(int)bytes || !candidate.tensor[0] ||
        (candidate.mode!=3 && candidate.mode!=4) || !candidate.packed_bytes ||
        candidate.packed_bytes>PACKED_LIMIT || !is_sha(candidate.checkpoint_sha) || !is_sha(candidate.index_sha)) return 0;
    int n=snprintf(canonical,sizeof canonical,
        "schema=ordinary-qkv8192-v1\ntensor=%s\nstore=%u\nvariant=%u\nmode=%u\n"
        "N=10240\nK=2560\npacked_bytes=%zu\ncheckpoint_sha256=%s\nindex_sha256=%s\n",
        candidate.tensor,candidate.store,candidate.variant,candidate.mode,candidate.packed_bytes,
        candidate.checkpoint_sha,candidate.index_sha);
    if (n<=0 || (size_t)n!=bytes || memcmp(text,canonical,bytes)) return 0;
    receipt=candidate;trace_files++;trace_bytes+=bytes;return 1;
}
static int armed_locked(void) {
    if (trace_error || atomic_load(&harvested)) return 0;
    if (atomic_load(&armed_once)) return 1;
    int armed=trigger("armed",arm_content,sizeof arm_content-1);
    if (armed<0) {disable("arm-content");return 0;}
    if (!armed) return 0;
    if (!load_receipt()) {disable("receipt-missing-or-unqualified");return 0;}
    atomic_store(&armed_once,1);return 1;
}
static void resolve_symbols(void) {
    hip_sync=(sync_fn)dlsym(RTLD_NEXT,"hipDeviceSynchronize");
    hip_copy=(copy_fn)dlsym(RTLD_NEXT,"hipMemcpy");
    hip_range=(range_fn)dlsym(RTLD_NEXT,"hipMemGetAddressRange");
    real_launch=(launch_fn)dlsym(RTLD_NEXT,"hipLaunchKernel");
    real_matmul=(matmul_fn)dlsym(RTLD_NEXT,"hipblasLtMatmul");
}
static int span(uintptr_t p,size_t bytes) {return p && bytes && bytes<=UINTPTR_MAX-p;}
static int separate(uintptr_t a,size_t an,uintptr_t b,size_t bn) {return a+an<=b || b+bn<=a;}
static int allocations(struct sample *s,int after) {
    uintptr_t pointers[5]={s->packed,s->signs,s->scales,s->x,s->y};
    size_t sizes[5]={receipt.packed_bytes,SIGNS_BYTES,SCALES_BYTES,X_BYTES,Y_BYTES};
    for (unsigned i=0;i<5;i++) {
        void *base=NULL;size_t bytes=0;
        s->observer_range_queries++;
        if (hip_range(&base,&bytes,(void *)pointers[i]) || !span((uintptr_t)base,bytes) ||
            pointers[i]<(uintptr_t)base || pointers[i]-(uintptr_t)base>bytes ||
            sizes[i]>bytes-(pointers[i]-(uintptr_t)base)) {
            sample_error(after?"allocation-range-after":"allocation-range-before");return 0;
        }
        if (after) {
            s->allocation_base_after[i]=(uintptr_t)base;s->allocation_bytes_after[i]=bytes;
            if (s->allocation_base_before[i]!=(uintptr_t)base || s->allocation_bytes_before[i]!=bytes) {
                sample_error("allocation-range-changed");return 0;
            }
        } else {s->allocation_base_before[i]=(uintptr_t)base;s->allocation_bytes_before[i]=bytes;}
    }
    if (after) s->allocation_snapshot_after=1;else s->allocation_snapshot_before=1;
    return 1;
}
static int globals(uintptr_t *router,uint64_t *capacity,uintptr_t *rotated,uintptr_t *partial) {
    if (!mapped_read(engine_base+ROUTER_RVA,sizeof(uintptr_t)) ||
        !mapped_read(engine_base+CAPACITY_RVA,3*sizeof(uint64_t))) return 0;
    *router=(uintptr_t)u64_at((const void *)(engine_base+ROUTER_RVA),0);
    *capacity=u64_at((const void *)(engine_base+CAPACITY_RVA),0);
    *rotated=(uintptr_t)u64_at((const void *)(engine_base+ROTATED_RVA),0);
    *partial=(uintptr_t)u64_at((const void *)(engine_base+PARTIAL_RVA),0);
    return 1;
}
static int observe_entry(void *d,const void *x,void *y,uintptr_t caller) {
    struct sample *s=&sample;
    s->descriptor=(uintptr_t)d;s->x=(uintptr_t)x;s->y=(uintptr_t)y;
    s->fc_caller=active_fc->caller;s->packed_caller=caller;
    if (!mapped_read((uintptr_t)d,DESC_BYTES)) {sample_error("descriptor-host-span");return 0;}
    memcpy(s->descriptor_before,d,DESC_BYTES);
    s->packed=(uintptr_t)u64_at(s->descriptor_before,0x30);
    s->signs=(uintptr_t)u64_at(s->descriptor_before,0x38);
    s->scales=(uintptr_t)u64_at(s->descriptor_before,0x40);
    s->diagnostic_name=(uintptr_t)u64_at(s->descriptor_before,0x70);
    size_t name_bytes=strlen(receipt.tensor)+1;
    if (u32_at(s->descriptor_before,0x48)!=receipt.mode || u32_at(s->descriptor_before,0x4c)!=10240 ||
        u64_at(s->descriptor_before,0x50)!=2560 || !mapped_read(s->diagnostic_name,name_bytes) ||
        memcmp((const void *)s->diagnostic_name,receipt.tensor,name_bytes)) {
        sample_error("descriptor-receipt-identity");return 0;
    }
    uintptr_t pointers[5]={s->packed,s->signs,s->scales,s->x,s->y};
    size_t sizes[5]={receipt.packed_bytes,SIGNS_BYTES,SCALES_BYTES,X_BYTES,Y_BYTES};
    for (unsigned i=0;i<5;i++) {
        if (!span(pointers[i],sizes[i]) || (pointers[i]&1)) {sample_error("device-span-arithmetic");return 0;}
        for (unsigned j=0;j<i;j++) if (!separate(pointers[i],sizes[i],pointers[j],sizes[j])) {
            sample_error("unexpected-tensor-alias");return 0;
        }
    }
    if (!globals(&s->router_before,&s->capacity_before,&s->rotated_before,&s->partial_before)) {
        sample_error("source-global-span");return 0;
    }
    /* Allocation ranges are queried at completed boundaries below. Root supplies
     * the independent tensor metadata and exclusive, immutable process lifetime. */
    if (pthread_once(&symbols_once,resolve_symbols) || !hip_sync || !hip_copy || !hip_range) {
        sample_error("capture-symbols");return 0;
    }
    size_t bytes=receipt.packed_bytes+SIGNS_BYTES+SCALES_BYTES+X_BYTES+Y_BYTES;
    s->staging=malloc(bytes);
    if (!s->staging) {sample_error("host-staging-allocation");return 0;}
    s->packed_host=s->staging;s->signs_host=s->packed_host+receipt.packed_bytes;
    s->scales_host=s->signs_host+SIGNS_BYTES;s->x_host=s->scales_host+SCALES_BYTES;
    s->y_host=s->x_host+X_BYTES;
    s->observer_syncs++;
    if (hip_sync()) {sample_error("pre-original-sync");return 0;}
    if (!allocations(s,0)) return 0;
    void *dest[4]={s->packed_host,s->signs_host,s->scales_host,s->x_host};
    for (unsigned i=0;i<4;i++) {
        s->observer_copies++;
        if (hip_copy(dest[i],(const void *)pointers[i],sizes[i],2)) {
            sample_error("input-device-copy");return 0;
        }
    }
    s->inputs_ready=1;return 1;
}
static void observe_output(void *d) {
    struct sample *s=&sample;
    if (!s->inputs_ready || s->error) return;
    if (!s->original_result) {sample_error("packed-original-declined");return;}
    s->observer_syncs++;
    if (hip_sync()) {sample_error("post-original-sync");return;}
    if (!mapped_read((uintptr_t)d,DESC_BYTES) ||
        !globals(&s->router_after,&s->capacity_after,&s->rotated_after,&s->partial_after)) {
        sample_error("post-original-host-span");return;
    }
    memcpy(s->descriptor_after,d,DESC_BYTES);
    if (memcmp(s->descriptor_before+0x30,s->descriptor_after+0x30,0x28) ||
        u64_at(s->descriptor_before,0x70)!=u64_at(s->descriptor_after,0x70)) {
        sample_error("descriptor-identity-changed");return;
    }
    if (!allocations(s,1)) return;
    s->observer_copies++;
    if (hip_copy(s->y_host,(const void *)s->y,Y_BYTES,2)) {sample_error("reference-device-copy");return;}
    s->output_ready=1;
}
static void tapped_fc(void *d,const void *x,void *y,int n,int m,int64_t k) {
    int incoming_errno=errno;
    uintptr_t address=(uintptr_t)__builtin_return_address(0);
    uintptr_t caller=address>=engine_base?address-engine_base:UINTPTR_MAX;
    if (!atomic_load(&initialized)) {errno=incoming_errno;original_fc(d,x,y,n,m,k);return;}
    struct fc_scope scope={d,x,y,n,m,k,caller,active_fc};active_fc=&scope;
    if (pthread_mutex_lock(&trace_mutex)) fatal("fc-entry-mutex");
    if (fc_in_flight && sample.reserved && !sample.completed) disable("overlapping-fc-calls");
    fc_in_flight++;
    if (caller==ORDINARY_QKV_RETURN && n==10240 && m==8192 && k==2560) matching_fc_calls++;
    (void)pthread_mutex_unlock(&trace_mutex);
    errno=incoming_errno;original_fc(d,x,y,n,m,k);
    int result_errno=errno;
    active_fc=scope.previous;
    if (pthread_mutex_lock(&trace_mutex)) fatal("fc-exit-mutex");
    fc_in_flight--;
    if (!fc_in_flight) (void)pthread_cond_broadcast(&trace_idle);
    (void)pthread_mutex_unlock(&trace_mutex);
    errno=result_errno;
}
static bool tapped_packed(void *d,const void *x,void *y,bool out_f32,int n,int m,int64_t k) {
    int incoming_errno=errno;
    uintptr_t address=(uintptr_t)__builtin_return_address(0);
    uintptr_t caller=address>=engine_base?address-engine_base:UINTPTR_MAX;
    struct sample *selected=NULL;
    if (atomic_load(&initialized)) {
        if (pthread_mutex_lock(&trace_mutex)) fatal("packed-entry-mutex");
        struct fc_scope *scope=active_fc;
        if (!packed_depth && scope && !scope->previous && scope->caller==ORDINARY_QKV_RETURN &&
            caller==FC_PACKED_RETURN && !out_f32 && n==10240 && m==8192 && k==2560 &&
            d==scope->descriptor && x==scope->x && y==scope->y && n==scope->n && m==scope->m && k==scope->k &&
            !sample.reserved && armed_locked()) {
            sample.reserved=1;selected=&sample;
            if (fc_in_flight!=1) sample_error("overlapping-fc-calls");
            if (!sample.error) (void)observe_entry(d,x,y,caller);
        } else if (active_sample) {active_sample->nested_calls++;sample_error("nested-packed-call");}
        (void)pthread_mutex_unlock(&trace_mutex);
    }
    struct sample *saved=active_sample;active_sample=selected;packed_depth++;
    errno=incoming_errno;
    bool result=original_packed(d,x,y,out_f32,n,m,k);
    int result_errno=errno;
    packed_depth--;active_sample=saved;
    if (selected) {
        if (pthread_mutex_lock(&trace_mutex)) fatal("packed-exit-mutex");
        selected->packed_calls++;selected->original_result=result?1:0;
        observe_output(d);selected->completed=1;
        if (!selected->output_ready) sample_error("reference-incomplete");
        if (selected->error) disable(selected->error);
        (void)pthread_mutex_unlock(&trace_mutex);
    }
    errno=result_errno;return result;
}
int hipLaunchKernel(const void *function,hip_dim3 grid,hip_dim3 block,void **args,size_t shared,void *stream) {
    int incoming_errno=errno;
    if (pthread_once(&symbols_once,resolve_symbols) || !real_launch) fatal("launch-symbol");
    struct sample *s=active_sample;unsigned index=0;
    if (s) {
        index=s->launches++;
        if (stream) s->nondefault_streams++;
        if (index>=LAUNCH_LIMIT) sample_error("kernel-record-limit");
        else {
            uintptr_t address=(uintptr_t)__builtin_return_address(0);
            struct launch_record *r=&s->launch[index];
            r->caller=address>=engine_base?address-engine_base:UINTPTR_MAX;
            r->function=(uintptr_t)function;r->grid=grid;r->block=block;
            r->shared=shared;r->stream=(uintptr_t)stream;
        }
    }
    errno=incoming_errno;int result=real_launch(function,grid,block,args,shared,stream);int result_errno=errno;
    if (s) {
        if (index<LAUNCH_LIMIT) s->launch[index].result=result;
        if (result) sample_error("original-kernel-submission-result");
    }
    errno=result_errno;return result;
}
int hipblasLtMatmul(void *handle,void *desc,const void *alpha,const void *a,void *a_desc,
    const void *b,void *b_desc,const void *beta,const void *c,void *c_desc,void *d,void *d_desc,
    const void *algo,void *workspace,size_t bytes,void *stream) {
    int incoming_errno=errno;
    if (pthread_once(&symbols_once,resolve_symbols) || !real_matmul) fatal("matmul-symbol");
    struct sample *s=active_sample;
    if (s) {
        uintptr_t address=(uintptr_t)__builtin_return_address(0);
        uintptr_t caller=address>=engine_base?address-engine_base:UINTPTR_MAX;
        s->lt_calls++;
        if (stream) s->nondefault_streams++;
        if (s->lt_calls!=1 || caller!=LT_RETURN) sample_error("library-submission-contract");
        else {
            s->lt_handle=(uintptr_t)handle;s->lt_desc=(uintptr_t)desc;
            s->lt_a=(uintptr_t)a;s->lt_b=(uintptr_t)b;s->lt_c=(uintptr_t)c;s->lt_d=(uintptr_t)d;
            s->lt_algorithm=(uintptr_t)algo;s->lt_workspace=(uintptr_t)workspace;
            s->lt_workspace_bytes=bytes;s->lt_stream=(uintptr_t)stream;
        }
    }
    errno=incoming_errno;
    int result=real_matmul(handle,desc,alpha,a,a_desc,b,b_desc,beta,c,c_desc,d,d_desc,algo,workspace,bytes,stream);
    int result_errno=errno;
    if (s) {s->lt_result=result;if (result) sample_error("original-library-submission-result");}
    errno=result_errno;return result;
}
static void harvest(int requested) {
    if (pthread_mutex_lock(&trace_mutex)) fatal("harvest-mutex");
    atomic_store(&harvested,1);
    if (requested<0) disable("harvest-content");
    while (fc_in_flight) if (pthread_cond_wait(&trace_idle,&trace_mutex)) fatal("harvest-wait");
    struct sample *s=&sample;
    if (!s->reserved || !s->completed || !s->inputs_ready || !s->output_ready || s->packed_calls!=1) disable("incomplete-sample");
    char hashes[5][65]={{0}};
    const char *names[5]={"packed.bin","signs-u16.bin","scales-u16.bin","x-u16.bin","y-reference-u16.bin"};
    const void *data[5]={s->packed_host,s->signs_host,s->scales_host,s->x_host,s->y_host};
    size_t sizes[5]={receipt.packed_bytes,SIGNS_BYTES,SCALES_BYTES,X_BYTES,Y_BYTES};
    if (s->inputs_ready && s->output_ready) {
        for (unsigned i=0;i<5;i++) if (!buffer_hash(data[i],sizes[i],hashes[i]) || !save_file(names[i],data[i],sizes[i])) disable("fixture-export");
        if (!save_file("descriptor-before.bin",s->descriptor_before,DESC_BYTES) ||
            !save_file("descriptor-after.bin",s->descriptor_after,DESC_BYTES)) disable("descriptor-export");
    }
    char records[16384];
    int n=snprintf(records,sizeof records,
        "{\"schema\":1,\"mode\":\"ordinary-qkv8192-v1\",\"engine_sha256\":\"%s\","
        "\"receipt_sha256\":\"%s\",\"tensor\":\"%s\",\"store\":%u,\"variant\":%u,\"descriptor_mode\":%u,"
        "\"checkpoint_sha256\":\"%s\",\"index_sha256\":\"%s\",\"M\":8192,\"N\":10240,\"K\":2560,"
        "\"output_float32\":false,\"instrumented\":true,\"timing_claim\":false,\"candidate_calls\":0,"
        "\"packed_original_calls\":%u,\"matching_fc_calls\":%u,\"reserved\":%s,\"completed\":%s,"
        "\"inputs_ready\":%s,\"output_ready\":%s,\"original_result\":%d,\"nested_calls\":%u,"
        "\"descriptor\":\"0x%" PRIxPTR "\",\"diagnostic_name_pointer\":\"0x%" PRIxPTR "\","
        "\"fc_caller_rva\":\"0x%" PRIxPTR "\",\"packed_caller_rva\":\"0x%" PRIxPTR "\","
        "\"packed_pointer\":\"0x%" PRIxPTR "\",\"signs_pointer\":\"0x%" PRIxPTR "\","
        "\"scales_pointer\":\"0x%" PRIxPTR "\",\"x_pointer\":\"0x%" PRIxPTR "\",\"y_pointer\":\"0x%" PRIxPTR "\","
        "\"router_before\":\"0x%" PRIxPTR "\",\"router_after\":\"0x%" PRIxPTR "\","
        "\"rotation_capacity_elements_before\":%" PRIu64 ",\"rotation_capacity_elements_after\":%" PRIu64 ","
        "\"rotated_pointer_before\":\"0x%" PRIxPTR "\",\"rotated_pointer_after\":\"0x%" PRIxPTR "\","
        "\"partial_pointer_before\":\"0x%" PRIxPTR "\",\"partial_pointer_after\":\"0x%" PRIxPTR "\","
        "\"allocation_lifetime_exclusive_external\":true,\"allocation_snapshot_before\":%s,\"allocation_snapshot_after\":%s,"
        "\"observer_allocation_range_queries\":%u,\"packed_preparation_branch\":null,"
        "\"library_calls\":%u,\"library_result\":%d,\"library_handle\":\"0x%" PRIxPTR "\","
        "\"library_desc\":\"0x%" PRIxPTR "\",\"library_a\":\"0x%" PRIxPTR "\",\"library_b\":\"0x%" PRIxPTR "\","
        "\"library_c\":\"0x%" PRIxPTR "\",\"library_d\":\"0x%" PRIxPTR "\","
        "\"algorithm_pointer\":\"0x%" PRIxPTR "\",\"algorithm_bytes\":null,\"algorithm_identity\":null,"
        "\"library_workspace\":\"0x%" PRIxPTR "\",\"library_workspace_bytes\":%zu,\"library_stream\":\"0x%" PRIxPTR "\","
        "\"observer_hip_syncs\":%u,\"observer_hip_copies\":%u,\"nondefault_stream_submissions\":%u,"
        "\"files\":[{\"name\":\"packed.bin\",\"bytes\":%zu,\"sha256\":\"%s\"},"
        "{\"name\":\"signs-u16.bin\",\"bytes\":5120,\"sha256\":\"%s\"},"
        "{\"name\":\"scales-u16.bin\",\"bytes\":20480,\"sha256\":\"%s\"},"
        "{\"name\":\"x-u16.bin\",\"bytes\":41943040,\"sha256\":\"%s\"},"
        "{\"name\":\"y-reference-u16.bin\",\"bytes\":167772160,\"sha256\":\"%s\"}],\"launches\":[",
        ENGINE_SHA,receipt_sha,receipt.tensor,receipt.store,receipt.variant,receipt.mode,receipt.checkpoint_sha,receipt.index_sha,
        s->packed_calls,matching_fc_calls,s->reserved?"true":"false",s->completed?"true":"false",
        s->inputs_ready?"true":"false",s->output_ready?"true":"false",s->original_result,s->nested_calls,
        s->descriptor,s->diagnostic_name,s->fc_caller,s->packed_caller,s->packed,s->signs,s->scales,s->x,s->y,
        s->router_before,s->router_after,s->capacity_before,s->capacity_after,s->rotated_before,s->rotated_after,
        s->partial_before,s->partial_after,s->allocation_snapshot_before?"true":"false",s->allocation_snapshot_after?"true":"false",
        s->observer_range_queries,s->lt_calls,s->lt_result,s->lt_handle,s->lt_desc,s->lt_a,s->lt_b,s->lt_c,s->lt_d,
        s->lt_algorithm,s->lt_workspace,s->lt_workspace_bytes,s->lt_stream,s->observer_syncs,s->observer_copies,
        s->nondefault_streams,receipt.packed_bytes,hashes[0],hashes[1],hashes[2],hashes[3],hashes[4]);
    if (n<=0 || n>=(int)sizeof records) fatal("records-format");
    size_t used=(size_t)n;
    for (unsigned i=0;i<s->launches && i<LAUNCH_LIMIT;i++) {
        const struct launch_record *r=&s->launch[i];
        n=snprintf(records+used,sizeof records-used,
            "%s{\"caller_rva\":\"0x%" PRIxPTR "\",\"function_pointer\":\"0x%" PRIxPTR "\","
            "\"stream\":\"0x%" PRIxPTR "\",\"grid\":[%u,%u,%u],\"block\":[%u,%u,%u],\"shared_bytes\":%zu,\"result\":%d}",
            i?",":"",r->caller,r->function,r->stream,r->grid.x,r->grid.y,r->grid.z,r->block.x,r->block.y,r->block.z,r->shared,r->result);
        if (n<=0 || (size_t)n>=sizeof records-used) fatal("launch-record-format");
        used+=(size_t)n;
    }
    n=snprintf(records+used,sizeof records-used,
        "],\"launches_total\":%u,\"allocations\":[",s->launches);
    if (n<=0 || (size_t)n>=sizeof records-used) fatal("allocation-record-prefix");
    used+=(size_t)n;
    const char *allocation_names[5]={"packed","signs","scales","x","y"};
    for (unsigned i=0;i<5;i++) {
        n=snprintf(records+used,sizeof records-used,
            "%s{\"name\":\"%s\",\"base_before\":\"0x%" PRIxPTR "\",\"extent_before_bytes\":%zu,"
            "\"base_after\":\"0x%" PRIxPTR "\",\"extent_after_bytes\":%zu}",
            i?",":"",allocation_names[i],s->allocation_base_before[i],s->allocation_bytes_before[i],
            s->allocation_base_after[i],s->allocation_bytes_after[i]);
        if (n<=0 || (size_t)n>=sizeof records-used) fatal("allocation-record-format");
        used+=(size_t)n;
    }
    n=snprintf(records+used,sizeof records-used,
        "],\"error\":%s%s%s}\n",s->error?"\"":"",s->error?s->error:"null",s->error?"\"":"");
    if (n<=0 || (size_t)n>=sizeof records-used || !save_file("records.json",records,used+(size_t)n)) disable("records-export");
    char complete[1024];
    n=snprintf(complete,sizeof complete,
        "{\"schema\":1,\"mode\":\"ordinary-qkv8192-v1\",\"passed\":%s,\"instrumented\":true,\"timing_claim\":false,"
        "\"candidate_calls\":0,\"packed_original_calls\":%u,\"error\":%s%s%s}\n",
        trace_error?"false":"true",s->packed_calls,trace_error?"\"":"",trace_error?trace_error:"null",trace_error?"\"":"");
    if (n<=0 || n>=(int)sizeof complete || !save_file("complete.json",complete,(size_t)n)) fatal("complete-export");
    free(s->staging);s->staging=NULL;
    (void)pthread_mutex_unlock(&trace_mutex);
}
static void *harvest_worker(void *unused) {
    (void)unused;struct timespec began,now,delay={0,20000000};
    if (clock_gettime(CLOCK_MONOTONIC,&began)) return NULL;
    for (;;) {
        int request=trigger("harvest",harvest_content,sizeof harvest_content-1);
        if (request) {harvest(request);return NULL;}
        if (clock_gettime(CLOCK_MONOTONIC,&now) || now.tv_sec-began.tv_sec>1800) return NULL;
        (void)nanosleep(&delay,NULL);
    }
}
static void verify_hash(int fd,off_t offset,size_t bytes,const char *wanted) {
    EVP_MD_CTX *ctx=EVP_MD_CTX_new();
    if (!ctx || EVP_DigestInit_ex(ctx,EVP_sha256(),NULL)!=1) fatal("hash-init");
    unsigned char buffer[65536],digest[32];unsigned n=0;
    while (bytes) {
        size_t amount=bytes<sizeof buffer?bytes:sizeof buffer;ssize_t got=pread(fd,buffer,amount,offset);
        if (got<0 && errno==EINTR) continue;
        if (got<=0 || (size_t)got>amount || EVP_DigestUpdate(ctx,buffer,(size_t)got)!=1) fatal("hash-read");
        offset+=got;bytes-=(size_t)got;
    }
    if (EVP_DigestFinal_ex(ctx,digest,&n)!=1 || n!=sizeof digest) fatal("hash-final");
    EVP_MD_CTX_free(ctx);char hex[65];
    for (size_t i=0;i<sizeof digest;i++) snprintf(hex+i*2,3,"%02x",(unsigned)digest[i]);
    if (strcmp(hex,wanted)) fatal("hash-mismatch");
}
struct site {uintptr_t base;unsigned fc,packed,router,scratch;};
static int find_site(struct dl_phdr_info *info,size_t unused,void *opaque) {
    (void)unused;if (info->dlpi_name && *info->dlpi_name) return 0;
    struct site *s=opaque;
    if (PARTIAL_RVA+sizeof(uintptr_t)>UINTPTR_MAX-info->dlpi_addr) fatal("base-overflow");
    s->base=info->dlpi_addr;
    for (size_t i=0;i<info->dlpi_phnum;i++) {
        const Elf64_Phdr *p=&info->dlpi_phdr[i];
        if (p->p_type!=PT_LOAD || p->p_vaddr>UINT64_MAX-p->p_memsz || p->p_vaddr>UINT64_MAX-p->p_filesz) continue;
        if (p->p_flags==(PF_R|PF_X)) {
            if (p->p_vaddr<=FC_RVA && FC_RVA+FC_BYTES<=p->p_vaddr+p->p_filesz &&
                p->p_offset+FC_RVA-p->p_vaddr==(uint64_t)FC_OFFSET) s->fc++;
            if (p->p_vaddr<=PACKED_RVA && PACKED_RVA+PACKED_BYTES<=p->p_vaddr+p->p_filesz &&
                p->p_offset+PACKED_RVA-p->p_vaddr==(uint64_t)PACKED_OFFSET) s->packed++;
        }
        if ((p->p_flags&PF_R) && p->p_vaddr<=ROUTER_RVA && ROUTER_RVA+sizeof(uintptr_t)<=p->p_vaddr+p->p_memsz) s->router++;
        if ((p->p_flags&PF_R) && p->p_vaddr<=CAPACITY_RVA && PARTIAL_RVA+sizeof(uintptr_t)<=p->p_vaddr+p->p_memsz) s->scratch++;
    }
    return 1;
}
static void absolute_jump(unsigned char *at,uintptr_t target) {
    const unsigned char prefix[6]={0xff,0x25,0,0,0,0};memcpy(at,prefix,6);memcpy(at+6,&target,8);
}
static uintptr_t install_hook(uintptr_t entry,uintptr_t target,const unsigned char signature[32]) {
    long size=sysconf(_SC_PAGESIZE);
    if (size<=0 || ((unsigned long)size&((unsigned long)size-1))) fatal("page-size");
    uintptr_t page=entry&~((uintptr_t)size-1);unsigned char *thunk=NULL;
    if (entry+32>page+(uintptr_t)size || !mapped_span(page,(size_t)size,"r-xp")) fatal("entry-page");
    for (unsigned i=0;i<256;i++) {
        uintptr_t distance=(uintptr_t)(i/2+1)*0x200000;
        if ((i&1)?page<distance:distance>UINTPTR_MAX-page) continue;
        uintptr_t candidate=(i&1)?page-distance:page+distance;
        void *area=mmap((void *)candidate,(size_t)size,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS|MAP_FIXED_NOREPLACE,-1,0);
        if (area==MAP_FAILED) {if (errno==EEXIST) continue;fatal("thunk-map");}
        if (area!=(void *)candidate) {if (munmap(area,(size_t)size)) fatal("thunk-unmap");fatal("fixed-noreplace");}
        thunk=area;break;
    }
    if (!thunk) fatal("thunk-exhausted");
    absolute_jump(thunk,target);
    /* Both pinned prologues start with complete, non-RIP-relative instructions:
     * push rbp; push r15; push r14 (5 bytes). Preserve the rest unchanged. */
    memcpy(thunk+64,signature,5);absolute_jump(thunk+69,entry+5);
    if (mprotect(thunk,(size_t)size,PROT_READ|PROT_EXEC) || !mapped_span((uintptr_t)thunk,(size_t)size,"r-xp")) fatal("thunk-rx");
    intptr_t relative=(intptr_t)((uintptr_t)thunk-(entry+5));
    if (relative<INT32_MIN || relative>INT32_MAX) fatal("jump-range");
    unsigned char jump[5]={0xe9};int32_t delta=(int32_t)relative;memcpy(jump+1,&delta,4);
    if (mprotect((void *)page,(size_t)size,PROT_READ|PROT_WRITE)) fatal("entry-rw");
    memcpy((void *)entry,jump,5);__builtin___clear_cache((char *)entry,(char *)entry+5);
    if (mprotect((void *)page,(size_t)size,PROT_READ|PROT_EXEC) || !mapped_span(page,(size_t)size,"r-xp")) fatal("entry-rx");
    return (uintptr_t)(thunk+64);
}
static int serving_process(void) {
    int fd=open("/proc/self/cmdline",O_RDONLY|O_CLOEXEC);char command[4096];ssize_t bytes;
    if (fd<0) fatal("cmdline-open");
    do {bytes=read(fd,command,sizeof command);} while (bytes<0 && errno==EINTR);
    int ok=bytes>0 && bytes<(ssize_t)sizeof command && !command[bytes-1];
    if (close(fd)) fatal("cmdline-close");
    if (!ok) fatal("cmdline-read");
    const char *argument=memchr(command,0,(size_t)bytes);
    return argument && argument+1<command+bytes && !strcmp(argument+1,"--ck");
}
__attribute__((constructor)) static void install(void) {
    const char *mode=getenv("HALOGEN_PREFILL_HT_CAPTURE");
    if (!mode) return;
    char name[4096];ssize_t n=readlink("/proc/self/exe",name,sizeof name-1);
    if (n<0 || n>=(ssize_t)sizeof name-1) fatal("executable-name");
    name[n]=0;const char *base=strrchr(name,'/');base=base?base+1:name;
    if (strcmp(base,"flash_serve") || !serving_process()) return;
    const char *directory=getenv("HALOGEN_PREFILL_HT_CAPTURE_DIR"),*sha=getenv("HALOGEN_PREFILL_HT_CAPTURE_RECEIPT_SHA256");
    if (strcmp(mode,"ordinary-qkv8192-v1") || !directory || !is_sha(sha) ||
        strncmp(directory,trace_prefix,sizeof trace_prefix-1) || strlen(directory)!=sizeof trace_prefix-1+32) fatal("configuration");
    for (const char *p=directory+sizeof trace_prefix-1;*p;p++) if (!((*p>='0' && *p<='9') || (*p>='a' && *p<='f'))) fatal("trace-run-id");
    memcpy(receipt_sha,sha,sizeof receipt_sha);
    const char *conflicts[]={"HALOGEN_MTP_FC_QUALITY","HALOGEN_MTP_HIDDEN_RMS_TAP","HALOGEN_MTP_EMBEDDING_CACHE",
        "HALOGEN_MTP_RAW_EMBEDDING_CAPTURE","HALOGEN_MTP_FULL_EVENT_TAP"};
    for (size_t i=0;i<sizeof conflicts/sizeof conflicts[0];i++) if (getenv(conflicts[i])) fatal("other-interposer-mode");
    int fd=open("/proc/self/exe",O_RDONLY|O_CLOEXEC);struct stat before,after;Elf64_Ehdr eh;
    if (fd<0 || fstat(fd,&before) || !S_ISREG(before.st_mode) || before.st_size!=ENGINE_BYTES) fatal("executable-stat");
    if (pread(fd,&eh,sizeof eh,0)!=(ssize_t)sizeof eh || memcmp(eh.e_ident,ELFMAG,SELFMAG) ||
        eh.e_ident[EI_CLASS]!=ELFCLASS64 || eh.e_ident[EI_DATA]!=ELFDATA2LSB || eh.e_type!=ET_DYN || eh.e_machine!=EM_X86_64) fatal("elf-identity");
    verify_hash(fd,0,(size_t)before.st_size,ENGINE_SHA);
    verify_hash(fd,FC_OFFSET,FC_BYTES,FC_SHA);verify_hash(fd,PACKED_OFFSET,PACKED_BYTES,PACKED_SHA);
    if (fstat(fd,&after) || !stable_stat(&before,&after) || close(fd)) fatal("executable-consistency");
    struct site s={0};char hash[65];
    if (dl_iterate_phdr(find_site,&s)!=1 || s.fc!=1 || s.packed!=1 || s.router!=1 || s.scratch!=1 ||
        !mapped_span(s.base+FC_RVA,FC_BYTES,"r-xp") || !mapped_span(s.base+PACKED_RVA,PACKED_BYTES,"r-xp") ||
        memcmp((const void *)(s.base+FC_RVA),fc_signature,32) || memcmp((const void *)(s.base+PACKED_RVA),packed_signature,32) ||
        !buffer_hash((const void *)(s.base+FC_RVA),FC_BYTES,hash) || strcmp(hash,FC_SHA) ||
        !buffer_hash((const void *)(s.base+PACKED_RVA),PACKED_BYTES,hash) || strcmp(hash,PACKED_SHA)) fatal("mapped-signatures");
    engine_base=s.base;
    int tmp=open("/tmp",O_RDONLY|O_DIRECTORY|O_CLOEXEC|O_NOFOLLOW);struct stat st;
    if (tmp<0 || fstat(tmp,&st) || !S_ISDIR(st.st_mode)) fatal("tmp-directory");
    const char *leaf=directory+sizeof "/tmp/"-1;
    if (mkdirat(tmp,leaf,0700)) fatal("trace-mkdir");
    trace_dir=openat(tmp,leaf,O_RDONLY|O_DIRECTORY|O_CLOEXEC|O_NOFOLLOW);
    if (close(tmp)) fatal("tmp-close");
    if (trace_dir<0 || fstat(trace_dir,&st) || !S_ISDIR(st.st_mode) || st.st_uid!=geteuid() || (st.st_mode&0777)!=0700) fatal("trace-directory");
    /* Account for both externally created triggers; receipt is charged on load. */
    trace_files=2;trace_bytes=sizeof arm_content+sizeof harvest_content-2;
    original_packed=(packed_fn)install_hook(s.base+PACKED_RVA,(uintptr_t)tapped_packed,packed_signature);
    original_fc=(fc_fn)install_hook(s.base+FC_RVA,(uintptr_t)tapped_fc,fc_signature);
    char header[4096];
    n=snprintf(header,sizeof header,
        "{\"schema\":1,\"mode\":\"ordinary-qkv8192-v1\",\"engine_sha256\":\"%s\",\"engine_bytes\":26052768,"
        "\"fc_rva\":\"0x178cf90\",\"fc_sha256\":\"%s\",\"packed_rva\":\"0x17f8280\",\"packed_sha256\":\"%s\","
        "\"ordinary_qkv_return_rva\":\"0x1791400\",\"fc_packed_return_rva\":\"0x178cfc0\",\"receipt_sha256\":\"%s\","
        "\"limit\":1,\"M\":8192,\"N\":10240,\"K\":2560,\"output_float32\":false,\"descriptor_bytes\":120,"
        "\"packed_bytes_source\":\"external-pinned-receipt\",\"packed_bytes_limit\":67108864,"
        "\"x_bytes\":41943040,\"y_bytes\":167772160,\"signs_bytes\":5120,\"scales_bytes\":20480,"
        "\"observer_device_allocations\":0,\"tensor_writes\":0,\"host_device_pointer_dereferences\":0,"
        "\"candidate_calls\":0,\"instrumented\":true,\"timing_claim\":false,\"allocation_ranges_required\":true,"
        "\"allocation_lifetime_exclusive_external\":true,"
        "\"post_request_harvest_required\":true,\"file_limit\":16,\"byte_limit\":314572800}\n",
        ENGINE_SHA,FC_SHA,PACKED_SHA,receipt_sha);
    if (n<=0 || n>=(ssize_t)sizeof header || !save_file("activation.json",header,(size_t)n)) fatal("activation-export");
    pthread_t worker;
    if (pthread_create(&worker,NULL,harvest_worker,NULL) || pthread_detach(worker)) fatal("harvest-thread");
    atomic_store(&initialized,1);
}
