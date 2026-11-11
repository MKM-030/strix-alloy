"""Bounded same-ready22-GiB admission around the unchanged frozen campaign.

No model/API/GPU operation occurs inside the wait. Its separate receipts are
outside HTTP/RAW timing and do not change any sample, threshold or capacity.
"""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time

HERE=Path(__file__).resolve().parent
BASE_SHA='800782162ad0132c38be02ebbaa618cdefb564943e0aaaa8a0e6db342ec953ee'
ROOT=HERE.parents[5]
GIB=2**30


def need(ok,message):
    if not ok:raise ValueError(message)


class AdmissionWaiter:
    def __init__(self,output,*,clock=time.monotonic,pause=time.sleep,
                 ensure_directory=lambda path:path.mkdir()):
        self.folder=Path(str(output)+'.admission-waits');self.clock=clock;self.pause=pause
        self.ensure_directory=ensure_directory;self.started=False;self.sequence=0

    def same_ready(self,runtime,expected):
        outer=runtime.ops.read(ROOT/'server/.local/current.json')
        inner=runtime.ops.read(ROOT/'backends/halogen-wsl2-0.20.3/.local/current-service.json')
        need(outer['phase']==inner['phase']=='ready'
             and outer['run_id']==expected['outer']['run_id']
             and inner['run_id']==expected['inner']['run_id']
             and outer['pid']==expected['identities']['controller']['pid']
             and inner['controller_pid']==expected['identities']['backend']['pid']
             and outer.get('profile_sha256')==expected['outer'].get('profile_sha256')
             and not outer.get('active_requests',0),'Verified ready controller identity or idle state changed')
        for identity in expected['identities'].values():
            need(runtime.previous.identity_live(identity)
                 and runtime.ops.ident.process_identity(identity['pid'])==identity,
                 'Verified ready process identity changed')

    def wait(self,runtime,label):
        expected=copy.deepcopy(getattr(runtime,'real_npu_admission_verified',None))
        need(type(expected)is dict and expected['outer']['phase']==expected['inner']['phase']=='ready',
             'An already verified ready controller is required before admission')
        if not self.started:
            need(not self.folder.exists(),'Observe the existing admission owner; never duplicate this run')
            self.ensure_directory(self.folder);self.started=True
        self.sequence+=1;path=self.folder/(str(self.sequence).zfill(4)+'.json')
        began=self.clock();deadline=began+120;eligible=0
        record=dict(schema='halogen0203.same-ready-memory-admission.v1',label=label,
            controller_run=expected['outer']['run_id'],backend_run=expected['inner']['run_id'],
            identities=expected['identities'],maximum_seconds=120,entry_reserve_gib=22,
            runtime_reserve_gib=18,required_eligible_frames=2,eligible_frames=0,
            terminal=False,admitted=False,samples=[],model_API_GPU_calls=0,
            process_launches=0,HTTP_or_RAW_timing_modified=False)
        print(json.dumps(dict(event='npu_memory_admission_begin',label=label,
            controller_run=record['controller_run'],elapsed_seconds=0,eligible_frames=0)),flush=True)
        def save():
            record['elapsed_seconds']=max(0,self.clock()-began)
            runtime.ops.atomic(path,record)
        save()
        try:
            while True:
                need(self.clock()<deadline,'120-second memory admission deadline reached on the same ready controller')
                self.same_ready(runtime,expected)
                frame=runtime.ops.host.frame()
                need(all(type(frame.get(key))is int and frame[key]>=0
                         for key in ('available_bytes','commit_headroom_bytes')),'Invalid local memory sample')
                row=dict(elapsed_seconds=max(0,self.clock()-began),memory=frame)
                record['samples'].append(row)
                need(min(frame['available_bytes'],frame['commit_headroom_bytes'])>=18*GIB,
                     '18-GiB physical/commit runtime floor crossed during admission')
                self.same_ready(runtime,expected)
                need(self.clock()<=deadline,'120-second memory admission deadline reached')
                eligible=eligible+1 if min(frame['available_bytes'],frame['commit_headroom_bytes'])>=22*GIB else 0
                row['eligible_frames']=eligible;record['eligible_frames']=eligible;save()
                if eligible==2:
                    record.update(terminal=True,admitted=True);save();return frame
                remaining=deadline-self.clock()
                need(remaining>0,'120-second memory admission deadline reached')
                self.pause(min(.25,remaining))
        except BaseException as error:
            record.update(terminal=True,admitted=False,error=dict(type=type(error).__name__,message=str(error)))
            save();raise
        finally:
            print(json.dumps(dict(event='npu_memory_admission_end',label=label,
                controller_run=record['controller_run'],elapsed_seconds=max(0,self.clock()-began),
                eligible_frames=record['eligible_frames'],admitted=record['admitted'])),flush=True)


def reserve_check(waiter,original):
    def check(runtime,floor):
        return waiter.wait(runtime,'collector-22') if floor==22 else original(runtime,floor)
    return check


def start_admitted(producer,original_start,waiter):
    frame=waiter.wait(producer.runtime,'producer-start-22')
    host=producer.runtime.ops.host;original_frame=host.frame;used=False
    def frame_once():
        nonlocal used
        if not used:used=True;return frame
        return original_frame()
    # The frozen direct check consumes the final fresh admission sample once.
    # Subsequent watcher samples and all18-GiB guards still read actual memory.
    host.frame=frame_once
    try:return original_start(producer)
    finally:host.frame=original_frame


def install(campaign):
    old_support,old_load,old_producer=campaign.support,campaign.load,campaign.OwnedProducer
    state={};original_checks=[]
    def support(output,bindings):
        waiter=AdmissionWaiter(output);state['waiter']=waiter
        module,reference=old_support(output,bindings);previous_support=module.support
        def runtime_support():
            previous,runtime=previous_support();verify=runtime.verify
            def verified(*args,**kwargs):
                result=verify(*args,**kwargs)
                runtime.real_npu_admission_verified=copy.deepcopy(result);return result
            runtime.verify=verified;return previous,runtime
        module.support=runtime_support;return module,reference
    def load(name,path):
        module=old_load(name,path)
        if name=='real_npu_qualified_callback_collector':
            original_checks.append((module.m,module.m.check_reserve))
            module.m.check_reserve=reserve_check(state['waiter'],module.m.check_reserve)
        return module
    class AdmittedProducer(old_producer):
        def start(self):return start_admitted(self,old_producer.start,state['waiter'])
    campaign.support=support;campaign.load=load;campaign.OwnedProducer=AdmittedProducer
    def restore():
        campaign.support=old_support;campaign.load=old_load;campaign.OwnedProducer=old_producer
        for module,original in reversed(original_checks):module.check_reserve=original
    return restore


def main():
    path=HERE/'cohort_campaign.py'
    need(hashlib.sha256(path.read_bytes()).hexdigest()==BASE_SHA,'Frozen campaign source changed')
    spec=importlib.util.spec_from_file_location('real_npu_frozen_campaign_admission_v2',path)
    campaign=importlib.util.module_from_spec(spec);sys.modules[spec.name]=campaign;spec.loader.exec_module(campaign)
    restore=install(campaign)
    try:return campaign.main()
    finally:restore()


if __name__=='__main__':raise SystemExit(main())
