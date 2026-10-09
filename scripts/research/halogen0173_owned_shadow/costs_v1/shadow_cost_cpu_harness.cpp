// CPU-only source fixture. Build/run belongs to the parent task owner.
// GNU --wrap affects this executable only; production has no injected clock.
#include "shadow_collector.h"
#include <cassert>
#include <cerrno>
#include <cstring>
#include <fstream>
#include <vector>
using namespace halogen0173::shadow;
extern "C" CostStamp __real_hgn_shadow_cost_stamp() noexcept;
static int clock_mode;
static unsigned clock_calls;
extern "C" CostStamp __wrap_hgn_shadow_cost_stamp() noexcept {
    ++clock_calls;
    if(clock_mode==1) return {0,CostClockReadFailed,EIO};
    if(clock_mode==2) return {clock_calls%2?200u:100u,CostClockValid,0};
    if(clock_mode==3) return {0,CostClockInvalidSample,EOVERFLOW};
    return __real_hgn_shadow_cost_stamp();
}
template<class T,std::size_t N> void put(std::array<std::uint8_t,N>& bytes,std::size_t offset,T value) {
    assert(offset+sizeof(value)<=N); std::memcpy(bytes.data()+offset,&value,sizeof(value));
}
struct Native {
    std::array<std::uint8_t,0xe00> stack{};
    std::array<std::uint8_t,0x308> record{};
    std::array<std::uint8_t,0x2b0> request{};
    std::array<std::uint8_t,0x300> model{};
    Frame frame{};
    Native() {
        const auto rq=reinterpret_cast<std::uint64_t>(request.data());
        const auto md=reinterpret_cast<std::uint64_t>(model.data());
        put(record,0,std::uint64_t{0x10000004d}); put(record,8,std::int32_t{3}); put(record,0x10,rq);
        put(request,0x108,md); put(request,0x138,std::int32_t{2}); put(request,0x13c,std::int32_t{2});
        put(request,0x228,std::int32_t{256}); put(model,0x14,std::int32_t{17});
        put(model,0x118,std::int32_t{8192}); put(model,0x2e8,std::int32_t{100});
        std::memcpy(stack.data()+0xa00,record.data(),record.size());
        put(stack,0x10,rq); put(stack,0x78,reinterpret_cast<std::uint64_t>(record.data()));
        frame.gpr[7]=reinterpret_cast<std::uint64_t>(stack.data()); frame.gpr[5]=rq;
    }
    void counters(bool partial=false) {
        put(request,0,std::uint64_t{1}); put(request,0x28,std::uint64_t{2});
        put(request,0x68,std::uint64_t{1}); put(request,0x70,std::uint64_t{2}); put(request,0x78,std::uint64_t{1});
        put(record,0x58,std::uint32_t{partial?1u:2u});
    }
};
struct Copy { Event event; CostEvent cost; };
std::vector<Copy> drain(Collector& c) {
    std::vector<Copy> result; Copy record{};
    while(c.drain(record.event,record.cost)) result.push_back(record);
    return result;
}
void check_match(const Copy& r) {
    assert(r.event.sequence==r.cost.sequence && r.event.kind==r.cost.kind);
    assert(r.event.owner_birth==r.cost.owner_birth && r.event.slot_cookie==r.cost.slot_cookie);
    assert(r.event.slot_epoch==r.cost.slot_epoch && r.event.round==r.cost.round);
    assert(r.event.wire_request_id==r.cost.wire_request_id && r.event.source==r.cost.source);
    assert(r.event.flags==r.cost.native_flags && r.event.dropped_cumulative==r.cost.dropped_cumulative);
}
void round(Collector& c,Native& native,bool partial=false) {
    c.on_site(Site::SuccessfulBirthA,native.frame);
    c.on_site(Site::BeforeNeuralDepth,native.frame);
    native.counters(partial);
    const auto rq=native.request; const auto md=native.model;
    const auto record=native.record; const auto stack=native.stack;
    c.on_site(Site::CommonOutcome,native.frame);
    assert(rq==native.request && md==native.model && record==native.record && stack==native.stack);
    c.on_site(Site::RequestDestructor,native.frame);
}
int main(int argc,char** argv) {
    std::array<std::uint8_t,16> nonce{}; nonce[0]=1;
    { static Collector disabled; Frame bad{}; bad.gpr.fill(1);
      disabled.on_site(Site::BeforeNeuralDepth,bad); assert(drain(disabled).empty()); assert(clock_calls==0); }
    { static Collector untimed; Native n; assert(untimed.configure(true,nonce)); round(untimed,n);
      const auto records=drain(untimed); assert(records.size()==5 && clock_calls==0);
      for(const auto& r:records) assert(static_cast<std::uint32_t>(r.cost.kind)==0); }
    static Collector genuine; assert(genuine.configure(true,nonce,true)); Native n;
    errno=EDOM; round(genuine,n); assert(errno==EDOM && clock_calls==2);
    const auto observed=drain(genuine); assert(observed.size()==5);
    check_match(observed[2]); check_match(observed[3]);
    assert(observed[2].cost.flags==CostClockValid && observed[3].cost.flags==CostClockValid);
    assert(observed[3].cost.raw_ns>=observed[2].cost.raw_ns);
    genuine.disable(); std::uint64_t dropped{},live{},pending{};
    assert(genuine.close_counts(dropped,live,pending) && !dropped && !live && !pending);
    if(argc>2) {
        std::ofstream native(argv[1],std::ios::binary),cost(argv[2],std::ios::binary); assert(native && cost);
        const auto nh=genuine.header(); const auto ch=genuine.cost_header();
        native.write(reinterpret_cast<const char*>(&nh),sizeof(nh)); cost.write(reinterpret_cast<const char*>(&ch),sizeof(ch));
        for(const auto& r:observed) {
            native.write(reinterpret_cast<const char*>(&r.event),sizeof(r.event));
            if(r.event.kind==Kind::Begin || r.event.kind==Kind::Outcome) cost.write(reinterpret_cast<const char*>(&r.cost),sizeof(r.cost));
        }
        assert(native && cost);
    }
    { static Collector failed; Native native; clock_mode=1;
      assert(failed.configure(true,nonce,true)); round(failed,native); const auto records=drain(failed);
      check_match(records[2]); check_match(records[3]);
      assert(records[2].cost.flags==CostClockReadFailed && records[3].cost.flags==CostClockReadFailed);
      assert(!records[2].cost.raw_ns && records[2].cost.error==EIO); }
    { static Collector reversed; Native native; clock_mode=2; clock_calls=0;
      assert(reversed.configure(true,nonce,true)); round(reversed,native); const auto records=drain(reversed);
      assert(records[2].cost.flags==CostClockValid && records[3].cost.flags==(CostClockValid|CostClockReversed)); }
    { static Collector invalid; Native native; clock_mode=3;
      assert(invalid.configure(true,nonce,true)); round(invalid,native); const auto records=drain(invalid);
      assert(records[2].cost.flags==CostClockInvalidSample && records[2].cost.error==EOVERFLOW); }
    { static Collector partial; Native native; clock_mode=0;
      assert(partial.configure(true,nonce,true)); round(partial,native,true); const auto records=drain(partial);
      assert(records[3].event.flags&PartialOutput); check_match(records[3]); }
    { static Collector retired; Native native;
      assert(retired.configure(true,nonce,true)); retired.on_site(Site::SuccessfulBirthA,native.frame);
      retired.on_site(Site::BeforeNeuralDepth,native.frame); retired.on_site(Site::RequestDestructor,native.frame);
      retired.on_site(Site::CommonOutcome,native.frame); const auto records=drain(retired);
      assert(records.size()==4 && records[2].event.kind==Kind::Begin && records[3].event.kind==Kind::Retire); }
    { static Collector overflow; Native native;
      assert(overflow.configure(true,nonce,true));
      for(std::size_t i=0;i<Collector::kRing;++i) { overflow.on_site(Site::SuccessfulBirthA,native.frame); overflow.on_site(Site::RequestDestructor,native.frame); }
      const auto records=drain(overflow); bool lost=false;
      for(const auto& r:records) lost|=r.event.kind==Kind::Gap || r.event.dropped_cumulative>0;
      assert(lost); overflow.on_site(Site::BeforeNeuralDepth,native.frame); assert(drain(overflow).empty()); }
    assert(sizeof(Header)==128 && sizeof(Event)==512 && sizeof(CostHeader)==128 && sizeof(CostEvent)==96);
}
