# Halogen MTP: smallest remaining action — 4 October 2026

No saved result establishes a new acceptance or speed gain. Under the present
source-only scope without new detours, the smallest untested native experiment is a
managed **prompt-lookup on/off ablation**, not another depth sweep or a new NPU
expert graph. Its bounded opt-in profile/launcher pass-through is now implemented;
hardware qualification remains a separate gate. This work performed no
model/provider/engine launch or binary change.

## Fixed comparison and already completed work

The latest direct stock PP8192/TG128 MTP cohort is **1584.5019 prefill / 47.0600
decode tok/s / 207 accepted of 345 proposed (60%)**, depth2, v2, one slot,
262144 capacity, cacheOff, greedy, thinkingOff. Its separate PP8192/TG1 serial
cohort is 1661.0181 tok/s. Sources: [published control](../benchmarks/halogen9h-optimization-20261004.md)
and retained `server/.local/optimization9h-20261004/stock8k-final-no-observer-1/{cold-analysis.json,backend-manifest.json}`.

* [0.16.2 screening](../benchmarks/halogen0162-upgrade-20261003.md) already
  measured depths1/3 at 512/2048/8192, chunks8192/16384/32768, keep-trunk,
  DN/attention/MoE controls, and cache policies. Later stock removed useful
  kernel/chunk advantages; incompatible-output candidates remain rejected.
* Later 32K greedy coding matrices also reject [depth1](../benchmarks/halogen0162-greedy-depth1-results-20261004/README.md)
  and [depth3](../benchmarks/halogen0162-greedy-depth-results-20261004/README.md)
  against warmed depth2 controls. Depth1 raises the accepted fraction while
  lowering speed. These are separate workloads from the 8K stock cohort.
* [Sampled dispatch](halogen-sampled-mtp-depth-20261004.md) proposes one token
  per round regardless of startup depth. The sampled lookup-placement and
  gather results therefore supply neither a depth sweep nor a prompt-lookup
  drafting ablation. The large n-gram lookup tensor supplies model features;
  moving it is distinct from prompt lookup proposing repeated context tokens.

## Best ordinary-source action

The [pinned supported flags](https://github.com/peonist-ai/halogen-flash-server/blob/7f31bbd4021f217a1be9776bdb7304bcf8eca62d/docs/FLAGS.md)
define `HALOGEN_PLD=3,3` by default and `0` to disable it. It proposes tokens
from earlier context for greedy requests while generating alone; the native
head must open the chain. Enabling the default is already stock behavior.
`K>3` exceeds the image's existing verification reservation.

The separate Halogen-specific opt-in accepts **only `0` or `3,3`** through
`server/draft_profiles.py` → `server/controller.py` → the 0.16.2 `Start.ps1` →
`scripts/service.py` manifest. Omission emits no override. The existing
`prompt_lookup` boolean belongs to GUFO and is explicitly refused for Halogen;
its meaning remains unchanged. `engine.speculation_policy` holds an object of
the two allowed environment keys; `--speculation-policy-json` creates the
isolated profile. For example, `{"HALOGEN_PLD":"0"}` disables only PLD, while
`{"HALOGEN_SPEC_ADAPT":"0"}` disables only adaptation. The launcher argument
is `-SpeculationPolicyJson` and the service CLI uses the same JSON flag.
The backend source-pin receipt includes the new validator and changed sources.
Four backend and two server checks pass: native manifest omission/exact
forwarding, bounded/duplicate JSON validation, actual PowerShell forwarding
and legacy refusal, profile copying, inherited-invalid and backend refusal.
The stock manifest differs only by explicitly selected policy environment
entries and their receipt. These offline checks establish no live speed gain.

No completed PLD policy ablation was found in the inspected research,
benchmark reports or stock manifest. This is a testable remaining candidate,
not evidence of likely gain. A prose answer with little copied context may
benefit from avoiding lookup overhead; copied code may instead benefit from
lookup. The next owned live comparison must retain the exact 8K stock request,
native MTP depth2 and verifier, then bookend `3,3` → `0` → `3,3`, one warmup
plus three measured repetitions per cell. Require unchanged prompt/request/
output hashes, generated counts/finish reasons, proposal/accept counts,
calibrated PP/decode and independent wall, ordinary cleanup/recovery, and
the existing reserve. Both stock bookends must support a useful wall/decode
gain before selection. If it fails, retain stock; no further grid follows
without evidence.

`HALOGEN_SPEC_ADAPT=32,0.35,64` is also already enabled by its native default;
the new interface permits exactly that string or `0`.
The [prior scout](halogen-update-gpu-scout-20261004.md) recommends an ablation
only after low-acceptance windows or unexpected serial fallback are observed.
Aggregate 60% acceptance does not prove either trigger. Changing selection of
drafted rounds can raise the fraction without improving draft quality.

## Separate route to actual candidate acceptance

The [complete-MLP publisher](halogen-mtp-quality-publication-source-20261004.md)
is the shortest prepared seam to propagate an explicit approximate candidate
through native attention/HC/vocabulary and target verification. It requires a
new runtime detour, outside this work's scope. Its native MLP
runs first, and publication replaces complete BF16[2560] routed-plus-shared
output; this diagnostic cannot prove speed. Eight Python wire checks establish
only packet behavior; the C shim is unbuilt. Remaining gates are warning-clean
C build; absent/stale/invalid and success/failure publication execution;
namespace/atomic transport qualification; real nonzero packed-QMoE output;
native selected-ID/coefficient semantics at the provider's 512-wide routing
interface; shared contribution and rounding; then matched greedy proposal,
accepted/proposed, final-output and native-verifier qualification. A responder
that returns the saved original is an IPC control, not an NPU quality result.

## Why full NPU MTP is a longer path

Native complete MLP averages .404612 ms; fixed-top10 NPU expert replay already
averages 1.504985 ms before shared/router work or transport. Its weights are
already initializer-backed, so removing per-call weight feeds is not a new
solution. [Resident-path audit](halogen-npu-resident-next-path-20261004.md).

The complete count1 native head averages 3.32356 ms, but excludes 42 multirow
calls. A complete replacement still needs the [full stage/weight plan](halogen-mtp-npu-full-head-plan-20261004.md),
strict NPU placement, shared embedding/vocabulary assets, qualified raw-u16
interpretation and native arithmetic mode, and real dynamic all-512/top10
execution. It also needs persistent transport/publication and private history
per model/slot/epoch with K/V, pooled keys/carry, continuation and cache tags.
Scalar residual input+output is 40960 bytes; an 8192-row bootstrap is 160 MiB each
way. No zero-copy import is established.

[Accepted-prefix replay](halogen-mtp-accepted-prefix-replay-20261004.md) now
establishes `k=a+1` target rows and replay `(P,k)` after commit, so private
history can rewind at P and append shifted accepted tokens/correction. The 24
synthetic schedule checks prove only that ledger. Real pooling/attention,
bootstrap/multirow, reset/slot change, skipped replay, logits invalidation and
failure recovery remain gates. The [state ABI](halogen-mtp-full-head-state-abi-20261004.md)
observes kind1 in eight scalar entries but does not prove FD ownership/lifetime
or native head rollback. Approximate proposals need not match internal FP32;
they still need valid state and native target verification. No smaller graph,
extra INT4 quantization or token-only sidecar removes these gates.
