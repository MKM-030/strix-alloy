// Private CPU-only post-native-ID phase. No ID arithmetic, engine hooks, new
// threads, native completion epilogue, H2D call, or mapping ownership lives here.
#pragma once
#include "page_segment_scheduler.h"
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <mutex>

namespace ple_native_page_0172 {
enum class Result { success, abort };
enum class Failure { none, cancelled, schedule, copy, synchronization, stale_generation };

struct Arguments {
    const void* native_context{};
    std::size_t token_count{};
    std::uint64_t context_rows{};
    // Borrow native context +0x30. Native producers write these IDs before
    // entering run_phase(); this phase never computes or changes an ID.
    std::span<const std::int64_t> ids;
    ple_page::TableView table;
    ple_page::OutputView raw;
    std::uint64_t native_stride{};
    std::int32_t native_table_encoding{-1};
};

struct Qualification {
    bool exact_native_sites_and_once_per_state{};
    bool selected_mapping_owner_extent_and_lifetime{};
    bool native_raw_and_ids_lifetime{};
    bool cancellation_failure_and_join_bound{};
    bool terminal_consumer_check_bound{};
    bool prior_workers_joined{};
    bool explicitly_selected{};
    bool complete() const noexcept {
        return exact_native_sites_and_once_per_state &&
               selected_mapping_owner_extent_and_lifetime && native_raw_and_ids_lifetime &&
               cancellation_failure_and_join_bound && terminal_consumer_check_bound &&
               prior_workers_joined && explicitly_selected;
    }
};

struct Callbacks {
    void* context{};
    void* cookie{};
    // Nonblocking atomic read of native context +0x60. The callback and its
    // cookie live through the native joins and must not reenter this Phase.
    bool (*cancel_requested)(void*, void*) noexcept{};
};

inline bool can_select(const Arguments& args, const Qualification& qualified,
                       ple_page::Policy policy, std::size_t workers,
                       Callbacks callbacks, std::uint64_t generation) noexcept {
    constexpr std::size_t max_tokens=8192, max_rows=131072, max_scratch=6*1024*1024;
    if (!qualified.complete() || !policy.allow_page_order || !generation ||
        !workers || workers>256 || !args.native_context ||
        callbacks.context!=args.native_context || !callbacks.cancel_requested ||
        !args.token_count || args.token_count>max_tokens ||
        args.context_rows!=args.token_count*16 || args.ids.size()!=args.context_rows ||
        args.ids.size()<policy.min_rows || args.ids.size()>policy.max_rows || args.ids.size()>max_rows ||
        args.native_stride!=160 || args.native_table_encoding!=0 ||
        !args.ids.data() || !args.raw.base || !args.table.base || !args.table.mapping_base ||
        !args.table.row_count || args.table.row_count>std::numeric_limits<std::size_t>::max()/160 ||
        args.ids.size()*40+4>std::min(policy.max_scratch_bytes,max_scratch)) return false;

    // Only geometry is checked before native ID production. The elected planner
    // validates all completed IDs before publishing a plan or writing raw bytes.
    const auto map=reinterpret_cast<std::uintptr_t>(args.table.mapping_base);
    const auto table=reinterpret_cast<std::uintptr_t>(args.table.base);
    const auto raw=reinterpret_cast<std::uintptr_t>(args.raw.base);
    const auto ids=reinterpret_cast<std::uintptr_t>(args.ids.data());
    auto end_address=[](std::uintptr_t begin, std::size_t size, std::uintptr_t& end) noexcept {
        if (size>std::numeric_limits<std::uintptr_t>::max()-begin) return false;
        end=begin+size; return true;
    };
    auto overlap=[](std::uintptr_t a, std::uintptr_t ae, std::uintptr_t b, std::uintptr_t be) noexcept {
        return a<be && b<ae;
    };
    std::uintptr_t map_end,table_end,raw_end,ids_end;
    if (args.raw.capacity_bytes<args.ids.size()*160 ||
        !end_address(map,args.table.mapping_bytes,map_end) ||
        !end_address(table,std::size_t(args.table.row_count)*160,table_end) ||
        table<map || table_end>map_end ||
        !end_address(raw,args.raw.capacity_bytes,raw_end) ||
        !end_address(ids,args.ids.size()*sizeof(std::int64_t),ids_end)) return false;
    return !overlap(raw,raw_end,map,map_end) && !overlap(raw,raw_end,ids,ids_end) &&
           !overlap(ids,ids_end,map,map_end);
}

class Phase {
    enum class Stage { ids, planning, copying };
    Arguments args_;
    Callbacks callbacks_;
    ple_page::Policy policy_;
    ple_page::Schedule schedule_;
    std::uint64_t generation_{};
    std::atomic<std::size_t> ids_left_{}, workers_left_{}, page_cursor_{};
    std::atomic<Stage> stage_{Stage::ids};
    std::atomic<Failure> failure_{Failure::none};
    std::atomic<bool> active_{}, terminal_done_{}, terminal_success_{};
    mutable std::mutex lifecycle_mutex_;
    std::mutex wait_mutex_;
    std::condition_variable wait_cv_;

    void fail(Failure reason) noexcept {
        auto expected=Failure::none;
        failure_.compare_exchange_strong(expected,reason,std::memory_order_acq_rel);
        wait_cv_.notify_all();
    }
    bool stopping() noexcept {
        if (failure_.load(std::memory_order_acquire)!=Failure::none) return true;
        if (callbacks_.cancel_requested(callbacks_.context,callbacks_.cookie)) {
            fail(Failure::cancelled); return true;
        }
        return false;
    }
    static bool stop_adapter(void* self) noexcept { return static_cast<Phase*>(self)->stopping(); }

    void arrive_ids() {
        if (ids_left_.fetch_sub(1,std::memory_order_acq_rel)==1) {
            // The release/acquire RMW chain publishes every original native ID
            // store to this sole planner. No producer may write IDs after arrival.
            stage_.store(Stage::planning,std::memory_order_release);
            if (!stopping()) {
                const auto status=schedule_.prepare(args_.table,args_.raw,args_.ids,policy_,{this,stop_adapter});
                if (status!=ple_page::Status::ready)
                    fail(status==ple_page::Status::cancelled ? Failure::cancelled : Failure::schedule);
            }
            // Acquiring copying publishes immutable descriptors to all workers.
            // A failed plan is never a request to resume the skipped native copies.
            stage_.store(Stage::copying,std::memory_order_release);
            wait_cv_.notify_all();
        } else {
            std::unique_lock lock(wait_mutex_);
            while (stage_.load(std::memory_order_acquire)!=Stage::copying && !stopping())
                wait_cv_.wait_for(lock,std::chrono::milliseconds(10));
        }
    }

    void finish_worker() noexcept {
        // All copies are sequenced before this release/acquire RMW chain. Every
        // successful run_phase return acquires terminal_done, including workers
        // with no pages, so the complete raw buffer is visible before success.
        if (workers_left_.fetch_sub(1,std::memory_order_acq_rel)==1) {
            terminal_success_.store(!stopping(),std::memory_order_relaxed);
            terminal_done_.store(true,std::memory_order_release);
            wait_cv_.notify_all();
        }
    }

public:
    Phase()=default;
    Phase(const Phase&)=delete;
    Phase& operator=(const Phase&)=delete;

    // Called once before any selected native thread starts. Arguments and native
    // owners stay fixed until all native threads have joined, including the
    // original completion epilogues. Reuse/destruction requires those joins.
    // Native launch failure must cancel this generation. A fatal selected-path
    // abort may exit immediately; nonfatal reuse must also account for every
    // unstarted worker with abort_unstarted() before joining launched workers.
    bool begin(Arguments args, Qualification qualified, ple_page::Policy policy,
               std::size_t workers, Callbacks callbacks, std::uint64_t generation) {
        if (!can_select(args,qualified,policy,workers,callbacks,generation)) return false;
        std::lock_guard lock(lifecycle_mutex_);
        if (workers_left_.load(std::memory_order_acquire) || generation<=generation_) return false;
        active_.store(false,std::memory_order_release);
        schedule_.prepare({}, {}, {}, {}); // Invalidate an old plan, retain bounded scratch.
        args_=args; callbacks_=callbacks; policy_=policy;
        policy_.max_scratch_bytes=std::min(policy_.max_scratch_bytes,std::size_t(6*1024*1024));
        generation_=generation;
        ids_left_.store(workers,std::memory_order_relaxed);
        workers_left_.store(workers,std::memory_order_relaxed);
        page_cursor_.store(0,std::memory_order_relaxed);
        stage_.store(Stage::ids,std::memory_order_relaxed);
        failure_.store(Failure::none,std::memory_order_relaxed);
        terminal_success_.store(false,std::memory_order_relaxed);
        terminal_done_.store(false,std::memory_order_relaxed);
        active_.store(true,std::memory_order_release);
        return true;
    }

    // Called exactly once per selected original native worker at 0x1865d72,
    // after it exhausted the original ID cursor or observed cancellation. The
    // attachment resumes that state's original epilogue exactly once on return.
    // There is no scalar recomputation, completion callback, or copy fallback.
    Result run_phase(std::uint64_t expected_generation) noexcept {
        {
            std::lock_guard lock(lifecycle_mutex_);
            if (!active_.load(std::memory_order_acquire) || expected_generation!=generation_)
                return Result::abort;
        }
        try {
            stopping();
            arrive_ids();
            while (!stopping()) {
                const auto page=page_cursor_.fetch_add(1,std::memory_order_relaxed);
                if (page>=schedule_.page_count()) break;
                const auto status=schedule_.copy_pages(page,page+1,{this,stop_adapter});
                if (status!=ple_page::Status::complete) {
                    fail(status==ple_page::Status::cancelled ? Failure::cancelled : Failure::copy);
                    break;
                }
            }
            stopping();
        } catch (...) { fail(Failure::synchronization); }
        finish_worker();
        try {
            std::unique_lock lock(wait_mutex_);
            while (!terminal_done_.load(std::memory_order_acquire) && !stopping()) {
                wait_cv_.wait_for(lock,std::chrono::milliseconds(10));
            }
        } catch (...) {
            fail(Failure::synchronization);
            // An abort never authorizes H2D. The attachment handles selected
            // phase failure before the original consumer may use the buffer.
        }
        // Cancellation/failure may return abort before other phase releases,
        // allowing an owner-bound fatal deadline to stop partial thread launch.
        // Only success requires/acquires the complete terminal copy publication.
        return terminal_done_.load(std::memory_order_acquire) &&
               terminal_success_.load(std::memory_order_relaxed) && !stopping() ? Result::success : Result::abort;
    }

    // Capture this launch's generation in cancellation/retirement callbacks;
    // stale callbacks must never cancel a newer context generation.
    void cancel(std::uint64_t expected_generation) noexcept {
        std::lock_guard lock(lifecycle_mutex_);
        if (active_.load(std::memory_order_acquire) && expected_generation==generation_)
            fail(Failure::cancelled);
    }

    // Launcher-only failure path: count includes ONLY states which will never
    // enter run_phase. Owner serializes this with thread creation, calls once
    // for those states, then joins all launched workers. Copies always abort.
    bool abort_unstarted(std::uint64_t expected_generation, std::size_t count) noexcept {
        std::lock_guard lock(lifecycle_mutex_);
        if (!active_.load(std::memory_order_acquire) || expected_generation!=generation_ || !count ||
            count>ids_left_.load(std::memory_order_acquire) || count>workers_left_.load(std::memory_order_acquire))
            return false;
        fail(Failure::cancelled);
        ids_left_.fetch_sub(count,std::memory_order_acq_rel);
        if (workers_left_.fetch_sub(count,std::memory_order_acq_rel)==count) {
            terminal_success_.store(false,std::memory_order_relaxed);
            terminal_done_.store(true,std::memory_order_release);
        }
        wait_cv_.notify_all();
        return true;
    }

    // Additional guard after original native wait/join, before original H2D.
    // Native countdown zero alone has no successful-copy meaning.
    bool permit_h2d(std::uint64_t expected_generation, bool native_workers_joined) noexcept {
        std::lock_guard lock(lifecycle_mutex_);
        return native_workers_joined && active_.load(std::memory_order_acquire) &&
               expected_generation==generation_ && workers_left_.load(std::memory_order_acquire)==0 &&
               terminal_done_.load(std::memory_order_acquire) &&
               terminal_success_.load(std::memory_order_relaxed) && !stopping();
    }
    Failure failure(std::uint64_t expected_generation) const noexcept {
        std::lock_guard lock(lifecycle_mutex_);
        return !active_.load(std::memory_order_acquire) || expected_generation!=generation_ ?
               Failure::stale_generation : failure_.load(std::memory_order_acquire);
    }
};
}
