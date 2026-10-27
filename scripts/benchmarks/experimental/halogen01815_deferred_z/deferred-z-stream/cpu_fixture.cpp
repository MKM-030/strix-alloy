#include "deferred_z_stream.h"
#include <cassert>
#include <cstdio>
#include <map>
#include <string>
#include <vector>

using namespace deferred_z;
namespace {
struct Event { int time{}, records{}; };
struct Fake {
    int main{},side{},completed{},calls{},fail_at{},sync_fail{},destroyed{};
    std::uintptr_t next{16};
    std::map<Handle,Event> events;
    std::vector<std::string> log;
    int step(const char* name) { log.emplace_back(name); return ++calls==fail_at ? 9:0; }
    int& clock(Handle stream) { assert(!stream || stream==reinterpret_cast<Handle>(1)); return stream?side:main; }
}* f;
int sc(Handle* h,unsigned flags) { assert(flags==1);int r=f->step("stream_create");if(!r)*h=reinterpret_cast<Handle>(1);return r; }
int sd(Handle h) { assert(h==reinterpret_cast<Handle>(1));return f->step("stream_destroy"); }
int ss(Handle h) { f->log.emplace_back(h?"sync_side":"sync_main");if(f->sync_fail)return 9;f->completed=999999;return 0; }
int ec(Handle* h,unsigned flags) { assert(flags==2);int r=f->step("event_create");if(!r){*h=reinterpret_cast<Handle>(f->next++);f->events[*h]={};}return r; }
int ed(Handle h) { int r=f->step("event_destroy");if(!r){assert(f->events.erase(h)==1);++f->destroyed;}return r; }
int er(Handle e,Handle s) { int r=f->step(s?"record_side":"record_main");if(!r){f->events.at(e).time=f->clock(s);++f->events.at(e).records;}return r; }
int eq(Handle e) { int r=f->step("query");if(r)return r;return f->events.at(e).time<=f->completed?0:600; }
int sw(Handle s,Handle e,unsigned flags) { assert(flags==0);int r=f->step(s?"wait_side":"wait_main");if(!r){auto& t=f->clock(s);if(t<f->events.at(e).time)t=f->events.at(e).time;}return r; }
Api api{sc,sd,ss,ec,ed,er,eq,sw};
bool pins_ok=true;
int verified=0;
bool verify(const char* hash,const Pin* pins,std::size_t count) {
    ++verified; assert(std::string(hash)==engine_sha && count==1 && pins[0].bytes==1);return pins_ok;
}
unsigned char expected=0x90;
Pin pin{0x100,&expected,1};
Qualification qualified() {
    Qualification q{};q.enabled=true;q.single_owner=true;q.disjoint_z_output=true;
    q.unchanged_fc=true;q.scratch_sequential=true;q.no_native_prefetch=true;
    q.all_exits_bound=true;q.complete_fc_launch_coverage=true;
    q.warmed_algorithm_cache=true;q.stock_ht_path=true;q.live_ranges_verified=true;
    q.image_hash=engine_sha;q.pins=&pin;q.pin_count=1;q.verify_identity_and_bytes=verify;return q;
}
int native_calls=0;
void fc(void* d,const void* in,void* out,int n,int m,int k) {
    assert(d==reinterpret_cast<void*>(2) && in==reinterpret_cast<void*>(3) && out==reinterpret_cast<void*>(4));
    assert(n==6144 && m==8192 && k==2560);
    Handle actual=nullptr;assert(redirect_stream(nullptr,actual));assert(actual==reinterpret_cast<void*>(1));
    // hipBLASLt can internally submit with the stream already redirected.
    Handle nested=nullptr;assert(redirect_stream(actual,nested));assert(nested==actual);
    assert(f->side>=f->main);f->side+=10;++native_calls;
}
void throwing_fc(void*,const void*,void*,int,int,int) { Handle s{};assert(redirect_stream(nullptr,s));f->side+=1;throw 3; }
void foreign_fc(void*,const void*,void*,int,int,int) { Handle s{};assert(!redirect_stream(reinterpret_cast<void*>(77),s)); }
void uncovered_fc(void*,const void*,void*,int,int,int) {}
FcCall call(Fc original=fc) { return {original,reinterpret_cast<void*>(2),reinterpret_cast<void*>(3),reinterpret_cast<void*>(4),6144,8192,2560}; }

void defaults_and_qualification() {
    Fake fake;f=&fake;Context c;Qualification off{};
    assert(c.open(api,off));assert(c.capture(call())==Result::stock);assert(c.close());assert(fake.calls==0);
    auto q=qualified();q.complete_fc_launch_coverage=false;assert(!c.open(api,q));assert(fake.calls==0);
    q=qualified();q.image_hash="wrong";assert(!c.open(api,q));assert(fake.calls==0);
    pins_ok=false;assert(!c.open(api,qualified()));assert(fake.calls==0);pins_ok=true;
}
void schedule_and_generations() {
    Fake fake;f=&fake;Context c;assert(c.open(api,qualified()));
    for(int i=0;i<8;++i){
        assert(c.capture(call())==Result::captured);f->main+=10; // AB and QKV completion on main
        assert(c.after_ab()==Result::pending);assert(active_redirect==nullptr);
        f->main+=5;assert(f->main<f->side); // independent main prep overlaps Z
        assert(c.join_pending()==Result::joined);assert(f->main==f->side);
    }
    const int before=native_calls;assert(c.capture(call())==Result::stock);assert(native_calls==before);
    f->completed=999999;assert(c.capture(call())==Result::captured);
    assert(c.after_ab()==Result::pending);assert(c.join_pending()==Result::joined);
    assert(c.close());assert(fake.events.empty());assert(fake.destroyed==24);
}
void capture_early_exit() {
    Fake fake;f=&fake;Context c;assert(c.open(api,qualified()));assert(c.capture(call())==Result::captured);
    assert(c.close()); // original Z has been suppressed, caller must abort request
    assert(fake.log[25]=="sync_side" && fake.log[26]=="sync_main");assert(fake.events.empty());
}
void irreversible_errors() {
    for(Fc fn:{throwing_fc,foreign_fc,uncovered_fc}){
        Fake fake;f=&fake;Context c;assert(c.open(api,qualified()));assert(c.capture(call(fn))==Result::captured);
        assert(c.after_ab()==Result::fatal);assert(c.poisoned());assert(active_redirect==nullptr);
        assert(c.capture(call())==Result::fatal);assert(c.close());assert(fake.events.empty());
    }
    // Every enqueue boundary fails in turn. No stock retry after suppressing Z.
    for(int offset=1;offset<=5;++offset){
        Fake fake;f=&fake;Context c;assert(c.open(api,qualified()));assert(c.capture(call())==Result::captured);
        fake.fail_at=fake.calls+offset;
        Result r=c.after_ab();if(r==Result::pending)r=c.join_pending();
        assert(r==Result::fatal);assert(c.poisoned());assert(c.close());
    }
    Fake fake;f=&fake;Context c;assert(c.open(api,qualified()));assert(c.capture(call())==Result::captured);
    assert(c.after_ab()==Result::pending);fake.sync_fail=1;
    assert(!c.close());assert(fake.events.size()==24 && fake.destroyed==0);
    fake.sync_fail=0;assert(c.close());assert(fake.events.empty());
}
void initial_resource_failures() {
    for(int at=1;at<=25;++at){Fake fake;f=&fake;fake.fail_at=at;Context c;assert(!c.open(api,qualified()));assert(c.close());assert(fake.events.empty());}
}
void bounded_event_slots() {
    for(std::size_t count:{std::size_t(0),std::size_t(9)}){
        Fake fake;f=&fake;Context c;auto q=qualified();q.event_slots=count;
        assert(!c.open(api,q));assert(fake.calls==0&&fake.events.empty());assert(c.close());
    }
    Fake fake;f=&fake;Context c;auto q=qualified();q.event_slots=1;
    assert(c.open(api,q));assert(fake.calls==4&&fake.events.size()==3);
    assert(c.capture(call())==Result::captured);fake.main=10;
    assert(c.after_ab()==Result::pending);assert(c.join_pending()==Result::joined);
    const int before=native_calls;assert(c.capture(call())==Result::stock);assert(native_calls==before);
    fake.completed=fake.main;assert(c.capture(call())==Result::captured);
    assert(c.after_ab()==Result::pending);assert(c.join_pending()==Result::joined);
    assert(c.close());assert(fake.destroyed==3&&fake.events.empty());
    for(int at=1;at<=4;++at){
        Fake partial;f=&partial;partial.fail_at=at;Context context;
        assert(!context.open(api,q));assert(context.close());assert(partial.events.empty());
    }
}
int observer_calls=0;
bool observer(void* cookie,const Submit& view) {
    assert(cookie==reinterpret_cast<void*>(123));++observer_calls;
    return view.kind==SubmitKind::kernel;
}
void scoped_observer() {
    Submit view{};view.kind=SubmitKind::kernel;view.args=reinterpret_cast<void**>(321);
    assert(observe_submit(view));assert(observer_calls==0);
    Observation o{observer,reinterpret_cast<void*>(123),false};
    {ObserverScope scope(o);assert(scope.entered());assert(observe_submit(view));assert(observer_calls==1);
     ObserverScope nested(o);assert(!nested.entered());
     Redirect r{nullptr,reinterpret_cast<void*>(1),false,0};
     {RedirectScope z(r);assert(observe_submit(view));assert(observer_calls==2);}
     view.kind=SubmitKind::copy;assert(!observe_submit(view));assert(observer_calls==3);}
    assert(active_observation==nullptr);assert(observe_submit(view));assert(observer_calls==3);
}
}
int main(){defaults_and_qualification();schedule_and_generations();capture_early_exit();irreversible_errors();initial_resource_failures();bounded_event_slots();scoped_observer();std::puts("PASS: disabled/pins, AB ordering, event pool/reuse, one-slot bounded creation/exhaustion/retirement/reuse and invalid limits, early exit, scope/foreign errors, failed drain retention, all creation failures, scoped observer");}
