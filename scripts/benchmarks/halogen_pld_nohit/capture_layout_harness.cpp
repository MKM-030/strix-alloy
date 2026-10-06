#include "native_capture_layout.h"
#include <algorithm>
#include <cstdio>
#include <limits>

using namespace halogen_nohit;
using namespace halogen_nohit::capture;
namespace {
int failed = 0, checks = 0;
void check(bool result, const char* label) {
    ++checks;
    if (!result) { ++failed; std::printf("FAIL: %s\n", label); }
}
template<std::size_t N> void put(std::array<std::uint8_t, N>& b,
                                 std::size_t offset, std::uint64_t value, std::size_t width) {
    for (std::size_t i=0; i<width; ++i) { b[offset+i]=static_cast<std::uint8_t>(value>>(i*8)); }
}
struct Fixture {
    std::array<std::uint8_t,kRequestBytes> request{};
    std::array<std::uint8_t,kModelBytes> model{};
    std::array<std::uint8_t,kRecordBytes> record{};
    std::array<std::uint8_t,kOuterBytes> outer{};
    std::array<std::int32_t,kMaxWindowTokens> suffix{};
    TokenDefinitions tokens{};
    NoHitCopies copies{};
    Fixture(std::uint64_t length=8192) {
        tokens.id_limit=1000; tokens.defined_bits.fill(0xff);
        copies.request={0x200000,request}; copies.model={0x300000,model};
        copies.record={0x400000,record}; copies.outer={0x500000,outer};
        copies.gpr[Rbp]=copies.request.native_origin;
        copies.gpr[Rsp]=copies.outer.native_origin;
        copies.gpr[R15]=copies.record.native_origin;
        copies.gpr[R9]=3; copies.tokens=&tokens;
        put(request,0xd8,copies.model.native_origin,8);
        put(request,0xec,3,4); put(request,0xf0,3,4); put(request,0x104,2,4);
        put(request,0x15c,611,4); put(request,0x160,612,4); put(request,0x170,3,4);
        put(request,0x178,0x1000000,8); put(request,0x180,0x1000000+length*4,8);
        put(request,0x188,0x1000000+kContextCapacity*4,8); put(request,0x1e0,128,4);
        put(model,0x14,4,4); put(model,0xf0,kContextCapacity,4);
        // Position deliberately differs from prefix length; neither can stand in
        // for the other. Independent expected allowance below is min(3,3,...,127).
        put(model,0x220,length+23,4); model[0x900]=1; model[0x901]=1;
        put(model,0xa0,7,4); put(record,8,7,4); put(record,0x10,copies.request.native_origin,8);
        put(record,0x140,0x2000000,8); put(record,0x148,0x2000020,8); put(record,0x158,8,8);
        put(outer,8,copies.record.native_origin,8);
        put(outer,0x170,copies.record.native_origin,8);
        put(outer,0x178,copies.record.native_origin+kRecordBytes,8);
        const auto count=static_cast<std::size_t>(std::min(length,std::uint64_t{kMaxWindowTokens}));
        for(std::size_t i=0;i<count;++i) { suffix[i]=static_cast<std::int32_t>(100+i); }
        suffix[count-1]=611;
        copies.suffix_native_origin=0x1000000+(length-count)*4;
        copies.suffix=std::span<const std::int32_t>{suffix.data(),count};
    }
    Fixture(const Fixture&)=delete;
};
void expect_reject(Fixture& f, DecodeResult reason, const char* label) {
    NoHitFacts out{}; out.prefix_length=91; out.current_id=77; out.window_ids[510]=89;
    check(decode_nohit(f.copies,out)==reason,label);
    check(out.prefix_length==91 && out.current_id==77 && out.window_ids[510]==89,
          "failure preserves caller facts");
}
}
int main() {
    // These tests catch concrete failures: truncating long prompt length,
    // conflating position with length, treating consumed QWORD as DWORD,
    // wraparound allowance arithmetic, or trusting packet/frame origin labels.
    for(const std::uint64_t length:{8192ULL,16384ULL,131072ULL,260000ULL}) {
        Fixture f(length); NoHitFacts out{};
        check(decode_nohit(f.copies,out)==DecodeResult::Captured,"actual long vector layout captured");
        check(out.prefix_length==length && out.target_position==length+23,
              "independent position and complete long prefix survive");
        check(out.window_count==512 && out.window_origin==length-512 &&
              out.window_ids[0]==100 && out.window_ids[511]==611,"exact owned512 suffix copied");
        check(out.native_allowance==3 && out.opening_gate_eligible && out.no_constraints &&
              out.sufficient_context && out.slot==7 && out.cached_opening_id==612,
              "native independent allowance and opening gates captured");
    }
    {Fixture f(3); NoHitFacts out{}; check(decode_nohit(f.copies,out)==DecodeResult::Captured &&
        out.window_count==3 && out.window_ids[3]==0,"short copied suffix zeros unused slots");}
    {Fixture f; f.copies.request.bytes=f.copies.request.bytes.first(0x1e0);
        expect_reject(f,DecodeResult::MissingCopy,"short request copy rejected");}
    {Fixture f; ++f.copies.gpr[Rbp]; expect_reject(f,DecodeResult::FrameMismatch,"saved actual RBP linked");}
    {Fixture f; put(f.outer,0x178,f.copies.record.native_origin+2*kRecordBytes,8);
        expect_reject(f,DecodeResult::RecordMismatch,"two queued records rejected");}
    {Fixture f; put(f.record,0x158,7,8);
        expect_reject(f,DecodeResult::PrefillIncomplete,"pending prefill tokens rejected");}
    {Fixture f; put(f.record,0x158,0x100000000ULL,8); NoHitFacts out{};
        check(decode_nohit(f.copies,out)==DecodeResult::Captured,"prefill consumed is full QWORD");}
    {Fixture f; put(f.request,0x180,0x1000000+8192*4+1,8);
        expect_reject(f,DecodeResult::VectorInvalid,"unaligned vector end rejected");}
    {Fixture f; ++f.copies.suffix_native_origin;
        expect_reject(f,DecodeResult::VectorInvalid,"suffix source does not match native vector");}
    {Fixture f; f.suffix[511]=612;
        expect_reject(f,DecodeResult::TokenInvalid,"native tail must equal current ID");}
    {Fixture f; f.tokens.defined_bits[100/8]&=static_cast<std::uint8_t>(~(1U<<(100%8)));
        expect_reject(f,DecodeResult::TokenInvalid,"undefined suffix ID rejected");}
    {Fixture f; f.request[0x1e4]=1;
        expect_reject(f,DecodeResult::PhaseReentry,"postseed phase reentry rejected");}
    {Fixture f; put(f.request,0x1e0,0x80000000ULL,4);
        expect_reject(f,DecodeResult::ArithmeticInvalid,"Q minus one overflow rejected");}
    {Fixture f; f.copies.gpr[R9]=2;
        expect_reject(f,DecodeResult::AllowanceMismatch,"actual R9D must match independent B");}
    {Fixture f; put(f.model,0x14,1,4); f.copies.gpr[R9]=0; NoHitFacts out{};
        check(decode_nohit(f.copies,out)==DecodeResult::Captured && out.native_allowance==0,
              "nonpositive allowance remains observed stock gate fact");}
    {Fixture f; put(f.request,0x1e8,0x700000,8); NoHitFacts out{};
        check(decode_nohit(f.copies,out)==DecodeResult::Captured && !out.no_constraints,
              "constraint is observed without granting selection");}
    std::printf("native capture layout: %s (%d failed checks, %d checks)\n",failed?"FAIL":"PASS",failed,checks);
    return failed?1:0;
}
