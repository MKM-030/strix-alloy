# Recurrent snapshot resolution for the separate GPU drafter

One concrete new implementation seam exists: **save the separate Qwen3.5
drafter's recurrent state on its own device before drafting, restore it after
rejection, prune its attention suffix, and replay only authoritative outputs**.
This can replace the growing drafter's measured full-prefix rebuild operation.
It is an implementable component candidate, not a qualified Halogen feed or an
acceptance/speed improvement. The ready target was not touched.

The mechanism does not train a better predictor. A higher native acceptance
claim still needs a better held-out proposal result and usable native insertion
coverage. The present hit-only seam cannot consume it at any of the retained
exact-three opportunities, because there are none. No new full-engine cohort is
recommended from this audit.

## Why this is a distinct candidate

The [growing GPU screen](halogen-growing-gpu-proposer-screen-20261006.md)
already charges all fifteen correction operations. Nine used a complete
clear/prefill, averaging 33.859311 ms; six appended, averaging 4.716867 ms.
The initial seed and all corrections produce 34.279573 ms/round, exceeding its
generous 31.758897-ms cross-cohort rejection allowance. Merely retaining its
existing producer or consumer does not remove those nine rebuilds.

The current [bridge](../../scripts/benchmarks/halogen_llama_raw_id_bridge/bridge.cpp)
explicitly requests `n_rs_seq=0` at line 491. Its `propose()` makes two separate
scalar forwards for three IDs (lines 284–294); `commit()` rebuilds after a
rejected consumed ID (lines 305–326). It owns committed and speculative F32
rows separately. The new operation belongs immediately before that first
speculative forward and in the rejected-input resolution branch.

Use the already matched bundle at
`C:/AI/build/laurent-llamacpp-qwen4exp-rocmfpx`, commit
`3466b48806f9fefe1162aa4053ffebcfcabe83aa`. A direct read-only PE export parse
rechecked its 262 exports and found all four required names:
`llama_state_seq_get_size_ext`, `llama_state_seq_get_data_ext`,
`llama_state_seq_set_data_ext`, and `llama_memory_seq_rm`. The DLL SHA256 is
`ecca09d1880e55bc3c353e09ab3e6569ebf5f41bf5f4c8c6976305777408492e`.
Its existing matched header/import-library boundary applies; no DLL was loaded.

The pinned source supplies these operations:

| Source in that bundle | Relevant behavior |
|---|---|
| `include/llama.h:947–973` | `PARTIAL_ONLY=1` selects partial states; `ON_DEVICE=2` retains tensor payloads in backend buffers. Saving another state for the same sequence invalidates its previous device snapshot. |
| `src/llama-memory-hybrid.cpp:190–201` | Partial save/restore omits attention K/V and includes recurrent state. |
| `src/llama-memory-recurrent.cpp:843–844,897–957,992–1033` | Serialization includes recurrent metadata/position, convolution R and recurrent S tensors. Restore replaces the recurrent sequence metadata and tensor rows. |
| `src/llama-context.cpp:2735–2828,2867–2918` | Device snapshot storage uses the source tensors' backend buffer types and copies tensor views; restore copies those saved views back. It is not a host serialization of the complete attention prefix. |
| `src/llama-context.cpp:4172–4180` | Public get/set APIs synchronize before the operation. Synchronization and copies must be priced. |
| `src/llama-memory-hybrid.cpp:143–149` | Composite suffix removal tries recurrence first, then attention. Restore recurrence before suffix removal: its position is already `committed_length-1`, outside the removed interval. |

These are local source findings at the matched revision, also available in the
[pinned source tree](https://github.com/LaurentZuijdwijk/llama.cpp/tree/3466b48806f9fefe1162aa4053ffebcfcabe83aa).
They establish a concrete API path, not executed device-copy behavior.

## Bounded implementation and component probe

Retain the growing256-to512 policy, raw shared IDs, one sequence and existing
native opening restriction. Keep `n_rs_seq=0`. Add an explicitly selected,
default-off rejection-resolution mode to the separate bridge:

1. Before a proposal consumes an input, save sequence0 with flags
   `PARTIAL_ONLY | ON_DEVICE`. Own the returned metadata bytes, committed
   length, current row and context epoch. Save exactly once per pending round;
   count1 consumes no inputs and needs no snapshot.
2. If all consumed inputs become authoritative, use the existing append path
   and retire the snapshot. If consumed inputs are rejected, restore the saved
   partial state first, then call
   `llama_memory_seq_rm(memory, 0, committed_length, -1)`. Require the full
   restore byte count and successful removal. Check the resulting sequence
   position before forwarding any outputs.
3. Replay the complete authoritative accepted/correction/bonus sequence from
   that saved boundary, at consecutive positions. Own-copy the final F32 row.
   Retire the saved snapshot before another save, reset, rebase or exception.
   On any failed operation, clear/rebuild and account for its actual cost.
   Window eviction still rebuilds; the retained 37 outputs end at293, so this
   finite pilot has no eviction.

The useful root-owned probe is one finite **joint prediction and complete
resolution** pass of the same fifteen cases, not another append parity run or
a standalone snapshot timer. Charge every snapshot, restore, attention
removal, authoritative forward and fallback, including the final round. Keep
labels solely in the evaluator; they enter the drafter only as authoritative
resolution outputs after proposals are recorded. Record raw drafts, opening
reference equality, exact prefix lengths and complete elapsed costs.

For state correctness, compare the candidate's full F32 row after each
resolution against a control which starts with the identical256 prefill and
then consumes all authoritative outputs through the same scalar incremental
path, without speculative mutations. This avoids conflating restoration with
the already observed parallel-prefill/incremental discrepancy. Require exact
row equality for this state claim; do not relax any original native projection
tolerance. Control work belongs to verification cost, not the candidate's
resolution latency. Changing the proposer state path can change later drafts;
the prior19 opening-conditioned label matches cannot be carried forward.

The historical cost allowance is only an optimistic rejection screen. If the
old six append resolutions and proposal costs stayed unchanged, initial seed,
proposals and those six appends total209.4598 ms. The remaining allowance for
the whole fifteen-round component would be266.9237 ms for fifteen saves, nine
restores/removals, and nineteen authoritative scalar replays on the formerly
rebuilt rounds. Those operation counts are causal retained-data counts, not a
predicted latency or gain; new predictions may change resolution choices. No
copy latency, snapshot residency or contention was measured here.

Do not replace this mechanism with merely setting `n_rs_seq=2` and rewinding.
`models/delta-net-base.cpp:587–603` writes only
`min(n_seq_tokens, K)` recurrent snapshots; each current scalar call writes one.
Its convolution snapshot loop at497–520 similarly constructs states from the
current microbatch. This does not establish two-step rollback across the
bridge's two separate scalar calls. An explicit before-proposal snapshot
preserves the correct committed boundary without that assumption.

## Exactness, acceptance and device scope

Target arithmetic, weights and verification remain unchanged. The separate
drafter's snapshot is intended to reproduce its own incremental state; native
verification still owns committed IDs. This mechanism directly changes
resolution cost and consistency, with **no demonstrated improvement to draft
quality, native acceptance or target Prefill**.

GPU is the useful first realization because its measured proposal cost is the
best retained one and its rejection rebuild dominates this policy. Device
snapshot buffers add their own allocation/copy work and share GPU/DDR with the
target in any later integration. CPU can use the same matched APIs with CPU
buffer types, but its earlier proposal-plus-one-append cost already exceeds
the allowance; rollback alone supplies no reason to rerun CPU. The FLM NPU
engine has different checkpoint operations and unresolved stale-attention-row
semantics in its [checkpoint audit](halogen-npu-pld-raw-id-checkpoint-20261005.md).
It does not inherit this llama.cpp device snapshot proof, and its prior
proposal/append cost remains defeated.

Even a favorable GPU component result does not resolve the native seam:
`0x172e95f` remains hit-only and capped by stock count/three/native allowance,
and current raw-ID bridges inject nothing. A no-hit branch insertion, complete
native ownership qualification and matched complete target time per committed
token are still necessary before an integrated gain can be assessed. These
are missing implementation prerequisites, not a recommendation for another
diagnostic engine run.

## Additional causal exclusion: shorter prompt keys

A pure CPU pass independently checked the hash-verified shifted8192 seed and
all fifteen authoritative replay binaries, using only IDs committed before
each queried boundary. The [workload](halogen-independent-proposer-workload-20261006.json)
SHA256 is `1f3a2fbfafe1a8fd90f99c23dac49f3f0028644d5f010fcd057edfcce26a4919`.
It selected the latest earlier continuation of each exact short key and at
most three already-known IDs:

| Policy | Boundary hits | Exact first target ID | Native opening equality |
|---|---:|---:|---:|
| Exact2/latest | 2/15 | 0/2 | 0/2 |
| Exact1/latest | 5/15 | 0/5 | 0/5 |

Exact2 hit cases0/12, with8/1 occurrences. Exact1 hit cases0/2/6/12/14,
with8/55/4/116/429 occurrences. This is a policy simulation on one retained
family, not native eligibility or hash-collision observation. The shifted
seed omits the original first prompt ID. No favorable live result is inferred
from it. The [pinned supported flag description](https://raw.githubusercontent.com/peonist-ai/halogen-flash-server/7f31bbd4021f217a1be9776bdb7304bcf8eca62d/docs/FLAGS.md)
permits an N,K prompt lookup policy, while this repository's validator accepts
only off or stock3,3. There is no evidence here to extend that validator or run
a short-key hardware sweep.

## Read-only pins and scope

| File | SHA256 |
|---|---|
| Current raw-ID bridge | `4ca6ddba716a32aafbac37c4e73b6b9aad20dec1e29d06a7c34f382c0c3e2460` |
| Matched `include/llama.h` | `0518f73a23ad77192d278b5a5fadc3faea0765901830482111225d794d522581` |
| Matched `src/llama-context.cpp` | `daab90ea408491c7d0f4b6e029f81ec8fcf81a8a2577475b0a300136ee0468dd` |
| Matched `src/llama-memory-hybrid.cpp` | `b2b193c4a412a91b1fe15a3c239d3b2664b5208ff49d6dba244ff8fec0880f92` |
| Matched `src/llama-memory-recurrent.cpp` | `35903c832ba321aad3fca8b2adf2d481f6ba41196478c6c8f248ffe2bd7d9d51` |
| Matched `src/models/delta-net-base.cpp` | `5e3b318953f854b3825dd7cfe4b483ca7935cd5f6680438a3ece4be9b4d5428f` |
| Growing GPU evidence JSON | `5db42c600ea6701ffb906fe99857db53326cdb5100012a01378c54e60829d3ee` |

Only this new document was written. Local reads, finite standard-library CPU
simulation, PE parsing and one primary flag-page read were performed. No model
runtime import, compiler, engine request, hardware diagnostic, WSL action,
process mutation, source implementation, stage or commit occurred. Unrelated
untracked files were untouched.
