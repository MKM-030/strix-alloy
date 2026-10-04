"""Opt-in Windows host telemetry for a retained Halogen engine manifest.

Default: one metadata/counter snapshot. --seconds adds at most 60 seconds of
observation. No model payload is read, no WSL command is invoked, and no process,
cache, affinity, or system setting is changed. Host disk/CPU counters are shared
with other applications; they cannot establish engine-only I/O or acceptance.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'server'))
from host_frames import frame

GIB = 1024 ** 3
MAX_MANIFEST_BYTES = 256 * 1024
COUNTER_COMMAND = r'''
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$taskDisk = @(Get-CimInstance Win32_PerfFormattedData_PerfDisk_PhysicalDisk |
    Select-Object Name,DiskReadBytesPersec,DiskReadsPersec,CurrentDiskQueueLength)
$taskDiskRaw = @(Get-CimInstance Win32_PerfRawData_PerfDisk_PhysicalDisk |
    Select-Object Name,DiskReadBytesPersec,DiskReadsPersec,AvgDisksecPerRead,
        AvgDisksecPerRead_Base,Frequency_PerfTime,Timestamp_PerfTime)
$taskCpu = @(Get-CimInstance Win32_PerfFormattedData_PerfOS_Processor |
    Where-Object Name -eq '_Total' | Select-Object Name,PercentProcessorTime)
$taskWsl = @(Get-CimInstance Win32_PerfFormattedData_PerfProc_Process |
    Where-Object Name -like 'vmmem*' |
    Select-Object Name,IDProcess,PercentProcessorTime,IOReadBytesPersec,IOReadOperationsPersec)
[pscustomobject]@{disk=$taskDisk; disk_raw=$taskDiskRaw; cpu=$taskCpu; wsl_processes=$taskWsl} |
    ConvertTo-Json -Compress -Depth 4
'''


def manifest_receipt(path):
    with path.open('rb') as stream:
        raw = stream.read(MAX_MANIFEST_BYTES + 1)
    if len(raw) > MAX_MANIFEST_BYTES:
        raise ValueError('manifest exceeds the 256 KiB metadata budget')
    value = json.loads(raw)
    if not isinstance(value, dict) or not isinstance(value.get('mounts'), dict):
        raise ValueError('requires an engine manifest with a mounts object')
    mounts = []
    for destination in ('/models', '/ngram-w4b.hgn'):
        source = value['mounts'].get(destination)
        if source is None:
            continue
        if not isinstance(source, str):
            raise ValueError('mount source must be text')
        drive = re.fullmatch(r'/mnt/([a-z])/(.+)', source)
        row = {'destination': destination, 'source': source,
               'path_kind': 'Windows drive mount' if drive else 'Linux path',
               'filesystem_verified_by_probe': False}
        # Do not access \\wsl$ or auto-start a distribution to inspect Linux paths.
        if drive:
            local = Path(drive[1].upper() + ':/' + drive[2])
            info = local.stat()
            row['windows_file_metadata'] = {'path': str(local), 'bytes': info.st_size,
                'mtime_ns': info.st_mtime_ns, 'payload_read': False}
        mounts.append(row)
    environment = value.get('environment', {})
    names = ('HALOGEN_CTX', 'HALOGEN_NGRAM_TABLE', 'HALOGEN_NGRAM_GATHER_THREADS',
             'HALOGEN_HOST_RESERVE_GIB', 'HALOGEN_MTP_DEPTH', 'HALOGEN_PROMPT_CACHE',
             'HALOGEN_KV_POOL_POSITIONS', 'HALOGEN_KV_SLOTS', 'HALOGEN_HYBRID_COPY_BYTES')
    return {'path': str(path.resolve()), 'sha256': hashlib.sha256(raw).hexdigest(),
            'run_id': value.get('run_id'), 'image': value.get('image'),
            'mounts': mounts, 'controls': {key: environment[key] for key in names if key in environment}}


def snapshot(counter_timeout, reserve_gib):
    before = frame()
    if min(before['available_bytes'], before['commit_headroom_bytes']) < reserve_gib * GIB:
        raise RuntimeError('host physical/commit headroom is below the requested reserve')
    started = time.monotonic()
    completed = subprocess.run(
        ['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', COUNTER_COMMAND],
        capture_output=True, encoding='utf-8-sig', timeout=counter_timeout, check=True,
        creationflags=subprocess.CREATE_NO_WINDOW)
    counters = json.loads(completed.stdout)
    after = frame()
    if min(after['available_bytes'], after['commit_headroom_bytes']) < reserve_gib * GIB:
        raise RuntimeError('host physical/commit headroom crossed the requested reserve')
    return {'time_unix': time.time(), 'counter_query_seconds': time.monotonic() - started,
            'memory_before': before, 'memory_after': after, 'host_counters': counters}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--seconds', type=float, default=0, help='0: one snapshot; otherwise 1..60 seconds')
    parser.add_argument('--interval', type=float, default=2, help='pause after each sample, 1..10 seconds')
    parser.add_argument('--reserve-gib', type=float, default=18, help='observation floor, at least 18 GiB')
    args = parser.parse_args(argv)
    if os.name != 'nt':
        parser.error('this host telemetry helper is Windows-only')
    if (not (args.seconds == 0 or 1 <= args.seconds <= 60) or not 1 <= args.interval <= 10
            or not 18 <= args.reserve_gib <= 128):
        parser.error('requires seconds 0 or 1..60, interval 1..10, reserve 18..128 GiB')
    receipt = manifest_receipt(args.manifest)
    result = {'schema': 1, 'scope': 'Windows host counters, not engine-only or guest row-cache evidence',
              'manifest': receipt, 'reserve_gib': args.reserve_gib, 'seconds_requested': args.seconds,
              'model_payload_bytes_read': 0, 'processes_or_caches_changed': False,
              'reserve_check_is_memory_reservation': False, 'samples': [], 'passed': False}
    # Claim the output before querying counters. Never overwrite prior evidence.
    with args.out.open('x', encoding='utf-8') as output:
        started = time.monotonic()
        deadline = started + args.seconds if args.seconds else None
        try:
            while True:
                remaining = deadline - time.monotonic() if deadline is not None else 10
                if remaining <= 0:
                    result['end_reason'] = 'observation deadline'
                    break
                try:
                    sample = snapshot(min(10, remaining), args.reserve_gib)
                except subprocess.TimeoutExpired:
                    # A final query clipped by the observation deadline is an
                    # ordinary bounded stop when earlier samples succeeded.
                    if deadline is not None and time.monotonic() >= deadline and result['samples']:
                        result['end_reason'] = 'observation deadline during counter query'
                        break
                    raise
                sample['elapsed_seconds'] = time.monotonic() - started
                result['samples'].append(sample)
                if deadline is None:
                    break
                time.sleep(max(0, min(args.interval, deadline - time.monotonic())))
            result['passed'] = bool(result['samples'])
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
            result['error'] = type(exc).__name__ + ': ' + str(exc)
        finally:
            result['elapsed_seconds'] = time.monotonic() - started
            json.dump(result, output, indent=2, allow_nan=False)
            output.write('\n')
    print(json.dumps({'passed': result['passed'], 'samples': len(result['samples']),
                      'output': str(args.out.resolve()), 'error': result.get('error')}))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
