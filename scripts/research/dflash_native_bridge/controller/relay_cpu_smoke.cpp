// Executes the actual relay instruction stream with fake native continuations.
// Windows adaptation changes only FS TLS prefixes to GS; no engine/device call.
#define HGN_DFLASH_SYSV_MOCK 1
#include "retained_relay.h"
#ifndef HGN_MOCK_CASE_LIMIT
#define HGN_MOCK_CASE_LIMIT 7
#endif
using namespace hgn_dflash;
extern "C" {
alignas(64) u8 mock_before_xstate[65536]{},mock_after_xstate[65536]{};
Frame mock_expected{},mock_observed{};
u8 mock_redzone[128]{};
u64 mock_relay_target{},mock_mask{},mock_record{},mock_aggregate{};
u32 mock_observed_action{};
int mock_errno=99;
void hgn_mock_run();
void hgn_mock_stock();void hgn_mock_scalar();void hgn_mock_ready();
int* __errno_location()noexcept{return &mock_errno;}
void* memcpy(void* dst,const void* src,__SIZE_TYPE__ n){auto* d=static_cast<u8*>(dst);auto* s=static_cast<const u8*>(src);for(__SIZE_TYPE__ i=0;i<n;++i)d[i]=s[i];return dst;}
void* memset(void* dst,int v,__SIZE_TYPE__ n){auto* d=static_cast<u8*>(dst);for(__SIZE_TYPE__ i=0;i<n;++i)d[i]=u8(v);return dst;}
}
alignas(64) static u8 model[4096],request[1024],record[128],aggregate[16];
static i32 history[4]={4,5,6,7};static u8 allowed[13];
static Lane lane;static Configuration provider_config;
static u8 optional_enabled;static u64 in_flight;static relay::StackBounds bounds;
static int failures;
static void check(bool ok){if(!ok)++failures;}
static void put(u8* p,u32 offset,u64 value,u32 bytes=8){for(u32 i=0;i<bytes;++i)p[offset+i]=u8(value>>(8*i));}
static bool provider(void*,const Snapshot& s,Candidate& c)noexcept{
    mock_errno=1234;c.binding=s.binding;c.count=3;c.ids[0]=8;c.ids[1]=9;c.ids[2]=10;return true;
}
static void rel32(const u8* symbol,u64 target){
    auto field=u64(symbol);auto delta=i64(target)-i64(field+4);
    check(delta>=-2147483648LL&&delta<=2147483647LL);
    auto* bytes=reinterpret_cast<volatile u8*>(field);for(u32 i=0;i<4;++i)bytes[i]=u8(u32(i32(delta))>>(8*i));
}
static void configure(relay::Configuration* config,u32 extent){
    config->lane=&lane;config->enabled=1;config->runtime_enabled=&optional_enabled;
    config->in_flight_counter=&in_flight;config->loss_counter=&lane.loss;
    config->provider=&provider_config;config->callback=&hgn_dflash_ready_callback;
    config->xsave_bytes=extent;config->xcr0_mask=mock_mask;config->required_stack_below_original_rsp=extent+65536;
    u64 teb;asm volatile("movq %%gs:0x30,%0":"=r"(teb));config->stack_tls_offset=i64(u64(&bounds)-teb);
}
static void fixture(bool owned=true){
    for(auto& b:model)b=0;for(auto& b:request)b=0;for(auto& b:record)b=0;
    for(auto& b:allowed)b=255;for(auto& b:mock_before_xstate)b=0;for(auto& b:mock_after_xstate)b=0;
    lane={};check(pin_lane(lane,u64(model),0));
    put(model,0xc8,0,4);put(model,0x14,4,4);put(model,0x2e0,4,4);put(model,0x118,100,4);put(model,0x2e8,12,4);
    put(model,0xb7c,1,1);put(model,0xb7d,1,1);put(model,0x40,33,4);
    put(request,0x108,u64(model));put(request,0x19c,7,4);put(request,0x11c,1,4);put(request,0x120,3,4);put(request,0x228,4,4);
    put(request,0x1c0,u64(history));put(request,0x1c8,u64(history+4));put(request,0x1d0,u64(history+4));
    put(record,0,77);put(record,8,0,4);put(record,0x10,u64(request));put(aggregate,0,u64(model));put(aggregate,8,0);
    if(owned){PendingBinding p{u64(model),u64(request)+4096,77,8,99,0};auto g=arm_pending(lane,p);
        check(full_reset_complete(lane,g,u64(model),0,true,true)==ResetResult::FreshPending);
        check(materialize_pending(lane,g,p.holder));check(transfer_pending(lane,g,p,u64(request),13));enable_ready(lane,true);}
    provider_config={};provider_config.pins_verified=true;provider_config.pins[0]=provider_config.pins[16]=provider_config.pins[48]=provider_config.pins[80]=1;
    provider_config.provider=provider;provider_config.allowed=allowed;provider_config.id_count=100;
    for(u32 i=0;i<16;++i)mock_expected.gpr[i]=0x1111000000000000ULL+i*0x1111;
    mock_expected.gpr[0]=u64(model);mock_expected.gpr[1]=u64(request);mock_expected.gpr[2]=u64(model);
    mock_expected.gpr[3]=0x2222333344445500ULL;mock_expected.gpr[4]=u64(request);mock_expected.gpr[5]=u64(model);
    mock_expected.ordinary_rflags=0x646;mock_errno=99;mock_observed_action=99;in_flight=0;optional_enabled=0;
    mock_record=u64(record);mock_aggregate=u64(aggregate);
    bounds.low=1;bounds.high=~u64(0);
}
static void verify(u32 action,bool prepare=false){
    check(mock_observed_action==action);
    for(u32 i=0;i<16;++i){auto expected=mock_expected.gpr[i];if(i==13&&action==2)expected=3;if(i==3&&prepare)expected=(expected&~u64(255))|1;
        check(mock_observed.gpr[i]==expected);}
    check(mock_observed.ordinary_rflags==(action==0&&!prepare&&mock_relay_target==u64(&hgn_dflash_relay_0_begin)?u64(0x602):u64(0x646)));
    for(auto byte:mock_redzone)check(byte==0x5a);
    for(u32 i=0;i<65536;++i)check(mock_before_xstate[i]==mock_after_xstate[i]);
    check(mock_errno==99);check(in_flight==0);
}
int main(){
    u32 a,b,c,d;asm volatile("cpuid":"=a"(a),"=b"(b),"=c"(c),"=d"(d):"a"(1),"c"(0));
    if((c&((1u<<26)|(1u<<27)))!=((1u<<26)|(1u<<27)))return 120;
    asm volatile("xgetbv":"=a"(a),"=d"(d):"c"(0));mock_mask=(u64(d)<<32)|a;
    asm volatile("cpuid":"=a"(a),"=b"(b),"=c"(c),"=d"(d):"a"(13),"c"(0));if(b<576||b>65536)return 121;
    configure(const_cast<relay::Configuration*>(&hgn_dflash_relay_0_config),b);
    configure(const_cast<relay::Configuration*>(&hgn_dflash_relay_1_config),b);
    configure(const_cast<relay::Configuration*>(&hgn_dflash_relay_2_config),b);
    configure(const_cast<relay::Configuration*>(&hgn_dflash_relay_3_config),b);
    configure(const_cast<relay::Configuration*>(&hgn_dflash_relay_4_config),b);
    rel32(hgn_dflash_relay_0_stock_delta,u64(&hgn_mock_stock));rel32(hgn_dflash_relay_0_scalar_delta,u64(&hgn_mock_scalar));
    rel32(hgn_dflash_relay_0_ready_delta,u64(&hgn_mock_ready));rel32(hgn_dflash_relay_1_stock_delta,u64(&hgn_mock_stock));
    rel32(hgn_dflash_relay_2_stock_delta,u64(&hgn_mock_stock));rel32(hgn_dflash_relay_3_stock_delta,u64(&hgn_mock_stock));
    rel32(hgn_dflash_relay_4_stock_delta,u64(&hgn_mock_stock));
    fixture(false);mock_relay_target=u64(&hgn_dflash_relay_0_begin);hgn_mock_run();verify(0);
    if(HGN_MOCK_CASE_LIMIT==1)return failures?1:0;
    fixture();mock_relay_target=u64(&hgn_dflash_relay_0_begin);hgn_mock_run();verify(1);check(lane.round==1);
    if(HGN_MOCK_CASE_LIMIT==2)return failures?1:0;
    fixture();optional_enabled=1;mock_relay_target=u64(&hgn_dflash_relay_0_begin);hgn_mock_run();verify(2);check(lane.round==1);
    if(HGN_MOCK_CASE_LIMIT==3)return failures?1:0;
    fixture();optional_enabled=1;bounds.low=0;mock_relay_target=u64(&hgn_dflash_relay_0_begin);hgn_mock_run();verify(1);check(lane.loss==1&&!lane.ready_enabled);
    fixture();mock_relay_target=u64(&hgn_dflash_relay_1_begin);hgn_mock_run();verify(0,true);check(native_i32(u64(request),0x224)==2147483647);
    fixture();mock_relay_target=u64(&hgn_dflash_relay_3_begin);hgn_mock_run();
    // Stock replay loads holder+0x180 into RSI. Here RAX is a host mock model.
    mock_expected.gpr[4]=native_read(u64(model),0x180);verify(0);check(native_read(u64(model),0xb7d,1)==0);
    fixture();mock_relay_target=u64(&hgn_dflash_relay_4_begin);hgn_mock_run();
    mock_expected.gpr[0]=mock_expected.gpr[14]+0x328;verify(0);check(native_read(u64(model),0xb7d,1)==0);
    return failures?1:0;
}
