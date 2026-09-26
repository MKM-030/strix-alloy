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
DLL_SHA256 = {
    'amdhip64_7.dll': '71C41D9DB361E544D1CB6DFF91530D5705FFC5F1A91BA8EDCF583FB882E282BF',
    'rocm_kpack.dll': '9B6ABC1A45443709309AD136ED09C60EEEC45E77A003A23F6B35730036085649',
    'amd_comgr.dll': 'EA2825C6588FD48536377309848999C9EF98137C0FA8E8424D0B7CAD95D0F724',
}
RUNTIME_POLICY = 'app-local-sdk-three-dlls-v1'
REVIEWED_FAILED_RUN = EVIDENCE / '20260926T125657Z-7f662648dd3c4ff887bdb875297023a1'
REVIEWED_RESULT_SHA256 = '2DDF73DCB8B6DB10693DCE880EFB0192C58696401F7A8FEB79D6738F3F998F91'
REVIEWED_OLD_POLICY = 'operator-bootstrap-v1'


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


def artifact_record(path):
    path = Path(path)
    before = stamp(path)
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            digest.update(block)
    if stamp(path) != before:
        raise ValueError('artifact_changed_during_hash')
    return {'stamp': before, 'sha256': digest.hexdigest().upper()}


def _runtime_artifacts(probe):
    return [
        (BUILD/probe.filename, probe.sha256),
        *((SDK/'bin'/name, DLL_SHA256[name]) for name in DLLS),
        *((BUILD/name, DLL_SHA256[name]) for name in DLLS),
    ]


def verify(probe):
    if PROBES.get(probe.key) != probe:
        raise ValueError('unknown_probe')
    source_identity()
    if any(not (SDK/part).is_dir() for part in
           ('bin', 'lib/llvm/bin', 'lib/llvm/amdgcn/bitcode')):
        raise ValueError('sdk_directory_missing')
    artifacts = []
    for index, (path, expected) in enumerate(_runtime_artifacts(probe)):
        record = artifact_record(path)
        if record['sha256'] != expected:
            raise ValueError('binary_hash_mismatch' if index == 0
                             else 'runtime_dll_hash_mismatch')
        artifacts.append(record)
    return {'policy': POLICY_ID, 'source': SOURCE_COMMIT,
            'probe': probe.key, 'executable': str((BUILD/probe.filename).resolve()),
            'sdk': str(SDK), 'runtime_policy': RUNTIME_POLICY,
            'artifacts': artifacts}


def recheck(manifest):
    source_identity()
    try:
        probe = PROBES[manifest['probe']]
        expected = _runtime_artifacts(probe)
        entries = manifest['artifacts']
        if (manifest['policy'] != POLICY_ID or manifest['source'] != SOURCE_COMMIT
                or manifest['runtime_policy'] != RUNTIME_POLICY
                or manifest['sdk'] != str(SDK)
                or manifest['executable'] != str((BUILD/probe.filename).resolve())
                or len(entries) != len(expected)):
            raise ValueError('manifest_runtime_mismatch')
        for entry, (path, digest) in zip(entries, expected):
            if (entry['sha256'] != digest
                    or entry['stamp'][0] != str(path.resolve())):
                raise ValueError('manifest_runtime_mismatch')
    except (KeyError, TypeError, IndexError) as error:
        raise ValueError('manifest_runtime_mismatch') from error
    for entry in entries:
        if stamp(entry['stamp'][0]) != entry['stamp']:
            raise ValueError('artifact_changed')


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


def _reviewed_retry(root, state):
    try:
        if (root.resolve() != EVIDENCE.resolve()
                or state.get('run') != str(REVIEWED_FAILED_RUN)):
            raise ValueError('prior_stage_requires_review')
        path = REVIEWED_FAILED_RUN/'result.json'
        before = stamp(path)
        if before[1] > 2*1024*1024:
            raise ValueError('prior_stage_requires_review')
        # Authenticate exactly the bytes parsed below; never reopen after hashing.
        with path.open('rb') as stream:
            payload = stream.read(2*1024*1024 + 1)
        if (len(payload) > 2*1024*1024 or stamp(path) != before
                or hashlib.sha256(payload).hexdigest().upper() != REVIEWED_RESULT_SHA256):
            raise ValueError('prior_stage_requires_review')
        result = json.loads(payload)
        manifest = result['manifest']
        if (result['success'] is not False or result['numerical_pass'] is not False
                or result['cleanup_confirmed'] is not True
                or result['owned_exit_confirmed'] is not True
                or result['collector_terminal'] is not True
                or result['recovery_samples'] != 5
                or result['exit_code'] != 0xC0000005
                or result['failure'] != 'nonzero_exit'
                or manifest['policy'] != REVIEWED_OLD_POLICY
                or POLICY_ID != REVIEWED_OLD_POLICY
                or manifest['source'] != SOURCE_COMMIT
                or manifest['probe'] != 'gdn'
                or manifest['executable'] != str(BUILD/PROBES['gdn'].filename)
                or manifest['sdk'] != str(SDK)
                or [entry['sha256'] for entry in manifest['artifacts']] !=
                   [PROBES['gdn'].sha256, *(DLL_SHA256[name] for name in DLLS)]):
            raise ValueError('prior_stage_requires_review')
        values = result['original_baseline']
        expected_state = {
            'stage': 'gdn', 'policy': REVIEWED_OLD_POLICY, 'source': SOURCE_COMMIT,
            'binary': PROBES['gdn'].sha256, 'success': False,
            'baseline': values, 'run': str(REVIEWED_FAILED_RUN),
        }
        if state != expected_state:
            raise ValueError('prior_stage_requires_review')
        return values
    except (OSError, KeyError, TypeError, ValueError, AttributeError) as error:
        raise ValueError('prior_stage_requires_review') from error


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
    if key == 'gdn':
        values = _reviewed_retry(root, state)
    else:
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
