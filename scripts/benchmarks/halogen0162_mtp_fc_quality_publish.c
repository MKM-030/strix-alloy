/* Source-only count1 D paired FC SHADOW publication foundation. Root alone
 * builds/reviews/runs it in a fresh serial owned process and epoch.
 * Default: no detours. HALOGEN_MTP_FC_QUALITY=shadow4-v1,
 * HALOGEN_MTP_FC_QUALITY_DIR=/tmp/alloy-mtp-fc-quality-<32 lowercase hex>,
 * and explicit HALOGEN_MTP_WIRE=D are required. The constructor creates the
 * directory exclusively. One unarmed native head may publish observed.bin;
 * root then binds that observation and publishes the exact 120-byte armed
 * descriptor before any further head. There is no skip mode: each original
 * e/h FC executes once. Discovery reads host identity/descriptor values only.
 * This source does not qualify transport, reset interception, integration,
 * arithmetic, NPU execution, parity, acceptance, or performance.
 * Root-only build: gcc -O2 -Wall -Wextra -Werror -shared -fPIC
 *   -fno-optimize-sibling-calls <this-source> -ldl -lcrypto -pthread -o <new.so>
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
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <time.h>
#include <unistd.h>

#if !defined(__x86_64__) || !defined(__linux__)
#error Linux x86-64 only
#endif
#define ENGINE_BYTES ((off_t)26052768)
#define ENGINE_SHA "ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b"
#define HEAD_RVA ((uintptr_t)0x17db310)
#define HEAD_OFFSET ((off_t)0x17da310)
#define HEAD_BYTES ((size_t)(0x17dc289-0x17db310))
#define HEAD_SHA "132f2da76d86694ffe5f120d61e304e57c685f3db72935c6d5e61bf7b0d5cc20"
#define FC_RVA ((uintptr_t)0x178cf90)
#define FC_OFFSET ((off_t)0x178bf90)
#define FC_BYTES ((size_t)(0x178efa7-0x178cf90))
#define FC_SHA "f8f9d77041011251d11d0b97d7298926aa053d5435310826a00c408e5bff24e9"
#define E_RETURN_RVA ((uintptr_t)0x17db548)
#define H_RETURN_RVA ((uintptr_t)0x17db663)
#define LAUNCH_RETURN_RVA ((uintptr_t)0x17fdba0)
#define E_KERNEL_RVA ((uintptr_t)0x18d6690)
#define H_KERNEL_RVA ((uintptr_t)0x18d66f0)
#define H_INPUT_RVA ((uintptr_t)0x18db210)
#define H_OUTPUT_RVA ((uintptr_t)0x18db228)
#define WIRE_RVA ((uintptr_t)0x18dccc0)
#define WIRE_GUARD_RVA ((uintptr_t)0x18dccc8)
#define MODEL_BYTES ((size_t)0xb10)
#define DESCRIPTOR_BYTES ((size_t)0x78)
#define E_BYTES 5120U
#define H_BYTES 20480U
#define PAIR_BYTES (E_BYTES+H_BYTES)
#define REQUEST_BODY_BYTES (2U*PAIR_BYTES)
#define MAX_CALLS 4U
#define WAIT_NS 200000000ULL
#define ARMWAIT_NS 2000000000ULL
#define LOG_LIMIT 32768U
#ifndef RENAME_NOREPLACE
#define RENAME_NOREPLACE 1U
#endif
static const char directory_prefix[]="/tmp/alloy-mtp-fc-quality-";
static const unsigned char head_signature[32]={
    0x55,0x41,0x57,0x41,0x56,0x41,0x55,0x41,0x54,0x53,0x48,0x81,0xec,0x98,0,0,
    0,0xb8,0xff,0xff,0xff,0xff,0x80,0xbf,0,0x09,0,0,0x01,0x0f,0x85,0x31
};
static const unsigned char fc_signature[32]={
    0x55,0x41,0x57,0x41,0x56,0x41,0x55,0x41,0x54,0x53,0x48,0x83,0xec,0x48,0x4c,0x89,
    0xcb,0x45,0x89,0xc5,0x89,0xcd,0x49,0x89,0xd6,0x49,0x89,0xf7,0x49,0x89,0xfc,0x4c
};
static const unsigned char e_call[5]={0xe8,0x48,0x1a,0xfb,0xff};
static const unsigned char h_call[5]={0xe8,0x2d,0x19,0xfb,0xff};
/* Natural SysV x86-64 layout equals the explicit little-endian wire formats. */
struct armed {
    unsigned char magic[8];
    uint32_t version,reserved;
    unsigned char nonce[16],epoch[16];
    uint64_t model;
    unsigned char model_binding[32],graph_binding[32];
};
struct header {
    unsigned char magic[8];
    uint32_t version,body_bytes;
    int32_t sequence,position,slot;
    uint32_t reserved;
    int32_t count,token,outer_position;
    uint32_t wire;
    unsigned char nonce[16],epoch[16];
    uint64_t model,reserved64;
    unsigned char model_binding[32],graph_binding[32],input_binding[32],request_binding[32];
};
struct request {struct header header;unsigned char body[REQUEST_BODY_BYTES];};
struct response {struct header header;unsigned char body[PAIR_BYTES],digest[32];};
struct observation {
    unsigned char magic[8];
    uint32_t version,record_bytes;
    unsigned char nonce[16];
    uint32_t pid,reserved;
    uint64_t starttime,head_caller,model;
    int32_t sequence,count,position,token,slot,outer_position;
    uint32_t wire,wire_guard;
    uint64_t tokens,e_input,e_output,h_input,h_output,seed,e_descriptor_address,h_descriptor_address,e_weight,h_weight;
    unsigned char e_descriptor[DESCRIPTOR_BYTES],h_descriptor[DESCRIPTOR_BYTES];
    int32_t head_result,head_errno,outer_position_after;
    uint32_t reserved_after;
    unsigned char digest[32];
};
_Static_assert(sizeof(struct armed)==120 && offsetof(struct armed,model)==48 &&
               offsetof(struct armed,model_binding)==56,"armed wire ABI");
_Static_assert(sizeof(struct header)==224 && offsetof(struct header,nonce)==48 &&
               offsetof(struct header,model)==80 && offsetof(struct header,model_binding)==96 &&
               offsetof(struct header,request_binding)==192,"FC header ABI");
_Static_assert(sizeof(struct request)==51424 && sizeof(struct response)==25856,"FC packet extents");
_Static_assert(sizeof(struct observation)==464 && offsetof(struct observation,starttime)==40 &&
               offsetof(struct observation,tokens)==96 && offsetof(struct observation,e_descriptor)==176 &&
               offsetof(struct observation,head_result)==416 && offsetof(struct observation,digest)==432,
               "discovery observation ABI");
typedef int32_t (*head_fn)(void *,const int32_t *,int32_t,int32_t);
typedef void (*fc_fn)(void *,const uint16_t *,uint16_t *,int32_t,int32_t,int64_t);
typedef struct {unsigned x,y,z;} hip_dim3;
typedef int (*launch_fn)(const void *,hip_dim3,hip_dim3,void **,size_t,void *);
typedef int (*sync_fn)(void);
typedef int (*copy_fn)(void *,const void *,size_t,int);
struct context {
    struct armed arm;
    uintptr_t model,tokens,head_caller,e_input,e_output,h_input,h_output,seed;
    int32_t token,count,position,slot,outer_position,head_result,head_errno;
    unsigned sequence,e_calls,h_calls,phase,original_calls[2],launches[2],launch_ok[2];
    unsigned sync_attempts,sync_ok,copy_attempts,copy_ok,restore_attempts,restore_ok;
    unsigned captured,response_ready,published,restored,completed,discovering,pair_observed,wire_guard;
    unsigned char e_descriptor[DESCRIPTOR_BYTES],h_descriptor[DESCRIPTOR_BYTES];
    char native_e_hash[65],native_h_hash[65],candidate_e_hash[65],candidate_h_hash[65];
    const char *error,*outcome;
    struct request request;
    struct response response;
};
static struct context contexts[MAX_CALLS]; /* Fixed < 320 KiB host-only staging. */
static struct context discovery; /* One further fixed host context, no tensor capture. */
static struct observation observed;
_Static_assert(sizeof contexts+sizeof discovery+sizeof observed<=400U*1024U,"bounded host discovery/shadow staging");
static uint32_t process_pid;
static uint64_t process_starttime;
static unsigned discovery_reserved,observed_published;
static int32_t last_position,last_outer_position;
static _Thread_local struct context *active;
static _Thread_local unsigned head_depth;
static head_fn original_head;
static fc_fn original_fc;
static launch_fn real_launch;
static sync_fn hip_sync;
static copy_fn hip_copy;
static uintptr_t engine_base;
static unsigned char run_nonce[16];
static int directory_fd=-1,log_fd=-1;
static unsigned calls,in_flight,forward_calls,excluded_calls,overlaps;
static struct armed epoch_arm;
static unsigned epoch_armed;
/* Exposure lasts until full-head exit: after seed-add, FC rollback is insufficient. */
static unsigned output_exposed,log_bytes;
static _Atomic int initialized,disabled;
static pthread_mutex_t state_mutex=PTHREAD_MUTEX_INITIALIZER;
static pthread_once_t symbols_once=PTHREAD_ONCE_INIT;

static _Noreturn void fatal(const char *reason) {
    dprintf(STDERR_FILENO,"[mtp-fc-quality] fatal reason=%s errno=%d\n",reason,errno);
    _exit(79);
}
static void lock_state(void) {if (pthread_mutex_lock(&state_mutex)) fatal("state-lock");}
static void unlock_state(void) {if (pthread_mutex_unlock(&state_mutex)) fatal("state-unlock");}
static void reject(struct context *s,const char *reason) {
    if (s && !s->error) s->error=reason;
    atomic_store(&disabled,1);
}
static uintptr_t pointer_at(const void *object,size_t offset) {
    uintptr_t value;memcpy(&value,(const unsigned char *)object+offset,sizeof value);return value;
}
static int32_t int32_at(const void *object,size_t offset) {
    int32_t value;memcpy(&value,(const unsigned char *)object+offset,sizeof value);return value;
}
static int nonzero(const void *data,size_t bytes) {
    const unsigned char *at=data;unsigned char bits=0;
    for (size_t i=0;i<bytes;i++) bits|=at[i];
    return bits!=0;
}
static int mapped_span(uintptr_t address,size_t bytes,const char *wanted) {
    if (!address || !bytes || bytes>UINTPTR_MAX-address) return 0;
    FILE *file=fopen("/proc/self/maps","re");if (!file) return 0;
    char line[4096],permissions[5];unsigned long low,high;int found=0;
    while (fgets(line,sizeof line,file)) {
        if (sscanf(line,"%lx-%lx %4s",&low,&high,permissions)!=3) continue;
        if (address>=low && address+bytes<=high &&
            (wanted?!strcmp(permissions,wanted):permissions[0]=='r')) {found=1;break;}
    }
    int bad=ferror(file);if (fclose(file)) bad=1;return bad?0:found;
}
static int span(uintptr_t p,size_t bytes) {return p && bytes && bytes<=UINTPTR_MAX-p;}
static int disjoint(uintptr_t a,size_t na,uintptr_t b,size_t nb) {
    return span(a,na) && span(b,nb) && (a+na<=b || b+nb<=a);
}
static int digest_two(const void *a,size_t na,const void *b,size_t nb,unsigned char digest[32]) {
    EVP_MD_CTX *ctx=EVP_MD_CTX_new();unsigned length=0;if (!ctx) return 0;
    int ok=EVP_DigestInit_ex(ctx,EVP_sha256(),NULL)==1 && EVP_DigestUpdate(ctx,a,na)==1 &&
        (!nb || EVP_DigestUpdate(ctx,b,nb)==1) && EVP_DigestFinal_ex(ctx,digest,&length)==1 && length==32;
    EVP_MD_CTX_free(ctx);return ok;
}
static int buffer_hash(const void *data,size_t bytes,char hex[65]) {
    unsigned char digest[32];if (!digest_two(data,bytes,NULL,0,digest)) return 0;
    for (unsigned i=0;i<32;i++) snprintf(hex+2*i,3,"%02x",(unsigned)digest[i]);
    return 1;
}
static int finite_bf16(const unsigned char *data,size_t bytes) {
    if (bytes%2) return 0;
    for (size_t i=0;i<bytes;i+=2) {
        uint16_t bits;memcpy(&bits,data+i,2);if ((bits&0x7f80)==0x7f80) return 0;
    }
    return 1;
}
static int same_stat(const struct stat *a,const struct stat *b) {
    return a->st_dev==b->st_dev && a->st_ino==b->st_ino && a->st_size==b->st_size &&
        a->st_mode==b->st_mode && a->st_uid==b->st_uid && a->st_nlink==b->st_nlink &&
        a->st_mtim.tv_sec==b->st_mtim.tv_sec && a->st_mtim.tv_nsec==b->st_mtim.tv_nsec &&
        a->st_ctim.tv_sec==b->st_ctim.tv_sec && a->st_ctim.tv_nsec==b->st_ctim.tv_nsec;
}
static int write_all(int fd,const void *data,size_t bytes) {
    const unsigned char *at=data;
    while (bytes) {
        ssize_t n=write(fd,at,bytes);if (n<0 && errno==EINTR) continue;
        if (n<=0) return 0;
        at+=n;bytes-=(size_t)n;
    }
    return 1;
}
/* Linux field22 is process start time in clock ticks since boot. The comm
 * field may contain spaces/parentheses; parse after its final ')', not by a
 * naive whitespace split. The bounded kernel file is identity, not payload. */
static int read_process_identity(uint32_t *pid,uint64_t *starttime) {
    int fd=open("/proc/self/stat",O_RDONLY|O_CLOEXEC|O_NOFOLLOW|O_NONBLOCK);
    if (fd<0) return 0;
    char record[4097];ssize_t bytes=-1;unsigned attempts=0;
    do {bytes=read(fd,record,sizeof record-1);} while (bytes<0 && errno==EINTR && ++attempts<4);
    int ok=bytes>0 && bytes<(ssize_t)sizeof record-1;
    if (close(fd)) ok=0;
    if (!ok) return 0;
    record[bytes]=0;char *end=NULL;errno=0;
    unsigned long parsed_pid=strtoul(record,&end,10);
    if (errno || !end || end==record || end[0]!=' ' || end[1]!='(' ||
        !parsed_pid || parsed_pid>INT32_MAX || parsed_pid!=(unsigned long)getpid()) return 0;
    char *last=strrchr(end+1,')');
    if (!last || last[1]!=' ' || !last[2]) return 0;
    char *at=last+2;
    for (unsigned field=3;field<=22;field++) {
        while (*at==' ' || *at=='\t' || *at=='\n') at++;
        if (!*at) return 0;
        char *first=at;while (*at && *at!=' ' && *at!='\t' && *at!='\n') at++;
        if (field==22) {
            for (char *digit=first;digit<at;digit++) if (*digit<'0' || *digit>'9') return 0;
            errno=0;unsigned long long ticks=strtoull(first,&end,10);
            if (errno || end!=at || !ticks) return 0;
            *pid=(uint32_t)parsed_pid;*starttime=(uint64_t)ticks;return 1;
        }
    }
    return 0;
}
static int same_process(void) {
    uint32_t pid=0;uint64_t starttime=0;
    return read_process_identity(&pid,&starttime) && pid==process_pid && starttime==process_starttime;
}
/* No-follow exact regular owner-only files, unchanged handle and pathname. */
static int read_exact_file(const char *name,void *data,size_t bytes,int pending_link) {
    int fd=openat(directory_fd,name,O_RDONLY|O_CLOEXEC|O_NOFOLLOW|O_NONBLOCK);
    if (fd<0) return errno==ENOENT?0:-1;
    struct stat before,after,path_after;
    int ok=!fstat(fd,&before) && S_ISREG(before.st_mode) && before.st_size==(off_t)bytes &&
        before.st_uid==geteuid() && (before.st_mode&0777)==0600;
    if (ok && pending_link && before.st_nlink==2) return close(fd)?-1:0;
    ok=ok && before.st_nlink==1;size_t done=0;
    while (ok && done<bytes) {
        ssize_t n=pread(fd,(unsigned char *)data+done,bytes-done,(off_t)done);
        if (n<0 && errno==EINTR) continue;
        if (n<=0) {ok=0;break;}done+=(size_t)n;
    }
    ok=ok && !fstat(fd,&after) && !fstatat(directory_fd,name,&path_after,AT_SYMLINK_NOFOLLOW) &&
        same_stat(&before,&after) && same_stat(&after,&path_after);
    if (close(fd)) ok=0;
    return ok?1:-1;
}
static int read_arm(struct armed *arm) {
    int ready=read_exact_file("armed",arm,sizeof *arm,0);if (ready!=1) return ready;
    if (memcmp(arm->magic,"HGNFCA01",8) || arm->version!=1 || arm->reserved || !arm->model ||
        memcmp(arm->nonce,run_nonce,16) || !nonzero(arm->nonce,16) || !nonzero(arm->epoch,16) ||
        !nonzero(arm->model_binding,32) || !nonzero(arm->graph_binding,32)) return -1;
    return 1;
}
static int observation_live(uintptr_t model);
static int same_observed_file(void) {
    struct observation copy;
    return observed_published && read_exact_file("observed.bin",&copy,sizeof copy,0)==1 &&
        !memcmp(&copy,&observed,sizeof copy);
}
static int same_arm(const struct context *s) {
    struct armed arm;return observation_live(s->model) && same_observed_file() && read_arm(&arm)==1 &&
        !memcmp(&arm,&s->arm,sizeof arm) && arm.model==s->model;
}
static int known_head_caller(uintptr_t caller) {
    return caller==0x17dcc08 || caller==0x17dcd54 || caller==0x17dcf49 || caller==0x17de236;
}
static int normal_descriptor(const unsigned char *descriptor) {
    uintptr_t weight=pointer_at(descriptor,0x10);
    return !pointer_at(descriptor,0) && !pointer_at(descriptor,0x30) &&
        span(weight,6963200U) && !(weight&15U);
}
static int wire_D(void) {
    return *(const unsigned char *)(engine_base+WIRE_RVA)=='D' &&
        *(const unsigned char *)(engine_base+WIRE_GUARD_RVA)!=0;
}
static int stable_native(const struct context *s,int paired) {
    if (!same_process() || !mapped_span(s->model,MODEL_BYTES,NULL) || !mapped_span(s->tokens,sizeof(int32_t),NULL) ||
        ((const unsigned char *)s->model)[0x900]!=1 || int32_at((void *)s->tokens,0)!=s->token ||
        int32_at((void *)s->model,0x220)!=s->outer_position || int32_at((void *)s->model,0xa0)!=s->slot ||
        memcmp((void *)(s->model+0x908),s->e_descriptor,DESCRIPTOR_BYTES) ||
        memcmp((void *)(s->model+0x980),s->h_descriptor,DESCRIPTOR_BYTES) || !wire_D() ||
        *(const unsigned char *)(engine_base+WIRE_GUARD_RVA)!=s->wire_guard ||
        pointer_at((void *)s->model,0x6c8)!=s->e_input || pointer_at((void *)s->model,0xb00)!=s->e_output ||
        pointer_at((void *)s->model,0x6d0)!=s->seed) return 0;
    return !paired || (pointer_at((void *)engine_base,H_INPUT_RVA)==s->h_input &&
                       pointer_at((void *)engine_base,H_OUTPUT_RVA)==s->h_output);
}
static int stable(const struct context *s,int paired) {
    if (atomic_load(&disabled) || (!s->discovering && !same_arm(s)) || !stable_native(s,paired)) return 0;
    lock_state();int serial=in_flight==1;unlock_state();return serial;
}
static int pair_spans(const struct context *s) {
    uintptr_t p[4]={s->e_input,s->h_input,s->e_output,s->h_output};
    size_t n[4]={E_BYTES,H_BYTES,E_BYTES,H_BYTES};
    for (unsigned i=0;i<4;i++) {
        if (!disjoint(p[i],n[i],s->seed,H_BYTES)) return 0;
        for (unsigned j=0;j<i;j++) if (!disjoint(p[i],n[i],p[j],n[j])) return 0;
    }
    return 1;
}
/* Cached discovery pointer/descriptor identity is a separate admission gate;
 * nonzero opaque manifest hashes alone never admit candidate writes. The host
 * tokens pointer belongs to the historical discovery call and is not reused. */
static int observation_live(uintptr_t model) {
    return observed_published && observed.pid==process_pid && observed.starttime==process_starttime &&
        same_process() && model==observed.model && mapped_span(model,MODEL_BYTES,NULL) &&
        ((const unsigned char *)model)[0x900]==1 && int32_at((void *)model,0xa0)==observed.slot &&
        !memcmp((void *)(model+0x908),observed.e_descriptor,DESCRIPTOR_BYTES) &&
        !memcmp((void *)(model+0x980),observed.h_descriptor,DESCRIPTOR_BYTES) &&
        pointer_at((void *)model,0x6c8)==observed.e_input && pointer_at((void *)model,0xb00)==observed.e_output &&
        pointer_at((void *)model,0x6d0)==observed.seed &&
        pointer_at((void *)engine_base,H_INPUT_RVA)==observed.h_input &&
        pointer_at((void *)engine_base,H_OUTPUT_RVA)==observed.h_output && wire_D() &&
        *(const unsigned char *)(engine_base+WIRE_GUARD_RVA)==observed.wire_guard;
}
static int valid_head_entry(void *model,const int32_t *tokens,int32_t count,int32_t position,uintptr_t caller) {
    return count==1 && position>=0 && known_head_caller(caller) && same_process() &&
        mapped_span((uintptr_t)model,MODEL_BYTES,NULL) && mapped_span((uintptr_t)tokens,sizeof *tokens,NULL) &&
        ((const unsigned char *)model)[0x900]==1 && int32_at(tokens,0)>=0 &&
        int32_at(model,0x220)>=0 && int32_at(model,0xa0)>=0;
}
static void context_entry(struct context *s,void *model,const int32_t *tokens,int32_t count,int32_t position,uintptr_t caller) {
    s->model=(uintptr_t)model;s->tokens=(uintptr_t)tokens;s->head_caller=caller;
    s->token=int32_at(tokens,0);s->count=count;s->position=position;
    s->slot=int32_at(model,0xa0);s->outer_position=int32_at(model,0x220);s->seed=pointer_at(model,0x6d0);
    memcpy(s->e_descriptor,(const unsigned char *)model+0x908,DESCRIPTOR_BYTES);
    memcpy(s->h_descriptor,(const unsigned char *)model+0x980,DESCRIPTOR_BYTES);
    if (!normal_descriptor(s->e_descriptor) || !normal_descriptor(s->h_descriptor)) reject(s,"head-descriptor-contract");
}
static int discovery_after_head(const struct context *s) {
    /* Native installs the ABI position after seed-add; the outer position must
     * not be compared with its pre-seed value at full-head exit. All descriptor
     * and device buffer identities must nevertheless remain unchanged. */
    return same_process() && mapped_span(s->model,MODEL_BYTES,NULL) &&
        mapped_span(s->tokens,sizeof(int32_t),NULL) && int32_at((void *)s->tokens,0)==s->token &&
        ((const unsigned char *)s->model)[0x900]==1 && int32_at((void *)s->model,0xa0)==s->slot &&
        int32_at((void *)s->model,0x220)>=0 &&
        !memcmp((void *)(s->model+0x908),s->e_descriptor,DESCRIPTOR_BYTES) &&
        !memcmp((void *)(s->model+0x980),s->h_descriptor,DESCRIPTOR_BYTES) &&
        pointer_at((void *)s->model,0x6c8)==s->e_input && pointer_at((void *)s->model,0xb00)==s->e_output &&
        pointer_at((void *)s->model,0x6d0)==s->seed &&
        pointer_at((void *)engine_base,H_INPUT_RVA)==s->h_input &&
        pointer_at((void *)engine_base,H_OUTPUT_RVA)==s->h_output && wire_D() &&
        *(const unsigned char *)(engine_base+WIRE_GUARD_RVA)==s->wire_guard && pair_spans(s);
}
/* Called under the all-head mutex after the original head returns, before the
 * in-flight count is released. Exactly one fixed record; no device copies. */
static int publish_observation(struct context *s) {
    struct armed premature;
    if (observed_published || in_flight!=1 || atomic_load(&disabled) || s->error ||
        !s->pair_observed || s->head_result<0 || !discovery_after_head(s) || read_arm(&premature)!=0) return 0;
    memcpy(observed.magic,"HGNFCO01",8);observed.version=1;observed.record_bytes=sizeof observed;
    memcpy(observed.nonce,run_nonce,16);observed.pid=process_pid;observed.starttime=process_starttime;
    observed.head_caller=s->head_caller;observed.model=s->model;observed.sequence=0;
    observed.count=s->count;observed.position=s->position;observed.token=s->token;observed.slot=s->slot;
    observed.outer_position=s->outer_position;observed.wire='D';observed.wire_guard=s->wire_guard;
    observed.tokens=s->tokens;observed.e_input=s->e_input;observed.e_output=s->e_output;
    observed.h_input=s->h_input;observed.h_output=s->h_output;observed.seed=s->seed;
    observed.e_descriptor_address=s->model+0x908;observed.h_descriptor_address=s->model+0x980;
    observed.e_weight=pointer_at(s->e_descriptor,0x10);observed.h_weight=pointer_at(s->h_descriptor,0x10);
    memcpy(observed.e_descriptor,s->e_descriptor,DESCRIPTOR_BYTES);memcpy(observed.h_descriptor,s->h_descriptor,DESCRIPTOR_BYTES);
    observed.head_result=s->head_result;observed.head_errno=s->head_errno;
    observed.outer_position_after=int32_at((void *)s->model,0x220);
    if (!digest_two(&observed,offsetof(struct observation,digest),NULL,0,observed.digest)) return 0;
    int fd=openat(directory_fd,"observed.partial",O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC|O_NOFOLLOW,0600);
    if (fd<0) return 0;
    struct stat status;int ok=!fstat(fd,&status) && S_ISREG(status.st_mode) && status.st_uid==geteuid() &&
        status.st_nlink==1 && (status.st_mode&0777)==0600 && !status.st_size &&
        write_all(fd,&observed,sizeof observed) && !fsync(fd);
    if (close(fd)) ok=0;
    if (ok && syscall(SYS_renameat2,directory_fd,"observed.partial",directory_fd,"observed.bin",RENAME_NOREPLACE)) ok=0;
    if (!ok) {if (unlinkat(directory_fd,"observed.partial",0) && errno!=ENOENT) return 0;return 0;}
    if (fsync(directory_fd)) return 0;
    observed_published=1;last_position=s->position;last_outer_position=observed.outer_position_after;
    return same_observed_file();
}
static void resolve_symbols(void) {
    real_launch=(launch_fn)dlsym(RTLD_NEXT,"hipLaunchKernel");
    hip_sync=(sync_fn)dlsym(RTLD_NEXT,"hipDeviceSynchronize");
    hip_copy=(copy_fn)dlsym(RTLD_NEXT,"hipMemcpy");
}
/* This observer establishes the actual normal Q8 M1/M4 route. The retained
 * wave branches load 18d6690/18d66f0 then jump to common launch 17fdb8e;
 * its PLT call returns to 17fdba0. Device pointers are values, never host data. */
int hipLaunchKernel(const void *function,hip_dim3 grid,hip_dim3 block,void **args,size_t shared,void *stream) {
    int incoming_errno=errno;uintptr_t address=(uintptr_t)__builtin_return_address(0);
    uintptr_t caller=address>=engine_base?address-engine_base:UINTPTR_MAX;
    if (pthread_once(&symbols_once,resolve_symbols) || !real_launch) fatal("launch-symbol");
    struct context *s=active;unsigned phase=s?s->phase:0;int valid=0;
    if (phase==1 || phase==2) {
        unsigned side=phase-1;s->launches[side]++;
        uintptr_t expected_kernel=engine_base+(side?H_KERNEL_RVA:E_KERNEL_RVA);
        valid=s->launches[side]==1 && caller==LAUNCH_RETURN_RVA && (uintptr_t)function==expected_kernel &&
            grid.x==160 && grid.y==1 && grid.z==1 && block.x==256 && block.y==1 && block.z==1 &&
            !shared && !stream && mapped_span((uintptr_t)args,5*sizeof(void *),NULL);
        uintptr_t values[5]={0};
        if (valid) {
            memcpy(values,args,sizeof values);
            for (unsigned i=0;i<5;i++) if (!mapped_span(values[i],8,NULL)) valid=0;
        }
        if (valid) {
            valid=pointer_at((void *)values[0],0)==pointer_at(side?s->h_descriptor:s->e_descriptor,0x10) &&
                pointer_at((void *)values[1],0)==(side?s->h_input:s->e_input) &&
                pointer_at((void *)values[2],0)==(side?s->h_output:s->e_output) &&
                pointer_at((void *)values[3],0)==2560 && pointer_at((void *)values[4],0)==2560;
        }
        if (!valid) reject(s,"native-fc-launch-contract");
    }
    errno=incoming_errno;int result=real_launch(function,grid,block,args,shared,stream);int result_errno=errno;
    if (phase==1 || phase==2) {
        if (valid && !result) s->launch_ok[phase-1]++;
        else if (result) reject(s,"native-fc-launch-result");
    }
    errno=result_errno;return result;
}
static int checked_sync(struct context *s) {
    s->sync_attempts++;int result=hip_sync();if (!result) s->sync_ok++;return result==0;
}
static int checked_copy(struct context *s,void *to,const void *from,size_t bytes,int kind) {
    s->copy_attempts++;int result=hip_copy(to,from,bytes,kind);if (!result) s->copy_ok++;return result==0;
}
static int capture_one(struct context *s,void *to,uintptr_t from,size_t bytes) {
    return stable(s,1) && checked_copy(s,to,(void *)from,bytes,2) && stable(s,1);
}
static int publish_request(struct context *s) {
    char temporary[40],final[40];
    snprintf(temporary,sizeof temporary,"%03u-request.partial",s->sequence);
    snprintf(final,sizeof final,"%03u-request.bin",s->sequence);
    int fd=openat(directory_fd,temporary,O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC|O_NOFOLLOW,0600);
    if (fd<0) return 0;
    struct stat status;int ok=!fstat(fd,&status) && S_ISREG(status.st_mode) && status.st_uid==geteuid() &&
        status.st_nlink==1 && (status.st_mode&0777)==0600 && !status.st_size &&
        write_all(fd,&s->request,sizeof s->request) && !fsync(fd);
    if (close(fd)) ok=0;
    if (ok && syscall(SYS_renameat2,directory_fd,temporary,directory_fd,final,RENAME_NOREPLACE)) ok=0;
    if (!ok) {if (unlinkat(directory_fd,temporary,0) && errno!=ENOENT) return 0;return 0;}
    return !fsync(directory_fd);
}
static uint64_t now_ns(void) {
    struct timespec value;if (clock_gettime(CLOCK_MONOTONIC,&value)) return 0;
    return (uint64_t)value.tv_sec*1000000000ULL+(uint64_t)value.tv_nsec;
}
/* One discovery rendezvous before the native caller can enter another head.
 * The original head is complete but stays registered in-flight. Do not hold
 * the state mutex while polling: any other head must register and invalidate
 * this serial epoch. No device operation is performed in this wait. */
static int await_discovery_arm(struct context *s) {
    uint64_t started=now_ns();if (!started) return -1;
    for (;;) {
        uint64_t current=now_ns();if (!current || current<started) return -1;
        if (current-started>=ARMWAIT_NS) return 0;
        if (atomic_load(&disabled) || !observation_live(s->model) || !same_observed_file()) return -1;
        struct armed arm;int ready=read_arm(&arm);
        if (ready<0 || (ready==1 && arm.model!=observed.model)) return -1;
        if (ready==1) {
            lock_state();
            struct armed confirmed;
            int valid=in_flight==1 &&
                !atomic_load(&disabled) && observation_live(s->model) && same_observed_file();
            if (valid && (read_arm(&confirmed)!=1 || memcmp(&arm,&confirmed,sizeof arm))) valid=0;
            current=now_ns();
            if (!current || current<started || current-started>=ARMWAIT_NS) valid=0;
            if (valid && epoch_armed && memcmp(&arm,&epoch_arm,sizeof arm)) valid=0;
            if (valid) {epoch_arm=arm;epoch_armed=1;}
            unlock_state();
            return valid?1:-1;
        }
        current=now_ns();if (!current || current<started) return -1;
        if (current-started>=ARMWAIT_NS) return 0;
        struct timespec pause={0,10000000};if (nanosleep(&pause,NULL) && errno!=EINTR) return -1;
    }
}
static int await_response(struct context *s) {
    char name[40];snprintf(name,sizeof name,"%03u-response.bin",s->sequence);
    uint64_t started=now_ns();if (!started) return -1;
    for (;;) {
        uint64_t current=now_ns();if (!current || current<started) return -1;
        if (current-started>=WAIT_NS) return 0;
        if (!stable(s,1)) return -1;
        int ready=read_exact_file(name,&s->response,sizeof s->response,1);if (ready<0) return -1;
        if (ready==1) {
            struct header expected=s->request.header;memcpy(expected.magic,"HGNFCPR1",8);expected.body_bytes=PAIR_BYTES;
            unsigned char digest[32];
            if (memcmp(&s->response.header,&expected,sizeof expected) ||
                !digest_two(&s->response,offsetof(struct response,digest),NULL,0,digest) ||
                memcmp(digest,s->response.digest,32) || !finite_bf16(s->response.body,PAIR_BYTES) ||
                !stable(s,1)) return -1;
            current=now_ns();if (!current || current<started) return -1;
            if (current-started>=WAIT_NS) return 0;
            return 1;
        }
        current=now_ns();if (!current || current<started) return -1;
        if (current-started>=WAIT_NS) return 0;
        struct timespec pause={0,10000000};if (nanosleep(&pause,NULL) && errno!=EINTR) return -1;
    }
}
static void rollback_pair(struct context *s) {
    /* Never short-circuit the second restore or final synchronization. */
    if (!stable_native(s,1)) fatal("rollback-native-identity");
    s->restore_attempts++;
    int e=checked_copy(s,(void *)s->e_output,s->request.body+PAIR_BYTES,E_BYTES,1);
    if (!stable_native(s,1)) fatal("rollback-e-identity");
    s->restore_attempts++;
    int h=checked_copy(s,(void *)s->h_output,s->request.body+PAIR_BYTES+E_BYTES,H_BYTES,1);
    int synced=checked_sync(s);
    if (!e || !h || !synced || !stable_native(s,1)) fatal("paired-native-output-restore");
    s->restore_ok=2;s->restored=1;s->outcome="native_restored";
    reject(s,"candidate-copy-or-identity");
}
static void paired_shadow(struct context *s) {
    s->outcome="native_capture_failed";
    if (s->error || s->e_calls!=1 || s->h_calls!=1 || s->original_calls[0]!=1 || s->original_calls[1]!=1 ||
        s->launches[0]!=1 || s->launches[1]!=1 || s->launch_ok[0]!=1 || s->launch_ok[1]!=1 ||
        !hip_sync || !hip_copy || !stable(s,1) || !pair_spans(s) || !checked_sync(s) || !stable(s,1) ||
        !capture_one(s,s->request.body,s->e_input,E_BYTES) ||
        !capture_one(s,s->request.body+E_BYTES,s->h_input,H_BYTES) ||
        !capture_one(s,s->request.body+PAIR_BYTES,s->e_output,E_BYTES) ||
        !capture_one(s,s->request.body+PAIR_BYTES+E_BYTES,s->h_output,H_BYTES) ||
        !finite_bf16(s->request.body,REQUEST_BODY_BYTES)) {reject(s,"paired-native-capture");return;}
    s->captured=1;struct header *header=&s->request.header;
    memcpy(header->magic,"HGNFCPQ1",8);header->version=1;header->body_bytes=REQUEST_BODY_BYTES;
    header->sequence=(int32_t)s->sequence;header->position=s->position;header->slot=s->slot;
    header->count=s->count;header->token=s->token;header->outer_position=s->outer_position;header->wire='D';
    memcpy(header->nonce,s->arm.nonce,16);memcpy(header->epoch,s->arm.epoch,16);header->model=s->model;
    memcpy(header->model_binding,s->arm.model_binding,32);memcpy(header->graph_binding,s->arm.graph_binding,32);
    if (!digest_two(s->request.body,PAIR_BYTES,NULL,0,header->input_binding) ||
        !digest_two(header,offsetof(struct header,request_binding),s->request.body,REQUEST_BODY_BYTES,header->request_binding) ||
        !buffer_hash(s->request.body+PAIR_BYTES,E_BYTES,s->native_e_hash) ||
        !buffer_hash(s->request.body+PAIR_BYTES+E_BYTES,H_BYTES,s->native_h_hash) ||
        !stable(s,1) || !publish_request(s)) {s->outcome="native_request_failed";reject(s,"request-publication");return;}
    int ready=await_response(s);
    if (!ready) {s->outcome="native_timeout";return;}
    if (ready<0) {s->outcome="native_invalid_response";reject(s,"response-contract");return;}
    s->response_ready=1;
    if (!buffer_hash(s->response.body,E_BYTES,s->candidate_e_hash) ||
        !buffer_hash(s->response.body+E_BYTES,H_BYTES,s->candidate_h_hash) || !stable(s,1)) {
        s->outcome="native_invalid_identity";reject(s,"pre-publication-identity");return;
    }
    lock_state();
    if (in_flight!=1 || output_exposed || atomic_load(&disabled)) {
        unlock_state();reject(s,"publication-overlap");return;
    }
    output_exposed=1;unlock_state();
    /* Any full-head overlap from here through this head's exit fail-stops.
     * No candidate write is admitted without the exact armed native model. */
    if (!same_arm(s) || !stable_native(s,1)) {
        lock_state();output_exposed=0;unlock_state();reject(s,"publication-arm-identity");return;
    }
    int e=checked_copy(s,(void *)s->e_output,s->response.body,E_BYTES,1);
    if (!stable_native(s,1)) fatal("candidate-e-native-identity");
    if (!e || !same_arm(s) || atomic_load(&disabled)) {rollback_pair(s);return;}
    int h=checked_copy(s,(void *)s->h_output,s->response.body+E_BYTES,H_BYTES,1);
    int synced=checked_sync(s);
    if (!stable_native(s,1)) fatal("candidate-h-native-identity");
    if (!h || !synced || !same_arm(s) || atomic_load(&disabled)) {rollback_pair(s);return;}
    s->published=1;s->outcome="candidate_pair_published";
}
__attribute__((noinline)) static void shadow_fc(void *descriptor,const uint16_t *input,uint16_t *output,
    int32_t n,int32_t m,int64_t k) {
    int incoming_errno=errno;uintptr_t address=(uintptr_t)__builtin_return_address(0);
    uintptr_t caller=address>=engine_base?address-engine_base:UINTPTR_MAX;
    struct context *s=active;unsigned phase=0;
    if (s && (caller==E_RETURN_RVA || caller==H_RETURN_RVA)) {
        if (caller==E_RETURN_RVA) {
            s->e_calls++;s->original_calls[0]++;
            s->e_input=(uintptr_t)input;s->e_output=(uintptr_t)output;
            s->wire_guard=*(const unsigned char *)(engine_base+WIRE_GUARD_RVA);
            if (s->e_calls!=1 || s->h_calls || descriptor!=(void *)(s->model+0x908) ||
                n!=2560 || m!=1 || k!=2560 || !normal_descriptor(s->e_descriptor) ||
                !disjoint(s->e_input,E_BYTES,s->e_output,E_BYTES) || !stable(s,0)) reject(s,"embedding-fc-contract");
            else phase=1;
        } else {
            s->h_calls++;s->original_calls[1]++;
            s->h_input=(uintptr_t)input;s->h_output=(uintptr_t)output;
            if (s->e_calls!=1 || s->h_calls!=1 || descriptor!=(void *)(s->model+0x980) ||
                n!=2560 || m!=4 || k!=2560 || !normal_descriptor(s->h_descriptor) ||
                !pair_spans(s) || !stable(s,1)) reject(s,"hidden-fc-contract");
            else phase=2;
        }
    }
    unsigned saved_phase=s?s->phase:0;if (s) s->phase=phase;
    errno=incoming_errno;
    original_fc(descriptor,input,output,n,m,k); /* Exactly once for every dispatcher call. */
    int result_errno=errno;if (s) s->phase=saved_phase;
    if (phase && (s->launches[phase-1]!=1 || s->launch_ok[phase-1]!=1 || !stable(s,phase==2)))
        reject(s,"original-fc-completion");
    if (phase==2 && !s->error) {
        if (s->discovering) {
            if (s->e_calls==1 && s->h_calls==1 && s->original_calls[0]==1 && s->original_calls[1]==1 &&
                s->launches[0]==1 && s->launches[1]==1 && s->launch_ok[0]==1 && s->launch_ok[1]==1 &&
                stable(s,1) && pair_spans(s)) s->pair_observed=1;
            else reject(s,"discovery-exact-native-pair");
        } else paired_shadow(s);
    }
    errno=result_errno;
}
static void log_context(struct context *s) {
    char binding[65]="";
    /* The transported binding is already a digest; encode it directly. */
    for (unsigned i=0;i<32;i++) snprintf(binding+2*i,3,"%02x",(unsigned)s->request.header.request_binding[i]);
    char line[4096];int bytes=snprintf(line,sizeof line,
        "{\"sequence\":%u,\"discovery\":%s,\"outcome\":\"%s\",\"error\":%s%s%s,\"position\":%d,\"outer_position\":%d,"
        "\"slot\":%d,\"token\":%d,\"model\":\"0x%" PRIxPTR "\",\"head_caller_rva\":\"0x%" PRIxPTR "\","
        "\"head_result\":%d,\"head_errno\":%d,\"completed\":%s,\"e_calls\":%u,\"h_calls\":%u,"
        "\"original_e_calls\":%u,\"original_h_calls\":%u,\"e_launches\":%u,\"h_launches\":%u,"
        "\"e_launch_ok\":%u,\"h_launch_ok\":%u,\"captured\":%s,\"response_ready\":%s,"
        "\"candidate_published\":%s,\"native_restored\":%s,\"sync_attempts\":%u,\"sync_ok\":%u,"
        "\"copy_attempts\":%u,\"copy_ok\":%u,\"restore_attempts\":%u,\"restore_ok\":%u,"
        "\"request_binding\":\"%s\",\"native_e_sha256\":\"%s\",\"native_h_sha256\":\"%s\","
        "\"candidate_e_sha256\":\"%s\",\"candidate_h_sha256\":\"%s\",\"forward_calls\":%u,"
        "\"excluded_count_calls\":%u,\"overlaps\":%u,\"integration_qualified\":false,"
        "\"arithmetic_qualified\":false,\"npu_qualified\":false,\"parity_qualified\":false,"
        "\"acceptance_qualified\":false,\"performance_qualified\":false,\"native_reset_interception_qualified\":false}\n",
        s->sequence,s->discovering?"true":"false",s->outcome?s->outcome:"native_unmatched",s->error?"\"":"",s->error?s->error:"null",s->error?"\"":"",
        s->position,s->outer_position,s->slot,s->token,s->model,s->head_caller,s->head_result,s->head_errno,
        s->completed?"true":"false",s->e_calls,s->h_calls,s->original_calls[0],s->original_calls[1],
        s->launches[0],s->launches[1],s->launch_ok[0],s->launch_ok[1],s->captured?"true":"false",
        s->response_ready?"true":"false",s->published?"true":"false",s->restored?"true":"false",
        s->sync_attempts,s->sync_ok,s->copy_attempts,s->copy_ok,s->restore_attempts,s->restore_ok,binding,
        s->native_e_hash,s->native_h_hash,s->candidate_e_hash,s->candidate_h_hash,forward_calls,excluded_calls,overlaps);
    if (bytes<=0 || bytes>=(int)sizeof line || (unsigned)bytes>LOG_LIMIT-log_bytes ||
        !write_all(log_fd,line,(size_t)bytes) || fsync(log_fd)) {reject(s,"records-write");return;}
    log_bytes+=(unsigned)bytes;
}
__attribute__((noinline)) static int32_t shadow_head(void *model,const int32_t *tokens,int32_t count,int32_t position) {
    int incoming_errno=errno;uintptr_t address=(uintptr_t)__builtin_return_address(0);
    uintptr_t caller=address>=engine_base?address-engine_base:UINTPTR_MAX;
    lock_state();
    forward_calls++;if (count!=1) excluded_calls++;
    if (in_flight || head_depth) {
        overlaps++;atomic_store(&disabled,1);
        if (output_exposed) fatal("full-head-overlap-after-output-write");
    }
    in_flight++;struct context *s=NULL;
    if (atomic_load(&initialized) && !atomic_load(&disabled)) {
        struct armed arm;int armed=read_arm(&arm);
        if (armed<0) atomic_store(&disabled,1);
        if (observed_published && (count!=1 || !known_head_caller(caller) ||
            !observation_live((uintptr_t)model) || !same_observed_file() || position<last_position ||
            int32_at(model,0x220)<last_outer_position)) {
            armed=-1;atomic_store(&disabled,1);
        }
        /* A discovery record is one completed head in one paused owned epoch.
         * Any subsequent unarmed head makes that observation stale. */
        if ((armed==1 && !observed_published) || (armed==0 && observed_published)) {
            armed=-1;atomic_store(&disabled,1);
        }
        if (armed==1 && epoch_armed && memcmp(&arm,&epoch_arm,sizeof arm)) {
            armed=-1;atomic_store(&disabled,1);
        }
        if (armed==1 && calls<MAX_CALLS && !atomic_load(&disabled)) {
            if (!epoch_armed) {epoch_arm=arm;epoch_armed=1;}
            if (arm.model!=observed.model || arm.model!=(uintptr_t)model ||
                !valid_head_entry(model,tokens,count,position,caller)) atomic_store(&disabled,1);
            else {
                s=&contexts[calls];s->sequence=calls++;s->arm=arm;
                context_entry(s,model,tokens,count,position,caller);last_position=position;
            }
        } else if (armed==0 && !discovery_reserved && count==1 && !atomic_load(&disabled)) {
            if (!valid_head_entry(model,tokens,count,position,caller)) atomic_store(&disabled,1);
            else {
                discovery_reserved=1;s=&discovery;s->discovering=1;s->sequence=0;
                context_entry(s,model,tokens,count,position,caller);
            }
        }
    }
    unlock_state();
    struct context *saved=active;active=s;head_depth++;
    errno=incoming_errno;int32_t result=original_head(model,tokens,count,position);int result_errno=errno;
    head_depth--;active=saved;
    lock_state();
    if (s) {
        s->head_result=result;s->head_errno=result_errno;s->completed=1;
        if (s->e_calls!=1 || s->h_calls!=1 || s->original_calls[0]!=1 || s->original_calls[1]!=1)
            reject(s,"head-exact-pair-count");
        if (result<0) reject(s,"native-head-result");
        if (s->discovering) {
            if (publish_observation(s)) {
                s->outcome="native_discovery_published";
                /* Root validates this synced native receipt before HELLO/ARM. */
                log_context(s);
                if (!atomic_load(&disabled)) {
                    unlock_state();int armed=await_discovery_arm(s);lock_state();
                    if (armed==1 && in_flight==1 && !atomic_load(&disabled) &&
                        observation_live(s->model) && same_observed_file()) s->outcome="native_discovery_armed";
                    else {
                        s->outcome=armed==0?"native_discovery_arm_timeout":"native_discovery_arm_rejected";
                        reject(s,armed==0?"discovery-arm-timeout":"discovery-arm-identity-or-overlap");
                    }
                } else s->outcome="native_discovery_arm_rejected";
            }
            else {s->outcome="native_discovery_rejected";reject(s,"discovery-publication-or-identity");}
        } else if (!atomic_load(&disabled)) {
            if (!observation_live(s->model) || !same_observed_file() ||
                int32_at((void *)s->model,0x220)<last_outer_position) reject(s,"post-head-observation-identity");
            else last_outer_position=int32_at((void *)s->model,0x220);
        }
        output_exposed=0;log_context(s);
    }
    if (!in_flight) fatal("head-in-flight-underflow");
    in_flight--;unlock_state();errno=result_errno;return result;
}
static void verify_hash(int fd,off_t offset,size_t bytes,const char *wanted) {
    EVP_MD_CTX *ctx=EVP_MD_CTX_new();unsigned char block[65536],digest[32];unsigned length=0;
    if (!ctx || EVP_DigestInit_ex(ctx,EVP_sha256(),NULL)!=1) fatal("hash-init");
    while (bytes) {
        size_t amount=bytes<sizeof block?bytes:sizeof block;ssize_t n=pread(fd,block,amount,offset);
        if (n<0 && errno==EINTR) continue;
        if (n<=0 || (size_t)n>amount || EVP_DigestUpdate(ctx,block,(size_t)n)!=1) fatal("hash-read");
        offset+=n;bytes-=(size_t)n;
    }
    if (EVP_DigestFinal_ex(ctx,digest,&length)!=1 || length!=32) fatal("hash-final");
    EVP_MD_CTX_free(ctx);char hex[65];
    for (unsigned i=0;i<32;i++) snprintf(hex+2*i,3,"%02x",(unsigned)digest[i]);
    if (strcmp(hex,wanted)) fatal("hash-mismatch");
}
struct sites {uintptr_t base,head,fc;unsigned heads,fcs,globals,kernels;};
static int contained(const Elf64_Phdr *p,uintptr_t start,size_t bytes,int file) {
    uint64_t extent=file?p->p_filesz:p->p_memsz;
    return p->p_type==PT_LOAD && p->p_vaddr<=start && bytes<=extent && start-p->p_vaddr<=extent-bytes;
}
static int find_sites(struct dl_phdr_info *info,size_t ignored,void *opaque) {
    (void)ignored;if (info->dlpi_name && *info->dlpi_name) return 0;
    struct sites *sites=opaque;
    if (WIRE_GUARD_RVA+1>UINTPTR_MAX-info->dlpi_addr) fatal("base-overflow");
    sites->base=info->dlpi_addr;
    for (unsigned i=0;i<info->dlpi_phnum;i++) {
        const Elf64_Phdr *p=&info->dlpi_phdr[i];
        if (p->p_flags==(PF_R|PF_X) && contained(p,HEAD_RVA,HEAD_BYTES,1) &&
            p->p_offset+HEAD_RVA-p->p_vaddr==(uint64_t)HEAD_OFFSET) {sites->head=sites->base+HEAD_RVA;sites->heads++;}
        if (p->p_flags==(PF_R|PF_X) && contained(p,FC_RVA,FC_BYTES,1) &&
            p->p_offset+FC_RVA-p->p_vaddr==(uint64_t)FC_OFFSET) {sites->fc=sites->base+FC_RVA;sites->fcs++;}
        if (p->p_flags==(PF_R|PF_W) && contained(p,H_INPUT_RVA,WIRE_GUARD_RVA+1-H_INPUT_RVA,0)) sites->globals++;
        if ((p->p_flags&PF_R) && contained(p,E_KERNEL_RVA,H_KERNEL_RVA+8-E_KERNEL_RVA,0)) sites->kernels++;
    }
    return 1;
}
static void absolute_jump(unsigned char *at,uintptr_t target) {
    const unsigned char prefix[6]={0xff,0x25,0,0,0,0};memcpy(at,prefix,6);memcpy(at+6,&target,8);
}
struct detour {uintptr_t entry,page,trampoline;size_t page_size;unsigned char jump[5];};
static struct detour prepare_detour(uintptr_t entry,uintptr_t target,const unsigned char signature[32]) {
    long size=sysconf(_SC_PAGESIZE);
    if (size<=0 || ((unsigned long)size&((unsigned long)size-1))) fatal("page-size");
    struct detour detour={.entry=entry,.page=entry&~((uintptr_t)size-1),.page_size=(size_t)size};
    if (entry+32>detour.page+(uintptr_t)size || !mapped_span(detour.page,(size_t)size,"r-xp")) fatal("entry-page");
    unsigned char *thunk=NULL;
    for (unsigned i=0;i<256;i++) {
        uintptr_t distance=(uintptr_t)(i/2+1)*0x200000;
        if ((i&1)?detour.page<distance:distance>UINTPTR_MAX-detour.page) continue;
        uintptr_t candidate=(i&1)?detour.page-distance:detour.page+distance;
        void *area=mmap((void *)candidate,(size_t)size,PROT_READ|PROT_WRITE,
            MAP_PRIVATE|MAP_ANONYMOUS|MAP_FIXED_NOREPLACE,-1,0);
        if (area==MAP_FAILED) {if (errno==EEXIST) continue;fatal("thunk-map");}
        if (area!=(void *)candidate) {if (munmap(area,(size_t)size)) fatal("thunk-unmap");fatal("fixed-noreplace");}
        thunk=area;break;
    }
    if (!thunk) fatal("thunk-exhausted");
    absolute_jump(thunk,target);
    /* Whole non-RIP-relative push rbp; push r15; push r14 instructions only. */
    memcpy(thunk+64,signature,5);absolute_jump(thunk+69,entry+5);detour.trampoline=(uintptr_t)(thunk+64);
    if (mprotect(thunk,(size_t)size,PROT_READ|PROT_EXEC) || !mapped_span((uintptr_t)thunk,(size_t)size,"r-xp")) fatal("thunk-rx");
    int64_t relative=(int64_t)(uintptr_t)thunk-(int64_t)(entry+5);
    if (relative<INT32_MIN || relative>INT32_MAX) fatal("jump-range");
    detour.jump[0]=0xe9;int32_t delta=(int32_t)relative;memcpy(detour.jump+1,&delta,4);return detour;
}
static void patch_detour(const struct detour *detour) {
    if (mprotect((void *)detour->page,detour->page_size,PROT_READ|PROT_WRITE)) fatal("entry-rw");
    memcpy((void *)detour->entry,detour->jump,5);
    __builtin___clear_cache((char *)detour->entry,(char *)detour->entry+5);
    if (mprotect((void *)detour->page,detour->page_size,PROT_READ|PROT_EXEC) ||
        !mapped_span(detour->page,detour->page_size,"r-xp")) fatal("entry-rx");
}
static int serving_process(void) {
    int fd=open("/proc/self/cmdline",O_RDONLY|O_CLOEXEC);char command[4096];ssize_t bytes;
    if (fd<0) fatal("cmdline-open");
    do {bytes=read(fd,command,sizeof command);} while (bytes<0 && errno==EINTR);
    if (bytes<=0 || bytes>=(ssize_t)sizeof command || command[bytes-1] || close(fd)) fatal("cmdline-read");
    const char *argument=memchr(command,0,(size_t)bytes);
    return argument && argument+1<command+bytes && !strcmp(argument+1,"--ck");
}
__attribute__((constructor)) static void install(void) {
    const char *mode=getenv("HALOGEN_MTP_FC_QUALITY");if (!mode) return;
    if (strcmp(mode,"shadow4-v1")) fatal("shadow-mode");
    char executable[4096];ssize_t length=readlink("/proc/self/exe",executable,sizeof executable-1);
    if (length<0 || length>=(ssize_t)sizeof executable-1) fatal("executable-name");
    executable[length]=0;const char *base=strrchr(executable,'/');base=base?base+1:executable;
    if (strcmp(base,"flash_serve") || !serving_process()) return;
    const char *wire=getenv("HALOGEN_MTP_WIRE"),*wave=getenv("HALOGEN_LQ8_WAVE");
    const char *directory=getenv("HALOGEN_MTP_FC_QUALITY_DIR");
    if (!wire || strcmp(wire,"D") || (wave && strcmp(wave,"1")) || !directory ||
        strncmp(directory,directory_prefix,sizeof directory_prefix-1) ||
        strlen(directory)!=sizeof directory_prefix-1+32) fatal("shadow-configuration");
    const char *hex=directory+sizeof directory_prefix-1;
    for (unsigned i=0;i<32;i++) {
        int value=hex[i]>='0' && hex[i]<='9'?hex[i]-'0':hex[i]>='a' && hex[i]<='f'?hex[i]-'a'+10:-1;
        if (value<0) fatal("run-nonce");
        run_nonce[i/2]|=(unsigned char)(value<<(i%2?0:4));
    }
    if (!nonzero(run_nonce,16)) fatal("zero-run-nonce");
    int fd=open("/proc/self/exe",O_RDONLY|O_CLOEXEC);struct stat before,after;Elf64_Ehdr elf;
    if (fd<0 || fstat(fd,&before) || !S_ISREG(before.st_mode) || before.st_size!=ENGINE_BYTES ||
        pread(fd,&elf,sizeof elf,0)!=(ssize_t)sizeof elf || memcmp(elf.e_ident,ELFMAG,SELFMAG) ||
        elf.e_ident[EI_CLASS]!=ELFCLASS64 || elf.e_ident[EI_DATA]!=ELFDATA2LSB ||
        elf.e_type!=ET_DYN || elf.e_machine!=EM_X86_64) fatal("elf-identity");
    verify_hash(fd,0,(size_t)before.st_size,ENGINE_SHA);verify_hash(fd,HEAD_OFFSET,HEAD_BYTES,HEAD_SHA);
    verify_hash(fd,FC_OFFSET,FC_BYTES,FC_SHA);
    if (fstat(fd,&after) || !same_stat(&before,&after) || close(fd)) fatal("executable-consistency");
    struct sites sites={0};
    if (dl_iterate_phdr(find_sites,&sites)!=1 || sites.heads!=1 || sites.fcs!=1 || sites.globals!=1 || sites.kernels!=1 ||
        !mapped_span(sites.head,HEAD_BYTES,"r-xp") || !mapped_span(sites.fc,FC_BYTES,"r-xp") ||
        memcmp((void *)sites.head,head_signature,32) || memcmp((void *)sites.fc,fc_signature,32) ||
        memcmp((void *)(sites.base+E_RETURN_RVA-5),e_call,5) ||
        memcmp((void *)(sites.base+H_RETURN_RVA-5),h_call,5) ||
        !mapped_span(sites.base+H_INPUT_RVA,WIRE_GUARD_RVA+1-H_INPUT_RVA,"rw-p") ||
        !mapped_span(sites.base+E_KERNEL_RVA,H_KERNEL_RVA+8-E_KERNEL_RVA,NULL)) fatal("native-sites");
    char hash[65];
    if (!buffer_hash((void *)sites.head,HEAD_BYTES,hash) || strcmp(hash,HEAD_SHA) ||
        !buffer_hash((void *)sites.fc,FC_BYTES,hash) || strcmp(hash,FC_SHA)) fatal("mapped-function-hash");
    engine_base=sites.base;
    if (!read_process_identity(&process_pid,&process_starttime)) fatal("process-identity");
    int tmp=open("/tmp",O_RDONLY|O_DIRECTORY|O_CLOEXEC|O_NOFOLLOW);struct stat status;
    if (tmp<0 || fstat(tmp,&status) || !S_ISDIR(status.st_mode)) fatal("tmp-directory");
    const char *name=directory+sizeof "/tmp/"-1;
    if (mkdirat(tmp,name,0700)) fatal("fresh-directory-required");
    directory_fd=openat(tmp,name,O_RDONLY|O_DIRECTORY|O_CLOEXEC|O_NOFOLLOW);
    if (close(tmp) || directory_fd<0 || fstat(directory_fd,&status) || !S_ISDIR(status.st_mode) ||
        status.st_uid!=geteuid() || (status.st_mode&0777)!=0700) fatal("owned-directory");
    log_fd=openat(directory_fd,"records.jsonl",O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC|O_NOFOLLOW,0600);
    if (log_fd<0) fatal("records-create");
    struct detour head=prepare_detour(sites.head,(uintptr_t)shadow_head,head_signature);
    struct detour fc=prepare_detour(sites.fc,(uintptr_t)shadow_fc,fc_signature);
    original_head=(head_fn)head.trampoline;original_fc=(fc_fn)fc.trampoline;
    /* Root must install in an owned process before serving. This is not a
     * concurrent hot-patch protocol; partial installation terminates the process. */
    patch_detour(&head);patch_detour(&fc);
    static const char activation[]=
        "{\"schema\":1,\"mode\":\"shadow4-v1\",\"engine_sha256\":\"" ENGINE_SHA "\","
        "\"head_sha256\":\"" HEAD_SHA "\",\"fc_dispatcher_sha256\":\"" FC_SHA "\","
        "\"head_rva\":\"0x17db310\",\"fc_rva\":\"0x178cf90\",\"request_bytes\":51424,"
        "\"response_bytes\":25856,\"armed_bytes\":120,\"request_binding_offset\":192,\"limit\":4,"
        "\"observed_bytes\":464,\"observed_digest_offset\":432,\"discovery_limit\":1,\"discovery_device_copies\":0,"
        "\"discovery_arm_wait_ns\":2000000000,"
        "\"wait_ns\":200000000,\"original_each_once\":true,\"paired_restore\":true,"
        "\"integration_qualified\":false,\"arithmetic_qualified\":false,\"npu_qualified\":false,"
        "\"parity_qualified\":false,\"acceptance_qualified\":false,\"performance_qualified\":false,"
        "\"transport_qualified\":false,\"native_reset_interception_qualified\":false}\n";
    int activation_fd=openat(directory_fd,"activation.json",O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC|O_NOFOLLOW,0600);
    if (activation_fd<0 || !write_all(activation_fd,activation,sizeof activation-1) || fsync(activation_fd) ||
        close(activation_fd) || fsync(directory_fd)) fatal("activation-publication");
    atomic_store(&initialized,1);
}
