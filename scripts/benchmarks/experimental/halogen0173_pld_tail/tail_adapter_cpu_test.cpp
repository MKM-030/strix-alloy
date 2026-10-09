#include "tail_adapter.h"
#include "oracle_format.h"
using namespace halogen0173::tail;
// Freestanding test DLL only; the Linux serving adapter uses ordinary libc.
extern "C" void* memcpy(void* to,const void* from,__SIZE_TYPE__ size) noexcept {
    auto* dst=static_cast<u8*>(to);const auto* src=static_cast<const u8*>(from);
    for(__SIZE_TYPE__ i=0;i<size;++i) dst[i]=src[i]; return to;
}
struct Fixture { int mode{}; int calls{}; bool live{true}; };
static bool ready(void* opaque,const Snapshot& s,Candidate& result) noexcept {
    auto& f=*static_cast<Fixture*>(opaque); ++f.calls;
    if(f.mode==1) return false;
    result.binding=s.key; result.count=s.key.width;
    result.ids[0]=s.key.stock[0]; result.ids[1]=11; result.ids[2]=12;
    if(f.mode==2) ++result.binding.slot_epoch;
    if(f.mode==3) result.ids[0]=9;
    if(f.mode==4) result.ids[2]=31; // excluded target/control token
    if(f.mode==5) ++result.count;
    if(f.mode==6) for(u32 i=0;i<s.key.width;++i) result.ids[i]=s.key.stock[i];
    if(f.mode==7) ++result.binding.suffix[0];
    return true;
}
static bool guard(void* opaque) noexcept { return static_cast<Fixture*>(opaque)->live; }
static Snapshot snapshot() noexcept {
    Snapshot s{}; s.owned=s.greedy=s.unconstrained=s.complete=true;
    auto& k=s.key; k.owner_birth=k.slot_cookie=k.slot_epoch=k.round=1;
    k.context_total=k.context_count=2; k.model_position=1; k.current_id=7;
    k.native_allowance=3; k.width=3; k.stock[0]=8;k.stock[1]=9;k.stock[2]=10;
    k.suffix[0]=6;k.suffix[1]=7; return s;
}
extern "C" __declspec(dllexport) int run_cpu_tests() noexcept {
    Adapter off; Snapshot empty{};
    if(off.replace(empty,reinterpret_cast<i32*>(1),~u64(0),nullptr,nullptr)!=Status::Disabled) return 1;
    u8 allowed[4]{255,255,255,127}; Fixture f{}; Configuration cfg{};
    cfg.enabled=cfg.exact_native_pins_verified=true; cfg.session[0]=1;
    cfg.model_sha256[0]=2;cfg.tokenizer_sha256[0]=3;
    cfg.allowed_ids=allowed;cfg.allowed_id_count=32;cfg.provider=&ready;cfg.provider_context=&f;
    Adapter a;if(!a.configure(cfg)) return 2;
    auto s=snapshot();a.pin_key(s.key);
    const Status expected[]{Status::Applied,Status::Unavailable,Status::Stale,Status::Invalid,
        Status::Invalid,Status::Invalid,Status::Unchanged,Status::Stale};
    for(int mode=0;mode<8;++mode) {
        f.mode=mode;i32 output[5]{8,9,10,100,101};
        auto status=a.replace(s,output,3,&guard,&f);
        if(status!=expected[mode]) return 10+mode;
        if(output[0]!=8 || output[3]!=100 || output[4]!=101) return 20+mode;
        if(mode==0 ? (output[1]!=11 || output[2]!=12) : (output[1]!=9 || output[2]!=10)) return 30+mode;
    }
    f.mode=0;f.live=false;i32 output[4]{8,9,10,100};
    if(a.replace(s,output,3,&guard,&f)!=Status::LostOwner || output[1]!=9) return 40;
    f.live=true;output[1]=22;
    if(a.replace(s,output,3,&guard,&f)!=Status::ChangedInput || output[1]!=22 || output[2]!=10) return 41;
    const auto old_calls=f.calls;s.unconstrained=false;
    if(a.replace(s,output,3,&guard,&f)!=Status::Ineligible || f.calls!=old_calls) return 42;
    s.unconstrained=true;s.key.width=2;output[1]=9;
    if(a.replace(s,output,2,&guard,&f)!=Status::Applied || output[1]!=11 || output[2]!=10) return 43;
    s.key.width=3;
    if(a.replace(s,output,2,&guard,&f)!=Status::Ineligible) return 44;
    s.key.native_allowance=2;
    if(a.replace(s,output,3,&guard,&f)!=Status::Ineligible) return 45;
    return 0;
}
