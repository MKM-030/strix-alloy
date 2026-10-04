# Halogen 0.16.2 direct lookup placement — 4 October 2026

E does not beat both stock means; improvement over first stockA alone is not evidence of a placement gain.

32K occupied input at 64K capacity; two three-turn sampled conversations per cell. Separate from 8K greedy controls. Coding/review outputs are ungraded; retrieval equivalence is observed 14/14 only.

No OS cache flush was performed. Sequential stockA/E/stockB results do not establish a causal placement gain.

The configured startup MTP depth is 2. This temperature-1 sampled workload uses one draft proposal per sampled round and a two-token verification input; it does not exercise the greedy depth-2 chain. See the pinned [sampled MTP dispatch evidence](../../research/halogen-sampled-mtp-depth-20261004.md).

Normalized conversation time is the sum of `TTFT + 1000/decode tok/s` over three turns, averaged across two matched repetitions. Actual wall time is the sum of all six observed requests. Prefill is the mean of two cold initial prompts; decode is weighted by generated tokens, including reasoning.

| Cell | Normalized 3-turn seconds, mean [rep0, rep1] | Actual six-request wall s | Prefill tok/s | Decode tok/s | Accepted/proposed | Retrieval | Capped / clamped / EOS |
|---|---:|---:|---:|---:|---:|---:|---:|
| lookup-stocka | 127.828 [137.017, 118.639] | 223.136 | 731.50 | 36.07 | 2094/2497 (83.86%) | 14/14 | 0 / 0 / 6 |
| lookup-e | 114.183 [116.900, 111.465] | 196.400 | 901.00 | 38.49 | 2094/2497 (83.86%) | 14/14 | 0 / 0 / 6 |
| lookup-stockb | 104.319 [105.850, 102.787] | 180.124 | 1033.54 | 40.72 | 2094/2497 (83.86%) | 14/14 | 0 / 0 / 6 |

| E compared with | Normalized change % (positive=faster) | Actual wall change % | Matched normalized rep0 / rep1 % |
|---|---:|---:|---:|
| lookup-stocka | +10.67 | +11.98 | +14.68 / +6.05 |
| lookup-stockb | -9.46 | -9.04 | -10.44 / -8.44 |

All cells completed six requests and stopped with cleanup/recovery proven. Physical and commit request floors were at least 18 GiB. Compute manifests match after normalization of only the lookup mount/qualification and unique lifecycle mount paths; entrypoint and source hashes remain checked.

The JSON retains per-request canonical/file hashes, request options and message-content hashes/byte counts, output/reasoning hashes and token counts, timing/clock/cache counters, memory floors, lifecycle identities, lookup receipt and all retained artifact/source/profile/client/corpus hashes. Full prompts and reasoning text, credentials and raw Docker inspection data are omitted.

Lookup-read timings below come only from each exact owned engine log. They may include startup/calibration; client-window links are approximate UTC attribution. Unlogged lookup reads have unknown cost.

| Cell | Logged lookup reads (tokens, seconds) |
|---|---|
| lookup-stocka | 32768, 22.5s; 32768, 10.1s |
| lookup-e | 32768, 11.4s; 32768, 9.5s |
| lookup-stockb | 32768, 11.4s; 32768, 9.7s |

This 32K sampled retrieval/implementation/review workload remains distinct from the 8K greedy controls. The generated implementation/review is ungraded; 14/14 retrieval supports only the observed fixture equivalence.

Evidence and source hashes: [results.json](results.json).
