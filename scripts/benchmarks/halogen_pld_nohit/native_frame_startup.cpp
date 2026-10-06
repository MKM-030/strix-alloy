#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include "native_frame_startup.h"

#if !defined(__linux__) || !defined(__x86_64__)
#error "native frame startup requires Linux x86-64"
#endif

#include <cerrno>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fcntl.h>
#include <sched.h>
#include <signal.h>
#include <sys/auxv.h>
#include <sys/syscall.h>
#include <unistd.h>

#ifndef AT_MINSIGSTKSZ
#define AT_MINSIGSTKSZ 51
#endif

namespace halogen_nohit::frame_startup {
namespace {
constexpr std::uint64_t kCallbackBudget = 256;
constexpr unsigned kMaximumSignal = 64;
constexpr std::uint64_t kKernelDefault = 0;
constexpr std::uint64_t kKernelIgnore = 1;
StartupObservation observation{};
bool ready = false;

[[noreturn]] void fatal(const char* reason) noexcept {
    dprintf(STDERR_FILENO, "[nohit-frame-startup] fatal reason=%s errno=%d\n", reason, errno);
    _exit(78);
}

bool serving_process() noexcept {
    char executable[4096];
    const auto length = readlink("/proc/self/exe", executable, sizeof executable - 1);
    if (length <= 0 || length >= static_cast<ssize_t>(sizeof executable - 1)) {
        fatal("executable-name");
    }
    executable[length] = 0;
    const auto* slash = std::strrchr(executable, '/');
    if (std::strcmp(slash ? slash + 1 : executable, "flash_serve")) { return false; }
    const int fd = open("/proc/self/cmdline", O_RDONLY | O_CLOEXEC);
    if (fd < 0) { fatal("cmdline-open"); }
    char command[4096];
    ssize_t bytes = 0;
    do { bytes = read(fd, command, sizeof command); } while (bytes < 0 && errno == EINTR);
    const int close_result = close(fd);
    if (bytes <= 0 || bytes >= static_cast<ssize_t>(sizeof command) || close_result || command[bytes - 1]) {
        fatal("cmdline-read");
    }
    const auto* first_end = static_cast<const char*>(std::memchr(command, 0, static_cast<std::size_t>(bytes)));
    // Same serving-only convention as the frozen core; --resident-gib is stock.
    return first_end && first_end + 1 < command + bytes && !std::strcmp(first_end + 1, "--ck");
}

void actual_main_stack(StartupObservation& out) noexcept {
    if (syscall(SYS_gettid) != getpid()) { fatal("constructor-not-main-task"); }
    out.main_tid = static_cast<std::uint64_t>(getpid());
    FILE* file = fopen("/proc/self/maps", "re");
    if (!file) { fatal("stack-maps-open"); }
    char line[4096], permissions[5];
    unsigned matches = 0;
    while (fgets(line, sizeof line, file)) {
        if (!std::strchr(line, '\n') && !feof(file)) { fatal("stack-maps-line-length"); }
        unsigned long low = 0, high = 0, offset = 0, inode = 0;
        unsigned device_major = 0, device_minor = 0;
        int consumed = 0;
        if (std::sscanf(line, "%lx-%lx %4s %lx %x:%x %lu %n", &low, &high, permissions,
                        &offset, &device_major, &device_minor, &inode, &consumed) != 7 || consumed <= 0) {
            fatal("stack-maps-format");
        }
        auto* name = line + consumed;
        if (auto* newline = std::strchr(name, '\n')) { *newline = 0; }
        if (std::strcmp(name, "[stack]")) { continue; }
        if (++matches != 1 || low == 0 || low >= high || std::strcmp(permissions, "rw-p") ||
            offset || device_major || device_minor || inode || out.constructor_rsp < low ||
            out.constructor_rsp >= high || sizeof(std::uint64_t) > high - out.constructor_rsp) {
            fatal("actual-main-stack-mapping");
        }
        out.stack_low = low;
        out.stack_high = high;
    }
    const bool read_error = ferror(file) != 0;
    if (fclose(file) || read_error || matches != 1) { fatal("stack-maps-complete"); }
    // The complete actual VMA goes to the core. No RLIMIT/pthread reservation,
    // guessed stack size, alternate stack, stack growth or caller assertion.
}

// The Linux x86-64 kernel ABI includes libc-reserved signals in this query.
// libc sigaction() intentionally cannot inspect its reserved signal numbers.
struct KernelSignalAction {
    std::uint64_t handler{}, flags{}, restorer{}, mask{};
};
static_assert(sizeof(KernelSignalAction) == 32);

void startup_signal_budget(StartupObservation& out) noexcept {
    for (unsigned signal = 1; signal <= kMaximumSignal; ++signal) {
        if (signal == SIGKILL || signal == SIGSTOP) { continue; }
        KernelSignalAction action{};
        if (syscall(SYS_rt_sigaction, signal, nullptr, &action, sizeof action.mask)) {
            fatal("signal-action-query");
        }
        if (action.handler != kKernelDefault && action.handler != kKernelIgnore) {
            fatal("preexisting-custom-signal-handler");
        }
    }
    errno = 0;
    const auto minimum = getauxval(AT_MINSIGSTKSZ);
    // Main installs the same source-pinned leaf for SIGTERM and SIGINT with
    // flags=0 and an empty sa_mask. One can interrupt the other; the active
    // signal blocks itself. Budget two kernel frames, each plus a full red zone.
    // AT_MINSIGSTKSZ is kernel context space, not an arbitrary handler budget.
    constexpr auto maximum = frame_relay::kMaximumSignalReserve / 2 - HGN_RELAY_RED_ZONE;
    if (errno || minimum == 0 || minimum > maximum) { fatal("kernel-signal-stack-size"); }
    out.kernel_minimum_signal_stack = minimum;
    out.signal_reserve = 2 * (static_cast<std::uint64_t>(minimum) + HGN_RELAY_RED_ZONE);
    // A later foreign handler, SA_NODEFER, altstack/reentry policy or kernel
    // lacking this auxv is outside this source. No signal policy is changed.
}

void observe_cpu_affinity(StartupObservation& out) noexcept {
    cpu_set_t allowed{};
    if (sched_getaffinity(0, sizeof allowed, &allowed)) { fatal("main-affinity-query"); }
    static_assert(CPU_SETSIZE == 1024);
    const int current = sched_getcpu();
    if (current < 0 || current >= CPU_SETSIZE || !CPU_ISSET(current, &allowed)) {
        fatal("main-current-cpu");
    }
    out.startup_cpu = static_cast<std::uint32_t>(current);
    for (unsigned cpu = 0; cpu < CPU_SETSIZE; ++cpu) {
        if (!CPU_ISSET(cpu, &allowed)) { continue; }
        out.allowed_cpus[cpu / 64] |= std::uint64_t{1} << (cpu % 64);
        ++out.allowed_cpu_count;
    }
    if (!out.allowed_cpu_count) { fatal("main-affinity-empty"); }
    // Observation only. CPUID/XGETBV discovery in the frozen core qualifies
    // its startup CPU candidate, not all CPUs in this allowed set or migration.
}

__attribute__((constructor)) void guarded_preload_startup() noexcept {
    const auto* mode = std::getenv("HALOGEN_NOHIT_FRAME_INSTALL");
    if (!mode) { return; }
    if (!serving_process()) { return; }
    if (std::strcmp(mode, "register-stock-v1")) { fatal("installation-mode"); }

    StartupObservation next{};
    __asm__ volatile("movq %%rsp,%0" : "=r"(next.constructor_rsp));
    actual_main_stack(next);
    startup_signal_budget(next);
    observe_cpu_affinity(next);
    frame_relay::StartupRequest request{};
    request.enable = true;
    request.scope = frame_relay::XsaveScope::ArchitecturalUserState;
    request.registered_stack_low = next.stack_low;
    request.registered_stack_high = next.stack_high;
    request.callback_stack_budget = kCallbackBudget;
    request.signal_reserve = next.signal_reserve;
    next.result = frame_install::install_before_handler(request);
    if (next.result != frame_install::InstallResult::InstalledStockObserver) {
        fatal("constructor-install-result");
    }
    observation = next;
    __atomic_store_n(&ready, true, __ATOMIC_RELEASE);
}
} // namespace

bool copy_startup_observation(StartupObservation& out) noexcept {
    if (!__atomic_load_n(&ready, __ATOMIC_ACQUIRE)) { return false; }
    out = observation;
    return true;
}
} // namespace halogen_nohit::frame_startup
