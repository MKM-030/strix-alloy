"""Private guarded Reddit GUFO workload. ``validate`` never starts a model.

Each ``run`` owns one table/process and consumes its own permanent attempt marker.
The exact measured messages, including GUFO's prefix reply, are retained for replay.
"""
import argparse
import base64
from dataclasses import asdict
from datetime import datetime, timezone
from hashlib import sha256
import importlib
import json
import os
from pathlib import Path
import socket
import sys
import threading
import time

from . import (benchmark_http, model_identity, no_snapshot_260k_run as prior,
               operator_probe, operator_store, pp_remeasure_native as native,
               smoke_guard, smoke_http, smoke_store)
from .operator_policy import (Frame, _base_valid, _frame_reasons, _identity,
                              GPU_FIELDS, MAX_PRELAUNCH_AGE_SECONDS,
                              MAX_SAMPLE_AGE_SECONDS)

ROOT = smoke_store.ROOT
SOURCE = ROOT/'sources'/'gufo-windows'
UPSTREAM = SOURCE/'tools'/'gufo'/'model_bench'/'llm.py'
BENCH = SOURCE/'docs'/'models'/'qwen3.8-flash-next'/'artifacts'/'bench.json'
SOURCE_COMMIT = 'cff564964e8506c0abb3e530cecb55332187ac6c'
UPSTREAM_SHA = 'FE01466A0FEA0C6419587086F0D69FE292944EC20BB4CE05D54AF3A2A46FE2C9'
BENCH_SHA = 'A8C70E48BE58FF68E54651014030DEB6298589E42FEE0530E6463BD467CD9FF3'
BUILD = ROOT/'build'/'gufo-hip-10.2'
BINARY = BUILD/'gufo.exe'
BINARY_SHA = 'E7F5B899C54C747EE5038C0598016394D2A70F25EE69AFBB1E02859FD223D943'
PROFILE = 'gufo-reddit-native-20260928-v1'
REPORTS = ROOT/'reports'
REVIEW = REPORTS/'reddit-benchmark-task-review-20260928.json'
GIB = 1 << 30
MIB = 1 << 20
REQUEST_LIMIT = 4*MIB
RESPONSE_LIMIT = MIB
MAX_CALLS = 15
CONTEXT = 133760
DEPTHS = (0, 131072)
PROMPT = 2048
OUTPUT = 128
CALIBRATION_WORDS = 3000
TABLES = {'mixed': 'prose', 'repetitive': 'repetition'}
LIMITS = dict(gpu_peak_bytes=78*GIB, host_peak_bytes=12*GIB,
              shared_physical_allowance_bytes=20*GIB, commit_peak_bytes=90*GIB)
FRESH_PHYSICAL = 43.564664300*GIB
FRESH_COMMIT = 102*GIB
REQUEST_SECONDS = 1800
LIFETIME_SECONDS = 7200


def digest(data):
    return sha256(data).hexdigest().upper()


def upstream():
    if prior.file_digest(UPSTREAM) != UPSTREAM_SHA:
        raise ValueError('upstream_generator_changed')
    if str(SOURCE/'tools') not in sys.path:
        sys.path.insert(0, str(SOURCE/'tools'))
    return importlib.import_module('gufo.model_bench.llm')


def turn_text(new_target, ratio, task, depth, attempt):
    if task not in TABLES.values() or depth not in DEPTHS or not 0 <= attempt < 4:
        raise ValueError('workload_not_bound')
    return upstream().turn_prompt(new_target, ratio, task=task, depth=depth,
                                  repetition=0, attempt=attempt)


def request_body(messages, max_tokens, *, stream):
    if max_tokens not in (1, 8, 16, 128) or type(stream) is not bool:
        raise ValueError('unbound_output_budget')
    if not isinstance(messages, list) or not 1 <= len(messages) <= 3 or any(
            not isinstance(m, dict) or set(m) != {'role', 'content'} or
            m['role'] not in ('user', 'assistant') or not isinstance(m['content'], str)
            for m in messages):
        raise ValueError('invalid_messages')
    request = dict(model=smoke_http.MODEL, messages=messages, max_tokens=max_tokens,
                   temperature=0, stream=stream)
    if stream:
        request['stream_options'] = {'include_usage': True}
    body = json.dumps(request, ensure_ascii=False, separators=(',', ':'),
                      allow_nan=False).encode('utf-8')
    if len(body) > REQUEST_LIMIT:
        raise ValueError('request_body_limit')
    return request, body


def decode_body(body):
    return json.loads(body.decode('utf-8'))


def count_errors(metrics, depth, prompt=PROMPT, output=OUTPUT):
    errors = []
    for field, target in (('cached_prompt_tokens', depth),
                          ('new_prefill_tokens', prompt)):
        value = metrics.get(field)
        if type(value) is not int or abs(value-target) > max(32, int(target*.005)):
            errors.append('cache_outside_tolerance' if field == 'cached_prompt_tokens'
                          else 'prefill_outside_tolerance')
    if metrics.get('completion_tokens') != output:
        errors.append('output_count_invalid')
    logical = metrics.get('logical_prompt_tokens')
    cached = metrics.get('cached_prompt_tokens')
    fresh = metrics.get('new_prefill_tokens')
    if (type(logical) is not int or type(cached) is not int or type(fresh) is not int
            or logical != cached+fresh or logical+output > CONTEXT):
        errors.append('logical_count_or_capacity_invalid')
    if not isinstance(metrics.get('engine_decode_ms'), (int, float)) or metrics['engine_decode_ms'] <= 0:
        errors.append('decode_timing_invalid')
    if not isinstance(metrics.get('engine_prefill_ms'), (int, float)) or metrics['engine_prefill_ms'] <= 0:
        errors.append('prefill_timing_invalid')
    if not isinstance(metrics.get('engine_tg_tokens_per_second'), (int, float)) or metrics['engine_tg_tokens_per_second'] <= 0:
        errors.append('decode_rate_invalid')
    return errors


def fixed_argv(secret):
    argv = smoke_guard.fixed_argv(secret)
    argv[0] = str(BINARY)
    for flag, value in (('--context', str(CONTEXT)), ('--max-tokens', str(OUTPUT)),
                        ('--sessions', '1'), ('--max-connections', '1'),
                        ('--max-pending', '1'), ('--max-pending-per-client', '1'),
                        ('--max-request-bytes', str(REQUEST_LIMIT)),
                        ('--request-timeout-ms', str(REQUEST_SECONDS*1000)),
                        ('--max-output-bytes', str(RESPONSE_LIMIT)),
                        ('--speculative', 'mtp')):
        argv[argv.index(flag)+1] = value
    argv += ['--mtp-model', str(model_identity.MTP_SIDECAR.path),
             '--draft-tokens', '7', '--min-draft-tokens', '1',
             '--mtp-policy', 'survival', '--mtp-draft-vocab', 'latin', '--prompt-lookup']
    return argv


def source_identity():
    # The original adapter checks the clean pinned tree separately from the
    # large artifact and model-header validation.
    operator_store.source_identity()


def static_binding(table):
    if table not in TABLES:
        raise ValueError('unknown_table')
    source_identity()
    for path, expected in ((UPSTREAM, UPSTREAM_SHA), (BENCH, BENCH_SHA), (BINARY, BINARY_SHA)):
        if path.is_symlink() or prior.file_digest(path) != expected:
            raise ValueError('bound_artifact_changed:'+path.name)
    model = model_identity.validate_ar4k_model(smoke_store.FIRST_SHARD)
    sidecar = model_identity.validate_mtp_sidecar(model.first_shard)
    records = native.probe_records()
    # Full payload hashes are not claimed for GGUF; validated metadata and
    # stable stamps are the pre-existing model identity contract.
    return dict(profile=PROFILE, table=table, task=TABLES[table], source=SOURCE_COMMIT,
        binary_sha256=BINARY_SHA, upstream_sha256=UPSTREAM_SHA, bench_sha256=BENCH_SHA,
        controller_sha256=prior.file_digest(__file__), probe_artifacts=records,
        model_revision=model.revision, sidecar=sidecar,
        shard_stamps=[operator_store.stamp(model.first_shard.parent/p.filename)
                      for p in model_identity.AR4K_PINS.shards],
        workload=dict(context=CONTEXT, depths=DEPTHS, prompt=PROMPT, output=OUTPUT,
                      max_calls_per_table=MAX_CALLS, max_calibration_attempts_per_depth=4,
                      calibration='independent_per_fresh_table_process',
                      prefix_reply_replay='frozen_gufo_text'),
        limits=LIMITS, draft_ceiling_source='GUFO source default; contributor cap not published')


def review_binding(binding):
    canonical = json.dumps(binding, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    return digest(canonical)


class Profile(prior.Profile):
    @property
    def envelope(self):
        return dict(stage=self.stage, **LIMITS,
                    kind='live_stop_ceilings_not_reservations')


class Policy(prior.Policy):
    def profile_from_manifest(self, manifest):
        if manifest.get('profile') != PROFILE or manifest['binding']['table'] != self.stage:
            raise ValueError('policy_profile_mismatch')
        return Profile(self.stage, **LIMITS)

    def _reasons(self, profile, base, frame, now, now_utc, max_age):
        if profile != Profile(self.stage, **LIMITS) or not _base_valid(base):
            return ['invalid_private_profile_or_baseline']
        reasons = _frame_reasons(frame, now=now, now_utc=now_utc, max_age=max_age)
        if reasons:
            return reasons
        if _identity(frame.snapshot) != base.identity or frame.query_start < base.last_end:
            return ['adapter_changed_or_sample_before_baseline']
        s = frame.snapshot
        reasons = []
        if s['available_physical_bytes'] < 24*GIB:
            reasons.append('runtime_physical_floor')
        if s['commit_headroom_bytes'] < 12*GIB:
            reasons.append('commit_floor')
        if base.available_min-s['available_physical_bytes'] > 32*GIB:
            reasons.append('physical_envelope')
        if s['host_committed_bytes']-base.committed_max > 90*GIB:
            reasons.append('commit_envelope')
        for key, maximum, allowance in zip(GPU_FIELDS, base.gpu_max,
                                           (78*GIB, 20*GIB, 78*GIB)):
            if s[key]-maximum > allowance:
                reasons.append('gpu_envelope:'+key)
        return reasons

    def admission_reasons(self, profile, base, frame, *, now, now_utc):
        reasons = super().admission_reasons(profile, base, frame, now=now, now_utc=now_utc)
        if not reasons:
            snapshot = frame.snapshot
            if snapshot['available_physical_bytes'] < FRESH_PHYSICAL:
                reasons.append('scenario_fresh_physical_below_43_564664300_gib')
            if snapshot['commit_headroom_bytes'] < FRESH_COMMIT:
                reasons.append('scenario_fresh_commit_below_102_gib')
        return reasons


class Store:
    def __init__(self, table):
        if table not in TABLES:
            raise ValueError('unknown_table')
        self.stage = table
        self.EVIDENCE = REPORTS/f'reddit-native-{table}-20260928-v1-runs'
        self.BUILD = BUILD
        self.cached_manifest = None
        self.original = None

    def verify_static(self):
        binding = static_binding(self.stage)
        if any((self.EVIDENCE/name).exists() for name in ('attempt.json', 'incomplete.json')):
            raise ValueError('table_already_attempted_or_incomplete')
        if not REVIEW.exists() or REVIEW.is_symlink() or REVIEW.stat().st_size > MIB:
            raise ValueError('review_missing')
        review = json.loads(REVIEW.read_text(encoding='utf-8'))
        if review != {'decision': 'approved', 'binding_sha256': review_binding(binding),
                      'table': self.stage}:
            raise ValueError('independent_review_binding_missing')
        artifact_paths = [UPSTREAM, BENCH, BINARY, Path(__file__),
                          *(item['stamp'][0] for item in binding['probe_artifacts']),
                          *(item[0] for item in binding['shard_stamps']),
                          binding['sidecar']['path']]
        artifact_stamps = [operator_store.stamp(path) for path in artifact_paths]
        for expected in [*binding['shard_stamps'], binding['sidecar']['stamp'],
                         *(item['stamp'] for item in binding['probe_artifacts'])]:
            if operator_store.stamp(expected[0]) != expected:
                raise ValueError('bound_artifact_changed_during_validation')
        self.EVIDENCE.mkdir(parents=True, exist_ok=True)
        log = self.EVIDENCE/f'prelaunch-baseline-{time.time_ns()}.jsonl'
        frames = []
        deadline = time.monotonic()+30
        for _ in range(11):
            if time.monotonic()+operator_probe.MAX_QUERY_SECONDS > deadline:
                raise TimeoutError('fresh_baseline_timeout')
            if frames:
                time.sleep(max(0, frames[-1].query_start+operator_probe.QUERY_INTERVAL-time.monotonic()))
            start = time.monotonic()
            snapshot = native.collect()
            end = time.monotonic()
            if end-start > operator_probe.MAX_QUERY_SECONDS:
                raise TimeoutError('fresh_baseline_query_timeout')
            frame = Frame(snapshot, start, end, datetime.now(timezone.utc))
            operator_probe.log_frame(log, frame, 'fresh_baseline')
            frames.append(frame)
        self.original = prior.variation_baseline(frames)
        manifest = dict(profile=PROFILE, binding=binding, review_sha256=prior.file_digest(REVIEW),
                        artifact_stamps=artifact_stamps,
                        operator=dict(original_baseline=asdict(self.original),
                                      fresh_baseline_log=str(log),
                                      fresh_baseline_log_sha256=prior.file_digest(log)))
        self.cached_manifest = manifest
        return manifest

    def load_original_operator_baseline(self):
        if self.original is None:
            raise ValueError('fresh_baseline_missing')
        return self.original

    def recheck_static(self, manifest, *, current_run=None):
        if manifest != self.cached_manifest:
            raise ValueError('binding_changed')
        source_identity()
        for expected in manifest['artifact_stamps']:
            if operator_store.stamp(expected[0]) != expected:
                raise ValueError('bound_artifact_stamp_changed:'+Path(expected[0]).name)
        if prior.file_digest(REVIEW) != manifest['review_sha256']:
            raise ValueError('review_changed')
        if prior.file_digest(manifest['operator']['fresh_baseline_log']) != manifest['operator']['fresh_baseline_log_sha256']:
            raise ValueError('baseline_evidence_changed')
        attempt, latch = self.EVIDENCE/'attempt.json', self.EVIDENCE/'incomplete.json'
        if current_run is None:
            if attempt.exists() or latch.exists():
                raise ValueError('table_already_attempted_or_incomplete')
        else:
            run = Path(current_run)
            if (run.resolve().parent != self.EVIDENCE.resolve() or run.is_symlink()
                    or operator_store.read_json(attempt).get('run') != str(run)
                    or operator_store.read_json(latch).get('run') != str(run)):
                raise ValueError('current_run_marker_mismatch')

    def begin_run(self, run_dir, manifest, baseline):
        self.recheck_static(manifest)
        if Path(run_dir).resolve().parent != self.EVIDENCE.resolve() or asdict(baseline) != manifest['operator']['original_baseline']:
            raise ValueError('run_baseline_or_path_mismatch')
        native.exclusive_json(self.EVIDENCE/'attempt.json', dict(run=str(run_dir), table=self.stage))
        native.exclusive_json(self.EVIDENCE/'incomplete.json', dict(run=str(run_dir), phase='before_create', original_baseline=asdict(baseline)))
        native.exclusive_json(Path(run_dir)/'manifest.json', manifest)

    def finish_run(self, run_dir, result):
        if operator_store.read_json(self.EVIDENCE/'attempt.json').get('run') != str(run_dir):
            raise ValueError('attempt_marker_changed')
        operator_store.atomic_json(Path(run_dir)/'result.json', result)
        if result.get('cleanup_confirmed') is True:
            (self.EVIDENCE/'incomplete.json').unlink()

    def build_argv(self, secret):
        if self.cached_manifest is None:
            raise ValueError('static_not_validated')
        return fixed_argv(secret)


def _exchange(body, secret, deadline, cancel, *, stream):
    """Bounded loopback transport with upstream's X-Client-ID and owned deadline."""
    if len(body) > REQUEST_LIMIT:
        raise smoke_http.SmokeError('request_body_limit')
    smoke_http._check(deadline, cancel)
    head = (f'POST /v1/chat/completions HTTP/1.1\r\nHost: 127.0.0.1:8836\r\n'
            f'Authorization: Bearer {secret}\r\nX-Client-ID: model-bench\r\n'
            f'Content-Type: application/json\r\n'
            f'Accept: {"text/event-stream" if stream else "application/json"}\r\n'
            f'Connection: close\r\nContent-Length: {len(body)}\r\n\r\n').encode('ascii')
    started = time.monotonic()
    reader = None
    parts = []
    status = None
    headers = {}
    try:
        with socket.create_connection(('127.0.0.1', 8836), timeout=.25) as sock:
            sock.settimeout(.25)
            sock.sendall(head)
            view = memoryview(body)
            while view:
                smoke_http._check(deadline, cancel)
                sent = sock.send(view[:65536])
                if sent == 0:
                    raise smoke_http.SmokeError('request_send_closed')
                view = view[sent:]
            reader = smoke_http._Reader(sock, deadline, cancel, wire_limit=RESPONSE_LIMIT+16384)
            raw_head = reader.until(b'\r\n\r\n', 16384)
            lines = raw_head[:-4].decode('iso-8859-1').split('\r\n')
            pieces = lines[0].split(' ', 2)
            if len(pieces) < 2 or not pieces[0].startswith('HTTP/1.'):
                raise smoke_http.SmokeError('malformed_status')
            status = int(pieces[1])
            for line in lines[1:]:
                if ':' not in line:
                    raise smoke_http.SmokeError('malformed_header')
                name, value = line.split(':', 1)
                name = name.strip().lower()
                if name in headers:
                    raise smoke_http.SmokeError('duplicate_header')
                headers[name] = value.strip()
            transfer = headers.get('transfer-encoding')
            if (transfer is not None and transfer.lower() != 'chunked') or (transfer is not None and 'content-length' in headers):
                raise smoke_http.SmokeError('ambiguous_response_framing')
            for part, arrived in smoke_http._body_chunks(reader, headers, body_limit=RESPONSE_LIMIT):
                parts.append((part, arrived))
            smoke_http._check(deadline, cancel)
            return status, headers, b''.join(p for p, _ in parts), started, time.monotonic(), parts
    except (OSError, ValueError, smoke_http.SmokeError) as error:
        failure = error if isinstance(error, smoke_http.SmokeError) else smoke_http.SmokeError('transport_'+type(error).__name__)
        failure.raw_response = bytes(reader.raw) if reader is not None else b''
        failure.body_parts, failure.status, failure.headers = parts, status, headers
        failure.submitted = started
        raise failure from None


def observe(messages, max_tokens, secret, deadline, cancel, *, stream, label):
    request, body = request_body(messages, max_tokens, stream=stream)
    record = dict(label=label, request=request, request_body_base64=base64.b64encode(body).decode('ascii'),
                  request_sha256=digest(body), request_bytes=len(body), success=False,
                  status=None, response_headers=None, raw_response_base64=None,
                  raw_response_sha256=None, body_parts=[], submitted_monotonic=None,
                  completed_monotonic=None, error=None)
    raw, parts = b'', []
    partial = False
    try:
        status, headers, raw, start, end, parts = _exchange(body, secret, deadline, cancel, stream=stream)
        record.update(status=status, response_headers=headers, submitted_monotonic=start,
                      completed_monotonic=end)
        expected_type = 'text/event-stream' if stream else 'application/json'
        if status != 200 or headers.get('content-type', '').split(';', 1)[0].strip().lower() != expected_type:
            raise smoke_http.SmokeError('response_status_or_type')
        parsed = (smoke_http.parse_sse_response(parts, start)
                  if stream else benchmark_http._parse_json_response(raw, '/v1/chat/completions'))
        metrics, errors, unavailable = smoke_http._validate_usage(parsed['usage'], parsed['timings'],
            max_prompt_tokens=CONTEXT, max_completion_tokens=max_tokens, cache_policy='allow')
        metrics['http_duration_ms'] = 1000*(end-start)
        metrics['first_visible_content_ms'] = parsed['first_visible_content_ms']
        benchmark_http._rates(metrics, errors, pp1=False)
        if parsed['finish_reason'] not in ('stop', 'length') or any(
                model != smoke_http.MODEL for model in parsed['observed_models']):
            errors.append('completion_identity_or_finish_invalid')
        if stream and parsed['first_visible_content_ms'] is None:
            errors.append('ttft_missing')
        if not parsed['observed_models']:
            errors.append('model_identity_missing')
        if metrics.get('logical_prompt_tokens') is not None and metrics['logical_prompt_tokens']+max_tokens > CONTEXT:
            errors.append('capacity_exceeded')
        record.update(parsed=parsed, metrics=metrics, validation_errors=errors,
                      unavailable_metrics=unavailable, success=not errors)
        if errors:
            record['error'] = 'validation_failed'
    except smoke_http.SmokeError as error:
        record['error'] = error.code
        if getattr(error, 'raw_response', None):
            partial = True
            parts = getattr(error, 'body_parts', [])
            record['status'] = getattr(error, 'status', None)
            record['response_headers'] = getattr(error, 'headers', None)
            record['submitted_monotonic'] = getattr(error, 'submitted', None)
    except Exception as error:
        record['error'] = type(error).__name__+':'+str(error)
    finally:
        record['completed_monotonic'] = record['completed_monotonic'] or time.monotonic()
        if partial:
            record['raw_response_omission_reason'] = 'partial_wire_body_offsets_unavailable'
            raw = b''
        secret_bytes = secret.encode('ascii')
        clean = raw.replace(secret_bytes, b'*'*len(secret_bytes))
        record['raw_response_base64'] = base64.b64encode(clean).decode('ascii')
        record['raw_response_sha256'] = digest(clean)
        joined = b''.join(part for part, _ in parts).replace(secret_bytes, b'*'*len(secret_bytes))
        offset = 0
        for part, arrived in parts:
            clean_part = joined[offset:offset+len(part)]
            offset += len(part)
            record['body_parts'].append(dict(base64=base64.b64encode(clean_part).decode('ascii'),
                                             arrived_monotonic=arrived))
    return smoke_guard._redact(record, secret)


class Session(prior.Session):
    def __init__(self, store, *, api_key, startup_deadline, lifetime_deadline, cancel):
        self.store, self.key = store, api_key
        self.startup_deadline, self.lifetime_deadline, self.cancel = startup_deadline, lifetime_deadline, cancel
        self.done = threading.Event()
        self.result = dict(success=False, error=None, requests=[], table=store.stage,
                           cells={}, calibration=None)
        self.workers = []
        self.thread = threading.Thread(target=self._run, name='reddit-native-session', daemon=True)
        self.thread.start()

    def _call(self, messages, max_tokens, *, stream=True, label):
        if len(self.result['requests']) >= MAX_CALLS:
            raise ValueError('table_generation_limit')
        deadline = min(time.monotonic()+REQUEST_SECONDS, self.lifetime_deadline)
        row = observe(messages, max_tokens, self.key, deadline, self.cancel,
                      stream=stream, label=label)
        self.result['requests'].append(row)
        if not row['success']:
            raise ValueError('request_failed:'+label+':'+str(row['error']))
        return row

    def _run(self):
        try:
            self._ready()
            source = upstream()
            one = self._call([dict(role='user', content='Hi')], 1, label='calibration-hi')
            probe_text = source.synthetic_text(7777, CALIBRATION_WORDS)
            two = self._call([dict(role='user', content=probe_text)], 1, label='calibration-3000')
            if (one['metrics'].get('completion_tokens') != 1
                    or two['metrics'].get('completion_tokens') != 1):
                raise ValueError('calibration_output_count_invalid')
            overhead = one['metrics']['logical_prompt_tokens']-1
            ratio = (two['metrics']['logical_prompt_tokens']-overhead)/CALIBRATION_WORDS
            if not 0 <= overhead <= 256 or not .5 <= ratio <= 10:
                raise ValueError('calibration_invalid')
            self.result['calibration'] = dict(overhead=overhead, ratio=ratio,
                                              probe_text_sha256=digest(probe_text.encode()))
            warm = source.synthetic_text(8888, max(1, round(PROMPT/ratio)))
            self._call([dict(role='user', content=warm)], 16, label='warmup')
            task = TABLES[self.store.stage]
            for depth in DEPTHS:
                accepted = False
                for attempt in range(4):
                    messages = []
                    if depth:
                        prefix_target = depth-overhead-8
                        prefix = source.synthetic_text(1+depth, max(1, round(prefix_target/ratio)))
                        prepared = self._call([dict(role='user', content=prefix)], 8,
                                              stream=False, label=f'd{depth}-a{attempt}-prefix')
                        reply = prepared['parsed']['visible_answer']
                        if not reply or prepared['metrics'].get('completion_tokens') != 8:
                            raise ValueError('prefix_reply_invalid')
                        messages = [dict(role='user', content=prefix),
                                    dict(role='assistant', content=reply)]
                    text = turn_text(PROMPT-overhead, ratio, task, depth, attempt)
                    messages.append(dict(role='user', content=text))
                    row = self._call(messages, OUTPUT, label=f'd{depth}-a{attempt}-measured')
                    errors = count_errors(row['metrics'], depth)
                    row['cell_validation_errors'] = errors
                    # Preserve complete exact request text even on rejected attempts.
                    row['frozen_messages_sha256'] = digest(json.dumps(messages, ensure_ascii=False,
                        separators=(',', ':')).encode('utf-8'))
                    if not errors:
                        self.result['cells'][str(depth)] = dict(status='accepted', attempt=attempt,
                            request_index=len(self.result['requests'])-1, task=task,
                            frozen_messages=messages, frozen_messages_sha256=row['frozen_messages_sha256'],
                            counts=dict(cache_n=row['metrics']['cached_prompt_tokens'],
                                prompt_n=row['metrics']['new_prefill_tokens'],
                                predicted_n=row['metrics']['completion_tokens']),
                            pp=row['metrics'].get('engine_pp_tokens_per_second'),
                            tg=row['metrics'].get('engine_tg_tokens_per_second'),
                            http_duration_ms=row['metrics']['http_duration_ms'])
                        accepted = True
                        break
                    if any(error not in ('cache_outside_tolerance', 'prefill_outside_tolerance') for error in errors):
                        self.result['cells'][str(depth)] = dict(status='failed', attempt=attempt,
                            request_index=len(self.result['requests'])-1, errors=errors)
                        raise ValueError('cell_invalid:'+','.join(errors))
                    total = row['metrics']['new_prefill_tokens']+row['metrics']['cached_prompt_tokens']
                    words = sum(len(m['content'].split()) for m in messages if m['role'] == 'user')
                    ratio = (total-overhead)/words
                    if not .5 <= ratio <= 10:
                        raise ValueError('recalibration_invalid')
                    self.result['calibration'].setdefault('corrections', []).append(
                        dict(depth=depth, attempt=attempt, ratio=ratio))
                if not accepted:
                    self.result['cells'][str(depth)] = dict(status='failed', reason='four_attempts_exhausted')
                    raise ValueError('cell_four_attempts_exhausted:'+str(depth))
            self.result['success'] = True
        except BaseException as error:
            self.result['error'] = type(error).__name__+':'+str(error)
            self.cancel.set()
        finally:
            self.done.set()


class Guardian(prior.Guardian):
    def __init__(self, store):
        self.private_store = store
        smoke_guard._Guardian.__init__(self, store=store, policy_module=Policy(store.stage),
            profile_id=PROFILE, collect=native.collect, argv_builder=store.build_argv,
            http_start=lambda **kw: Session(store, **kw))

    def _result(self):
        result = smoke_guard._Guardian._result(self)
        result.update(table=self.private_store.stage, qualification='reviewed_empirical_trial_only',
                      draft_ceiling='source_default_assumption_not_contributor_command')
        return result


def run(table):
    store = Store(table)
    guardian = Guardian(store)
    class Deadline:
        def deadline(self, resumed_at):
            return resumed_at+LIFETIME_SECONDS
        def on_started(self, *args):
            pass
        def on_ready(self, *args):
            pass
        def poll(self, now):
            if guardian.ready and guardian.http is not None and guardian.http.done.is_set():
                return 'stop' if guardian.http.result.get('success') else None
            return None
        def on_result(self, result):
            pass
    guardian.lifecycle = Deadline()
    result = guardian.run()
    print(json.dumps({k: result.get(k) for k in ('table', 'success', 'failure', 'run',
                                                 'cleanup_confirmed', 'exit_code')}, allow_nan=False))
    return 0 if result['success'] else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description='Guarded private Reddit GUFO table adapter')
    parser.add_argument('action', choices=('validate', 'run'))
    parser.add_argument('table', choices=tuple(TABLES))
    args = parser.parse_args(argv)
    if args.action == 'validate':
        binding = static_binding(args.table)
        print(json.dumps(dict(valid=True, binding=binding,
                              binding_sha256=review_binding(binding),
                              review_path=str(REVIEW)), allow_nan=False))
        return 0
    if os.name != 'nt':
        parser.error('Windows required')
    return run(args.table)


if __name__ == '__main__':
    raise SystemExit(main())
