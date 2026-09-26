# GUFO isolated runtime package implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Provide a reproducible PowerShell entrypoint that stages and revalidates the exact already-qualified native GUFO runtime in a separate directory, without executing it.

**Architecture:** A thin explicit-Python PowerShell wrapper calls a standard-library static package module. A portable checked-in policy pins the existing executable,17 DLLs and250 resource files by identity. A runtime manifest records static package identity only; it cannot serve as model, memory, loader or persistent-service qualification. This is the first independently testable part of the full setup/launcher delivery, not a replacement for the remaining bounded build script or persistent controller.

**Tech Stack:** Windows PowerShell5.1+, explicit64-bit Python3.12, standard library, existing unittest suite. No new package manager or Python dependency.

## Global Constraints

- Preserve the existing native Strix Alloy, Halogen WSL2 and27B installations and launchers; GUFO remains optional and independently selectable.
- No source-snapshot edits, model/native executable launch, GPU allocation, build, download, service/autostart registration, environment/registry/security/driver/BIOS/pagefile/WSL change, reboot, D: action or publication in this task.
- Existing runtime identity: sourcecff564964e8506c0abb3e530cecb55332187ac6c; TheRock10.2.0; gufo.exe42429952 bytes/SHA256E7F5B899C54C747EE5038C0598016394D2A70F25EE69AFBB1E02859FD223D943. No latest-file fallback or generic executable acceptance.
- Exactly nine SDK DLLs, eight vcpkg DLLs and two complete gfx1151 trees from the accepted package report; no wildcard whole-bin copies, model files, public archive or System32 replacement.
- Explicit canonical paths, no source/destination overlap or reparse points, no foreign nonempty destination, no overwrite of differing files. Same validated package is idempotent. Verify every payload file before manifest success.
- Static package status is `staged-static-only`, never `qualified`. Host OpenMP is checked and recorded but not bundled. Missing, altered or extra payload must make verification fail, not repair silently.

---

### Task 1: Static package CLI, portable pins, tests and short guide

**Files:**
- Create: `scripts/gufo_control/runtime_package.py` (file/package verification and staging only).
- Create: `config/gufo-runtime-pins.json` (portable expected identity; no local absolute paths).
- Create: `setup/stage-gufo-runtime.ps1` (thin argument forwarding wrapper).
- Create: `tests/gufo/test_runtime_package.py` (standard unittest fixtures and wrapper checks).
- Create: `setup/GUFO.md` (short optional experimental package guide).
- Do not modify existing Guardian/store/launcher/release code.

**Interfaces:**
- `load_policy() -> dict`: load the one repository-relative policy file, validate schema1, exact names/types/digests and source/executable/SDK identity. No public policy override.
- `inventory_sources(build_dir: Path, sdk_dir: Path, vcpkg_dir: Path) -> dict`: pure read-only verification returning canonical paths, expected payload records and host prerequisite observation. Requires pinned gufo.exe, SDK `.info/version`10.2.0,17 exact DLL identities, build-output vcpkg DLL equality to installed/x64-windows/bin, both tree identities and host OpenMP.
- `stage_runtime(build_dir: Path, sdk_dir: Path, vcpkg_dir: Path, runtime_dir: Path) -> dict`: complete preflight before creation/copy, owned finite static staging, destination verification, atomic `runtime-manifest.json`; no executable launch.
- `verify_runtime(runtime_dir: Path) -> dict`: read-only relocation-friendly verification using relative payload paths and fixed policy, not source files/paths recorded in the manifest. Rechecks current host OpenMP. Returns verified manifest or raises a clear error.
- Module CLI `stage --build-dir ... --sdk-dir ... --vcpkg-dir ... --runtime-dir ...` and `verify --runtime-dir ...`; JSON result, exit0 success/2 refusal, no hidden repair or launch.

**Required references (read before implementation):**
- `C:/Projects/strix-alloy-research/reports/gufo-runtime-setup-implementation-brief-20260926.md` (whole-setup context; this task only stages the exact existing binary, not a new build).
- `C:/Projects/strix-alloy-research/reports/gufo-server-runtime-package-20260926.md` (all SDK identities and canonical tree format).
- `scripts/gufo_control/smoke_store.py` SDK_DLLS, VCPKG_DLLS and TREES (exact existing verified values). Copy these values into portable JSON; leave historical constants untouched. Regression tests assert equality so accidental policy drift is visible.

- [ ] **Step 1: Write failing focused tests.**

Use tiny ordinary files in TemporaryDirectory, a patched internal `load_policy()` for their hashes, and patched host-prerequisite/free-space readers. The public CLI has no fixture/policy override. Build all17 named DLL fixture files and two miniature trees; real-pins tests separately compare all counts/digests with the existing historical constants.

```python
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from gufo_control import runtime_package

class RuntimePackageTests(unittest.TestCase):
    def test_unknown_nonempty_target_is_not_touched(self):
        with TemporaryDirectory() as temp:
            target = Path(temp) / 'runtime'
            target.mkdir()
            existing = target / 'user.txt'
            existing.write_text('keep', encoding='utf-8')
            with self.assertRaises(ValueError):
                runtime_package.stage_runtime(Path(temp)/'build', Path(temp)/'sdk',
                                              Path(temp)/'vcpkg', target)
            self.assertEqual(existing.read_text(encoding='utf-8'), 'keep')

    def test_cli_requires_explicit_inputs(self):
        with self.assertRaises(SystemExit) as caught:
            runtime_package.main(['stage', '--runtime-dir', 'C:/missing'])
        self.assertEqual(caught.exception.code, 2)
```

Run with absolute PYTHONPATH: `python -m unittest discover -s tests/gufo -p test_runtime_package.py -v`; expect import failure before the module exists. Capture intentional argparse stderr in the finished test so successful output is clean.

- [ ] **Step 2: Implement deterministic identity and path helpers.**

Use chunked SHA256 reads and strict file checks; never read or hash model weights. Detect symlinks/reparse points on every existing path component with lstat and FILE_ATTRIBUTE_REPARSE_POINT. Refuse non-files, case-folded relative-path collisions, traversal, UNC/device namespaces and stream-colon payload paths. All caller roots must be absolute after canonical resolution; path-overlap comparisons use Windows case-insensitive ancestry, not string prefix. Outputs must not be any input root/ancestor/descendant. Verify target parents before writing.

Canonical tree digest must be exactly:

```python
from hashlib import sha256

def tree_digest(records):
    ordered = sorted(records, key=lambda row: row['path'])
    text = ''.join(f"{row['path']}|{row['size_bytes']}|{row['sha256'].lower()}\n"
                   for row in ordered)
    return sha256(text.encode('utf-8')).hexdigest().upper()
```

Paths inside each tree are relative to hipblaslt/rocblas root, e.g. `library/gfx1151/name.co`, case-preserved and slash-separated. Expected hipBLASLt100files/13164894bytes/digest79EB8214145013B0F9CAFDD128942B94542C10FCEFB80B827472940EB4D4BB56; rocBLAS150/17243350/D160DEE878CB2DF152A39DB55506085C2918CAA83041C61E58096EA8B8E64D06. Portable policy records exact hashes/lengths for all17 DLLs. Verify SDK files under bin and vcpkg files under installed/x64-windows/bin; verify the eight build-directory DLLs equal their installed sources.

Host OpenMP: resolve Windows system directory using GetSystemDirectoryW (no PATH search); validate `libomp140.x86_64.dll`,634936bytes/SHA2569AB1CB787E52B2A36133899C01C1DB1F876067D1471CD224EAD85F40A8152B99. Store its path/size/hash but do not copy it. Isolate that reader so offline tests use a fixture instead of touching the host library.

- [ ] **Step 3: Implement fail-closed, non-overwriting staging and verification.**

Before any target writes, validate all source identities and paths, target ancestry, complete inventory and free space >=payload bytes+1GiB on the target volume. This reserve is for the ~298MiB static copy, not the separate25GiB build reserve. Reject a nonempty target unless its existing manifest and entire payload pass current policy. For a valid matching target, return the existing verified manifest without rewriting it.

For a new/empty target, use an exclusive sibling staging lock and unique temporary sibling directory; lock creation must be atomic and ownership-scoped. Copy only enumerated files with exclusive creation and streamed copying, then hash/size-verify every destination and both trees. Source replacement during copy must fail verification, not produce a successful manifest. Write a manifest only after all bytes verify. Publish the staged directory without overwriting an existing destination; an existing empty target may be removed only with an emptiness/reparse/identity recheck and nonrecursive rmdir. Never recursively delete anything. On failure retain the temporary directory/log evidence and report its explicit path; it is not an installed package. Release only the lock created by this invocation after owned work is terminal. Reject stale locks; no generic force/unlock option.

Manifest schema:

```python
manifest = {
    'schema': 1,
    'kind': 'gufo-native-static-runtime',
    'status': 'staged-static-only',
    'created_utc': created_utc,
    'expected_source_commit': policy['source_commit'],
    'sdk_version': policy['sdk_version'],
    'policy_sha256': policy_sha256,
    'sources': {'build_dir': str(build_dir), 'sdk_dir': str(sdk_dir),
                'vcpkg_dir': str(vcpkg_dir)},
    'files': payload_records,
    'trees': tree_records,
    'host_prerequisites': [openmp_record],
    'runtime_qualified': False,
}
```

Define `created_utc` as timezone-aware ISO8601 UTC; policy_sha256 hashes actual policy bytes. `payload_records` contain only slash-relative `path`, strict integer `size_bytes` and uppercase `sha256` fields. `tree_records` carry name,count,bytes,digest. No API key, general environment dump or model location belongs in the manifest. `expected_source_commit` identifies the reviewed binary's provenance, not a fresh source checkout/build verification. `runtime_qualified` must be exactly false.

Read-only verification checks strict schema/types/status, fixed policy identity, exact executable/DLL set, both actual tree digests, every record and actual file, missing/extra files and reparse/case collisions. Only the manifest is additional to payload. It must work after moving a valid package without requiring recorded source roots to exist. Tampered manifest records cannot redefine policy hashes or permit extra DLLs. Return clear `ValueError`/`OSError` refusals, CLI catches only expected failures and returns2.

- [ ] **Step 4: Add PowerShell wrapper and honest setup guide.**

Wrapper requires `-PythonExe`, `-RuntimeDir`, optional `-Verify`; stage additionally requires explicit `-BuildDir`, `-SdkDir`, `-VcpkgDir`. Resolve explicit Python file; no PATH/latest fallback. Invoke repository module through `python -c` with repository scripts path inserted in that child's sys.path (or scoped-and-finally-restored process PYTHONPATH), forwarding each argument separately; preserve exit code. Do not change caller environment permanently, start GUFO or silently relax execution policy.

Guide: prerequisites explicit64-bit Python3.12/Windows PowerShell5.1+, exact existing compiled tuple, independent runtime path, source and license links, CLI stage/verify examples, ~298MiB local payload plus1GiB reserve, no model/AMD binary redistribution. Clearly say bounded build script and persistent start/status/stop remain a later delivery step; this command does not make a service ready. Rollback is stop selecting the optional runtime; removal needs explicit reviewed path and is not performed by verify/stage. Source-built new gufo.exe hashes require updated reviewed package policy rather than claiming equivalence.

- [ ] **Step 5: Complete fixture and integration-boundary coverage.**

Test valid stage→verify and byte-identical idempotent return; relocation; mixed-case ordinal tree digest; exact real-pin equality; corrupt/missing/extra DLL and resource; altered manifest hash/count/path/status/qualification flag; dirty unknown target unchanged; overlap in both ancestor directions; symlink/junction/reparse rejection; insufficient disk causes no staging; source change during copy fails; copy failure retains diagnostic directory and no published target; valid child-safe quoting with spaces through PowerShell wrapper; no caller-environment mutation; no subprocess/model invocation from Python static stage/verify. Include staged directory publication race refusing an independently created target. No test launches GUFO or copies real SDK/model files.

Focused command as Step1; run full offline suite once with absolute PYTHONPATH before commit. Use existing Windows tests' harmless subprocess conventions for wrapper testing. Do not blanket-skip Windows wrapper tests on this Windows host. Record RED/GREEN, exact counts and limitations.

- [ ] **Step 6: Self-review and commit only task-owned paths.**

`git diff --check`; explicit-file stage/commit `feat: add isolated GUFO runtime staging and verification`. Write `.superpowers/sdd/runtime-package-report.md` with tests, policy hashes, files, and no-live-actions statement. Return compact status/commit/tests. Parent independently reviews, then may stage one new real local package after disk/target checks; no model execution is implied.
