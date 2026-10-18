# Full DraftBackbone finite accumulation — 10 October 2026

Actual frozen BF16 learned bank, one shared deterministic synthetic fixture: capacity16640, accepted length16416, seven query rows and grouped_batch2 attention. All212 primitive finite checks and mathematical operations are unchanged. Both variants share the same learned/index and input tensor objects. The actual original head is retained as an unused CPU mmap; no head or embedding computation occurs.

| Variant | Mean ms | Min ms | Max ms | Sample SD ms |
|---|---:|---:|---:|---:|
| Original backbone | 33.551921 | 31.770568 | 34.344604 | 0.924647 |
| Accumulated backbone | 29.625776 | 27.431857 | 32.200365 | 1.803117 |

The accumulator saves 3.926144ms (11.70%) in this full-body component window. Every paired candidate call is cheaper; the gain is positive in both execution orders. The one excluded preflight pair and all six measured pairs have bit-identical7×2560 BF16 hidden values, equal true finite flags and zero maximum absolute difference. All rows are retained. The cold original warmup took642.432ms and is excluded as declared before execution. Reserved storage is stable for every measured call.

Timing uses Linux CLOCK_MONOTONIC_RAW from full body entry through the equal all-row finite `.item()` boundary, with equal pre-call synchronization. CPU hidden copies and parity checks are outside timing for both variants. Dispatch time alone is not isolated GPU cost. Numerical parity covers one finite synthetic fixture, not model-body fault injection or historical native features. The previous850 CPU predicate cases qualified conjunction logic only.

This measures backbone cost, not a complete proposal, useful teacher agreement, native MTP/PLD acceptance, NPU operation or Prefill/Decode token rate. Do not subtract this difference from a historical natural proposal or convert it into serving tok/s. The low useful agreement of the earlier natural DFlash shadow remains unresolved; further microbenchmarks need new utility evidence before native/NPU attachment. Retain the accumulator default-off.

The owned worker completed session73216, exit0, and was removed. The normal Halogen0.17.3 server remained ready/open with zero request/cancellation deltas. Minimum sampled physical/commit reserve was19.269/111.151GiB, above18/18GiB. The4GiB cgroup succeeded for this exact fixture; this does not establish sufficiency for other components.

Pre-execution source review corrected persistent inference tensors without version counters and made RAW timing explicit. Final pins, warmup, paired costs, memory frames, asset provenance, actual tool handle and ownership receipts are retained in the adjacent JSON. No completed series was repeated.
