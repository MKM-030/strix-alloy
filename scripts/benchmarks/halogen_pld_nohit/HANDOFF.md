# Fixed-storage native authoritative-outcome handoff

This default-off source component connects finite native outcome tracking to the
existing reviewed `consume()` interface. It establishes synthetic CPU behavior,
including stock controller/scalar outcomes when no custom proposal was selected.
It does not install a hook, capture actual engine state, authenticate transport,
run a model, or establish serving readiness or gain. The serving decision remains
off. The reviewed consumer, existing runner and engine/lifecycle files are unchanged.

## Contract and caller boundary

`native_outcome_handoff.h/.cpp` owns a single seed lifetime, one pending preview,
up to 65 round reservations, one unread owned preview event, one sticky retirement
notice, a 64-entry one-shot consumer ledger and 64 immutable sealed outcome records.
All storage is embedded. Operations are `noexcept`, with
no allocation, callback, lock, wait, retry, runtime, device or transport action.
The component cannot be copied/moved, silently reseeded after initialization,
or have its ledgers cleared. Drain does not recycle the finite event budget.
Exhaustion retires eligibility and preserves previously sealed unread outcomes.

The value-only event ABI binds a unique seed ID, birth nonce, native context epoch,
owner and model-slot generations, key/model/tokenizer identity, frontier/window
IDs, exact copied suffix, independent target position, canonical length/current
token, full-prefix fingerprint and round ID/generation. IDs and generations are
opaque identities, never encoded native addresses. Packet envelopes bind this
whole reservation because wire version 1 does not carry seed/window IDs, epoch
or these generations. Epoch is native context truth, never a drafter/bridge epoch.
Every initialized lifetime requires a newly qualified birth/seed/generation; an
external owner registry must prevent nonce/identity reuse across new objects.

`Qualification` describes externally established capture, reset exclusion,
exclusive serialization, held lifetime, tokenizer definitions and exact
full-prefix fingerprint verification. **Setting booleans cannot establish any of
those engine facts.** The caller must implement and qualify the native copying,
ownership and synchronization boundary. Inputs remain immutable for each call;
one exclusive owner serializes all methods and the saved frame. This source has
no cross-thread release/acquire event protocol. A future transport owner must
copy/publish entire events with qualified ordering and must never overwrite an
unread outcome.

The caller supplies an exact postinitialization seed from the native canonical
PLD vector, independently records actual target position and verifies suffix
tail/current-token equality. The current 1..512-token suffix is copied, with
unused `window_ids` slots zeroed for complete value comparisons. The full-prefix
fingerprint must be computed and independently verified outside an interior hook;
the component validates its presence/binding and exact bounded suffix evolution,
and does not hash an unbounded history. A cryptographic implementation/collision
assumption is still external. The fixture fingerprint is deliberately opaque and
noncryptographic. Constructor addresses, response text and shifted verifier input
are insufficient seed evidence. Initialization/prefill reentry requires a fresh
qualified seed lifetime; no unobserved vector append can be silently adopted.

## Preview, seal, stock outcomes and seam consumption

1. `initialize(true, SeedCopy)` admits a qualified seed as a sealed frontier.
   `adopt_round()` checks complete independently copied current equality at actual
   decoder setup before making its existing reservation active. Unexpected owner,
   epoch, model slot, prefix/window or current-token change retires the feed.
2. `preview()` accepts exactly one bounded selected-output copy, with an ordered
   sequence and unused successor round ID. Distinct `OuterPldCopy`,
   `NestedControllerCopy` and `ScalarCopy` types specify outer shifted output
   `+0x1980` after `0x172d80f`, nested controller output `+0x30` after
   `0x173b769`, and one selected scalar ID after constraint validation. No stack
   address, vector view or native pointer enters those types. The verifier input
   `[current, proposals...]` must never be substituted for selected outputs.
   PLD/controller copies require `k=a+1` with `1<=k<=4`; scalar requires count one.
   `pop_preview()` drains a complete immutable value copy with previous identity,
   route, sequence, owned outputs, recorded external IDs and successor reserved
   round ID/generation, so private resolution can start before native seal. It
   does not clear the independently retained pending validation copy. Neither
   that event nor the reserved ID makes a packet eligible. The one unread preview
   slot must be drained before admitting a later round; exhaustion retires the
   feed rather than overwrite a missed event.
3. `seal()` continues only on the matching sequence/from-reservation, complete
   zero-stop output loop, exactly `k` emitted/vector-appended IDs, unchanged owner,
   target position advanced by `k`, exact suffix/tail/current equality and fresh
   frontier/window identities. It records all authoritative outputs and the exact
   successor binding atomically within the exclusive, nonthrowing source call.
   Partial stop, explicit retirement, duplicate/missing/out-of-order seal,
   malformed copied token, identity reuse or mismatch retires provisional work.
   Only previously completed sealed events remain drainable. `pop_retirement()`
   delivers a sticky one-shot value notice carrying the last sealed reservation
   and any revoked preview sequence/successor ID/generation. An owner that already
   drained a preview can therefore observe cancellation. Retirement revokes all
   private completions for that seed/owner and cannot be reversed or reseeded.
4. `pop_authoritative()` drains every sealed outcome once and in order, including
   native lookup hits, no proposal, disabled/unready/malformed/stale custom reply,
   opening mismatch, stock nested controller and stock scalar routes. Preview
   does not require a no-hit seam visit. Retiring an unsupported path preserves
   stock execution and requires an explicit new qualified seed before resuming.
5. `consume_at_seam()` always calls the same existing `halogen_nohit::consume()`.
   It supplies qualified `CallerTruth` only from an adopted, previously sealed
   frontier that exactly matches independently copied `SeamCapture`, including
   actual saved RBP/original outer RSP identities. Those local saved-frame facts
   are never transported. Native allowance B and all existing gate facts come
   from the copied native capture, never a packet or target prediction. Both round
   adoption and seam selection check available event/reservation/preview capacity
   before permitting custom consumption; 64 stock outcomes cannot leave packet65
   selectable merely because the separate consumer ledger is still empty. The first
   feed also requires independently qualified `opening_gate_eligible`, including
   the documented MTP/opening-policy/position scope; branches which skip the
   retained opening equality receive no custom packet.
6. Each actual no-hit seam visit expires that round's reply eligibility. An
   absent, late, stale, oversized, malformed, untrusted or gate-ineligible reply
   immediately follows the exact stock LEA continuation. A gate/reply decline
   preserves stock canonical advancement; unknown owner/capture/reset facts
   retire it. Unsealed preview packets and duplicate seam visits never select.
   Complete stock outputs can still preview/seal after a missed reply.

Successful selection uses the reviewed join `0x172e95f`, preserving opening,
target verification, output/stop and replay control flow. Selection records the
external IDs before any later outcome is handled. `AuthoritativeOutcome` carries
those IDs and `ExternalUse::{None,OpeningRejected,Verified}` separately from the
native matched count. It contains **no custom accepted-count field**. A verified
external capture must be coherent with its recorded matched IDs. Native controller
acceptance after an external opening rejection remains native acceptance.

A future worker resolves the complete authoritative stream against its own
recorded external inputs, snapshots and exact opening/reuse/window rules. An
unused/rejected external proposal requires conservative restoration and scalar
replay; count one consumes no speculative model input. This component performs
neither model mutation nor snapshot resolution. The main checkout bridge's older
`commit(accepted,extra)` is not a complete-outcome operation.

## Focused CPU verification and exact receipts

`handoff_harness.cpp` uses a separate whole canonical-history oracle and four
groups: stock output/frontier evolution including 511→515 suffix rollover;
sealed/unsealed packets through the same consumer with recorded external IDs,
opening rejection and missed replies; preview/seal retirement; qualification,
token/identity failures and finite storage/order preservation. It compares exact
saved-frame state on declines/success, using destination canaries from the
reviewed synthetic consumer image. No fake XSAVE or hardware parity is claimed.

The runner is a new adaptation of the reviewed Windows CPU runner. Before any
helper import it pins `server/host_frames.py`, `server/winjob.py`, the named existing
MSVC environment file, compiler, linker and front/back-end compiler DLLs. It uses
only its own suspended, kill-on-close job children, checks both physical and
commit reserves before construction/resume (22 GiB), and continuously samples an
18 GiB reserve with 250-ms waits. Compiler/harness deadlines are 90/10 seconds.
Construction exceptions recover `error.owner`; close failures retain that owner
for an explicit retry and prevent a clean result if closure remains unconfirmed.
There was no injected constructor/cleanup fault in these runs.

Commands from the repository root:

```powershell
python -B scripts/benchmarks/halogen_pld_nohit/run_handoff_harness.py --phase red
python -B scripts/benchmarks/halogen_pld_nohit/run_handoff_harness.py --phase green
```

| First cycle (historical) | RED scaffold | Initial GREEN implementation |
|---|---|---|
| Local result under `_artifacts/` | `20261006-080742-handoff-red-97ced6ca/result.json` | `20261006-081210-handoff-green-4b0b6c6d/result.json` |
| Compiler exit | 0 | 0 |
| Harness exit | 1 (expected) | 0 |
| Behavioral result | 33 failures / 48 checks | 0 failures / 116 checks |
| Runner expectation / errors | true / empty | true / empty |
| Compiler owner PID / creation 100ns | 28916 / 134357404626182399 | 24140 / 134357407304412979 |
| Harness owner PID / creation 100ns | 29904 / 134357404650540047 | 21040 / 134357407328259238 |
| Both owned jobs closed | true | true |
| Minimum physical available bytes | 33,792,626,688 | 33,762,254,848 |
| Minimum commit headroom bytes | 132,449,329,152 | 132,427,649,024 |
| Maximum sample gap seconds | 0.265559500 | 0.261773700 |
| Executable SHA256 | `8419c23f32b33eb3d9cede461b252080979c2ced89765523bbdb0a9df519a204` | `0d91538abad05b1eeaab05dba2b858565eacb8554414a1994b528a3aab13eef2` |

The scaffold failed because interface behavior was absent, after a successful
compile. Before GREEN, root review added the independent opening-gate restriction
and its focused stock-continuation fixture; suffix rollover checks were completed
in the same four groups. The additional GREEN checks include draining all 64
sealed events, which the RED scaffold never produced. Full phase source pins,
owned identities, compiler/test logs and telemetry remain in those local receipts.
The initial GREEN was not final. Independent review found two missing mechanisms:
an explicit early owned preview drain/observable revocation and capacity admission
before custom consumption after 64 stock outcomes. A focused fixture first failed
exactly those three behavioral checks against the otherwise passing source. The
minimal fix added the preview/retirement drains and admission checks, then reran
the whole four-group handoff harness once. Its test-only event owner now drains
preview notifications before successive native round admission.

| Review cycle (final source) | Focused RED | Final GREEN |
|---|---|---|
| Local result under `_artifacts/` | `20261006-081602-handoff-red-62f2abc0/result.json` | `20261006-081739-handoff-green-a8ad0141/result.json` |
| Compiler exit | 0 | 0 |
| Harness exit | 1 (expected) | 0 |
| Behavioral result | 3 failures / 124 checks | 0 failures / 124 checks |
| Runner expectation / errors | true / empty | true / empty |
| Compiler owner PID / creation 100ns | 31032 / 134357409624648836 | 29560 / 134357410593527714 |
| Harness owner PID / creation 100ns | 28808 / 134357409649830645 | 17804 / 134357410617995023 |
| Both owned jobs closed | true | true |
| Minimum physical available bytes | 33,734,979,584 | 33,792,376,832 |
| Minimum commit headroom bytes | 132,403,613,696 | 132,453,056,512 |
| Maximum sample gap seconds | 0.264932200 | 0.265280200 |
| Executable SHA256 | `3b495052de3edcaf4df74e1589126f15331be5bae7e28b1a4b58f12fd78dea2b` | `341e148f478ac82f67a89863eedb7f84e758a26ca6e653fa0c18065b8ab98f37` |

Final compiler and harness stderr are empty; compiler stdout contains only compilation progress.
`--phase red` now fails its expectation for a passing implementation.

| Current source / retained boundary | SHA256 |
|---|---|
| `native_outcome_handoff.h` | `5d4a42ad70edb14ae30f6c3043db4d889565031ef449de4ede9d6ce74536f835` |
| `native_outcome_handoff.cpp` | `9c642024ebd5a7b514a3acd598776f7657e5ff4ffcefad382e7647d7bef49cb8` |
| `handoff_harness.cpp` | `772f825c77b3c39a9bfe952bf01011ef40f2743183cf07568fa0bb3959885564` |
| `run_handoff_harness.py` | `731f312c0e0279e3fa3633ae18b9a8bb77171bf45d0833164e680e98b398eea1` |
| Existing `seam_contract.h` | `caa67ed65e991e2f8474e5ba16ae5c8a29cc74bc517d253fe95a330e152bc5f2` |
| Existing `seam_contract.cpp` | `c03d638baee63cf1d26c69a8cca19dd5c06d4cede60ae46150dbbdcbc2adf0f7` |
| Existing `server/host_frames.py` | `417e33060ce6bc5b8f336f9e90282012a4a0e12475a13ad1dba20eec2df8bdf8` |
| Existing `server/winjob.py` | `3d2db1c5c8ea3846152a0073dd4ed324a47ffd36ac63bf8f48cc52e39b0d4d4c` |
| Existing `vcvars64.bat` | `6b516d8fcf543c14b2d861e1f45661e0029230fe0dc48e86ce78522801822209` |
| Existing MSVC 14.44.35207 `cl.exe` | `88c8344236a27a6e727e0a8edc49aaa2690bdc7a9464b9d18cc7abe70a9f1c0d` |
| Existing MSVC `link.exe` | `ca11e6c45debd34bf652dfe984c5360a531a005ed78bf72852330c9c2590cf0d` |
| Existing MSVC `c1xx.dll` | `688fe28f3065283edf668868e76aeab28f03f80e2171c14c7d4e37f64513f623` |
| Existing MSVC `c2.dll` | `98050f97d60f7e95fcaf3525a7103e4818fba498a43563922476819ce88ed162` |

## Placement, measurements and remaining proof

| Role | Assessment |
|---|---|
| CPU | Appropriate for these bounded copied facts, ledgers and packet checks. CPU model work would still pay host/DDR contention; the retained 45.09-ms proposal-plus-one-append proxy supplies no readiness case. This change does not run that model route. |
| GPU/Vulkan | Plausible later connected proposer/snapshot route. The pinned snapshot geometry has a 19.265625-MiB logical slot and 36 separately submitted blocking copies per save/restore. Native accepted-head replay shares GPU/DDR/queues; copy latency, contention and timely complete resolution remain unmeasured. No GPU action occurred. |
| NPU/FLM | The owned token/outcome ABI can describe it, but Vulkan recurrent restore proof does not transfer to XRT padded-attention rollback or caller ABI. The prior 67.68-ms proxy supplies no readiness case. No NPU action occurred. |

Historical placement facts above come from the
[authoritative handoff design](../../../docs/research/halogen-pld-authoritative-handoff-design-20261006.md)
and [snapshot feasibility audit](../../../docs/research/halogen-recurrent-snapshot-adapter-feasibility-20261006.md),
not measurements of this component.

| Serving measurement | Value |
|---|---|
| Preview-to-next-no-hit window W | null |
| Complete resolution/prepare/authentication/transport cost C | null |
| Ready packet rate / native opening-gate rate | null |
| Custom accepted tokens / custom acceptance rate | null |
| Serving Prefill / Decode / tokens per second / gain | null |
| Snapshot save/restore latency / joint GPU or NPU contention | null |

Required before live integration: actual native vector/current-token/position
seed and route capture; owner registry and constructor-success birth assignment;
in-place reset/model-slot/destruction exclusion; lifetime and worker cancellation;
the exact full-prefix fingerprint implementation; authenticated immutable wire
publication with protected epoch/envelope binding; ordered acquire/release event
transport and one pending producer; useful same-birth next-no-hit readiness and
complete matched target cost per actually committed token.

Each proposed interior site also needs genuine GPR/RFLAGS/all enabled XSAVE
component preservation with correct size/alignment, original outer/controller
frame addressing, SysV stack alignment/red-zone handling, displaced-instruction
replay, unwind/signal behavior, computed-entry exclusion, retained image/ASLR pins
and atomic installation/removal. The synthetic 1024-byte opaque frame and FXSAVE
are insufficient. No live detour, callback, engine/lifecycle edit, provider import,
WSL, hardware run, serving request, GPU/NPU work or staging/commit occurred here.
