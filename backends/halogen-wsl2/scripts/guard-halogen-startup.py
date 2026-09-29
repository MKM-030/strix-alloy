#!/usr/bin/env python3
"""Windows-only bounded guard for one explicitly identified Halogen test container.

Attach immediately after docker run -d for startup, or explicitly select a runtime
observation interval. Not a background service. Only the exact validated container
can receive read-only model cache advice or docker stop.
Thresholds are conservative experimental policy, not a guaranteed RAM reservation.
After delayed cleanup exhausted a 16 GiB buffer, startup now stops below 20 GiB
and runtime below 24 GiB. These earlier triggers still cannot bound driver cleanup.
Whole-file advice affects the lookup cache too: never issue it during a benchmark.
Private registration creates COW copies while the original clean file pages
remain cached. Advise those source files early, with at most one operation in
flight, rather than waiting for severe Windows pressure. This does not discard
registered host mappings or change the model's contents.
The six-minute startup deadline includes API readiness and slow but progressing
file reads.
"""
import argparse
import concurrent.futures
import ctypes
import datetime
import json
import os
import pathlib
import re
import subprocess
import time
import urllib.request
from package import linux_path, wsl_command

STARTUP_TIMEOUT_SECONDS = 360

IMAGE = ('ghcr.io/peonist-ai/halogen-flash-server@sha256:'
         '6e626c979d536ab1edb07898e278be6686afd353758ea268817457f801d687dd')
REVIEWED_IMAGES = frozenset((IMAGE,))
WSL = None
EXPECTED_MOUNTS = None

def configure_target(distro, user, models, workspace, dxg):
    global WSL, EXPECTED_MOUNTS
    WSL = wsl_command(distro, user, ['docker'])
    EXPECTED_MOUNTS = {'/models': linux_path(models, native=True),
                       '/workspace': linux_path(workspace),
                       '/usr/lib/librocdxg.so': linux_path(dxg),
                       '/usr/lib/libdxcore.so': '/usr/lib/wsl/lib/libdxcore.so'}
CACHE_CODE = '''import os
for path in ('/models/qwen38-flash-next-w4b.hgn', '/models/qwen38-flash-next-w4b.overlay.hgn'):
    fd = os.open(path, os.O_RDONLY)
    try:
        os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_DONTNEED)
        print(path, 'read-only cache advice completed', flush=True)
    finally:
        os.close(fd)
'''


def decide(available, elapsed, healthy, advice_pending, last_advice):
    if available is None or available < 0:
        return 'stop_telemetry'
    if available < 20 << 30:
        return 'stop_pressure'
    if elapsed >= STARTUP_TIMEOUT_SECONDS:
        return 'stop_timeout'
    if advice_pending:
        return 'wait'
    if healthy and available >= 24 << 30:
        return 'ready'
    if available < 64 << 30 and (last_advice is None or elapsed - last_advice >= 1):
        return 'advise'
    return 'wait'


def decide_runtime(available, elapsed, duration):
    if available is None or available < 0:
        return 'stop_telemetry'
    if available < 24 << 30:
        return 'stop_pressure'
    if elapsed >= duration:
        return 'complete'
    return 'wait'


def probe_fresh(good, completed_at, now):
    return bool(good and completed_at is not None and 0 <= now - completed_at <= 6)


def validate_target(info, container_id):
    if not re.fullmatch('[0-9a-f]{64}', container_id) or info.get('Id') != container_id:
        raise ValueError('Requires an exact full container ID')
    if not info.get('Name', '').startswith('/halogen-flash-hybrid-'):
        raise ValueError('Not a named hybrid test container')
    config = info.get('Config', {})
    if ((config.get('Labels') or {}).get('halogen.performance') != 'hybrid'
            or (config.get('Labels') or {}).get('strix-alloy.owner') != 'strix-alloy-wsl2'
            or (config.get('Labels') or {}).get('strix-alloy.run') != info.get('Name', '').lstrip('/')
            or config.get('Image') not in REVIEWED_IMAGES):
        raise ValueError('Unrecognized test label or pinned image')
    if info.get('State', {}).get('Running') is not True:
        raise ValueError('Container must already be running')
    mounts = info.get('Mounts', [])
    if EXPECTED_MOUNTS is None or len(mounts) != len(EXPECTED_MOUNTS):
        raise ValueError('Expected exactly the admitted read-only bindings')
    for destination, source in EXPECTED_MOUNTS.items():
        matches = [m for m in mounts if m.get('Destination') == destination]
        if (len(matches) != 1 or matches[0].get('RW') is not False or
                matches[0].get('Type') != 'bind' or matches[0].get('Source') != source):
            raise ValueError('Expected exact read-only binding: ' + destination)
    host = info.get('HostConfig', {})
    if host.get('Memory') != 47244640256 or host.get('MemorySwap') != 47244640256:
        raise ValueError('Expected 44 GiB cgroup limit without extra swap')
    ports = info.get('NetworkSettings', {}).get('Ports', {}).get('8731/tcp')
    if ports != [{'HostIp': '127.0.0.1', 'HostPort': '8731'}]:
        raise ValueError('Expected private localhost API publication')


class MemoryStatus(ctypes.Structure):
    _fields_ = [('length', ctypes.c_uint32), ('load', ctypes.c_uint32)] + [
        (name, ctypes.c_uint64) for name in ('total', 'available', 'total_page',
                                            'available_page', 'total_virtual',
                                            'available_virtual', 'extended')]


def available_windows_bytes():
    data = MemoryStatus()
    data.length = ctypes.sizeof(data)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(data)):
        raise OSError('GlobalMemoryStatusEx failed')
    return data.available


def run_docker(*args, timeout=5):
    return subprocess.run(WSL + list(args), capture_output=True, text=True,
                          timeout=timeout, check=True,
                          creationflags=subprocess.CREATE_NO_WINDOW).stdout


def health(url='http://127.0.0.1:8731/health'):
    try:
        with urllib.request.urlopen(url, timeout=3) as response:
            data = json.load(response)
            return data.get('status') == 'ok'
    except (OSError, ValueError):
        return False


def monitor(container_id, output, runtime_seconds=0):
    started = time.monotonic()
    pending = None
    last_advice = None
    ready_since = None
    last_inspect = 0
    minimum = None
    validated = False
    with pathlib.Path(output).open('x', encoding='utf-8') as log:
        workers = concurrent.futures.ThreadPoolExecutor(max_workers=2)
        health_future = None
        state_future = None
        last_health = -5
        health_good = False
        health_completed = None
        state_completed = None
        def event(kind, **values):
            item = dict(event=kind, utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                        elapsed=round(time.monotonic() - started, 3), **values)
            log.write(json.dumps(item) + '\n')
            log.flush()
            if kind != 'sample':
                print(json.dumps(item), flush=True)

        def best_effort_event(kind, **values):
            # Cleanup must survive disk-full, closed stdout and failed flushing.
            try:
                event(kind, **values)
            except Exception:
                pass
        try:
            info = json.loads(run_docker('inspect', container_id))[0]
            validate_target(info, container_id)
            validated = True
            state_completed = time.monotonic() - started
            event('validated', container_id=container_id, name=info['Name'],
                  image=info['Config']['Image'], reserve_bytes=(24 if runtime_seconds else 20) << 30,
                  advice_below_bytes=64 << 30, ready_reserve_bytes=24 << 30,
                  timeout_seconds=STARTUP_TIMEOUT_SECONDS,
                  phase='runtime' if runtime_seconds else 'startup',
                  duration_seconds=runtime_seconds if runtime_seconds else STARTUP_TIMEOUT_SECONDS)
            while True:
                elapsed = time.monotonic() - started
                available = available_windows_bytes()
                if available is not None and available >= 0:
                    minimum = available if minimum is None else min(minimum, available)
                if pending is not None:
                    if pending.poll() is not None:
                        stdout, stderr = pending.communicate()
                        code = pending.returncode
                        pending = None
                        event('advice_finished', returncode=code, stdout=stdout, stderr=stderr)
                        if code:
                            raise RuntimeError('Cache advice failed')
                    elif elapsed - last_advice > 20:
                        raise TimeoutError('Cache advice exceeded 20 seconds')
                # Pressure is checked before any potentially slow health/inspect operation.
                action = (decide_runtime(available, elapsed, runtime_seconds) if runtime_seconds
                          else decide(available, elapsed, False, pending is not None, last_advice))
                if action.startswith('stop_'):
                    raise RuntimeError(action)
                if state_future is not None and state_future.done():
                    state = json.loads(state_future.result())
                    state_future = None
                    if state.get('Running') is not True:
                        raise RuntimeError('Container exited during monitoring')
                    state_completed = time.monotonic() - started
                if state_future is None and elapsed - last_inspect >= 10:
                    state_future = workers.submit(run_docker, 'inspect', '--format',
                                                  '{{json .State}}', container_id)
                    last_inspect = elapsed
                if health_future is not None and health_future.done():
                    health_good = health_future.result()
                    health_future = None
                    health_completed = time.monotonic() - started
                if health_future is None and elapsed - last_health >= 5:
                    health_future = workers.submit(health)
                    last_health = elapsed
                healthy = probe_fresh(health_good, health_completed, time.monotonic() - started)
                action = (decide_runtime(available, time.monotonic() - started, runtime_seconds)
                          if runtime_seconds else decide(available, time.monotonic() - started,
                                                         healthy, pending is not None, last_advice))
                event('sample', available_bytes=available, healthy=healthy, action=action)
                if action.startswith('stop_'):
                    raise RuntimeError(action)
                if action == 'complete':
                    event('runtime_complete', minimum_available_bytes=minimum,
                          current_available_bytes=available)
                    return 0
                if action == 'ready':
                    ready_since = elapsed if ready_since is None else ready_since
                    if (elapsed - ready_since >= 10 and state_future is None
                            and probe_fresh(True, state_completed, time.monotonic() - started)):
                        event('ready', minimum_available_bytes=minimum,
                              current_available_bytes=available)
                        return 0
                else:
                    ready_since = None
                if action == 'advise':
                    pending = subprocess.Popen(WSL + ['exec', container_id, 'python3', '-c', CACHE_CODE],
                                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                               text=True, creationflags=subprocess.CREATE_NO_WINDOW)
                    last_advice = time.monotonic() - started
                    event('advice_started', available_bytes=available)
                time.sleep(1)
        except (Exception, KeyboardInterrupt) as error:
            best_effort_event('failed', error=repr(error), minimum_available_bytes=minimum)
            if validated:
                stopper = concurrent.futures.ThreadPoolExecutor(max_workers=1)
                try:
                    # Avoid grace-period allocations, and continue observing
                    # delayed driver cleanup.
                    stopping = stopper.submit(run_docker, 'stop', '-t', '0', container_id, timeout=30)
                    while not stopping.done():
                        try:
                            available = available_windows_bytes()
                            if available is not None and available >= 0:
                                minimum = available if minimum is None else min(minimum, available)
                            best_effort_event('stop_sample', available_bytes=available)
                        except Exception as telemetry_error:
                            best_effort_event('stop_telemetry_failed', error=repr(telemetry_error))
                        time.sleep(0.2)
                    result = stopping.result()
                    best_effort_event('stopped', container_id=container_id, stdout=result,
                                      minimum_available_bytes=minimum)
                except Exception as stop_error:
                    best_effort_event('stop_failed', error=repr(stop_error), container_id=container_id,
                                      minimum_available_bytes=minimum)
                finally:
                    stopper.shutdown(wait=False, cancel_futures=True)
            return 2
        finally:
            workers.shutdown(wait=False, cancel_futures=True)
            if pending is not None:
                try:
                    pending.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    pending.kill()  # only this WSL client; the named container was stopped above
                    pending.communicate(timeout=5)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--container-id', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--runtime-seconds', type=int, default=0)
    parser.add_argument('--distro', required=True)
    parser.add_argument('--user', required=True)
    parser.add_argument('--models', required=True)
    parser.add_argument('--workspace', required=True)
    parser.add_argument('--dxg', required=True)
    args = parser.parse_args()
    if os.name != 'nt':
        parser.error('Run on Windows, not inside WSL')
    if not re.fullmatch('[0-9a-f]{64}', args.container_id):
        parser.error('Use the full 64-character container ID')
    if args.runtime_seconds != 0 and not 30 <= args.runtime_seconds <= 3600:
        parser.error('--runtime-seconds must be 0 or between 30 and 3600')
    configure_target(args.distro, args.user, args.models, args.workspace, args.dxg)
    return monitor(args.container_id, args.output, runtime_seconds=args.runtime_seconds)


if __name__ == '__main__':
    raise SystemExit(main())
