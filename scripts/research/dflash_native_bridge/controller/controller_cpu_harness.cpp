#include "retained_controller.h"
using namespace hgn_dflash;
static int failures;
static void check(bool yes) { if(!yes) ++failures; }
static void put(u8* p,u32 at,u64 v,u32 bytes=8) { for(u32 i=0;i<bytes;++i)p[at+i]=u8(v>>(8*i)); }
static u64 get(const u8* p,u32 at,u32 bytes=8) { u64 v=0;for(u32 i=0;i<bytes;++i)v|=u64(p[at+i])<<(8*i);return v; }
alignas(64) static u8 model[4096], request[1024], record[512], stack[8192];
static i32 history[4]={4,5,6,7};
static u8 allowed[13];
static Frame frame;
static Lane lane;
extern "C" void* memcpy(void* dst,const void* src,__SIZE_TYPE__ count){auto* d=static_cast<u8*>(dst);auto* s=static_cast<const u8*>(src);for(__SIZE_TYPE__ i=0;i<count;++i)d[i]=s[i];return dst;}
extern "C" void* memset(void* dst,int value,__SIZE_TYPE__ count){auto* d=static_cast<u8*>(dst);for(__SIZE_TYPE__ i=0;i<count;++i)d[i]=u8(value);return dst;}
static bool provider(void* raw,const Snapshot& s,Candidate& c) noexcept {
    auto mode=*static_cast<u32*>(raw);c.binding=s.binding;c.count=3;c.ids[0]=8;c.ids[1]=9;c.ids[2]=10;
    if(mode==1)++c.binding.position;
    if(mode==2)c.ids[2]=100;
    if(mode==3)mark_loss(lane);
    if(mode==4)put(request,0x19c,11,4);
    return mode!=5;
}
int main() {
    for(auto& v:model)v=0;for(auto& v:request)v=0;for(auto& v:record)v=0;for(auto& v:stack)v=0;
    for(auto& v:allowed)v=255;
    put(model,0xc8,0,4);put(model,0x14,4,4);put(model,0x2e0,4,4);put(model,0x118,100,4);put(model,0x2e8,12,4);put(model,0xb7c,1,1);
    put(request,0x108,u64(model));put(request,0x19c,7,4);put(request,0x11c,1,4);put(request,0x120,3,4);put(request,0x228,4,4);
    put(request,0x1c0,u64(history));put(request,0x1c8,u64(history+4));put(request,0x1d0,u64(history+4));
    put(record,0,77);put(record,8,0,4);put(record,0x10,u64(request));put(stack,0x10,u64(request));put(stack,0x78,u64(record));
    frame.gpr[7]=u64(stack);frame.gpr[5]=u64(model);frame.gpr[4]=u64(request);frame.gpr[1]=u64(request);frame.gpr[13]=1234;
    check(pin_lane(lane,u64(model),0));
    PendingBinding p{u64(model),u64(request)+4096,77,8,99,0};
    auto generation=arm_pending(lane,p);check(generation==1);
    check(full_reset_complete(lane,generation,u64(model),0,true,true)==ResetResult::FreshPending);
    check(materialize_pending(lane,generation,p.holder));
    check(retire_pending(lane,generation,p.holder));check(lane.phase==u32(Phase::Pending));
    check(transfer_pending(lane,generation,p,u64(request),13));
    Invocation invocation{};mandatory_dispatch(lane,Site::Entry,frame,invocation);
    // Missing optional collector/disabled/busy/admission cannot remove serial enforcement.
    check(invocation.action==u64(Action::Scalar));check(get(request,0x224,4)==0x7fffffff);check(get(model,0xb7d,1)==0);check(get(model,0x40,4)==0xffffffff);
    check(lane.round==1);
    frame.gpr[3]=0xabcdef00;put(request,0x224,0,4);mandatory_dispatch(lane,Site::Prepare,frame,invocation);
    check((frame.gpr[3]&255)==1);check(get(request,0x224,4)==0x7fffffff);
    u32 mode=0;Configuration cfg{};cfg.pins_verified=true;cfg.pins[0]=cfg.pins[16]=cfg.pins[48]=cfg.pins[80]=1;cfg.provider=provider;cfg.context=&mode;cfg.allowed=allowed;cfg.id_count=100;
    enable_ready(lane,true);invocation.action=u64(Action::Scalar);ready_dispatch(lane,cfg,frame,invocation);
    check(invocation.action==u64(Action::Ready));check(get(stack,0x6a0,4)==8);check(get(stack,0x6a8,4)==10);check(frame.gpr[13]==3);check(get(stack,0x18)==u64(request)+0x240);
    check(lane.round==1); // Ready lookup never owns or advances native round.
    for(mode=1;mode<=5;++mode){
        put(request,0x19c,7,4);frame.gpr[13]=1234;put(stack,0x6a0,42,4);enable_ready(lane,true);invocation.action=u64(Action::Scalar);
        ready_dispatch(lane,cfg,frame,invocation);check(invocation.action==u64(Action::Scalar));check(get(stack,0x6a0,4)==42);check(frame.gpr[13]==1234);
    }
    put(request,0x19c,7,4);mode=0;enable_ready(lane,true);lane.lock=1;invocation.action=u64(Action::Scalar);ready_dispatch(lane,cfg,frame,invocation);
    check(invocation.action==u64(Action::Scalar));lane.lock=0;
    check(retire_request(lane,generation,u64(request),13));check(lane.phase==u32(Phase::Quarantined));
    mandatory_dispatch(lane,Site::Entry,frame,invocation);check(invocation.action==u64(Action::Scalar));
    check(full_reset_complete(lane,generation,u64(model),0,false,false)==ResetResult::Retained);
    check(full_reset_complete(lane,generation,u64(model),0,true,true)==ResetResult::Released);
    mandatory_dispatch(lane,Site::Entry,frame,invocation);check(invocation.action==u64(Action::Stock));
    auto next=arm_pending(lane,p);check(next>generation);
    check(full_reset_complete(lane,next,u64(model),0,true,true)==ResetResult::FreshPending);
    check(lane.phase==u32(Phase::Pending)&&lane.generation==next&&lane.fresh_reset_generation==next);
    mark_loss(lane);mandatory_dispatch(lane,Site::Entry,frame,invocation);check(invocation.action==u64(Action::Scalar));
    check(full_reset_complete(lane,generation,u64(model),0,true,true)==ResetResult::Retained);
    // PostReset gate preserves new pending ownership, then releases a cancelled
    // quarantine only after the real null-cache/fresh-native conditions.
    put(stack,8,u64(record));put(record,0,u64(model));put(record,8,0);
    put(model,0x2e8,0,4);put(model,0x18,0,4);put(model,0x40,0xffffffff,4);
    put(model,0x48,0xffffffff,4);put(model,0x58,0xffffffff,4);
    lane.fresh_reset_generation=0;mandatory_dispatch(lane,Site::PostReset,frame,invocation);
    check(lane.generation==next&&lane.fresh_reset_generation==next&&lane.phase==u32(Phase::Pending));
    check(retire_pending(lane,next,p.holder));check(lane.phase==u32(Phase::Quarantined));
    put(record,8,1);mandatory_dispatch(lane,Site::PostReset,frame,invocation);check(lane.phase==u32(Phase::Quarantined));
    put(record,8,0);lane.lock=1;mandatory_dispatch(lane,Site::PostReset,frame,invocation);check(lane.phase==u32(Phase::Quarantined));
    lane.lock=0;mandatory_dispatch(lane,Site::PostReset,frame,invocation);check(lane.phase==u32(Phase::Idle)&&lane.generation==next+1);
    next=arm_pending(lane,p);check(next!=0);lane.round=~u64(0);
    mandatory_dispatch(lane,Site::Entry,frame,invocation);check(invocation.action==u64(Action::Scalar)&&lane.round==~u64(0)&&!lane.ready_enabled);
    frame.gpr[2]=u64(model);put(model,0xb7d,1,1);put(model,0x40,33,4);
    mandatory_dispatch(lane,Site::InitialFlag,frame,invocation);check(invocation.action==u64(Action::Stock)&&get(model,0xb7d,1)==0&&get(model,0x40,4)==0xffffffff);
    frame.gpr[0]=u64(model);put(model,0xb7d,1,1);put(model,0x40,44,4);
    mandatory_dispatch(lane,Site::ChunkFlag,frame,invocation);check(invocation.action==u64(Action::Stock)&&get(model,0xb7d,1)==0&&get(model,0x40,4)==0xffffffff);
    return failures;
}
