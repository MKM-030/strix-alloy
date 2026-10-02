# Halogen memory-placement investigation: measured baseline, not a speedup

Tested 1 October 2026 on the existing Windows Ryzen AI Max+ 395 / Radeon 8060S
host with 128 GiB unified memory, a 64 GiB graphics carve and driver 32.0.32015.2008.
The user requested higher Halogen throughput while retaining at least 16 GiB of
available Windows physical memory. The conservative interpretation here is 16 GiB,
not 16 decimal GB. No BIOS, driver, weights or kernel arithmetic were changed.

## Outcome

**No live-tested Halogen optimization was completed or promoted in this task.**
The original Halogen 0.15.1 v2 configuration was remeasured and restored. Runtime
source and manifest bytes match the pre-task snapshot. All figures below are
baseline observations, not improved numbers or a claimed globally optimal setup.

## Completed baseline through the Strix Alloy gateway

One slot, 262144 allocated context positions, prefix cache Off, greedy decoding,
thinking disabled, exactly 128 generated prose tokens for each decode measurement.
Input counts include the chat template. Each point has one warmup followed by three
retained measurements. PP is measured separately with a one-token output probe.

| Input | Prefill-only tokens/s | Serial decode tokens/s | MTP decode tokens/s |
|---:|---:|---:|---:|
|512|1048.57 +/-2.39|36.72 +/-0.21|42.94 +/-0.44|
|2048|1384.21 +/-25.25|35.80 +/-0.19|43.94 +/-0.51|
|8192|1368.27 +/-1.66|34.70 +/-2.56|40.71 +/-0.84|

Values are means +/- sample standard deviations, not confidence intervals.

These are **derived clock-calibrated engine phase rates**. The JSON also retains
unmodified engine fields, per-request monotonic/raw clock ratios, Windows request
wall time and output hashes. Clock-rate changes within a request can leave phase
uncertainty not represented by the standard deviation. No timing correction is a
GPU optimization. All serial/MTP output hashes at each tested length were identical.
There are 27 measured requests, plus excluded warmups. This is not a filled 262K
conversation or an independent model-quality evaluation.

## Memory observations and stricter supplementary monitoring

The two completed baseline runs recorded minimum available Windows physical RAM of
37.37 and 37.10 GiB. Every captured sample remained above 16 GiB. Existing Halogen and
managed-controller 12 GiB protections were **not changed**. An additional monitor
samples Windows availability every 0.2 seconds and requests the existing ordinary
owned-controller stop below 18 GiB, leaving a 2 GiB margin above the requested floor.
It requests cleanup on a telemetry exception too. It never kills an unrelated process
or changes a protection limit. It must remain running for the extra monitoring to apply.

This is not an instantaneous allocator-enforced 16 GiB guarantee. A polling monitor
and graceful stop cannot prevent an arbitrary sudden outside allocation. Benchmarking
with other large workloads paused and retaining a margin is still necessary.

An initial version redundantly checked controller heartbeat freshness. It stopped
one baseline retry during startup despite ample free memory. That check was removed
from the additional monitor; existing engine/controller liveness checks remain.
The interrupted attempt supplied no benchmark score. Unit tests cover the memory
threshold, invalid telemetry, exact owned-stop identity and failure cleanup.

## Why PROJFIX's selector cannot simply be copied

The inspected v2 adapter requests one contiguous 62.1 GiB immutable-weight device
allocation. The current w4b adapter instead already uses a
48 GiB device-copy budget plus host registrations. PROJFIX's per-tensor CLI
selector is neither understood by Halogen nor sufficient to split v2's pointer layout.

A proposed workspace-only pinned-host adapter passed small mock allocation/free/cap
checks. It was **not** loaded into a real Halogen process. Tool safety blocked the
necessary launcher integration, and experimental service edits were rolled back.
No live placement gain, numerical equivalence or real HIP compatibility is claimed.
The prototype and negative evidence remain in the ignored local investigation folder.

A separate supported experiment would increase `HALOGEN_PREFILL_CHUNK` and its
matching `HALOGEN_MAX_TOK` arena from 2048 to 8192 for v2. Its configuration unit test
passed, but the tool blocked the candidate startup. The defaults were restored
before the final baseline restart. That test has no candidate speed or memory result.
The upstream flags guide supports changing these prefill dimensions, but its native
Linux reference results are not proof of gains on this Windows/DXG adaptation.

## Reproduction and scope

[Benchmark instructions](../../scripts/benchmarks/README.md) describe the optional
input-size list and separate reserve monitor. The old default PP512/PP2048 workload
is unchanged. The PP8192 extension uses the same counter validation and timing method.
The [JSON](halogen-placement-baseline-20261001.json) and
[CSV](halogen-placement-baseline-20261001.csv) distinguish each measured size and mode.
No SDK binaries, checkpoints, API keys or local runtime payloads are published.

Primary reference: [Halogen's pinned supported flags](https://github.com/peonist-ai/halogen-flash-server/blob/82c92af2289f6f1086ab8362b18669ccff36968b/docs/FLAGS.md).
The engine, source pins, allocator and model data stayed unchanged; PROJFIX/GUFO
registrations were retained. Successful baseline testing is not an optimization result.

## Final verified state

The original v2 configuration was restored and started through the normal managed launcher. Local and public HTTPS authentication/inference checks are below; requests originated from the Windows PC, not a separate cloud instance. The supplementary memory monitor remained running.

```json
{
  "checked_at": "2026-10-01T11:34:13.609226+00:00",
  "run_id": "f09bc011fb454fbc8c66268da8d78181",
  "phase": "ready",
  "model": "halogen-v2",
  "context": 262144,
  "runtime_configuration": "Original baseline, no optimization promoted",
  "checks": [
    {
      "origin": "http://127.0.0.1:8840",
      "transport": "IPv4, normal TLS certificate verification",
      "missing_status": 401,
      "wrong_status": 401,
      "status": 200,
      "answer": "OK"
    },
    {
      "origin": "https://strix-alloy.tail7f425a.ts.net",
      "transport": "IPv4, normal TLS certificate verification",
      "missing_status": 401,
      "wrong_status": 401,
      "status": 200,
      "answer": "OK"
    }
  ],
  "additional_monitor_run_minimum_gib": 37.50871276855469,
  "request_origin": "Windows PC, not the external cloud instance",
  "api_key_changed": false
}
```

## Source verification

Fresh exported source passed 33 benchmark tests, 23 controller tests, 15 publication tests, 12 PROJFIX tests and 15 GUFO policy tests. The Halogen suite ran 108 tests with 22 platform/installation-dependent skips (86 passed). All 27 PowerShell files parsed. These source tests do not qualify the unexecuted allocation or prefill candidates.
