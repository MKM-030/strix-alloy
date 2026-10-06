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
