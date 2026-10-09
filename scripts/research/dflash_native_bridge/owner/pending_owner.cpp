#include "pending_owner.h"
#include <cstring>
#include <limits>
namespace halogen0173::dflash::prefill {
bool Owner::configure(bool enabled,const std::array<std::uint8_t,16>& session,
                      Storage storage,LeaseOps lease,CopyOps copy) noexcept {
    if(configured_) return false;
    if(!enabled) return true;
    bool nonzero=false;for(auto b:session)nonzero|=b!=0;
    if(!nonzero || !storage.ids || !storage.id_capacity || !storage.features || !storage.fence ||
       storage.id_capacity>std::numeric_limits<std::uint32_t>::max() ||
       storage.id_capacity>std::numeric_limits<std::size_t>::max()/kConcatRowBytes ||
       storage.feature_bytes<storage.id_capacity*kConcatRowBytes ||
       !lease.arm || !lease.valid || !lease.healthy || !lease.materialize || !lease.transfer || !lease.retire || !lease.loss || !lease.abandon_materialized ||
       !copy.copy_2d || !copy.record_fence || !copy.query_fence) return false;
    session_=session;storage_=storage;lease_=lease;copy_=copy;configured_=true;
    enabled_.store(true,std::memory_order_release);return true;
}
bool Owner::enter(bool contention_loss) noexcept {
    if(busy_.test_and_set(std::memory_order_acquire)) {if(contention_loss)source_loss();return false;}
    const auto n=losses_.load(std::memory_order_acquire);
    if(n!=seen_loss_) {feature_valid_=false;seen_loss_=n;}
    drain_retirements();
    return true;
}
void Owner::leave() noexcept {drain_retirements();busy_.clear(std::memory_order_release);}
bool Owner::pin_identity() noexcept {
    identity_users_.fetch_add(1,std::memory_order_seq_cst);
    if(!identity_writer_.load(std::memory_order_seq_cst))return true;
    unpin_identity();return false;
}
void Owner::unpin_identity() noexcept {identity_users_.fetch_sub(1,std::memory_order_seq_cst);}
void Owner::retire_local(bool materialized) noexcept {
    if(state_==State::Retired)return;
    if(copy_queued_ && !fence_recorded_) {
        fence_recorded_=copy_.record_fence(copy_.context,storage_.fence,stream_);
        fence_failed_=!fence_recorded_;
    }
    feature_valid_=false;chunk_open_=false;
    retirement_binding_=binding_;retirement_materialized_=materialized;retirement_waiting_=true;
    state_.store(State::Retired,std::memory_order_release);
}
void Owner::drain_retirements() noexcept {
    const auto g=generation_.load(std::memory_order_acquire);
    const auto holder=holder_retirement_.exchange(0,std::memory_order_acq_rel);
    const auto pending_holder=pending_holder_retirement_.exchange(0,std::memory_order_acq_rel);
    const auto request=request_retirement_.exchange(0,std::memory_order_acq_rel);
    const auto materialized=materialized_retirement_.exchange(0,std::memory_order_acq_rel);
    if(g && holder==g && holder_live_)holder_live_=false;
    if(g && pending_holder==g) {
        holder_live_=false;
        if(state_==State::Pending || state_==State::Materialized || state_==State::Request)
            retire_local(state_==State::Materialized);
    }
    if(g && request==g && state_==State::Request)retire_local();
    if(g && materialized==g && (state_==State::Materialized || state_==State::Request))
        retire_local(state_==State::Materialized);
    if(retirement_waiting_) {
        const bool done=retirement_materialized_?
            lease_.abandon_materialized(lease_.context,retirement_binding_):
            lease_.retire(lease_.context,retirement_binding_);
        if(done)retirement_waiting_=false;
    }
}
void Owner::source_loss() noexcept {
    losses_.fetch_add(1,std::memory_order_acq_rel);
    const auto g=generation_.load(std::memory_order_acquire);
    if(g && lease_.loss)lease_.loss(lease_.context,g);
}
void Owner::invalidate() noexcept {feature_valid_=false;source_loss();}
bool Owner::publish(const Admission& a) noexcept {
    if(!enabled_.load(std::memory_order_acquire) || !enter()) return false;
    const auto state=state_.load(std::memory_order_relaxed);
    if((state!=State::Idle && state!=State::Retired) || retirement_waiting_ || borrowed_ ||
       (copy_queued_ && !finish_fence())) {leave();return false;}
    if(!a.holder || !a.model || !a.cache_generation || a.slot!=0 || a.current_slot!=a.slot ||
       a.generation_mode!=1 || a.slot_count!=1 || !a.actual_cache_null ||
       !a.ordinary_text || !a.pins_verified || !a.total || !a.ids ||
       a.total>storage_.id_capacity || next_ticket_==std::numeric_limits<std::uint64_t>::max()) {
        leave();return false;
    }
    for(std::uint32_t i=0;i<a.total;++i)if(a.ids[i]<0) {leave();return false;}
    Binding b{session_,++next_ticket_,0,a.cache_generation,a.holder,a.model,a.wire,0,0,a.slot,a.total};
    identity_writer_.store(true,std::memory_order_seq_cst);
    if(identity_users_.load(std::memory_order_seq_cst)) {identity_writer_.store(false,std::memory_order_seq_cst);leave();return false;}
    std::uint64_t g{};
    if(!lease_.arm(lease_.context,b,g) || !g) {identity_writer_.store(false,std::memory_order_seq_cst);leave();return false;}
    b.lease_generation=g;binding_=immutable_identity_=b;generation_.store(g,std::memory_order_release);
    std::memcpy(storage_.ids,a.ids,a.total*sizeof(std::int32_t));
    request_identity_.store(0,std::memory_order_relaxed);birth_identity_.store(0,std::memory_order_relaxed);
    captured_=chunk_start_=chunk_rows_=tap_mask_=0;stream_=nullptr;chunk_open_=false;
    feature_valid_=true;copy_queued_=fence_recorded_=fence_failed_=fence_complete_=borrowed_=false;
    holder_live_=true;seen_loss_=losses_.load(std::memory_order_acquire);
    state_.store(State::Pending,std::memory_order_release);identity_writer_.store(false,std::memory_order_seq_cst);leave();return true;
}
bool Owner::begin_chunk(std::uint64_t holder,std::uint64_t model,std::uint32_t processed,
                        std::uint32_t count,std::int32_t position,void* stream) noexcept {
    if(!generation_.load(std::memory_order_acquire) || !enter())return false;
    if(state_!=State::Pending || !holder_live_ || binding_.holder!=holder || binding_.model!=model ||
       !lease_.valid(lease_.context,binding_)) {leave();return false;}
    if(chunk_open_ || stream!=nullptr || count==0 || processed!=captured_ || position<0 ||
       static_cast<std::uint32_t>(position)!=processed || processed>binding_.total ||
       count>binding_.total-processed) {invalidate();leave();return false;}
    chunk_start_=processed;chunk_rows_=count;tap_mask_=0;stream_=stream;chunk_open_=true;
    leave();return true;
}
bool Owner::capture_hc(std::uint64_t model,std::uint32_t layer,std::uint32_t rows,
                       const void* source,void* stream) noexcept {
    if(!generation_.load(std::memory_order_acquire) || !enter())return false;
    std::size_t tap=0;while(tap<kNativeLayers.size() && kNativeLayers[tap]!=layer)++tap;
    if(tap==kNativeLayers.size()) {leave();return true;}
    if(state_!=State::Pending || binding_.model!=model) {leave();return true;}
    if(state_!=State::Pending || binding_.model!=model || !chunk_open_ ||
       !lease_.valid(lease_.context,binding_)) {invalidate();leave();return false;}
    const auto bit=std::uint32_t{1}<<tap;
    if(!source || rows!=chunk_rows_ || stream!=stream_ || tap_mask_&bit) {invalidate();leave();return false;}
    tap_mask_|=bit;
    if(!lease_.healthy(lease_.context,binding_))invalidate();
    if(!feature_valid_) {leave();return false;}
    auto* dst=static_cast<std::uint8_t*>(storage_.features)+
        std::size_t{chunk_start_}*kConcatRowBytes+tap*kRowBytes;
    // Conservatively pin storage even if a backend reports partial enqueue failure.
    copy_queued_=true;
    const bool ok=copy_.copy_2d(copy_.context,dst,kConcatRowBytes,source,kRowBytes,
                              kRowBytes,rows,stream);
    if(!ok)invalidate();
    leave();return ok;
}
bool Owner::end_chunk(std::uint64_t holder,std::uint32_t processed,std::int32_t position) noexcept {
    if(!generation_.load(std::memory_order_acquire) || !enter())return false;
    if(state_!=State::Pending || binding_.holder!=holder || !chunk_open_) {invalidate();leave();return false;}
    const auto expected=std::uint64_t{chunk_start_}+chunk_rows_;
    const bool ok=expected==processed && position>=0 && std::uint64_t{static_cast<std::uint32_t>(position)}==expected && tap_mask_==31;
    chunk_open_=false;captured_=processed;
    if(!ok)invalidate();
    leave();return ok;
}
bool Owner::materialize(std::uint64_t holder,std::uint64_t wire,std::int32_t slot,std::uint32_t processed) noexcept {
    if(!generation_.load(std::memory_order_acquire) || !enter())return false;
    if(state_!=State::Pending || binding_.holder!=holder || binding_.wire!=wire || binding_.slot!=slot ||
       processed!=binding_.total || !lease_.valid(lease_.context,binding_)) {leave();return false;}
    if(chunk_open_ || captured_!=binding_.total)invalidate();
    chunk_open_=false;
    if(copy_queued_) {
        fence_recorded_=copy_.record_fence(copy_.context,storage_.fence,stream_);
        if(!fence_recorded_) {fence_failed_=true;invalidate();}
    } else fence_complete_=true;
    if(!lease_.materialize(lease_.context,binding_)) {invalidate();leave();return false;}
    state_.store(State::Materialized,std::memory_order_release);leave();return true;
}
void Owner::holder_destructor(std::uint64_t holder) noexcept {
    if(!generation_.load(std::memory_order_acquire))return;
    if(!enter(false)) {
        if(!pin_identity())return; // A publication writer can only replace an already retired owner.
        const auto state=state_.load(std::memory_order_acquire);
        if(immutable_identity_.holder==holder && state==State::Pending)
            pending_holder_retirement_.store(immutable_identity_.lease_generation,std::memory_order_release);
        else if(immutable_identity_.holder==holder && state==State::Materialized)
            holder_retirement_.store(immutable_identity_.lease_generation,std::memory_order_release);
        unpin_identity();return;
    }
    if(binding_.holder==holder && holder_live_) {
        holder_live_=false;
        if(state_==State::Pending) {
            retire_local();
        }
    }
    leave();
}
bool Owner::transfer(std::uint64_t request,std::uint64_t birth,std::uint64_t model,
                     std::uint64_t wire,std::int32_t slot,std::uint32_t mode,
                     const std::int32_t* ids,std::uint32_t count) noexcept {
    if(!generation_.load(std::memory_order_acquire) || !enter())return false;
    bool match=state_==State::Materialized && request && birth && model==binding_.model &&
        wire==binding_.wire && slot==binding_.slot && mode==1 && count==binding_.total && ids;
    if(match)for(std::uint32_t i=0;i<count;++i)if(ids[i]!=storage_.ids[i]) {match=false;break;}
    if(!match || !lease_.transfer(lease_.context,binding_,request,birth)) {invalidate();leave();return false;}
    binding_.request=request;binding_.birth=birth;
    request_identity_.store(request,std::memory_order_relaxed);birth_identity_.store(birth,std::memory_order_relaxed);
    state_.store(State::Request,std::memory_order_release);
    leave();return true;
}
bool Owner::abandon_materialized(std::uint64_t wire,std::int32_t slot,std::uint32_t mode,
                                 const std::int32_t* ids,std::uint32_t count) noexcept {
    if(!generation_.load(std::memory_order_acquire))return false;
    if(!enter(false)) {
        if(!pin_identity())return false;
        const auto& b=immutable_identity_;
        bool match=state_.load(std::memory_order_acquire)==State::Materialized && b.wire==wire && b.slot==slot &&
            mode==1 && ids && count==b.total;
        if(match)for(std::uint32_t i=0;i<count;++i)if(ids[i]!=storage_.ids[i]) {match=false;break;}
        if(match)materialized_retirement_.store(b.lease_generation,std::memory_order_release);
        unpin_identity();return match;
    }
    bool match=state_==State::Materialized && binding_.wire==wire && binding_.slot==slot && mode==1 &&
        count==binding_.total && ids;
    if(match)for(std::uint32_t i=0;i<count;++i)if(ids[i]!=storage_.ids[i]) {match=false;break;}
    if(match) {
        retire_local(true);
    }
    leave();return match;
}
void Owner::request_destructor(std::uint64_t request) noexcept {
    if(!generation_.load(std::memory_order_acquire))return;
    if(!enter(false)) {
        if(!pin_identity())return;
        if(state_.load(std::memory_order_acquire)==State::Request && request_identity_.load(std::memory_order_relaxed)==request)
            request_retirement_.store(immutable_identity_.lease_generation,std::memory_order_release);
        unpin_identity();return;
    }
    if(state_==State::Request && binding_.request==request) {
        retire_local();
    }
    leave();
}
bool Owner::force_serial(std::uint64_t holder,std::uint64_t model,std::int32_t slot) noexcept {
    if(!generation_.load(std::memory_order_acquire) || !enter())return false;
    const bool result=state_==State::Pending && binding_.holder==holder && binding_.model==model &&
        binding_.slot==slot && lease_.valid(lease_.context,binding_);
    leave();return result;
}
bool Owner::finish_fence() noexcept {
    if(!copy_queued_ || fence_complete_)return true;
    if(!fence_recorded_ || fence_failed_)return false;
    const auto p=copy_.query_fence(copy_.context,storage_.fence);
    if(p==Poll::Failed) {fence_failed_=true;invalidate();return false;}
    if(p==Poll::Complete) {fence_complete_=true;return true;}
    return false;
}
bool Owner::acquire_features(FeatureView& view) noexcept {
    if(!generation_.load(std::memory_order_acquire) || !enter())return false;
    bool ok=state_==State::Request && !borrowed_ && feature_valid_ &&
        lease_.valid(lease_.context,binding_) && lease_.healthy(lease_.context,binding_) && finish_fence();
    drain_retirements();
    ok=ok && state_==State::Request && feature_valid_ && seen_loss_==losses_.load(std::memory_order_acquire);
    if(ok) {view={binding_,storage_.ids,storage_.features,binding_.total,kConcatRowBytes};borrowed_=true;}
    leave();return ok;
}
bool Owner::release_features(std::uint64_t ticket) noexcept {
    if(!generation_.load(std::memory_order_acquire) || !enter())return false;
    const bool ok=borrowed_ && binding_.ticket==ticket;
    if(ok)borrowed_=false;
    leave();return ok;
}
bool Owner::storage_reclaimable() noexcept {
    if(!configured_ || !enter())return !configured_;
    bool ok=(state_==State::Idle || state_==State::Retired) && !retirement_waiting_ && !borrowed_ && finish_fence();
    if(ok) {
        // Close reader admission before checking existing full-ID proofs. A
        // later publish reopens admission only after copying its new identity.
        identity_writer_.store(true,std::memory_order_seq_cst);
        ok=identity_users_.load(std::memory_order_seq_cst)==0;
    }
    leave();return ok;
}
Binding Owner::binding() noexcept {
    if(!configured_ || !enter())return {};
    const auto result=binding_;leave();return result;
}
}
