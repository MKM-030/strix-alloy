/* Default-off, one frozen 16K request: publish owned later-chunk raw tokens.
 * Separate 0.17.2 source-only port. Void forwarding follows the captured native ABI.
 * Source only here. Root owns build, sole process, sealed owner receipt,
 * native reset/cache policy, request, outer guard and cleanup. No HIP API,
 * device buffer, activation capture, worker start or result substitution.
 * Copy the complete request at wrapper entry; publish at its first ordinary
 * Target tap, after the wrapper has resolved its effective 8192 chunk size.
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
#include <sys/syscall.h>
#include <time.h>
#include <unistd.h>
#include "ple_engine_binding_0172.h"
#define PLE_BINDING_HEADER_SHA "70fef9599dd6f9f4722ce73d73a11a5c92e4e790cc6ba505f5b176a0d6824681"

#if !defined(__linux__) || !defined(__x86_64__)
#error Root reviewed Linux x86-64 build required
#endif
#ifndef PLE_EARLY_BUILD_SHA
#error Root must pin the complete publisher source SHA256 at build time
#endif
#ifndef RENAME_NOREPLACE
#define RENAME_NOREPLACE 1
#endif
#define WRAPPER_RVA PLE_WRAPPER_RVA
#define WRAPPER_OFFSET PLE_WRAPPER_OFFSET
#define WRAPPER_PIN_BYTES PLE_WRAPPER_BYTES
#define WRAPPER_PIN_SHA PLE_WRAPPER_SHA
#define WRAPPER_TARGET_RETURN PLE_WRAPPER_TARGET_RETURN
#define HELPER_RETURN PLE_HELPER_RETURN
#define KEY_RETURN PLE_KEY_RETURN
#define CHUNK_GLOBAL PLE_CHUNK_GLOBAL
#define CHUNK_INIT_GLOBAL PLE_CHUNK_INIT_GLOBAL
#define FULL_COUNT 16384
#define CHUNK_COUNT 8192
#define OUTPUT_BYTE_LIMIT ((size_t)65536)
#define OUTPUT_FILE_LIMIT 6u
#define PUBLICATION_BUDGET_NS UINT64_C(5000000000)
#define wrapper_signature ple_wrapper_signature
static const char directory_prefix[]="/tmp/alloy-ple16k-early-0172-";
static const char arm_text[]="ordinary-ple16k-raw-0172-v1-armed\n";
typedef void (*wrapper_fn)(void *,const int32_t *,int32_t);
typedef void (*target_fn)(void *,const int32_t *,int32_t,int32_t);
typedef void (*helper_fn)(const int32_t *,const int64_t *,const int64_t *,
    const int64_t *,const int64_t *,int32_t,int64_t *,int64_t *,int32_t *);
typedef void (*fc_fn)(const void *,const void *,void *,int32_t,int32_t,int64_t);
static wrapper_fn original_wrapper;
static target_fn original_target;
static helper_fn original_helper;
static fc_fn original_fc;
static uintptr_t engine_base;
static int out_dir=-1;
static size_t output_bytes;
static unsigned output_files,target_calls,helper_calls,key_calls;
static _Atomic int enabled,claimed,wrappers_in_flight,targets_in_flight;
static pthread_mutex_t selection_mutex=PTHREAD_MUTEX_INITIALIZER;
static _Thread_local int selected_wrapper,selected_target=-1;
static int32_t owned_full[FULL_COUNT],target_next[2];
static int64_t owned_history[2];
static const int32_t *request_tokens;
static void *request_model;
static uintptr_t request_callback_manager,request_callback_invoker;
static char request_id[33],model_generation[33],table_generation[33];
static char owner_sha[65],full_sha[65],chunk_sha[65],history_sha[65];
static uint64_t process_birth_ticks,wrapper_enter_ns,copy_done_ns,publish_begin_ns;
static uint64_t published_ns,target_begin_ns[2],target_end_ns[2],later_helper_ns,later_key_ns;

static _Noreturn void fatal(const char *why) {
    dprintf(2,"[ple16k-early] fatal %s errno=%d\n",why,errno);_exit(79);
}
static int hex_text(const char *p,size_t n) {
    return p && strlen(p)==n && strspn(p,"0123456789abcdef")==n;
}
static int generation(const char *p) {
    return hex_text(p,32) && strspn(p,"0")!=32;
}
static uint64_t clock_ns(void) {
    struct timespec t;
    if (clock_gettime(CLOCK_MONOTONIC_RAW,&t) || t.tv_sec<0 || t.tv_nsec<0 ||
        t.tv_nsec>=1000000000L || (uint64_t)t.tv_sec>(UINT64_MAX-(uint64_t)t.tv_nsec)/UINT64_C(1000000000)) fatal("raw-clock");
    return (uint64_t)t.tv_sec*UINT64_C(1000000000)+(uint64_t)t.tv_nsec;
}
static int stable_stat(const struct stat *a,const struct stat *b) {
    return a->st_dev==b->st_dev && a->st_ino==b->st_ino && a->st_size==b->st_size &&
        a->st_mtim.tv_sec==b->st_mtim.tv_sec && a->st_mtim.tv_nsec==b->st_mtim.tv_nsec &&
        a->st_ctim.tv_sec==b->st_ctim.tv_sec && a->st_ctim.tv_nsec==b->st_ctim.tv_nsec;
}
static void hash_buffer(const void *p,size_t n,char out[65]) {
    unsigned char digest[32];unsigned count=0;
    if (EVP_Digest(p,n,digest,&count,EVP_sha256(),NULL)!=1 || count!=32) fatal("buffer-hash");
    for (unsigned i=0;i<32;i++) snprintf(out+i*2,3,"%02x",digest[i]);
}
static void verify_hash(int fd,off_t at,size_t bytes,const char *wanted) {
    EVP_MD_CTX *ctx=EVP_MD_CTX_new();unsigned char block[65536],digest[32];unsigned count=0;
    if (!ctx || EVP_DigestInit_ex(ctx,EVP_sha256(),NULL)!=1) fatal("image-hash-init");
    while (bytes) {
        size_t amount=bytes<sizeof block?bytes:sizeof block;
        ssize_t got=pread(fd,block,amount,at);
        if (got<0 && errno==EINTR) continue;
        if (got<=0 || (size_t)got>amount || EVP_DigestUpdate(ctx,block,(size_t)got)!=1) fatal("image-hash-read");
        at+=got;bytes-=(size_t)got;
    }
    if (EVP_DigestFinal_ex(ctx,digest,&count)!=1 || count!=32) fatal("image-hash-final");
    EVP_MD_CTX_free(ctx);char actual[65];
    for (unsigned i=0;i<32;i++) snprintf(actual+i*2,3,"%02x",digest[i]);
    if (strcmp(actual,wanted)) fatal("image-hash-differs");
}
static int mapped(uintptr_t address,size_t bytes,const char *wanted) {
    if (!address || !bytes || bytes>UINTPTR_MAX-address) return 0;
    FILE *f=fopen("/proc/self/maps","re");if (!f) return 0;
    char line[4096],perms[5];unsigned long lo,hi;int found=0;
    while (fgets(line,sizeof line,f)) {
        if (sscanf(line,"%lx-%lx %4s",&lo,&hi,perms)!=3) continue;
        if (address>=lo && address+bytes<=hi && (wanted?!strcmp(perms,wanted):perms[0]=='r')) {found=1;break;}
    }
    int error=ferror(f);if (fclose(f)) error=1;return error?0:found;
}
static int owned_read(const char *name,char *out,size_t cap,size_t *bytes) {
    int fd=openat(out_dir,name,O_RDONLY|O_NOFOLLOW|O_CLOEXEC);
    if (fd<0) return errno==ENOENT?0:-1;
    struct stat a,b;ssize_t got=-1;
    int ok=!fstat(fd,&a) && S_ISREG(a.st_mode) && a.st_uid==geteuid() && a.st_nlink==1 &&
        (a.st_mode&0777)==0600 && a.st_size>0 && (uint64_t)a.st_size<cap;
    if (ok) {do {got=pread(fd,out,(size_t)a.st_size+1,0);} while (got<0 && errno==EINTR);}
    if (!ok || got!=a.st_size || fstat(fd,&b) || !stable_stat(&a,&b)) ok=0;
    if (close(fd)) ok=0;
    if (!ok) return -1;
    *bytes=(size_t)got;out[*bytes]=0;return 1;
}
static int armed(void) {
    char text[64];size_t bytes=0;int result=owned_read("armed",text,sizeof text,&bytes);
    if (result<0 || (result && (bytes!=strlen(arm_text) || memcmp(text,arm_text,bytes)))) fatal("arm-binding");
    return result;
}
static void check_cancel(void) {
    char text[256],wanted[256];size_t bytes=0;
    int result=owned_read("cancel",text,sizeof text,&bytes);
    if (result<0) fatal("cancel-file-binding");
    if (!result) return;
    int n=snprintf(wanted,sizeof wanted,"schema=ordinary-ple16k-raw-0172-v1-cancel\nrequest_id=%s\nmodel_generation=%s\n",
                   request_id,model_generation);
    if (n<=0 || (size_t)n>=sizeof wanted || bytes!=(size_t)n || memcmp(text,wanted,bytes)) fatal("cancel-generation-differs");
    fatal("owned-request-canceled");
}
static void publication_gate(void) {
    uint64_t now=clock_ns();
    if (now<wrapper_enter_ns || now-wrapper_enter_ns>=PUBLICATION_BUDGET_NS) fatal("publication-soft-deadline");
    check_cancel();
    now=clock_ns();
    if (now<wrapper_enter_ns || now-wrapper_enter_ns>=PUBLICATION_BUDGET_NS) fatal("publication-soft-deadline-after-probe");
}
static void save_file(const char *name,const void *data,size_t bytes) {
    if (!bytes || output_files>=OUTPUT_FILE_LIMIT || output_bytes>OUTPUT_BYTE_LIMIT || bytes>OUTPUT_BYTE_LIMIT-output_bytes) fatal("bounded-output");
    int fd=openat(out_dir,name,O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);
    struct stat st;if (fd<0 || fstat(fd,&st) || !S_ISREG(st.st_mode) || st.st_uid!=geteuid() || st.st_nlink!=1 ||
        (st.st_mode&0777)!=0600 || st.st_size) fatal("exclusive-output");
    output_files++;const unsigned char *at=data;size_t remaining=bytes;
    while (remaining) {
        ssize_t got=write(fd,at,remaining);if (got<0 && errno==EINTR) continue;
        if (got<=0 || (size_t)got>remaining) fatal("output-write");
        at+=got;remaining-=(size_t)got;output_bytes+=(size_t)got;
    }
    if (fsync(fd) || close(fd)) fatal("output-fsync-close");
}
static void process_birth(void) {
    int fd=open("/proc/self/stat",O_RDONLY|O_CLOEXEC);char text[4096];ssize_t n;
    if (fd<0) fatal("birth-open");
    do {n=read(fd,text,sizeof text-1);} while (n<0 && errno==EINTR);
    if (n<=0 || n>=(ssize_t)sizeof text-1 || close(fd)) fatal("birth-read");
    text[n]=0;char *at=strrchr(text,')');if (!at || at[1]!=' ') fatal("birth-parse");at+=2;
    for (unsigned field=3;field<=22;field++) {
        char *end=strchr(at,' ');if (!end) fatal("birth-field");
        if (field==22) {
            errno=0;char *number_end=NULL;unsigned long long value=strtoull(at,&number_end,10);
            if (errno || number_end!=end || !value) fatal("birth-value");
            process_birth_ticks=(uint64_t)value;
            return;
        }
        at=end+1;
    }
    fatal("birth-missing");
}
static void load_owner(void) {
    char text[1024],canonical[1024],actual[65];size_t bytes=0;int end=0;
    if (owned_read("owner.receipt",text,sizeof text,&bytes)!=1) fatal("owner-receipt");
    hash_buffer(text,bytes,actual);if (strcmp(actual,owner_sha)) fatal("owner-receipt-sha");
    int count=sscanf(text,"schema=ordinary-ple16k-raw-0172-v1\nengine_version=0.17.2\nengine_sha256=" PLE_ENGINE_SHA "\nsource_sha256=" PLE_EARLY_BUILD_SHA "\nbinding_header_sha256=" PLE_BINDING_HEADER_SHA "\nrequest_id=%32[0-9a-f]\nmodel_generation=%32[0-9a-f]\ntable_generation=%32[0-9a-f]\nfull_tokens_sha256=%64[0-9a-f]\n%n",
        request_id,model_generation,table_generation,full_sha,&end);
    if (count!=4 || end!=(int)bytes || !generation(request_id) || !generation(model_generation) ||
        !generation(table_generation) || !hex_text(full_sha,64)) fatal("owner-fields");
    int n=snprintf(canonical,sizeof canonical,"schema=ordinary-ple16k-raw-0172-v1\nengine_version=0.17.2\nengine_sha256=" PLE_ENGINE_SHA "\nsource_sha256=" PLE_EARLY_BUILD_SHA "\nbinding_header_sha256=" PLE_BINDING_HEADER_SHA "\nrequest_id=%s\nmodel_generation=%s\ntable_generation=%s\nfull_tokens_sha256=%s\n",
        request_id,model_generation,table_generation,full_sha);
    if (n<=0 || (size_t)n!=bytes || memcmp(text,canonical,bytes)) fatal("owner-canonical");
    const char *directory=getenv("HALOGEN_PLE_EARLY_TOKENS_DIR");
    if (!directory || strcmp(directory+sizeof directory_prefix-1,request_id)) fatal("request-directory-generation");
}
static int ordinary_model(void *model) {
    return mapped((uintptr_t)model,PLE_MODEL_READABLE_EXTENT,NULL) &&
        !*(const uintptr_t *)((const unsigned char *)model+PLE_MODEL_MIXED_MANAGER_1) &&
        !*(const uintptr_t *)((const unsigned char *)model+PLE_MODEL_MIXED_MANAGER_2) &&
        !*((const unsigned char *)model+PLE_MODEL_STOP);
}
static int effective_chunk(void *model) {
    if (!*(const unsigned char *)(engine_base+CHUNK_INIT_GLOBAL)) return 0;
    int32_t configured=*(const int32_t *)(engine_base+CHUNK_GLOBAL);
    int32_t capacity=*(const int32_t *)((const unsigned char *)model+PLE_MODEL_CAPACITY);
    int32_t preferred=configured>0?configured:FULL_COUNT;
    return capacity<preferred?capacity:preferred;
}
/* The native wrapper owns joining/cleanup. Inspect only after its return. */
static int native_wrapper_complete(void *model) {
    const unsigned char *m=model;
    if (!ordinary_model(model) || *(const int32_t *)(m+PLE_MODEL_POSITION)!=FULL_COUNT ||
        *(const uintptr_t *)(m+PLE_MODEL_CALLBACK_MANAGER)!=request_callback_manager ||
        *(const uintptr_t *)(m+PLE_MODEL_CALLBACK_INVOKER)!=request_callback_invoker ||
        *(const uintptr_t *)(m+PLE_MODEL_NATIVE_NEXT_TOKENS) ||
        *(const int32_t *)(m+PLE_MODEL_NATIVE_NEXT_COUNT)) return 0;
    uintptr_t state=*(const uintptr_t *)(m+PLE_MODEL_NATIVE_THREAD_STATE);
    if (!state) return 1;
    if (!mapped(state,0xf1,NULL)) return 0;
    const unsigned char *s=(const unsigned char *)state;
    return !s[0xf0] && *(const uintptr_t *)(s+0xc8)==*(const uintptr_t *)(s+0xd0) &&
        *(const uintptr_t *)(s+8)==*(const uintptr_t *)(s+0x10);
}
static void publish_tokens(void) {
    publication_gate();publish_begin_ns=clock_ns();
    save_file("tokens-i32.bin",owned_full+CHUNK_COUNT,(size_t)CHUNK_COUNT*4);
    publication_gate();save_file("history-before-i64.bin",owned_history,sizeof owned_history);
    publication_gate();char text[3072];
    int n=snprintf(text,sizeof text,
        "{\"engine_version\":\"" PLE_ENGINE_VERSION "\",\"binding_header_sha256\":\"" PLE_BINDING_HEADER_SHA "\",\"schema\":\"private.ple-early-raw-token-publication.0172.v1\",\"request_id\":\"%s\","
        "\"model_generation\":\"%s\",\"table_generation\":\"%s\",\"pid\":%ld,\"process_birth_ticks\":%" PRIu64 ","
        "\"model_pointer\":\"0x%" PRIxPTR "\",\"full_token_count\":16384,\"chunk_offset\":8192,\"chunk_count\":8192,"
        "\"full_tokens_sha256\":\"%s\",\"tokens_file\":\"tokens-i32.bin\",\"tokens_bytes\":32768,\"tokens_sha256\":\"%s\","
        "\"history_file\":\"history-before-i64.bin\",\"history_bytes\":16,\"history_sha256\":\"%s\","
        "\"preceding_two_signed_int64\":[%" PRId64 ",%" PRId64 "],\"owner_receipt_sha256\":\"%s\","
        "\"source_sha256\":\"%s\",\"engine_sha256\":\"%s\",\"clock\":\"CLOCK_MONOTONIC_RAW\","
        "\"wrapper_enter_ns\":%" PRIu64 ",\"owned_copy_done_ns\":%" PRIu64 ",\"publication_begin_ns\":%" PRIu64 ","
        "\"publication_completed_ns_location\":\"token-window.json after the request\",\"stage\":\"first ordinary Target tap before original Target\","
        "\"native_first_target_not_entered\":true,\"worker_started\":false,\"input_ready\":false,\"result_substitution\":false,\"speed_claim\":false}\n",
        request_id,model_generation,table_generation,(long)getpid(),process_birth_ticks,(uintptr_t)request_model,
        full_sha,chunk_sha,history_sha,owned_history[0],owned_history[1],owner_sha,PLE_EARLY_BUILD_SHA,PLE_ENGINE_SHA,
        wrapper_enter_ns,copy_done_ns,publish_begin_ns);
    if (n<=0 || (size_t)n>=sizeof text) fatal("ready-format");
    save_file("token-ready.json.partial",text,(size_t)n);
    /* Final cancellation/deadline check follows receipt fsync. Only then expose readiness. */
    publication_gate();
    if (syscall(SYS_renameat2,out_dir,"token-ready.json.partial",out_dir,"token-ready.json",RENAME_NOREPLACE) || fsync(out_dir)) fatal("atomic-token-publication");
    published_ns=clock_ns();
}
static void export_window(void) {
    if (target_calls!=2 || helper_calls!=1 || key_calls!=1 || !published_ns ||
        published_ns>target_begin_ns[0] || target_end_ns[0]>target_begin_ns[1] ||
        target_begin_ns[1]>later_helper_ns || later_helper_ns>later_key_ns || later_key_ns>target_end_ns[1]) fatal("incomplete-stage-observation");
    char text[3072];int n=snprintf(text,sizeof text,
        "{\"engine_version\":\"" PLE_ENGINE_VERSION "\",\"binding_header_sha256\":\"" PLE_BINDING_HEADER_SHA "\",\"schema\":\"private.ple-early-raw-token-window.0172.v1\",\"structural_observation_complete\":true,\"request_id\":\"%s\","
        "\"model_generation\":\"%s\",\"table_generation\":\"%s\",\"pid\":%ld,\"process_birth_ticks\":%" PRIu64 ","
        "\"chunk_offset\":8192,\"chunk_count\":8192,\"full_tokens_sha256\":\"%s\",\"tokens_sha256\":\"%s\",\"history_sha256\":\"%s\","
        "\"clock\":\"CLOCK_MONOTONIC_RAW\",\"wrapper_enter_ns\":%" PRIu64 ",\"owned_copy_done_ns\":%" PRIu64 ","
        "\"publication_begin_ns\":%" PRIu64 ",\"publication_completed_ns\":%" PRIu64 ","
        "\"target_begin_ns\":[%" PRIu64 ",%" PRIu64 "],\"target_end_ns\":[%" PRIu64 ",%" PRIu64 "],"
        "\"later_helper_begin_ns\":%" PRIu64 ",\"later_key_begin_ns\":%" PRIu64 ","
        "\"target_next_arguments\":[%d,%d],\"native_wrapper_returned\":true,"
        "\"source_sha256\":\"%s\",\"owner_receipt_sha256\":\"%s\",\"observed_targets\":2,"
        "\"actual_second_slice_bytes_verified\":true,\"native_calls_preserved\":true,\"device_syncs\":0,\"device_copies\":0,"
        "\"engine_sha256\":\"" PLE_ENGINE_SHA "\",\"model_position_after\":16384,\"stop_after\":false,"
        "\"callback_fields_preserved\":true,\"native_thread_cleanup_observed\":true,"
        "\"inference_success_claim\":false,\"external_http_completion_required\":true,"
        "\"worker_started\":false,\"input_ready_lead_qualified\":false,\"serving_gain_qualified\":false,\"speed_claim\":false}\n",
        request_id,model_generation,table_generation,(long)getpid(),process_birth_ticks,full_sha,chunk_sha,history_sha,
        wrapper_enter_ns,copy_done_ns,publish_begin_ns,published_ns,target_begin_ns[0],target_begin_ns[1],target_end_ns[0],target_end_ns[1],
        later_helper_ns,later_key_ns,target_next[0],target_next[1],PLE_EARLY_BUILD_SHA,owner_sha);
    if (n<=0 || (size_t)n>=sizeof text) fatal("window-format");
    save_file("token-window.json",text,(size_t)n);
}
__attribute__((noinline)) static void wrapper_tap(void *model,const int32_t *tokens,int32_t count) {
    int incoming_errno=errno,selected=0;
    unsigned preceding=(unsigned)atomic_fetch_add(&wrappers_in_flight,1);
    if (atomic_load(&claimed)==1 && preceding) fatal("overlapping-wrapper");
    if (!preceding && !selected_wrapper && count==FULL_COUNT && atomic_load(&enabled)) {
        if (pthread_mutex_lock(&selection_mutex)) fatal("selection-lock");
        if (!atomic_load(&claimed) && armed()) {
            load_owner();check_cancel();
            if (!ordinary_model(model) || *(const int32_t *)((const unsigned char *)model+PLE_MODEL_POSITION)!=0 ||
                !mapped((uintptr_t)tokens,sizeof owned_full,NULL) || atomic_load(&targets_in_flight)) fatal("full-request-ownership");
            atomic_store(&claimed,1);selected=1;selected_wrapper=1;wrapper_enter_ns=clock_ns();
            request_tokens=tokens;request_model=model;
            request_callback_manager=*(const uintptr_t *)((const unsigned char *)model+PLE_MODEL_CALLBACK_MANAGER);
            request_callback_invoker=*(const uintptr_t *)((const unsigned char *)model+PLE_MODEL_CALLBACK_INVOKER);
            if (request_callback_manager!=engine_base+PLE_SERVING_CALLBACK_MANAGER_RVA ||
                request_callback_invoker!=engine_base+PLE_SERVING_CALLBACK_INVOKER_RVA)
                fatal("serving-callback-binding");
            memcpy(owned_full,tokens,sizeof owned_full);
            char actual[65];hash_buffer(owned_full,sizeof owned_full,actual);
            if (strcmp(actual,full_sha)) fatal("frozen-full-tokens-differ");
            owned_history[0]=(int64_t)owned_full[CHUNK_COUNT-2];owned_history[1]=(int64_t)owned_full[CHUNK_COUNT-1];
            hash_buffer(owned_full+CHUNK_COUNT,(size_t)CHUNK_COUNT*4,chunk_sha);
            hash_buffer(owned_history,sizeof owned_history,history_sha);copy_done_ns=clock_ns();
        }
        if (pthread_mutex_unlock(&selection_mutex)) fatal("selection-unlock");
    }
    errno=incoming_errno;original_wrapper(model,tokens,count);int original_errno=errno;
    if (selected) {
        check_cancel();
        if (!native_wrapper_complete(model)) fatal("native-wrapper-completion-binding");
        export_window();selected_wrapper=0;atomic_store(&claimed,2);
    }
    atomic_fetch_sub(&wrappers_in_flight,1);errno=original_errno;
}
__attribute__((noinline)) static void target_tap(void *model,const int32_t *tokens,int32_t count,int32_t next) {
    int incoming_errno=errno;uintptr_t pc=(uintptr_t)__builtin_return_address(0);
    unsigned preceding=(unsigned)atomic_fetch_add(&targets_in_flight,1);int index=-1;
    if (selected_wrapper) {
        index=(int)target_calls;
        if (preceding || index>=2 || selected_target!=-1 || pc!=engine_base+WRAPPER_TARGET_RETURN || model!=request_model ||
            !ordinary_model(model) || effective_chunk(model)!=CHUNK_COUNT || count!=CHUNK_COUNT ||
            *(const int32_t *)((const unsigned char *)model+PLE_MODEL_POSITION)!=index*CHUNK_COUNT ||
            tokens!=request_tokens+(size_t)index*CHUNK_COUNT ||
            memcmp(tokens,owned_full+(size_t)index*CHUNK_COUNT,(size_t)CHUNK_COUNT*4) ||
            next!=(index? -1:owned_full[CHUNK_COUNT])) fatal("ordinary-target-slice-binding");
        check_cancel();if (!index) publish_tokens();
        else if (!published_ns) fatal("later-target-before-publication");
        selected_target=index;target_next[index]=next;target_begin_ns[index]=clock_ns();target_calls++;
    } else if (atomic_load(&claimed)==1) fatal("unowned-target-overlap");
    errno=incoming_errno;original_target(model,tokens,count,next);int original_errno=errno;
    if (index>=0) {
        target_end_ns[index]=clock_ns();selected_target=-1;
        if (!ordinary_model(model) ||
            *(const int32_t *)((const unsigned char *)model+PLE_MODEL_POSITION)!=(index+1)*CHUNK_COUNT)
            fatal("native-target-completion-binding");
    }
    atomic_fetch_sub(&targets_in_flight,1);errno=original_errno;
}
__attribute__((noinline)) static void helper_tap(const int32_t *t,const int64_t *c,const int64_t *mult,
    const int64_t *mod,const int64_t *offsets,int32_t count,int64_t *out,int64_t *hist,int32_t *seg) {
    int incoming_errno=errno;uintptr_t pc=(uintptr_t)__builtin_return_address(0);
    if (selected_target==1 && pc==engine_base+HELPER_RETURN) {
        if (count!=CHUNK_COUNT || helper_calls++) fatal("later-helper-identity");
        later_helper_ns=clock_ns();
    }
    errno=incoming_errno;original_helper(t,c,mult,mod,offsets,count,out,hist,seg);
}
__attribute__((noinline)) static void fc_tap(const void *d,const void *x,void *y,int32_t n,int32_t m,int64_t k) {
    int incoming_errno=errno;uintptr_t pc=(uintptr_t)__builtin_return_address(0);
    if (selected_target==1 && pc==engine_base+KEY_RETURN) {
        if (key_calls++ || !later_helper_ns) fatal("later-key-identity");
        later_key_ns=clock_ns();
    }
    errno=incoming_errno;original_fc(d,x,y,n,m,k);
}

/* Exact five-byte, whole-instruction detours from the reviewed capture source. */
static void absolute_jump(unsigned char *p,uintptr_t target) {
    const unsigned char prefix[6]={0xff,0x25,0,0,0,0};memcpy(p,prefix,6);memcpy(p+6,&target,8);
}
static uintptr_t install_hook(uintptr_t entry,uintptr_t target,const unsigned char signature[32]) {
    long page_bytes=sysconf(_SC_PAGESIZE);
    if (page_bytes<=0 || ((unsigned long)page_bytes&((unsigned long)page_bytes-1))) fatal("page-size");
    uintptr_t page=entry&~((uintptr_t)page_bytes-1);unsigned char *thunk=NULL;
    if (entry+32>page+(uintptr_t)page_bytes || !mapped(page,(size_t)page_bytes,"r-xp")) fatal("entry-page");
    for (unsigned i=0;i<256;i++) {
        uintptr_t distance=(uintptr_t)(i/2+1)*0x200000;
        if ((i&1)?page<distance:distance>UINTPTR_MAX-page) continue;
        uintptr_t candidate=(i&1)?page-distance:page+distance;
        void *area=mmap((void *)candidate,(size_t)page_bytes,PROT_READ|PROT_WRITE,
                       MAP_PRIVATE|MAP_ANONYMOUS|MAP_FIXED_NOREPLACE,-1,0);
        if (area==MAP_FAILED) {if (errno==EEXIST) continue;fatal("thunk-map");}
        if (area!=(void *)candidate) fatal("fixed-noreplace");
        thunk=area;
        break;
    }
    if (!thunk) fatal("thunk-exhausted");
    absolute_jump(thunk,target);memcpy(thunk+64,signature,5);absolute_jump(thunk+69,entry+5);
    if (mprotect(thunk,(size_t)page_bytes,PROT_READ|PROT_EXEC)) fatal("thunk-rx");
    intptr_t distance=(intptr_t)((uintptr_t)thunk-(entry+5));
    if (distance<INT32_MIN || distance>INT32_MAX) fatal("thunk-range");
    unsigned char jump[5]={0xe9};int32_t relative=(int32_t)distance;memcpy(jump+1,&relative,4);
    if (mprotect((void *)page,(size_t)page_bytes,PROT_READ|PROT_WRITE)) fatal("entry-rw");
    memcpy((void *)entry,jump,5);__builtin___clear_cache((char *)entry,(char *)entry+5);
    if (mprotect((void *)page,(size_t)page_bytes,PROT_READ|PROT_EXEC)) fatal("entry-rx");
    return (uintptr_t)(thunk+64);
}
struct site {uintptr_t base;unsigned functions[4],globals;};
static int find_site(struct dl_phdr_info *info,size_t unused,void *opaque) {
    (void)unused;if (info->dlpi_name && *info->dlpi_name) return 0;
    struct site *s=opaque;s->base=info->dlpi_addr;
    const uintptr_t rvas[4]={WRAPPER_RVA,PLE_TARGET_RVA,PLE_HELPER_RVA,PLE_FC_RVA};
    const size_t bytes[4]={WRAPPER_PIN_BYTES,PLE_TARGET_BYTES,PLE_HELPER_BYTES,PLE_FC_BYTES};
    const off_t offsets[4]={WRAPPER_OFFSET,PLE_TARGET_OFFSET,PLE_HELPER_OFFSET,PLE_FC_OFFSET};
    if (CHUNK_INIT_GLOBAL+1>UINTPTR_MAX-s->base) fatal("engine-base-overflow");
    for (size_t i=0;i<info->dlpi_phnum;i++) {
        const Elf64_Phdr *p=&info->dlpi_phdr[i];
        if (p->p_type!=PT_LOAD || p->p_vaddr>UINT64_MAX-p->p_filesz || p->p_vaddr>UINT64_MAX-p->p_memsz) continue;
        for (unsigned j=0;j<4;j++) if (p->p_flags==(PF_R|PF_X) && p->p_vaddr<=rvas[j] &&
            rvas[j]+bytes[j]<=p->p_vaddr+p->p_filesz && p->p_offset+rvas[j]-p->p_vaddr==(uint64_t)offsets[j]) s->functions[j]++;
        if (p->p_flags==(PF_R|PF_W) && p->p_vaddr<=CHUNK_GLOBAL && CHUNK_INIT_GLOBAL+1<=p->p_vaddr+p->p_memsz) s->globals++;
    }
    return 1;
}
static int serving_process(void) {
    int fd=open("/proc/self/cmdline",O_RDONLY|O_CLOEXEC);char text[4096];ssize_t bytes;
    if (fd<0) fatal("cmdline-open");
    do {bytes=read(fd,text,sizeof text);} while (bytes<0 && errno==EINTR);
    if (bytes<=0 || bytes>=(ssize_t)sizeof text || text[bytes-1] || close(fd)) fatal("cmdline-read");
    const char *argument=memchr(text,0,(size_t)bytes);
    return argument && argument+1<text+bytes && !strcmp(argument+1,"--ck");
}
__attribute__((constructor)) static void install(void) {
    const char *mode=getenv("HALOGEN_PLE_EARLY_TOKENS");if (!mode) return;
    char exe[4096];ssize_t size=readlink("/proc/self/exe",exe,sizeof exe-1);
    if (size<0 || size>=(ssize_t)sizeof exe-1) fatal("executable-name");
    exe[size]=0;const char *name=strrchr(exe,'/');name=name?name+1:exe;
    if (strcmp(name,"flash_serve") || !serving_process()) return;
    const char *directory=getenv("HALOGEN_PLE_EARLY_TOKENS_DIR"),*pin=getenv("HALOGEN_PLE_EARLY_TOKENS_RECEIPT_SHA256");
    if (strcmp(mode,"ordinary-ple16k-raw-0172-v1") || !directory || !hex_text(pin,64) ||
        strncmp(directory,directory_prefix,sizeof directory_prefix-1) || strlen(directory)!=sizeof directory_prefix-1+32 ||
        !generation(directory+sizeof directory_prefix-1) || !hex_text(PLE_EARLY_BUILD_SHA,64)) fatal("configuration");
    memcpy(owner_sha,pin,65);
    const char *conflicts[]={"HALOGEN_PLE_COMPONENT","HALOGEN_PREFILL_HT_CAPTURE","HALOGEN_MTP_RAW_EMBEDDING_CAPTURE",
        "HALOGEN_MTP_FC_QUALITY","HALOGEN_MTP_HIDDEN_RMS_TAP","HALOGEN_MTP_EMBEDDING_CACHE","HALOGEN_MTP_FULL_EVENT_TAP"};
    for (unsigned i=0;i<sizeof conflicts/sizeof conflicts[0];i++) if (getenv(conflicts[i])) fatal("other-interposer");
    int fd=open("/proc/self/exe",O_RDONLY|O_CLOEXEC);struct stat before,after;Elf64_Ehdr eh;
    if (fd<0 || fstat(fd,&before) || !S_ISREG(before.st_mode) || before.st_size!=PLE_ENGINE_BYTES) fatal("engine-stat");
    if (pread(fd,&eh,sizeof eh,0)!=(ssize_t)sizeof eh || memcmp(eh.e_ident,ELFMAG,SELFMAG) ||
        eh.e_ident[EI_CLASS]!=ELFCLASS64 || eh.e_ident[EI_DATA]!=ELFDATA2LSB || eh.e_type!=ET_DYN || eh.e_machine!=EM_X86_64) fatal("engine-ELF");
    verify_hash(fd,0,(size_t)before.st_size,PLE_ENGINE_SHA);
    const uintptr_t rvas[4]={WRAPPER_RVA,PLE_TARGET_RVA,PLE_HELPER_RVA,PLE_FC_RVA};
    const off_t offsets[4]={WRAPPER_OFFSET,PLE_TARGET_OFFSET,PLE_HELPER_OFFSET,PLE_FC_OFFSET};
    const size_t bytes[4]={WRAPPER_PIN_BYTES,PLE_TARGET_BYTES,PLE_HELPER_BYTES,PLE_FC_BYTES};
    const char *hashes[4]={WRAPPER_PIN_SHA,PLE_TARGET_SHA,PLE_HELPER_SHA,PLE_FC_SHA};
    const unsigned char *signatures[4]={wrapper_signature,ple_target_signature,ple_helper_signature,ple_fc_signature};
    for (unsigned i=0;i<4;i++) verify_hash(fd,offsets[i],bytes[i],hashes[i]);
    if (fstat(fd,&after) || !stable_stat(&before,&after) || close(fd)) fatal("engine-changed");
    struct site site={0};if (dl_iterate_phdr(find_site,&site)!=1 || site.globals!=1) fatal("engine-load-map");
    for (unsigned i=0;i<4;i++) {
        char actual[65];
        if (site.functions[i]!=1 || !mapped(site.base+rvas[i],bytes[i],"r-xp") ||
            memcmp((void *)(site.base+rvas[i]),signatures[i],32)) fatal("mapped-entry-binding");
        hash_buffer((void *)(site.base+rvas[i]),bytes[i],actual);if (strcmp(actual,hashes[i])) fatal("mapped-code-sha");
    }
    if (!mapped(site.base+CHUNK_GLOBAL,9,"rw-p")) fatal("chunk-global-map");
    engine_base=site.base;
    int tmp=open("/tmp",O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);struct stat st;
    if (tmp<0 || fstat(tmp,&st) || !S_ISDIR(st.st_mode)) fatal("tmp-directory");
    const char *leaf=directory+5;if (mkdirat(tmp,leaf,0700)) fatal("exclusive-directory");
    out_dir=openat(tmp,leaf,O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
    if (close(tmp) || out_dir<0 || fstat(out_dir,&st) || !S_ISDIR(st.st_mode) || st.st_uid!=geteuid() || (st.st_mode&0777)!=0700) fatal("output-directory");
    process_birth();
    original_helper=(helper_fn)install_hook(engine_base+PLE_HELPER_RVA,(uintptr_t)helper_tap,ple_helper_signature);
    original_fc=(fc_fn)install_hook(engine_base+PLE_FC_RVA,(uintptr_t)fc_tap,ple_fc_signature);
    original_target=(target_fn)install_hook(engine_base+PLE_TARGET_RVA,(uintptr_t)target_tap,ple_target_signature);
    original_wrapper=(wrapper_fn)install_hook(engine_base+WRAPPER_RVA,(uintptr_t)wrapper_tap,wrapper_signature);
    char text[1024];int n=snprintf(text,sizeof text,
        "{\"engine_version\":\"" PLE_ENGINE_VERSION "\",\"binding_header_sha256\":\"" PLE_BINDING_HEADER_SHA "\",\"schema\":\"private.ple-early-raw-token-activation.0172.v1\",\"source_sha256\":\"%s\",\"engine_sha256\":\"%s\","
        "\"pid\":%ld,\"process_birth_ticks\":%" PRIu64 ",\"full_count\":16384,\"chunk_offset\":8192,\"chunk_count\":8192,"
        "\"owned_raw_buffer_bytes\":65552,\"output_file_limit\":6,\"output_byte_limit\":65536,"
        "\"publication_soft_budget_ns\":5000000000,\"device_allocations\":0,\"device_syncs\":0,\"device_copies\":0,"
        "\"result_substitution\":false,\"worker_started\":false,\"speed_claim\":false}\n",
        PLE_EARLY_BUILD_SHA,PLE_ENGINE_SHA,(long)getpid(),process_birth_ticks);
    if (n<=0 || (size_t)n>=sizeof text) fatal("activation-format");
    save_file("activation.json",text,(size_t)n);
    atomic_store(&enabled,1);
}
__attribute__((destructor)) static void dispose(void) {
    if (!atomic_load(&enabled)) return;
    if (atomic_load(&wrappers_in_flight) || atomic_load(&targets_in_flight)) fatal("live-request-at-exit");
    if (out_dir>=0 && close(out_dir)) fatal("output-close");
    /* Sole owned process exit releases detours and owned raw buffers. No unload while serving. */
}
