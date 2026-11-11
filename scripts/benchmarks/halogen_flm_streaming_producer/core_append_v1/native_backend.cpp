// Typed FLM 1.0.12-only C boundary. Root owns build, DLL load and execution.
#if !defined(_WIN32) || !defined(_M_X64)
#error Windows AMD64 is required.
#endif
#if defined(FLM_USE_HRX)
#error Matching XRT backend requires FLM_USE_HRX undefined.
#endif
#include "models/qwen3_5vl/flm/aie2p/qwen3_5vl_npu.hpp"
#include "flm_state_api.h"
#include "append_head_scope.hpp"
#include <windows.h>
#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <limits>
#include <memory>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>

namespace stateful1012 {
using json=nlohmann::json;
namespace fs=std::filesystem;
constexpr int rows=248070,seed=512,limit=640;
static_assert(sizeof(bf16)==2);
static_assert(offsetof(flm_state_api,state_estimate_bytes)+sizeof(void*)==72);
thread_local std::string last_error;
void need(bool ok,const char* why){if(!ok)throw std::runtime_error(why);}
struct Timing{std::int64_t started_ticks,finished_ticks,frequency;};
std::int64_t qpc(){LARGE_INTEGER x;need(QueryPerformanceCounter(&x),"QPC unavailable");return x.QuadPart;}
std::int64_t frequency(){LARGE_INTEGER x;need(QueryPerformanceFrequency(&x)&&x.QuadPart>0,"QPC frequency unavailable");return x.QuadPart;}
struct Clock{
    Timing* value;
    explicit Clock(Timing* out):value(out){need(value,"Timing buffer required");value->frequency=frequency();value->started_ticks=qpc();value->finished_ticks=0;}
    ~Clock()noexcept{LARGE_INTEGER now;value->finished_ticks=QueryPerformanceCounter(&now)?now.QuadPart:0;}
};
json read_json(const fs::path& path){
    need(fs::is_regular_file(path)&&fs::file_size(path)<=1024*1024,"Bounded model JSON required");
    std::ifstream s(path);need(s.good(),"Cannot read config");auto c=json::parse(s);need(c.is_object(),"Object config required");return c;
}
LM_Config config(const wchar_t* model,const wchar_t* bundle){
    need(model&&bundle,"Model and bundle paths required");const fs::path m(model),b(bundle);
    need(fs::is_regular_file(m/"model.q4nx"),"Q4NX language weights absent");
    LM_Config c;c.model_path=fs::absolute(m).string();c.exec_path=fs::absolute(b).string();
    c.model_name="Qwen3.5-0.8B-NPU2";c._json_config=read_json(m/"config.json");
    for(const auto& item:std::vector<std::pair<const char*,int>>{{"vocab_size",248320},{"hidden_size",1024},
        {"num_hidden_layers",24},{"head_dim",256},{"num_attention_heads",8},{"num_key_value_heads",2}})
        need(c._json_config.contains(item.first)&&c._json_config[item.first]==item.second,"Unexpected 0.8B geometry");
    c.flm_version=c._json_config.value("flm_version",std::string("0.0.0"));
    c._json_config["is_vlm"]=false;c._json_config["is_audio"]=false;
    for(const char* name:{"layer.xclbin","lm_head.xclbin","mm.xclbin","attn.xclbin","conv.xclbin","GateDeltaNet_prefill.xclbin"})
        need(fs::is_regular_file(b/"xclbins"/c.model_name/name),"Qualified token kernel missing");
    return c;
}
// Only the private child owns this module's single engine and actor thread.
// Exact whole-file SHA/path admission is performed by the Python binding;
// this independent native guard checks the actual mapped PE and call bytes.
class WindowsPatchMemory {
    HMODULE module_=nullptr;
    std::uint8_t* base_=nullptr;
    static constexpr std::size_t begin_rva=0x58358,end_rva=0x58399;
    bool match(std::size_t rva,const std::uint8_t* expected,std::size_t bytes)const noexcept {
        const volatile std::uint8_t* actual=base_+rva;
        for(std::size_t i=0;i<bytes;++i)if(actual[i]!=expected[i])return false;
        return true;
    }
public:
    WindowsPatchMemory(){
        module_=GetModuleHandleW(L"qwen3_5vl_npu.dll");need(module_,"Qualified FLM module is not mapped");
        base_=reinterpret_cast<std::uint8_t*>(module_);
        const auto* dos=reinterpret_cast<const IMAGE_DOS_HEADER*>(base_);
        need(dos->e_magic==IMAGE_DOS_SIGNATURE&&dos->e_lfanew>=sizeof(IMAGE_DOS_HEADER)&&dos->e_lfanew<=0x1000,
             "Qualified native PE DOS header differs");
        const auto* pe=reinterpret_cast<const IMAGE_NT_HEADERS64*>(base_+dos->e_lfanew);
        need(pe->Signature==IMAGE_NT_SIGNATURE&&pe->FileHeader.Machine==0x8664&&
             pe->FileHeader.TimeDateStamp==0x6ae53ad3&&pe->OptionalHeader.Magic==IMAGE_NT_OPTIONAL_HDR64_MAGIC&&
             pe->OptionalHeader.SizeOfImage==0x241000,"Qualified FLM1.0.12 PE identity differs");
        need(protection_restored(),"Two call sites require original committed RX image protection");
        for(unsigned i=0;i<2;++i){append_head::Bytes actual{};need(read(i,actual)&&actual==append_head::original[i],"Original head call instruction differs");}
        const std::uint8_t layers_start[]={0xff,0x15,0xcd,0x43,0x0b,0};
        const std::uint8_t layers_wait[]={0xff,0x15,0xa4,0x43,0x0b,0};
        const std::uint8_t hidden_sync[]={0xff,0x15,0xdf,0x41,0x0b,0};
        const std::uint8_t output_sync[]={0xff,0x15,0x73,0x41,0x0b,0};
        const std::uint8_t context_update[]={0xe8,0x38,0x9c,0,0};
        need(match(0x58175,layers_start,sizeof(layers_start))&&match(0x58196,layers_wait,sizeof(layers_wait))&&
             match(0x5834b,hidden_sync,sizeof(hidden_sync))&&match(0x583b7,output_sync,sizeof(output_sync))&&
             match(0x58373,context_update,sizeof(context_update)),"Retained layers/synchronization/context instruction differs");
    }
    std::uint64_t current_thread()const noexcept{return GetCurrentThreadId();}
    bool contains(const void* address)const noexcept {
        auto pointer=reinterpret_cast<std::uintptr_t>(address),base=reinterpret_cast<std::uintptr_t>(base_);
        return pointer>=base&&pointer<base+0x241000;
    }
    bool read(unsigned index,append_head::Bytes& value)const noexcept {
        if(index>=2)return false;
        const volatile std::uint8_t* p=base_+(index?0x58393:0x58358);
        for(std::size_t i=0;i<value.size();++i)value[i]=p[i];return true;
    }
    bool protection_restored()const noexcept {
        MEMORY_BASIC_INFORMATION info{};
        return base_&&VirtualQuery(base_+begin_rva,&info,sizeof(info))==sizeof(info)&&
            info.AllocationBase==module_&&info.State==MEM_COMMIT&&info.Type==MEM_IMAGE&&
            info.Protect==PAGE_EXECUTE_READ&&
            reinterpret_cast<std::uintptr_t>(info.BaseAddress)+info.RegionSize>=
                reinterpret_cast<std::uintptr_t>(base_)+end_rva;
    }
    bool writable(std::uint32_t& previous)noexcept {
        DWORD old=0;if(!VirtualProtect(base_+begin_rva,end_rva-begin_rva,PAGE_EXECUTE_READWRITE,&old))return false;
        previous=old;return true;
    }
    bool write(unsigned index,const append_head::Bytes& value)noexcept {
        if(index>=2)return false;
        std::memcpy(base_+(index?0x58393:0x58358),value.data(),value.size());return true;
    }
    bool flush()noexcept{return FlushInstructionCache(GetCurrentProcess(),base_+begin_rva,end_rva-begin_rva)!=0;}
    bool restore_protection(std::uint32_t protection)noexcept {
        DWORD ignored=0;return VirtualProtect(base_+begin_rva,end_rva-begin_rva,protection,&ignored)!=0;
    }
};
struct Snapshot{flm_state* value;int length;};
struct Engine{
    DWORD owner=GetCurrentThreadId();
    append_head::SingleEngineLease single_engine;
    WindowsPatchMemory patch_memory;
    append_head::Guard<WindowsPatchMemory> head_scope;
    bool append_head_skip=false;
    LM_Config cfg;flm_rt::device device;
    npu_xclbin_manager manager;std::unique_ptr<qwen3_5vl_npu> model;
    const flm_state_api* api=nullptr;std::set<Snapshot*> states;
    Engine(const wchar_t* path,const wchar_t* bundle):single_engine(this),patch_memory(),head_scope(patch_memory,owner),
        cfg(config(path,bundle)),device(0),manager(device_npu2,&device,false){
        {Q4NX weights(cfg.model_path);model=std::make_unique<qwen3_5vl_npu>(cfg,&manager,4096);
         model->qwen3_5vl_npu::load_weights(weights);model->qwen3_5vl_npu::clear_context();}
        api=qwen3_5vl_state_api(model.get());
        need(api&&api->version==1&&api->struct_size>=72,"Unsupported FLM v1 state table");
        need(api->state_new&&api->state_free&&api->state_read&&api->state_write&&api->state_write_kv&&
            api->state_context_length&&api->state_kv_from&&api->state_estimate_bytes,"Incomplete FLM state API");
        need(patch_memory.contains(reinterpret_cast<const void*>(api->state_read)),"Model state provider differs from guarded mapped module");
        context(0);
    }
    ~Engine(){for(auto* s:states){api->state_free(s->value);delete s;}}
    int length()const{return model->qwen3_5vl_npu::get_current_context_length();}
    void context(int expected)const{need(length()==expected,"Native context differs from expected prefix");}
    void own_thread()const{need(owner==GetCurrentThreadId(),"Native engine is bound to one serial actor thread");}
    void state(Snapshot* s)const{need(s&&states.count(s),"Foreign or freed state handle");}
};
Engine& engine(void* opaque){need(opaque,"Native engine handle required");auto& e=*static_cast<Engine*>(opaque);e.own_thread();e.head_scope.require_restored();return e;}
void copy_row(const buffer<bf16>& logits,std::uint16_t* out,std::uint32_t size,std::int32_t* greedy){
    need(out&&greedy&&size==rows&&logits.data()&&logits.size()>=rows&&logits.size()<=248320,"Complete owned shared row required");
    float best=-std::numeric_limits<float>::infinity();*greedy=-1;
    for(int i=0;i<rows;++i){const bf16 value=logits[i];const float f=static_cast<float>(value);
        need(std::isfinite(f),"Nonfinite shared BF16 value");std::memcpy(out+i,&value,2);
        if(*greedy<0||f>best){best=f;*greedy=i;}}
}
template<class F>int checked(F action){try{last_error.clear();action();return 0;}
    catch(const std::exception& e){last_error=e.what();return -1;}
    catch(...){last_error="Unknown native exception";return -1;}}
}

#define EXPORT extern "C" __declspec(dllexport)
EXPORT const char* sl1012_last_error(){return stateful1012::last_error.c_str();}
EXPORT void* sl1012_create(const wchar_t* model,const wchar_t* bundle,stateful1012::Timing* timing){
    void* result=nullptr;
    stateful1012::checked([&]{stateful1012::Clock clock(timing);result=new stateful1012::Engine(model,bundle);});return result;
}
EXPORT int sl1012_close(void* opaque){return stateful1012::checked([&]{auto& e=stateful1012::engine(opaque);delete &e;});}
EXPORT int sl1012_context(void* opaque,std::int32_t* count){return stateful1012::checked([&]{
    auto& e=stateful1012::engine(opaque);stateful1012::need(count,"Context output required");*count=e.length();});}
EXPORT int sl1012_set_append_head_skip(void* opaque,int enabled){return stateful1012::checked([&]{
    auto& e=stateful1012::engine(opaque);stateful1012::need(enabled==0||enabled==1,"Explicit boolean append-head mode required");
    e.append_head_skip=enabled!=0;});}
EXPORT int sl1012_head_skip_status(void* opaque,std::uint64_t* skipped,std::int32_t* restored){return stateful1012::checked([&]{
    stateful1012::need(opaque&&skipped&&restored,"Head status owner and outputs required");
    auto& e=*static_cast<stateful1012::Engine*>(opaque);e.own_thread();
    *skipped=e.head_scope.skipped();*restored=e.head_scope.restored()?1:0;});}
EXPORT int sl1012_seed(void* opaque,const std::int32_t* ids,std::uint32_t count,
    std::uint16_t* out,std::uint32_t row_count,std::int32_t* greedy,stateful1012::Timing* timing){
    return stateful1012::checked([&]{auto& e=stateful1012::engine(opaque);
        stateful1012::need(ids&&count==512&&e.states.empty(),"Seed needs exact tail512 and no old states");
        std::vector<int> tokens(ids,ids+count);for(int id:tokens)stateful1012::need(id>=0&&id<stateful1012::rows,"Seed token outside shared range");
        stateful1012::Clock clock(timing);e.model->qwen3_5vl_npu::clear_context();e.context(0);
        stateful1012::copy_row(e.model->qwen3_5vl_npu::prefill(tokens,nullptr),out,row_count,greedy);e.context(512);});
}
EXPORT int sl1012_forward(void* opaque,std::int32_t token,std::uint16_t* out,std::uint32_t row_count,
    std::int32_t* greedy,stateful1012::Timing* timing){return stateful1012::checked([&]{auto& e=stateful1012::engine(opaque);
        stateful1012::need(token>=0&&token<stateful1012::rows,"Forward token outside shared range");
        const int before=e.length();stateful1012::need(before>=512&&before<640,"Qualified local bound512..640 exceeded");
        stateful1012::Clock clock(timing);stateful1012::copy_row(e.model->qwen3_5vl_npu::forward(token),out,row_count,greedy);e.context(before+1);});}
EXPORT int sl1012_append_only(void* opaque,std::int32_t token,stateful1012::Timing* timing){
    return stateful1012::checked([&]{auto& e=stateful1012::engine(opaque);
        stateful1012::need(token>=0&&token<stateful1012::rows,"Append token outside shared range");
        const int before=e.length();stateful1012::need(before>=512&&before<640,"Qualified local bound512..640 exceeded");
        // Same scalar recurrent forward; an already-observed intermediate ID
        // needs no owned row, host copy, finite scan, greedy scan or snapshot.
        stateful1012::Clock clock(timing);
        e.head_scope.run(e.append_head_skip,[&]{(void)e.model->qwen3_5vl_npu::forward(token);e.context(before+1);});});
}
EXPORT int sl1012_state_read(void* opaque,void** output,std::uint64_t* estimated,stateful1012::Timing* timing){
    return stateful1012::checked([&]{auto& e=stateful1012::engine(opaque);
        stateful1012::need(output&&estimated&&e.states.size()<4,"State output required; ring is at most four");*output=nullptr;
        const int length=e.length();stateful1012::need(length>=512&&length<=640,"State prefix outside qualified range");
        auto saved=std::make_unique<stateful1012::Snapshot>();saved->value=e.api->state_new(e.model.get());saved->length=length;
        stateful1012::need(saved->value,"Cannot allocate opaque FLM state");
        try{stateful1012::Clock clock(timing);
            stateful1012::need(e.api->state_read(e.model.get(),saved->value,0)==length&&
                e.api->state_context_length(saved->value)==length&&e.api->state_kv_from(saved->value)==0,"Snapshot read/KV boundary differs");
            e.context(length);*estimated=e.api->state_estimate_bytes(saved->value,length,0);e.states.insert(saved.get());*output=saved.release();
        }catch(...){if(saved)e.api->state_free(saved->value);throw;}});
}
EXPORT int sl1012_state_write(void* opaque,void* state,std::int32_t* length,stateful1012::Timing* timing){
    return stateful1012::checked([&]{auto& e=stateful1012::engine(opaque);auto* s=static_cast<stateful1012::Snapshot*>(state);e.state(s);
        stateful1012::need(length,"Restored context output required");stateful1012::Clock clock(timing);
        *length=e.api->state_write(e.model.get(),s->value);stateful1012::need(*length==s->length,"Snapshot restore differs");e.context(s->length);});
}
EXPORT int sl1012_state_free(void* opaque,void* state){return stateful1012::checked([&]{auto& e=stateful1012::engine(opaque);
    auto* s=static_cast<stateful1012::Snapshot*>(state);e.state(s);e.api->state_free(s->value);e.states.erase(s);delete s;});}
