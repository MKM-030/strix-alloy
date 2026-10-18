# Finite scalar accumulation on the GPU

One excluded warmup per variant, then six alternating paired comparisons (12 measured calls). Both variants use the same 212 distinct ready GPU bool scalars, start synchronization and timed terminal `.item()` readback.

| Variant | Mean ms | Min ms | Max ms |
|---|---:|---:|---:|
| Original flat AND chain | 2.521585 | 1.818560 | 2.893684 |
| Stack/all accumulator | 0.265649 | 0.249305 | 0.299288 |

The accumulator saves 2.255936 ms (89.46% of this component). It is cheaper in every pair. All 12 results and both warmups are valid; all rows are retained. Reserved storage stays at 2 MiB for every measured call.

This compares ready-scalar aggregation. It excludes the original staged/nested RMS dependency graph, primitive finite reductions, weights, backbone, head, native consumer and serving. It supplies no new Prefill, Decode or MTP acceptance value. The source candidate preserves all 212 primitive checks and numerical operations, but full-body parity and cost remain to be measured.

Proceed to a same-input paired full-body comparison. Keep native/NPU attachment disabled. The root worker completed exit 0 and was removed; the normal Halogen 0.17.3 server remained ready/open with zero request/cancellation deltas. The earlier blanket Riot assertion stopped before any worker or inference; its evidence is preserved separately. Fresh valid GPU counters and the exact assessed background-client identities admitted this distinct window.

Raw rows, warmups, memory observations, source pins, tool identity and ownership receipts are retained in the adjacent JSON. No serving tok/s is derived from component milliseconds.
