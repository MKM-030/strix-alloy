# Finite native owner, seed, reset and no-hit capture path

**The smallest concrete mechanism is a default-off native observer adapter for one successfully constructed request, one actual queued record, one handler/thread and one model slot.** It assigns birth at successful construction, copies the exact native PLD vector after prefill, observes destructive/reset entries independently, and supplies the existing [outcome handoff](../../scripts/benchmarks/halogen_pld_nohit/native_outcome_handoff.h) and [no-hit consumer](../../scripts/benchmarks/halogen_pld_nohit/seam_contract.h) from the real saved native frame. Every unsupported transition can immediately retire the finite feed while native execution continues.

This audit identifies the required native boundaries. It does **not** yet justify setting `CallerTruth.ownership_qualified=true`: one queued record is observable, but exclusive ownership against the concrete worker jobs and their downstream aliases is not proved. A constructor nonce plus matching token/position does not establish reset exclusion either. The in-place reset/import map below supplies independently observable retirement events; those events must actually be connected, not replaced by a fixture qualification flag. No live observer/detour or transport is implemented by this document.

All addresses below are RVAs in the pinned stripped ELF. Function names describe inferred behavior, not exported APIs. The selected handler FDE is `0x171c260..0x17305ed`; its outer frame allocates `0x2648` bytes after saved registers. Handler entry saves the connection argument at outer `RSP+0x70` (`0x171c271`) and root object at outer `RSP+0` (`0x171c276`); the model is `**(outer RSP+0)`.

## Birth and exact seed

| Boundary | Concrete capture and identity rule |
|---|---|
| Constructor `0x1749d10..0x1749f31` | Entry has `RDI=request`, `RSI=model`, `EDX=current ID` and further parameter/context arguments. Both reviewed calls, `0x17202a9` and `0x172a422`, follow a `0x1f8` allocation. Record a pending construction under the current handler/thread cookie; entry alone is not birth. |
| Successful epilogue `0x1749f0b` | `RBX` still identifies the request; this is the normal epilogue after optional context/current append. Only here assign a fresh private session prefix plus monotonic birth counter, and publish the registry entry. The exceptional path at `0x1749f1c` destroys the PLD subobject and does not reach this success boundary. Never mint a nonce from a first-seen pointer, an existing address, a frontend ID or process lifetime. |
| Common destructor `0x17590c0..0x17591af` | Entry `RDI=request`: revoke owner/packet generations before native frees, including vector release at `0x1759138..0x175914e`. Encoded direct calls are `0x17202ca`, `0x17322ec`, `0x1734d8d`, `0x1749cef`. This covers the reviewed replacement and holder-cleanup release paths. |
| Replacement and holder movement | Direct replacement stores the new pointer at `0x17202ba`, then destroys the old object. Helper `0x1749ce0` also replaces/destroys. Holder move `0x1734d60..0x1735614` moves a request pointer and zeros the source; destination-old destruction is separate. The moved request retains its birth. Queue/holder relocation is not construction. |
| Single-record decode | At `0x172c21d`, outer `RSP+0x170/+0x178` bound queued records of stride `0x308`. `0x172c248..0x172c24e` requires exactly one record; request `record+0x10` must be nonnull and `(record+0x148-record+0x140)/4 <= record+0x158` must show prefill consumption complete (`0x172c254..0x172c278`). Otherwise retire/decline. Slot selection is `0x172c289`, with `ESI=int32(record+8)`. |
| Round snapshot `0x172d2f2` | `RBP=*(R15+0x10)` is the actual request, `R15` the actual queued record; outer `RSP+8` also holds that record. `Q` has just been stored at request `+0x1e0` (`0x172d2c4`). Snapshot before phase flag `+0x1e4` is cleared. Before the first seed, allow native phase completion and recheck at the gate; after seed, flag `1` retires the feed as prefill/phase reentry. |

Request fields needed by the adapter are model `+0xd8`, current ID `+0x15c`, cached native opening `+0x160`, PLD width `+0x170`, vector begin/end/capacity `+0x178/+0x180/+0x188`, sampler `+0x150`, PLD policy `+0xec`, proposal cap `+0xf0`, MTP policy `+0x104`, suppression `+0x1d0`, continuation suppression `+0x1dc`, constraint `+0x1e8` and phase flag `+0x1e4`.

For the first implementation, require the complete native vector to fit **512 IDs** and retire before a subsequent frontier exceeds that bound. Copy all IDs into preallocated owned storage, record the native position separately, and require the actual vector tail to equal current ID. Constructor bulk helper `0x17592a0` appends every supplied ID through `0x1759730`; its request `+0x100` limit bounds hash indexing, **not** vector truncation. Do not reconstruct missing prompt IDs from the shifted head trace or assume vector length equals target position. A last256 proposer window is an independent declared context policy.

Compute the prefix fingerprint outside the interior hook from the owned copy. Bind its acknowledgement to birth, epoch, generation and exact copied frontier. Until that acknowledgement matches the actual current vector/position, decline the seam; continuing stock outcomes still enter the owned outcome log. A digest acknowledges a copy, not exclusive ownership or absence of reset. The exact owned IDs remain available for bounded byte-for-byte checks. Loaded model/tokenizer fingerprints and `TokenDefinitions` must be independently bound to the actual selected model and tokenizer; hashing a pointer or trusting a producer label supplies neither.

## Observe in-place reset independently

The model address can survive context replacement. Keep private `native_epoch` and `model_slot_generation` distinct from birth, frontier/round IDs and the private drafter's epoch. Retire the active finite feed on the following entry observations for its model, before mutation, even when a reset later fails. Increment the appropriate generation; do not automatically reseed that birth.

| Native entry | Observed mutation and finite policy |
|---|---|
| Slot select `0x17e2e50..0x17e303e` | Compares `ESI` with model `+0xa0`. Same slot is a no-op; a changed slot saves old state through `0x1778c90`, imports a `0x138` slot record including native position at `0x17e2f87`, then changes `+0xa0` at `0x17e2fd5`. Table begin/end are model `+0x88/+0x90`. A changed slot retires before import; observe slot selection independently of request birth. |
| Reset `0x1779250..0x177962f` | Clears model `+0x220` as a QWORD at `0x1779426` and resets head/residual caches. Direct callers: `0x1729bcb`, `0x174a235`, `0x176f3c6`, `0x17e342e`, `0x17e38ee`. Same-address reset is real. |
| External import `0x17e1ea0..0x17e22f1` | Imports device state, writes position at `0x17e21d5`, invalidates caches; direct call `0x176793e`. |
| State copy/import `0x17e2ba0..0x17e2d2b` | Copies state buffers, writes position at `0x17e2c6e`, invalidates caches; direct calls `0x1767966`, `0x1769965`. |
| Slot-state restore `0x17e2d30..0x17e2e45` | Restores pointer table, position at `0x17e2dfb` and capacities. No encoded direct call was found; that does not exclude an indirect invocation. Observe the function entry. |
| Slot remap `0x17e3a60..0x17e3dfd` | Changes slot origin/extent (`0x17e3bd9..0x17e3be5`); active-slot reimport writes position at `0x17e3cf7`. Handler calls `0x1728621`, `0x17294dd`, `0x172b556`, `0x172be85`; helper calls `0x173836c`, `0x17387fc`. Conservatively retire on entry for this model, including a remap of another slot. |
| Batched slot forward/import `0x17e4b00..0x17e5433` | Restores active position at `0x17e5217`; handler call `0x172c885`. Retire on postseed entry. |

Expected scalar target forward (`0x177e4f0`, position store `0x177e588`) and accepted-prefix commit (`0x17def00`, store `0x17def32`) are outcome advancement, not reset. Full head `0x17db310` temporarily rewrites position at `0x17dbbad` and restores it at `0x17dbbe6`; blindly treating every position store as reset would retire normal replay. The reset observers above distinguish these operations. A focused scan found no explicit handler `RBP/RBX` writes to request vector pointers or model field, but that is not complete alias exclusion. `reset_excluded` remains false until the selected mode's complete mutation/entry coverage and actual installed observation are proved, including indirect invocation of restore.

Cancellation has concrete retirement entries too: queued removal `0x1731990` (call `0x171e665`), lone completion `0x17370b0` (call `0x171ec7c`), and prefill cancellation `0x1749140`. The narrow finite adapter may retire conservatively under its handler cookie at these entries without parsing a frontend ID. Actual successful releases additionally reach the common destructor. Failed completion need not release the native request; conservative private retirement is still valid.

## Actual no-hit allowance and all entries

At `0x172d357..0x172d38b`, with signed `P=int32(model+0x220)` and `Q=int32(request+0x1e0)`, native code computes:

```text
B = min(int32(model+0x14)-1, int32(request+0xf0),
        int32(model+0xf0)-P-1, Q-1)
```

`R9D` holds `B` after `0x172d387`. Independently recompute with wide signed arithmetic, decline overflow/out-of-range operands, and require equality with saved `R9D`. Policy `<=0`, nonnull sampler or nonzero suppression branch directly to `0x172d42b` at `0x172d336/0x172d344/0x172d351`; they do not enter this seam.

| Entry to no-hit `0x172d3bd` | Is saved `R9D` the computed B? | Admission |
|---|---|---|
| `0x172d38e jle`, `B<=0` | Yes | Decline. |
| `0x172d39a jle`, width `<=0` | Yes | Decline. |
| Fallthrough from `0x172d3b7` when unsigned `len-width` underflows | Yes | Insufficient context; decline. |
| `0x172dcd7 je`, null hash bucket | Yes | Candidate miss. |
| `0x172dcf9 jne`, bucket mismatch | Yes | Candidate miss. |
| `0x172dd0e je`, chain end | Yes | Candidate miss. |
| `0x172dd31 jmp`, 64-bit bucket mismatch | Yes | Candidate miss. |
| `0x172dda6 je`, no linear-hash node | Yes | Candidate miss. |
| `0x172ddc9 je`, continuation index equals context length | Yes | Candidate miss. |

The lookup miss paths do not write `R9D`. Hit-copy code at `0x172de10` uses it as a token temporary but joins `0x172e95f`; it does not return to `0x172d3bd`. Thus every reviewed entry can use independently checked B, including entries which must decline.

At the actual seam require positive policy/width, null sampler/constraint, zero suppression, actual vector length at least positive width, stable owner/slot/reset generations and exact current frontier. Count must fit `min(B,3)`. For the first feed also require `request+0x104!=0`, `request+0x1dc==0`, `P+2<=model+0xf0`, and actual enabled MTP flags `model+0x900/+0x901`, so the retained native opening equality gate remains in scope. Take request `RBP` and original outer `RSP` from the saved machine frame, never from packet fields. `SeamCapture` contains those local identities; its `CallerTruth` is formed only after the independent observations qualify them.

## Outcome capture and preservation pins

The adapter must observe outcomes whether a custom packet was consumed or the round used stock behavior. The [authoritative handoff design](halogen-pld-authoritative-handoff-design-20261006.md) explains preview versus seal; these are its concrete native inputs:

| Route | Preview and continuing seal |
|---|---|
| Outer PLD | Postcommit return `0x172d80f`: `RBP=request`, outer `+0x1980` contains `k=outer[+0x40]` IDs (`1..4`), `R15` native matched count, outer `+0x30` final ID. After full zero-result output loop and current store `0x172d8f1`, seal at `0x172d8f7`. Nonzero output callback branches to `0x172d943` and bypasses this seal; retire. |
| Nested controller | Postcommit `0x173b769`: `RBX=request`, controller `RSP+0x30` outputs, `R15=k` before later loop reuse. Current store `0x173b84e` also occurs on a partial stop, so it alone is insufficient. `0x173b884` tests callback EAX and branches terminal on nonzero; continuing observer `0x173b88c` follows only zero. Require exact `k` vector growth/tail and position. Suppression branch `0x173b87e→0x173b935` bypasses this boundary; retire it. Controller frame is not the outer frame. |
| Scalar | One-ID previews after selected-ID store and optional constraint validation, `0x172d515` / `0x172d745`. Output returns `0x172d57e` / `0x172d7ba` must have EAX zero and one exact append/current-ID equality. Continue only a mapped surviving branch; otherwise retain the owned outcome and retire. No acceptance count from an unused external proposal may be invented. |

Batched-prefill append `0x172cc97` sets phase flag `+0x1e4`; special append `0x172e683` is outside these three routes. Postseed entry retires. For every seal verify exact old vector plus the selected block, final current ID, native position and unchanged birth/epochs. Partial output, gaps, duplicate/out-of-order outcome events and budget exhaustion revoke all ready packets.

| Observer point | Pinned displaced instruction bytes | Reviewed direct incoming coverage |
|---|---|---|
| Constructor entry `0x1749d10` | `55 41 57 41 56` | Two constructor calls above. |
| Successful epilogue `0x1749f0b` | `48 83 c4 08 5b` | `0x1749ec6 jne`, or fallthrough after append. |
| Destructor entry `0x17590c0` | `41 57 41 56 53` | Four calls above. |
| Round snapshot `0x172d2f2` | `80 bd e4 01 00 00 01` | Sequential fallthrough; no encoded direct incoming edge. |
| No-hit `0x172d3bd` | `48 8d 85 e8 01 00 00` | Eight direct edges plus insuff-context fallthrough above; stock resume `0x172d3c4`, proposal join `0x172e95f`. |
| Outer preview `0x172d80f` / seal `0x172d8f7` | `f3 0f 6f 45 40` / `8b 85 dc 01 00 00` | Sequential fallthrough; no encoded direct incoming edges. |
| Controller preview `0x173b769` | `31 c0 45 85 ed` | Sequential fallthrough; no encoded direct incoming edge. |
| Controller test `0x173b884` | `85 c0 0f 85 df 02 00 00` | `0x173b860`, `0x173b86a`, `0x173b874`, or fallthrough after `0x173b87e`; EAX must still be checked. |

These byte/edge pins are observation descriptors, not installation qualification. Computed-entry exclusion, complete enabled extended-state preservation, original-frame addressing, unwind/signal behavior and atomic install/remove remain required. The synthetic saved frame/1024-byte extended-state array does not prove those properties.

## Handler, callbacks and the precise worker residual

Handler entry installs native callback data at model `+0x238/+0x240`, manager `0x1736da0` at `+0x248`, and prefill callback `0x1736aa0` at `+0x250` (`0x171c2c8..0x171c30b`). `0x17e6050` invokes the prefill callback at `0x17e615e`; that callback polls root commands through `0x1730890` at `0x1736ab7`. Retire on postseed prefill callback reentry. `0x1736da0` is the callback copy/release manager, not a decoder worker. Same-stack cancellation alone does not exclude this reentry.

Thread start `0x173eac3` does not run `0x1745706` (a one-byte `ret` linkage argument). Its `0x10` state has vtable `0x18d4fd8` and payload at `+8`; pinned ELF RELATIVE relocations resolve destructor `0x1745710` and run `0x1745730`. Run loads that payload and jumps to `0x1745740..0x1745fce`. The payload is a distinct `0x240` allocation (`0x173c2ae`, constructor `0x173dcb0`), not the request's `0x1f8` object. The worker uses mutex `+0xd8`, queue `+0x1c8..+0x1e8`, a stack-owned job at `RSP+0x88`, and calls job executor `0x1746300` at `0x1745a56` before job destruction `0x1746a20`. No indirect CALL was found inside the run span; downstream job callees still carry state pointers.

All encoded calls to thread start `0x18d3630` are `0x173eac3`, `0x176cb6a`, `0x17d7cd6`, `0x17d7dee`, `0x188dba7`, `0x188dc98`. Additional run slots resolve to `0x17ec240` (vtable `0x18d5bd0`, timed condition-wait shape), `0x1847cb0` (`0x18d7ec0`, parallel copies through native buffers and borrowed stack pointers), and `0x189b030` (`0x18d8648`, atomic work index and call `0x189b1a0`). These are actual worker entry evidence, not proof they cannot mutate the selected owner.

**The remaining serial-owner proof is specific:** trace creation/enqueue and downstream executor arguments for the `0x240` worker jobs to exclude selected request/vector/model-slot aliases, and establish that the other native parallel operations join or otherwise cease relevant mutation before each capture/consumer interval. Then close indirect aliases and exceptional/asynchronous destruction for this selected mode. Observed same handler/thread, one record and stable slot are necessary facts, not a substitute. Until that proof closes, `serial_owner`, `lifetime_held` and therefore `ownership_qualified` stay false; source fixtures cannot turn them on.

## One next source adapter

Implement a default-off `native_owner_capture` adapter alongside the existing component, with a preallocated registry for this one birth and finite64-round/512-ID budget. Its entry points should accept real saved-frame observations: pending constructor entry and exceptional abort; successful birth; destructor/retire; model reset/import/slot selection; round snapshot; the three distinct outcome-preview layouts; continuing/retiring seal; and no-hit capture. It should call `NativeOutcomeHandoff.initialize/adopt_round/preview/seal/retire/consume_at_seam`; it must not create another predictor protocol.

The handler is the exclusive caller of `NativeOutcomeHandoff` (the current class is not a concurrent queue). Cross-worker transport uses a separate preallocated immutable mailbox with release/acquire publication and generation ownership. Copy primitive values/IDs before publishing; never publish request, model, native vector, stack or device pointers. No hook allocates, waits, locks, reenters native serving or performs device work. An unread-slot collision retires instead of overwriting a missing outcome. A completion for an old birth/epoch/generation is discarded without touching the native object.

Keep observation provenance separate from `Qualification` assertions. Birth success establishes birth; proved-complete installed destructive/reset observers establish epoch coverage; exact copied full vector and mapped append/seal continuity establish the prefix; actual machine frame establishes caller identities and B; independently bounded tokenizer/model definitions establish IDs; completed worker exclusion establishes serialization/lifetime. Publish a ready packet only when private preparation and the exact continuing seal both exist. A late/unqualified packet immediately takes stock resume. Retirement is final for this finite birth; another attempt needs an explicitly fresh qualified capture, not address reuse or a first-seen pointer.

This is actionable source work while ownership proof continues. It neither qualifies live injection nor establishes readiness or serving gain. The user's standing measurement/lifecycle authorization remains valid; the remaining items are engineering proof and implementation work, not another permission request.

## Evidence and audit scope

| Locally rehashed retained evidence | SHA256 |
|---|---|
| `backends/halogen-wsl2-0.16.2/.local/flash_serve` (26,052,768 bytes) | `ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b` |
| `server/.local/optimization9h-20261004/mtp-route-static-20261004/host-text-disassembly.txt` (22,406,098 bytes) | `523467ac08e576e770a9fcffdb59ffa9542f82d58958bd03d74743f8caccb8f9` |
| Same directory `host-frames.txt` | `03b9bef6fd4182013dcec8ecb9c850dcc5c5ae474b57ecf2925934359115b923` |

ELF text RVA minus file offset is `0x1000`; data PT_LOAD difference is `0x2000`. Vtable method values above come from ELF relocation addends, not unrelocated zero file bytes. Prior [lifecycle ownership](halogen-npu-pld-lifecycle-ownership-20261005.md) and [native insertion scope](halogen-npu-native-pld-injection-scope-20261005.md) remain background evidence; this report supplies the new reset map and correct worker-run resolution.

Only this document was created. Work consisted of bounded local document/source/disassembly/frame/ELF-byte reads and hashing. No compiler, tests, runtime/model/hardware, WSL, serving request, engine/lifecycle action, production edit, stage or commit occurred.
