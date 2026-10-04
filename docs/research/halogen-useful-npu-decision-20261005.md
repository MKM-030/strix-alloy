# NPU accuracy and practical throughput decision — 5 October 2026

The corrected NPU projection passes the original development tolerances on both
frozen native-GPU input sets. It is slower than the original GPU projection, so
the colleague's Halogen server keeps GPU prefill and native MTP decode.

The numerical change uses generic high/residual operands, retains the original
BF16 output boundaries, disables graph fusion explicitly, and requires stable
high parts under repeated provider quantization. It does not widen the tolerance
or fit individual values to the GPU oracle. Actual NPU execution, with CPU
fallback disabled, has zero embedding and hidden elements outside
`rtol=0.03, atol=0.003` in both input sets across twelve alternating calls.
This screen does not establish full-head, logit or proposal parity; the stable
CPU sibling also retains one failure at its stricter CPU gate.

| Paired projection measurement | Time per call |
|---|---:|
| Original GPU, resident device event bracket | 0.311702 ms |
| Original GPU, host enqueue and wait bracket | 0.487170 ms |
| Corrected NPU, session execution | 1.850025 ms |
| Corrected NPU, preparation and diagnostic call | 3.539513 ms |

NPU session execution alone takes about 3.80 times the GPU host bracket. These
are component timings with different scopes, not a matched live-engine A/B.
Transport and integration costs are not included. A component measurement
cannot be translated into a measured tok/s improvement.

The latest standard control uses the frozen nonrepetitive greedy prose
prompt, cache Off, MTP depth 2, PLD 3,3, one warmup and three measured requests:

| Actual input tokens | Output tokens | Prefill tok/s | MTP decode tok/s | Acceptance |
|---:|---:|---:|---:|---:|
| 8,192 | 128 | 1,229.125265 | 41.945034 | 60.0% (207/345) |

All three outputs have the frozen historical output hash. The measurement
finished at 22:02:49 UTC on October 4. Capacity is 262,144 tokens; this is an
8,192-token occupied input measurement. It is not a 128K or 260K input result.

No live NPU substitution was enabled, so there is no measured NPU prefill,
decode or acceptance delta. The justified deployment decision is to omit this
NPU candidate. The lower current throughput versus the separate historical
1,866.537/48.423621 result is real and is being investigated; it cannot be
attributed to an NPU candidate that was never loaded.

A separate request-order diagnostic completed at 22:23:30 UTC: one frozen
serial PP8192/TG1 request before each timed MTP request gave 1,259.987028
prefill and 41.625016 decode tok/s, with the same 60.0% acceptance and frozen
outputs. It did not restore historical decode. Conditioning consumed another
24.451235 seconds across four pairs, excluded from the MTP timers; it is not
an engine optimization or NPU result and is not selected for normal service.
The [conditioned-control report](halogen-conditioned-control-20261005.md) retains
all request identities, measured windows and the complete GPU telemetry.

The [bounded GPU embedding-cache replay](halogen-embedding-cache-replay-20261005.md)
also passes exact output checks but supplies no useful speed gain: hits take
essentially the same host time and misses take longer. It remains disabled.
An NPU producer would have to demonstrate a benefit after transfers and
scheduling while preserving quality. No such producer is currently admitted.

[Machine-readable decision and pinned receipts](halogen-useful-npu-decision-20261005.json),
[precision correction evidence](halogen-npu-precision-correction-20261004.md),
and [performance-gap audit](halogen-performance-gap-audit-20261005.md).

All jobs for the retained regular control are closed and its memory monitor
stopped. The colleague server remains open. The complete optimization goal
remains active; this document records a resolved placement decision, not its
completion.
