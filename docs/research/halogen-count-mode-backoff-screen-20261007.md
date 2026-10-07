# Count-mode backoff: retire the fixed hybrid policy

One bounded causal CPU screen produced **no continuation IDs in any of the 15
retained rounds**. Retire this fixed policy for the retained request family.
It adds no useful leading-label coverage and supplies no reason for native
integration, another gate run or an engine cohort. No native acceptance,
Prefill, Decode or serving gain was measured.

The full private [receipt](../../server/.local/optimization9h-20261004/next-mechanism-20261007/count-mode-backoff-proposal.json)
is 41,647 bytes, SHA256
`8f03b75199f8727d11b7d3e2ada78c8b16e89ca27d60212a8a997f0f02770f7c`.
Publication rechecked that receipt, the workload hash, all 17
seed/trace/replay pins, every causal prefix hash, native opening ID,
authoritative update, result count and retained cost arithmetic. It did not
rerun the predictor or timings.

The screen ran as an inline Python body through native PowerShell 5.1 and
Python 3.13 with `-I -c`. That exact body and the separately executed
receipt-finalization body were recovered from the tool calls and saved after
the pass. These are retrospective source pins; the receipt remains unchanged.
The finalizer added stock-fallback summaries and the retirement decision from
the recorded cases without running the predictor.

| Recovered executed body | SHA256 |
|---|---|
| [Screen, 9,599 bytes](../../server/.local/optimization9h-20261004/next-mechanism-20261007/count_mode_backoff_screen.py) | `fc4e3e71e6f569dad879beee81d96f459bf384fec6ce1b580c9ac22cc51006f6` |
| [Receipt finalizer, 1,740 bytes](../../server/.local/optimization9h-20261004/next-mechanism-20261007/count_mode_backoff_receipt_finalize.py) | `5ce78a14ae6ab52a6bbbc749457330b810758e2e1b3b6d3801d3fcc747278892` |

## Executed policy and causal inputs

The executed policy used **maximum conditioning order 3**, at least two
observations for a conditional distribution, a modal fraction of at least
0.5, and the lowest raw ID on a count tie. It examined the longest qualifying
suffix first and backed off through shorter suffixes, with no unigram
fallback. Total chain length was capped at three IDs. The earlier maximum-order
2 sketch was not executed; the actual order-3 constants were frozen before
evaluation, without a parameter or strategy search.

The first chain ID was the retained **native cached MTP opening ID**. The CPU
policy could propose at most two following IDs. This was a hybrid native/CPU
chain: the first ID depended on existing native head work and was not an
independent prediction or a target oracle. Its equality with the opening
reference was automatic because it used that same retained native ID.

The index contained only the available 8,192-ID shifted seed and outputs
already committed at each round. A pending chain extended the query suffix but
never entered the index. Each complete proposal was recorded before that
round's authoritative outputs updated the index; all 15 proposals were frozen
before evaluator-only future labels were scored. The missing original first
prompt ID was never guessed. There were 37 authoritative updates, ending at
8,229 known IDs, in one retained request family.

The [workload](halogen-independent-proposer-workload-20261006.json) SHA256 is
`1f3a2fbfafe1a8fd90f99c23dac49f3f0028644d5f010fcd057edfcce26a4919`.
Its seed SHA256 is
`dc1b73cc84046ca0fe0ed09520540eed9c06e2682fbd23eeff7077209f7ee31b`.

## Result and complete CPU scope

| Retained reconstruction | Result |
|---|---:|
| Cases with any CPU continuation ID | 0/15 |
| Complete three-ID proposals | 0/15 |
| New useful leading IDs | None |
| Native opening IDs matching the next label | 12/15 |
| Seed-only chain leading-label matches | 12 |
| Stock leading-label matches | 22 across 44 retained labels |
| Keep stock whenever mode backoff declines | 22; zero added coverage |

The 12 seed-only matches belong to the native first ID. They are not CPU
predictor accuracy or native acceptance. Replacing the stock chain with those
single-ID chains would lose ten retained leading matches; falling back to
stock preserves the existing 22 while adding CPU work. No later leading ID
was proposed, so there is no continuation-candidate acceptance denominator.
Actual native allowance, hit, readiness and consumer eligibility remain null.

| One un-warmed CPU pass | Total ms |
|---|---:|
| Initial index build | 7.9084 |
| All 15 queries | 1.0629 |
| All 37 authoritative index updates | 0.0492 |
| Index + queries + updates | 9.0205; 0.60137 per round |
| Full replay including prefix hashes and receipt bookkeeping | 11.8178; 0.78785 per round |

These are retained `time.perf_counter_ns` wall measurements. Fixture I/O/hash
verification, evaluator rescoring and JSON output are excluded. Native head,
transport/authentication, live ownership, target verification/replay and
contention costs were not measured. The small single pass is not a serving
benchmark or a universal timing bound.

CPU performed the count indexing. GPU retained the native first-head and
target-verification roles; neither was executed here. NPU was not invoked and
supplies no demonstrated advantage for this token-indexing policy. The
[source consumer](halogen-pld-nohit-live-gap-20261007.md) accepts at most
`min(3,B)` IDs through the native verifier, but its installed relay still
follows stock. This failed quality screen does not justify closing that live
integration gap.

Only the private receipt, recovered source bodies and this requested report
were written. No model, provider, engine, hardware, hook, lifecycle or runtime
configuration changed.
