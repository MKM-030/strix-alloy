# Halogen 0.17.2: native registration-only HC6 remap

The complete stock → candidate → stock cohort qualifies **no serving speed gain**. The registration-only adapter completed exact output/accounting parity, but remains disabled and will not be repeated unchanged. Normal Halogen 0.17.2 is restored ready/open on port 8840 with its visible request-log console. The full acceleration goal remains unachieved.

“Stock” is the normal project profile, including its existing WSL memory-registration/upload adapters. The candidate removes the previous experiment's per-launch hook and separate module route: it substitutes one immutable complete bundle through `__hipRegisterFatBinary`, preserves the native returned handle, all 1,484 host registrations and all 1,491 device exports, and retains the copied image through native teardown/process exit. Independent source and exact installed-runtime reviews found no static correctness blocker. The installed custom ROCm 7.14 runtime is not equated with the upstream source revision.

The frozen request has **8,192 actual synthetic pseudoprose input tokens**, including **116 repeated ` a` INPUT calibration-prefix units**, and **128 ordinarily generated prose OUTPUT tokens**. This is not a representative non-repetitive document workload. Context capacity 262144, one slot, prefill chunk/max 8192, MTP2/PLD3,3, temperature0/seed1, Thinking Off and Cache Off remain fixed. Each arm has one excluded warmup and three measured requests. Spread below is sample standard deviation. Acceptance is combined native API **MTP+PLD**, not isolated MTP acceptance.

| Arm | Native API Prefill tok/s, mean ± SD | Native API Decode tok/s, mean ± SD | Acceptance |
| --- | ---: | ---: | ---: |
| before | 1093.756 ± 55.238 | 40.467 ± 0.276 | 210/339 = 61.95% |
| candidate | 1248.015 ± 14.790 | 42.226 ± 0.929 | 210/339 = 61.95% |
| after | 1228.149 ± 24.746 | 42.264 ± 1.092 | 210/339 = 61.95% |

The before arm's Linux MONOTONIC/RAW interval ratio is approximately **1.083307**, while candidate and after are approximately **1.000001**. RAW agrees with Windows QPC within 0.1%. Guest-clock scaling changed across the restart. Consequently the raw before→candidate increase and combined stock bookend calculation are **not qualified speed comparisons**. These are preserved native API numbers; no clock normalization or reconstructed phase rate is presented.

The bounded native timer audit proves that the Decode producer calls `steady_clock::now`; the normal provider in the exact image implements `CLOCK_MONOTONIC`. Live loaded-provider binding and phase-local clock slopes were not newly measured. The Prefill duration writer remains unproved in this audit, so the Decode clock result is not extended to a definitive Prefill clock claim. Whole-HTTP calibration cannot reconstruct measured phase rates.

Candidate and after have comparable observed clock ratios. Against after, candidate Prefill is **+1.62%** and Decode **−0.089%**; their measured ranges overlap. Three measurements per arm establish neither a repeatable acceleration nor a significance/confidence claim. The adapter is not promoted.

All twelve requests, including excluded warmups, match exact choices, model and usage, frozen output SHA256 `0fbe27247d33d2829aa90b66964ff3bb946679be7ce79b379e2555f60ec74fa6`, actual8192/128/8320 tokens, zero cache/disk restore and 70 accepted/113 drafted per request. Each measured arm aggregates 210/339. This workload's output/accounting parity does not prove general logits/state equivalence or general acceptance.

| Excluded warmup | Native Prefill tok/s | Native Decode tok/s | QPC request wall s |
| --- | ---: | ---: | ---: |
| before | 1163.157 | 40.310 | 9.463879 |
| candidate | 672.672 | 33.283 | 16.410970 |
| after | 687.473 | 27.088 | 16.674291 |

The observed minimum reserves across the twelve requests are 24.026 GiB physical and 111.441 GiB commit, above the unchanged 18/18 GiB runtime floor. This cohort does not prove startup sufficiency at the exact 35 GiB boundary. Both owned stops used normal lifecycle cleanup. Final authenticated health is idle, completed4/cancelled0, with controller15348, backend28816 and visible console33112 verified by process creation identities.

The frozen remap changes fourteen bytes: twelve integer-register operands, one descriptor field and one metadata count. Whole-kernel VGPR use125→120 may cross a theoretical allocation threshold, but actual occupancy and device-phase latency were not measured. The registration receipt confirms the exact candidate complete-bundle/payload hashes, fourteen changed bytes, original native dispatch and a nonnull native handle before and after its requests. Thirteen CPU mock cases passed without HIP initialization; those mocks are separate from real engine execution.

Engine SHA256 is `ac73b1df48510a34e0246a77bd984f1df0e02e5fa6cf1530d3d77c91d3c0e913`; installed HIP SHA256 `6f3c9fe6b655a611e04a9a5a157cb46c425717e2873973f11a67bb6bbf6587b5`; candidate complete bundle `f668c44ee907d72d07e4cc89eb3234dc384a9ec5c39b8e702b49e616690892ff`; payload `39053af36ed652892f7082af4eca5cd153b593260448b3c91a67f277cd0f1259`.

[Compact evidence](halogen0172-hc6-registration-route-20261009.json) retains samples, clocks, counters, lifecycle identities and private raw-evidence hashes. The [source archive](../../scripts/benchmarks/experimental/halogen0172_hc6_registration/README.md) is default-off and retains private Windows/WSL/controller/profile/engine/runtime/code/prompt dependencies; it is not portable startup. No native binaries, model data, full disassembly, prompts, generated responses or credentials are published. No NPU execution or NPU benefit is claimed.
