"""Prospective real Stock/NPU/Stock cohort. Only Root-sealed --run does work.

Uses the existing lifecycle and qualified four-request RAW collector. Current
BEFORE outputs are comparison evidence only and are never sent to the producer.
"""
import argparse
import asyncio
import copy
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import socket
import sys
import traceback

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from evidence import need,read,pin,save_new,capture,stats,delta,require_parity,require_warmup
from owned_producer import OwnedProducer

PRIMARY=HERE.parents[1]; ROOT=HERE.parents[5]
OLD_PRIMARY=ROOT/'server/.local/halogen-update-20261110/primary0201'
PACKAGE=ROOT/'backends/halogen-wsl2-0.20.2'
NORMAL=PRIMARY/'serving0202-text32k-8192.json'
NORMAL_SHA='e9452bdf8075ffffb498c41d86ba9b0a9533695417d842a5258f336a54fab7fe'
BASE_SOURCE_SHA='0a9ad79d7d0d30aebbeda41ce4e92509021631a9750f8cfb7fbb246b71592171'
REQUEST=ROOT/'server/.local/halogen-update-20261107/primary0191/natural8192-prep/request-natural8192.json'
REQUEST_SHA='2e26413988ce75fcf745a1a143aa3647297349c1516f9d18968e9d1b4da0632d'
STATE=ROOT/'server/.local/optimization9h-20261004/continuation-current.json'
ARMS=('before','candidate','after'); CASE='natural8192'


class NPUWarmupFailure(RuntimeError): pass


def utc(): return datetime.now(timezone.utc).isoformat()


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec); sys.modules[name]=module; spec.loader.exec_module(module)
    return module


def profiles():
    need(pin(NORMAL)['sha256']==NORMAL_SHA,'Exact current8192 normal profile changed')
    normal=read(NORMAL); engine=normal['engine']
    need(engine['prefill_chunk']==engine['max_prefill_tokens']==8192
         and engine['context']==engine['kv_pool_positions']==32768
         and engine['slots']==normal['concurrency']==1 and engine['prompt_cache']=='Off',
         'Frozen8192 one-slot CacheOff profile differs')
    result={}
    for arm in ARMS:
        value=copy.deepcopy(normal)
        value['engine']['kernel_controls'].update(HALOGEN_PHASE_RAW=1,HALOGEN_SERVE_TRACE=1,
            HALOGEN_DECODE_PREFETCH=0,HALOGEN_EXTERNAL_STREAM=int(arm=='candidate'))
        result[arm]=value
    return result


def validate_bindings(path,expected_sha,*,running=False):
    need(pin(path)['sha256']==expected_sha,'Exact Root binding changed')
    value=read(path)
    need(value.get('schema')=='halogen0202.real-NPU-cohort-bindings.v1'
         and value.get('oracle_future_IDs') is False,'Real-NPU bindings required')
    need(pin(REQUEST)['sha256']==REQUEST_SHA and {k:v for k,v in read(REQUEST).items() if k!='prompt'}
         ==dict(cache_prompt=False,drafter='mtp',max_tokens=128,model='halogen-v2',
             prompt_cache_policy='no_store',seed=1,stream=False,temperature=0),'Frozen greedy128 request changed')
    profiles()
    if value.get('root_sealed') is not True:
        need(not running,'Root must seal final RAW/reverse overlay, sources, artifacts and producer before run')
        return value,None
    need(value.get('source_freeze_complete') is True,'Final source freeze must precede Root execution seal')
    for expected in value['pins']:need(pin(expected['path'])==expected,'Executed input changed: '+expected['path'])
    transition=read(value['transition'])
    need(transition['schema']=='halogen0202.RAW-reverse-HDO2-private-source-overlay.v1'
         and transition['normal_source_manifest']['sha256']==BASE_SOURCE_SHA
         and transition['common_RAW_observer_all_arms'] is True
         and transition['watchdog_timers_and_uptime_body_byte_identical'] is True
         and len(transition['baseline'])==48,'Exact common RAW/reverse source47 baseline required')
    need(len(value['artifacts'])==2 and {row['target'] for row in value['artifacts']}==
         {'.local/libhgn0202-stream.so','.local/libhgn0202_raw_side.so'},'Exactly two owned native artifacts required')
    need(value['producer']['service'].endswith('service_request_scoped_v2.py')
         and value['producer']['connect']==dict(host='127.0.0.1',port=8843),
         'Explicit request-scoped reverse helper required')
    for arm,profile in profiles().items():
        need(read(Path(value['transition']).parent/(arm+'.profile.json'))==profile,'Frozen overlay arm profile differs')
        env=value['native_environment'][arm]
        need(env['HGN0202_RAW_ENABLE']=='1' and env['HGN0202_API_NATIVE_ID']=='1'
             and env['HALOGEN_PREFILL_CHUNK']==env['HALOGEN_MAX_TOK']=='8192'
             and env['HGN0202_STREAM_CAPTURE']=='1'
             and env.get('HGN0202_EXTERNAL_STREAM')==('1' if arm=='candidate' else None),
             'Common RAW/capture and0/1/0 native environment differ')
    return value,transition


def normalized_transition(value):
    return dict(baseline=dict(files=value['baseline']),candidate=value['candidate'],
        rollback_restore=value['baseline'],rollback_remove={name:value['candidate'][name] for name in value['added']},
        candidate_delta={name:value['candidate'][name] for name in value['changed_existing']+value['added']})


def close_before_gpu_stop(helper,stop_gpu):
    """A failed helper close never prevents restoration of the owned GPU arm."""
    failure=None; result=None
    try:
        if helper is not None:result=helper.close()
    except BaseException as error:failure=error
    finally:stop_gpu()
    if failure is not None:raise failure
    return result


def support(output,bindings):
    module=load('real_npu_existing_lifecycle',OLD_PRIMARY/'prefill4096-cohort-prep/root_campaign.py')
    module.OUT=output; module.PACKAGE=PACKAGE; module.NORMAL=NORMAL; module.NORMAL_SHA256=NORMAL_SHA; module.CASE_NAMES=(CASE,)
    module.policy.normal=lambda:read(NORMAL)
    module.private_profile=lambda baseline,arm,experiment=None:profiles()[arm]
    module.native_environment=lambda rule='gate',arm='before':bindings['native_environment'][arm]
    old_trace=load('real_npu_original_lookup_trace',OLD_PRIMARY/'oracle-cohort-prep/oracle_trace.py')
    def qualified_trace(text,samples,rule):
        result=old_trace.qualify_trace(text,samples,rule)
        result.update(schema='halogen0202.native-NPU-trace.v1',NPU_lookup_activity_allowed=True,
                      copied_NPU_counters_folded_into_acceptance=False)
        result.pop('oracle_lookup_activity_allowed',None); result.pop('copied_oracle_counters_folded_into_acceptance',None)
        return result
    import types
    module.trace_parser=types.SimpleNamespace(qualify_trace=qualified_trace)
    reference=load('real_npu_existing_cleanup',OLD_PRIMARY/'oracle-cohort-prep/oracle_campaign.py')
    reference.NORMAL=NORMAL; reference.NORMAL_SHA=NORMAL_SHA
    # Fresh collector and RAW bindings are separately pinned/reviewed in this run.
    # Retained reference supplies artifact restoration and authenticated discovery only.
    return module,reference


def run(bindings,transition,output):
    output=Path(output).resolve()
    need(not output.exists() and output.is_relative_to(PRIMARY.resolve()),
         'Observe retained campaign handles; this one finite output must be fresh')
    bound=Path(bindings['transition']).parent; plan=normalized_transition(transition)
    module,reference=support(output,bindings)
    module.check_files(PACKAGE,plan['baseline']['files']); module.check_files(bound/'candidate',plan['candidate'])
    module.check_files(bound/'rollback',plan['rollback_restore'])
    previous,runtime=module.support(); previous.allowed(runtime)
    baseline=runtime.verify(NORMAL,8840,require_idle=True)
    need(baseline['profile']['sha256']==NORMAL_SHA,'Current normal owner/profile differs')
    collector=load('real_npu_qualified_callback_collector',HERE.parent/'raw/collector/collect_epoch.py')
    collector.m.check_reserve(runtime,22)
    with socket.socket() as probe:probe.bind(('127.0.0.1',18840))
    output.mkdir(); save_new(output/'executed-bindings.json',bindings)
    record=dict(schema='halogen0202.real-NPU-cohort.v1',utc=utc(),terminal=False,completed=False,restored=False,
        identity=runtime.ops.ident.process_identity(os.getpid()),baseline=baseline,owned_runs=[],owned_bindings={},
        results={},artifacts=[],weights_identity_by_arm={},startup_allocation_by_arm={},oracle_future_IDs=False,
        real_NPU_prediction=True,headline_qualified=False,hardware_owner='root',
        warmups_excluded=1,measured_repetitions=3,actual_input_tokens=8192,output_tokens=128)
    def save(phase,**updates):
        record.update(phase=phase,**updates); runtime.ops.atomic(output/'handle.json',record)
        state=runtime.ops.read(STATE)
        state['current_work']=dict(scope='halogen0202_real_NPU_finite',phase=phase,handle=str(output/'handle.json'),
            identity=record['identity'],hardware_owner='root',server_restore_required=not record['restored'],
            lifecycle_receipt=record.get('lifecycle_receipt'),do_not_duplicate_live_handles=True,goal_achieved=False)
        runtime.ops.atomic(STATE,state)
    def launch(profile,label,port):
        receipt=output/(label+'-launch.json')
        save(label+'_launching',lifecycle_receipt=str(receipt),launch_result=None,launch_observed=False)
        result=runtime.lifecycle.launch(argparse.Namespace(profile=profile,receipt=receipt,version='0.20.2',
            port=port,visible=port==8840,admission_wait=180))
        save(label+'_launch_returned',launch_result=result); need(result==0,'Existing startup admission failed')
        ready=runtime.await_ready(profile,port,receipt)
        record['owned_runs'].append(ready['outer']['run_id']); record['owned_bindings'][ready['outer']['run_id']]=ready
        save(label+'_ready',active=ready,launch_observed=True); return ready
    active=baseline; overlay_attempted=False; helper=None; reference_output=None
    save('normal_verified')
    with runtime.previous.wsl_stdin_lease(output):
        try:
            runtime.gpu_receipt('before-stop'); runtime.stop_owned(active,'normal-stop'); active=None
            runtime.ops.atomic(output/'normal-terminal.json',module.terminal(runtime,baseline,record['owned_runs'],record['owned_bindings']))
            overlay_attempted=True; module.apply_overlay(PACKAGE,bound,plan)
            for item in bindings['artifacts']:
                record['artifacts'].append(reference.artifact_install(module,output,PACKAGE/item['target'],Path(item['source'])))
            save('private_source_applied')
            for index,arm in enumerate(ARMS):
                profile=output/(arm+'.profile.json'); runtime.ops.atomic(profile,profiles()[arm])
                active=launch(profile,arm,18840); module.check_files(PACKAGE,plan['candidate'])
                arm_dir=output/arm; arm_dir.mkdir()
                save_new(arm_dir/'initial-service-manifest.json',(Path(active['inner']['attempt'])/'manifest.json').read_bytes(),raw=True)
                weights_before=module.observe_weights_identity()
                record['startup_allocation_by_arm'][arm]=module.save_startup_allocation(runtime,active,arm)
                raw_dir=Path(active['inner']['attempt'])/'raw-phase'; folder=arm_dir/CASE
                prior_stats=stats(runtime,active) if arm=='candidate' else None
                if arm=='candidate':
                    monitor=load('real_npu_module_enumerator',OLD_PRIMARY/'stateful1012-prep/run_owned_stateful.py')
                    helper=OwnedProducer(runtime,output/'npu-helper',bindings['producer'],monitor.module_paths)
                    helper.start(); helper.wait_connected()
                    save('candidate_helper_started',NPU_helper_handle=str(helper.folder/'handle.json'))
                def after_validated(ordinal,sample,raw_sample,current_folder):
                    nonlocal reference_output,prior_stats
                    need(sample['finish_reason']=='length','Frozen128-token cohort must finish at length cap')
                    current=capture(raw_dir,current_folder,ordinal,sample,candidate=arm=='candidate')
                    if reference_output is None:
                        need(arm=='before' and ordinal==0,'Only current BEFORE warmup may establish output comparison')
                        reference_output=current
                    require_parity(reference_output,current)
                    if arm=='candidate':
                        helper.check(); observed=stats(runtime,active); changes=delta(prior_stats,observed); prior_stats=observed
                        save_new(Path(current_folder)/('HDO2-stats-'+str(ordinal)+'.json'),dict(after=observed,delta=changes))
                        if ordinal==0:
                            try:require_warmup(changes)
                            except ValueError as error:raise NPUWarmupFailure(str(error)) from error
                            save('candidate_warmup_proved',first_candidate_consumer=changes,exact_native_T_and_output_parity=True)
                save('collecting',arm=arm)
                report=asyncio.run(collector.collect_epoch(runtime=runtime,profile=profile,port=18840,expected=active,
                    request_bytes=REQUEST.read_bytes(),request_sha256=REQUEST_SHA,route='/v1/completions',raw_dir=raw_dir,
                    epoch=0x0202001200000001+index,output=folder,expected_prompt_tokens=8192,expected_output_tokens=128,
                    after_validated_sample=after_validated))
                module.save_cost_trace(runtime,active,profile,folder,report,{},arm=arm)
                record['results'][arm]={CASE:report}
                weights_after=module.observe_weights_identity()
                record['weights_identity_by_arm'][arm]=module.save_weights_identity(runtime,arm,weights_before,weights_after)
                closed_helper=close_before_gpu_stop(helper,lambda:runtime.stop_owned(active,arm+'-stop'))
                active=None
                if helper is not None:
                    record['NPU_helper']=closed_helper
                    need(record['NPU_helper']['request_contexts']==4,'Four request contexts must close')
                    helper=None
                save('arm_complete',arm=arm)
                runtime.ops.atomic(output/(arm+'-terminal.json'),module.terminal(runtime,baseline,record['owned_runs'],record['owned_bindings']))
            record['completed']=all(record['results'].get(arm,{}).get(CASE,{}).get('collector',{}).get('completed') is True
                and len(record['results'][arm][CASE]['samples'])==4 for arm in ARMS)
            # Results stay raw evidence until Root independently audits the completed cohort.
        except BaseException as error:
            save('error',error=dict(type=type(error).__name__,message=str(error),traceback=traceback.format_exc()),
                 consumer_failure=isinstance(error,NPUWarmupFailure))
            if not isinstance(error,NPUWarmupFailure):raise
        finally:
            if helper is not None:
                try:record['NPU_helper']=helper.close()
                except BaseException as error:
                    record['NPU_helper_cleanup_error']=dict(type=type(error).__name__,message=str(error))
                    need(helper.child is None or helper.child.poll() is not None,
                         'Retained own NPU process is still live; observe its handle before any restoration launch')
                helper=None
            current=runtime.ops.read(ROOT/'server/.local/current.json')
            if active is None and record.get('lifecycle_receipt'):
                receipt_path=Path(record['lifecycle_receipt'])
                if receipt_path.exists():
                    receipt=runtime.ops.read(receipt_path)
                    if current['phase'] in ('starting','ready'):
                        active=runtime.await_ready(Path(receipt['profile']['path']),receipt['port'],receipt_path)
                        if active['outer']['run_id'] not in record['owned_runs']:record['owned_runs'].append(active['outer']['run_id'])
                        record['owned_bindings'][active['outer']['run_id']]=active
                    else:
                        need(not runtime.previous.identity_live(receipt['launcher_identity']) or record.get('launch_observed'),
                             'Unpublished live launcher must be observed before restoration')
                        if receipt.get('controller_run'):
                            need(current['run_id']==receipt['controller_run'] and not runtime.previous.identity_live(receipt['controller_identity']),
                                 'Terminal owned launch identity differs or remains live')
                            if current['run_id'] not in record['owned_runs']:record['owned_runs'].append(current['run_id'])
                elif record.get('launch_result') not in (2,):raise RuntimeError('Unresolved launch; inspect actual handles before another start')
            current=runtime.ops.read(ROOT/'server/.local/current.json')
            if not overlay_attempted and active is baseline and current['phase']=='ready' and current['run_id']==baseline['outer']['run_id']:
                restored=runtime.verify(NORMAL,8840,require_idle=False)
                need(restored['identities']==baseline['identities'],'Original runtime changed after preflight rejection')
            else:
                if active is not None and current['phase'] in ('starting','ready'):runtime.stop_owned(active,'final-private-stop')
                active=None
                runtime.ops.atomic(output/'rollback-terminal.json',module.terminal(runtime,baseline,record['owned_runs'],record['owned_bindings']))
                if overlay_attempted:
                    reference.artifacts_restore(module,record['artifacts']); module.restore_overlay(PACKAGE,bound,plan)
                module.check_files(PACKAGE,plan['baseline']['files'])
                need(pin(PACKAGE/'profiles/sources.json')['sha256']==BASE_SOURCE_SHA
                     and len(read(PACKAGE/'profiles/sources.json')['files'])==47,'Exact fresh source47 rollback failed')
                save('normal_source_restored'); restored=launch(NORMAL,'restore-normal',8840)
            reference.refresh_consumer(runtime,restored,output)
            runtime.ops.atomic(output/'ready-left-online.json',restored)
            save('complete_normal_online',restored=True,final=restored,terminal=True,ended_utc=utc())
    return record


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bindings',type=Path,required=True); parser.add_argument('--bindings-sha',required=True)
    parser.add_argument('--run',action='store_true'); parser.add_argument('--output',type=Path)
    args=parser.parse_args(); bindings,transition=validate_bindings(args.bindings,args.bindings_sha,running=args.run)
    if not args.run:
        print(json.dumps(dict(source_only=True,root_sealed=bindings.get('root_sealed') is True,native_execution=False)))
        return 0
    need(args.output is not None,'Explicit fresh Root-owned output required')
    result=run(bindings,transition,args.output)
    return 0 if result['completed'] and result['restored'] else 2


if __name__=='__main__':raise SystemExit(main())
