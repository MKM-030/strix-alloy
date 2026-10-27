#pragma once
// CPU-testable private-stream ownership core. No hook installation or HIP load.
#include <array>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <thread>

namespace deferred_z {
using Handle = void*;
constexpr const char* engine_sha = "ce1c375eb2d92a4c7b2b0e1d969acd865bb72bb248c52498eedb170cbaea8a89";
constexpr unsigned stream_nonblocking = 1, event_disable_timing = 2;
constexpr int not_ready = 600;
enum class Result { stock, captured, pending, joined, fatal };

struct Api {
    int (*stream_create)(Handle*, unsigned){};
    int (*stream_destroy)(Handle){};
    int (*stream_sync)(Handle){};
    int (*event_create)(Handle*, unsigned){};
    int (*event_destroy)(Handle){};
    int (*event_record)(Handle, Handle){};
    int (*event_query)(Handle){};
    int (*stream_wait)(Handle, Handle, unsigned){};
};

// Provider verifies the exact mapped engine hash AND each seam's expected bytes.
// The concrete current-image byte map is owned by the separate seam adapter.
struct Pin { std::uintptr_t address{}; const unsigned char* expected{}; std::size_t bytes{}; };
struct Qualification {
    bool enabled{}; // caller reads explicit exact opt-in; false is default
    bool single_owner{}, disjoint_z_output{}, unchanged_fc{}, scratch_sequential{};
    bool no_native_prefetch{}, all_exits_bound{}, complete_fc_launch_coverage{};
    bool warmed_algorithm_cache{}, stock_ht_path{}, live_ranges_verified{};
    std::size_t event_slots{8}; // bounded request-local generations; valid 1..8
    const char* image_hash{};
    const Pin* pins{};
    std::size_t pin_count{};
    bool (*verify_identity_and_bytes)(const char*, const Pin*, std::size_t){};
};

using Fc = void (*)(void*, const void*, void*, int, int, int);
struct FcCall {
    Fc original{};
    void* descriptor{};
    const void* input{};
    void* output{};
    int n{}, m{}, k{};
};

enum class SubmitKind { kernel, module, ext_module, matmul, copy, memset, synchronize, host_callback, allocate, release, synchronous_copy };
struct Submit {
    SubmitKind kind{};
    const void* function{};
    Handle stream{};
    void** args{};
    void** extra{};
    unsigned grid[3]{}, block[3]{};
    std::size_t shared{}, bytes{};
    const void* source{};
    void* destination{};
    void* workspace{};
    std::size_t workspace_bytes{};
    // Observer-only native matmul pointers. No dereference occurs in wrappers.
    // Exact-caller installer qualification owns scalar/algorithm snapshots.
    const void* matmul_handle{};
    const void* matmul_operands[4]{}; // a,b,c,d
    const void* matmul_layouts[4]{}; // ad,bd,cd,dd
    const void* matmul_alpha{};
    const void* matmul_beta{};
    const void* matmul_algorithm{};
    int operation_value{};
    unsigned flags{};
    Handle start_event{}, stop_event{};
    const void* caller{};
};
using Observer=bool (*)(void*,const Submit&);
struct Observation { Observer callback{}; void* cookie{}; bool inside{}; };
inline thread_local Observation* active_observation=nullptr;

class ObserverScope {
    bool entered_{};
public:
    explicit ObserverScope(Observation& o) noexcept {
        if (!active_observation && o.callback) { active_observation=&o; entered_=true; }
    }
    ~ObserverScope(){if(entered_)active_observation=nullptr;}
    bool entered() const noexcept{return entered_;}
    ObserverScope(const ObserverScope&)=delete;
};

struct Redirect {
    Handle main{}, side{};
    bool failed{};
    unsigned redirected{};
};
inline thread_local Redirect* active_redirect = nullptr;

inline bool observe_submit(const Submit& submit) noexcept {
    if (!active_observation) return true;
    auto& o=*active_observation;
    if(o.inside){if(active_redirect)active_redirect->failed=true;return false;}
    o.inside=true;
    bool ok=false;
    try { ok=o.callback(o.cookie,submit); } catch (...) {}
    o.inside=false;
    if(!ok && active_redirect)active_redirect->failed=true;
    return ok;
}

// Used by audited launch interposers only. Unknown/foreign streams fail rather
// than borrowing a native stream. nullptr is the original main stream here.
inline bool redirect_stream(Handle requested, Handle& actual) noexcept {
    if (!active_redirect) { actual=requested; return true; }
    if (active_redirect->failed ||
        (requested!=active_redirect->main && requested!=active_redirect->side)) {
        active_redirect->failed=true; return false;
    }
    actual=active_redirect->side;
    ++active_redirect->redirected;
    return true;
}
inline void launch_error(int result) noexcept {
    if (active_redirect && result) active_redirect->failed=true;
}

class RedirectScope {
    Redirect& state_;
    bool entered_{};
public:
    explicit RedirectScope(Redirect& state) noexcept: state_(state) {
        if (active_redirect) { state_.failed=true; return; }
        active_redirect=&state_; entered_=true;
    }
    ~RedirectScope() { if (entered_) active_redirect=nullptr; }
    bool entered() const noexcept { return entered_; }
    RedirectScope(const RedirectScope&)=delete;
};

class Context {
    enum class State { empty, available, captured, side_queued, retired };
    struct Slot { Handle fork{}, done{}, retired{}; State state{State::empty}; };
    static constexpr std::size_t pool_size=8;
    Api api_{};
    Handle side_{};
    std::array<Slot,pool_size> slots_{};
    std::size_t slot_count_{pool_size};
    Slot* pending_{};
    FcCall call_{};
    Redirect redirect_{}; // Context lifetime exceeds every scoped TLS use.
    std::thread::id owner_{};
    bool enabled_{}, poisoned_{}, touched_{};
    bool owner() const noexcept { return owner_==std::this_thread::get_id(); }
    bool valid_api() const noexcept {
        return api_.stream_create && api_.stream_destroy && api_.stream_sync &&
            api_.event_create && api_.event_destroy && api_.event_record &&
            api_.event_query && api_.stream_wait;
    }
    Result fail() noexcept { poisoned_=true; return Result::fatal; }
    bool create_event(Handle& h) noexcept { return api_.event_create(&h,event_disable_timing)==0 && h; }
public:
    Context()=default;
    Context(const Context&)=delete;
    Context& operator=(const Context&)=delete;
    // No destructor silently frees device-owned handles. Owner must close() at
    // every lifetime/early-exit path; a failed drain requires process fail-stop.
    ~Context()=default;

    bool open(const Api& api, const Qualification& q) noexcept {
        if (enabled_ || side_ || poisoned_) return false;
        if (!q.enabled) return true; // no HIP calls, no pin reads when disabled
        if (!q.single_owner || !q.disjoint_z_output || !q.unchanged_fc ||
            !q.scratch_sequential || !q.no_native_prefetch || !q.all_exits_bound ||
            !q.complete_fc_launch_coverage || !q.warmed_algorithm_cache ||
            !q.stock_ht_path || !q.live_ranges_verified || q.event_slots<1 ||
            q.event_slots>pool_size || !q.image_hash ||
            std::strcmp(q.image_hash,engine_sha) || !q.pins || !q.pin_count ||
            !q.verify_identity_and_bytes) return false;
        for (std::size_t i=0;i<q.pin_count;++i)
            if (!q.pins[i].address || !q.pins[i].expected || !q.pins[i].bytes) return false;
        if (!q.verify_identity_and_bytes(engine_sha,q.pins,q.pin_count)) return false;
        api_=api;
        if (!valid_api()) return false;
        owner_=std::this_thread::get_id();
        slot_count_=q.event_slots;
        if (api_.stream_create(&side_,stream_nonblocking) || !side_) { poisoned_=true; return false; }
        for (std::size_t i=0;i<slot_count_;++i) {
            auto& s=slots_[i];
            if (!create_event(s.fork) || !create_event(s.done) || !create_event(s.retired)) {
                poisoned_=true; close(); return false;
            }
            s.state=State::available;
        }
        enabled_=true;
        return true;
    }

    Result capture(const FcCall& call) noexcept {
        if (!enabled_) return poisoned_ ? Result::fatal : Result::stock;
        if (!owner() || poisoned_ || pending_ || active_redirect) return fail();
        if (!call.original || !call.descriptor || !call.input || !call.output ||
            call.n!=6144 || call.m<=8 || call.m>8192 || call.k!=2560) return Result::stock;
        for (std::size_t i=0;i<slot_count_;++i) {
            auto& s=slots_[i];
            if (s.state==State::retired) {
                const int r=api_.event_query(s.retired);
                if (!r) s.state=State::available;
                else if (r!=not_ready) return fail();
            }
            if (s.state==State::available) {
                call_=call; pending_=&s; s.state=State::captured;
                touched_=true; // early exit must drain native main producers too
                return Result::captured;
            }
        }
        return Result::stock; // no original call was suppressed
    }

    Result after_ab() noexcept {
        if (!enabled_) return poisoned_ ? Result::fatal : Result::stock;
        if (!owner() || poisoned_ || !pending_ || pending_->state!=State::captured) return fail();
        auto& s=*pending_;
        // AB is already enqueued on original main(0). This dependency is on
        // device completion, not merely host completion of the AB FC calls.
        touched_=true;
        if (api_.event_record(s.fork,nullptr) || api_.stream_wait(side_,s.fork,0)) return fail();
        s.state=State::side_queued; // original FC may enqueue before it fails
        redirect_={nullptr,side_,false,0};
        auto& redirect=redirect_;
        {
            RedirectScope scope(redirect);
            if (!scope.entered()) return fail();
            try { call_.original(call_.descriptor,call_.input,call_.output,call_.n,call_.m,call_.k); }
            catch (...) { redirect.failed=true; }
        }
        if (redirect.failed || !redirect.redirected) return fail();
        if (api_.event_record(s.done,side_)) return fail();
        return Result::pending;
    }

    // Mandatory before fused DN's first Z read AND any later FC workspace use.
    // A device wait permits main non-FC work already enqueued to overlap Z.
    Result join_pending() noexcept {
        if (!enabled_) return poisoned_ ? Result::fatal : Result::stock;
        if (!owner() || poisoned_) return fail();
        if (!pending_) return Result::stock;
        auto& s=*pending_;
        if (s.state!=State::side_queued) return fail();
        if (api_.stream_wait(nullptr,s.done,0) || api_.event_record(s.retired,nullptr)) return fail();
        s.state=State::retired; pending_=nullptr; call_={};
        return Result::joined;
    }

    // Request abort/early return after capture must call close, not replay stock
    // Z or continue a request with its Z projection missing. Future model calls
    // are rejected once poisoned. Drains both streams even when one fails.
    bool close() noexcept {
        if (!side_) { enabled_=false; return true; }
        if (!owner() || active_redirect) { poisoned_=true; return false; }
        enabled_=false;
        int a=0,b=0;
        if (touched_) { a=api_.stream_sync(side_); b=api_.stream_sync(nullptr); }
        if (a || b) { poisoned_=true; return false; } // retain all live handles
        pending_=nullptr; call_={};
        bool ok=true;
        for (auto& s:slots_) {
            for (Handle* h:{&s.fork,&s.done,&s.retired}) {
                if (*h) { if (api_.event_destroy(*h)) ok=false; else *h=nullptr; }
            }
            if (!s.fork && !s.done && !s.retired) s.state=State::empty;
        }
        if (ok && api_.stream_destroy(side_)==0) side_=nullptr;
        else ok=false;
        if (!ok) poisoned_=true;
        return ok;
    }
    bool poisoned() const noexcept { return poisoned_; }
    bool has_pending() const noexcept { return pending_!=nullptr; }
};
} // namespace deferred_z
