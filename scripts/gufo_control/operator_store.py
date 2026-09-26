"""Fixed provenance and durable state for the private operator experiment."""
from contextlib import contextmanager
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import subprocess
import uuid

from .operator_policy import Baseline, POLICY_ID, PROBES, SOURCE_COMMIT

ROOT = Path(r'C:\Projects\strix-alloy-research')
SOURCE = ROOT / 'sources/gufo-windows'
BUILD = ROOT / 'build/gufo-hip-10.2/tests/models/qwen38_flash_next'
SDK = Path(r'C:\AI\sdk\therock1151')
EVIDENCE = ROOT / 'reports/gufo-operator-runs'
DLLS = ('amdhip64_7.dll', 'rocm_kpack.dll', 'amd_comgr.dll')


def atomic_json(path, value):
    path = Path(path)
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    with temp.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, path)


def read_json(path):
    path = Path(path)
    if path.stat().st_size > 2*1024*1024:
        raise ValueError('oversized_state')
    with path.open(encoding='utf-8') as stream:
        return json.load(stream)


@contextmanager
def exclusive(root):
    import msvcrt
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    with (root / 'runner.lock').open('a+b') as stream:
        if stream.seek(0, 2) == 0:
            stream.write(b'0')
            stream.flush()
        stream.seek(0)
        try:
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as error:
            raise RuntimeError('operator_runner_busy') from error
        try:
            yield
        finally:
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)


def source_identity():
    def git(*args):
        p = subprocess.run(['git', '-C', str(SOURCE), *args],
            capture_output=True, text=True, timeout=5,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if p.returncode:
            raise ValueError('source_identity_unavailable')
        return p.stdout.strip()
    if git('rev-parse', 'HEAD') != SOURCE_COMMIT or git('status', '--porcelain'):
        raise ValueError('source_identity_changed')


def stamp(path):
    path = Path(path).resolve(strict=True)
    if not path.is_file():
        raise ValueError('artifact_not_file')
    s = path.stat()
    return [str(path), s.st_size, s.st_mtime_ns]


def verify(probe):
    if PROBES.get(probe.key) != probe:
        raise ValueError('unknown_probe')
    source_identity()
    if any(not (SDK/part).is_dir() for part in
           ('bin', 'lib/llvm/bin', 'lib/llvm/amdgcn/bitcode')):
        raise ValueError('sdk_directory_missing')
    exe = BUILD / probe.filename
    paths = [exe, *(SDK/'bin'/name for name in DLLS)]
    for name in DLLS:
        if (BUILD/name).exists():
            raise ValueError('shadow_sdk_dll')
    artifacts = []
    for path in paths:
        before = stamp(path)
        digest = hashlib.sha256()
        with path.open('rb') as stream:
            for block in iter(lambda: stream.read(1024*1024), b''):
                digest.update(block)
        if stamp(path) != before:
            raise ValueError('artifact_changed_during_hash')
        artifacts.append({'stamp': before, 'sha256': digest.hexdigest().upper()})
    if artifacts[0]['sha256'] != probe.sha256:
        raise ValueError('binary_hash_mismatch')
    return {'policy': POLICY_ID, 'source': SOURCE_COMMIT,
            'probe': probe.key, 'executable': str(exe.resolve()),
            'sdk': str(SDK), 'artifacts': artifacts}


def recheck(manifest):
    source_identity()
    for entry in manifest['artifacts']:
        if stamp(entry['stamp'][0]) != entry['stamp']:
            raise ValueError('artifact_changed')
    if any((BUILD/name).exists() for name in DLLS):
        raise ValueError('shadow_sdk_dll')


def child_environment(parent):
    forbidden = ('HIP_VISIBLE_DEVICES', 'ROCR_VISIBLE_DEVICES', 'GPU_DEVICE_ORDINAL')
    if any(k.upper() in forbidden or k.upper().startswith('HSA_') for k in parent):
        raise ValueError('inherited_gpu_override')
    path = next((v for k, v in parent.items() if k.upper() == 'PATH'), '')
    env = {k: v for k, v in parent.items()
           if not k.upper().startswith('GUFO_')
           and k.upper() not in ('PATH', 'HIP_PATH', 'HIP_DEVICE_LIB_PATH')}
    env.update(PATH=str(SDK/'bin')+os.pathsep+str(SDK/'lib/llvm/bin')+os.pathsep+path,
               HIP_PATH=str(SDK), HIP_DEVICE_LIB_PATH=str(SDK/'lib/llvm/amdgcn/bitcode'))
    return env


def sequence_baseline(root, key):
    root = Path(root)
    if (root/'incomplete.json').exists():
        raise ValueError('prior_cleanup_unconfirmed')
    path = root/'sequence.json'
    if not path.exists():
        if key != 'gdn':
            raise ValueError('gdn_required')
        return None
    state = read_json(path)
    if (key != 'iq-experts' or state.get('stage') != 'gdn'
            or state.get('policy') != POLICY_ID or state.get('source') != SOURCE_COMMIT
            or state.get('binary') != PROBES['gdn'].sha256
            or state.get('success') is not True):
        raise ValueError('prior_stage_requires_review')
    values = state['baseline']
    return Baseline(tuple(values['identity']), values['available_min'],
        values['committed_max'], tuple(values['gpu_max']),
        values['first_start'], values['last_end'])


def begin(root, run_dir, probe, base):
    path = Path(root)/'incomplete.json'
    # Called under exclusive(); existence is checked again, never overwritten.
    if path.exists():
        raise ValueError('prior_cleanup_unconfirmed')
    atomic_json(path, {'run': str(run_dir), 'probe': probe.key,
        'phase': 'before_create', 'baseline': asdict(base)})


def finish(root, run_dir, probe, base, result):
    atomic_json(Path(run_dir)/'result.json', result)
    atomic_json(Path(root)/'sequence.json', {'stage': probe.key,
        'policy': POLICY_ID, 'source': SOURCE_COMMIT, 'binary': probe.sha256,
        'success': result['success'], 'baseline': asdict(base), 'run': str(run_dir)})
    if result['cleanup_confirmed']:
        (Path(root)/'incomplete.json').unlink()
