# Release validation — 29 September 2026

This is an integration/research checkpoint, not a released four-engine package.
See [backend status](../user/backends.md) for the repository and installation
boundaries. Existing production installations are unchanged.

## Halogen 0.14.2 lifecycle

The separately reviewed WSL2 release controller passed a real one-session 4K
serial check: `17 + 25` returned `42`, and the German colour question returned
`Grün`. The sampler quiesced, the exact owned container stopped, memory recovered,
and the independent host guard exited successfully before the release marker.
There were ten complete guest/GPU samples and 175 direct Windows memory frames;
minimum available Windows physical memory was 19.479 GiB. This is correctness
and lifecycle evidence, not a decode-performance benchmark or persistent-service
qualification. The live run did not happen to have a pending sample at quiescence;
that drain path is covered by the offline tests.

Evidence: local attempt
`halogen-flash-hybrid-0142-smoke-ac8ad25ef630410c845f96abf8fa21de`, success SHA-256
`e35705546f1cc4cefd2c021084254bde3f9ce8d89fcd1a12be5867b68c6104ac`.
The earlier failed repetitive attempt is unchanged. Its stale lock was separately
reconciled and preserved as an archive, not deleted to manufacture a pass.

## Cold prefill: completed Halogen 0.14.2 measurement

Three repetitions per size, one active session, greedy AR, thinking off, no
reused prompt/KV tokens, one output token. Context/pool capacity was 16384;
prefill chunk was 2048. Cold refers to prompt cache, not cold model/OS pages.
HTTP PP divides actual fresh prompt tokens by the complete client request time,
including the one output token. Means below use sample standard deviation.

| Deployment | Actual input/output | HTTP PP2048 (tok/s) | HTTP PP8192 (tok/s) |
| --- | --- | ---: | ---: |
| Halogen 0.14.2, patched WSL2, HGN | 2047/1; 8185/1 | **1314.83 ± 15.26** | **1310.73 ± 4.93** |
| Existing GUFO Windows `cff5649`, IQ4_XS, AR | 2047/1; 8185/1 | 877.40 ± 17.92 | 928.00 ± 19.85 |
| Updated GUFO v0.1.1 Windows candidate | Not measured | — | — |
| Updated native llama.cpp / PROJFIX | Not measured | — | — |
| CIRU Flash | No matching local checkpoint | — | — |

The existing GUFO row comes from the [27 September cold-PP report](gufo-pp-20260927.md),
using the same filler/calibration and output budget. Different model formats,
builds and host state make this a deployment comparison, not an isolated engine
or Windows/Linux speedup. These one-output runs do **not** measure decode speed.

Halogen HTTP ranges were 1297.21–1324.06 and 1306.46–1316.13 tok/s.
Its engine-derived PP was separately 1239.61 ± 12.34 and 1216.01 ± 6.28 tok/s.
**All six engine times exceeded complete HTTP wall time**, by 91.0–100.9 ms
and 477.2–500.7 ms. The cause remains unresolved; do not mix those clocks or
claim validated engine-speedup/parity from these observations.

The independently audited run completed all nine requests (warmup, two
calibrations and six measurements), all ten guest/GPU samples, owned shutdown,
memory recovery and guard exit. Minimum available Windows physical memory was
20.519 GiB; minimum commit headroom was 113.160 GiB. Admission was 45/117 GiB
physical/commit and runtime floors were 12/12 GiB; these are not reserved RAM.

Local raw attempt: `halogen-flash-hybrid-0142-pp-7f75a8cb47964d989179c228d4283556`
under the research workspace's `artifacts/halogen0142/attempts/`.
Source seal: `658a9017381c5f047169c3056b46ca73094eebcce86759ff6449f73b08267c37`.
Success SHA-256: `99f39b688035186cc5459365e2bed46a45b385682be6717177b8e6b66e810f12`.
Audit: `reports/halogen0142-cold-pp-live-audit-20260929.md` in the research workspace.
Raw artifacts are local evidence, not bundled release assets.
The [portable measurement excerpt](data/halogen0142-cold-pp-20260929.json)
retains all nine original response bodies, exact client timestamps and request
hashes. Repetitive user messages use a lossless prefix/filler-count encoding;
it omits local machine paths and process identities, not failed observations.

## Offline verification

The first 797-test run reported four failures/errors. Two HTTP fixtures mixed
real and simulated clocks; two release fixtures had scheduling/cleanup hazards.
Only those tests were corrected; the frozen production release runner did not
change. An independent fresh run of the affected 46 tests passed.

The subsequent full run executed **811 tests in 704.542 seconds**, with three
skips and one error: a newly added PP test was loaded while its admission floor
was changing from 116 to 117 GiB. The other cases, including the unchanged
100,000-sample ledger stress case, passed. This was not an all-green full run.
A redundant broad repeat was stopped; it is not counted as passing evidence.
After freezing the final files, the complete scoped Halogen/HTTP suite ran
**91 tests in 27.077 seconds: OK, one existing POSIX-only skip**. The PP-specific
subset was independently reviewed and passed all 15 tests. No failed or
interrupted run is relabelled as successful.

A final frozen full discovery run completed on 29 September: **817 tests in
644.605 seconds, OK (three skips)**, exit 0. Command: Python 3.12.10,
`-B -m unittest discover -s tests/gufo -p 'test_*.py' -q`, with absolute
`scripts` and `tests/gufo` directories in `PYTHONPATH`. Saved local log:
`reports/release-offline-frozen-20260929.log`. This is the complete existing
suite at that snapshot; newly developed candidate bindings under
`experimental/native_release_20260929` are outside that discovery and require
their own checks. An offline pass does not qualify new GPU binaries.

## Engine updates

- GUFO: stable v0.1.1 source plus the reconciled Windows port now builds on CPU and HIP;
  ten focused CPU tests pass. A regression demonstrated and fixed the Windows
  fast-sampling path bypassing new JSON constraints. The isolated HIP runtime's
  268 payload hashes and CLI version/help were checked. The new executable is
  `F72443ECE330684185F8A240C3B4271321B4C6171D52377DE0EC8DDC7B4C81B4`;
  model inference is not yet qualified. Previous `cff5649` measurements remain
  the local numbers, not v0.1.1 performance results.
- Native PROJFIX: current pwilkin `strix-halo@b0f31f58` plus the published Windows
  prefetch compatibility patch built successfully in an isolated tree, including
  llama-server and llama-bench. App-local HIP DLLs were pinned and CLI version
  checked. No current-build model-load qualification or rate is claimed.
- CIRU Flash: no corresponding local model or measurement. Publisher results
  are references, not our benchmarks; the installed Ornith model is not a
  substitute. Its roughly 136 GB model set exceeds the inspected C: free space.

The builds were paused before the new Halogen PP measurement to avoid compiler
load contaminating its results. No BIOS, driver, carve, service, pagefile or
security configuration was changed; no reboot or large-model download occurred.
