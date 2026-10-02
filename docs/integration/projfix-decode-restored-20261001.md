# PROJFIX decode restored by explicit weight placement

Measured on 1 October 2026 on the existing Ryzen AI Max+ 395 / 128 GiB Windows
machine, with its 64 GiB graphics carve-out. Target: original IQ4_NL-PROJFIX
Flash-Next shards. Engine binary, model data, TheRock 10.2.0a20260930 runtime and
display driver 32.0.32015.2008 were unchanged during this experiment.

## Result and comparison scope

The preceding recovery made the service work, but left serial decode near 6.3 t/s
and MTP near 12 t/s. Explicitly assigning a subset of expert tensors to GPU-accessible
pinned host storage restored serial decode to the low-30s range without changing
weights, precision or equations. The selected default is now **fast serial**, not MTP.

| Configuration | Capacity | Input | Separate prefill t/s | Decode t/s |
|---|---:|---:|---:|---:|
| Previous resident MTP, freshly repeated | 262144 | 512 | 538.46 | 11.78 |
| Previous resident MTP, freshly repeated | 262144 | 2048 | 718.93 | 12.54 |
| Previous resident serial, retained same-day reference | 262144 | 512 | 553.33 | 6.35 |
| Previous resident serial, retained same-day reference | 262144 | 2048 | 739.69 | 6.23 |
| Split-placement serial | 262144 | 512 | 721.94 | 33.12 |
| Split-placement serial | 262144 | 2048 | 895.64 | 31.77 |

Each short point has one warmup and three measured repetitions. Prefill is a
one-output-token probe; decode generates exactly 128 prose tokens. Inputs are exact
including the chat template, prefix caching is disabled, thinking is off and
temperature is zero. These are native Windows engine timers through the authenticated
Strix Alloy gateway, without WSL clock rescaling. The standard deviations for the
new decode points were 0.061 and0.010 t/s respectively; not confidence intervals.

The new serial outputs were byte-identical to the retained slow serial reference
at both lengths, across warmup and measured repeats. The same engine/library hashes,
environment and parameter values were checked; `--lazy-mode on` had moved in the
argument list but not changed. This is not an interleaved A-B-A experiment. The
fresh MTP comparison changes both placement and decoding mode, so its approximately
2.5-2.8x service improvement is not a placement-only causal estimate.

The old 31.49 t/s headline used llama-bench with a 96 GB carve-out and synthetic
single-token evaluation. The restored serving rate is in that range, but it is not
a matched percentage comparison against that historical harness.

## Why the placement matters

A metadata-only census found about 66.34 GiB of target weights excluding the mapped
lookup table, before KV/state/work buffers. The slow MTP process reported 80.79 GiB
GPU-committed memory, including 62.57 GiB dedicated and 18.22 GiB shared allocation.
A split-placement serial snapshot reported 51.62 GiB dedicated and 24.16 GiB shared.
These are allocation/accounting counters, not independent physical pools or an
ETW trace of individual page migrations. MTP and serial also have different buffers.

The fix selects 54 expert tensors, totaling 23.73046875 GiB, in layers 0-17:

```text
-ot ^blk[.](?:[0-9]|1[0-7])[.]ffn_(?:gate|up|down)_exps[.]weight$=CPU
```

In this pinned fork, the CPU selector prefers the GPU host-buffer allocator. The
integrated HIP backend accepts that pinned buffer for GPU operations. It does not
mean offloading those layers to ordinary CPU compute. The remaining device-resident
weights and working state fit more comfortably below the dedicated budget. The
measured speedup supports a placement bottleneck; specific driver paging costs were
not independently profiled. The total amount of model mathematics did not change.

## MTP attempts and retained safeguards

The mixed-placement target loads and runs correctly on its own. Adding the shared
MTP head failed before inference with `invalid vector subscript` while loading the
draft. Explicit draft placement and the existing full Q8_0 draft reproduced the
failure. No timings or correctness passes are credited to those attempts. The
initial literal `ROCm_Host` selector was rejected by the CLI, which lists default
device buffer types; the supported `CPU` selector reaches the host-buffer preference.

The selected profile is deliberately serial, not a silently substituted model.
Explicit `--mode mtp` still creates the older resident MTP layout and may be slower.
Mixed-placement MTP, the 2048-microbatch kernel failure and NPU offload are not fixed
or claimed as part of this change. GUFO/Halogen are not used to produce these numbers.
The 512 microbatch, lazy lookup mapping, f16 KV, twelve-GiB physical/commit reserves
and Windows GPU watchdog remain unchanged. No BIOS, driver or power-plan change.

## Continuity after normal registration and restart

The normally registered launcher completed two three-turn conversations starting
with 32,794 and 32,795 input tokens inside the 262,144 capacity. All six streams
completed and 16/16 exact retrieval values were correct. Decode averaged 27.85 t/s
across all output tokens; individual turns ranged 26.75-29.86 t/s. The four coding
follow-ups reached their 512-token output ceiling. Generated code was not executed.

Long-history prefill in this sampled/thinking test was only about 251 t/s. The short
prefill improvement above must not be used to claim that long-prompt throughput is
fully optimized. This test is not a filled 262K quality evaluation or the earlier
article's exact protocol. A separate short-prompt rerun after these conversations
is retained in the JSON and shown below.

## Repeat after the six long-conversation requests

| Input | Prefill-only t/s | Serial TG128 t/s | Decode sample standard deviation |
|---:|---:|---:|---:|
| 512 | 729.62 | 33.48 | 0.095 |
| 2048 | 892.60 | 32.02 | 0.017 |

Three measured repetitions followed a new warmup at every point. These are not
first-request-only peaks. The JSON retains the repeated outputs and their identity
comparison with both the first fast run and the earlier slow serial reference.

## Operation and evidence

The profile generator and standalone no-draft launcher encode the same placement.
An existing managed profile must be explicitly regenerated after a controlled stop;
updating source files alone does not silently rewrite an operator's registration.
The old registration is retained locally for rollback; no model, runtime or driver
was replaced. Use [the profile guide](../../backends/projfix-windows/README.md).

The [JSON](projfix-decode-restored-20261001.json) includes timing samples, cold-cache
controls, output-hash checks, allocation snapshots, failed draft attempts and final
connection evidence. The [CSV](projfix-decode-restored-20261001.csv) names each mode
and reference separately. Historical slow/failure reports are not rewritten.

Primary source for the buffer-selection order:
[pinned llama-model.cpp](https://github.com/pwilkin/llama.cpp/blob/40a9f4d01b69314d0f75c9120abe8e199e49111d/src/llama-model.cpp).
GPU buffer support is implemented in the corresponding `ggml-cuda.cu`; the CLI's
accepted buffer names are in `common/arg.cpp`. These implementation details are
specific to the pinned engine, not general promises about every llama.cpp version.

## Final verification and running state

Fresh-source export tests: projfix 12, publication 15, server 23, benchmark 27, gufo_policy 15. All passed; 27 PowerShell files parsed. These are source tests, separate from live benchmarks.

The fast test run stopped cleanly and the new registered run completed the long-chat and repeated short tests. A fresh client-disconnect/cancellation test was not part of this change.

```json
{
  "checked_at": "2026-10-01T07:05:43.633719+00:00",
  "phase": "ready",
  "run_id": "3f611af734244559bb4dcf7a9c61e8ad",
  "backend": "projfix-flash-next",
  "context": 262144,
  "mode": "serial",
  "minimum_free_gib": 22.004806518554688,
  "api_key_changed": false,
  "checks": [
    {
      "origin": "http://127.0.0.1:8840",
      "transport": "IPv4; normal certificate verification",
      "missing_status": 401,
      "wrong_status": 401,
      "status": 200,
      "answer": "OK"
    },
    {
      "origin": "https://strix-alloy.tail7f425a.ts.net",
      "transport": "IPv4; normal certificate verification",
      "missing_status": 401,
      "wrong_status": 401,
      "status": 200,
      "answer": "OK"
    }
  ],
  "request_origin": "Windows PC, not external cloud instance"
}
```
