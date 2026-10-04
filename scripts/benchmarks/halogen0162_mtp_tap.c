/* Research-only read-only MTP trace. No NPU substitution and no checkpoint I/O.
 * Build: gcc -O2 -Wall -Wextra -Werror -shared -fPIC -fno-optimize-sibling-calls
 *        halogen0162_mtp_tap.c -ldl -lcrypto -pthread -o libhalogen0162-mtp-tap.so
 * The root coordinator alone owns any engine launch. Trace timing is intrusive.
 * Set HALOGEN_MTP_TAP=trace32-v1 and HALOGEN_MTP_TAP_DIR=/tmp/alloy-mtp-tap-<32hex>.
 * The tap creates that directory exclusively. A regular file named armed containing
 * exactly "trace32-v1-ready\n" arms the next 32 calls only after service READY.
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
#define FUNCTION_SHA "132f2da76d86694ffe5f120d61e304e57c685f3db72935c6d5e61bf7b0d5cc20"
#define ENTRY_RVA ((uintptr_t)0x17db310)
#define ENTRY_OFFSET ((off_t)0x17da310)
#define FUNCTION_BYTES ((size_t)(0x17dc289 - 0x17db310))
#define RESIDUAL_BYTES ((size_t)0x5000)
#define MTP_SMALL_STATE_BYTES ((size_t)0x300)
#define LOGIT_BYTES ((size_t)248320 * sizeof(float))
#define TRACE_LIMIT 32U
#define TOKEN_COUNT_LIMIT 32768
static const char trace_prefix[] = "/tmp/alloy-mtp-tap-";
static const char arm_content[] = "trace32-v1-ready\n";
static const unsigned char entry_signature[32] = {
    0x55,0x41,0x57,0x41,0x56,0x41,0x55,0x41,0x54,0x53,0x48,0x81,0xec,0x98,0,0,
    0,0xb8,0xff,0xff,0xff,0xff,0x80,0xbf,0,0x09,0,0,0x01,0x0f,0x85,0x31
};
typedef int32_t (*head_fn)(void *, const int32_t *, int32_t, int32_t);
typedef int (*sync_fn)(void);
typedef int (*copy_fn)(void *, const void *, size_t, int);
static head_fn original_head;
static sync_fn hip_sync;
static copy_fn hip_copy;
static int trace_dir = -1, trace_log = -1;
static unsigned trace_count;
static int logits_saved;
static pthread_mutex_t trace_mutex = PTHREAD_MUTEX_INITIALIZER;

static _Noreturn void fatal(const char *reason) {
    dprintf(STDERR_FILENO, "[mtp-tap] fatal reason=%s errno=%d\n", reason, errno);
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
static void write_all(int fd, const void *data, size_t bytes) {
    const unsigned char *at = data;
    while (bytes) {
        ssize_t written = write(fd, at, bytes);
        if (written < 0 && errno == EINTR) continue;
        if (written <= 0) fatal("write");
        at += written; bytes -= (size_t)written;
    }
}
static void save_bytes(unsigned index, const char *kind, const void *data, size_t bytes) {
    char name[64];
    if (snprintf(name, sizeof name, "%02u-%s.bin", index, kind) >= (int)sizeof name)
        fatal("name");
    int fd = openat(trace_dir, name, O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC | O_NOFOLLOW, 0600);
    if (fd < 0) fatal("capture-open");
    write_all(fd, data, bytes);
    if (close(fd)) fatal("capture-close");
}
static void save_device(unsigned index, const char *kind, uintptr_t source, size_t bytes) {
    if (!source || bytes > LOGIT_BYTES || bytes > UINTPTR_MAX - source)
        fatal("device-span");
    void *buffer = malloc(bytes);
    if (!buffer) fatal("capture-allocation");
    /* HIP kind 2 is DeviceToHost. The pre/post hipDeviceSynchronize is explicit. */
    if (hip_copy(buffer, (void *)source, bytes, 2)) fatal("device-read");
    save_bytes(index, kind, buffer, bytes);
    free(buffer);
}
static int armed(void) {
    int fd = openat(trace_dir, "armed", O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
    if (fd < 0) {
        if (errno == ENOENT) return 0;
        fatal("arm-open");
    }
    struct stat before, after;
    char content[sizeof arm_content];
    if (fstat(fd, &before) || !S_ISREG(before.st_mode) || before.st_nlink != 1 ||
        before.st_size != (off_t)(sizeof arm_content - 1) ||
        pread(fd, content, sizeof content, 0) != (ssize_t)(sizeof arm_content - 1) ||
        memcmp(content, arm_content, sizeof arm_content - 1) || fstat(fd, &after) ||
        before.st_dev != after.st_dev || before.st_ino != after.st_ino ||
        before.st_size != after.st_size || before.st_mtim.tv_sec != after.st_mtim.tv_sec ||
        before.st_mtim.tv_nsec != after.st_mtim.tv_nsec || close(fd)) fatal("arm-content");
    return 1;
}
static void log_meta(unsigned index, const char *phase, const unsigned char *model,
                     uintptr_t caller, int32_t count, int32_t position, int32_t result,
                     uintptr_t small_state) {
    if (dprintf(trace_log,
        "{\"index\":%u,\"phase\":\"%s\",\"model\":\"0x%" PRIxPTR
        "\",\"caller\":\"0x%" PRIxPTR "\",\"count\":%d,\"start_position\":%d,"
        "\"result\":%d,\"spec_n\":%d,\"spec_base\":%d,\"position\":%d,"
        "\"draft_cache\":[%d,%d,%d],\"tap_position\":%d,\"head_count\":%d,"
        "\"small_state_position\":%d,\"small_state_slot\":%d,"
        "\"residual_snapshot\":\"0x%" PRIx64 "\",\"small_state_snapshot\":\"0x%" PRIx64
        "\",\"input_residual\":\"0x%" PRIx64 "\",\"head_hidden\":\"0x%" PRIx64
        "\",\"head_logits\":\"0x%" PRIx64 "\",\"small_state\":\"0x%" PRIxPTR "\"}\n",
        index, phase, (uintptr_t)model, caller, count, position, result,
        word32(model,0x18), word32(model,0x1c), word32(model,0x220),
        word32(model,0x40),word32(model,0x44),word32(model,0x48),
        word32(model,0x58),word32(model,0x5c),word32(model,0x70),word32(model,0x74),
        word64(model,0x50),word64(model,0x68),word64(model,0x6d0),
        word64(model,0xb00),word64(model,0xb08),small_state) < 0) fatal("metadata-write");
}
static int32_t tapped_head(void *object, const int32_t *tokens, int32_t count, int32_t position) {
    int incoming_errno = errno;
    if (!armed()) {
        errno = incoming_errno;
        return original_head(object,tokens,count,position);
    }
    if (pthread_mutex_lock(&trace_mutex)) fatal("mutex-lock");
    if (trace_count >= TRACE_LIMIT) {
        if (pthread_mutex_unlock(&trace_mutex)) fatal("mutex-unlock");
        errno = incoming_errno;
        return original_head(object,tokens,count,position);
    }
    unsigned index = trace_count++;
    const unsigned char *model = object;
    if (!mapped_read((uintptr_t)model,0xb10) || count <= 0 || count > TOKEN_COUNT_LIMIT || position < 0 ||
        !mapped_read((uintptr_t)tokens,(size_t)count*sizeof *tokens)) fatal("entry-contract");
    uintptr_t layer_table = (uintptr_t)word64(model,0x4d8), small_state = 0;
    if (layer_table && layer_table <= UINTPTR_MAX - 0x25888 &&
        mapped_read(layer_table + 0x25880,sizeof small_state))
        memcpy(&small_state,(void *)(layer_table + 0x25880),sizeof small_state);
    if (!hip_sync) hip_sync = (sync_fn)dlsym(RTLD_DEFAULT,"hipDeviceSynchronize");
    if (!hip_copy) hip_copy = (copy_fn)dlsym(RTLD_DEFAULT,"hipMemcpy");
    if (!hip_sync || !hip_copy || hip_sync()) fatal("entry-sync");
    log_meta(index,"entry",model,(uintptr_t)__builtin_return_address(0),count,position,-1,small_state);
    save_bytes(index,"tokens-i32",tokens,(size_t)count*sizeof *tokens);
    uintptr_t residual = (uintptr_t)word64(model,0x6d0);
    size_t row_offset = (size_t)(count-1)*RESIDUAL_BYTES;
    if (row_offset > UINTPTR_MAX - residual) fatal("residual-overflow");
    /* Storage is raw u16[10240]; numerical BF16 interpretation is not asserted here. */
    save_device(index,"entry-residual-last-u16",residual + row_offset,RESIDUAL_BYTES);
    if (small_state) save_device(index,"entry-small-state-raw",small_state,MTP_SMALL_STATE_BYTES);
    errno = incoming_errno;
    int32_t result = original_head(object,tokens,count,position);
    int result_errno = errno;
    if (hip_sync()) fatal("exit-sync");
    log_meta(index,"exit",model,(uintptr_t)__builtin_return_address(0),count,position,result,small_state);
    if (small_state) save_device(index,"exit-small-state-raw",small_state,MTP_SMALL_STATE_BYTES);
    if (!logits_saved && count == 1 && result >= 0) {
        save_device(index,"exit-logits-f32",(uintptr_t)word64(model,0xb08),LOGIT_BYTES);
        logits_saved = 1;
    }
    if (pthread_mutex_unlock(&trace_mutex)) fatal("mutex-unlock");
    errno = result_errno;
    return result;
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
struct site { uintptr_t entry; int found; };
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
            site->entry=info->dlpi_addr+ENTRY_RVA;site->found++;
        }
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
    const char *mode=getenv("HALOGEN_MTP_TAP"),*directory=getenv("HALOGEN_MTP_TAP_DIR");
    if (!mode || strcmp(mode,"trace32-v1") || !directory ||
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
    if (dl_iterate_phdr(find_site,&site)!=1 || site.found!=1 ||
        !mapped_span(site.entry,FUNCTION_BYTES,"r-xp") || memcmp((void *)site.entry,entry_signature,sizeof entry_signature))
        fatal("entry-signature");
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
    absolute_jump(thunk,(uintptr_t)tapped_head);
    /* Relocate exactly three complete, non-RIP-relative prologue pushes. */
    memcpy(thunk+64,entry_signature,5);absolute_jump(thunk+69,site.entry+5);
    original_head=(head_fn)(thunk+64);
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
    if (dprintf(trace_log,"{\"schema\":1,\"engine_sha256\":\"%s\",\"function_sha256\":\"%s\","
        "\"entry_rva\":\"0x17db310\",\"limit\":32,\"token_count_limit\":32768,"
        "\"arming\":\"regular-file:armed:trace32-v1-ready\\n\",\"residual_storage\":\"raw-u16[10240]\","
        "\"residual_bytes\":20480,\"small_state_bytes\":768,\"logits_bytes\":993280}\n",ENGINE_SHA,FUNCTION_SHA)<0)
        fatal("activation-log");
}
