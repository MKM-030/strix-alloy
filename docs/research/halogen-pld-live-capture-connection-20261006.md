# One native no-hit observation connected to the owned decoder and handoff

**The smallest useful source change is an engine-local `native_owner_capture.h/.cpp` adapter with fixed owned storage, called from a separately scoped native-copy boundary.** It copies one actual invocation at `0x172d3bd`, calls the existing `capture::decode_nohit`, and supplies the existing `NativeOutcomeHandoff` with a current frontier and `packet=null`. The first connected mode remains stock-only: the existing relay restores state, replays `LEA RAX,[RBP+0x1e8]`, and resumes `0x172d3c4`. This report specifies that connection; it does not implement or qualify it.

There is a present API restriction: [the relay header](../../scripts/benchmarks/halogen_pld_nohit/native_frame_relay.h) supplies only real registers/XSAVE and expressly limits `halogen_nohit_frame_observer` to the owned image/view. [Its documentation](../../scripts/benchmarks/halogen_pld_nohit/FRAME_RELAY.md) forbids native-object dereferences. Following RBP/R15/RSP inside that callback would exceed the current contract. A native-copy adapter therefore needs an explicit, reviewed engine read boundary before it supplies immutable copies to the unchanged decoder. Merely defining the unresolved observer symbol cannot establish this connection.

## Concrete copy and existing API sequence

At the pinned no-hit instruction, original outer RSP has body CFA `RSP+0x2680`; live RBP is the request and R15 is the queued record. Register capture must come from the real invocation, not `SavedFrame` fixtures. The adapter keeps all native addresses and copy descriptors inside the engine. Cross-worker publication carries owned IDs and value identities only.

Preallocate one copy slot holding request `0x1f8`, model `0x902`, record `0x308`, outer `0x180` bytes, and at most 512 suffix IDs, plus the real GPR/ordinary-flags projection and origin metadata. Those object/suffix bytes total 6,018 bytes before metadata. Do not allocate these objects on each hook entry or store real machine state in the synthetic 1,024-byte extended-state field. The invocation's real XSAVE image remains the relay's restoration source.

1. Before this invocation, establish one successful request birth, exact full-vector seed, model/tokenizer binding, independent reset/slot generations and the worker/lifetime exclusions below. Copy the complete native vector into separately preallocated seed storage. The decoder permits a native vector length up to 262,144 IDs, but checks only its exact last `min(length,512)` IDs; it does **not** copy or fingerprint the omitted prefix.
2. Compute the full-prefix fingerprint outside the interior hook. Return an acknowledgement bound to birth, epoch, owner/slot generation, native position and the exact copied frontier. That acknowledgement must already match before this seam. If it is absent or late, keep stock execution; do not wait, hash inside the seam, initialize with placeholder qualification, or qualify the elapsed invocation after its return.
3. Under the proved native read lifetime, copy request/model/record/outer and actual suffix bytes into the owned slot. The decoder consumes these immutable spans synchronously. The new copier is the only part that reads native memory; `decode_nohit` remains pointer-free. Do not publish `ObjectCopy.native_origin`, native GPR pointer values or native-stack views to a proposer.
4. On `DecodeResult::Captured`, combine `NoHitFacts` with the **independently observed** owner and acknowledged full-prefix binding. Populate `Frontier` and `SeamCapture`. Call `initialize(true, SeedCopy)` only for an actually qualified first seed, then `adopt_round` with the exact current frontier; otherwise require the already sealed matching reservation. The same handler exclusively owns these handoff calls.
5. Project real GPRs and flags into local `SavedFrame` for `consume_at_seam(capture, nullptr, projected)`. Keep its opaque extended-state field separate from real XSAVE. With no packet, record the stock decision; the relay performs its own displaced LEA and stock continuation. No proposal bytes, saved RBX or success join are applied in this first observing mode.

If native qualification is incomplete, the new adapter may still retain an owned observation and decoded facts for inspection. It must not turn those facts into a qualified handoff seed. `initialize(true, unqualified_seed)` currently retires permanently; it is not a pending-seed API. `NoHitFacts` has no ownership, epoch, authentication or fingerprint fields, and intentionally cannot manufacture them.

## Proof sources for the copied fields

| Fact supplied to decoder/handoff | Actual source |
|---|---|
| Request, outer and record identities | Real saved `RBP`, original `RSP`, `R15`. Request model `+0xd8` must equal copied model origin. Outer `+8` and record `+0x10` must identify this record/request. |
| One record and completed prefill | Outer queued begin/end `+0x170/+0x178` span exactly `0x308`; record prefill begin/end `+0x140/+0x148`, consumed count `+0x158`. |
| Full length and actual suffix | Request begin/end/capacity `+0x178/+0x180/+0x188`; copy from `end-4*min(length,512)`. Suffix tail equals current ID at request `+0x15c`; native position is independently model `+0x220`. |
| Slot and phase | Record `+8` equals model `+0xa0`; request phase `+0x1e4` is zero at the seam. Postseed phase/prefill reentry retires. |
| Actual allowance B | `min(model+0x14-1, request+0xf0, model+0xf0-P-1, request+0x1e0-1)` with checked signed32 operands; must equal saved R9D. |
| Native gate observations | Request policy `+0xec`, sampler `+0x150`, suppression `+0x1d0`, width `+0x170`, constraint `+0x1e8`. Opening scope uses request `+0x104/+0x1dc`, model capacity and flags `+0x900/+0x901`. |
| Owner and complete prefix | Successful construction observation at `0x1749f0b`, private birth/session counter, observed epoch/generations, trusted loaded model/tokenizer fingerprints and token definitions, exact owned full-vector seed plus prior acknowledgement. None comes from packet fields or address hashing. |

These are implemented decoder checks in [native_capture_layout.cpp](../../scripts/benchmarks/halogen_pld_nohit/native_capture_layout.cpp). The handoff's six `Qualification` members remain assertions about independently established evidence. Its [implementation](../../scripts/benchmarks/halogen_pld_nohit/native_outcome_handoff.cpp) requires all six for initialization, adoption and seam admission. A matching suffix, digest or pointer identity does not supply missing lifetime or reset exclusion.

## Native lifetime, reset and worker interval

The [owner audit](halogen-pld-native-owner-capture-path-20261006.md) supplies exact entry/byte/frame pins. Register pending construction at `0x1749d10`; publish birth only at successful `0x1749f0b`. Destructor `0x17590c0`, replacement/holder release, queued removal `0x1731990`, completion `0x17370b0` and prefill cancellation `0x1749140` revoke this feed before native release. Observe reset/import entries `0x1779250`, `0x17e1ea0`, `0x17e2ba0`, `0x17e2d30`, slot remap `0x17e3a60`, changed slot select `0x17e2e50`, and postseed batched import `0x17e4b00`. Expected scalar/accepted-prefix position advancement is a distinct outcome operation.

The [worker audit](halogen-pld-native-worker-exclusion-20261006.md) supplies the selected-mode exclusions:

| Family | Evidence needed during capture and handoff call |
|---|---|
| Disk queue | Actual `A=*(outer RSP+0)`, `M=*(A+0)`, `C=*(A+8)`, and null `C+0xe0` with observed startup skip or failed-init teardown/join. Cache Off alone is insufficient. Later `0x173c200/0x173dcb0/0x173c950` entries retire. |
| Construction timer | Successful `0x176b800` return after join `0x176f413`; no active constructor/reset scope. |
| Parallel copy | No active `0x17d76b0` scope; successful return follows joins at `0x17d8213`. Its real writes to model `+0x6b8` can overlap callbacks at `0x17d8045/0x17d816c`. Retire before postseed `0x1736aa0` command processing and refuse nested capture while the helper is active. |
| Indexed jobs | No active dispatcher `0x188da30`; prior successful return follows all joins at `0x188def3`. Retire before any postseed dispatcher entry. The large executor's complete transitive alias proof remains open, so enabled overlap is excluded by this concrete bypass. |

Retirement notices revoke private packets; they do not lock or hold native objects alive. A cross-thread destructor/reset can continue after publishing a retirement flag. Before native reads, the installation must establish that the relevant release/mutation paths are serialized under this selected native owner or are excluded by the proven mode. A generation check before/after a copy cannot repair a use-after-free or establish a coherent native snapshot.

## Exact implementation gaps and next change

Add the fixed-storage native copier and synchronous decoder-to-handoff projection in one new `native_owner_capture` adapter. Keep the existing capture decoder, handoff and consumer APIs. Its first invocation uses `packet=null`; it emits owned observations and value events while retaining stock behavior. Use the reports' existing pins, not another generic contract or synthetic harness.

The remaining connections are concrete: a scoped native-read entry compatible with the relay restriction; installed successful-birth/release/reset/worker observations; a complete owned seed and acknowledged digest before seam; trusted model/token definitions; handler-owned state and immutable publication; and actual default-off seam installation, near direct continuation, native state/unwind/signal/stack qualification. The current relay has no installer, native copier or packet-success route. Until those connections exist, source flags remain false.

One observing seam can retire immediately afterward. Continuing causal Prefill/Decode/acceptance work additionally needs real stock outcome previews/seals: outer `0x172d80f/0x172d8f7`, controller `0x173b769/0x173b88c`, and scalar selected-ID/postcallback boundaries recorded in the owner audit. A no-hit event alone carries no authoritative acceptance outcome. CPU capture/decoding, GPU proposal/state work and NPU proposal/state work may share the value protocol, but no placement or performance fact follows from this connection report. Prefill, Decode, acceptance, readiness, device placement and serving gain remain `null`.

Only this report was created. Work used current local source and the existing pinned reports; no repeated disassembly, compiler, tests, runtime, WSL, hardware, process-management, production edit, stage or commit occurred.
