"""Private, one-attempt adapter for the reviewed no-snapshot two-session trial.

``validate`` is offline. Only ``run`` can create the owned GUFO process.
There are no retry, override, cache, or public qualification switches.
"""
import argparse
import base64
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import threading
import time

from . import (benchmark_http, benchmark_recipes, matched_profile, matched_recipes, model_identity, operator_probe,
               operator_store, pp_remeasure_native as native, smoke_guard,
               smoke_http, smoke_policy, smoke_store)
from .operator_policy import (Baseline, Frame, _base_valid, _frame_reasons, _identity, _series,
                              GPU_FIELDS, MAX_PRELAUNCH_AGE_SECONDS,
                              MAX_SAMPLE_AGE_SECONDS)

ROOT = smoke_store.ROOT
REPORTS = ROOT / 'reports'
BUILD_DIR = ROOT / 'build' / 'gufo-no-snapshot-hip-10.2'
BUILD_RESULT = REPORTS / 'gufo-no-snapshot-build-20260928' / 'build-result.json'
RUNTIME_CLOSURE = REPORTS / 'gufo-no-snapshot-build-20260928' / 'runtime-closure.json'
SOURCE = ROOT / 'engine' / 'gufo-no-snapshot-260k'
SOURCE_COMMIT = '8309dfc150bf0a213f52597abfb5bd80d0ea9c05'
PROFILE = 'gufo-no-snapshot-260k-v1'
GIB = 1 << 30
MIB = 1 << 20
LIMITS = dict(gpu_peak_bytes=86*GIB, host_peak_bytes=4*GIB,
              shared_physical_allowance_bytes=25*GIB, commit_peak_bytes=90*GIB)
REQUEST_MAX = 4*MIB
RESPONSE_MAX = 1*MIB
STAGES = {
    'small': dict(context=4096, max_tokens=1024, request_timeout_ms=60000,
                  lifetime_seconds=600, ids=('arithmetic', 'code_a')),
    'long': dict(context=262144, max_tokens=256, request_timeout_ms=1800000,
                 lifetime_seconds=2400, ids=('long_a', 'long_b')),
}
HEX = re.compile(r'[0-9A-Fa-f]{64}\Z')


def digest(data):
    return sha256(data).hexdigest().upper()


def file_digest(path, *, maximum=None):
    path = Path(path)
    if maximum is not None and path.stat().st_size > maximum:
        raise ValueError('oversized_artifact:' + path.name)
    h = sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(MIB), b''):
            h.update(chunk)
    return h.hexdigest().upper()


def _bound_file(path, expected, *, maximum=None):
    if not isinstance(path, str) or not Path(path).is_absolute() or not isinstance(expected, str) or not HEX.fullmatch(expected):
        raise ValueError('invalid_artifact_pin')
    candidate = Path(path)
    if candidate.is_symlink() or candidate.resolve(strict=True) != candidate:
        raise ValueError('artifact_redirected:' + candidate.name)
    if file_digest(candidate, maximum=maximum) != expected.upper():
        raise ValueError('artifact_changed:' + candidate.name)
    return dict(path=str(candidate), sha256=expected.upper(),
                stamp=operator_store.stamp(candidate))


def _source_identity():
    command = ['git', '-C', str(SOURCE), 'rev-parse', 'HEAD']
    value = subprocess.run(command, capture_output=True, text=True, timeout=10, check=True).stdout.strip()
    dirty = subprocess.run(['git', '-C', str(SOURCE), 'status', '--porcelain'],
                           capture_output=True, text=True, timeout=10, check=True).stdout
    if value != SOURCE_COMMIT or dirty.strip():
        raise ValueError('candidate_source_changed')


def _request(record, stage):
    if not isinstance(record, dict) or set(record) != {'id', 'path', 'sha256', 'body_bytes',
            'native_prompt_tokens', 'rendered_sha256'}:
        raise ValueError('request_schema')
    if record['id'] not in STAGES[stage]['ids']:
        raise ValueError('request_id')
    data_path = Path(record['path'])
    if not data_path.is_absolute() or data_path.is_symlink() or data_path.resolve(strict=True) != data_path:
        raise ValueError('request_path')
    body = data_path.read_bytes()
    if (type(record['body_bytes']) is not int or len(body) != record['body_bytes']
            or not 0 < len(body) <= REQUEST_MAX or digest(body) != record['sha256'].upper()):
        raise ValueError('request_body_changed')
    count = record['native_prompt_tokens']
    if (type(count) is not int or not (259000 <= count <= 260999 if stage == 'long'
                                     else 1 <= count <= 4096-STAGES[stage]['max_tokens'])
            or not isinstance(record['rendered_sha256'], str)
            or not HEX.fullmatch(record['rendered_sha256'])):
        raise ValueError('native_count_record_invalid')
    request = json.loads(body.decode('utf-8'))
    cap = 64 if record['id'] == 'arithmetic' else STAGES[stage]['max_tokens']
    if (not isinstance(request, dict) or request.get('model') != smoke_http.MODEL
            or not isinstance(request.get('messages'), list) or len(request['messages']) != 1
            or request['messages'][0].get('role') != 'user'
            or type(request.get('max_tokens')) is not int or not 1 <= request['max_tokens'] <= cap
            or request.get('temperature') != 0 or request.get('seed') != 42
            or request.get('cache_prompt') is not False or request.get('stream') is not True
            or request.get('stream_options') != {'include_usage': True}
            or request.get('chat_template_kwargs') != {'enable_thinking': False, 'preserve_thinking': False}
            or request.get('tools') is not None or request.get('tool_choice') is not None):
        raise ValueError('request_profile_invalid:' + record['id'])
    if stage == 'long' and count + request['max_tokens'] >= STAGES[stage]['context']:
        raise ValueError('context_clips_output')
    return body


def validate_manifest(path, *, require_review=True):
    path = Path(path)
    if path.is_symlink():
        raise ValueError('stage_manifest_invalid')
    path = path.resolve(strict=True)
    if path.stat().st_size > 2*MIB:
        raise ValueError('stage_manifest_invalid')
    manifest = json.loads(path.read_text(encoding='utf-8'))
    required = {'stage', 'source_commit', 'build_result_path', 'build_result_sha256',
                'runtime_closure_path', 'runtime_closure_sha256', 'binary_path',
                'binary_sha256', 'review_path', 'review_sha256', 'controller_sha256',
                'helper_artifacts', 'requests', 'limits'}
    if not isinstance(manifest, dict) or set(manifest) != required:
        raise ValueError('stage_manifest_schema')
    stage = manifest['stage']
    if stage not in STAGES or manifest['source_commit'] != SOURCE_COMMIT or manifest['limits'] != LIMITS:
        raise ValueError('stage_profile_mismatch')
    if manifest['build_result_path'] != str(BUILD_RESULT) or manifest['runtime_closure_path'] != str(RUNTIME_CLOSURE):
        raise ValueError('build_binding_mismatch')
    if manifest['binary_path'] != str(BUILD_DIR/'gufo.exe'):
        raise ValueError('binary_path_mismatch')
    _source_identity()
    records = [_bound_file(manifest['build_result_path'], manifest['build_result_sha256'], maximum=2*MIB),
               _bound_file(manifest['runtime_closure_path'], manifest['runtime_closure_sha256'], maximum=2*MIB),
               _bound_file(manifest['binary_path'], manifest['binary_sha256'])]
    build = json.loads(BUILD_RESULT.read_text(encoding='utf-8'))
    closure = json.loads(RUNTIME_CLOSURE.read_text(encoding='utf-8'))
    if (not isinstance(build, dict) or not isinstance(closure, dict)
            or build.get('status') != 'built-not-executed'
            or build.get('source_head') != SOURCE_COMMIT
            or not any(item.get('path') == manifest['binary_path'] and
                       item.get('sha256', '').upper() == manifest['binary_sha256'].upper()
                       for item in build.get('binaries', []) if isinstance(item, dict))):
        raise ValueError('build_records_invalid')
    if closure.get('source_commit') != SOURCE_COMMIT:
        raise ValueError('runtime_closure_source_changed')
    expected_executable = closure.get('executable')
    if (not isinstance(expected_executable, dict)
            or not isinstance(expected_executable.get('stamp'), list)
            or expected_executable['stamp'][0] != manifest['binary_path']
            or expected_executable.get('sha256', '').upper() != manifest['binary_sha256'].upper()):
        raise ValueError('runtime_closure_executable_changed')
    dependencies = closure.get('dependencies')
    if not isinstance(dependencies, list) or not dependencies:
        raise ValueError('runtime_closure_dependencies_missing')
    for item in dependencies:
        if (not isinstance(item, dict) or not isinstance(item.get('stamp'), list)
                or len(item['stamp']) != 3 or 'sha256' not in item):
            raise ValueError('runtime_dependency_invalid')
        record = _bound_file(item['stamp'][0], item['sha256'], maximum=256*MIB)
        if record['stamp'] != item['stamp']:
            raise ValueError('runtime_dependency_stamp_changed')
        records.append(record)
    controller = Path(__file__)
    if file_digest(controller) != str(manifest['controller_sha256']).upper():
        raise ValueError('controller_changed')
    helpers = manifest['helper_artifacts']
    if not isinstance(helpers, list) or not helpers:
        raise ValueError('helper_binding_missing')
    for item in helpers:
        if not isinstance(item, dict) or set(item) != {'path', 'sha256'}:
            raise ValueError('helper_binding_invalid')
        records.append(_bound_file(item['path'], item['sha256'], maximum=20*MIB))
    ids = STAGES[stage]['ids']
    if (not isinstance(manifest['requests'], list) or
            tuple(item.get('id') for item in manifest['requests']) != ids):
        raise ValueError('fixed_request_order')
    bodies = [_request(item, stage) for item in manifest['requests']]
    if require_review:
        records.append(_bound_file(manifest['review_path'], manifest['review_sha256'], maximum=2*MIB))
        review = json.loads(Path(manifest['review_path']).read_text(encoding='utf-8'))
        binding = dict(manifest)
        binding.pop('review_path')
        binding.pop('review_sha256')
        bound_sha = digest(json.dumps(binding, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode('utf-8'))
        if (review.get('decision') != 'approved' or review.get('stage_manifest_binding_sha256') != bound_sha
                or review.get('stage') != stage):
            raise ValueError('independent_review_binding_missing')
    model = model_identity.validate_ar4k_model(smoke_store.FIRST_SHARD)
    sidecar = model_identity.validate_mtp_sidecar(model.first_shard)
    return manifest, bodies, records, dict(first_shard=str(model.first_shard),
        revision=model.revision, sidecar=sidecar,
        shard_stamps=[operator_store.stamp(model.first_shard.parent / pin.filename)
                      for pin in model_identity.AR4K_PINS.shards])


@dataclass(frozen=True)
class Profile:
    stage: str
    gpu_peak_bytes: int = LIMITS['gpu_peak_bytes']
    host_peak_bytes: int = LIMITS['host_peak_bytes']
    shared_physical_allowance_bytes: int = LIMITS['shared_physical_allowance_bytes']
    commit_peak_bytes: int = LIMITS['commit_peak_bytes']

    @property
    def envelope(self):
        return dict(stage=self.stage, **LIMITS, kind='live_stop_ceilings_not_reservations')


class Policy:
    def __init__(self, stage):
        self.stage = stage

    def profile_from_manifest(self, manifest):
        if manifest['profile'] != PROFILE or manifest['stage_manifest']['stage'] != self.stage:
            raise ValueError('policy_profile_mismatch')
        return Profile(self.stage)

    stricter_runtime_baseline = staticmethod(smoke_policy.stricter_runtime_baseline)
    owned_inventory_frame = staticmethod(smoke_policy.owned_inventory_frame)

    def _reasons(self, profile, base, frame, now, now_utc, max_age):
        if profile != Profile(self.stage) or not _base_valid(base):
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
        if base.available_min-s['available_physical_bytes'] > profile.host_peak_bytes+profile.shared_physical_allowance_bytes:
            reasons.append('physical_envelope')
        if s['host_committed_bytes']-base.committed_max > profile.commit_peak_bytes:
            reasons.append('commit_envelope')
        for key, maximum, allowance in zip(GPU_FIELDS, base.gpu_max,
                                           (profile.gpu_peak_bytes, profile.shared_physical_allowance_bytes,
                                            profile.gpu_peak_bytes)):
            if s[key]-maximum > allowance:
                reasons.append('gpu_envelope:'+key)
        return reasons

    def frame_numeric_reasons(self, profile, base, frame, *, now, now_utc):
        return self._reasons(profile, base, frame, now, now_utc, MAX_SAMPLE_AGE_SECONDS)

    def admission_reasons(self, profile, base, frame, *, now, now_utc):
        return self._reasons(profile, base, frame, now, now_utc, MAX_PRELAUNCH_AGE_SECONDS)

    def admission_decision(self, profile, base, frame, *, now, now_utc):
        reasons = self.admission_reasons(profile, base, frame, now=now, now_utc=now_utc)
        return dict(allowed=not reasons, reasons=reasons,
                    admission='fresh_observed_headroom_only_no_future_placement_proof')

    def runtime_decision(self, profile, base, frame, owned, *, now, now_utc):
        try:
            scoped = self.owned_inventory_frame(frame, owned)
            reasons = self.frame_numeric_reasons(profile, base, scoped, now=now, now_utc=now_utc)
            proof = scoped.snapshot['owned_inventory_proof']
        except ValueError:
            reasons, proof = ['owned_identity_unverified'], dict(status='unverified')
        return dict(allowed=not reasons, reasons=reasons, owned_inventory_proof=proof)

    def recovery_reasons(self, base, frames):
        reasons = _series(frames)
        if reasons:
            return reasons
        if len(frames) != 5 or not _base_valid(base):
            return ['recovery_count_or_baseline']
        if _identity(frames[0].snapshot) != base.identity or frames[0].query_start < base.last_end:
            return ['adapter_changed_or_sample_before_baseline']
        reasons = []
        for frame in frames:
            s = frame.snapshot
            if s['available_physical_bytes'] < max(24*GIB, base.available_min-GIB):
                reasons.append('physical_not_recovered')
            if s['host_committed_bytes'] > base.committed_max+512*MIB:
                reasons.append('commit_not_recovered')
            if s['commit_headroom_bytes'] < 12*GIB:
                reasons.append('commit_floor')
            for key, maximum in zip(GPU_FIELDS, base.gpu_max):
                if s[key] > maximum+256*MIB:
                    reasons.append('gpu_not_recovered:'+key)
        for key in GPU_FIELDS:
            if max(f.snapshot[key] for f in frames)-min(f.snapshot[key] for f in frames) > 64*MIB:
                reasons.append('recovery_unstable:'+key)
        return list(dict.fromkeys(reasons))


VARIATION_CAPS = {'available_physical_bytes': GIB,
                  'host_committed_bytes': 2*GIB,
                  **{key: 256*MIB for key in GPU_FIELDS}}


def variation_spans(frames):
    return {key: max(f.snapshot[key] for f in frames)-min(f.snapshot[key] for f in frames)
            for key in VARIATION_CAPS}


def variation_baseline(frames):
    errors = _series(frames)
    if errors:
        raise ValueError('baseline_'+errors[0])
    if len(frames) != 11 or not 10 <= frames[-1].query_end-frames[0].query_start <= 30:
        raise ValueError('baseline_duration')
    for key, span in variation_spans(frames).items():
        if span > VARIATION_CAPS[key]:
            raise ValueError('baseline_variation:'+key)
    if any(f.snapshot['available_physical_bytes'] < 24*GIB or
           f.snapshot['commit_headroom_bytes'] < 12*GIB for f in frames):
        raise ValueError('baseline_runtime_floor')
    return Baseline(_identity(frames[0].snapshot),
        min(f.snapshot['available_physical_bytes'] for f in frames),
        max(f.snapshot['host_committed_bytes'] for f in frames),
        tuple(max(f.snapshot[k] for f in frames) for k in GPU_FIELDS),
        frames[0].query_start, frames[-1].query_end)


class Store:
    """One immutable attempt per stage, with a separate retained incomplete latch."""
    def __init__(self, stage_manifest):
        self.path = Path(stage_manifest).resolve(strict=True)
        stage = json.loads(self.path.read_text(encoding='utf-8')).get('stage')
        if stage not in STAGES:
            raise ValueError('unknown_stage')
        self.stage = stage
        self.ID = PROFILE
        self.EVIDENCE = REPORTS / ('no-snapshot-260k-'+stage+'-20260928-v1-runs')
        self.BUILD = BUILD_DIR
        self.cached_manifest = None
        self.cached_bodies = None
        self.original = None

    def verify_static(self):
        stage, bodies, records, model = validate_manifest(self.path)
        if stage['stage'] != self.stage:
            raise ValueError('stage_changed')
        if any((self.EVIDENCE/name).exists() for name in ('attempt.json', 'incomplete.json')):
            raise ValueError('stage_already_attempted_or_incomplete')
        # New candidate, new current-baseline evidence. A prior build's
        # historical baseline does not authenticate this trial.
        baseline_log = self.EVIDENCE/('prelaunch-baseline-'+str(time.time_ns())+'.jsonl')
        frames = []
        deadline = time.monotonic()+30
        for _ in range(11):
            if time.monotonic()+operator_probe.MAX_QUERY_SECONDS > deadline:
                raise TimeoutError('fresh_baseline_timeout')
            if frames:
                time.sleep(max(0, frames[-1].query_start+operator_probe.QUERY_INTERVAL-time.monotonic()))
            started = time.monotonic()
            snapshot = native.collect()  # Synchronous; no untracked bootstrap worker.
            ended = time.monotonic()
            if ended-started > operator_probe.MAX_QUERY_SECONDS:
                raise TimeoutError('fresh_baseline_query_timeout')
            frame = Frame(snapshot, started, ended, datetime.now(timezone.utc))
            operator_probe.log_frame(baseline_log, frame, 'fresh_baseline')
            frames.append(frame)
        original = variation_baseline(frames)
        self.original = original
        manifest = dict(profile=PROFILE, source=SOURCE_COMMIT, stage_manifest=stage,
                        stage_manifest_sha256=file_digest(self.path), artifacts=records,
                        model=model, operator=dict(original_baseline=asdict(original),
                            fresh_baseline_log=str(baseline_log),
                            fresh_baseline_log_sha256=file_digest(baseline_log)),
                        limits=dict(LIMITS),
                        interpretation='live stop ceilings; empirical run, not capacity proof')
        self.cached_manifest = manifest
        self.cached_bodies = bodies
        return manifest

    def load_original_operator_baseline(self):
        if self.original is None:
            raise ValueError('fresh_baseline_missing')
        return self.original

    def recheck_static(self, manifest, *, current_run=None):
        if manifest != self.cached_manifest or file_digest(self.path) != manifest['stage_manifest_sha256']:
            raise ValueError('stage_manifest_changed')
        _source_identity()
        for record in manifest['artifacts']:
            if operator_store.stamp(record['path']) != record['stamp']:
                raise ValueError('bound_artifact_stamp_changed')
        if file_digest(manifest['operator']['fresh_baseline_log']) != manifest['operator']['fresh_baseline_log_sha256']:
            raise ValueError('fresh_baseline_evidence_changed')
        stage = manifest['stage_manifest']
        for item, body in zip(stage['requests'], self.cached_bodies):
            if Path(item['path']).read_bytes() != body:
                raise ValueError('request_body_changed')
        for item in manifest['model']['shard_stamps']:
            if operator_store.stamp(item[0]) != item:
                raise ValueError('model_shard_changed')
        if operator_store.stamp(model_identity.MTP_SIDECAR.path) != manifest['model']['sidecar']['stamp']:
            raise ValueError('mtp_changed')
        attempt, latch = self.EVIDENCE/'attempt.json', self.EVIDENCE/'incomplete.json'
        if current_run is None:
            if attempt.exists() or latch.exists():
                raise ValueError('stage_already_attempted_or_incomplete')
        else:
            run = Path(current_run)
            if (run.resolve().parent != self.EVIDENCE.resolve() or run.is_symlink()
                    or operator_store.read_json(attempt).get('run') != str(run)
                    or operator_store.read_json(latch).get('run') != str(run)
                    or operator_store.read_json(run/'manifest.json') !=
                       json.loads(json.dumps(manifest, allow_nan=False))):
                raise ValueError('current_run_marker_mismatch')

    def begin_run(self, run_dir, manifest, baseline):
        self.recheck_static(manifest)
        if (Path(run_dir).resolve().parent != self.EVIDENCE.resolve()
                or asdict(baseline) != manifest['operator']['original_baseline']):
            raise ValueError('run_baseline_or_path_mismatch')
        # Exclusive creates make consumption of this stage irreversible and visible.
        native.exclusive_json(self.EVIDENCE/'attempt.json',
                              dict(run=str(run_dir), stage=self.stage, profile=PROFILE))
        native.exclusive_json(self.EVIDENCE/'incomplete.json',
                              dict(run=str(run_dir), phase='before_create', original_baseline=asdict(baseline)))
        native.exclusive_json(Path(run_dir)/'manifest.json', manifest)
        for item, body in zip(manifest['stage_manifest']['requests'], self.cached_bodies):
            destination = Path(run_dir)/('request-'+item['id']+'.json')
            with destination.open('xb') as stream:
                stream.write(body)
                stream.flush()
                os.fsync(stream.fileno())

    def finish_run(self, run_dir, result):
        if operator_store.read_json(self.EVIDENCE/'attempt.json').get('run') != str(run_dir):
            raise ValueError('attempt_marker_changed')
        operator_store.atomic_json(Path(run_dir)/'result.json', result)
        if result.get('cleanup_confirmed') is True:
            (self.EVIDENCE/'incomplete.json').unlink()

    def build_argv(self, secret):
        if self.cached_manifest is None:
            raise ValueError('stage_not_validated')
        config = STAGES[self.stage]
        argv = matched_profile.build_argv(matched_recipes.PROFILE_MTP_D3, secret)
        argv[0] = str(BUILD_DIR/'gufo.exe')
        for flag, value in (('--sessions', '2'), ('--context', str(config['context'])),
                            ('--max-tokens', str(config['max_tokens'])),
                            ('--max-request-bytes', str(REQUEST_MAX)),
                            ('--request-timeout-ms', str(config['request_timeout_ms'])),
                            ('--max-connections', '4'), ('--max-pending', '2'),
                            ('--max-pending-per-client', '2')):
            if flag in argv:
                argv[argv.index(flag)+1] = value
            else:
                argv.extend((flag, value))
        if '--cache-disk-bytes' in argv or '--cache-disk-staging-bytes' in argv:
            raise ValueError('unexpected_disk_cache_flag')
        return argv


def _large_exchange(path, body, key, deadline, cancel):
    """Only private 4 MiB loopback POST; reuse the bounded parser primitives."""
    if path != '/v1/chat/completions' or len(body) > REQUEST_MAX:
        raise smoke_http.SmokeError('request_body_limit')
    smoke_http._check(deadline, cancel)
    head = (f'POST {path} HTTP/1.1\r\nHost: 127.0.0.1:8836\r\n'
            f'Authorization: Bearer {key}\r\nConnection: close\r\n'
            f'Accept: text/event-stream\r\nContent-Type: application/json\r\n'
            f'Content-Length: {len(body)}\r\n\r\n').encode('ascii')
    submitted = time.monotonic()
    reader = None
    parts, status, headers = [], None, {}
    try:
        with socket.create_connection(('127.0.0.1', 8836), timeout=.25) as sock:
            sock.settimeout(.25)
            sock.sendall(head)
            view = memoryview(body)
            while view:
                smoke_http._check(deadline, cancel)
                count = sock.send(view[:65536])
                if count == 0:
                    raise smoke_http.SmokeError('request_send_closed')
                view = view[count:]
            reader = smoke_http._Reader(sock, deadline, cancel,
                                         wire_limit=RESPONSE_MAX+16384)
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
            total = 0
            for part, arrived in smoke_http._body_chunks(reader, headers, body_limit=RESPONSE_MAX):
                total += len(part)
                if total > RESPONSE_MAX:
                    raise smoke_http.SmokeError('response_body_limit')
                parts.append((part, arrived))
            smoke_http._check(deadline, cancel)
            return status, headers, b''.join(p for p, _ in parts), submitted, time.monotonic(), parts
    except (OSError, ValueError, smoke_http.SmokeError) as error:
        failure = error if isinstance(error, smoke_http.SmokeError) else smoke_http.SmokeError('transport_'+type(error).__name__)
        failure.raw_response = bytes(reader.raw) if reader is not None else b''
        failure.body_parts, failure.status, failure.headers = parts, status, headers
        failure.submitted = submitted
        raise failure from None


def _one_request(item, body, key, deadline, cancel):
    record = dict(id=item['id'], request_path=item['path'], request_sha256=item['sha256'],
                  request_body_bytes=len(body), recorded_native_prompt_tokens=item['native_prompt_tokens'],
                  rendered_sha256=item['rendered_sha256'], success=False,
                  submitted_monotonic=None, completed_monotonic=None, status=None,
                  response_headers=None, raw_response_base64=None, body_parts=[], error=None)
    parts = []
    raw = b''
    partial_wire = False
    try:
        status, headers, raw, submitted, completed, parts = _large_exchange(
            '/v1/chat/completions', body, key, deadline, cancel)
        record.update(status=status, response_headers=headers, submitted_monotonic=submitted,
                      completed_monotonic=completed)
        if status != 200 or headers.get('content-type', '').split(';', 1)[0].strip().lower() != 'text/event-stream':
            raise smoke_http.SmokeError('response_status_or_type')
        parsed = smoke_http.parse_sse_response(parts, submitted, path='/v1/chat/completions')
        metrics, errors, unavailable = smoke_http._validate_usage(
            parsed['usage'], parsed['timings'], max_prompt_tokens=262143,
            max_completion_tokens=json.loads(body)['max_tokens'], cache_policy='cold')
        metrics['http_duration_ms'] = (completed-submitted)*1000
        metrics['first_visible_content_ms'] = parsed['first_visible_content_ms']
        benchmark_http._rates(metrics, errors, pp1=False)
        usage = parsed['usage']
        gufo = usage.get('gufo', {})
        if metrics['logical_prompt_tokens'] != item['native_prompt_tokens']:
            errors.append('native_prompt_count_mismatch')
        if (parsed['finish_reason'] not in ('stop', 'length') or parsed['first_visible_content_ms'] is None
                or not parsed['observed_models']
                or any(m != smoke_http.MODEL for m in parsed['observed_models'])):
            errors.append('completion_or_ttft_invalid')
        if item['id'] == 'arithmetic':
            answer = benchmark_recipes.validate_answer('WARMUP', dict(
                visible_answer=parsed['visible_answer'], finish_reason=parsed['finish_reason'],
                tool_calls=parsed['tool_calls'], metrics=metrics))
            record['answer_assessment'] = answer
            if answer['state'] == 'failed':
                errors.append('small_answer_failed')
        elif item['id'] == 'code_a':
            answer = dict(state='semantic_review_pending' if parsed['visible_answer'].strip()
                          and parsed['finish_reason'] in ('stop', 'length') else 'failed',
                          fixture='original_halogen_merge_lists')
            record['answer_assessment'] = answer
            if answer['state'] == 'failed':
                errors.append('small_answer_failed')
        record.update(parsed=parsed, metrics=metrics, validation_errors=errors,
                      unavailable_metrics=unavailable,
                      physical_execution_width=gufo.get('physical_execution_width'),
                      execution_plan=gufo.get('execution_plan'))
        if errors:
            raise smoke_http.SmokeError('validation_failed')
        record['success'] = True
    except smoke_http.SmokeError as error:
        record['error'] = error.code
        if error.raw_response:
            raw = error.raw_response
            partial_wire = True
            parts = getattr(error, 'body_parts', [])
            record['status'] = getattr(error, 'status', None)
            record['response_headers'] = getattr(error, 'headers', None)
            record['submitted_monotonic'] = getattr(error, 'submitted', None)
    except Exception as error:
        record['error'] = type(error).__name__+':'+str(error)
    finally:
        record['completed_monotonic'] = record['completed_monotonic'] or time.monotonic()
        # Partial wire may split a secret across receive boundaries. Omit that
        # representation; completed decoded SSE chunks are retained below.
        if partial_wire:
            record['raw_response_omission_reason'] = 'partial_wire_body_offsets_unavailable'
            raw = b''
        secret = key.encode('ascii')
        clean = raw.replace(secret, b'*'*len(secret))
        record['raw_response_base64'] = base64.b64encode(clean).decode('ascii')
        joined = b''.join(part for part, _ in parts).replace(secret, b'*'*len(secret))
        offset = 0
        for part, arrived in parts:
            clean_part = joined[offset:offset+len(part)]
            offset += len(part)
            record['body_parts'].append(dict(base64=base64.b64encode(clean_part).decode('ascii'),
                                             arrived_monotonic=arrived))
    return smoke_guard._redact(record, key)


class Session:
    def __init__(self, store, *, api_key, startup_deadline, lifetime_deadline, cancel):
        self.store, self.key = store, api_key
        self.startup_deadline, self.lifetime_deadline, self.cancel = startup_deadline, lifetime_deadline, cancel
        self.done = threading.Event()
        self.result = dict(success=False, error=None, requests=[], stage=store.stage)
        self.workers = []
        self.thread = threading.Thread(target=self._run, name='no-snapshot-260k-session', daemon=True)
        self.thread.start()

    def terminal(self):
        return self.done.is_set() and not self.thread.is_alive() and all(not t.is_alive() for t in self.workers)

    def _ready(self):
        for attempt in range(smoke_http.MAX_READY_POLLS):
            smoke_http._check(min(self.startup_deadline, self.lifetime_deadline), self.cancel)
            try:
                status, _, body, _, _, _ = smoke_http._exchange('GET', '/ready', None, self.key,
                    min(self.startup_deadline, self.lifetime_deadline), self.cancel)
            except smoke_http.SmokeError as error:
                if error.code in ('transport_ConnectionRefusedError', 'connect_timeout'):
                    self.cancel.wait(2)
                    continue
                raise
            if status == 503:
                self.cancel.wait(2)
                continue
            if status != 200 or smoke_http._json_object(body).get('status') != 'ready':
                raise smoke_http.SmokeError('ready_invalid')
            return
        raise smoke_http.SmokeError('ready_poll_limit')

    def _run(self):
        try:
            self._ready()
            rows = self.store.cached_manifest['stage_manifest']['requests']
            if self.store.stage == 'small':
                for item, body in zip(rows, self.store.cached_bodies):
                    deadline = min(time.monotonic()+60, self.lifetime_deadline)
                    observation = _one_request(item, body, self.key, deadline, self.cancel)
                    self.result['requests'].append(observation)
                    if not observation['success']:
                        raise ValueError('small_request_failed:'+item['id'])
            else:
                barrier = threading.Barrier(3)
                results = [None, None]

                def worker(index):
                    try:
                        barrier.wait(timeout=10)
                        start = time.monotonic()
                        results[index] = _one_request(rows[index], self.store.cached_bodies[index],
                            self.key, min(start+1800, self.lifetime_deadline), self.cancel)
                        if not results[index]['success']:
                            self.cancel.set()
                    except BaseException as error:
                        results[index] = dict(id=rows[index]['id'], success=False,
                                              error=type(error).__name__+':'+str(error))
                        self.cancel.set()

                for index in range(2):
                    thread = threading.Thread(target=worker, args=(index,),
                                              name='no-snapshot-260k-worker-'+str(index), daemon=True)
                    self.workers.append(thread)
                    thread.start()
                barrier.wait(timeout=10)
                for thread in self.workers:
                    thread.join(timeout=max(0, self.lifetime_deadline-time.monotonic()))
                if any(thread.is_alive() for thread in self.workers):
                    self.cancel.set()
                    raise TimeoutError('long_worker_join_timeout')
                self.result['requests'] = results
                if not all(row is not None and row.get('success') is True for row in results):
                    raise ValueError('long_request_failed')
                starts = [row['submitted_monotonic'] for row in results]
                ends = [row['completed_monotonic'] for row in results]
                self.result['common_full_interval_seconds'] = max(0, min(ends)-max(starts))
                self.result['aggregate_pure_decode_rate'] = None
                self.result['aggregate_pure_decode_rate_status'] = 'not_inferable_from_http_overlap'
            self.result['success'] = True
        except BaseException as error:
            self.result['error'] = type(error).__name__+':'+str(error)
            self.cancel.set()
        finally:
            self.done.set()


class Guardian(smoke_guard._Guardian):
    def __init__(self, store):
        self.private_store = store
        super().__init__(store=store, policy_module=Policy(store.stage),
                         profile_id=PROFILE, collect=native.collect,
                         argv_builder=store.build_argv,
                         http_start=lambda **kw: Session(store, **kw))

    def _collect_initial_baseline(self):
        frames = []
        deadline = time.monotonic()+30
        for _ in range(11):
            if time.monotonic()+operator_probe.MAX_QUERY_SECONDS > deadline:
                raise TimeoutError('current_baseline_timeout')
            frame = operator_probe.collect_one(self.collect, self.run_dir/'telemetry.jsonl',
                'baseline', frames[-1].query_start if frames else None, query_factory=self._query)
            frames.append(frame)
            reasons = self.policy.admission_reasons(self.profile, self.original, frame,
                now=frame.query_end, now_utc=frame.validated_utc)
            if reasons:
                raise ValueError('current_baseline:'+','.join(reasons))
        current = variation_baseline(frames)
        self._write('current-baseline-variation.json', dict(current=asdict(current),
            spans_bytes=variation_spans(frames), samples=11))
        return current, frames[-1]

    def _baseline_trend_reasons(self, frames):
        variation_baseline(frames)
        return []

    def _http_terminal(self):
        return not self.http_requested or (self.http is not None and self.http.terminal())

    def _recover(self):
        super()._recover()

    def _result(self):
        result = super()._result()
        result.update(stage=self.private_store.stage,
                      controller_sha256=self.manifest['stage_manifest']['controller_sha256'] if self.manifest else None,
                      qualification='empirical_trial_only',
                      old_49_gib_admission_waived=True)
        return result


def run(stage_manifest):
    store = Store(stage_manifest)
    guardian = Guardian(store)
    # A finite lifecycle callback supplies only the extended process deadline.
    class Deadline:
        def deadline(self, resumed_at):
            return resumed_at + STAGES[store.stage]['lifetime_seconds']
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
    print(json.dumps({key: result.get(key) for key in ('stage', 'success', 'failure',
                                                     'run', 'cleanup_confirmed', 'exit_code')},
                     allow_nan=False))
    return 0 if result['success'] else 1


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('validate', 'run'))
    parser.add_argument('--stage-manifest', required=True)
    args = parser.parse_args(argv)
    if args.action == 'validate':
        stage, bodies, records, model = validate_manifest(args.stage_manifest)
        print(json.dumps(dict(valid=True, stage=stage['stage'], request_bytes=[len(b) for b in bodies],
                              artifact_count=len(records), model_revision=model['revision'])))
        return 0
    return run(args.stage_manifest)


if __name__ == '__main__':
    raise SystemExit(main())
