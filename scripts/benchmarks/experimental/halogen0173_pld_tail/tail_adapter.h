#pragma once

// This component never installs a native hook or starts a producer. The owned
// 0.17.3 collector calls it only at the pinned copied-PLD-hit boundary.
// No standard-library/OS dependency: its CPU tests cannot initialize a device.
namespace halogen0173::tail {
using u8 = __UINT8_TYPE__;
using u32 = __UINT32_TYPE__;
using u64 = __UINT64_TYPE__;
using i32 = __INT32_TYPE__;

enum class Status : u32 {
    Disabled, Ineligible, Unavailable, Stale, Invalid, Unchanged, LostOwner,
    ChangedInput, Applied, Count
};

struct Key {
    u8 session[16]{};
    u8 model_sha256[32]{};
    u8 tokenizer_sha256[32]{};
    u64 owner_birth{}, slot_cookie{}, slot_epoch{}, round{}, wire_request_id{};
    u32 context_total{}, context_count{}, transported_count{};
    i32 model_position{}, current_id{}, native_allowance{};
    u32 width{};
    i32 stock[3]{};
    i32 suffix[64]{};
};

struct Snapshot {
    Key key{};
    // Populated exclusively by the lexical owned collector; the provider cannot
    // use this struct to request another native branch or alter these gates.
    bool owned{}, greedy{}, unconstrained{}, complete{};
};

struct Candidate {
    Key binding{};
    u32 count{};
    i32 ids[3]{};
};
using Provider = bool (*)(void*, const Snapshot&, Candidate&) noexcept;
using Guard = bool (*)(void*) noexcept;

struct Configuration {
    bool enabled{};
    bool exact_native_pins_verified{};
    u8 session[16]{};
    u8 model_sha256[32]{};
    u8 tokenizer_sha256[32]{};
    // Frozen startup-owned bitmap: only defined ordinary target IDs have a bit.
    // It and the provider/context remain alive until every relay is drained.
    const u8* allowed_ids{};
    u32 allowed_id_count{};
    Provider provider{};
    void* provider_context{};
};

template<class T, u32 N> inline bool equal(const T (&a)[N], const T (&b)[N]) noexcept {
    for(u32 i=0; i<N; ++i) if(a[i]!=b[i]) return false;
    return true;
}
template<u32 N> inline bool nonzero(const u8 (&a)[N]) noexcept {
    for(u32 i=0; i<N; ++i) if(a[i]) return true;
    return false;
}
inline bool equal(const Key& a, const Key& b) noexcept {
    return equal(a.session,b.session) && equal(a.model_sha256,b.model_sha256)
        && equal(a.tokenizer_sha256,b.tokenizer_sha256)
        && a.owner_birth==b.owner_birth && a.slot_cookie==b.slot_cookie
        && a.slot_epoch==b.slot_epoch && a.round==b.round
        && a.wire_request_id==b.wire_request_id && a.context_total==b.context_total
        && a.context_count==b.context_count && a.transported_count==b.transported_count
        && a.model_position==b.model_position && a.current_id==b.current_id
        && a.native_allowance==b.native_allowance && a.width==b.width
        && equal(a.stock,b.stock) && equal(a.suffix,b.suffix);
}

class Adapter {
public:
    // Cold startup only. Disabled configuration never inspects the bitmap or
    // provider. The installed collector's close barrier owns shutdown.
    bool configure(const Configuration& cfg) noexcept {
        if(configured_) return false;
        if(cfg.enabled && (!cfg.exact_native_pins_verified || !nonzero(cfg.session)
            || !nonzero(cfg.model_sha256) || !nonzero(cfg.tokenizer_sha256)
            || !cfg.allowed_ids || cfg.allowed_id_count==0 || !cfg.provider)) return false;
        cfg_=cfg; configured_=true; return true;
    }

    void pin_key(Key& key) const noexcept {
        for(u32 i=0;i<16;++i) key.session[i]=cfg_.session[i];
        for(u32 i=0;i<32;++i) {
            key.model_sha256[i]=cfg_.model_sha256[i];
            key.tokenizer_sha256[i]=cfg_.tokenizer_sha256[i];
        }
    }

    Status replace(const Snapshot& s, i32* borrowed_offer, u64 borrowed_count,
                   Guard owner_still_live, void* guard_context) noexcept {
        if(!cfg_.enabled) return note(Status::Disabled);
        const auto& k=s.key;
        if(!s.owned || !s.greedy || !s.unconstrained || !s.complete
            || !k.owner_birth || !k.slot_cookie || !k.slot_epoch || !k.round
            || k.width<2 || k.width>3 || k.context_count==0 || k.context_count>64
            || k.context_count>k.context_total || k.native_allowance<i32(k.width)
            || k.model_position<0 || k.suffix[k.context_count-1]!=k.current_id
            || !borrowed_offer || borrowed_count!=k.width || !owner_still_live
            || !equal(k.session,cfg_.session) || !equal(k.model_sha256,cfg_.model_sha256)
            || !equal(k.tokenizer_sha256,cfg_.tokenizer_sha256)) return note(Status::Ineligible);
        Candidate candidate{};
        // Provider consumes COPIED values only. It must return an already-ready
        // result immediately: no NPU dispatch, waits, native calls or allocation.
        if(!cfg_.provider(cfg_.provider_context,s,candidate)) return note(Status::Unavailable);
        if(!equal(k,candidate.binding)) return note(Status::Stale);
        if(candidate.count!=k.width || candidate.ids[0]!=k.stock[0]) return note(Status::Invalid);
        bool changed=false;
        for(u32 i=0;i<k.width;++i) {
            if(!allowed(candidate.ids[i])) return note(Status::Invalid);
            changed|=candidate.ids[i]!=k.stock[i];
        }
        if(!changed) return note(Status::Unchanged);
        // The collector checks its current owner/slot epoch and loss counter
        // here, after the provider has returned and immediately before mutation.
        if(!owner_still_live(guard_context)) return note(Status::LostOwner);
        for(u32 i=0;i<k.width;++i)
            if(borrowed_offer[i]!=k.stock[i]) return note(Status::ChangedInput);
        // Keep original opening, count, RBX, frame, request and model untouched.
        // No partial mutation can occur on any failure path above.
        for(u32 i=1;i<k.width;++i) borrowed_offer[i]=candidate.ids[i];
        return note(Status::Applied);
    }

    u64 count(Status status) const noexcept { return counts_[u32(status)]; }
    bool enabled() const noexcept { return cfg_.enabled; }
private:
    bool allowed(i32 id) const noexcept {
        return id>=0 && u32(id)<cfg_.allowed_id_count
            && (cfg_.allowed_ids[u32(id)/8] & u8(1u<<(u32(id)%8)));
    }
    Status note(Status status) noexcept { ++counts_[u32(status)]; return status; }
    Configuration cfg_{};
    bool configured_{};
    u64 counts_[u32(Status::Count)]{};
};
} // namespace halogen0173::tail
