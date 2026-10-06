# Next mechanisms after the GPU batching screen

The goal is higher actual Halogen Prefill and Decode throughput and native draft acceptance. Evaluate GPU, CPU and NPU after each development; select by complete engine benefit. No new improvement is qualified in this source review. The original arena8192 server remains ready/open. Automation remains paused.

The [compact-Q8 GPU H audit and DPP screen](halogen-gpu-compact-h-mechanisms-20261006.md)
are now complete. Selected H has no WMMA/LDS staging to pad. Its distinct DPP
exchange realization produced exact frozen outputs, but showed no demonstrated
advantage: mean140.444 microseconds original versus141.222 candidate, with the
second arm faster in every measured pair. No intrinsic slowdown or serving
gain follows. It remains disabled and is not repeated. A separate two-row Q8
input-reuse lead is source-only; ordinary Prefill needs its own bound dispatch.

The user's standing instruction on 6 October makes this device comparison a
requirement for every development. Exact replacements can lower compute or
host overhead while preserving native acceptance; an acceptance increase
requires better proposals or a different verified speculation policy. Report
measured serving rates separately from component latency and from unmeasured
applicability. A faster component alone is not a serving gain.

The distinct growing256 GPU drafter has now completed its finite screen with
all correction costs: [report](halogen-growing-gpu-proposer-screen-20261006.md).
Three-ID proposal mean10.148ms plus complete resolution mean22.202ms, with the
initial seed paid once, totals34.280ms per round. Six rounds appended and nine
cleared/rebuilt both caches. Offline prefix matches are22/44, with19 matches
conditioned on opening-reference equality; none are native acceptance values.
The route remains disabled and is not repeated merely to collect more gates.

| Development | GPU assessment | CPU assessment | NPU assessment | Serving outcome |
|---|---|---|---|---|
| Complete growing-window proposer replay | Measured34.280ms/round including seed and all corrections | Prior45.09ms proposal+one-append proxy already too costly under the same planning reference; no repeat | Prior distinct-quantization67.68ms proxy already too costly; no repeat | No Prefill/Decode/native-acceptance delta measured; original restored ready/open |

The31.759ms rejection allowance is conditional on the historical48.2804tok/s
reference and retained37/15 stock outputs. It is not a controlled comparison
against every current workload or slower stock rate. The measured component
cost and limited offline match depth do not justify engine adoption. New
development must identify its target Prefill/Decode/acceptance mechanism,
assess GPU/CPU/NPU feasibility, then price complete costs before a matched
serving comparison. Device utilization alone is not the success metric.

| Development | GPU applicability | CPU applicability | NPU applicability | Serving metric in scope |
|---|---|---|---|---|
| BF16 hidden vector sibling | Measured slower:160.095 versus136.962 microseconds; disabled | No new CPU implementation | Existing synchronous projection also rejected | MTP Decode only; target Prefill outside this boundary; exact rows preserve proposal IDs |
| Fixed embedding checked-copy consumer | Skips native gather/RMS/M1 with original GPU row bytes | Replaces18 live maps scans per hit with bounded fresh owned copies | Producer deferred until consumer wins | Potential Decode improvement; no intended acceptance change; target Prefill outside this boundary |
| Independent verified drafter | Existing rolling512 GPU screen rejected; growing policy distinct and unmeasured | Existing rolling512 CPU screen rejected | Token-proposal route distinct from projection replacement | Potential Decode and accepted-proposal improvement only if proposal, correction and transport costs beat the native path |

The first checked-copy observer identified the sole WSL VM GPU worker as a
foreign process because this machine attributes GPU work to `vmwp`, rather than
`vmmemWSL`. That stock window was retained as an invalid matrix; no candidate
engine was started. The corrected observer retains the single VM worker PID and
birth, checks them during the cohort, and detects other Windows process GPU
activity. Its attribution covers the WSL VM as a whole, rather than each Linux
process; exclusive original-engine/container admission remains necessary.

## Native GPU and CPU/SSD source findings

The paired natural16K batching experiment is [terminal](../benchmarks/halogen0162-natural16k-native-batch-20261006.md). Its candidate changed the output and the final stock window was not admitted. Do not repeat that rejected cohort. The earlier standalone H-vector sibling was slower than native and does not replace ordinary target prefill.

The native learned PLE table is a read-only shared mapping. Selected 160-byte rows are copied with `memcpy`; there is no per-row read/pread syscall to remove. Exact row IDs arrive after synchronous device-to-host transfer at RVA `0x17d7aa6`. Workers already claim 256-row ranges. A page-ordered gather could scatter the same bytes back to original destinations, but no retained native row/page/residency/fault trace establishes a benefit. Sorting would add critical-path work. No blind readahead, duplicate LRU or NPU decoder is justified by this evidence. See [the retained native LUT audit](halogen-cpu-ssd-opportunities-20261004.md).

The attached ready-embedding worktree already implements whole-branch gather/RMS/M1 suppression and direct seed argument substitution. Both capture and fixed controls completed and slowed Decode. Direct aliasing is therefore an existing rejected mechanism, not a newly discovered implementation gap. The fixed control had 292 complete hits, identical output and 60% native acceptance, but Decode fell from the stock bookend mean 41.589 to 32.539 tok/s. Its source report is `C:/Users/Marcel/.codex/worktrees/npu-ready-embedding/strix-alloy-clean/docs/research/halogen-npu-ready-embedding-status-20261005.md`.

## Different consumer cost mechanism: checked host copies

The fixed consumer performs 18 fresh `/proc/self/maps` scans per complete warmed hit. A prior faster-parser replay excluded filesystem reopening and live proc-map generation; it did not price eliminating those scans. A separate, default-off checked-copy policy will replace hot raw host reads with exact bounded `process_vm_readv(self)` snapshots.

Every relevant seam freshly copies model fields/descriptor, token and wire data into owned host storage. Launch validation copies the argument pointer array, then the 4/8-byte argument values. Require exact returned byte counts; discard incomplete snapshots. The seed launch submits an entirely owned three-value argument vector. Caller, kernel, shape, branch order, descriptor and pointer identities remain checked. Activation retains exact executable/mapping permissions and hashes. Existing serial head ownership, immutable imported rows and conservative GPU-context/allocation retirement remain.

This new policy requires readable host ranges, rather than asserting that each range lies inside one VMA. It does not cache host mapping lifetime. Snapshot copying is not atomic against a concurrent writer; the existing single-owner generation is still mandatory. A failure before arming excludes the candidate; after any skipped branch operation it fails stop. Numeric tolerances and target arithmetic are unchanged. Fixed rows were uploaded and synchronized before visibility, so a fixed-only lookup may omit repeat readiness event queries while keeping lifetime and retirement checks.

GPU applicability: remove host launch-validation overhead around previously proved GPU branch skips. CPU applicability: perform small kernel-checked reads instead of proc-map scans. NPU applicability: prepare equivalent immutable rows only after the GPU-produced consumer demonstrates a serving benefit. The NPU does not become extra GPU memory and no NPU speed gain is inferred. The new policy is unmeasured until a matched stock/candidate/stock comparison completes with identical requests, output, counts and native acceptance, complete skip counters, unchanged reserves and restoration.

## Separate drafter correctness and growing context

The [hit-only greedy PLD seam](halogen-npu-native-pld-injection-scope-20261005.md) consumes bounded raw IDs, retaining native opening-head equality and exact target verification/commit/replay. Independent draft logits never replace target logits. Full F32 equality between a separate draft model's incremental and fresh-prefill rows is therefore not a necessary condition of that greedy token interface. The previously observed numerical parity failure remains a failure; it is not relabeled as passing. Exact native projection replacement continues to require its unchanged quality tolerances.

This distinction agrees with the [original speculative-decoding formulation](https://proceedings.mlr.press/v202/leviathan23a.html): the target verifies an approximation model's proposals; correctness relies on the verification rule. It does not qualify this project's native injection, cancellation or ownership protocol by itself.

Mandatory external state includes authoritative committed IDs/positions, fresh request and round epochs, deep-owned logits, tokenizer/model binding and the native proposal-count cap. Only a fully authoritative consumed prefix permits append. Rejected consumed IDs, an opening-rejected/unused proposal, cancellation or window rebase must discard speculative state and clear both attention and recurrent state before rebuilding. No future target labels may enter prediction.

The current rolling512 GPU route costs approximately 63 ms for proposal plus rebuild and is rejected. A 256-ID seed growing toward512 is a distinct context policy. Its existing proposal-plus-one-append proxy is 15.54 ms, but that omits rejection, extra authoritative updates and native contention. The retained rolling512 cases permit append in only six of fifteen cases after the offline opening constraint; nine require discard/rebuild. Those counts cannot be transferred to the shorter context. A useful next component screen must measure its actual predictions and complete correction costs, not repeat count1 append parity. This source distinction does not authorize live injection or establish native acceptance.
