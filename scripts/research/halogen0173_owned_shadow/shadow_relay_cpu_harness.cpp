#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include "shadow_relay.h"

#include <algorithm>
#include <alloca.h>
#include <atomic>
#include <cerrno>
#include <climits>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <iterator>
#include <pthread.h>
#include <sys/mman.h>
#include <unistd.h>

// Standalone CPU qualifier; do not link shadow_install.cpp or load the engine.
// Build shadow_relay.S as exact basename shadow_relay.o, then link that object,
// this file and shadow_relay_cpu_harness.S with shadow_relay.ld, -std=c++20,
// -fcf-protection=branch -pthread -lgcc_s. Inspect linked code/frames before run.
// This source does not launch, build, preload, install or qualify native serving.
using halogen_shadow::relay::Configuration;
using halogen_shadow::relay::Frame;
constexpr std::size_t kAreaBytes = 65536;
struct ProbeStackBounds { std::uint64_t low, high; };

extern "C" {
__thread ProbeStackBounds hgn_probe_stack __attribute__((tls_model("initial-exec"))) = {};
alignas(64) unsigned char hgn_probe_before_xsave[kAreaBytes]{};
alignas(64) unsigned char hgn_probe_after_xsave[kAreaBytes]{};
alignas(64) unsigned char hgn_probe_caller_xsave[kAreaBytes]{};
alignas(64) unsigned char hgn_probe_seed_xsave[kAreaBytes]{};
alignas(64) unsigned char hgn_probe_poison_xsave[kAreaBytes]{};
alignas(64) unsigned char hgn_probe_poison_snapshot[kAreaBytes]{};
Frame hgn_probe_before{}, hgn_probe_after{}, hgn_probe_callback_frame{};
std::uint64_t hgn_probe_patterns[16]{}, hgn_probe_red_zone[16]{};
std::uint64_t hgn_probe_mask{}, hgn_probe_target{}, hgn_probe_callbacks{};
std::uint32_t hgn_probe_branch{}, hgn_probe_callback_site{};
void hgn_shadow_probe_run() noexcept;
void hgn_shadow_probe_stock() noexcept;
void hgn_shadow_probe_taken() noexcept;
void hgn_shadow_probe_fallthrough() noexcept;
void hgn_shadow_probe_poison() noexcept;
void __register_frame(void*);
void* __deregister_frame(const void*);
struct ProbeDwarfBases { void* text; void* data; void* function; };
const void* _Unwind_Find_FDE(const void*, ProbeDwarfBases*);
extern const unsigned char hgn_shadow_island_begin[], hgn_shadow_island_end[];
extern const unsigned char hgn_shadow_island_frames[], hgn_shadow_island_frames_end[];
}

extern "C" __attribute__((visibility("hidden"), noinline))
void hgn_shadow_probe_callback(std::uint32_t site, const Frame* frame) noexcept {
    const int saved = errno;
    ++hgn_probe_callbacks;
    hgn_probe_callback_site = site;
    hgn_probe_callback_frame = *frame;
    errno = ERANGE;
    hgn_shadow_probe_poison(); // Real full-mask XRSTOR and GPR/flag poisoning.
    errno = saved;
}

namespace {
constexpr std::uint64_t kFlags = 0xcd5, kCanary = 0x1122334455667788ULL;
constexpr int kErrno = E2BIG;
std::atomic<std::uint64_t> dropped{0}, in_flight{0};
std::atomic<bool> enabled{false};
static_assert(std::atomic<std::uint64_t>::is_always_lock_free && sizeof(dropped) == 8);
static_assert(std::atomic<bool>::is_always_lock_free && sizeof(enabled) == 1);
int failures{}, checks{};
void check(bool good, const char* message) {
    ++checks;
    if (!good) { ++failures; std::printf("FAIL: %s\n", message); }
}
[[noreturn]] void fatal(const char* message) {
    std::fprintf(stderr, "CPU relay harness setup failed: %s\n", message);
    std::exit(2);
}
template<class T> T read(const void* p) { T v{}; std::memcpy(&v, p, sizeof(v)); return v; }
template<class T> void store(unsigned char* p, T v) { std::memcpy(p, &v, sizeof(v)); }
struct Cpuid { std::uint32_t a, b, c, d; };
Cpuid cpuid(unsigned leaf, unsigned sub = 0) {
    Cpuid r{}; asm volatile("cpuid" : "=a"(r.a), "=b"(r.b), "=c"(r.c), "=d"(r.d) : "a"(leaf), "c"(sub)); return r;
}
struct Extent { std::uint32_t offset{}, bytes{}; };
struct Cpu { std::uint64_t mask{}; std::uint32_t bytes{}; std::array<Extent,64> extents{}; };
bool discover(Cpu& cpu) {
    const auto top = cpuid(0), features = cpuid(1);
    if (top.a < 13 || (features.c & ((1U << 26) | (1U << 27))) != ((1U << 26) | (1U << 27))) return false;
    unsigned low, high; asm volatile("xgetbv" : "=a"(low), "=d"(high) : "c"(0));
    cpu.mask = (std::uint64_t{high} << 32) | low;
    const auto area = cpuid(13);
    cpu.bytes = area.b;
    const auto supported = (std::uint64_t{area.d} << 32) | area.a;
    if ((cpu.mask & 3) != 3 || (cpu.mask & ~supported) || (cpu.mask & ~std::uint64_t{0x2e7}) ||
        cpu.bytes < 576 || cpu.bytes > kAreaBytes || cpu.bytes > area.c) return false;
    const auto avx512 = std::uint64_t{0xe0};
    if ((cpu.mask & avx512) && ((cpu.mask & avx512) != avx512 || !(cpu.mask & 4))) return false;
    const bool amd = top.b == 0x68747541 && top.d == 0x69746e65 && top.c == 0x444d4163;
    const bool intel = top.b == 0x756e6547 && top.d == 0x49656e69 && top.c == 0x6c65746e;
    if (!amd && !intel) return false;
    if (amd && (cpuid(0x80000000).a < 0x80000008 || !(cpuid(0x80000008).b & (1U << 2)))) return false;
    for (unsigned bit = 2; bit < 64; ++bit) if (cpu.mask & (std::uint64_t{1} << bit)) {
        const auto e = cpuid(13, bit);
        if (!e.a || e.b < 576 || (e.c & 5) || e.b > cpu.bytes || e.a > cpu.bytes - e.b) return false;
        cpu.extents[bit] = {e.b, e.a};
        for (unsigned other = 2; other < bit; ++other) {
            const auto old = cpu.extents[other];
            if (old.bytes && e.b < old.offset + old.bytes && old.offset < e.b + e.a) return false;
        }
    }
    return true;
}
__attribute__((noinline)) void commit_stack(std::size_t bytes) {
    auto* p=static_cast<volatile unsigned char*>(alloca(bytes));
    for (std::size_t i=0;i<bytes;i+=4096) p[i]=0;
    p[bytes-1]=0;
}
void prepare_image(unsigned char* image, const Cpu& cpu, bool poison, bool init) {
    std::memset(image, 0, kAreaBytes);
    store<std::uint32_t>(image + 24, init ? 0x1f80 : poison ? 0x3f80 : 0x5f80);
    if (init) return; // XSTATE_BV=0 tests restoration of architectural init state.
    store<std::uint64_t>(image + 512, cpu.mask);
    store<std::uint16_t>(image, poison ? 0x077f : 0x037f);
    image[4] = 1; // Valid nonempty physical x87 ST0, TOP=0, no pending exception.
    store<std::uint64_t>(image + 32, 0x8000000000000000ULL);
    store<std::uint16_t>(image + 40, poison ? 0x4000 : 0x3fff); // 2.0 versus 1.0.
    for (std::size_t i = 160; i < 416; ++i) image[i] = static_cast<unsigned char>((i * 13 + (poison ? 91 : 17)) & 255);
    for (unsigned bit = 2; bit < 64; ++bit) if (cpu.mask & (std::uint64_t{1} << bit)) {
        const auto e = cpu.extents[bit];
        if (bit == 9) {
            // Key0 remains fully accessible. No pkey allocation or external
            // mappings are involved; the remaining keys receive distinct state.
            store<std::uint32_t>(image + e.offset, poison ? 0x55555550U : 0xaaaaaaa0U);
        } else {
            for (unsigned i = 0; i < e.bytes; ++i) image[e.offset + i] = static_cast<unsigned char>((i * 7 + bit * 11 + (poison ? 101 : 23)) & 255);
        }
    }
}
bool xstate_equal(const unsigned char* a, const unsigned char* b, const Cpu& cpu) {
    const auto av = read<std::uint64_t>(a + 512), bv = read<std::uint64_t>(b + 512);
    if (((av | bv) & ~cpu.mask) || read<std::uint64_t>(a + 520) || read<std::uint64_t>(b + 520)) return false;
    auto x87 = [](const unsigned char* p, std::uint64_t bits, unsigned offset, unsigned width, std::uint64_t initial) {
        std::uint64_t value = 0;
        if (!(bits & 1)) return initial;
        for (unsigned i = 0; i < width; ++i) value |= std::uint64_t{p[offset + i]} << (i * 8);
        return value;
    };
    const auto control = x87(a,av,0,2,0x37f), status = x87(a,av,2,2,0), tag = x87(a,av,4,1,0);
    if (control != x87(b,bv,0,2,0x37f) || status != x87(b,bv,2,2,0) || tag != x87(b,bv,4,1,0)) return false;
    const auto top = (status >> 11) & 7;
    for (unsigned logical = 0; logical < 8; ++logical) if (tag & (std::uint64_t{1} << ((top + logical) & 7)))
        if (std::memcmp(a + 32 + logical * 16, b + 32 + logical * 16, 10)) return false;
    // Compare architectural fields; omit undefined empty/reserved bytes and
    // AMD's physical FOP/FIP/FDP metadata, which this relay does not promise.
    if (read<std::uint32_t>(a + 24) != read<std::uint32_t>(b + 24)) return false;
    for (unsigned i = 160; i < 416; ++i) if (((av & 2) ? a[i] : 0) != ((bv & 2) ? b[i] : 0)) return false;
    for (unsigned bit = 2; bit < 64; ++bit) if (cpu.mask & (std::uint64_t{1} << bit)) {
        const auto e = cpu.extents[bit]; const auto bytes = bit == 9 ? 4U : e.bytes;
        for (unsigned i = 0; i < bytes; ++i)
            if (((av & (std::uint64_t{1} << bit)) ? a[e.offset+i] : 0) != ((bv & (std::uint64_t{1} << bit)) ? b[e.offset+i] : 0)) return false;
    }
    return true;
}

struct Template { std::uintptr_t begin, end, config, resume; };
#define HGN_TEMPLATE(i) {reinterpret_cast<std::uintptr_t>(&hgn_shadow_relay_##i##_begin), reinterpret_cast<std::uintptr_t>(hgn_shadow_relay_##i##_code_end), reinterpret_cast<std::uintptr_t>(&hgn_shadow_relay_##i##_config), reinterpret_cast<std::uintptr_t>(hgn_shadow_relay_##i##_resume_delta)}
const Template templates[] = {HGN_TEMPLATE(0),HGN_TEMPLATE(1),HGN_TEMPLATE(2),HGN_TEMPLATE(3),HGN_TEMPLATE(4),HGN_TEMPLATE(5),HGN_TEMPLATE(6),HGN_TEMPLATE(7),HGN_TEMPLATE(8)};
#undef HGN_TEMPLATE
struct Island { std::uintptr_t original{}, copied{}, frames{}, frames_end{}; std::size_t bytes{}; };
std::uintptr_t translate(const Island& copy, std::uintptr_t old) { return copy.copied + old - copy.original; }
void rel32(std::uintptr_t field, std::uintptr_t target) {
    if (read<std::uint32_t>(reinterpret_cast<void*>(field)) != HGN_SHADOW_REL32_SENTINEL) fatal("branch sentinel");
    const auto delta = static_cast<std::int64_t>(target) - static_cast<std::int64_t>(field + 4);
    if (delta < INT32_MIN || delta > INT32_MAX) fatal("branch reach");
    const auto value = static_cast<std::int32_t>(delta); std::memcpy(reinterpret_cast<void*>(field), &value, 4);
}
void verify_frames(const Island& copy) {
    constexpr unsigned char prefix[] = {1,'z','R',0,1,0x78,16,1,0x1b};
    std::array<std::uintptr_t,9> fdes{}; auto at = copy.frames; unsigned count = 0;
    while (at + 4 <= copy.frames_end) {
        const auto length = read<std::uint32_t>(reinterpret_cast<void*>(at));
        if (!length) { if (at + 4 != copy.frames_end || count != 9) fatal("frame terminator/count"); break; }
        if (length == UINT32_MAX || length < 13 || length > copy.frames_end - at - 4) fatal("frame record bounds");
        const auto id = read<std::uint32_t>(reinterpret_cast<void*>(at + 4));
        if (!id) {
            if (length < 17 || std::memcmp(reinterpret_cast<void*>(at + 8),prefix,sizeof(prefix))) fatal("CIE encoding");
        } else {
            if (id > at + 4 - copy.frames) fatal("CIE reach");
            const auto cie = at + 4 - id;
            if (cie >= at || read<std::uint32_t>(reinterpret_cast<void*>(cie+4)) != 0) fatal("CIE identity");
            const auto begin = static_cast<std::uintptr_t>(static_cast<std::int64_t>(at + 8) + read<std::int32_t>(reinterpret_cast<void*>(at+8)));
            const auto size = read<std::uint32_t>(reinterpret_cast<void*>(at+12)); bool matched = false;
            for (unsigned i = 0; i < 9; ++i) if (begin == translate(copy,templates[i].begin) && size == templates[i].end - templates[i].begin && !fdes[i]) {
                fdes[i] = at; ++count; matched = true;
            }
            if (!matched) fatal("copied FDE code envelope");
        }
        at += 4 + length;
    }
    if (at + 4 != copy.frames_end || count != 9) fatal("missing final frame terminator");
    __register_frame(reinterpret_cast<void*>(copy.frames));
    for (unsigned i = 0; i < 9; ++i) {
        const auto begin = translate(copy,templates[i].begin), end = translate(copy,templates[i].end);
        for (const auto pc : {begin, begin + (end-begin)/2, end-1}) {
            ProbeDwarfBases bases{};
            const auto fde = reinterpret_cast<std::uintptr_t>(_Unwind_Find_FDE(reinterpret_cast<void*>(pc),&bases));
            if (fde != fdes[i] || reinterpret_cast<std::uintptr_t>(bases.function) != begin) fatal("registered copied FDE lookup");
        }
    }
    check(true,"all nine copied CIE/FDE envelopes and 27 registered FDE lookups");
}
Island make_island(const Cpu& cpu, std::uint64_t required) {
    Island copy{}; copy.original = reinterpret_cast<std::uintptr_t>(hgn_shadow_island_begin);
    const auto original_end = reinterpret_cast<std::uintptr_t>(hgn_shadow_island_end);
    if (original_end <= copy.original || original_end - copy.original > 1024*1024) fatal("island envelope");
    const auto page = static_cast<std::size_t>(sysconf(_SC_PAGESIZE));
    if (page != 4096) fatal("page size");
    copy.bytes = (original_end - copy.original + page - 1) & ~(page - 1);
    const auto anchor = reinterpret_cast<std::uintptr_t>(&hgn_shadow_probe_stock) & ~(std::uintptr_t{page}-1);
    for (unsigned i = 1; i <= 256 && !copy.copied; ++i) for (const int sign : {1,-1}) {
        const auto address = static_cast<std::int64_t>(anchor) + std::int64_t{sign} * i * 0x200000;
        if (address < 65536 || address > INT64_MAX - static_cast<std::int64_t>(copy.bytes)) continue;
        void* area = mmap(reinterpret_cast<void*>(address),copy.bytes,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS|MAP_FIXED_NOREPLACE,-1,0);
        if (area == MAP_FAILED) { if (errno == EEXIST) continue; fatal("near mmap"); }
        if (reinterpret_cast<std::uintptr_t>(area) != static_cast<std::uintptr_t>(address)) fatal("fixed-noreplace address");
        copy.copied = static_cast<std::uintptr_t>(address); break;
    }
    if (!copy.copied) fatal("near island exhausted");
    std::memcpy(reinterpret_cast<void*>(copy.copied),reinterpret_cast<void*>(copy.original),original_end-copy.original);
    constexpr unsigned char endbr[] = {0xf3,0x0f,0x1e,0xfa};
    if (std::memcmp(reinterpret_cast<const void*>(&hgn_shadow_probe_callback),endbr,sizeof(endbr))) fatal("callback ENDBR64");
    std::uintptr_t thread_pointer; asm volatile("movq %%fs:0,%0":"=r"(thread_pointer));
    Configuration cfg{}; cfg.enabled=1; cfg.xsave_bytes=cpu.bytes; cfg.xcr0_mask=cpu.mask;
    cfg.required_stack_below_original_rsp=required;
    cfg.stack_tls_offset=static_cast<std::int64_t>(reinterpret_cast<std::uintptr_t>(&hgn_probe_stack))-static_cast<std::int64_t>(thread_pointer);
    cfg.callback=hgn_shadow_probe_callback; cfg.loss_counter=reinterpret_cast<std::uint64_t*>(&dropped);
    cfg.runtime_enabled=reinterpret_cast<const unsigned char*>(&enabled); cfg.in_flight_counter=reinterpret_cast<std::uint64_t*>(&in_flight);
    for (const auto& t : templates) {
        std::memcpy(reinterpret_cast<void*>(translate(copy,t.config)),&cfg,sizeof(cfg));
        rel32(translate(copy,t.resume),reinterpret_cast<std::uintptr_t>(&hgn_shadow_probe_fallthrough));
    }
    rel32(translate(copy,reinterpret_cast<std::uintptr_t>(hgn_shadow_relay_4_branch_delta)),reinterpret_cast<std::uintptr_t>(&hgn_shadow_probe_taken));
    rel32(translate(copy,reinterpret_cast<std::uintptr_t>(hgn_shadow_relay_8_branch_delta)),reinterpret_cast<std::uintptr_t>(&hgn_shadow_probe_taken));
    copy.frames=translate(copy,reinterpret_cast<std::uintptr_t>(hgn_shadow_island_frames));
    copy.frames_end=translate(copy,reinterpret_cast<std::uintptr_t>(hgn_shadow_island_frames_end));
    __builtin___clear_cache(reinterpret_cast<char*>(copy.copied),reinterpret_cast<char*>(copy.copied+copy.bytes));
    if (mprotect(reinterpret_cast<void*>(copy.copied),copy.bytes,PROT_READ|PROT_EXEC)) fatal("copy RX");
    verify_frames(copy); return copy;
}

struct Result { Frame before, after; std::uint32_t branch; int observed_errno; bool state_equal, redzone, poisoned, callback_frame; };
Result run_once(std::uintptr_t target, const Cpu& cpu) {
    hgn_probe_target=target; hgn_probe_callbacks=0; hgn_probe_callback_site=UINT32_MAX;
    hgn_probe_before={}; hgn_probe_after={}; hgn_probe_callback_frame={};
    std::memset(hgn_probe_before_xsave,0,kAreaBytes); std::memset(hgn_probe_after_xsave,0,kAreaBytes);
    std::memset(hgn_probe_caller_xsave,0,kAreaBytes); std::memset(hgn_probe_poison_snapshot,0,kAreaBytes);
    std::fill(std::begin(hgn_probe_red_zone),std::end(hgn_probe_red_zone),0); hgn_probe_branch=UINT32_MAX;
    errno=kErrno; hgn_shadow_probe_run(); const int observed_errno=errno;
    return {hgn_probe_before,hgn_probe_after,hgn_probe_branch,observed_errno,
        xstate_equal(hgn_probe_before_xsave,hgn_probe_after_xsave,cpu),
        std::all_of(std::begin(hgn_probe_red_zone),std::end(hgn_probe_red_zone),[](auto x){return x==kCanary;}),
        xstate_equal(hgn_probe_poison_snapshot,hgn_probe_poison_xsave,cpu),
        hgn_probe_callback_frame.gpr==hgn_probe_before.gpr &&
        (hgn_probe_callback_frame.ordinary_rflags&kFlags)==(hgn_probe_before.ordinary_rflags&kFlags)};
}
enum class Bounds { Valid, Missing, Short };
void run_case(const Island& island, const Cpu& cpu, ProbeStackBounds stack, bool zero, bool init, bool runtime_enabled, Bounds bounds) {
    alignas(16) static unsigned char object[80]{};
    store<std::uint32_t>(object+0x48,zero?0U:1U);
    for (unsigned i=0;i<16;++i) hgn_probe_patterns[i]=0x1020304050607080ULL+i*0x0101010101010101ULL;
    hgn_probe_patterns[5]=reinterpret_cast<std::uintptr_t>(object);
    prepare_image(hgn_probe_seed_xsave,cpu,false,init);
    hgn_probe_stack=stack;
    const auto stock=run_once(reinterpret_cast<std::uintptr_t>(&hgn_shadow_probe_stock),cpu);
    check(stock.before.gpr==stock.after.gpr && stock.state_equal && stock.redzone && stock.observed_errno==kErrno,"independent stock CMP/Jcc preserves all expected state");
    check(stock.branch==(zero?1U:0U),"independent stock branch outcome");
    if (bounds==Bounds::Missing) hgn_probe_stack={};
    if (bounds==Bounds::Short) hgn_probe_stack={stock.before.gpr[7]-128,stack.high};
    dropped.store(0); in_flight.store(0); enabled.store(runtime_enabled);
    const auto actual=run_once(translate(island,templates[8].begin),cpu);
    const bool callback=runtime_enabled && bounds==Bounds::Valid;
    bool seed_ok=actual.before.gpr[7]!=0;
    for (unsigned i=0;i<16;++i) if (i!=7) seed_ok&=actual.before.gpr[i]==hgn_probe_patterns[i];
    check(seed_ok,"independent snapshot observes every seeded non-RSP GPR");
    check(actual.before.gpr==actual.after.gpr,"copied relay preserves all GPRs and original entry RSP");
    check((actual.before.ordinary_rflags&kFlags)==kFlags && (actual.after.ordinary_rflags&kFlags)==(stock.after.ordinary_rflags&kFlags),"copied CMP/Jcc flags equal independent stock flags including DF");
    check(actual.branch==stock.branch,"copied JE taken/fallthrough equals stock");
    check(actual.redzone && actual.observed_errno==kErrno,"copied relay preserves all 128 red-zone bytes and errno");
    check(actual.state_equal,"copied relay preserves full enabled architectural XSAVE state");
    check(hgn_probe_callbacks==(callback?1U:0U),"enabled callback once; disabled and rejected-stack callbacks absent");
    check(dropped.load()==(runtime_enabled && bounds!=Bounds::Valid?1U:0U) && in_flight.load()==0,"stack bypass records one explicit loss and releases in-flight admission");
    if (callback) check(hgn_probe_callback_site==8 && actual.callback_frame && actual.poisoned,"callback sees exact saved frame and performs real full-mask xstate poison");
    if (init) check((read<std::uint64_t>(hgn_probe_before_xsave+512)&(3ULL|(cpu.mask&4)))==0,"x87/SSE/AVX init components start absent from XSTATE_BV");
    std::printf("case zero=%u init=%u enabled=%u bounds=%u done\n",static_cast<unsigned>(zero),static_cast<unsigned>(init),static_cast<unsigned>(runtime_enabled),static_cast<unsigned>(bounds));
}
} // namespace

int main() {
    Cpu cpu{}; if (!discover(cpu)) { std::puts("DECLINED unsupported architectural XSAVE configuration; no relay executed"); return 77; }
    pthread_attr_t attr; void* low=nullptr; std::size_t bytes=0;
    if (pthread_getattr_np(pthread_self(),&attr)) fatal("pthread stack attributes");
    const int got=pthread_attr_getstack(&attr,&low,&bytes), destroyed=pthread_attr_destroy(&attr);
    if (got || destroyed || !low || bytes>UINTPTR_MAX-reinterpret_cast<std::uintptr_t>(low)) fatal("pthread stack range");
    ProbeStackBounds stack{reinterpret_cast<std::uintptr_t>(low),reinterpret_cast<std::uintptr_t>(low)+bytes};
    const auto required=std::uint64_t{cpu.bytes}+HGN_SHADOW_CAPTURE_RESERVE+HGN_SHADOW_XSAVE_PAD+63+8192+65536;
    const auto current=reinterpret_cast<std::uintptr_t>(&attr);
    if (current<stack.low || current-stack.low<required+65536 || current>=stack.high) fatal("reported stack reserve");
    commit_stack(static_cast<std::size_t>(required+65536)); // Returns with committed pages below the caller again.
    FILE* maps=std::fopen("/proc/self/maps","r"); if (!maps) fatal("stack mapping inventory");
    char line[1024],permissions[8]; unsigned long begin,end; bool mapped=false;
    while (std::fgets(line,sizeof(line),maps)) if (std::sscanf(line,"%lx-%lx %7s",&begin,&end,permissions)==3 && begin<=current && current<end && !std::strcmp(permissions,"rw-p")) {
        stack.low=std::max<std::uint64_t>(stack.low,begin); stack.high=std::min<std::uint64_t>(stack.high,end); mapped=true; break;
    }
    if (std::fclose(maps) || !mapped || current-stack.low<required+32768) fatal("actual mapped stack margin");
    hgn_probe_mask=cpu.mask; prepare_image(hgn_probe_poison_xsave,cpu,true,false);
    const auto island=make_island(cpu,required);
    for (const bool zero : {false,true}) run_case(island,cpu,stack,zero,false,true,Bounds::Valid);
    for (const bool zero : {false,true}) run_case(island,cpu,stack,zero,true,true,Bounds::Valid);
    run_case(island,cpu,stack,false,false,false,Bounds::Valid);
    run_case(island,cpu,stack,true,false,false,Bounds::Missing);
    run_case(island,cpu,stack,false,false,true,Bounds::Missing);
    run_case(island,cpu,stack,true,false,true,Bounds::Short);
    enabled.store(false);
    check(in_flight.load()==0,"all CPU probe admissions drained before unregister/unmap");
    __deregister_frame(reinterpret_cast<void*>(island.frames));
    if (munmap(reinterpret_cast<void*>(island.copied),island.bytes)) fatal("island unmap");
    std::printf("CPU copied-relay qualifier: %s; checks=%d failures=%d; engine, signals, concurrency, native installation and serving remain unqualified\n",failures?"FAIL":"PASS",checks,failures);
    return failures?1:0;
}
