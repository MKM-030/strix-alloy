#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include "native_frame_install.h"
#include "seam_contract.h"

#if !defined(__linux__) || !defined(__x86_64__)
#error "native frame installation requires Linux x86-64"
#endif

#include <asm/prctl.h>
#include <bit>
#include <cerrno>
#include <climits>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <dirent.h>
#include <elf.h>
#include <fcntl.h>
#include <link.h>
#include <openssl/evp.h>
#include <signal.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/sysmacros.h>
#include <unistd.h>

extern "C" {
// Defined by the exact-object linker fragment, not guessed function sizes.
extern const unsigned char __hgn_island_begin[], __hgn_island_end[];
extern const unsigned char __hgn_rx_begin[], __hgn_rx_end[], __hgn_code_end[];
extern const unsigned char __hgn_ro_begin[], __hgn_ro_end[];
extern const unsigned char __hgn_frames_begin[], __hgn_frames_end[];
extern const unsigned char __hgn_config_begin[], __hgn_config_end[];
extern const unsigned char __hgn_owned_begin[], __hgn_owned_end[];
extern const unsigned char halogen_nohit_installed_stock_delta[];
extern const unsigned char halogen_nohit_installed_observation[];
void __register_frame(void*);
struct HgnDwarfBases { void* text; void* data; void* function; };
const void* _Unwind_Find_FDE(const void*, HgnDwarfBases*);
}

namespace halogen_nohit::frame_install {
namespace {
constexpr std::size_t kPage = 4096;
constexpr off_t kEngineBytes = 26052768;
constexpr char kEngineSha[] = "ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b";
constexpr std::size_t kWindowBytes = 32;
constexpr std::size_t kMaximumIsland = 16 * kPage;
constexpr unsigned char kPad[9]{0xf3,0x0f,0x1e,0xfa,0xe9,0xde,0xc0,0x17,0x5a};
constexpr unsigned long kShadowStackStatus = 0x5005; // Linux UAPI ARCH_SHSTK_STATUS.
static_assert(kStockResumeRva == kSeamRva + kDisplacedLea.size());

struct OwnedRecord {
    std::uint32_t state{}, reserved{};
    frame_relay::RegisterImage registers{};
};
static_assert(offsetof(OwnedRecord, registers) == HGN_INSTALL_OBSERVATION_REGISTERS);
static_assert(sizeof(OwnedRecord) == HGN_INSTALL_OBSERVATION_BYTES);
static_assert(__atomic_always_lock_free(sizeof(std::uint32_t), nullptr));

struct Island {
    std::uintptr_t begin{}, end{}, rx_end{}, code_end{}, ro_end{}, config_end{};
    std::uintptr_t frames{}, frames_end{}, configuration{}, observation{}, observer{}, pad{}, delta{};
};
bool installed = false;
void* retained_mapping = nullptr; // Permanent until process exit: never hot-unmap.
OwnedRecord* retained_record = nullptr;

[[noreturn]] void fatal(const char* reason) noexcept {
    dprintf(STDERR_FILENO, "[nohit-frame-install] fatal reason=%s errno=%d\n", reason, errno);
    _exit(78);
}
std::uintptr_t address(const void* value) noexcept { return reinterpret_cast<std::uintptr_t>(value); }
bool span(std::uintptr_t begin, std::size_t bytes, std::uintptr_t low, std::uintptr_t high) noexcept {
    return begin >= low && begin <= high && bytes <= high - begin;
}
bool relative(std::uintptr_t target, std::uintptr_t after, std::int32_t& out) noexcept {
    const auto difference = target >= after ? target - after : after - target;
    const auto limit = target >= after ? std::uint64_t{INT32_MAX} : std::uint64_t{INT32_MAX} + 1;
    if (difference > limit) { return false; }
    out = static_cast<std::int32_t>(target >= after ? static_cast<std::int64_t>(difference)
                                                   : -static_cast<std::int64_t>(difference));
    return true;
}
std::uint32_t u32(const unsigned char* bytes) noexcept {
    std::uint32_t out = 0;
    std::memcpy(&out, bytes, sizeof out);
    return out;
}
bool same_file(const struct stat& a, const struct stat& b) noexcept {
    return a.st_dev == b.st_dev && a.st_ino == b.st_ino && a.st_mode == b.st_mode && a.st_size == b.st_size &&
        a.st_mtim.tv_sec == b.st_mtim.tv_sec && a.st_mtim.tv_nsec == b.st_mtim.tv_nsec &&
        a.st_ctim.tv_sec == b.st_ctim.tv_sec && a.st_ctim.tv_nsec == b.st_ctim.tv_nsec;
}
bool mapped(std::uintptr_t start, std::size_t bytes, const char* permissions,
            const struct stat* identity = nullptr, std::uint64_t file_offset = 0) noexcept {
    if (!start || !bytes || bytes > UINTPTR_MAX - start) { return false; }
    FILE* file = fopen("/proc/self/maps", "re");
    if (!file) { return false; }
    char line[4096], perms[5];
    unsigned long low = 0, high = 0, offset = 0, inode = 0;
    unsigned int device_major = 0, device_minor = 0;
    bool found = false;
    while (fgets(line, sizeof line, file)) {
        if (std::sscanf(line, "%lx-%lx %4s %lx %x:%x %lu", &low, &high, perms,
                        &offset, &device_major, &device_minor, &inode) != 7) { continue; }
        if (!span(start, bytes, low, high)) { continue; }
        if (permissions ? std::strcmp(perms, permissions) != 0 : perms[0] != 'r') { break; }
        if (identity && (inode != identity->st_ino || device_major != major(identity->st_dev) ||
            device_minor != minor(identity->st_dev) || file_offset != offset + (start - low))) { break; }
        found = true;
        break;
    }
    if (ferror(file)) { found = false; }
    if (fclose(file)) { return false; }
    return found;
}
void read_exact(int fd, void* target, std::size_t bytes, off_t offset) noexcept {
    auto* at = static_cast<unsigned char*>(target);
    while (bytes) {
        const auto got = pread(fd, at, bytes, offset);
        if (got < 0 && errno == EINTR) { continue; }
        if (got <= 0) { fatal("executable-read"); }
        at += got; bytes -= static_cast<std::size_t>(got); offset += got;
    }
}
bool serving_process() noexcept {
    char name[4096];
    const auto n = readlink("/proc/self/exe", name, sizeof name - 1);
    if (n <= 0 || n >= static_cast<ssize_t>(sizeof name - 1)) { fatal("executable-name"); }
    name[n] = 0;
    const auto* base = std::strrchr(name, '/');
    if (std::strcmp(base ? base + 1 : name, "flash_serve") != 0) { return false; }
    const int fd = open("/proc/self/cmdline", O_RDONLY | O_CLOEXEC);
    if (fd < 0) { fatal("cmdline-open"); }
    char command[4096];
    ssize_t bytes = 0;
    do { bytes = read(fd, command, sizeof command); } while (bytes < 0 && errno == EINTR);
    if (bytes <= 0 || bytes >= static_cast<ssize_t>(sizeof command) || command[bytes - 1] || close(fd)) {
        fatal("cmdline-read");
    }
    const auto* argument = static_cast<const char*>(std::memchr(command, 0, static_cast<std::size_t>(bytes)));
    // Match the existing preload convention: --resident-gib inspection is stock.
    return argument && argument + 1 < command + bytes && std::strcmp(argument + 1, "--ck") == 0;
}
void one_thread() noexcept {
    if (syscall(SYS_gettid) != getpid()) { fatal("startup-not-main-thread"); }
    DIR* directory = opendir("/proc/self/task");
    if (!directory) { fatal("task-directory"); }
    unsigned count = 0;
    errno = 0;
    while (const auto* entry = readdir(directory)) {
        if (entry->d_name[0] == '.') { continue; }
        if (++count > 1) { fatal("startup-not-single-threaded"); }
    }
    if (errno || closedir(directory) || count != 1) { fatal("startup-task-count"); }
}
void inactive_shadow_stack() noexcept {
    unsigned long features = 0;
    if (syscall(SYS_arch_prctl, kShadowStackStatus, &features) == 0) {
        if (features != 0) { fatal("active-cet-shadow-stack"); }
    } else if (errno != EINVAL && errno != ENOSYS && errno != EOPNOTSUPP) {
        fatal("cet-status-unknown");
    }
    // Unsupported STATUS is not a new CET/state qualification. Root must pin
    // actual kernel/loader/CET behavior; this refuses observed active SHSTK.
}
struct Target { std::uintptr_t site{}, page{}; std::uint64_t offset{}; unsigned count{}; };
int main_headers(dl_phdr_info* info, std::size_t, void* opaque) noexcept {
    if (info->dlpi_name && info->dlpi_name[0]) { return 0; }
    auto& target = *static_cast<Target*>(opaque);
    if (kSeamRva > UINTPTR_MAX - info->dlpi_addr) { fatal("engine-base-overflow"); }
    const auto site = info->dlpi_addr + kSeamRva;
    for (std::size_t i = 0; i < info->dlpi_phnum; ++i) {
        const auto& p = info->dlpi_phdr[i];
        if (p.p_type != PT_LOAD || p.p_flags != (PF_R | PF_X)) { continue; }
        if (p.p_vaddr > UINTPTR_MAX - info->dlpi_addr || p.p_memsz > UINTPTR_MAX - (info->dlpi_addr + p.p_vaddr) ||
            p.p_filesz > UINT64_MAX - p.p_vaddr) { fatal("engine-segment-overflow"); }
        if (!span(site, kWindowBytes, info->dlpi_addr + p.p_vaddr, info->dlpi_addr + p.p_vaddr + p.p_memsz) ||
            !span(kSeamRva, kWindowBytes, p.p_vaddr, p.p_vaddr + p.p_filesz)) { continue; }
        if (p.p_offset > UINT64_MAX - (kSeamRva - p.p_vaddr)) { fatal("engine-offset-overflow"); }
        target = {site, site & ~(kPage - 1), p.p_offset + kSeamRva - p.p_vaddr, target.count + 1};
    }
    return 1;
}
struct stat verify_engine(Target& target) noexcept {
    struct stat first{}, last{};
    const int fd = open("/proc/self/exe", O_RDONLY | O_CLOEXEC);
    if (fd < 0 || fstat(fd, &first) || !S_ISREG(first.st_mode) || first.st_size != kEngineBytes) {
        fatal("executable-stat");
    }
    Elf64_Ehdr header{};
    read_exact(fd, &header, sizeof header, 0);
    if (std::memcmp(header.e_ident, ELFMAG, SELFMAG) || header.e_ident[EI_CLASS] != ELFCLASS64 ||
        header.e_ident[EI_DATA] != ELFDATA2LSB || header.e_machine != EM_X86_64 || header.e_type != ET_DYN ||
        header.e_phentsize != sizeof(Elf64_Phdr) || !header.e_phnum) { fatal("elf-identity"); }
    EVP_MD_CTX* context = EVP_MD_CTX_new();
    if (!context || EVP_DigestInit_ex(context, EVP_sha256(), nullptr) != 1) { fatal("digest-init"); }
    unsigned char buffer[65536], digest[EVP_MAX_MD_SIZE];
    off_t offset = 0;
    while (offset < first.st_size) {
        const auto left = static_cast<std::uint64_t>(first.st_size - offset);
        const auto wanted = left < sizeof buffer ? static_cast<std::size_t>(left) : sizeof buffer;
        read_exact(fd, buffer, wanted, offset);
        if (EVP_DigestUpdate(context, buffer, wanted) != 1) { fatal("digest-update"); }
        offset += static_cast<off_t>(wanted);
    }
    unsigned length = 0;
    if (EVP_DigestFinal_ex(context, digest, &length) != 1 || length != 32) { fatal("digest-final"); }
    EVP_MD_CTX_free(context);
    char hex[65];
    for (std::size_t i = 0; i < 32; ++i) { std::snprintf(hex + 2 * i, 3, "%02x", digest[i]); }
    if (std::strcmp(hex, kEngineSha)) { fatal("elf-sha256"); }
    if (dl_iterate_phdr(main_headers, &target) != 1 || target.count != 1 ||
        target.offset != kSeamRva - 0x1000 || !span(target.site, kWindowBytes, target.page, target.page + kPage) ||
        !mapped(target.site, kWindowBytes, "r-xp", &first, target.offset) ||
        !mapped(target.page, kPage, "r-xp")) { fatal("engine-site-mapping"); }
    unsigned char window[kWindowBytes];
    read_exact(fd, window, sizeof window, static_cast<off_t>(target.offset));
    if (std::memcmp(window, kDisplacedLea.data(), kDisplacedLea.size()) ||
        std::memcmp(reinterpret_cast<const void*>(target.site), window, sizeof window)) {
        fatal("nohit-instruction-window");
    }
    if (fstat(fd, &last) || !same_file(first, last) || close(fd)) { fatal("executable-consistency"); }
    return first;
}
bool in_module(const dl_phdr_info& info, std::uintptr_t location, std::size_t bytes) noexcept {
    for (std::size_t i = 0; i < info.dlpi_phnum; ++i) {
        const auto& p = info.dlpi_phdr[i];
        if (p.p_type == PT_LOAD && (p.p_flags & PF_R) && p.p_vaddr <= UINTPTR_MAX - info.dlpi_addr &&
            p.p_memsz <= UINTPTR_MAX - (info.dlpi_addr + p.p_vaddr) &&
            span(location, bytes, info.dlpi_addr + p.p_vaddr, info.dlpi_addr + p.p_vaddr + p.p_memsz)) { return true; }
    }
    return false;
}
std::uintptr_t dynamic_pointer(const dl_phdr_info& info, std::uintptr_t value, std::size_t bytes) noexcept {
    if (in_module(info, value, bytes)) { return value; }
    if (value <= UINTPTR_MAX - info.dlpi_addr && in_module(info, info.dlpi_addr + value, bytes)) {
        return info.dlpi_addr + value;
    }
    fatal("payload-dynamic-pointer");
}
void check_relocations(const dl_phdr_info& info, std::uintptr_t table, std::size_t bytes,
                       const Island& island) noexcept {
    if (!bytes) { return; }
    if (!table || bytes % sizeof(Elf64_Rela) || bytes / sizeof(Elf64_Rela) > 65536) { fatal("payload-rela-table"); }
    const auto at = dynamic_pointer(info, table, bytes);
    if (!mapped(at, bytes, nullptr)) { fatal("payload-rela-mapping"); }
    const auto* entries = reinterpret_cast<const Elf64_Rela*>(at);
    for (std::size_t i = 0; i < bytes / sizeof(Elf64_Rela); ++i) {
        if (entries[i].r_offset > UINTPTR_MAX - info.dlpi_addr) { fatal("payload-relocation-overflow"); }
        const auto destination = info.dlpi_addr + entries[i].r_offset;
        if (destination >= island.begin && destination < island.end) { fatal("dynamic-relocation-in-island"); }
    }
}
struct PayloadCheck { const Island* island{}; unsigned count{}; };
int payload_headers(dl_phdr_info* info, std::size_t, void* opaque) noexcept {
    auto& check = *static_cast<PayloadCheck*>(opaque);
    if (!in_module(*info, check.island->begin, 1)) { return 0; }
    if (!info->dlpi_name || !info->dlpi_name[0]) { fatal("payload-must-be-preload-dso"); }
    check.count++;
    std::uintptr_t rela = 0, plt = 0;
    std::size_t rela_bytes = 0, plt_bytes = 0;
    std::uint64_t rela_size = 0, plt_kind = DT_RELA;
    bool dynamic_found = false;
    for (std::size_t i = 0; i < info->dlpi_phnum; ++i) {
        const auto& p = info->dlpi_phdr[i];
        if (p.p_type != PT_DYNAMIC) { continue; }
        if (dynamic_found || p.p_vaddr > UINTPTR_MAX - info->dlpi_addr || p.p_memsz > 65536 ||
            p.p_memsz % sizeof(Elf64_Dyn)) { fatal("payload-dynamic-header"); }
        const auto location = info->dlpi_addr + p.p_vaddr;
        if (!in_module(*info, location, p.p_memsz) || !mapped(location, p.p_memsz, nullptr)) { fatal("payload-dynamic-mapping"); }
        const auto* dynamic = reinterpret_cast<const Elf64_Dyn*>(location);
        bool terminated = false;
        for (std::size_t n = 0; n < p.p_memsz / sizeof(Elf64_Dyn); ++n) {
            const auto& d = dynamic[n];
            if (d.d_tag == DT_NULL) { terminated = true; break; }
            switch (d.d_tag) {
            case DT_RELA: rela = d.d_un.d_ptr; break;
            case DT_RELASZ: rela_bytes = d.d_un.d_val; break;
            case DT_RELAENT: rela_size = d.d_un.d_val; break;
            case DT_JMPREL: plt = d.d_un.d_ptr; break;
            case DT_PLTRELSZ: plt_bytes = d.d_un.d_val; break;
            case DT_PLTREL: plt_kind = d.d_un.d_val; break;
            case DT_TEXTREL: fatal("payload-textrel");
            case DT_FLAGS:
                if (d.d_un.d_val & DF_TEXTREL) { fatal("payload-textrel-flag"); }
                break;
            case DT_REL: case DT_RELSZ: case DT_RELENT:
            case 35: case 36: case 37: // DT_RELRSZ/DT_RELR/DT_RELRENT: deliberately unsupported.
                if (d.d_un.d_val) { fatal("payload-non-rela-relocations"); }
                break;
            default: break;
            }
        }
        if (!terminated) { fatal("payload-dynamic-unterminated"); }
        dynamic_found = true;
    }
    if (!dynamic_found || (rela_bytes && rela_size != sizeof(Elf64_Rela)) || (plt_bytes && plt_kind != DT_RELA)) {
        fatal("payload-relocation-format");
    }
    check_relocations(*info, rela, rela_bytes, *check.island);
    check_relocations(*info, plt, plt_bytes, *check.island);
    return 1;
}
void verify_frames(const Island& island) noexcept {
    // Exact simple GNU CIE: version1,zR, code-align1,data-align-8,RIP16,
    // one augmentation byte DW_EH_PE_pcrel|sdata4. No personality/LSDA/GOT.
    constexpr unsigned char cie_prefix[9]{1,'z','R',0,1,0x78,16,1,0x1b};
    bool relay = false, observer = false, pad = false;
    unsigned fdes = 0;
    auto at = island.frames;
    while (span(at, 4, island.frames, island.frames_end)) {
        const auto* bytes = reinterpret_cast<const unsigned char*>(at);
        const auto length = u32(bytes);
        if (!length) {
            if (at + 4 != island.frames_end || fdes != 3 || !relay || !observer || !pad) { fatal("payload-frame-terminator"); }
            return;
        }
        if (length == UINT32_MAX || length < 13 || !span(at, std::size_t{length} + 4, island.frames, island.frames_end)) {
            fatal("payload-frame-length");
        }
        const auto id = u32(bytes + 4);
        if (!id) {
            if (std::memcmp(bytes + 8, cie_prefix, sizeof cie_prefix)) { fatal("payload-cie-format"); }
        } else {
            if (id > at + 4 - island.frames) { fatal("payload-fde-cie"); }
            const auto cie = at + 4 - id;
            if (!span(cie, 17, island.frames, at) || u32(reinterpret_cast<const unsigned char*>(cie) + 4) != 0 ||
                std::memcmp(reinterpret_cast<const unsigned char*>(cie) + 8, cie_prefix, sizeof cie_prefix)) {
                fatal("payload-fde-cie-reference");
            }
            const auto delta = std::bit_cast<std::int32_t>(u32(bytes + 8));
            const auto base = at + 8;
            if ((delta < 0 && static_cast<std::uint64_t>(-std::int64_t{delta}) > base) ||
                (delta >= 0 && static_cast<std::uint64_t>(delta) > UINTPTR_MAX - base)) { fatal("payload-fde-pc-overflow"); }
            const auto begin = delta < 0 ? base - static_cast<std::uint64_t>(-std::int64_t{delta}) : base + delta;
            const auto extent = u32(bytes + 12);
            if (!extent || bytes[16] != 0 || !span(begin, extent, island.begin, island.code_end)) { fatal("payload-fde-range"); }
            relay |= span(island.begin, 1, begin, begin + extent);
            observer |= span(island.observer, 1, begin, begin + extent);
            pad |= span(island.pad, 1, begin, begin + extent);
            ++fdes;
        }
        at += std::size_t{length} + 4;
    }
    fatal("payload-frames-missing-terminator");
}
Island original_island() noexcept {
    Island result{address(__hgn_island_begin), address(__hgn_island_end), address(__hgn_rx_end), address(__hgn_code_end),
        address(__hgn_ro_end), address(__hgn_config_end), address(__hgn_frames_begin), address(__hgn_frames_end),
        address(&halogen_nohit_relay_configuration), address(halogen_nohit_installed_observation),
        reinterpret_cast<std::uintptr_t>(halogen_nohit_frame_observer),
        reinterpret_cast<std::uintptr_t>(halogen_nohit_native_stock_resume), address(halogen_nohit_installed_stock_delta)};
    if (sysconf(_SC_PAGESIZE) != static_cast<long>(kPage) || result.begin != address(__hgn_rx_begin) ||
        result.rx_end != address(__hgn_ro_begin) || result.ro_end != address(__hgn_config_begin) ||
        result.config_end != address(__hgn_owned_begin) || result.end != address(__hgn_owned_end) ||
        result.begin >= result.code_end || result.code_end > result.rx_end || result.rx_end >= result.ro_end ||
        result.ro_end >= result.config_end || result.config_end >= result.end || result.end - result.begin > kMaximumIsland ||
        (result.begin | result.rx_end | result.ro_end | result.config_end | result.end) % kPage != 0 ||
        reinterpret_cast<std::uintptr_t>(halogen_nohit_native_frame_relay) != result.begin ||
        !span(result.configuration, sizeof(frame_relay::RelayConfiguration), result.ro_end, result.config_end) ||
        result.observation != result.config_end || !span(result.observation, sizeof(OwnedRecord), result.config_end, result.end) ||
        !span(result.observer, 4, result.begin, result.code_end) || !span(result.pad, sizeof kPad, result.begin, result.code_end) ||
        result.delta != result.pad + 5 || result.frames_end <= result.frames ||
        !span(result.frames, result.frames_end - result.frames, result.rx_end, result.ro_end)) {
        fatal("payload-layout");
    }
    if (!mapped(result.begin, result.rx_end - result.begin, "r-xp") ||
        !mapped(result.rx_end, result.ro_end - result.rx_end, nullptr) ||
        !mapped(result.ro_end, result.config_end - result.ro_end, nullptr) ||
        !mapped(result.config_end, result.end - result.config_end, "rw-p") ||
        std::memcmp(reinterpret_cast<const void*>(result.begin), kPad, 4) ||
        std::memcmp(reinterpret_cast<const void*>(result.observer), kPad, 4) ||
        std::memcmp(reinterpret_cast<const void*>(result.pad), kPad, sizeof kPad) ||
        u32(reinterpret_cast<const unsigned char*>(result.rx_end)) != 0x1f80) { fatal("payload-template"); }
    const OwnedRecord empty{};
    if (std::memcmp(reinterpret_cast<const void*>(result.observation), &empty, sizeof empty)) { fatal("payload-observation-not-empty"); }
    PayloadCheck check{&result, 0};
    if (dl_iterate_phdr(payload_headers, &check) != 1 || check.count != 1) { fatal("payload-module"); }
    verify_frames(result);
    return result;
}
Island move_island(const Island& original, std::uintptr_t next) noexcept {
    Island copy = original;
    auto translate = [&](std::uintptr_t value) { return next + (value - original.begin); };
    copy.begin = next; copy.end = translate(original.end); copy.rx_end = translate(original.rx_end);
    copy.code_end = translate(original.code_end); copy.ro_end = translate(original.ro_end); copy.config_end = translate(original.config_end);
    copy.frames = translate(original.frames); copy.frames_end = translate(original.frames_end);
    copy.configuration = translate(original.configuration); copy.observation = translate(original.observation);
    copy.observer = translate(original.observer); copy.pad = translate(original.pad); copy.delta = translate(original.delta);
    return copy;
}
Island allocate_near(const Island& original, const Target& target) noexcept {
    const auto bytes = original.end - original.begin;
    for (unsigned i = 0; i < 256; ++i) {
        const auto distance = std::uintptr_t{i / 2 + 1} * 0x200000;
        if ((i & 1) ? target.page < distance : distance > UINTPTR_MAX - target.page) { continue; }
        const auto candidate = (i & 1) ? target.page - distance : target.page + distance;
        if (!candidate || bytes > UINTPTR_MAX - candidate) { continue; }
        const auto relocated = move_island(original, candidate);
        std::int32_t entry_delta = 0, stock_delta = 0;
        if (!relative(relocated.begin, target.site + 5, entry_delta) ||
            !relative(target.site + kDisplacedLea.size(), relocated.pad + 9, stock_delta)) { continue; }
        void* area = mmap(reinterpret_cast<void*>(candidate), bytes, PROT_READ | PROT_WRITE,
            MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE, -1, 0);
        if (area == MAP_FAILED) { if (errno == EEXIST) { continue; } fatal("near-island-map"); }
        if (area != reinterpret_cast<void*>(candidate)) { fatal("fixed-noreplace-unsupported"); }
        if (!mapped(candidate, bytes, "rw-p")) { fatal("near-island-rw"); }
        std::memcpy(area, reinterpret_cast<const void*>(original.begin), bytes);
        std::memcpy(reinterpret_cast<void*>(relocated.delta), &stock_delta, sizeof stock_delta);
        return relocated;
    }
    fatal("near-island-exhausted");
}
void publish_island(const Island& copy, const frame_relay::RelayConfiguration& candidate) noexcept {
    std::memcpy(reinterpret_cast<void*>(copy.configuration), &candidate, sizeof candidate);
    verify_frames(copy);
    __builtin___clear_cache(reinterpret_cast<char*>(copy.begin), reinterpret_cast<char*>(copy.rx_end));
    if (mprotect(reinterpret_cast<void*>(copy.begin), copy.rx_end - copy.begin, PROT_READ | PROT_EXEC) ||
        mprotect(reinterpret_cast<void*>(copy.rx_end), copy.ro_end - copy.rx_end, PROT_READ) ||
        mprotect(reinterpret_cast<void*>(copy.ro_end), copy.config_end - copy.ro_end, PROT_READ) ||
        !mapped(copy.begin, copy.rx_end - copy.begin, "r-xp") ||
        !mapped(copy.rx_end, copy.ro_end - copy.rx_end, "r--p") ||
        !mapped(copy.ro_end, copy.config_end - copy.ro_end, "r--p") ||
        !mapped(copy.config_end, copy.end - copy.config_end, "rw-p")) { fatal("island-final-permissions"); }
    __register_frame(reinterpret_cast<void*>(copy.frames));
    const std::array<std::uintptr_t, 3> pcs{copy.begin, copy.observer, copy.pad};
    for (const auto pc : pcs) {
        HgnDwarfBases bases{};
        const auto fde = address(_Unwind_Find_FDE(reinterpret_cast<const void*>(pc), &bases));
        if (!span(fde, 17, copy.frames, copy.frames_end) || address(bases.function) != pc) { fatal("copied-frame-registration"); }
    }
}
} // namespace

InstallResult install_before_handler(const frame_relay::StartupRequest& request) noexcept {
    if (!request.enable) { return InstallResult::Disabled; }
    const auto* mode = std::getenv("HALOGEN_NOHIT_FRAME_INSTALL");
    if (!mode) { return InstallResult::Disabled; }
    if (std::strcmp(mode, "register-stock-v1")) { fatal("installation-mode"); }
    if (__atomic_load_n(&installed, __ATOMIC_ACQUIRE)) { return InstallResult::AlreadyInstalled; }
    if (!serving_process()) { return InstallResult::Disabled; }

    // Startup quiescence is concrete: block catchable signals on the only task
    // for hash/mapping/frame publication and the complete seven-byte patch.
    // This is not an exclusion policy for later native serving/capture.
    // Kernel rt_sigprocmask also blocks libc-reserved catchable signals. Linux
    // x86-64 uses the eight-byte kernel signal mask; SIGKILL/STOP stay unblockable.
    const std::uint64_t all = UINT64_MAX;
    std::uint64_t previous = 0;
    if (syscall(SYS_rt_sigprocmask, SIG_BLOCK, &all, &previous, sizeof previous)) { fatal("startup-signal-block"); }
    one_thread();
    inactive_shadow_stack();
    std::uintptr_t startup_rsp = 0;
    __asm__ volatile("movq %%rsp,%0" : "=r"(startup_rsp));
    if (request.registered_stack_low >= request.registered_stack_high ||
        !span(startup_rsp, sizeof(std::uint64_t), request.registered_stack_low, request.registered_stack_high) ||
        !mapped(request.registered_stack_low, request.registered_stack_high - request.registered_stack_low, "rw-p")) {
        fatal("registered-owner-stack-mapping");
    }
    frame_relay::RelayConfiguration candidate{};
    if (frame_relay::discover_configuration(request, candidate) != frame_relay::ConfigurationResult::ArchitecturalCandidate) {
        fatal("relay-configuration");
    }
    Target target{};
    const auto identity = verify_engine(target);
    const auto original = original_island();
    const auto copy = allocate_near(original, target);
    publish_island(copy, candidate);
    one_thread();
    if (!mapped(target.site, kDisplacedLea.size(), "r-xp", &identity, target.offset) ||
        !mapped(target.page, kPage, "r-xp") ||
        std::memcmp(reinterpret_cast<const void*>(target.site), kDisplacedLea.data(), kDisplacedLea.size())) {
        fatal("site-changed-before-patch");
    }
    std::int32_t delta = 0;
    if (!relative(copy.begin, target.site + 5, delta)) { fatal("direct-entry-range"); }
    unsigned char jump[7]{0xe9,0,0,0,0,0x90,0x90};
    std::memcpy(jump + 1, &delta, sizeof delta);
    // No RWX phase and no concurrent entry; incomplete installation is fatal.
    if (mprotect(reinterpret_cast<void*>(target.page), kPage, PROT_READ | PROT_WRITE)) { fatal("site-rw"); }
    std::memcpy(reinterpret_cast<void*>(target.site), jump, sizeof jump);
    __builtin___clear_cache(reinterpret_cast<char*>(target.site), reinterpret_cast<char*>(target.site + sizeof jump));
    if (mprotect(reinterpret_cast<void*>(target.page), kPage, PROT_READ | PROT_EXEC) ||
        !mapped(target.page, kPage, "r-xp") || std::memcmp(reinterpret_cast<const void*>(target.site), jump, sizeof jump)) {
        fatal("site-patch-rx");
    }
    retained_mapping = reinterpret_cast<void*>(copy.begin);
    retained_record = reinterpret_cast<OwnedRecord*>(copy.observation);
    __atomic_store_n(&installed, true, __ATOMIC_RELEASE);
    if (syscall(SYS_rt_sigprocmask, SIG_SETMASK, &previous, nullptr, sizeof previous)) { fatal("startup-signal-restore"); }
    return InstallResult::InstalledStockObserver;
}

bool copy_first_register_observation(frame_relay::RegisterImage& out) noexcept {
    if (!__atomic_load_n(&installed, __ATOMIC_ACQUIRE) || retained_mapping == nullptr ||
        __atomic_load_n(&retained_record->state, __ATOMIC_ACQUIRE) != 2) { return false; }
    out = retained_record->registers;
    return true;
}
} // namespace halogen_nohit::frame_install
