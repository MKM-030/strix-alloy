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
