#include "owned_transport.h"
using namespace halogen0173::dflash::transport;
using namespace halogen0173::dflash::prefill;
#if defined(TRANSPORT_ORDINARY_CRT)
#include <cstring>
#else
extern "C" void* memcpy(void* d,const void* s,__SIZE_TYPE__ n){auto* x=static_cast<unsigned char*>(d);auto* y=static_cast<const unsigned char*>(s);for(__SIZE_TYPE__ i=0;i<n;++i)x[i]=y[i];return d;}
extern "C" void* memset(void* d,int c,__SIZE_TYPE__ n){auto* x=static_cast<unsigned char*>(d);for(__SIZE_TYPE__ i=0;i<n;++i)x[i]=static_cast<unsigned char>(c);return d;}
extern "C" int memcmp(const void* a,const void* b,__SIZE_TYPE__ n){auto* x=static_cast<const unsigned char*>(a);auto* y=static_cast<const unsigned char*>(b);for(__SIZE_TYPE__ i=0;i<n;++i)if(x[i]!=y[i])return int(x[i])-int(y[i]);return 0;}
#endif
struct Fixture {
    Owner owner;DecodeCapture decode;Exporter exporter;
    bool valid{true},healthy{true},source_done{true},d2h_done{},fail_copy{},fail_record{},fail_query{},drain_ok{},sink_ok{true};
    std::uint64_t generation{},losses{};
    unsigned copies{},queries{},drains{},writes{};
    SinkOps override_sink{};
    bool ack_during_retire{},busy_ack_result{true};
    std::array<std::int32_t,5> ids{11,12,13,14,15},copied_ids{};
    std::array<std::uint16_t,5*kConcatWidth> staging{};
    std::array<std::uint16_t,4*kConcatWidth> host{};
    std::array<std::array<std::uint16_t,4*kConcatWidth>,DecodeCapture::kSlots> decode_staging{};
    std::array<int,DecodeCapture::kSlots> fences{};
    std::array<std::uint16_t,5*kWidth> native{};
    std::array<std::uint8_t,kHeaderBytes> header{};
    std::array<std::uint8_t,16> payload_ids{};
    const void* pending_src{};void* pending_dst{};std::uint32_t pending_rows{};
    std::uint64_t retire_on_copy{};
    static bool arm(void* p,const Binding&,std::uint64_t& g) noexcept {g=++static_cast<Fixture*>(p)->generation;return true;}
    static bool live(void* p,const Binding& b) noexcept {auto& x=*static_cast<Fixture*>(p);return x.valid&&b.lease_generation==x.generation;}
    static bool health(void* p,const Binding& b) noexcept {return live(p,b)&&static_cast<Fixture*>(p)->healthy;}
    static bool yes(void* p,const Binding&) noexcept {auto& x=*static_cast<Fixture*>(p);if(x.ack_during_retire){x.ack_during_retire=false;x.busy_ack_result=x.exporter.acknowledge(x.exporter.active_identity());}return true;}
    static bool transfer(void*,const Binding&,std::uint64_t,std::uint64_t) noexcept {return true;}
    static void loss(void* p,std::uint64_t) noexcept {auto& x=*static_cast<Fixture*>(p);++x.losses;x.healthy=false;}
    static bool source_copy(void*,void* d,std::size_t dp,const void* s,std::size_t sp,std::size_t n,std::size_t rows,void*) noexcept {
        for(std::size_t r=0;r<rows;++r)memcpy(static_cast<char*>(d)+r*dp,static_cast<const char*>(s)+r*sp,n);return true;
    }
    static bool source_record(void*,void*,void*) noexcept {return true;}
    static Poll source_query(void* p,void*) noexcept {return static_cast<Fixture*>(p)->source_done?Poll::Complete:Poll::Pending;}
    LeaseOps lease() noexcept {return {this,arm,live,health,yes,transfer,yes,loss,yes};}
    static bool d2h_copy(void* p,void* d,const void* s,std::uint32_t rows) noexcept {
        auto& x=*static_cast<Fixture*>(p);++x.copies;x.pending_src=s;x.pending_dst=d;x.pending_rows=rows;
        if(x.retire_on_copy)x.owner.request_destructor(x.retire_on_copy);
        return !x.fail_copy;
    }
    static bool d2h_record(void* p) noexcept {return !static_cast<Fixture*>(p)->fail_record;}
    static Poll d2h_query(void* p) noexcept {
        auto& x=*static_cast<Fixture*>(p);++x.queries;if(x.fail_query)return Poll::Failed;
        if(!x.d2h_done)return Poll::Pending;
        memcpy(x.pending_dst,x.pending_src,x.pending_rows*kConcatRowBytes);x.pending_src=nullptr;return Poll::Complete;
    }
    static bool d2h_drain(void* p) noexcept {auto& x=*static_cast<Fixture*>(p);++x.drains;return x.drain_ok;}
    static bool write(void* p,const std::uint8_t* h,std::size_t hn,const std::uint8_t* ids,std::size_t n,const void* data,std::size_t bytes) noexcept {
        auto& x=*static_cast<Fixture*>(p);if(hn!=kHeaderBytes||n>x.payload_ids.size()||bytes>sizeof(x.host))return false;
        ++x.writes;memcpy(x.header.data(),h,hn);memcpy(x.payload_ids.data(),ids,n);
        if(bytes&&data!=x.host.data())return false;return x.sink_ok;
    }
    bool setup(bool enabled=true) noexcept {
        if(!owner.configure(true,{1},{copied_ids.data(),copied_ids.size(),staging.data(),sizeof(staging),this},lease(),{this,source_copy,source_record,source_query}))return false;
        Admission a{100,200,300,9,0,0,1,1,5,ids.data(),true,true,true};
        if(!owner.publish(a)||!owner.begin_chunk(100,200,0,5,0,nullptr))return false;
        for(std::size_t t=0;t<5;++t){for(std::size_t r=0;r<5;++r)for(std::size_t c=0;c<kWidth;++c)native[r*kWidth+c]=std::uint16_t(100*t+10*r+c%10);
            if(!owner.capture_hc(200,kNativeLayers[t],5,native.data(),nullptr))return false;memset(native.data(),255,sizeof(native));}
        if(!owner.end_chunk(100,5,5)||!owner.materialize(100,300,0,5))return false;
        owner.holder_destructor(100);if(!owner.transfer(400,5,200,300,0,1,ids.data(),5))return false;
        std::array<DecodeStorage,DecodeCapture::kSlots> storage{};
        for(std::size_t i=0;i<storage.size();++i)storage[i]={decode_staging[i].data(),sizeof(decode_staging[i]),&fences[i]};
        if(!decode.configure(true,lease(),{this,source_copy,source_record,source_query},storage))return false;
        return exporter.configure(enabled,&owner,&decode,lease(),{host.data(),sizeof(host),4,true},
            {this,d2h_copy,d2h_record,d2h_query,d2h_drain},override_sink.write?override_sink:SinkOps{this,write});
    }
    bool make_decode(DecodeSource source,std::uint64_t round,std::uint32_t count,std::int32_t anchor=5,std::int32_t current=31) noexcept {
        auto b=owner.binding();const std::int32_t input[4]{current,32,33,34};auto rows=source==DecodeSource::Verify?4u:1u;
        if(!decode.begin(b,round,source,anchor,input,rows,std::uint32_t(anchor)))return false;
        for(std::size_t t=0;t<5;++t){for(std::size_t r=0;r<rows;++r)for(std::size_t c=0;c<kWidth;++c)native[r*kWidth+c]=std::uint16_t(1000+100*t+10*r+c%10);
            if(!decode.capture_hc(200,kNativeLayers[t],rows,native.data(),nullptr))return false;memset(native.data(),255,sizeof(native));}
        return decode.forward_returned()&&decode.committed(count,anchor+std::int32_t(count))&&decode.outcome(b,0,99,std::uint32_t(anchor)+count);
    }
};
static Fixture f[13];
static std::uint32_t u32(const std::uint8_t* p){return std::uint32_t(p[0])|(std::uint32_t(p[1])<<8)|(std::uint32_t(p[2])<<16)|(std::uint32_t(p[3])<<24);}
static bool prefill(Fixture& x){if(x.exporter.step()!=Step::Queued)return false;x.d2h_done=true;
    return x.exporter.step()==Step::Sent&&x.exporter.step()==Step::Queued&&x.exporter.step()==Step::Sent&&x.exporter.step()==Step::Acknowledged;}
int main(){
    if(!f[0].setup(false)||f[0].exporter.step()!=Step::Off||f[0].copies)return 1;
    auto& a=f[1];if(!a.setup()||a.exporter.step()!=Step::Queued)return 2;
    auto id=a.exporter.active_identity();if(a.exporter.acknowledge(id)||a.exporter.drained())return 3;
    a.owner.request_destructor(400);if(a.owner.storage_reclaimable()||a.exporter.step()!=Step::Waiting||a.writes)return 4;
    a.d2h_done=true;a.valid=false;
    if(a.exporter.step()!=Step::Sent||a.exporter.step()!=Step::Acknowledged||!a.owner.storage_reclaimable()||!a.exporter.drained())return 5;
    auto& b=f[2];if(!b.setup()||b.exporter.step()!=Step::Queued||b.exporter.step()!=Step::Waiting)return 6;
    b.d2h_done=true;if(b.exporter.step()!=Step::Sent||u32(b.header.data()+168)!=0||u32(b.header.data()+172)!=4)return 7;
    for(std::size_t r=0;r<4;++r)for(std::size_t t=0;t<5;++t)for(std::size_t c=0;c<kWidth;++c)if(b.host[r*kConcatWidth+t*kWidth+c]!=100*t+10*r+c%10)return 8;
    if(b.exporter.acknowledge(b.exporter.active_identity())||b.exporter.step()!=Step::Queued||b.exporter.step()!=Step::Sent)return 9;
    id=b.exporter.active_identity();auto wrong=id;++wrong.binding.ticket;if(b.exporter.acknowledge(wrong))return 10;
    wrong=id;++wrong.binding.lease_generation;if(b.exporter.acknowledge(wrong))return 11;
    wrong=id;++wrong.capture_sequence;if(b.exporter.acknowledge(wrong)||!b.exporter.acknowledge(id))return 12;
    if(b.exporter.step()!=Step::Idle||!b.make_decode(DecodeSource::Verify,7,2)||b.exporter.step()!=Step::Queued)return 13;
    id=b.exporter.active_identity();if(!id.capture_sequence||b.decode.release(id.capture_sequence+1)||b.exporter.acknowledge(id))return 14;
    if(b.exporter.step()!=Step::Sent||u32(b.header.data()+36)!=1||u32(b.header.data()+164)!=2||u32(b.header.data()+172)!=2||u32(b.payload_ids.data())!=31||u32(b.payload_ids.data()+4)!=32)return 15;
    b.decode.retire(id.binding.lease_generation);b.decode.disable_new();if(b.decode.storage_reclaimable())return 16;
    if(b.exporter.step()!=Step::Acknowledged||!b.decode.storage_reclaimable())return 17;
    auto& c=f[3];if(!c.setup()||!prefill(c)||!c.make_decode(DecodeSource::Scalar,9,1)||c.exporter.step()!=Step::Queued||c.exporter.step()!=Step::Sent)return 18;
    if(u32(c.header.data()+36)!=2||u32(c.header.data()+160)!=1||u32(c.header.data()+164)!=1||c.exporter.step()!=Step::Acknowledged)return 19;
    auto& d=f[4];if(!d.setup())return 20;d.fail_query=true;if(d.exporter.step()!=Step::Queued||d.exporter.step()!=Step::Poisoned||d.exporter.drained())return 21;
    d.owner.request_destructor(400);if(d.owner.storage_reclaimable()||d.exporter.recover_failed_copy())return 22;
    d.drain_ok=true;if(!d.exporter.recover_failed_copy()||d.exporter.step()!=Step::Sent||d.exporter.step()!=Step::Acknowledged||!d.owner.storage_reclaimable())return 23;
    auto& e=f[5];if(!e.setup())return 24;e.fail_record=true;if(e.exporter.step()!=Step::Poisoned||e.exporter.drained())return 25;
    auto& g=f[6];if(!g.setup()||g.exporter.step()!=Step::Queued)return 26;id=g.exporter.active_identity();wrong=id;++wrong.capture_sequence;
    if(g.exporter.cancel(wrong)||!g.exporter.cancel(id)||g.exporter.step()!=Step::Waiting||g.exporter.acknowledge(id))return 27;
    g.d2h_done=true;if(g.exporter.step()!=Step::Sent||u32(g.header.data()+32)!=3||g.exporter.step()!=Step::Acknowledged||g.exporter.step()!=Step::Stopped)return 28;
    auto& h=f[7];if(!h.setup())return 29;h.source_done=false;if(h.exporter.step()!=Step::Idle||h.copies)return 30;
    h.source_done=true;if(h.exporter.step()!=Step::Queued)return 31;h.sink_ok=false;h.d2h_done=true;
    if(h.exporter.step()!=Step::Stopped||h.exporter.step()!=Step::Acknowledged||h.exporter.step()!=Step::Stopped)return 32;
    auto& j=f[8];if(!j.setup())return 33;j.fail_copy=true;if(j.exporter.step()!=Step::Poisoned||j.exporter.drained())return 34;
    auto& k=f[9];if(!k.setup()||k.exporter.step()!=Step::Queued)return 35;k.exporter.disable_new();k.d2h_done=true;
    if(k.exporter.step()!=Step::Sent||k.exporter.step()!=Step::Queued||k.exporter.step()!=Step::Sent||k.exporter.step()!=Step::Acknowledged||k.exporter.step()!=Step::Stopped)return 36;
    auto& l=f[10];if(!l.setup()||l.exporter.step()!=Step::Queued)return 37;l.d2h_done=true;
    if(l.exporter.step()!=Step::Sent||l.exporter.step()!=Step::Queued||l.exporter.step()!=Step::Sent)return 38;
    l.ack_during_retire=true;l.owner.request_destructor(400);
    if(l.busy_ack_result||l.exporter.drained()||l.owner.storage_reclaimable())return 39;
    if(l.exporter.step()!=Step::Sent||l.exporter.step()!=Step::Acknowledged||!l.owner.storage_reclaimable())return 40;
    auto& m=f[11];if(!m.setup()||!prefill(m))return 41;
    auto terminal=m.owner.binding();auto foreign=terminal;++foreign.wire;
    if(m.exporter.retire(foreign)||!m.exporter.retire(terminal)||m.exporter.step()!=Step::Sent||u32(m.header.data()+32)!=3||m.exporter.step()!=Step::Stopped||!m.exporter.drained())return 42;
    auto& n=f[12];if(!n.setup()||n.exporter.step()!=Step::Queued)return 43;n.d2h_done=true;
    if(n.exporter.step()!=Step::Sent||n.exporter.step()!=Step::Queued||n.exporter.step()!=Step::Sent)return 44;
    id=n.exporter.active_identity();n.valid=false;
    if(n.exporter.acknowledge(id)||n.exporter.drained()||!n.losses)return 45;
    n.owner.request_destructor(400);if(n.owner.storage_reclaimable())return 46;
    if(n.exporter.step()!=Step::Sent||u32(n.header.data()+32)!=3||n.exporter.step()!=Step::Acknowledged||n.exporter.step()!=Step::Stopped||!n.owner.storage_reclaimable())return 47;
    return 0;
}
