// Finite typed 1.0.7 replay. Root must build and run this explicitly.
// Import linking can load DLLs before main; --run gates device initialization.
#include "growing_bridge.hpp"
#include <cstring>

namespace replay {
using raw_id::json;
namespace fs = std::filesystem;
constexpr std::size_t max_cases = 2;

std::int64_t frequency() {
    LARGE_INTEGER value;
    raw_id::require(QueryPerformanceFrequency(&value) && value.QuadPart > 0, "QPC frequency unavailable");
    return value.QuadPart;
}

json timing(std::int64_t host_start, std::int64_t native_start,
            std::int64_t owned, std::int64_t host_end, std::int64_t hz) {
    raw_id::require(host_start <= native_start && native_start <= owned && owned <= host_end,
                    "Native/host QPC endpoints out of order");
    return {{"clock", "Windows QPC"}, {"frequency", hz},
        {"host_call_started_ticks", host_start}, {"operation_started_ticks", native_start},
        {"logits_owned_ticks", owned}, {"host_call_returned_ticks", host_end}};
}

json state(const fs::path& rows_dir, std::size_t case_index, std::size_t index,
           std::size_t length, const raw_id::OwnedLogits& owned, const json& clocks) {
    const auto file = "case-" + std::to_string(case_index) + "-state-" + std::to_string(index) + ".bf16";
    const auto write_begin = growing_raw::qpc();
    raw_id::write_rows(rows_dir / file, owned);
    const auto write_end = growing_raw::qpc();
    return {{"state_index", index}, {"local_count", length}, {"greedy_id", owned.greedy_id},
        {"row_count", raw_id::shared_rows}, {"row_file", file}, {"timing", clocks},
        {"rows_write_started_ticks", write_begin}, {"rows_write_finished_ticks", write_end}};
}

void expect_length(qwen3_5vl_npu& engine, std::size_t count) {
    raw_id::require(engine.qwen3_5vl_npu::get_current_context_length() == static_cast<int>(count),
                    "Reference context differs from sequential authoritative history");
}

void validate(const json& input) {
    raw_id::require(input.at("schema") == "halogen0201.growing-native-replay-input.v1"
        && input.at("authority") == "recorded_native_T", "Bound native T input required");
    raw_id::require(input.at("target_engine_sha256") == "7a72e138f0090008d171e41358a23f86a875fe92fadbcbc5daf2d3225e426577"
        && input.at("target_tokenizer_sha256") == "0997f410c57a1f4e53b09e4be8f4a172d90edd9564368fb0847030937229b9f3",
        "Target engine/tokenizer differs");
    const auto& cases = input.at("cases");
    raw_id::require(cases.is_array() && !cases.empty() && cases.size() <= max_cases, "One or two finite cases required");
    std::set<std::string> epochs;
    for (const auto& c : cases) {
        const auto name=c.at("name").get<std::string>();
        const auto input_count=c.at("actual_input_tokens").get<int>();
        raw_id::require((name=="natural8192" && input_count==8192)
            || (name=="natural16384" && input_count==16384), "Frozen natural family/count required");
        const auto request_sha=c.at("request_sha256").get<std::string>();
        raw_id::require(request_sha.size()==64 && std::all_of(request_sha.begin(),request_sha.end(),[](char ch) {
            return (ch>='0' && ch<='9') || (ch>='a' && ch<='f');
        }), "Request SHA256 required");
        const auto seed = raw_id::parse_ids(c.at("seed_tail_ids"), growing_raw::seed_count, false);
        const auto teachers = raw_id::parse_ids(c.at("teacher_ids"), growing_raw::output_limit, false);
        raw_id::require(seed.size() == growing_raw::seed_count && teachers.size() == growing_raw::output_limit,
                        "Exactly512 seed and128 authoritative IDs required");
        const auto request = c.at("request_id").get<std::int64_t>();
        raw_id::require(request >= 0, "Nonnegative native request ID required");
        const auto epoch = c.at("request_epoch").get<std::string>();
        raw_id::require(epoch.size() == 32 && std::all_of(epoch.begin(), epoch.end(), [](char ch) {
            return (ch >= '0' && ch <= '9') || (ch >= 'a' && ch <= 'f');
        }) && epochs.insert(epoch).second, "Fresh32-hex request epoch required");
    }
}

json run_case(qwen3_5vl_npu& engine, const json& c, const std::string& mode,
              const fs::path& rows_dir, std::size_t index, std::int64_t hz) {
    auto seed = raw_id::parse_ids(c.at("seed_tail_ids"), growing_raw::seed_count, false);
    const auto teachers = raw_id::parse_ids(c.at("teacher_ids"), growing_raw::output_limit, false);
    const auto request = c.at("request_id").get<std::uint64_t>();
    const auto epoch = c.at("request_epoch").get<std::string>();
    json result = {{"name", c.at("name")}, {"request_id", request}, {"request_epoch", epoch},
        {"actual_input_tokens", c.at("actual_input_tokens")}, {"seed_tail_ids", seed}, {"teacher_ids", teachers},
        {"speculative_inputs", 0}, {"consumer_arrival_timestamp", nullptr}, {"target_need_timestamp", nullptr},
        {"consumer_arrived_before_target_need", nullptr}, {"states", json::array()}, {"predictions", json::array()}};
    if (mode == "candidate") {
        growing_raw::Bridge bridge(engine);
        auto host_start = growing_raw::qpc();
        auto reply = bridge.begin(request, epoch, seed);
        auto host_end = growing_raw::qpc();
        result["states"].push_back(state(rows_dir,index,0,reply.local_count,bridge.committed_logits(),
            timing(host_start,reply.native_timing.operation_started_ticks,reply.native_timing.logits_owned_ticks,host_end,hz)));
        for (std::size_t step=0; step<teachers.size(); ++step) {
            // Copy and compare every owned word across ready_one, before consuming T.
            const auto before = bridge.committed_logits().rows;
            const auto before_count = engine.qwen3_5vl_npu::get_current_context_length();
            const auto proposal_start = growing_raw::qpc();
            const auto proposed = bridge.ready_one();
            const auto proposal_end = growing_raw::qpc();
            raw_id::require(proposed.has_value() && proposed->local_count == growing_raw::seed_count+step
                && proposed->speculative_inputs == 0, "Bound count-one prediction missing");
            raw_id::require(engine.qwen3_5vl_npu::get_current_context_length() == before_count
                && before.size() == bridge.committed_logits().rows.size()
                && std::memcmp(before.data(),bridge.committed_logits().rows.data(),before.size()*sizeof(bf16)) == 0,
                "ready_one mutated authoritative state or owned rows");
            // Only now is the next recorded authoritative T supplied to the engine.
            const int teacher = teachers[step];
            result["predictions"].push_back({{"ordinal",step},{"local_count",proposed->local_count},
                {"predicted_id",proposed->greedy_id},{"authoritative_id_after_prediction",teacher},
                {"ready_started_ticks",proposal_start},{"ready_finished_ticks",proposal_end},
                {"owned_words_unchanged",true},{"context_unchanged",true},{"speculative_inputs",0},
                {"consumer_arrival_timestamp",nullptr},{"target_need_timestamp",nullptr},
                {"consumer_arrived_before_target_need",nullptr}});
            host_start = growing_raw::qpc();
            reply = bridge.append_authoritative(request,epoch,teacher);
            host_end = growing_raw::qpc();
            result["states"].push_back(state(rows_dir,index,step+1,reply.local_count,bridge.committed_logits(),
                timing(host_start,reply.native_timing.operation_started_ticks,reply.native_timing.logits_owned_ticks,host_end,hz)));
        }
        raw_id::require(bridge.committed_ids().size() == growing_raw::local_limit && !bridge.ready_one(),
                        "Final640-token limit did not retire readiness");
        bridge.cancel(epoch);
        raw_id::require(!bridge.ready_one(), "Cancelled epoch retained a proposal");
    } else {
        auto host_start = growing_raw::qpc();
        auto native_start = growing_raw::qpc();
        engine.qwen3_5vl_npu::clear_context();
        expect_length(engine,0);
        auto owned = raw_id::own_logits(engine.qwen3_5vl_npu::prefill(seed,nullptr));
        expect_length(engine,growing_raw::seed_count);
        auto owned_at = growing_raw::qpc();
        auto host_end = growing_raw::qpc();
        result["states"].push_back(state(rows_dir,index,0,growing_raw::seed_count,owned,
            timing(host_start,native_start,owned_at,host_end,hz)));
        for (std::size_t step=0; step<teachers.size(); ++step) {
            host_start = growing_raw::qpc();
            native_start = growing_raw::qpc();
            owned = raw_id::own_logits(engine.qwen3_5vl_npu::forward(teachers[step]));
            expect_length(engine,growing_raw::seed_count+step+1);
            owned_at = growing_raw::qpc();
            host_end = growing_raw::qpc();
            result["states"].push_back(state(rows_dir,index,step+1,growing_raw::seed_count+step+1,owned,
                timing(host_start,native_start,owned_at,host_end,hz)));
        }
    }
    raw_id::require(result["states"].size() == 129, "Incomplete native replay");
    return result;
}
} // namespace replay

int main(int argc,char** argv) {
    using namespace raw_id;
    try {
        require(argc==7 && std::string(argv[1])=="--run",
            "usage: replay.exe --run candidate|reference MODEL_DIR BUNDLE_ROOT INPUT.json OUTPUT.json");
        const std::string mode(argv[2]);
        require(mode=="candidate" || mode=="reference", "Unknown replay mode");
        const auto input=read_json(argv[5]);
        replay::validate(input); // All bounded input syntax checked before device creation.
        const fs::path output_path(argv[6]);
        const fs::path rows_dir(std::string(argv[6])+".rows");
        require(!fs::exists(output_path) && !fs::exists(rows_dir), "Fresh unique replay output required");
        require(fs::create_directory(rows_dir), "Cannot create replay row directory");
        const auto config=load_config(argv[3],argv[4]);
        const auto hz=replay::frequency();
        const auto startup_started=growing_raw::qpc();
        // Separate fresh process per mode; never two simultaneous NPU engines.
        flm_rt::device device(0);
        npu_xclbin_manager manager(device_npu2,&device,false);
        qwen3_5vl_npu engine(config,&manager,engine_capacity);
        { Q4NX weights(config.model_path); engine.qwen3_5vl_npu::load_weights(weights); }
        json output={{"schema","halogen0201.growing-native-replay.v1"},{"mode",mode},
            {"complete",false},{"shared_rows",shared_rows},{"engine_capacity_requested",engine_capacity},
            {"seed_count",growing_raw::seed_count},{"output_limit",growing_raw::output_limit},
            {"clock","Windows QPC"},{"QPC_frequency",hz},{"startup_started_ticks",startup_started},
            {"startup_finished_ticks",growing_raw::qpc()},{"input",input},
            {"bf16_rows_directory",fs::absolute(rows_dir).string()},
            {"native_acceptance",nullptr},{"readiness_to_target",nullptr},{"cases",json::array()}};
        std::size_t index=0;
        for(const auto& c:input["cases"]) output["cases"].push_back(replay::run_case(engine,c,mode,rows_dir,index++,hz));
        output["complete"]=true;
        std::ofstream stream(output_path,std::ios::binary|std::ios::trunc);
        require(stream.good(),"Cannot write replay JSON");
        stream<<output.dump(2)<<'\n';require(stream.good(),"Cannot finish replay JSON");
        return 0;
    } catch(const std::exception& error) {
        std::cerr<<"growing native replay failed: "<<error.what()<<'\n';
        return 1;
    }
}
