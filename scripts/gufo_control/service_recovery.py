"""One exact, model-free late recovery disposition for the failed service smoke.

This may establish present recovery and archive its original incomplete latch.
It never changes the failed result, certifies the original deadline, or launches.
"""
import ctypes
from ctypes import wintypes
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import time

from . import operator_store, service_smoke_store, smoke_policy
from .operator_policy import Baseline, MAX_QUERY_SECONDS, recovery_reasons
from .operator_probe import QUERY_INTERVAL, Query, finish_query
from .smoke_guard import _rising_residual, check_port
from .telemetry import collect_snapshot

ROOT = Path(r'C:\Projects\strix-alloy-research\reports\gufo-service-policy-smoke-v1-runs')
RUN = ROOT/'20260927T012337Z-235d219b52834cfb9ec0b3d52aff6729'
LATCH = ROOT/'incomplete.json'
ATTEMPT = ROOT/'attempt.json'
ARCHIVE = RUN/'late-recovery-original-incomplete.json'
CERTIFICATE = RUN/'late-recovery-certificate.json'
TELEMETRY = RUN/'late-recovery-telemetry.jsonl'
AUDIT_ATTEMPT = RUN/'late-recovery-attempt.json'
PROFILE_ID = 'ar4k-service-policy-smoke-v1'
RESULT_SHA = '0C507AFCFE4B4555BFCB7FA92917610FD0B0D63380B408A36C18AFEC4779470E'
LATCH_SHA = 'FCC4174CD935192BE0B050DA63396A35A3B8417FD9258E5A7229DC154A4780F9'
ATTEMPT_SHA = '8D466A0BE8B747D0007720450F15B8F763D1D2CACBC9A4CE1204D0E8D2975455'
IDENTITY = dict(pid=7372, creation_time_100ns=134349458322118578,
    executable=r'C:\Projects\strix-alloy-research\runtimes\gufo-native-service-139aa9c-therock10.2\gufo.exe')
TERMINAL_FLAGS = ('owned_exit_confirmed', 'collector_terminal',
    'collector_cleanup_confirmed', 'http_terminal', 'inspection_terminal',
    'inspection_duplicate_closed', 'evidence_write_confirmed')


def read_pinned(path, expected):
    if path.is_symlink() or path.resolve(strict=True) != path or not path.is_file():
        raise ValueError('unexpected_evidence_path')
    if path.stat().st_size > 2*1024*1024:
        raise ValueError('evidence_too_large')
    with path.open('rb') as stream:
        data = stream.read(2*1024*1024+1)
    if len(data) > 2*1024*1024 or hashlib.sha256(data).hexdigest().upper() != expected:
        raise ValueError('pinned_evidence_changed')
    return json.loads(data)


def validate_result(result):
    if (result['run'] != str(RUN) or result['profile'] != PROFILE_ID
            or result['identity'] != IDENTITY
            or result['success'] is not False or result['cleanup_confirmed'] is not False
            or result['recovery_samples'] != 5 or result['exit_code'] != 0
            or result['failure'] != 'RuntimeError:recovery_unconfirmed'):
        raise ValueError('unexpected_original_outcome')
    for key in TERMINAL_FLAGS:
        if result[key] is not True:
            raise ValueError('unconfirmed_terminal_state:'+key)
    http = result['http']
    if (http['success'] is not True or http['post_attempted'] is not True
            or http['visible_answer'] != '4' or http['finish_reason'] != 'stop'
            or http['validation_errors'] != []
            or not any(response['path'] == '/v1/chat/completions'
                       and response['status'] == 200 for response in http['responses'])):
        raise ValueError('unexpected_http_outcome')


def pinned_state():
    for path in (ROOT, RUN, operator_store.EVIDENCE):
        if path.is_symlink() or path.resolve(strict=True) != path or not path.is_dir():
            raise ValueError('unexpected_directory')
    if RUN.parent != ROOT:
        raise ValueError('unexpected_run_parent')
    result = read_pinned(RUN/'result.json', RESULT_SHA)
    validate_result(result)
    latch = read_pinned(LATCH, LATCH_SHA)
    attempt = read_pinned(ATTEMPT, ATTEMPT_SHA)
    if (latch['run'] != str(RUN) or latch['original_baseline'] != result['original_baseline']
            or attempt != dict(profile=PROFILE_ID, run=str(RUN))):
        raise ValueError('marker_identity_mismatch')
    if (operator_store.EVIDENCE/'incomplete.json').exists():
        raise ValueError('operator_cleanup_unconfirmed')
    return result


def baseline_from(value):
    copied = dict(value)
    copied['identity'] = tuple(copied['identity'])
    copied['gpu_max'] = tuple(copied['gpu_max'])
    return Baseline(**copied)


def policy_inputs(result):
    pins = service_smoke_store.PINS
    manifest = result['manifest']
    if (manifest['source'] != pins.source_commit
            or manifest['service'] != service_smoke_store.service_binding(pins)['service']):
        raise ValueError('service_manifest_changed')
    profile = smoke_policy.profile_from_manifest(manifest, pins=pins)
    original = baseline_from(result['original_baseline'])
    current = baseline_from(result['current_baseline'])
    strict = smoke_policy.stricter_runtime_baseline(original, current)
    if asdict(strict) != asdict(baseline_from(result['runtime_baseline'])):
        raise ValueError('stricter_baseline_changed')
    return pins, profile, current, strict


def validate_frame(frame, profile, strict, pins):
    reasons = smoke_policy.frame_numeric_reasons(profile, strict, frame,
        now=time.monotonic(), now_utc=datetime.now(timezone.utc), pins=pins)
    if reasons:
        raise ValueError('fresh_recovery:'+','.join(reasons))
    try:
        processes = frame.snapshot['raw']['processes']
        if not isinstance(processes, list) or any(type(p['pid']) is not int for p in processes):
            raise ValueError('raw_process_inventory_invalid')
        if any(p['pid'] == IDENTITY['pid'] for p in processes):
            raise ValueError('original_pid_present_or_reused')
    except (KeyError, TypeError) as error:
        raise ValueError('raw_process_inventory_invalid') from error


def require_pid_absent():
    # Query-limited access only. A reused PID or access denial refuses.
    api = ctypes.WinDLL('kernel32', use_last_error=True)
    api.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    api.OpenProcess.restype = wintypes.HANDLE
    api.CloseHandle.argtypes = [wintypes.HANDLE]
    api.CloseHandle.restype = wintypes.BOOL
    handle = api.OpenProcess(0x1000, False, IDENTITY['pid'])
    if handle:
        if not api.CloseHandle(handle):
            raise ctypes.WinError(ctypes.get_last_error())
        raise ValueError('original_pid_present_or_reused')
    error = ctypes.get_last_error()
    if error != 87:
        raise OSError(error, 'process_absence_unconfirmed')


def write_new(path, value):
    data = (json.dumps(value, sort_keys=True, indent=2, allow_nan=False)+'\n').encode('utf-8')
    with path.open('xb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    digest = hashlib.sha256(data).hexdigest().upper()
    read_pinned(path, digest)
    return digest


def _create_telemetry():
    with TELEMETRY.open('xb') as stream:
        stream.flush()
        os.fsync(stream.fileno())


def archive_verified(certificate_sha):
    # The global blocker is recognized by all operator and service starts.
    blocker = operator_store.EVIDENCE/'incomplete.json'
    blocker_sha = write_new(blocker, dict(run=str(RUN),
        phase='late_recovery_archival_in_progress', certificate_sha256=certificate_sha,
        original_latch_sha256=LATCH_SHA, original_latch=str(LATCH), archive=str(ARCHIVE)))
    try:
        if ARCHIVE.exists():
            raise ValueError('archive_already_exists')
        os.rename(LATCH, ARCHIVE)
        read_pinned(ARCHIVE, LATCH_SHA)
        read_pinned(RUN/'result.json', RESULT_SHA)
        read_pinned(ATTEMPT, ATTEMPT_SHA)
        read_pinned(CERTIFICATE, certificate_sha)
        if LATCH.exists():
            raise ValueError('latch_archival_unconfirmed')
        read_pinned(blocker, blocker_sha)
    except BaseException:
        # Restoration cannot overwrite. The separate blocker remains on errors.
        if not LATCH.exists() and ARCHIVE.exists():
            os.rename(ARCHIVE, LATCH)
            read_pinned(LATCH, LATCH_SHA)
        raise
    blocker.unlink()


def main():
    if os.name != 'nt':
        raise OSError('Windows required')
    with operator_store.exclusive(operator_store.EVIDENCE):
        with operator_store.exclusive(ROOT):
            result = pinned_state()
            if any(path.exists() for path in (AUDIT_ATTEMPT, TELEMETRY,
                                              CERTIFICATE, ARCHIVE)):
                raise ValueError('prior_disposition_artifact_exists')
            require_pid_absent()
            check_port()
            pins, profile, current, strict = policy_inputs(result)
            write_new(AUDIT_ATTEMPT, dict(run=str(RUN), result_sha256=RESULT_SHA,
                original_latch_sha256=LATCH_SHA, meaning='one_time_late_recovery_audit',
                recorded_utc=datetime.now(timezone.utc).isoformat()))
            _create_telemetry()
            frames, previous, query = [], None, None
            deadline = time.monotonic()+60
            while time.monotonic() < deadline:
                start = max(time.monotonic(), previous+QUERY_INTERVAL if previous is not None else 0)
                if start+MAX_QUERY_SECONDS > deadline:
                    break
                time.sleep(max(0, start-time.monotonic()))
                query = Query(collect_snapshot)
                previous = query.started
                frame = finish_query(query, TELEMETRY, 'present_recovery_observed_later')
                if not query.done.is_set():
                    raise ValueError('collector_nonterminal')
                validate_frame(frame, profile, strict, pins)
                frames = (frames+[frame])[-5:]
                if (len(frames) == 5 and not recovery_reasons(current, frames)
                        and not _rising_residual(frames)):
                    break
            if (query is None or not query.done.is_set() or time.monotonic() > deadline
                    or len(frames) != 5 or recovery_reasons(current, frames)
                    or _rising_residual(frames)):
                raise ValueError('present_recovery_unconfirmed')
            require_pid_absent()
            check_port()
            pinned_state()
            validate_frame(frames[-1], profile, strict, pins)
            certificate = dict(meaning='present_recovery_observed_later',
                original_run_still_failed=True, original_cleanup_still_unconfirmed=True,
                original_recovery_deadline_not_certified=True, no_model_launch=True,
                run=str(RUN), result_sha256=RESULT_SHA, latch_sha256=LATCH_SHA,
                retained_attempt_sha256=ATTEMPT_SHA,
                recorded_utc=datetime.now(timezone.utc).isoformat(),
                recovery_baseline=asdict(current), stricter_numeric_baseline=asdict(strict),
                original_owned_identity=IDENTITY, original_pid_absent=True,
                original_terminal_flags={key: result[key] for key in TERMINAL_FLAGS},
                frames=[dict(asdict(frame), validated_utc=frame.validated_utc.isoformat())
                        for frame in frames])
            digest = write_new(CERTIFICATE, certificate)
            require_pid_absent()
            check_port()
            pinned_state()
            read_pinned(CERTIFICATE, digest)
            validate_frame(frames[-1], profile, strict, pins)
            if time.monotonic() > deadline:
                raise ValueError('present_recovery_deadline_expired')
            archive_verified(digest)
            print(json.dumps(dict(disposition='exact_failed_latch_archived_after_late_recovery',
                certificate=str(CERTIFICATE), certificate_sha256=digest,
                archive=str(ARCHIVE), original_result_unchanged=True,
                permanent_attempt_preserved=True, launch_performed=False)))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(json.dumps(dict(refused=type(error).__name__+':'+str(error),
            launch_performed=False)))
        raise SystemExit(1)
