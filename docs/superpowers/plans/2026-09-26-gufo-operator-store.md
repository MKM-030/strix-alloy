# GUFO Operator Store Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement these tasks with independent review between them. Planning creates only this private report; implementation/GPU execution is not performed here.

**Goal:** Run one pinned model-free operator under job ownership, an independent telemetry watchdog, durable evidence and fail-closed cleanup state.

**Architecture:** A small persistence/provenance module supports a foreground runner. The runner consumes the reviewed pure operator policy and OwnedProcess APIs; its main thread owns the process and deadlines while one daemon worker performs each non-overlapping telemetry query. No detached service, HTTP, general command runner or mutable model qualification.

**Tech Stack:** Existing Python standard library, Windows msvcrt lock, existing gufo_control modules, unittest.

## Global Constraints

- Integration root `C:\Projects\strix-alloy-research\integration`. All implementation paths below are relative to it.
- Before every test command, set `$env:PYTHONPATH = Join-Path $PWD 'scripts'` from that root in the child shell. This absolute path is mandatory because existing guardian tests launch Python from temporary working directories; a relative `scripts` path breaks their imports.
- Consume `operator_policy` exactly as specified in `reports/gufo-operator-policy-plan-20260926.md`: PROBES, Frame, Baseline, baseline, admission_reasons, runtime_reasons, recovery_reasons. No fake model revision or alteration of policy constants.
- Reviewed winjob at9d3ed93: `OwnedProcess(argv, cwd=..., env=..., stdout_path=..., stderr_path=...)`; `identity`; `resume()`; `wait(timeout_ms=0)`; `exit_code()`; `close(timeout_ms=...)`. Construction is suspended and job-assigned; both log paths exclusive. Construction exceptions may carry `.owner` requiring cleanup.
- Query duration<=2s; final prelaunch age<=2s; current sample age<=5s; active query watchdog2s independent of blocking collector. Physical49/24GiB and commit12GiB remain fixed. No more than one query at a time; starts>=1s apart.
- Only CLI `python -m gufo_control.operator_probe gdn` or `... iq-experts`. One launch maximum. Fixed paths and profiles; no override flags, reset flag, fake telemetry CLI or model/server target.
- A GDN successful outcome must precede IQ. Invocation of the IQ command follows the parent's review of GDN evidence; the CLI's hard gate requires that successful saved result. It does not manufacture a human review token. Repeating either stage or recovering a stale latch requires separate engineering review; no automatic retries.
- An OS process lock prevents concurrent invocations; durable latch survives crashes. Store original sequence Baseline after GDN; IQ collects a fresh stable series for eligibility but compares run/recovery against the saved original baseline.
- Source/hash verification is before final telemetry; executable/DLL metadata and source HEAD/clean status are rechecked after final telemetry and before creation. Freshness rechecked after suspended creation, before resume. No concurrent build/update is permitted. Metadata recheck does not defend against a malicious replacement preserving size/mtime; do not claim it does.
- Preserve full stdout/stderr, raw snapshots, manifest and failed results. Main-thread disk writes and OS APIs cannot provide hard real-time guarantees under an OS/driver/filesystem hang. Worker isolation avoids ordinary blocked collection delaying the watchdog; it cannot prevent a driver freeze.
- Future implementer runs only listed offline/mocked and harmless child tests, not the production CLI. No GPU/model/WSL work or publication. Commits only if authorized by parent.

### Task 1: Provenance, lock and durable sequence state

**Create:** `scripts/gufo_control/operator_store.py`, `tests/gufo/test_operator_store.py`.

- [ ] Add the complete tests below first, observe focused import failure, then add the complete module below.

```python
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
```

```python
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from gufo_control import operator_store as store
from gufo_control.operator_policy import Baseline, PROBES


class StoreTests(unittest.TestCase):
    def test_atomic_and_latch_and_failed_result(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            run = root/'run'
            run.mkdir()
            base = Baseline(('test',), 100, 200, (1, 2, 3), 0, 11)
            store.begin(root, run, PROBES['gdn'], base)
            with self.assertRaisesRegex(ValueError, 'cleanup'):
                store.sequence_baseline(root, 'gdn')
            store.finish(root, run, PROBES['gdn'], base,
                         {'success': False, 'cleanup_confirmed': True})
            self.assertFalse((root/'incomplete.json').exists())
            with self.assertRaisesRegex(ValueError, 'review'):
                store.sequence_baseline(root, 'iq-experts')
            self.assertFalse(store.read_json(run/'result.json')['success'])

    def test_write_failure_keeps_latch(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            base = Baseline(('test',), 100, 200, (1, 2, 3), 0, 11)
            store.begin(root, root, PROBES['gdn'], base)
            with patch.object(store, 'atomic_json', side_effect=OSError('disk')):
                with self.assertRaises(OSError):
                    store.finish(root, root, PROBES['gdn'], base,
                                 {'success': True, 'cleanup_confirmed': True})
            self.assertTrue((root/'incomplete.json').exists())

    def test_sequence_keeps_original_values(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            base = Baseline(('original',), 100, 200, (1, 2, 3), 0, 11)
            self.assertIsNone(store.sequence_baseline(root, 'gdn'))
            with self.assertRaisesRegex(ValueError, 'gdn_required'):
                store.sequence_baseline(root, 'iq-experts')
            store.begin(root, root, PROBES['gdn'], base)
            store.finish(root, root, PROBES['gdn'], base,
                         {'success': True, 'cleanup_confirmed': True})
            self.assertEqual(store.sequence_baseline(root, 'iq-experts'), base)
            with self.assertRaises(ValueError):
                store.sequence_baseline(root, 'gdn')

    def test_environment(self):
        original = {'Path': 'old', 'gufo_TEST': 'x', 'HIP_PATH': 'wrong', 'SystemRoot': 'Windows'}
        env = store.child_environment(original)
        self.assertEqual(original['Path'], 'old')
        self.assertNotIn('gufo_TEST', env)
        self.assertNotIn('Path', env)
        self.assertTrue(env['PATH'].startswith(str(store.SDK/'bin')))
        for key in ('hsa_TEST', 'HIP_VISIBLE_DEVICES', 'ROCR_VISIBLE_DEVICES', 'GPU_DEVICE_ORDINAL'):
            with self.assertRaises(ValueError):
                store.child_environment({key: '0'})

    def test_recheck_detects_change(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'x'
            path.write_bytes(b'a')
            manifest = {'artifacts': [{'stamp': store.stamp(path)}]}
            path.write_bytes(b'ab')
            with patch.object(store, 'source_identity'), patch.object(store, 'BUILD', Path(folder)):
                with self.assertRaisesRegex(ValueError, 'artifact_changed'):
                    store.recheck(manifest)

    def test_binary_hash_and_shadow(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root/'bin').mkdir()
            (root/'lib/llvm/bin').mkdir(parents=True)
            (root/'lib/llvm/amdgcn/bitcode').mkdir(parents=True)
            for name in store.DLLS:
                (root/'bin'/name).write_bytes(b'dll')
            (root/PROBES['gdn'].filename).write_bytes(b'wrong')
            with patch.object(store, 'SOURCE', root), patch.object(store, 'BUILD', root), \
                 patch.object(store, 'SDK', root), patch.object(store, 'source_identity'):
                with self.assertRaisesRegex(ValueError, 'binary_hash'):
                    store.verify(PROBES['gdn'])
                (root/store.DLLS[0]).write_bytes(b'shadow')
                with self.assertRaisesRegex(ValueError, 'shadow'):
                    store.verify(PROBES['gdn'])

    @unittest.skipUnless(os.name == 'nt', 'Windows file lock')
    def test_lock_and_release(self):
        with tempfile.TemporaryDirectory() as folder:
            with store.exclusive(folder):
                with self.assertRaises(RuntimeError):
                    with store.exclusive(folder):
                        self.fail('second owner acquired lock')
            with store.exclusive(folder):
                pass


if __name__ == '__main__':
    unittest.main()
```

- [ ] From the integration root set `$env:PYTHONPATH = Join-Path $PWD 'scripts'`, then run focused store tests using `python -m unittest discover -s tests/gufo -p test_operator_store.py -v`; expect7 tests passing (Windows lock test skipped only on non-Windows). Run the full `python -m unittest discover -s tests/gufo -v` once. Review serialization, source/hash gate and failed-write latch retention. The parent authorizes a local commit of only these two files: `git add scripts/gufo_control/operator_store.py tests/gufo/test_operator_store.py` then `git commit -m "feat: add GUFO operator provenance and durable state"`. Report the commit for independent review before Task2.
