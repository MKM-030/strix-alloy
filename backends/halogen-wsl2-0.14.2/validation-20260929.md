# Halogen 0.14.2 update validation â€” 29 September 2026

This record applies to the version-specific package in this directory, on one
128 GiB Strix Halo Windows / WSL2 machine. It is not an upstream WSL support
claim, a three-engine service release, or a general model-quality benchmark.

## Identity and installation

The official 0.14.2 image is pinned by digest in [release.json](profiles/release.json).
The installer used the existing image and model files, extracted dependencies
from a stopped owned container, then rebuilt all three adapters locally. The
bridge, private-mapping shim and HIP probe each matched the pinned binary SHA-256
from the previously reviewed local 0.14.2 artifacts. The entrypoint transform and
ELF/ABI checks passed. The temporary setup container was removed without starting
it. No model download, global configuration change or driver replacement occurred.

The generated engine, headers, libraries and machine configuration remain ignored
under `.local/`. No engine binary, AMD header/library bundle, model or container
archive is added to Git. Model sizes were checked; this update did not rehash the
entire pair of large model files. Explicit `-VerifyModelHash` remains available.

## Source and checkout checks

| Check | Result |
|---|---|
| 0.14.2 offline/installed-asset suite | 27 passed, zero skips |
| Shared selector/API helper suite | 10 passed |
| Fresh staged checkout, without installed assets | 25 passed, two installed-asset checks skipped |
| Shared helpers from that fresh checkout | 10 passed |
| PowerShell parsing | 16 source files, no parser errors |
| Current package source hashes in fresh checkout | 18 of 18 matched |
| Legacy 0.13.8 imported files | 84 of 84 unchanged, including fresh-checkout verification |
| Targeted new-source secret and binary scan | No matching credential patterns or redistributed binary/model assets |

The fresh staged checkout was exported with `core.autocrlf=true` before tests;
version-local `-text` attributes preserve the sealed source bytes. The retained
telemetry helper has an extra final blank line; otherwise the staged whitespace
check passed. A targeted secret scan is not a guarantee of detecting all possible
secret formats. The earlier interrupted legacy Git-fixture test remains recorded
in the historical integration validation; this update does not relabel it.

## Live qualification

| Profile | Observed result |
|---|---|
| Trace4k, final source | Passed exact pre-registration trace, terminal state, recovery and guard exit |
| Single4k | API and engine both reported 0.14.2; answers were `42` and `GrÃ¼n`; cleanup/recovery passed |
| Serve4k, 30 seconds | Repeated correct smoke answers; reached READY; timer and shutdown/recovery passed |
| Real shared PowerShell helper during serving | Exit 0, advertised `halogen-qwen3.8-flash-next`, final answer exactly `OK` |

The test server was stopped by the bounded controller. The first diagnostic run
before the controller docstring cleanup also passed and remains in local evidence;
the published trace row above identifies the final source, not inherited approval.


Normal owned-container stop is immediate and can yield exit 137; terminal
verification additionally requires Running=false, PID=0, OOMKilled=false and no
Docker state error. It is not treated as an OOM merely because the exit code is
137. Cleanup, last-five-frame baseline-relative recovery and the matching guard
exit acknowledgement were checked separately. Sampler quiescence precedes the
normal stop; the host guard remains active through recovery.

The compact [evidence excerpt](validation-20260929.json) records actual run IDs,
source seals, success-file hashes, answers, version reports and recovery checks.
Full local attempts, guard samples, subprocess diagnostics and container logs are
retained under `.local/attempts/`, not included as a machine-specific public dump.

## Boundaries

Only a 4,096-position, single-slot profile is supplied. The live serving check
uses a 30-second window and serial requests; it does not establish arbitrary
MTP/DFlash2 behavior, 32K/260K contexts, concurrency, 300-second stress stability
or unattended operation. The permitted serving range is 30â€“300 seconds, within
the separate 600-second container deadline. Fresh installations must run their
own exact-source Trace4k and Single4k gates before Serve4k is accepted.

Admission remains 45 GiB available physical memory and 117 GiB commit headroom;
runtime floors are 12 GiB each. These Windows counters are not additive model
residency figures and are not a guarantee against all possible driver failures.
The older 0.13.8 package, its different profile limits, and historical benchmark
claims remain unchanged. No GUFO qualification, native update, common endpoint,
main-branch merge, release tag or combined runtime ZIP follows from this update.
