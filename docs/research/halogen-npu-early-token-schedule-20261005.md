# Early token schedule and remaining useful NPU path — 5 October 2026

The corrected paired NPU projection passes the unchanged `rtol=.03,
atol=.003` frozen native-GPU screen, but is slower than the original GPU
projection. It remains unsuitable for synchronous placement. No current
source implements an early NPU producer or admits a live FC output swap.
There is no actual NPU-on Prefill/Decode token-rate result.

The smallest new implementation is the pure host-token planner in
[`halogen_mtp_early_token_schedule.py`](../../scripts/benchmarks/halogen_mtp_early_token_schedule.py).
It snapshots immutable token IDs, implements the exact automatic/replay shift,
deduplicates the known token-only producer requests, and checks the actual late
head position/count/tokens against that plan. It reports potential row coverage
without treating token membership as completed upload or arithmetic admission.
It performs no file, engine, model, tensor, provider or device operation. Its
syntax was checked with `ast.parse`; no behavioral or hardware test was run.

## Original embedding RMS was already executed

The previous early-token note's statement that original embedding RMS had no
executed receipt is stale. The retained root-owned ROCr component run
`alloy-rocr-component-16a35be771404bd7a7ac3d1b43526528` executed the original
`k_rmsnorm_grouped` on both explicit frozen embedding rows. The stock window
completed at `2026-10-05T00:38:45.151842514Z`. Its `stock/result/probe.json`
has independently retained receipt SHA256
`421b0f484f5364a3b71938729e78a4ef98f6eefa94ee4d8ba7d279ca42c41790`.
The outer `result.json` records `passed=true`, no contamination, exit0,
closed jobs, removed containers, and no pending cleanup; minimum physical
reserve was 26.030510 GiB.

The original engine/codeobject/HIP/ROCr bindings, raw gamma hash
`04c4a570850e06f2d8913da8220d54d4c7f87db6eb6d45480b938e8ba41d6a86`,
width 2560/groups 1, grid 1/block 256, and in-place input/output alias are retained.
Eight warmups and 64 measurements per row produced exact repeat parity.

| Frozen row | Native RMS output SHA256 | Reference relationship |
|---|---|---|
| A, raw `af284c...e374` | `97079c27ab56da44c2ab29780c856be79803d402caf754acfbf7d187fbe34892` | Matches the retained NumPy, ORT and embedding-FC input hashes |
| B, raw `e14b7e...1b4` | `8104e72375af48ab130c04b01fe68399e1d6c84951f9aa45c67a54b7d00db6ce` | Matches the retained NumPy, ORT and embedding-FC input hashes |

These facts come from the already executed probe and sealed fixture JSON;
this source audit read no tensor output bytes and reran no kernel. The original
standalone RMS arithmetic on these two rows is established. The raw native
embedding table gather, unseen-token/general-table lineage, batch dispatch and
live-head quality remain separate requirements. Root's separate accuracy audit
is updating the preparer's receipt binding; this planner supplies no numerical
admission or provider execution.

## Exact early schedule

At Target entry `0x17dd020`, RSI contains host input IDs, EDX is count, ECX
is the next token or a negative sentinel, and `model+0x220` supplies the base
position. The source retains EDX in R14D at `0x17dd031`, RSI in R12 at
`0x17dd059`, and ECX at stack+0x94 at `0x17dd034`. Trunk layers 0..47 then
execute. Automatic replay later copies `input_tokens[1:]` at
`0x17de1a9..0x17de1bb`, writes the saved/sampled final ID at `0x17de1c7`, and
calls the head at `0x17de231` with the original count and base position.
Chunk frontend `0x17e6130` supplies an already known next ID for nonfinal
chunks; direct/final calls pass a negative value. The planner maps every
negative native sentinel to unknown and never invents a prediction.

Verification `0x17dcfc0` sets model[0] bit0 and suppresses that automatic head.
Before it, `[current,draft1,...]` is already known. Preparing its drafts can
overlap the trunk, but accepted-prefix replay at `0x17dcd4f` later uses
`[matched drafts...,correction]`, count=`matched+1`, and the verification base.
The final correction/bonus ID remains unknown until target completion. The
planner validates the actual matched prefix and reports the uncovered tail.
A correction that equals a prepared draft ID may reuse that token-only entry;
it is not assumed beforehand.

The native source evidence is the retained text disassembly, SHA256
`523467ac08e576e770a9fcffdb59ffa9542f82d58958bd03d74743f8caccb8f9`,
and the [accepted-prefix ABI](halogen-mtp-accepted-prefix-replay-20261004.md).
The existing normalized head buffer remains late and cannot supply this plan.

## Narrow integration path and benefit gate

Do not build transport before the missing raw-gather gate passes. The next
concrete arithmetic action is root's existing token14367 raw capture followed
by the sealed preparer's exact-word check. The RMS gap does not need a new
kernel run for the two already qualified explicit rows. One native table-row
match still cannot qualify arbitrary token IDs.

If broader token lineage is subsequently qualified, the minimal live path is:

1. A separate constructor-installed Target hook copies bounded host tokens
   before invoking the unchanged original once; it attaches an independently
   qualified immutable model/table/gamma/weight epoch and invokes the planner.
2. A persistent Windows producer computes only the token embedding branch;
   hidden RMS/FC stays native. Retain the stable high/residual arithmetic,
   original BF16 boundaries, explicit `ORT_DISABLE_ALL`, executed NPU-only
   placement and unchanged `.03/.003` screen for each actually supported shape.
3. Completed same-epoch outputs are uploaded into private GPU cache allocations
   on a qualified stream. Publication requires a successful device event;
   merely receiving the Windows result is insufficient. A local lookup at
   embedding-FC return seam `0x17db548` uses only already complete entries.
   An unfinished entry must immediately take the original path.
4. Initially skip only the separately qualified M1 FC. Count >1 needs a genuine
   batch dispatch oracle and a complete-row hit, or separately qualified mixed
   native/candidate row assembly. The existing M1 cache cannot skip a batch.
5. Obtain shadow quality, then full-head proposals/outputs/acceptance and matched
   engine A/B rates. Count windows, missed publications, skipped FC work,
   transport/preparation/upload/lookup cost and concurrent resource contention.

This is a limited opportunity. The original embedding FC is approximately
0.153 ms GPU device time per scalar call, while the current engine averages
about 24 ms per generated token. An ideal one-FC-per-output removal is about
0.64% of that time; real call frequency, cache hits, transfers and contention
change the result. It is not a universal bound on batch prefill or a measured
gain. The native GPU cache variants already measured no net benefit. The
paired candidate's 1.850025-ms NPU session and 3.539513-ms diagnostic path cannot
be used as timings for a new embedding-only batch producer. Require measured
`max(0,L-W)+lookup/publication < G` before further integration work.

No actual tok/s A/B can be produced from the newly restored, unchanged
colleague server by these sources. Native hooks install at process construction;
it has neither an early producer nor an admitted output-swap mode. A future
separate owned instrumented engine process would be required. Under the current
single-engine reserve constraint that would displace the colleague's server.
Do not hot patch it, relabel an unchanged GPU control as NPU-on, or report zero
NPU token-rate delta for an unperformed A/B.

## Independent Windows sidecars

The public Halogen decision, embedding, reranking and moderation responders
use native Linux `amdxdna`/XRT. The [retained integration audit](halogen-laya-jev-sidecar-feasibility-20261004.md)
does not establish those services on Windows/WSL. The gateway's rerank routes
only forward requests; they supply no Windows responder or NPU placement proof.
The installed portable Windows FastFlowLM Qwen3:0.6b has standalone NPU chat
evidence, but no held-out decision/rerank quality qualification. Its
[coexistence measurements](npu-coexistence-measured-20261001.md) showed about 7%
GPU decode loss under continuous helper requests and about 2–3% with four-second
pauses. Adding routine helpers therefore has no demonstrated main-path benefit.

A separately qualified narrow decision/rerank model could reduce total GPU
work by replacing an entire auxiliary Qwen request or supplying a smaller
retrieval context. That is a different workload and must be measured as task
quality and total request cost. It does not increase Flash's unchanged-prompt
Prefill/Decode rate. No new model, sidecar, provider or service was activated.
