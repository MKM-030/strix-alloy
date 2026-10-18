"""Fail-closed normalization of one Windows host and DXGI adapter snapshot."""
import copy
from datetime import datetime, timezone
import json
import math
import ntpath
import os
from pathlib import Path
import re
import struct
import subprocess
import time

from .admission import MAX_BYTES, MAX_SAMPLE_AGE_SECONDS


class TelemetryError(ValueError):
    """A required telemetry reading could not be trusted."""


HISTORICAL_PROVIDER = 'PDH/Get-Counter;DXGI/EnumAdapters1'
PROVIDER = 'PDH/native-gauges;DXGI/EnumAdapters1'
ALLOWED_PROVIDERS = frozenset((HISTORICAL_PROVIDER, PROVIDER))
KNOWN = {'gufo', 'llama-server', 'llama-cli', 'ollama', 'ollama_llama_server',
         'vmmem', 'vmmemwsl', 'wslhost', 'com.docker.backend', 'docker desktop', 'lm studio'}
HOST = {'available bytes': 'available_physical_bytes', 'committed bytes': 'host_committed_bytes',
        'commit limit': 'host_commit_limit_bytes'}
GPU = {'dedicated usage': 'adapter_dedicated_bytes', 'shared usage': 'adapter_shared_bytes',
       'total committed': 'adapter_total_committed_bytes'}
LUID = re.compile(r'0x[0-9a-f]{8}_0x[0-9a-f]{8}')
HOST_PATH = re.compile(r'\\\\[^\\]+\\memory\\([^\\]+)')
GPU_PATH = re.compile(r'\\\\[^\\]+\\gpu adapter memory\(([^)]+)\)\\([^\\]+)')
INSTANCE = re.compile(r'luid_(0x[0-9a-f]{8}_0x[0-9a-f]{8})_phys_([0-9]+)')
PROCESS_PATH = re.compile(r'\\\\[^\\]+\\gpu process memory\(([^)]+)\)\\([^\\]+)')
PROCESS_INSTANCE = re.compile(r'pid_([0-9]+)_luid_(0x[0-9a-f]{8}_0x[0-9a-f]{8})_phys_([0-9]+)')
OWNED_FIELDS = ('process_dedicated_bytes', 'process_shared_bytes',
                'process_total_committed_bytes', 'working_set_bytes', 'private_bytes')


def _owned_identity(expected, actual):
    if (not isinstance(expected, dict) or not isinstance(actual, dict)
            or any(type(expected.get(k)) is not int or expected[k] <= 0
                   or expected[k] != actual.get(k) for k in ('pid', 'creation_time_100ns'))
            or not isinstance(expected.get('executable'), str)
            or ntpath.normcase(expected['executable']) != ntpath.normcase(actual.get('executable', ''))):
        raise TelemetryError('owned_identity_mismatch')


def _owned_snapshot(raw, request, *, luid, captured_monotonic, now_utc):
    result = dict(available=False, reason='not_requested', provider=PROVIDER,
        gpu_scope='owned_process_target_adapter', host_scope='owned_process',
        required_for_admission=False, captured_monotonic=captured_monotonic,
        adapter_luid=luid, identity=None, sample_utc_min=None, sample_utc_max=None,
        **dict.fromkeys(OWNED_FIELDS))
    if request is None: return result
    try:
        _owned_identity(request, request)
        if request.get('adapter_luid') != luid:
            raise TelemetryError('owned_adapter_mismatch')
        result['identity'] = {k: request[k] for k in ('pid', 'creation_time_100ns', 'executable')}
        if not isinstance(raw, dict) or raw.get('available') is not True:
            reason = raw.get('reason') if isinstance(raw, dict) else None
            result['reason'] = reason if reason in ('process_exited', 'owned_identity_mismatch',
                'owned_handle_unavailable', 'process_counters_unavailable') else 'process_counters_unavailable'
            return result
        _owned_identity(request, raw.get('identity_before'))
        _owned_identity(request, raw.get('identity_after'))
        values, stamps = {}, []
        for key in ('working_set_bytes', 'private_bytes'):
            value = integer(raw.get(key), key)
            values[key], stamp = counter_value(dict(status=0, raw_value=value,
                cooked_value=value, timestamp_utc=raw.get('host_timestamp_utc')), key, now_utc)
            stamps.append(stamp)
        rows = raw.get('counters')
        if not isinstance(rows, list) or len(rows) > 10000:
            raise TelemetryError('owned_rows_invalid')
        for row in rows:
            parsed = PROCESS_PATH.fullmatch(row['path'].lower())
            instance = PROCESS_INSTANCE.fullmatch(parsed[1]) if parsed else None
            if not instance or row.get('instance', '').lower() != parsed[1] or parsed[2] not in GPU:
                raise TelemetryError('owned_counter_identity_invalid')
            if int(instance[1]) != request['pid'] or instance[2] != luid: continue
            if instance[3] != '0': raise TelemetryError('owned_topology_ambiguous')
            key = GPU[parsed[2]].replace('adapter_', 'process_')
            if key in values: raise TelemetryError('owned_counter_ambiguous')
            values[key], stamp = counter_value(row, key, now_utc)
            stamps.append(stamp)
        if set(values) != set(OWNED_FIELDS): raise TelemetryError('owned_instance_missing')
        result.update(values, available=True, reason=None,
            sample_utc_min=min(stamps).isoformat(), sample_utc_max=max(stamps).isoformat())
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError) as error:
        reason = str(error)
        result['reason'] = reason if reason in ('owned_instance_missing', 'owned_counter_ambiguous',
            'owned_identity_mismatch', 'owned_adapter_mismatch', 'owned_topology_ambiguous') else 'owned_sample_invalid_or_stale'
    return result


def _host_process_memory(peer):
    """Query only the retained query/synchronize handle; never acquire kill rights."""
    import ctypes as C
    from ctypes import wintypes as W
    class Memory(C.Structure):
        _fields_ = [('cb', W.DWORD), ('faults', W.DWORD)] + [
            (key, C.c_size_t) for key in ('peak_ws', 'ws', 'peak_paged', 'paged',
                'peak_nonpaged', 'nonpaged', 'pagefile', 'peak_pagefile', 'private')]
    api = C.WinDLL('psapi', use_last_error=True)
    fn = api.GetProcessMemoryInfo
    fn.argtypes, fn.restype = [W.HANDLE, C.POINTER(Memory), W.DWORD], W.BOOL
    value = Memory()
    value.cb = C.sizeof(value)
    if not fn(peer.handle, C.byref(value), value.cb): raise C.WinError(C.get_last_error())
    return dict(working_set_bytes=int(value.ws), private_bytes=int(value.private))


def integer(value, label, maximum=MAX_BYTES):
    if type(value) is not int or not 0 <= value <= maximum:
        raise TelemetryError('invalid integer: ' + label)
    return value


def finite_time(value):
    try:
        return type(value) in (int, float) and value >= 0 and math.isfinite(value)
    except OverflowError:
        return False


def counter_value(row, key, now_utc):
    if integer(row.get('status'), 'counter status', 0xffffffff) not in (0, 1):
        raise TelemetryError('unhealthy counter: ' + key)
    value = integer(row.get('raw_value'), key)
    cooked = row.get('cooked_value')
    try:
        valid = type(cooked) in (int, float) and math.isfinite(cooked) and cooked == value
    except OverflowError:
        valid = False
    if not valid:
        raise TelemetryError('inconsistent raw/cooked bytes: ' + key)
    try:
        text = row['timestamp_utc']
        if not isinstance(text, str):
            raise ValueError('timestamp is not text')
        stamp = datetime.fromisoformat(text.replace('Z', '+00:00'))
        if stamp.utcoffset() is None or not 0 <= (now_utc - stamp).total_seconds() <= MAX_SAMPLE_AGE_SECONDS:
            raise ValueError('stale/future counter')
    except (KeyError, TypeError, ValueError, AttributeError, OverflowError) as error:
        raise TelemetryError('invalid counter timestamp') from error
    return value, stamp


def normalize_snapshot(raw: dict, *, captured_monotonic: float, now_monotonic: float,
                       now_utc: datetime, owned=None) -> dict:
    """Qualify English PDH paths for one Radeon 8060S adapter aggregate."""
    if not finite_time(captured_monotonic) or not finite_time(now_monotonic):
        raise TelemetryError('invalid monotonic timestamp')
    if not 0 <= now_monotonic - captured_monotonic <= MAX_SAMPLE_AGE_SECONDS:
        raise TelemetryError('stale collection')
    if not isinstance(now_utc, datetime) or now_utc.utcoffset() is None:
        raise TelemetryError('timezone-aware UTC reference required')
    if (not isinstance(raw, dict) or type(raw.get('schema')) is not int or raw['schema'] != 1
            or not isinstance(raw.get('provider'), str) or raw['provider'] not in ALLOWED_PROVIDERS):
        raise TelemetryError('unknown telemetry provider/schema')
    for field in ('adapters', 'counters', 'processes'):
        if not isinstance(raw.get(field), list) or len(raw[field]) > 10000:
            raise TelemetryError('missing or excessive ' + field)
    if not raw['adapters'] or not raw['counters']:
        raise TelemetryError('empty adapter or counter collection')
    matches = []
    seen_luids = set()
    for adapter in raw['adapters']:
        if not isinstance(adapter, dict):
            raise TelemetryError('malformed adapter')
        luid = adapter.get('luid')
        if not isinstance(luid, str) or not LUID.fullmatch(luid.lower()):
            raise TelemetryError('invalid adapter LUID')
        normalized_luid = luid.lower()
        if normalized_luid in seen_luids:
            raise TelemetryError('duplicate adapter LUID')
        seen_luids.add(normalized_luid)
        for field, limit in (('vendor_id', 0xffff), ('device_id', 0xffff),
                             ('subsystem_id', 0xffffffff), ('flags', 0xffffffff)):
            integer(adapter.get(field), field, limit)
        integer(adapter.get('dedicated_video_memory'), 'dedicated capacity')
        if not isinstance(adapter.get('description'), str) or not adapter['description'].strip():
            raise TelemetryError('invalid adapter description')
        if (adapter['vendor_id'] == 0x1002 and adapter['device_id'] == 0x1586 and
                adapter['flags'] == 0):
            matches.append(adapter)
    if len(matches) != 1:
        raise TelemetryError('expected exactly one Radeon8060S adapter')
    adapter = matches[0]
    luid = adapter['luid'].lower()
    instance = 'luid_' + luid + '_phys_0'
    result = {'adapter_luid': luid, 'adapter_identity': copy.deepcopy(adapter),
              'dedicated_capacity_bytes': adapter['dedicated_video_memory'],
              'captured_monotonic': captured_monotonic, 'provider': raw['provider'],
              'gpu_scope': 'adapter_aggregate', 'host_scope': 'host_global',
              'inventory_scope': 'known_engine_and_guest_names'}
    stamps = []
    for row in raw['counters']:
        if not isinstance(row, dict) or not isinstance(row.get('path'), str):
            raise TelemetryError('malformed counter row')
        path = row['path'].lower()
        host = HOST_PATH.fullmatch(path)
        gpu = GPU_PATH.fullmatch(path)
        key = None
        if host:
            if row.get('instance') is not None or host[1] not in HOST:
                raise TelemetryError('unsupported host counter identity')
            key = HOST[host[1]]
        elif gpu:
            parsed = INSTANCE.fullmatch(gpu[1])
            if not parsed or not isinstance(row.get('instance'), str) or row['instance'].lower() != gpu[1]:
                raise TelemetryError('counter instance/path disagree')
            if gpu[2] not in GPU:
                raise TelemetryError('unsupported GPU counter')
            if parsed[1] == luid:
                if gpu[1] != instance:
                    raise TelemetryError('unsupported physical-node topology')
                key = GPU[gpu[2]]
        else:
            raise TelemetryError('unsupported counter namespace')
        value, stamp = counter_value(row, key or path, now_utc)
        if key is None:
            continue
        if key in result:
            raise TelemetryError('duplicate counter: ' + key)
        result[key] = value
        stamps.append(stamp)
    if any(key not in result for key in (*HOST.values(), *GPU.values())):
        raise TelemetryError('required counter missing')
    if (result['host_committed_bytes'] > result['host_commit_limit_bytes'] or
            result['dedicated_capacity_bytes'] == 0 or
            result['adapter_dedicated_bytes'] > result['dedicated_capacity_bytes']):
        raise TelemetryError('inconsistent memory counters')
    pids = []
    seen = set()
    for proc in raw['processes']:
        if not isinstance(proc, dict) or not isinstance(proc.get('name'), str) or not proc['name'].strip():
            raise TelemetryError('malformed process inventory')
        pid = integer(proc.get('pid'), 'PID', 0xffffffff)
        if pid in seen:
            raise TelemetryError('duplicate process PID')
        seen.add(pid)
        if proc['name'].casefold() in KNOWN:
            if pid == 0:
                raise TelemetryError('invalid inference PID')
            pids.append(pid)
    result.update(telemetry_ok=True, other_inference_pids=sorted(pids),
                  commit_headroom_bytes=result['host_commit_limit_bytes'] - result['host_committed_bytes'],
                  sample_utc_min=min(stamps).isoformat(), sample_utc_max=max(stamps).isoformat(),
                  raw=copy.deepcopy(raw))
    result['owned_counters'] = _owned_snapshot(raw.get('owned'), owned, luid=luid,
        captured_monotonic=captured_monotonic, now_utc=now_utc)
    return result


def collect_snapshot(*, owned=None, probe_executable=None) -> dict:
    """Run one bounded hidden probe; alternate binary identity is caller-pinned."""
    if os.name != 'nt' or struct.calcsize('P') != 8:
        raise TelemetryError('Windows x64 required')
    executable = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
    started = time.monotonic()
    peer = None
    diagnostic = dict(available=False, reason='not_requested')
    if owned is not None:
        try:
            from .service_ipc import _Peer
            _owned_identity(owned, owned)
            peer = _Peer(owned['pid'])
            _owned_identity(owned, peer.identity)
            diagnostic = dict(available=True, identity_before=dict(peer.identity))
        except (OSError, ValueError, TypeError, KeyError):
            diagnostic = dict(available=False, reason='owned_handle_unavailable')
    try:
        script = Path(__file__).with_name('windows_probe.ps1').resolve(strict=True)
        remaining = 5 if owned is None else 5-(time.monotonic()-started)
        if remaining <= 0: raise TelemetryError('sample_deadline_expired')
        if probe_executable is None:
            argv = [str(executable), '-NoProfile', '-NonInteractive', '-File', str(script)]
            if diagnostic['available']: argv += ['-OwnedPid', str(owned['pid'])]
        else:
            native = Path(probe_executable)
            if not native.is_absolute() or native.is_symlink() or native.resolve(strict=True) != native:
                raise TelemetryError('invalid native probe path')
            argv = [str(native)]
            if diagnostic['available']: argv += ['--owned-pid', str(owned['pid'])]
        completed = subprocess.run(argv,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=remaining,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
        if completed.returncode or not completed.stdout or len(completed.stdout) > 2 * 1024 * 1024:
            raise TelemetryError('probe failed or output exceeds limit')
        raw = json.loads(completed.stdout.decode('utf-8-sig'))
        if not isinstance(raw, dict) or raw.get('provider') != PROVIDER:
            raise TelemetryError('unexpected live telemetry provider')
        if diagnostic['available']:
            try:
                if not peer.alive(): raise TelemetryError('process_exited')
                _owned_identity(owned, peer.identity)
                diagnostic.update(_host_process_memory(peer), identity_after=dict(peer.identity),
                    host_timestamp_utc=datetime.now(timezone.utc).isoformat())
                if not peer.alive(): raise TelemetryError('process_exited')
                optional = raw.get('owned', {})
                if not isinstance(optional, dict) or optional.get('available') is not True:
                    raise TelemetryError('process_counters_unavailable')
                diagnostic['counters'] = optional.get('counters')
            except (OSError, ValueError, TypeError, KeyError):
                diagnostic = dict(available=False, reason='process_exited' if not peer.alive()
                                  else 'process_counters_unavailable')
        raw['owned'] = diagnostic
    except (OSError, subprocess.TimeoutExpired, UnicodeError, ValueError) as error:
        raise TelemetryError('Windows telemetry unavailable: ' + str(error)) from error
    finally:
        if peer is not None: peer.close()
    return normalize_snapshot(raw, captured_monotonic=started,
                              now_monotonic=time.monotonic(), now_utc=datetime.now(timezone.utc), owned=owned)
