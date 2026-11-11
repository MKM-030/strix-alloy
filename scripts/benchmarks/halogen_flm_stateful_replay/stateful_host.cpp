// Finite FLM 1.0.12 XRT state parity component. Root owns build and invocation.
// Import-linked DLLs can load before main: --run is not a no-load smoke test.
#if !defined(_WIN32) || !defined(_M_X64)
#error Windows AMD64 is required.
#endif
#if defined(FLM_USE_HRX)
#error FLM_USE_HRX must remain undefined.
#endif
#include "models/qwen3_5vl/flm/aie2p/qwen3_5vl_npu.hpp"
#include "flm_state_api.h"
#include <windows.h>
#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <limits>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>

namespace component {
using json = nlohmann::json;
namespace fs = std::filesystem;
constexpr int rows = 248070, seed_count = 512, output_count = 128, local_cap = 640;
static_assert(sizeof(bf16) == 2);
void need(bool ok, const char* why) { if (!ok) throw std::runtime_error(why); }
long long ticks() { LARGE_INTEGER t; need(QueryPerformanceCounter(&t), "QPC unavailable"); return t.QuadPart; }
long long frequency() { LARGE_INTEGER t; need(QueryPerformanceFrequency(&t) && t.QuadPart>0,"QPC frequency unavailable"); return t.QuadPart; }
json span(long long begin, long long end) {
    need(begin>=0 && end>=begin,"QPC order differs");
    return {{"started_ticks",begin},{"finished_ticks",end}};
}
json read_json(const fs::path& path) {
    need(fs::is_regular_file(path) && fs::file_size(path)<=1024*1024,"Bounded JSON file required");
    std::ifstream stream(path); need(stream.good(),"Cannot read JSON");
    auto value=json::parse(stream); need(value.is_object(),"JSON object required"); return value;
}
std::vector<int> ids(const json& value, std::size_t count) {
    need(value.is_array() && value.size()==count,"Exact bounded ID count required");
    std::vector<int> result;
    for (const auto& item:value) {
        need(item.is_number_integer(),"Integer ID required"); const auto id=item.get<long long>();
        need(id>=0 && id<rows,"ID outside shared vocabulary"); result.push_back(static_cast<int>(id));
    }
    return result;
}
void length(qwen3_5vl_npu& engine,int expected) {
    const int actual=engine.qwen3_5vl_npu::get_current_context_length();
    if (actual!=expected) throw std::runtime_error("Context differs: actual="+std::to_string(actual)+" expected="+std::to_string(expected));
}
struct Row { std::vector<std::uint16_t> words; int greedy=-1; };
Row own(const buffer<bf16>& logits) {
    need(logits.data()!=nullptr && logits.size()>=rows && logits.size()<=248320,"Complete logits row required");
    Row out; out.words.reserve(rows); float best=-std::numeric_limits<float>::infinity();
    for (int i=0;i<rows;++i) {
        const bf16 value=logits[i]; const float f=static_cast<float>(value);
        need(std::isfinite(f),"Nonfinite shared logit"); std::uint16_t word;
        std::memcpy(&word,&value,2); out.words.push_back(word);
        if(out.greedy<0 || f>best) { best=f; out.greedy=i; }
    }
    return out;
}
json dump(const fs::path& dir,int index,const Row& row,const json& timing) {
    const auto name="state-"+std::to_string(index)+".bf16";
    const auto begin=ticks(); std::ofstream stream(dir/name,std::ios::binary|std::ios::trunc);
    need(stream.good(),"Cannot write row"); stream.write(reinterpret_cast<const char*>(row.words.data()),rows*2);
    stream.close(); need(stream.good(),"Incomplete row write");
    return {{"state_index",index},{"local_count",seed_count+index},{"row_count",rows},
        {"row_file",name},{"greedy_id",row.greedy},{"timing",timing},{"row_write_timing",span(begin,ticks())}};
}
LM_Config config(const fs::path& model,const fs::path& bundle) {
    need(fs::is_regular_file(model/"model.q4nx"),"Language weights absent");
    LM_Config c; c.model_path=fs::absolute(model).string(); c.exec_path=fs::absolute(bundle).string();
    c.model_name="Qwen3.5-0.8B-NPU2"; c._json_config=read_json(model/"config.json");
    for(const auto& item:std::vector<std::pair<const char*,int>>{{"vocab_size",248320},{"hidden_size",1024},
        {"num_hidden_layers",24},{"head_dim",256},{"num_attention_heads",8},{"num_key_value_heads",2}})
        need(c._json_config.contains(item.first) && c._json_config[item.first]==item.second,"Wrong 0.8B geometry");
    c.flm_version=c._json_config.value("flm_version",std::string("0.0.0"));
    c._json_config["is_vlm"]=false; c._json_config["is_audio"]=false;
    for(const char* name:{"layer.xclbin","lm_head.xclbin","mm.xclbin","attn.xclbin","conv.xclbin","GateDeltaNet_prefill.xclbin"})
        need(fs::is_regular_file(bundle/"xclbins"/c.model_name/name),"Token kernel absent");
    return c;
}
json validate(const json& input) {
    need(input.at("schema")=="halogen0201.growing-native-replay-input.v1" && input.at("authority")=="recorded_native_T","Recorded T input required");
    need(input.at("target_engine_sha256")=="7a72e138f0090008d171e41358a23f86a875fe92fadbcbc5daf2d3225e426577" &&
        input.at("target_tokenizer_sha256")=="0997f410c57a1f4e53b09e4be8f4a172d90edd9564368fb0847030937229b9f3","Target identity differs");
    need(input.at("cases").is_array() && input.at("cases").size()==1,"Exactly one frozen family required");
    const auto c=input.at("cases")[0]; need(c.at("name")=="natural8192" && c.at("actual_input_tokens")==8192,"Frozen 8K family required");
    ids(c.at("seed_tail_ids"),seed_count); ids(c.at("teacher_ids"),output_count);
    need(c.at("request_id").is_number_integer() && c.at("request_id").get<long long>()>=0,"Nonnegative request ID required");
    for(const auto& field:std::vector<std::pair<const char*,int>>{{"request_epoch",32},{"request_sha256",64}}) {
        const auto text=c.at(field.first).get<std::string>();
        need(text.size()==static_cast<std::size_t>(field.second) && std::all_of(text.begin(),text.end(),[](char x){return(x>='0'&&x<='9')||(x>='a'&&x<='f');}),"Request identity malformed");
    }
    return c;
}
const flm_state_api* state_api(qwen3_5vl_npu& engine) {
    const auto* a=qwen3_5vl_state_api(&engine);
    constexpr auto required=offsetof(flm_state_api,state_estimate_bytes)+sizeof(a->state_estimate_bytes);
    need(a && a->version==FLM_STATE_API_VERSION && a->struct_size>=required,"Unsupported state table ABI");
    need(a->state_new && a->state_free && a->state_read && a->state_write && a->state_write_kv &&
        a->state_context_length && a->state_kv_from && a->state_estimate_bytes,"Incomplete state table");
    return a;
}
struct Saved {
    const flm_state_api* api; flm_state* value;
    explicit Saved(const flm_state_api* a,qwen3_5vl_npu& e):api(a),value(a->state_new(&e)) { need(value,"Cannot allocate state handle"); }
    Saved(const Saved&)=delete; Saved& operator=(const Saved&)=delete;
    ~Saved() { api->state_free(value); }
};
json run(qwen3_5vl_npu& e,const flm_state_api* api,const json& c,const std::string& mode,const fs::path& dir) {
    auto seed=ids(c.at("seed_tail_ids"),seed_count); const auto teachers=ids(c.at("teacher_ids"),output_count);
    json result={{"schema","halogen0201.flm1012-state-parity.v1"},{"mode",mode},{"complete",false},{"case",c},
        {"QPC_frequency",frequency()},{"runtime_requested","1.0.12"},{"states",json::array()},{"cycles",json::array()},
        {"native_acceptance",nullptr},{"target_readiness",nullptr},{"prefill_tok_s",nullptr},{"decode_tok_s",nullptr},
        {"full_retain_optimization_qualified",false},{"forced_branches_are_prediction_quality",false}};
    length(e,0); auto begin=ticks(); Row current=own(e.qwen3_5vl_npu::prefill(seed,nullptr));
    length(e,seed_count); result["states"].push_back(dump(dir,0,current,span(begin,ticks())));
    std::unique_ptr<Saved> saved; if(mode=="scenario") saved=std::make_unique<Saved>(api,e);
    int natural_equal=0;
    for(int step=0;step<output_count;++step) {
        const int L=seed_count+step; length(e,L);
        natural_equal+=current.greedy==teachers[step];
        if(saved) {
            const Row committed=current; const int count=std::min(3,local_cap-L);
            const auto read_begin=ticks(); const int read_L=api->state_read(&e,saved->value,0); const auto read_end=ticks();
            need(read_L==L && api->state_context_length(saved->value)==L && api->state_kv_from(saved->value)==0,"Snapshot length or KV boundary differs"); length(e,L);
            const auto estimated=api->state_estimate_bytes(saved->value,L,0);
            // Forced fixtures exercise zero/partial/full branch agreement only.
            // They use recorded labels and are never real predictor acceptance.
            const std::string label=step==0?"forced_zero":step==15?"forced_partial":step==16?"forced_full":"natural";
            std::vector<int> proposed; json forwards=json::array(); Row scratch=current;
            for(int j=0;j<count;++j) {
                int token=scratch.greedy;
                if(label!="natural") token=teachers[step+j];
                if((label=="forced_zero" && j==0)||(label=="forced_partial" && j==1)) token=(token+1)%rows;
                proposed.push_back(token);
                if(j+1<count) {
                    const auto forward_begin=ticks(); scratch=own(e.qwen3_5vl_npu::forward(token));
                    length(e,L+j+1); forwards.push_back(span(forward_begin,ticks()));
                }
            }
            length(e,L+count-1); int equal=0; while(equal<count && proposed[equal]==teachers[step+equal])++equal;
            const auto write_begin=ticks(); const int write_L=api->state_write(&e,saved->value); const auto write_end=ticks();
            need(write_L==L,"State restore failed"); length(e,L);
            current=committed; // The C state API does not restore the owned logits.
            result["cycles"].push_back({{"step",step},{"committed_length",L},{"proposal_count",count},
                {"consumed_inputs",count-1},{"proposals",proposed},{"proposal_prefix_matches",equal},
                {"label",label},{"forced",label!="natural"},{"state_read_length",read_L},{"saved_length",api->state_context_length(saved->value)},
                {"saved_kv_from",api->state_kv_from(saved->value)},{"state_write_length",write_L},{"restored_length",e.qwen3_5vl_npu::get_current_context_length()},
                {"committed_authority",teachers[step]},{"estimated_state_bytes",estimated},
                {"read_timing",span(read_begin,read_end)},{"write_timing",span(write_begin,write_end)},{"speculative_forward_timings",forwards}});
        }
        begin=ticks(); current=own(e.qwen3_5vl_npu::forward(teachers[step])); length(e,L+1);
        result["states"].push_back(dump(dir,step+1,current,span(begin,ticks())));
    }
    length(e,local_cap); result["natural_committed_next_ID_matches"]=natural_equal;
    result["natural_committed_predictions"]=output_count; result["complete"]=true; return result;
}
} // namespace component

int main(int argc,char** argv) {
    using namespace component;
    try {
        need(argc==7 && std::string(argv[1])=="--run","usage: stateful.exe --run reference|scenario MODEL_DIR BUNDLE_ROOT INPUT.json OUTPUT.json");
        const std::string mode=argv[2]; need(mode=="reference"||mode=="scenario","Unknown mode");
        const auto input=read_json(argv[5]); const auto c=validate(input); const auto cfg=config(argv[3],argv[4]);
        const fs::path output=argv[6],dir=std::string(argv[6])+".rows";
        need(!fs::exists(output) && !fs::exists(dir),"Fresh unique output required"); need(fs::create_directory(dir),"Cannot create row directory");
        const auto startup_begin=ticks(); flm_rt::device device(0); npu_xclbin_manager manager(device_npu2,&device,false);
        std::unique_ptr<qwen3_5vl_npu> engine;
        { Q4NX weights(cfg.model_path); engine=std::make_unique<qwen3_5vl_npu>(cfg,&manager,4096);
          engine->qwen3_5vl_npu::load_weights(weights); engine->qwen3_5vl_npu::clear_context(); }
        const auto* api=state_api(*engine); const auto startup_end=ticks();
        auto result=run(*engine,api,c,mode,dir); result["startup_timing"]=span(startup_begin,startup_end);
        result["state_api_version"]=api->version; result["state_api_struct_size"]=api->struct_size;
        result["bf16_rows_directory"]=fs::absolute(dir).string(); result["input"]=input;
        std::ofstream stream(output,std::ios::binary|std::ios::trunc); need(stream.good(),"Cannot write report");
        stream<<result.dump(2)<<'\n'; stream.close(); need(stream.good(),"Incomplete report write"); return 0;
    } catch(const std::exception& error) { std::cerr<<"stateful1012 failed: "<<error.what()<<'\n'; return 1; }
}
