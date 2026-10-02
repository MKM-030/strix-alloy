# PROJFIX MTP with host placement: implementation and measured result

Measured on 1 October 2026 on the existing BOSGAME Ryzen AI Max+ 395 / 128 GiB
Windows host, 64 GiB graphics carve-out. Source base: f221eaba0a34fa7503b663aa751fdcbe6f6863e4.
The unchanged PROJFIX engine uses its pinned TheRock 10.2.0a20260930 runtime and
existing IQ4_NL-PROJFIX shards. No model, driver, BIOS or binary was replaced.

## Selected implementation

`backends/projfix-windows/profile.py --mode mtp-host` now creates a separate,
opt-in profile combining the existing pinned-host expert placement with the real
MTP head. It uses `--tensor-split 1` and one draft token per round. The target's
expert tensors in layers 0-17 remain GPU-computed through pinned host buffers.
This is not CPU computation, extra physical RAM or NPU MTP offload.

The default serial and legacy resident MTP command vectors remain unchanged.
The new mode requires `--output`; it cannot silently replace the registered default.
The generated profile was produced against the real local runtime and models;
its command vector exactly matched the live-tested one-token configuration.

## Matched 262144-capacity results

Exact 512/2048 inputs include the chat template; output is exactly 128 prose tokens.
Temperature 0, thinking off, prefix cache Off. One warmup and three measured repeats
per point. Native Windows engine timers through the authenticated gateway, with
separate Windows wall times. Model/OS caches are warm, not globally evicted.

| Input | Serial decode | Selected MTP decode | Decode gain | Serial wall | MTP wall | Wall reduction |
|---:|---:|---:|---:|---:|---:|---:|
|512|33.2553|39.0627|17.46%|4.5325 s|4.0043 s|11.65%|
|2048|31.8327|40.7887|28.13%|6.2790 s|5.5089 s|12.26%|

Rates are tokens/s. Sample decode standard deviations were 0.0573/0.0505 for
serial and 0.2461/0.0862 for selected MTP at 512/2048. They are not confidence
intervals. Prompt and output SHA-256 values match between serial and selected MTP
at both sizes, including retained warmups. This does not certify every prompt,
sampled decoding, long-context quality or arbitrary structured-output requests.

Prefill-only performance declined from 725.28 to 688.32 tokens/s at 512, and from
898.22 to 862.39 at 2048. The improvement is in generation, not prompt processing.
Very short outputs or prompt-dominated workloads need a separate comparison.

Both 262K arms used the explicit split of 1, identical placement, model, runtime,
input files and sampling. Runs were sequential, not an interleaved A-B-A design.
262144 is allocated capacity, not the occupied context depth. These are not
like-for-like speed claims against Halogen, a different checkpoint or an NPU model.

## Rejected wider draft and startup evidence

Two draft tokens loaded successfully at both 32768 and 262144 capacity. At 262144,
this candidate reached 41.63/43.11 decode tokens/s, but its 512-input output differed
from serial. The 2048-input output matched. It was not selected despite its higher
rate. A one-token draft restored output identity on both measured cases.

The inspected loader normalizes device free-memory split weights without a zero-sum
guard. With a zero free-memory report this can produce NaNs and an out-of-range
device index. A positive explicit split bypasses that path for this single GPU.
The prior `invalid vector subscript` draft-loading failure no longer reproduced.
This is a tested configuration workaround, not a compiled loader repair or an
independent trace proving every allocation/paging event.

## Memory, lifecycle and limitations

The selected 262K run used the new controller threshold of 18 GiB for physical
availability and commit headroom. Its recorded minimum physical availability was
27.24 GiB. The control and earlier trials retained an independent 18 GiB observer.
No guard was weakened. The configurable threshold defaults to the existing 12 GiB
policy for old profiles and rejects relaxation below 12 GiB or invalid values.
A polling guard is not an instantaneous allocator reservation.

All four experimental model runs stopped through normal owned-controller cleanup.
The original Halogen v2 configuration was restarted at 262144 capacity, cache Off,
and its separate 18 GiB observer was restarted. Authenticated model discovery again
reported halogen-v2. No NPU worker was started by this implementation.

The new profile is opt-in because two short greedy benchmarks are not a general
quality qualification. An additional live multi-turn/JSON check was tool-blocked
and is not credited. New filled-context, sampled-equivalence and cancellation
qualification were not performed. Existing tests and historical results do not
substitute for those missing live checks.

## Offline regression verification

A fresh working-source export ran all nine discovered Python test suites:
454 test cases in those invocations, 385 passed, 68 platform-specific skips,
and one failure. PROJFIX: 20 passed. Managed server: 26 passed. Current Halogen
0.15.1: 86 passed and 22 skipped. All 27 PowerShell source files parsed.
The deliberate HTTP-disconnect fixture emits a connection-reset diagnostic while
its assertion passes; this is retained in the test logs.

The failure is the older backend's
`test_hybrid48_sessions.SessionsTests.test_sessions_probe_cleanup_terminates_real_descendant`
(`DUMMY_DESCENDANT_SURVIVED`). It was reproduced separately from an unmodified
HEAD archive of `backends/halogen-wsl2`. That old path was not changed or repaired.
The full repository suite is therefore not described as entirely green.

## Files and reproduction

Ready local candidate: `server/.local/projfix-mtp-host-262k.json`.
Generating a new candidate with the documented profile CLI verifies runtime pins
and model size/header checks without starting an engine or storing API-key values.
See the [backend guide](../../backends/projfix-windows/README.md) for controlled start/stop.
Raw experiments and logs remain in `server/.local/mtp-host-20261001/`, including
`serial262-cold`, `mtp262-cold`, `mtp1-262-cold` and `mtp32-cold`.
The selected 262K comparison is serial versus one-token MTP, not versus the
historical slow resident mode. All rejected results and warmups are retained.

Current phase instrumentation shows that target verification still dominates
MTP generation time. It does not supply an isolated NPU head latency. NPU-native
head conversion, state transfer and verified rollback remain unimplemented.
A continuous independent NPU worker is not enabled because the prior coexistence
measurements showed a GPU throughput penalty rather than a free acceleration.

Primary implementation inspected locally: `src/llama-model.cpp` and
`common/speculative.cpp` in the existing native engine source tree.
Related upstream zero-free-memory report:
https://github.com/ggml-org/llama.cpp/issues/27454
