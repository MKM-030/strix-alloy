// Source-only typed component; no DLL loading, construction or device creation here.
// Include this once in a matching 1.0.7 Windows XRT host translation unit.
#pragma once
#define RAW_ID_BRIDGE_NO_MAIN
#include "../halogen_flm_raw_id_bridge/bridge.cpp"
#include <set>
#include <windows.h>

namespace growing_raw {
constexpr std::size_t seed_count = 512;
constexpr std::size_t output_limit = 128;
constexpr std::size_t local_limit = seed_count + output_limit;
static_assert(local_limit < raw_id::engine_capacity);

struct Timing {
    std::int64_t operation_started_ticks = 0;
    std::int64_t logits_owned_ticks = 0;
    std::int64_t frequency = 0;
};

inline std::int64_t qpc() {
    LARGE_INTEGER value;
    raw_id::require(QueryPerformanceCounter(&value) != 0, "QPC unavailable");
    return value.QuadPart;
}

struct Reply {
    std::uint64_t request_id;
    std::string request_epoch;
    std::size_t local_count;
    int greedy_id;
    bool owned_rows = true;
    std::size_t row_count = raw_id::shared_rows;
    std::size_t speculative_inputs = 0;
    Timing native_timing;
};

// One serial actor and one externally owned engine. No thread may call this
// concurrently. A host controller can retire its epoch while a native call
// finishes, then discard that response; it must never publish a retired reply.
class Bridge {
public:
    explicit Bridge(qwen3_5vl_npu& engine) : engine_(engine) {
        LARGE_INTEGER value;
        raw_id::require(QueryPerformanceFrequency(&value) != 0 && value.QuadPart > 0,
                        "QPC frequency unavailable");
        frequency_ = value.QuadPart;
    }

    Reply begin(std::uint64_t request, std::string epoch, const std::vector<int>& tail512) {
        retire();
        raw_id::require(request < (std::uint64_t{1} << 63), "Request ID is outside nonnegative int64");
        raw_id::require(epoch.size() == 32 && std::all_of(epoch.begin(), epoch.end(), [](char c) {
            return (c >= '0' && c <= '9') || (c >= 'a' && c <= 'f');
        }), "A32-character lowercase hexadecimal epoch is required");
        raw_id::require(seen_epochs_.count(epoch) == 0, "Request epoch was already used");
        raw_id::require(tail512.size() == seed_count, "Seed must be exactly512 authoritative tail IDs");
        for (int id : tail512) raw_id::check_id(id);
        seen_epochs_.insert(epoch);
        request_ = request;
        epoch_ = std::move(epoch);
        const auto started = qpc();
        try {
            engine_.qwen3_5vl_npu::clear_context();
            expect_length(0);
            auto ids = tail512;
            auto logits = raw_id::own_logits(engine_.qwen3_5vl_npu::prefill(ids, nullptr));
            expect_length(seed_count);
            committed_ = tail512;
            logits_ = std::move(logits);
            active_ = true;
            pending_ = true;
            timing_ = Timing{started, qpc(), frequency_};
            return reply();
        } catch (...) { retire(); throw; }
    }

    // The caller must supply an actually observed native target T ID. A
    // predicted ID is never consumed merely because ready_one() returned it.
    Reply append_authoritative(std::uint64_t request, const std::string& epoch, int token) {
        try {
            raw_id::require(active_ && request == request_ && epoch == epoch_,
                            "Authoritative append belongs to a retired or different request");
            raw_id::require(committed_.size() < local_limit, "Planned128 outputs already appended");
            raw_id::check_id(token);
            pending_ = false;
            const auto started = qpc();
            auto logits = raw_id::own_logits(engine_.qwen3_5vl_npu::forward(token));
            expect_length(committed_.size() + 1);
            committed_.push_back(token);
            logits_ = std::move(logits);
            pending_ = committed_.size() < local_limit;
            timing_ = Timing{started, qpc(), frequency_};
            return reply();
        } catch (...) { retire(); throw; }
    }

    // One ID from already owned committed logits. No NPU call and no
    // speculative mutation: consumed_inputs is always zero for this variant.
    std::optional<Reply> ready_one() {
        if (!active_ || !logits_ || committed_.size() >= local_limit) return std::nullopt;
        pending_ = true;
        return reply();
    }

    void cancel(const std::string& epoch) { if (active_ && epoch_ == epoch) retire(); }
    void reset() { retire(); } // A later begin performs the actual context clear.
    bool has_pending() const { return pending_; }
    const std::vector<int>& committed_ids() const { return committed_; }
    const raw_id::OwnedLogits& committed_logits() const {
        raw_id::require(active_ && logits_.has_value(), "No owned committed logits");
        return *logits_; // Invalidated by a later operation, as in the original bridge.
    }

private:
    qwen3_5vl_npu& engine_;
    std::vector<int> committed_;
    std::optional<raw_id::OwnedLogits> logits_;
    std::set<std::string> seen_epochs_;
    std::uint64_t request_ = 0;
    std::string epoch_;
    std::int64_t frequency_ = 0;
    Timing timing_;
    bool active_ = false;
    bool pending_ = false;

    void expect_length(std::size_t count) {
        raw_id::require(engine_.qwen3_5vl_npu::get_current_context_length() == static_cast<int>(count),
                        "Native context length differs from authoritative history");
    }
    Reply reply() const {
        raw_id::require(active_ && logits_.has_value(), "No active native reply");
        return Reply{request_, epoch_, committed_.size(), logits_->greedy_id,
                     true, raw_id::shared_rows, 0, timing_};
    }
    void retire() {
        active_ = pending_ = false;
        logits_.reset();
        committed_.clear();
        epoch_.clear();
    }
};
} // namespace growing_raw
