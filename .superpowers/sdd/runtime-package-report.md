# GUFO static runtime package implementation report

Status: implemented and verified offline on Windows. This task added only the optional static staging component; it did not stage a real package or execute GUFO.

## Implemented

- `config/gufo-runtime-pins.json`: portable schema-1 reviewed identity for the existing GUFO executable, TheRock 10.2.0, 9 SDK DLLs, 8 vcpkg DLLs, two gfx1151 resource trees, and host OpenMP. No local absolute paths.
- `scripts/gufo_control/runtime_package.py`: fixed-policy loading, strict path and byte verification, read-only source inventory, owned finite staging with an exclusive sibling lock and unique retained diagnostic directory on failure, atomic manifest, and relocation-friendly read-only verification. The CLI prints JSON on success and refuses with exit 2 for expected path/identity errors.
- `setup/stage-gufo-runtime.ps1`: explicit Python path and separately forwarded stage/verify arguments, preserving the child exit code and caller environment.
- `tests/gufo/test_runtime_package.py`: tiny offline fixtures and Windows wrapper/junction checks.
- `setup/GUFO.md`: optional experimental usage and qualification boundary.

## Pinned identity

- Policy file SHA-256: `C363650BDFF6B79B3482B198D7EFBEE03E25C9D52A298B51B9B54724316F6B63`.
- Expected source commit: `cff564964e8506c0abb3e530cecb55332187ac6c`; SDK version: `10.2.0`.
- Reviewed `gufo.exe`: 42,429,952 bytes, SHA-256 `E7F5B899C54C747EE5038C0598016394D2A70F25EE69AFBB1E02859FD223D943`.
- 9 SDK DLL and 8 vcpkg DLL byte lengths and hashes match the existing `smoke_store` constants exactly; tests compare all 17 records independently. Build-output vcpkg DLLs must also match installed `x64-windows/bin` copies.
- Canonical ordinal trees: hipBLASLt 100 files / 13,164,894 bytes / `79EB8214145013B0F9CAFDD128942B94542C10FCEFB80B827472940EB4D4BB56`; rocBLAS 150 files / 17,243,350 bytes / `D160DEE878CB2DF152A39DB55506085C2918CAA83041C61E58096EA8B8E64D06`.
- Host OpenMP: 634,936 bytes / `9AB1CB787E52B2A36133899C01C1DB1F876067D1471CD224EAD85F40A8152B99`. It is checked through `GetSystemDirectoryW` and not copied.
- Expected package payload: 311,830,580 bytes (about 298 MiB), plus 1 GiB free-space reserve on the destination volume.

## TDD and test evidence

- RED: `C:\Users\Marcel\AppData\Local\Programs\Python\Python312\python.exe -m unittest discover -s tests/gufo -p test_runtime_package.py -v`, with `PYTHONPATH=C:/Projects/strix-alloy-research/integration/scripts`; test module import failed with `ImportError: cannot import name 'runtime_package' from 'gufo_control'`. This was expected before the module existed.
- GREEN focused: the same command after implementation: 15 tests, `OK (skipped=1)`, in 3.146 s. The skipped symlink case requires unavailable symlink privilege; a real Windows junction test ran and passed to exercise reparse refusal.
- Full offline suite: `C:\Users\Marcel\AppData\Local\Programs\Python\Python312\python.exe -m unittest discover -s tests/gufo -v`, with the same absolute `PYTHONPATH`: 381 tests, `OK (skipped=1)`, in 48.884 s.
- Covered valid stage/verify/idempotent return and relocation; mixed-case ordinal digest; source corruption, version mismatch, low space, overlapping paths, unknown destinations, stale lock, source replacement during copy, retained diagnostic directory, publish race, actual Windows junction refusal, payload and manifest tampering, and PowerShell quoting/environment forwarding. No fixture uses real SDK or model files.

## Self-review and boundaries

Reviewed the five task-owned files for scope, fixed policy identity, relative manifest payload paths, exclusive creation, source recheck after copy, target identity before replacing an empty directory, and no recursive delete. No existing Guardian, launcher, release, model, or build code changed. The test process ran ordinary fixture and harmless wrapper subprocesses only. There was no GPU/model/native execution, real package staging, build, download, D: drive action, setting change, or publication. Static identity does not establish loader behavior, model correctness, or service readiness.

Concern: direct symlink creation was unavailable under this Windows account, so that individual test skipped. The junction test passed and covers the Windows reparse-point gate.

Bookkeeping: this report resides under the repository's ignored `.superpowers` scratch tree. The task commit `9df450e` had already completed with this report force-added before the parent clarified that the report should stay on disk but outside the commit. The commit was not rewritten. The five requested product paths are the other files in that commit.
