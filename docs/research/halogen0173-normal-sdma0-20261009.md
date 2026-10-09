# Halogen 0.17.3: normal SDMA copy-policy screen

The standard SDMA1 server is restored ready/open. SDMA0 remains an explicit default-off experiment. The full acceleration goal remains active; no NPU gain or universal speed improvement is claimed.

Only `HSA_ENABLE_SDMA=1` changed to `0`. The normal image, backend sources, GPU kernels, model, preloads, API credential, context 262144, one slot, MTP depth 2 / PLD 3,3, prefill chunk and arena 8192 and normal lifecycle stayed fixed. This is distinct from the disabled BN64 adapter and the previous scalar asynchronous hook. The actual mapped baseline HIP/HSA ELF hashes match the pinned SDK 7.14.0 source. Compute blits retain the source's dependencies, completions and system fences, but consume GPU compute resources. [AMD documentation](https://rocm.docs.amd.com/projects/HIP/en/latest/how-to/debugging.html)

Frozen synthetic pseudoprose has 8192 actual input tokens, including 116 repeated calibration units; each request generates 128 ordinary tokens. Cache and Thinking off, temperature 0 / seed 1. Each arm has one excluded warmup and three measurements. These are not new natural-input post benchmarks. Acceptance is combined API MTP/PLD draft-token accounting, not separately isolated MTP acceptance.

| Arm | Native API Prefill tok/s, mean ± SD | Native API Decode tok/s, mean ± SD | Accepted/drafted | Host QPC request seconds, mean |
| --- | ---: | ---: | ---: | ---: |
| before | 1068.953 ± 42.847 | 38.985 ± 2.274 | 210/339 | 9.9969 |
| candidate | 1089.861 ± 21.840 | 40.759 ± 0.157 | 210/339 | 9.7236 |
| after | 1239.812 ± 23.805 | 44.357 ± 0.629 | 210/339 | 9.5021 |

All 12 output hashes and draft-counter pairs match; each measured arm has 210/339=61.946903% acceptance. SDMA0 versus before gives raw mean Prefill+1.9559%/Decode+4.5522%; that pair passes its clock gate. Versus after, the raw differences are Prefill-12.0947%/Decode-8.1107%, but that comparison fails its clock gate and establishes no regression. A positive mean alone does not prove a causal improvement beyond sample spread.

Measured whole-request MONOTONIC/RAW ranges 1.002580192..1.099999934, relative spread 0.0971690274. RAW/QPC ranges 0.999995991..1.000007747. The cross-arm 0.1% clock gate is failed. Native phase rates remain unchanged API observations; they are not converted to RAW/QPC-derived rates. MONOTONIC advances about 10% faster than RAW in before/candidate and about 0.258% faster in after. These are not independently calibrated absolute token-speed claims. The whole-request probes do not independently establish the ratio inside either phase. QPC request seconds describe the complete request and do not isolate Prefill or Decode. No comparison to the historical 48.42 tok/s workload is made.

Decision: **retain standard; no qualified net Prefill/Decode gain**. A small cohort is a screen, not a statistical general-performance proof. Completed windows will not be repeated solely to obtain favorable numbers. Startup and load are excluded from request rates; their original lifecycle evidence remains private. Collection `passed` means successful requests and parity, while clock qualification is checked separately.

All arms passed 22/22 GiB measurement entry and 18/18 GiB runtime reserves, with no observed League/Riot process or unrelated GPU load at each entry. Startup remains 35 GiB physical / 131 GiB commit, with unchanged guards and recovery. Root alone performed all hardware/lifecycle actions. Own clients, clock probes and stop observers are closed; final standard serving remains in its visible PowerShell 5.1 console.

The independent NPU source scope identifies a tiny token-only prefix-survival/offer-width classifier as a different hypothesis. It would select stock offers without splitting target weights or reading GPU logits. Current 0.17.3 lacks a supported, request-generation-safe per-round selection callback and aligned outcome/training feed; instruction addresses alone do not implement that interface. No selector was trained, exported or run on NPU. Native adaptation already uses accepted-prefix EMA/hysteresis. Raising a reported acceptance ratio by truncating offers is not itself a Decode gain.

[Numeric evidence](halogen0173-normal-sdma0-20261009.json) · [Owned source archive](../../scripts/benchmarks/experimental/halogen0173_normal_sdma0/README.md)
