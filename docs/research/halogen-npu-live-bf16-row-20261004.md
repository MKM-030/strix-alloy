# Live BF16 row-Gather NPU admission — 4 October 2026

The root-owned guarded rank-two row-Gather attempt failed strict NPU admission.
Session initialization returned the CPU-fallback-disabled error after 23.553 s;
the NPU receipt contains **zero execution calls**. CPU validation passed, but
there is no NPU numerical result or qualified NPU timing and no demonstrated
speed advantage over the measured native GPU MLP.

## Frozen candidate and scope

The [separate row-Gather probe](../../scripts/benchmarks/halogen_npu_v2_live_bf16_row_gather_probe.py)
uses the first two distinct captured live routes, preserving captured expert
order, coefficients, and exact widening of BF16 input. It reuses the reviewed
16-expert, 157,286,400-byte BF16 bank and saved independent BF16/decoded-FP32
references without decoding the checkpoint again. Bank tensors flatten only
their first two axes to `[40960,1280]` and `[10240,2560]`; host row indices are
`bank_index*2560+arange(2560)` and `bank_index*640+arange(640)`. Two axis-zero
Gathers, two Reshapes and two Casts precede the unchanged eight expert operators.
Runtime feeds total 266,280 bytes per call; weights remain constant.

Both CPU runs used one thread, four warmups and eight measured alternating
calls. All normal outputs passed strict BF16 graph semantics and the separately
labelled original FP32 approximation gate. Strict original-FP32 agreement failed
and remains explicitly reported. Eight additional CPU calls detected each stale
row-index, input or coefficient substitution at both labelled tolerances.

| CPU replay | Mean host call (ms) | Mean session run (ms) | Mean feed copy (ms) |
|---|---:|---:|---:|
| Offline | 20.0730625 | 20.0518125 | 0.0212500 |
| Root guarded | 20.3555625 | 20.3333875 | 0.0221750 |

These timings include fresh feed copies and `session.run` transfer/execution/output;
build, verification, reference preparation and numerical gates are excluded.
Offline peak private-memory increase was 514,273,280 bytes; guarded CPU peak was
514,375,680 bytes, both below the 1-GiB cap. The complete guarded run retained at
least 43.5694 GiB physical memory and 197.8795 GiB commit headroom, with no guard
errors. All three retained Owned Jobs closed; provider unregister, DLL directory
close and bootstrap shutdown succeeded.

## Negative partition evidence and GPU comparison

The saved compiler context claims twelve of fourteen original operators in one
VAIML partition: both Reshapes, both Casts and all eight expert operators. Its
inputs include `selected_gate_up_rows_bf16` and `selected_down_rows_bf16`, the
two Gather outputs. Comparing this partition with the frozen graph identifies
the two rank-two Gathers as the CPU remainder. The embedding-style row geometry
did not close the admission gap. Claimed VAIML membership does not establish
internal hardware placement or execution; no retries were performed by this
reporting task.

The separate successful native layer-48/count-one GPU event run recorded 73 MLP
calls: mean **0.404611973 ms**, median 0.390228987 ms, p95 0.487067997 ms and total
29.536674023 ms. It observed 584 kernels (eight per call), zero hipblasLt calls,
and only stream zero; generated output matched stock, with cleanup/recovery
proven. The instrumented event brackets include GPU waits, enqueue gaps and
observer overhead. They are not exact uninstrumented latency or accepted-token
cost. This native measurement and the CPU expert-subgraph replay have different
scopes; the failed NPU attempt supports no speedup claim or complete MLP/MTP claim.

## Retained identities

Offline artifacts: `C:/AI/halogen-mtp-npu/v2-live-bf16-row-gather-offline-20261004`.
Root-owned attempt: `C:/AI/halogen-mtp-npu/v2-live-bf16-row-gather-guarded-20261004`.
GPU receipts: `server/.local/optimization9h-20261004/mtp-event-timing-b3437ba2bb1f4e5697a02e266fd5952a`.
The probe builds with `--build-from-reviewed`; NPU launch remains root-owned.

| Artifact | SHA-256 |
|---|---|
| Row probe source | `4adcaa30d8d8e240696b184d05293f176ad7fb1c2de5d85685dbc2ee40c8418a` |
| Frozen parent BF16 probe source | `6d665ec8d88df6cc177c8c0747329714183825ed80f23e87a347701d91d9d53d` |
| Parent reviewed build receipt | `28bc4f16814efb0b4007937e4bde429a6d2eb6320745935362d427bdf57d9d21` |
| Row ONNX, 2,354 bytes | `845efcdd900d7bedd33bb0759497afaae3d962ff2dd722a30095ecbd238a2728` |
| Exact reused bank data | `bf47a0989cbbb038d57c7daf22bfb06b887e5c6052e4cdaa6d5c584e8777b8fa` |
| Offline build receipt | `6f17c951e7341652bf86e99635fad9a08a0e217aea65179e71a8f6584696727e` |
| Offline CPU receipt | `5a731001d245aa00ec1d47aef8c0755d9a12f51df8ab4bd6e4003a749c2fedf9` |
| Root row guard source | `91bd511e1ed282a0bdee395958f6a290805b93881ced8b5381ca89eff02c0581` |
| Guarded build receipt | `030f1044904f7e7672036283ba2346794e13ecf3bb9048de3cd003d039cab8f8` |
| Guarded CPU receipt | `cb0187fc6b74e16da7f8275ff1a9b824ddd65b535dba5266be1841d9ef640ccb` |
| Guarded NPU receipt | `06f31ab40293600804c50b3b59386f6c4de04e842333de772135fdddef5f97b6` |
| Guarded result | `87bd595e4128f2868fe1cc1bbae878f6b94e4a4660135d88388afe7f4769ac45` |
| Row compiler context | `4a6646655ece22f8f265798a5f2ce7dc7fe419f8eaf6a4641767433f6b26253f` |
| GPU result | `eee7b6f12dd2cb4718f77b521d3bfebd5fc388a2adff09a64f47cb8624ed4757` |
| GPU event statistics | `2b923accfab79f3f34bd77e8056e622f587c4aee02c7d15d0797c6bacbfe2da8` |
