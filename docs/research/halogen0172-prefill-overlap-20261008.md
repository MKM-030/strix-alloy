# Halogen 0.17.2 performance development, 8 October 2026

The subsequent connected ordinary-first-gather comparison is complete. The
clean 0.17.2 Thinking server was restored in a visible Windows PowerShell 5.1
console and verified ready/open. Its final three measured 8192-token prose
requests with Thinking Off and 128 output tokens averaged **1226.59 prefill
tok/s, 42.88 decode tok/s and 210/339 = 61.95% combined API MTP+PLD acceptance**.
Serial TG1 prefill was 1261.00 tok/s. These are the current cohort's values,
separate from the earlier fixed-depth comparison below.

The new exact-version ordinary lookup attachment loaded, but its complete-row
marker never appeared. It therefore establishes no copied-row coverage or
speed improvement and stays disabled. The pinned native prefetch branch can
bypass this ordinary seam; dropping the adapter's flag check would not change
that branch. A concrete next scope targets the native copy worker after its
original scalar ID stores, preserving native threads and GPU math. This is a
static scope, not an installed worker optimization. See the
[full comparison](../benchmarks/halogen0172-ordinary-first-gather-20261008.md)
and [worker scope](../../scripts/benchmarks/experimental/native-worker-interception-scope.md).

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

The corrected v2 C/header are now implemented, independently reviewed by Root
and compiled successfully with `-Wall -Wextra -Werror`. They observe the actual
CPU-prefetch launch, callback completion, promoted state and native join before
the second key. The native default64/max256 worker policy is supported and
callback payload/TID reuse is allowed after return. The built ELF is47064 bytes,
SHA256`8833bf7dd0424cb3b17027342ceed985fb86fe44dd8444b7a0592915842d0da5`.
Root then loaded the separately sealed v2 wrapper and ran one distinct owned
16,384-token request. It completed HTTP 200 with 128 output tokens. All 64
native workers returned and joined; the actual full raw input, second suffix,
carry, callback and promoted state bindings passed. The request was intrusive
observation, with no warmup-plus-three throughput cohort.

| Native raw-clock observation | Milliseconds |
| --- | ---: |
| Small token publication | 17.520212 |
| Publication to second-chunk CPU launch | 6058.587138 |
| Whole native CPU worker interval | 8647.885010 |
| Publication to second key projection | 14708.678294 |
| Native wait entry to completed join | 200.944243 |

Most second-chunk lookup work is already overlapped. The 14.709-second
publication-to-key interval is a possible preparation budget, not a measured
Windows input-ready lead. No NPU, result substitution or device copy was
performed by the observer. It cannot establish Prefill, Decode, acceptance or a
serving speedup. The unchanged v2 observation will not be repeated for more
diagnostics. Its job exited zero, errors were empty, and the clean Thinking
profile was restored ready and open with the observer removed.

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

The private mapped-row CPU producer v4 completed one guarded replay of this
actual archived second-chunk suffix and carry. Its worker wall was 1.015000
seconds, sampled before ready-receipt publication. It copied 106,478 unique
160-byte rows (17,036,480 logical bytes), using 52 bounded indexed-copy tiles
from one read-only mapping. The mapped copy timer was 0.223063 seconds; mapping
close took 0.275064 seconds. These are filesystem/cache and CPU component
intervals, not isolated physical SSD latency. Cache state was not controlled;
no speedup ratio against prior workers or the native interval is qualified.

Complete 40 MiB BF16 and 80 MiB FLOAT inputs were published and independently
rehashed. Every one of the 20,971,520 FLOAT words is the exact finite widening
of its BF16 input. This verifies the saved artifacts, not equality to the
current native GPU input. The replay ran after the observer was stopped;
it does not qualify live ownership or a Windows-to-WSL readiness lead. The
owned CPU job closed with exit zero and no errors; the serving server was not
changed. No NPU or accelerator provider was used.

The v5 derivative also completed one archived replay, adding a 20 MiB raw FP8
row buffer and a 1 MiB original-order int64 row-ID buffer. Its sampled worker
wall was 0.859000 seconds before ready publication. All four outputs were
independently streamed and rehashed (147,849,216 bytes); BF16/FLOAT match the
previously verified v4 outputs, raw FP8 matches v4's recorded reconstructed
digest, and row IDs match the recorded original order. The publication,
process, model, table and constant bindings also agree. No worker was rerun
for verification. Cache/import conditions differed, so the v4/v5 times do not
qualify a causal speedup. These are saved second-chunk artifacts; first-chunk
ownership, a live handoff and serving-rate improvement remain unqualified.

A separate CPU/SSD candidate was identified in the actual native copy-mode
worker: retain exact ID generation and original ID order, then use a separate
page permutation to copy rows into the existing native buffer. The worker uses
mapped copies rather than read/pread syscalls. This is a real worker split,
not a launch wrapper. Mapping extents, output lifetime, cross-page rows and
cancellation/completion behavior must be preserved. No speed claim or hardware
measurement was made for this candidate.

The separate page-segment scheduler is now implemented and its focused
synthetic verification covers page crossings, duplicates, exact original-order
scatter, parallel disjoint-page copies, bounds and cancellation. Native
attachment remains disabled: scalar-ID ownership, selected mapping provenance,
phase completion and asynchronous raw-buffer reuse still require a connected
adapter. A completed countdown alone cannot authorize H2D after cancellation.
The ordinary first lookup is also being reviewed because changing an already
overlapped second lookup has limited potential.

The connected candidate targets that ordinary first lookup: group selected
source pages, copy exact row bytes into their original destination order, and
retain native GPU ID/history processing, unpack, RMS and FC. Stock second-chunk
prefetch remains in place. The first lookup uses a different worker and vtable,
so the prefetch worker binding alone cannot enable it. Implementation is in
progress; no extra throughput cohort or startup-floor study has been run.

## Retained evidence

All private evidence below is beneath
`server/.local/optimization9h-20261004/halogen0172-backend-preparation-20261008/`:

- Failed single window and clean restoration:
  `ple-early-observer-0172-source/ple-early-token-window-e7dacadddb844d47a7913e8b59122084/{result,final-ready}.json`.
- Current code object: `ple0172-math-delta-audit/engine0172-gfx1151-bundle0.hsaco`,
  SHA256`18937428b544e8a5ef1dae31db97f36136e8cdeca90e6c49458ef831b822a039`.
- Complete static bridge: `ple0172-math-delta-audit/audit-delivery.json`,
  SHA256`ad581d6a02fd13980514735cc8bf1187137cff3481dd93a79477589ed80f36f4`.
- Mapped-row source: `ple-numeric-0172-v3-source/source-delivery.json`;
  worker SHA256`ddd1cc18d31baf0ef885791854c32fbfe4093c08e9db6f7b6748fdfe61345990`.
- Fresh process identity and local/public health:
  `continuation-checkpoint-6eb39cfe0160409087de596596f11c8f.json`.
- Successful v2 observation and normal restoration:
  `ple-early-observer-0172-v2-source/ple-early-token-window-0172-v2-e01d259b8503429fa3831dbf01c53e18/{result,token-release-manifest,final-ready}.json`.
- Actual archived v4 input and artifact verification:
  `ple-input-archived-0172-v4-e01d259b8503429fa3831dbf01c53e18/`.
- Actual archived v5 raw rows, IDs and independent artifact verification:
  `ple-input-archived-0172-v5-e01d259b8503429fa3831dbf01c53e18/`.
- CPU page scheduler source and focused verification:
  `ple0172-native-page-scheduler-v1/delivery.json`.

The [companion status JSON](halogen0172-prefill-overlap-20261008.json) binds
these completed records and keeps all serving-gain claims false.

No startup-floor investigation was performed. The full acceleration goal
remains active and unachieved; no new NPU token-rate gain is claimed.
