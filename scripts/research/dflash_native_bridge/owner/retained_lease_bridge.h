#pragma once
#include "pending_owner.h"
#include "native_decode_adapter.h"
#include "../dflash-retained-controller-20261009/retained_controller.h"
namespace halogen0173::dflash::prefill {
class RetainedLeaseBridge final {
public:
    explicit RetainedLeaseBridge(hgn_dflash::Lane& lane) noexcept:lane_(lane) {}
    LeaseOps operations() noexcept {return {this,arm,valid,healthy,materialize,transfer,retire,loss,abandon};}
    RoundSource rounds() noexcept {return {this,current_round};}
private:
    static hgn_dflash::PendingBinding pending(const Binding& b) noexcept {
        return {b.model,b.holder,b.wire,b.cache_generation,b.ticket,b.slot};
    }
    static bool arm(void* ctx,const Binding& b,std::uint64_t& generation) noexcept {
        auto& self=*static_cast<RetainedLeaseBridge*>(ctx);
        generation=hgn_dflash::arm_pending(self.lane_,pending(b));
        if(generation)self.loss_at_arm_=hgn_dflash::atomic_load(self.lane_.loss);
        return generation!=0;
    }
    static bool match(const hgn_dflash::Lane& l,const Binding& b) noexcept {
        const auto phase=hgn_dflash::atomic_load(l.phase);
        return hgn_dflash::atomic_load(l.generation)==b.lease_generation && l.model==b.model && l.slot==b.slot &&
            l.holder==b.holder && l.wire==b.wire && l.cache_generation==b.cache_generation &&
            l.pending_ticket==b.ticket &&
            ((phase==hgn_dflash::u32(hgn_dflash::Phase::Pending) && !b.request && !b.birth) ||
             (phase==hgn_dflash::u32(hgn_dflash::Phase::Request) && l.request==b.request && l.birth==b.birth));
    }
    static bool valid(void* ctx,const Binding& b) noexcept {
        auto& self=*static_cast<RetainedLeaseBridge*>(ctx);hgn_dflash::Lock lock(self.lane_);
        if(!lock.held) {hgn_dflash::mark_loss(self.lane_);return false;}
        return match(self.lane_,b);
    }
    static bool healthy(void* ctx,const Binding& b) noexcept {
        auto& self=*static_cast<RetainedLeaseBridge*>(ctx);hgn_dflash::Lock lock(self.lane_);
        if(!lock.held) {hgn_dflash::mark_loss(self.lane_);return false;}
        return match(self.lane_,b) && hgn_dflash::atomic_load(self.lane_.loss)==self.loss_at_arm_;
    }
    static std::uint64_t current_round(void* ctx,const Binding& b) noexcept {
        auto& self=*static_cast<RetainedLeaseBridge*>(ctx);hgn_dflash::Lock lock(self.lane_);
        if(!lock.held) {hgn_dflash::mark_loss(self.lane_);return 0;}
        return match(self.lane_,b)?hgn_dflash::atomic_load(self.lane_.round):0;
    }
    static bool materialize(void* ctx,const Binding& b) noexcept {
        auto& self=*static_cast<RetainedLeaseBridge*>(ctx);
        return hgn_dflash::materialize_pending(self.lane_,b.lease_generation,b.holder);
    }
    static bool transfer(void* ctx,const Binding& b,std::uint64_t request,std::uint64_t birth) noexcept {
        auto& self=*static_cast<RetainedLeaseBridge*>(ctx);
        return hgn_dflash::transfer_pending(self.lane_,b.lease_generation,pending(b),request,birth);
    }
    static bool retire(void* ctx,const Binding& b) noexcept {
        auto& l=static_cast<RetainedLeaseBridge*>(ctx)->lane_;
        if(!retirement_identity(l,b))return false;
        if(hgn_dflash::atomic_load(l.generation)!=b.lease_generation ||
           hgn_dflash::atomic_load(l.phase)==hgn_dflash::u32(hgn_dflash::Phase::Quarantined))return true;
        if(b.request)return hgn_dflash::retire_request(l,b.lease_generation,b.request,b.birth);
        return hgn_dflash::retire_pending(l,b.lease_generation,b.holder);
    }
    static bool retirement_identity(hgn_dflash::Lane& l,const Binding& b) noexcept {
        hgn_dflash::Lock lock(l);
        if(!lock.held) {hgn_dflash::mark_loss(l);return false;}
        // A later native reset has already disposed of this exact generation;
        // acknowledge the stale record without writing the newer lane.
        const auto generation=hgn_dflash::atomic_load(l.generation);
        if(generation!=b.lease_generation)return generation>b.lease_generation;
        const auto phase=hgn_dflash::atomic_load(l.phase);
        if(phase==hgn_dflash::u32(hgn_dflash::Phase::Quarantined))
            return l.model==b.model && l.slot==b.slot && l.holder==b.holder && l.wire==b.wire &&
                l.cache_generation==b.cache_generation && l.pending_ticket==b.ticket && (!b.request || l.birth==b.birth);
        return match(l,b);
    }
    static void loss(void* ctx,std::uint64_t generation) noexcept {
        auto& l=static_cast<RetainedLeaseBridge*>(ctx)->lane_;
        if(hgn_dflash::atomic_load(l.generation)==generation)hgn_dflash::mark_loss(l);
    }
    static bool abandon(void* ctx,const Binding& b) noexcept {
        auto& l=static_cast<RetainedLeaseBridge*>(ctx)->lane_;
        if(!retirement_identity(l,b))return false;
        if(hgn_dflash::atomic_load(l.generation)!=b.lease_generation ||
           hgn_dflash::atomic_load(l.phase)==hgn_dflash::u32(hgn_dflash::Phase::Quarantined))return true;
        return hgn_dflash::retire_materialized(l,b.lease_generation,pending(b));
    }
    hgn_dflash::Lane& lane_;
    std::uint64_t loss_at_arm_{};
};
}
