# Completed K3 drafter shadow observation — 10 October 2026

One natural request used 16,384 actual input tokens and 128 output tokens. A GPU-only pretrained 500M drafter proposed three tokens at 32 fixed anchors after one excluded proposal warmup. Labels came from later actual scalar packets. All 127 scalar packets were received and all 32 measured proposals were completed. No proposals were published to or acquired by the native serving consumer; NPU was off.

| Consecutive correct proposed tokens | Anchors |
|---|---:|
| 0 | 19 |
| 1 | 8 |
| 2 | 3 |
| 3 | 2 |

The mean useful prefix was **0.625 tokens**. At least one token matched at 13/32 anchors (40.625%); all three matched at 2/32 (6.25%). These are shadow agreement statistics, not native MTP acceptance. They do not establish serving speed or equivalence for a future native speculative consumer.

| Measured proposal component | Mean ms |
|---|---:|
| Input preparation | 1.3934 |
| Drafter backbone and finite synchronization | 47.8156 |
| Full BF16 head and host token-ID copy | 6.3765 |
| Total proposal | 55.5855 |

The current attention path materializes repeated KV heads; the full BF16 vocabulary head is also retained. The synchronous proposal is too expensive to adopt on this evidence. A distinct grouped2d replay can assess the cost of avoiding repeated KV materialization before another serving trial. Connecting an NPU producer to this consumer is not justified.

The instrumented whole request took 46.32495 seconds. This is diagnostic wall time, including capture and shadow work; it is not a normal Prefill/Decode benchmark or NPU result. No new serving tok/s or native MTP acceptance is claimed.

Session 65898 exited 0. Its candidate owners were closed; 23 runtime evidence files were retained. The original context262144 server was restored ready/open and verified by the terminal checkpoint. Runtime minimum physical/commit reserve was 21.9509/113.6183 GiB (actual bytes in JSON). The service remains on the normal path. Full acceleration goal remains unachieved.

The adjacent JSON pins raw observations, diagnostic output, outcome, memory record, terminal checkpoint and retained runtime manifest. No public commit or push was performed.
