/* Source-only, default-off complete ordinary QKV GPU replay, Halogen0.16.2.
 * Root alone reviews/builds/runs and owns exclusive initialized engine lifetime.
 * No host hooks, serving substitution, recapture, model/driver/config changes.
 * Frozen capture inputs only. Stock ALWAYS includes original preparation+GEMM;
 * native ALWAYS includes original rotation+packed multiply+full completion.
 * Cached-original independently prepares one own50-MiB W once outside timing.
 * Exact raw Y qualification precedes each arm's warmup/timing. A native mismatch
 * retires only native; cached-original remains independent. No wider tolerance.
 *
 * Root build: gcc -O2 -Wall -Wextra -Werror -shared -fPIC replay.c
 *   -ldl -lcrypto -pthread -o NEW_REPLAY_SO
 * Env HALOGEN_PREFILL_HT_REPLAY=ordinary-qkv8192-v1,
 * HALOGEN_PREFILL_HT_REPLAY_DIR=/tmp/alloy-prefill-ht-replay-<32lowerhex>,
 * HALOGEN_PREFILL_HT_REPLAY_FIXTURE_DIR=<absolute immutable captured directory>,
 * HALOGEN_PREFILL_HT_REPLAY_MANIFEST_SHA256=<canonical receipt SHA256>.
 * Constructor is inert absent mode. With mode: pins executable/helpers, creates
 * output directory and worker; no hardware call before root's post-ready arm.
 * Root writes owner-only0600 replay.receipt, then exclusive0600 armed containing
 * ordinary-qkv8192-v1-replay-ready\n ONLY after readiness/reserve/exclusivity.
 * Canonical ASCII/LF receipt, eight64-lowercase-hex hashes, final LF:
 * schema=ordinary-qkv8192-replay-v1
 * stock_route=direct-original
 * packed_sha256=...
 * signs_sha256=...
 * scales_sha256=...
 * x_sha256=...
 * y_sha256=...
 * descriptor_sha256=...
 * records_sha256=...
 * complete_sha256=...
 * Exactly one stock/native/cached qualification. Each admitted candidate gets
 * two excluded balanced warmup pairs and eight balanced pairs versus stock.
 * No fallback/tolerance widening/retry loop. At most43 complete pipeline calls.
 * Component CPU submission-to-device-completion wall is not Prefill/Decode
 * tok/s, GPU busy time, acceptance or an engine speed claim.
 */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <elf.h>
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <link.h>
#include <openssl/evp.h>
#include <pthread.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>
#if !defined(__linux__) || !defined(__x86_64__)
#error Linux x86-64 only
#endif
#define ENGINE_BYTES ((off_t)26052768)
#define ENGINE_SHA "ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b"
#define CHECKPOINT_SHA "71246c6ab3fc1de2cf06326f18e275fe9c2a18366d646ed3357d194c884fc687"
#define INDEX_SHA "2302900dfe860fd7a689c90bdf1d3fe674d78aa8bf3c166e05000c9d5e5e9ceb"
#define PREP_RVA ((uintptr_t)0x17ec6e0)
#define PREP_OFFSET ((off_t)0x17eb6e0)
#define PREP_BYTES ((size_t)2046)
#define PREP_SHA "34bb1998a74e03c63c714ea1e43d505eb88e59ff1c6266f39ba997a6f174d12d"
#define MM_RVA ((uintptr_t)0x18c6b80)
#define MM_OFFSET ((off_t)0x18c5b80)
#define MM_BYTES ((size_t)102)
#define MM_SHA "6336433c1a337ff1faf7f72767ea869bfab343355ce74130226bd0ba76651a7d"
#define NATIVE_RVA ((uintptr_t)0x18092f0)
#define NATIVE_OFFSET ((off_t)0x18082f0)
#define NATIVE_BYTES ((size_t)2228)
#define NATIVE_SHA "fda51e1d8cf5008e6e5e61a85ee33199a008a4833799452d1e6db9786350e231"
#define ROUTER_RVA ((uintptr_t)0x18db4d8)
#define CAPACITY_RVA ((uintptr_t)0x18dcf28)
#define ROTATED_RVA ((uintptr_t)0x18dcf30)
#define PARTIAL_RVA ((uintptr_t)0x18dcf38)
#define KEEP_RVA ((uintptr_t)0x18dcf41)
#define TARGET_RVA ((uintptr_t)0x18dd290)
#define ROWS_RVA ((uintptr_t)0x18dd2a0)
#define DESC_BYTES ((size_t)120)
#define PACKED_BYTES ((size_t)13107200)
#define SIGNS_BYTES ((size_t)5120)
#define SCALES_BYTES ((size_t)20480)
#define X_BYTES ((size_t)41943040)
#define Y_BYTES ((size_t)167772160)
#define W_BYTES ((size_t)52428800)
#define FILE_LIMIT ((size_t)314572800)
#define RUN_LIMIT 43U
#define STOCK 0U
#define NATIVE 1U
#define CACHED 2U
#define M 8192
#define N 10240
#define K 2560
static const char prefix[]="/tmp/alloy-prefill-ht-replay-";
static const char arm_text[]="ordinary-qkv8192-v1-replay-ready\n";
static const char tensor_name[]="layers.0.linear_attn.in_proj_qkv.weight";
typedef void (*prep_fn)(const void *,int,int,int64_t,const void *,const void *,void *);
typedef void (*mm_fn)(void *,const void *,const void *,void *,int64_t,int64_t,int64_t);
typedef bool (*native_fn)(void *,const void *,void *,int,int,int64_t);
typedef int (*sync_fn)(void);
typedef int (*copy_fn)(void *,const void *,size_t,int);
typedef int (*alloc_fn)(void **,size_t);
typedef int (*free_fn)(void *);
typedef int (*range_fn)(void **,size_t *,void *);
typedef int (*set_fn)(void *,int,size_t);
typedef int (*device_fn)(int);
struct api {sync_fn sync;copy_fn copy;alloc_fn alloc;free_fn release;range_fn range;set_fn set;device_fn device;};
struct identity {struct stat st;char sha[65];};
struct manifest {char sha[8][65];};
struct run {
    unsigned arm,cohort,phase,pair,completed,exact;uint64_t wall_ns,word_mismatches;
    char output_sha[65];unsigned shown;
    size_t mismatch_index[16];uint16_t expected[16],actual[16];
};
struct device_buffer {void *pointer,*base;size_t bytes,extent;};
static uintptr_t engine_base,router,rotated,partial,scratch_base;
static uint64_t capacity;
static size_t scratch_extent;
static prep_fn prepare;
static mm_fn multiply;
static native_fn native_ht;
static struct api api;
static struct manifest manifest;
static struct run runs[RUN_LIMIT];
static struct {unsigned qualified,retired,warmup_pairs,measured_pairs;const char *reason;} arms[3];
static unsigned run_count,allocations_ok,free_ok,cleanup_errors;
static int output_dir=-1,fixture_dir=-1,error_code;
static size_t input_file_bytes,output_file_bytes;
static char manifest_sha[65];
static const char *error_reason;
static unsigned char *host,*packed_host,*signs_host,*scales_host,*x_host,*reference,*readback;
static unsigned char descriptor[DESC_BYTES];
static struct device_buffer buffers[7];
static uint64_t cached_prepare_wall_ns;
static unsigned cached_preparations,native_successful_calls;
static const char *file_names[8]={"packed.bin","signs-u16.bin","scales-u16.bin","x-u16.bin",
    "y-reference-u16.bin","descriptor-before.bin","records.json","complete.json"};
static const size_t fixed_bytes[6]={PACKED_BYTES,SIGNS_BYTES,SCALES_BYTES,X_BYTES,Y_BYTES,DESC_BYTES};
static struct identity inputs[8];

static _Noreturn void fatal(const char *reason) {
    dprintf(STDERR_FILENO,"[prefill-ht-replay] fatal reason=%s errno=%d\n",reason,errno);_exit(79);
}
static int fail(const char *reason,int code) {if (!error_reason) {error_reason=reason;error_code=code;}return 0;}
static int sha_valid(const char *s) {return s && strlen(s)==64 && strspn(s,"0123456789abcdef")==64;}
static int hash(const void *p,size_t bytes,char out[65]) {
    unsigned char digest[32];unsigned n=0;
    if (EVP_Digest(p,bytes,digest,&n,EVP_sha256(),NULL)!=1 || n!=32) return 0;
    for (unsigned i=0;i<32;i++) snprintf(out+2*i,3,"%02x",(unsigned)digest[i]);
    return 1;
}
static int same(const struct stat *a,const struct stat *b) {
    return a->st_dev==b->st_dev && a->st_ino==b->st_ino && a->st_size==b->st_size &&
        a->st_mtim.tv_sec==b->st_mtim.tv_sec && a->st_mtim.tv_nsec==b->st_mtim.tv_nsec &&
        a->st_ctim.tv_sec==b->st_ctim.tv_sec && a->st_ctim.tv_nsec==b->st_ctim.tv_nsec;
}
static uint64_t u64(const void *p,size_t offset) {uint64_t v;memcpy(&v,(const unsigned char *)p+offset,8);return v;}
static uint32_t u32(const void *p,size_t offset) {uint32_t v;memcpy(&v,(const unsigned char *)p+offset,4);return v;}
static void put64(void *p,size_t offset,uint64_t v) {memcpy((unsigned char *)p+offset,&v,8);}
static void put32(void *p,size_t offset,uint32_t v) {memcpy((unsigned char *)p+offset,&v,4);}
static int mapped(uintptr_t address,size_t bytes,int executable) {
    if (!address || !bytes || bytes>UINTPTR_MAX-address) return 0;
    FILE *f=fopen("/proc/self/maps","re");if (!f) return 0;
    char line[4096],perms[5];unsigned long low,high;int result=0;
    while (fgets(line,sizeof line,f)) if (sscanf(line,"%lx-%lx %4s",&low,&high,perms)==3 &&
        address>=low && address+bytes<=high && (executable?!strcmp(perms,"r-xp"):perms[0]=='r')) {result=1;break;}
    int bad=ferror(f);
    if (fclose(f)) bad=1;
    return bad?0:result;
}
static int load_file(int directory,const char *name,size_t expected,size_t limit,void *p,
    const char *wanted,struct identity *identity,size_t *loaded) {
    if (!sha_valid(wanted)) return fail("input-sha-format",0);
    int fd=openat(directory,name,O_RDONLY|O_CLOEXEC|O_NOFOLLOW);struct stat a,b;
    if (fd<0) return fail("input-open",errno);
    int ok=!fstat(fd,&a) && S_ISREG(a.st_mode) && a.st_uid==geteuid() && a.st_nlink==1 &&
        (a.st_mode&0777)==0600 && a.st_size>0 && (uint64_t)a.st_size<=limit &&
        (!expected || (uint64_t)a.st_size==expected);
    if (!ok) {close(fd);return fail("input-file-contract",errno);}
    size_t left=(size_t)a.st_size;unsigned char *at=p;
    while (left) {ssize_t n=read(fd,at,left);if (n<0 && errno==EINTR) continue;
        if (n<=0) {ok=0;break;}at+=n;left-=(size_t)n;}
    char actual[65];
    if (!ok || fstat(fd,&b) || !same(&a,&b) || !hash(p,(size_t)a.st_size,actual) || strcmp(actual,wanted)) ok=0;
    if (close(fd)) ok=0;
    if (!ok) return fail("input-read-hash-identity",errno);
    if (identity) {identity->st=a;memcpy(identity->sha,actual,65);}
    if (loaded) *loaded=(size_t)a.st_size;
    return 1;
}
static int manifest_load(void) {
    char text[2048],canonical[2048];size_t bytes=0;
    if (!load_file(output_dir,"replay.receipt",0,sizeof text-1,text,manifest_sha,NULL,&bytes)) return 0;
    text[bytes]=0;int end=0;
    int assignments=sscanf(text,"schema=ordinary-qkv8192-replay-v1\nstock_route=direct-original\n"
        "packed_sha256=%64[0-9a-f]\nsigns_sha256=%64[0-9a-f]\nscales_sha256=%64[0-9a-f]\n"
        "x_sha256=%64[0-9a-f]\ny_sha256=%64[0-9a-f]\ndescriptor_sha256=%64[0-9a-f]\n"
        "records_sha256=%64[0-9a-f]\ncomplete_sha256=%64[0-9a-f]\n%n",
        manifest.sha[0],manifest.sha[1],manifest.sha[2],manifest.sha[3],manifest.sha[4],manifest.sha[5],manifest.sha[6],manifest.sha[7],&end);
    if (assignments!=8 || end!=(int)bytes) return fail("manifest-schema",0);
    for (unsigned i=0;i<8;i++) if (!sha_valid(manifest.sha[i])) return fail("manifest-sha-format",0);
    int n=snprintf(canonical,sizeof canonical,"schema=ordinary-qkv8192-replay-v1\nstock_route=direct-original\n"
        "packed_sha256=%s\nsigns_sha256=%s\nscales_sha256=%s\nx_sha256=%s\ny_sha256=%s\n"
        "descriptor_sha256=%s\nrecords_sha256=%s\ncomplete_sha256=%s\n",
        manifest.sha[0],manifest.sha[1],manifest.sha[2],manifest.sha[3],manifest.sha[4],manifest.sha[5],manifest.sha[6],manifest.sha[7]);
    return (n>0 && (size_t)n==bytes && !memcmp(text,canonical,bytes)) || fail("manifest-canonical",0);
}
static int arm_status(void) {
    int fd=openat(output_dir,"armed",O_RDONLY|O_CLOEXEC|O_NOFOLLOW);
    if (fd<0) return errno==ENOENT?0:-1;
    struct stat a,b;char text[64];ssize_t n=-1;
    int ok=!fstat(fd,&a) && S_ISREG(a.st_mode) && a.st_uid==geteuid() && a.st_nlink==1 &&
        (a.st_mode&0777)==0600 && a.st_size==(off_t)(sizeof arm_text-1);
    if (ok) {do {n=pread(fd,text,sizeof text,0);} while (n<0 && errno==EINTR);}
    if (!ok || n!=(ssize_t)(sizeof arm_text-1) || memcmp(text,arm_text,sizeof arm_text-1) || fstat(fd,&b) || !same(&a,&b)) ok=0;
    if (close(fd)) ok=0;
    return ok?1:-1;
}
/* Only the fixed capture schema is accepted; strings/pointers below are read
 * from hashed diagnostic JSON, never dereferenced as new process addresses. */
static int json_u64(const char *text,const char *key,int hexadecimal,uint64_t *value) {
    char token[128];int n=snprintf(token,sizeof token,hexadecimal?"\"%s\":\"0x":"\"%s\":",key);
    if (n<=0 || n>=(int)sizeof token) return 0;
    const char *p=strstr(text,token);
    if (!p || strstr(p+1,token)) return 0;
    p+=n;
    if (!*p || (*p=='-' || *p=='+')) return 0;
    errno=0;char *end;
    unsigned long long v=strtoull(p,&end,hexadecimal?16:10);
    if (errno || end==p || (hexadecimal?*end!='"':(*end!=',' && *end!='}'))) return 0;
    *value=(uint64_t)v;return 1;
}
static int capture_proof(const char *records,const char *complete) {
    if (!strstr(complete,"\"passed\":true") || !strstr(complete,"\"packed_original_calls\":1") ||
        !strstr(complete,"\"candidate_calls\":0") || !strstr(complete,"\"mode\":\"ordinary-qkv8192-v1\"")) return fail("capture-complete",0);
    uint64_t calls,result,stream,x,y,b,c,d,mode,fc,packed;
    if (!json_u64(records,"library_calls",0,&calls) || calls!=1 || !json_u64(records,"library_result",0,&result) || result ||
        !json_u64(records,"library_stream",1,&stream) || stream || !json_u64(records,"x_pointer",1,&x) ||
        !json_u64(records,"y_pointer",1,&y) || !json_u64(records,"library_b",1,&b) ||
        !json_u64(records,"library_c",1,&c) || !json_u64(records,"library_d",1,&d) || !x || !y || b!=x || c!=y || d!=y ||
        !json_u64(records,"descriptor_mode",0,&mode) || mode!=4 || !json_u64(records,"fc_caller_rva",1,&fc) || fc!=0x1791400 ||
        !json_u64(records,"packed_caller_rva",1,&packed) || packed!=0x178cfc0 ||
        !strstr(records,"\"tensor\":\"layers.0.linear_attn.in_proj_qkv.weight\"") || !strstr(records,CHECKPOINT_SHA) ||
        !strstr(records,INDEX_SHA) || !strstr(records,"\"allocation_snapshot_before\":true") ||
        !strstr(records,"\"allocation_snapshot_after\":true")) return fail("capture-stock-binding",0);
    int prep_seen=0;const char *p=records;
    while ((p=strstr(p,"\"caller_rva\":\"0x"))) {
        p+=strlen("\"caller_rva\":\"0x");errno=0;char *end;unsigned long long v=strtoull(p,&end,16);
        if (errno || end==p || *end!='"') return fail("capture-kernel-caller",0);
        if (v==0x17ecd6a) prep_seen=1;
        p=end+1;
    }
    return prep_seen || fail("capture-original-preparation-unbound",0);
}
static int load_fixture(void) {
    size_t host_bytes=PACKED_BYTES+SIGNS_BYTES+SCALES_BYTES+X_BYTES+2*Y_BYTES;
    host=malloc(host_bytes);if (!host) return fail("host-staging",errno);
    packed_host=host;signs_host=packed_host+PACKED_BYTES;scales_host=signs_host+SIGNS_BYTES;
    x_host=scales_host+SCALES_BYTES;reference=x_host+X_BYTES;readback=reference+Y_BYTES;
    void *destination[6]={packed_host,signs_host,scales_host,x_host,reference,descriptor};
    for (unsigned i=0;i<6;i++) {
        if (!load_file(fixture_dir,file_names[i],fixed_bytes[i],fixed_bytes[i],destination[i],manifest.sha[i],&inputs[i],NULL)) return 0;
        input_file_bytes+=fixed_bytes[i];
    }
    char records[32769],complete[2049];size_t nr=0,nc=0;
    if (!load_file(fixture_dir,file_names[6],0,sizeof records-1,records,manifest.sha[6],&inputs[6],&nr) ||
        !load_file(fixture_dir,file_names[7],0,sizeof complete-1,complete,manifest.sha[7],&inputs[7],&nc)) return 0;
    records[nr]=0;complete[nc]=0;input_file_bytes+=nr+nc;
    if (input_file_bytes>FILE_LIMIT || u32(descriptor,0x48)!=4 || u32(descriptor,0x4c)!=N || u64(descriptor,0x50)!=K) return fail("fixture-shape-limit",0);
    return capture_proof(records,complete);
}
static int coverage(void *pointer,size_t needed,void **base,size_t *extent) {
    int e=api.range(base,extent,pointer);uintptr_t p=(uintptr_t)pointer,a=(uintptr_t)*base;
    return (!e && a && *extent && *extent<=UINTPTR_MAX-a && p>=a && p-a<=*extent && needed<=*extent-(p-a))
        || fail("allocation-coverage",e);
}
static int current_globals(int after) {
    if (!mapped(engine_base+ROUTER_RVA,8,0) || !mapped(engine_base+CAPACITY_RVA,24,0) ||
        !mapped(engine_base+KEEP_RVA,1,0) || !mapped(engine_base+TARGET_RVA,4,0) || !mapped(engine_base+ROWS_RVA,4,0)) return fail("runtime-global-span",0);
    uintptr_t r=(uintptr_t)u64((void *)(engine_base+ROUTER_RVA),0),s=(uintptr_t)u64((void *)(engine_base+ROTATED_RVA),0);
    uintptr_t optional=(uintptr_t)u64((void *)(engine_base+PARTIAL_RVA),0);
    uint64_t cap=u64((void *)(engine_base+CAPACITY_RVA),0);
    if (!r || !s || cap<(uint64_t)M*K || cap>SIZE_MAX/2 || !mapped(r,0x50,0) || u64((void *)r,0x48) ||
        *(const unsigned char *)(engine_base+KEEP_RVA)) return fail("initialized-router-scratch-contract",0);
    if (!after) {router=r;rotated=s;partial=optional;capacity=cap;
        void *base=NULL;size_t extent=0;
        if (!coverage((void *)s,(size_t)cap*2,&base,&extent)) return 0;
        scratch_base=(uintptr_t)base;scratch_extent=extent;
    } else {
        if (router!=r || rotated!=s || partial!=optional || capacity!=cap ||
            (native_successful_calls && (u32((void *)(engine_base+TARGET_RVA),0)!=80 ||
            u32((void *)(engine_base+ROWS_RVA),0)!=256))) return fail("runtime-controls-or-globals-changed",0);
        void *base=NULL;size_t extent=0;
        if (!coverage((void *)s,(size_t)cap*2,&base,&extent) || (uintptr_t)base!=scratch_base || extent!=scratch_extent) return fail("scratch-allocation-changed",0);
    }
    return 1;
}
static int resolve_api(void) {
    api.sync=(sync_fn)dlsym(RTLD_DEFAULT,"hipDeviceSynchronize");
    api.copy=(copy_fn)dlsym(RTLD_DEFAULT,"hipMemcpy");api.alloc=(alloc_fn)dlsym(RTLD_DEFAULT,"hipMalloc");
    api.release=(free_fn)dlsym(RTLD_DEFAULT,"hipFree");api.range=(range_fn)dlsym(RTLD_DEFAULT,"hipMemGetAddressRange");
    api.set=(set_fn)dlsym(RTLD_DEFAULT,"hipMemset");api.device=(device_fn)dlsym(RTLD_DEFAULT,"hipSetDevice");
    return (api.sync && api.copy && api.alloc && api.release && api.range && api.set && api.device) || fail("required-hip-symbol",0);
}
static int allocate_buffers(void) {
    const size_t sizes[7]={PACKED_BYTES,SIGNS_BYTES,SCALES_BYTES,X_BYTES,Y_BYTES,W_BYTES,W_BYTES};
    const void *source[4]={packed_host,signs_host,scales_host,x_host};
    for (unsigned i=0;i<7;i++) {
        buffers[i].bytes=sizes[i];int e=api.alloc(&buffers[i].pointer,sizes[i]);
        if (e || !buffers[i].pointer) return fail("owned-device-allocation",e);
        allocations_ok++;
        if (!coverage(buffers[i].pointer,sizes[i],&buffers[i].base,&buffers[i].extent)) return 0;
        for (unsigned j=0;j<i;j++) if (buffers[i].pointer==buffers[j].pointer) return fail("owned-allocation-alias",0);
        if (i<4) {e=api.copy(buffers[i].pointer,source[i],sizes[i],1);if (e) return fail("frozen-input-upload",e);}
    }
    memset(descriptor,0,sizeof descriptor);
    put64(descriptor,0x30,(uintptr_t)buffers[0].pointer);put64(descriptor,0x38,(uintptr_t)buffers[1].pointer);
    put64(descriptor,0x40,(uintptr_t)buffers[2].pointer);put32(descriptor,0x48,4);put32(descriptor,0x4c,N);
    put64(descriptor,0x50,K);put64(descriptor,0x70,(uintptr_t)tensor_name);
    int e=api.sync();return !e || fail("upload-completion",e);
}
static int check_words(struct run *r) {
    if (!hash(readback,Y_BYTES,r->output_sha)) return fail("output-hash",0);
    if (!memcmp(readback,reference,Y_BYTES)) {r->exact=1;return 1;}
    const uint16_t *actual=(const uint16_t *)readback,*expected=(const uint16_t *)reference;
    for (size_t i=0;i<Y_BYTES/2;i++) if (actual[i]!=expected[i]) {
        r->word_mismatches++;
        if (r->shown<16) {unsigned j=r->shown++;r->mismatch_index[j]=i;r->expected[j]=expected[i];r->actual[j]=actual[i];}
    }
    return 0;
}
static uint64_t ns_delta(struct timespec a,struct timespec b) {
    return (uint64_t)(b.tv_sec-a.tv_sec)*1000000000ULL+(uint64_t)(b.tv_nsec-a.tv_nsec);
}
/* Return1 exact,2 retired candidate,0 process/API/baseline failure. */
static int execute(unsigned arm,unsigned cohort,unsigned phase,unsigned pair) {
    if (run_count>=RUN_LIMIT) return fail("finite-run-limit",0);
    struct run *r=&runs[run_count++];r->arm=arm;r->cohort=cohort;r->phase=phase;r->pair=pair;
    int e=api.set(buffers[4].pointer,0xff,Y_BYTES);if (e) return fail("owned-output-poison",e);
    if (arm==STOCK) {e=api.set(buffers[5].pointer,0xff,W_BYTES);if (e) return fail("owned-weight-poison",e);}
    e=api.sync();if (e) return fail("pre-run-completion",e);
    struct timespec begin,end;
    if (clock_gettime(CLOCK_MONOTONIC_RAW,&begin)) return fail("timing-start",errno);
    if (arm==NATIVE) {
        if (!native_ht(descriptor,buffers[3].pointer,buffers[4].pointer,N,M,K)) {
            arms[arm].retired=1;arms[arm].reason="native-ht-declined";return 2;
        }
        native_successful_calls++;
    } else if (arm==CACHED) {
        multiply((void *)router,buffers[6].pointer,buffers[3].pointer,buffers[4].pointer,M,N,K);
    } else {
        prepare(buffers[0].pointer,4,N,K,buffers[1].pointer,buffers[2].pointer,buffers[5].pointer);
        multiply((void *)router,buffers[5].pointer,buffers[3].pointer,buffers[4].pointer,M,N,K);
    }
    e=api.sync();if (e) return fail("complete-pipeline-sync",e);
    if (clock_gettime(CLOCK_MONOTONIC_RAW,&end)) return fail("timing-end",errno);
    r->wall_ns=ns_delta(begin,end);
    e=api.copy(readback,buffers[4].pointer,Y_BYTES,2);if (e) return fail("output-readback",e);
    r->completed=1;
    if (!check_words(r)) {
        if (arm==STOCK || error_reason) return fail(error_reason?error_reason:"stock-raw-y-mismatch",0);
        arms[arm].retired=1;arms[arm].qualified=0;
        arms[arm].reason=arm==NATIVE?"native-raw-y-mismatch":"cached-original-raw-y-mismatch";return 2;
    }
    return 1;
}
static int prepare_cached_once(void) {
    int e=api.set(buffers[6].pointer,0xff,W_BYTES);
    if (e) return fail("cached-weight-poison",e);
    e=api.sync();if (e) return fail("cached-preparation-start-completion",e);
    struct timespec begin,end;
    if (clock_gettime(CLOCK_MONOTONIC_RAW,&begin)) return fail("cached-preparation-clock-start",errno);
    prepare(buffers[0].pointer,4,N,K,buffers[1].pointer,buffers[2].pointer,buffers[6].pointer);
    cached_preparations++;
    e=api.sync();if (e) return fail("cached-preparation-completion",e);
    if (clock_gettime(CLOCK_MONOTONIC_RAW,&end)) return fail("cached-preparation-clock-end",errno);
    cached_prepare_wall_ns=ns_delta(begin,end);return 1;
}
static int paired_cohort(unsigned candidate) {
    for (unsigned phase=1;phase<=2;phase++) {
        unsigned pairs=phase==1?2:8;
        for (unsigned pair=0;pair<pairs;pair++) {
            unsigned first=(pair&1)?candidate:STOCK,second=first==STOCK?candidate:STOCK;
            int a=execute(first,candidate,phase,pair);
            if (!a) return 0;
            if (a==2) return 1;
            int b=execute(second,candidate,phase,pair);
            if (!b) return 0;
            if (b==2) return 1;
            if (phase==1) arms[candidate].warmup_pairs++;else arms[candidate].measured_pairs++;
        }
    }
    return 1;
}
static int recheck_inputs(void) {
    for (unsigned i=0;i<8;i++) {
        int fd=openat(fixture_dir,file_names[i],O_RDONLY|O_CLOEXEC|O_NOFOLLOW);struct stat st;
        if (fd<0) return fail("fixture-final-open",errno);
        int ok=!fstat(fd,&st) && same(&inputs[i].st,&st);if (close(fd)) ok=0;
        if (!ok) return fail("fixture-final-identity",errno);
    }
    return 1;
}
static void cleanup(void) {
    if (api.sync && api.sync()) cleanup_errors++;
    for (unsigned i=7;i>0;i--) if (buffers[i-1].pointer) {
        if (!api.release || api.release(buffers[i-1].pointer)) cleanup_errors++;
        else {free_ok++;buffers[i-1].pointer=NULL;}
    }
    if (cleanup_errors) fail("owned-cleanup",0);
    free(host);host=NULL;
}
static int save(const char *name,const void *data,size_t bytes) {
    if (bytes>FILE_LIMIT-output_file_bytes) return 0;
    int fd=openat(output_dir,name,O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC|O_NOFOLLOW,0600);if (fd<0) return 0;
    struct stat st;int ok=!fstat(fd,&st) && S_ISREG(st.st_mode) && st.st_uid==geteuid() && st.st_nlink==1 && st.st_size==0;
    const unsigned char *p=data;
    while (ok && bytes) {ssize_t n=write(fd,p,bytes);if (n<0 && errno==EINTR) continue;
        if (n<=0) {ok=0;break;}p+=n;bytes-=(size_t)n;output_file_bytes+=(size_t)n;}
    if (fsync(fd)) ok=0;
    if (close(fd)) ok=0;
    return ok;
}
static void report(void) {
    char text[32768];uint64_t totals[3][2]={{0}};unsigned measured[3][2]={{0}};
    for (unsigned i=0;i<run_count;i++) {
        const struct run *r=&runs[i];
        if (r->completed && r->exact && r->phase==2 && r->cohort>=NATIVE && r->cohort<=CACHED) {
            unsigned side=r->arm==STOCK?0:1;totals[r->cohort][side]+=r->wall_ns;measured[r->cohort][side]++;
        }
    }
    int candidate_complete[3]={0,0,0};
    for (unsigned a=NATIVE;a<=CACHED;a++) candidate_complete[a]=arms[a].retired ||
        (arms[a].qualified && arms[a].warmup_pairs==2 && arms[a].measured_pairs==8 && measured[a][0]==8 && measured[a][1]==8);
    int passed=!error_reason && arms[STOCK].qualified && candidate_complete[NATIVE] && candidate_complete[CACHED] &&
        cached_preparations==1 && allocations_ok==7 && free_ok==7 && !cleanup_errors;
    int n=snprintf(text,sizeof text,
        "{\"schema\":1,\"mode\":\"ordinary-qkv8192-replay-v1\",\"passed\":%s,\"engine_sha256\":\"%s\","
        "\"manifest_sha256\":\"%s\",\"stock_pipeline\":\"original-preparation-plus-library\","
        "\"native_pipeline\":\"original-rotation-plus-packed-multiply\","
        "\"cached_pipeline\":\"original-prepared-weight-resident-plus-library\",\"M\":8192,\"N\":10240,\"K\":2560,"
        "\"descriptor_mode\":4,\"raw_y_contract\":\"exact-native16-bit-words\",\"tolerance_widened\":false,"
        "\"measurement\":\"cpu-submission-to-full-device-completion-wall\",\"gpu_busy_time_claim\":false,"
        "\"token_rate_claim\":false,\"acceptance_claim\":false,\"serving_substitution\":false,\"device\":0,"
        "\"router\":\"0x%" PRIxPTR "\",\"rotated_scratch\":\"0x%" PRIxPTR "\",\"capacity_elements\":%" PRIu64 ","
        "\"scratch_allocation_base\":\"0x%" PRIxPTR "\",\"scratch_allocation_extent_bytes\":%zu,"
        "\"partial_scratch\":\"0x%" PRIxPTR "\",\"native_blocks_default\":80,\"native_rows_default\":256,"
        "\"keep_trunk\":false,\"ht_threshold_changed\":false,\"algorithm_bytes_identity\":null,"
        "\"cached_weight_resident_bytes\":52428800,\"cached_preparations_excluded\":%u,\"cached_prepare_wall_ns\":%" PRIu64 ","
        "\"own_device_bytes_budget\":327705600,\"native_successful_calls\":%u,"
        "\"own_device_allocations\":%u,\"own_device_frees\":%u,\"cleanup_errors\":%u,\"input_file_bytes\":%zu,"
        "\"error_code\":%d,\"error\":%s%s%s,\"comparisons\":[",
        passed?"true":"false",ENGINE_SHA,manifest_sha,router,rotated,capacity,scratch_base,scratch_extent,partial,
        cached_preparations,cached_prepare_wall_ns,native_successful_calls,allocations_ok,free_ok,cleanup_errors,input_file_bytes,
        error_code,error_reason?"\"":"",error_reason?error_reason:"null",error_reason?"\"":"");
    if (n<=0 || n>=(int)sizeof text) fatal("report-format");
    size_t used=(size_t)n;
    for (unsigned a=NATIVE;a<=CACHED;a++) {
        int usable=!error_reason && !cleanup_errors && arms[a].qualified && candidate_complete[a] && !arms[a].retired;
        char stock_mean[64]="null",candidate_mean[64]="null";
        if (usable) {
            snprintf(stock_mean,sizeof stock_mean,"%.9f",(double)totals[a][0]/measured[a][0]/1e6);
            snprintf(candidate_mean,sizeof candidate_mean,"%.9f",(double)totals[a][1]/measured[a][1]/1e6);
        }
        n=snprintf(text+used,sizeof text-used,
            "%s{\"candidate\":\"%s\",\"qualified\":%s,\"retired\":%s,\"warmup_pairs\":%u,\"measured_pairs\":%u,"
            "\"stock_count\":%u,\"candidate_count\":%u,\"stock_mean_wall_ms\":%s,\"candidate_mean_wall_ms\":%s,"
            "\"error\":%s%s%s}",
            a==NATIVE?"":",",a==NATIVE?"native-ht":"cached-original",usable?"true":"false",arms[a].retired?"true":"false",
            arms[a].warmup_pairs,arms[a].measured_pairs,measured[a][0],measured[a][1],stock_mean,candidate_mean,
            arms[a].reason?"\"":"",arms[a].reason?arms[a].reason:"null",arms[a].reason?"\"":"");
        if (n<=0 || (size_t)n>=sizeof text-used) fatal("comparison-report-format");
        used+=(size_t)n;
    }
    n=snprintf(text+used,sizeof text-used,"],\"runs\":[");
    if (n<=0 || (size_t)n>=sizeof text-used) fatal("run-report-prefix");
    used+=(size_t)n;
    for (unsigned i=0;i<run_count;i++) {
        const struct run *r=&runs[i];
        n=snprintf(text+used,sizeof text-used,
            "%s{\"index\":%u,\"arm\":\"%s\",\"cohort\":%u,\"phase\":%u,\"pair\":%u,\"completed\":%s,\"exact\":%s,\"wall_ns\":%" PRIu64 ","
            "\"word_mismatches\":%" PRIu64 ",\"output_sha256\":\"%s\",\"mismatch_examples\":[",
            i?",":"",i,r->arm==STOCK?"stock":(r->arm==NATIVE?"native-ht":"cached-original"),r->cohort,r->phase,r->pair,
            r->completed?"true":"false",r->exact?"true":"false",r->wall_ns,r->word_mismatches,r->output_sha);
        if (n<=0 || (size_t)n>=sizeof text-used) fatal("run-report-format");
        used+=(size_t)n;
        for (unsigned j=0;j<r->shown;j++) {
            n=snprintf(text+used,sizeof text-used,"%s{\"word\":%zu,\"expected_u16\":%u,\"actual_u16\":%u}",
                j?",":"",r->mismatch_index[j],(unsigned)r->expected[j],(unsigned)r->actual[j]);
            if (n<=0 || (size_t)n>=sizeof text-used) fatal("mismatch-report-format");
            used+=(size_t)n;
        }
        n=snprintf(text+used,sizeof text-used,"]}");
        if (n<=0 || (size_t)n>=sizeof text-used) fatal("run-report-end");
        used+=(size_t)n;
    }
    n=snprintf(text+used,sizeof text-used,"]}\n");
    if (n<=0 || (size_t)n>=sizeof text-used || !save("replay.json",text,used+(size_t)n)) fatal("report-export");
    char done[256];n=snprintf(done,sizeof done,"{\"schema\":1,\"passed\":%s,\"runs\":%u,\"token_rate_claim\":false}\n",passed?"true":"false",run_count);
    if (n<=0 || n>=(int)sizeof done || !save("complete.json",done,(size_t)n)) fatal("complete-export");
}
static void *worker(void *unused) {
    (void)unused;struct timespec began,now,delay={0,20000000};
    if (clock_gettime(CLOCK_MONOTONIC,&began)) return NULL;
    for (;;) {
        int status=arm_status();if (status<0) {fail("arm-content",0);report();return NULL;}
        if (status==1) break;
        if (clock_gettime(CLOCK_MONOTONIC,&now) || now.tv_sec-began.tv_sec>1800) return NULL;
        (void)nanosleep(&delay,NULL);
    }
    if (!manifest_load() || !load_fixture() || !resolve_api()) goto done;
    int e=api.device(0);if (e) {fail("worker-device-zero",e);goto done;}
    e=api.sync();if (e) {fail("initial-completion",e);goto done;}
    if (!current_globals(0) || !allocate_buffers()) goto done;
    /* Qualification/plan selection/cached preparation never contribute to a
     * measured cohort. A retired native arm does not authorize any native loop. */
    if (execute(STOCK,0,0,0)!=1) goto done;
    arms[STOCK].qualified=1;
    int native_status=execute(NATIVE,NATIVE,0,0);
    if (!native_status) goto done;
    if (native_status==1) arms[NATIVE].qualified=1;
    if (!current_globals(1) || !prepare_cached_once()) goto done;
    int cached_status=execute(CACHED,CACHED,0,0);
    if (!cached_status) goto done;
    if (cached_status==1) arms[CACHED].qualified=1;
    if (arms[NATIVE].qualified && !paired_cohort(NATIVE)) goto done;
    if (arms[CACHED].qualified && !paired_cohort(CACHED)) goto done;
    if (!current_globals(1) || !recheck_inputs()) goto done;
done:
    cleanup();report();return NULL;
}
static void file_hash(int fd,off_t offset,size_t bytes,const char *wanted) {
    EVP_MD_CTX *ctx=EVP_MD_CTX_new();if (!ctx || EVP_DigestInit_ex(ctx,EVP_sha256(),NULL)!=1) fatal("executable-hash-init");
    unsigned char block[65536],digest[32];unsigned n=0;
    while (bytes) {size_t count=bytes<sizeof block?bytes:sizeof block;ssize_t got=pread(fd,block,count,offset);
        if (got<0 && errno==EINTR) continue;
        if (got<=0 || (size_t)got>count || EVP_DigestUpdate(ctx,block,(size_t)got)!=1) fatal("executable-hash-read");
        offset+=got;bytes-=(size_t)got;}
    if (EVP_DigestFinal_ex(ctx,digest,&n)!=1 || n!=32) fatal("executable-hash-final");
    EVP_MD_CTX_free(ctx);
    char out[65];
    for (unsigned i=0;i<32;i++) snprintf(out+2*i,3,"%02x",(unsigned)digest[i]);
    if (strcmp(out,wanted)) fatal("executable-hash-mismatch");
}
struct site {uintptr_t base;unsigned helpers;};
static int find_site(struct dl_phdr_info *info,size_t unused,void *opaque) {
    (void)unused;
    if (info->dlpi_name && *info->dlpi_name) return 0;
    struct site *s=opaque;
    if (ROWS_RVA+4>UINTPTR_MAX-info->dlpi_addr) fatal("image-base-overflow");
    s->base=info->dlpi_addr;
    uintptr_t rva[3]={PREP_RVA,MM_RVA,NATIVE_RVA};off_t offset[3]={PREP_OFFSET,MM_OFFSET,NATIVE_OFFSET};size_t bytes[3]={PREP_BYTES,MM_BYTES,NATIVE_BYTES};
    for (size_t i=0;i<info->dlpi_phnum;i++) {const Elf64_Phdr *p=&info->dlpi_phdr[i];
        if (p->p_type!=PT_LOAD || p->p_flags!=(PF_R|PF_X) || p->p_vaddr>UINT64_MAX-p->p_filesz) continue;
        for (unsigned j=0;j<3;j++) if (p->p_vaddr<=rva[j] && rva[j]+bytes[j]<=p->p_vaddr+p->p_filesz &&
            p->p_offset+rva[j]-p->p_vaddr==(uint64_t)offset[j]) s->helpers++;}
    return 1;
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
    const char *mode=getenv("HALOGEN_PREFILL_HT_REPLAY");if (!mode) return;
    char path[4096];ssize_t n=readlink("/proc/self/exe",path,sizeof path-1);if (n<0 || n>=(ssize_t)sizeof path-1) fatal("executable-name");
    path[n]=0;const char *leaf=strrchr(path,'/');leaf=leaf?leaf+1:path;
    /* Startup CLI probes use the same executable. Only the actual serving
     * argv may reserve the exclusive trace directory or create the worker. */
    if (strcmp(leaf,"flash_serve") || !serving_process()) return;
    const char *directory=getenv("HALOGEN_PREFILL_HT_REPLAY_DIR"),*fixture=getenv("HALOGEN_PREFILL_HT_REPLAY_FIXTURE_DIR");
    const char *sha=getenv("HALOGEN_PREFILL_HT_REPLAY_MANIFEST_SHA256");
    if (strcmp(mode,"ordinary-qkv8192-v1") || !directory || !fixture || fixture[0]!='/' || !sha_valid(sha) ||
        strncmp(directory,prefix,sizeof prefix-1) || strlen(directory)!=sizeof prefix-1+32) fatal("configuration");
    for (const char *p=directory+sizeof prefix-1;*p;p++) if (!((*p>='0' && *p<='9') || (*p>='a' && *p<='f'))) fatal("run-id");
    /* Preserve native defaults and reject all prior capture/replacement modes.
     * No setenv or assignment to original control/scratch globals occurs. */
    const char *conflicts[]={"HALOGEN_PREFILL_KEEP_TRUNK","HALOGEN_HT_TG_BLOCKS","HALOGEN_HT_TG_M128","HALOGEN_HT_TRUNK_GEMM",
        "HALOGEN_PREFILL_HT_CAPTURE","HALOGEN_MTP_RAW_EMBEDDING_CAPTURE","HALOGEN_MTP_HIDDEN_RMS_TAP",
        "HALOGEN_MTP_FULL_EVENT_TAP","HALOGEN_MTP_FC_QUALITY","HALOGEN_MTP_EMBEDDING_CACHE"};
    for (size_t i=0;i<sizeof conflicts/sizeof conflicts[0];i++) if (getenv(conflicts[i])) fatal("nondefault-or-other-mode");
    memcpy(manifest_sha,sha,65);
    int fd=open("/proc/self/exe",O_RDONLY|O_CLOEXEC);struct stat a,b;Elf64_Ehdr eh;
    if (fd<0 || fstat(fd,&a) || !S_ISREG(a.st_mode) || a.st_size!=ENGINE_BYTES ||
        pread(fd,&eh,sizeof eh,0)!=(ssize_t)sizeof eh || memcmp(eh.e_ident,ELFMAG,SELFMAG) ||
        eh.e_ident[EI_CLASS]!=ELFCLASS64 || eh.e_ident[EI_DATA]!=ELFDATA2LSB || eh.e_type!=ET_DYN || eh.e_machine!=EM_X86_64) fatal("executable-identity");
    file_hash(fd,0,(size_t)a.st_size,ENGINE_SHA);file_hash(fd,PREP_OFFSET,PREP_BYTES,PREP_SHA);
    file_hash(fd,MM_OFFSET,MM_BYTES,MM_SHA);file_hash(fd,NATIVE_OFFSET,NATIVE_BYTES,NATIVE_SHA);
    if (fstat(fd,&b) || !same(&a,&b) || close(fd)) fatal("executable-consistency");
    struct site s={0};char actual[65];
    if (dl_iterate_phdr(find_site,&s)!=1 || s.helpers!=3 || !mapped(s.base+PREP_RVA,PREP_BYTES,1) ||
        !mapped(s.base+MM_RVA,MM_BYTES,1) || !mapped(s.base+NATIVE_RVA,NATIVE_BYTES,1) ||
        !hash((void *)(s.base+PREP_RVA),PREP_BYTES,actual) || strcmp(actual,PREP_SHA) ||
        !hash((void *)(s.base+MM_RVA),MM_BYTES,actual) || strcmp(actual,MM_SHA) ||
        !hash((void *)(s.base+NATIVE_RVA),NATIVE_BYTES,actual) || strcmp(actual,NATIVE_SHA)) fatal("mapped-helper-binding");
    engine_base=s.base;prepare=(prep_fn)(engine_base+PREP_RVA);multiply=(mm_fn)(engine_base+MM_RVA);native_ht=(native_fn)(engine_base+NATIVE_RVA);
    fixture_dir=open(fixture,O_RDONLY|O_DIRECTORY|O_CLOEXEC|O_NOFOLLOW);struct stat st;
    if (fixture_dir<0 || fstat(fixture_dir,&st) || !S_ISDIR(st.st_mode) || st.st_uid!=geteuid() || (st.st_mode&0777)!=0700) fatal("fixture-directory");
    int tmp=open("/tmp",O_RDONLY|O_DIRECTORY|O_CLOEXEC|O_NOFOLLOW);if (tmp<0 || mkdirat(tmp,directory+5,0700)) fatal("output-mkdir");
    output_dir=openat(tmp,directory+5,O_RDONLY|O_DIRECTORY|O_CLOEXEC|O_NOFOLLOW);if (close(tmp)) fatal("tmp-close");
    if (output_dir<0 || fstat(output_dir,&st) || !S_ISDIR(st.st_mode) || st.st_uid!=geteuid() || (st.st_mode&0777)!=0700) fatal("output-directory");
    char activation[2048];n=snprintf(activation,sizeof activation,
        "{\"schema\":1,\"mode\":\"ordinary-qkv8192-replay-v1\",\"engine_sha256\":\"%s\",\"prepare_sha256\":\"%s\","
        "\"matmul_sha256\":\"%s\",\"native_sha256\":\"%s\",\"manifest_sha256\":\"%s\",\"constructor_hardware_calls\":0,"
        "\"host_hooks\":0,\"serving_substitution\":false,\"recapture\":false,\"qualification_runs\":3,\"excluded_warmup_pairs_per_candidate\":2,"
        "\"measured_balanced_pairs_per_candidate\":8,\"run_limit\":43,\"cached_original_bytes\":52428800,"
        "\"file_byte_limit\":314572800,\"token_rate_claim\":false}\n",
        ENGINE_SHA,PREP_SHA,MM_SHA,NATIVE_SHA,manifest_sha);
    if (n<=0 || n>=(ssize_t)sizeof activation || !save("activation.json",activation,(size_t)n)) fatal("activation-export");
    pthread_t thread;if (pthread_create(&thread,NULL,worker,NULL) || pthread_detach(thread)) fatal("worker-create");
}
