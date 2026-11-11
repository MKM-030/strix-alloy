"""Offline terminal-only DNZ audit. Import and default CLI open no campaign data.

Only --audit --terminal-confirmed reads closed evidence. There is no process,
socket, WSL, API, compiler, driver or model interface in this module.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / 'dnz-prefill-capacity8192-v2'
EXPECTED_BINDING_SHA = 'ff52909f4e838c2e8b8ec6d105584a288add1f9c8bc759cf5bb806e6a0170ca8'
EXPECTED_RECOVERY_SHA = 'c14c7221586e81e78b3166a1ef8cfbbb26d8afa191239a3a517adfac3c95db4b'
ARMS = ('before', 'candidate', 'after')
SCOPES = ('head', 'lookup', 'grammar')
ENGINE_SHA = 'bf84053705d1e89c214ff64c79ad1276c5fe353d80a9bb0f38ef3bac6645b97c'


def need(ok, message):
    if not ok: raise ValueError(message)


def number(value, name, minimum=0):
    need(type(value) in (int, float) and math.isfinite(value) and value >= minimum,
         'Invalid finite ' + name)
    return value


def sha(data): return hashlib.sha256(data).hexdigest()


def stable_bytes(path, maximum=64*1024*1024):
    path=Path(path)
    need(path.is_file() and not path.is_symlink(), 'Regular unlinked evidence file required: '+str(path))
    before=path.stat()
    need(before.st_size<=maximum, 'Evidence exceeds bounded read: '+str(path))
    data=path.read_bytes();after=path.stat()
    need((before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns)==
         (after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns)
         and len(data)==after.st_size, 'Evidence changed while reading: '+str(path))
    return data


def read(path): return json.loads(stable_bytes(path))


def file_pin(path):
    path=Path(path);before=path.stat();digest=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):digest.update(block)
    after=path.stat()
    need((before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns)==
         (after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns), 'Pin changed during read')
    return dict(path=str(path.resolve()),bytes=after.st_size,sha256=digest.hexdigest())


def verify_pins(pins, expected_count=262):
    need(type(pins) is list and len(pins)==expected_count, 'Exactly262 executed pins required')
    seen=set()
    for row in pins:
        path=Path(row['path']);key=str(path.resolve()).casefold()
        need(path.is_absolute() and key not in seen, 'Duplicate/nonabsolute execution pin')
        seen.add(key);actual=file_pin(path)
        need(actual['bytes']==row['bytes'] and actual['sha256']==row['sha256'],
             'Executed source/artifact pin drift: '+str(path))
    return len(seen)


def require_complete(handle):
    need(handle.get('terminal') is True and handle.get('completed') is True
         and handle.get('restored') is True and handle.get('phase')=='complete_normal_online'
         and bool(handle.get('ended_utc')) and not handle.get('error')
         and not handle.get('restoration_error'), 'Complete terminal and normal restoration required')
    need(handle.get('NPU_helper') is False and handle.get('capacity_context')==8192
         and handle.get('actual_input_tokens')==2048 and handle.get('output_tokens')==128
         and handle.get('warmups_excluded')==1 and handle.get('measured_per_arm')==3,
         'Frozen GPU-only2K/8K-capacity cohort required')


def response_metrics(response):
    need(type(response.get('choices')) is list and len(response['choices'])==1, 'One OAI choice required')
    choice=response['choices'][0];text=choice.get('text');message=choice.get('message',{})
    need(type(text) is str and choice.get('finish_reason')=='length' and '<think>' not in text
         and '</think>' not in text and not message.get('reasoning_content')
         and not message.get('tool_calls'), 'Frozen ordinary length128 text required')
    usage,t=response['usage'],response['timings']
    need(type(usage.get('prompt_tokens')) is int and usage['prompt_tokens']==2048
         and type(usage.get('completion_tokens')) is int and usage['completion_tokens']==128
         and type(usage.get('total_tokens')) is int and usage['total_tokens']==2176
         and type(t.get('prompt_n')) is int and t['prompt_n']==2048
         and type(t.get('predicted_n')) is int and t['predicted_n']==128,
         'Actual request/response2048+128 counts differ')
    need(t.get('cache_n',0)==0 and t.get('disk_restore_n',0)==0
         and usage.get('prompt_tokens_details',{}).get('cached_tokens',0)==0
         and usage.get('cached_tokens',0)==0
         and usage.get('completion_tokens_details',{}).get('reasoning_tokens',0)==0
         and not any('clamp' in key for key in t), 'Cache/reasoning/clamp outside frozen scope')
    need(type(t.get('raw_native_request_id')) is int and t['raw_native_request_id']>0,
         'Causal native request ID required')
    ledger=t.get('speculation');need(type(ledger) is dict and ledger.get('drafter')=='mtp', 'MTP ledger required')
    scopes={}
    for name in SCOPES:
        scope=ledger.get(name)
        need(type(scope) is dict and all(type(scope.get(k)) is int and scope[k]>=0
             for k in ('rounds','drafted','accepted')) and scope['accepted']<=scope['drafted'],
             'Malformed reported acceptance scope')
        scopes[name]=dict(scope)
    need(sum(s['rounds'] for s in scopes.values())==ledger.get('rounds')
         and sum(s['drafted'] for s in scopes.values())==t.get('draft_n')
         and sum(s['accepted'] for s in scopes.values())==t.get('draft_n_accepted'),
         'Reported scoped and aggregate counters disagree')
    output=text.encode('utf-8')
    return dict(actual_input_tokens=2048,actual_output_tokens=128,finish_reason='length',
                output_utf8_bytes=len(output),output_sha256=sha(output),scoped=scopes,
                native_request_id=t['raw_native_request_id'])


def require_response_parity(reference,current):
    fields=('actual_input_tokens','actual_output_tokens','finish_reason','output_utf8_bytes','output_sha256','scoped')
    need(all(reference[k]==current[k] for k in fields), 'Exact UTF8/count/finish/scoped parity differs')


def restored_artifacts(items):
    for item in items:
        path=Path(item['path']);before=item.get('before')
        if before is None:
            need(not path.exists() and not path.is_symlink(),'Previously absent private artifact was not removed')
        else:
            need(file_pin(path)==before,'Original private artifact was not restored exactly')
            backup=file_pin(item['backup'])
            need(backup['bytes']==before['bytes'] and backup['sha256']==before['sha256'],
                 'Original private artifact backup drift')


def counter_delta(before,after,mode):
    need(type(mode) is int and mode in (0,1), 'Exact DNZ0/1 selector required')
    for key in ('identity','container_id','load_base','counter_address','counter_rva'):
        need(before.get(key)==after.get(key), 'Counter owner or PIE mapping changed')
    need(before.get('counter_rva')=='0x21ca518', 'DNZ counter RVA differs')
    for value in (before,after):
        need(value.get('read_only') is True and value.get('counter_bytes')==8
             and type(value.get('counter_value')) is int and 0<=value['counter_value']<1<<64,
             'Exact read-only uint64 counter required')
        identity=value['identity']
        need(identity.get('sha256')==ENGINE_SHA and identity.get('bytes')==35410384
             and type(identity.get('pid')) is int and identity['pid']>0
             and type(identity.get('starttime_ticks')) is int and identity['starttime_ticks']>0,
             'Exact DNZ ELF/process capture identity differs')
        need(int(value['counter_address'],16)==int(value['load_base'],16)+0x21ca518,
             'DNZ counter address does not match captured PIE base plus RVA')
    need(after['counter_value']>=before['counter_value'], 'Counter reset/wrap rejected')
    delta=after['counter_value']-before['counter_value']
    need(delta>0 if mode else delta==0, 'DNZ candidate must execute; stock must not execute')
    return delta


def validate_transport(transport,counter,mode):
    start,end=transport.get('qpc_start_ns'),transport.get('qpc_end_ns')
    need(type(start) is int and type(end) is int and 0<=start<end
         and transport.get('http_status')==200, 'Successful complete HTTPQPC boundaries required')
    seconds=number(transport.get('http_qpc_seconds'),'HTTPQPC')
    need(seconds==(end-start)/1e9, 'WholeHTTP seconds differ from exact boundaries')
    minimum=number(transport.get('minimum_reserve_gib'),'runtime reserve',18)
    need(counter.get('outside_HTTP_QPC_proved') is True and
         0<=counter['before_host_started_ns']<=counter['before_host_finished_ns']<=start<end
         <=counter['after_host_started_ns']<=counter['after_host_finished_ns'],
         'Counter reads entered matching HTTP timing interval')
    delta=counter_delta(counter['before'],counter['after'],mode)
    need(counter.get('delta')==delta and not counter.get('counter_error')
         and not counter.get('request_error'), 'Counter result contains error or wrong saved delta')
    return dict(HTTP_seconds=seconds,runtime_minimum_observed_gib=minimum,DNZ_successful_enqueues=delta,
                qpc_start_ns=start,qpc_end_ns=end)


def raw_rates(raw,transport):
    need(raw.get('valid') is True and raw.get('prompt')==raw.get('processed_prompt')==2048
         and raw.get('output_cap')==raw.get('generated_end')==raw.get('decode_numerator')==128
         and raw.get('generated_begin')==1 and raw.get('generated_delta')==127,
         'RAW actual counts/convention differ')
    total_upper=0;rates={}
    for phase,numerator in (('prefill',2048),('decode',128)):
        lower,upper=(raw[phase+'_raw_'+which+'_ns'] for which in ('lower','upper'))
        need(type(lower) is int and type(upper) is int and 0<lower<=upper, 'Invalid RAW bracket')
        total_upper+=upper
        prefix='RAW_'+phase+'_tok_s'
        rates[prefix]=numerator*1e9/((lower+upper)/2)
        rates[prefix+'_lower']=numerator*1e9/upper
        rates[prefix+'_upper']=numerator*1e9/lower
        for suffix,computed in (('mid',rates[prefix]),('lower',rates[prefix+'_lower']),('upper',rates[prefix+'_upper'])):
            need(raw.get(phase+'_raw_tps_'+suffix)==computed,'Saved RAW arithmetic differs')
    need(total_upper<=transport['qpc_end_ns']-transport['qpc_start_ns'], 'RAW upper phases exceed wholeHTTPQPC')
    return rates


def summarize_arm(rows):
    need(len(rows)==4 and [r.get('ordinal') for r in rows]==list(range(4))
         and [r.get('phase') for r in rows]==['warmup_excluded','measured','measured','measured'],
         'Warmup plus all three ordered measured rows required')
    measured=rows[1:];result={}
    for key in ('RAW_prefill_tok_s','RAW_decode_tok_s','RAW_prefill_tok_s_lower','RAW_prefill_tok_s_upper',
                'RAW_decode_tok_s_lower','RAW_decode_tok_s_upper','HTTP_seconds'):
        values=[number(row[key],key) for row in measured]
        result[key]=dict(values=values,mean=sum(values)/3,minimum=min(values),maximum=max(values))
    result['acceptance_scopes']={}
    for name in SCOPES:
        accepted=sum(row['scoped'][name]['accepted'] for row in measured)
        drafted=sum(row['scoped'][name]['drafted'] for row in measured)
        result['acceptance_scopes'][name]=dict(accepted=accepted,drafted=drafted,
                                              rate=accepted/drafted if drafted else None)
    result.update(warmup_excluded=True,measured_per_arm=3,arithmetic_rate_means=True)
    return result


def verify_ready(value,context,profile):
    need(value['profile']==profile and value['outer']['phase']==value['inner']['phase']=='ready'
         and value['outer']['context']==value['inner']['context']==context
         and value['native']['context']==value['native']['slot_ctx']==value['native']['kv_pool_positions']==context
         and value['native']['slots']==1 and value['native']['status']=='ok'
         and value['gateway']['status']=='ok' and value['gateway']['context']==context
         and value['native']['version']==dict(api='0.20.3',engine='0.20.3',match=True),
         'Saved native Ready capacity/version/profile differs')


def _validator(source):
    path=source/'raw/observer/validate_capture.py'
    spec=importlib.util.spec_from_file_location('dnz_closed_RAW_validator',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def _pure_module(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def reconcile_partial_recovery(original,original_pin,receipt,supplement,normal,smoke,profile):
    flags={key:original.get(key) for key in ('terminal','completed','restored','phase')}
    need(flags==dict(terminal=False,completed=False,restored=False,phase='restoration_incomplete'),
         'Original partial/restoration failure must remain unchanged')
    need(receipt.get('schema')=='halogen0203.DNZ8K-supplemental-normal-recovery.v1'
         and receipt.get('original_campaign_handle')==original_pin
         and receipt.get('original_campaign_flags')==flags
         and receipt.get('original_evidence_unchanged') is True
         and receipt.get('coordinator_identity_exited') is True
         and type(receipt.get('campaign_session_id')) is int and receipt.get('campaign_exit_code')==1
         and type(receipt.get('supplemental_session_id')) is int and receipt.get('supplemental_exit_code')==0,
         'Separate Root terminal/session/original evidence attestation differs')
    need(receipt.get('supplemental_ready') is True
         and receipt.get('restored_after_supplemental_recovery') is True
         and receipt.get('normal_profile')==profile and receipt.get('normal')==normal
         and supplement.get('terminal') is True and supplement.get('ready') is True
         and supplement.get('stage')=='normal_ready_open' and supplement.get('benchmark_requests')==0
         and supplement.get('effective_service_startup_floor_GiB')==[30,131],
         'Supplemental recovery is not separately complete at unchanged startup floors')
    need(receipt.get('benchmark_requests_total')==receipt.get('excluded_warmups')==1
         and receipt.get('measured_requests')==0 and receipt.get('candidate_started') is False
         and receipt.get('DNZ_gain_qualified') is False and receipt.get('full_goal_achieved') is False,
         'Partial campaign cannot become a complete measurement')
    need(receipt.get('original_failure')==original.get('error')
         and receipt.get('original_restoration_error')==original.get('restoration_error'),
         'Original admission/restoration failure provenance differs')
    verify_ready(normal,32768,profile)
    need(normal['outer']['port']==8840
         and supplement['normal']['outer']['run_id']==normal['outer']['run_id']
         and supplement['normal']['inner']['run_id']==normal['inner']['run_id'],
         'Supplemental recovered native owner differs')
    need(smoke.get('status')==200 and smoke.get('not_benchmark') is True
         and smoke['response']['choices'][0]['message'].get('content')=='READY',
         'Separate authenticated functional READY smoke differs')
    return dict(original_campaign_flags=flags,original_failure=original['error'],
        original_restoration_error=original['restoration_error'],later_normal_recovery_verified=True,
        saved_normal_port=8840,saved_normal_context=32768,
        saved_normal_controller_pid=normal['outer']['pid'] if 'pid' in normal['outer'] else None,
        saved_normal_backend_pid=normal['inner'].get('controller_pid'),
        original_coordinator_exit_proved_by_Root_receipt=True,
        campaign_session_id=receipt['campaign_session_id'],campaign_exit_code=1,
        supplemental_session_id=receipt['supplemental_session_id'],supplemental_exit_code=0,
        headline_qualified=False,DNZ_tok_s_difference=None,independent_live_liveness_check=False)


def audit_partial_recovered(handle_path,recovery_path,*,confirmed=False,
                            recovery_sha=EXPECTED_RECOVERY_SHA,binding_sha=EXPECTED_BINDING_SHA,source=SOURCE):
    need(confirmed is True,'Explicit Root terminal confirmation is required before evidence access')
    handle_path=Path(handle_path).resolve();folder=handle_path.parent;source=Path(source).resolve()
    original=read(handle_path);original_pin=file_pin(handle_path)
    report=dict(schema='halogen0203.DNZ8K-partial-and-supplemental-recovery-audit.v1',
        utc=datetime.now(timezone.utc).isoformat(),headline_qualified=False,rates_verified=False,
        warmup_throughput_exported=False,arms={},audit_passed=False,
        new_prefill_tok_s=None,new_decode_tok_s=None,new_acceptance=None,
        independent_native_token_ID_sequence_reconstruction=False,
        independent_all_neural_acceptance_reconstruction=False,
        hardware_calls=0,API_calls=0,WSL_used=False,DLL_loaded=False,
        source=file_pin(Path(__file__)),original_handle=original_pin,errors=[])
    try:
        recovery_data=stable_bytes(recovery_path)
        need(sha(recovery_data)==recovery_sha,'Actual Root supplemental receipt SHA differs')
        receipt=json.loads(recovery_data)
        need(receipt['original_campaign_handle']==original_pin,'Original handle differs from supplemental pin')
        linked={}
        for key in ('supplemental_recovery','normal_ready','authenticated_smoke'):
            pin=receipt[key];actual=file_pin(pin['path'])
            need(actual==pin,'Supplemental linked evidence pin differs: '+key)
            linked[key]=read(pin['path'])
        binding=read(folder/'executed-bindings.json');seal_data=stable_bytes(source/'Root-execution-bindings-v2.json')
        need(sha(seal_data)==binding_sha and binding==json.loads(seal_data)
             and binding['root_sealed'] is True and binding['dependency_closure_reviewed'] is True,
             'Root-sealed262-pin executed binding differs')
        report['executed_pins_verified']=verify_pins(binding['pins'])
        need(binding['guards']==dict(startup_physical=30,startup_commit=131,entry=22,runtime=18)
             and binding['NPU_helper'] is False and binding['external_stream'] is False,
             'Unchanged GPU-only resource policy differs')
        report.update(reconcile_partial_recovery(original,original_pin,receipt,
            linked['supplemental_recovery'],linked['normal_ready'],linked['authenticated_smoke'],binding['normal_profile']))
        need(original['capacity_context']==8192 and original['actual_input_tokens']==2048
             and original['output_tokens']==128 and original.get('results')=={}
             and original['NPU_helper'] is False,'Original incomplete cohort scope differs')
        case=binding['case'];data_dir=folder/'before'/case['name']
        collector=read(data_dir/'handle.json')
        need(collector.get('terminal') is True and collector.get('completed') is False
             and collector.get('completed_requests')==1 and collector.get('ordinal')==0
             and collector.get('disarmed_after_error') is True and not collector.get('disarm_error')
             and collector.get('error',{}).get('message')=='22-GiB memory reserve unavailable',
             'Closed partial collector/disarm/failure evidence differs')
        need(not (folder/'candidate').exists() and not (folder/'after').exists()
             and sorted(p.name for p in data_dir.glob('response-*.json'))==['response-0.json']
             and not list((data_dir/'journals').glob('*fault*')),
             'Additional candidate/measured responses or RAW fault marker found')
        request_data=stable_bytes(data_dir/'request.json');request=json.loads(request_data)
        need(sha(request_data)==case['request']['sha256']
             and request_data==stable_bytes(case['request']['path']), 'Exact partial request identity differs')
        response_data=stable_bytes(data_dir/'response-0.json');response=json.loads(response_data)
        metrics=response_metrics(response);sample=read(data_dir/'sample-0.json')
        need(sample['ordinal']==0 and sample['phase']=='warmup_excluded'
             and sample['request_sha256']==sha(request_data)
             and sample['response_sha256']==sha(response_data)
             and sample['output_sha256']==metrics['output_sha256']
             and sample['scoped']==metrics['scoped'] and sample['timings']==response['timings'],
             'Closed response/sample/explicit warmup identity differs')
        need(stable_bytes(folder/'reference-output.utf8')==response['choices'][0]['text'].encode('utf-8'),
             'Original excluded warmup UTF8 reference differs')
        transport=read(data_dir/'transport-0.json');counter=read(data_dir/'dnz-counter-0.json')
        timing=validate_transport(transport,counter,0)
        validator=_validator(source);epoch=0x020300D800000001
        journal_data=stable_bytes(data_dir/'journals'/f'capture-{epoch:016x}-0.bin')
        raw=validator.validate(validator.read_capture(journal_data,0,epoch),response,request=request,require_cold=True)
        raw_rates(raw,transport)  # Exact arithmetic checked; no partial rates exported.
        saved_raw=read(data_dir/'raw-sample-0.json')
        need(all(saved_raw.get(k)==v for k,v in raw.items())
             and saved_raw['journal_sha256']==sha(journal_data)
             and saved_raw['response_sha256']==sha(response_data),'Excluded warmup RAW recomputation differs')
        parity=read(data_dir/'parity-0.json')
        need(parity.get('exact_UTF8_finish_counts_scopes') is True
             and parity.get('native_token_ID_sequence_parity') is False,'Partial parity scope differs')
        verify_ready(read(folder/'before-launch.ready.json'),8192,binding['profiles']['before'])
        allocation=read(folder/'before/startup-allocation.json')
        need(allocation==original['startup_allocation_by_arm']['before']
             and allocation.get('exact_byte_allocation_claimed') is False,'Actual private8K allocation evidence differs')
        transition=read(binding['transition']);package=Path(binding['normal_source_manifest']['path']).parent.parent
        baseline=transition['baseline']['files']
        for relative,digest in baseline.items():
            path=(package/relative).resolve()
            need(path.is_relative_to(package.resolve()) and file_pin(path)['sha256']==digest,
                 'Original normal baseline was not restored: '+relative)
        restored_artifacts(original.get('artifacts',[]))
        report.update(status='partial_later_normal_recovered_verified',audit_passed=True,
            benchmark_requests_total=1,excluded_warmups=1,measured_requests=0,candidate_started=False,
            DNZ_successful_enqueues_before_warmup=timing['DNZ_successful_enqueues'],
            actual_input_tokens=2048,actual_output_tokens=128,private_context_capacity=8192,
            valid_excluded_warmup_RAW_brackets_and_HTTPQPC=True,
            runtime_minimum_observed_gib=timing['runtime_minimum_observed_gib'],
            resource_policy=dict(startup_physical=30,startup_commit=131,entry=22,runtime=18),
            original_native8K_ready_observed=True,startup_allocation_is_rounded_not_physical_release=True,
            normal_baseline_files_rehashed=len(baseline),original_artifact_restoration_verified=True,
            authenticated_READY_smoke_verified=True,smoke_is_not_a_benchmark=True,
            recovery_receipt=file_pin(recovery_path),linked_recovery_pins={key:receipt[key] for key in linked},
            closed_collector=file_pin(data_dir/'handle.json'),
            excluded_warmup_evidence=[file_pin(data_dir/name) for name in
                ('response-0.json','sample-0.json','raw-sample-0.json','transport-0.json','dnz-counter-0.json','parity-0.json')]
                +[file_pin(data_dir/'journals'/f'capture-{epoch:016x}-0.bin')],
            full_goal_achieved=False)
    except (ValueError,KeyError,TypeError,OSError,StopIteration) as error:
        report['status']='partial_recovery_audit_failed_no_headline'
        report['errors'].append(type(error).__name__+': '+str(error))
    need(file_pin(handle_path)==original_pin,'Original failed handle changed during offline audit')
    return report


def audit_terminal(handle_path,*,confirmed=False,binding_sha=EXPECTED_BINDING_SHA,source=SOURCE):
    need(confirmed is True,'Explicit Root terminal confirmation is required before evidence access')
    handle_path=Path(handle_path).resolve();folder=handle_path.parent;source=Path(source).resolve()
    record=read(handle_path)
    report=dict(schema='halogen0203.DNZ-capacity8192-independent-offline-audit.v2',
        utc=datetime.now(timezone.utc).isoformat(),terminal_confirmation_supplied=True,
        handle=file_pin(handle_path),headline_qualified=False,rates_verified=False,arms={},errors=[],
        hardware_calls=0,API_calls=0,WSL_used=False,DLL_loaded=False,
        independent_native_token_ID_sequence_reconstruction=False,
        independent_all_neural_acceptance_reconstruction=False,
        independent_review_required=True,API_clocks_used_for_headline=False,
        clock_scaling_or_component_conversion=False)
    try:
        require_complete(record)
        binding_data=stable_bytes(folder/'executed-bindings.json')
        seal_data=stable_bytes(source/'Root-execution-bindings-v2.json')
        need(sha(seal_data)==binding_sha and json.loads(binding_data)==json.loads(seal_data),
             'Actual executed binding differs from Root source seal')
        binding=json.loads(binding_data)
        need(binding.get('root_sealed') is True and binding.get('dependency_closure_reviewed') is True
             and binding.get('schema')=='halogen0203.DNZ-capacity8192-actual2048-bindings.v2'
             and binding.get('guards')==dict(startup_physical=30,startup_commit=131,entry=22,runtime=18)
             and binding.get('NPU_helper') is False and binding.get('external_stream') is False,
             'Execution seal or unchanged resource contract differs')
        report['executed_pins_verified']=verify_pins(binding['pins'])
        source_pins={str(Path(p['path']).resolve()).casefold():p for p in binding['pins']}
        for path in (source/'raw/observer/validate_capture.py',source/'raw/binding.json'):
            need(str(path.resolve()).casefold() in source_pins,'Offline RAW source is not executed-pin bound')
        validator=_validator(source)
        trace_path=next(Path(p['path']) for p in binding['pins']
                        if str(p['path']).replace('\\','/').endswith('/prefill8192-cohort-prep-v2/mtp_trace.py'))
        trace_parser=_pure_module(trace_path,'dnz_closed_native_trace_parser')
        case=binding['case'];request_data=stable_bytes(case['request']['path']);request=json.loads(request_data)
        need(sha(request_data)==case['request']['sha256'] and case['actual_input_tokens']==2048
             and case['actual_output_tokens']==128 and case['capacity_context']==8192,
             'Frozen actual2K request identity differs')
        need({k:v for k,v in request.items() if k!='prompt'}==dict(cache_prompt=False,drafter='mtp',
             max_tokens=128,model='halogen-v2',prompt_cache_policy='no_store',seed=1,stream=False,temperature=0),
             'Frozen request options differ')
        ids_pin=next(p for p in case['pins'] if Path(p['path']).name=='actual-input-ids.json')
        ids=read(ids_pin['path']);need(type(ids) is list and len(ids)==2048
             and all(type(i) is int and 0<=i<248320 for i in ids),'Exact tokenized input2048 proof differs')
        reference=None;all_rows={};minimum=float('inf');previous_global_end=0;counter_totals={}
        weight_reference=None;profile_reference=None
        for arm_index,arm in enumerate(ARMS):
            need(arm in record['results'],'Missing completed arm: '+arm)
            arm_result=record['results'][arm];collector=arm_result['collector']
            need(collector.get('terminal') is True and collector.get('completed') is True
                 and not collector.get('error') and arm_result['raw_report'].get('valid') is True
                 and len(arm_result['samples'])==4,'Incomplete or failed arm: '+arm)
            arm_dir=folder/arm;data_dir=arm_dir/case['name'];epoch=0x020300D800000001+arm_index
            need(stable_bytes(data_dir/'request.json')==request_data,'Per-arm request bytes changed')
            profile=read(binding['profiles'][arm]['path']);manifest=read(arm_dir/'initial-service-manifest.json')
            need(profile['engine']['context']==profile['backend']['context']==8192
                 and profile['engine']['prefill_chunk']==profile['engine']['max_prefill_tokens']==8192
                 and 'slots' not in profile['engine'] and 'kv_pool_positions' not in profile['engine']
                 and profile['concurrency']==1,'Frozen ordinary one-slot8K profile differs')
            comparable=json.loads(json.dumps(profile))
            need(comparable['engine']['kernel_controls'].pop('HALOGEN_DN_Z_STREAM')==int(arm=='candidate'),
                 'Profile DNZ0/1/0 differs')
            if profile_reference is None:profile_reference=comparable
            need(comparable==profile_reference,'Arm profiles differ beyond DNZ')
            env=manifest['environment'];mode=int(arm=='candidate')
            need(env.get('HALOGEN_DN_Z_STREAM')==str(mode) and env.get('HALOGEN_CTX')=='8192'
                 and env.get('HALOGEN_KV_POOL_POSITIONS')=='8192' and env.get('HALOGEN_MAX_TOK')=='8192'
                 and env.get('HALOGEN_PREFILL_CHUNK')=='8192' and env.get('HALOGEN_PROMPT_CACHE')=='0'
                 and env.get('HGN0203_RAW_ENABLE')==env.get('HGN0203_API_NATIVE_ID')=='1'
                 and not any(key in env for key in ('HALOGEN_EXTERNAL_STREAM','HGN0203_STREAM_CAPTURE',
                     'HGN0203_EXTERNAL_STREAM','HGN0203_STREAM_CONFIG','HGN0203_STREAM_CONFIG_SHA256',
                     'HGN0203_STREAM_SOCKET','HGN0203_STREAM_STATS'))
                 and 'streaming_draft' not in manifest,'Resolved native DNZ/capacity/isolation differs')
            ready=read(folder/(arm+'-launch.ready.json'));verify_ready(ready,8192,binding['profiles'][arm])
            allocation=read(arm_dir/'startup-allocation.json')
            need(allocation==record['startup_allocation_by_arm'][arm]
                 and allocation.get('exact_byte_allocation_claimed') is False,'Native allocation receipt differs')
            weights=read(arm_dir/'weights-integrity.json')
            need(weights==record['weights_identity_by_arm'][arm]
                 and weights['stat_before']==weights['stat_after'],'Weights identity changed within arm')
            signature=(weights['checkpoint_source'],weights['receipt_payload'],weights['receipt'])
            if weight_reference is None:weight_reference=signature
            need(signature==weight_reference,'Weights receipt/source changed between arms')
            rows=[];last_raw=0;request_ids=set();total_enqueues=0
            for ordinal in range(4):
                response_data=stable_bytes(data_dir/f'response-{ordinal}.json');response=json.loads(response_data)
                metrics=response_metrics(response)
                if reference is None:reference=metrics
                require_response_parity(reference,metrics)
                transport=read(data_dir/f'transport-{ordinal}.json');counters=read(data_dir/f'dnz-counter-{ordinal}.json')
                timing=validate_transport(transport,counters,mode)
                need(timing['qpc_start_ns']>=previous_global_end,'Global HTTP requests overlap/reorder')
                previous_global_end=timing['qpc_end_ns'];minimum=min(minimum,timing['runtime_minimum_observed_gib'])
                total_enqueues+=timing['DNZ_successful_enqueues']
                journal=stable_bytes(data_dir/'journals'/f'capture-{epoch:016x}-{ordinal}.bin')
                events=validator.read_capture(journal,ordinal,epoch)
                raw=validator.validate(events,response,request=request,require_cold=True)
                need(raw['native_slot']==0 and events[0]['raw_before']>=last_raw,'RAW native slot/order differs')
                last_raw=events[-1]['raw_after']
                need(raw['request_id']==metrics['native_request_id'] and raw['request_id'] not in request_ids,
                     'RAW causal ID reused or differs')
                request_ids.add(raw['request_id']);rates=raw_rates(raw,transport)
                saved_raw=read(data_dir/f'raw-sample-{ordinal}.json')
                need(all(saved_raw.get(k)==v for k,v in raw.items())
                     and saved_raw.get('journal_sha256')==sha(journal)
                     and saved_raw.get('response_sha256')==sha(response_data),'Saved RAW sample differs from recomputation')
                saved_sample=read(data_dir/f'sample-{ordinal}.json')
                need(saved_sample['response_sha256']==sha(response_data)
                     and saved_sample['request_sha256']==sha(request_data)
                     and saved_sample['output_sha256']==metrics['output_sha256']
                     and saved_sample['scoped']==metrics['scoped']
                     and saved_sample['timings']==response['timings'] and saved_sample['usage']==response['usage']
                     and saved_sample==arm_result['samples'][ordinal]
                     and counters==arm_result['DNZ_counter_samples'][ordinal],
                     'Saved sample source accounting or terminal copy differs')
                parity=read(data_dir/f'parity-{ordinal}.json')
                need(parity.get('exact_UTF8_finish_counts_scopes') is True
                     and parity.get('native_token_ID_sequence_parity') is False,'Saved parity scope differs')
                rows.append(dict(ordinal=ordinal,phase='warmup_excluded' if ordinal==0 else 'measured',
                    **metrics,**timing,**rates,response_sha256=sha(response_data),journal_sha256=sha(journal)))
            need(read(data_dir/'arm-disarmed.json').get('after_responses')==4,'Closed epoch disarm receipt missing')
            need(not list((data_dir/'journals').glob('*fault*')),'Retained RAW fault marker found')
            all_rows[arm]=rows;counter_totals[arm]=total_enqueues
            report['arms'][arm]=summarize_arm(rows)
            for phase in ('prefill','decode'):
                for suffix,key in (('mid',''),('lower','_lower'),('upper','_upper')):
                    expected=report['arms'][arm]['RAW_'+phase+'_tok_s'+key]['mean']
                    need(arm_result['raw_report']['arithmetic_means'][phase+'_raw_tps_'+suffix]==expected,
                         'Saved complete-cohort RAW arithmetic mean differs')
            log=stable_bytes(data_dir/'native-cost-log.txt');trace=trace_parser.qualify_trace(
                log.decode('utf-8'),arm_result['samples'],'gate')
            saved_trace=read(data_dir/'mtp-cost-trace.json')
            need(all(saved_trace.get(k)==v for k,v in trace.items())
                 and saved_trace['log']['sha256']==sha(log)
                 and trace['acceptance_independently_reconciled'] is False
                 and trace['exact_independent_full_accepted_counter_proof'] is False,
                 'Native trace/scoped mapping or honest acceptance limitations differ')
        need(reference['output_sha256']==sha(stable_bytes(folder/'reference-output.utf8')),
             'Exact original BEFORE-warmup reference bytes differ')
        final=read(folder/'ready-left-online.json');verify_ready(final,32768,binding['normal_profile'])
        need(final==record['final'] and final['outer']['port']==8840,'Saved normal Ready differs from terminal handle')
        transition=read(binding['transition']);package=Path(binding['normal_source_manifest']['path']).parent.parent
        baseline=transition['baseline']['files']
        for relative,digest in baseline.items():
            target=(package/relative).resolve()
            need(target.is_relative_to(package.resolve()) and file_pin(target)['sha256']==digest,
                 'Normal baseline file was not exactly restored: '+relative)
        restored_artifacts(record.get('artifacts',[]))
        report.update(rates_verified=True,status='complete_offline_checks_passed',samples=all_rows,
            actual_input_tokens=2048,output_tokens=128,capacity_context=8192,
            measured_per_arm=3,warmup_excluded=True,DNZ_counter_totals_including_warmup=counter_totals,
            runtime_minimum_observed_gib=minimum,resource_policy=dict(startup_physical=30,startup_commit=131,
                each_request_physical_commit=22,runtime_physical_commit=18),
            resource_observation_scope='Pinned completed admission flow plus saved runtime samples; not an independent continuous peak trace.',
            normal_baseline_files_rehashed=len(baseline),normal_saved_ready_on8840=True,
            normal_live_liveness_rechecked=False,output_sha256=reference['output_sha256'],
            exact_UTF8_finish_counts_reported_scopes=True,
            native_acceptance_scope='Reported API head/lookup/grammar counters; no independent all-neural reconstruction')
        report['comparison']={}
        for key in ('RAW_prefill_tok_s','RAW_decode_tok_s','HTTP_seconds'):
            before,candidate,after=(report['arms'][a][key]['mean'] for a in ARMS)
            stock=(before+after)/2
            report['comparison'][key]=dict(stock_bookend_mean=stock,candidate=candidate,
                candidate_minus_stock=candidate-stock,candidate_vs_stock_percent=(candidate/stock-1)*100,
                stock_after_vs_before_percent=(after/before-1)*100)
    except (ValueError,KeyError,TypeError,OSError,StopIteration) as error:
        report.update(status='partial_inapplicable_or_failed_no_headline',rates_verified=False,arms={})
        report['errors'].append(type(error).__name__+': '+str(error))
        report['campaign_error']=record.get('error')
        report['restoration_error']=record.get('restoration_error')
        report['terminal_saved_flags']={key:record.get(key) for key in ('terminal','completed','restored','phase')}
    need(file_pin(handle_path)==report['handle'],'Terminal handle changed during offline audit')
    return report


def markdown(report):
    lines=['# DNZ private8K capacity: offline evidence audit','',
        'Actual 2,048 input / 128 output tokens. Normal restoration remains a saved terminal observation.','']
    if report.get('status')=='partial_later_normal_recovered_verified':
        return '\n'.join(lines+['No qualified performance values or DNZ speed difference.',
            'The campaign completed one excluded stock warmup and zero measurements. The DNZ candidate never started.',
            'Admission failed at the 22 GiB request-entry check before the first measured request.',
            'The original restoration attempt also failed. Its terminal:false/completed:false/restored:false flags remain unchanged.',
            'A separately pinned Root recovery finished afterward: normal 32K serving on port 8840 and an authenticated READY functional smoke are verified in saved evidence.',
            f"All {report['executed_pins_verified']} execution pins and {report['normal_baseline_files_rehashed']} restored baseline files were rehashed. The excluded warmup RAW/HTTP/counter evidence validates, but its rates remain excluded.",
            'Native output-ID sequence and complete neural acceptance are not independently reconstructed. No new benchmark, process or hardware access occurred in this audit.',''])
    if not report['rates_verified']:
        return '\n'.join(lines+['No qualified headline values. The cohort is partial, inapplicable or failed.',
                                  '',*report['errors'],''])
    lines+=['| Arm | RAW Prefill tok/s | RAW Decode tok/s | WholeHTTP mean s | API reported head acceptance |',
            '| --- | ---: | ---: | ---: | ---: |']
    for arm in ARMS:
        row=report['arms'][arm];scope=row['acceptance_scopes']['head']
        acceptance=f"{scope['accepted']}/{scope['drafted']}"+(f" = {scope['rate']*100:.2f}%" if scope['rate'] is not None else ' = undefined')
        lines.append(f"| {arm} | {row['RAW_prefill_tok_s']['mean']:.6f} | {row['RAW_decode_tok_s']['mean']:.6f} | {row['HTTP_seconds']['mean']:.6f} | {acceptance} |")
    lines+=['','Each mean excludes its warmup and includes all three measurements. RAW bracket endpoints and all samples remain in JSON.',
        'API phase clocks are not used for the table. DNZ counts successful submissions, not tokens or independently completed GPU jobs.',
        'Exact UTF8/finish/count and reported scoped-counter parity passes. Native-ID sequence and complete neural acceptance are not independently reconstructed.',
        'Independent terminal review remains required; this helper alone does not authorize promotion.','']
    return '\n'.join(lines)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit',action='store_true');parser.add_argument('--terminal-confirmed',action='store_true')
    parser.add_argument('--handle',type=Path);parser.add_argument('--output',type=Path)
    parser.add_argument('--binding-sha',default=EXPECTED_BINDING_SHA)
    parser.add_argument('--recovery-receipt',type=Path)
    parser.add_argument('--recovery-sha',default=EXPECTED_RECOVERY_SHA)
    args=parser.parse_args()
    if not args.audit:
        print(json.dumps(dict(source_only=True,campaign_evidence_read=False)));return 0
    need(args.terminal_confirmed and args.handle is not None and args.output is not None,
         'Explicit audit, terminal confirmation, handle and fresh output are required')
    need(not args.output.exists(),'Fresh audit export directory required')
    report=(audit_partial_recovered(args.handle,args.recovery_receipt,confirmed=True,
                binding_sha=args.binding_sha,recovery_sha=args.recovery_sha)
            if args.recovery_receipt is not None else
            audit_terminal(args.handle,confirmed=True,binding_sha=args.binding_sha))
    args.output.mkdir(parents=True)
    (args.output/'audit.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    (args.output/'audit.md').write_text(markdown(report),encoding='utf-8')
    print(json.dumps(dict(status=report['status'],rates_verified=report['rates_verified'],
                         headline_qualified=False,output=str(args.output))))
    return 0 if report['rates_verified'] or report.get('audit_passed') is True else 2


if __name__=='__main__':raise SystemExit(main())
