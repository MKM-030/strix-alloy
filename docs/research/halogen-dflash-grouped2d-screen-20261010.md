# DFlash grouped2d GPU attention screen — 10 October 2026

One synthetic BF16 Q/K/V/mask fixture used the same frozen inputs for both layouts: capacity16,640, valid prefix16,384 and three query slots. One warmup per layout was excluded, followed by three alternating measured pairs. No model weights, serving requests or NPU were used. Exact captured natural tensors were unavailable.

| GPU attention layout | Mean ms | Measured range ms | Extra allocated peak MiB |
|---|---:|---:|---:|
| repeat | 7.1354 | 7.1012–7.1763 | 403.53 |
| grouped2d | 2.5878 | 2.5666–2.6214 | 40.63 |

Grouped2d was **2.757× faster in this component**. Timing uses CLOCK_MONOTONIC_RAW and includes finite reductions and GPU synchronization. It excludes projections, MLP, context construction, the full vocabulary head, setup and output copying. Allocation peaks cover only the worker's Torch allocator during a call; they are not system memory or five-layer traffic.

All eight calls were finite. Every pair had max absolute difference0.000244140625, RMSE5.5626697e-6 and255 unequal elements out of18,432. Outputs are not bit-identical. No model-quality tolerance was changed or claimed satisfied; real proposal quality and native acceptance remain unqualified for this layout.

The normal server stayed ready/open. Gateway completed/cancelled deltas were both zero. The network-disabled worker loaded no model, exited0 and was removed through exact ID/name/image/label ownership. Minimum monitored physical/commit reserve was 21.781/113.288GiB. Session67750 ended0. The root packaging fix carried the two standard DXG bridge mounts read-only from the verified original manifest; its old source and change receipt are retained.

This result establishes a component improvement, not a full-backbone or serving speed gain. It does not produce new Prefill/Decode tok/s, native MTP acceptance, or an NPU benefit. Keep the candidate default off and assess whether graph/fused execution can reduce the remaining attention cost before another serving test.

The adjacent JSON retains input hashes, every measured call, error statistics, allocation/setup scopes and raw evidence hashes. No public commit or push was performed.
