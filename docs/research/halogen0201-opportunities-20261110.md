# Halogen 0.20.1: opportunities and next comparisons - 10 November 2026

The official latest release is **0.20.1**, published on 9 November. It creates a useful follow-up latency candidate, while new open GPU kernels supply concrete source-study leads. No new local throughput, acceptance or NPU acceleration result is established by this research. The [0.20.0 installation record](halogen0200-update-20261108.md) remains a dated installation record, not proof of a running 0.20.1 server.

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

## Second candidate: price the native MTP round at fixed Q4

The existing [cost-rule prospective study](../benchmarks/halogen0191-mtp-cost-gate-plan-20261107-v2.md) already separates confidence from expected useful-prefix value. Its fixed-Q4 `gate / cost / gate` comparison should remain the next decode experiment after a normal latest-version baseline. Porting the old candidate requires fresh 0.20.1 source/ABI and counter verification; the old engine identity is not reusable evidence.

Retain natural 8192/16384-token inputs, paired 2048 prefill settings, exact 128-token outputs, warmup exclusion and three measured requests per size/arm. Report neural-head accepted/drafted counts separately from lookup counters and useful-output tok/s. Higher acceptance alone can lose speed if proposing and verifying its extra tokens costs more than it saves. Do not combine a Q8 vocabulary change with the first cost-rule comparison.

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

1. Root qualifies the installed latest engine through the normal authenticated lifecycle and preserves the public endpoint.
2. Compare exact-history cached follow-ups with a separately reported cold-input control.
3. Qualify the fixed-Q4 native cost-rule comparison on the new engine.
4. Study one specific GPU hot path from the new open sources; only then admit a matched kernel experiment.
5. Reopen NPU hardware work only for a new supported mechanism with measurable benefit potential.

Startup remains 30/131 GiB physical/commit admission; runtime reserve is 18/18 GiB and measurement entry 22/22 GiB. Root checks actual live owners and GPU load. Source changes, utilization or passing numerical tests alone do not qualify a throughput improvement. The full acceleration goal remains unachieved.
