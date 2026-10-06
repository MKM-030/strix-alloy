# Native owner capture source review

**No remaining blocker was found in the frozen, default-off source connector under its documented upstream capability contract.** The implementation contains one concrete path from supplied actual native read spans, through fixed private owned copies and unchanged `capture::decode_nohit`, to unchanged `NativeOutcomeHandoff::consume_at_seam(..., nullptr, projected)`. It neither supplies an installed native read boundary nor establishes the capabilities required to enter that path safely. This disposition must not be read as a live engine connection, native ownership qualification or serving result.

## Scope and frozen source

This independent review read the new header, implementation and documentation against the existing decoder, handoff, consumer and relay contracts and the [live connection design](../../../docs/research/halogen-pld-live-capture-connection-20261006.md). It inspected source and local SHA256 hashes only. No compiler, test, runtime, WSL, model, hardware, installer, process lifecycle, staging or commit ran in this review. The reviewer wrote only this file and did not edit implementation files.

| Reviewed file | SHA256 |
|---|---|
| `native_owner_capture.h` | `649c202063f572a574622ea133b67822c02c78312686b24de8d57c268dfcf87f` |
| `native_owner_capture.cpp` | `e7e1ce7399e41a9327530b1b635caae6fe14a458516d7c6836948008ef6cfcdf` |
| `NATIVE_OWNER_CAPTURE.md` | `63df9530b2be1c5c6b508c84ab5549b8068a3b99aa1e5c14e197af7f69ce13cc` |

The final source includes the review correction below. Earlier source hashes are superseded by these pins.

## Finding resolved before disposition

The first frozen binding carried owner/slot generations, but no explicit acknowledged native slot index. The decoder independently checked that the actual record and model agreed on their slot; that equality did not itself compare the current slot with the prior acknowledged slot. The author added `PriorPrefixBinding::native_slot` at header line 66 and its exact comparison with `NoHitFacts::slot` at implementation line 118. The documentation now includes the selected native slot among the bounded acknowledgement comparisons. Existing decoder and handoff sources remained unchanged.

## Copy bounds and ownership

`NativeOwnerCapture` defaults to disabled and uses member storage allocated with the adapter before invocation. Its request/model/record/outer/suffix capacities are exactly `0x1f8`, `0x902`, `0x308`, `0x180` and 512 signed32 IDs: 6,018 bytes in total, excluding fixed metadata and work buffers. The source asserts the 64-bit pointer and little-endian assumptions. The separate complete-prefix seed remains upstream-owned immutable preallocated storage; the seam does not copy or scan up to 262,144 full IDs.

The disabled return precedes all interval inspection and leaves the handoff untouched. Missing or invalid interval identity returns before native spans are read. The descriptor checks at implementation lines 67-75 require exact object extents, a nonempty suffix of at most 2,048 bytes divisible by four, nonnull pointers, finite address extents and correspondence of request/record/outer origins with the owned real RBP/R15/RSP image. Pointer conversion is used only to compare origins; no integer origin is converted back to a pointer.

The five `memcpy` calls at lines 83-88 are the adapter's native byte reads. Their destinations are fixed private member buffers, and their counts are bounded by the preceding checks. No copied request/model/record pointer is followed. The unchanged decoder receives const spans over those member buffers, the copied register values, the supplied native origins and the immutable trusted token definitions. It runs synchronously before storage is reused. It then checks the request-model origin, actual record/request relationship, single-record queue extent, prefill completion, aligned ordered vector boundaries, exact suffix origin/count, defined IDs and current tail, phase, checked signed32 allowance and saved R9D.

These checks establish copying bounds and layout consistency under the upstream interval contract. They do not establish mappings, residency, object lifetime, coherent snapshots, successful birth, reset exclusion or exclusive ownership. The interval issuer must hold all native spans alive and coherent for the whole call and exclude the concrete release/reset/slot/worker paths. A generation check cannot repair a read from freed or concurrently mutated storage. The adapter and handoff also require exclusive ownership throughout the call; there is no lock, atomic ownership or reentry mechanism here.

## Prior acknowledgement and qualification

`NativeReadInterval` and `PriorPrefixAcknowledgement` have private constructors and cannot be copied or moved. Their only external issuers are the intentionally unimplemented `NativeReadBoundary` and `PrefixAcknowledgementAuthority`. Those types encode trusted upstream assertions; C++ access control is not evidence that the assertions have been acquired or that a native integration is installed.

The prefix authority must complete the exact full-ID and full-fingerprint verification outside the seam and before the bound invocation, bind the independently observed successful birth/model/tokenizer/epoch/owner and slot generations, and prove complete-vector continuity to the specified native read interval. The interval identity and invocation sequence must be assigned in advance and never reused. The complete owned IDs, token definitions and observed owner must remain immutable and alive through `observe`.

The seam comparison at implementation lines 113-124 binds the same read interval and token-definition object, the complete observed owner value, nonzero frontier/window/fingerprint identities, positive native position, exact decoded prefix length/position/current ID/zero-padded suffix, acknowledged native slot, exact full seed length, all four object origins and native vector begin/end/capacity. A suffix has at most 512 IDs. The code deliberately does not dereference or scan the omitted prefix, compare every complete seed ID, recompute a fingerprint, or acquire acknowledgement transport. The length and nonzero fingerprint checks cannot provide that missing proof. The positive qualified route therefore remains conditional on the authority's independently established full-prefix verification and continuity, including the omitted prefix.

Only after both capabilities and their bounded binding checks succeed does line 132 translate their asserted semantics into the existing handoff's six true qualification members. The decoder, gates, pointer equalities, nonzero IDs and matching suffix do not independently justify that translation. A future issuer that fabricates those capabilities would violate this review's admitted contract and would need its own review; this adapter cannot make such an issuer safe.

Missing acknowledgement or observed owner produces `OwnedUnqualified` after safe copying and decoding, without `initialize`, `adopt_round` or `consume_at_seam`. A mismatched acknowledgement likewise avoids those calls. Invalid capture, decode rejection or lost evidence retires an already live feed; a still-disabled handoff remains uninitialized. First initialization additionally requires a nonzero first round ID and passes the complete qualified seed to the unchanged handoff. Subsequent use requires `Status::Sealed` and exact equality with its existing frontier before adoption. Unqualified initialization is never used as a pending-seed mechanism.

## Seam projection and stock behavior

The adapter is explicitly a separate native-read entry; it does not define `halogen_nohit_frame_observer` or relax that callback's owned-image-only contract. The relay/header/configuration remain frozen.

Implementation lines 158-175 populate `SeamCapture` from the acknowledged current frontier, independently asserted qualification, real saved RBP/RSP and decoded native gates/allowance. They project real GPRs and ordinary flags into the adapter's synthetic `SavedFrame`; its stack and 1,024-byte opaque extended-state array are zeroed and remain separate from actual XSAVE.

The sole seam consume call passes `packet=null`. The unchanged consumer therefore cannot select a proposal, write proposal bytes or take the success join. Its displaced-LEA change affects only the private projected frame, which the adapter discards. The adapter writes no native objects, real register image, native stack or real XSAVE image and has no copy-back route. `OwnedObservation` contains decoded values and stock status, without native origins, pointer-valued registers, descriptors or read capabilities. A qualified observing consume expires that round's proposal eligibility; actual stock outcome preview/seal remains the handler's separate responsibility.

An installed execution path must still arrange the relay's real restoration, displaced `LEA RAX,[RBP+0x1e8]` and direct stock continuation at `0x172d3c4`. Calling this source entry alone does not establish that placement or continuation.

## Unchanged prerequisites and remaining limits

The following hashes were read before and after this review and remained identical. This records source stability; prior standalone relay receipts do not qualify the new copier, issuer or installed callback call tree.

| Existing file | SHA256 |
|---|---|
| `native_frame_relay.h` | `f6aaf827d5187a3eb47bda94bf9f19d6eae29664251ede96c29b7d84e9c74cbe` |
| `native_frame_relay.S` | `b9bbbe04ce46a5c61fefa08fbdac56fcaffd5c9489e7c764c1e9dd4ae8d0fba5` |
| `native_frame_config.cpp` | `8bcc5d760cc6204a7896d8a1ddd866f1bb6b63fdb6a6584a5587a9e65447b57d` |
| `native_capture_layout.h` | `e7ce7302eb98cfa09a2c7ee2b1747e8c2a88d4311de0dfbdf10a5a03ab7eee1a` |
| `native_capture_layout.cpp` | `88bb4c55c0fea429633c5f196a94e7126258ce9c8182b8892cbff4b7e4b8bac5` |
| `native_outcome_handoff.h` | `5d4a42ad70edb14ae30f6c3043db4d889565031ef449de4ede9d6ce74536f835` |
| `native_outcome_handoff.cpp` | `9c642024ebd5a7b514a3acd598776f7657e5ff4ffcefad382e7647d7bef49cb8` |
| `seam_contract.h` | `caa67ed65e991e2f8474e5ba16ae5c8a29cc74bc517d253fe95a330e152bc5f2` |
| `seam_contract.cpp` | `c03d638baee63cf1d26c69a8cca19dd5c06d4cede60ae46150dbbdcbc2adf0f7` |

Uninstalled prerequisites include the successful-birth and release/reset/slot/worker observations, actual native lifetime/exclusion authority, complete seed acquisition and prior acknowledgement, trusted model/tokenizer binding, read entry compatible with the relay restriction, finite default-off installer/placement, and native state/stack/unwind/signal/CET qualification. Actual stock output preview/seal boundaries are also unconnected here. Phase zero at the no-hit seam still cannot exclude an earlier before-clear phase reentry without the separate installed observation.

This source review establishes no compilation result, actual engine observation, ownership/reset qualification, packet readiness, CPU capture cost, GPU/NPU placement, Prefill/Decode rate, native acceptance or serving gain. Those facts remain unqualified or null. Root owns any later finite compilation and meaningful focused execution; this reviewer performed neither.
