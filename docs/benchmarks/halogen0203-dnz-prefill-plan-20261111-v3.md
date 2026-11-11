# Halogen 0.20.3 DNZ: prospective paired2048-arena protocol

This is a new, finite test of the native auxiliary-stream Prefill projection,
with **both** private Prefill controls reduced from8192 to2048 in every arm.
The closed v1/v2 attempts never started a DNZ candidate. Their failed outcomes
are retained in the [attempt report](halogen0203-dnz-prefill-20261111.md).
An idle host-memory rebound alone does not justify repeating either attempt.

The changed mechanism is a smaller common working arena. The current upstream
entrypoint preflight estimate predicts a1.65-GiB reduction in its variable term. Prior
0.20.1 startup logs show5.8 versus4.0GiB working allocation for paired8192
and2048, but that is a different executable. Neither observation establishes
today's Windows physical-memory release. Actual0.20.3 startup and post-warmup
headroom must still pass the existing checks. No speed gain is assumed.

## Frozen comparison

| Setting | All private arms |
| --- | --- |
| Engine | Current0.20.3, exact executable pinned |
| Capacity | Context/pool8192, one implicit slot |
| Actual input |2048 contiguous natural novel-prefix tokens, no repetition/padding |
| Output |128 tokens, length finish required |
| Prefill chunk / max |2048 /2048 |
| Sampling |temperature0, seed1, ThinkingOff |
| Cache / Vision |Off /Off |
| Speculation |native MTP, gate0.90, PLD3,3 |
| Prefetch |0 |
| NPU/external consumer |Off |
| DN_Z_STREAM |before0 / candidate1 / after0 |

Request SHA256:
`d7ae756957ef499de88880aba9c6c89da076cad6bcad70d120c54431c7bc071b`.
Each arm has one excluded warmup and three measured requests. Do not append
an8192-input cohort to this8K-capacity protocol.

The configured2048 piece remains above the native DNZ default threshold1280;
actual projection M and loaded-descriptor eligibility remain unobserved.
Existing layout, packed-weight, BF16/scratch and stream/event guards remain
authoritative. Candidate first use can add159.5MiB scratch. The native use
counter must show0 submissions in both stock arms and positive submissions
in the candidate. Read it outside the timed HTTP interval. Source reachability
alone is not proof that the loaded model took the branch.

## Execution and restoration

Only Root runs hardware, after complete source review, focused fake CPU tests,
all execution dependency pins, current actual process/run identities and a
fresh single-engine/GPU/game check. Riot/League and other GPU contention must
satisfy the existing admission policy. No foreign programs are terminated.

Startup stays30GiB physical and131GiB commit; each request needs22/22GiB,
and runtime stays18/18GiB. The private ordinary-capacity v2 commit clamp stays
at least131GiB. On a reserve rejection retain the exact checked memory frame,
outside HTTP/RAW timing, and close the finite cohort rather than retry it.

The existing normal32K, paired8192 server on8840 is restored in all outcomes.
Before its one ordinary launch, an outer check waits for actual30.25/131GiB
stable for10seconds, at most300seconds, while retaining18/18GiB runtime.
This supplements the known restoration race; it does not lower or replace
the ordinary service30/131GiB check. Observe live lifecycle handles through
timeouts. Only authoritative terminal state permits recovery action.

## Qualification

Retain every actual input/output count, exact output/finish/scoped-counter
parity, current checkpoint/file identities, startup allocation, original
HTTPQPC intervals, native RAW phase brackets, counter applicability and resource
evidence. A complete cohort requires all12 requests. Warmups are excluded from
the3-per-arm means and ranges. Independently check bookend drift, paired
output parity and phase timing before claiming any causal change. Native
output-ID reconstruction and independently reconstructed neural acceptance
remain separate limitations of the retained observer.

Partial arms, an unexercised candidate or a functional READY reply are not
new performance values. No outcome is registered yet. A useful qualified
result can justify a subsequent deployment decision; default serving remains
unchanged until then. The full GPU/NPU/CPU acceleration goal remains open.
