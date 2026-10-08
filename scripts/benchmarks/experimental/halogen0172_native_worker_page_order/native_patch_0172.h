#ifndef PLE0172_NATIVE_PATCH_0172_H
#define PLE0172_NATIVE_PATCH_0172_H
#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif

#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <cerrno>
#include <climits>
#include <elf.h>
#include <fcntl.h>
#include <link.h>
#include <openssl/evp.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>

#if !defined(__linux__) || !defined(__x86_64__)
#error Exact Linux x86-64 Halogen 0.17.2 engine required
#endif

extern "C" {
__attribute__((visibility("hidden"))) void ple0172_native_launch_seam();
__attribute__((visibility("hidden"))) void ple0172_native_copy_seam();
__attribute__((visibility("hidden"))) void ple0172_native_complete_seam();
__attribute__((visibility("hidden"))) void ple0172_native_consumer_seam();
}

enum Ple0172NativeSeamIndex : unsigned {
    PLE0172_NATIVE_LAUNCH = 0,
    PLE0172_NATIVE_COPY = 1,
    PLE0172_NATIVE_COMPLETE = 2,
    PLE0172_NATIVE_CONSUMER = 3
};

struct Ple0172NativePatch {
    std::uintptr_t engine_base{};
    std::uintptr_t stock_replay[4]{};
};

namespace ple0172_native_patch_detail {
inline constexpr std::uint64_t engine_bytes = 26178504;
inline constexpr char engine_sha[] =
    "ac73b1df48510a34e0246a77bd984f1df0e02e5fa6cf1530d3d77c91d3c0e913";
struct Seam {
    std::uintptr_t rva;
    std::uintptr_t continuation_rva;
    std::size_t bytes;
    unsigned char expected[7];
};
inline constexpr Seam seams[4] = {
    {0x1801426, 0x180142d, 7, {0x48,0x63,0x85,0x70,0x07,0x00,0x00}},
    {0x1865ab4, 0x1865abb, 7, {0x4c,0x89,0xfb,0x49,0xc1,0xe7,0x04}},
    {0x1865d72, 0x1865d78, 6, {0x48,0x83,0x7c,0x24,0x10,0x00,0x00}},
    {0x17eec5b, 0x17eec62, 7, {0x48,0x63,0x8b,0x70,0x07,0x00,0x00}}
};
inline constexpr std::size_t page_bytes = 4096;
inline constexpr std::size_t relay_slot_bytes = 128;
inline constexpr std::size_t replay_offset = 64;

[[noreturn]] inline void fail(const char* reason) noexcept {
    dprintf(2, "[ple0172-native-page-order] abort %s errno=%d; no incomplete H2D\n",
            reason, errno);
    _exit(79);
}

inline bool readable_executable(const void* pointer, std::size_t bytes) noexcept {
    const auto address = reinterpret_cast<std::uintptr_t>(pointer);
    if (!address || !bytes || bytes > UINTPTR_MAX - address) return false;
    FILE* file = std::fopen("/proc/self/maps", "re");
    if (!file) return false;
    char line[4096], permissions[5];
    unsigned long low, high;
    bool found = false;
    while (std::fgets(line, sizeof line, file)) {
        if (std::sscanf(line, "%lx-%lx %4s", &low, &high, permissions) == 3 &&
            address >= low && address + bytes <= high &&
            permissions[0] == 'r' && permissions[1] == '-' && permissions[2] == 'x') {
            found = true;
            break;
        }
    }
    const bool error = std::ferror(file) != 0;
    const int closed = std::fclose(file);
    return found && !error && !closed;
}

inline int main_image(dl_phdr_info* info, std::size_t, void* opaque) noexcept {
    if (info->dlpi_name && *info->dlpi_name) return 0;
    unsigned covered = 0;
    for (const auto& seam : seams) {
        bool found = false;
        if (seam.continuation_rva != seam.rva + seam.bytes ||
            seam.continuation_rva > UINTPTR_MAX - info->dlpi_addr) return 0;
        for (std::size_t i = 0; i < info->dlpi_phnum; ++i) {
            const auto& p = info->dlpi_phdr[i];
            if (p.p_type != PT_LOAD || p.p_flags != (PF_R | PF_X) ||
                p.p_vaddr > seam.rva || p.p_filesz > UINT64_MAX - p.p_vaddr ||
                seam.continuation_rva > p.p_vaddr + p.p_filesz) continue;
            const auto delta = seam.rva - p.p_vaddr;
            if (delta > UINT64_MAX - p.p_offset ||
                p.p_offset + delta != seam.rva - 0x1000) continue;
            found = true;
            break;
        }
        covered += found;
    }
    if (covered != 4) return 0;
    *static_cast<std::uintptr_t*>(opaque) = info->dlpi_addr;
    return 1;
}

inline std::uintptr_t verify_engine() noexcept {
    const int fd = open("/proc/self/exe", O_RDONLY | O_CLOEXEC);
    struct stat before{}, after{};
    if (fd < 0 || fstat(fd, &before) || !S_ISREG(before.st_mode) ||
        before.st_size < 0 || std::uint64_t(before.st_size) != engine_bytes)
        fail("engine-stat");
    EVP_MD_CTX* context = EVP_MD_CTX_new();
    unsigned char buffer[65536], digest[32];
    unsigned length = 0;
    if (!context || EVP_DigestInit_ex(context, EVP_sha256(), nullptr) != 1)
        fail("hash-init");
    std::uint64_t copied = 0;
    while (copied < engine_bytes) {
        const auto remaining = engine_bytes - copied;
        const auto amount = remaining < sizeof buffer ? std::size_t(remaining) : sizeof buffer;
        const ssize_t got = pread(fd, buffer, amount, off_t(copied));
        if (got < 0 && errno == EINTR) continue;
        if (got <= 0 || std::size_t(got) > amount ||
            EVP_DigestUpdate(context, buffer, std::size_t(got)) != 1) fail("hash-read");
        copied += std::size_t(got);
    }
    if (EVP_DigestFinal_ex(context, digest, &length) != 1 || length != 32)
        fail("hash-end");
    EVP_MD_CTX_free(context);
    char actual[65];
    for (unsigned i = 0; i < 32; ++i) std::snprintf(actual + i * 2, 3, "%02x", digest[i]);
    if (std::strcmp(actual, engine_sha) || fstat(fd, &after) ||
        before.st_dev != after.st_dev || before.st_ino != after.st_ino ||
        before.st_size != after.st_size ||
        before.st_mtim.tv_sec != after.st_mtim.tv_sec ||
        before.st_mtim.tv_nsec != after.st_mtim.tv_nsec ||
        before.st_ctim.tv_sec != after.st_ctim.tv_sec ||
        before.st_ctim.tv_nsec != after.st_ctim.tv_nsec || close(fd)) fail("engine-changed");
    std::uintptr_t base{};
    if (dl_iterate_phdr(main_image, &base) != 1) fail("engine-load");
    for (const auto& seam : seams) {
        const auto* entry = reinterpret_cast<const void*>(base + seam.rva);
        if (!readable_executable(entry, seam.bytes) ||
            std::memcmp(entry, seam.expected, seam.bytes)) fail("seam-bytes");
    }
    return base;
}

inline void absolute_jump(unsigned char* buffer, std::uintptr_t target) noexcept {
    constexpr unsigned char opcode[6] = {0xff, 0x25, 0, 0, 0, 0};
    std::memcpy(buffer, opcode, sizeof opcode);
    std::memcpy(buffer + sizeof opcode, &target, sizeof target);
}

inline bool relative_displacement(std::uintptr_t after_jump, std::uintptr_t target,
                                  std::int32_t& displacement) noexcept {
    if (target >= after_jump) {
        const auto delta = target - after_jump;
        if (delta > std::uintptr_t(INT32_MAX)) return false;
        displacement = std::int32_t(delta);
    } else {
        const auto delta = after_jump - target;
        if (delta > std::uintptr_t(INT32_MAX) + 1) return false;
        displacement = std::int32_t(-std::int64_t(delta));
    }
    return true;
}
} // namespace ple0172_native_patch_detail

/* Call once from the opt-in preload constructor, before native workers start.
 * The caller owns enable/default selection. This helper accepts only the exact
 * primary engine image; bad pins or an incomplete installation terminate 79.
 * Replay blocks contain only complete, non-PC-relative native instructions.
 */
inline Ple0172NativePatch ple0172_install_native_patch() noexcept {
    using namespace ple0172_native_patch_detail;
    Ple0172NativePatch installed{};
    installed.engine_base = verify_engine();
    if (sysconf(_SC_PAGESIZE) != long(page_bytes)) fail("page-size");
    const std::uintptr_t wrappers[4] = {
        reinterpret_cast<std::uintptr_t>(&ple0172_native_launch_seam),
        reinterpret_cast<std::uintptr_t>(&ple0172_native_copy_seam),
        reinterpret_cast<std::uintptr_t>(&ple0172_native_complete_seam),
        reinterpret_cast<std::uintptr_t>(&ple0172_native_consumer_seam)
    };
    const auto anchor = (installed.engine_base + seams[0].rva) & ~std::uintptr_t(page_bytes - 1);
    unsigned char* relay = nullptr;
    for (unsigned i = 0; i < 256; ++i) {
        const auto distance = std::uintptr_t(i / 2 + 1) * 0x200000;
        if ((i & 1) ? anchor < distance : distance > UINTPTR_MAX - anchor) continue;
        const auto candidate = (i & 1) ? anchor - distance : anchor + distance;
        bool in_range = true;
        for (unsigned slot = 0; slot < 4; ++slot) {
            std::int32_t ignored{};
            if (candidate > UINTPTR_MAX - slot * relay_slot_bytes ||
                !relative_displacement(installed.engine_base + seams[slot].rva + 5,
                                       candidate + slot * relay_slot_bytes, ignored)) {
                in_range = false;
                break;
            }
        }
        if (!in_range) continue;
        void* area = mmap(reinterpret_cast<void*>(candidate), page_bytes, PROT_READ | PROT_WRITE,
                          MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE, -1, 0);
        if (area == MAP_FAILED) {
            if (errno == EEXIST) continue;
            fail("relay-map");
        }
        if (area != reinterpret_cast<void*>(candidate)) fail("relay-address");
        relay = static_cast<unsigned char*>(area);
        break;
    }
    if (!relay) fail("relay-exhausted");
    for (unsigned i = 0; i < 4; ++i) {
        auto* slot = relay + i * relay_slot_bytes;
        absolute_jump(slot, wrappers[i]);
        auto* replay = slot + replay_offset;
        std::memcpy(replay, seams[i].expected, seams[i].bytes);
        absolute_jump(replay + seams[i].bytes, installed.engine_base + seams[i].continuation_rva);
        installed.stock_replay[i] = reinterpret_cast<std::uintptr_t>(replay);
    }
    if (mprotect(relay, page_bytes, PROT_READ | PROT_EXEC)) fail("relay-rx");
    std::uintptr_t native_pages[4]{};
    unsigned page_count = 0;
    unsigned char patches[4][7];
    for (unsigned i = 0; i < 4; ++i) {
        const auto entry = installed.engine_base + seams[i].rva;
        if (!readable_executable(reinterpret_cast<void*>(entry), seams[i].bytes) ||
            std::memcmp(reinterpret_cast<void*>(entry), seams[i].expected, seams[i].bytes))
            fail("seam-changed");
        std::memset(patches[i], 0x90, sizeof patches[i]);
        patches[i][0] = 0xe9;
        std::int32_t displacement{};
        if (!relative_displacement(entry + 5,
                reinterpret_cast<std::uintptr_t>(relay + i * relay_slot_bytes), displacement))
            fail("relay-range");
        std::memcpy(patches[i] + 1, &displacement, sizeof displacement);
        const auto page = entry & ~std::uintptr_t(page_bytes - 1);
        if (entry - page + seams[i].bytes > page_bytes) fail("seam-crosses-page");
        bool seen = false;
        for (unsigned p = 0; p < page_count; ++p) seen |= native_pages[p] == page;
        if (!seen) native_pages[page_count++] = page;
    }
    for (unsigned p = 0; p < page_count; ++p)
        if (mprotect(reinterpret_cast<void*>(native_pages[p]), page_bytes, PROT_READ | PROT_WRITE))
            fail("seam-rw");
    for (unsigned i = 0; i < 4; ++i) {
        auto* entry = reinterpret_cast<unsigned char*>(installed.engine_base + seams[i].rva);
        std::memcpy(entry, patches[i], seams[i].bytes);
        __builtin___clear_cache(reinterpret_cast<char*>(entry),
                                reinterpret_cast<char*>(entry + seams[i].bytes));
    }
    for (unsigned p = 0; p < page_count; ++p)
        if (mprotect(reinterpret_cast<void*>(native_pages[p]), page_bytes, PROT_READ | PROT_EXEC))
            fail("seam-rx");
    for (unsigned i = 0; i < 4; ++i)
        if (std::memcmp(reinterpret_cast<void*>(installed.engine_base + seams[i].rva),
                        patches[i], seams[i].bytes)) fail("seam-write");
    return installed;
}

#endif // PLE0172_NATIVE_PATCH_0172_H
