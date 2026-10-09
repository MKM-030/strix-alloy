#include "native_adapter.h"
#include <cstring>
#include <limits>
namespace halogen0173::dflash::prefill {
namespace {
template<class T>T read(std::uint64_t base,std::size_t offset=0) noexcept {
    T value{};std::memcpy(&value,reinterpret_cast<const void*>(base+offset),sizeof(value));return value;
}
template<class T>void write(std::uint64_t base,std::size_t offset,T value) noexcept {
    std::memcpy(reinterpret_cast<void*>(base+offset),&value,sizeof(value));
}
bool ids(std::uint64_t object,const std::int32_t*& out,std::uint32_t& count) noexcept {
    const auto begin=read<std::uint64_t>(object,0x38),end=read<std::uint64_t>(object,0x40),cap=read<std::uint64_t>(object,0x48);
    const auto total=read<std::int32_t>(object,0x54);
    if(total<=0 || !begin || begin>end || end>cap || ((end-begin)&3) || ((cap-begin)&3) ||
       (end-begin)/4!=static_cast<std::uint32_t>(total))return false;
    out=reinterpret_cast<const std::int32_t*>(begin);count=static_cast<std::uint32_t>(total);return true;
}
}
bool NativeAdapter::configure(bool enable,Owner* owner,NativeProof proof) noexcept {
    if(enabled_)return false;
    if(!enable)return true;
    if(!owner || !proof.admit || !proof.selected_model || !proof.default_stream_verified)return false;
    owner_=owner;proof_=proof;enabled_=true;return true;
}
void NativeAdapter::on_site(Site site,const Frame& f) noexcept {
    // Off mode does not touch even deliberately invalid native addresses.
    if(!enabled_)return;
    const auto rsp=f.gpr[7];
    if(site==Site::PendingPublication) {
        const auto holder=read<std::uint64_t>(rsp,0x88),aggregate=read<std::uint64_t>(rsp,8);
        if(!holder || !aggregate)return;
        const auto model=read<std::uint64_t>(aggregate);
        if(model!=proof_.selected_model || read<std::uint64_t>(aggregate,8)!=0)return;
        const auto slot=read<std::int32_t>(holder,8);
        const auto mode=read<std::uint32_t>(holder,0xc);
        const auto wire=read<std::uint64_t>(holder);
        const std::int32_t* input{};std::uint32_t total{};std::uint64_t cache_generation{};
        if(!ids(holder,input,total) || mode!=1 || !proof_.admit(proof_.context,holder,model,wire,slot,cache_generation))return;
        owner_->publish({holder,model,wire,cache_generation,slot,read<std::int32_t>(model,0xc8),mode,1,total,input,true,true,true});
    } else if(site==Site::InitialFlagJoin || site==Site::ChunkFlagJoin) {
        const auto holder=site==Site::InitialFlagJoin?read<std::uint64_t>(rsp,0x88):f.gpr[14];
        const auto aggregate=site==Site::InitialFlagJoin?read<std::uint64_t>(rsp,8):f.gpr[15];
        if(!holder || !aggregate)return;
        const auto model=read<std::uint64_t>(aggregate);
        if(model==proof_.selected_model && owner_->force_serial(holder,model,read<std::int32_t>(holder,8))) {
            write<std::uint8_t>(model,0xb7d,0);write<std::int32_t>(model,0x40,-1);
        }
    } else if(site==Site::ChunkForward) {
        const auto holder=f.gpr[14],model=f.gpr[5];
        if(!holder || model!=proof_.selected_model)return;
        const auto processed=read<std::int32_t>(holder,0x410),count=static_cast<std::int32_t>(f.gpr[13]);
        if(processed<0 || count<=0 || f.gpr[4]!=read<std::uint64_t>(holder,0x38)+std::uint64_t{static_cast<std::uint32_t>(processed)}*4 ||
           static_cast<std::int32_t>(f.gpr[3])!=count) {owner_->source_loss();return;}
        owner_->begin_chunk(holder,model,static_cast<std::uint32_t>(processed),static_cast<std::uint32_t>(count),read<std::int32_t>(model,0x2e8),nullptr);
    } else if(site==Site::ChunkForwardReturned) {
        const auto holder=f.gpr[14];if(!holder)return;
        const auto b=owner_->binding();if(!b.model || b.holder!=holder || owner_->state()!=State::Pending)return;
        const auto old=read<std::int32_t>(holder,0x410),count=static_cast<std::int32_t>(f.gpr[13]);
        if(old<0 || count<=0 || std::int64_t{old}+count>std::numeric_limits<std::int32_t>::max()) {owner_->source_loss();return;}
        owner_->end_chunk(holder,static_cast<std::uint32_t>(old+count),read<std::int32_t>(b.model,0x2e8));
    } else if(site==Site::RecordMaterialize) {
        const auto holder=f.gpr[4];if(!holder)return;
        const auto processed=read<std::int32_t>(holder,0x410);
        if(processed<0)return;
        owner_->materialize(holder,read<std::uint64_t>(holder),read<std::int32_t>(holder,8),static_cast<std::uint32_t>(processed));
    } else if(site==Site::PendingDestructor) {
        owner_->holder_destructor(f.gpr[5]);
    } else if(site==Site::RequestDestructor) {
        owner_->request_destructor(f.gpr[5]);
    } else if(site==Site::RecordDestructor) {
        if(owner_->state()!=State::Materialized || !f.gpr[5])return;
        const auto record=f.gpr[5];const std::int32_t* input{};std::uint32_t total{};
        if(ids(record,input,total))owner_->abandon_materialized(read<std::uint64_t>(record),read<std::int32_t>(record,8),
            read<std::uint32_t>(record,0xc),input,total);
    } else if(site==Site::SuccessfulBirthA || site==Site::SuccessfulBirthB) {
        const auto record=rsp+0xa00,request=read<std::uint64_t>(record,0x10);
        if(!request)return; // Actual serial record ABI intentionally unselected.
        const auto model=read<std::uint64_t>(request,0x108);
        if(model!=proof_.selected_model)return;
        const std::int32_t* input{};std::uint32_t total{};
        if(!ids(record,input,total) || births_==std::numeric_limits<std::uint64_t>::max()) {owner_->source_loss();return;}
        owner_->transfer(request,++births_,model,read<std::uint64_t>(record),read<std::int32_t>(record,8),read<std::uint32_t>(record,0xc),input,total);
    }
}
void NativeAdapter::on_hc(const Frame& f) noexcept {
    if(!enabled_ || f.gpr[14]!=proof_.selected_model)return;
    const auto b=owner_->binding();if(!b.lease_generation || owner_->state()!=State::Pending)return;
    const auto layer=static_cast<std::uint32_t>(f.gpr[1]),rows=static_cast<std::uint32_t>(f.gpr[6]);
    owner_->capture_hc(f.gpr[14],layer,rows,reinterpret_cast<const void*>(read<std::uint64_t>(f.gpr[14],0x948)),nullptr);
}
}
