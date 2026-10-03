"""Startup-only file-cache advice and measured guest/cgroup memory.

Runs INSIDE the owned container, never clears host-wide caches. Only the two
read-only model files receive DONTNEED advice. Must exit before client inference.
"""
import argparse
import json
import os
from pathlib import Path
import re
import time

MODELS = ('/models/qwen38-flash-next-w4b.hgn',
          '/models/qwen38-flash-next-w4b.overlay.hgn')


def memory_snapshot():
    values = {}
    for line in Path('/proc/meminfo').read_text().splitlines():
        key, value = line.split(':', 1)
        if key in ('MemTotal', 'MemFree', 'MemAvailable', 'Cached', 'SwapFree', 'AnonPages'):
            values[key] = int(value.split()[0]) * 1024
    for line in Path('/sys/fs/cgroup/memory.stat').read_text().splitlines():
        key, value = line.split()
        if key in ('anon', 'file', 'file_mapped', 'inactive_file', 'active_file', 'unevictable'):
            values['cgroup_' + key] = int(value)
    values['cgroup_current'] = int(Path('/sys/fs/cgroup/memory.current').read_text())
    return values


def advise(descriptors):
    # No file writes and no mmap/madvise on registered model pages.
    for fd in descriptors:
        os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_DONTNEED)


def run(run_id, stop_file, seconds, *, paths=MODELS, interval=1.0,
        clock=time.monotonic, sleep=time.sleep, emit=None, snapshot=memory_snapshot):
    if not re.fullmatch('[0-9a-f]{32}', run_id):
        raise ValueError('Exact service run ID required')
    if seconds <= 0 or interval <= 0:
        raise ValueError('Positive startup limits required')
    if emit is None:
        emit = lambda value: print(json.dumps(value, allow_nan=False), flush=True)
    descriptors = []
    begin = clock()
    try:
        for path in paths:
            descriptors.append(os.open(path, os.O_RDONLY | getattr(os, 'O_CLOEXEC', 0)))
        while clock() - begin < seconds:
            if stop_file.exists():
                if json.loads(stop_file.read_text()) != {'run_id':run_id}:
                    raise ValueError('Invalid startup-cache stop target')
                emit({'event':'stopped', 'run_id':run_id, 'elapsed':clock()-begin})
                return 0
            before = snapshot()
            started = clock()
            advise(descriptors)
            after = snapshot()
            emit({'event':'advice', 'run_id':run_id, 'elapsed':clock()-begin,
                  'duration':clock()-started, 'before':before, 'after':after})
            sleep(interval)
        raise TimeoutError('Startup-cache deadline expired; model is not ready')
    finally:
        for fd in descriptors:
            os.close(fd)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run-id', required=True)
    p.add_argument('--seconds', type=int, required=True)
    args = p.parse_args(argv)
    variant=os.environ.get('HALOGEN_CHECKPOINT_VARIANT','w4b')
    if variant not in ('w4b','v2'): raise ValueError('Unknown startup-cache checkpoint')
    paths=MODELS if variant=='w4b' else ('/models/qwen38-flash-next-v2.hgn',)
    return run(args.run_id, Path('/service-state/cache-stop.json'), args.seconds,paths=paths)


if __name__ == '__main__':
    raise SystemExit(main())
