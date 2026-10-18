"""Finite warmup plus one synchronized two-request native C2 measurement."""
from hashlib import sha256
import json
import math
from pathlib import Path
import threading
import time

from . import benchmark_http, benchmark_suite, small_c2_recipe as recipe, smoke_http


def _bound_request(row, provider, validator):
    request = provider.request_for(row)
    if validator is not None:
        validator(row, request)
    body = json.dumps(request, ensure_ascii=False, allow_nan=False,
                      separators=(',', ':')).encode('utf-8')
    if len(body) > 262144:
        raise ValueError('request_body_limit')
    prompt = request['messages'][0]['content'].encode('utf-8')
    return request, dict(prompt_bytes=len(prompt),
        prompt_sha256=sha256(prompt).hexdigest().upper(),
        request_bytes=len(body), request_sha256=sha256(body).hexdigest().upper())


def _record(row, observation, metadata, root, assessor, definition):
    correctness, errors = assessor(row, observation, definition)
    observation.update(suite_correctness=correctness, suite_errors=errors,
                       prompt_record=metadata)
    artifact = benchmark_suite._persist(root, row['ordinal'], observation)
    answer = observation.get('visible_answer') or ''
    answer_bytes = answer.encode('utf-8') if isinstance(answer, str) else b''
    gufo = (observation.get('usage') or {}).get('gufo') or {}
    if not isinstance(gufo, dict):
        gufo = {}
    row.update(status='failed' if errors else 'completed',
        attempted=observation.get('post_attempted') is True,
        artifact=artifact, correctness=correctness, errors=errors,
        metrics=observation.get('metrics') or {},
        matched_evidence=observation.get('matched_evidence'),
        validation_errors=observation.get('validation_errors') or [],
        unavailable_metrics=observation.get('unavailable_metrics') or [],
        finish_reason=observation.get('finish_reason'),
        submitted_monotonic=observation.get('submitted_monotonic'),
        completed_monotonic=observation.get('completed_monotonic'),
        requested_logical_concurrency=gufo.get('requested_logical_concurrency'),
        resident_requests_at_admission=gufo.get('resident_requests_at_admission'),
        physical_execution_width=gufo.get('physical_execution_width'),
        execution_plan=gufo.get('execution_plan'),
        output_bytes=len(answer_bytes),
        output_sha256=sha256(answer_bytes).hexdigest().upper(), **metadata)
    return errors


def _request(request, row, api_key, deadline, cancel):
    return benchmark_http.request_once(port=smoke_http.PORT, api_key=api_key,
        path='/v1/chat/completions', request=request,
        limits=benchmark_http.RequestLimits(max_prompt_tokens=256,
            max_completion_tokens=row['output_budget'], cache_policy='cold'),
        deadline=deadline, cancel=cancel)


def _pair_summary(rows):
    pair = rows[1:]
    starts = [row.get('submitted_monotonic') for row in pair]
    ends = [row.get('completed_monotonic') for row in pair]
    timed = all(type(value) in (int, float) and math.isfinite(value)
                for value in starts + ends)
    overlap = timed and max(starts) < min(ends)
    duration = max(ends) - min(starts) if timed else None
    counts = [row.get('metrics', {}).get('completion_tokens') for row in pair]
    complete = all(row['status'] == 'completed' for row in pair)
    throughput = (sum(counts) / duration if complete and timed and duration > 0
                  and all(type(count) is int and count > 0 for count in counts)
                  else None)
    native = complete and all(
        type(row.get('requested_logical_concurrency')) is int
        and row['requested_logical_concurrency'] == 2
        and type(row.get('physical_execution_width')) is int
        and row['physical_execution_width'] == 2
        and row.get('execution_plan') == 'batched-w2' for row in pair)
    return dict(client_http_overlap=bool(overlap),
        native_batch_evidence_both=bool(native),
        concurrency_qualified=bool(overlap and native),
        first_http_start_monotonic=min(starts) if timed else None,
        last_http_finish_monotonic=max(ends) if timed else None,
        group_end_to_end_output_tokens_per_second=throughput,
        group_throughput_basis='native_output_tokens_over_first_submit_to_last_finish',
        common_window_decode_tokens_per_second=None)


def start_suite(*, profile_id: str, evidence_dir: Path, api_key: str,
                startup_deadline: float, lifetime_deadline: float,
                cancel: threading.Event | None = None, recipe_provider=None,
                request_validator=None, response_assessor=None):
    """Return SmokeTask; exactly one warmup and one two-request wave, no retry."""
    task = smoke_http.SmokeTask(cancel if cancel is not None else threading.Event())
    provider = recipe_provider if recipe_provider is not None else recipe
    validator = request_validator if request_validator is not None else provider.validate_request
    assessor = response_assessor if response_assessor is not None else provider.assess

    def work():
        started = time.monotonic()
        result = dict(success=False, error=None, profile_id=profile_id,
            post_attempted=False, rows=[], readiness={}, pair={},
            semantic_status='not_reviewed',
            timestamps=dict(worker_started_monotonic=started))
        workers = []
        launch = None
        try:
            definition = provider.recipe_definition(profile_id)
            if ([row['case'] for row in definition['schedule']]
                    != ['WARMUP', 'code_a', 'proof_a'] or
                    definition['max_requests'] != 3):
                raise ValueError('manifest_changed')
            result['recipe'] = definition
            result['recipe_sha256'] = sha256(provider.recipe_json(profile_id).encode()).hexdigest().upper()
            result['rows'] = [dict(row, status='not_run') for row in definition['schedule']]
            if (not isinstance(api_key, str) or not api_key or len(api_key) > 256
                    or not api_key.isascii()
                    or any(ch.isspace() or ord(ch) < 33 or ord(ch) == 127 for ch in api_key)):
                raise ValueError('invalid_private_key')
            if not all(type(value) in (int, float) and math.isfinite(value)
                       for value in (startup_deadline, lifetime_deadline)):
                raise ValueError('invalid_deadline')
            root = Path(evidence_dir).resolve(strict=True)
            if not root.is_dir() or Path(evidence_dir).is_symlink():
                raise ValueError('invalid_evidence_dir')
            lifetime = min(lifetime_deadline, started + 600)
            benchmark_suite._ready(api_key, min(startup_deadline, lifetime, started + 480),
                                   task.cancel, result['readiness'])

            warmup = result['rows'][0]
            warm_request, warm_metadata = _bound_request(warmup, provider, validator)
            smoke_http._check(min(time.monotonic() + 60, lifetime), task.cancel)
            warm_observation = _request(warm_request, warmup, api_key,
                                        min(time.monotonic() + 60, lifetime), task.cancel)
            result['post_attempted'] |= warm_observation.get('post_attempted') is True
            warm_errors = _record(warmup, warm_observation, warm_metadata,
                                  root, assessor, definition)
            if warm_errors:
                raise smoke_http.SmokeError(warm_errors[0])

            pair = []
            for row in result['rows'][1:]:
                request, metadata = _bound_request(row, provider, validator)
                pair.append((row, request, metadata))
            launch = threading.Barrier(3)
            observations = [None, None]
            worker_errors = [None, None]

            def wait_for_launch():
                launch.wait(timeout=max(0, min(5, lifetime - time.monotonic())))

            def run_one(index, row, request):
                try:
                    wait_for_launch()
                    deadline = min(time.monotonic() + 60, lifetime)
                    observation = _request(request, row, api_key, deadline, task.cancel)
                    observations[index] = observation
                    _, errors = assessor(row, observation, definition)
                    if errors:
                        task.cancel.set()
                except BaseException as exc:
                    worker_errors[index] = type(exc).__name__
                    task.cancel.set()

            for index, (row, request, _) in enumerate(pair):
                worker = threading.Thread(target=run_one, args=(index, row, request),
                                          daemon=True, name=f'gufo-small-c2-{index}')
                workers.append(worker)
                worker.start()
            wait_for_launch()
            # request_once uses the shared cancellation event and a finite deadline.
            # Keep task.done unset until both request workers have exited.
            for worker in workers:
                while worker.is_alive():
                    worker.join(timeout=.25)
                    if time.monotonic() >= lifetime:
                        task.cancel.set()
            pair_errors = []
            for index, (row, _, metadata) in enumerate(pair):
                observation = observations[index]
                if observation is None:
                    row.update(status='failed', attempted=False,
                               errors=['worker_' + (worker_errors[index] or 'missing_result')])
                    pair_errors.extend(row['errors'])
                    continue
                result['post_attempted'] |= observation.get('post_attempted') is True
                try:
                    pair_errors.extend(_record(row, observation, metadata,
                                               root, assessor, definition))
                except BaseException as exc:
                    row.update(status='failed', attempted=observation.get('post_attempted') is True,
                               evidence_write_error=type(exc).__name__,
                               errors=['evidence_write_failed'])
                    pair_errors.append('evidence_write_failed')
            result['pair'] = _pair_summary(result['rows'])
            if pair_errors:
                task.cancel.set()
                raise smoke_http.SmokeError(pair_errors[0])
            result['success'] = True
        except smoke_http.SmokeError as exc:
            result['error'] = exc.code
            task.cancel.set()
        except BaseException as exc:
            result['error'] = 'suite_' + type(exc).__name__
            task.cancel.set()
        finally:
            # Handles launch/record failures after a worker has started.
            if launch is not None:
                launch.abort()
            for worker in workers:
                while worker.is_alive():
                    worker.join(timeout=.25)
                    if time.monotonic() >= min(lifetime_deadline, started + 600):
                        task.cancel.set()
            rows = result['rows']
            result['counts'] = dict(completed=sum(row['status'] == 'completed' for row in rows),
                failed=sum(row['status'] == 'failed' for row in rows),
                not_run=sum(row['status'] == 'not_run' for row in rows))
            result['semantic_status'] = 'semantic_review_pending' if result['success'] else 'incomplete'
            result['timestamps']['worker_finished_monotonic'] = time.monotonic()
            try:
                task.result = smoke_http._redact(result, api_key) if isinstance(api_key, str) and api_key else result
            finally:
                task.done.set()

    threading.Thread(target=work, daemon=True, name='gufo-small-c2-suite').start()
    return task
