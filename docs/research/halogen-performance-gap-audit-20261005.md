# Performance gap: retained-source and telemetry audit — 5 October 2026

The slowdown is reproducible and real: historical paired 8K Stock A was 1866.537 / 48.423621 tok/s; the initial keep-open run was 1239.198392 / 42.150412; the fresh same-engine control is 1229.125265 / 41.945034. All retain the same profile, prompt/output identities and 207/345 acceptance. Request wall rose 7.0541 → 9.6742 → 9.7510 s. Clock correction is near 1, so it cannot explain the gap.

Actual manifests match image, native environment, source hashes and generated entrypoint exactly. Startup allocation also matches. One-time memory telemetry finished before the initial slow benchmark. There is no retained CPU-rate/affinity evidence for either benchmark, no changed CPU cap proved, and no live NPU or decode profiler override in the current manifest.

The new GPU logger covers the complete warmup (9 samples) and just 0.451488 s of measured request 1 (one sample); measured requests 2/3 have no sensor coverage. Host epoch/QPC interpolation uses 440 anchors with no extrapolation; observed affine consistency residual is 0.001647 ms. Guest UTC and ADLX driver timestamps are excluded.

| Sensor window | GPU MHz min/mean/max | Reported GPU W min/mean/max | °C min/mean/max | VRAM MHz |
|---|---:|---:|---:|---:|
| Current complete warmup, 9 samples | 687 / 1632.44 / 2085 | 36 / 59.78 / 83 | 45 / 53.89 / 59 | 1000 |
| Current partial measured request 1, 1 sample | 2177 | 55 | 53 | 1000 |
| Historical same-shape MTP warmup, 8 samples | 2533 / 2678.13 / 2749 | 114 / 133.88 / 145 | 61 / 74 / 82 | 1000 |
| Historical separate measured MTP control, 24 samples | 2125 / 2677.17 / 2894 | 85 / 135.58 / 155 | 60 / 79.54 / 88 | 1000 |

The last 6 current warmup samples show 92–99% GPU usage at 1636–2085 MHz and 55–71 W, so the lower observed operating range is not only its idle first sample. This supports inspecting runtime performance state; it proves neither a power limit nor thermal cause. GPUPower rail accounting and sensor refresh latency remain unknown, and no complete current measured cohort is covered. The exact 1866/48.42 reference has no matching GPU sensors.

No evidence-backed live setting is selected. Prior and fresh Windows readbacks both name REV:N Performance, and ADLX tuning support is false. Root's current 24-processor WSL configuration and Docker unlimited CPU/noCpuset are preserved; no correspondingly bound Oct 4 historical HostConfig/.wslconfig is retained. CPU affinity should follow actual process/thread telemetry.

A concrete no-restart single-variable diagnostic is request conditioning: insert one frozen serial PP8192/TG1 call outside each MTP timing window versus the sequential MTP control. Historical client had calibration plus four PP8192/TG1 calls and alternated serial/MTP; current client sends sequential MTP. This tests that difference, but supplies no engine optimization or causal claim. Fresh repeated decode remains about 42 tok/s, so the first warmup alone does not explain steady decode.

The historical request constructor is `scripts/benchmarks/gateway_cold.py:99–102,115–116`. Its serial body uses `model: halogen-v2`, one user message containing the frozen prompt, `temperature: 0`, `seed: 1`, `stream: false`, `cache_prompt: false`, `enable_thinking: false`, `reasoning_effort: none`, `chat_template_kwargs: {enable_thinking: false}`, `max_tokens: 1`, and `drafter: serial`. Its sorted-JSON request SHA is `c908c88d62356450236f5dacb1bad2cb51a8ce19dced1bae739e97bda854d91f`. The historical receipt has prompt/output counts 8192/1 and zero cache, disk restore, drafted and accepted draft tokens. A conditioned control should preserve those fields, keep conditioning outside MTP timers, and retain conditioning receipts separately from one warmup and three measured MTP128 receipts.

The concrete prefill candidate with existing positive evidence is the qualified native WSL lookup mount: sampled article initial turns were 28.16%/31.66% faster than late stock, with byte-identical lookup values. It has no demonstrated 8K, decode or full-wall gain. It requires a restart because HGN mapping and tensor pointers are established at load; there is no supported live remap endpoint. PLD, gather, depth/chunk/kernel and trained-matmul alternatives have already been screened or rejected.

[Machine-readable source identities, interval membership and limitations](halogen-performance-gap-audit-20261005.json). This audit read retained source/log/JSON files only and published sanitized reports. It performed no hardware/provider/model payload call, process mutation, test or engine restart.
