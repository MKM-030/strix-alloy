# DFlash context-window v2 screen — 10 October 2026

One frozen natural 16,384-input/128-output request; 32 identical paired anchors, one excluded paired warmup, 16 pairs in each execution order. Both variants use seven shared conditioning queries, grouped_batch2 attention and the same original BF16 full head for the first three outputs.

The control attends over the 16,640-capacity accepted cache. The candidate copies the last 4,096 accepted rows into owned compact BF16 storage (40 MiB), preserving absolute RoPE and query positions. The persistent cache/frontier and scalar ingestion remain unchanged.

| Draft context | Mean consecutive matched tokens | Any match | All three | Complete proposal mean (ms) | Maximum (ms) |
|---|---:|---:|---:|---:|---:|
| full | 0.68750 | 14/32 | 2/32 | 37.05427 | 62.23056 |
| tail4096 | 0.62500 | 13/32 | 2/32 | 27.94785 | 60.86282 |

Tail4096 improved 3 anchors, tied 26 and worsened 3. Mean useful-prefix change: -0.06250 tokens. Mean complete proposal change (tail minus full): -9.10642 ms.

Each complete variant cost includes shared query preparation, its context preparation, backbone submission and all-row finite synchronization, full-head submission and validity synchronization, and host ID copy. The compact copy is included, with queued device work charged to the existing finite synchronization envelope. Dispatch alone is not isolated GPU execution.

Shared input preparation occurs once per pair but is attributed in full to each standalone variant cost. Pair reconciliation subtracts it once: full total + tail total − shared preparation. Mean adjusted body pair: 63.57974 ms; actual pair wall: 65.56715 ms; ownership brackets/gaps: 1.98741 ms.

The JSON retains all 32 measured pairs, the excluded warmup, match histograms, execution-order splits and every original cost row. No outliers were removed. This is shadow teacher agreement and component cost, with no Ready publication/acquisition or NPU execution. It supplies no native MTP acceptance or serving token rates; milliseconds are not converted to tok/s. Training with earlier-context attention does not establish equivalence to a trained sliding window.

Keep native/NPU attachment off: the compact tail reduced component cost but lost mean useful-prefix agreement on this panel.

The actual trial terminated successfully, owned native/worker cleanup qualified, and the normal 262,144-context server was restored ready/open before publication. Exact raw evidence, retirement/terminal receipts and memory minima are pinned in the JSON.
