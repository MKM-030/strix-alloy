"""Startup-only file-cache advice and measured guest/cgroup memory.

Runs INSIDE the owned container, never clears host-wide caches. Only the two
read-only model files receive DONTNEED advice. Must exit before client inference.
"""
import argparse
import json
import os
from pathlib import Path, PurePosixPath
import re
import time

MODELS = ('/models/qwen38-flash-next-w4b.hgn',
          '/models/qwen38-flash-next-w4b.overlay.hgn')

CGROUP_STAT_KEYS = ('anon', 'file', 'file_mapped', 'inactive_file',
                    'active_file', 'unevictable')


def _mount_path(value):
    # mountinfo escapes these four characters. Decode once: a literal
    # backslash followed by digits must not become a second escape.
    escapes = {'040': ' ', '011': '\t', '012': '\n', '134': '\\'}
    if re.search(r'\\(?!040|011|012|134)', value):
        raise ValueError('Invalid mountinfo path escape')
    return re.sub(r'\\(040|011|012|134)', lambda match: escapes[match[1]], value)


def _path_components(value):
    if not value.startswith('/') or '\x00' in value:
        raise ValueError('Absolute cgroup path required')
    components = value.split('/')[1:]
    if value == '/':
        return ()
    if any(component in ('', '.', '..') for component in components):
        raise ValueError('Noncanonical cgroup path')
    return tuple(components)


def resolve_cgroup_memory_path(cgroup_text, mountinfo_text):
    memberships = []
    for line in cgroup_text.splitlines():
        fields = line.split(':', 2)
        if len(fields) != 3:
            raise ValueError('Malformed cgroup membership')
        if fields[:2] == ['0', '']:
            # /proc/self/cgroup is literal, unlike mountinfo path fields.
            if fields[2].endswith(' (deleted)'):
                raise ValueError('Deleted cgroup membership')
            memberships.append(_path_components(fields[2]))
    if len(memberships) != 1:
        raise ValueError('Exactly one unified cgroup membership required')
    member = memberships[0]
    candidates = []
    for line in mountinfo_text.splitlines():
        parts = line.split(' - ')
        if len(parts) != 2:
            raise ValueError('Malformed mountinfo record')
        fields, filesystem = parts[0].split(), parts[1].split()
        if len(fields) < 6 or len(filesystem) < 3:
            raise ValueError('Malformed mountinfo fields')
        if filesystem[0] != 'cgroup2':
            continue
        root = _path_components(_mount_path(fields[3]))
        mountpoint = _path_components(_mount_path(fields[4]))
        if member[:len(root)] == root:
            path = PurePosixPath('/').joinpath(*mountpoint, *member[len(root):])
            candidates.append((len(root), path))
    if not candidates:
        raise ValueError('No cgroup2 mount covers unified membership')
    specificity = max(depth for depth, path in candidates)
    matches = [path for depth, path in candidates if depth == specificity]
    if len(matches) != 1:
        raise ValueError('Ambiguous cgroup2 mount for unified membership')
    return matches[0]


def cgroup_memory_snapshot():
    directory = Path(str(resolve_cgroup_memory_path(
        Path('/proc/self/cgroup').read_text(),
        Path('/proc/self/mountinfo').read_text())))
    values = {'schema': 'startup-cache-cgroup-memory-v1',
              'cgroup_path': directory.as_posix()}
    for metric in ('memory.current', 'memory.peak', 'memory.swap.current'):
        value = (directory / metric).read_text().strip()
        if not re.fullmatch('[0-9]+', value):
            raise ValueError('Invalid cgroup metric: ' + metric)
        values[metric] = int(value)
    stat = {}
    for line in (directory / 'memory.stat').read_text().splitlines():
        key, value = line.split()
        if key in CGROUP_STAT_KEYS:
            if key in stat or not re.fullmatch('[0-9]+', value):
                raise ValueError('Invalid cgroup memory.stat field: ' + key)
            stat[key] = int(value)
    if set(stat) != set(CGROUP_STAT_KEYS):
        raise ValueError('Incomplete cgroup memory.stat telemetry')
    values['memory.stat'] = stat
    return values


def memory_snapshot():
    cgroup = cgroup_memory_snapshot()
    values = {'cgroup_path': cgroup['cgroup_path'],
              'cgroup_current': cgroup['memory.current']}
    for line in Path('/proc/meminfo').read_text().splitlines():
        key, value = line.split(':', 1)
        if key in ('MemTotal', 'MemFree', 'MemAvailable', 'Cached', 'SwapFree', 'AnonPages'):
            values[key] = int(value.split()[0]) * 1024
    for key, value in cgroup['memory.stat'].items():
        values['cgroup_' + key] = value
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
    p.add_argument('--memory-only', action='store_true',
                   help='Read this process cgroup only; do not open models or advise cache')
    p.add_argument('--run-id')
    p.add_argument('--seconds', type=int)
    args = p.parse_args(argv)
    if args.memory_only:
        if args.run_id is not None or args.seconds is not None:
            p.error('--memory-only cannot be combined with worker arguments')
        print(json.dumps(cgroup_memory_snapshot(), allow_nan=False), flush=True)
        return 0
    if args.run_id is None or args.seconds is None:
        p.error('--run-id and --seconds are required for the startup worker')
    variant=os.environ.get('HALOGEN_CHECKPOINT_VARIANT','w4b')
    if variant not in ('w4b','v2'): raise ValueError('Unknown startup-cache checkpoint')
    paths=MODELS if variant=='w4b' else ('/models/qwen38-flash-next-v2.hgn',)
    return run(args.run_id, Path('/service-state/cache-stop.json'), args.seconds,paths=paths)


if __name__ == '__main__':
    raise SystemExit(main())
