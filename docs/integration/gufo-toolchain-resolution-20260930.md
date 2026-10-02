# GUFO Windows numerical blockers resolved

The original attention-preparation and fused-projection tests now pass without
changing GUFO kernel arithmetic, reference outputs or assertion tolerances.
The fix is a qualified build-toolchain pin: TheRock 10.0.0 / clang 23 instead of
TheRock 10.2 / clang 24. The newly installed AMD display driver remains 32.0.32015.2008.
Those are independent components; the display driver was not rolled back.

## Controlled diagnosis

The original 10.2-built tests failed again on the new display driver, so the driver
update alone did not clear the errors. The entire 15-test Flash-Next operator suite
then passed in both Windows-tuning modes (30/30) with unmodified source built using
10.0. It passed again through the published qualification script (another 30/30).
Original source/test hashes and exact binary/runtime identities are recorded in JSON.

| Compiled with | App-local runtime | Attention test | Fused projection test |
|---|---|---|---|
| 10.2 | 10.2 | FAIL | FAIL |
| 10.2 | 10.0 | FAIL | FAIL |
| 10.0 | 10.2 | PASS | PASS |
| 10.0 | 10.0 | PASS | PASS |

The display driver was held constant for this matrix. This isolates the failing
behavior to the build-side compiler/device-code toolchain, not merely which HIP DLL
is loaded. It is not a minimized upstream LLVM bug report: the SDK's compiler, device
libraries and headers are a bundle. Diagnostic kernel changes were rejected and restored.
No claim is made that 10.2-generated code now passes or that mixed SDKs are preferred.
The operational profile uses the fully matched 10.0 compiler and runtime.

## Real model and API validation

The existing Unsloth UD-IQ4_XS Flash-Next target and shared Q8_0 MTP head loaded at
32768 and 262144 configured context capacity. Short semantic answers were exactly
`OK` and `4`; missing/incorrect tokens returned 401. App-local HIP loading was checked
through the owned process handle. Each finite run closed only its owned Windows job
and met the original memory-recovery criterion. No other model weights were downloaded.
A first launcher argument check rejected inconsistent queue/per-client limits before
loading; that harness configuration was corrected and the failed attempt retained.

The shared controller then served GUFO on localhost:8840, forwarding to native
localhost:8836. A real stream delivered 128 content events and [DONE]; after closing
another stream, the next request returned OK. This is a small functional/regression
check, not a universal cancellation, long-context-quality or endurance guarantee.

## Measured native performance

One session; configured capacity 262144; exact PP512/PP2048 input including chat
template; 128 generated prose tokens; greedy, thinking off, cache_prompt=false.
Each point uses a warmup plus three measured repetitions. All 24 retained requests
had zero prefix-cache hits, and generated output hashes matched both repeats and
serial versus MTP. MTP uses a 3-token draft cap and the existing shared Q8_0 head.

| Mode | Input | Prefill tokens/s | Decode tokens/s |
|---|---:|---:|---:|
| off | 512 | 520.91 +/- 6.05 | 27.45 +/- 0.08 |
| off | 2048 | 855.38 +/- 11.19 | 26.59 +/- 0.07 |
| mtp | 512 | 477.00 +/- 12.17 | 34.44 +/- 0.03 |
| mtp | 2048 | 751.53 +/- 47.66 | 33.26 +/- 0.67 |

Rates are the native engine's own stage timers. No WSL clock correction is applied.
Values show mean +/- sample standard deviation, not confidence intervals. The one-token
prefill probes are never scored as decode benchmarks. OS/model-file caches were not
flushed between repetitions. Capacity is not an occupied-262K prompt. Serial and MTP
were separate runs, not a randomized interleaved experiment. Different weights,
placement and display driver mean this is not a controlled head-to-head with the
older Halogen measurements or a measurement of the AMD driver's speedup.

## Prevention and reproducibility

[Build/qualification workflow](../../backends/gufo-windows/README.md) pins SDK archive,
compiler and runtime bytes, source revision and original test source hashes. It
rejects the unsupported 10.2 compiler instead of merely warning. The managed native
adapter also verifies application-local runtime DLL hashes before launch, as well
as the executable hash. The API key is read from its existing private file at launch,
not embedded as plaintext in the saved command configuration.

No compiler flags or test thresholds were relaxed to make the failing tests pass.
Both toolchains used the same effective optimization flags for this comparison.
Removing HIP debug information was retained in both arms from the earlier build
workaround; it is not claimed as a numerical or throughput improvement.

The [JSON evidence](gufo-toolchain-resolution-20260930.json) contains original results,
cross-runtime tests, per-request measurements and lifecycle observations. Full local
logs and rejected experiments remain in ignored version-specific evidence directories.
The new build directory is for local use, not a redistributable binary release.

This clears the two numerical blockers. It does not establish arbitrary-model quality,
vision/tool-use correctness, filled-262K accuracy, or compatibility with future SDKs.
The current managed GUFO profile deliberately exposes only the tested Chat Completions
route. Halogen remains an available, separately selected backend; Projfix qualification
is unchanged. A model/backend switch still requires a controlled stop/start.

## Final checked service

```json
{
  "phase": "ready",
  "backend": "GUFO",
  "source_commit": "7e924c2d787aabf640db3c0f818cb824dc18ec8e",
  "sdk": "10.0.0",
  "display_driver": "32.0.32015.2008",
  "context": 262144,
  "model": "gufo-flash-next",
  "local_api": "http://127.0.0.1:8840/v1",
  "public_api": "https://strix-alloy.tail7f425a.ts.net/v1",
  "token_changed": false,
  "checks": {
    "http://127.0.0.1:8840": {
      "answer": "OK",
      "negative_auth": 401
    },
    "https://strix-alloy.tail7f425a.ts.net": {
      "answer": "OK",
      "negative_auth": 401
    }
  },
  "public_origin": "Windows PC through public hostname; external cloud instance not tested",
  "minimum_free_gib": 40.099876403808594,
  "run_id": "5ffb7409ad6d4f5da61ed41d91b57314",
  "checked_at": "2026-09-30T12:31:19.336915+00:00",
  "transient_errors": []
}
```

## Source-level regression checks

Six toolchain policy tests, 23 controller/gateway tests and 14 shared-helper tests passed.
All 27 PowerShell source files parsed. The published build wrapper also configured the
pinned source/SDK and completed its test-target build successfully (no rebuild was needed).
Operator-only and model-level checks are reported separately above.

The fresh index-exported source also passed the same 6 toolchain, 23 controller and
14 helper tests, plus all 27 PowerShell parses. This used the existing isolated Python
test environment; it was not another model installation or another GPU benchmark run.
