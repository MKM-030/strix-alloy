#include "decode_capture.h"
#include <limits>
namespace halogen0173::dflash::prefill {
namespace {
bool equal_owner(const Binding& a,const Binding& b) noexcept {
    return a.session==b.session && a.ticket==b.ticket && a.lease_generation==b.lease_generation &&
        a.cache_generation==b.cache_generation && a.holder==b.holder && a.model==b.model &&
        a.wire==b.wire && a.request==b.request && a.birth==b.birth && a.slot==b.slot;
}
}
bool DecodeCapture::configure(bool enable,LeaseOps lease,CopyOps copy,const std::array<DecodeStorage,kSlots>& storage) noexcept {
    if(configured_)return false;
    if(!enable)return true;
    if(!lease.valid || !lease.healthy || !lease.loss || !copy.copy_2d || !copy.record_fence || !copy.query_fence)return false;
    for(const auto& s:storage)if(!s.features || !s.fence || s.bytes<4*kConcatRowBytes ||
        reinterpret_cast<std::uintptr_t>(s.features)>std::numeric_limits<std::uintptr_t>::max()-s.bytes)return false;
    for(std::size_t i=0;i<kSlots;++i)for(std::size_t j=0;j<i;++j) {
        const auto a=reinterpret_cast<std::uintptr_t>(storage[i].features),b=reinterpret_cast<std::uintptr_t>(storage[j].features);
        if(storage[i].fence==storage[j].fence || (a<b+storage[j].bytes && b<a+storage[i].bytes))return false;
    }
    for(std::size_t i=0;i<kSlots;++i)slots_[i].storage=storage[i];
    lease_=lease;copy_=copy;configured_=true;enabled_.store(true,std::memory_order_release);return true;
}
bool DecodeCapture::enter(bool contention_loss) noexcept {
    if(busy_.test_and_set(std::memory_order_acquire)) {if(contention_loss)source_loss();return false;}
    drain_retirements();
    return true;
}
void DecodeCapture::leave() noexcept {drain_retirements();busy_.clear(std::memory_order_release);}
void DecodeCapture::finish_admission() noexcept {
    const auto word=admission_generation_.exchange(0,std::memory_order_acq_rel);
    if(word&kRetired) {
        const auto g=word&~kRetired;retired_generation_=g;
        auto expected=g;generation_.compare_exchange_strong(expected,word,std::memory_order_acq_rel);
    }
}
void DecodeCapture::drain_retirements() noexcept {
    const auto current=generation_.load(std::memory_order_acquire);
    if(current&kRetired) {retired_generation_=current&~kRetired;active_=kSlots;}
    for(std::size_t i=0;i<kSlots;++i) {
        const auto word=slot_generation_[i].load(std::memory_order_acquire);
        auto& s=slots_[i];
        const bool tagged=(word&kRetired) && s.view.binding.lease_generation==(word&~kRetired);
        const bool current_retired=(current&kRetired) && s.view.binding.lease_generation==(current&~kRetired);
        if(!s.occupied || (!tagged && !current_retired))continue;
        s.valid=false;
        if(!s.done) {
            if(s.queued && !s.recorded) {
                s.recorded=copy_.record_fence(copy_.context,s.storage.fence,nullptr);s.fence_failed=!s.recorded;
            }
            s.done=true;
        }
        if(active_==i)active_=kSlots;
    }
}
void DecodeCapture::source_loss() noexcept {
    losses_.fetch_add(1,std::memory_order_acq_rel);
    const auto g=generation_.load(std::memory_order_acquire)&~kRetired;
    if(g && lease_.loss)lease_.loss(lease_.context,g);
}
void DecodeCapture::invalidate(Slot& s) noexcept {s.valid=false;source_loss();}
bool DecodeCapture::begin(const Binding& b,std::uint64_t round,DecodeSource source,std::int32_t anchor,
                          const std::int32_t* ids,std::uint32_t rows,std::uint32_t transported) noexcept {
    if(!enabled_.load(std::memory_order_acquire) || !enter())return false;
    if(active_!=kSlots || count_==kSlots || slots_[write_].occupied) {source_loss();leave();return false;}
    if(!b.request || !b.birth || !b.lease_generation || b.lease_generation>=kRetired ||
       b.lease_generation==retired_generation_ || !b.ticket || !b.model || !round || anchor<0 ||
       !ids || rows!=(source==DecodeSource::Verify?4u:1u)) {leave();return false;}
    admission_generation_.store(b.lease_generation,std::memory_order_release);
    if(!lease_.valid(lease_.context,b) || !lease_.healthy(lease_.context,b) ||
       (admission_generation_.load(std::memory_order_acquire)&kRetired) ||
       generation_.load(std::memory_order_acquire)==(b.lease_generation|kRetired)) {
        finish_admission();leave();return false;
    }
    if(((generation_.load(std::memory_order_relaxed)&~kRetired)==b.lease_generation && round<=last_round_) ||
       sequence_==std::numeric_limits<std::uint64_t>::max()) {source_loss();finish_admission();leave();return false;}
    for(std::uint32_t i=0;i<rows;++i)if(ids[i]<0) {source_loss();finish_admission();leave();return false;}
    auto& s=slots_[write_];const auto storage=s.storage;s=Slot{};s.storage=storage;
    s.view.binding=b;s.view.capture_sequence=++sequence_;s.view.round=round;s.view.source=source;
    s.view.anchor=anchor;s.view.verified_rows=rows;s.view.bf16_concat=storage.features;
    for(std::uint32_t i=0;i<rows;++i)s.view.ids[i]=ids[i];
    s.transported_before=transported;s.loss=losses_.load(std::memory_order_acquire);s.valid=s.occupied=true;
    if((generation_.load(std::memory_order_relaxed)&~kRetired)!=b.lease_generation)
        generation_.store(b.lease_generation,std::memory_order_release);
    slot_generation_[write_].store(b.lease_generation,std::memory_order_release);last_round_=round;
    active_=write_;write_=(write_+1)%kSlots;++count_;finish_admission();leave();return true;
}
bool DecodeCapture::capture_hc(std::uint64_t model,std::uint32_t layer,std::uint32_t rows,const void* src,void* stream) noexcept {
    if(!configured_ || !enter())return false;
    std::size_t tap=0;while(tap<5 && kNativeLayers[tap]!=layer)++tap;
    if(active_==kSlots || tap==5) {leave();return true;}
    auto& s=slots_[active_];
    if(model!=s.view.binding.model) {leave();return true;}
    const auto bit=std::uint32_t{1}<<tap;
    if(!src || stream || rows!=s.view.verified_rows || s.returned || (s.mask&bit)) {invalidate(s);leave();return false;}
    s.mask|=bit;
    if(!s.valid || s.loss!=losses_.load(std::memory_order_acquire) || !lease_.healthy(lease_.context,s.view.binding)) {
        invalidate(s);leave();return false;
    }
    s.queued=true;auto* dst=static_cast<std::uint8_t*>(s.storage.features)+tap*kRowBytes;
    const bool ok=copy_.copy_2d(copy_.context,dst,kConcatRowBytes,src,kRowBytes,kRowBytes,rows,nullptr);
    if(!ok)invalidate(s);
    leave();return ok;
}
bool DecodeCapture::forward_returned() noexcept {
    if(!configured_ || !enter())return false;
    if(active_==kSlots) {leave();return false;}
    auto& s=slots_[active_];
    if(s.returned || s.mask!=31)invalidate(s);
    s.returned=true;
    if(s.queued) {
        s.recorded=copy_.record_fence(copy_.context,s.storage.fence,nullptr);
        if(!s.recorded) {s.fence_failed=true;invalidate(s);}
    } else s.complete=true;
    const bool ok=s.valid;leave();return ok;
}
bool DecodeCapture::committed(std::uint32_t k,std::int32_t position) noexcept {
    if(!configured_ || !enter())return false;
    if(active_==kSlots) {leave();return false;}
    auto& s=slots_[active_];
    const auto expected=std::int64_t{s.view.anchor}+k;
    const bool ok=s.returned && !s.committed && k>0 && k<=s.view.verified_rows &&
        (s.view.source==DecodeSource::Verify || k==1) && expected==position;
    if(ok) {s.view.committed_rows=k;s.committed=true;} else invalidate(s);
    leave();return ok;
}
bool DecodeCapture::outcome(const Binding& b,std::int32_t status,std::int32_t current,std::uint32_t transported) noexcept {
    if(!configured_ || !enter())return false;
    if(active_==kSlots) {leave();return false;}
    auto& s=slots_[active_];
    const bool emitted=std::uint64_t{s.transported_before}+s.view.committed_rows==transported;
    const bool ok=s.valid && equal_owner(s.view.binding,b) && s.returned && s.committed &&
        status==0 && current>=0 && emitted && s.loss==losses_.load(std::memory_order_acquire) &&
        lease_.valid(lease_.context,b) && lease_.healthy(lease_.context,b);
    if(!ok)invalidate(s);
    s.view.next_current=current;s.done=true;
    // Discard all speculative suffix IDs, even though independent staging keeps
    // the verified rows until its fence completes. Provider sees first k only.
    for(std::uint32_t i=s.view.committed_rows;i<4;++i)s.view.ids[i]=0;
    active_=kSlots;leave();return ok;
}
bool DecodeCapture::fence_complete(Slot& s) noexcept {
    if(!s.queued || s.complete)return true;
    if(!s.recorded || s.fence_failed)return false;
    const auto p=copy_.query_fence(copy_.context,s.storage.fence);
    if(p==Poll::Failed) {s.fence_failed=true;invalidate(s);return false;}
    if(p==Poll::Complete) {s.complete=true;return true;}
    return false;
}
void DecodeCapture::clear_front() noexcept {
    slot_generation_[read_].store(0,std::memory_order_release);
    auto& s=slots_[read_];const auto storage=s.storage;s=Slot{};s.storage=storage;
    read_=(read_+1)%kSlots;--count_;
}
bool DecodeCapture::acquire(DecodeView& view) noexcept {
    if(!configured_ || !enter())return false;
    for(std::size_t i=0;i<kSlots && count_;++i) {
        auto& s=slots_[read_];
        if(!s.done || s.borrowed || !fence_complete(s)) {leave();return false;}
        drain_retirements();
        if(s.loss!=losses_.load(std::memory_order_acquire) || !lease_.valid(lease_.context,s.view.binding) ||
           !lease_.healthy(lease_.context,s.view.binding))s.valid=false;
        drain_retirements();
        if(!s.valid) {clear_front();continue;}
        view=s.view;s.borrowed=true;leave();return true;
    }
    leave();return false;
}
bool DecodeCapture::release(std::uint64_t sequence) noexcept {
    if(!configured_ || !enter())return false;
    const bool ok=count_ && slots_[read_].borrowed && slots_[read_].view.capture_sequence==sequence;
    if(ok)clear_front();
    leave();return ok;
}
void DecodeCapture::retire(std::uint64_t generation) noexcept {
    if(!configured_ || !generation || generation>=kRetired)return;
    for(auto& word:slot_generation_) {
        auto expected=generation;
        word.compare_exchange_strong(expected,generation|kRetired,std::memory_order_acq_rel);
    }
    auto expected=generation;
    // Tag tentative admission first. If it already cleared, successful begin
    // has published generation_ and the following CAS catches the handoff.
    admission_generation_.compare_exchange_strong(expected,generation|kRetired,std::memory_order_acq_rel);
    expected=generation;
    generation_.compare_exchange_strong(expected,generation|kRetired,std::memory_order_acq_rel);
    if(enter(false))leave();
}
bool DecodeCapture::storage_reclaimable() noexcept {
    if(!configured_ || !enter())return !configured_;
    bool ok=!enabled_.load(std::memory_order_acquire) && active_==kSlots;
    for(auto& s:slots_)if(s.occupied)ok=ok && !s.valid && !s.borrowed && s.done && fence_complete(s);
    leave();return ok;
}
}
