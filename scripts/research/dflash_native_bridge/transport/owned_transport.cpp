#include "owned_transport.h"
namespace halogen0173::dflash::transport {
namespace {
bool same(const source::Binding& a,const source::Binding& b) noexcept {
    return a.session==b.session&&a.ticket==b.ticket&&a.lease_generation==b.lease_generation&&
        a.cache_generation==b.cache_generation&&a.holder==b.holder&&a.model==b.model&&a.wire==b.wire&&
        a.request==b.request&&a.birth==b.birth&&a.slot==b.slot&&a.total==b.total;
}
bool admitted(const source::Binding& b) noexcept {
    return b.ticket&&b.lease_generation&&b.cache_generation&&b.holder&&b.model&&b.wire&&b.request&&b.birth&&b.slot>=0&&b.total&&b.total<=262140;
}
void le32(std::uint8_t* p,std::uint32_t n) noexcept {for(unsigned i=0;i<4;++i)p[i]=std::uint8_t(n>>(8*i));}
void le64(std::uint8_t* p,std::uint64_t n) noexcept {for(unsigned i=0;i<8;++i)p[i]=std::uint8_t(n>>(8*i));}
constexpr auto crc_table() noexcept {
    std::array<std::uint32_t,256> out{};for(std::uint32_t i=0;i<256;++i){auto c=i;for(unsigned j=0;j<8;++j)c=(c>>1)^((c&1)?0xedb88320u:0);out[i]=c;}return out;
}
constexpr auto table=crc_table();
std::uint32_t crc(std::uint32_t c,const void* data,std::size_t bytes) noexcept {
    auto* p=static_cast<const std::uint8_t*>(data);for(std::size_t i=0;i<bytes;++i)c=table[(c^p[i])&255]^(c>>8);return c;
}
}
bool Exporter::configure(bool enable,source::Owner* owner,source::DecodeCapture* decode,source::LeaseOps lease,HostChunk host,D2HOps d2h,SinkOps sink) noexcept {
    if(configured_)return false;
    if(!enable)return true;
    if(!owner||!decode||!lease.valid||!lease.healthy||!lease.loss||!host.pinned||!host.features||
       host.rows<4||host.rows>kMaxChunkRows||host.bytes<std::size_t(host.rows)*source::kConcatRowBytes||
       !d2h.enqueue||!d2h.record||!d2h.query||!d2h.drain||!sink.write)return false;
    owner_=owner;decode_=decode;lease_=lease;host_=host;d2h_=d2h;sink_=sink;configured_=enabled_=true;return true;
}
bool Exporter::live() noexcept {return lease_.valid(lease_.context,binding_)&&lease_.healthy(lease_.context,binding_);}
void Exporter::fail() noexcept {
    aborted_=true;enabled_=false;
    if(!sink_failed_)ready_ack_=false;
    if(!loss_notified_){loss_notified_=true;lease_.loss(lease_.context,binding_.lease_generation);}
}
bool Exporter::equal(const Identity& i) const noexcept {return borrowed_&&sequence_==i.capture_sequence&&same(binding_,i.binding);}
bool Exporter::acquire() noexcept {
    source::FeatureView prefill{};source::DecodeView decoded{};
    if(!same(owner_->binding(),last_prefill_)) {
        if(!owner_->acquire_features(prefill))return false;
        input_=Input::Prefill;binding_=prefill.binding;staging_=prefill.bf16_concat;prefill_ids_=prefill.ids;
        sequence_=round_=0;rows_=verified_=prefill.rows;anchor_=0;next_current_=-1;
        borrowed_=true;
        if(!admitted(binding_)||!prefill.ids||!staging_||rows_!=binding_.total||prefill.row_bytes!=source::kConcatRowBytes)fail();
    } else if(decode_->acquire(decoded)) {
        input_=decoded.source==source::DecodeSource::Verify?Input::Verify:Input::Scalar;
        binding_=decoded.binding;staging_=decoded.bf16_concat;decode_ids_=decoded.ids;
        sequence_=decoded.capture_sequence;round_=decoded.round;rows_=decoded.committed_rows;verified_=decoded.verified_rows;
        anchor_=decoded.anchor;next_current_=decoded.next_current;borrowed_=true;
        if(!admitted(binding_)||!same(binding_,last_prefill_)||!staging_||!sequence_||!round_||anchor_<0||
           (decoded.source!=source::DecodeSource::Verify&&decoded.source!=source::DecodeSource::Scalar)||
           next_current_<0||std::uint32_t(next_current_)>=kMaskId||decoded.row_bytes!=source::kConcatRowBytes||
           !rows_||rows_>4||verified_!=(input_==Input::Verify?4u:1u)||rows_>verified_)fail();
    } else return false;
    offset_=chunk_rows_=0;in_flight_=ready_ack_=poisoned_=abort_emitted_=sink_failed_=false;
    return true;
}
bool Exporter::enqueue() noexcept {
    chunk_rows_=rows_-offset_;if(chunk_rows_>host_.rows)chunk_rows_=host_.rows;
    for(std::uint32_t r=0;r<chunk_rows_;++r){const auto id=input_==Input::Prefill?prefill_ids_[offset_+r]:decode_ids_[offset_+r];
        if(id<0||std::uint32_t(id)>=kMaskId){fail();return false;}le32(id_bytes_.data()+r*4,std::uint32_t(id));}
    auto* src=static_cast<const std::uint8_t*>(staging_)+std::size_t(offset_)*source::kConcatRowBytes;
    in_flight_=true;
    const bool copied=d2h_.enqueue(d2h_.context,host_.features,src,chunk_rows_);
    // Always try to order a fence after an enqueue attempt, including failures.
    const bool recorded=d2h_.record(d2h_.context);
    if(!copied||!recorded){fail();poisoned_=true;return false;}return true;
}
bool Exporter::emit(bool abort) noexcept {
    if(sink_failed_)return false;
    if(packet_sequence_==~std::uint64_t{0}){sink_failed_=true;fail();return false;}
    std::array<std::uint8_t,kHeaderBytes> h{};const std::uint8_t magic[8]={'H','G','N','D','T','H','0','1'};
    for(unsigned i=0;i<8;++i)h[i]=magic[i];
    const auto count=abort?0u:chunk_rows_;
    const auto feature_bytes=std::size_t(count)*source::kConcatRowBytes,id_bytes=std::size_t(count)*4;
    le32(h.data()+8,1);le32(h.data()+12,kHeaderBytes);le64(h.data()+16,id_bytes+feature_bytes);
    le64(h.data()+24,++packet_sequence_);le32(h.data()+32,abort?3u:1u);le32(h.data()+36,std::uint32_t(input_));
    le32(h.data()+40,!abort&&offset_+count==rows_?1u:0u);
    for(unsigned i=0;i<16;++i)h[48+i]=binding_.session[i];
    le64(h.data()+64,binding_.ticket);le64(h.data()+72,binding_.lease_generation);le64(h.data()+80,binding_.cache_generation);
    le64(h.data()+88,binding_.holder);le64(h.data()+96,binding_.model);le64(h.data()+104,binding_.wire);
    le64(h.data()+112,binding_.request);le64(h.data()+120,binding_.birth);le32(h.data()+128,std::uint32_t(binding_.slot));
    le32(h.data()+132,binding_.total);le64(h.data()+136,sequence_);le64(h.data()+144,round_);
    le32(h.data()+152,std::uint32_t(anchor_));le32(h.data()+156,std::uint32_t(next_current_));
    le32(h.data()+160,verified_);le32(h.data()+164,rows_);le32(h.data()+168,offset_);le32(h.data()+172,count);
    le32(h.data()+176,source::kConcatWidth);le32(h.data()+180,source::kConcatRowBytes);
    for(unsigned i=0;i<5;++i)le32(h.data()+184+4*i,source::kNativeLayers[i]);le32(h.data()+204,1);
    auto c=crc(~std::uint32_t{0},id_bytes_.data(),id_bytes);c=crc(c,host_.features,feature_bytes);
    le32(h.data()+208,~c);le32(h.data()+212,~crc(~std::uint32_t{0},h.data(),h.size()));
    if(!sink_.write(sink_.context,h.data(),h.size(),id_bytes_.data(),id_bytes,host_.features,feature_bytes)) {
        sink_failed_=true;fail();ready_ack_=true;return false;
    }
    if(abort){abort_emitted_=ready_ack_=true;}else {offset_+=count;ready_ack_=offset_==rows_;}
    return true;
}
Step Exporter::step() noexcept {
    if(!configured_)return Step::Off;
    if(terminal_pending_){terminal_pending_=false;return emit(true)?Step::Sent:Step::Stopped;}
    if(!borrowed_){if(!enabled_)return Step::Stopped;if(!acquire())return Step::Idle;}
    if(ready_ack_) {
        if(!aborted_&&!live())fail();
        else return acknowledge(active_identity())?Step::Acknowledged:Step::Waiting;
    }
    if(poisoned_)return Step::Poisoned;
    if(in_flight_){const auto p=d2h_.query(d2h_.context);
        if(p==source::Poll::Pending)return Step::Waiting;
        if(p==source::Poll::Failed){fail();poisoned_=true;return Step::Poisoned;}
        in_flight_=false;
        if(!aborted_&&!live())fail();
        return emit(aborted_)?Step::Sent:Step::Stopped;
    }
    if(!aborted_&&!live())fail();
    if(aborted_)return emit(true)?Step::Sent:Step::Stopped;
    if(enqueue())return Step::Queued;
    if(poisoned_)return Step::Poisoned;
    return emit(true)?Step::Sent:Step::Stopped;
}
bool Exporter::acknowledge(const Identity& i) noexcept {
    if(!equal(i)||!ready_ack_||in_flight_||poisoned_)return false;
    if(!aborted_&&!live()){fail();return false;}
    const bool ok=input_==Input::Prefill?owner_->release_features(binding_.ticket):decode_->release(sequence_);
    // Contention leaves the exact copied identity and borrow intact for retry.
    if(!ok)return false;
    if(input_==Input::Prefill&&!aborted_)last_prefill_=binding_;
    borrowed_=ready_ack_=false;staging_=nullptr;prefill_ids_=nullptr;return true;
}
bool Exporter::cancel(const Identity& i) noexcept {
    if(!equal(i))return false;fail();return true;
}
bool Exporter::retire(const source::Binding& b) noexcept {
    if(!configured_||!admitted(b))return false;
    if(borrowed_){if(!same(binding_,b))return false;fail();return true;}
    if(!same(last_prefill_,b)||sink_failed_||terminal_pending_||abort_emitted_)return false;
    binding_=b;sequence_=round_=0;rows_=verified_=b.total;offset_=chunk_rows_=0;input_=Input::Prefill;
    anchor_=0;next_current_=-1;fail();terminal_pending_=true;return true;
}
bool Exporter::recover_failed_copy() noexcept {
    if(!borrowed_||!poisoned_||!in_flight_||!d2h_.drain(d2h_.context))return false;
    in_flight_=poisoned_=false;return true;
}

bool HipD2H::configure(bool enable,HipFunctions f,int success,int not_ready,std::uint32_t rows,Exporter* owner) noexcept {
    if(configured_||host_||event_||stream_)return false;
    if(!enable)return true;
    if(!owner||rows<4||rows>kMaxChunkRows||success==not_ready||!f.host_malloc||!f.host_free||!f.stream_create||!f.stream_destroy||
       !f.stream_synchronize||!f.event_create||!f.event_destroy||!f.memcpy_2d_async||!f.event_record||!f.event_query)return false;
    f_=f;success_=success;not_ready_=not_ready;rows_=rows;owner_=owner;
    if(f_.host_malloc(&host_,std::size_t(rows)*source::kConcatRowBytes,0)!=success_||!host_||
       f_.stream_create(&stream_,1)!=success_||!stream_||f_.event_create(&event_,2)!=success_||!event_) {
        dispose();return false;
    }
    configured_=true;return true;
}
HostChunk HipD2H::host_chunk() const noexcept {return {host_,std::size_t(rows_)*source::kConcatRowBytes,rows_,configured_};}
D2HOps HipD2H::operations() noexcept {return {this,enqueue,record,query,drain};}
bool HipD2H::enqueue(void* p,void* dst,const void* src,std::uint32_t rows) noexcept {
    auto& x=*static_cast<HipD2H*>(p);if(!x.configured_||x.queued_||dst!=x.host_||!src||!rows||rows>x.rows_)return false;
    x.queued_=true;x.recorded_=false;
    return x.f_.memcpy_2d_async(dst,source::kConcatRowBytes,src,source::kConcatRowBytes,source::kConcatRowBytes,rows,2,x.stream_)==x.success_;
}
bool HipD2H::record(void* p) noexcept {
    auto& x=*static_cast<HipD2H*>(p);if(!x.configured_||!x.queued_)return false;
    x.recorded_=x.f_.event_record(x.event_,x.stream_)==x.success_;return x.recorded_;
}
source::Poll HipD2H::query(void* p) noexcept {
    auto& x=*static_cast<HipD2H*>(p);if(!x.configured_||!x.queued_||!x.recorded_)return source::Poll::Failed;
    const auto status=x.f_.event_query(x.event_);
    if(status==x.not_ready_)return source::Poll::Pending;
    if(status!=x.success_)return source::Poll::Failed;
    x.queued_=x.recorded_=false;return source::Poll::Complete;
}
bool HipD2H::drain(void* p) noexcept {
    auto& x=*static_cast<HipD2H*>(p);if(!x.configured_||x.f_.stream_synchronize(x.stream_)!=x.success_)return false;
    x.queued_=x.recorded_=false;return true;
}
bool HipD2H::dispose() noexcept {
    if(queued_)return false;
    if(event_){if(f_.event_destroy(event_)!=success_)return false;event_=nullptr;}
    if(stream_){if(f_.stream_destroy(stream_)!=success_)return false;stream_=nullptr;}
    if(host_){if(f_.host_free(host_)!=success_)return false;host_=nullptr;}
    configured_=false;return true;
}
bool HipD2H::close(const Exporter& x) noexcept {return &x==owner_&&x.stopped()&&x.drained()&&dispose();}
}
