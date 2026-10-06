# Partial device snapshot: executed result and failed qualification

**The partial recurrent snapshot completed the finite GPU pass but failed exact
state qualification. Keep this realization disabled.** Exact full-F32 row
equality first failed in round 2, when committed length grew from 260 to 263.
Agreement of all 15 post-resolution greedy IDs with the scalar control does not
satisfy that requirement. No tolerance was relaxed and no serving rate, native
acceptance or historical paired improvement is established.

## What actually ran

The retained work directory is
`C:/Projects/strix-alloy-clean/server/.local/optimization9h-20261004/snapshot-gpu-component-1a07c0ad3795401799c1accc7c7fe382`;
the plan uses the same UUID. The matched llama.cpp revision is
`3466b48806f9fefe1162aa4053ffebcfcabe83aa`. The separate
`Qwen3.5-0.8B-Q4_0.gguf` remains SHA256
`57d1997790d1744fba5b40a7317df71ea5e2acee28c47e78f0cce39c0703f8cf`.
The runtime bridge source pin was
`04b76e99569ed9dfa1249e8ac0c20c72ad4ced912d012f6477073dbcb5dd57d7`.
The [JSON companion](halogen-device-partial-snapshot-results-20261006.json)
preserves complete plan/runtime/source pins and the fresh per-round analysis.

The AMD Radeon 8060S Vulkan candidate logged 25/25 layer offload. It used one
sequence, growing 256-to512 policy and a 1024-token engine context. Three warmup
commands were excluded on each side. The candidate then paid one 256-ID seed,
15 three-ID proposals and all 15 complete resolutions; it applied all 37
authoritative IDs and ended at 293. The snapshot-off control used the identical
256 prefill followed by 37 scalar authoritative forwards. There were 34 candidate
commands and 41 control commands.

Measured operations include 15 before-proposal partial device saves, nine
restores, six append resolutions, 30 speculative scalar calls and 25
authoritative replay calls. No measured resolution cleared/prefilled the full
prefix. Save/restore returned 460-byte host metadata records; this does not
describe the size of the device tensor payload.

## Exactness and freshly computed label counts

Independent offline reads compared 993,280-byte rows, all 248,320 F32 words,
against the control at the same committed length. Initial rows and resolutions
0/1 were byte-identical. Round 2 differed in 248,319 words, with maximum absolute
difference 0.1567313969. All 13 resolutions from round 2 onward differed; the
largest observed absolute difference was 0.2726221085. Committed ID histories
matched throughout and all 15 post-resolution greedy IDs matched. The cause of
the full-row discrepancy remains unestablished by these results.

The evaluator freshly scanned each actual draft against the workload's
`expected_next_ids`, stopping at the first mismatch. It separately compared the
first draft with `native_cached_first_id`; no historical prediction score was
carried forward.

| Offline statistic, one retained family | Actual result |
|---|---:|
| Leading exact-prefix label matches | 22/44 |
| Leading prefix lengths by round | 0,0,1,2,3,1,0,2,2,3,1,1,3,3,0 |
| First ID equals next target label | 11/15 |
| First ID equals retained native opening reference | 10/15 |
| Leading matches in opening-equal rounds | 19 |

There were 45 predictions and 44 retained label positions; the final third ID
is unscored. These are offline counts from a trajectory that failed exact row
qualification. They are not measured native acceptance or a useful gain over
the retained stock drafts. Actual hit eligibility, opening execution, readiness,
verification/replay cost and target contention remain unmeasured.

## Costs of this failed trajectory

| Recorded candidate operation | Milliseconds |
|---|---:|
| Initial 256 prefill | 32.6397 |
| Proposal mean, including save | 10.95597 |
| Complete resolution mean, all 15 rounds | 8.61200 |
| Restore-resolution mean, nine rounds | 11.35153 |
| Append-resolution mean, six rounds | 4.50270 |
| Save mean, already included in proposal | 2.01169 |
| Restore mean, already included in resolution | 1.96563 |
| Seed plus all proposals/resolutions | 326.1592 |
| Seed-amortized core per round | 21.74395 |

Binary row writes took 40.8288 ms across candidate commands and are excluded from
the command timers. Candidate excluded warmup commands took 1246.8931 ms.
Runtime elapsed before manifest writing was 2328.4921 ms candidate and 977.9367 ms
control; the owned component-process receipt records 4.625 s. Control cost is
verification overhead, not a competing serving baseline. These are measured
component costs without a matched Halogen comparison or concurrent target load.
They cannot qualify this numerically failed candidate.

## Lifecycle receipts and reporting scope

The component exited 0, closed its owned job and reported qualification failure.
The initial coordinator restoration receipt and subsequent bounded observation
receipt both reported readiness failure; both remain intact. A later
`supplemental-ready-8bcaad09e312472cbacdbf1974b68723.json` read-only receipt
verified the same launched original ready/open without restart or inference:
controller 23252, backend 24280, backend birth 134357508439272936. Its profile
hash remained unchanged. The companion binds all three receipts and keeps the
earlier failures distinct from this successful supplemental observation.

This report/companion were produced by source/receipt reads and fresh
standard-library CPU arithmetic only. No new model/runtime load, compiler,
hardware, WSL, lifecycle action, native hook, bridge/checker edit or Git action
was performed. The independent [external-history result](halogen-external-history-screen-20261006.md)
remains unchanged. A future snapshot mechanism needs its own exact control
qualification; this result supplies no approval to integrate the partial one.
