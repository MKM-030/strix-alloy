# Halogen 0.16.2: natural 16K native batch experiment — 2026-10-06

**No improvement adopted.** Both individual windows completed, but the candidate generated different greedy text. The final stock measurement window was not admitted: Windows reported 2.884% utilization on a PID 4 System copy engine against the fixed 2% preflight threshold. This observation does not identify a foreign workload. The original server was restored, verified ready/idle and left open. No cohort was retried.

The frozen request contains exactly **16,384 complete-framed input tokens and 128 output tokens**, one 66,336-character *War and Peace* prefix plus the unchanged story task. There is no padding or repeated source. Each completed window has one excluded warmup and three measurements, temperature 0, seed 1, thinking off, cache off, MTP2/PLD3,3, one slot and 262,144-position capacity. Rates are native phase measurements calibrated against guest raw/monotonic and host QPC clocks.

| Window | Prefill chunk / maximum tokens | Prefill tok/s | Decode tok/s | Native accepted / drafted | Mean request wall, s |
|---|---:|---:|---:|---:|---:|
| stock_before | 8192 / 8192 | 1206.59 | 36.58 | 186 / 387 (48.06%) | 17.161 |
| candidate16384 | 16384 / 16384 | 1227.50 | 35.91 | 186 / 381 (48.82%) | 16.993 |
| Restored stock | 8192 / 8192 | Not measured | Not measured | Not measured | Not measured |

These are measurements of two different continuations, **not a qualified optimization delta**. The candidate produced 186 accepted drafts out of 381 attempts versus 186/387 for stock; the larger ratio cannot be claimed as an acceptance improvement with different output and an incomplete bookend comparison. Both completed windows passed exact usage/native 16,384/128 counts, within-window output equality, integer draft accounting, zero disk restores, gateway counter increments and final native idle checks. Request-file, normalized request and prompt hashes match across the two windows; output hashes do not.

Stock output: `bc179b2873f085833dbd1ec05e9aba7703957dfafafdab71bba3d3cfb2f32e4d`. Candidate output: `b7201ef3158b6e2a77ff10ce51b35fe5532c77f67d1d0a22e994cde76dd40a5b`. The first text difference is at character 28: stock says “did not roll”; candidate says “did not merely roll”.

Both native controls were changed together, from 8192/8192 to 16384/16384. Startup logs show 5.6 versus 7.8 GiB working memory, rounded; no exact byte allocation or exact-44-GiB sufficiency claim is made. The unchanged admission gates remained 44 GiB physical/131 GiB commit for 60 stable seconds, 22 GiB before requests and 18 GiB continuously. Whole-lifecycle observed minima were 28.55 GiB physical and 120.17 GiB commit.

The earlier chunk-16384 cell used max_prefill_tokens=32768 and had adverse results in the [upgrade comparison](halogen0162-upgrade-20261003.md); it is a different profile. This experiment supplies no improvement relative to historical synthetic 8K/16K fixtures and no new long-context rates. It changes native GPU prefill batching; it neither implements a vector kernel nor offloads work to CPU/NPU.

The [standing hardware policy](../research/halogen-npu-compact-pld-proposer-plan-20261005.md) requires each development to assess GPU, CPU and NPU relevance to actual target Prefill, Decode and native MTP acceptance. Component milliseconds and offline draft matches remain separate from engine token rates.

Final controller: 29004 / `9dba1390ccc24bcd89a383e639c18429`. Backend: 5560 / `21da7e1c5b724668a561350e8480a28e`. Port 8840, original 8192/8192 profile, context 262144, cache off, ready/idle, NPU disabled. Own measurement/lifecycle session is terminal; persistent server remains open.

Raw local evidence: `C:\Projects\strix-alloy-clean\server\.local\optimization9h-20261004\natural16k-native-batch-9075904b759e48c589fa461342269ddb`. Frozen preparation: `C:\Projects\strix-alloy-clean\server\.local\optimization9h-20261004\natural16k-prepared-2e01b684230e49e4b2bfc0c1c29fd3dc`. Compact raw samples, clock/reserve evidence, seals, telemetry and restoration proof are retained in the [JSON evidence](halogen0162-natural16k-native-batch-20261006.json), SHA256 `199feee103bd7a19f8832b6bc5ce5a61f01647de91e8247eb512bdf5529302ee`.
