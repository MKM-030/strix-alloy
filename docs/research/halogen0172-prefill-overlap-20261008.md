# Halogen 0.17.2 performance development, 8 October 2026

The serving instance is **Halogen 0.17.2**, v2, context capacity 262144,
MTP2/PLD3,3, chunk/arena8192, Cache Off and one slot. After the single experimental
observer window, the clean stock path was restored ready and open. Local and
public authenticated health returned HTTP200. Thinking defaults remain On,
medium, with a 2048-token thinking budget; clients can override them.

The latest matched 8192-token non-repeated prose comparison uses **Thinking Off**,
temperature0/seed1, an excluded warmup and three measured runs. It is separate
from the Thinking-enabled serving configuration:

| Metric | Halogen 0.17.2 | Difference vs matched 0.16.2 bookends |
| --- | ---: | ---: |
| Serial TG1 prefill | 1232.58 tok/s | -4.50% |
| MTP TG128 prompt prefill | 1199.00 tok/s | -4.20% |
| MTP TG128 decode | 43.73 tok/s | +6.97% |
| API combined MTP+PLD acceptance | 210/339 = 61.95% | 60.00% in both bookends |

These values do not establish an NPU benefit. Historical48.42 belongs to a
different workload/arena. Detailed measurements remain in
[the matched comparison](../benchmarks/halogen0172-fixed-depth2-20261008.md).

## Work completed on the current version

The callback-bound early-token publisher compiled with warnings treated as
errors. Root ran one owned16384-token observation with the frozen request.
The engine rejected the observer's `later-key-identity` check; the API returned
HTTP502 and no complete token-window receipt exists. The failed attempt remains
recorded and contributes no prefill, decode, acceptance or release-lead result.
Cleanup and normal restoration completed. The memory reserve monitor reported
no violation. The unchanged v1 observer will not be repeated.

Static analysis identifies a native-prefetch branch at model+0x7c0 that can skip
the ordinary helper inside the later Target. The observer had required that
helper timestamp there. The correction must observe the actual native prefetch
caller and preserve request, token-slice, carry and model-lifetime ownership.
The actual native worker computes row IDs inline on the CPU; it does not call
the GPU helper. A new observation must label this path separately and preserve
the existing native prefetch optimization.

Separately, bounded CPU extraction of the current embedded gfx1151 code object
closed the static shader identity gap. Six PLE history/input/gather/RMS kernels
and five default BF16 FC kernels have exact matching function bytes against the
previously validated shader. Kernel descriptor differences are only checked
code-entry displacements. The current helper and FC instruction sequences also
match after PC-relative address normalization, and current host registration
names were resolved. This permits reuse of existing independent checkpoint
constants, row-ID/FP8 math and BF16 weights without recapturing weights. Actual
current second-chunk input parity, executed FC route and NPU output/serving
benefit remain separate qualifications.

The private mapped-row CPU producer is implemented and independently reviewed.
It replaces serialized page reads with bounded2048-row indexed copies from one
read-only mapping. It has not been run and has no measured speed claim.

## Retained evidence

All private evidence below is beneath
`server/.local/optimization9h-20261004/halogen0172-backend-preparation-20261008/`:

- Failed single window and clean restoration:
  `ple-early-observer-0172-source/ple-early-token-window-e7dacadddb844d47a7913e8b59122084/{result,final-ready}.json`.
- Current code object: `ple0172-math-delta-audit/gfx1151-bundle0.hsaco`,
  SHA256`18937428b544e8a5ef1dae31db97f36136e8cdeca90e6c49458ef831b822a039`.
- Complete static bridge: `ple0172-math-delta-audit/audit-delivery.json`,
  SHA256`ad581d6a02fd13980514735cc8bf1187137cff3481dd93a79477589ed80f36f4`.
- Mapped-row source: `ple-numeric-0172-v3-source/source-delivery.json`;
  worker SHA256`ddd1cc18d31baf0ef885791854c32fbfe4093c08e9db6f7b6748fdfe61345990`.
- Fresh process identity and local/public health:
  `continuation-checkpoint-6eb39cfe0160409087de596596f11c8f.json`.

No startup-floor investigation was performed. The full acceleration goal
remains active and unachieved; no new NPU token-rate gain is claimed.
