"""Finite unused-head component qualification; validation is inert by default.

This is teacher-forced correctness/timing replay, never an engine proposal feed.
Root owns the external22/18-GiB monitor, the <=120-second child and module proof.
No API, GPU lifecycle, WSL, compiler, second native engine or speculation is used.
"""
import argparse
import ctypes
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import statistics
import struct
import time
import uuid

from actor import HASH_DOMAIN,ROWS,PrefixKey,StatefulActor,digest_ids,need,prefix_hash
from service import ENGINE,TOKENIZER

HERE=Path(__file__).resolve().parent
PRIMARY=HERE.parents[1]
DEFAULT_INPUT=PRIMARY/'stateful1012-live-prep/producer/qualification-input-natural8192.json'
DEFAULT_REFERENCE=PRIMARY/'stateful1012-npu-v1/reference.json'
INPUT_SHA='65bc27c06fa19582634ce768b1e7d3cd6928bcfa34342fdc24b00dbc83d04de0'
REFERENCE_SHA='c72d4591e000f4dc832e567f52e56b14e89598fe3332474343515aa5c6cb9f8d'
ENDPOINTS=tuple(range(0,129,16))


def pin(path):
    path=Path(path).resolve();h=hashlib.sha256()
    with path.open('rb')as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
    return dict(path=str(path),bytes=path.stat().st_size,sha256=h.hexdigest())


def validate_input(value):
    need(value.get('schema')=='halogen0201.stateful1012-full-prompt-input.v1','Frozen full prompt input required')
    packet=value['input'];need(packet.get('target_engine_sha256')==ENGINE
        and packet.get('target_tokenizer_sha256')==TOKENIZER and len(packet.get('cases',[]))==1,'Frozen native authority required')
    case=packet['cases'][0];ids=value['prompt_ids'];teachers=case['teacher_ids']
    need(case.get('name')=='natural8192'and case.get('actual_input_tokens')==8192
         and type(ids)is list and len(ids)==8192 and type(teachers)is list and len(teachers)==128
         and all(type(t)is int and 0<=t<ROWS for t in ids+teachers)
         and ids[-512:]==case['seed_tail_ids'],'Exact8192/512/128 IDs required')
    need(hashlib.sha256(struct.pack('<8192i',*ids)).hexdigest()==value.get('raw_LE_ID_sha256')
         =='322ad3ae71dac4989a35ef9c9a73b3f80dba15443b6ef1160467681355acfbe5'
         and prefix_hash(ids)==value.get('hdo2_prefix_sha256')==case['native_prompt_prefix_sha256']
         =='db50995e2fb9f8eff514405041f9f9b2511acd09b013591d30971d0b14f1242b'
         and value.get('hash_domain_hex')==HASH_DOMAIN.hex(),'Frozen full prompt hash differs')
    for expected in value['source_pins']:need(pin(expected['path'])==expected,'Input provenance changed: '+expected['path'])
    return case


def validated_reference(input_path,reference_path):
    need(pin(input_path)['sha256']==INPUT_SHA,'Frozen full-prompt input changed')
    need(pin(reference_path)['sha256']==REFERENCE_SHA,'Frozen sequential reference changed')
    value=json.loads(Path(input_path).read_bytes());validate_input(value)
    reference=json.loads(Path(reference_path).read_bytes())
    need(reference['input']==value['input'],'Prior1.0.12 authority differs')
    tools_path=PRIMARY/'stateful1012-prep/stateful_tools.py'
    spec=importlib.util.spec_from_file_location('catchup_original_exact_criterion',tools_path)
    tools=importlib.util.module_from_spec(spec);spec.loader.exec_module(tools)
    tools.validate_report(reference,'reference');rows={}
    for g in ENDPOINTS:
        state=reference['states'][g];path=tools.row_file(reference_path,reference,state);raw=path.read_bytes()
        need(len(raw)==ROWS*2 and tools.row_greedy(raw)==state['greedy_id'],'Complete finite reference endpoint differs')
        rows[g]=dict(data=raw,greedy_id=state['greedy_id'],pin=pin(path))
    return value,rows,pin(tools_path)


class WindowsQPC:
    def __init__(self):
        need(os.name=='nt','Explicit native execution requires Windows QPC')
        self.api=ctypes.WinDLL('kernel32',use_last_error=True)
        for name in('QueryPerformanceCounter','QueryPerformanceFrequency'):
            fn=getattr(self.api,name);fn.argtypes=[ctypes.POINTER(ctypes.c_int64)];fn.restype=ctypes.c_int
        frequency=ctypes.c_int64();need(self.api.QueryPerformanceFrequency(ctypes.byref(frequency))and frequency.value>0,'QPC frequency unavailable')
        self.frequency=frequency.value

    def __call__(self):
        tick=ctypes.c_int64();need(self.api.QueryPerformanceCounter(ctypes.byref(tick)),'QPC unavailable');return tick.value


def current_module_paths():
    """Own process modules; no native model calls and no child/process creation."""
    from ctypes import wintypes as W
    api=ctypes.WinDLL('kernel32',use_last_error=True)
    api.GetCurrentProcess.argtypes=[];api.GetCurrentProcess.restype=W.HANDLE
    api.K32EnumProcessModulesEx.argtypes=[W.HANDLE,ctypes.POINTER(W.HMODULE),W.DWORD,ctypes.POINTER(W.DWORD),W.DWORD]
    api.K32EnumProcessModulesEx.restype=W.BOOL
    api.K32GetModuleFileNameExW.argtypes=[W.HANDLE,W.HMODULE,W.LPWSTR,W.DWORD]
    api.K32GetModuleFileNameExW.restype=W.DWORD
    modules=(W.HMODULE*512)();needed=W.DWORD();handle=api.GetCurrentProcess()
    need(api.K32EnumProcessModulesEx(handle,modules,ctypes.sizeof(modules),ctypes.byref(needed),3)
         and needed.value<=ctypes.sizeof(modules),'Own loaded-module enumeration failed')
    paths=[]
    for module in modules[:needed.value//ctypes.sizeof(W.HMODULE)]:
        buffer=ctypes.create_unicode_buffer(32768)
        need(api.K32GetModuleFileNameExW(handle,module,buffer,len(buffer))>0,'Loaded-module path unavailable')
        paths.append(buffer.value)
    return sorted(set(paths))


def run_modes(factory,value,*,clock,frequency,deadline_seconds=110,row_bytes=ROWS*2,module_probe=lambda:[]):
    """One engine, eight timed resets plus one unmeasured mixed-batch check."""
    case=validate_input(value)
    need(type(frequency)is int and frequency>0 and 0<deadline_seconds<=115
         and type(row_bytes)is int and 0<row_bytes<=ROWS*2 and row_bytes%2==0,'Finite replay/clock bounds required')
    started=time.monotonic();deadline=started+deadline_seconds;backend=None;actor=None;rows={}
    report=dict(schema='halogen0201.stateful1012-core-append-qualification.v1',complete=False,error=None,
        native_closed=False,native_cleanup_complete=True,terminal_cancel_completed=False,runs=[],operations=[],
        head_instructions_restored=False,append_mode_default_off=True,
        endpoint_indices=list(ENDPOINTS),endpoints_per_run=9,QPC_frequency=frequency,
        clock='Windows QPC',module_observations=[],module_verification_owner='Root external monitor',
        teacher_forced_component_only=True,engine_future_feed=False,speculative_prepare_calls=0,
        native_engine_constructions=0,native_acceptance=None,prefill_tok_s=None,decode_tok_s=None,
        target_readiness=None,engine_benefit=None,
        timing_scope='Sum of eight commit-only QPC spans per run; seed/reset, endpoint capture, disk and comparisons excluded')
    def check():need(time.monotonic()<deadline,'Finite catchup component deadline expired')
    def capture(run):
        check();g=actor.key.global_t_count;node=actor._ring[0]
        need(g in ENDPOINTS and node.local_count==512+g and len(node.row.data)==row_bytes,
             'Exact deep-owned committed endpoint row required')
        need(g==ENDPOINTS[len(run['states'])],'Exactly nine ordered committed endpoints required')
        rows[(run['run_index'],g)]=node.row.data
        run['states'].append(dict(state_index=g,actual_global_T_count=g,local_count=node.local_count,
            row_count=row_bytes//2,greedy_id=node.row.greedy_id,row_sha256=node.row.sha256,
            prefix_sha256=actor.key.prefix_sha256,row_file=f"run-{run['run_index']}-state-{g}.bf16"))
    try:
        check();backend=factory();report['native_engine_constructions']=1;actor=StatefulActor(backend)
        report['module_observations'].append(dict(phase='constructed',paths=module_probe()))
        for run_index in range(9):
            check();timed=run_index<8
            mode=('head_on','head_skip')[run_index%2]if timed else 'correctness_mixed_batches'
            epoch=uuid.uuid4().hex
            run=dict(run_index=run_index,mode=mode,timed=timed,excluded_warmup=run_index<2,
                measured_run=(run_index-2)//2+1 if 2<=run_index<8 else None,complete=False,
                actual_committed_T_count=0,committed_event_batches=0,states=[],commit_segments=[],
                operations_begin=len(backend.operations))
            if timed:report['runs'].append(run)
            else:
                report['correctness_mixed_batches']=run
                run['batch_sizes_per_span']=[1,2,3,4,6]
            need(actor.key is None and not backend.states,'Previous opaque states must retire before reset')
            backend.set_append_head_skip(mode!='head_on')
            before_status=backend.head_skip_status()
            need(before_status['restored']is True,'Original head instructions must be restored before reset')
            run['head_skip_status_before']=before_status
            h=digest_ids(value['prompt_ids']);key=PrefixKey(case['request_id'],8192,epoch,1,0,h.hexdigest(),-1)
            transactions=[]
            for g,token in enumerate(case['teacher_ids'],1):
                h.update(struct.pack('<i',token));transactions.append((PrefixKey(case['request_id'],8192,epoch,1,g,h.hexdigest(),token),[token]))
            # sl1012_seed explicitly clear_context()s after states.empty().
            actor.begin(key,value['prompt_ids']);capture(run)
            for offset in range(0,128,16):
                check();batch=transactions[offset:offset+16];before=clock()if timed else None;finished=False
                try:
                    if timed:
                        actor.commit_batch(actor.key,batch);run['committed_event_batches']+=1
                    else:
                        cursor=0
                        for size in(1,2,3,4,6):
                            actor.commit_batch(actor.key,batch[cursor:cursor+size])
                            run['committed_event_batches']+=1;cursor+=size
                    finished=True
                finally:
                    if timed:
                        after=clock();need(0<=before<=after,'Monotonic actual QPC endpoints required')
                        run['commit_segments'].append(dict(first_T_index=offset+1,last_T_index=offset+16,
                            started_ticks=before,finished_ticks=after,complete=finished))
                capture(run);run['actual_committed_T_count']=actor.key.global_t_count
            if timed:run['commit_loop_ms']=sum(s['finished_ticks']-s['started_ticks']for s in run['commit_segments'])*1000/frequency
            run['operations_end']=len(backend.operations)
            actor.cancel();need(not backend.states,'Run cancellation retained opaque snapshots')
            after_status=backend.head_skip_status();run['head_skip_status_after']=after_status
            run['head_skip_count_delta']=after_status['count']-before_status['count']
            run['head_instructions_restored']=after_status['restored']
            need(after_status['restored']is True,'Head instructions not restored after arm')
            need(run['head_skip_count_delta']==(120 if mode=='head_skip'else 0 if mode=='head_on'else 88),
                 'Exact completed intermediate head-skip count differs')
            run['complete']=True
        report['module_observations'].append(dict(phase='after_all_runs',paths=module_probe()))
    except BaseException as error:
        report['error']=type(error).__name__+': '+str(error)
        if getattr(error,'native_cleanup_complete',True)is not True:report['native_cleanup_complete']=False
    finally:
        # Observation must remain possible after a native restoration fault.
        # Never turn a failed patch scope into a claimed successful cleanup.
        try:
            if backend is not None:
                status=backend.head_skip_status();report['terminal_head_skip_status']=status
                report['head_instructions_restored']=status['restored']
                need(status['restored']is True,'Native head restoration failed before terminal cleanup')
                backend.set_append_head_skip(False)
        except BaseException as error:
            report['native_cleanup_complete']=False;report['error']=report['error']or type(error).__name__+': '+str(error)
        try:
            if actor is not None:actor.cancel()
            report['terminal_cancel_completed']=actor is not None and actor.key is None and not backend.states
        except BaseException as error:
            report['native_cleanup_complete']=False;report['error']=report['error']or type(error).__name__+': '+str(error)
        try:
            if backend is not None:backend.close()
            report['native_closed']=backend is not None and backend.handle is None and not backend.states
        except BaseException as error:
            report['native_cleanup_complete']=False;report['error']=report['error']or type(error).__name__+': '+str(error)
        if backend is not None:
            report['operations']=backend.operations
            report['head_skip_loaded_provider_identity']=getattr(backend,'head_skip_identity',None)
        report['elapsed_seconds']=time.monotonic()-started
    report['complete']=report['error']is None and report['native_closed']and report['native_cleanup_complete']and report['head_instructions_restored']
    report['complete']=report['complete']and report['terminal_cancel_completed']and len(report['runs'])==8 and all(r['complete']for r in report['runs'])
    report['complete']=report['complete']and report.get('correctness_mixed_batches',{}).get('complete',False)
    if report['complete']:
        report['summary']={}
        for mode in('head_on','head_skip'):
            selected=[r for r in report['runs']if r['mode']==mode];measured=[r['commit_loop_ms']for r in selected if not r['excluded_warmup']]
            report['summary'][mode]=dict(excluded_warmup_commit_loop_ms=selected[0]['commit_loop_ms'],
                measured_commit_loop_ms=measured,mean_commit_loop_ms=statistics.fmean(measured),median_commit_loop_ms=statistics.median(measured))
        report['summary']['mean_commit_loop_reduction_ms']=report['summary']['head_on']['mean_commit_loop_ms']-report['summary']['head_skip']['mean_commit_loop_ms']
    return report,rows


def persist_and_compare(report,rows,reference_rows,rows_dir,*,row_bytes=ROWS*2):
    """Disk and exact comparisons happen after the engine has closed, never timed."""
    rows_dir=Path(rows_dir);comparisons=[];total=0
    timed_total=0;mixed_comparison=None
    replays=report['runs']+([report['correctness_mixed_batches']]if 'correctness_mixed_batches'in report else [])
    for run in replays:
        states=[]
        for state in run['states']:
            g=state['state_index'];raw=rows[(run['run_index'],g)];baseline=reference_rows[g]
            need(len(raw)==len(baseline['data'])==row_bytes,'Complete equal-size endpoint rows required')
            path=rows_dir/state['row_file']
            with path.open('xb')as stream:need(stream.write(raw)==row_bytes,'Incomplete endpoint write')
            state['row_pin']=pin(path);equal=raw==baseline['data'];greedy_equal=state['greedy_id']==baseline['greedy_id']
            owned_hash_equal=state['row_pin']['sha256']==state['row_sha256']
            states.append(dict(state_index=g,exact_BF16_bytes_equal=equal,greedy_id_equal=greedy_equal,
                owned_row_hash_equal=owned_hash_equal,passed=equal and greedy_equal and owned_hash_equal,compared_BF16_values=row_bytes//2,
                candidate=state['row_pin'],reference=baseline['pin']))
            total+=1
        result=dict(run_index=run['run_index'],mode=run['mode'],comparisons=states)
        if run.get('timed',True):comparisons.append(result);timed_total+=len(states)
        else:mixed_comparison=result
    passed=report['complete']and total==81 and timed_total==72 and all(s['passed']for r in comparisons+[mixed_comparison]if r for s in r['comparisons'])
    return dict(schema='halogen0201.stateful1012-core-append-comparison.v1',exact_endpoint_row_parity=bool(passed),
        compared_endpoint_states=total,compared_BF16_values=total*(row_bytes//2),endpoint_indices=list(ENDPOINTS),
        timed_compared_endpoint_states=timed_total,timed_compared_BF16_values=timed_total*(row_bytes//2),
        endpoint_states_per_complete_run=9,tolerance_relaxed=False,criterion='original exact BF16 byte equality',
        runs=comparisons,correctness_mixed_batches=mixed_comparison,native_acceptance=None,prefill_tok_s=None,decode_tok_s=None,target_readiness=None,engine_benefit=None)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--enable-native-component',action='store_true')
    for name in('dll','model','bundle','runtime-dir'):parser.add_argument('--'+name,type=Path)
    parser.add_argument('--input',type=Path,default=DEFAULT_INPUT);parser.add_argument('--reference',type=Path,default=DEFAULT_REFERENCE)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--deadline-seconds',type=float,default=110)
    args=parser.parse_args(argv);value,reference_rows,criterion_pin=validated_reference(args.input,args.reference)
    need(0<args.deadline_seconds<=115,'Finite <=115-second native child workload required')
    if not args.enable_native_component:
        print(json.dumps(dict(validated=True,native_execution=False,endpoint_indices=list(ENDPOINTS),
            timed_runs=8,unmeasured_mixed_batch_runs=1,excluded_warmup_per_mode=1,measured_runs_per_mode=3)));return 0
    need(all(getattr(args,name)is not None for name in('dll','model','bundle','runtime_dir')),'Explicit native paths required')
    rows_dir=Path(str(args.output)+'.rows');comparison_path=Path(str(args.output)+'.comparison.json')
    need(args.output.parent.is_dir()and not any(p.exists()for p in(args.output,rows_dir,comparison_path)),'Fresh output and rows required')
    source_pins=[pin(HERE/name)for name in('qualify_core_append.py','actor.py','service.py','native_backend.py','native_backend.cpp','append_head_scope.hpp','request_scoped_backend.py')]
    native_pin=pin(args.dll);clock=WindowsQPC();rows_dir.mkdir()
    from native_backend import NativeBackend
    report,rows=run_modes(lambda:NativeBackend(args.dll,args.model,args.bundle,args.runtime_dir),value,
        clock=clock,frequency=clock.frequency,deadline_seconds=args.deadline_seconds,module_probe=current_module_paths)
    report.update(source_input=pin(args.input),reference_report=pin(args.reference),native_wrapper=native_pin,
        source_pins=source_pins,criterion_source=criterion_pin,bf16_rows_directory=str(rows_dir.resolve()),
        actual_teacher_ids=value['input']['cases'][0]['teacher_ids'],input=value)
    comparison=None
    try:comparison=persist_and_compare(report,rows,reference_rows,rows_dir)
    except BaseException as error:
        report['complete']=False;report['comparison_error']=type(error).__name__+': '+str(error)
    with args.output.open('x',encoding='utf-8')as stream:json.dump(report,stream,indent=2);stream.write('\n')
    if comparison is not None:
        comparison['report']=pin(args.output)
        with comparison_path.open('x',encoding='utf-8')as stream:json.dump(comparison,stream,indent=2);stream.write('\n')
    return 0 if report['complete']and comparison is not None and comparison['exact_endpoint_row_parity']else 1


if __name__=='__main__':raise SystemExit(main())
