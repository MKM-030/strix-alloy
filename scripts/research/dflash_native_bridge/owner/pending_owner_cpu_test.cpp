#include "pending_owner.h"
#include "native_adapter.h"
#include "hip_copy_backend.h"
#include "decode_capture.h"
#include "retained_lease_bridge.h"
#include <cassert>
#include <cstring>
#include <iostream>
#include <vector>
using namespace halogen0173::dflash::prefill;
struct Backend {
    std::uint64_t generation{},armed{},transferred{},retired{},lost{};
    bool valid{true},done{},fail_copy{},fail_record{},fail_query{};
    unsigned copies{};
    void* callback_context{};
    void (*on_copy)(void*) noexcept{},(*on_live)(void*) noexcept{},(*on_query)(void*) noexcept{},(*on_loss)(void*) noexcept{};
    static void fire(void (*&callback)(void*) noexcept,void* context) noexcept {
        const auto fn=callback;callback=nullptr;if(fn)fn(context);
    }
    static bool arm(void* p,const Binding&,std::uint64_t& g) noexcept {
        auto& b=*static_cast<Backend*>(p);g=++b.generation;++b.armed;return b.valid;
    }
    static bool live(void* p,const Binding& b) noexcept {
        auto& x=*static_cast<Backend*>(p);fire(x.on_live,x.callback_context);return x.valid&&b.lease_generation==x.generation;
    }
    static bool materialize(void* p,const Binding& b) noexcept { return live(p,b); }
    static bool transfer(void* p,const Binding& b,std::uint64_t,std::uint64_t) noexcept {
        auto& x=*static_cast<Backend*>(p);if(!live(p,b))return false;++x.transferred;return true;
    }
    static bool retire(void* p,const Binding&) noexcept {++static_cast<Backend*>(p)->retired;return true;}
    static void loss(void* p,std::uint64_t) noexcept {auto& b=*static_cast<Backend*>(p);++b.lost;fire(b.on_loss,b.callback_context);}
    static bool copy(void* p,void* d,std::size_t dp,const void* s,std::size_t sp,
                     std::size_t n,std::size_t rows,void* stream) noexcept {
        auto& b=*static_cast<Backend*>(p);assert(stream==nullptr);if(b.fail_copy)return false;
        ++b.copies;fire(b.on_copy,b.callback_context);for(std::size_t r=0;r<rows;++r)std::memcpy(static_cast<char*>(d)+r*dp,static_cast<const char*>(s)+r*sp,n);return true;
    }
    static bool record(void* p,void*,void* stream) noexcept {assert(!stream);return !static_cast<Backend*>(p)->fail_record;}
    static Poll query(void* p,void*) noexcept {auto& b=*static_cast<Backend*>(p);fire(b.on_query,b.callback_context);return b.fail_query?Poll::Failed:b.done?Poll::Complete:Poll::Pending;}
};
struct Fixture {
    Backend backend;
    std::vector<std::uint16_t> features=std::vector<std::uint16_t>(8*kConcatWidth);
    std::array<std::int32_t,8> copied{};
    std::array<std::int32_t,4> input{11,12,13,14};
    Owner owner;
    std::array<std::uint8_t,16> session{1};
    Admission admission{100,200,300,9,0,0,1,1,4,input.data(),true,true,true};
    bool configure(bool enable=true) {
        return owner.configure(enable,session,{copied.data(),copied.size(),features.data(),features.size()*2,&backend},
            {&backend,Backend::arm,Backend::live,Backend::live,Backend::materialize,Backend::transfer,Backend::retire,Backend::loss,Backend::retire},
            {&backend,Backend::copy,Backend::record,Backend::query});
    }
    void chunk(std::uint32_t first,std::uint32_t rows) {
        assert(owner.begin_chunk(100,200,first,rows,static_cast<std::int32_t>(first),nullptr));
        std::vector<std::uint16_t> hc(rows*kWidth);
        for(std::size_t t=0;t<5;++t) {
            for(std::uint32_t r=0;r<rows;++r)for(std::size_t c=0;c<kWidth;++c)
                hc[r*kWidth+c]=static_cast<std::uint16_t>(1000*t+100*(first+r)+c%100);
            assert(owner.capture_hc(200,kNativeLayers[t],rows,hc.data(),nullptr));
            // Native storage is immediately reused; independent concat must survive.
            std::fill(hc.begin(),hc.end(),65535);
        }
        assert(owner.end_chunk(100,first+rows,static_cast<std::int32_t>(first+rows)));
    }
    void complete() {
        chunk(0,2);chunk(2,2);
        assert(owner.materialize(100,300,0,4));
        owner.holder_destructor(100);
        assert(owner.state()==State::Materialized);
        assert(owner.transfer(400,5,200,300,0,1,input.data(),4));
    }
};
struct DecodeFixture {
    Fixture owner_fixture;
    DecodeCapture capture;
    std::array<std::vector<std::uint16_t>,DecodeCapture::kSlots> buffers;
    std::array<int,DecodeCapture::kSlots> fences{};
    std::array<DecodeStorage,DecodeCapture::kSlots> storage{};
    DecodeFixture() {
        assert(owner_fixture.configure());assert(owner_fixture.owner.publish(owner_fixture.admission));owner_fixture.complete();
        for(std::size_t i=0;i<buffers.size();++i) {buffers[i].resize(4*kConcatWidth);storage[i]={buffers[i].data(),buffers[i].size()*2,&fences[i]};}
        auto& b=owner_fixture.backend;
        assert(capture.configure(true,{&b,Backend::arm,Backend::live,Backend::live,Backend::materialize,Backend::transfer,Backend::retire,Backend::loss},
            {&b,Backend::copy,Backend::record,Backend::query},storage));
    }
    Binding binding() {return owner_fixture.owner.binding();}
    void taps(std::uint32_t rows) {
        std::vector<std::uint16_t> hc(rows*kWidth);
        for(std::size_t t=0;t<5;++t) {
            for(std::uint32_t r=0;r<rows;++r)std::fill(hc.begin()+r*kWidth,hc.begin()+(r+1)*kWidth,static_cast<std::uint16_t>(100*t+r));
            assert(capture.capture_hc(200,kNativeLayers[t],rows,hc.data(),nullptr));std::fill(hc.begin(),hc.end(),65535);
        }
        assert(capture.forward_returned());
    }
};
struct RetainedFixture:Fixture {
    hgn_dflash::Lane lane;
    RetainedLeaseBridge bridge{lane};
    RetainedFixture() {
        assert(hgn_dflash::pin_lane(lane,200,0));
        assert(owner.configure(true,session,{copied.data(),copied.size(),features.data(),features.size()*2,&backend},
            bridge.operations(),{&backend,Backend::copy,Backend::record,Backend::query}));
        assert(owner.publish(admission));
        assert(hgn_dflash::full_reset_complete(lane,hgn_dflash::atomic_load(lane.generation),200,0,true,true)==hgn_dflash::ResetResult::FreshPending);
    }
};
template<class T>void store(void* p,std::size_t off,T v) {std::memcpy(static_cast<char*>(p)+off,&v,sizeof(v));}
template<class T>T load(void* p,std::size_t off) {T v;std::memcpy(&v,static_cast<char*>(p)+off,sizeof(v));return v;}
bool admit(void*,std::uint64_t,std::uint64_t,std::uint64_t,std::int32_t,std::uint64_t& cache) noexcept {cache=9;return true;}
std::uint64_t round_source(void* p,const Binding&) noexcept {return *static_cast<std::uint64_t*>(p);}
std::size_t hip_calls{};
int hip_copy(void* dst,std::size_t dp,const void* src,std::size_t sp,std::size_t bytes,std::size_t rows,int kind,void* stream) {
    assert(kind==3&&!stream&&bytes==kRowBytes&&dp==kConcatRowBytes&&sp==kRowBytes);++hip_calls;
    for(std::size_t r=0;r<rows;++r)std::memcpy(static_cast<char*>(dst)+r*dp,static_cast<const char*>(src)+r*sp,bytes);
    return 0;
}
int hip_record(void*,void* stream) {assert(!stream);++hip_calls;return 0;}
int hip_query(void*) {++hip_calls;return 600;}
int main() {
    unsigned cases=0;
    { Fixture f; assert(f.configure(false));auto bad=f.admission;bad.ids=reinterpret_cast<const std::int32_t*>(1);
      assert(!f.owner.publish(bad));assert(f.backend.armed==0);++cases; }
    { Fixture f;assert(f.configure());auto a=f.admission;
      a.actual_cache_null=false;assert(!f.owner.publish(a));a=f.admission;a.slot_count=2;assert(!f.owner.publish(a));
      a=f.admission;a.generation_mode=0;assert(!f.owner.publish(a));a=f.admission;a.total=9;assert(!f.owner.publish(a));
      assert(f.backend.armed==0);++cases; }
    { Fixture f;assert(f.configure());assert(f.owner.publish(f.admission));assert(f.backend.armed==1);
      f.input[0]=99;assert(f.copied[0]==11);f.input[0]=11;f.complete();
      assert(f.backend.retired==0&&f.backend.transferred==1);FeatureView v;
      assert(!f.owner.acquire_features(v));f.backend.done=true;assert(f.owner.acquire_features(v));
      assert(v.binding.ticket==1&&v.binding.request==400&&v.binding.birth==5&&v.rows==4);
      for(std::size_t r=0;r<4;++r)for(std::size_t t=0;t<5;++t)for(std::size_t c=0;c<kWidth;++c)
          assert(f.features[r*kConcatWidth+t*kWidth+c]==1000*t+100*r+c%100);
      assert(!f.owner.acquire_features(v));f.owner.request_destructor(400);assert(!f.owner.storage_reclaimable());
      assert(!f.owner.release_features(2));assert(f.owner.release_features(1));assert(f.owner.storage_reclaimable());++cases; }
    { Fixture f;assert(f.configure());assert(f.owner.publish(f.admission));f.chunk(0,2);
      f.owner.holder_destructor(100);assert(f.owner.state()==State::Retired&&f.backend.retired==1);
      assert(!f.owner.storage_reclaimable());f.backend.done=true;assert(f.owner.storage_reclaimable());++cases; }
    { Fixture f;assert(f.configure());assert(f.owner.publish(f.admission));f.chunk(0,2);f.chunk(2,2);
      assert(f.owner.materialize(100,300,0,4));auto wrong=f.input;wrong[3]=99;
      assert(!f.owner.transfer(400,5,200,300,0,1,wrong.data(),4));assert(f.backend.transferred==0);++cases; }
    { Fixture f;assert(f.configure());assert(f.owner.publish(f.admission));f.chunk(0,2);f.chunk(2,2);
      assert(f.owner.materialize(100,300,0,4));f.owner.holder_destructor(100);
      assert(f.owner.abandon_materialized(300,0,1,f.input.data(),4));assert(f.owner.state()==State::Retired);
      assert(!f.owner.transfer(400,5,200,300,0,1,f.input.data(),4));assert(f.backend.retired==1);
      f.backend.done=true;assert(f.owner.storage_reclaimable());++cases; }
    { Fixture f;assert(f.configure());assert(f.owner.publish(f.admission));f.complete();f.backend.done=true;
      f.owner.source_loss();FeatureView v;assert(!f.owner.acquire_features(v));assert(f.backend.lost>0);++cases; }
    { Fixture f;assert(f.configure());assert(f.owner.publish(f.admission));
      assert(!f.owner.begin_chunk(100,200,1,2,1,nullptr));f.owner.holder_destructor(100);++cases; }
    { Fixture f;assert(f.configure());assert(f.owner.publish(f.admission));
      assert(f.owner.begin_chunk(100,200,0,4,0,nullptr));std::vector<std::uint16_t> hc(4*kWidth,7);
      assert(f.owner.capture_hc(200,4,4,hc.data(),nullptr));assert(!f.owner.capture_hc(200,4,4,hc.data(),nullptr));
      assert(!f.owner.end_chunk(100,4,4));assert(f.owner.materialize(100,300,0,4));
      assert(f.owner.transfer(400,5,200,300,0,1,f.input.data(),4));f.backend.done=true;FeatureView v;
      assert(!f.owner.acquire_features(v));++cases; }
    { Fixture f;assert(f.configure());assert(f.owner.publish(f.admission));f.backend.fail_copy=true;
      assert(f.owner.begin_chunk(100,200,0,4,0,nullptr));std::vector<std::uint16_t> hc(4*kWidth,7);
      assert(!f.owner.capture_hc(200,4,4,hc.data(),nullptr));f.backend.fail_record=true;f.owner.holder_destructor(100);
      f.backend.done=true;assert(!f.owner.storage_reclaimable());++cases; }
    { Fixture f;assert(f.configure());assert(f.owner.publish(f.admission));f.complete();f.backend.fail_query=true;
      FeatureView v;assert(!f.owner.acquire_features(v));f.owner.request_destructor(400);assert(!f.owner.storage_reclaimable());++cases; }
    { Fixture f;assert(f.configure());assert(f.owner.publish(f.admission));assert(f.owner.force_serial(100,200,0));
      f.owner.disable_new();assert(f.owner.force_serial(100,200,0));f.owner.holder_destructor(100);
      assert(!f.owner.publish(f.admission));++cases; }
    { Fixture f;assert(f.configure());assert(f.owner.publish(f.admission));f.complete();f.backend.done=true;
      f.owner.request_destructor(400);assert(f.owner.publish(f.admission));assert(f.owner.binding().ticket==2);
      assert(f.owner.binding().lease_generation==2);assert(!f.owner.transfer(400,5,200,300,0,1,f.input.data(),4));++cases; }
    { NativeAdapter off;Frame garbage;garbage.gpr.fill(1);assert(off.configure(false,nullptr,{}));
      off.on_site(Site::PendingPublication,garbage);off.on_hc(garbage);++cases; }
    { Fixture f;assert(f.configure());
      std::array<std::uint8_t,0xc00> model{};std::array<std::uint8_t,0x490> holder{};
      std::array<std::uint8_t,0x1100> stack{};std::array<std::uint8_t,0x300> request{};
      std::array<std::uint64_t,3> aggregate{reinterpret_cast<std::uint64_t>(model.data()),0,0};
      const auto hp=reinterpret_cast<std::uint64_t>(holder.data()),mp=aggregate[0];
      store(stack.data(),8,reinterpret_cast<std::uint64_t>(aggregate.data()));store(stack.data(),0x88,hp);
      store(holder.data(),0,std::uint64_t{300});store(holder.data(),0xc,std::uint32_t{1});
      store(holder.data(),0x38,reinterpret_cast<std::uint64_t>(f.input.data()));
      store(holder.data(),0x40,reinterpret_cast<std::uint64_t>(f.input.data()+4));
      store(holder.data(),0x48,reinterpret_cast<std::uint64_t>(f.input.data()+4));store(holder.data(),0x54,std::int32_t{4});
      NativeAdapter adapter;assert(adapter.configure(true,&f.owner,{nullptr,admit,mp,true}));Frame frame;
      frame.gpr[7]=reinterpret_cast<std::uint64_t>(stack.data());adapter.on_site(Site::PendingPublication,frame);
      assert(f.owner.state()==State::Pending);store(model.data(),0xb7d,std::uint8_t{1});
      adapter.on_site(Site::InitialFlagJoin,frame);assert(load<std::uint8_t>(model.data(),0xb7d)==0);
      assert(load<std::int32_t>(model.data(),0x40)==-1);
      frame.gpr[14]=hp;frame.gpr[15]=reinterpret_cast<std::uint64_t>(aggregate.data());
      store(model.data(),0xb7d,std::uint8_t{1});adapter.on_site(Site::ChunkFlagJoin,frame);
      assert(load<std::uint8_t>(model.data(),0xb7d)==0);
      frame.gpr[5]=mp;frame.gpr[4]=reinterpret_cast<std::uint64_t>(f.input.data());frame.gpr[13]=4;frame.gpr[3]=4;
      adapter.on_site(Site::ChunkForward,frame);std::vector<std::uint16_t> hc(4*kWidth,123);
      store(model.data(),0x948,reinterpret_cast<std::uint64_t>(hc.data()));Frame hc_frame;
      hc_frame.gpr[14]=mp;hc_frame.gpr[6]=4;
      for(auto tap:kNativeLayers) {hc_frame.gpr[1]=tap;adapter.on_hc(hc_frame);}
      store(model.data(),0x2e8,std::int32_t{4});adapter.on_site(Site::ChunkForwardReturned,frame);
      store(holder.data(),0x410,std::int32_t{4});frame.gpr[4]=hp;adapter.on_site(Site::RecordMaterialize,frame);
      frame.gpr[5]=hp;adapter.on_site(Site::PendingDestructor,frame);assert(f.owner.state()==State::Materialized);
      std::memcpy(stack.data()+0xa00,holder.data(),0x60);store(request.data(),0x108,mp);
      store(stack.data(),0xa10,reinterpret_cast<std::uint64_t>(request.data()));adapter.on_site(Site::SuccessfulBirthB,frame);
      assert(f.owner.state()==State::Request);assert(f.owner.binding().birth==1);assert(f.backend.copies==5);
      f.backend.done=true;FeatureView view;assert(f.owner.acquire_features(view));assert(f.owner.release_features(view.binding.ticket));++cases;
      DecodeCapture decode;std::array<std::vector<std::uint16_t>,8> device;std::array<int,8> events{};std::array<DecodeStorage,8> decode_storage{};
      for(std::size_t i=0;i<8;++i) {device[i].resize(4*kConcatWidth);decode_storage[i]={device[i].data(),device[i].size()*2,&events[i]};}
      auto& back=f.backend;
      assert(decode.configure(true,{&back,Backend::arm,Backend::live,Backend::live,Backend::materialize,Backend::transfer,Backend::retire,Backend::loss},
          {&back,Backend::copy,Backend::record,Backend::query},decode_storage));
      std::uint64_t shared_round=93;NativeDecodeAdapter decode_adapter;assert(decode_adapter.configure(true,&f.owner,&decode,{&shared_round,round_source},true));
      std::array<std::uint8_t,0x100> record{};std::memcpy(record.data(),stack.data()+0xa00,0x60);
      store(stack.data(),0x78,reinterpret_cast<std::uint64_t>(record.data()));store(stack.data(),0x10,reinterpret_cast<std::uint64_t>(request.data()));
      std::array<std::int32_t,4> verify_inputs{15,16,17,18};store(request.data(),0x19c,std::int32_t{15});
      frame.gpr[5]=mp;frame.gpr[4]=reinterpret_cast<std::uint64_t>(verify_inputs.data());frame.gpr[3]=4;
      decode_adapter.on_site(DecodeSite::VerifyBegin,frame);
      for(auto tap:kNativeLayers) {hc_frame.gpr[1]=tap;decode_adapter.on_hc(hc_frame);}
      decode_adapter.on_site(DecodeSite::VerifyReturned,frame);frame.gpr[4]=2;decode_adapter.on_site(DecodeSite::CommitBegin,frame);
      store(model.data(),0x2e8,std::int32_t{6});decode_adapter.on_site(DecodeSite::CommitReturned,frame);
      store(request.data(),0x19c,std::int32_t{19});store(record.data(),0x58,std::uint32_t{2});frame.gpr[0]=0;
      decode_adapter.on_site(DecodeSite::CommonOutcome,frame);DecodeView dv;assert(decode.acquire(dv));
      assert(dv.round==93&&dv.anchor==4&&dv.committed_rows==2&&dv.ids[0]==15&&dv.ids[1]==16&&dv.next_current==19);
      assert(decode.release(dv.capture_sequence));++cases;
      shared_round=94;frame.gpr[4]=reinterpret_cast<std::uint64_t>(request.data()+0x19c);frame.gpr[3]=1;
      decode_adapter.on_site(DecodeSite::ScalarBegin,frame);hc_frame.gpr[6]=1;
      for(auto tap:kNativeLayers) {hc_frame.gpr[1]=tap;decode_adapter.on_hc(hc_frame);}
      store(model.data(),0x2e8,std::int32_t{7});decode_adapter.on_site(DecodeSite::ScalarReturned,frame);
      store(request.data(),0x19c,std::int32_t{20});store(record.data(),0x58,std::uint32_t{3});
      decode_adapter.on_site(DecodeSite::CommonOutcome,frame);assert(decode.acquire(dv));
      assert(dv.round==94&&dv.anchor==6&&dv.committed_rows==1&&dv.ids[0]==19&&dv.next_current==20);
      assert(decode.release(dv.capture_sequence));++cases; }
    { HipCopyBackend h;assert(!h.operations().copy_2d);
      assert(h.configure({hip_copy,hip_record,hip_query},0,600));auto op=h.operations();
      std::vector<std::uint16_t> src(kWidth,2),dst(kConcatWidth);assert(op.copy_2d(op.context,dst.data(),kConcatRowBytes,src.data(),kRowBytes,kRowBytes,1,nullptr));
      assert(op.record_fence(op.context,&h,nullptr));assert(op.query_fence(op.context,&h)==Poll::Pending);assert(hip_calls==3);++cases; }
    for(std::uint32_t k=1;k<=4;++k) {
        DecodeFixture f;const auto b=f.binding();const std::array<std::int32_t,4> input{9,10,11,12};
        assert(f.capture.begin(b,71,DecodeSource::Verify,20,input.data(),4,6));f.taps(4);
        assert(f.capture.committed(k,20+static_cast<std::int32_t>(k)));assert(f.capture.outcome(b,0,77,6+k));
        DecodeView view;assert(!f.capture.acquire(view));f.owner_fixture.backend.done=true;assert(f.capture.acquire(view));
        assert(view.round==71&&view.anchor==20&&view.verified_rows==4&&view.committed_rows==k&&view.next_current==77);
        for(std::uint32_t i=0;i<4;++i)assert(view.ids[i]==(i<k?input[i]:0));
        auto* rows=static_cast<const std::uint16_t*>(view.bf16_concat);
        for(std::uint32_t r=0;r<k;++r)for(std::size_t t=0;t<5;++t)assert(rows[r*kConcatWidth+t*kWidth]==100*t+r);
        assert(!f.capture.release(view.capture_sequence+1));assert(f.capture.release(view.capture_sequence));++cases;
    }
    { DecodeFixture f;const auto b=f.binding();const std::int32_t id=80;
      assert(f.capture.begin(b,5,DecodeSource::Scalar,20,&id,1,0));f.taps(1);assert(f.capture.committed(1,21));
      assert(f.capture.outcome(b,0,81,1));f.owner_fixture.backend.done=true;DecodeView view;assert(f.capture.acquire(view));
      assert(view.source==DecodeSource::Scalar&&view.ids[0]==80&&view.next_current==81&&view.committed_rows==1);
      assert(f.capture.release(view.capture_sequence));++cases; }
    { DecodeFixture f;const auto b=f.binding();const std::array<std::int32_t,4> input{1,2,3,4};
      assert(f.capture.begin(b,1,DecodeSource::Verify,20,input.data(),4,0));f.taps(4);assert(f.capture.committed(3,23));
      assert(!f.capture.outcome(b,0,8,2));f.owner_fixture.backend.done=true;DecodeView view;assert(!f.capture.acquire(view));++cases; }
    { DecodeFixture f;const auto b=f.binding();const std::int32_t id=1;
      assert(f.capture.begin(b,1,DecodeSource::Scalar,20,&id,1,0));f.taps(1);assert(f.capture.committed(1,21));
      assert(!f.capture.outcome(b,1,8,1));f.owner_fixture.backend.done=true;DecodeView view;assert(!f.capture.acquire(view));++cases; }
    { DecodeFixture f;const auto b=f.binding();const std::int32_t id=1;
      for(std::uint64_t r=1;r<=8;++r) {assert(f.capture.begin(b,r,DecodeSource::Scalar,static_cast<std::int32_t>(r),&id,1,0));f.taps(1);
        assert(f.capture.committed(1,static_cast<std::int32_t>(r+1)));assert(f.capture.outcome(b,0,8,1));}
      assert(!f.capture.begin(b,9,DecodeSource::Scalar,9,&id,1,0));assert(f.owner_fixture.backend.lost>0);
      f.owner_fixture.backend.done=true;DecodeView view;assert(!f.capture.acquire(view));++cases; }
    { DecodeFixture f;const auto b=f.binding();const std::int32_t id=1;
      assert(f.capture.begin(b,1,DecodeSource::Scalar,20,&id,1,0));f.owner_fixture.backend.fail_record=true;
      std::vector<std::uint16_t> hc(kWidth);for(auto t:kNativeLayers)assert(f.capture.capture_hc(200,t,1,hc.data(),nullptr));
      assert(!f.capture.forward_returned());assert(f.capture.committed(1,21));assert(!f.capture.outcome(b,0,8,1));
      f.owner_fixture.backend.done=true;f.capture.disable_new();assert(!f.capture.storage_reclaimable());++cases; }
    { Fixture f;hgn_dflash::Lane lane;assert(hgn_dflash::pin_lane(lane,200,0));RetainedLeaseBridge bridge(lane);
      assert(f.owner.configure(true,f.session,{f.copied.data(),8,f.features.data(),f.features.size()*2,&f.backend},bridge.operations(),
          {&f.backend,Backend::copy,Backend::record,Backend::query}));
      assert(f.owner.publish(f.admission));auto binding=f.owner.binding();assert(lane.generation==binding.lease_generation);
      assert(hgn_dflash::full_reset_complete(lane,lane.generation,200,0,true,true)==hgn_dflash::ResetResult::FreshPending);
      f.complete();assert(lane.phase==hgn_dflash::u32(hgn_dflash::Phase::Request));
      hgn_dflash::atomic_store(lane.round,hgn_dflash::u64{91});assert(bridge.rounds().current(bridge.rounds().context,f.owner.binding())==91);
      f.backend.done=true;FeatureView view;assert(f.owner.acquire_features(view));assert(f.owner.release_features(view.binding.ticket));
      hgn_dflash::mark_loss(lane);assert(!f.owner.acquire_features(view));f.owner.request_destructor(400);
      assert(lane.phase==hgn_dflash::u32(hgn_dflash::Phase::Quarantined));++cases; }
    { Fixture f;assert(f.configure());assert(f.owner.publish(f.admission));
      assert(f.owner.begin_chunk(100,200,0,4,0,nullptr));std::vector<std::uint16_t> hc(4*kWidth,7);
      f.backend.callback_context=&f.owner;f.backend.on_copy=[](void* p) noexcept {static_cast<Owner*>(p)->holder_destructor(100);};
      assert(f.owner.capture_hc(200,4,4,hc.data(),nullptr));
      assert(f.owner.state()==State::Retired&&f.backend.retired==1);assert(!f.owner.storage_reclaimable());
      f.backend.done=true;assert(f.owner.storage_reclaimable());++cases; }
    { Fixture f;assert(f.configure());assert(f.owner.publish(f.admission));f.chunk(0,2);f.chunk(2,2);
      assert(f.owner.materialize(100,300,0,4));f.backend.callback_context=&f.owner;
      f.backend.on_live=[](void* p) noexcept {static_cast<Owner*>(p)->holder_destructor(100);};
      assert(f.owner.transfer(400,5,200,300,0,1,f.input.data(),4));
      assert(f.owner.state()==State::Request&&f.backend.retired==0&&f.backend.lost==0);
      f.backend.done=true;FeatureView view;assert(f.owner.acquire_features(view));assert(f.owner.release_features(view.binding.ticket));++cases; }
    { Fixture f;assert(f.configure());assert(f.owner.publish(f.admission));f.chunk(0,2);f.chunk(2,2);
      assert(f.owner.materialize(100,300,0,4));f.backend.callback_context=&f;
      f.backend.on_live=[](void* p) noexcept {auto& x=*static_cast<Fixture*>(p);
          assert(x.owner.abandon_materialized(300,0,1,x.input.data(),4));x.input.fill(-1);};
      assert(f.owner.transfer(400,5,200,300,0,1,f.input.data(),4));
      assert(f.owner.state()==State::Retired&&f.backend.retired==1);f.backend.done=true;assert(f.owner.storage_reclaimable());++cases; }
    { Fixture f;assert(f.configure());assert(f.owner.publish(f.admission));f.complete();f.backend.done=true;
      f.backend.callback_context=&f.owner;f.backend.on_query=[](void* p) noexcept {static_cast<Owner*>(p)->request_destructor(400);};
      FeatureView view;assert(!f.owner.acquire_features(view));assert(f.owner.state()==State::Retired&&f.backend.retired==1);
      assert(f.owner.storage_reclaimable());++cases; }
    { DecodeFixture f;auto b=f.binding();const std::int32_t id=1;
      assert(f.capture.begin(b,1,DecodeSource::Scalar,20,&id,1,0));f.owner_fixture.backend.callback_context=&f;
      f.owner_fixture.backend.on_copy=[](void* p) noexcept {auto& x=*static_cast<DecodeFixture*>(p);x.capture.retire(x.binding().lease_generation);};
      std::vector<std::uint16_t> hc(kWidth,7);assert(f.capture.capture_hc(200,4,1,hc.data(),nullptr));
      f.capture.disable_new();assert(!f.capture.storage_reclaimable());f.owner_fixture.backend.done=true;
      assert(f.capture.storage_reclaimable());DecodeView view;assert(!f.capture.acquire(view));++cases; }
    { RetainedFixture f;const auto old=f.owner.binding();
      { hgn_dflash::Lock held(f.lane);assert(held.held);f.owner.holder_destructor(100);
        assert(f.owner.state()==State::Retired);assert(hgn_dflash::atomic_load(f.lane.phase)==hgn_dflash::u32(hgn_dflash::Phase::Pending));
        assert(!f.owner.storage_reclaimable());assert(!f.owner.publish(f.admission)); }
      assert(f.owner.storage_reclaimable());assert(hgn_dflash::atomic_load(f.lane.phase)==hgn_dflash::u32(hgn_dflash::Phase::Quarantined));
      assert(f.owner.publish(f.admission));auto current=f.owner.binding();assert(current.ticket>old.ticket&&current.lease_generation>old.lease_generation);
      auto ops=f.bridge.operations();assert(ops.retire(ops.context,old));
      assert(hgn_dflash::atomic_load(f.lane.phase)==hgn_dflash::u32(hgn_dflash::Phase::Pending));
      auto foreign=current;foreign.cache_generation++;assert(!ops.retire(ops.context,foreign));
      foreign=current;foreign.lease_generation++;assert(!ops.retire(ops.context,foreign));
      assert(hgn_dflash::atomic_load(f.lane.generation)==current.lease_generation);++cases; }
    { RetainedFixture f;f.complete();f.backend.done=true;FeatureView view;assert(f.owner.acquire_features(view));
      { hgn_dflash::Lock held(f.lane);assert(held.held);f.owner.request_destructor(400);
        assert(f.owner.state()==State::Retired&&!f.owner.storage_reclaimable());
        assert(f.owner.release_features(view.binding.ticket));assert(!f.owner.storage_reclaimable());
        assert(hgn_dflash::atomic_load(f.lane.phase)==hgn_dflash::u32(hgn_dflash::Phase::Request)); }
      assert(f.owner.storage_reclaimable());assert(hgn_dflash::atomic_load(f.lane.phase)==hgn_dflash::u32(hgn_dflash::Phase::Quarantined));++cases; }
    { RetainedFixture f;f.chunk(0,2);f.chunk(2,2);assert(f.owner.materialize(100,300,0,4));f.owner.holder_destructor(100);
      { hgn_dflash::Lock held(f.lane);assert(held.held);assert(f.owner.abandon_materialized(300,0,1,f.input.data(),4));
        f.input.fill(-1);assert(f.owner.state()==State::Retired);assert(!f.owner.storage_reclaimable());
        assert(hgn_dflash::atomic_load(f.lane.phase)==hgn_dflash::u32(hgn_dflash::Phase::Pending)); }
      assert(!f.owner.storage_reclaimable());f.backend.done=true;assert(f.owner.storage_reclaimable());
      assert(hgn_dflash::atomic_load(f.lane.phase)==hgn_dflash::u32(hgn_dflash::Phase::Quarantined));++cases; }
    { Fixture f;assert(f.configure());assert(f.owner.publish(f.admission));f.chunk(0,2);f.chunk(2,2);
      f.backend.callback_context=&f.owner;f.backend.on_live=[](void* p) noexcept {static_cast<Owner*>(p)->holder_destructor(100);};
      assert(f.owner.materialize(100,300,0,4));assert(f.owner.state()==State::Retired&&f.backend.retired==1);
      assert(!f.owner.transfer(400,5,200,300,0,1,f.input.data(),4));f.backend.done=true;assert(f.owner.storage_reclaimable());++cases; }
    { Fixture f;assert(f.configure());assert(f.owner.publish(f.admission));f.complete();f.backend.done=true;FeatureView view;assert(f.owner.acquire_features(view));
      f.backend.callback_context=&f.owner;f.backend.on_loss=[](void* p) noexcept {static_cast<Owner*>(p)->request_destructor(400);};
      assert(!f.owner.end_chunk(100,4,4));assert(f.owner.state()==State::Retired&&f.backend.retired==1);
      assert(!f.owner.storage_reclaimable());assert(f.owner.release_features(view.binding.ticket));assert(f.owner.storage_reclaimable());++cases; }
    { Fixture f;assert(f.configure());assert(f.owner.publish(f.admission));f.backend.callback_context=&f.owner;
      f.backend.on_live=[](void* p) noexcept {auto& owner=*static_cast<Owner*>(p);owner.holder_destructor(999);owner.request_destructor(400);};
      assert(f.owner.force_serial(100,200,0));assert(f.owner.state()==State::Pending&&f.backend.retired==0&&f.backend.lost==0);
      f.chunk(0,2);f.chunk(2,2);assert(f.owner.materialize(100,300,0,4));
      f.backend.callback_context=&f;f.backend.on_live=[](void* p) noexcept {auto& x=*static_cast<Fixture*>(p);auto ids=x.input;ids[3]=99;
          assert(!x.owner.abandon_materialized(300,0,1,ids.data(),4));assert(!x.owner.abandon_materialized(301,0,1,x.input.data(),4));};
      assert(f.owner.transfer(400,5,200,300,0,1,f.input.data(),4));assert(f.owner.state()==State::Request&&f.backend.retired==0);++cases; }
    { DecodeFixture f;const auto b=f.binding();const std::int32_t id=1;
      assert(f.capture.begin(b,1,DecodeSource::Scalar,20,&id,1,0));f.taps(1);assert(f.capture.committed(1,21));assert(f.capture.outcome(b,0,2,1));
      f.owner_fixture.backend.done=true;DecodeView view;assert(f.capture.acquire(view));f.capture.retire(b.lease_generation);
      f.capture.disable_new();assert(!f.capture.storage_reclaimable());assert(!f.capture.release(view.capture_sequence+1));
      assert(f.capture.release(view.capture_sequence));assert(f.capture.storage_reclaimable());++cases; }
    { DecodeFixture f;auto b=f.binding();const std::int32_t id=1;f.capture.retire(b.lease_generation+1);
      assert(f.capture.begin(b,1,DecodeSource::Scalar,20,&id,1,0));f.taps(1);assert(f.capture.committed(1,21));assert(f.capture.outcome(b,0,2,1));
      f.capture.retire(b.lease_generation+1);f.owner_fixture.backend.done=true;DecodeView view;assert(f.capture.acquire(view));assert(f.capture.release(view.capture_sequence));
      f.capture.retire(b.lease_generation);assert(!f.capture.begin(b,2,DecodeSource::Scalar,21,&id,1,1));
      ++b.lease_generation;++f.owner_fixture.backend.generation;assert(f.capture.begin(b,1,DecodeSource::Scalar,21,&id,1,1));
      f.capture.retire(b.lease_generation-1);f.taps(1);assert(f.capture.committed(1,22));assert(f.capture.outcome(b,0,2,2));
      assert(f.capture.acquire(view));assert(f.capture.release(view.capture_sequence));++cases; }
    { DecodeFixture f;const auto b=f.binding();const std::int32_t id=1;
      assert(f.capture.begin(b,1,DecodeSource::Scalar,20,&id,1,0));f.taps(1);assert(f.capture.committed(1,21));assert(f.capture.outcome(b,0,2,1));
      f.owner_fixture.backend.done=true;f.owner_fixture.backend.callback_context=&f;
      f.owner_fixture.backend.on_query=[](void* p) noexcept {auto& x=*static_cast<DecodeFixture*>(p);x.capture.retire(x.binding().lease_generation);};
      DecodeView view;assert(!f.capture.acquire(view));f.capture.disable_new();assert(f.capture.storage_reclaimable());++cases; }
    { DecodeFixture f;const auto b=f.binding();const std::int32_t id=1;
      f.owner_fixture.backend.callback_context=&f;
      f.owner_fixture.backend.on_live=[](void* p) noexcept {auto& x=*static_cast<DecodeFixture*>(p);x.capture.retire(x.binding().lease_generation);};
      assert(!f.capture.begin(b,1,DecodeSource::Scalar,20,&id,1,0));f.capture.disable_new();assert(f.capture.storage_reclaimable());++cases; }
    { DecodeFixture f;const auto b=f.binding();const std::int32_t id=1;
      assert(f.capture.begin(b,10,DecodeSource::Scalar,20,&id,1,0));f.taps(1);
      assert(f.capture.committed(1,21));assert(f.capture.outcome(b,0,2,1));
      auto foreign=b;++foreign.lease_generation;
      assert(!f.capture.begin(foreign,1,DecodeSource::Scalar,21,&id,1,1));
      assert(!f.capture.begin(b,10,DecodeSource::Scalar,21,&id,1,1));++cases; }
    std::cout<<"pending owner CPU cases passed: "<<cases<<"\n";
}
