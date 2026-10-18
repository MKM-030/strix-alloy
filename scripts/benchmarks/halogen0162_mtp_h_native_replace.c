/* Offline-only source for a default-off H-only replacement consumer.
 * Root owns compilation, fresh serial engine epoch, bridge, Windows job and
 * qualification. Enable only HALOGEN_MTP_H_NATIVE=replace64-v1, explicit wireD,
 * inherited connected AF_UNIX HALOGEN_MTP_H_FD, HALOGEN_MTP_H_PEER_PID, and
 * nonzero lowercase hex HALOGEN_MTP_H_NONCE/EPOCH/MODEL_SHA256/GRAPH_SHA256.
 * HALOGEN_MTP_H_TIMEOUT_US is 1..200000 (default200000); the absolute deadline
 * starts before the input fence and ends after candidate output visibility.
 * Handshake has a separate absolute2s deadline before detours are installed.
 * One native discovery head proves the unchanged M1/M4 route and pins host
 * descriptor/device-pointer identity in memory; it consumes no candidate seq.
 * The following at most64 eligible heads replace exactly H before seed-add.
 * No request files, Python relay, payload loads or process creation in hot path.
 * Metadata /proc checks remain inside timing and are not speed-qualified.
 * Precommit failure poisons transport and invokes original H once. From the
 * first candidate-write attempt onward, any failure fail-stops; no rollback.
 * No compilation or hardware execution was performed by the source author.
 * Root build: gcc -O2 -Wall -Wextra -Werror -shared -fPIC
 * -fno-optimize-sibling-calls this.c -ldl -lcrypto -pthread -o new.so
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
#include <poll.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <time.h>
#include <unistd.h>
#include "halogen_mtp_h_wire.h"
#if !defined(__linux__) || !defined(__x86_64__)
#error Linux x86-64 only
#endif
#define ENGINE_BYTES ((off_t)26052768)
#define ENGINE_SHA HGNH_ENGINE_SHA
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
#define H_BYTES HGNH_H_BYTES
#define MAX_CALLS HGNH_MAX_CALLS
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
typedef int32_t (*head_fn)(void *,const int32_t *,int32_t,int32_t);
typedef void (*fc_fn)(void *,const uint16_t *,uint16_t *,int32_t,int32_t,int64_t);
typedef struct {unsigned x,y,z;} hip_dim3;
typedef int (*launch_fn)(const void *,hip_dim3,hip_dim3,void **,size_t,void *);
typedef int (*sync_fn)(void *);
typedef int (*copy_fn)(void *,const void *,size_t,int);
struct context {
    uintptr_t model,tokens,head_caller,e_input,e_output,h_input,h_output,seed;
    int32_t token,count,position,slot,outer_position,head_result,head_errno;
    unsigned sequence,e_calls,h_calls,phase,original_calls[2],launches[2],launch_ok[2];
    unsigned discovery,completed,wire_guard,captured,response_ready,commit_started,published;
    unsigned sync_attempts,sync_ok,copy_attempts,copy_ok;
    uint64_t started_ns,visible_ns;
    unsigned char e_descriptor[DESCRIPTOR_BYTES],h_descriptor[DESCRIPTOR_BYTES];
    const char *error,*outcome;
    struct hgnh_request request;
    struct hgnh_response response;
};
static struct context contexts[MAX_CALLS],discovery,baseline;
_Static_assert(sizeof contexts+sizeof discovery+sizeof baseline<3U*1024U*1024U,"bounded staging");
static struct hgnh_hello session;
static uint32_t process_pid;
static uint64_t process_starttime,timeout_ns=200000000ULL;
static unsigned baseline_ready,discovery_reserved,calls,in_flight,head_calls,excluded_calls,overlaps;
static int32_t last_position,last_outer_position;
static _Thread_local struct context *active;
static _Thread_local unsigned head_depth;
static head_fn original_head;
static fc_fn original_fc;
static launch_fn real_launch;
static sync_fn hip_sync;
static copy_fn hip_copy;
static uintptr_t engine_base;
static int transport_fd=-1,peer_pidfd=-1;
static pid_t peer_pid;
static struct stat transport_stat;
static unsigned output_exposed;
static _Atomic int initialized,disabled;
static pthread_mutex_t state_mutex=PTHREAD_MUTEX_INITIALIZER;
static pthread_once_t symbols_once=PTHREAD_ONCE_INIT;

static _Noreturn void fatal(const char *reason) {
    dprintf(STDERR_FILENO,"[mtp-h-native] fatal reason=%s errno=%d\n",reason,errno);
    _exit(79);
}
static void lock_state(void) {if (pthread_mutex_lock(&state_mutex)) fatal("state-lock");}
static void unlock_state(void) {if (pthread_mutex_unlock(&state_mutex)) fatal("state-unlock");}
static void reject(struct context *s,const char *reason) {
    if (s && !s->error) s->error=reason;
    atomic_store(&disabled,1);
}
static void poison(struct context *s,const char *reason) {
    reject(s,reason);
    /* shutdown invalidates the retained channel without an fd-reuse window. */
    if (transport_fd>=0) (void)shutdown(transport_fd,SHUT_RDWR);
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
    char *last=strrchr(end+1,')');if (!last || last[1]!=' ' || !last[2]) return 0;
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
static uint64_t now_ns(void) {
    struct timespec value;if (clock_gettime(CLOCK_MONOTONIC,&value)) return 0;
    return (uint64_t)value.tv_sec*1000000000ULL+(uint64_t)value.tv_nsec;
}
static int before(uint64_t deadline) {uint64_t now=now_ns();return now && now<deadline;}
static int transport_live(void) {
    struct stat current;struct ucred credentials;socklen_t bytes=sizeof credentials;
    struct pollfd peer={.fd=peer_pidfd,.events=POLLIN};
    int flags=transport_fd>=0?fcntl(transport_fd,F_GETFL):-1;
    return transport_fd>=0 && peer_pidfd>=0 && getppid()==peer_pid && flags>=0 && (flags&O_NONBLOCK) &&
        !fstat(transport_fd,&current) && S_ISSOCK(current.st_mode) &&
        current.st_dev==transport_stat.st_dev && current.st_ino==transport_stat.st_ino &&
        !getsockopt(transport_fd,SOL_SOCKET,SO_PEERCRED,&credentials,&bytes) &&
        bytes==sizeof credentials && credentials.pid==peer_pid && credentials.uid==geteuid() &&
        credentials.gid==getegid() && poll(&peer,1,0)==0;
}
static int wait_io(short events,uint64_t deadline) {
    for (;;) {
        uint64_t now=now_ns();if (!now || now>=deadline || atomic_load(&disabled) || !transport_live()) return 0;
        uint64_t remaining=deadline-now;
        struct timespec timeout={(time_t)(remaining/1000000000ULL),(long)(remaining%1000000000ULL)};
        struct pollfd descriptors[2]={{transport_fd,events,0},{peer_pidfd,POLLIN,0}};
        int ready=ppoll(descriptors,2,&timeout,NULL);
        if (ready<0 && errno==EINTR) continue;
        if (ready<=0 || descriptors[1].revents) return 0;
        if (descriptors[0].revents&events) return 1;
        if (descriptors[0].revents&(POLLERR|POLLHUP|POLLNVAL)) return 0;
    }
}
static int exact_io(void *data,size_t bytes,int writing,uint64_t deadline) {
    unsigned char *at=data;
    while (bytes) {
        if (!before(deadline) || atomic_load(&disabled) || !transport_live()) return 0;
        ssize_t n=writing?send(transport_fd,at,bytes,MSG_NOSIGNAL|MSG_DONTWAIT):
                          recv(transport_fd,at,bytes,MSG_DONTWAIT);
        if (n<0 && errno==EINTR) continue;
        if (n<0 && (errno==EAGAIN || errno==EWOULDBLOCK)) {
            if (!wait_io(writing?POLLOUT:POLLIN,deadline)) return 0;
            continue;
        }
        if (n<=0) return 0;
        at+=(size_t)n;bytes-=(size_t)n;
    }
    return before(deadline) && transport_live();
}
static int send_frame(uint32_t kind,uint64_t sequence,void *payload,size_t bytes,uint64_t deadline) {
    struct hgnh_frame frame={0};memcpy(frame.magic,HGNH_FRAME_MAGIC,8);
    frame.kind=kind;frame.payload_bytes=(uint32_t)bytes;frame.sequence=sequence;
    return digest_two(payload,bytes,NULL,0,frame.payload_sha256) &&
        exact_io(&frame,sizeof frame,1,deadline) && exact_io(payload,bytes,1,deadline);
}
static int receive_frame(uint32_t kind,uint64_t sequence,void *payload,size_t bytes,uint64_t deadline) {
    struct hgnh_frame frame;unsigned char digest[32];
    return exact_io(&frame,sizeof frame,0,deadline) && !memcmp(frame.magic,HGNH_FRAME_MAGIC,8) &&
        frame.kind==kind && frame.payload_bytes==bytes && frame.sequence==sequence &&
        exact_io(payload,bytes,0,deadline) && digest_two(payload,bytes,NULL,0,digest) &&
        !memcmp(digest,frame.payload_sha256,32) && before(deadline) && transport_live();
}
static int no_unsolicited_data(void) {
    unsigned char byte;ssize_t n=recv(transport_fd,&byte,1,MSG_DONTWAIT|MSG_PEEK);
    return n<0 && (errno==EAGAIN || errno==EWOULDBLOCK);
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
static int pair_spans(const struct context *s) {
    uintptr_t p[4]={s->e_input,s->h_input,s->e_output,s->h_output};
    size_t n[4]={E_BYTES,H_BYTES,E_BYTES,H_BYTES};
    for (unsigned i=0;i<4;i++) {
        if (!disjoint(p[i],n[i],s->seed,H_BYTES)) return 0;
        for (unsigned j=0;j<i;j++) if (!disjoint(p[i],n[i],p[j],n[j])) return 0;
    }
    return 1;
}
static int baseline_live(uintptr_t model) {
    return baseline_ready && model==baseline.model && same_process() && mapped_span(model,MODEL_BYTES,NULL) &&
        ((const unsigned char *)model)[0x900]==1 && int32_at((void *)model,0xa0)==baseline.slot &&
        !memcmp((void *)(model+0x908),baseline.e_descriptor,DESCRIPTOR_BYTES) &&
        !memcmp((void *)(model+0x980),baseline.h_descriptor,DESCRIPTOR_BYTES) &&
        pointer_at((void *)model,0x6c8)==baseline.e_input && pointer_at((void *)model,0xb00)==baseline.e_output &&
        pointer_at((void *)model,0x6d0)==baseline.seed &&
        pointer_at((void *)engine_base,H_INPUT_RVA)==baseline.h_input &&
        pointer_at((void *)engine_base,H_OUTPUT_RVA)==baseline.h_output && wire_D() &&
        *(const unsigned char *)(engine_base+WIRE_GUARD_RVA)==baseline.wire_guard;
}
static int stable(const struct context *s,int paired) {
    if (atomic_load(&disabled) || !transport_live() || (!s->discovery && !baseline_live(s->model)) ||
        !stable_native(s,paired)) return 0;
    lock_state();int serial=in_flight==1;unlock_state();return serial;
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
    s->wire_guard=*(const unsigned char *)(engine_base+WIRE_GUARD_RVA);
    memcpy(s->e_descriptor,(const unsigned char *)model+0x908,DESCRIPTOR_BYTES);
    memcpy(s->h_descriptor,(const unsigned char *)model+0x980,DESCRIPTOR_BYTES);
    if (!normal_descriptor(s->e_descriptor) || !normal_descriptor(s->h_descriptor)) reject(s,"head-descriptor-contract");
}
static int after_head(const struct context *s) {
    /* Native installs position after seed-add; permit that field to advance. */
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
static void resolve_symbols(void) {
    real_launch=(launch_fn)dlsym(RTLD_NEXT,"hipLaunchKernel");
    hip_sync=(sync_fn)dlsym(RTLD_NEXT,"hipStreamSynchronize");
    hip_copy=(copy_fn)dlsym(RTLD_NEXT,"hipMemcpy");
}
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
    s->sync_attempts++;int result=hip_sync(NULL);if (!result) s->sync_ok++;return result==0;
}
static int checked_copy(struct context *s,void *to,const void *from,size_t bytes,int kind) {
    s->copy_attempts++;int result=hip_copy(to,from,bytes,kind);if (!result) s->copy_ok++;return result==0;
}
static int replace_hidden(struct context *s) {
    /* All failures returning zero precede any candidate write attempt. */
    s->outcome="native_precommit_fallback";s->started_ns=now_ns();
    if (!s->started_ns || timeout_ns>UINT64_MAX-s->started_ns) goto precommit;
    uint64_t deadline=s->started_ns+timeout_ns;
    if (s->error || !hip_sync || !hip_copy || s->e_calls!=1 || s->h_calls!=1 ||
        s->original_calls[0]!=1 || s->original_calls[1] || s->launches[0]!=1 || s->launch_ok[0]!=1 ||
        s->launches[1] || !pair_spans(s) || !stable(s,1) || !before(deadline) ||
        !checked_sync(s) || !stable(s,1) || !before(deadline) ||
        !checked_copy(s,s->request.body,(void *)s->h_input,H_BYTES,2) || !stable(s,1) ||
        !before(deadline) || !finite_bf16(s->request.body,H_BYTES)) goto precommit;
    s->captured=1;struct hgnh_header *header=&s->request.header;
    memcpy(header->magic,HGNH_REQUEST_MAGIC,8);header->version=HGNH_VERSION;header->body_bytes=H_BYTES;
    header->sequence=(int32_t)s->sequence;header->position=s->position;header->slot=s->slot;
    header->count=1;header->token=s->token;header->outer_position=s->outer_position;header->wire=HGNH_WIRE_D;
    memcpy(header->nonce,session.nonce,16);memcpy(header->epoch,session.epoch,16);
    header->model=s->model;header->process_id=process_pid;
    memcpy(header->model_binding,session.model_binding,32);memcpy(header->graph_binding,session.graph_binding,32);
    if (!digest_two(s->request.body,H_BYTES,NULL,0,header->input_binding) ||
        !digest_two(header,HGNH_REQUEST_BINDING_OFFSET,s->request.body,H_BYTES,header->request_binding) ||
        !stable(s,1) || !no_unsolicited_data() ||
        !send_frame(HGNH_REQUEST,s->sequence,&s->request,sizeof s->request,deadline) ||
        !receive_frame(HGNH_RESPONSE,s->sequence,&s->response,sizeof s->response,deadline)) goto precommit;
    struct hgnh_header expected=*header;memcpy(expected.magic,HGNH_RESPONSE_MAGIC,8);
    unsigned char digest[32];
    if (memcmp(&s->response.header,&expected,sizeof expected) ||
        !digest_two(&s->response,offsetof(struct hgnh_response,digest),NULL,0,digest) ||
        memcmp(digest,s->response.digest,32) || !finite_bf16(s->response.body,H_BYTES) ||
        !stable(s,1) || !no_unsolicited_data() || !before(deadline)) goto precommit;
    s->response_ready=1;
    lock_state();
    int admissible=in_flight==1 && !output_exposed && !atomic_load(&disabled) &&
        baseline_live(s->model) && stable_native(s,1) && transport_live() && before(deadline);
    if (admissible) {s->commit_started=1;output_exposed=1;}
    unlock_state();
    if (!admissible) goto precommit;
    /* hipMemcpy can write partially even when it fails. The commit boundary is
     * before calling it, so neither copy nor later fence failure may fallback. */
    if (!checked_copy(s,(void *)s->h_output,s->response.body,H_BYTES,1)) fatal("candidate-copy-after-commit");
    if (!stable(s,1) || !checked_sync(s) || !stable(s,1) || !before(deadline))
        fatal("candidate-visibility-or-identity-after-commit");
    s->visible_ns=now_ns();
    if (!s->visible_ns || s->visible_ns<s->started_ns || s->visible_ns>=deadline) fatal("candidate-clock-after-commit");
    s->published=1;s->outcome="candidate_h_published";return 1;
precommit:
    poison(s,"hidden-precommit-capture-transport-or-identity");return 0;
}
__attribute__((noinline)) static void replacement_fc(void *descriptor,const uint16_t *input,uint16_t *output,
    int32_t n,int32_t m,int64_t k) {
    int incoming_errno=errno;uintptr_t address=(uintptr_t)__builtin_return_address(0);
    uintptr_t caller=address>=engine_base?address-engine_base:UINTPTR_MAX;
    struct context *s=active;unsigned phase=0;
    if (s && (caller==E_RETURN_RVA || caller==H_RETURN_RVA)) {
        if (caller==E_RETURN_RVA) {
            s->e_calls++;s->e_input=(uintptr_t)input;s->e_output=(uintptr_t)output;
            if (s->e_calls!=1 || s->h_calls || descriptor!=(void *)(s->model+0x908) ||
                n!=2560 || m!=1 || k!=2560 || !normal_descriptor(s->e_descriptor) ||
                !disjoint(s->e_input,E_BYTES,s->e_output,E_BYTES) || !stable(s,0)) reject(s,"embedding-fc-contract");
            phase=1;
        } else {
            s->h_calls++;s->h_input=(uintptr_t)input;s->h_output=(uintptr_t)output;
            if (s->e_calls!=1 || s->h_calls!=1 || descriptor!=(void *)(s->model+0x980) ||
                n!=2560 || m!=4 || k!=2560 || !normal_descriptor(s->h_descriptor) ||
                !pair_spans(s) || !stable(s,1)) reject(s,"hidden-fc-contract");
            phase=2;
            if (!s->discovery && !s->error && replace_hidden(s)) {
                /* Exactly this H dispatcher call is skipped; E already ran. */
                errno=incoming_errno;return;
            }
        }
    }
    if (s && s->commit_started && phase) fatal("original-fc-after-candidate-commit");
    unsigned saved_phase=s?s->phase:0;if (s) {s->phase=phase;if (phase) s->original_calls[phase-1]++;}
    errno=incoming_errno;original_fc(descriptor,input,output,n,m,k);
    int result_errno=errno;if (s) s->phase=saved_phase;
    if (phase && (s->launches[phase-1]!=1 || s->launch_ok[phase-1]!=1 ||
        !stable_native(s,phase==2))) reject(s,"original-fc-completion");
    errno=result_errno;
}
__attribute__((noinline)) static int32_t replacement_head(void *model,const int32_t *tokens,int32_t count,int32_t position) {
    int incoming_errno=errno;uintptr_t address=(uintptr_t)__builtin_return_address(0);
    uintptr_t caller=address>=engine_base?address-engine_base:UINTPTR_MAX;
    lock_state();head_calls++;if (count!=1) excluded_calls++;
    if (in_flight || head_depth) {
        overlaps++;atomic_store(&disabled,1);
        if (output_exposed) fatal("full-head-overlap-after-commit");
    }
    in_flight++;struct context *s=NULL;
    if (atomic_load(&initialized) && !atomic_load(&disabled)) {
        if (count!=1) {
            if (baseline_ready) reject(NULL,"epoch-excluded-head");
        } else if (!transport_live() || !valid_head_entry(model,tokens,count,position,caller)) reject(NULL,"head-entry-identity");
        else if (baseline_ready) {
            if (!baseline_live((uintptr_t)model) || position<last_position ||
                int32_at(model,0x220)<last_outer_position) reject(NULL,"epoch-head-identity");
            else if (calls<MAX_CALLS) {
                s=&contexts[calls];s->sequence=calls++; /* Burn before any request/work. */
                context_entry(s,model,tokens,count,position,caller);last_position=position;
            }
        } else if (!discovery_reserved) {
            discovery_reserved=1;s=&discovery;s->discovery=1;
            context_entry(s,model,tokens,count,position,caller);
        } else reject(NULL,"missing-native-discovery");
    }
    unlock_state();struct context *saved=active;active=s;head_depth++;
    errno=incoming_errno;int32_t result=original_head(model,tokens,count,position);int result_errno=errno;
    head_depth--;active=saved;lock_state();
    if (s) {
        s->head_result=result;s->head_errno=result_errno;s->completed=1;
        int exact=s->e_calls==1 && s->h_calls==1 && s->original_calls[0]==1 &&
            s->original_calls[1]==(s->published?0U:1U) && s->launches[0]==1 && s->launch_ok[0]==1 &&
            s->launches[1]==(s->published?0U:1U) && s->launch_ok[1]==(s->published?0U:1U);
        int valid=exact && result>=0 && after_head(s) && in_flight==1;
        if (s->commit_started && (!s->published || !valid || s->error || atomic_load(&disabled) ||
            !transport_live() || !baseline_live(s->model))) fatal("owned-head-failure-after-commit");
        if (!valid) reject(s,"head-count-result-or-identity");
        if (s->discovery) {
            if (valid && !s->error && !atomic_load(&disabled) && transport_live()) {
                baseline=*s;baseline_ready=1;last_position=s->position;
                last_outer_position=int32_at((void *)s->model,0x220);s->outcome="native_discovery_pinned";
            } else {s->outcome="native_discovery_rejected";poison(s,"discovery-native-route");}
        } else if (!atomic_load(&disabled)) last_outer_position=int32_at((void *)s->model,0x220);
        output_exposed=0;
    }
    if (!in_flight) fatal("head-in-flight-underflow");
    in_flight--;unlock_state();errno=result_errno;return result;
}
/* Reporting is terminal-only, outside every FC/head window. No record/fsync
 * publication participates in the request path or the component bracket. */
static void report_context(const struct context *s) {
    char input_hash[65]="",request_hash[65]="",candidate_hash[65]="";
    if (s->captured) {
        for (unsigned i=0;i<32;i++) {
            snprintf(input_hash+2*i,3,"%02x",(unsigned)s->request.header.input_binding[i]);
            snprintf(request_hash+2*i,3,"%02x",(unsigned)s->request.header.request_binding[i]);
        }
    }
    if (s->response_ready && !buffer_hash(s->response.body,H_BYTES,candidate_hash)) fatal("terminal-candidate-hash");
    dprintf(STDERR_FILENO,"{\"schema\":1,\"mode\":\"replace64-v1\",\"sequence\":%u,\"discovery\":%s,"
        "\"outcome\":\"%s\",\"error\":\"%s\",\"completed\":%s,\"head_result\":%d,"
        "\"process_id\":%u,\"model\":\"0x%" PRIxPTR "\",\"position\":%d,\"outer_position\":%d,\"slot\":%d,\"token\":%d,"
        "\"input_binding\":\"%s\",\"request_binding\":\"%s\",\"candidate_sha256\":\"%s\","
        "\"original_e_calls\":%u,\"original_h_calls\":%u,\"e_launches\":%u,\"h_launches\":%u,"
        "\"captured\":%s,\"response_ready\":%s,\"commit_started\":%s,\"published\":%s,"
        "\"started_ns\":%" PRIu64 ",\"visible_ns\":%" PRIu64 ",\"readiness_to_visibility_ns\":%" PRIu64 ","
        "\"sync_attempts\":%u,\"sync_ok\":%u,\"copy_attempts\":%u,\"copy_ok\":%u,"
        "\"transport_qualified\":false,\"arithmetic_qualified\":false,\"npu_qualified\":false,"
        "\"full_head_qualified\":false,\"acceptance_qualified\":false,\"performance_qualified\":false}\n",
        s->sequence,s->discovery?"true":"false",s->outcome?s->outcome:"native_fallback",
        s->error?s->error:"",s->completed?"true":"false",s->head_result,
        process_pid,s->model,s->position,s->outer_position,s->slot,s->token,input_hash,request_hash,candidate_hash,
        s->original_calls[0],s->original_calls[1],
        s->launches[0],s->launches[1],s->captured?"true":"false",s->response_ready?"true":"false",
        s->commit_started?"true":"false",s->published?"true":"false",s->started_ns,s->visible_ns,
        s->published?s->visible_ns-s->started_ns:0,s->sync_attempts,s->sync_ok,s->copy_attempts,s->copy_ok);
}
__attribute__((destructor)) static void finish(void) {
    if (!atomic_load(&initialized)) return;
    lock_state();if (in_flight || output_exposed) fatal("teardown-during-owned-head");
    if (discovery_reserved) report_context(&discovery);
    for (unsigned i=0;i<calls;i++) report_context(&contexts[i]);
    dprintf(STDERR_FILENO,"[mtp-h-native] terminal calls=%u heads=%u excluded=%u overlaps=%u disabled=%d\n",
        calls,head_calls,excluded_calls,overlaps,atomic_load(&disabled));
    if (transport_fd>=0) {if (close(transport_fd)) fatal("transport-close");transport_fd=-1;}
    if (peer_pidfd>=0) {if (close(peer_pidfd)) fatal("peer-pidfd-close");peer_pidfd=-1;}
    unlock_state();
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
    /* Complete non-RIP-relative push rbp;push r15;push r14 only. */
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
static int hex_bytes(const char *text,unsigned char *out,size_t bytes) {
    if (!text || strlen(text)!=2*bytes) return 0;
    for (size_t i=0;i<2*bytes;i++) {
        int value=text[i]>='0' && text[i]<='9'?text[i]-'0':text[i]>='a' && text[i]<='f'?text[i]-'a'+10:-1;
        if (value<0) return 0;
        if (!(i&1)) out[i/2]=(unsigned char)(value<<4);else out[i/2]|=(unsigned char)value;
    }
    return nonzero(out,bytes);
}
static int decimal(const char *text,unsigned long minimum,unsigned long maximum,unsigned long *value) {
    if (!text || !*text) return 0;
    for (const char *at=text;*at;at++) if (*at<'0' || *at>'9') return 0;
    char *end=NULL;errno=0;unsigned long parsed=strtoul(text,&end,10);
    if (errno || !end || *end || parsed<minimum || parsed>maximum) return 0;
    *value=parsed;return 1;
}
static void establish_transport(void) {
    unsigned long inherited,peer,timeout=200000;
    const char *budget=getenv("HALOGEN_MTP_H_TIMEOUT_US");
    if (!decimal(getenv("HALOGEN_MTP_H_FD"),3,INT_MAX,&inherited) ||
        !decimal(getenv("HALOGEN_MTP_H_PEER_PID"),1,INT_MAX,&peer) ||
        (budget && !decimal(budget,1,200000,&timeout))) fatal("transport-configuration");
    timeout_ns=(uint64_t)timeout*1000ULL;peer_pid=(pid_t)peer;
    if (getppid()!=peer_pid) fatal("transport-owned-parent");
    transport_fd=fcntl((int)inherited,F_DUPFD_CLOEXEC,3);
    if (transport_fd<0 || close((int)inherited)) fatal("transport-retain-fd");
    int domain=0,type=0;socklen_t bytes=sizeof domain;
    if (getsockopt(transport_fd,SOL_SOCKET,SO_DOMAIN,&domain,&bytes) || bytes!=sizeof domain || domain!=AF_UNIX)
        fatal("transport-domain");
    bytes=sizeof type;
    if (getsockopt(transport_fd,SOL_SOCKET,SO_TYPE,&type,&bytes) || bytes!=sizeof type || type!=SOCK_STREAM ||
        fstat(transport_fd,&transport_stat) || !S_ISSOCK(transport_stat.st_mode)) fatal("transport-type");
    int flags=fcntl(transport_fd,F_GETFL);
    if (flags<0 || fcntl(transport_fd,F_SETFL,flags|O_NONBLOCK)) fatal("transport-nonblocking");
    peer_pidfd=(int)syscall(SYS_pidfd_open,peer_pid,0);
    if (peer_pidfd<0 || !transport_live() || !no_unsolicited_data()) fatal("transport-peer-identity");
    memcpy(session.magic,HGNH_HELLO_MAGIC,8);session.version=HGNH_VERSION;
    session.max_calls=MAX_CALLS;session.process_id=process_pid;session.h_bytes=H_BYTES;session.wire=HGNH_WIRE_D;
    if (!hex_bytes(getenv("HALOGEN_MTP_H_NONCE"),session.nonce,16) ||
        !hex_bytes(getenv("HALOGEN_MTP_H_EPOCH"),session.epoch,16) ||
        !hex_bytes(getenv("HALOGEN_MTP_H_MODEL_SHA256"),session.model_binding,32) ||
        !hex_bytes(getenv("HALOGEN_MTP_H_GRAPH_SHA256"),session.graph_binding,32) ||
        !hex_bytes(ENGINE_SHA,session.engine_sha256,32)) fatal("session-bindings");
    uint64_t started=now_ns();if (!started || UINT64_MAX-started<2000000000ULL) fatal("handshake-clock");
    uint64_t deadline=started+2000000000ULL;struct hgnh_hello ready,expected=session;
    memcpy(expected.magic,HGNH_READY_MAGIC,8);
    if (!send_frame(HGNH_HELLO,0,&session,sizeof session,deadline) ||
        !receive_frame(HGNH_READY,0,&ready,sizeof ready,deadline) || memcmp(&ready,&expected,sizeof ready) ||
        !no_unsolicited_data() || !transport_live()) fatal("owned-session-handshake");
}
__attribute__((constructor)) static void install(void) {
    const char *mode=getenv("HALOGEN_MTP_H_NATIVE");if (!mode) return;
    if (strcmp(mode,"replace64-v1")) fatal("replacement-mode");
    char executable[4096];ssize_t length=readlink("/proc/self/exe",executable,sizeof executable-1);
    if (length<0 || length>=(ssize_t)sizeof executable-1) fatal("executable-name");
    executable[length]=0;const char *base=strrchr(executable,'/');base=base?base+1:executable;
    if (strcmp(base,"flash_serve") || !serving_process()) return;
    const char *wire=getenv("HALOGEN_MTP_WIRE"),*wave=getenv("HALOGEN_LQ8_WAVE");
    if (!wire || strcmp(wire,"D") || (wave && strcmp(wave,"1"))) fatal("replacement-wire-configuration");
    int fd=open("/proc/self/exe",O_RDONLY|O_CLOEXEC);struct stat initial,after;Elf64_Ehdr elf;
    if (fd<0 || fstat(fd,&initial) || !S_ISREG(initial.st_mode) || initial.st_size!=ENGINE_BYTES ||
        pread(fd,&elf,sizeof elf,0)!=(ssize_t)sizeof elf || memcmp(elf.e_ident,ELFMAG,SELFMAG) ||
        elf.e_ident[EI_CLASS]!=ELFCLASS64 || elf.e_ident[EI_DATA]!=ELFDATA2LSB ||
        elf.e_type!=ET_DYN || elf.e_machine!=EM_X86_64) fatal("elf-identity");
    verify_hash(fd,0,(size_t)initial.st_size,ENGINE_SHA);verify_hash(fd,HEAD_OFFSET,HEAD_BYTES,HEAD_SHA);
    verify_hash(fd,FC_OFFSET,FC_BYTES,FC_SHA);
    if (fstat(fd,&after) || !same_stat(&initial,&after) || close(fd)) fatal("executable-consistency");
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
    if (pthread_once(&symbols_once,resolve_symbols) || !real_launch || !hip_sync || !hip_copy) fatal("hip-symbols");
    establish_transport();
    struct detour head=prepare_detour(sites.head,(uintptr_t)replacement_head,head_signature);
    struct detour fc=prepare_detour(sites.fc,(uintptr_t)replacement_fc,fc_signature);
    original_head=(head_fn)head.trampoline;original_fc=(fc_fn)fc.trampoline;
    /* Fresh process before serving; partial installation terminates. */
    patch_detour(&head);patch_detour(&fc);atomic_store(&initialized,1);
    dprintf(STDERR_FILENO,"[mtp-h-native] installed default_off=true discovery_heads=1 limit=%u "
        "request_bytes=%u response_bytes=%u timeout_ns=%" PRIu64 " qualification=false\n",
        MAX_CALLS,HGNH_REQUEST_BYTES,HGNH_RESPONSE_BYTES,timeout_ns);
}
