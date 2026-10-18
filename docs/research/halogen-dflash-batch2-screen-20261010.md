# DFlash two-group batched GPU attention — 10 October 2026

One excluded warmup per layout and three alternating measured pairs used the same frozen BF16 Q/K/V/mask bytes as the preceding screen: capacity16,640, prefix16,384, three queries. No model, inference request or NPU was used.

| Layout | Mean ms | Range ms | Extra allocated peak MiB |
|---|---:|---:|---:|
| grouped2d | 2.167354 | 2.057064–2.298858 | 40.63 |
| grouped_batch2 | 1.971452 | 1.928606–1.997471 | 40.63 |

Batching both independent KV groups reduced this component time by **9.04%** (1.099×). Use the baseline in this paired run; the earlier grouped2d mean came from a different window. CLOCK_MONOTONIC_RAW includes all input/score/probability/output finite reductions and synchronization, while setup/copies/error analysis are outside timing.

All eight calls were finite. Every measured pair had max absolute difference 0.0001220703125, RMSE 1.213191808e-06, and 34 unequal elements of 18432. Inputs, mathematical head order, finite predicates and BF16-score/FP32-softmax/BF16-probability policy were retained. Batched GEMM results are not bit-identical; no model-quality tolerance was changed or qualified.

Session20113 ended0. Its exact labeled network-disabled worker exited0 and was removed. Normal server completed/cancelled deltas stayed0; it remains ready/open. Minimum monitored physical/commit reserve was 21.950/113.612GiB. The existing cached runtime/image and standard read-only DXG bridge mounts were used; nothing was installed.

This is not a new Prefill/Decode rate, native acceptance or NPU result. Projections, context construction, MLP and full head were excluded. Full-backbone proposal costs and native integration still require separate evidence before adoption. The next independent mechanism is graph replay of unchanged GPU operations; exact installed worker graph API source is retained.

Adjacent JSON pins each observation, fixture hash, source and owned cleanup evidence. No public commit or push was performed.
