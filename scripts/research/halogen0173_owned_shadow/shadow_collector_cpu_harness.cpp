// CPU-only source harness. The task owner builds/runs it; this agent did not.
// Removing dtor retirement, epoch rejection or const native reads breaks these cases.
#include "shadow_collector.h"
#include <cassert>
#include <cstring>
#include <fstream>
#include <vector>
using namespace halogen0173::shadow;
template<class T, std::size_t N> void put(std::array<std::uint8_t,N>& b, std::size_t o, T v) {
    assert(o+sizeof(v)<=N); std::memcpy(b.data()+o,&v,sizeof(v));
}
struct Native {
    static constexpr std::uint64_t kWireRequestId=0x10000004d;
    std::array<std::uint8_t,0xe00> stack{};
    std::array<std::uint8_t,0x308> record{};
    std::array<std::uint8_t,0x2b0> request{};
    std::array<std::uint8_t,0x300> model{};
    std::array<std::int32_t,70> history{};
    Frame frame{};
    Native() {
        auto rp=reinterpret_cast<std::uint64_t>(request.data());
        auto mp=reinterpret_cast<std::uint64_t>(model.data());
        put(record,0,kWireRequestId); put(record,8,std::int32_t{3}); put(record,0x10,rp);
        put(request,0x108,mp); put(request,0x11c,std::int32_t{1});
        put(request,0x19c,std::int32_t{21}); put(request,0x1a0,std::int32_t{22});
        put(request,0x138,std::int32_t{2}); put(request,0x13c,std::int32_t{4});
        put(request,0x228,std::int32_t{256});
        put(model,0x14,std::int32_t{17}); put(model,0x118,std::int32_t{4096});
        put(model,0x2e8,std::int32_t{70}); put(model,0xc8,std::int32_t{3});
        put(request,0x1b8,std::int32_t{4});
        for (int i=0;i<70;++i) history[i]=100+i;
        auto hp=reinterpret_cast<std::uint64_t>(history.data());
        put(request,0x1c0,hp); put(request,0x1c8,hp+280); put(request,0x1d0,hp+280);
        std::memcpy(stack.data()+0xa00,record.data(),record.size()); // birth local record
        put(stack,0x10,rp); put(stack,0x78,reinterpret_cast<std::uint64_t>(record.data()));
        frame.gpr[7]=reinterpret_cast<std::uint64_t>(stack.data());
    }
    void accepted(std::uint64_t attempts, std::uint64_t accepted, std::uint64_t output, std::uint32_t sent) {
        put(request,0,std::uint64_t{1}); put(request,0x68,std::uint64_t{1});
        put(request,0x70,attempts); put(request,0x78,accepted); put(request,0x28,output);
        put(record,0x58,sent);
    }
};
std::vector<Event> drain(Collector& c) { std::vector<Event> v; Event e{}; while(c.drain(e)) v.push_back(e); return v; }
int main(int argc,char** argv) {
    std::array<std::uint8_t,16> session{}; session[0]=1;
    { static Collector disabled; Frame invalid{}; invalid.gpr.fill(1);
      disabled.on_site(Site::SuccessfulBirthA,invalid); assert(drain(disabled).empty()); }
    { static Collector serial; assert(serial.configure(true,session)); Native n;
      put(n.stack,0xa10,std::uint64_t{0});
      serial.on_site(Site::SuccessfulBirthA,n.frame);
      serial.on_site(Site::SuccessfulBirthB,n.frame);
      assert(drain(serial).empty()); serial.disable();
      std::uint64_t dropped{},live{},pending{};
      assert(serial.close_counts(dropped,live,pending) && !dropped && !live && !pending); }
    static Collector c; assert(c.configure(true,session)); Native n;
    c.on_site(Site::SuccessfulBirthA,n.frame);
    c.on_site(Site::BeforeNeuralDepth,n.frame);
    auto stack=n.stack; auto record=n.record; auto request=n.request; auto model=n.model;
    n.accepted(4,2,3,3); request=n.request; record=n.record;
    c.on_site(Site::CommonOutcome,n.frame);
    assert(stack==n.stack && record==n.record && request==n.request && model==n.model);
    auto events=drain(c); assert(events.size()==4);
    const auto& begin=events[2]; const auto& end=events[3];
    assert(begin.kind==Kind::Begin && end.kind==Kind::Outcome && begin.owner_birth==end.owner_birth);
    assert(begin.wire_request_id==Native::kWireRequestId && end.wire_request_id==Native::kWireRequestId);
    assert(begin.context_count==64 && begin.context_total==70 && begin.context_suffix[0]==106);
    assert((end.flags&Continuing) && !(end.flags&PartialOutput));
    assert(end.counters[6]-begin.counters[6]==4 && end.counters[7]-begin.counters[7]==2);
    assert(begin.native_allowance>=4);
    // Optionally export a complete REAL collector birth/begin/outcome/retire.
    n.frame.gpr[5]=reinterpret_cast<std::uint64_t>(n.request.data());
    c.on_site(Site::RequestDestructor,n.frame); auto retirement=drain(c);
    assert(retirement.size()==1 && retirement[0].kind==Kind::Retire);
    if(argc>1) {
        std::ofstream fixture(argv[1],std::ios::binary); assert(fixture);
        auto h=c.header(); fixture.write(reinterpret_cast<const char*>(&h),sizeof(h));
        for(const auto& e:events) fixture.write(reinterpret_cast<const char*>(&e),sizeof(e));
        fixture.write(reinterpret_cast<const char*>(&retirement[0]),sizeof(Event)); assert(fixture);
    }
    c.on_site(Site::SuccessfulBirthA,n.frame); auto rebirth=drain(c);
    auto first_birth=rebirth.back().owner_birth;
    // Record relocation retains Request identity; begin sees the new lexical record.
    auto moved_record=n.record; put(n.stack,0x78,reinterpret_cast<std::uint64_t>(moved_record.data()));
    c.on_site(Site::BeforeNeuralDepth,n.frame); c.on_site(Site::CommonOutcome,n.frame);
    events=drain(c); assert(events.size()==2 && events[0].owner_birth==first_birth);
    // ABA: same native address after destruction receives a distinct birth.
    n.frame.gpr[5]=reinterpret_cast<std::uint64_t>(n.request.data());
    c.on_site(Site::RequestDestructor,n.frame);
    c.on_site(Site::CommonOutcome,n.frame); // no pending outcome can be revived
    c.on_site(Site::SuccessfulBirthB,n.frame);
    events=drain(c); assert(events.back().kind==Kind::SlotAttach && events.back().owner_birth!=first_birth);
    // A slot binding invalidates the in-flight round before outcome.
    put(n.stack,0x78,reinterpret_cast<std::uint64_t>(n.record.data()));
    c.on_site(Site::BeforeNeuralDepth,n.frame);
    n.frame.gpr[5]=reinterpret_cast<std::uint64_t>(n.model.data()); n.frame.gpr[4]=3;
    c.on_site(Site::SlotBind,n.frame); c.on_site(Site::CommonOutcome,n.frame);
    events=drain(c); assert(events.size()==2 && events.back().kind==Kind::SlotInvalidate);
    // Stop after partly transported batch is explicit and not a continuing label.
    n.frame.gpr[5]=reinterpret_cast<std::uint64_t>(n.request.data());
    c.on_site(Site::RequestDestructor,n.frame);
    c.on_site(Site::SuccessfulBirthB,n.frame); c.on_site(Site::BeforeNeuralDepth,n.frame);
    n.accepted(8,4,5,4); n.frame.gpr[0]=1; c.on_site(Site::CommonOutcome,n.frame);
    events=drain(c); assert(events.back().flags&Terminal); assert(events.back().flags&PartialOutput);
    // Overflow preserves explicit cumulative loss and clears in-flight ownership.
    c.on_site(Site::RequestDestructor,n.frame);
    for (std::size_t i=0;i<Collector::kRing;++i) {
        c.on_site(Site::SuccessfulBirthA,n.frame); c.on_site(Site::RequestDestructor,n.frame);
    }
    events=drain(c); assert(events.size()>=Collector::kRing);
    c.on_site(Site::SuccessfulBirthA,n.frame); events=drain(c);
    assert(!events.empty() && events.front().dropped_cumulative>0);
    assert(c.header().record_bytes==512 && sizeof(Event)==512 && sizeof(Header)==128);
}
