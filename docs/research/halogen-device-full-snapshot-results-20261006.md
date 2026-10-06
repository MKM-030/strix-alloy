# Full device snapshot: executed exact-state result

**The full ON_DEVICE snapshot passed exact state qualification for this finite
GPU workload.** Independent retained-row reads found an identical initial row
and all 15 identical post-resolution F32 rows. The candidate remains default off;
native acceptance, useful prediction gain, target contention, and serving speed
are unmeasured. The broader Halogen acceleration goal remains unachieved.

## What actually ran

The completed work directory is
`C:/Projects/strix-alloy-clean/server/.local/optimization9h-20261004/full-snapshot-gpu-component-d07bf4b747224116b00dd6e1c55a3a62`;
the plan uses the same UUID and SHA-256
`53256d228ed125f12ad0944247d33b405a82f5a8ca860f000e52faff673286ef`.
This is one completed full-mode screen, distinct from the earlier partial
candidate and the failed preflight described below.

The matched llama.cpp revision is
`3466b48806f9fefe1162aa4053ffebcfcabe83aa`. The runtime bridge source pin is
`8fce4c04b2eeea73f354ee2591c765bfaf610e789b1275883b5d21e7de0515aa`;
the built executable pin is
`4820a137a7bb840130b1c47bc4b5a752d3d6d59769e4f6ae460c59376f8fc984`.
The separate `Qwen3.5-0.8B-Q4_0.gguf` retains SHA-256
`57d1997790d1744fba5b40a7317df71ea5e2acee28c47e78f0cce39c0703f8cf`.
The [JSON companion](halogen-device-full-snapshot-results-20261006.json)
preserves the retained plan's complete source/runtime pins, freshly hashed
artifacts, and fresh per-round arithmetic.

The AMD Radeon 8060S Vulkan candidate used one sequence, a 512-ID window policy,
a 1024-token engine context, and four CPU threads. One warmup iteration,
comprising three commands, was excluded on each side. The measured candidate
paid a 256-ID seed, 15 three-ID proposals, and all 15 resolutions. It applied
all 37 authoritative IDs and ended at committed length 293. The snapshot-off
control used the identical 256 prefill followed by 37 consecutive scalar
authoritative forwards. There were 34 candidate and 41 control commands.

The full candidate selected `ON_DEVICE` alone, flags `2`, with no PARTIAL_ONLY
bit. It performed 15 before-proposal saves, nine private attention/recurrent
clears followed by nine full restores, six append resolutions, 30 speculative
scalar calls, and 25 authoritative scalar replay calls. Save/restore receipts
bind sequence 0, saved epoch, committed length, metadata bytes, and restored
position. No measured save failure, restore fallback, or full-prefix rebuild
occurred. Host metadata ranged from 6,764 to 7,604 bytes; device tensor payload
size was not measured. The frozen
[source review](../../scripts/benchmarks/halogen_llama_raw_id_bridge/FULL_SNAPSHOT_REVIEW.md)
remains unchanged.

## Exactness and freshly computed label counts

Independent standard-library CPU reads compared all 993,280 bytes and all
248,320 F32 words per row against the scalar control at the same committed
length. The initial row and every resolution were byte-identical. Total full
and shared-vocabulary word mismatches were zero, and the maximum absolute
difference was zero. Committed ID histories matched throughout; greedy IDs
recomputed from supported rows also matched all 15 control rows. No tolerance
was introduced.

The evaluator freshly scanned actual proposal IDs against each workload case's
`expected_next_ids`, stopping at the first mismatch. It separately compared the
first draft with `native_cached_first_id`.

| Offline statistic, one retained family | Actual result |
| --- | ---: |
| Leading exact-prefix label matches | 22/44 |
| Leading prefix lengths by round | 0, 0, 1, 2, 3, 1, 0, 2, 2, 3, 1, 1, 3, 3, 0 |
| First ID equals next target label | 11/15 |
| First ID equals retained native opening reference | 10/15 |
| Leading matches in opening-equal rounds | 19 |

There were 45 predictions and 44 retained label positions; the final third ID
is unscored. Exact memory-state parity establishes this finite rollback result.
These offline labels do not measure native hit eligibility, actual opening
execution, accepted drafts, verification/replay cost, readiness, or target
contention. No useful improvement over retained stock drafts is established.

## Offline ensemble coverage from these observed inputs

For each case, an optimistic oracle takes the maximum of the independent
observed leading-prefix length and the retained `stock_accepted_draft_count`,
clipping both to available label positions. Stock contributes 22/44 positions;
the oracle union contributes 28/44, adding six labels in rounds 4, 9, 12, and 13.
When the small proposal is eligible only if its first ID equals
`native_cached_first_id`, the combined maximum is 25/44, adding three labels in
rounds 4, 9, and 13.

| Round | Stock prefix | Independent prefix | Opening equal | Oracle added labels | Opening-constrained added labels |
| --- | ---: | ---: | --- | ---: | ---: |
| 4 | 2 | 3 | Yes | 1 | 1 |
| 9 | 2 | 3 | Yes | 1 | 1 |
| 12 | 0 | 3 | No | 3 | 0 |
| 13 | 2 | 3 | Yes | 1 | 1 |

The retained native head differs from the next authoritative label in rounds
0, 6, and 12. The independent first ID rescues one of those three cases: round
12 predicts target ID 17739 while the retained native opening reference is
7963. Its three-label contribution is excluded by the opening constraint.

This establishes complementary observed coverage within the unchanged 15-case,
one-family, 44-label sample. The oracle uses hindsight to choose the better
prefix; it is not a usable router or measured native acceptance. Verification,
opening behavior, readiness, placement, target contention, and the cost of any
combined execution remain unmeasured. No serving rate is inferred.

## Complete measured costs

| Recorded candidate operation | Milliseconds |
| --- | ---: |
| Initial 256 prefill | 31.8703 |
| All 15 proposals, including saves | 204.0217 |
| All 15 complete resolutions | 154.9398 |
| Proposal mean, including save | 13.60145 |
| Complete resolution mean | 10.32932 |
| Restore-resolution mean, nine rounds | 13.98428 |
| Append-resolution mean, six rounds | 4.84688 |
| Save mean, already included in proposal | 4.61052 |
| Private clear mean, already included in resolution | 1.45657 |
| Restore mean, already included in resolution | 3.13696 |
| Seed plus all proposals/resolutions | 390.8318 |
| Seed-amortized core per round | 26.05545 |

Fresh arithmetic reproduced the qualifier's totals. Recorded native component
durations fit their command wall times. Successful clear and restore timers
are separate; native durations are not added again to command wall time.

Diagnostic row writes took 37.0657 ms for the measured seed and rounds, or
46.8504 ms across all candidate commands, and are excluded from command timers.
Excluded candidate warmup commands took 1253.8696 ms. Runtime elapsed before
manifest writing was 2381.5316 ms candidate and 989.1604 ms control; the owned
component-process receipt records 5.188 s. Control cost is verification overhead.
These component measurements do not establish a historical paired improvement,
target prefill/decode tok/s, native acceptance, or serving gain.

## Distinct preflight and lifecycle receipts

The earlier UUID `688352fec0794b39b869b06aadbae621` retains its own plan,
preparation, commands, and failed coordinator receipt. That receipt reports
`screen_passed: false`, `normal_stop_proven: false`, and
`original_ready_open: true`; no component result or candidate output exists for
it. The parent identified a wrong Python environment before the normal stop.
This preflight failure is separate from the completed full-mode measurement.

The completed full component exited 0, passed the state/cost qualifier, closed
its owned job, and reports no pending component cleanup. Its separate
coordinator receipt passed, proves the normal stop, and reports original
ready/open restoration after 338.656 s. The normal restoration `result.json`,
`final-ready.json`, and the subsequent
`supplemental-ready-4c9565d179fd4a5bb369e26102dd174b.json` are retained under
`full-snapshot-gpu-held-restoration-1e3f488aba5c48de943b338eafce5f56` and hashed
in the companion.

Those receipts identify controller 2172, birth 134357523143840310, run
`8c9c658dd57649b694322011d7f3581b`, and backend 25932, birth
134357523252585985, run `d77cc8e645b64ccf8afbb989e8ea022b`. Health is `ok`,
draining is false, and the original profile hash is unchanged. The restoration
owned WSL job closed with no recovery pending; the restored normal persistent
controller/backend remain ready. The supplemental receipt adopted the same
launched controller and performed no restart or inference. This readiness
conclusion comes from the final receipts; the first preflight's separate
terminal failure remains intact.

The earlier [partial result](halogen-device-partial-snapshot-results-20261006.md)
remains a failed exact-state candidate. The full pass does not establish the
cause of its discrepancy. The
[external-history result](halogen-external-history-screen-20261006.md) is also
unchanged. This report and companion used fresh standard-library CPU arithmetic
and retained source/receipt/F32 reads only, with no new model/runtime load,
compiler, hardware, WSL, lifecycle action, native hook, bridge/checker/review edit,
or Git action.
