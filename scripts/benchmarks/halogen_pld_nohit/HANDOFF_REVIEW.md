# Independent handoff source review, 6 October 2026

The frozen final source has no identified correctness blocker within its declared
finite, synthetic, trusted-caller scope. The component now exposes the owned
preseal event needed for early private work, makes retirement observable, and
declines custom consumption before outcome capacity is exhausted. This approves
the bounded source contract only. The serving decision remains off.

Review consisted of source, documentation and retained receipt reads plus static
file hashing. No tests, compilation, runtime/model loading, GPU/NPU, WSL, serving,
engine, process/lifecycle action, staging or commit was performed by this reviewer.
Only this separate review file was written. Implementation, the existing consumer,
old `REVIEW.md` and other documents were not edited.

## Frozen scope and pins

The author confirmed that implementation, harness and runner were frozen after
the final GREEN receipt. Independent local hashes match that receipt. The amended
`HANDOFF.md` was then read and hashed. Paths below are relative to this directory
unless otherwise stated.

| Source or evidence | SHA256 |
|---|---|
| `native_outcome_handoff.h` | `5d4a42ad70edb14ae30f6c3043db4d889565031ef449de4ede9d6ce74536f835` |
| `native_outcome_handoff.cpp` | `9c642024ebd5a7b514a3acd598776f7657e5ff4ffcefad382e7647d7bef49cb8` |
| `handoff_harness.cpp` | `772f825c77b3c39a9bfe952bf01011ef40f2743183cf07568fa0bb3959885564` |
| `run_handoff_harness.py` | `731f312c0e0279e3fa3633ae18b9a8bb77171bf45d0833164e680e98b398eea1` |
| `HANDOFF.md` | `266a188bb584c7c7141ce7ea48ba008651cc524f04fffa0f734989c3a20e0985` |
| Existing `seam_contract.h` | `caa67ed65e991e2f8474e5ba16ae5c8a29cc74bc517d253fe95a330e152bc5f2` |
| Existing `seam_contract.cpp` | `c03d638baee63cf1d26c69a8cca19dd5c06d4cede60ae46150dbbdcbc2adf0f7` |
| Repository `docs/research/halogen-pld-authoritative-handoff-design-20261006.md` | `aac25eaa90b396dc48730c9f085a20cc0709cb06acc77447240a3ad1b6fee74f` |
| `_artifacts/20261006-081602-handoff-red-62f2abc0/result.json` | `33d91aa46635331f339bd1389ce267de02d49040c476e5ea41b413ed914eb5c8` |
| `_artifacts/20261006-081739-handoff-green-a8ad0141/result.json` | `98b4cf539a7f506484cdea1536f6e75b4c7ed29cc84f6a462692a702c07202fc` |

The seam source pins remain identical to its earlier independent review. This
component calls that same `halogen_nohit::consume()` implementation at
`native_outcome_handoff.cpp:252`; it introduces no alternative predictor or native
success protocol.

## Findings and disposition

| Finding in the initially reviewed implementation | Final disposition |
|---|---|
| Preview stayed private until seal, preventing the promised early owned handoff. | Fixed. `PreviewEvent` and `pop_preview()` expose complete copied values, prior binding, successor round ID/generation, route/sequence, native outputs and recorded external IDs. Draining leaves `pending_` intact for seal validation. |
| An already-drained preview owner could not observe partial-stop retirement. | Fixed. Idempotent retirement retains a one-shot `RetirementNotice` with the last sealed reservation and revoked provisional identity. It clears pending/unread preview eligibility and permanently rejects old completions. |
| After 64 stock outcomes, packet65 could select because the separate custom-consumption ledger was still empty, although outcome65 could never be recorded. | Fixed. `adopt_round()` and `consume_at_seam()` check event/reservation/unread-preview capacity before admission. The focused fixture checks exact stock frame replay and unchanged consumer ledger for a valid packet65. |

The focused RED receipt and stdout report exactly these three failures against the
otherwise passing source. The final GREEN stdout reports four groups, zero failed
checks and 124 checks; its receipt records compiler and harness exit zero, an empty
error list and both owned jobs closed. Those are author/root-owned execution
receipts inspected by this reviewer, not an independent execution claim. The
earlier GREEN receipt at `20261006-081210-handoff-green-4b0b6c6d` is historical and
does not describe the final source.

The final source also rejects a claimed verified external outcome when its native
matched count exceeds the recorded external proposal count or its matched output
IDs differ from the recorded external prefix (`native_outcome_handoff.cpp:122`).
Native matched count remains separate from external use and recorded external
IDs. The event ABI has no fabricated custom accepted-count field. In particular,
stock controller acceptance after an opening rejection cannot become acceptance
of the unused external proposal.

## State, bounded validation and stock continuity

Initialization checks qualified ownership, nonzero seed/birth/key/model/tokenizer
identities and generations, token definitions, independent target position,
canonical length, suffix origin/count, current-token/tail equality, and zero unused
window slots. Adoption requires exact equality with the previously sealed
frontier. Complete reservations bind seed, native epoch, owner/model-slot
generation, frontier/window IDs, full copied suffix and round generation beyond
the existing wire fields. Same saved addresses do not substitute for these
identities. An external registry must still ensure freshness across new objects.

Preview validates route-specific count, ordered sequence, exact prior reservation,
unused successor ID, every output token, position advancement and overflow before
storing the preview or reserving a successor. Scalar copies require one output;
outer/controller copies require `k=a+1` and at most four outputs. Seal validates its
matching sequence, full emitted count, continuing disposition, unchanged owner,
actual canonical extent/position/current token, fresh frontier/window identities
and exact retained suffix plus output evolution before publishing its authoritative
event or advancing `current_`. Work is bounded by 512 suffix IDs, four outputs and
the fixed ledgers. Counters cannot approach arithmetic overflow within the finite
64-outcome lifetime.

Preview supplies no eligible caller truth. The seam adapter requires an active
adopted frontier, exact independently copied current equality, qualification and
the actual saved RBP/original outer RSP identities. It separately requires
`opening_gate_eligible`, then passes independently copied B and the existing native
gate facts to the reviewed consumer. A packet must match the complete current
reservation and still pass all existing authentication assertions, framing,
binding, epoch, token, allowance and one-shot checks before native frame mutation.
This review does not claim that asserted capture or gate facts were obtained from
an engine.

The first seam visit expires reply eligibility. Absent, malformed, late, stale or
gate-declined replies immediately replay the existing stock continuation while
ordinary outcome tracking remains active. Stock preview/seal requires no no-hit
visit at all. Unknown native ownership/reset facts, gaps, partial stop and other
invalid transitions retire the feed. Retirement retains sealed unread outcomes,
and drains never recycle reservations or event budget. A pending unread preview
must be drained before a later round can be admitted; it cannot be silently
overwritten. The object is noncopyable/nonmovable and has no reseed/ledger-clear
operation.

All mutable operations require one exclusive owner, immutable inputs and held
lifetimes. These assertions are explicit caller obligations. Embedded storage and
`noexcept` source calls provide bounded nonthrowing updates under that ownership;
they do not implement concurrent publication, reset exclusion or engine lifetime
protection.

## Harness and launcher review

The canonical oracle retains its entire small history, appends every supplied
native output, and independently derives canonical length, current token, target
position, suffix and opaque fixture fingerprint. It does not call the component's
suffix evolution helper. Its initial position differs from prefix length, and the
511-to-515 case checks the exact 512-ID suffix with origin three. Other fixtures
cover stock controller/scalar/outer outputs without custom selection, missing,
duplicate and out-of-order transitions, partial stop, epoch/generation changes,
undefined final output IDs, round reuse, opening rejection, missed/late replies,
preseal drain, observable revocation and finite budget/order preservation.

The harness compares all synthetic GPRs, saved flags, stack bytes and opaque
extended-state bytes for exact stock declines and bounded proposal success. Its
placement reconstruction starts new test-only object lifetimes; production has
no reset API. The token bitmap, capture booleans, fixture digest and synthetic
authentication assertions are test premises, not native truth or HMAC proof.

The launcher checks helper and named tool hashes before helper import, retains
the existing suspended child/kill-on-close job ownership, and recovers an attached
`error.owner` when construction cleanup fails. `finally` closes only the retained
owned child; failed close retains its owner for retry and prevents a clean result
when cleanup is unconfirmed. No broad process-name/PID killing is introduced.
Both available physical memory and commit headroom must exceed 22 GiB before
construction/resume and 18 GiB during the 250-ms wait loop. Build and harness
deadlines are finite at 90 and 10 seconds. Source hashes are recorded receipts;
the final frozen source/receipt equivalence was independently checked above.
No constructor/cleanup fault injection was performed by this reviewer.

Independently rehashed launcher dependencies:

| Dependency | SHA256 |
|---|---|
| Repository `server/host_frames.py` | `417e33060ce6bc5b8f336f9e90282012a4a0e12475a13ad1dba20eec2df8bdf8` |
| Repository `server/winjob.py` | `3d2db1c5c8ea3846152a0073dd4ed324a47ffd36ac63bf8f48cc52e39b0d4d4c` |
| Existing VS2022 BuildTools `VC/Auxiliary/Build/vcvars64.bat` | `6b516d8fcf543c14b2d861e1f45661e0029230fe0dc48e86ce78522801822209` |
| Existing MSVC 14.44.35207 `bin/Hostx64/x64/cl.exe` | `88c8344236a27a6e727e0a8edc49aaa2690bdc7a9464b9d18cc7abe70a9f1c0d` |
| Same tool directory `link.exe` | `ca11e6c45debd34bf652dfe984c5360a531a005ed78bf72852330c9c2590cf0d` |
| Same tool directory `c1xx.dll` | `688fe28f3065283edf668868e76aeab28f03f80e2171c14c7d4e37f64513f623` |
| Same tool directory `c2.dll` | `98050f97d60f7e95fcaf3525a7103e4818fba498a43563922476819ce88ed162` |

## Explicit exclusions

Real native owner/seed/round/outcome/gate truth, reset maps and slot/lifetime
exclusion remain unqualified. This review excludes detour installation/removal,
image/ASLR/computed-entry proof, unwind/signals, SysV frame handling and full enabled
XSAVE preservation. It excludes cryptography, protected immutable publication,
cross-thread acquire/release ordering and cross-process transport. It also
excludes snapshot/model resolution, a ready producer, GPU/NPU parity or contention,
preview-to-seam timing, useful readiness, serving qualification and gain.

The source makes the finite preview/seal/retire handoff reviewable. It supplies no
evidence that a live packet can finish before a qualified native seam, and does
not authorize or justify a disconnected hardware qualifier.
