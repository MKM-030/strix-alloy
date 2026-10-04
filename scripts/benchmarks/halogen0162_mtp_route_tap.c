/* Research-only exact MTP routing trace. Original MLP always executes.
 * Build: gcc -O2 -Wall -Wextra -Werror -shared -fPIC -fno-optimize-sibling-calls
 *        halogen0162_mtp_route_tap.c -ldl -lcrypto -pthread -o libhalogen0162-mtp-route-tap.so
 * Root alone owns engine launches. Timing is intrusive; no throughput claims.
 * HALOGEN_MTP_ROUTE_TAP=route128-v1; directory=/tmp/alloy-mtp-route-tap-<32hex>.
 * A regular exclusive armed file containing route128-v1-ready\n is published after READY.
 * Captures only layer 48/count 1: raw-u16 input[2560], int32 IDs[10], FP32
 * coefficients[10], and complete raw-u16 MLP output[2560]. No BF16 interpretation.
 * Static lifetime receipt: server/.local/optimization9h-20261004/mtp-route-static-20261004/seam-report.md.
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
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>

#if !defined(__x86_64__) || !defined(__linux__)
#error Linux x86-64 only
#endif
#define ENGINE_SHA "ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b"
#define FUNCTION_SHA "e318b4639c8bd2e57d66b12b823fcafc1f5c5a5136e3651c06e2bac54e46c717"
#define ENTRY_RVA ((uintptr_t)0x17bd410)
#define ENTRY_OFFSET ((off_t)0x17bc410)
#define FUNCTION_BYTES ((size_t)(0x17ca056 - 0x17bd410))
#define TENSOR_BYTES ((size_t)2560 * sizeof(uint16_t))
#define ROUTE_BYTES ((size_t)10 * sizeof(int32_t))
#define COEFF_RVA ((uintptr_t)0x18db3e0)
#define IDS_RVA ((uintptr_t)0x18db400)
#define TRACE_LIMIT 128U
#define TRACE_BYTE_LIMIT ((size_t)2 * 1024 * 1024)
#define TRACE_FILE_LIMIT (TRACE_LIMIT * 4U + 2U)
static const char trace_prefix[] = "/tmp/alloy-mtp-route-tap-";
static const char arm_content[] = "route128-v1-ready\n";
static const unsigned char entry_signature[32] = {
    0x55,0x41,0x57,0x41,0x56,0x41,0x55,0x41,0x54,0x53,0x48,0x81,0xec,0x58,0x0f,0,
    0,0x48,0x89,0x94,0x24,0xf0,0,0,0,0x89,0x94,0x24,0xa4,0,0,0
};
typedef void (*mlp_fn)(void *, int32_t, int32_t);
typedef int (*sync_fn)(void);
typedef int (*copy_fn)(void *, const void *, size_t, int);
static mlp_fn original_mlp;
static uintptr_t engine_base;
static sync_fn hip_sync;
static copy_fn hip_copy;
static int trace_dir = -1, trace_log = -1;
static unsigned trace_count;
static int trace_disabled;
static size_t trace_bytes;
static unsigned trace_files;
static pthread_mutex_t trace_mutex = PTHREAD_MUTEX_INITIALIZER;

static _Noreturn void fatal(const char *reason) {
    dprintf(STDERR_FILENO, "[mtp-route-tap] fatal reason=%s errno=%d\n", reason, errno);
    _exit(79);
}
static int mapped_span(uintptr_t address, size_t bytes, const char *wanted) {
    if (!address || !bytes || bytes > UINTPTR_MAX - address) return 0;
    FILE *file = fopen("/proc/self/maps", "re");
    if (!file) return 0;
    char line[4096], perms[5]; unsigned long low, high;
    int found = 0;
    while (fgets(line, sizeof line, file)) {
        if (sscanf(line, "%lx-%lx %4s", &low, &high, perms) != 3) continue;
        if (address >= low && address + bytes <= high &&
            (wanted ? !strcmp(perms,wanted) : perms[0] == 'r')) {
            found = 1; break;
        }
    }
    if (ferror(file) || fclose(file)) return 0;
    return found;
}
static int mapped_read(uintptr_t address, size_t bytes) {
    return mapped_span(address,bytes,NULL);
}
static uint64_t word64(const unsigned char *model, size_t offset) {
    uint64_t value; memcpy(&value, model + offset, sizeof value); return value;
}
static int32_t word32(const unsigned char *model, size_t offset) {
    int32_t value; memcpy(&value, model + offset, sizeof value); return value;
}
/* Every capture error disables tracing, but preserves the original MLP call.
 * Installation errors remain fatal before the entrypoint has been patched. */
static int append_bytes(int fd, const void *data, size_t bytes) {
    if (bytes > TRACE_BYTE_LIMIT - trace_bytes) return 0;
    const unsigned char *at=data;
    while (bytes) {
        ssize_t written=write(fd,at,bytes);
        if (written<0 && errno==EINTR) continue;
        if (written<=0) return 0;
        at+=written;bytes-=(size_t)written;trace_bytes+=(size_t)written;
    }
    return 1;
}
static void capture_error(unsigned index, const char *reason) {
    trace_disabled=1;
    dprintf(STDERR_FILENO,"[mtp-route-tap] capture disabled index=%u reason=%s errno=%d\n",index,reason,errno);
    char line[256];
    int n=snprintf(line,sizeof line,"{\"index\":%u,\"phase\":\"capture-error\",\"reason\":\"%s\"}\n",index,reason);
    if (n>0 && n<(int)sizeof line) (void)append_bytes(trace_log,line,(size_t)n);
}
static int save_bytes(unsigned index, const char *kind, const void *data, size_t bytes) {
    char name[64];
    if (trace_files>=TRACE_FILE_LIMIT || bytes>TRACE_BYTE_LIMIT-trace_bytes ||
        snprintf(name,sizeof name,"%03u-%s.bin",index,kind)>=(int)sizeof name) return 0;
    int fd=openat(trace_dir,name,O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC|O_NOFOLLOW,0600);
    if (fd<0) return 0;
    trace_files++;
    int ok=append_bytes(fd,data,bytes);
    if (close(fd)) ok=0;
    return ok;
}
static int save_device(unsigned index, const char *kind, uintptr_t source, size_t bytes) {
    if (!source || bytes>TENSOR_BYTES || bytes>UINTPTR_MAX-source) return 0;
    unsigned char buffer[TENSOR_BYTES];
    /* HIP kind 2 is DeviceToHost; caller explicitly synchronizes first. */
    if (hip_copy(buffer,(void *)source,bytes,2)) return 0;
    return save_bytes(index,kind,buffer,bytes);
}
static int armed(void) {
    int fd=openat(trace_dir,"armed",O_RDONLY|O_CLOEXEC|O_NOFOLLOW);
    if (fd<0) return errno==ENOENT?0:-1;
    struct stat before,after;
    char content[sizeof arm_content];
    int ok=!fstat(fd,&before) && S_ISREG(before.st_mode) && before.st_nlink==1 &&
        before.st_size==(off_t)(sizeof arm_content-1) &&
        pread(fd,content,sizeof content,0)==(ssize_t)(sizeof arm_content-1) &&
        !memcmp(content,arm_content,sizeof arm_content-1) && !fstat(fd,&after) &&
        before.st_dev==after.st_dev && before.st_ino==after.st_ino &&
        before.st_size==after.st_size && before.st_mtim.tv_sec==after.st_mtim.tv_sec &&
        before.st_mtim.tv_nsec==after.st_mtim.tv_nsec;
    if (close(fd)) ok=0;
    return ok?1:-1;
}
static uintptr_t global_pointer(uintptr_t rva) {
    uintptr_t result;
    memcpy(&result,(void *)(engine_base+rva),sizeof result);
    return result;
}
static int device_span(uintptr_t pointer, size_t bytes) {
    return pointer && bytes<=UINTPTR_MAX-pointer;
}
static int disjoint(uintptr_t a, size_t na, uintptr_t b, size_t nb) {
    return device_span(a,na) && device_span(b,nb) && (a+na<=b || b+nb<=a);
}
static int log_meta(unsigned index, const char *phase, const unsigned char *model,
                    uintptr_t caller, uintptr_t input, uintptr_t ids,
                    uintptr_t coeff, uintptr_t output) {
    char line[1536];
    int n=snprintf(line,sizeof line,
        "{\"index\":%u,\"phase\":\"%s\",\"model\":\"0x%" PRIxPTR
        "\",\"caller\":\"0x%" PRIxPTR "\",\"caller_rva\":\"0x%" PRIxPTR
        "\",\"layer\":48,\"count\":1,\"spec_n\":%d,\"spec_base\":%d,\"position\":%d,"
        "\"draft_cache\":[%d,%d,%d],\"tap_position\":%d,\"head_count\":%d,"
        "\"small_state_position\":%d,\"small_state_slot\":%d,"
        "\"mlp_input\":\"0x%" PRIxPTR "\",\"expert_ids\":\"0x%" PRIxPTR
        "\",\"coefficients\":\"0x%" PRIxPTR "\",\"complete_mlp_output\":\"0x%" PRIxPTR "\"}\n",
        index,phase,(uintptr_t)model,caller,caller-engine_base,
        word32(model,0x18),word32(model,0x1c),word32(model,0x220),
        word32(model,0x40),word32(model,0x44),word32(model,0x48),
        word32(model,0x58),word32(model,0x5c),word32(model,0x70),word32(model,0x74),
        input,ids,coeff,output);
    return n>0 && n<(int)sizeof line && append_bytes(trace_log,line,(size_t)n);
}
static void tapped_mlp(void *object, int32_t layer, int32_t count) {
    int incoming_errno=errno;
    if (layer!=48 || count!=1) {
        original_mlp(object,layer,count);
        return;
    }
    if (pthread_mutex_lock(&trace_mutex)) {
        errno=incoming_errno;
        original_mlp(object,layer,count);
        return;
    }
    int arm=trace_disabled || trace_count>=TRACE_LIMIT?0:armed();
    if (arm<0) capture_error(trace_count,"arm-content");
    if (arm!=1) {
        (void)pthread_mutex_unlock(&trace_mutex);
        errno=incoming_errno;
        original_mlp(object,layer,count);
        return;
    }
    unsigned index=trace_count++;
    const unsigned char *model=object;
    uintptr_t caller=(uintptr_t)__builtin_return_address(0),input=0,ids=0,coeff=0,output=0;
    int captured=mapped_read((uintptr_t)model,0xb10) &&
        caller>=engine_base && (caller-engine_base==0x17da361 || caller-engine_base==0x17da2e9);
    if (captured) {
        input=(uintptr_t)word64(model,0x6e8);output=(uintptr_t)word64(model,0x6d8);
        ids=global_pointer(IDS_RVA);coeff=global_pointer(COEFF_RVA);
        /* The exact binary publishes adjacent coeff/ID regions in one arena.
         * Kernels consume these as const inputs after top-k. Check the live
         * slots and tensor separation; IDs/coeffs are copied before reuse. */
        captured=device_span(input,TENSOR_BYTES) && device_span(output,TENSOR_BYTES) &&
            device_span(coeff,ROUTE_BYTES) && device_span(ids,ROUTE_BYTES) &&
            coeff+ROUTE_BYTES<=ids &&
            disjoint(input,TENSOR_BYTES,output,TENSOR_BYTES) &&
            disjoint(input,TENSOR_BYTES,ids,ROUTE_BYTES) &&
            disjoint(input,TENSOR_BYTES,coeff,ROUTE_BYTES) &&
            disjoint(output,TENSOR_BYTES,ids,ROUTE_BYTES) &&
            disjoint(output,TENSOR_BYTES,coeff,ROUTE_BYTES);
    }
    if (!captured) capture_error(index,"entry-contract");
    if (captured) {
        if (!hip_sync) hip_sync=(sync_fn)dlsym(RTLD_DEFAULT,"hipDeviceSynchronize");
        if (!hip_copy) hip_copy=(copy_fn)dlsym(RTLD_DEFAULT,"hipMemcpy");
        captured=hip_sync && hip_copy && !hip_sync();
        if (!captured) capture_error(index,"entry-sync");
    }
    if (captured) {
        captured=log_meta(index,"entry",model,caller,input,ids,coeff,output) &&
            save_device(index,"entry-mlp-input-u16",input,TENSOR_BYTES);
        if (!captured) capture_error(index,"entry-capture");
    }
    errno=incoming_errno;
    /* The original executes exactly once on every path through this hook. */
    original_mlp(object,layer,count);
    int result_errno=errno;
    if (captured) {
        captured=!hip_sync() && mapped_read((uintptr_t)model,0xb10) &&
            word64(model,0x6e8)==input && word64(model,0x6d8)==output &&
            global_pointer(IDS_RVA)==ids && global_pointer(COEFF_RVA)==coeff;
        if (!captured) capture_error(index,"exit-sync-or-pointers");
    }
    if (captured) {
        captured=save_device(index,"exit-expert-ids-i32",ids,ROUTE_BYTES) &&
            save_device(index,"exit-coefficients-f32",coeff,ROUTE_BYTES) &&
            save_device(index,"exit-complete-mlp-output-u16",output,TENSOR_BYTES) &&
            log_meta(index,"exit",model,caller,input,ids,coeff,output);
        if (!captured) capture_error(index,"exit-capture");
    }
    if (pthread_mutex_unlock(&trace_mutex)) capture_error(index,"mutex-unlock");
    errno=result_errno;
}

static void verify_hash(int fd, off_t offset, size_t bytes, const char *wanted) {
    EVP_MD_CTX *ctx = EVP_MD_CTX_new();
    if (!ctx || EVP_DigestInit_ex(ctx,EVP_sha256(),NULL) != 1) fatal("hash-init");
    unsigned char buffer[65536],digest[32]; unsigned length = 0;
    while (bytes) {
        size_t amount = bytes < sizeof buffer ? bytes : sizeof buffer;
        ssize_t got = pread(fd,buffer,amount,offset);
        if (got < 0 && errno == EINTR) continue;
        if (got <= 0 || EVP_DigestUpdate(ctx,buffer,(size_t)got) != 1) fatal("hash-read");
        offset += got; bytes -= (size_t)got;
    }
    if (EVP_DigestFinal_ex(ctx,digest,&length) != 1 || length != sizeof digest) fatal("hash-final");
    EVP_MD_CTX_free(ctx);
    char hex[65];
    for (size_t i=0;i<sizeof digest;i++) snprintf(hex+i*2,3,"%02x",digest[i]);
    if (strcmp(hex,wanted)) fatal("hash-mismatch");
}
struct site { uintptr_t entry, base; int found, globals_found; };
static int find_site(struct dl_phdr_info *info, size_t ignored, void *opaque) {
    (void)ignored;
    if (info->dlpi_name && *info->dlpi_name) return 0;
    struct site *site = opaque;
    if (ENTRY_RVA > UINTPTR_MAX-info->dlpi_addr) fatal("base-overflow");
    for (size_t i=0;i<info->dlpi_phnum;i++) {
        const Elf64_Phdr *p = &info->dlpi_phdr[i];
        if (p->p_type == PT_LOAD && p->p_flags == (PF_R|PF_X) &&
            p->p_vaddr <= ENTRY_RVA && ENTRY_RVA + FUNCTION_BYTES <= p->p_vaddr + p->p_filesz &&
            p->p_offset + ENTRY_RVA - p->p_vaddr == (uint64_t)ENTRY_OFFSET) {
            site->entry=info->dlpi_addr+ENTRY_RVA;site->base=info->dlpi_addr;site->found++;
        }
        if (p->p_type==PT_LOAD && p->p_flags==(PF_R|PF_W) &&
            p->p_vaddr<=COEFF_RVA && IDS_RVA+sizeof(uintptr_t)<=p->p_vaddr+p->p_memsz)
            site->globals_found++;
    }
    return 1;
}
static void absolute_jump(unsigned char *at, uintptr_t target) {
    const unsigned char prefix[6] = {0xff,0x25,0,0,0,0};
    memcpy(at,prefix,sizeof prefix);memcpy(at+6,&target,sizeof target);
}
static int serving_process(void) {
    /* The pinned entrypoint first runs flash_serve --resident-gib to read its
     * checkpoint header. Only its subsequent --ck serving process owns a trace. */
    int fd=open("/proc/self/cmdline",O_RDONLY|O_CLOEXEC);
    char command[4096]; ssize_t bytes;
    if (fd<0) fatal("cmdline-open");
    do { bytes=read(fd,command,sizeof command); } while (bytes<0 && errno==EINTR);
    if (bytes<=0 || bytes>=(ssize_t)sizeof command || command[bytes-1] || close(fd))
        fatal("cmdline-read");
    const char *argument=memchr(command,0,(size_t)bytes);
    if (!argument || argument+1>=command+bytes) return 0;
    return !strcmp(argument+1,"--ck");
}
__attribute__((constructor)) static void install(void) {
    char name[4096]; ssize_t n = readlink("/proc/self/exe",name,sizeof name-1);
    if (n < 0 || n >= (ssize_t)sizeof name-1) fatal("executable-name");
    name[n]=0; const char *base=strrchr(name,'/');base=base?base+1:name;
    if (strcmp(base,"flash_serve")) return;
    if (!serving_process()) return;
    const char *mode=getenv("HALOGEN_MTP_ROUTE_TAP"),*directory=getenv("HALOGEN_MTP_ROUTE_TAP_DIR");
    if (!mode || strcmp(mode,"route128-v1") || !directory ||
        strncmp(directory,trace_prefix,sizeof trace_prefix - 1) ||
        strlen(directory) != sizeof trace_prefix - 1 + 32) fatal("configuration");
    for (const char *at=directory + sizeof trace_prefix - 1; *at; at++)
        if (!((*at>='0' && *at<='9') || (*at>='a' && *at<='f'))) fatal("trace-run-id");
    int fd=open("/proc/self/exe",O_RDONLY|O_CLOEXEC);struct stat before,after;
    if (fd<0 || fstat(fd,&before) || !S_ISREG(before.st_mode) || before.st_size<=ENTRY_OFFSET) fatal("executable-stat");
    Elf64_Ehdr eh;
    if (pread(fd,&eh,sizeof eh,0)!=(ssize_t)sizeof eh || memcmp(eh.e_ident,ELFMAG,SELFMAG) ||
        eh.e_ident[EI_CLASS]!=ELFCLASS64 || eh.e_ident[EI_DATA]!=ELFDATA2LSB ||
        eh.e_type!=ET_DYN || eh.e_machine!=EM_X86_64) fatal("elf-identity");
    verify_hash(fd,0,(size_t)before.st_size,ENGINE_SHA);
    verify_hash(fd,ENTRY_OFFSET,FUNCTION_BYTES,FUNCTION_SHA);
    if (fstat(fd,&after) || before.st_dev!=after.st_dev || before.st_ino!=after.st_ino ||
        before.st_size!=after.st_size || before.st_mtim.tv_sec!=after.st_mtim.tv_sec ||
        before.st_mtim.tv_nsec!=after.st_mtim.tv_nsec || before.st_ctim.tv_sec!=after.st_ctim.tv_sec ||
        before.st_ctim.tv_nsec!=after.st_ctim.tv_nsec || close(fd)) fatal("executable-consistency");
    struct site site={0};
    if (dl_iterate_phdr(find_site,&site)!=1 || site.found!=1 || site.globals_found!=1 ||
        !mapped_span(site.base+COEFF_RVA,IDS_RVA+sizeof(uintptr_t)-COEFF_RVA,"rw-p") ||
        !mapped_span(site.entry,FUNCTION_BYTES,"r-xp") || memcmp((void *)site.entry,entry_signature,sizeof entry_signature))
        fatal("entry-signature");
    engine_base=site.base;
    int tmp_dir=open("/tmp",O_RDONLY|O_DIRECTORY|O_CLOEXEC|O_NOFOLLOW);
    struct stat tmp_stat;
    if (tmp_dir<0 || fstat(tmp_dir,&tmp_stat) || !S_ISDIR(tmp_stat.st_mode)) fatal("tmp-directory");
    const char *trace_name=directory + sizeof "/tmp/" - 1;
    if (mkdirat(tmp_dir,trace_name,0700)) fatal("trace-mkdir");
    trace_dir=openat(tmp_dir,trace_name,O_RDONLY|O_DIRECTORY|O_CLOEXEC|O_NOFOLLOW);
    if (close(tmp_dir)) fatal("tmp-close");
    if (trace_dir<0) fatal("trace-directory");
    trace_log=openat(trace_dir,"trace.jsonl",O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC|O_NOFOLLOW,0600);
    if (trace_log<0) fatal("trace-log");
    long size=sysconf(_SC_PAGESIZE);
    if (size<=0 || ((unsigned long)size&((unsigned long)size-1))) fatal("page-size");
    uintptr_t page=site.entry&~((uintptr_t)size-1);unsigned char *thunk=NULL;
    if (site.entry+sizeof entry_signature>page+(uintptr_t)size) fatal("entry-page");
    if (!mapped_span(page,(size_t)size,"r-xp")) fatal("entry-page-rx");
    for (unsigned i=0;i<256;i++) {
        uintptr_t distance=(uintptr_t)(i/2+1)*0x200000;
        if ((i&1)?page<distance:distance>UINTPTR_MAX-page) continue;
        uintptr_t candidate=(i&1)?page-distance:page+distance;
        void *area=mmap((void *)candidate,(size_t)size,PROT_READ|PROT_WRITE,
            MAP_PRIVATE|MAP_ANONYMOUS|MAP_FIXED_NOREPLACE,-1,0);
        if (area==MAP_FAILED) {if(errno==EEXIST)continue;fatal("thunk-map");}
        if (area!=(void *)candidate) {
            if (munmap(area,(size_t)size)) fatal("thunk-unmap");
            fatal("fixed-noreplace");
        }
        thunk=area;break;
    }
    if (!thunk) fatal("thunk-exhausted");
    absolute_jump(thunk,(uintptr_t)tapped_mlp);
    /* Relocate exactly three complete, non-RIP-relative prologue pushes. */
    memcpy(thunk+64,entry_signature,5);absolute_jump(thunk+69,site.entry+5);
    original_mlp=(mlp_fn)(thunk+64);
    if (mprotect(thunk,(size_t)size,PROT_READ|PROT_EXEC) ||
        !mapped_span((uintptr_t)thunk,(size_t)size,"r-xp")) fatal("thunk-rx");
    intptr_t relative=(intptr_t)((uintptr_t)thunk-(site.entry+5));
    if (relative<INT32_MIN || relative>INT32_MAX) fatal("jump-range");
    unsigned char jump[5]={0xe9};int32_t delta=(int32_t)relative;memcpy(jump+1,&delta,4);
    if (mprotect((void *)page,(size_t)size,PROT_READ|PROT_WRITE)) fatal("entry-rw");
    memcpy((void *)site.entry,jump,5);
    __builtin___clear_cache((char *)site.entry,(char *)site.entry+5);
    if (mprotect((void *)page,(size_t)size,PROT_READ|PROT_EXEC) ||
        !mapped_span(page,(size_t)size,"r-xp")) fatal("entry-rx");
    trace_files=2; /* trace.jsonl plus the later exclusive arm file. */
    trace_bytes=sizeof arm_content-1; /* Include the coordinator-written arm. */
    char header[1024];
    int header_n=snprintf(header,sizeof header,
        "{\"schema\":1,\"engine_sha256\":\"%s\",\"function_sha256\":\"%s\","
        "\"entry_rva\":\"0x17bd410\",\"limit\":128,\"layer\":48,\"count\":1,"
        "\"arming\":\"regular-file:armed:route128-v1-ready\\n\",\"tensor_storage\":\"raw-u16[2560]\","
        "\"input_bytes\":5120,\"ids_bytes\":40,\"coefficient_bytes\":40,\"output_bytes\":5120,"
        "\"byte_limit\":2097152,\"file_limit\":514,\"ids_rva\":\"0x18db400\",\"coefficient_rva\":\"0x18db3e0\","
        "\"output_scope\":\"complete-MLP\",\"acceptance_scope\":\"unqualified-speculative-calls\"}\n",
        ENGINE_SHA,FUNCTION_SHA);
    if (header_n<=0 || header_n>=(int)sizeof header || !append_bytes(trace_log,header,(size_t)header_n))
        fatal("activation-log");
}
