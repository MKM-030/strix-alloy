#pragma once
// Freestanding retained controller. No allocator, OS/device call or installer.
namespace hgn_dflash {
using u8=__UINT8_TYPE__;using u32=__UINT32_TYPE__;using u64=__UINT64_TYPE__;using i32=__INT32_TYPE__;using i64=__INT64_TYPE__;
enum class Phase:u32{Idle,Pending,Request,Quarantined};enum class Action:u64{Stock,Scalar,Ready};enum class Site:u32{Entry,Prepare,PostReset,InitialFlag,ChunkFlag};
enum class ResetResult:u32{Retained,Released,FreshPending};
struct Lane {
    u64 model{};i32 slot{};u32 configured{};u64 generation{};u32 phase{},lock{};
    u64 request{},holder{},wire{},birth{},cache_generation{},pending_ticket{},round{},loss{},fresh_reset_generation{};
    u32 materialized{},ready_enabled{};
};
static_assert(sizeof(Lane)==112);
static_assert(__builtin_offsetof(Lane,phase)==24&&__builtin_offsetof(Lane,lock)==28);
static_assert(__builtin_offsetof(Lane,loss)==88&&__builtin_offsetof(Lane,fresh_reset_generation)==96);
struct PendingBinding{u64 model{},holder{},wire{},cache_generation{},pending_ticket{};i32 slot{};};
struct Frame{u64 gpr[16]{};u64 ordinary_rflags{};};struct Invocation{u64 action{};};
static_assert(sizeof(Frame)==136&&sizeof(Invocation)==8);
struct Binding {
    u8 pins[112]{}; // Session16, loaded target32, tokenizer32, trained drafter32.
    u64 generation{},wire{},birth{},cache_generation{},pending_ticket{},round{},loss{};
    i32 position{},current{};u32 history_total{},history_count{};i32 suffix[64]{};
};
struct Snapshot{Binding binding{};};struct Candidate{Binding binding{};u32 count{};i32 ids[3]{};};
using Provider=bool(*)(void*,const Snapshot&,Candidate&)noexcept;
struct Configuration{bool pins_verified{};u8 pins[112]{};const u8* allowed{};u32 id_count{};Provider provider{};void* context{};};
template<class T> inline T atomic_load(const T& v)noexcept{return __atomic_load_n(&v,__ATOMIC_ACQUIRE);}
template<class T> inline void atomic_store(T& v,T x)noexcept{__atomic_store_n(&v,x,__ATOMIC_RELEASE);}
inline bool enter(Lane& l)noexcept{u32 expected=0;return __atomic_compare_exchange_n(&l.lock,&expected,1,false,__ATOMIC_ACQUIRE,__ATOMIC_RELAXED);}
inline void leave(Lane& l)noexcept{atomic_store(l.lock,u32(0));}
struct Lock{Lane& lane;bool held;explicit Lock(Lane& l):lane(l),held(enter(l)){}~Lock(){if(held)leave(lane);}};
inline void mark_loss(Lane& l)noexcept{__atomic_fetch_add(&l.loss,u64(1),__ATOMIC_ACQ_REL);atomic_store(l.ready_enabled,u32(0));}
// Exactly one native transaction entry owns the round stamp. Optional lookup
// does not advance it. Contention/overflow loses provider ownership while the
// retained mandatory serial gate remains effective.
inline u64 begin_transaction(Lane& l)noexcept{
    auto expected=atomic_load(l.round);
    if(expected==~u64(0)){mark_loss(l);return 0;}
    const auto next=expected+1;
    if(!__atomic_compare_exchange_n(&l.round,&expected,next,false,__ATOMIC_ACQ_REL,__ATOMIC_ACQUIRE)){
        mark_loss(l);return 0;
    }
    return next;
}
inline bool pin_lane(Lane& l,u64 model,i32 slot)noexcept{
    Lock lock(l);if(!lock.held||!model||slot<0||atomic_load(l.configured))return false;
    l.model=model;l.slot=slot;atomic_store(l.configured,u32(1));return true;
}
inline u64 arm_pending(Lane& l,const PendingBinding& p)noexcept{
    Lock lock(l);if(!lock.held){mark_loss(l);return 0;}
    if(!atomic_load(l.configured)||p.model!=l.model||p.slot!=l.slot||!p.holder||!p.cache_generation||!p.pending_ticket
       ||atomic_load(l.phase)==u32(Phase::Pending)||atomic_load(l.phase)==u32(Phase::Request)||atomic_load(l.generation)==~u64(0))return 0;
    const auto generation=atomic_load(l.generation)+1;atomic_store(l.generation,generation);
    l.request=l.birth=0;l.holder=p.holder;l.wire=p.wire;l.cache_generation=p.cache_generation;
    l.pending_ticket=p.pending_ticket;atomic_store(l.round,u64(0));l.fresh_reset_generation=0;l.materialized=0;atomic_store(l.ready_enabled,u32(0));
    atomic_store(l.phase,u32(Phase::Pending));return generation;
}
inline bool materialize_pending(Lane& l,u64 generation,u64 holder)noexcept{
    Lock lock(l);if(!lock.held){mark_loss(l);return false;}
    if(atomic_load(l.generation)!=generation||l.holder!=holder||atomic_load(l.phase)!=u32(Phase::Pending))return false;
    l.materialized=1;return true;
}
inline bool transfer_pending(Lane& l,u64 generation,const PendingBinding& p,u64 request,u64 birth)noexcept{
    Lock lock(l);if(!lock.held){mark_loss(l);return false;}
    if(!request||!birth||atomic_load(l.generation)!=generation||atomic_load(l.phase)!=u32(Phase::Pending)||!l.materialized
       ||l.fresh_reset_generation!=generation||l.model!=p.model||l.slot!=p.slot||l.holder!=p.holder||l.wire!=p.wire
       ||l.cache_generation!=p.cache_generation||l.pending_ticket!=p.pending_ticket)return false;
    l.request=request;l.birth=birth;atomic_store(l.ready_enabled,u32(0));atomic_store(l.phase,u32(Phase::Request));return true;
}
inline bool retire_pending(Lane& l,u64 generation,u64 holder)noexcept{
    Lock lock(l);if(!lock.held){mark_loss(l);return false;}if(atomic_load(l.generation)!=generation||l.holder!=holder)return false;
    auto phase=atomic_load(l.phase);
    // Normal holder destruction follows materialization BEFORE Request birth.
    if(phase==u32(Phase::Request)||(phase==u32(Phase::Pending)&&l.materialized))return true;
    if(phase!=u32(Phase::Pending))return false;
    atomic_store(l.ready_enabled,u32(0));atomic_store(l.phase,u32(Phase::Quarantined));return true;
}
inline bool retire_request(Lane& l,u64 generation,u64 request,u64 birth)noexcept{
    Lock lock(l);if(!lock.held){mark_loss(l);return false;}
    if(atomic_load(l.generation)!=generation||atomic_load(l.phase)!=u32(Phase::Request)||l.request!=request||l.birth!=birth)return false;
    atomic_store(l.ready_enabled,u32(0));l.request=0;atomic_store(l.phase,u32(Phase::Quarantined));return true;
}
inline bool retire_materialized(Lane& l,u64 generation,const PendingBinding& p)noexcept{
    Lock lock(l);if(!lock.held){mark_loss(l);return false;}
    if(atomic_load(l.generation)!=generation||atomic_load(l.phase)!=u32(Phase::Pending)||!l.materialized
       ||l.model!=p.model||l.slot!=p.slot||l.holder!=p.holder||l.wire!=p.wire
       ||l.cache_generation!=p.cache_generation||l.pending_ticket!=p.pending_ticket)return false;
    atomic_store(l.ready_enabled,u32(0));atomic_store(l.phase,u32(Phase::Quarantined));return true;
}
inline void enable_ready(Lane& l,bool enabled)noexcept{atomic_store(l.ready_enabled,u32(enabled&&atomic_load(l.phase)==u32(Phase::Request)));}
inline ResetResult full_reset_complete(Lane& l,u64 generation,u64 model,i32 slot,bool cache_null,bool fresh_native)noexcept{
    Lock lock(l);if(!lock.held)return ResetResult::Retained;
    if(!cache_null||!fresh_native||l.model!=model||l.slot!=slot||atomic_load(l.generation)!=generation)return ResetResult::Retained;
    auto phase=atomic_load(l.phase);atomic_store(l.ready_enabled,u32(0));
    if(phase==u32(Phase::Pending)){l.fresh_reset_generation=generation;return ResetResult::FreshPending;}
    if(phase==u32(Phase::Idle)||atomic_load(l.generation)==~u64(0))return ResetResult::Retained;
    atomic_store(l.generation,atomic_load(l.generation)+1);l.request=l.birth=0;
    atomic_store(l.round,u64(0));atomic_store(l.phase,u32(Phase::Idle));return ResetResult::Released;
}
inline u64 native_read(u64 ptr,u32 offset,u32 count=8)noexcept{
    u64 result=0;auto* p=reinterpret_cast<const u8*>(ptr+offset);for(u32 i=0;i<count;++i)result|=u64(p[i])<<(8*i);return result;
}
inline void native_write(u64 ptr,u32 offset,u64 value,u32 count=8)noexcept{
    auto* p=reinterpret_cast<u8*>(ptr+offset);for(u32 i=0;i<count;++i)p[i]=u8(value>>(8*i));
}
inline i32 native_i32(u64 ptr,u32 offset)noexcept{return i32(native_read(ptr,offset,4));}
inline bool matches_lane(const Lane& l,u64 model)noexcept{
    return model&&atomic_load(l.configured)&&atomic_load(l.phase)!=u32(Phase::Idle)&&l.model==model&&native_i32(model,0xc8)==l.slot;
}
// CPU counterpart of the relay's unconditional gate; optional collection,
// readiness, callback admission and producer loss never remove quarantine.
inline void mandatory_dispatch(Lane& l,Site site,Frame& f,Invocation& out)noexcept{
    out.action=u64(Action::Stock);
    if(site==Site::InitialFlag||site==Site::ChunkFlag){
        auto model=site==Site::InitialFlag?f.gpr[2]:f.gpr[0];
        if(matches_lane(l,model)){native_write(model,0xb7d,0,1);native_write(model,0x40,0xffffffff,4);}
        return;
    }
    if(site==Site::PostReset){
        auto aggregate=native_read(f.gpr[7],8);if(!aggregate)return;auto model=native_read(aggregate,0);
        if(model==l.model&&model&&native_read(aggregate,8)==0&&native_i32(model,0xc8)==l.slot){
            bool fresh=native_i32(model,0x2e8)==0&&native_i32(model,0x18)==0&&native_i32(model,0x40)==-1
                &&native_i32(model,0x48)==-1&&native_i32(model,0x58)==-1;
            full_reset_complete(l,atomic_load(l.generation),model,l.slot,true,fresh);
        }return;
    }
    auto request=site==Site::Entry?f.gpr[4]:f.gpr[1];if(!request)return;auto model=native_read(request,0x108);
    if(!matches_lane(l,model)||(site==Site::Entry&&f.gpr[5]!=model))return;
    native_write(request,0x224,0x7fffffff,4);native_write(model,0xb7d,0,1);native_write(model,0x40,0xffffffff,4);
    if(site==Site::Prepare)f.gpr[3]=(f.gpr[3]&~u64(255))|1;
    else {out.action=u64(Action::Scalar);begin_transaction(l);}
}
inline bool equal(const Binding& a,const Binding& b)noexcept{
    for(u32 i=0;i<112;++i)if(a.pins[i]!=b.pins[i])return false;
    if(a.generation!=b.generation||a.wire!=b.wire||a.birth!=b.birth||a.cache_generation!=b.cache_generation
       ||a.pending_ticket!=b.pending_ticket||a.round!=b.round||a.loss!=b.loss||a.position!=b.position
       ||a.current!=b.current||a.history_total!=b.history_total||a.history_count!=b.history_count)return false;
    for(u32 i=0;i<64;++i)if(a.suffix[i]!=b.suffix[i])return false;
    return true;
}
inline bool snapshot_native(const Lane& l,const Configuration& cfg,const Frame& f,u64 round,Snapshot& out)noexcept{
    const auto request=f.gpr[4],model=f.gpr[5],rsp=f.gpr[7];if(!request||!model||!rsp)return false;auto record=native_read(rsp,0x78);
    if(atomic_load(l.phase)!=u32(Phase::Request)||l.request!=request||l.model!=model||!record
       ||native_read(request,0x108)!=model||native_read(record,0x10)!=request||native_read(record,0)!=l.wire
       ||native_i32(record,8)!=l.slot||native_i32(model,0xc8)!=l.slot)return false;
    if(native_i32(request,0x11c)<=0||native_read(request,0x190)||native_read(request,0x240)||native_i32(request,0x218)!=0
       ||native_i32(request,0x120)<3||native_i32(model,0x14)<4||native_i32(model,0x2e0)<4
       ||native_read(model,0xb7c,1)!=1||native_i32(model,0x164)!=0)return false;
    auto position=native_i32(model,0x2e8),allowance=native_i32(request,0x228);
    if(position<=0||i64(position)+4>i64(native_i32(model,0x118))||(allowance>0&&allowance<4))return false;
    auto begin=native_read(request,0x1c0),end=native_read(request,0x1c8),cap=native_read(request,0x1d0);
    if(!begin||begin>end||end>cap||((end-begin)&3)||((cap-begin)&3)||(end-begin)/4>0xffffffff)return false;
    auto total=u32((end-begin)/4);if(!total)return false;auto& k=out.binding;
    for(u32 i=0;i<112;++i)k.pins[i]=cfg.pins[i];
    k.generation=atomic_load(l.generation);k.wire=l.wire;k.birth=l.birth;k.cache_generation=l.cache_generation;
    k.pending_ticket=l.pending_ticket;k.round=round;k.loss=atomic_load(l.loss);k.position=position;k.current=native_i32(request,0x19c);
    k.history_total=total;k.history_count=total<64?total:64;
    for(u32 i=0;i<64;++i)k.suffix[i]=i<k.history_count?native_i32(end-4*k.history_count,4*i):0;
    return k.suffix[k.history_count-1]==k.current;
}
inline bool complete_pins(const Configuration& cfg)noexcept{
    const u32 ends[4]={16,48,80,112};u32 start=0;
    for(auto end:ends){bool any=false;for(auto i=start;i<end;++i)any|=cfg.pins[i]!=0;if(!any)return false;start=end;}return true;
}
inline void ready_dispatch(Lane& l,const Configuration& cfg,Frame& f,Invocation& out)noexcept{
    if(out.action!=u64(Action::Scalar)||!atomic_load(l.ready_enabled)||!cfg.pins_verified||!complete_pins(cfg)
       ||!cfg.provider||!cfg.allowed||!cfg.id_count)return;
    Lock lock(l);if(!lock.held)return;
    const auto round=atomic_load(l.round);if(!round||round==~u64(0))return;
    Snapshot before{};if(!snapshot_native(l,cfg,f,round,before))return;Candidate candidate{};
    // Already-ready copied values only: no native pointers escape to provider.
    if(!cfg.provider(cfg.context,before,candidate)||candidate.count!=3||!equal(before.binding,candidate.binding))return;
    for(auto id:candidate.ids)if(id<0||u32(id)>=cfg.id_count||!(cfg.allowed[u32(id)/8]&u8(1u<<(u32(id)%8))))return;
    if(!atomic_load(l.ready_enabled))return;
    Snapshot after{};
    if(atomic_load(l.round)!=round||!snapshot_native(l,cfg,f,round,after)||!equal(before.binding,after.binding))return;
    auto rsp=f.gpr[7];for(u32 i=0;i<3;++i)native_write(rsp,0x6a0+4*i,u32(candidate.ids[i]),4);
    native_write(rsp,0x18,f.gpr[4]+0x240);f.gpr[13]=3;out.action=u64(Action::Ready);
}
}
