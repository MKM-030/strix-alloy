# DFlash attention graph replay — 10 October 2026

Graph replay captures the identical two-group batched BF16 attention and all finite predicates. The exact frozen synthetic inputs are shared with the preceding screens: capacity 16,640, prefix 16,384, three queries. No model weights, inference requests or NPU were used.

The first window's raw means were eager 4.413413 ms versus replay 2.049004 ms. This is **not a qualified steady speed gain**: the eager warmup preceded capture, whose Torch context calls empty_cache. The first measured eager call grew reserved storage from 182,452,224 to 245,366,784 bytes and took 8.823803 ms. Later eager calls were 2.137799 and 2.278638 ms. All original rows are retained; none was silently discarded.

A distinct v2 moved the unchanged excluded eager warmup after capture setup. That excluded warmup absorbed a 10.279435 ms allocation call. Reserved storage then stayed 245,366,784 bytes for every measured row. No math, input or finite check changed.

| Corrected paired comparison | Mean ms | Range ms |
|---|---:|---:|
| Eager batch2 | 2.099909 | 2.056385–2.144840 |
| Graph replay batch2 | 2.102430 | 2.056204–2.178322 |

**No attention speed improvement is established.** Outputs were bit-identical for all three pairs in both windows: max absolute error/RMSE/unequal elements were zero out of 18,432 values. This proves agreement on the synthetic fixture, not model-quality or natural proposal equivalence.

Each window reports three excluded side-stream setup forwards, one capture invocation, one excluded comparison warmup per mode and three alternating measured pairs: 12 total forward/replay invocations, eight timed comparison calls, six measured calls. Capture/setup use CLOCK_MONOTONIC separately; measured attention/checks/synchronization/finite readback use CLOCK_MONOTONIC_RAW. Readbacks remain outside capture; global mode/private pool/static references are retained and the graph was reset. Replay allocates no additional scratch during its call because capture storage already exists; this does not mean its memory footprint is zero.

Both tool calls ended 0 without a yielded session (chunks a625d0 and 13feda). Both exact labeled network-disabled workers exited 0 and were removed. Normal server completed/cancelled deltas stayed zero and it remains ready/open. V2 minimum monitored physical/commit reserve was 22.071/113.729 GiB. Nothing was installed or publicly committed/pushed.

Keep attention graph replay off and do not repeat these unchanged windows. There is no new Prefill/Decode tok/s, native acceptance or NPU gain. The separate seven-slot training-layout correction remains a hypothesis to assess using complete proposal cost and actual subsequent target labels.
