#include "shadow_collector.h"
#include <algorithm>
#include <climits>
#include <cstring>
#include <limits>

namespace halogen0173::shadow {
namespace {
template<class T> T load(std::uint64_t p, std::size_t offset=0) noexcept {
    T v{}; std::memcpy(&v,reinterpret_cast<const void*>(p+offset),sizeof(v)); return v;
}
constexpr std::array<std::size_t,8> kCounterOffsets{0,0x28,0x40,0x48,0x60,0x68,0x70,0x78};
constexpr auto kMax=std::numeric_limits<std::uint64_t>::max();
}
bool Collector::configure(bool enable, const std::array<std::uint8_t,16>& session) noexcept {
    if(enabled_ || sequence_ || count_) return false;
    if(!enable) return true;
    bool nonzero=false; for(auto b:session) nonzero|=(b!=0);
    const std::uint16_t endian=1;
    if(!nonzero || *reinterpret_cast<const std::uint8_t*>(&endian)!=1) return false;
    session_=session; enabled_=true; return true;
}
Header Collector::header() const noexcept {
    Header h{}; std::memcpy(h.runtime_sha256.data(),kRuntimeSha256,64); h.session_nonce=session_; return h;
}
bool Collector::enter() noexcept {
    if(busy_.test_and_set(std::memory_order_acquire)) { lose(); return false; }
    reconcile_loss(); return true;
}
void Collector::leave() noexcept { busy_.clear(std::memory_order_release); }
void Collector::lose() noexcept { dropped_.fetch_add(1,std::memory_order_relaxed); }
void Collector::reconcile_loss() noexcept {
    auto loss=dropped_.load(std::memory_order_relaxed);
    if(loss==loss_seen_) return;
    // A lost lifecycle observation must never turn pointer reuse into ownership.
    // Clear all bindings after any loss; a future successful birth is required.
    for(auto& o:owners_) o=Owner{};
    for(auto& s:slots_) if(s.used) {
        if(s.epoch==kMax) enabled_=false; else ++s.epoch;
    }
    loss_seen_=loss;
    gap_pending_=true;
}
bool Collector::publish(Event event) noexcept {
    if(sequence_==kMax) { enabled_=false; return false; }
    if(gap_pending_ && event.kind!=Kind::Gap) {
        if(count_+1>=kRing) { ++sequence_; lose(); return false; }
        Event gap{}; gap.kind=Kind::Gap; gap.flags=Censored;
        gap_pending_=false; publish(gap);
    }
    event.sequence=++sequence_; event.dropped_cumulative=dropped_.load(std::memory_order_relaxed);
    if(count_==kRing) { lose(); return false; }
    ring_[write_]=event; write_=(write_+1)%kRing; ++count_; return true;
}
bool Collector::drain(Event& event) noexcept {
    // A consumer that encounters the producer's short critical section has
    // dropped no native observation and must not manufacture a loss.
    if(busy_.test_and_set(std::memory_order_acquire)) return false;
    reconcile_loss();
    if(gap_pending_ && count_<kRing) {
        Event gap{}; gap.kind=Kind::Gap; gap.flags=Censored;
        gap_pending_=false; publish(gap);
    }
    if(!count_) { leave(); return false; }
    event=ring_[read_]; read_=(read_+1)%kRing; --count_; leave(); return true;
}
bool Collector::close_counts(std::uint64_t& dropped,std::uint64_t& live,std::uint64_t& pending) noexcept {
    if(enabled_ || busy_.test_and_set(std::memory_order_acquire)) return false;
    reconcile_loss();
    if(count_ || gap_pending_) { leave(); return false; }
    dropped=dropped_.load(std::memory_order_relaxed); live=pending=0;
    for(const auto& o:owners_) if(o.live) { ++live; pending+=o.pending?1u:0u; }
    leave(); return true;
}
Collector::Owner* Collector::find(std::uint64_t request) noexcept {
    for(auto& o:owners_) if(o.live && o.request==request) return &o;
    return nullptr;
}
Collector::Slot* Collector::slot(std::uint64_t model,std::int32_t number,bool create) noexcept {
    for(auto& s:slots_) if(s.used && s.model==model && s.number==number) return &s;
    if(!create || cookies_==kMax) return nullptr;
    for(auto& s:slots_) if(!s.used) { s={model,++cookies_,0,number,true}; return &s; }
    return nullptr;
}
Event Collector::identity(const Owner& o,Kind kind) const noexcept {
    Event e{}; e.kind=kind; e.owner_birth=o.birth; e.slot_cookie=o.cookie; e.slot_epoch=o.epoch;
    e.round=o.round; e.wire_request_id=o.wire; return e;
}
void Collector::invalidate(std::uint64_t model,std::int32_t number) noexcept {
    auto* s=slot(model,number,false); if(!s) return;
    if(s->epoch==kMax) { enabled_=false; return; }
    // Publish OLD owner tickets, then advance the private slot generation.
    for(auto& o:owners_) if(o.live && o.cookie==s->cookie && o.epoch==s->epoch) {
        publish(identity(o,Kind::SlotInvalidate)); o.pending=false;
    }
    ++s->epoch;
}
bool Collector::snapshot(Event& e,std::uint64_t rq,std::uint64_t record,
                         Source source,std::uint64_t offer,std::uint64_t offer_n) noexcept {
    if(!rq || !record || load<std::uint64_t>(record,0x10)!=rq) return false;
    auto model=load<std::uint64_t>(rq,0x108); if(!model) return false;
    e.source=source; e.flags|=TransportAvailable|CountersAvailable;
    e.current_id=load<std::int32_t>(rq,0x19c); e.opening_id=load<std::int32_t>(rq,0x1a0);
    e.depth_low=load<std::int32_t>(rq,0x138); e.depth_high=load<std::int32_t>(rq,0x13c);
    e.adaptive=load<std::uint8_t>(rq,0x1b0); e.stock_width=-1;
    e.transported_count=load<std::uint32_t>(record,0x58);
    e.model_position=load<std::int32_t>(model,0x2e8);
    for(std::size_t i=0;i<8;++i) e.counters[i]=load<std::uint64_t>(rq,kCounterOffsets[i]);
    // Native ceiling independent of the chosen low/high depth. All arithmetic widened.
    std::int64_t ceiling=std::min<std::int64_t>(load<std::int32_t>(model,0x14)-std::int64_t{1},
        load<std::int32_t>(model,0x118)-std::int64_t{e.model_position}-1);
    auto output_allowance=load<std::int32_t>(rq,0x228);
    if(output_allowance>0) ceiling=std::min(ceiling,std::int64_t{output_allowance}-1);
    if(source==Source::Pld) ceiling=std::min(ceiling,std::int64_t{load<std::int32_t>(rq,0x120)});
    e.native_allowance=static_cast<std::int32_t>(std::clamp<std::int64_t>(ceiling,0,INT32_MAX));
    // This is the native PLD host-history vector. It includes prompt/history IDs,
    // and is not described as a transport-only transcript. Copy only its suffix.
    if(load<std::int32_t>(rq,0x11c)>0 && load<std::uint64_t>(rq,0x190)==0) {
        const auto begin=load<std::uint64_t>(rq,0x1c0),end=load<std::uint64_t>(rq,0x1c8),cap=load<std::uint64_t>(rq,0x1d0);
        if(begin<=end && end<=cap && ((end-begin)&3)==0 && ((cap-begin)&3)==0 &&
           (begin || end==0) && (end-begin)/4<=UINT32_MAX) {
            e.context_total=static_cast<std::uint32_t>((end-begin)/4);
            e.context_count=std::min<std::uint32_t>(e.context_total,kContextCapacity);
            e.flags|=ContextAvailable;
            if(e.context_count<e.context_total) e.flags|=ContextTruncated;
            if(e.context_count) std::memcpy(e.context_suffix.data(),reinterpret_cast<const void*>(end-4*e.context_count),4*e.context_count);
        } else e.flags|=Censored;
    }
    if(source==Source::Pld && offer) {
        if(offer_n>INT32_MAX) return false;
        e.offer_total=static_cast<std::uint32_t>(offer_n); e.offer_count=std::min<std::uint32_t>(e.offer_total,kOfferCapacity);
        e.flags|=OfferAvailable; if(e.offer_count<e.offer_total) e.flags|=OfferTruncated;
        if(e.offer_count) std::memcpy(e.pld_offer.data(),reinterpret_cast<const void*>(offer),4*e.offer_count);
        e.stock_width=static_cast<std::int32_t>(offer_n);
        // Constraint virtual calls occur after the copied-hit seam. Their ABI
        // does not certify unchanged proposals for this first training route.
        if(load<std::uint64_t>(rq,0x240)!=0) e.flags|=Censored;
    }
    return true;
}
void Collector::on_site(Site site,const Frame& f) noexcept {
    // In particular, disabled mode must not dereference bogus native pointers.
    if(!enabled_ || !enter()) return;
    if(!enabled_) { leave(); return; }
    const auto rsp=f.gpr[7];
    if(site==Site::SuccessfulBirthA || site==Site::SuccessfulBirthB) {
        const auto record=rsp+0xa00, rq=load<std::uint64_t>(record,0x10);
        // These append seams also admit serial records whose native branch
        // bypasses Request construction. No owned Request was lost there.
        if(!rq) { leave(); return; }
        const auto model=rq?load<std::uint64_t>(rq,0x108):0;
        const auto number=load<std::int32_t>(record,8);
        auto* s=model?slot(model,number,true):nullptr;
        auto* o=find(rq);
        // No inspected native path re-births a live allocation. This is missing
        // lifecycle coverage or duplicate interception, never synthetic retirement.
        if(o) { lose(); leave(); return; }
        if(!o) for(auto& candidate:owners_) if(!candidate.live) { o=&candidate; break; }
        if(!rq || !s || !o || births_==kMax || s->epoch==kMax) { lose(); leave(); return; }
        ++s->epoch;
        for(auto& prior:owners_) if(prior.live && prior.cookie==s->cookie) prior.pending=false;
        // Native output formatter loads Record+0 as a signed 64-bit ID.
        // Preserve its full bit pattern in the existing uint64 wire field.
        *o={rq,model,++births_,load<std::uint64_t>(record),s->cookie,s->epoch,0,number,true,false,{}};
        if(publish(identity(*o,Kind::Birth))) publish(identity(*o,Kind::SlotAttach));
    } else if(site==Site::RequestDestructor) {
        if(auto* o=find(f.gpr[5])) { publish(identity(*o,Kind::Retire)); *o=Owner{}; }
    } else if(site==Site::SlotBind) {
        invalidate(f.gpr[5],static_cast<std::int32_t>(f.gpr[4]));
    } else if(site==Site::CurrentSlotReset) {
        auto model=f.gpr[5]; if(model) invalidate(model,load<std::int32_t>(model,0xc8));
    } else if(site==Site::SlotRelease) {
        auto aggregate=f.gpr[5]; if(aggregate) invalidate(load<std::uint64_t>(aggregate),static_cast<std::int32_t>(f.gpr[4]));
    } else {
        const auto rq=load<std::uint64_t>(rsp,0x10), record=load<std::uint64_t>(rsp,0x78);
        auto* o=find(rq); auto* s=o?slot(o->model,o->slot,false):nullptr;
        if(!o || !s || o->epoch!=s->epoch || !record || load<std::uint64_t>(record,0x10)!=rq ||
           load<std::uint64_t>(record)!=o->wire || load<std::int32_t>(record,8)!=o->slot) { leave(); return; }
        if(site==Site::BeforeNeuralDepth || site==Site::PldCopiedHit) {
            // A copied PLD hit can fail the native opening check and then reach
            // the neural depth seam. Close that unattempted candidate explicitly.
            if(o->pending && site==Site::BeforeNeuralDepth && o->before.source==Source::Pld) {
                auto skipped=identity(*o,Kind::Outcome);
                if(!snapshot(skipped,rq,record,Source::Neural,0,0)) { lose(); leave(); return; }
                skipped.source=Source::Pld; skipped.flags|=Censored|Continuing;
                skipped.context_total=skipped.context_count=0; skipped.context_suffix.fill(0);
                skipped.flags&=~(ContextAvailable|ContextTruncated);
                publish(skipped); o->pending=false;
            }
            if(o->pending || o->round==kMax) { lose(); leave(); return; }
            ++o->round; auto e=identity(*o,Kind::Begin);
            auto source=site==Site::BeforeNeuralDepth?Source::Neural:Source::Pld;
            if(!snapshot(e,rq,record,source,source==Source::Pld?rsp+0x6a0:0,source==Source::Pld?f.gpr[1]:0)) { lose(); leave(); return; }
            o->before=e; o->pending=publish(e);
        } else if(site==Site::CommonOutcome && o->pending) {
            auto e=identity(*o,Kind::Outcome); const auto before=o->before; o->pending=false;
            if(!snapshot(e,rq,record,before.source,0,0)) { lose(); leave(); return; }
            e.context_total=e.context_count=e.offer_total=e.offer_count=0;
            e.context_suffix.fill(0); e.pld_offer.fill(0);
            e.flags&=~(ContextAvailable|ContextTruncated|OfferAvailable|OfferTruncated);
            e.native_status=static_cast<std::int32_t>(f.gpr[0]); e.stock_width=before.stock_width;
            e.flags|=before.flags&Censored;
            bool monotonic=e.transported_count>=before.transported_count;
            for(std::size_t i=0;i<8;++i) monotonic&=e.counters[i]>=before.counters[i];
            const auto attempted=before.source==Source::Neural?6u:4u,accepted=before.source==Source::Neural?7u:3u;
            const auto n=e.counters[attempted]-before.counters[attempted],a=e.counters[accepted]-before.counters[accepted];
            if(!monotonic || a>n || n==0) e.flags|=Censored;
            if(e.native_status==0) e.flags|=Continuing;
            else e.flags|=Terminal;
            if(e.native_status!=0 && e.native_status!=1 && e.native_status!=-1 && e.native_status!=-2) e.flags|=Censored;
            if(monotonic && n>0 && std::uint64_t{e.transported_count-before.transported_count}<a+1) e.flags|=PartialOutput;
            publish(e);
        }
    }
    leave();
}
} // namespace halogen0173::shadow
