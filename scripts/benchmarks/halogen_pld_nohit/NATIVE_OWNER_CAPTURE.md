# Native owner capture connection

`native_owner_capture.h/.cpp` adds the fixed-storage, default-off connection
specified in [the live capture report](../../../docs/research/halogen-pld-live-capture-connection-20261006.md).
It copies actual scoped request/model/record/outer/suffix read spans into private
owned storage, calls unchanged `capture::decode_nohit`, and, only with the prior
independently qualified binding, calls unchanged `NativeOutcomeHandoff` with
`packet=null`. It has no installer, native pointer probing, producer or success
join. The relay, decoder, handoff and consumer sources are unchanged.

## Separate native read boundary

`NativeOwnerCapture` is preallocated once per exclusively owned handler and
disabled by default. Its five object/suffix buffers total **6,018 bytes**;
register projection, observation, seed and seam work buffers are also fixed
members. There is no allocation, wait, full-prefix scan/hash or lazy startup in
`observe`. Copies consume exact fixed object extents and at most 512 suffix IDs.
The native suffix is supplied as bytes, copied into owned signed32 storage on
the pinned little-endian x86-64 target. The unchanged decoder consumes const
owned spans synchronously before reuse. Returned `OwnedObservation` is a value
copy of decoded facts and stock status; it contains no native addresses.

`NativeReadInterval` is a scoped upstream capability. Its private constructor is
available only to the intentionally unimplemented `NativeReadBoundary` engine
integration. The issuer must already hold native objects/vector bytes alive and
coherent, exclude release/reset/slot/worker mutation, serialize the handler and
supply this invocation's real seam register image. Span sizes, pointer equality,
nonzero interval IDs and generation checks cannot establish that proof. No read
occurs when the interval is absent. A safe interval without owner/prefix proof
can produce an **unqualified owned observation**; it never becomes a seed.

This is a separate native-read entry. It is **not** an implementation or expanded
contract for `halogen_nohit_frame_observer`, whose frozen API continues to permit
only owned register/XSAVE view inspection. An installed read boundary compatible
with the pinned relay is still missing. No pointer in copied fields is followed;
upstream supplies all held spans. Descriptor/origin checks validate layout only.

## Already acknowledged complete prefix

`PriorPrefixAcknowledgement` also has no public constructor. Only the separately
reviewed, intentionally unimplemented `PrefixAcknowledgementAuthority` may issue
it after the complete acknowledgement finishes **before** the bound invocation.
The authority must copy all actual IDs, up to 262,144, into separate preallocated
immutable owned seed storage; verify the complete IDs and fingerprint outside
the seam; bind successful birth, model/tokenizer, epoch, owner/slot generations,
native position, exact frontier and tokenizer definitions; and independently
establish complete-vector continuity through the bound native read interval.
It must assign a private invocation identity in advance and never reuse it.

The adapter requires the acknowledgement's exact interval/owner/token mapping,
object origins, selected native slot and vector begin/end/capacity to match. Its frontier length,
position, current ID and zero-padded suffix must match decoded facts. The complete
owned seed span must have the exact full length. These bounded checks inspect
metadata and at most 512 IDs; they do **not** compare the omitted prefix or
validate a fingerprint. Equal suffixes, arbitrary nonzero fingerprints, address
hashes or toggled booleans cannot replace the authority's earlier complete proof.
Private constructors encode the trust boundary; they do not implement native
synchronization, cryptography, acknowledgement transport or proof acquisition.

If any evidence is absent/mismatched, execution remains stock and no unqualified
`initialize`/`adopt_round`/`consume_at_seam` occurs. A still-disabled handoff stays
uninitialized. An already live feed is retired on lost evidence, invalid capture
or decode rejection, including postseed phase/prefill reentry. Disabled adapter
mode leaves the handoff untouched. Only a qualified first seed initializes the
one-lifetime handoff; subsequent seams require its exact already sealed frontier.
The same owner must handle adoption, stock outcome preview/seal and retirement.

## Observing seam and remaining proof

The adapter projects real GPRs and ordinary flags into a local preallocated
`SavedFrame`, keeping its synthetic stack/opaque extended-state fields zero.
`consume_at_seam(seam, nullptr, projected)` records the stock decision. It expires
the round's proposal eligibility without selecting a proposal. No projected
register, synthetic stack or extended-state bytes are copied back to native
state. The relay's actual XSAVE image remains its restoration source; the relay
replays `LEA RAX,[RBP+0x1e8]` and directly resumes stock `0x172d3c4`.

Successful birth at `0x1749f0b`, the pending-construction/release/reset/slot paths
and the disk/timer/parallel-copy/indexed-worker exclusions specified in the live
capture report remain uninstalled. Cross-thread retirement alone does not hold
native objects alive. Real seed acquisition/acknowledgement, installer, actual
seam placement, native unwind/signal/CET/stack qualification and authoritative
stock output preview/seal boundaries remain outstanding. No authority capability
or serving qualification is claimed by this source. The existing reports' ELF
and instruction pins remain the reference; no disassembly was repeated.

CPU owns the scoped bounded capture/decoder/handler work described here. GPU and
NPU may eventually consume owned value publications for proposal/state work,
after their own integration and readiness are qualified. This source establishes
no device placement or performance result. CPU capture cost, GPU/NPU readiness,
Prefill tok/s, Decode tok/s, native acceptance and serving gain are all **null /
unmeasured**. No compilation, test execution, native runtime, WSL, hardware,
process lifecycle, staging or commit was performed by the source author.
