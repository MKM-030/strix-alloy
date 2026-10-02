# GUFO: native Windows qualification on the latest TheRock SDK

This work replaces the earlier compiler downgrade workaround with a source-only
compatibility patch compiled entirely by **TheRock 10.2.0a20260930 / AMD clang 24**.
The installed **32.0.32015.2008 / Adrenalin 26.9.2** display driver remains unchanged.
The AMD nightly index listed this as the latest Windows/gfx1151 package when checked
on 30 September 2026. This is a dated nightly qualification, not a promise about
untested future builds. A nightly and a stable release are not interchangeable labels.

The source base is Thomas's Windows port at
`7e924c2d787aabf640db3c0f818cb824dc18ec8e`. The exact three-file patch and compiler,
runtime and test-source hashes are in
[compatibility.json](../../backends/gufo-windows/compatibility.json).
No old compiler-generated object, old device library or 10.0 runtime is used in the
qualified candidate. The previous working source, SDK, binary and profile are retained
for rollback. No model download, BIOS change or memory-limit relaxation was required.

## What changed and why

The original newer-compiler errors were not fixed by swapping runtime DLLs. Compiler
optimizations changed reduction/rounding boundaries in attention, quantization and
recurrent math. The original 30 operator checks alone were insufficient: an early
patch passed them while changing complete-model logits. That candidate was rejected.

The retained source changes make the existing numerical contract explicit:

1. Preserve the selected wave/block and expert-routing reduction order.
2. Preserve quantized-product rounding at half-integer boundaries, and use the
   actual FP32 reciprocal builtin in the scalar quantizer rather than its FP64 sibling.
3. Preserve compensated `log1p` intermediate/FMA boundaries in recurrent decay.
   The helper derives from licensed ROCm OCML source and retains its license.
   It is compiled as ordinary source by the new SDK; it is not an old binary shim.

The broad no-vectorization and broad reciprocal-order rewrites were rejected. Global
optimization was not disabled. The final build retains the production optimization
flags; `-g0` is the previous debug-information build workaround, not a throughput claim.
The original kernel reference formulas, test files, assertion thresholds and declared
model-regression acceptance criteria were not weakened.

## Matched full-model numerical gate

The same fixed 258-token corpus was teacher-forced through the same target/MTP files,
with 256 recorded positions in each of three schedules: scalar decode, varying
verification widths 2..8, and prefill width 8. The recorded 10.0 build is a regression
reference, not an independent unquantized-model oracle.

| Schedule | Compared positions | Top-1 equality | Max target log-probability difference | Complete raw-logit rows |
|---|---:|---:|---:|---|
| Scalar | 256 | 256 / 256 | 0 | All hashes identical |
| Verification widths 2..8 | 256 | 256 / 256 | 0 | All hashes identical |
| Prefill width 8 | 256 | 256 / 256 | 0 | All hashes identical |

Perplexity is unchanged at **8.1581227272** for the first two schedules and
**8.1582476379** for prefill. All 768 full-vocabulary row hashes match. This is
stronger than comparing just top-64 probabilities or generated text. It does not
prove arbitrary-input or filled-262K equivalence. The test includes teacher forcing,
not every speculative rejection path; separate operator and serving checks apply.

The isolated recurrence replay also matched all 720 captured decay factors across
15 positions and 48 heads. Captured model tensors and rejected experimental binaries
remain private local evidence and are not included in the repository. All 15 original
Flash-Next operator tests passed with Windows tuning both enabled and disabled.
## Fresh-build and serving measurements

A separate clean checkout was patched using the published wrapper and built from
an empty build directory, using only the pinned latest SDK. All 30 original operator
checks passed again, followed by the same 768 full-logit hash comparisons. That
fresh binary, rather than a diagnostic or mixed-object executable, was benchmarked.

| Mode | Input | Prefill tokens/s | Decode tokens/s |
|---|---:|---:|---:|
| off | 512 | 544.16 +/- 13.13 | 27.82 +/- 0.03 |
| off | 2048 | 839.46 +/- 10.76 | 26.48 +/- 0.03 |
| mtp | 512 | 498.88 +/- 33.30 | 34.33 +/- 0.05 |
| mtp | 2048 | 756.05 +/- 21.60 | 33.13 +/- 0.07 |

Each point uses a warmup followed by three measured repetitions. Prefill is measured
with a one-token probe; that probe is never counted as a decode benchmark. Decode
uses 128 generated prose tokens. All 24 retained requests had zero prefix-cache hits,
actual requested token counts and identical generated text across repeats and drafters.
Rates are native Windows engine phase timers, without WSL clock correction.

Serial and MTP are separate runs, not randomized/interleaved trials. OS/model file
caches were not flushed. Differences from the earlier 10.0 run also include time and
machine/cache state; they are not a display-driver speedup measurement. No filled-262K
quality, vision, tool-use or indefinite endurance guarantee is claimed.

## Managed lifecycle validation

The latest registered runtime loaded at 262144 capacity through the Windows gateway.
The live test received 128 content events and a normal [DONE], disconnected a separate
stream, then received OK on the next request. Missing/incorrect credentials returned
401. The controller stopped, both owned listeners closed, and a new managed run reached
READY. Authenticated inference also returned OK through the existing public HTTPS
hostname. Those HTTPS requests originated from this Windows PC, not the user's cloud
instance. The API key and tunnel address were not changed.

Source-policy tests cover multi-file patch acceptance and rejection of missing helpers,
modified helper bytes, path escapes and unrelated additions. The final fresh-source export passed 15 toolchain/source-policy tests, 23
controller/gateway tests, 14 publication-helper tests and 27 PowerShell source parses.
The patch digest was identical after export. These checks used the existing isolated
Python test environment; the separate clean runtime build and real-model tests are
reported above.

## Reproduce and audit

[Build and registration instructions](../../backends/gufo-windows/README.md) pin the exact SDK, patch and original tests. [JSON evidence](gufo-latest-sdk-20260930.json) retains all 24 timing requests, complete model-comparison summaries, runtime identities and memory outcomes.

| Mode | Lowest available Windows memory | Cleanup | Recovery |
|---|---:|---|---|
| off | 43.50 GiB | True | True |
| mtp | 38.96 GiB | True | True |

Source-policy checks reject altered compiler/runtime bytes, a partial source patch,
modified original tests and unrelated source edits. The operator receipt now also
binds the actual engine binary and patch identity. The SDK archive digest was computed
after download from official AMD HTTPS; it is not represented as a publisher-signed
checksum. Keep the old SDK/profile available rather than updating files in place.

Primary references: [AMD driver notes](https://www.amd.com/en/resources/support-articles/release-notes/RN-RAD-WIN-26-9-2.html),
[official nightly index](https://nightly.repo.amd.com/rocm/core/tarball/),
[Clang AMDGPU builtin signatures](https://clang.llvm.org/docs/AMDGPUBuiltinReference.html),
[ROCm compensated arithmetic](https://github.com/ROCm/llvm-project/blob/4f43f4746ede4cc49ab4129f473dbd54e0d9db4f/amd/device-libs/ocml/src/ep.h)
and [ROCm log1p](https://github.com/ROCm/llvm-project/blob/4f43f4746ede4cc49ab4129f473dbd54e0d9db4f/amd/device-libs/ocml/src/log1pF.cl).

## Final checked service

```json
{
  "phase": "ready",
  "backend": "GUFO",
  "source_commit": "7e924c2d787aabf640db3c0f818cb824dc18ec8e",
  "sdk": "10.2.0a20260930",
  "source_patch_sha256": "f7173edf67d5d834da06554fbdfd7e3df39ec5246e87047eb2335ea34d24e1fd",
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
  "minimum_free_gib": 39.053646087646484,
  "run_id": "15a9c3284222495bb498861b7dccb54e",
  "checked_at": "2026-09-30T19:21:00.704169+00:00",
  "transient_errors": []
}
```
