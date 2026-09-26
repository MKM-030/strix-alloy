# GUFO App-Local Probe Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Require the three reviewed SDK DLLs beside the two existing operator executables and permit one evidence-bound GDN retry while preserving the original baseline and all existing admission/cleanup guards.

**Architecture:** Change only `operator_store.py` and its unit tests. Hash both SDK sources and app-local copies before telemetry, include all seven artifacts in the manifest, and retain cheap metadata checks after final telemetry. A narrow exception in `sequence_baseline` authenticates the one existing failed result and its exact sequence state; the unchanged `begin`/`finish` lifecycle prevents overlap and consumes the exception when a retry completes.

**Tech Stack:** Python 3.12 standard library, unittest, Windows PowerShell; existing private operator runner.

## Global Constraints

- Research root: `C:\Projects\strix-alloy-research`; integration repository: `C:\Projects\strix-alloy-research\integration`.
- Only implementation-owned files: `C:\Projects\strix-alloy-research\integration\scripts\gufo_control\operator_store.py` and `C:\Projects\strix-alloy-research\integration\tests\gufo\test_operator_store.py`.
- This document is a plan. Its creation does not implement code, stage DLLs, or launch anything.
- Keep GUFO source, both build EXEs, SDK contents, driver/System32, models, settings, HIP/WSL configuration, and all existing evidence unchanged.
- Fixed shared executable directory: `C:\Projects\strix-alloy-research\build\gufo-hip-10.2\tests\models\qwen38_flash_next`. The GDN and IQ-experts EXEs already share this directory; one set of three adjacent DLLs serves both.
- No generic runtime path override, retry flag, force/reset flag, evidence reset, state deletion/move, SDK download, or broader runtime search.
- Preserve 49/24/12 GiB admission/runtime/reserve limits, query timeouts, freshness bounds, baseline collection, original baseline, process ownership, lock, incomplete latch, and recovery policy unchanged.
- Implementation and tests use temporary files/mocked pins and no GPU, HIP, WSL, GUFO test EXE, model, or production runner execution. Only the parent may perform the three application-local copies and later runtime work, after independent implementation review.
- No new user approval is required for this normal application packaging within the existing finish-with-safeguards request. Independent implementation review remains mandatory before parent runtime.
- No concurrent build, SDK update, executable/DLL edit, or other packaging writer during parent staging and runtime.

## Evidence and narrow rationale

The first GDN run was `20260926T125657Z-7f662648dd3c4ff887bdb875297023a1`. Its immutable `result.json` SHA-256 is `2DDF73DCB8B6DB10693DCE880EFB0192C58696401F7A8FEB79D6738F3F998F91`. It records exit `3221225477` (`0xC0000005`), `nonzero_exit`, owned exit confirmed, collector terminal, five recovery samples, cleanup confirmed, and no numerical pass. Its original baseline is retained in both result and current sequence state.

Current `verify` forbids adjacent copies while the environment only prepends SDK paths. [ROCm issue 10178](https://github.com/ROCm/rocm-libraries/issues/10178) documents the matching Windows failure class: System32's HIP runtime precedes PATH; placing the intended artifact DLLs beside the EXE fixes their reported reproducer. This supports a targeted packaging correction, not a claim that the local failure's loaded-module provenance or eventual numerical success has already been proven.

Exact SHA-256 pins read from the existing failed manifest:

| DLL | SHA-256 |
| --- | --- |
| amdhip64_7.dll | 71C41D9DB361E544D1CB6DFF91530D5705FFC5F1A91BA8EDCF583FB882E282BF |
| rocm_kpack.dll | 9B6ABC1A45443709309AD136ED09C60EEEC45E77A003A23F6B35730036085649 |
| amd_comgr.dll | EA2825C6588FD48536377309848999C9EF98137C0FA8E8424D0B7CAD95D0F724 |

## Task 1: Require pinned app-local runtime and authenticate the single retry

**Files:** Modify only the two implementation-owned paths above. `operator_store.py` owns provenance/state; `test_operator_store.py` owns CPU-only fixtures and regression coverage. Do not alter runner or policy files.

**Interfaces:** Keep `verify(probe) -> dict`, `recheck(manifest) -> None`, and `sequence_baseline(root, key) -> Baseline | None` unchanged. Manifest artifacts become selected EXE, three SDK source DLLs, then three app-local DLLs, in `DLLS` order, plus a `runtime_policy` field. Keep `begin`, `finish`, and `child_environment` unchanged. `artifact_record(path)` performs stable pre-telemetry hashing; `_reviewed_retry(root, state)` returns authenticated original baseline values or raises `ValueError('prior_stage_requires_review')`.

- [ ] Step 1: Add these imports to `test_operator_store.py` (retain all existing imports):

```python
from contextlib import ExitStack, contextmanager
from copy import deepcopy
from dataclasses import asdict, replace
import hashlib
```

- [ ] Step 2: Insert these complete test fixtures before `class StoreTests`. Tests supply temporary pins; no real SDK or GPU is read or executed.

```python
@contextmanager
def runtime_fixture():
    with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
        root = Path(folder)
        sdk, build = root/'sdk', root/'build'
        build.mkdir()
        for part in ('bin', 'lib/llvm/bin', 'lib/llvm/amdgcn/bitcode'):
            (sdk/part).mkdir(parents=True, exist_ok=True)
        pins = {}
        for name in store.DLLS:
            content = ('test-runtime:' + name).encode()
            pins[name] = hashlib.sha256(content).hexdigest().upper()
            (sdk/'bin'/name).write_bytes(content)
            (build/name).write_bytes(content)
        probes = {}
        for key, probe in PROBES.items():
            content = ('test-executable:' + key).encode()
            (build/probe.filename).write_bytes(content)
            probes[key] = replace(probe, sha256=hashlib.sha256(content).hexdigest().upper())
        for name, value in (('SDK', sdk), ('BUILD', build), ('DLL_SHA256', pins),
                            ('PROBES', probes)):
            stack.enter_context(patch.object(store, name, value))
        stack.enter_context(patch.object(store, 'source_identity'))
        yield sdk, build, probes


@contextmanager
def retry_fixture():
    with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
        root = Path(folder)
        run = root/'reviewed-failure'
        run.mkdir()
        base = Baseline(('original',), 100, 200, (1, 2, 3), 0, 11)
        values = json.loads(json.dumps(asdict(base)))
        result = {
            'success': False, 'cleanup_confirmed': True,
            'owned_exit_confirmed': True, 'collector_terminal': True,
            'recovery_samples': 5, 'exit_code': 0xC0000005,
            'failure': 'nonzero_exit', 'numerical_pass': False,
            'original_baseline': values,
            'manifest': {
                'policy': 'operator-bootstrap-v1', 'source': store.SOURCE_COMMIT,
                'probe': 'gdn', 'executable': str(store.BUILD/PROBES['gdn'].filename),
                'sdk': str(store.SDK),
                'artifacts': [
                    {'sha256': PROBES['gdn'].sha256},
                    *({'sha256': store.DLL_SHA256[name]} for name in store.DLLS),
                ],
            },
        }
        state = {'stage': 'gdn', 'policy': 'operator-bootstrap-v1',
                 'source': store.SOURCE_COMMIT, 'binary': PROBES['gdn'].sha256,
                 'success': False, 'baseline': values, 'run': str(run)}
        store.atomic_json(run/'result.json', result)
        store.atomic_json(root/'sequence.json', state)
        digest = hashlib.sha256((run/'result.json').read_bytes()).hexdigest().upper()
        for name, value in (('EVIDENCE', root), ('REVIEWED_FAILED_RUN', run),
                            ('REVIEWED_RESULT_SHA256', digest)):
            stack.enter_context(patch.object(store, name, value))
        yield root, run, base, result, state
```

- [ ] Step 3: Replace the existing `test_recheck_detects_change` and `test_binary_hash_and_shadow` methods with these methods in `StoreTests`. Keep its other five existing methods unchanged.

```python
    def test_recheck_detects_change(self):
        with runtime_fixture() as (sdk, build, probes):
            for target in (build/probes['gdn'].filename,
                           sdk/'bin'/store.DLLS[0], build/store.DLLS[0]):
                with self.subTest(target=target):
                    original = target.read_bytes()
                    manifest = store.verify(probes['gdn'])
                    target.write_bytes(original + b'changed')
                    with self.assertRaisesRegex(ValueError, 'artifact_changed'):
                        store.recheck(manifest)
                    target.write_bytes(original)

    def test_binary_hash_and_required_local_runtime(self):
        with runtime_fixture() as (sdk, build, probes):
            for probe in probes.values():
                with self.subTest(probe=probe.key):
                    manifest = store.verify(probe)
                    self.assertEqual(len(manifest['artifacts']), 7)
                    self.assertEqual(manifest['runtime_policy'], store.RUNTIME_POLICY)
                    self.assertEqual(
                        [e['stamp'][0] for e in manifest['artifacts'][4:]],
                        [str((build/name).resolve()) for name in store.DLLS])
                    store.recheck(manifest)
            (build/probes['gdn'].filename).write_bytes(b'wrong executable')
            with self.assertRaisesRegex(ValueError, 'binary_hash_mismatch'):
                store.verify(probes['gdn'])
```

- [ ] Step 4: Add this complete test class before the existing `if __name__ == '__main__'` block:

```python
class AppLocalRuntimeTests(unittest.TestCase):
    def test_each_source_and_adjacent_dll_is_required_and_pinned(self):
        with runtime_fixture() as (sdk, build, probes):
            for directory in (sdk/'bin', build):
                for name in store.DLLS:
                    target = directory/name
                    original = target.read_bytes()
                    for mode in ('missing', 'wrong'):
                        with self.subTest(directory=directory, name=name, mode=mode):
                            if mode == 'missing':
                                target.unlink()
                            else:
                                target.write_bytes(b'wrong runtime')
                            for probe in probes.values():
                                with self.assertRaises((ValueError, OSError)):
                                    store.verify(probe)
                            target.write_bytes(original)

    def test_recheck_rejects_missing_runtime_and_manifest_tampering(self):
        with runtime_fixture() as (sdk, build, probes):
            manifest = store.verify(probes['gdn'])
            for position in range(1, 7):
                changed = deepcopy(manifest)
                changed['artifacts'][position]['sha256'] = '0'*64
                with self.assertRaisesRegex(ValueError, 'manifest_runtime_mismatch'):
                    store.recheck(changed)
            for field, value in (('runtime_policy', 'old'), ('source', 'wrong'),
                                 ('policy', 'wrong'), ('executable', 'wrong'),
                                 ('sdk', 'wrong'), ('probe', 'unknown')):
                changed = deepcopy(manifest)
                changed[field] = value
                with self.assertRaisesRegex(ValueError, 'manifest_runtime_mismatch'):
                    store.recheck(changed)
            changed = deepcopy(manifest)
            changed['artifacts'].pop()
            with self.assertRaisesRegex(ValueError, 'manifest_runtime_mismatch'):
                store.recheck(changed)
            changed = deepcopy(manifest)
            changed['artifacts'][-1]['stamp'][0] = str(build/'other.dll')
            with self.assertRaisesRegex(ValueError, 'manifest_runtime_mismatch'):
                store.recheck(changed)
            (build/store.DLLS[0]).unlink()
            with self.assertRaises((ValueError, OSError)):
                store.recheck(manifest)

    def test_exact_retry_preserves_baseline_and_latch(self):
        with retry_fixture() as (root, run, base, result, state):
            before = (root/'sequence.json').read_bytes()
            self.assertEqual(store.sequence_baseline(root, 'gdn'), base)
            self.assertEqual((root/'sequence.json').read_bytes(), before)
            with self.assertRaisesRegex(ValueError, 'review'):
                store.sequence_baseline(root, 'iq-experts')
            retry = root/'retry'
            retry.mkdir()
            store.begin(root, retry, PROBES['gdn'], base)
            with self.assertRaisesRegex(ValueError, 'cleanup'):
                store.sequence_baseline(root, 'gdn')

    def test_tampered_result_and_each_state_mismatch_deny_retry(self):
        with retry_fixture() as (root, run, base, result, state):
            original = (run/'result.json').read_bytes()
            (run/'result.json').write_bytes(original + b' ')
            with self.assertRaisesRegex(ValueError, 'review'):
                store.sequence_baseline(root, 'gdn')
            (run/'result.json').write_bytes(original)
            for field, value in (('run', str(root/'other-run')), ('stage', 'iq-experts'),
                                 ('policy', 'other'), ('source', 'other'),
                                 ('binary', '0'*64), ('success', True),
                                 ('baseline', {})):
                changed = deepcopy(state)
                changed[field] = value
                store.atomic_json(root/'sequence.json', changed)
                with self.subTest(field=field):
                    with self.assertRaisesRegex(ValueError, 'review'):
                        store.sequence_baseline(root, 'gdn')
            store.atomic_json(root/'sequence.json', state)
            with patch.object(store, 'EVIDENCE', root/'other-root'):
                with self.assertRaisesRegex(ValueError, 'review'):
                    store.sequence_baseline(root, 'gdn')

    def test_unconfirmed_cleanup_and_wrong_failure_deny_even_with_mocked_hash(self):
        with retry_fixture() as (root, run, base, result, state):
            mutations = (
                ('cleanup_confirmed', False), ('owned_exit_confirmed', False),
                ('collector_terminal', False), ('recovery_samples', 4),
                ('exit_code', 1), ('failure', 'deadline'), ('success', True),
                ('numerical_pass', True),
            )
            for field, value in mutations:
                changed = deepcopy(result)
                changed[field] = value
                store.atomic_json(run/'result.json', changed)
                digest = hashlib.sha256((run/'result.json').read_bytes()).hexdigest().upper()
                with self.subTest(field=field), patch.object(store, 'REVIEWED_RESULT_SHA256', digest):
                    with self.assertRaisesRegex(ValueError, 'review'):
                        store.sequence_baseline(root, 'gdn')

    def test_second_failure_and_success_consume_retry(self):
        for success in (False, True):
            with self.subTest(success=success), retry_fixture() as (root, run, base, result, state):
                original = (run/'result.json').read_bytes()
                self.assertEqual(store.sequence_baseline(root, 'gdn'), base)
                retry = root/'retry'
                retry.mkdir()
                store.begin(root, retry, PROBES['gdn'], base)
                store.finish(root, retry, PROBES['gdn'], base,
                             {'success': success, 'cleanup_confirmed': True})
                self.assertEqual((run/'result.json').read_bytes(), original)
                self.assertEqual(store.read_json(root/'sequence.json')['run'], str(retry))
                with self.assertRaisesRegex(ValueError, 'review'):
                    store.sequence_baseline(root, 'gdn')
                if success:
                    self.assertEqual(store.sequence_baseline(root, 'iq-experts'), base)
                else:
                    with self.assertRaisesRegex(ValueError, 'review'):
                        store.sequence_baseline(root, 'iq-experts')
```

- [ ] Step 5: Run the focused tests before implementation. Expected failure: missing `DLL_SHA256`/`REVIEWED_FAILED_RUN` attributes and the former shadow-DLL behavior. Do not run any production probe.

```powershell
Set-Location -LiteralPath 'C:\Projects\strix-alloy-research\integration'
$env:PYTHONPATH = 'C:\Projects\strix-alloy-research\integration\scripts'
& 'C:\Users\Marcel\AppData\Local\Programs\Python\Python312\python.exe' -m unittest discover -s tests/gufo -p test_operator_store.py -v
```

- [ ] Step 6: In `operator_store.py`, retain existing imports and constants and insert these constants immediately after `DLLS`:

```python
DLL_SHA256 = {
    'amdhip64_7.dll': '71C41D9DB361E544D1CB6DFF91530D5705FFC5F1A91BA8EDCF583FB882E282BF',
    'rocm_kpack.dll': '9B6ABC1A45443709309AD136ED09C60EEEC45E77A003A23F6B35730036085649',
    'amd_comgr.dll': 'EA2825C6588FD48536377309848999C9EF98137C0FA8E8424D0B7CAD95D0F724',
}
RUNTIME_POLICY = 'app-local-sdk-three-dlls-v1'
REVIEWED_FAILED_RUN = EVIDENCE / '20260926T125657Z-7f662648dd3c4ff887bdb875297023a1'
REVIEWED_RESULT_SHA256 = '2DDF73DCB8B6DB10693DCE880EFB0192C58696401F7A8FEB79D6738F3F998F91'
REVIEWED_OLD_POLICY = 'operator-bootstrap-v1'
```

- [ ] Step 7: Replace the complete existing `verify` and `recheck` functions with this code, including the new helpers. Leave `stamp` and `source_identity` unchanged.

```python
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
```

Recheck intentionally does not hash 278 MB of DLL data after final telemetry. It checks the already-hashed manifest's required paths/digests and current stamps. Like the existing design, it does not claim protection from a malicious concurrent replacement preserving size and modification time. The no-concurrent-writer condition remains necessary. Adding three local metadata checks must not cause any change to timestamp semantics or the two-second freshness policy; a late check still refuses safely.

- [ ] Step 8: Replace the complete existing `sequence_baseline` function with these two functions. Preserve `begin` and `finish` byte-for-byte.

```python
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
```

Exception lifetime: repeated read-only calls or prelaunch refusals do not consume it because no launch occurred. `begin` writes the existing incomplete latch before creation. A crash or unconfirmed cleanup keeps that latch and blocks further attempts. `finish` writes a new sequence with the retry's unique run path, so both success and another failure make this exception inapplicable. Never restore the old sequence, remove a latch, or rewrite the original result to obtain another retry. No generic failure gets this exemption.

- [ ] Step 9: Run the focused CPU-only store tests and adjacent pure policy tests. Expected: 13 store tests pass on Windows (one lock test skips on non-Windows) and the existing policy suite remains green. These commands do not run the full suite because other suites may exercise process executables, outside this plan's implementation test scope.

```powershell
Set-Location -LiteralPath 'C:\Projects\strix-alloy-research\integration'
$env:PYTHONPATH = 'C:\Projects\strix-alloy-research\integration\scripts'
& 'C:\Users\Marcel\AppData\Local\Programs\Python\Python312\python.exe' -m unittest discover -s tests/gufo -p test_operator_store.py -v
& 'C:\Users\Marcel\AppData\Local\Programs\Python\Python312\python.exe' -m unittest discover -s tests/gufo -p test_operator_policy.py -v
git diff --check
git diff -- scripts/gufo_control/operator_store.py tests/gufo/test_operator_store.py
```

- [ ] Step 10: Independent implementation review must inspect the diff and test results before any parent DLL staging/runtime. Review exact pins, the seven-artifact order, unchanged timing/limits/lifecycle, authenticated fixed retry and baseline, second-failure denial, and the absence of reset/override paths. Address findings within the same two files and repeat only affected checks. Do not commit unrelated changes; if the parent requests a checkpoint commit, stage precisely these two paths and use `fix: pin app-local GUFO operator runtime and reviewed retry` as the message.

## Task 2: Parent-only app-local packaging after independent review

**Files:** Add exactly three DLLs in the fixed shared BUILD folder. No EXE, source, SDK source DLL, driver DLL, state, or evidence file is edited by these packaging steps.

**Interfaces:** Satisfies Task 1's `verify(PROBES['gdn'])` and `verify(PROBES['iq-experts'])`. This task does not start either executable. Later parent runtime remains governed by the existing bounded runner and the unchanged safeguards.

- [ ] Step 1: Parent performs this read-only preflight. All three destinations must be absent; both EXEs and all source DLLs must match. Stop on any mismatch; do not overwrite or remove an existing destination. Maintain exclusive operational ownership of the fixed BUILD directory throughout staging, since a PowerShell existence check plus copy is not an atomic no-clobber primitive.

```powershell
$ErrorActionPreference = 'Stop'
$probeBuild = 'C:\Projects\strix-alloy-research\build\gufo-hip-10.2\tests\models\qwen38_flash_next'
$probeSdkBin = 'C:\AI\sdk\therock1151\bin'
$probeDllPins = [ordered]@{
    'amdhip64_7.dll' = '71C41D9DB361E544D1CB6DFF91530D5705FFC5F1A91BA8EDCF583FB882E282BF'
    'rocm_kpack.dll' = '9B6ABC1A45443709309AD136ED09C60EEEC45E77A003A23F6B35730036085649'
    'amd_comgr.dll' = 'EA2825C6588FD48536377309848999C9EF98137C0FA8E8424D0B7CAD95D0F724'
}
$probeExePins = [ordered]@{
    'qwen38_flash_next_gdn_ops_test.exe' = 'DDA3E38D646CC9DDF141B8A73C2A725A5BAC755D6D2B5D8D637F19614922C97F'
    'qwen38_flash_next_iq_experts_ops_test.exe' = 'AE8B70B1621880E4AD58AFEC52F607E70BBD79DBDD27F63A126F9394D7020AF8'
}
foreach ($entry in $probeDllPins.GetEnumerator()) {
    if (Test-Path -LiteralPath (Join-Path $probeBuild $entry.Key)) { throw "Destination already exists: $($entry.Key)" }
    if ((Get-FileHash -LiteralPath (Join-Path $probeSdkBin $entry.Key) -Algorithm SHA256).Hash -ne $entry.Value) { throw "SDK hash mismatch: $($entry.Key)" }
}
foreach ($entry in $probeExePins.GetEnumerator()) {
    if ((Get-FileHash -LiteralPath (Join-Path $probeBuild $entry.Key) -Algorithm SHA256).Hash -ne $entry.Value) { throw "EXE hash mismatch: $($entry.Key)" }
}
$failedResult = 'C:\Projects\strix-alloy-research\reports\gufo-operator-runs\20260926T125657Z-7f662648dd3c4ff887bdb875297023a1\result.json'
if ((Get-FileHash -LiteralPath $failedResult -Algorithm SHA256).Hash -ne '2DDF73DCB8B6DB10693DCE880EFB0192C58696401F7A8FEB79D6738F3F998F91') { throw 'Failed evidence changed' }
```

- [ ] Step 2: Parent performs exactly these three copy operations, once, without `-Force`. Each immediately checks its destination again. These create application-local copies and never modify the SDK originals. If any copy fails, stop; leave partial staging in place for diagnosis and do not rerun blindly.

```powershell
if (Test-Path -LiteralPath 'C:\Projects\strix-alloy-research\build\gufo-hip-10.2\tests\models\qwen38_flash_next\amdhip64_7.dll') { throw 'amdhip64_7.dll destination already exists' }
Copy-Item -LiteralPath 'C:\AI\sdk\therock1151\bin\amdhip64_7.dll' -Destination 'C:\Projects\strix-alloy-research\build\gufo-hip-10.2\tests\models\qwen38_flash_next\amdhip64_7.dll' -ErrorAction Stop
if (Test-Path -LiteralPath 'C:\Projects\strix-alloy-research\build\gufo-hip-10.2\tests\models\qwen38_flash_next\rocm_kpack.dll') { throw 'rocm_kpack.dll destination already exists' }
Copy-Item -LiteralPath 'C:\AI\sdk\therock1151\bin\rocm_kpack.dll' -Destination 'C:\Projects\strix-alloy-research\build\gufo-hip-10.2\tests\models\qwen38_flash_next\rocm_kpack.dll' -ErrorAction Stop
if (Test-Path -LiteralPath 'C:\Projects\strix-alloy-research\build\gufo-hip-10.2\tests\models\qwen38_flash_next\amd_comgr.dll') { throw 'amd_comgr.dll destination already exists' }
Copy-Item -LiteralPath 'C:\AI\sdk\therock1151\bin\amd_comgr.dll' -Destination 'C:\Projects\strix-alloy-research\build\gufo-hip-10.2\tests\models\qwen38_flash_next\amd_comgr.dll' -ErrorAction Stop
```

- [ ] Step 3: Parent verifies all six DLL hashes, both unchanged EXEs, source provenance through `verify`, both manifests, and the retry baseline without invoking the production runner. These checks deliberately precede any future telemetry window. Expected output: six DLL matches, two EXE matches, then `Pinned runtime and original retry baseline verified; no process launched.`

```powershell
foreach ($entry in $probeDllPins.GetEnumerator()) {
    foreach ($directory in @($probeSdkBin, $probeBuild)) {
        $probeArtifact = Join-Path $directory $entry.Key
        if ((Get-FileHash -LiteralPath $probeArtifact -Algorithm SHA256).Hash -ne $entry.Value) { throw "DLL hash mismatch: $probeArtifact" }
        Write-Output "DLL verified: $probeArtifact"
    }
}
foreach ($entry in $probeExePins.GetEnumerator()) {
    $probeArtifact = Join-Path $probeBuild $entry.Key
    if ((Get-FileHash -LiteralPath $probeArtifact -Algorithm SHA256).Hash -ne $entry.Value) { throw "EXE hash mismatch: $probeArtifact" }
    Write-Output "EXE verified: $probeArtifact"
}
$env:PYTHONPATH = 'C:\Projects\strix-alloy-research\integration\scripts'
& 'C:\Users\Marcel\AppData\Local\Programs\Python\Python312\python.exe' -c 'from gufo_control import operator_store as s; from gufo_control.operator_policy import PROBES; from dataclasses import asdict; import json; [s.recheck(s.verify(p)) for p in PROBES.values()]; b=s.sequence_baseline(s.EVIDENCE,"gdn"); assert json.loads(json.dumps(asdict(b))) == s.read_json(s.REVIEWED_FAILED_RUN/"result.json")["original_baseline"]; print("Pinned runtime and original retry baseline verified; no process launched.")'
if ($LASTEXITCODE -ne 0) { throw 'Read-only runtime verification failed' }
```

On success, hand the verified packaging result to the parent. The parent may perform the already-authorized single guarded GDN retry through the existing runner, and proceed to IQ-experts only if normal successful GDN sequencing and all safeguards allow it. A second GDN failure or unconfirmed cleanup stops progression. Do not expand this correction into a model qualification, allocation review, or additional experiment.

## Plan self-review

- [x] Correct DLL pins taken from the failed manifest, including the full `rocm_kpack.dll` digest.
- [x] Both operator profiles use the same fixed adjacent DLL directory; selected EXE remains separately pinned.
- [x] All three SDK sources and all three local copies required and hashed, then covered by metadata recheck.
- [x] Fixed failed run, fixed result digest, exact old policy/source/binary/state, cleanup/exit/recovery, and baseline equality gate the retry.
- [x] Existing latch and `finish` lifecycle enforce at most one launched retry; original evidence and baseline remain preserved.
- [x] Tests cover both profiles, every missing/wrong DLL, recheck drift and manifest tampering, original baseline, tampered result/state, cleanup mismatch, overlap latch, and second failure/success consumption.
- [x] Complete code replacements, imports, tests, expected outcomes, independent review gate, and parent-only three-copy/hash commands supplied.
- [x] No runtime, settings, source/build, SDK, policy timing/limits, or evidence mutation is performed by writing this plan.
