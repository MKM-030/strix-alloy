// Source-only finite adapter for the pinned Laurent CPU/Vulkan llama.cpp bundle.
// Root owns compilation, DLL/model qualification, execution and target lifecycle.
#if !defined(_WIN32) || !defined(_M_X64)
#error This adapter requires Windows AMD64 and the pinned native C API ABI.
#endif
#if !defined(LLAMA_SHARED) || !defined(GGML_SHARED)
#error Compile with LLAMA_SHARED and GGML_SHARED, using the matching import libraries.
#endif
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#ifndef NOMINMAX
#define NOMINMAX
#endif
#ifndef _WIN32_WINNT
#define _WIN32_WINNT 0x0602
#endif
#include <windows.h>
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
#include "llama.h"
#include "nlohmann/json.hpp"
#include "replay_policy.h"

// The link command MUST delay all three directly imported llama/ggml DLLs.
// MSVC does not accept /DELAYLOAD in #pragma comment(linker). Verify the PE.
#pragma comment(lib, "delayimp.lib")

namespace raw_id {
using json = nlohmann::json;
namespace fs = std::filesystem;
using steady_clock = std::chrono::steady_clock;
constexpr std::size_t shared_rows = 248070;
constexpr std::size_t max_head_rows = 248320;
constexpr std::size_t window_limit = 512;
constexpr std::size_t max_drafts = 3;
constexpr std::size_t max_replay_outputs = max_drafts + 1;
constexpr std::size_t max_commands = 64;
constexpr std::uint32_t context_capacity = 1024;
constexpr std::int32_t cpu_threads = 4;
constexpr std::uintmax_t model_bytes = 563036064;
constexpr std::int64_t startup_budget_ms = 120000;
constexpr const char* source_revision = "3466b48806f9fefe1162aa4053ffebcfcabe83aa";
static_assert(sizeof(float) == 4 && std::numeric_limits<float>::is_iec559,
              "snapshots require native IEEE-754 F32 rows");
static_assert(sizeof(llama_token) == 4 && sizeof(llama_pos) == 4,
              "raw IDs and positions require the pinned int32 C API");

void require(bool condition, const char* message) {
    if (!condition) throw std::runtime_error(message);
}
double elapsed_ms(steady_clock::time_point started) {
    return std::chrono::duration<double, std::milli>(steady_clock::now() - started).count();
}
std::int64_t unix_ms() {
    return std::chrono::duration_cast<std::chrono::milliseconds>(
            std::chrono::system_clock::now().time_since_epoch()).count();
}
struct StartupBudget {
    const steady_clock::time_point started = steady_clock::now();
    bool available() const noexcept {
        return steady_clock::now() - started <= std::chrono::milliseconds(startup_budget_ms);
    }
    void check() const { require(available(), "cooperative startup budget exceeded"); }
};
bool load_progress(float, void* user_data) noexcept {
    return static_cast<const StartupBudget*>(user_data)->available();
}
void check_id(llama_token token) {
    require(token >= 0 && static_cast<std::size_t>(token) < shared_rows,
            "raw token ID is outside the shared vocabulary");
}
std::vector<llama_token> parse_ids(const json& value, std::size_t limit, bool empty_ok) {
    require(value.is_array() && value.size() <= limit && (empty_ok || !value.empty()),
            "invalid bounded ID array");
    std::vector<llama_token> ids;
    ids.reserve(value.size());
    for (const auto& item : value) {
        require(item.is_number_integer(), "token IDs must be integers");
        const auto wide = item.get<std::int64_t>();
        require(wide >= 0 && wide < static_cast<std::int64_t>(shared_rows),
                "raw token ID is outside the shared vocabulary");
        ids.push_back(static_cast<llama_token>(wide));
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
        if (op == "resolve_replay") {
            parse_ids(command.at("ids"), max_replay_outputs, true);
            parse_ids(json::array({command.at("opening_reference_id")}), 1, false);
            continue;
        }
        throw std::runtime_error("unknown command operation");
    }
}

// DLL search is process-local. Import thunks are delayed until after this scope
// preloads the complete pinned bundle and verifies each resolved module path.
class LoadedBundle {
public:
    explicit LoadedBundle(const fs::path& requested) : root_(fs::canonical(requested)) {
        require(fs::is_directory(root_), "DLL bundle directory is missing");
        for (const wchar_t* name : names_) {
            require(fs::is_regular_file(root_ / name), "a required bundle DLL is missing");
            require(GetModuleHandleW(name) == nullptr, "a llama/ggml DLL was already loaded before bundle selection");
        }
        require(SetDefaultDllDirectories(LOAD_LIBRARY_SEARCH_SYSTEM32 | LOAD_LIBRARY_SEARCH_USER_DIRS) != 0,
                "cannot restrict process DLL search");
        cookie_ = AddDllDirectory(root_.c_str());
        require(cookie_ != nullptr, "cannot add the exact DLL bundle directory");
        try {
            for (const wchar_t* name : names_) {
                const auto path = root_ / name;
                auto module = LoadLibraryExW(path.c_str(), nullptr, LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR |
                        LOAD_LIBRARY_SEARCH_SYSTEM32 | LOAD_LIBRARY_SEARCH_USER_DIRS);
                require(module != nullptr, "cannot load a pinned bundle DLL or its system dependency");
                modules_.push_back(module);
                std::vector<wchar_t> resolved(32768);
                const auto length = GetModuleFileNameW(module, resolved.data(), static_cast<DWORD>(resolved.size()));
                require(length != 0 && length < resolved.size(), "cannot resolve the loaded DLL path");
                require(fs::equivalent(path, fs::path(std::wstring(resolved.data(), length))),
                        "loaded DLL path differs from the selected bundle");
            }
        } catch (...) { close(); throw; }
    }
    ~LoadedBundle() { close(); }
    LoadedBundle(const LoadedBundle&) = delete;
    LoadedBundle& operator=(const LoadedBundle&) = delete;
    const fs::path& root() const { return root_; }
private:
    const wchar_t* names_[5] = {L"ggml-base.dll", L"ggml-cpu.dll", L"ggml-vulkan.dll", L"ggml.dll", L"llama.dll"};
    fs::path root_;
    DLL_DIRECTORY_COOKIE cookie_ = nullptr;
    std::vector<HMODULE> modules_;
    void close() noexcept {
        for (auto it = modules_.rbegin(); it != modules_.rend(); ++it) FreeLibrary(*it);
        modules_.clear();
        if (cookie_) { RemoveDllDirectory(cookie_); cookie_ = nullptr; }
    }
};
struct BackendScope {
    BackendScope() { llama_backend_init(); }
    ~BackendScope() { llama_backend_free(); }
    BackendScope(const BackendScope&) = delete;
    BackendScope& operator=(const BackendScope&) = delete;
};
struct ModelDelete { void operator()(llama_model* model) const { llama_model_free(model); } };
struct ContextDelete { void operator()(llama_context* context) const { llama_free(context); } };
using Model = std::unique_ptr<llama_model, ModelDelete>;
using Context = std::unique_ptr<llama_context, ContextDelete>;

std::size_t parse_device_index(const std::string& text) {
    require(!text.empty() && std::all_of(text.begin(), text.end(), [](char c) { return c >= '0' && c <= '9'; }),
            "device index must be an explicit nonnegative decimal integer");
    const auto wide = std::stoull(text);
    require(wide <= 64, "device index exceeds the finite device-selection bound");
    return static_cast<std::size_t>(wide);
}
ggml_backend_dev_t select_device(bool vulkan, std::size_t index) {
    const auto reg = ggml_backend_reg_by_name(vulkan ? "Vulkan" : "CPU");
    require(reg != nullptr && index < ggml_backend_reg_dev_count(reg), "requested backend/device is absent");
    auto device = ggml_backend_reg_dev_get(reg, index);
    require(device != nullptr, "requested backend device is null");
    const auto type = ggml_backend_dev_type(device);
    require(vulkan ? (type == GGML_BACKEND_DEVICE_TYPE_GPU || type == GGML_BACKEND_DEVICE_TYPE_IGPU)
                   : (type == GGML_BACKEND_DEVICE_TYPE_CPU), "backend device has an unexpected type");
    return device;
}

struct OwnedLogits {
    std::vector<float> rows; // Full native vocabulary, including rows excluded from greedy.
    llama_token greedy_id = -1;
    float greedy_value = -std::numeric_limits<float>::infinity();
};
void write_rows(const fs::path& path, const OwnedLogits& logits) {
    std::ofstream stream(path, std::ios::binary | std::ios::trunc);
    require(stream.good(), "cannot open native F32 snapshot file");
    stream.write(reinterpret_cast<const char*>(logits.rows.data()),
                 static_cast<std::streamsize>(logits.rows.size() * sizeof(float)));
    stream.flush();
    require(stream.good(), "cannot write native F32 snapshot file");
    stream.close();
    require(stream.good(), "cannot close native F32 snapshot file");
}
class Batch {
public:
    explicit Batch(std::size_t capacity) : value(llama_batch_init(static_cast<std::int32_t>(capacity), 0, 1)) {
        if (!value.token || !value.pos || !value.n_seq_id || !value.seq_id || !value.logits) {
            llama_batch_free(value);
            throw std::runtime_error("cannot allocate an owned raw-ID batch");
        }
    }
    ~Batch() { llama_batch_free(value); }
    Batch(const Batch&) = delete;
    Batch& operator=(const Batch&) = delete;
    llama_batch value;
};

// Synchronous, one owned context and one pending proposal. CLI acceptance and
// opening equality are caller-supplied replay evidence, never target verification.
// No partial removal/rollback is used.
class Bridge {
public:
    Bridge(llama_context& context, std::size_t head_rows, bool append_when_authoritative = false)
        : context_(context), head_rows_(head_rows), append_when_authoritative_(append_when_authoritative) {
        require(head_rows >= shared_rows && head_rows <= max_head_rows, "native vocabulary is outside the pinned row bound");
        require(llama_get_memory(&context_) != nullptr, "context has no hybrid memory");
    }
    void begin_command() { calls_ = json::array(); update_path_ = "none"; }
    const json& native_calls() const { return calls_; }
    const char* update_path() const { return update_path_; }
    std::uint64_t context_epoch() const { return epoch_; }
    void clear_context() {
        retire();
        clear_engine();
    }
    const OwnedLogits& prefill(std::vector<llama_token> ids) {
        require(!ids.empty() && ids.size() <= window_limit, "prefill requires 1..512 IDs");
        for (auto token : ids) check_id(token);
        return rebuild(std::move(ids));
    }
    const OwnedLogits& forward(llama_token token) {
        require(logits_.has_value() && !pending_, "forward requires an idle committed prefix");
        check_id(token);
        auto ids = committed_;
        ids.push_back(token);
        if (ids.size() > window_limit) {
            ids.erase(ids.begin());
            return rebuild(std::move(ids));
        }
        try {
            auto next = decode({token}, committed_.size(), "authoritative_forward");
            committed_ = std::move(ids);
            logits_ = std::move(next);
            update_path_ = "authoritative_append";
            return *logits_;
        } catch (...) { invalidate(); throw; }
    }
    std::vector<llama_token> propose(std::size_t count) {
        require(logits_.has_value() && !pending_, "propose requires an idle committed prefix");
        require(count >= 1 && count <= max_drafts, "propose requires 1..3 drafts");
        std::vector<llama_token> drafts;
        drafts.reserve(count);
        auto greedy = logits_->greedy_id;
        try {
            for (std::size_t index = 0; index < count; ++index) {
                drafts.push_back(greedy);
                if (index + 1 < count) {
                    auto next = decode({greedy}, committed_.size() + index, "speculative_forward");
                    greedy = next.greedy_id;
                    pending_logits_ = std::move(next);
                }
            }
            proposal_ = drafts;
            pending_ = true;
            pending_epoch_ = epoch_;
            return drafts;
        } catch (...) { invalidate(); throw; }
    }
    const OwnedLogits& commit(const std::vector<llama_token>& accepted, std::optional<llama_token> extra) {
        require(logits_.has_value() && pending_ && pending_epoch_ == epoch_, "commit requires this context's pending proposal");
        require(accepted.size() <= proposal_.size() &&
                std::equal(accepted.begin(), accepted.end(), proposal_.begin()),
                "accepted IDs differ from the proposed prefix");
        for (auto token : accepted) check_id(token);
        if (extra) check_id(*extra);
        auto ids = committed_;
        ids.insert(ids.end(), accepted.begin(), accepted.end());
        if (extra) ids.push_back(*extra);
        const auto consumed = proposal_.size() - 1;
        const bool can_append = append_when_authoritative_ && accepted.size() >= consumed && ids.size() <= window_limit;
        if (can_append) {
            try {
                const auto old_length = committed_.size();
                expect_length(old_length + consumed);
                auto next = consumed == 0 ? std::move(logits_) : std::move(pending_logits_);
                require(next.has_value(), "missing owned logits for the consumed accepted prefix");
                retire(); // No available feed remains while authoritative mutation runs.
                for (std::size_t index = old_length + consumed; index < ids.size(); ++index)
                    next = decode({ids[index]}, index, "authoritative_forward");
                committed_ = std::move(ids);
                logits_ = std::move(next);
                update_path_ = "authoritative_append";
                return *logits_;
            } catch (...) { invalidate(); throw; }
        }
        if (ids.size() > window_limit)
            ids.erase(ids.begin(), ids.end() - static_cast<std::ptrdiff_t>(window_limit));
        return rebuild(std::move(ids)); // Rejected mutation, window shift or default policy.
    }
    bool opening_reference_equal(llama_token reference) const {
        check_id(reference);
        require(logits_.has_value() && pending_ && pending_epoch_ == epoch_ && !proposal_.empty(),
                "opening comparison requires this context's pending proposal");
        return proposal_.front() == reference;
    }
    const OwnedLogits& resolve_replay(const std::vector<llama_token>& authoritative_ids, bool reuse_permitted) {
        require(logits_.has_value() && pending_ && pending_epoch_ == epoch_,
                "resolve_replay requires this context's pending proposal");
        require(authoritative_ids.size() <= max_replay_outputs, "resolve_replay requires 0..4 retained output IDs");
        for (auto token : authoritative_ids) check_id(token);
        auto ids = committed_;
        ids.insert(ids.end(), authoritative_ids.begin(), authoritative_ids.end());
        require(!ids.empty(), "resolve_replay requires a nonempty resulting committed prefix");
        const auto consumed = proposal_.size() - 1;
        const bool can_append = replay_append_eligible(append_when_authoritative_, reuse_permitted,
                                                       committed_.size(), proposal_, authoritative_ids);
        if (can_append) {
            try {
                const auto old_length = committed_.size();
                expect_length(old_length + consumed);
                auto next = consumed == 0 ? std::move(logits_) : std::move(pending_logits_);
                require(next.has_value(), "missing owned logits for the consumed replay prefix");
                const std::vector<llama_token> suffix(authoritative_ids.begin() + consumed, authoritative_ids.end());
                retire(); // No available feed remains while authoritative mutation runs.
                if (!suffix.empty()) {
                    next = decode(suffix, old_length + consumed, "authoritative_replay");
                }
                committed_ = std::move(ids);
                logits_ = std::move(next);
                update_path_ = "authoritative_append";
                return *logits_;
            } catch (...) { invalidate(); throw; }
        }
        if (ids.size() > window_limit)
            ids.erase(ids.begin(), ids.end() - static_cast<std::ptrdiff_t>(window_limit));
        return rebuild(std::move(ids));
    }
    const std::vector<llama_token>& committed_ids() const { return committed_; }
    const OwnedLogits& committed_logits() const {
        require(logits_.has_value(), "no committed logits are available");
        return *logits_;
    }
    const OwnedLogits* speculative_logits() const {
        return pending_ && pending_logits_ ? &*pending_logits_ : nullptr;
    }
    std::size_t consumed_speculative_ids() const { return pending_ ? proposal_.size() - 1 : 0; }
private:
    llama_context& context_;
    const std::size_t head_rows_;
    const bool append_when_authoritative_;
    std::vector<llama_token> committed_;
    std::optional<OwnedLogits> logits_;
    std::optional<OwnedLogits> pending_logits_;
    std::vector<llama_token> proposal_;
    bool pending_ = false;
    std::uint64_t epoch_ = 0;
    std::uint64_t pending_epoch_ = 0;
    json calls_ = json::array();
    const char* update_path_ = "none";
    void retire() {
        logits_.reset(); pending_logits_.reset(); committed_.clear(); proposal_.clear(); pending_ = false; ++epoch_;
    }
    void expect_length(std::size_t expected) const {
        require(expected <= context_capacity, "consumed state exceeds the requested context capacity");
        const auto maximum = llama_memory_seq_pos_max(llama_get_memory(&context_), 0);
        require(maximum == (expected == 0 ? -1 : static_cast<llama_pos>(expected - 1)),
                "native memory position differs from the adapter's consumed IDs");
    }
    void clear_engine() {
        const auto started = steady_clock::now();
        llama_synchronize(&context_);
        llama_memory_clear(llama_get_memory(&context_), true); // Clears attention and recurrent data/metadata.
        llama_synchronize(&context_);
        expect_length(0);
        calls_.push_back({{"kind", "clear_both_caches"}, {"elapsed_ms", elapsed_ms(started)}});
    }
    void invalidate() noexcept {
        retire();
        try { clear_engine(); } catch (...) {} // Preserve the original failure; no live owned feed survives.
    }
    OwnedLogits decode(const std::vector<llama_token>& ids, std::size_t start_position, const char* kind) {
        require(!ids.empty() && ids.size() <= window_limit && start_position + ids.size() <= context_capacity,
                "decode exceeds the finite batch/context bound");
        expect_length(start_position);
        Batch batch(ids.size());
        batch.value.n_tokens = static_cast<std::int32_t>(ids.size());
        for (std::size_t index = 0; index < ids.size(); ++index) {
            check_id(ids[index]);
            require(batch.value.seq_id[index] != nullptr, "raw-ID batch sequence storage is null");
            batch.value.token[index] = ids[index];
            batch.value.pos[index] = static_cast<llama_pos>(start_position + index);
            batch.value.n_seq_id[index] = 1;
            batch.value.seq_id[index][0] = 0;
            batch.value.logits[index] = index + 1 == ids.size() ? 1 : 0;
        }
        json call = {{"kind", kind}, {"input_tokens", ids.size()}, {"start_position", start_position}};
        auto started = steady_clock::now();
        const auto status = llama_decode(&context_, batch.value);
        call["decode_dispatch_ms"] = elapsed_ms(started);
        require(status == 0, "native decode returned a warning/error; discard this context");
        started = steady_clock::now();
        llama_synchronize(&context_);
        call["synchronize_ms"] = elapsed_ms(started);
        expect_length(start_position + ids.size());
        started = steady_clock::now();
        const float* raw = llama_get_logits_ith(&context_, -1); // Also synchronizes in this exact source revision.
        call["logits_readiness_ms"] = elapsed_ms(started);
        require(raw != nullptr, "native decode produced no final logits");
        OwnedLogits owned;
        started = steady_clock::now();
        owned.rows.assign(raw, raw + head_rows_); // Full F32 head owned before any further engine call.
        call["logits_copy_ms"] = elapsed_ms(started);
        started = steady_clock::now();
        for (std::size_t index = 0; index < shared_rows; ++index) {
            const float value = owned.rows[index];
            require(std::isfinite(value), "nonfinite supported native logit");
            if (owned.greedy_id < 0 || value > owned.greedy_value) {
                owned.greedy_id = static_cast<llama_token>(index);
                owned.greedy_value = value;
            }
        }
        call["greedy_ms"] = elapsed_ms(started);
        calls_.push_back(std::move(call));
        return owned;
    }
    const OwnedLogits& rebuild(std::vector<llama_token> ids) {
        retire();
        try {
            clear_engine();
            auto next = decode(ids, 0, "prefill");
            committed_ = std::move(ids);
            logits_ = std::move(next);
            update_path_ = "clear_rebuild";
            return *logits_;
        } catch (...) { invalidate(); throw; }
    }
};
} // namespace raw_id

#ifndef RAW_ID_BRIDGE_NO_MAIN
int main(int argc, char** argv) {
    using namespace raw_id;
    const auto run_started = steady_clock::now();
    const auto run_started_unix_ms = unix_ms();
    try {
        require(argc == 8 && std::string(argv[1]) == "--run",
                "usage: bridge.exe --run MODEL.gguf DLL_BUNDLE_DIR cpu|vulkan DEVICE_INDEX COMMANDS.json OUTPUT.json");
        const auto input = read_json(argv[6]);
        validate_commands(input); // Only syntax/range checks; labels never enter prediction calls.
        const std::string backend_name(argv[4]);
        require(backend_name == "cpu" || backend_name == "vulkan", "backend must be explicitly cpu or vulkan");
        const bool vulkan = backend_name == "vulkan";
        const auto device_index = parse_device_index(argv[5]);
        require(vulkan || device_index == 0, "CPU mode requires device index 0");
        const auto model_path = fs::canonical(argv[2]);
        require(fs::is_regular_file(model_path) && fs::file_size(model_path) == model_bytes,
                "GGUF must have the exact pinned 563036064-byte payload length");
        const fs::path output_path(argv[7]);
        const fs::path rows_dir(std::string(argv[7]) + ".rows");
        require(!fs::exists(output_path) && !fs::exists(rows_dir), "output JSON and .rows directory must be fresh unique paths");
        require(fs::create_directory(rows_dir), "cannot create F32 snapshot directory");
        const auto startup_started_unix_ms = unix_ms();
        StartupBudget startup_budget;
        auto started = steady_clock::now();
        LoadedBundle bundle(argv[3]);
        const auto dll_load_ms = elapsed_ms(started);
        startup_budget.check();
        started = steady_clock::now();
        BackendScope backend;
        auto device = select_device(vulkan, device_index);
        const auto backend_device_ms = elapsed_ms(started);
        startup_budget.check();
        ggml_backend_dev_props props{};
        ggml_backend_dev_get_props(device, &props);
        ggml_backend_dev_t devices[2] = {vulkan ? device : nullptr, nullptr};
        auto model_params = llama_model_default_params();
        model_params.devices = devices; // CPU: explicit empty list, never automatic GPU selection.
        model_params.n_gpu_layers = vulkan ? -1 : 0;
        model_params.split_mode = LLAMA_SPLIT_MODE_NONE;
        model_params.main_gpu = 0;
        model_params.load_mtp = false;
        model_params.ple_on_disk = false;
        model_params.ple_direct_io = false;
        model_params.progress_callback = load_progress;
        model_params.progress_callback_user_data = &startup_budget;
        started = steady_clock::now();
        Model model(llama_model_load_from_file(model_path.string().c_str(), model_params));
        require(model != nullptr, "cannot load the qualified Qwen3.5 GGUF");
        const auto model_load_ms = elapsed_ms(started);
        startup_budget.check();
        const auto vocab = llama_model_get_vocab(model.get());
        require(vocab != nullptr && llama_vocab_n_tokens(vocab) == static_cast<std::int32_t>(max_head_rows) &&
                llama_model_n_layer(model.get()) == 24 && llama_model_n_embd(model.get()) == 1024 &&
                llama_model_is_hybrid(model.get()) && llama_model_has_decoder(model.get()) && !llama_model_has_encoder(model.get()),
                "model does not have the pinned Qwen3.5-0.8B text geometry");
        auto context_params = llama_context_default_params();
        context_params.n_ctx = context_capacity;
        context_params.n_batch = static_cast<std::uint32_t>(window_limit);
        context_params.n_ubatch = static_cast<std::uint32_t>(window_limit);
        context_params.n_seq_max = 1;
        context_params.n_rs_seq = 0;
        context_params.n_outputs_max = 1;
        context_params.n_outputs_max_per_seq = 1;
        context_params.n_threads = cpu_threads;
        context_params.n_threads_batch = cpu_threads;
        context_params.ctx_type = LLAMA_CONTEXT_TYPE_DEFAULT;
        context_params.offload_kqv = vulkan;
        context_params.op_offload = vulkan;
        context_params.embeddings = false;
        context_params.samplers = nullptr;
        context_params.n_samplers = 0;
        context_params.ctx_other = nullptr;
        context_params.no_perf = false;
        started = steady_clock::now();
        Context context(llama_init_from_model(model.get(), context_params));
        require(context != nullptr, "cannot initialize the bounded raw-ID context");
        llama_synchronize(context.get());
        const auto context_init_ms = elapsed_ms(started);
        startup_budget.check();
        require(llama_n_ctx(context.get()) == context_capacity && llama_n_ctx_seq(context.get()) == context_capacity &&
                llama_n_seq_max(context.get()) == 1 && llama_n_rs_seq(context.get()) == 0 &&
                llama_n_batch(context.get()) <= window_limit && llama_n_ubatch(context.get()) <= window_limit &&
                llama_n_threads(context.get()) == cpu_threads && llama_n_threads_batch(context.get()) == cpu_threads,
                "actual context geometry exceeds/differs from the finite requested bounds");
        const bool append_enabled = input.value("append_when_authoritative", false);
        Bridge bridge(*context, max_head_rows, append_enabled);
        bridge.clear_context();
        json output = {{"format", "llama-raw-id-source-bridge-v1"}, {"source_revision", source_revision},
                       {"process_id", GetCurrentProcessId()}, {"backend", backend_name}, {"device_index", device_index},
                       {"device_name", ggml_backend_dev_name(device)}, {"device_description", ggml_backend_dev_description(device)},
                       {"device_id", props.device_id ? props.device_id : ""}, {"dll_bundle_directory", bundle.root().string()},
                       {"model_file", model_path.string()}, {"shared_rows", shared_rows}, {"f32_row_count", max_head_rows},
                       {"window_limit", window_limit}, {"replay_output_limit", max_replay_outputs},
                       {"actual_n_ctx", llama_n_ctx(context.get())},
                       {"actual_n_ctx_seq", llama_n_ctx_seq(context.get())}, {"actual_n_batch", llama_n_batch(context.get())},
                       {"actual_n_ubatch", llama_n_ubatch(context.get())}, {"n_threads", cpu_threads}, {"n_threads_batch", cpu_threads},
                       {"requested_n_outputs_max", 1}, {"requested_n_outputs_max_per_seq", 1},
                       {"requested_n_gpu_layers", model_params.n_gpu_layers}, {"offload_kqv", vulkan}, {"op_offload", vulkan},
                       {"append_when_authoritative", append_enabled}, {"startup_started_unix_ms", startup_started_unix_ms},
                       {"startup_ended_unix_ms", unix_ms()}, {"dll_load_ms", dll_load_ms}, {"backend_device_ms", backend_device_ms},
                       {"model_load_ms", model_load_ms}, {"context_init_ms", context_init_ms},
                       {"cooperative_startup_budget_ms", startup_budget_ms},
                       {"f32_rows_directory", fs::absolute(rows_dir).string()}, {"results", json::array()}};
        std::size_t command_index = 0;
        for (const auto& command : input["commands"]) {
            const auto op = command.at("op").get<std::string>();
            json result = {{"op", op}, {"started_unix_ms", unix_ms()}, {"command_index", command_index}};
            bridge.begin_command();
            const auto command_started = steady_clock::now();
            if (op == "clear") bridge.clear_context();
            else if (op == "prefill") bridge.prefill(parse_ids(command.at("ids"), window_limit, false));
            else if (op == "forward") bridge.forward(command.at("id").get<llama_token>());
            else if (op == "propose") result["draft_ids"] = bridge.propose(command.at("count").get<std::size_t>());
            else if (op == "commit") {
                const auto& extra = command.at("correction_or_bonus");
                bridge.commit(parse_ids(command.at("accepted_ids"), max_drafts, true),
                              extra.is_null() ? std::nullopt : std::optional<llama_token>(extra.get<llama_token>()));
            }
            else if (op == "resolve_replay") {
                const auto ids = parse_ids(command.at("ids"), max_replay_outputs, true);
                const auto reference = command.at("opening_reference_id").get<llama_token>();
                const bool opening_equal = bridge.opening_reference_equal(reference);
                result["opening_reference_id"] = reference;
                result["opening_reference_equal"] = opening_equal;
                result["replay_consumed_inputs"] = bridge.consumed_speculative_ids();
                result["replay_ids"] = ids;
                bridge.resolve_replay(ids, opening_equal);
            }
            result["elapsed_ms"] = elapsed_ms(command_started);
            result["ended_unix_ms"] = unix_ms();
            result["native_calls"] = bridge.native_calls();
            result["update_path"] = bridge.update_path();
            result["context_epoch"] = bridge.context_epoch();
            result["committed_length"] = bridge.committed_ids().size();
            result["committed_ids"] = bridge.committed_ids();
            result["consumed_speculative_ids"] = bridge.consumed_speculative_ids();
            double snapshot_write_ms = 0.0;
            if (op != "clear") {
                const auto file = "command-" + std::to_string(command_index) + "-committed.f32";
                auto snapshot_started = steady_clock::now();
                write_rows(rows_dir / file, bridge.committed_logits());
                snapshot_write_ms += elapsed_ms(snapshot_started);
                result["committed_f32_file"] = file;
                result["committed_greedy_id"] = bridge.committed_logits().greedy_id;
                result["f32_row_count"] = bridge.committed_logits().rows.size();
                if (const auto* speculative = bridge.speculative_logits()) {
                    const auto pending_file = "command-" + std::to_string(command_index) + "-speculative.f32";
                    snapshot_started = steady_clock::now();
                    write_rows(rows_dir / pending_file, *speculative);
                    snapshot_write_ms += elapsed_ms(snapshot_started);
                    result["speculative_f32_file"] = pending_file;
                    result["speculative_greedy_id"] = speculative->greedy_id;
                }
            }
            result["snapshot_write_ms"] = snapshot_write_ms;
            output["results"].push_back(std::move(result));
            ++command_index;
        }
        output["run_started_unix_ms"] = run_started_unix_ms;
        output["run_ended_unix_ms"] = unix_ms();
        output["run_elapsed_ms_before_manifest_write"] = elapsed_ms(run_started);
        // Separate from library stdout. A failed command leaves no success manifest.
        std::ofstream stream(output_path, std::ios::binary | std::ios::trunc);
        require(stream.good(), "cannot open output manifest");
        stream << output.dump(2) << '\n';
        stream.flush();
        require(stream.good(), "cannot write output manifest");
        stream.close();
        require(stream.good(), "cannot close output manifest");
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "raw-ID llama bridge failed: " << error.what() << '\n';
        return 1;
    }
}
#endif // RAW_ID_BRIDGE_NO_MAIN
