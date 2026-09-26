"""Sole fixed MTP HTTP worker and native response evidence checks."""
from copy import deepcopy
from hashlib import sha256
import json
import math
from pathlib import Path
import re
import threading
import time

from . import benchmark_http, benchmark_suite, smoke_http


def validate_response(observation):
    """Validate native counters and structure; semantics require human review."""
    errors = []
    result = dict(state='failed', errors=errors, lookup_source=None,
                  draft_tokens=None, draft_tokens_accepted=None,
                  mtp_acceptance=None, unaccepted_proposals=None)
    if not isinstance(observation, dict) or observation.get('success') is not True:
        errors.append('transport_failed')
        return result
    usage, timings = observation.get('usage'), observation.get('timings')
    if not isinstance(usage, dict) or not isinstance(timings, dict):
        errors.append('native_counters_missing')
        return result
    gufo, details = usage.get('gufo'), usage.get('prompt_tokens_details')
    if not isinstance(gufo, dict) or not isinstance(details, dict):
        errors.append('native_cache_fields_missing')
        return result

    def integer(source, name, *, lower=0):
        value = source.get(name)
        if type(value) is not int or value < lower:
            errors.append('invalid_'+name)
            return None
        return value

    proposed = integer(usage, 'draft_tokens', lower=1)
    accepted = integer(usage, 'draft_tokens_accepted', lower=1)
    timing_proposed = integer(timings, 'draft_n', lower=1)
    timing_accepted = integer(timings, 'draft_n_accepted', lower=1)
    if proposed is not None and accepted is not None and (
            accepted > proposed or timing_proposed != proposed or timing_accepted != accepted):
        errors.append('draft_counters_disagree')
    if proposed and accepted and accepted <= proposed:
        ratio = accepted / proposed
        result.update(draft_tokens=proposed, draft_tokens_accepted=accepted,
                      mtp_acceptance=ratio, unaccepted_proposals=proposed-accepted)
        reported = observation.get('metrics', {}).get('mtp_acceptance')
        if (type(reported) not in (int, float) or not math.isfinite(reported)
                or abs(reported-ratio) > 1e-12):
            errors.append('acceptance_ratio_disagrees')

    pair = ('lookup_n', 'lookup_n_accepted')
    present = [key in timings for key in pair]
    if present == [False, False]:
        result['lookup_source'] = 'omitted_when_zero_in_pinned_emitter'
    elif present == [True, True] and all(type(timings[key]) is int and timings[key] == 0 for key in pair):
        result['lookup_source'] = 'explicit_zero'
    else:
        errors.append('lookup_not_zero')

    prompt = integer(usage, 'prompt_tokens', lower=1)
    completion = integer(usage, 'completion_tokens', lower=1)
    total = integer(usage, 'total_tokens', lower=1)
    prefill = integer(gufo, 'prefill_tokens', lower=1)
    timing_prompt = integer(timings, 'prompt_n', lower=1)
    predicted = integer(timings, 'predicted_n', lower=1)
    cache_fields = ((usage, 'cached_tokens'), (details, 'cached_tokens'),
                    (timings, 'cache_n'), (gufo, 'cache_restore_bytes'),
                    (gufo, 'cache_disk_queued_bytes'),
                    (gufo, 'cache_common_prefix_tokens'),
                    (gufo, 'cache_shared_bytes'),
                    (gufo, 'cache_shared_prefix_snapshots'),
                    (gufo, 'cache_shared_prefix_bytes'))
    for source, name in cache_fields:
        value = integer(source, name)
        if value is not None and value != 0:
            errors.append('nonzero_'+name)
    if gufo.get('cache_hit') is not False or gufo.get('cache_disk_hit') is not False:
        errors.append('cache_hit_not_false')
    if (prompt is not None and (prompt > 243 or prefill != prompt or timing_prompt != prompt)):
        errors.append('prompt_count_disagrees')
    if (completion is not None and (completion > 64 or predicted != completion)):
        errors.append('completion_count_disagrees')
    if (prompt is not None and completion is not None and total != prompt+completion):
        errors.append('total_count_disagrees')
    for name in ('physical_execution_width', 'requested_logical_concurrency',
                 'resident_requests_at_admission'):
        width = integer(gufo, name, lower=1)
        if width is not None and width != 1:
            errors.append('concurrency_'+name)

    models = observation.get('observed_models')
    if (not isinstance(models, list) or not models or any(
            type(model) is not str or model != smoke_http.MODEL for model in models)):
        errors.append('response_model_mismatch')
    if observation.get('finish_reason') != 'stop' or observation.get('truncated') is True:
        errors.append('finish_not_stop')
    if observation.get('reasoning_content') != '' or observation.get('tool_calls') != []:
        errors.append('reasoning_or_tools')
    text = observation.get('visible_answer')
    if not isinstance(text, str):
        errors.append('visible_text_invalid')
    else:
        text = text.replace('\r\n', '\n').strip()
        lines = text.split('\n')
        if (len(lines) != 2 or any(not line or line != line.strip() for line in lines)
                or any(char in text for char in ('\ufffd', '<|', '|>', '```'))
                or any(ord(char) < 32 and char != '\n' for char in text)
                or any(re.match(r'^(?:[-*+#>]\s|\d+[.)]\s|#{1,6}\s)', line) for line in lines)
                or any(token in text for token in ('**', '__', '`'))
                or any(re.search(r'</?[A-Za-z][^<>]*>', line) for line in lines)
                or any(re.search(r'(?<!\w)\*\S.*?\*', line) for line in lines)
                or any(re.search(r'(?<!\w)_(?=\S).*?_(?!\w)', line) for line in lines)
                or lines[0].startswith('DE:') or lines[1].startswith('EN:')):
            errors.append('bilingual_structure_invalid')
    if not errors:
        result['state'] = 'semantic_review_pending'
    return result


def start_stage(*, evidence_dir: Path, api_key: str, startup_deadline: float,
                lifetime_deadline: float, cancel: threading.Event | None = None):
    """Bounded readiness followed by exactly one POST, with raw evidence saved."""
    from . import mtp_stage
    mtp_stage.validate_request(mtp_stage.request_fixture())
    if not isinstance(api_key, str) or not api_key or not api_key.isascii():
        raise ValueError('invalid_private_key')
    if not all(type(value) in (int, float) and math.isfinite(value)
               for value in (startup_deadline, lifetime_deadline)):
        raise ValueError('invalid_deadline')
    root = Path(evidence_dir).resolve(strict=True)
    if not root.is_dir() or Path(evidence_dir).is_symlink():
        raise ValueError('invalid_evidence_dir')
    task = smoke_http.SmokeTask(cancel if cancel is not None else threading.Event())

    def work():
        started = time.monotonic()
        result = dict(success=False, error=None, profile_id=mtp_stage.PROFILE_ID,
                      post_attempted=False, readiness={}, rows=[],
                      semantic_status='not_reviewed',
                      timestamps={'worker_started_monotonic': started})
        try:
            lifetime = min(lifetime_deadline, started+600)
            benchmark_suite._ready(api_key, min(startup_deadline, lifetime, started+480),
                                   task.cancel, result['readiness'])
            deadline = min(time.monotonic()+60, lifetime)
            smoke_http._check(deadline, task.cancel)
            request = mtp_stage.request_fixture()
            mtp_stage.validate_request(request)
            # This sole local copy is never exposed to a caller between proof and send.
            submitted = deepcopy(request)
            mtp_stage.validate_request(submitted)
            observation = benchmark_http.request_once(port=smoke_http.PORT, api_key=api_key,
                path='/v1/chat/completions', request=submitted,
                limits=benchmark_http.RequestLimits(512, 64, 'cold'),
                deadline=deadline, cancel=task.cancel)
            result['post_attempted'] = observation.get('post_attempted') is True
            assessment = validate_response(observation)
            body = json.dumps(submitted, sort_keys=True, separators=(',', ':'),
                              ensure_ascii=True, allow_nan=False).encode('utf-8')
            observation.update(stage_assessment=assessment,
                prompt_record=dict(rendered_input_bytes=243, input_token_upper_bound=243,
                    request_bytes=len(body), request_sha256=sha256(body).hexdigest().upper()))
            try:
                artifact = benchmark_suite._persist(root, 0, observation)
            except BaseException as error:
                raise smoke_http.SmokeError('evidence_write_failed') from error
            row = dict(status='completed' if assessment['state'] == 'semantic_review_pending' else 'failed',
                       artifact=artifact, metrics=observation.get('metrics', {}),
                       assessment=assessment, finish_reason=observation.get('finish_reason'),
                       post_attempted=result['post_attempted'])
            result['rows'] = [row]
            result['semantic_status'] = assessment['state']
            result['success'] = row['status'] == 'completed'
            if not result['success']:
                result['error'] = 'mtp_response_validation_failed'
        except smoke_http.SmokeError as error:
            result['error'] = error.code
        except BaseException as error:
            result['error'] = 'stage_'+type(error).__name__
        finally:
            result['timestamps']['worker_finished_monotonic'] = time.monotonic()
            try:
                task.result = smoke_http._redact(result, api_key)
            finally:
                task.done.set()

    threading.Thread(target=work, daemon=True, name='gufo-mtp-stage').start()
    return task
