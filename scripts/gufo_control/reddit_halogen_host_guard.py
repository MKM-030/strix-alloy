"""User-authorized 12 GiB physical and 12 GiB commit guard for one owned container."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import ctypes
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import time
from datetime import datetime, timezone

GIB = 1 << 30
PUBLIC = Path(r'C:\Projects\strix-alloy-wsl2\scripts')
sys.path.insert(0, str(PUBLIC))
spec = importlib.util.spec_from_file_location('pinned_public_guard', PUBLIC/'guard-halogen-startup.py')
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)
guard.configure_target('Ubuntu-24.04', 'revn', '/mnt/halogen-wsl-ext4/models',
                       '/mnt/c/Users/Marcel/Documents/Codex/2026-08-25/goal-ermittle-und-implementiere-auf-meinem',
                       '/home/revn/ciru-runtime/venv/lib/python3.14/site-packages/_rocm_sdk_devel/lib/librocdxg.so')


class Memory(ctypes.Structure):
    _fields_ = [('length', ctypes.c_uint32), ('load', ctypes.c_uint32)] + [
        (key, ctypes.c_uint64) for key in ('total', 'available', 'total_page', 'available_page',
                                          'total_virtual', 'available_virtual', 'extended')]


class Performance(ctypes.Structure):
    _fields_ = [('length', ctypes.c_uint32)] + [
        (key, ctypes.c_size_t) for key in ('commit_total', 'commit_limit', 'commit_peak',
                                          'physical_total', 'physical_available', 'system_cache',
                                          'kernel_total', 'kernel_paged', 'kernel_nonpaged', 'page_size')] + [
        (key, ctypes.c_uint32) for key in ('handle_count', 'process_count', 'thread_count')]


def frame():
    m, p = Memory(), Performance()
    m.length, p.length = ctypes.sizeof(m), ctypes.sizeof(p)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)):
        raise OSError('GlobalMemoryStatusEx_failed')
    if not ctypes.windll.psapi.GetPerformanceInfo(ctypes.byref(p), p.length):
        raise OSError('GetPerformanceInfo_failed')
    return dict(available_bytes=m.available, committed_bytes=p.commit_total*p.page_size,
                commit_limit_bytes=p.commit_limit*p.page_size,
                commit_headroom_bytes=(p.commit_limit-p.commit_total)*p.page_size)


def inspect(container):
    return json.loads(guard.run_docker('inspect', container, timeout=8))[0]


def owned(info, container, *, running):
    if info.get('Id') != container or info.get('Name') != '/' + info.get('Config', {}).get('Labels', {}).get('strix-alloy.run', ''):
        raise ValueError('owned_container_identity_invalid')
    if not re.fullmatch(r'/halogen-flash-hybrid-reddit-(mixed|repetitive)-[0-9a-f]{32}', info['Name']):
        raise ValueError('owned_container_name_invalid')
    if info['Config']['Image'] != guard.IMAGE or info['Config']['Labels'].get('strix-alloy.owner') != 'strix-alloy-wsl2':
        raise ValueError('owned_container_image_or_label_invalid')
    if running:
        guard.validate_target(info, container)


def monitor(container, output, release):
    started = time.monotonic()
    validated = False
    with Path(output).open('x', encoding='utf-8') as log:
        def event(kind, **values):
            log.write(json.dumps(dict(utc=datetime.now(timezone.utc).isoformat(), event=kind,
                                      elapsed_seconds=time.monotonic()-started, **values))+'\n')
            log.flush()
        info = inspect(container)
        owned(info, container, running=False)
        first = frame()
        event('sample', **first)
        if first['available_bytes'] < 12*GIB or first['commit_headroom_bytes'] < 12*GIB:
            event('initial_floor_unsafe', **first)
            return 2
        event('armed', container_id=container, **first)
        tripped = False
        stop_future = None
        stop_logged = False
        def stop_owned():
            current = inspect(container)
            running = bool(current.get('State', {}).get('Running'))
            owned(current, container, running=running)
            if running:
                guard.run_docker('stop', '-t', '0', container, timeout=45)
            terminal = inspect(container)
            owned(terminal, container, running=False)
            if terminal.get('State', {}).get('Running') or terminal.get('State', {}).get('Pid') != 0:
                raise ValueError('exact_container_not_terminal')
            return terminal['Id']
        with ThreadPoolExecutor(max_workers=1) as worker:
            while time.monotonic()-started < 4200:
                try:
                    reading = frame()
                    event('sample', **reading)
                    if not validated and stop_future is None:
                        info = inspect(container)
                        owned(info, container, running=False)
                        if info.get('State', {}).get('Running') is True:
                            owned(info, container, running=True)
                            validated = True
                            event('validated', container_id=container)
                    if reading['available_bytes'] < 12*GIB or reading['commit_headroom_bytes'] < 12*GIB:
                        event('floor_crossed', **reading)
                        tripped = True
                except Exception as error:
                    event('telemetry_or_identity_error', detail=type(error).__name__+':'+str(error))
                    tripped = True
                if tripped and stop_future is None:
                    stop_future = worker.submit(stop_owned)
                    event('exact_container_stop_started', container_id=container)
                if stop_future is not None and stop_future.done() and not stop_logged:
                    try:
                        event('exact_container_terminal', container_id=stop_future.result())
                    except Exception as error:
                        event('stop_failed', detail=type(error).__name__+':'+str(error))
                    stop_logged = True
                if Path(release).exists() and (stop_future is None or stop_future.done()):
                    event('released_after_cleanup', container_id=container, tripped=tripped)
                    return 2 if tripped else 0
                time.sleep(1)
            event('deadline_exceeded')
            return 4


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--container-id', required=True)
    p.add_argument('--output', required=True)
    p.add_argument('--release', required=True)
    a = p.parse_args()
    if not re.fullmatch('[0-9a-f]{64}', a.container_id) or sys.platform != 'win32':
        p.error('Windows and exact container ID required')
    return monitor(a.container_id, a.output, a.release)


if __name__ == '__main__':
    sys.exit(main())
