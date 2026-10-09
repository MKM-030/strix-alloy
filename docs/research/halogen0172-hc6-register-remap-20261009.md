# Halogen 0.17.2: native HC6 register-remap screen

The candidate completed native redirection and exact generated-output/accounting parity on the frozen workload, but established **no qualified serving speed gain**. It remains disabled and will not be repeated unchanged. Stock 0.17.2 is restored ready/open with the original profile and visible request-log console.

“Stock” means the unchanged normal project 0.17.2 profile, including its existing WSL memory-registration/upload adapters. It is not a vanilla upstream setup. The candidate adds only the HC6 remap and redirect to that baseline.

The stock → candidate → stock screen uses one excluded warmup and three measured requests per arm: 8,192 actual synthetic repeated input tokens and 128 normally generated output tokens per request, temperature 0, seed 1, Thinking Off and Cache Off. The finite-vocabulary pseudoprose contains 116 repeated calibration-prefix units; it is not representative non-repetitive document input. Context 262144, one slot, MTP2/PLD3,3 and prefill chunk/max 8192 remain fixed. Rates are direct native API rates, without clock normalization. Spread is sample standard deviation.

| Window | Prefill tok/s, mean ± SD | Decode tok/s, mean ± SD | Combined API MTP+PLD acceptance |
| --- | ---: | ---: | ---: |
| stock-before | 1233.112 ± 9.187 | 43.543 ± 0.875 | 210/339 = 61.95% |
| candidate | 1184.299 ± 31.672 | 43.540 ± 0.754 | 210/339 = 61.95% |
| stock-after | 1205.543 ± 35.731 | 42.620 ± 1.117 | 210/339 = 61.95% |

Candidate Prefill is -3.96% against stock-before and -1.76% against stock-after. Decode is -0.007% and +2.16%, respectively. Stock bookends drift -2.24% in Prefill and -2.12% in Decode. Candidate Prefill is below both stock means; its measured range overlaps stock-after. Decode overlaps both stocks. Neither an advantage nor a regression qualifies outside both observed stock spreads and drift. Three measurements per arm support no significance/confidence claim.

All twelve responses, including warmups, match exact `choices`, model and usage, the frozen generated-output hash, actual 8192/128/8320 tokens, zero cache/disk restore and 70 accepted / 113 drafted tokens per request. The measured 210/339 ratio uses combined native API MTP+PLD counters; isolated native MTP acceptance is unavailable. Generated-output/accounting parity on this repeated-input workload does not prove internal logits/state or general numerical equivalence.

The candidate changes fourteen bytes in the full pinned native gfx1151 code object: twelve integer register operands, one descriptor field and one metadata count. Six short middle-consumer temporaries reuse dead `v109`/`v119`, lowering whole-kernel VGPR use 125→120. All 3,352 instructions were audited; independent review and redisassembly found no static equivalence blocker. Arithmetic, instruction order, memory accesses, branches, EXEC, delays, synchronization, ABI and producer/HC6-consumer paths stay unchanged. LLVM resource rules imply physical wave32 allocation 144→120 and a VGPR-only theoretical limit 10→12 waves/SIMD. **Actual occupancy and GPU phase latency were not measured**, and these limits are not converted into token-rate forecasts.

The default-off preload redirects only the qualified native HC6<3> descriptor/caller/geometry, forwards all seventeen original argument-value pointers and preserves grid/block, shared memory and stream. The separate native module route and per-hit host checks can affect performance; this screen does not isolate their costs from the remap. READY3, 21,056 eligible candidate attempts, engine/code/module/function flags, all called HIP statuses and launch balances passed; errors, busy calls and eligible fallback are zero. Stats count process-lifetime submissions, including startup/warmup. Two identical idle reads and owning PID checks accompany the completed-request boundaries. Every arm records completed 0→4, cancelled 0→0 and idle final health. The before boundary uses retained matching-run lifecycle receipts; candidate/after clients add only health audit outside timed POSTs. Their two source hashes are retained.

Excluded warmup native Prefill/Decode rates and QPC request wall seconds are:

| Window | Prefill tok/s | Decode tok/s | Request wall s |
| --- | ---: | ---: | ---: |
| stock-before | 690.772 | 34.003 | 15.662567 |
| candidate | 692.998 | 31.845 | 15.870789 |
| stock-after | 690.114 | 32.844 | 15.797401 |

Both ordinary normal stops for this cohort, stock-before and candidate, passed cleanup/recovery with owning handles closed. These receipts do not relabel the earlier event diagnostic’s separate recovery/reconciliation exception. Root’s fresh stock checkpoint binds controller 21748, backend 17844 and visible console 8612 to the stock-after run, the original profile and idle completed 4 / cancelled 0 health, with candidate removed. No extra request or hardware action was performed by CPU analysis/publication. The earlier sampled event-attribution score is not a removable HC6 budget. The full acceleration goal remains unachieved.

[Compact evidence](halogen0172-hc6-register-remap-20261009.json) retains exact sample rates, deltas, warmups, counters, lifecycle results and private evidence hashes. The [historical source archive](../../scripts/benchmarks/experimental/halogen0172_hc6_register_remap/README.md) contains nine exact-byte sources/metadata records with [source hashes](../../scripts/benchmarks/experimental/halogen0172_hc6_register_remap/source-hashes.json). It is default-off and not portable startup. Audit/transform require omitted pinned native engine/code/disassembly; analysis requires private cohort/client/lifecycle evidence. Helpers retain private Windows `.local`, WSL/container/runtime, HIP/libcrypto and model-path dependencies. No native/candidate binaries, model/tensor data, full disassembly, raw prompts/responses or credentials are public.
