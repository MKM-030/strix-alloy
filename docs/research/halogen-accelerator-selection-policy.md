# Halogen accelerator selection

The user's 6 October instruction makes actual Prefill tok/s, Decode tok/s and
native MTP acceptance the primary outcomes across GPU, NPU and CPU development.
Assess all three placements after each candidate change. A device is useful only
when its complete serving contribution improves those outcomes under the same
workload and correctness contract.

For each candidate, record:

- Which operation and metric it can affect; acceptance requires better proposals,
  while exact replacement arithmetic normally preserves proposals.
- GPU, NPU and CPU applicability, including the consumer interface and required
  transfers, synchronization, host work, cold preparation and resident memory.
- The existing correctness tolerances and qualification result, without changing
  tolerances to admit a candidate.
- Component evidence separately from actual serving rates. Component milliseconds
  are never relabelled as Prefill/Decode tok/s or acceptance deltas.
- A frozen, nonrepetitive serving comparison for a qualified useful candidate,
  including excluded warmup, repeated measured runs and accepted/drafted counts.

Retire a slower complete component before connecting another producer. Retain
the original path by default until the serving comparison proves a benefit.
Root coordinates exclusive hardware, preserves memory reserves and foreign
programs, and leaves the normal server ready and open after every measurement.

The selected 50 MiB original-weight preparation cache was screened as a GPU
Prefill candidate: exact outputs, but 23.2392 ms versus 22.8911 ms mean complete
component latency. It remains disabled. CPU can own metadata and lifecycle; no
useful NPU contribution is established. It duplicates a prepared matrix while
retaining original weights. The native packed HT pipeline failed the exact output
contract and remains disabled. Neither establishes a Decode or acceptance gain.
The compact-Q8 two-row GPU MTP kernel also had higher measured component latency
and remains disabled. Wider cache entries and other shapes remain unmeasured;
this result does not qualify them.

The subsequent compact-Q8 single-row fused-packing/ADD-DPP GPU H candidate
also stays disabled. Its complete primed component comparison preserved all40
timed frozen outputs, but candidate mean173.988microseconds exceeded native
169.846, with7/16 pair wins and order/drift effects. This establishes no advantage,
not an intrinsic2.439% slowdown. CPU/NPU offload has no qualified benefit at this
resident seam; ordinary target Prefill is outside it and acceptance was not
measured. No unchanged rerun or serving cohort follows. See the
[source, device assessment and evidence](halogen-gpu-q8-fused-status-20261006.md).

The original W16 preparation sibling has also been screened as a GPU Prefill
candidate. All 26,214,400 output words matched, but the 16 balanced measured
pairs split eight wins per arm and their paired median opposed the small mean
advantage. It remains disabled; CPU metadata and NPU placement establish no
serving benefit. No complete-engine token-rate or acceptance result follows
from that preparation screen. See the
[retained result](halogen-prefill-deq-status-20261006.md).

The new default-off no-hit proposal consumer is bounded CPU branch work. Its
synthetic contract qualifier passed, while real native installation and ready
publication remain unqualified. GPU/Vulkan and NPU are separate possible
proposal producers; each must establish useful readiness, complete resolution
cost and net serving benefit. This consumer does not change ordinary target
Prefill, and its tests provide no Decode or acceptance value. See the
[contract evidence and placement assessment](halogen-pld-nohit-contract-status-20261006.md).
The next connected implementation is the bounded authoritative-outcome
preview/seal handoff described in the
[native scheduling design](halogen-pld-authoritative-handoff-design-20261006.md).
Its possible overlap window is structural; useful readiness has not been timed.

The fixed-storage outcome handoff is now implemented and independently reviewed
in [the source contract](../../scripts/benchmarks/halogen_pld_nohit/HANDOFF.md).
It copies selected native outcomes into a preview for early private work, grants
successor eligibility only after continuing seal, and makes retirement observable.
Its CPU qualifier establishes bounded value behavior, not native installation or
new token rates. CPU owns this metadata/control path. GPU and NPU remain possible
independent proposal producers whose complete resolution and readiness costs must
be compared; this handoff does not move target model weights or ordinary Prefill.
Native capture and worker exclusion follow the
[concrete owner/seed/reset audit](halogen-pld-native-owner-capture-path-20261006.md).
All three serving outcomes remain unqualified for this new component.

The subsequent [native byte-layout decoder](../../scripts/benchmarks/halogen_pld_nohit/CAPTURE_LAYOUT.md)
supports complete 8K/16K/128K/260K vector lengths with a bounded 512-ID suffix
and independently recomputes native B from copied fields. It is CPU observation
work, with no installed capture or packet selection. GPU/NPU placement of these
checks alone offers no demonstrated benefit; proposal production remains a
separate possible device task. Its focused CPU evidence adds no Prefill, Decode
or native acceptance result. The
[real frame adapter plan](halogen-pld-native-frame-adapter-20261006.md)
identifies the concrete register/xstate and installed observation work required
to connect it; synthetic frame equality never supplies that proof.

The stock-only native frame relay has now passed a focused, real-register Linux
CPU qualifier: three cases and 18 checks with no failures, using the actual
observed XCR0 `0xe7` / 2,432-byte XSAVE extent. Its
[standalone evidence](halogen-pld-native-frame-status-20261006.md) does not qualify
native installation, literal physical x87 metadata, signals or active CET. CPU
owns this control path; GPU/NPU remain independent possible producers rather
than placements for the register relay. No weights are separated and ordinary
Prefill is unchanged by this source component. No new serving token rates or
acceptance follow. The explicit next native connection is documented in the
[owned-copy boundary](halogen-pld-live-capture-connection-20261006.md).

The [native owner connector](halogen-pld-native-owner-connection-status-20261006.md)
now has a reviewed source path and one successful compile-only check. It remains
off: native read/prefix authorities, installation and actual outcome integration
are absent. CPU owns its bounded copy/metadata work; GPU/NPU are possible separate
proposal producers whose complete readiness and serving cost remain unmeasured.
It replaces no target Prefill operation and selects no proposals. New Prefill,
Decode and acceptance values remain null. The earlier vector-screen result does
not justify adoption or an unchanged rerun. After every development, retain this
explicit operation-to-metric and CPU/GPU/NPU assessment before any engine cohort.

Multiple different draft sources may improve continuation coverage. Retain total
authoritative committed tokens per second as the decision metric; at-least-one
candidate coverage and native accepted/drafted ratios are distinct. Our present
consumer verifies one linear chain, so parallel branches require additional
target recurrent/KV-state and commit machinery. Arbitrary model weight subsets
are not complete trained predictors. See the
[bounded recommendation](halogen-multi-draft-feasibility-20261006.md).

The [Strata v0.1.40 audit](strata0140-halogen-source-assessment-20261006.md)
identifies real gfx1151 kernel/source ideas and an owned-token CPU suffix
proposer. Its incremental yield after native lookup misses is unmeasured.
`--batch-mtp` concerns concurrent clients. Strata's external GGUF rates, HIP
switches and library-specific exact reductions supply no Halogen HGN speed or
acceptance result; some advertised fusion paths are disabled on HIP. Preserve
the unchanged tolerances and qualify each actual native operation separately.

The [default-off startup installer](halogen-pld-installer-status-20261006.md)
has reviewed source and corrected linked-object evidence. It has not been loaded
and selects no drafts. CPU control overhead remains unmeasured; GPU/NPU have no
new placement or serving benefit. Actual startup/read/outcome authority and a
complementary timely producer remain required before an acceleration cohort.
