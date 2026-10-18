"""Finite sequential suite, bounded evidence, no ownership or launch policy."""
from hashlib import sha256
import json
import math
from pathlib import Path
import statistics
import threading
import time

from . import benchmark_http, benchmark_recipes as recipes, operator_store, smoke_http


def _ready(api_key, deadline, cancel, metadata):
    metadata.update(ready_polls=0, ready_connect_timeouts=0)
    for _ in range(240):
        smoke_http._check(deadline,cancel)
        metadata['ready_polls'] += 1
        try:
            status, _, body, _, _, _ = smoke_http._exchange('GET','/ready',None,api_key,deadline,cancel)
        except smoke_http.SmokeError as exc:
            if exc.code not in ('transport_ConnectionRefusedError','connect_timeout'): raise
            if exc.code=='connect_timeout': metadata['ready_connect_timeouts'] += 1
            cancel.wait(min(2,max(0,deadline-time.monotonic())))
            continue
        metadata['last_ready_status'] = status
        response=smoke_http._json_object(body)
        if status==503 and isinstance(response.get('error'),dict) and response['error'].get('code')=='not_ready':
            cancel.wait(min(2,max(0,deadline-time.monotonic())))
            continue
        if status!=200: raise smoke_http.SmokeError(f'ready_http_{status}')
        if response.get('status')!='ready' or response.get('model')!=smoke_http.MODEL:
            raise smoke_http.SmokeError('wrong_ready_model')
        break
    else:
        raise smoke_http.SmokeError('ready_poll_limit')
    smoke_http._check(deadline,cancel)
    status, _, body, _, _, _ = smoke_http._exchange('GET','/v1/models',None,api_key,deadline,cancel)
    metadata['models_status']=status
    if status!=200: raise smoke_http.SmokeError(f'models_http_{status}')
    models=smoke_http._json_object(body).get('data')
    if not isinstance(models,list) or len(models)!=1 or not isinstance(models[0],dict) or models[0].get('id')!=smoke_http.MODEL:
        raise smoke_http.SmokeError('wrong_models_identity')


def _persist(evidence_dir, ordinal, observation):
    path=evidence_dir/f'request-{ordinal:03d}.json'
    if path.exists() or path.is_symlink() or path.resolve().parent!=evidence_dir:
        raise ValueError('request_artifact_exists_or_escapes')
    # Match atomic_json's formatting, including Windows newline expansion, without
    # constructing another giant serialized copy of the client's bounded evidence.
    size=2
    for piece in json.JSONEncoder(sort_keys=True,indent=2,allow_nan=False).iterencode(observation):
        size += len(piece.encode('utf-8')) + piece.count('\n')
        if size>16*1024*1024: raise ValueError('request_artifact_limit')
    operator_store.atomic_json(path,observation)
    record=operator_store.artifact_record(path)
    if not 0 < record['stamp'][1] <=16*1024*1024: raise ValueError('request_artifact_limit')
    return dict(name=path.name,size_bytes=record['stamp'][1],sha256=record['sha256'])


def _assess(row, observation, definition):
    metrics=observation.get('metrics',{})
    correctness=recipes.validate_answer(row['case'],observation)
    errors=[]
    prompt=metrics.get('logical_prompt_tokens')
    if type(prompt) is not int or prompt<0:
        errors.append('prompt_count_unknown')
    elif prompt>definition['max_prompt_tokens'] or prompt+row['output_budget']>definition['context_tokens']:
        errors.append('context_overflow')
    if row['case']=='PP1':
        new=metrics.get('new_prefill_tokens')
        if (type(new) is not int or abs(new-row['target_prompt_tokens'])>32
                or metrics.get('cached_prompt_tokens')!=0 or metrics.get('completion_tokens')!=1):
            errors.append('calibration_miss')
            correctness['calibration_miss']=True
    if row['case']=='CALIBRATION' and metrics.get('completion_tokens')!=1:
        errors.append('calibration_output_count')
    if correctness['state']=='failed': errors.append('known_correctness_failure')
    if not observation.get('success'): errors.insert(0,observation.get('error') or 'request_failed')
    if errors: correctness['state']='failed'
    return correctness, errors


def _summarize(rows, *, matched=False):
    groups={}
    for row in rows:
        key=(row['kind'],row['case'],row['mode'],row['target_prompt_tokens'],row['cache_prompt'])
        groups.setdefault(key,[]).append(row)
    result=[]
    for key, members in groups.items():
        metric_names=sorted({k for row in members for k in row.get('metrics',{})})
        metrics={}
        for name in metric_names:
            values=[row.get('metrics',{}).get(name) for row in members if row['status']=='completed'
                and (not matched or row.get('matched_evidence',{}).get('quality_failed') is False)]
            values=[v for v in values if type(v) in (int,float) and math.isfinite(v)]
            metrics[name]=dict(n=len(values),mean=statistics.mean(values) if values else None,
                sample_sd=statistics.stdev(values) if len(values)>=2 else None)
        group=dict(kind=key[0],case=key[1],mode=key[2],target_prompt_tokens=key[3],
            cache_prompt=key[4],ordinals=[r['ordinal'] for r in members],
            valid=sum(r['status']=='completed' for r in members),failed=sum(r['status']=='failed' for r in members),
            not_run=sum(r['status']=='not_run' for r in members),metrics=metrics)
        if matched:
            group['metrics_basis']='quality_eligible_completed_rows'
            group['quality_failed']=sum(r.get('matched_evidence',{}).get('quality_failed') is True for r in members)
            group['quality_eligible']=sum(r['status']=='completed' and
                r.get('matched_evidence',{}).get('quality_failed') is False for r in members)
        result.append(group)
    return result


def start_suite(*, profile_id: str, evidence_dir: Path, api_key: str,
                startup_deadline: float, lifetime_deadline: float,
                cancel: threading.Event | None = None, recipe_provider=None,
                request_validator=None, response_assessor=None):
    task=smoke_http.SmokeTask(cancel if cancel is not None else threading.Event())
    provider=recipe_provider if recipe_provider is not None else recipes
    assessor=response_assessor if response_assessor is not None else _assess
    matched=response_assessor is not None

    def work():
        result=dict(success=False,error=None,profile_id=profile_id,post_attempted=False,rows=[],readiness={},
            semantic_status='not_reviewed',common_window_decode_tokens_per_second=None,
            common_window_decode_reason='native_window_counters_unavailable',
            timestamps=dict(worker_started_monotonic=time.monotonic()))
        try:
            definition=provider.recipe_definition(profile_id)
            result['recipe']=definition
            result['recipe_sha256']=sha256(provider.recipe_json(profile_id).encode()).hexdigest().upper()
            result['rows']=[dict(row,status='not_run') for row in definition['schedule']]
            if (not isinstance(api_key,str) or not api_key or len(api_key)>256 or not api_key.isascii()
                    or any(c.isspace() or ord(c)<33 or ord(c)==127 for c in api_key)):
                raise ValueError('invalid_private_key')
            if not isinstance(task.cancel,threading.Event): raise ValueError('invalid_cancel')
            if not all(type(x) in (int,float) and math.isfinite(x) for x in (startup_deadline,lifetime_deadline)):
                raise ValueError('invalid_deadline')
            root=Path(evidence_dir).resolve(strict=True)
            if not root.is_dir() or Path(evidence_dir).is_symlink(): raise ValueError('invalid_evidence_dir')
            started=result['timestamps']['worker_started_monotonic']
            lifetime=min(lifetime_deadline,started+600)
            _ready(api_key,min(startup_deadline,lifetime,started+480),task.cancel,result['readiness'])
            calibration=[]
            for row in result['rows']:
                deadline=min(time.monotonic()+60,lifetime)
                smoke_http._check(deadline,task.cancel)
                request=provider.request_for(row,calibration)
                request_bytes=json.dumps(request,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode('utf-8')
                if len(request_bytes)>262144: raise ValueError('request_body_limit')
                prompt=request['messages'][0]['content'].encode('utf-8')
                metadata=dict(prompt_bytes=len(prompt),prompt_sha256=sha256(prompt).hexdigest().upper(),
                    request_bytes=len(request_bytes),request_sha256=sha256(request_bytes).hexdigest().upper())
                if request_validator is not None:
                    request_validator(row,request)
                observation=benchmark_http.request_once(port=smoke_http.PORT,api_key=api_key,
                    path='/v1/chat/completions',request=request,
                    limits=benchmark_http.RequestLimits(max_prompt_tokens=min(definition['max_prompt_tokens'],definition['context_tokens']-row['output_budget']),
                        max_completion_tokens=row['output_budget'],cache_policy='allow' if row['cache_prompt'] else 'cold'),
                    deadline=deadline,cancel=task.cancel)
                result['post_attempted'] |= observation.get('post_attempted') is True
                correctness,errors=assessor(row,observation,definition)
                if row['case']=='CALIBRATION' and not errors:
                    count=observation['metrics']['logical_prompt_tokens']
                    if calibration and count<=calibration[0]:
                        errors.append('invalid_calibration_counts'); correctness['state']='failed'
                    else: calibration.append(count)
                observation.update(suite_correctness=correctness,suite_errors=errors,prompt_record=metadata)
                try:
                    artifact=_persist(root,row['ordinal'],observation)
                except BaseException as exc:
                    row.update(status='failed',attempted=observation.get('post_attempted') is True,
                        evidence_write_error=type(exc).__name__,correctness=dict(state='failed'),
                        metrics=observation.get('metrics',{}),errors=['evidence_write_failed'],**metadata)
                    raise smoke_http.SmokeError('evidence_write_failed') from exc
                row.update(status='failed' if errors else 'completed',artifact=artifact,correctness=correctness,
                    metrics=observation.get('metrics',{}),finish_reason=observation.get('finish_reason'),
                    unavailable_metrics=observation.get('unavailable_metrics',[]),validation_errors=observation.get('validation_errors',[]),
                    errors=errors,**metadata)
                if matched:
                    row['matched_evidence']=observation.get('matched_evidence')
                text=observation.get('visible_answer','').encode('utf-8')
                row.update(output_bytes=len(text),output_sha256=sha256(text).hexdigest().upper())
                if row['case']=='CACHE':
                    gufo=(observation.get('usage') or {}).get('gufo',{})
                    row['cache_observation']='hit' if (row['metrics'].get('cached_prompt_tokens',0)>0 and gufo.get('cache_hit') is True) else 'miss'
                del observation
                if errors: raise smoke_http.SmokeError(errors[0])
            result['success']=True
        except smoke_http.SmokeError as exc:
            result['error']=exc.code
        except BaseException as exc:
            result['error']='suite_'+type(exc).__name__
        finally:
            rows=result['rows']
            result['counts']=dict(valid=sum(r['status']=='completed' for r in rows),
                failed=sum(r['status']=='failed' for r in rows),not_run=sum(r['status']=='not_run' for r in rows))
            if matched:
                result['counts'].update(completed=result['counts']['valid'],
                    quality_failed=sum(r.get('matched_evidence',{}).get('quality_failed') is True for r in rows),
                    invalid_metric=sum(r.get('matched_evidence',{}).get('fatal_kind') == 'native' for r in rows),
                    transport_failed=sum(r.get('matched_evidence',{}).get('fatal_kind') == 'transport' for r in rows))
                valid_long=[r for r in rows if r['status']=='completed' and r['case']=='LONG']
                correct_long=[r for r in valid_long if r.get('matched_evidence',{}).get('quality_failed') is False]
                draft_active=any(r['matched_evidence']['proposed'] > 0 for r in valid_long)
                result['claims']=dict(mtp_draft_path_exercised=draft_active if result.get('recipe',{}).get('speculative') is True else None,
                    useful_accepted_speculation_observed=(any(r['matched_evidence']['accepted'] > 0 for r in valid_long)
                        if result.get('recipe',{}).get('speculative') is True else None),
                    sustained_256_rows=[r['ordinal'] for r in valid_long if r['matched_evidence']['sustained_256_eligible']],
                    correct_sustained_256_rows=[r['ordinal'] for r in correct_long if r['matched_evidence']['sustained_256_eligible']])
            try:
                result['groups']=_summarize(rows,matched=matched)
            except BaseException as exc:
                result.update(success=False,error='summary_'+type(exc).__name__,groups=[])
            result['semantic_status']='semantic_review_pending' if result['success'] else 'incomplete'
            result['timestamps']['worker_finished_monotonic']=time.monotonic()
            # Raw/Base64 evidence was already sanitized by the client and has been
            # released. Only the compact scalar result crosses back to Guardian.
            try:
                task.result=smoke_http._redact(result,api_key) if isinstance(api_key,str) and api_key else result
            finally:
                task.done.set()

    threading.Thread(target=work,daemon=True,name='gufo-benchmark-suite').start()
    return task
