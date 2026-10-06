# Native serialization of a live PLD owner

**The selected queued request has a concrete native hold: move ownership in the handler's local queue, beneath a synchronous main-to-handler call that keeps the model alive.** In the narrow CacheOff, one-request scalar route below, ordinary progress callbacks do not destroy that request or reset its model, and copy workers join before the outcome observers. This supports repeated stock scalar observations without retiring on every progress callback. It does not establish an installed, qualified live capture or custom acceptance.

This source-only report uses the retained ELF, disassembly and unwind frames. No compiler, test, runtime, WSL, hardware, process or server lifecycle action was used. It narrows the conservative callback interpretation in the frozen [owner audit](halogen-pld-native-owner-capture-path-20261006.md), [worker report](halogen-pld-native-worker-exclusion-20261006.md) and [connection report](halogen-pld-live-capture-connection-20261006.md); those files remain unchanged.

## The native object is held by the paused call stack

Let `A` be the aggregate saved at handler outer `RSP+0`, `M=*(A+0)` the model, `C=*(A+8)` the cache manager, `R` the selected `0x308` queue record and `N=*(R+0x10)` its `0x1f8` request. At the no-hit seam, native `RBP=N`, `R15=R` and outer `RSP+8=R`. The handler FDE is `0x171c260..0x17305ed`; its fixed allocation is `0x2648` bytes, and CFA is original outer `RSP+0x2680`. The queue descriptor is outer `RSP+0x170/+0x178/+0x180`.

Construction at `0x172024c..0x17202a9` allocates the request and calls `0x1749d10`. The pointer is temporarily held at outer `RSP+0x990`, then insertion `0x1734be0` receives the queue descriptor and transient record at `0x17202ec`. The second construction route similarly inserts at `0x172a44b` and destroys the transient record at `0x172a458`.

Insertion calls record move constructor `0x17331d0`: it loads source `+0x10` at `0x17331e1`, writes destination `+0x10` at `0x17331e5`, then **zeros source `+0x10` at `0x17331e9`**. Reallocation repeats that move for every record and only then destroys each moved-from record (`0x1734ca6/0x1734cae`). This is transferred ownership, not a second owning pointer. Move assignment also clears the source before replacing the destination; an old destination request is destroyed at `0x1734d8d` and freed. Record destruction loads its owned pointer at `0x17322e0`, invokes request destructor `0x17590c0` at `0x17322ec`, and frees `0x1f8` bytes. The request destructor frees its ordinary host PLD-vector allocation at `0x1759138..0x175914e`.

Queued removal `0x1731990` completes the selected record, shifts following records by move assignment and destroys the final record. Its seven encoded direct callers are inside the handler: `0x171e665`, `0x172cfce`, `0x172d069`, `0x172d0ee`, `0x172d16b`, `0x172d9c9`, `0x172e854`. All encoded direct request-destructor callers are construction replacement, record destruction, record move assignment or pointer replacement (`0x17202ca`, `0x17322ec`, `0x1734d8d`, `0x1749cef`). These native releases cannot execute concurrently on the paused owner thread.

The main accept loop constructs a stack connection, calls the handler synchronously at `0x171ba1a`, closes the connection only after return at `0x171ba21`, then loops. There is no handler-thread start in that loop. `M` is main's stack object at `main RSP+0x6d8`, constructed at `0x171a13f` and destroyed normally at `0x171bd06`. Main cannot reach that teardown while its handler call is paused. The installed signal-15 handler `0x1730880` only stores `1` to global `0x18db008` and returns; it performs no request release or model reset. Exceptional unwinding ends the current capture interval; it supplies no continuing outcome seal.

The hold is therefore the native ownership and call order. A private retirement flag adds no lifetime protection. This reasoning relies on the finite alias exclusions below; the encoded-call inventory is not a claim that arbitrary computed invocation is impossible.

## Progress callbacks and commands have different effects

The full polling FDE `0x1730890..0x17311fd` manages listener `A+0xa8` and FD vector `A+0xb0/+0xb8/+0xc0`, answers `PING` and `INFO`, and uses info text `A+0x20/+0x28`. It has no indirect call and no access to the serving-command vector `A+0x140/+0x148/+0x150`, selected queue descriptor or request destructor. Earlier descriptions of this poller as itself appending serving commands were too broad.

Progress callback `0x1736aa0` loads `A` from its callback data and polls at `0x1736ab7`. It then loads pending-prefill holder `A+0x130`; **null branches directly to return at `0x1736ac6 -> 0x1736d10`**. With this holder null, repeated progress callbacks neither parse serving commands nor mutate the selected request/model. Empty polling is not a destructive transition.

The nonnull pending path is different. It calls `0x1736dd0`, which updates that pending object's progress/time fields `+0x47c/+0x480` and prints; later guarded parsing at `0x1736b2e` can append serving commands and set model cancellation byte `M+0x258` at `0x1736d09/0x1736d37`. The narrow route excludes this pending holder rather than assuming a pending object cannot alias the selected record. Its full transfer/cancellation closure is not established here.

Parser FDE `0x1731200..0x173147a` reads the supplied connection and copies complete command lines into owned strings: allocation/copy at `0x1731306..0x1731349`, pointer move at `0x1731381`, vector-end advance at `0x1731408`. Its only encoded direct callers are handler `0x171c679`, handler `0x171f82f` and the guarded progress callback `0x1736b2e`.

Handler drain transfers `A+0x140/+0x148/+0x150` to outer `RSP+0x290/+0x298/+0x2a0`, exchanging the old descriptor back at `0x171c64d..0x171c665`. After parsing, both ordinary handler paths converge at `0x171c67e`. **Conditional branch `0x171c696` enters command handling at `0x171c77f` only when `R15 != local command end`.** A future finite adapter can retire immediately before that nonempty dispatch, before a command can replace/reset/cancel the owner, while retaining empty parses and control polls. This boundary deliberately declines even harmless serving commands until their effects are classified. It is more useful than retirement on every `0x1736aa0` entry and requires no change to native command behavior.

## Scalar forward has joined workers and empty optional hooks

Natural `Q=int32(N+0x1e0)==1` selects scalar fallback at `0x172d676/0x172d67a` when the capacity branch has not already selected it. Keep sampler `N+0x150` and constraint holder `N+0x1e8` null; this excludes sampling and constraint virtual calls. With zero suppression, forward receives input count `1` at `0x172d6d8/0x172d6dd`. Count one bypasses chunk callback `0x17e615e` in wrapper `0x17e6050` and tail-jumps to `0x17dd020` at `0x17e61a9`.

It does **not** bypass the copy helper. Forward stores input count in `R14D` at `0x17dd031`. `R13D` is instead the layer-loop index, zeroed at `0x17dd61f` and incremented toward `0x30`; the `R13D==1` branch reaches copy helper `0x17d76b0` at `0x17dd721`. That distinction corrects a tempting count-one interpretation. The worker report proves the helper's model-buffer writes and every normal-return join at `0x17d8213`. Its progress callbacks run before joins; the null pending holder above makes them harmless to this owner, but nested capture remains unsupported while the helper is active. Read only after actual successful return, never merely after a retirement notice.

Forward can also invoke optional hooks through `M+0x278` at `0x17dd564/0x17dd781/0x17dd89f`, and through `M+0x298` at `0x17dd70e`, guarded by holders `M+0x270` and `M+0x290`. Model construction binds `RBX=M`, zeros `XMM0` at `0x176b8af`, then zeros both holder/function pairs at `0x176ba3a` and `0x176ba2c`. No nonzero binding to these model pairs was found on the reviewed serving route. Apparent writes in configuration `0x1771337`, `0x177248d`, `0x177254d` concern a **layer object**: `L=*(M+0x4d8)+index*0xc68`, established at `0x1770f85..0x1770f97` and saved at that frame's `RSP+0x28`. They are tensor fields in `L`, not model hook installation.

The live route must bind those empty pairs to this actual successful construction and retain their null state. A nonzero pair leaves its callable and publication behavior unresolved and is outside this proof. The known worker scope additionally needs the actual absent disk holder `C+0xe0` with startup skip/join provenance, completed construction timer and no active/postseed indexed dispatch, as already demonstrated in the worker report. A frontend CacheOff label cannot substitute for those native facts.

Scalar selection/preview/append/output occurs after forward return: `0x172d711`, `0x172d745`, append `0x172d76d`, output `0x172d7b5`, outcome return `0x172d7ba`. Output FDE `0x173b430..0x173b621` builds an owned string and synchronously calls sender `0x1731480` at `0x173b46b`. Sender FDE `0x1731480..0x1731585` copies that string, loops over send at `0x173151e`, frees its own string and returns a result. Neither reviewed full FDE starts a worker, invokes a request destructor or dispatches serving commands. Output does update record counters/termination fields and calls `0x1734aa0`; these are stock owner-thread outcome effects, preceding the seal. Failure/termination can subsequently reach queued removal, whose entry retires the feed before release.

## Supported interval and remaining limits

The smallest supported CPU read interval is an actual one-record handler invocation, after completed prefill/forward worker scopes, with `A+0x130==0`, proven absent disk worker, empty optional model hooks, no active indexed work, null sampler/constraint, and natural scalar `Q==1`. The owner thread may pause at no-hit `0x172d3bd` and the scalar outcome observers: queue release, command dispatch and main teardown are all sequenced outside that pause. Across rounds, continuing stock seals and unchanged native identity keep the same hold; empty progress callbacks do not force a new birth. Nonempty serving-command dispatch at `0x171c696`, pending-holder publication or a native destructive/reset transition ends that finite interval.

This route can test a future repeated stock observation feed, but cannot demonstrate custom proposal selection: native allowance `B` includes `Q-1`, so `Q==1` makes `B<=0`. Scalar fallback selected by capacity exhaustion or positive suppression also lies outside the first custom-eligibility scope. No positive acceptance or serving-equality claim follows.

The unresolved aliases are specific: a nonnull pending-prefill `A+0x130`; nonempty callable holders `M+0x270/+0x290`; enabled disk payload's borrowed `M`; and the indexed executor's transformed destinations. They are excluded in this route, not proved safe when enabled. The large inference/backend chain following `0x17dd791 -> 0x17d9eb0` has not received a complete transitive publication audit against every external/driver callable; this report closes the identified native CPU ownership paths, not arbitrary external publication. Ordinary host request-vector storage is distinct from device tensors, so a device queue wait is not inferred as a host-object lifetime hold.

No observer was installed or live holder value read. Actual birth, construction, mode and successful-return observations, complete destructive/reset coverage, and a scoped native-copy installation are still absent. Therefore the existing source fixtures' `serial_owner`, `lifetime_held`, `reset_excluded` and `ownership_qualified` remain false. Device placement, latency, throughput and acceptance remain `null`.

## Evidence origins

All three inputs were rehashed for this report. Text RVA minus ELF file offset is `0x1000`; the following bytes were independently read from the ELF at that offset and matched to retained disassembly.

| Input | Bytes | SHA256 |
|---|---:|---|
| [ELF](../../backends/halogen-wsl2-0.16.2/.local/flash_serve) | 26,052,768 | `ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b` |
| [Text](../../server/.local/optimization9h-20261004/mtp-route-static-20261004/host-text-disassembly.txt) | 22,406,098 | `523467ac08e576e770a9fcffdb59ffa9542f82d58958bd03d74743f8caccb8f9` |
| [Frames](../../server/.local/optimization9h-20261004/mtp-route-static-20261004/host-frames.txt) | 3,177,351 | `03b9bef6fd4182013dcec8ecb9c850dcc5c5ae474b57ecf2925934359115b923` |

| RVA | ELF bytes | Meaning |
|---|---|---|
| `0x171ba1a` | `e8 41 08 00 00` | Synchronous handler call |
| `0x171bd06` | `e8 95 d9 05 00` | Main model destruction |
| `0x17331e9` | `48 c7 46 10 00 00 00 00` | Clear moved-from request owner |
| `0x17322ec` | `e8 cf 6d 02 00` | Record destroys its request |
| `0x1730880` | `c7 05 7e a7 1a 00 01 00 00 00` | Signal handler sets termination flag |
| `0x176ba2c` | `0f 11 83 90 02 00 00` | Empty model hook pair `+0x290/+0x298` |
| `0x176ba3a` | `0f 11 83 70 02 00 00` | Empty model hook pair `+0x270/+0x278` |
| `0x1736ac6` | `0f 84 44 02 00 00` | Null pending holder returns from callback |
| `0x1731349` | `e8 32 1d 1a 00` | Copy command bytes into owned string |
| `0x1731408` | `48 83 40 08 20` | Advance owned command vector |
| `0x171c65d` | `f3 0f 7f 87 40 01 00 00` | Exchange serving-command descriptor |
| `0x171c696` | `0f 85 e3 00 00 00` | Nonempty serving-command dispatch |
| `0x172d676` | `41 83 f8 01` | Natural `Q==1` scalar choice |
| `0x17e61a9` | `e9 72 6e ff ff` | Direct forward without chunk callback |
| `0x17dd61f` | `45 31 ed` | Layer index begins at zero |
| `0x17dd721` | `e8 8a 9f ff ff` | Layer-one copy helper |
| `0x17dd70e` | `ff 90 98 02 00 00` | Optional model hook `+0x298` |
| `0x17dd781` | `ff 90 78 02 00 00` | Optional model hook `+0x278` |
| `0x173b46b` | `e8 10 60 ff ff` | Synchronous owned output send |
| `0x173151e` | `e8 1d 1e 1a 00` | Sender's send loop |
