# Original-H native screens: packed Q8 and decoded BF16

5 October 2026. Both root-owned standalone native screens passed the unchanged
frozen A/B NPU tolerance and closed their owned jobs after exit 0. Each made two
real original-H calls with zero warmups. These initial observations establish
neither steady-state latency nor a live engine gain. The H replacement consumer
remains disabled. The later original GPU server restoration passed separately.

| Observation | Packed Q8 | Decoded BF16 |
| --- | ---: | ---: |
| Complete A call, ms | 25.4992 | 4.7757 |
| Complete B call, ms | 22.8709 | 2.2519 |
| Complete two-call mean, ms | 24.18505 | 3.5138 |
| Submit/wait two-call mean, ms | 24.1738 | 3.50975 |
| Runtime initialization, ms, excluded above | 33.7685 | 505.8045 |
| Verified output values | 20,480 | 20,480 |
| NPU tolerance mismatches | 0 | 0 |
| Exact BF16 word mismatches | 1 | 1 |
| Maximum absolute error, as reported | 0.000488 | 0.000488 |
| Specified DDR bytes/call | 7,147,520 | 13,291,520 |
| Weight synchronization | once | once |
| Owned job closed / exit code | yes / 0 | yes / 0 |

Both use the same distinct frozen A/B inputs and original-GPU oracle. The
unchanged numerical test is `abs(error) <= 0.003 + 0.03*abs(reference)`.
The first input has no exact-word mismatch; the second has one in each screen.
A tolerance pass therefore does not establish bit-exact native arithmetic,
general numerical parity or full-head/output correctness.

The complete interval includes input copy, output poison, synchronization,
launch/wait and output synchronization/readback. Runtime initialization is
recorded separately. The decoded weights were already prepared by an exact
one-time conversion in 118.3896 ms; that earlier preparation cost is separate
from both its 505.8045-ms runtime initialization and per-call latency.

The decoded report records zero weight-decoder calls per projection. Its
specified DDR traffic adds 6,144,000 B per call while avoiding repeated scalar
affine conversion. Both observed decoded calls are lower than the packed calls,
but these sequential two-call, zero-warmup screens are not a controlled
steady-state speed qualification or a causal attribution to any one change.

No matched original-GPU timing, Windows/WSL live publication, acceptance cohort
or whole-engine NPU A/B ran here. Component milliseconds must not be converted
to tokens/s. The historical failed lifecycle/admission attempts remain in the
[implementation report](halogen-npu-native-hidden-implementation-20261005.json).
The component runs kept the already-terminal original-server state unchanged;
44/131-GiB startup and 18-GiB live reserves remain unchanged.

The original GPU server was subsequently restored ready/idle at **2026-10-05
21:11:36 UTC**, context 262144, through port 8840 at `/v1`. The receipt binds
controller PID 21092 and backend PID 3804, controller birth time, both run IDs
and the container identity.
The result records errors=[], recovery_pending=false and the owned WSL hold job
closed; no NPU or benchmark ran during restoration. Its transient observer
errors are preserved. This establishes original-server readiness at that check,
separately from any candidate integration or engine acceleration.
[Final-ready](../../server/.local/optimization9h-20261004/native-hidden-held-restoration-v2-f346f01978f748b8a47457e7cda58889/final-ready.json),
[restoration result](../../server/.local/optimization9h-20261004/native-hidden-held-restoration-v2-f346f01978f748b8a47457e7cda58889/result.json).

The [machine-readable comparison](halogen-npu-native-hidden-comparison-20261005.json)
retains the verbatim reports, wrapper outcomes, scope identities and receipt
SHA256 values. Raw retained evidence:

- Packed: [native report](../../server/.local/optimization9h-20261004/native-hidden-stopped-component-99fc925b97154c89beb6cb4bad833a08/native-result.json), [owned wrapper](../../server/.local/optimization9h-20261004/native-hidden-stopped-component-99fc925b97154c89beb6cb4bad833a08/result.json), [scope](../../server/.local/optimization9h-20261004/native-hidden-stopped-component-99fc925b97154c89beb6cb4bad833a08/scope.json).
- Decoded: [native report](../../server/.local/optimization9h-20261004/native-hidden-decoded-stopped-component-0af50913d99b409abc6883adfb15e51a/native-result.json), [owned wrapper](../../server/.local/optimization9h-20261004/native-hidden-decoded-stopped-component-0af50913d99b409abc6883adfb15e51a/result.json), [scope](../../server/.local/optimization9h-20261004/native-hidden-decoded-stopped-component-0af50913d99b409abc6883adfb15e51a/scope.json).

The subsequent default-off contiguous-vector sibling has its own
[implementation and initial two-call screen](halogen-npu-native-hidden-vector-20261005.md).
This comparison remains the historical packed/decoded pair; its counts and
21:11 restoration receipt describe that pair. The new vector report preserves
the later actual receipts and restoration status, without a steady-state ratio
or engine acceleration claim.
