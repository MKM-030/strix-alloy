# Halogen 0.16.2 explicit accepted-prefix MTP replay

Source-only inspection establishes an explicit replay after the normal greedy
controller's accepted-prefix commit. Verification skips the target forward's
automatic head replay, but the controller subsequently calls a separate replay
helper. A replacement full head must process this call. No hardware or provider
was loaded for this investigation; existing instrumentation remains unchanged.

The pinned engine SHA256 is
`ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b`.
Evidence is the retained
`server/.local/optimization9h-20261004/mtp-route-static-20261004/host-text-disassembly.txt`.
Addresses below are RVAs in that same retained disassembly.

## Exact call and row contract

| Native instruction path | Established behavior |
|---|---|
| `0x173b710..0x173b724` | R13 counts matching drafts, `a`. |
| `0x173b732`, `0x173b924` | Accepted target input count is `k=a+1`; first mismatch uses `k=1`. |
| `0x173b741..0x173b759` | Stack `+0x30` receives matched drafts followed by target prediction/correction `model+0x20[a]`. |
| `0x173b764` | Calls target accepted-prefix helper `0x17def00(model,k)`. |
| `0x173b7ca`, `0x173b85b`, `0x173bb25` | Stores `k` at stack `+0x08`, then restores it into RDX for the replay path. |
| `0x173bb52..0x173bb5e` | RDI is the model, RSI is stack `+0x30`, EDX is `k`; calls helper `0x17dcc90`. |
| `0x17dccc4..0x17dcd06` | When a native carry snapshot has a valid tag and matching slot, copies 768 bytes into current layer48 carry and invalidates the saved position tag. |
| `0x17dcd0d..0x17dcd40` | Copies residual row `k-1` from `model+0x6d0` into accepted residual snapshot `model+0x50`; tags `model+0x58` with current target position. |
| `0x17dcd43..0x17dcd4f` | Calls full head `0x17db310(model, shifted_tokens, k, current_position-k)`. |
| `0x17dcd54..0x17dcd68` | Caches returned proposal at `+0x40`, last shifted input token at `+0x44`, and current target position at `+0x48`. |

If verification began at target position `P`, target commit sets current
position to `P+k`. Replay therefore has head position `P`, count `k`, target
residual inputs for `[current,draft1,...,draft_a]`, and shifted token inputs
`[draft1,...,draft_a,correction]`. The final target residual snapshot is the
last committed target input row. The correction/bonus token is an output of
this block and the last shifted input to its head replay.

Replay is eligible on the normal continuation path. EOS/output-stop paths can
exit before it. Adaptive speculation suppression at `0x173bb2c..0x173bb50`
disables `model+0x901`, invalidates the first-proposal cache and skips replay.
The helper itself refuses nonpositive count, MTP disabled at `+0x900`, or count
greater than `model+0x218`. This is not an unconditional call on every exit.
The main decoder has additional calls to the same helper at `0x172e058` and
`0x172e8f4`; those call sites require separate path qualification.

The runtime captures' 42 calls with count other than one are consistent with
bootstrap and accepted-prefix replay, but this static finding does not assign
each runtime call to a path. It supplies no runtime acceptance or timing.

## Minimal private full-head cache schedule

Keep the existing controller, target verification, target commit and output
authority. Replace only the complete head computation at `0x17db310` once a
real NPU head is qualified. Own a private contiguous history per model/slot/
reset epoch. Interpret every head call's `(position,count)` as replacement of
the private suffix starting at `position`, followed by `count` produced rows.
An unknown prefix is a hard integration failure, never a fabricated history.

For cached depth2 at base `P`, private history already includes the cached first
proposal's head row at `P-1`. Positive offset1 writes a speculative head row at
`P`. Native verification commits `k` target rows. Explicit replay rewinds private
history to prefix length `P`, restores its pool-boundary/carry checkpoint there,
then replaces rows `P..P+k-1` using accepted target residuals and shifted tokens.
Private history ends at `P+k`, and replay supplies the next cached first proposal.
An uncached scalar first proposal at position `P-1` must similarly rewrite that
row from a private checkpoint. This avoids equating accepted drafts with head
calls or importing unproved native FD slot ownership.

The [CPU schedule check](../../scripts/benchmarks/halogen0162_mtp_cache_schedule_check.py)
checks 24 synthetic scenarios: all four pool-boundary phases, zero/one/two
matched drafts, and cached/uncached first proposals. It checks rejected-suffix
discard, rebuilt pool/carry grouping, final private length and unknown-prefix
rejection. Its opaque row ledger is a design check; real K/V, indexer arithmetic,
pooling phase, cache/reset transactions and NPU numerical execution are absent.

## Features and cost still required

Full-head replacement must compute four-stream input transforms, token
embedding and projection, mixers/norms, indexed attention and rotary positions,
512-expert/top10 routing plus shared expert, final transform, and shared
248320-way vocabulary projection/argmax. The 31 extracted MTP tensors omit
the shared embedding/output matrices. A fresh whole-head provider contract and
same-v2 packed weights are required; fixed-expert replay is insufficient.
Raw four-stream residual numeric interpretation remains unproved in the current
state ABI receipt. Kind1 was observed only for eight selected scalar calls;
bootstrap/multirow kind and reset/slot transition qualification remain open.

Keeping the native wrapper requires input residuals from `model+0x6d0` and
publishing compatible continuation residuals into the same buffer, together
with `model+0x5c=count`. It also requires consistent first-proposal and logits
cache tags. A greedy-only replacement may invalidate incompatible logits tags,
but sampled execution needs compatible logits or an independently qualified
sampling contract. Returning only a token is insufficient for this boundary.

The count1 full-head bracket averages 3.32356 ms. A synchronous replacement
needs the complete NPU computation, HIP synchronization/copies, persistent
Windows host dispatch, transport, continuation publication and cache work to
fit below that approximate instrumented scope. It is not an exact
uninstrumented budget. Native MLP's separate 0.404612-ms bracket is narrower;
the qualified fixed-top10 NPU expert graph's 1.504985 ms already exceeds it
before transport and remaining MLP work. A wider head path can be investigated,
but has no established advantage.

At the full-head boundary, raw residual input plus continuation output is
40960 bytes per scalar row, plus token IDs/protocol metadata. An 8192-row
bootstrap needs 160 MiB residual input and 160 MiB continuation output,
excluding weights, copies inside the transport, scratch and protocol metadata.
The count1 timing excludes that bootstrap and other multirow calls. A
persistent Windows NPU host is required; WSL's HIP pointers cannot be presumed
importable by the Windows EP. Any CPU IPC qualification must separately bound
cross-WSL transport with these exact payload sizes. No such transport was built
or measured here.

Before promotion, root must establish real whole-head NPU placement and quality,
private history rewind on all acceptance cases and pool phases, reset/slot
invalidation, bootstrap and multirow correctness, compatible native publication,
and coherent handling of EP failure after private advancement. Falling back to
the original GPU head with stale native history is invalid; use a proven replay
or terminate the owned request before committing incompatible state. The
existing 22-GiB admission and continuous 18-GiB physical/commit reserves remain
requirements. Matched PP/decode/acceptance and complete cleanup then decide any
promotion. The explicit replay seam removes one ABI ambiguity; it does not
implement the NPU head or establish a speedup.
