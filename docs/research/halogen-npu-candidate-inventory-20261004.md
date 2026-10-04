# Retained NPU candidate inventory — 4 October 2026

This is a **source and earlier-report inventory**, not a new measurement. It
reads research notes/JSON and runner source only; no payloads, providers,
processes, imports or hardware were used. The FC standalone and tiled-D work
being performed in the current root-owned window belongs in a separate fresh
result report. The older measurements below must retain their original scope
and date; a failed admission with zero inference calls is not a measured NPU
inference latency.

No retained candidate implements a complete qualified NPU MTP head. Subgraph
latency, numerical success and provider placement do not supply live MTP
acceptance or end-to-end decode throughput.

## Earlier outcomes and exact launch sources

Except the first row, these are **earlier 2026-10-04 results**, not current-window
reruns. Latencies are host-call means unless another scope is stated.
`LOCAL` below means `C:/Projects/strix-alloy-clean/server/.local/optimization9h-20261004`;
`BENCH` means `C:/Projects/strix-alloy-clean/scripts/benchmarks`.

| Candidate / original measurement date | Earlier result and scope | Existing launch source |
|---|---|---|
| Static single expert0, 2026-10-02 | CPU 0.101871 ms, 100 calls; no completed NPU result documented. Older w4b/extracted lineage. | `BENCH/halogen_npu_expert_onnx.py --check-model ... --provider cpu/npu --reps 100 --report ...`; this probe needs an outer owned guard. |
| Static selected top10, IDs0–9 | Final eight-operator graph: CPU **6.394102 ms**, NPU **1.504985 ms**, 100 calls; NPU initialization 32,704.2376 ms. Max absolute NPU error 2.797833e-4 passed `.03/.003`; all executed Nodes VitisAI, all eight dynamic outputs in hw/stx context. Fixed synthetic x/router, not live selection. Earlier nine-op variants failed strict placement/compilation. | `C:/AI/halogen-mtp-npu/run_top10_routing_guarded_20261004.py`; historical variants `run_top10_guarded_20261004.py`, `run_top10_copyep_guarded_20261004.py`. |
| Tiny runtime-weight expert | CPU **0.047997 ms**, 100 measured calls. NPU numerical warmup failed **21/64** elements; no qualified NPU mean. Two retained fused profile events are provider work, not a successful replay. | `BENCH/halogen_npu_parameter_guard.py` → `halogen_npu_parameter_probe.py`. |
| Tiny first GEMM | NPU returned all twelve A/B outputs, but A **16/640**, B **87/640** violate the frozen gate; no promoted NPU latency. | `LOCAL/run_first_gemm_guard.py` → `BENCH/halogen_npu_precision_probe.py`. |
| Four-term split first GEMM | CPU **0.7020375 ms**, NPU **1.17655 ms**, eight measured calls after four warmups. Both A/B pass; maximum errors .008962392807006836 / .01751232147216797; twelve VitisAI Node events. Tiny projection only, slower than CPU. | `LOCAL/run_split_gemm_guard.py` → `BENCH/halogen_npu_precision_split_probe.py`. |
| Full tiny split expert | CPU **0.7535125 ms** same-window mean. NPU retains twelve stable outputs: A passes, B **9/64** fail, max error .027966737747192383. `timing_qualified=false`. | `LOCAL/run_expert_split_guard.py` → `BENCH/halogen_npu_precision_expert_split_probe.py`. |
| Real-v2 runtime-weight top10, two selected sets | CPU **114.6097125 ms**, NPU **126.9444625 ms** host; `session.run` **6.207575 / 19.09755 ms**. Four warmups/eight measured calls, numerical screen passes. About108 ms per call is host weight preparation/copy, so NPU is slower. | `LOCAL/run_v2_dynamic_guard.py` → `BENCH/halogen_npu_v2_dynamic_expert_probe.py`. |
| FP32 bank20 with dynamic Gather | CPU **12.207125 ms**; strict NPU session fails because Gather remains outside VAIML. **Zero NPU inference calls**. | `LOCAL/run_bank20_guard.py` → `BENCH/halogen_npu_v2_bank20_expert_probe.py`. |
| BF16-rounded bank20 qualification | CPU precision prerequisite fails A **1,832/2,560**, B **2,274/2,560** against unchanged strict reference. **No BF16 graph/data or NPU session prepared**. | `BENCH/halogen_npu_v2_bf16_bank20_probe.py` is a CPU qualification, not an NPU replay. |
| Captured live-route BF16 bank16 Gather | CPU **17.709825 ms** offline. Strict NPU session placement fails; **zero NPU inference calls**. Two actual captured routes, approximate BF16-weight scope. | `LOCAL/run_live_bf16_guard.py` → `BENCH/halogen_npu_v2_live_bf16_gather_probe.py`. |
| Captured live-route BF16 row-Gather | Guarded CPU **20.3555625 ms**. Strict NPU session fails after23.553 s; both Gathers outside partition, **zero NPU inference calls**. | `LOCAL/run_live_bf16_row_guard.py` → `BENCH/halogen_npu_v2_live_bf16_row_gather_probe.py`. |
| Light EP ordinary tiny graph | Exact Light NPU selected; strict session placement fails with CPU assignment. **Zero inference calls**. | `LOCAL/run_light_ep_guard.py` → `BENCH/halogen_npu_light_ep_admission_probe.py`. |
| Light QMoEBf full packed bank, allocator/Header/rank variants | ORT1.25 custom-op registration/API gates fail. ORT1.29 strict sessions initialize, but first synthetic invocation crashes before return, including provider-I/O, basename, session allocator, retained-holder and coherent rank3 attempts. **Zero validated returned outputs or latency**. | `LOCAL/run_qmoe_light_guard.py`, `run_qmoe_provider_io_guard.py`, `run_qmoe_basename_guard.py`, `run_qmoe_native_session_allocator_guard.py`, `run_qmoe_retained_allocator_guard.py`, `run_qmoe_rank3_guard.py`. |
| Public DD zero-weight FC1/FC2 | Four individual completed intervals: FC1 **2.6798 / .2583 ms**, FC2 **.2723 / .2117 ms**. Synthetic operator admission; no top10/activation/routing or statistical mean. | `BENCH/halogen_dd_owned_fc_guard.py` or `LOCAL/run_dd_owned_fc_guard.py`, sealed config selects `BENCH/halogen_dd_owned_fc_probe.py`. |
| Public DD real-v2 expert0 FC1/FC2 | Both FC1 cases fail **1/1,280**; both FC2 pass with individual intervals **.2605 / .2032 ms**. FC1 timing null. Approximate INT4 conversion adds8.46–8.53% weight relative L2 error; no native/MTP parity. | Same DD guard with sealed config selecting `BENCH/halogen_dd_real_fc_probe.py`. |
| Original count1-D norms/FC/seed | CPU original NumPy screen fails. Separate original-ORT graph screen passes CPU; NPU compiler L1 allocation fails at SinglePassRMSNorm with **zero inference calls**. | `BENCH/halogen_npu_v2_d_prepare_probe.py`, `halogen_npu_v2_d_graph_probe.py`, through `LOCAL/d-prepare-owned-run.py --config ... --sha256 ... --out ...`. |
| Fixed256 tiled count1-D | Twelve CPU calls complete; hidden RMS matches native A/B words. Seed gate against original ORT fails **73 /55** elements, and A against NumPy fails1. **No tiled NPU session was started in the earlier report.** | `BENCH/halogen_npu_v2_d_tiled_probe.py`, same generic owned component runner. Current standalone diagnostic adaptation is separate. |

Sources for numerical/provider outcomes: [top10](halogen-npu-top10-20261004.md),
[tiny parameter input](halogen-npu-parameter-probe-20261004.md),
[precision/split probes](halogen-npu-precision-20261004.md),
[real-v2 dynamic/bank20](halogen-npu-v2-dynamic-20261004.md),
[live BF16](halogen-npu-live-bf16-20261004.md),
[row-Gather](halogen-npu-live-bf16-row-20261004.md),
[Light placement](halogen-npu-light-ep-route-20261004.md),
[QMoE registration](halogen-qmoe-registration-diagnosis-20261004.md),
[QMoE rank3 follow-up](halogen-qmoe-fault-contract-followup-20261004.md),
[DD synthetic](halogen-dd-owned-fc-admission-20261004.md),
[DD real](halogen-dd-real-fc-admission-20261004.md),
[D graph/tiled outcomes](halogen-npu-d-graph-fidelity-20261004.md), and
[2026-10-02 single-expert JSON](halogen-npu-microbench-20261002.json).

## Runnable gaps versus absent implementations

| Gap | Runnable status / smallest new evidence |
|---|---|
| Native-oriented paired FC, BF16-rounded decoded weights, normalized inputs | Built two-output graph and complete native-oracle probe exist. Normal `halogen_npu_v2_d_native_projection_probe.py` requires successful same-source CPU evidence before NPU. Current failed CPU evidence can be examined by the separately labelled `halogen_mtp_fc_npu_diagnostic.py`; it grants no integration admission. Root is producing the fresh result separately. |
| Fixed256 tiled-D NPU | Built graph, fixtures and probe exist, but normal NPU path rejects the failed CPU seed gate. A reviewed standalone diagnostic envelope is needed to measure hardware without relabelling CPU success; root's current adaptation covers this gap. |
| Original-decoded-FP32 normalized FC+seed suffix | Builder `halogen_npu_v2_d_projection_graph.py --weight-lineage original-decoded-FP32` and matching `halogen_npu_v2_d_projection_probe.py` exist. No successful CPU/NPU replay is documented in the reviewed notes. Build if no frozen graph already exists, then same-source CPU12 /NPU12 balanced calls through the owned runner. This measures the ORT-normalized cut, not native Q8 accuracy. |
| Static single expert0 NPU | Existing `halogen_npu_expert_onnx.py` can replay the retained model with `--check-model --provider npu`; outer owned guard required. Earlier CPU result has older lineage and is a separate latency control, not a current-v2 candidate qualification. |
| BF16-rounded FC+seed suffix | Projection builder supports this lineage, but the original-ORT projection probe explicitly rejects it; paired native projection probe exposes separate projections and excludes seed. **No matching retained FC+seed replay probe** found. |
| Composed native-oriented tiled-D, BF16 weight casts | Built by `halogen_npu_v2_d_native_graph.py`; seven diagnostic outputs. **No matching retained replay probe** found. Original/tiled/native-paired probes have different exact graph/output contracts. |
| BF16 bank20 / complete NPU head | Bank20 CPU precision prerequisite fails before graph preparation. Complete head is a plan with missing attention/history/HC/vocabulary implementation. Neither is a ready inference candidate. |
| Persistent FC shadow publication | Source implementation exists, but it requires genuine successful native/CPU/NPU arithmetic admission. Standalone diagnostic execution cannot satisfy this gate. No whole-head NPU/MTP benchmark can be inferred from it. |

The smallest useful new hardware set is the current paired-FC diagnostic and
tiled-D diagnostic, plus the original-FP32 normalized suffix if “all” includes
that distinct unmeasured cut. Static single-expert NPU is an optional old-lineage
dispatch control. The earlier successful static-top10, runtime-weight-top10 and
split-GEMM results already cover their unchanged configurations; failed Gather,
Light and QMoE attempts already identify their exact placement/fault boundaries.
They remain listed as failed or unmeasured inference, never as successful latency.

For a matched engine comparison, the earlier native layer48/count1 MLP bracket
is **.404611973 ms mean**,73 calls (median .390228987, p95 .487067997), including
event-observer waits/enqueue gaps. The separate stock PP8192/TG128 cohort is
**1584.5019 prefill /47.0600 decode tok/s,60% acceptance**. Neither denominator
is the same scope as a synthetic NPU operator replay; current engine throughput
requires its own matched workload and server-state result.
