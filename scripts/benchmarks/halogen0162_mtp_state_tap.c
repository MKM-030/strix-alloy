/* Research-only host metadata for the complete MTP forward. Native always runs.
 * Source-only review: compilation and all owned hardware jobs belong to root.
 * Build: gcc -O2 -Wall -Wextra -Werror -shared -fPIC -fno-optimize-sibling-calls
 *        halogen0162_mtp_state_tap.c -ldl -lcrypto -pthread -o libhalogen0162-mtp-state-tap.so
 * This observer performs no HIP copy, event, synchronization, or device-pointer
 * dereference. It makes no timing or state-ownership claim. The only native
 * memory write is the guarded constructor-time full-forward text hook.
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
#include <stdarg.h>
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
#define WRAPPER_RVA ((uintptr_t)0x17dcde0)
#define WRAPPER_OFFSET ((off_t)0x17dbde0)
#define WRAPPER_BYTES ((size_t)(0x17dcfb5 - 0x17dcde0))
#define WRAPPER_SHA "2c6dc2832f047253b7459303253da0199e35c6944afb629f381b42d47c986892"
#define SCATTER_RVA ((uintptr_t)0x18d5338)
#define SCATTER_RETURN_RVA ((uintptr_t)0x17a0b70)
#define FD_ATTN_RVA ((uintptr_t)0x18d5348)
#define FD_ATTN_ALT_RVA ((uintptr_t)0x18d5350)
#define DESCRIPTOR_BYTES ((size_t)0xc68)
#define L48_OFFSET ((size_t)(48U * 0xc68U))
#define LAYER_TABLE_BYTES ((size_t)(49U * 0xc68U))
#define MODEL_READ_BYTES ((size_t)0x4e8)
#define FD_ROWS_BYTES 160U
#define TRACE_LIMIT 8U
#define TRACE_BYTE_LIMIT ((size_t)65536)
static const char trace_prefix[]="/tmp/alloy-mtp-state-tap-";
static const char arm_content[]="state8-v1-ready\n";
static const char harvest_content[]="state8-v1-harvest\n";
static const unsigned char entry_signature[32]={
    0x55,0x41,0x57,0x41,0x56,0x41,0x55,0x41,0x54,0x53,0x48,0x81,0xec,0x98,0,0,
    0,0xb8,0xff,0xff,0xff,0xff,0x80,0xbf,0,0x09,0,0,0x01,0x0f,0x85,0x31
};
static const unsigned char wrapper_signature[32]={
    0x41,0x56,0x53,0x50,0x89,0x74,0x24,0x04,0xb8,0xff,0xff,0xff,0xff,0x80,0xbf,0,
    0x09,0,0,0x01,0x0f,0x85,0x4f,0x01,0,0,0x89,0xd3,0x85,0xd2,0x0f,0x95
};
typedef int32_t (*head_fn)(void *,const int32_t *,int32_t,int32_t);
/* ABI-only HIP dim3 and opaque pointers. No ROCm headers or HIP linking. */
typedef struct { unsigned x,y,z; } hip_dim3;
typedef int (*launch_fn)(const void *,hip_dim3,hip_dim3,void **,size_t,void *);
enum rows_state { ROWS_DISABLED,ROWS_NOT_SEEN,ROWS_CAPTURED,ROWS_ARGS_UNREADABLE,ROWS_OBJECT_UNREADABLE };
struct sample {
    uintptr_t caller_rva,model,table_begin,table_end,fd_owner;
    uintptr_t k_history,v_history,compressed_keys,carry,rows_host_address;
    size_t table_descriptors;
    int32_t count,position,slot,model_position,result;
    unsigned model_fields_valid,table_extent_valid,l48_fields_valid,entry_valid,completed;
    unsigned kind,scatter_flag,kernels,nondefault_stream_launches;
    unsigned scatter_launches,scatter_exact_callsite,scatter_other_callsite,fd_attention_launches;
    unsigned rows_attempted,scatter_result_valid,nested_forwards;
    int scatter_result;
    enum rows_state rows_state;
    const char *error;
    unsigned char rows[FD_ROWS_BYTES];
};
static struct sample samples[TRACE_LIMIT];
static char export_buffer[49152];
static _Thread_local struct sample *active_sample;
static _Thread_local unsigned head_depth;
static head_fn original_head;
static launch_fn real_launch;
static uintptr_t engine_base;
static int capture_rows,trace_dir=-1,records_fd=-1;
static struct stat records_identity;
static pthread_once_t symbols_once=PTHREAD_ONCE_INIT;
static pthread_mutex_t trace_mutex=PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t trace_idle=PTHREAD_COND_INITIALIZER;
static _Atomic int initialized,armed_once,harvested;
static unsigned trace_count,in_flight,forward_calls,count1_calls,excluded_count_calls,limit_skipped_calls;
static size_t trace_bytes;
static const char *trace_error;
static pthread_t worker;

static _Noreturn void fatal(const char *reason) {
    dprintf(STDERR_FILENO,"[mtp-state-tap] fatal reason=%s errno=%d\n",reason,errno);
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
    if (failed) return 0;
    return found;
}
static int mapped_read(uintptr_t address,size_t bytes) {return mapped_span(address,bytes,NULL);}
static uintptr_t word_pointer(const unsigned char *object,size_t offset) {
    uintptr_t value;memcpy(&value,object+offset,sizeof value);return value;
}
static int32_t word32(const unsigned char *object,size_t offset) {
    int32_t value;memcpy(&value,object+offset,sizeof value);return value;
}
static void resolve_launch(void) {real_launch=(launch_fn)dlsym(RTLD_NEXT,"hipLaunchKernel");}
int hipLaunchKernel(const void *function,hip_dim3 grid,hip_dim3 block,void **args,size_t shared,void *stream) {
    int incoming_errno=errno;
    uintptr_t return_address=(uintptr_t)__builtin_return_address(0);
    uintptr_t caller=return_address>=engine_base?return_address-engine_base:UINTPTR_MAX;
    if (pthread_once(&symbols_once,resolve_launch) || !real_launch) fatal("launch-symbol");
    struct sample *s=active_sample;
    int first_exact=0;
    if (s) {
        s->kernels++;
        if (stream) s->nondefault_stream_launches++;
        if ((uintptr_t)function==engine_base+SCATTER_RVA) {
            s->scatter_launches++;
            if (caller==SCATTER_RETURN_RVA) {
                s->scatter_exact_callsite++;
                first_exact=!s->scatter_result_valid;
                if (capture_rows && s->entry_valid && !s->rows_attempted) {
                    s->rows_attempted=1;
                    if (!mapped_read((uintptr_t)args,3U*sizeof(void *))) {
                        s->rows_state=ROWS_ARGS_UNREADABLE;s->error="scatter-args-host-span";
                    } else {
                        uintptr_t rows;
                        memcpy(&rows,(const unsigned char *)args+2U*sizeof(void *),sizeof rows);
                        s->rows_host_address=rows;
                        if (!mapped_read(rows,FD_ROWS_BYTES)) {
                            s->rows_state=ROWS_OBJECT_UNREADABLE;s->error="scatter-object-host-span";
                        } else {
                            /* Raw host object only. Never follow any embedded pointer. */
                            memcpy(s->rows,(const void *)rows,FD_ROWS_BYTES);
                            s->rows_state=ROWS_CAPTURED;
                        }
                    }
                }
            } else s->scatter_other_callsite++;
        }
        if ((uintptr_t)function==engine_base+FD_ATTN_RVA ||
            (uintptr_t)function==engine_base+FD_ATTN_ALT_RVA) s->fd_attention_launches++;
    }
    errno=incoming_errno;
    int result=real_launch(function,grid,block,args,shared,stream);
    int result_errno=errno;
    if (s && first_exact) {s->scatter_result=result;s->scatter_result_valid=1;}
    errno=result_errno;return result;
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
static int save_text(const char *name,const char *data,size_t bytes) {
    int fd=openat(trace_dir,name,O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC|O_NOFOLLOW,0600);
    if (fd<0) return 0;
    int ok=append_bytes(fd,data,bytes);
    if (fsync(fd)) ok=0;
    if (close(fd)) ok=0;
    return ok;
}
/* Caller owns trace_mutex. No error publication on the native request path. */
static void disable(const char *reason) {if (!trace_error) trace_error=reason;}
static int trigger(const char *name,const char *wanted,size_t bytes) {
    int fd=openat(trace_dir,name,O_RDONLY|O_CLOEXEC|O_NOFOLLOW);
    if (fd<0) return errno==ENOENT?0:-1;
    struct stat before,after;char content[64];
    int ok=bytes<sizeof content && !fstat(fd,&before) && S_ISREG(before.st_mode) &&
        before.st_uid==geteuid() && before.st_nlink==1 && before.st_size==(off_t)bytes &&
        pread(fd,content,sizeof content,0)==(ssize_t)bytes && !memcmp(content,wanted,bytes) &&
        !fstat(fd,&after) && before.st_dev==after.st_dev && before.st_ino==after.st_ino &&
        before.st_size==after.st_size && before.st_mtim.tv_sec==after.st_mtim.tv_sec &&
        before.st_mtim.tv_nsec==after.st_mtim.tv_nsec;
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
static void observe_entry(struct sample *s,void *object,int32_t count,int32_t position,uintptr_t caller) {
    s->caller_rva=caller;s->model=(uintptr_t)object;s->count=count;s->position=position;
    s->rows_state=capture_rows?ROWS_NOT_SEEN:ROWS_DISABLED;
    if (!known_forward_caller(caller)) {s->error="forward-caller-rva";return;}
    if (!mapped_read(s->model,MODEL_READ_BYTES)) {s->error="model-host-span";return;}
    const unsigned char *model=object;
    s->model_fields_valid=1;s->scatter_flag=model[0xa4];s->slot=word32(model,0xa0);
    s->model_position=word32(model,0x220);s->fd_owner=word_pointer(model,0x108);
    s->table_begin=word_pointer(model,0x4d8);s->table_end=word_pointer(model,0x4e0);
    /* Native table begin/end proof: 0x176ecd1..0x176ece6. Native allocation
     * iterates 0xc68-byte descriptors and explicitly tests index48. Mapping
     * alone cannot establish that the logical table contains descriptor48. */
    if (!s->table_begin || s->table_end<s->table_begin) {s->error="layer-table-range";return;}
    uintptr_t bytes=s->table_end-s->table_begin;
    if (bytes%DESCRIPTOR_BYTES || bytes<LAYER_TABLE_BYTES ||
        LAYER_TABLE_BYTES>UINTPTR_MAX-s->table_begin) {s->error="layer-table-descriptor48";return;}
    s->table_descriptors=(size_t)(bytes/DESCRIPTOR_BYTES);s->table_extent_valid=1;
    if (!mapped_read(s->table_begin,LAYER_TABLE_BYTES)) {s->error="layer-table-host-span";return;}
    const unsigned char *l48=(const unsigned char *)(s->table_begin+L48_OFFSET);
    s->kind=l48[0];s->k_history=word_pointer(l48,0xb98);s->v_history=word_pointer(l48,0xba0);
    s->compressed_keys=word_pointer(l48,0x4f8);s->carry=word_pointer(l48,0x500);
    s->l48_fields_valid=1;s->entry_valid=1;
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
    uintptr_t return_address=(uintptr_t)__builtin_return_address(0);
    uintptr_t caller=return_address>=engine_base?return_address-engine_base:UINTPTR_MAX;
    if (head_depth) {
        if (active_sample) {active_sample->nested_forwards++;active_sample->error="nested-full-forward";}
        /* Nested native work must not be attributed to the enclosing sample. */
        return run_native(object,tokens,count,position,NULL,incoming_errno);
    }
    if (!atomic_load(&initialized) || atomic_load(&harvested) || pthread_mutex_lock(&trace_mutex))
        return run_native(object,tokens,count,position,NULL,incoming_errno);
    struct sample *s=NULL;
    if (armed_locked()) {
        forward_calls++;
        if (count!=1) excluded_count_calls++;
        else {
            count1_calls++;
            if (trace_count==TRACE_LIMIT) limit_skipped_calls++;
            else {
                s=&samples[trace_count++];in_flight++;
                observe_entry(s,object,count,position,caller);
                if (s->error) disable(s->error);
            }
        }
    }
    (void)pthread_mutex_unlock(&trace_mutex);
    int32_t result=run_native(object,tokens,count,position,s,incoming_errno);
    int result_errno=errno;
    if (s) {
        if (pthread_mutex_lock(&trace_mutex)) fatal("sample-completion-mutex");
        s->result=result;s->completed=1;
        if (s->error) disable(s->error);
        in_flight--;
        if (!in_flight) (void)pthread_cond_broadcast(&trace_idle);
        (void)pthread_mutex_unlock(&trace_mutex);
    }
    errno=result_errno;return result;
}
static int append_format(char *buffer,size_t capacity,size_t *used,const char *format,...)
    __attribute__((format(printf,4,5)));
static int append_format(char *buffer,size_t capacity,size_t *used,const char *format,...) {
    if (*used>=capacity) return 0;
    va_list arguments;va_start(arguments,format);
    int n=vsnprintf(buffer+*used,capacity-*used,format,arguments);
    va_end(arguments);
    if (n<0 || (size_t)n>=capacity-*used) return 0;
    *used+=(size_t)n;return 1;
}
static const char *rows_name(enum rows_state state) {
    switch (state) {
    case ROWS_DISABLED:return "disabled";
    case ROWS_NOT_SEEN:return "not-seen";
    case ROWS_CAPTURED:return "captured";
    case ROWS_ARGS_UNREADABLE:return "args-unreadable";
    case ROWS_OBJECT_UNREADABLE:return "object-unreadable";
    }
    return "invalid";
}
static int export_records(void) {
    size_t used=0;
    if (!append_format(export_buffer,sizeof export_buffer,&used,
        "{\"schema\":1,\"mode\":\"state8-v1\",\"instrumented\":true,\"timing_claim\":false,"
        "\"fd_rows_capture_enabled\":%s,\"calls\":%u,\"limit_reached\":%s,\"forward_calls\":%u,"
        "\"count1_calls\":%u,\"excluded_count_calls\":%u,\"limit_skipped_calls\":%u,\"samples\":[\n",
        capture_rows?"true":"false",trace_count,trace_count==TRACE_LIMIT?"true":"false",forward_calls,
        count1_calls,excluded_count_calls,limit_skipped_calls)) return 0;
    for (unsigned i=0;i<trace_count;i++) {
        const struct sample *s=&samples[i];char hex[FD_ROWS_BYTES*2U+1U];
        hex[0]=0;
        if (s->rows_state==ROWS_CAPTURED)
            for (unsigned j=0;j<FD_ROWS_BYTES;j++) snprintf(hex+j*2U,3,"%02x",(unsigned)s->rows[j]);
        if (!append_format(export_buffer,sizeof export_buffer,&used,
            "%s{\"index\":%u,\"count\":%d,\"position\":%d,\"caller_rva\":\"0x%" PRIxPTR
            "\",\"model\":\"0x%" PRIxPTR "\",\"model_fields_valid\":%s,\"entry_valid\":%s,"
            "\"completed\":%s,\"result\":%d,\"model_scatter_flag_a4\":%u,\"model_slot_a0\":%d,"
            "\"model_position_220\":%d,\"fd_owner_108_present\":%s,\"fd_owner_108\":\"0x%" PRIxPTR
            "\",\"layer_table_begin_4d8\":\"0x%" PRIxPTR "\",\"layer_table_end_4e0\":\"0x%" PRIxPTR
            "\",\"table_extent_valid\":%s,\"table_descriptors\":%zu,\"l48_fields_valid\":%s,\"l48_kind\":%u,"
            "\"l48_b98_present\":%s,\"l48_b98\":\"0x%" PRIxPTR "\",\"l48_ba0_present\":%s,\"l48_ba0\":\"0x%" PRIxPTR
            "\",\"l48_4f8_present\":%s,\"l48_4f8\":\"0x%" PRIxPTR "\",\"l48_500_present\":%s,\"l48_500\":\"0x%" PRIxPTR
            "\",\"kernel_launches\":%u,\"nondefault_stream_launches\":%u,\"scatter_launches\":%u,"
            "\"scatter_exact_callsite\":%u,\"scatter_other_callsite\":%u,\"fd_attention_launches\":%u,"
            "\"scatter_result_valid\":%s,\"scatter_result\":%d,\"fd_rows_state\":\"%s\",\"fd_rows_attempted\":%s,"
            "\"fd_rows_host_address\":\"0x%" PRIxPTR "\",\"fd_rows_bytes\":%u,\"fd_rows_hex\":\"%s\","
            "\"nested_forwards\":%u,\"error\":%s%s%s}\n",
            i?",":"",i,s->count,s->position,s->caller_rva,s->model,s->model_fields_valid?"true":"false",
            s->entry_valid?"true":"false",s->completed?"true":"false",s->result,s->scatter_flag,s->slot,
            s->model_position,s->fd_owner?"true":"false",s->fd_owner,s->table_begin,s->table_end,
            s->table_extent_valid?"true":"false",s->table_descriptors,s->l48_fields_valid?"true":"false",s->kind,
            s->k_history?"true":"false",s->k_history,s->v_history?"true":"false",s->v_history,
            s->compressed_keys?"true":"false",s->compressed_keys,s->carry?"true":"false",s->carry,
            s->kernels,s->nondefault_stream_launches,s->scatter_launches,s->scatter_exact_callsite,
            s->scatter_other_callsite,s->fd_attention_launches,s->scatter_result_valid?"true":"false",
            s->scatter_result,rows_name(s->rows_state),s->rows_attempted?"true":"false",s->rows_host_address,
            s->rows_state==ROWS_CAPTURED?FD_ROWS_BYTES:0U,hex,s->nested_forwards,
            s->error?"\"":"",s->error?s->error:"null",s->error?"\"":"")) return 0;
    }
    if (!append_format(export_buffer,sizeof export_buffer,&used,"]}\n")) return 0;
    struct stat now;
    if (fstat(records_fd,&now) || !S_ISREG(now.st_mode) || now.st_uid!=geteuid() || now.st_nlink!=1 ||
        now.st_size!=0 || now.st_dev!=records_identity.st_dev || now.st_ino!=records_identity.st_ino) return 0;
    int ok=append_bytes(records_fd,export_buffer,used);
    if (fsync(records_fd)) ok=0;
    if (close(records_fd)) ok=0;
    records_fd=-1;return ok;
}
static void harvest(int requested) {
    if (pthread_mutex_lock(&trace_mutex)) return;
    atomic_store(&harvested,1);
    if (requested<0) disable("harvest-content");
    /* Controller publishes harvest only after the request returns. Freeze new
     * reservations and wait for native host calls to return; no HIP wait. */
    while (in_flight) {
        if (pthread_cond_wait(&trace_idle,&trace_mutex)) {
            (void)pthread_mutex_unlock(&trace_mutex);return;
        }
    }
    if (!trace_count) disable("no-samples");
    if (!export_records()) disable("records-export");
    char complete[512];
    int n=snprintf(complete,sizeof complete,
        "{\"schema\":1,\"passed\":%s,\"calls\":%u,\"error\":%s%s%s,"
        "\"instrumented\":true,\"timing_claim\":false,\"observer_hip_copies\":0,\"observer_hip_syncs\":0}\n",
        trace_error?"false":"true",trace_count,trace_error?"\"":"",trace_error?trace_error:"null",trace_error?"\"":"");
    if (n<=0 || n>=(int)sizeof complete || !save_text("complete.json",complete,(size_t)n)) disable("complete-write");
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
        if (got<=0 || EVP_DigestUpdate(ctx,buffer,(size_t)got)!=1) fatal("hash-read");
        offset+=got;bytes-=(size_t)got;
    }
    if (EVP_DigestFinal_ex(ctx,digest,&length)!=1 || length!=sizeof digest) fatal("hash-final");
    EVP_MD_CTX_free(ctx);
    char hex[65];
    for (size_t i=0;i<sizeof digest;i++) snprintf(hex+i*2,3,"%02x",(unsigned)digest[i]);
    if (strcmp(hex,wanted)) fatal("hash-mismatch");
}
struct site {uintptr_t entry,wrapper,base;int found,wrapper_found,kernels_found;};
static int find_site(struct dl_phdr_info *info,size_t ignored,void *opaque) {
    (void)ignored;
    if (info->dlpi_name && *info->dlpi_name) return 0;
    struct site *site=opaque;
    if (FD_ATTN_ALT_RVA+sizeof(uintptr_t)>UINTPTR_MAX-info->dlpi_addr) fatal("base-overflow");
    for (size_t i=0;i<info->dlpi_phnum;i++) {
        const Elf64_Phdr *p=&info->dlpi_phdr[i];
        if (p->p_type==PT_LOAD && p->p_flags==(PF_R|PF_X) &&
            p->p_vaddr<=ENTRY_RVA && ENTRY_RVA+FUNCTION_BYTES<=p->p_vaddr+p->p_filesz &&
            p->p_offset+ENTRY_RVA-p->p_vaddr==(uint64_t)ENTRY_OFFSET) {
            site->entry=info->dlpi_addr+ENTRY_RVA;site->base=info->dlpi_addr;site->found++;
        }
        if (p->p_type==PT_LOAD && p->p_flags==(PF_R|PF_X) &&
            p->p_vaddr<=WRAPPER_RVA && WRAPPER_RVA+WRAPPER_BYTES<=p->p_vaddr+p->p_filesz &&
            p->p_offset+WRAPPER_RVA-p->p_vaddr==(uint64_t)WRAPPER_OFFSET) {
            site->wrapper=info->dlpi_addr+WRAPPER_RVA;site->wrapper_found++;
        }
        if (p->p_type==PT_LOAD && (p->p_flags&PF_R) && p->p_vaddr<=SCATTER_RVA &&
            FD_ATTN_ALT_RVA+sizeof(uintptr_t)<=p->p_vaddr+p->p_memsz) site->kernels_found++;
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
    if (entry+sizeof entry_signature>page+(uintptr_t)size) fatal("entry-page");
    if (!mapped_span(page,(size_t)size,"r-xp")) fatal("entry-page-rx");
    for (unsigned i=0;i<256;i++) {
        uintptr_t distance=(uintptr_t)(i/2+1)*0x200000;
        if ((i&1)?page<distance:distance>UINTPTR_MAX-page) continue;
        uintptr_t candidate=(i&1)?page-distance:page+distance;
        void *area=mmap((void *)candidate,(size_t)size,PROT_READ|PROT_WRITE,
            MAP_PRIVATE|MAP_ANONYMOUS|MAP_FIXED_NOREPLACE,-1,0);
        if (area==MAP_FAILED) {if (errno==EEXIST) continue;fatal("thunk-map");}
        if (area!=(void *)candidate) {
            if (munmap(area,(size_t)size)) fatal("thunk-unmap");
            fatal("fixed-noreplace");
        }
        thunk=area;break;
    }
    if (!thunk) fatal("thunk-exhausted");
    absolute_jump(thunk,target);
    /* push rbp; push r15; push r14 are complete position-independent bytes. */
    memcpy(thunk+64,entry_signature,5);absolute_jump(thunk+69,entry+5);
    if (mprotect(thunk,(size_t)size,PROT_READ|PROT_EXEC) ||
        !mapped_span((uintptr_t)thunk,(size_t)size,"r-xp")) fatal("thunk-rx");
    intptr_t relative=(intptr_t)((uintptr_t)thunk-(entry+5));
    if (relative<INT32_MIN || relative>INT32_MAX) fatal("jump-range");
    unsigned char jump[5]={0xe9};int32_t delta=(int32_t)relative;memcpy(jump+1,&delta,4);
    if (mprotect((void *)page,(size_t)size,PROT_READ|PROT_WRITE)) fatal("entry-rw");
    memcpy((void *)entry,jump,5);
    __builtin___clear_cache((char *)entry,(char *)entry+5);
    if (mprotect((void *)page,(size_t)size,PROT_READ|PROT_EXEC) ||
        !mapped_span(page,(size_t)size,"r-xp")) fatal("entry-rx");
    return (uintptr_t)(thunk+64);
}
static int serving_process(void) {
    int fd=open("/proc/self/cmdline",O_RDONLY|O_CLOEXEC);
    char command[4096];ssize_t bytes;
    if (fd<0) fatal("cmdline-open");
    do {bytes=read(fd,command,sizeof command);} while (bytes<0 && errno==EINTR);
    if (bytes<=0 || bytes>=(ssize_t)sizeof command || command[bytes-1] || close(fd)) fatal("cmdline-read");
    const char *argument=memchr(command,0,(size_t)bytes);
    if (!argument || argument+1>=command+bytes) return 0;
    /* Skip the preceding checkpoint-header helper with --resident-gib. */
    return !strcmp(argument+1,"--ck");
}
__attribute__((constructor)) static void install(void) {
    char name[4096];ssize_t n=readlink("/proc/self/exe",name,sizeof name-1);
    if (n<0 || n>=(ssize_t)sizeof name-1) fatal("executable-name");
    name[n]=0;const char *base=strrchr(name,'/');base=base?base+1:name;
    if (strcmp(base,"flash_serve") || !serving_process()) return;
    const char *mode=getenv("HALOGEN_MTP_STATE_TAP"),*directory=getenv("HALOGEN_MTP_STATE_TAP_DIR");
    const char *rows=getenv("HALOGEN_MTP_STATE_TAP_FD_ROWS");
    if (!mode || strcmp(mode,"state8-v1") || !directory ||
        strncmp(directory,trace_prefix,sizeof trace_prefix-1) ||
        strlen(directory)!=sizeof trace_prefix-1+32) fatal("configuration");
    if (rows && strcmp(rows,"none") && strcmp(rows,"copy160-v1")) fatal("fd-rows-configuration");
    capture_rows=rows && !strcmp(rows,"copy160-v1");
    for (const char *at=directory+sizeof trace_prefix-1;*at;at++)
        if (!((*at>='0' && *at<='9') || (*at>='a' && *at<='f'))) fatal("trace-run-id");
    int fd=open("/proc/self/exe",O_RDONLY|O_CLOEXEC);struct stat before,after;
    if (fd<0 || fstat(fd,&before) || !S_ISREG(before.st_mode) || before.st_size!=ENGINE_BYTES) fatal("executable-stat");
    Elf64_Ehdr eh;
    if (pread(fd,&eh,sizeof eh,0)!=(ssize_t)sizeof eh || memcmp(eh.e_ident,ELFMAG,SELFMAG) ||
        eh.e_ident[EI_CLASS]!=ELFCLASS64 || eh.e_ident[EI_DATA]!=ELFDATA2LSB ||
        eh.e_type!=ET_DYN || eh.e_machine!=EM_X86_64) fatal("elf-identity");
    verify_hash(fd,0,(size_t)before.st_size,ENGINE_SHA);
    verify_hash(fd,ENTRY_OFFSET,FUNCTION_BYTES,FUNCTION_SHA);
    verify_hash(fd,WRAPPER_OFFSET,WRAPPER_BYTES,WRAPPER_SHA);
    if (fstat(fd,&after) || before.st_dev!=after.st_dev || before.st_ino!=after.st_ino ||
        before.st_size!=after.st_size || before.st_mtim.tv_sec!=after.st_mtim.tv_sec ||
        before.st_mtim.tv_nsec!=after.st_mtim.tv_nsec || before.st_ctim.tv_sec!=after.st_ctim.tv_sec ||
        before.st_ctim.tv_nsec!=after.st_ctim.tv_nsec || close(fd)) fatal("executable-consistency");
    struct site site={0};
    if (dl_iterate_phdr(find_site,&site)!=1 || site.found!=1 || site.wrapper_found!=1 || site.kernels_found!=1 ||
        !mapped_span(site.entry,FUNCTION_BYTES,"r-xp") ||
        memcmp((const void *)site.entry,entry_signature,sizeof entry_signature)) fatal("entry-signature");
    if (!mapped_span(site.wrapper,WRAPPER_BYTES,"r-xp") ||
        memcmp((const void *)site.wrapper,wrapper_signature,sizeof wrapper_signature)) fatal("wrapper-signature");
    if (!mapped_read(site.base+SCATTER_RVA,(size_t)(FD_ATTN_ALT_RVA+sizeof(uintptr_t)-SCATTER_RVA)))
        fatal("kernel-identity-span");
    engine_base=site.base;
    int tmp_dir=open("/tmp",O_RDONLY|O_DIRECTORY|O_CLOEXEC|O_NOFOLLOW);
    struct stat directory_stat;
    if (tmp_dir<0 || fstat(tmp_dir,&directory_stat) || !S_ISDIR(directory_stat.st_mode)) fatal("tmp-directory");
    const char *trace_name=directory+sizeof "/tmp/"-1;
    if (mkdirat(tmp_dir,trace_name,0700)) fatal("state-mkdir");
    trace_dir=openat(tmp_dir,trace_name,O_RDONLY|O_DIRECTORY|O_CLOEXEC|O_NOFOLLOW);
    if (close(tmp_dir)) fatal("tmp-close");
    if (trace_dir<0 || fstat(trace_dir,&directory_stat) || !S_ISDIR(directory_stat.st_mode) ||
        directory_stat.st_uid!=geteuid() || (directory_stat.st_mode&0777)!=0700) fatal("state-directory");
    records_fd=openat(trace_dir,"records.json",O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC|O_NOFOLLOW,0600);
    if (records_fd<0 || fstat(records_fd,&records_identity) || !S_ISREG(records_identity.st_mode) ||
        records_identity.st_uid!=geteuid() || records_identity.st_nlink!=1 || records_identity.st_size)
        fatal("records-fd");
    original_head=(head_fn)install_hook(site.entry,(uintptr_t)tapped_head);
    /* Include the two later exclusive controller triggers in the total budget. */
    trace_bytes=sizeof arm_content+sizeof harvest_content-2;
    char header[2048];
    int header_n=snprintf(header,sizeof header,
        "{\"schema\":1,\"mode\":\"state8-v1\",\"engine_sha256\":\"%s\",\"engine_bytes\":26052768,"
        "\"function_sha256\":\"%s\",\"entry_rva\":\"0x17db310\",\"wrapper_sha256\":\"%s\","
        "\"wrapper_rva\":\"0x17dcde0\",\"wrapper_hooked\":false,\"limit\":8,\"selected_count\":1,"
        "\"fd_rows_capture_enabled\":%s,\"fd_rows_host_bytes\":160,\"scatter_identity_rva\":\"0x18d5338\","
        "\"scatter_return_rva\":\"0x17a0b70\",\"layer_descriptor_bytes\":3176,\"table_end_offset\":\"0x4e0\","
        "\"device_pointer_dereferences\":0,\"observer_hip_calls\":0,\"per_call_record_writes\":false,"
        "\"post_request_harvest_required\":true,\"instrumented\":true,\"timing_claim\":false,"
        "\"ownership_claim\":false,\"file_limit\":5,\"byte_limit\":65536}\n",
        ENGINE_SHA,FUNCTION_SHA,WRAPPER_SHA,capture_rows?"true":"false");
    if (header_n<=0 || header_n>=(int)sizeof header || !save_text("activation.json",header,(size_t)header_n))
        fatal("activation-write");
    if (pthread_create(&worker,NULL,harvest_worker,NULL) || pthread_detach(worker)) fatal("harvest-thread");
    atomic_store(&initialized,1);
}
