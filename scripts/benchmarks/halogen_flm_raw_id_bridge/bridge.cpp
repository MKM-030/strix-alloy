// Source-only adapter for the pinned FLM 1.0.7 Windows XRT Qwen3.5 DLL.
// Build and runtime qualification are separate from this source artifact.
#if !defined(_WIN32) || !defined(_M_X64)
#error This adapter requires Windows AMD64 and the pinned XRT DLL ABI.
#endif
#if defined(FLM_USE_HRX)
#error FLM_USE_HRX must be undefined, including when its value would be zero.
#endif

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <limits>
#include <memory>
#include <optional>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>
#include "models/qwen3_5vl/qwen3_5vl_npu.hpp"

namespace raw_id {
constexpr std::size_t shared_rows = 248070;
constexpr std::size_t max_head_rows = 248320;
constexpr std::size_t window_limit = 512;
constexpr std::size_t max_drafts = 3;
constexpr std::size_t max_commands = 64;
constexpr int engine_capacity = 4096; // The pinned DLL clamps smaller requests.
using json = nlohmann::json;
namespace fs = std::filesystem;
using steady_clock = std::chrono::steady_clock;

double elapsed_ms(steady_clock::time_point started) {
    return std::chrono::duration<double, std::milli>(steady_clock::now() - started).count();
}

std::int64_t unix_ms() {
    return std::chrono::duration_cast<std::chrono::milliseconds>(
            std::chrono::system_clock::now().time_since_epoch()).count();
}

void require(bool condition, const char* message) {
    if (!condition) throw std::runtime_error(message);
}

void check_id(int token) {
    require(token >= 0 && static_cast<std::size_t>(token) < shared_rows,
            "raw token ID is outside the shared vocabulary");
}

std::vector<int> parse_ids(const json& value, std::size_t limit, bool empty_ok) {
    require(value.is_array() && value.size() <= limit && (empty_ok || !value.empty()),
            "invalid bounded ID array");
    std::vector<int> ids;
    ids.reserve(value.size());
    for (const auto& item : value) {
        require(item.is_number_integer(), "token IDs must be integers");
        const auto wide = item.get<std::int64_t>();
        require(wide >= 0 && wide < static_cast<std::int64_t>(shared_rows),
                "raw token ID is outside the shared vocabulary");
        ids.push_back(static_cast<int>(wide));
    }
    return ids;
}

json read_json(const fs::path& path) {
    require(fs::is_regular_file(path) && fs::file_size(path) <= 1024 * 1024,
            "JSON input must be a regular file of at most 1 MiB");
    std::ifstream stream(path, std::ios::binary);
    require(stream.good(), "cannot open JSON input");
    auto value = json::parse(stream);
    require(value.is_object(), "JSON input must be an object");
    return value;
}

LM_Config load_config(const fs::path& model_dir, const fs::path& bundle_root) {
    require(fs::is_directory(model_dir), "model directory is missing");
    require(fs::is_regular_file(model_dir / "model.q4nx"), "model.q4nx is missing");
    LM_Config config;
    config.model_path = fs::absolute(model_dir).lexically_normal().string();
    config.model_name = "Qwen3.5-0.8B-NPU2";
    // FLM appends xclbins/<model_name>/<kernel>.xclbin to this root.
    config.exec_path = fs::absolute(bundle_root).lexically_normal().string();
    config._json_config = read_json(model_dir / "config.json");
    for (const auto& [key, expected] : std::vector<std::pair<std::string, int>>{
            {"vocab_size", 248320}, {"hidden_size", 1024},
            {"num_hidden_layers", 24}, {"head_dim", 256},
            {"num_attention_heads", 8}, {"num_key_value_heads", 2}}) {
        require(config._json_config.contains(key) && config._json_config[key] == expected,
                "config does not match the pinned Qwen3.5-0.8B geometry");
    }
    config.flm_version = cfg_get<std::string>(config._json_config, "flm_version", "0.0.0");
    // Deliberately token-only. Disk config and weight files are not changed.
    // Static pinned-DLL inspection identifies is_vlm as the vision ctor/load gate.
    config._json_config["is_vlm"] = false;
    config._json_config["is_audio"] = false;
    const auto kernels = fs::path(config.exec_path) / "xclbins" / config.model_name;
    for (const char* file : {"layer.xclbin", "lm_head.xclbin", "mm.xclbin",
                             "attn.xclbin", "conv.xclbin", "GateDeltaNet_prefill.xclbin"}) {
        require(fs::is_regular_file(kernels / file), "a required token-only xclbin is missing");
    }
    return config;
}

struct OwnedLogits {
    std::vector<bf16> rows;
    int greedy_id = -1;
    float greedy_value = -std::numeric_limits<float>::infinity();
};
static_assert(sizeof(bf16) == 2, "BF16 snapshot files require two-byte native rows");

void write_rows(const fs::path& path, const OwnedLogits& logits) {
    std::ofstream stream(path, std::ios::binary | std::ios::trunc);
    require(stream.good(), "cannot open native BF16 snapshot file");
    stream.write(reinterpret_cast<const char*>(logits.rows.data()),
                 static_cast<std::streamsize>(logits.rows.size() * sizeof(bf16)));
    require(stream.good(), "cannot write native BF16 snapshot file");
}

OwnedLogits own_logits(const buffer<bf16>& raw) {
    require(raw.data() != nullptr && raw.size() >= shared_rows && raw.size() <= max_head_rows,
            "DLL output does not cover the bounded shared vocabulary");
    OwnedLogits owned;
    owned.rows.reserve(shared_rows);
    // Copy BF16 and compute greedy in one native pass, before another engine call.
    // Only supported rows participate; ties retain the first (lowest) ID.
    for (std::size_t index = 0; index < shared_rows; ++index) {
        const bf16 value = raw[index];
        const float converted = static_cast<float>(value);
        require(std::isfinite(converted), "nonfinite supported DLL logit");
        owned.rows.push_back(value);
        if (owned.greedy_id < 0 || converted > owned.greedy_value) {
            owned.greedy_id = static_cast<int>(index);
            owned.greedy_value = converted;
        }
    }
    return owned;
}

// The caller owns the engine/device lifetime and target acceptance authority.
// One synchronous adapter, one pending proposal; never invoke concurrently.
class Bridge {
public:
    explicit Bridge(qwen3_5vl_npu& engine, bool append_when_authoritative = false)
        : engine_(engine), append_when_authoritative_(append_when_authoritative) {}

    void clear_context() {
        retire();
        engine_.qwen3_5vl_npu::clear_context();
        expect_length(0);
    }

    const OwnedLogits& prefill(std::vector<int> ids) {
        retire(); // A failed reset cannot expose an earlier request's logits.
        require(!ids.empty() && ids.size() <= window_limit, "prefill requires 1..512 IDs");
        for (int token : ids) check_id(token);
        return rebuild(std::move(ids));
    }

    // A committed single-token append. At the cap, rebase to tail512 and rebuild.
    const OwnedLogits& forward(int token) {
        require(logits_.has_value() && !pending_, "forward requires an idle committed prefix");
        check_id(token);
        auto ids = committed_;
        ids.push_back(token);
        if (ids.size() > window_limit) {
            ids.erase(ids.begin());
            return rebuild(std::move(ids));
        }
        try {
            auto next = own_logits(engine_.qwen3_5vl_npu::forward(token));
            expect_length(ids.size());
            committed_ = std::move(ids);
            logits_ = std::move(next);
            return *logits_;
        } catch (...) { retire(); throw; }
    }

    std::vector<int> propose(std::size_t count) {
        require(logits_.has_value() && !pending_, "propose requires an idle committed prefix");
        require(count >= 1 && count <= max_drafts, "propose requires 1..3 drafts");
        std::vector<int> drafts;
        drafts.reserve(count);
        int greedy = logits_->greedy_id;
        try {
            for (std::size_t index = 0; index < count; ++index) {
                drafts.push_back(greedy);
                if (index + 1 < count) {
                    auto scratch = own_logits(engine_.qwen3_5vl_npu::forward(greedy));
                    expect_length(committed_.size() + index + 1);
                    greedy = scratch.greedy_id;
                    pending_logits_ = std::move(scratch);
                }
            }
            proposal_ = drafts;
            pending_ = true;
            return drafts;
        } catch (...) { retire(); throw; }
    }

    // accepted must be the independently verified prefix of this proposal.
    // This adapter does not establish native target authority or serialize packets.
    const OwnedLogits& commit(const std::vector<int>& accepted, std::optional<int> extra) {
        require(logits_.has_value() && pending_, "commit requires a pending proposal");
        require(accepted.size() <= proposal_.size() &&
                std::equal(accepted.begin(), accepted.end(), proposal_.begin()),
                "accepted IDs differ from the proposed prefix");
        for (int token : accepted) check_id(token);
        if (extra) check_id(*extra);
        auto ids = committed_;
        ids.insert(ids.end(), accepted.begin(), accepted.end());
        if (extra) ids.push_back(*extra);
        const auto consumed = proposal_.size() - 1;
        const bool can_append = append_when_authoritative_ &&
                accepted.size() >= consumed && ids.size() <= window_limit;
        if (can_append) {
            try {
                // Pending logits describe the consumed accepted prefix. With one
                // draft, committed logits already describe the unchanged engine.
                auto next = consumed == 0 ? std::move(logits_) : std::move(pending_logits_);
                require(next.has_value(), "missing owned logits for accepted engine prefix");
                expect_length(committed_.size() + consumed);
                for (std::size_t index = committed_.size() + consumed; index < ids.size(); ++index) {
                    next = own_logits(engine_.qwen3_5vl_npu::forward(ids[index]));
                    expect_length(index + 1);
                }
                committed_ = std::move(ids);
                logits_ = std::move(next);
                pending_logits_.reset();
                proposal_.clear();
                pending_ = false;
                return *logits_;
            } catch (...) { retire(); throw; }
        }
        if (ids.size() > window_limit)
            ids.erase(ids.begin(), ids.end() - static_cast<std::ptrdiff_t>(window_limit));
        // Default fallback, also mandatory after rejected mutation or window shift.
        return rebuild(std::move(ids));
    }

    const std::vector<int>& committed_ids() const { return committed_; }
    const OwnedLogits& committed_logits() const {
        require(logits_.has_value(), "no committed logits are available");
        return *logits_;
    }
    const OwnedLogits* speculative_logits() const {
        return pending_ && pending_logits_ ? &*pending_logits_ : nullptr;
    }

private:
    qwen3_5vl_npu& engine_;
    std::vector<int> committed_;
    std::optional<OwnedLogits> logits_;
    std::optional<OwnedLogits> pending_logits_;
    std::vector<int> proposal_;
    bool pending_ = false;
    const bool append_when_authoritative_;

    void retire() {
        logits_.reset();
        pending_logits_.reset();
        committed_.clear();
        proposal_.clear();
        pending_ = false;
    }
    void expect_length(std::size_t expected) {
        require(engine_.qwen3_5vl_npu::get_current_context_length() == static_cast<int>(expected),
                "DLL context length differs from the adapter's consumed IDs");
    }
    const OwnedLogits& rebuild(std::vector<int> ids) {
        retire();
        try {
            engine_.qwen3_5vl_npu::clear_context();
            expect_length(0);
            auto next = own_logits(engine_.qwen3_5vl_npu::prefill(ids, nullptr));
            expect_length(ids.size());
            committed_ = std::move(ids);
            logits_ = std::move(next);
            return *logits_;
        } catch (...) { retire(); throw; }
    }
};

void validate_commands(const json& input) {
    require(!input.contains("append_when_authoritative") || input["append_when_authoritative"].is_boolean(),
            "append_when_authoritative must be an explicit boolean");
    require(input.contains("commands") && input["commands"].is_array() &&
            !input["commands"].empty() && input["commands"].size() <= max_commands,
            "input requires 1..64 commands");
    for (const auto& command : input["commands"]) {
        require(command.is_object(), "command must be an object");
        const auto op = command.at("op").get<std::string>();
        if (op == "clear") continue;
        if (op == "prefill") { parse_ids(command.at("ids"), window_limit, false); continue; }
        if (op == "forward") { parse_ids(json::array({command.at("id")}), 1, false); continue; }
        if (op == "propose") {
            const auto& count = command.at("count");
            require(count.is_number_integer() && count >= 1 && count <= max_drafts,
                    "propose count must be an integer in 1..3");
            continue;
        }
        if (op == "commit") {
            parse_ids(command.at("accepted_ids"), max_drafts, true);
            const auto& extra = command.at("correction_or_bonus");
            if (!extra.is_null()) parse_ids(json::array({extra}), 1, false);
            continue;
        }
        throw std::runtime_error("unknown command operation");
    }
}
} // namespace raw_id

#ifndef RAW_ID_BRIDGE_NO_MAIN
int main(int argc, char** argv) {
    using namespace raw_id;
    try {
        require(argc == 6 && std::string(argv[1]) == "--run",
                "usage: bridge.exe --run MODEL_DIR XCLBIN_BUNDLE_ROOT COMMANDS.json OUTPUT.json");
        const auto input = read_json(argv[4]);
        validate_commands(input); // Validate bounded syntax before device initialization.
        auto config = load_config(argv[2], argv[3]);
        const fs::path output_path(argv[5]);
        const fs::path rows_dir(std::string(argv[5]) + ".rows");
        require(!fs::exists(output_path) && !fs::exists(rows_dir),
                "output JSON and derived .rows directory must be fresh unique paths");
        require(fs::create_directory(rows_dir), "cannot create BF16 snapshot directory");
        const auto startup_started_unix_ms = unix_ms();
        const auto device_started = steady_clock::now();
        // Destruction order is engine -> manager -> device. No borrowed state outlives them.
        flm_rt::device device(0);
        npu_xclbin_manager manager(device_npu2, &device, false);
        const auto device_manager_ms = elapsed_ms(device_started);
        const auto ctor_started = steady_clock::now();
        qwen3_5vl_npu engine(config, &manager, engine_capacity);
        const auto model_ctor_ms = elapsed_ms(ctor_started);
        const auto load_started = steady_clock::now();
        {
            Q4NX weights(config.model_path);
            engine.qwen3_5vl_npu::load_weights(weights);
        }
        const auto weights_load_ms = elapsed_ms(load_started);
        const bool append_enabled = input.value("append_when_authoritative", false);
        Bridge bridge(engine, append_enabled);
        bridge.clear_context();
        json output = {{"format", "flm-raw-id-source-bridge-v1"},
                       {"shared_rows", shared_rows}, {"window_limit", window_limit},
                       {"engine_capacity_requested", engine_capacity},
                       {"append_when_authoritative", append_enabled},
                       {"startup_started_unix_ms", startup_started_unix_ms},
                       {"startup_ended_unix_ms", unix_ms()},
                       {"device_manager_ms", device_manager_ms},
                       {"model_ctor_ms", model_ctor_ms}, {"weights_load_ms", weights_load_ms},
                       {"bf16_rows_directory", fs::absolute(rows_dir).string()},
                       {"results", json::array()}};
        std::size_t command_index = 0;
        for (const auto& command : input["commands"]) {
            const auto op = command.at("op").get<std::string>();
            json result = {{"op", op}, {"started_unix_ms", unix_ms()}};
            const auto command_started = steady_clock::now();
            if (op == "clear") bridge.clear_context();
            else if (op == "prefill") bridge.prefill(parse_ids(command.at("ids"), window_limit, false));
            else if (op == "forward") bridge.forward(command.at("id").get<int>());
            else if (op == "propose") result["draft_ids"] = bridge.propose(command.at("count").get<std::size_t>());
            else if (op == "commit") {
                const auto& extra = command.at("correction_or_bonus");
                bridge.commit(parse_ids(command.at("accepted_ids"), max_drafts, true),
                              extra.is_null() ? std::nullopt : std::optional<int>(extra.get<int>()));
            }
            result["elapsed_ms"] = elapsed_ms(command_started);
            result["ended_unix_ms"] = unix_ms();
            result["committed_length"] = bridge.committed_ids().size();
            if (op != "clear") {
                const auto file = "command-" + std::to_string(command_index) + "-committed.bf16";
                write_rows(rows_dir / file, bridge.committed_logits());
                result["committed_bf16_file"] = file;
                result["committed_greedy_id"] = bridge.committed_logits().greedy_id;
                result["bf16_row_count"] = shared_rows;
                if (const auto* speculative = bridge.speculative_logits()) {
                    const auto pending_file = "command-" + std::to_string(command_index) + "-speculative.bf16";
                    write_rows(rows_dir / pending_file, *speculative);
                    result["speculative_bf16_file"] = pending_file;
                    result["speculative_greedy_id"] = speculative->greedy_id;
                }
            }
            output["results"].push_back(std::move(result));
            ++command_index;
        }
        // Keep machine-readable output separate from possible FLM stdout logging.
        std::ofstream stream(argv[5], std::ios::binary | std::ios::trunc);
        require(stream.good(), "cannot open output file");
        stream << output.dump(2) << '\n';
        require(stream.good(), "cannot write output file");
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "raw-ID bridge failed: " << error.what() << '\n';
        return 1;
    }
}
#endif // RAW_ID_BRIDGE_NO_MAIN
