/* Research-only exact D hidden-RMS boundary observer. Native always executes.
 * Build (root only): gcc -O2 -Wall -Wextra -Werror -shared -fPIC
 *   -fno-optimize-sibling-calls halogen0162_mtp_hidden_rms_tap.c
 *   -ldl -lcrypto -pthread -o libhalogen0162-mtp-hidden-rms-tap.so
 * Explicit HALOGEN_MTP_WIRE=D is required. HALOGEN_MTP_HIDDEN_RMS_TAP=rms1-v1;
 * HALOGEN_MTP_HIDDEN_RMS_TAP_DIR=/tmp/alloy-mtp-hidden-rms-tap-<32hex>.
 * After READY, publish armed containing rms1-v1-ready\n. After the request
 * returns, publish harvest containing rms1-v1-harvest\n. Both are exclusive
 * regular owner-only files. Exactly one count1 forward is reserved.
 * Three static 20480-byte host buffers retain raw residual/gamma/output words.
 * No device allocation, checkpoint access, tensor mutation, or timing claim.
 * Static seam: D hipLaunchKernel at 0x17db62d returns to 0x17db632; FC starts
 * at 0x17db636. Capture after real_launch + successful hipDeviceSynchronize
 * and synchronous D2H hipMemcpy, before returning to the native caller.
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
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

#if !defined(__x86_64__) || !defined(__linux__)
#error Linux x86-64 only
#endif
#define ENGINE_SHA "ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b"
#define ENGINE_BYTES ((off_t)26052768)
#define FUNCTION_SHA "132f2da76d86694ffe5f120d61e304e57c685f3db72935c6d5e61bf7b0d5cc20"
#define ENTRY_RVA ((uintptr_t)0x17db310)
#define ENTRY_OFFSET ((off_t)0x17da310)
#define FUNCTION_BYTES ((size_t)(0x17dc289 - 0x17db310))
#define RMS_IDENTITY_RVA ((uintptr_t)0x18d5160)
#define RMS_SIGNATURE_RVA ((uintptr_t)0x17db619)
#define RMS_RETURN_RVA ((uintptr_t)0x17db632)
#define RMS_OUTPUT_SLOT_RVA ((uintptr_t)0x18db210)
#define WIRE_RVA ((uintptr_t)0x18dccc0)
#define WIRE_GUARD_RVA ((uintptr_t)0x18dccc8)
#define MODEL_BYTES ((size_t)0xb10)
#define TENSOR_BYTES ((size_t)20480)
#define TRACE_BYTE_LIMIT ((size_t)131072)
#define TRACE_FILE_LIMIT 8U
static const char trace_prefix[]="/tmp/alloy-mtp-hidden-rms-tap-";
static const char arm_content[]="rms1-v1-ready\n";
static const char harvest_content[]="rms1-v1-harvest\n";
static const unsigned char entry_signature[32]={
    0x55,0x41,0x57,0x41,0x56,0x41,0x55,0x41,0x54,0x53,0x48,0x81,0xec,0x98,0,0,
    0,0xb8,0xff,0xff,0xff,0xff,0x80,0xbf,0,0x09,0,0,0x01,0x0f,0x85,0x31
};
/* lea rdi,kernel; lea r9,args; push stream; push shared; call launch; add rsp,16.
 * At the second push rsp is already -8, so [rsp+0x28] is native [frame+0x20].
 * The wrapper uses the compiler's ordinary SysV dim3 ABI; it never steals or
 * edits the native stack. Native args[] contain addresses of stack values:
 * source at frame+0x38, gamma+0x30, output+0x28, width+0x48, groups+0x80.
 */
static const unsigned char rms_signature[29]={
    0x48,0x8d,0x3d,0x40,0x9b,0x0f,0,0x4c,0x8d,0x4c,0x24,0x50,
    0xff,0x74,0x24,0x40,0xff,0x74,0x24,0x28,0xe8,0xde,0x81,0x0f,0,
    0x48,0x83,0xc4,0x10
};
typedef int32_t (*head_fn)(void *,const int32_t *,int32_t,int32_t);
typedef struct {unsigned x,y,z;} hip_dim3;
typedef int (*launch_fn)(const void *,hip_dim3,hip_dim3,void **,size_t,void *);
typedef int (*sync_fn)(void);
typedef int (*copy_fn)(void *,const void *,size_t,int);
struct sample {
    uintptr_t model,forward_caller_rva,input,gamma,output,launch_caller_rva,kernel_rva;
    int32_t count,position,token,model_position,head_result,width,groups;
    unsigned reserved,completed,entry_valid,exact_launches,captured,nested_forwards;
    unsigned wire_before,wire_after,guard_before,guard_after,observer_syncs,observer_copies;
    hip_dim3 grid,block;
    size_t shared;
    uintptr_t stream;
    int launch_result,launch_result_valid;
    const char *error;
    unsigned char residual[TENSOR_BYTES],raw_gamma[TENSOR_BYTES],hidden_rms[TENSOR_BYTES];
};
static struct sample sample;
static _Thread_local struct sample *active_sample;
static _Thread_local unsigned head_depth;
static head_fn original_head;
static launch_fn real_launch;
static sync_fn hip_sync;
static copy_fn hip_copy;
static uintptr_t engine_base;
static int trace_dir=-1;
static unsigned forward_calls,count1_calls,excluded_count_calls,limit_skipped_calls;
static unsigned native_in_flight,trace_files;
static size_t trace_bytes;
static const char *trace_error;
static pthread_once_t symbols_once=PTHREAD_ONCE_INIT;
static pthread_mutex_t trace_mutex=PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t trace_idle=PTHREAD_COND_INITIALIZER;
static _Atomic int initialized,armed_once,harvested;

static _Noreturn void fatal(const char *reason) {
    dprintf(STDERR_FILENO,"[mtp-hidden-rms-tap] fatal reason=%s errno=%d\n",reason,errno);
    _exit(79);
}
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
static int mapped_read(uintptr_t address,size_t bytes) {return mapped_span(address,bytes,NULL);}
static uintptr_t pointer_at(const void *object,size_t offset) {
    uintptr_t value;memcpy(&value,(const unsigned char *)object+offset,sizeof value);return value;
}
static int32_t int32_at(const void *object,size_t offset) {
    int32_t value;memcpy(&value,(const unsigned char *)object+offset,sizeof value);return value;
}
static int device_span(uintptr_t pointer) {return pointer && TENSOR_BYTES<=UINTPTR_MAX-pointer;}
static int disjoint(uintptr_t a,uintptr_t b) {
    return device_span(a) && device_span(b) && (a+TENSOR_BYTES<=b || b+TENSOR_BYTES<=a);
}
static void sample_error(struct sample *s,const char *reason) {if (!s->error) s->error=reason;}
static void disable(const char *reason) {if (!trace_error) trace_error=reason;}
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
    if (trace_files>=TRACE_FILE_LIMIT || bytes>TRACE_BYTE_LIMIT-trace_bytes) return 0;
    int fd=openat(trace_dir,name,O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC|O_NOFOLLOW,0600);
    if (fd<0) return 0;
    trace_files++;
    struct stat status;
    int ok=!fstat(fd,&status) && S_ISREG(status.st_mode) && status.st_uid==geteuid() &&
        status.st_nlink==1 && status.st_size==0 && append_bytes(fd,data,bytes);
    if (fsync(fd)) ok=0;
    if (close(fd)) ok=0;
    return ok;
}
static int trigger(const char *name,const char *wanted,size_t bytes) {
    int fd=openat(trace_dir,name,O_RDONLY|O_CLOEXEC|O_NOFOLLOW);
    if (fd<0) return errno==ENOENT?0:-1;
    struct stat before,after;char content[64];
    int ok=bytes<sizeof content && !fstat(fd,&before) && S_ISREG(before.st_mode) &&
        before.st_uid==geteuid() && before.st_nlink==1 && (before.st_mode&0777)==0600 &&
        before.st_size==(off_t)bytes && pread(fd,content,sizeof content,0)==(ssize_t)bytes &&
        !memcmp(content,wanted,bytes) && !fstat(fd,&after) &&
        before.st_dev==after.st_dev && before.st_ino==after.st_ino && before.st_size==after.st_size &&
        before.st_mtim.tv_sec==after.st_mtim.tv_sec && before.st_mtim.tv_nsec==after.st_mtim.tv_nsec;
    if (close(fd)) ok=0;
    return ok?1:-1;
}
static int armed_locked(void) {
    if (trace_error || atomic_load(&harvested)) return 0;
    int arm=atomic_load(&armed_once)?1:trigger("armed",arm_content,sizeof arm_content-1);
    if (arm==1) atomic_store(&armed_once,1);else if (arm<0) disable("arm-content");
    return arm==1;
}
static int known_forward_caller(uintptr_t caller) {
    return caller==0x17dcc08 || caller==0x17dcd54 || caller==0x17dcf49 || caller==0x17de236;
}
static void observe_entry(struct sample *s,void *object,const int32_t *tokens,
    int32_t count,int32_t position,uintptr_t caller) {
    s->reserved=1;s->model=(uintptr_t)object;s->count=count;s->position=position;
    s->forward_caller_rva=caller;
    if (count!=1 || position<0 || !known_forward_caller(caller)) {sample_error(s,"forward-contract");return;}
    if (!mapped_read(s->model,MODEL_BYTES) || !mapped_read((uintptr_t)tokens,sizeof *tokens)) {
        sample_error(s,"entry-host-span");return;
    }
    if (((const unsigned char *)object)[0x900]!=1) {sample_error(s,"mtp-disabled");return;}
    memcpy(&s->token,tokens,sizeof s->token);
    s->entry_valid=1;
}
static void resolve_symbols(void) {
    real_launch=(launch_fn)dlsym(RTLD_NEXT,"hipLaunchKernel");
    hip_sync=(sync_fn)dlsym(RTLD_NEXT,"hipDeviceSynchronize");
    hip_copy=(copy_fn)dlsym(RTLD_NEXT,"hipMemcpy");
}
static int inspect_rms(struct sample *s,const void *function,hip_dim3 grid,hip_dim3 block,
    void **args,size_t shared,void *stream,uintptr_t caller) {
    s->launch_caller_rva=caller;s->kernel_rva=(uintptr_t)function-engine_base;
    s->grid=grid;s->block=block;s->shared=shared;s->stream=(uintptr_t)stream;
    if (!s->entry_valid || caller!=RMS_RETURN_RVA || (uintptr_t)function!=engine_base+RMS_IDENTITY_RVA ||
        grid.x!=1 || grid.y!=1 || grid.z!=1 || block.x!=256 || block.y!=1 || block.z!=1 || shared || stream) {
        sample_error(s,"rms-launch-contract");return 0;
    }
    if (!mapped_read(s->model,MODEL_BYTES) || !mapped_read((uintptr_t)args,5U*sizeof(void *))) {
        sample_error(s,"rms-host-span");return 0;
    }
    uintptr_t values[5];memcpy(values,args,sizeof values);
    for (unsigned i=0;i<5;i++) {
        if (!mapped_read(values[i],i<3?sizeof(uintptr_t):sizeof(int32_t))) {
            sample_error(s,"rms-arg-value-host-span");return 0;
        }
    }
    s->input=pointer_at((const void *)values[0],0);s->gamma=pointer_at((const void *)values[1],0);
    s->output=pointer_at((const void *)values[2],0);s->width=int32_at((const void *)values[3],0);
    s->groups=int32_at((const void *)values[4],0);
    s->wire_before=*(const unsigned char *)(engine_base+WIRE_RVA);
    s->guard_before=*(const unsigned char *)(engine_base+WIRE_GUARD_RVA);
    s->model_position=int32_at((const void *)s->model,0x220);
    if (s->wire_before!='D' || !s->guard_before || s->width!=10240 || s->groups!=1 ||
        s->input!=pointer_at((const void *)s->model,0x6d0) ||
        s->gamma!=pointer_at((const void *)s->model,0xaf0) ||
        s->output!=pointer_at((const void *)(engine_base+RMS_OUTPUT_SLOT_RVA),0) ||
        !disjoint(s->input,s->gamma) || !disjoint(s->input,s->output) || !disjoint(s->gamma,s->output)) {
        sample_error(s,"rms-input-output-wire-contract");return 0;
    }
    return 1;
}
int hipLaunchKernel(const void *function,hip_dim3 grid,hip_dim3 block,void **args,size_t shared,void *stream) {
    int incoming_errno=errno;
    uintptr_t address=(uintptr_t)__builtin_return_address(0);
    uintptr_t caller=address>=engine_base?address-engine_base:UINTPTR_MAX;
    if (pthread_once(&symbols_once,resolve_symbols) || !real_launch) fatal("launch-symbol");
    struct sample *s=active_sample;
    int capture=0;
    if (s && caller==RMS_RETURN_RVA) {
        s->exact_launches++;
        if (s->exact_launches!=1) sample_error(s,"duplicate-exact-rms-launch");
        if (!s->error && inspect_rms(s,function,grid,block,args,shared,stream,caller)) {
            if (!hip_sync || !hip_copy) sample_error(s,"capture-symbols");
            else {
                s->observer_syncs++;
                if (hip_sync()) sample_error(s,"pre-rms-sync");
                else {
                    s->observer_copies++;
                    if (hip_copy(s->residual,(const void *)s->input,TENSOR_BYTES,2)) sample_error(s,"residual-copy");
                    else {
                        s->observer_copies++;
                        if (hip_copy(s->raw_gamma,(const void *)s->gamma,TENSOR_BYTES,2)) sample_error(s,"gamma-copy");
                        else capture=1;
                    }
                }
            }
        }
    }
    errno=incoming_errno;
    /* Native launch executes exactly once, even if any capture check failed. */
    int result=real_launch(function,grid,block,args,shared,stream);
    int result_errno=errno;
    if (s && caller==RMS_RETURN_RVA && !s->launch_result_valid) {
        s->launch_result=result;s->launch_result_valid=1;
    }
    if (capture) {
        if (result) sample_error(s,"native-rms-launch");
        else {
            s->observer_syncs++;
            if (hip_sync()) sample_error(s,"post-rms-sync");
            else if (!mapped_read(s->model,MODEL_BYTES) ||
                s->input!=pointer_at((const void *)s->model,0x6d0) ||
                s->gamma!=pointer_at((const void *)s->model,0xaf0) ||
                s->output!=pointer_at((const void *)(engine_base+RMS_OUTPUT_SLOT_RVA),0))
                sample_error(s,"post-rms-pointers");
            else {
                s->wire_after=*(const unsigned char *)(engine_base+WIRE_RVA);
                s->guard_after=*(const unsigned char *)(engine_base+WIRE_GUARD_RVA);
                if (s->wire_after!='D' || !s->guard_after) sample_error(s,"post-rms-wire");
                else {
                    s->observer_copies++;
                    if (hip_copy(s->hidden_rms,(const void *)s->output,TENSOR_BYTES,2)) sample_error(s,"hidden-rms-copy");
                    else s->captured=1;
                }
            }
        }
    }
    errno=result_errno;return result;
}
static int32_t run_native(void *object,const int32_t *tokens,int32_t count,int32_t position,
    struct sample *s,int incoming_errno) {
    struct sample *saved=active_sample;
    active_sample=s;head_depth++;
    errno=incoming_errno;
    int32_t result=original_head(object,tokens,count,position);
    int result_errno=errno;
    head_depth--;active_sample=saved;
    errno=result_errno;return result;
}
static int32_t tapped_head(void *object,const int32_t *tokens,int32_t count,int32_t position) {
    int incoming_errno=errno;
    uintptr_t address=(uintptr_t)__builtin_return_address(0);
    uintptr_t caller=address>=engine_base?address-engine_base:UINTPTR_MAX;
    if (head_depth) {
        if (active_sample) {active_sample->nested_forwards++;sample_error(active_sample,"nested-full-forward");}
        return run_native(object,tokens,count,position,NULL,incoming_errno);
    }
    if (!atomic_load(&initialized)) return run_native(object,tokens,count,position,NULL,incoming_errno);
    if (pthread_mutex_lock(&trace_mutex)) fatal("forward-mutex");
    /* Overlapping forwards may reuse the global RMS destination. Reject any
     * overlap instead of attributing a device buffer to the wrong request. */
    if (native_in_flight && sample.reserved && !sample.completed) disable("overlapping-native-forwards");
    unsigned preceding=native_in_flight++;
    struct sample *s=NULL;
    if (armed_locked()) {
        forward_calls++;
        if (count!=1) excluded_count_calls++;
        else {
            count1_calls++;
            if (sample.reserved) limit_skipped_calls++;
            else {
                s=&sample;observe_entry(s,object,tokens,count,position,caller);
                if (preceding) {sample_error(s,"overlapping-native-forwards");disable(s->error);}
                if (s->error) disable(s->error);
            }
        }
    }
    (void)pthread_mutex_unlock(&trace_mutex);
    int32_t result=run_native(object,tokens,count,position,s,incoming_errno);
    int result_errno=errno;
    if (pthread_mutex_lock(&trace_mutex)) fatal("completion-mutex");
    if (s) {
        s->head_result=result;s->completed=1;
        if (!s->exact_launches) sample_error(s,"hidden-rms-not-seen");
        if (!s->captured) sample_error(s,"hidden-rms-not-captured");
        if (s->exact_launches!=1) sample_error(s,"hidden-rms-launch-count");
        if (result<0) sample_error(s,"native-head-result");
        if (s->error) disable(s->error);
    }
    native_in_flight--;
    if (!native_in_flight) (void)pthread_cond_broadcast(&trace_idle);
    (void)pthread_mutex_unlock(&trace_mutex);
    errno=result_errno;return result;
}
static int buffer_hash(const void *data,size_t bytes,char hex[65]) {
    unsigned char digest[32];unsigned length=0;
    if (EVP_Digest(data,bytes,digest,&length,EVP_sha256(),NULL)!=1 || length!=sizeof digest) return 0;
    for (size_t i=0;i<sizeof digest;i++) snprintf(hex+i*2,3,"%02x",(unsigned)digest[i]);
    return 1;
}
static void harvest(int requested) {
    if (pthread_mutex_lock(&trace_mutex)) fatal("harvest-mutex");
    atomic_store(&harvested,1);
    if (requested<0) disable("harvest-content");
    while (native_in_flight) {
        if (pthread_cond_wait(&trace_idle,&trace_mutex)) fatal("harvest-wait");
    }
    if (!sample.reserved) disable("no-samples");
    if (!sample.completed || !sample.captured) disable("incomplete-sample");
    char input_hash[65]="",gamma_hash[65]="",output_hash[65]="";
    if (sample.captured) {
        if (!buffer_hash(sample.residual,TENSOR_BYTES,input_hash) ||
            !buffer_hash(sample.raw_gamma,TENSOR_BYTES,gamma_hash) ||
            !buffer_hash(sample.hidden_rms,TENSOR_BYTES,output_hash)) disable("buffer-hash");
        if (!save_file("000-input-residual-u16.bin",sample.residual,TENSOR_BYTES) ||
            !save_file("000-raw-gamma-u16.bin",sample.raw_gamma,TENSOR_BYTES) ||
            !save_file("000-output-hidden-rms-u16.bin",sample.hidden_rms,TENSOR_BYTES)) disable("tensor-export");
    }
    const struct sample *s=&sample;char records[8192];
    int n=snprintf(records,sizeof records,
        "{\"schema\":1,\"mode\":\"rms1-v1\",\"engine_sha256\":\"%s\",\"function_sha256\":\"%s\","
        "\"instrumented\":true,\"timing_claim\":false,\"tensor_bytes\":20480,\"word_format\":\"little-endian-bf16-u16\","
        "\"forward_calls\":%u,\"count1_calls\":%u,\"excluded_count_calls\":%u,\"limit_skipped_calls\":%u,\"samples\":["
        "{\"index\":0,\"reserved\":%s,\"count\":%d,\"position\":%d,\"token_i32\":%d,\"model_position_220\":%d,"
        "\"model\":\"0x%" PRIxPTR "\",\"forward_caller_rva\":\"0x%" PRIxPTR "\",\"entry_valid\":%s,"
        "\"completed\":%s,\"head_result\":%d,\"captured\":%s,\"exact_launches\":%u,\"nested_forwards\":%u,"
        "\"wire_mode\":\"%s\",\"wire_byte_before\":%u,\"wire_byte_after\":%u,\"wire_initialized_before\":%s,"
        "\"wire_initialized_after\":%s,\"kernel_identity_rva\":\"0x%" PRIxPTR "\",\"launch_return_rva\":\"0x%" PRIxPTR "\","
        "\"width\":%d,\"groups\":%d,\"grid\":[%u,%u,%u],\"block\":[%u,%u,%u],\"shared_bytes\":%zu,"
        "\"stream\":\"0x%" PRIxPTR "\",\"launch_result_valid\":%s,\"launch_result\":%d,\"observer_hip_syncs\":%u,"
        "\"observer_hip_copies\":%u,\"input_device\":\"0x%" PRIxPTR "\",\"gamma_device\":\"0x%" PRIxPTR "\","
        "\"output_device\":\"0x%" PRIxPTR "\",\"input_residual_sha256\":\"%s\",\"raw_gamma_sha256\":\"%s\","
        "\"output_hidden_rms_sha256\":\"%s\",\"input_residual_file\":\"000-input-residual-u16.bin\","
        "\"raw_gamma_file\":\"000-raw-gamma-u16.bin\",\"output_hidden_rms_file\":\"000-output-hidden-rms-u16.bin\","
        "\"error\":%s%s%s}]}\n",
        ENGINE_SHA,FUNCTION_SHA,forward_calls,count1_calls,excluded_count_calls,limit_skipped_calls,
        s->reserved?"true":"false",s->count,s->position,s->token,s->model_position,s->model,s->forward_caller_rva,
        s->entry_valid?"true":"false",s->completed?"true":"false",s->head_result,s->captured?"true":"false",
        s->exact_launches,s->nested_forwards,s->wire_before=='D' && s->wire_after=='D'?"D":"unqualified",
        s->wire_before,s->wire_after,s->guard_before?"true":"false",s->guard_after?"true":"false",
        s->kernel_rva,s->launch_caller_rva,s->width,s->groups,s->grid.x,s->grid.y,s->grid.z,
        s->block.x,s->block.y,s->block.z,s->shared,s->stream,s->launch_result_valid?"true":"false",
        s->launch_result,s->observer_syncs,s->observer_copies,s->input,s->gamma,s->output,input_hash,gamma_hash,output_hash,
        s->error?"\"":"",s->error?s->error:"null",s->error?"\"":"");
    if (n<=0 || n>=(int)sizeof records || !save_file("records.json",records,(size_t)n)) disable("records-export");
    char complete[1024];
    n=snprintf(complete,sizeof complete,
        "{\"schema\":1,\"mode\":\"rms1-v1\",\"passed\":%s,\"calls\":%u,\"captured\":%s,"
        "\"error\":%s%s%s,\"instrumented\":true,\"timing_claim\":false,\"observer_hip_syncs\":%u,\"observer_hip_copies\":%u}\n",
        trace_error?"false":"true",sample.reserved,sample.captured?"true":"false",
        trace_error?"\"":"",trace_error?trace_error:"null",trace_error?"\"":"",sample.observer_syncs,sample.observer_copies);
    if (n<=0 || n>=(int)sizeof complete || !save_file("complete.json",complete,(size_t)n)) disable("complete-export");
    (void)pthread_mutex_unlock(&trace_mutex);
}
static void *harvest_worker(void *unused) {
    (void)unused;
    struct timespec began,now,delay={0,20000000};
    if (clock_gettime(CLOCK_MONOTONIC,&began)) return NULL;
    for (;;) {
        int requested=trigger("harvest",harvest_content,sizeof harvest_content-1);
        if (requested) {harvest(requested);return NULL;}
        if (clock_gettime(CLOCK_MONOTONIC,&now) || now.tv_sec-began.tv_sec>1800) return NULL;
        (void)nanosleep(&delay,NULL);
    }
}
static void verify_hash(int fd,off_t offset,size_t bytes,const char *wanted) {
    EVP_MD_CTX *ctx=EVP_MD_CTX_new();
    if (!ctx || EVP_DigestInit_ex(ctx,EVP_sha256(),NULL)!=1) fatal("hash-init");
    unsigned char buffer[65536],digest[32];unsigned length=0;
    while (bytes) {
        size_t amount=bytes<sizeof buffer?bytes:sizeof buffer;
        ssize_t got=pread(fd,buffer,amount,offset);
        if (got<0 && errno==EINTR) continue;
        if (got<=0 || (size_t)got>amount || EVP_DigestUpdate(ctx,buffer,(size_t)got)!=1) fatal("hash-read");
        offset+=got;bytes-=(size_t)got;
    }
    if (EVP_DigestFinal_ex(ctx,digest,&length)!=1 || length!=sizeof digest) fatal("hash-final");
    EVP_MD_CTX_free(ctx);
    char hex[65];
    for (size_t i=0;i<sizeof digest;i++) snprintf(hex+i*2,3,"%02x",(unsigned)digest[i]);
    if (strcmp(hex,wanted)) fatal("hash-mismatch");
}
struct site {uintptr_t entry,base;int found,kernel_found,globals_found;};
static int find_site(struct dl_phdr_info *info,size_t ignored,void *opaque) {
    (void)ignored;
    if (info->dlpi_name && *info->dlpi_name) return 0;
    struct site *site=opaque;
    if (WIRE_GUARD_RVA+1>UINTPTR_MAX-info->dlpi_addr) fatal("base-overflow");
    for (size_t i=0;i<info->dlpi_phnum;i++) {
        const Elf64_Phdr *p=&info->dlpi_phdr[i];
        if (p->p_type==PT_LOAD && p->p_flags==(PF_R|PF_X) &&
            p->p_vaddr<=ENTRY_RVA && ENTRY_RVA+FUNCTION_BYTES<=p->p_vaddr+p->p_filesz &&
            p->p_offset+ENTRY_RVA-p->p_vaddr==(uint64_t)ENTRY_OFFSET) {
            site->entry=info->dlpi_addr+ENTRY_RVA;site->base=info->dlpi_addr;site->found++;
        }
        if (p->p_type==PT_LOAD && (p->p_flags&PF_R) && p->p_vaddr<=RMS_IDENTITY_RVA &&
            RMS_IDENTITY_RVA+sizeof(uintptr_t)<=p->p_vaddr+p->p_memsz) site->kernel_found++;
        if (p->p_type==PT_LOAD && p->p_flags==(PF_R|PF_W) && p->p_vaddr<=RMS_OUTPUT_SLOT_RVA &&
            WIRE_GUARD_RVA+1<=p->p_vaddr+p->p_memsz) site->globals_found++;
    }
    return 1;
}
static void absolute_jump(unsigned char *at,uintptr_t target) {
    const unsigned char prefix[6]={0xff,0x25,0,0,0,0};
    memcpy(at,prefix,sizeof prefix);memcpy(at+6,&target,sizeof target);
}
static uintptr_t install_hook(uintptr_t entry,uintptr_t target) {
    long size=sysconf(_SC_PAGESIZE);
    if (size<=0 || ((unsigned long)size&((unsigned long)size-1))) fatal("page-size");
    uintptr_t page=entry&~((uintptr_t)size-1);unsigned char *thunk=NULL;
    if (entry+sizeof entry_signature>page+(uintptr_t)size || !mapped_span(page,(size_t)size,"r-xp")) fatal("entry-page");
    for (unsigned i=0;i<256;i++) {
        uintptr_t distance=(uintptr_t)(i/2+1)*0x200000;
        if ((i&1)?page<distance:distance>UINTPTR_MAX-page) continue;
        uintptr_t candidate=(i&1)?page-distance:page+distance;
        void *area=mmap((void *)candidate,(size_t)size,PROT_READ|PROT_WRITE,
            MAP_PRIVATE|MAP_ANONYMOUS|MAP_FIXED_NOREPLACE,-1,0);
        if (area==MAP_FAILED) {if (errno==EEXIST) continue;fatal("thunk-map");}
        if (area!=(void *)candidate) {if (munmap(area,(size_t)size)) fatal("thunk-unmap");fatal("fixed-noreplace");}
        thunk=area;break;
    }
    if (!thunk) fatal("thunk-exhausted");
    absolute_jump(thunk,target);
    /* Complete non-RIP-relative push rbp; push r15; push r14 only. The original
     * function resumes at +5 with its ordinary prologue/epilogue and ABI intact. */
    memcpy(thunk+64,entry_signature,5);absolute_jump(thunk+69,entry+5);
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
    int fd=open("/proc/self/cmdline",O_RDONLY|O_CLOEXEC);
    char command[4096];ssize_t bytes;
    if (fd<0) fatal("cmdline-open");
    do {bytes=read(fd,command,sizeof command);} while (bytes<0 && errno==EINTR);
    if (bytes<=0 || bytes>=(ssize_t)sizeof command || command[bytes-1] || close(fd)) fatal("cmdline-read");
    const char *argument=memchr(command,0,(size_t)bytes);
    return argument && argument+1<command+bytes && !strcmp(argument+1,"--ck");
}
__attribute__((constructor)) static void install(void) {
    char name[4096];ssize_t n=readlink("/proc/self/exe",name,sizeof name-1);
    if (n<0 || n>=(ssize_t)sizeof name-1) fatal("executable-name");
    name[n]=0;const char *base=strrchr(name,'/');base=base?base+1:name;
    if (strcmp(base,"flash_serve") || !serving_process()) return;
    const char *mode=getenv("HALOGEN_MTP_HIDDEN_RMS_TAP"),*directory=getenv("HALOGEN_MTP_HIDDEN_RMS_TAP_DIR");
    const char *wire=getenv("HALOGEN_MTP_WIRE");
    if (!mode || strcmp(mode,"rms1-v1") || !wire || strcmp(wire,"D") || !directory ||
        strncmp(directory,trace_prefix,sizeof trace_prefix-1) || strlen(directory)!=sizeof trace_prefix-1+32) fatal("configuration");
    for (const char *at=directory+sizeof trace_prefix-1;*at;at++)
        if (!((*at>='0' && *at<='9') || (*at>='a' && *at<='f'))) fatal("trace-run-id");
    int fd=open("/proc/self/exe",O_RDONLY|O_CLOEXEC);struct stat before,after;
    if (fd<0 || fstat(fd,&before) || !S_ISREG(before.st_mode) || before.st_size!=ENGINE_BYTES) fatal("executable-stat");
    Elf64_Ehdr eh;
    if (pread(fd,&eh,sizeof eh,0)!=(ssize_t)sizeof eh || memcmp(eh.e_ident,ELFMAG,SELFMAG) ||
        eh.e_ident[EI_CLASS]!=ELFCLASS64 || eh.e_ident[EI_DATA]!=ELFDATA2LSB || eh.e_type!=ET_DYN || eh.e_machine!=EM_X86_64) fatal("elf-identity");
    verify_hash(fd,0,(size_t)before.st_size,ENGINE_SHA);verify_hash(fd,ENTRY_OFFSET,FUNCTION_BYTES,FUNCTION_SHA);
    if (fstat(fd,&after) || before.st_dev!=after.st_dev || before.st_ino!=after.st_ino || before.st_size!=after.st_size ||
        before.st_mtim.tv_sec!=after.st_mtim.tv_sec || before.st_mtim.tv_nsec!=after.st_mtim.tv_nsec ||
        before.st_ctim.tv_sec!=after.st_ctim.tv_sec || before.st_ctim.tv_nsec!=after.st_ctim.tv_nsec || close(fd)) fatal("executable-consistency");
    struct site site={0};
    if (dl_iterate_phdr(find_site,&site)!=1 || site.found!=1 || site.kernel_found!=1 || site.globals_found!=1 ||
        !mapped_span(site.entry,FUNCTION_BYTES,"r-xp") || memcmp((const void *)site.entry,entry_signature,sizeof entry_signature) ||
        memcmp((const void *)(site.base+RMS_SIGNATURE_RVA),rms_signature,sizeof rms_signature)) fatal("native-signature");
    if (!mapped_read(site.base+RMS_IDENTITY_RVA,sizeof(uintptr_t)) ||
        !mapped_span(site.base+RMS_OUTPUT_SLOT_RVA,(size_t)(WIRE_GUARD_RVA+1-RMS_OUTPUT_SLOT_RVA),"rw-p")) fatal("native-global-span");
    engine_base=site.base;
    int tmp_dir=open("/tmp",O_RDONLY|O_DIRECTORY|O_CLOEXEC|O_NOFOLLOW);struct stat status;
    if (tmp_dir<0 || fstat(tmp_dir,&status) || !S_ISDIR(status.st_mode)) fatal("tmp-directory");
    const char *trace_name=directory+sizeof "/tmp/"-1;
    if (mkdirat(tmp_dir,trace_name,0700)) fatal("trace-mkdir");
    trace_dir=openat(tmp_dir,trace_name,O_RDONLY|O_DIRECTORY|O_CLOEXEC|O_NOFOLLOW);
    if (close(tmp_dir)) fatal("tmp-close");
    if (trace_dir<0 || fstat(trace_dir,&status) || !S_ISDIR(status.st_mode) || status.st_uid!=geteuid() ||
        (status.st_mode&0777)!=0700) fatal("trace-directory");
    /* Include both externally created exclusive triggers in the total cap. */
    trace_bytes=sizeof arm_content+sizeof harvest_content-2;trace_files=2;
    original_head=(head_fn)install_hook(site.entry,(uintptr_t)tapped_head);
    char header[4096];
    int header_n=snprintf(header,sizeof header,
        "{\"schema\":1,\"mode\":\"rms1-v1\",\"engine_sha256\":\"%s\",\"engine_bytes\":26052768,"
        "\"function_sha256\":\"%s\",\"entry_rva\":\"0x17db310\",\"kernel_identity_rva\":\"0x18d5160\","
        "\"launch_return_rva\":\"0x17db632\",\"fc_start_rva\":\"0x17db636\",\"wire_global_rva\":\"0x18dccc0\","
        "\"wire_env_required\":\"D\",\"output_slot_rva\":\"0x18db210\",\"input_model_offset\":\"0x6d0\","
        "\"raw_gamma_model_offset\":\"0xaf0\",\"limit\":1,\"selected_count\":1,\"width\":10240,\"groups\":1,"
        "\"tensor_bytes\":20480,\"host_staging_bytes\":61440,\"observer_device_allocations\":0,"
        "\"host_device_pointer_dereferences\":0,\"post_request_harvest_required\":true,\"per_call_record_writes\":false,"
        "\"instrumented\":true,\"timing_claim\":false,\"file_limit\":8,\"byte_limit\":131072}\n",ENGINE_SHA,FUNCTION_SHA);
    if (header_n<=0 || header_n>=(int)sizeof header || !save_file("activation.json",header,(size_t)header_n)) fatal("activation-export");
    pthread_t worker;
    if (pthread_create(&worker,NULL,harvest_worker,NULL) || pthread_detach(worker)) fatal("harvest-thread");
    atomic_store(&initialized,1);
}
