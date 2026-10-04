/* Source-only research preparation; root alone builds/launches this shim.
 * Default: no detour. Enable HALOGEN_MTP_QUALITY=quality4-v1 and a fresh
 * HALOGEN_MTP_QUALITY_DIR=/tmp/alloy-mtp-quality-<32 lowercase hex digits>.
 * Original MLP executes once. Only a validated explicit complete-MLP response
 * can replace its output; this is a quality harness, never a speed result.
 * gcc -O2 -Wall -Wextra -Werror -shared -fPIC -fno-optimize-sibling-calls
 *     halogen0162_mtp_quality_publish.c -ldl -lcrypto -pthread -o <new-owned.so>
 */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <elf.h>
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <limits.h>
#include <link.h>
#include <math.h>
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
#define ENGINE_SHA "ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b"
#define FUNCTION_SHA "e318b4639c8bd2e57d66b12b823fcafc1f5c5a5136e3651c06e2bac54e46c717"
#define ENTRY_RVA ((uintptr_t)0x17bd410)
#define ENTRY_OFFSET ((off_t)0x17bc410)
#define FUNCTION_BYTES ((size_t)(0x17ca056 - 0x17bd410))
#define COEFF_RVA ((uintptr_t)0x18db3e0)
#define IDS_RVA ((uintptr_t)0x18db400)
#define TENSOR_BYTES 5120U
#define BODY_BYTES 10320U
#define MAX_CALLS 4U
#define WAIT_NS 200000000ULL
#ifndef RENAME_NOREPLACE
#define RENAME_NOREPLACE 1U
#endif
static const char directory_prefix[] = "/tmp/alloy-mtp-quality-";
static const char arm_content[] = "quality4-v1-ready\n";
static const unsigned char entry_signature[32] = {
    0x55,0x41,0x57,0x41,0x56,0x41,0x55,0x41,0x54,0x53,0x48,0x81,0xec,0x58,0x0f,0,
    0,0x48,0x89,0x94,0x24,0xf0,0,0,0,0x89,0x94,0x24,0xa4,0,0,0
};
struct header {
    unsigned char magic[8];
    uint32_t version, body_bytes;
    int32_t sequence, position, slot;
    uint32_t reserved;
    unsigned char nonce[16], binding[32];
};
_Static_assert(sizeof(struct header)==80 && offsetof(struct header,binding)==48,
               "packet layout differs from the Python wire contract");
struct request { struct header header; unsigned char body[BODY_BYTES]; };
struct response {
    struct header header;
    unsigned char output[TENSOR_BYTES], digest[32];
};
_Static_assert(sizeof(struct request)==10400 && sizeof(struct response)==5232,
               "packet bounds changed");
typedef void (*mlp_fn)(void *,int32_t,int32_t);
typedef int (*sync_fn)(void);
typedef int (*copy_fn)(void *,const void *,size_t,int);
static mlp_fn original_mlp;
static sync_fn hip_sync;
static copy_fn hip_copy;
static uintptr_t engine_base;
static unsigned char run_nonce[16];
static int directory_fd=-1, log_fd=-1;
static unsigned calls;
static atomic_int disabled;
static pthread_mutex_t quality_mutex=PTHREAD_MUTEX_INITIALIZER;

static _Noreturn void fatal(const char *reason) {
    dprintf(STDERR_FILENO,"[mtp-quality] fatal reason=%s errno=%d\n",reason,errno);
    _exit(79);
}
static uint64_t word64(const void *object,size_t offset) {
    uint64_t value;memcpy(&value,(const unsigned char *)object+offset,sizeof value);return value;
}
static int32_t word32(const void *object,size_t offset) {
    int32_t value;memcpy(&value,(const unsigned char *)object+offset,sizeof value);return value;
}
static int mapped_span(uintptr_t address,size_t bytes,const char *wanted) {
    if (!address || !bytes || bytes>UINTPTR_MAX-address) return 0;
    FILE *file=fopen("/proc/self/maps","re");
    if (!file) return 0;
    char line[4096],permissions[5];unsigned long low,high;int found=0;
    while (fgets(line,sizeof line,file)) {
        if (sscanf(line,"%lx-%lx %4s",&low,&high,permissions)!=3) continue;
        if (address>=low && address+bytes<=high &&
            (wanted?!strcmp(permissions,wanted):permissions[0]=='r')) {found=1;break;}
    }
    int bad=ferror(file);
    if (fclose(file)) bad=1;
    return bad?0:found;
}
static int span(uintptr_t pointer,size_t bytes) {
    return pointer && bytes<=UINTPTR_MAX-pointer;
}
static int disjoint(uintptr_t a,size_t na,uintptr_t b,size_t nb) {
    return span(a,na) && span(b,nb) && (a+na<=b || b+nb<=a);
}
static int digest_two(const void *a,size_t na,const void *b,size_t nb,unsigned char digest[32]) {
    EVP_MD_CTX *ctx=EVP_MD_CTX_new();unsigned size=0;
    if (!ctx) return 0;
    int ok=EVP_DigestInit_ex(ctx,EVP_sha256(),NULL)==1 &&
        EVP_DigestUpdate(ctx,a,na)==1 && EVP_DigestUpdate(ctx,b,nb)==1 &&
        EVP_DigestFinal_ex(ctx,digest,&size)==1 && size==32;
    EVP_MD_CTX_free(ctx);return ok;
}
static int finite_bf16(const unsigned char *bytes) {
    for (unsigned i=0;i<TENSOR_BYTES;i+=2) {
        uint16_t bits;memcpy(&bits,bytes+i,2);if ((bits&0x7f80)==0x7f80) return 0;
    }
    return 1;
}
static int valid_routes(const unsigned char *body) {
    int32_t ids[10];float coefficients[10];double sum=0;
    memcpy(ids,body+TENSOR_BYTES,sizeof ids);
    memcpy(coefficients,body+TENSOR_BYTES+sizeof ids,sizeof coefficients);
    for (unsigned i=0;i<10;i++) {
        if (ids[i]<0 || ids[i]>=512 || !isfinite(coefficients[i]) || coefficients[i]<0) return 0;
        for (unsigned j=0;j<i;j++) if (ids[i]==ids[j]) return 0;
        sum+=coefficients[i];
    }
    return sum>0;
}
static int write_all(int fd,const void *data,size_t bytes) {
    const unsigned char *at=data;
    while (bytes) {
        ssize_t n=write(fd,at,bytes);
        if (n<0 && errno==EINTR) continue;
        if (n<=0) return 0;
        at+=n;bytes-=(size_t)n;
    }
    return 1;
}
/* Exact regular files; a hard-link response still being published is pending. */
static int read_exact_file(const char *name,void *data,size_t bytes,int pending_link) {
    int fd=openat(directory_fd,name,O_RDONLY|O_CLOEXEC|O_NOFOLLOW);
    if (fd<0) return errno==ENOENT?0:-1;
    struct stat before,after;int ok=!fstat(fd,&before) && S_ISREG(before.st_mode) &&
        before.st_size==(off_t)bytes && before.st_uid==geteuid();
    if (ok && pending_link && before.st_nlink==2) {
        return close(fd)?-1:0;
    }
    ok=ok && before.st_nlink==1;
    size_t done=0;
    while (ok && done<bytes) {
        ssize_t n=pread(fd,(unsigned char *)data+done,bytes-done,(off_t)done);
        if (n<0 && errno==EINTR) continue;
        if (n<=0) {ok=0;break;}done+=(size_t)n;
    }
    ok=ok && !fstat(fd,&after) && before.st_dev==after.st_dev && before.st_ino==after.st_ino &&
        before.st_size==after.st_size && before.st_mtim.tv_sec==after.st_mtim.tv_sec &&
        before.st_mtim.tv_nsec==after.st_mtim.tv_nsec && before.st_ctim.tv_sec==after.st_ctim.tv_sec &&
        before.st_ctim.tv_nsec==after.st_ctim.tv_nsec && after.st_nlink==1;
    if (close(fd)) ok=0;
    return ok?1:-1;
}
static void log_result(unsigned sequence,const char *outcome,const unsigned char binding[32]) {
    char hex[65];for (unsigned i=0;i<32;i++) snprintf(hex+i*2,3,"%02x",binding?binding[i]:0);
    char line[256];int n=snprintf(line,sizeof line,
        "{\"sequence\":%u,\"outcome\":\"%s\",\"request_sha256\":\"%s\"}\n",sequence,outcome,hex);
    if (n<=0 || n>=(int)sizeof line || !write_all(log_fd,line,(size_t)n)) atomic_store(&disabled,1);
}
static int publish_request(unsigned sequence,const struct request *request) {
    char pending[40],name[40];
    snprintf(pending,sizeof pending,"%03u-request.partial",sequence);
    snprintf(name,sizeof name,"%03u-request.bin",sequence);
    int fd=openat(directory_fd,pending,O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC|O_NOFOLLOW,0600);
    if (fd<0) return 0;
    int ok=write_all(fd,request,sizeof *request) && !fsync(fd);
    if (close(fd)) ok=0;
    /* Atomic single-link publication; never replace an existing final file. */
    if (ok && syscall(SYS_renameat2,directory_fd,pending,directory_fd,name,RENAME_NOREPLACE)) ok=0;
    if (!ok && unlinkat(directory_fd,pending,0)) return 0;
    return ok && !fsync(directory_fd);
}
static uint64_t now_ns(void) {
    struct timespec value;if (clock_gettime(CLOCK_MONOTONIC,&value)) return 0;
    return (uint64_t)value.tv_sec*1000000000ULL+(uint64_t)value.tv_nsec;
}
static int await_response(unsigned sequence,const struct request *request,struct response *response) {
    char name[40];snprintf(name,sizeof name,"%03u-response.bin",sequence);
    uint64_t started=now_ns();if (!started) return -1;
    for (;;) {
        int ready=read_exact_file(name,response,sizeof *response,1);
        if (ready<0) return -1;
        if (ready==1) {
            struct header expected=request->header;
            memcpy(expected.magic,"HGNMLPR1",8);expected.body_bytes=TENSOR_BYTES;
            unsigned char digest[32];
            if (memcmp(&response->header,&expected,sizeof expected) ||
                !digest_two(response,offsetof(struct response,digest),NULL,0,digest) ||
                memcmp(digest,response->digest,32) || !finite_bf16(response->output)) return -1;
            return 1;
        }
        uint64_t current=now_ns();if (!current || current<started) return -1;
        if (current-started>=WAIT_NS) return 0;
        struct timespec pause={0,10000000};
        /* Never restart an interrupted sleep with an unbounded remaining time. */
        if (nanosleep(&pause,NULL) && errno!=EINTR) return -1;
    }
}
static void quality_mlp(void *model,int32_t layer,int32_t count) {
    int incoming_errno=errno;
    if (layer!=48 || count!=1 || atomic_load(&disabled)) {
        errno=incoming_errno;original_mlp(model,layer,count);return;
    }
    if (pthread_mutex_trylock(&quality_mutex)) {
        atomic_store(&disabled,1);errno=incoming_errno;original_mlp(model,layer,count);return;
    }
    char armed_bytes[sizeof arm_content-1];
    int arm=calls>=MAX_CALLS?0:read_exact_file("armed",armed_bytes,sizeof armed_bytes,0);
    if (arm<0 || (arm==1 && memcmp(armed_bytes,arm_content,sizeof armed_bytes))) atomic_store(&disabled,1);
    if (arm!=1 || atomic_load(&disabled)) {
        if (pthread_mutex_unlock(&quality_mutex)) atomic_store(&disabled,1);
        errno=incoming_errno;original_mlp(model,layer,count);return;
    }
    unsigned sequence=calls++;
    struct request request={0};struct response response;
    uintptr_t caller=(uintptr_t)__builtin_return_address(0)-engine_base;
    uintptr_t input=0,output=0,ids=0,coeff=0,table=0;
    int capture=(caller==0x17da361 || caller==0x17da2e9) && mapped_span((uintptr_t)model,0xb10,NULL);
    if (capture) {
        table=(uintptr_t)word64(model,0x4d8);
        capture=span(table,49*0xc68) && mapped_span(table,49*0xc68,NULL) &&
            *((unsigned char *)model+0x900)==1 && *((unsigned char *)(table+48*0xc68))==1;
    }
    if (capture) {
        input=(uintptr_t)word64(model,0x6e8);output=(uintptr_t)word64(model,0x6d8);
        ids=(uintptr_t)word64((void *)engine_base,IDS_RVA);
        coeff=(uintptr_t)word64((void *)engine_base,COEFF_RVA);
        capture=disjoint(input,TENSOR_BYTES,output,TENSOR_BYTES) && coeff<=UINTPTR_MAX-40 &&
            coeff+40<=ids && disjoint(input,TENSOR_BYTES,ids,40) && disjoint(input,TENSOR_BYTES,coeff,40) &&
            disjoint(output,TENSOR_BYTES,ids,40) && disjoint(output,TENSOR_BYTES,coeff,40);
        request.header.position=word32(model,0x220);request.header.slot=word32(model,0xa0);
        capture=capture && request.header.position>=0 && request.header.slot>=0;
    }
    if (capture) {
        hip_sync=(sync_fn)dlsym(RTLD_DEFAULT,"hipDeviceSynchronize");
        hip_copy=(copy_fn)dlsym(RTLD_DEFAULT,"hipMemcpy");
        capture=hip_sync && hip_copy && !hip_sync() && !hip_copy(request.body,(void *)input,TENSOR_BYTES,2);
    }
    errno=incoming_errno;
    original_mlp(model,layer,count); /* Exactly once, on every path. */
    int result_errno=errno;
    if (capture) {
        capture=!hip_sync() && mapped_span((uintptr_t)model,0xb10,NULL) &&
            word64(model,0x6e8)==input && word64(model,0x6d8)==output &&
            word64((void *)engine_base,IDS_RVA)==ids && word64((void *)engine_base,COEFF_RVA)==coeff &&
            word32(model,0x220)==request.header.position && word32(model,0xa0)==request.header.slot &&
            !hip_copy(request.body+TENSOR_BYTES,(void *)ids,40,2) &&
            !hip_copy(request.body+TENSOR_BYTES+40,(void *)coeff,40,2) &&
            !hip_copy(request.body+TENSOR_BYTES+80,(void *)output,TENSOR_BYTES,2) &&
            finite_bf16(request.body) && finite_bf16(request.body+TENSOR_BYTES+80) && valid_routes(request.body);
    }
    const char *outcome="capture_failed";
    if (capture && !atomic_load(&disabled)) {
        memcpy(request.header.magic,"HGNMLPQ1",8);request.header.version=1;
        request.header.body_bytes=BODY_BYTES;request.header.sequence=(int32_t)sequence;
        memcpy(request.header.nonce,run_nonce,sizeof run_nonce);
        capture=digest_two(&request.header,48,request.body,sizeof request.body,request.header.binding) &&
            publish_request(sequence,&request);
        if (capture) {
            int ready=await_response(sequence,&request,&response);
            outcome=ready==0?"native_timeout":ready<0?"native_invalid_response":"native_disabled";
            if (ready<0) atomic_store(&disabled,1);
            if (ready==1 && !atomic_load(&disabled)) {
                /* No device write occurs before complete packet validation. */
                if (!hip_copy((void *)output,response.output,TENSOR_BYTES,1) && !hip_sync()) outcome="candidate_published";
                else {
                    if (hip_copy((void *)output,request.body+TENSOR_BYTES+80,TENSOR_BYTES,1) || hip_sync())
                        fatal("native-output-restore");
                    atomic_store(&disabled,1);outcome="native_restored";
                }
            }
        } else outcome="native_request_failed";
    }
    if (!capture) atomic_store(&disabled,1);
    log_result(sequence,outcome,request.header.binding);
    if (pthread_mutex_unlock(&quality_mutex)) atomic_store(&disabled,1);
    errno=result_errno;
}

/* Exact-version identity and the five-byte detour match the retained route tap. */
static void verify_hash(int fd,off_t offset,size_t bytes,const char *wanted) {
    EVP_MD_CTX *ctx=EVP_MD_CTX_new();unsigned char block[65536],digest[32];unsigned size=0;
    if (!ctx || EVP_DigestInit_ex(ctx,EVP_sha256(),NULL)!=1) fatal("hash-init");
    while (bytes) {
        size_t amount=bytes<sizeof block?bytes:sizeof block;
        ssize_t n=pread(fd,block,amount,offset);
        if (n<0 && errno==EINTR) continue;
        if (n<=0 || EVP_DigestUpdate(ctx,block,(size_t)n)!=1) fatal("hash-read");
        offset+=n;bytes-=(size_t)n;
    }
    if (EVP_DigestFinal_ex(ctx,digest,&size)!=1 || size!=32) fatal("hash-final");
    EVP_MD_CTX_free(ctx);char hex[65];
    for (unsigned i=0;i<32;i++) snprintf(hex+i*2,3,"%02x",digest[i]);
    if (strcmp(hex,wanted)) fatal("hash-mismatch");
}
struct site { uintptr_t entry,base;int found,globals; };
static int find_site(struct dl_phdr_info *info,size_t ignored,void *opaque) {
    (void)ignored;if (info->dlpi_name && *info->dlpi_name) return 0;
    struct site *site=opaque;if (ENTRY_RVA>UINTPTR_MAX-info->dlpi_addr) fatal("base-overflow");
    for (unsigned i=0;i<info->dlpi_phnum;i++) {
        const Elf64_Phdr *p=&info->dlpi_phdr[i];
        if (p->p_type==PT_LOAD && p->p_flags==(PF_R|PF_X) && p->p_vaddr<=ENTRY_RVA &&
            ENTRY_RVA+FUNCTION_BYTES<=p->p_vaddr+p->p_filesz &&
            p->p_offset+ENTRY_RVA-p->p_vaddr==(uint64_t)ENTRY_OFFSET) {
            site->entry=info->dlpi_addr+ENTRY_RVA;site->base=info->dlpi_addr;site->found++;
        }
        if (p->p_type==PT_LOAD && p->p_flags==(PF_R|PF_W) && p->p_vaddr<=COEFF_RVA &&
            IDS_RVA+sizeof(uintptr_t)<=p->p_vaddr+p->p_memsz) site->globals++;
    }
    return 1;
}
static void absolute_jump(unsigned char *at,uintptr_t target) {
    const unsigned char prefix[6]={0xff,0x25,0,0,0,0};memcpy(at,prefix,6);memcpy(at+6,&target,8);
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
    const char *mode=getenv("HALOGEN_MTP_QUALITY");if (!mode) return;
    if (strcmp(mode,"quality4-v1")) fatal("quality-mode");
    char executable[4096];ssize_t length=readlink("/proc/self/exe",executable,sizeof executable-1);
    if (length<0 || length>=(ssize_t)sizeof executable-1) fatal("executable-name");
    executable[length]=0;const char *base=strrchr(executable,'/');base=base?base+1:executable;
    if (strcmp(base,"flash_serve") || !serving_process()) return;
    const char *directory=getenv("HALOGEN_MTP_QUALITY_DIR");
    if (!directory || strncmp(directory,directory_prefix,sizeof directory_prefix-1) ||
        strlen(directory)!=sizeof directory_prefix-1+32) fatal("quality-directory");
    const char *hex=directory+sizeof directory_prefix-1;
    for (unsigned i=0;i<32;i++) {
        int value=hex[i]>='0' && hex[i]<='9'?hex[i]-'0':hex[i]>='a' && hex[i]<='f'?hex[i]-'a'+10:-1;
        if (value<0) fatal("run-id");
        run_nonce[i/2]|=(unsigned char)(value<<(i%2?0:4));
    }
    int fd=open("/proc/self/exe",O_RDONLY|O_CLOEXEC);struct stat before,after;Elf64_Ehdr elf;
    if (fd<0 || fstat(fd,&before) || !S_ISREG(before.st_mode) || before.st_size!=26052768 ||
        pread(fd,&elf,sizeof elf,0)!=(ssize_t)sizeof elf || memcmp(elf.e_ident,ELFMAG,SELFMAG) ||
        elf.e_ident[EI_CLASS]!=ELFCLASS64 || elf.e_ident[EI_DATA]!=ELFDATA2LSB ||
        elf.e_type!=ET_DYN || elf.e_machine!=EM_X86_64) fatal("elf-identity");
    verify_hash(fd,0,(size_t)before.st_size,ENGINE_SHA);
    verify_hash(fd,ENTRY_OFFSET,FUNCTION_BYTES,FUNCTION_SHA);
    if (fstat(fd,&after) || before.st_dev!=after.st_dev || before.st_ino!=after.st_ino ||
        before.st_size!=after.st_size || before.st_mtim.tv_sec!=after.st_mtim.tv_sec ||
        before.st_mtim.tv_nsec!=after.st_mtim.tv_nsec || before.st_ctim.tv_sec!=after.st_ctim.tv_sec ||
        before.st_ctim.tv_nsec!=after.st_ctim.tv_nsec || close(fd)) fatal("executable-consistency");
    struct site site={0};
    if (dl_iterate_phdr(find_site,&site)!=1 || site.found!=1 || site.globals!=1 ||
        !mapped_span(site.base+COEFF_RVA,IDS_RVA+sizeof(uintptr_t)-COEFF_RVA,"rw-p") ||
        !mapped_span(site.entry,FUNCTION_BYTES,"r-xp") ||
        memcmp((void *)site.entry,entry_signature,sizeof entry_signature)) fatal("entry-contract");
    engine_base=site.base;
    int tmp=open("/tmp",O_RDONLY|O_DIRECTORY|O_CLOEXEC|O_NOFOLLOW);
    if (tmp<0 || mkdirat(tmp,directory+5,0700)) fatal("fresh-directory");
    directory_fd=openat(tmp,directory+5,O_RDONLY|O_DIRECTORY|O_CLOEXEC|O_NOFOLLOW);
    if (close(tmp) || directory_fd<0) fatal("directory-open");
    log_fd=openat(directory_fd,"results.jsonl",O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC|O_NOFOLLOW,0600);
    if (log_fd<0) fatal("log-open");
    const char activation[]="{\"schema\":1,\"enabled\":true,\"layer\":48,\"count\":1,\"limit\":4,"
        "\"timeout_ms\":200,\"original_mlp\":\"always-once\",\"candidate\":\"explicit-complete-MLP-BF16\","
        "\"request_bytes\":10400,\"response_bytes\":5232,\"hardware_qualified\":false}\n";
    int activation_fd=openat(directory_fd,"activation.json",O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC|O_NOFOLLOW,0600);
    if (activation_fd<0 || !write_all(activation_fd,activation,sizeof activation-1) ||
        fsync(activation_fd) || close(activation_fd)) fatal("activation-write");
    long page_bytes=sysconf(_SC_PAGESIZE);
    if (page_bytes<=0 || ((unsigned long)page_bytes&((unsigned long)page_bytes-1))) fatal("page-size");
    uintptr_t page=site.entry&~((uintptr_t)page_bytes-1);unsigned char *thunk=NULL;
    if (site.entry+sizeof entry_signature>page+(uintptr_t)page_bytes ||
        !mapped_span(page,(size_t)page_bytes,"r-xp")) fatal("entry-page");
    for (unsigned i=0;i<256;i++) {
        uintptr_t distance=(uintptr_t)(i/2+1)*0x200000;
        if ((i&1)?page<distance:distance>UINTPTR_MAX-page) continue;
        uintptr_t candidate=(i&1)?page-distance:page+distance;
        void *area=mmap((void *)candidate,(size_t)page_bytes,PROT_READ|PROT_WRITE,
                       MAP_PRIVATE|MAP_ANONYMOUS|MAP_FIXED_NOREPLACE,-1,0);
        if (area==MAP_FAILED) {if (errno==EEXIST) continue;fatal("thunk-map");}
        if (area!=(void *)candidate) {if (munmap(area,(size_t)page_bytes)) fatal("thunk-unmap");fatal("fixed-map");}
        thunk=area;break;
    }
    if (!thunk) fatal("thunk-exhausted");
    absolute_jump(thunk,(uintptr_t)quality_mlp);
    memcpy(thunk+64,entry_signature,5);absolute_jump(thunk+69,site.entry+5);
    original_mlp=(mlp_fn)(thunk+64);
    if (mprotect(thunk,(size_t)page_bytes,PROT_READ|PROT_EXEC) ||
        !mapped_span((uintptr_t)thunk,(size_t)page_bytes,"r-xp")) fatal("thunk-rx");
    intptr_t relative=(intptr_t)((uintptr_t)thunk-(site.entry+5));
    if (relative<INT32_MIN || relative>INT32_MAX) fatal("jump-range");
    unsigned char jump[5]={0xe9};int32_t delta=(int32_t)relative;memcpy(jump+1,&delta,4);
    if (mprotect((void *)page,(size_t)page_bytes,PROT_READ|PROT_WRITE)) fatal("entry-rw");
    memcpy((void *)site.entry,jump,5);__builtin___clear_cache((char *)site.entry,(char *)site.entry+5);
    if (mprotect((void *)page,(size_t)page_bytes,PROT_READ|PROT_EXEC) ||
        !mapped_span(page,(size_t)page_bytes,"r-xp")) fatal("entry-rx");
}
