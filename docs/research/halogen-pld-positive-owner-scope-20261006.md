# Positive-allowance PLD owner and outcome scope

**The native queued-owner hold extends to custom-eligible `B>0`, `Q>1` rounds.** The custom join and native controller use the same held request/model; verification joins the identified host-copy workers and completes prediction readback before output selection. A concrete extension is therefore justified: host no-hit reads plus custom/controller preview and continuing-prefix seal observations. Accepted commit return does **not** establish device rollback completion. No observer, installer, runtime or hardware qualification was performed here.

This source-only audit uses the retained ELF, text and frames. The frozen [owner serialization report](halogen-pld-live-owner-serialization-20261006.md) supplies the queue/main hold and corrected callback interpretation; the [handoff design](halogen-pld-authoritative-handoff-design-20261006.md) supplies the outcome protocol. Their files remain unchanged.

## Positive admission

Use one actual queued request, completed prefill, stable selected slot and successful construction. Let `A=*(outer RSP+0)`, `M=*(A+0)`, `C=*(A+8)`, `R=R15`, `N=RBP=*(R+0x10)`. The synchronous handler retains these owners. Keep null sampler `N+0x150`, null constraint `N+0x1e8`, zero suppression `N+0x1d0/+0x1dc`, positive PLD policy/width and MTP policy, enabled `M+0x900/+0x901`, and the retained-opening capacity gate `P+2<=M+0xf0`. Require complete context and actual checked allowance:

```text
P=int32(M+0x220); Q=int32(N+0x1e0)
B=min(int32(M+0x14)-1, int32(N+0xf0), int32(M+0xf0)-P-1, Q-1)>0
```

Recompute with checked wide arithmetic and compare saved `R9D`; observe real native miss provenance. `Q>1` alone is insufficient. Packet count remains bounded by actual `B` and the existing consumer's maximum three IDs. Count two requires `B>=2`, hence `Q>=3`, and can contain the retained native opening plus one additional private ID. This is a concrete independently proposed continuation; it is not proof of acceptance or speedup. Count one remains eligible when its gates hold.

## The custom join and stock controller preserve the hold

| Route | Actual flow and observation |
|---|---|
| Custom join | `0x172e95f` reloads the constraint holder. Null takes `0x172ea19`, sets `R13D=EBX` and rejoins `0x172d3cc`. The retained opening comparison at `0x172d41e/0x172d425`, or after head call `0x172dd7b`, still applies; mismatch reaches stock `0x172d42b`. |
| Custom verify/commit | Outer `RSP+0x980` holds `[current, proposals...]`; `0x172d618` calls `0x17dcfc0`. Completed predictions at `M+0x20` determine `a` matches and `k=a+1`. Outer `RSP+0x1980` holds `[matched drafts, correction]`. Commit is `0x172d80a`; preview at return `0x172d80f` copies these `k` host IDs, never verifier inputs. |
| Custom seal/replay | Append/output calls are `0x172d8c8/0x172d8dc`. Only all-zero output results reach current-token store `0x172d8f1`; `0x172d8f7` is a seal candidate after exact native-vector extent/tail and current-ID checks. Stop/truncation at `0x172d943` retires the full preview. Normal continuation calls accepted head replay at `0x172e058`. |
| Stock controller | Unready/declined/opening-rejected proposals can reach synchronous controller call `0x172db61`. Its separate budget `N+0x108`, residual availability and clamped width must permit at least two drafts (`0x172dad1..0x172db39`). Controller frame `RSP+0x50` holds verifier inputs; verify is `0x173b6f6`. Frame `RSP+0x30` holds output IDs, `R15=k`; commit/preview are `0x173b764/0x173b769`. |
| Controller seal/replay | Appends/output are `0x173b825/0x173b838`. Current is stored at `0x173b84e`, even on partial output; that store alone is insufficient. Zero callback result at `0x173b884/0x173b886` reaches continuing seal candidate `0x173b88c`. Normal replay is `0x173bb5e`; suppression at `0x173bb2c` disables head replay and retires this scope. |

The controller's sole indirect call, constraint `+0x20` at `0x173b802`, is excluded by the null holder. Its reviewed complete FDE `0x173b630..0x173bb86` starts no host worker and releases no request owner. Its independent width can exceed three: require actual draft width `<=3` for the four-output handoff, or retire before that controller mutates. Scalar fallback can still occur during a positive round; capture the scalar outcomes already mapped in the handoff design, or retire before their target mutation. A missing stock outcome cannot leave the feed live. Scheduling and slot selection precede the next seam; there is no direct commit-to-no-hit jump.

## Worker, callback and backend completion

Verification wrapper `0x17dcfc0` sets `M[0]=1`, calls full target forward and clears it on return; verification bypasses automatic head replay. Forward's layer-index-one call `0x17dd721 -> 0x17d76b0` still runs for multiple inputs. Its normal return follows every copy-worker join at `0x17d8213`; refuse reads inside that active scope.

Handler installation at `0x171c28b..0x171c30b` sets callback data to `A` in `M+0x238`, manager `0x1736da0` at `+0x248`, and progress callable `0x1736aa0` at `+0x250`. Verification invokes this callable at `0x17dd7fc`; copy workers can invoke it before joining. Bind the actual installed pair/data, then require `A+0x130==0`: callback `0x1736ac6 -> 0x1736d10` returns after harmless control polling. Nonempty command dispatch at `0x171c696`, pending-holder publication, or loss of the known callable binding retires the interval.

Head backend `0x17d9eb0` retains `R14=M` at `0x17d9ec2`; its indirect call `0x17da289` uses `M+0x278`, guarded by `M+0x270`. Thus the previously established empty optional model hooks also exclude this additional head callback. Retain actual absent disk worker `C+0xe0` with startup provenance, completed construction timer, and no active/postseed indexed dispatcher, as required by the [worker audit](halogen-pld-native-worker-exclusion-20261006.md).

The ELF `.rela.plt` symbol indices and `.dynsym/.dynstr` names resolve these PLT/GOT pairs directly; no new disassembly was generated:

| PLT RVA | Relocation/GOT RVA | Imported symbol |
|---|---|---|
| `0x18d3710` | `0x18dab38` | `hipMemcpyAsync` |
| `0x18d3780` | `0x18dab70` | `hipMemcpy` |
| `0x18d3850` | `0x18dabd8` | `hipDeviceSynchronize` |
| `0x18d3870` | `0x18dabe8` | `hipGetLastError` |
| `0x18d3810` | `0x18dabb8` | `hipLaunchKernel` |
| `0x18d38f0` | `0x18dac28` | `__hipPushCallConfiguration` |

Forward explicitly synchronizes at `0x17dde45`, checks success, then verification takes checked `hipMemcpy` at `0x17ddef8`: source `M+0x738`, destination inline `M+0x20`, `count*4` bytes. These host predictions are complete before either comparison loop. Commit `0x17def00` advances host position at `0x17def32`, swaps target-layer pointers and enqueues residual/rejection copies and kernels. Its `0x17df272` call is **`hipGetLastError`, not synchronization**. Preview/seal therefore describe authoritative host IDs/prefix, not a completed tensor snapshot.

Accepted replay `0x17dcc90` restores carry/residual, calls full head with output IDs/count and position `P-k`, then updates opening cache. Full head temporarily writes position at `0x17dbbad`, restores it at `0x17dbbe6`, explicitly synchronizes at `0x17dc128`, and checks four-byte host readback at `0x17dc153` before normal return. These expected operations are not reset. Retain the independent reset/import/slot retirement map; never read inside forward, commit or replay and infer coherence from a matching position.

## Smallest installed extension and limits

Extend the engine-local `NativeReadBoundary` issuer of the existing [capture adapter](../../scripts/benchmarks/halogen_pld_nohit/native_owner_capture.h) to these positive gates. Issue scoped host spans only while the actual owner thread is paused at the seam, after relevant successful returns. Add outer-custom and nested-controller host preview/seal adapters with their distinct frames, and scalar advancement or prior retirement. Publish only immutable owned IDs/value bindings after complete copies; external preparation receives no request/model, stack, tensor or native-global pointers. Require prior complete-prefix acknowledgement and exact continuing seal before ready admission.

Additional unresolved aliases remain finite: nonnull pending holder, nonempty model hooks, enabled disk payload's borrowed model and indexed transformed destinations. Ordinary backend descendants of `0x17d9eb0`, `0x178cf90` and `0x17ccba0` still need a complete host-publication/destination audit. The latter two contain dispatch-table jumps; absence of indirect CALLs alone does not close their callees. Device waits neither supply host ownership nor qualify asynchronous driver behavior. Installed birth/release/reset/worker observations, real state/unwind preservation, trusted bindings and authenticated publication remain required. Source fixtures cannot set ownership qualification true.

CPU should perform bounded native copies, gates and outcome publication. The HIP target is GPU work; an independent GPU drafter could improve readiness but must pay transfer, snapshot/rollback, replay and contention costs. NPU production needs its own tokenizer/state/publication proof; no NPU result follows here. The useful metric is total target time per actually committed token, or committed tokens/second against stock native controller, including all private preparation and fallbacks. Capture alone with `packet=null` can add observation cost but cannot improve acceptance. All timing, acceptance and placement measurements remain unestablished.

## Evidence pins

Inputs were rehashed: ELF `ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b`, retained text `523467ac08e576e770a9fcffdb59ffa9542f82d58958bd03d74743f8caccb8f9`, frames `03b9bef6fd4182013dcec8ecb9c850dcc5c5ae474b57ecf2925934359115b923`. Their paths and frame conventions are pinned in the owner serialization report. Text bytes below were checked independently at ELF file offset `RVA-0x1000`.

| RVA | ELF bytes |
|---|---|
| `0x171c30b` | `48 89 91 50 02 00 00` |
| `0x172d618` | `e8 a3 f9 0a 00` |
| `0x172d80a` | `e8 f1 16 0b 00` |
| `0x172d80f` | `f3 0f 6f 45 40` |
| `0x172d8f1` | `89 85 5c 01 00 00` |
| `0x172d8f7` | `8b 85 dc 01 00 00` |
| `0x172e058` | `e8 33 ec 0a 00` |
| `0x172ea19` | `41 89 dd` |
| `0x173b6f6` | `e8 c5 18 0a 00` |
| `0x173b764` | `e8 97 37 0a 00` |
| `0x173b769` | `31 c0` |
| `0x173b88c` | `8b 83 e0 00 00 00` |
| `0x173bb5e` | `e8 2d 11 0a 00` |
| `0x17da289` | `41 ff 96 78 02 00 00` |
| `0x17dc128` | `e8 23 77 0f 00` |
| `0x17dc153` | `e8 28 76 0f 00` |
| `0x17dde45` | `e8 06 5a 0f 00` |
| `0x17dde4a` | `85 c0` |
| `0x17ddef8` | `e8 83 58 0f 00` |
| `0x17def32` | `89 87 20 02 00 00` |
| `0x17df272` | `e8 f9 45 0f 00` |
| `0x17df279` | `0f 85 b4 00 00 00` |
