#include "native_decode_adapter.h"
#include <cstring>
#include <limits>
namespace halogen0173::dflash::prefill {
namespace {template<class T>T read(std::uint64_t p,std::size_t off=0) noexcept {T v{};std::memcpy(&v,reinterpret_cast<const void*>(p+off),sizeof(v));return v;}}
bool NativeDecodeAdapter::configure(bool enable,Owner* owner,DecodeCapture* capture,RoundSource rounds,bool stream) noexcept {
    if(enabled_)return false;
    if(!enable)return true;
    if(!owner || !capture || !rounds.current || !stream)return false;
    owner_=owner;capture_=capture;rounds_=rounds;enabled_=true;return true;
}
void NativeDecodeAdapter::on_site(DecodeSite site,const Frame& f) noexcept {
    if(!enabled_)return;
    const auto b=owner_->binding();
    if(site==DecodeSite::RequestDestructor) {
        if(b.request==f.gpr[5]) {capture_->retire(b.lease_generation);active_=false;}
        return;
    }
    if(site==DecodeSite::VerifyBegin || site==DecodeSite::ScalarBegin) {
        if(owner_->state()!=State::Request || !b.request || f.gpr[5]!=b.model)return;
        const auto rq=read<std::uint64_t>(f.gpr[7],0x10),record=read<std::uint64_t>(f.gpr[7],0x78);
        const auto count=static_cast<std::uint32_t>(f.gpr[3]);
        if(rq!=b.request || !record || read<std::uint64_t>(record,0x10)!=rq ||
           read<std::uint64_t>(record)!=b.wire || read<std::int32_t>(record,8)!=b.slot ||
           !f.gpr[4] ||
           read<std::int32_t>(f.gpr[4])!=read<std::int32_t>(rq,0x19c)) {capture_->source_loss();return;}
        const auto round=rounds_.current(rounds_.context,b);
        active_=capture_->begin(b,round,site==DecodeSite::VerifyBegin?DecodeSource::Verify:DecodeSource::Scalar,
            read<std::int32_t>(b.model,0x2e8),reinterpret_cast<const std::int32_t*>(f.gpr[4]),count,read<std::uint32_t>(record,0x58));
        if(active_) {active_binding_=b;commit_count_=0;}
    } else if(active_) {
        if(site==DecodeSite::VerifyReturned)capture_->forward_returned();
        else if(site==DecodeSite::CommitBegin)commit_count_=static_cast<std::uint32_t>(f.gpr[4]);
        else if(site==DecodeSite::CommitReturned)capture_->committed(commit_count_,read<std::int32_t>(active_binding_.model,0x2e8));
        else if(site==DecodeSite::ScalarReturned) {
            capture_->forward_returned();capture_->committed(1,read<std::int32_t>(active_binding_.model,0x2e8));
        } else if(site==DecodeSite::CommonOutcome) {
            const auto record=read<std::uint64_t>(f.gpr[7],0x78);
            if(!record || read<std::uint64_t>(record,0x10)!=active_binding_.request ||
               b.request!=active_binding_.request || b.birth!=active_binding_.birth)capture_->retire(active_binding_.lease_generation);
            else capture_->outcome(b,static_cast<std::int32_t>(f.gpr[0]),read<std::int32_t>(b.request,0x19c),read<std::uint32_t>(record,0x58));
            active_=false;
        }
    }
}
void NativeDecodeAdapter::on_hc(const Frame& f) noexcept {
    if(!enabled_ || !active_ || f.gpr[14]!=active_binding_.model)return;
    capture_->capture_hc(f.gpr[14],static_cast<std::uint32_t>(f.gpr[1]),static_cast<std::uint32_t>(f.gpr[6]),
        reinterpret_cast<const void*>(read<std::uint64_t>(f.gpr[14],0x948)),nullptr);
}
}
