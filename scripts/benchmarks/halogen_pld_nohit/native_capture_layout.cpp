#include "native_capture_layout.h"
#include <algorithm>
#include <bit>
#include <limits>

namespace halogen_nohit::capture {
namespace {
std::uint64_t u64(std::span<const std::uint8_t> bytes, std::size_t at) noexcept {
    std::uint64_t value=0;
    for(std::size_t i=0;i<8;++i) { value|=std::uint64_t{bytes[at+i]}<<(8*i); }
    return value;
}
std::int32_t i32(std::span<const std::uint8_t> bytes, std::size_t at) noexcept {
    std::uint32_t value=0;
    for(std::size_t i=0;i<4;++i) { value|=std::uint32_t{bytes[at+i]}<<(8*i); }
    return std::bit_cast<std::int32_t>(value);
}
bool complete(const ObjectCopy& c, std::size_t size) noexcept {
    return c.native_origin!=0 && c.bytes.size()>=size &&
        c.native_origin<=std::numeric_limits<std::uint64_t>::max()-size;
}
bool defined(const TokenDefinitions& tokens, std::int32_t id) noexcept {
    if(id<0 || tokens.id_limit==0 || tokens.id_limit>kMaxTokenIds ||
       static_cast<std::uint32_t>(id)>=tokens.id_limit) { return false; }
    const auto value=static_cast<std::uint32_t>(id);
    return (tokens.defined_bits[value/8] & (1U<<(value%8)))!=0;
}
bool signed32(std::int64_t value) noexcept {
    return value>=std::numeric_limits<std::int32_t>::min() &&
           value<=std::numeric_limits<std::int32_t>::max();
}
}

DecodeResult decode_nohit(const NoHitCopies& c, NoHitFacts& out) noexcept {
    if(!complete(c.request,kRequestBytes) || !complete(c.model,kModelBytes) ||
       !complete(c.record,kRecordBytes) || !complete(c.outer,kOuterBytes) || !c.tokens) {
        return DecodeResult::MissingCopy;
    }
    const auto request=c.request.bytes, model=c.model.bytes;
    const auto record=c.record.bytes, outer=c.outer.bytes;
    if(c.gpr[Rbp]!=c.request.native_origin || c.gpr[Rsp]!=c.outer.native_origin ||
       c.gpr[R15]!=c.record.native_origin || u64(request,0xd8)!=c.model.native_origin) {
        return DecodeResult::FrameMismatch;
    }
    const auto queued_begin=u64(outer,0x170), queued_end=u64(outer,0x178);
    if(queued_begin!=c.record.native_origin || queued_end<queued_begin ||
       queued_end-queued_begin!=kRecordBytes || u64(outer,8)!=c.record.native_origin ||
       u64(record,0x10)!=c.request.native_origin || i32(record,8)!=i32(model,0xa0)) {
        return DecodeResult::RecordMismatch;
    }
    const auto prefill_begin=u64(record,0x140), prefill_end=u64(record,0x148);
    if(prefill_end<prefill_begin || (prefill_end-prefill_begin)%4!=0 ||
       (prefill_end-prefill_begin)/4>kContextCapacity ||
       u64(record,0x158)<(prefill_end-prefill_begin)/4) {
        return DecodeResult::PrefillIncomplete;
    }
    const auto begin=u64(request,0x178), end=u64(request,0x180), capacity=u64(request,0x188);
    if(begin==0 || end<begin || capacity<end || begin%4!=0 || end%4!=0 || capacity%4!=0) {
        return DecodeResult::VectorInvalid;
    }
    const auto length=(end-begin)/4;
    if(length==0 || length>kContextCapacity) { return DecodeResult::VectorInvalid; }
    const auto count=static_cast<std::uint32_t>(std::min(length,std::uint64_t{kMaxWindowTokens}));
    // This addition is <=end, already proved ordered; do not scan the full prefix.
    if(c.suffix.size()!=count || c.suffix_native_origin!=end-std::uint64_t{count}*4) {
        return DecodeResult::VectorInvalid;
    }
    const auto current=i32(request,0x15c);
    if(!defined(*c.tokens,current) || c.suffix[count-1]!=current) { return DecodeResult::TokenInvalid; }
    for(const auto token:c.suffix) {
        if(!defined(*c.tokens,token)) { return DecodeResult::TokenInvalid; }
    }
    if(request[0x1e4]!=0) { return DecodeResult::PhaseReentry; }
    const std::int64_t p=i32(model,0x220), capacity_tokens=i32(model,0xf0);
    const std::int64_t width_minus_one=std::int64_t{i32(model,0x14)}-1;
    const std::int64_t remaining=capacity_tokens-p-1;
    const std::int64_t q_minus_one=std::int64_t{i32(request,0x1e0)}-1;
    // Native operations are signed32. Reject a wrapping operand even when a
    // later minimum would mask it, rather than silently changing gate semantics.
    if(p<0 || capacity_tokens<0 || !signed32(width_minus_one) || !signed32(remaining) ||
       !signed32(q_minus_one) || !signed32(p+2)) { return DecodeResult::ArithmeticInvalid; }
    const auto allowance=static_cast<std::int32_t>(std::min({width_minus_one,
        std::int64_t{i32(request,0xf0)},remaining,q_minus_one}));
    const auto saved_b=std::bit_cast<std::int32_t>(static_cast<std::uint32_t>(c.gpr[R9]));
    if(saved_b!=allowance) { return DecodeResult::AllowanceMismatch; }
    NoHitFacts facts{};
    facts.prefix_length=length; facts.window_origin=length-count;
    facts.target_position=static_cast<std::uint64_t>(p); facts.window_count=count;
    for(std::size_t i=0;i<count;++i) { facts.window_ids[i]=c.suffix[i]; }
    facts.current_id=current; facts.slot=i32(record,8); facts.cached_opening_id=i32(request,0x160);
    facts.native_allowance=allowance; facts.positive_pld_policy=i32(request,0xec)>0;
    facts.no_sampler=u64(request,0x150)==0; facts.no_suppression=i32(request,0x1d0)==0;
    const auto width=i32(request,0x170);
    facts.positive_width=width>0;
    facts.sufficient_context=width>0 && length>=static_cast<std::uint32_t>(width);
    facts.no_constraints=u64(request,0x1e8)==0;
    facts.opening_gate_eligible=i32(request,0x104)!=0 && i32(request,0x1dc)==0 &&
        p+2<=capacity_tokens && model[0x900]==1 && model[0x901]==1;
    out=facts;
    return DecodeResult::Captured;
}
} // namespace halogen_nohit::capture
