#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <link.h>
#include <stdint.h>
#include <stddef.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/un.h>
#include <unistd.h>

#include "stream_consumer.h"
#include "native_pins.h"
#include "cold_addresses.h"
#include "sha256_core.h"

static uintptr_t image_base;
static int image_found;

static int engine_process(void) {
    char path[4096];
    ssize_t bytes = readlink("/proc/self/exe", path, sizeof(path) - 1);
    if (bytes <= 0 || bytes >= (ssize_t)sizeof(path) - 1)
        return 0;
    path[bytes] = '\0';
    const char *name = strrchr(path, '/');
    return name && strcmp(name + 1, "flash_serve") == 0;
}

static void fatal(const char *message) {
    ssize_t written = write(STDERR_FILENO, message, strlen(message));
    (void)written;
    _exit(125);
}

static int exact_engine(void) {
    unsigned char buffer[16384], digest[32];
    struct hgn_sha256 hash;
    struct stat before, after;
    uint64_t bytes = 0;
    int descriptor = open("/proc/self/exe", O_RDONLY | O_CLOEXEC);
    if (descriptor < 0)
        return 0;
    int valid = fstat(descriptor, &before) == 0 && S_ISREG(before.st_mode)
        && before.st_size == (off_t)HGN0202_ENGINE_BYTES;
    hgn_sha_init(&hash);
    while (valid) {
        ssize_t count = read(descriptor, buffer, sizeof(buffer));
        if (count < 0 && errno == EINTR)
            continue;
        if (count < 0) {
            valid = 0;
            break;
        }
        if (count == 0)
            break;
        bytes += (uint64_t)count;
        if (bytes > HGN0202_ENGINE_BYTES) {
            valid = 0;
            break;
        }
        hgn_sha_update(&hash, buffer, (unsigned)count);
    }
    hgn_sha_final(&hash, digest);
    valid = valid && bytes == HGN0202_ENGINE_BYTES
        && memcmp(digest, hgn0202_engine_sha, sizeof(digest)) == 0
        && fstat(descriptor, &after) == 0
        && before.st_dev == after.st_dev && before.st_ino == after.st_ino
        && before.st_size == after.st_size
        && before.st_mtim.tv_sec == after.st_mtim.tv_sec
        && before.st_mtim.tv_nsec == after.st_mtim.tv_nsec
        && before.st_ctim.tv_sec == after.st_ctim.tv_sec
        && before.st_ctim.tv_nsec == after.st_ctim.tv_nsec;
    if (close(descriptor) != 0)
        valid = 0;
    return valid;
}

static int locate_main(struct dl_phdr_info *info, size_t size, void *unused) {
    (void)unused;
    if (size < sizeof(*info) || !info->dlpi_name || info->dlpi_name[0])
        return 0;
    for (unsigned index = 0; index < HGN0202_PIN_COUNT; ++index) {
        const struct hgn0202_native_pin *pin = &hgn0202_pins[index];
        int executable = 0;
        for (unsigned member = 0; member < info->dlpi_phnum; ++member) {
            const ElfW(Phdr) *segment = &info->dlpi_phdr[member];
            executable |= segment->p_type == PT_LOAD && (segment->p_flags & PF_X)
                && pin->rva >= segment->p_vaddr
                && pin->rva + pin->bytes <= segment->p_vaddr + segment->p_filesz;
        }
        if (!executable || memcmp((const void *)(info->dlpi_addr + pin->rva),
                                  pin->original, pin->bytes) != 0)
            return 1;
    }
    image_base = info->dlpi_addr;
    image_found = 1;
    return 1;
}

static void *near_relay(uintptr_t target) {
    const uintptr_t page_mask = (uintptr_t)4095;
    uintptr_t aligned = target & ~page_mask;
    for (uintptr_t offset = 0x4000000; offset < 0x70000000; offset += 0x1000000) {
        uintptr_t hints[2] = {aligned + offset, aligned > offset ? aligned - offset : 0};
        for (unsigned side = 0; side < 2; ++side) {
            if (!hints[side])
                continue;
            void *page = mmap((void *)hints[side], 4096, PROT_READ | PROT_WRITE,
                              MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE, -1, 0);
            if (page == MAP_FAILED)
                continue;
            intptr_t delta = (intptr_t)page - (intptr_t)(target + 5);
            if (delta >= INT32_MIN && delta <= INT32_MAX)
                return page;
            (void)munmap(page, 4096);
        }
    }
    return MAP_FAILED;
}

static int socket_receiver(const char *path) {
    struct sockaddr_un address = {0};
    size_t length = strlen(path);
    if (strncmp(path, "/tmp/", 5) != 0 || length >= sizeof(address.sun_path))
        return -1;
    int descriptor = socket(AF_UNIX, SOCK_DGRAM | SOCK_NONBLOCK | SOCK_CLOEXEC, 0);
    if (descriptor < 0)
        return -1;
    address.sun_family = AF_UNIX;
    memcpy(address.sun_path, path, length + 1);
    if (bind(descriptor, (struct sockaddr *)&address,
             (socklen_t)(offsetof(struct sockaddr_un, sun_path) + length + 1)) != 0) {
        (void)close(descriptor);
        return -1;
    }
    return descriptor;
}

static struct hgn0202_stream_stats *statistics_page(const char *path) {
    if (strncmp(path, "/tmp/", 5) != 0)
        return MAP_FAILED;
    int descriptor = open(path, O_RDWR | O_CREAT | O_EXCL | O_CLOEXEC, 0600);
    if (descriptor < 0)
        return MAP_FAILED;
    void *mapped = MAP_FAILED;
    if (ftruncate(descriptor, 4096) == 0)
        mapped = mmap(NULL, 4096, PROT_READ | PROT_WRITE, MAP_SHARED, descriptor, 0);
    (void)close(descriptor);
    return mapped;
}

__attribute__((constructor)) static void initialize(void) {
    const char *enabled = getenv("HGN0202_EXTERNAL_STREAM");
    if (!enabled || strcmp(enabled, "1") != 0 || !engine_process())
        return;
    const char *socket_path = getenv("HGN0202_STREAM_SOCKET");
    const char *stats_path = getenv("HGN0202_STREAM_STATS");
    if (!socket_path || !stats_path || !exact_engine())
        fatal("HDO2 stream: exact engine and private paths required\n");
    (void)dl_iterate_phdr(locate_main, NULL);
    if (!image_found || sysconf(_SC_PAGESIZE) != 4096)
        fatal("HDO2 stream: native instruction or page binding differs\n");
    uintptr_t seam, fallback, consume;
    if (!hgn0202_cold_addresses(image_base, &seam, &fallback, &consume))
        fatal("HDO2 stream: generated native address roles differ\n");
    void *relay = near_relay(seam);
    int descriptor = socket_receiver(socket_path);
    struct hgn0202_stream_stats *statistics = statistics_page(stats_path);
    if (relay == MAP_FAILED || descriptor < 0 || statistics == MAP_FAILED)
        fatal("HDO2 stream: private relay or transport setup failed\n");
    if (!hgn0202_stream_configure(descriptor, 1, fallback, consume))
        fatal("HDO2 stream: consumer configuration failed\n");
    hgn0202_stream_bind_stats(statistics);
    const unsigned char indirect_jump[6] = {0xff, 0x25, 0, 0, 0, 0};
    uintptr_t entry = (uintptr_t)hgn0202_stream_relay;
    memcpy(relay, indirect_jump, sizeof(indirect_jump));
    memcpy((unsigned char *)relay + sizeof(indirect_jump), &entry, sizeof(entry));
    if (mprotect(relay, 4096, PROT_READ | PROT_EXEC) != 0)
        fatal("HDO2 stream: relay executable protection failed\n");
    unsigned char patch[7] = {0xe9, 0, 0, 0, 0, 0x90, 0x90};
    int32_t displacement = (int32_t)((intptr_t)relay - (intptr_t)(seam + 5));
    memcpy(patch + 1, &displacement, sizeof(displacement));
    void *page = (void *)(seam & ~(uintptr_t)4095);
    if (mprotect(page, 4096, PROT_READ | PROT_WRITE | PROT_EXEC) != 0)
        fatal("HDO2 stream: native patch protection failed\n");
    memcpy((void *)seam, patch, sizeof(patch));
    __builtin___clear_cache((char *)seam, (char *)seam + sizeof(patch));
    if (mprotect(page, 4096, PROT_READ | PROT_EXEC) != 0)
        fatal("HDO2 stream: native executable protection failed\n");
    static const char message[] = "HDO2 stream: exact0202 integer consumer active\n";
    ssize_t written = write(STDERR_FILENO, message, sizeof(message) - 1);
    (void)written;
}
