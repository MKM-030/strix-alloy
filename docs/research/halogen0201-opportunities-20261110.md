# Halogen 0.20.1: opportunities and next comparisons - 10 November 2026

The official latest release is **0.20.1**, published on 9 November. It creates a useful follow-up latency candidate, while new open GPU kernels supply concrete source-study leads. The completed native cost comparison adds workload-dependent throughput and API acceptance results. The 0.20.1 update records installation, serving verification and baseline measurements. [Update record](halogen0201-update-20261110.md).

## Verified release identity

| Field | Fresh public-source observation |
| --- | --- |
| Latest tag / main commit | `v0.20.1` / `d2f4286fc97fd1f75cd765714dbc50524004356f` |
| Commit date | `2026-11-09T04:10:02Z` |
| Immutable image | `ghcr.io/peonist-ai/halogen-flash-server@sha256:66dac8dac25bf15f2b63a684bbe3953036045172d881525600ea41d45e5acc73` |
| Image config SHA256 | `b0973fd66e5aa886b54cfaf2e4ad976b8d56ad2a2640221beec8dc920ade6e37` |
| Image revision label | `9f38fe7ba960` |

The public tag and main commit agreed. The GHCR manifest digest header agreed with SHA256 of its raw bytes; the config blob hash agreed with the manifest's config digest. These checks do not establish engine, provider or runtime identity after local installation. [Official tag](https://github.com/peonist-ai/halogen-flash-server/tree/v0.20.1), [official package](https://github.com/peonist-ai/halogen-flash-server/pkgs/container/halogen-flash-server).

## First candidate: reuse the exact completed reply

Version 0.20.1 caches a completed reply's end so an unchanged conversation continuation can resume there. Upstream reports follow-up first-token latency of 0.60 to 0.19 seconds on code edits and 0.36 to 0.21 seconds on document chat. The runtime, GEMM tuning and Flash weights remain those of 0.20.0. These are upstream follow-up latency observations, not local cold-prefill or decode gains. [Pinned changelog](https://github.com/peonist-ai/halogen-flash-server/blob/d2f4286fc97fd1f75cd765714dbc50524004356f/CHANGELOG.md).

The local comparison should keep a separate Cache Off cold-input control, then compare complete identical multi-turn requests with cache enabled. Preserve the previous assistant reply exactly, count newly read and reused input tokens, and report full-request latency and time to first token alongside native phase rates. A reused prompt cannot be presented as a faster computation of every original input token. Recheck effective cache settings and reply-end reuse in native logs; a configured policy alone is insufficient.

The completed 0.18.22 Off/Flexible/Off study reused 8064 of 8121 follow-up input tokens. First-content latency averaged 0.324 seconds against controls of 4.211 and 4.335 seconds. Those requests replaced the final user question and omitted the previous assistant reply. The 0.20.1 proposal appends the exact captured assistant answer and the next user question, then freezes identical history across all arms. Its results should retain full, reused and newly processed input counts, first-content latency and whole-request time. This three-arm design measures the combined cache benefit, with the incremental reply-end contribution still unresolved. [Completed local cache study](../benchmarks/halogen01822-cache-followups-20261101.md), [immutable reply-end release notes](https://github.com/peonist-ai/halogen-flash-server/blob/d2f4286fc97fd1f75cd765714dbc50524004356f/CHANGELOG.md#0201).

## Completed native MTP cost comparison

V5 completed all six `gate / cost / gate` cohorts on natural 8192/16384-token inputs, with a Q4 draft vocabulary, paired 2048 prefill settings and exact 128-token outputs. Each cohort excluded one warmup and retained three measured requests. All 24 responses preserved their input size's exact output bytes. [Completed comparison](../benchmarks/halogen0201-mtp-cost-gate-20261110.md).

At 8K, cost raised API head acceptance from 59.43% to 64.95%, while RAW decode fell to 42.54 tok/s against gate controls of 46.82 and 45.38. At 16K, cost reached 44.19 tok/s against 42.71 and 39.09, with acceptance rising from 50.46% to 58.16%. The stock controls drifted materially, and candidate prefill and whole-HTTP results lay between them. Cost remains default off, with general serving improvement unqualified and automatic promotion disabled. API acceptance remains explicitly reported with `acceptance_independently_reconciled=false`, and native chain counters retain their narrower scope. [Numeric evidence](../benchmarks/halogen0201-mtp-cost-gate-20261110.json), [counter derivation](halogen0201-counter-scopes-20261110.md).

## Paired prefill arena comparison

The V2 comparison completed all six paired 2048/8192/2048 cohorts with fixed natural inputs, weights and gate policy. Candidate prefill reached 1526.01 tok/s at 8K and 1380.48 at 16K, exceeding both controls by 17.95–26.22% and 4.58–13.17%. Candidate outputs differ from their controls, leaving causal decode comparisons open. The normal server uses paired 2048 while the next prefill setting is assessed. [Complete comparison](../benchmarks/halogen0201-prefill8192-20261111.md), [V2 plan](../benchmarks/halogen0201-prefill8192-plan-20261111-v2.json).

## Manufacturer comparability

The published v2 means of 66.80 tok/s on 0.18.16 and 66.97 on 0.20.0 cover ten short task shapes with a 256-token cap, greedy decoding and Thinking Off. The official `bench` sends HTTP chat requests and averages native/API ledger decode rates, with whole-request wall time reported separately. The reported machine has 128 GB and about 85 W sustained package power under native Linux. A latest-version replay should preserve the complete corpus and declare the local cache, capacity, arena and WSL differences. [Immutable performance tables](https://github.com/peonist-ai/halogen-flash-server/blob/d2f4286fc97fd1f75cd765714dbc50524004356f/docs/performance.md), [official runner](https://github.com/peonist-ai/halogen-flash-server/blob/d2f4286fc97fd1f75cd765714dbc50524004356f/tools/bench-serving.py).

The exact runner and prompt file are unchanged from the retained 0.18.22 sources. The completed local 0.18.15 same-corpus replay reported 50.13 native decode tok/s and 48.62 output tokens per whole-HTTP QPC second. A new replay can answer the latest-version same-corpus question while preserving the separate natural 8K/16K benchmark. [Completed local replay](../benchmarks/halogen01815-comparison-20261025.md), [immutable prompt set](https://github.com/peonist-ai/halogen-flash-server/blob/d2f4286fc97fd1f75cd765714dbc50524004356f/tools/eval-prompts.json).

## Third candidate: study specific GPU kernels

libosmos **0.6.0**, published at **18:12:04 UTC on 10 November**, pins commit `1159beef39c11dce66facc78e984c6e712eae2cc`. Its new source coalesces expert f16 gathers, fuses mixer operations and adjusts expert prompt tiles. These target memory movement and launch overhead. They are source-study leads for an open GPU implementation; a GGUF kernel is not a compatible replacement for Halogen's private weight layouts and consumers. [Primary release](https://github.com/mrsirg97-rgb/libosmos/releases/tag/v0.6.0), [pinned mixer kernels](https://github.com/mrsirg97-rgb/libosmos/blob/1159beef39c11dce66facc78e984c6e712eae2cc/kernels/q4x.hip), [pinned matmul kernels](https://github.com/mrsirg97-rgb/libosmos/blob/1159beef39c11dce66facc78e984c6e712eae2cc/kernels/mm.h).

Before any engine cohort, identify an actual matching hot path and prove shapes, strides, rounding boundaries, ordering, ownership and synchronization. Keep a candidate only if the complete request improves beyond the bookends' variability. The earlier [routing-table feasibility review](halogen0191-mtp-next-mechanisms-20261107.md) already found that Halogen has parallel histogram/scan/scatter; repeating that premise is not a new optimization.

## DFlash2: a workload selector, not universal acceptance

libosmos 0.5.12, commit `22f9710b211a5dff89fbcf11dc8b46698a983f8e`, adds a Qwen3.8 DFlash2 option. Its low-power tests report chat 54.9 versus MTP's 45.4 tok/s, but prose 39.4 versus 44.0 and real agent turns 41.7 versus 44.1. MTP stays its default. Its drafter consumes intermediate target features, so a separate model endpoint alone does not establish integration. [Primary release](https://github.com/mrsirg97-rgb/libosmos/releases/tag/v0.5.12), [pinned integration](https://github.com/mrsirg97-rgb/libosmos/blob/22f9710b211a5dff89fbcf11dc8b46698a983f8e/src/q4x/hip_dflash.c).

Any local proposal needs a compatible target-feature interface, token vocabulary, accepted-prefix feedback and rollback. Prefer an isolated workload comparison over parallel independent MTP servers. Neither racing more guesses nor a larger accepted fraction proves better useful-output throughput.

## NPU, drivers and community freshness

The existing [ready-embedding experiments](halogen-npu-ready-embedding-status-20261005.md) preserve outputs and acceptance but lose 21.76% decode in the fixed-row consumer. The [paired projection](halogen-useful-npu-decision-20261005.md) is also slower on the NPU. Both remain rejected for serving; no NPU producer should be attached to a consumer already shown to be slower. Their component milliseconds cannot be converted into measured prefill/decode tok/s. The reviewed distributed tile SRAM is not an additional GPU heap.

Ryzen AI documentation now identifies **1.9**, including longer NPU LLM contexts and dynamic LoRA for selected small Qwen models. It supplies no demonstrated Flash-Next MTP handoff. AMD's 395 support page still lists **26.10.2 Optional (30 October)** and **26.10.1 Recommended (20 October)**. XRT's release listing identifies 2.25.0 as a prerelease. These observations authorize no driver replacement and establish no speedup. [Ryzen AI notes](https://ryzenai.docs.amd.com/en/latest/relnotes.html), [AMD 395 drivers](https://www.amd.com/en/support/downloads/drivers.html/processors/ryzen/ryzen-ai-max-series/amd-ryzen-ai-max-plus-395.html), [XRT releases](https://github.com/Xilinx/XRT/releases).

Targeted Reddit searches again locate GPU/NPU prefill overlap projects. Their Linux fabric-hold requirement does not establish a supported Windows/WSL path. The retrieved subreddit new-feed snapshot was three weeks old, so current community freshness is unverified. No unsupported overlap, fabric-clock, voltage or overclocking change is proposed. A new NPU experiment must first name a supported handoff and independent computation with sufficient lead time and plausible whole-engine savings.

## Execution order and evidence

1. Assess paired 4096 on the latest engine using the completed 2048/8192 comparison and preserve the public endpoint.
2. Compare exact-history cached follow-ups with a separately reported cold-input control.
3. Use the completed fixed-Q4 draft-vocabulary cost comparison as the reference for further decode work.
4. Study one specific GPU hot path from the new open sources; only then admit a matched kernel experiment.
5. Reopen NPU hardware work only for a new supported mechanism with measurable benefit potential.

Startup remains 30/131 GiB physical/commit admission; runtime reserve is 18/18 GiB and measurement entry 22/22 GiB. Root checks actual live owners and GPU load. Source changes, utilization or passing numerical tests alone do not qualify a throughput improvement. The full acceleration goal remains unachieved.
