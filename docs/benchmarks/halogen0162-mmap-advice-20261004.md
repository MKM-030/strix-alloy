# Halogen lookup mmap advice: rejected on physical reserve

The candidate setting `HALOGEN_FLASH_NGRAM_RANDOM=0` completed zero requests.
The independent guard stopped its first prefill when available physical memory
fell below the unchanged 18-GiB reserve. It has no throughput result and is not
selected by a production profile. The experiment does not isolate whether the
advice setting, file-cache residency or another allocation caused the crossing.

The planned order was stock A / advice 0 / stock B. All used v2, capacity 65536,
initial target 32768, Exact prompt cache and configured MTP depth 2, with two
three-turn conversations, temperature 1, top-p .95, top-k 20, low thinking and a
1536-token output cap. The tracked article client was unchanged. Stock B was
not run after the failed candidate.

| Result | Stock A | Advice 0 |
| --- | ---: | ---: |
| Completed requests | 6 | 0 |
| Initial prefill tok/s | 1039.00 | Unavailable |
| Weighted sampled decode tok/s | 40.64 | Unavailable |
| Accepted / proposed drafts | 2094 / 2497 (83.86%) | Unavailable |
| Normalized three-turn seconds | 104.84 | Unavailable |
| Actual six-request wall seconds | 180.02 | Unavailable |

Stock A generated 4623 tokens, retrieved 14/14 fixture values and had no output
cap hits. These are the article client's phase-rate and normalized-conversation
definitions, not the separate greedy 8K PP/TG control. The candidate guard
recorded **17.881542 GiB** physical availability and **110.677952 GiB** commit
headroom. No reserve was reduced to obtain a measurement.

Backend cleanup and memory recovery passed. The backend deliberately retained
its ownership lock after the guard failure, so the coordinator's complete
cleanup gate failed. Its original `cleanup=false` and failed result remain
unchanged. A subsequent recovery receipt verified the exact owned container was
exited (`Running=false`, `Pid=0`, `OOMKilled=false`), both owner PIDs were absent,
known ports were closed and memory recovery had passed. Only that inactive
matching lock was moved into its service evidence directory. This later
retirement is not substituted for the original coordinator result.

The [evidence JSON](halogen0162-mmap-advice-20261004.json) retains the original
result fields, guard, terminal and recovery receipts, and artifact hashes. Raw
files remain in ignored `server/.local/article0162-20261003` and
`backends/halogen-wsl2-0.16.2/.local/services/e7bf6701702443f88ae7e9a8d2c91033`.
