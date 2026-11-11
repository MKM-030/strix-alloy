"""Read-only, finite DNZ counter reader. Import performs no process/file I/O.

Only Root's explicit campaign calls capture(). No ptrace, rights changes,
library loading, model requests or writes to the native address space exist.
"""
import hashlib
import json
import os
from pathlib import Path
import struct
import time

ENGINE_SHA = 'bf84053705d1e89c214ff64c79ad1276c5fe353d80a9bb0f38ef3bac6645b97c'
RVA = 0x21ca518


def need(value, message):
    if not value:
        raise ValueError(message)


def parse_maps(text):
    result = []
    for line in text.splitlines():
        fields = line.split(None, 5)
        need(len(fields) >= 5, 'Incomplete native mapping')
        start, end = (int(part, 16) for part in fields[0].split('-'))
        major, minor = (int(part, 16) for part in fields[3].split(':'))
        result.append(dict(start=start, end=end, permissions=fields[1],
                           offset=int(fields[2], 16), major=major, minor=minor,
                           inode=int(fields[4]), path=fields[5] if len(fields) == 6 else ''))
    return result


def locate_counter(text, major, minor, inode):
    maps = parse_maps(text)
    zero = [item for item in maps if item['offset'] == 0
            and (item['major'], item['minor'], item['inode']) == (major, minor, inode)]
    need(len(zero) == 1, 'One exact executable offset-zero mapping is required')
    base = zero[0]['start']
    address = base + RVA
    need(address % 8 == 0, 'Counter address is not uint64 aligned')
    regions = [item for item in maps if item['start'] <= address and address + 8 <= item['end']]
    need(len(regions) == 1 and regions[0]['permissions'].startswith('r'),
         'Complete8-byte counter must lie in one readable mapping')
    return dict(load_base=base, counter_address=address, counter_region=regions[0])


def process_identity(proc, engine_sha=ENGINE_SHA):
    stat_text = (proc / 'stat').read_text()
    starttime = int(stat_text.rsplit(')', 1)[1].split()[19])
    exe = proc / 'exe'
    before = exe.stat()
    data = exe.read_bytes()
    after = exe.stat()
    need((before.st_dev, before.st_ino, before.st_size) ==
         (after.st_dev, after.st_ino, after.st_size), 'Native executable changed during seal')
    digest = hashlib.sha256(data).hexdigest()
    need(digest == engine_sha, 'Exact native ELF SHA differs')
    need(data[:6] == b'\x7fELF\x02\x01' and len(data) >= 20
         and struct.unpack_from('<H', data, 16)[0] == 3, 'Exact little-endian ET_DYN ELF required')
    need(int((proc / 'stat').read_text().rsplit(')', 1)[1].split()[19]) == starttime,
         'Native PID starttime changed during seal')
    return dict(pid=int(proc.name), starttime_ticks=starttime,
                executable=os.readlink(exe), device=before.st_dev,
                inode=before.st_ino, bytes=before.st_size, sha256=digest)


def read_counter(expected=None, proc_root='/proc'):
    """Two process seals surround exactly one8-byte pread, outside model timing."""
    root = Path(proc_root)
    if expected is None:
        candidates = []
        for item in root.iterdir():
            if not item.name.isdigit():
                continue
            try:
                if Path(os.readlink(item / 'exe')).name == 'flash_serve':
                    candidates.append(item)
            except (FileNotFoundError, ProcessLookupError, PermissionError):
                continue
        need(len(candidates) == 1, 'Exactly one native flash_serve process required')
        proc = candidates[0]
    else:
        need(type(expected) is dict and type(expected.get('identity', {}).get('pid')) is int,
             'Exact previous process seal required')
        proc = root / str(expected['identity']['pid'])
    identity = process_identity(proc)
    located = locate_counter((proc / 'maps').read_text(),
                             os.major(identity['device']), os.minor(identity['device']),
                             identity['inode'])
    if expected is not None:
        need(identity == expected['identity']
             and hex(located['load_base']) == expected['load_base']
             and hex(located['counter_address']) == expected['counter_address'],
             'Native process or load mapping changed')
    began = time.perf_counter_ns()
    descriptor = os.open(proc / 'mem', os.O_RDONLY)
    try:
        data = os.pread(descriptor, 8, located['counter_address'])
    finally:
        os.close(descriptor)
    ended = time.perf_counter_ns()
    need(len(data) == 8, 'Incomplete native uint64 counter read')
    need(process_identity(proc) == identity, 'Native process changed around counter read')
    need(locate_counter((proc / 'maps').read_text(),
                        os.major(identity['device']), os.minor(identity['device']),
                        identity['inode']) == located, 'Native mappings changed around counter read')
    return dict(identity=identity, load_base=hex(located['load_base']),
                counter_rva=hex(RVA), counter_address=hex(located['counter_address']),
                counter_region=located['counter_region'], counter_value=struct.unpack('<Q', data)[0],
                read_started_ns=began, read_finished_ns=ended, clock='container perf_counter_ns',
                read_only=True, counter_bytes=8)


def capture(runtime, active, expected=None):
    """Called only by Root's --run path; use the already-owned container."""
    container = active['inner']['container_id']
    if expected is not None:
        need(expected.get('container_id') == container, 'Counter container ownership changed')
    source = Path(__file__).read_text(encoding='utf-8')
    code = ("n={'__name__':'dnz_read_only_counter'};exec(compile(" + repr(source)
            + ",'dnz_counter_bound.py','exec'),n);print(n['json'].dumps(n['read_counter'](expected="
            + repr(expected) + ')))')
    result = json.loads(runtime.ops.docker('exec', container, 'python3', '-c', code))
    result['container_id'] = container
    return result


def qualify_delta(before, after, mode):
    need(type(mode) is int and mode in (0, 1), 'Exact DNZ switch required')
    need(before['identity'] == after['identity']
         and before['container_id'] == after['container_id']
         and before['counter_address'] == after['counter_address'],
         'Counter process/container/address changed')
    values = (before['counter_value'], after['counter_value'])
    need(all(type(value) is int and 0 <= value < 1 << 64 for value in values),
         'Native unsigned64 counter values required')
    need(values[1] >= values[0], 'Counter reset or wrap cannot be corrected')
    delta = values[1] - values[0]
    need(delta > 0 if mode else delta == 0,
         'Candidate needs successful DNZ enqueues; Stock must have zero enqueues')
    return delta
