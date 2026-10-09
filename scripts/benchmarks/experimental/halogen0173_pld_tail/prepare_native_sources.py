"""Prepare a separate cold-start native consumer source tree; no builds/launches."""
from pathlib import Path
import hashlib
import json
import argparse

HERE=Path(__file__).resolve().parent
PINS={
 'shadow_collector.h':'31b01cdf933016204b15d9f2f1b9b1eeca26d944391a2afebc479700988fa287',
 'shadow_collector.cpp':'3801f62cacf5fc90a722159c04040451191aa07a0e46340455956eacb0e7aacb',
 'shadow_install.cpp':'94b983272ba8ea541d255e116a885a0b05ffb02fda30002ba8410e629cfe3963',
 'shadow_relay.S':'0230fc9d2e29aecac83c962182b781dfe58271144c402bf799d1e7f224bd1546',
 'shadow_relay.h':'57cba2403873b5e4e932844c4a87e7f05213824b9bc9408b70cb29920eee2459',
 'shadow_relay.ld':'6fcec8defdf68e0be9bb7c6885bcfdd580523b3e2cbb10783d72c0d0ce5052ad',
 'shadow_wire.h':'a5537bcc0568bed7f40b143b9eb890f6362489c859626d6cdd5bc71e22d6f489',
}
def replace_one(text,old,new):
    assert text.count(old)==1,(old,text.count(old))
    return text.replace(old,new)
def prepare(source: Path, output: Path):
    source=source.resolve(strict=True);output=output.resolve()
    if not source.is_dir() or output.exists():
        raise ValueError('Use a pinned source directory and a fresh output directory')
    inputs={name:(source/name).read_bytes() for name in PINS}
    for name,expected in PINS.items():
        if hashlib.sha256(inputs[name]).hexdigest()!=expected:
            raise ValueError('Pinned owned-hook source changed: '+name)
    headers={name:(HERE/name).read_bytes() for name in
        ('tail_adapter.h','oracle_format.h','readylist_oracle.h')}
    output.mkdir(parents=True,exist_ok=False)
    for name,data in headers.items():
        (output/name).write_bytes(data)
    for name,sha in PINS.items():
        data=inputs[name]
        text=data.decode()
        if name=='shadow_collector.h':
            text=replace_one(text,'#include "shadow_wire.h"','#include "shadow_wire.h"\n#include "tail_adapter.h"')
            text=replace_one(text,'    Header header() const noexcept;',
                '    Header header() const noexcept;\n    bool attach_tail(tail::Adapter* adapter) noexcept {\n        if(enabled_) return false; tail_=adapter; return true;\n    }')
            text=replace_one(text,'    std::atomic<bool> enabled_{false};','    tail::Adapter* tail_{};\n    std::atomic<bool> enabled_{false};')
        elif name=='shadow_collector.cpp':
            insertion='''            // New mutation transaction. Width and opening are unchanged; all
            // subsequent native constraints/verify/commit/replay remain stock.
            if(source==Source::Pld && tail_ && tail_->enabled()) {
                tail::Snapshot snapshot{};auto& key=snapshot.key;tail_->pin_key(key);
                key.owner_birth=e.owner_birth;key.slot_cookie=e.slot_cookie;
                key.slot_epoch=e.slot_epoch;key.round=e.round;key.wire_request_id=e.wire_request_id;
                key.context_total=e.context_total;key.context_count=e.context_count;
                key.transported_count=e.transported_count;key.model_position=e.model_position;
                key.current_id=e.current_id;key.native_allowance=e.native_allowance;
                key.width=e.offer_total;
                for(unsigned i=0;i<3;++i) key.stock[i]=i<e.offer_count?e.pld_offer[i]:0;
                for(unsigned i=0;i<64;++i) key.suffix[i]=e.context_suffix[i];
                snapshot.owned=true;snapshot.greedy=load<std::uint64_t>(rq,0x190)==0;
                snapshot.unconstrained=load<std::uint64_t>(rq,0x240)==0;
                snapshot.complete=(e.flags&(ContextAvailable|OfferAvailable))==(ContextAvailable|OfferAvailable)
                    && !(e.flags&(Censored|OfferTruncated)) && e.offer_total==e.offer_count;
                struct LiveGuard { Collector* collector;Owner* owner;Slot* slot;std::uint64_t request,record;const tail::Key* key; };
                LiveGuard guard{this,o,s,rq,record,&key};
                const auto still_live=[](void* opaque) noexcept {
                    const auto& g=*static_cast<LiveGuard*>(opaque);
                    if(!(g.collector->enabled_.load(std::memory_order_acquire)
                        && g.collector->dropped_.load(std::memory_order_acquire)==g.collector->loss_seen_
                        && g.owner->live && g.owner->request==g.request && g.owner->epoch==g.slot->epoch
                        && load<std::uint64_t>(g.record,0x10)==g.request
                        && load<std::uint64_t>(g.request,0x108)==g.owner->model
                        && load<std::int32_t>(g.owner->model,0x2e8)==g.key->model_position
                        && load<std::int32_t>(g.request,0x19c)==g.key->current_id)) return false;
                    const auto begin=load<std::uint64_t>(g.request,0x1c0),end=load<std::uint64_t>(g.request,0x1c8),cap=load<std::uint64_t>(g.request,0x1d0);
                    return begin<=end && end<=cap && (end-begin)==std::uint64_t{g.key->context_total}*4
                        && g.key->context_count<=g.key->context_total
                        && !std::memcmp(reinterpret_cast<const void*>(end-4*g.key->context_count),g.key->suffix,4*g.key->context_count);
                };
                if(tail_->replace(snapshot,reinterpret_cast<std::int32_t*>(rsp+0x6a0),f.gpr[1],still_live,&guard)==tail::Status::Applied)
                    for(unsigned i=1;i<key.width;++i) e.pld_offer[i]=load<std::int32_t>(rsp+0x6a0,4*i);
            }
'''
            text=replace_one(text,'            o->before=e; o->pending=publish(e);',insertion+'            o->before=e; o->pending=publish(e);')
        elif name=='shadow_install.cpp':
            text=replace_one(text,'#include "shadow_collector.h"','#include "shadow_collector.h"\n#include "readylist_oracle.h"')
            text=replace_one(text,'    if(!collector.configure(true,nonce)) { fail("collector-configure"); }',
                '    if(!halogen0173::tail::init_readylist(nonce)) fail("pld-tail-configure");\n'
                '    if(halogen0173::tail::measured_tail.enabled() && !collector.attach_tail(&halogen0173::tail::measured_tail)) fail("pld-tail-attach");\n'
                '    if(!collector.configure(true,nonce)) { fail("collector-configure"); }')
            text=replace_one(text,'    writer_stop.store(true); pthread_join(writer_thread,nullptr);',
                '    writer_stop.store(true); pthread_join(writer_thread,nullptr);\n    halogen0173::tail::report_readylist_counts();')
        (output/name).write_text(text,encoding='utf-8',newline='\n')
    receipt={'schema':'halogen0173.pld-tail.sources.v1','mode_default':'off','source_pins':PINS,
        'native_elf_sha256':'af4f07bbe3759206013eb6f1328095ca2105cfda5127c5b9a2ab93e1aea987b7',
        'runtime_build_or_launch':False,'future_label_oracle':True,'real_npu_producer':False,'tail_seam_rva':'0x17413ff','width_or_frame_mutation':False,
        'adapter_headers':{name:hashlib.sha256(data).hexdigest() for name,data in headers.items()},
        'outputs':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in output.glob('shadow_*') if p.is_file()}}
    (output/'native-source-preparation.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps({'prepared_sources':len(PINS),'runtime_build_or_launch':False,'future_label_oracle':True,'real_npu_producer':False}))

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-dir',required=True,type=Path,
        help='The seven original owned-hook source files matching PINS')
    parser.add_argument('--output-dir',required=True,type=Path,
        help='Fresh source tree only; no build, hook install or runtime launch')
    args=parser.parse_args();prepare(args.source_dir,args.output_dir)

if __name__=='__main__':main()
