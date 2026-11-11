# Authoritative NPU batching: negative native component result

The tested FLM 1.0.7 vector-prefill route is unsuitable for authoritative catch-up. Both batch widths **fail the original exact BF16-word criterion** and take longer than scalar forwarding for the same 128 recorded target IDs. Neither implementation is enabled. These component measurements establish no Halogen token-rate improvement.

| Native component observation | Scalar reference | Bulk 2 | Bulk 4 |
| --- | ---: | ---: | ---: |
| Authoritative append calls | 128 | 64 | 32 |
| Mean call through owned logits, ms | 22.3607 | 328.9817 | 333.0298 |
| Total append processing for 128 IDs, ms | 2,862.1677 | 21,054.8307 | 10,656.9546 |
| Total append time / scalar | 1.00× | 7.36× | 3.72× |
| Compared full-row endpoints, including seed | — | 65 | 33 |
| Endpoints failing exact word equality | — | 64 | 32 |
| Differing BF16 words | — | 15,560,897 | 7,779,567 |
| Largest absolute logit difference | — | 4.62109375 | 3.4921875 |
| Endpoints with a different greedy ID | — | 13 | 3 |

All non-seed bulk endpoints differ from the scalar reference. Matching greedy IDs at other endpoints do not satisfy the unchanged zero-different-word requirement. The numerical failures are preserved rather than accepted with a wider tolerance. [Numeric summary and evidence](halogen0201-bulk-npu-20261111.json).

The times use Windows QPC from operation start to owned logits, including native-library processing and the CPU copy/argmax. Snapshot writes are timed separately and excluded. Mean call times have different batch sizes; the total-append row compares the same 128 authoritative IDs. These are finite component observations, not pure NPU kernel timings, measured engine tok/s or native MTP acceptance.

## Workload and comparison

Three fresh native processes run sequentially using the retained typed Qwen3.5-0.8B-NPU2 engine and FLM 1.0.7 runtime. Each clears context once, seeds the same last 512 prompt IDs and consumes the same 128 already recorded target IDs through local context 640. Scalar uses `forward`; the two candidates use vector `prefill` for exactly two or four authoritative IDs per call. No speculative ID is fed to a model.

The teacher sequence comes from the excluded paired2048 target warmup of one exact, non-repeated 8,192-token document. It is separate from the promoted paired8192 output trajectory. No 16K teacher family or arbitrary production batching is qualified here.

The independent audit finite-scans all 227 complete snapshots and reconstructs each lowest-ID greedy result. It independently checks every BF16 word at all 65 bulk-2 and 33 bulk-4 endpoints against the matching scalar context: 16,124,550 and 8,186,310 compared values respectively. All three native processes finish with exit code 0; successful execution does not imply numerical equivalence. The earlier [qualified scalar growing component](halogen0201-growing-npu-20261111.md) remains a separate result.

## Ownership and server recovery

The actual loaded Qwen, Q4NX and System32 XRT paths and hashes match the retained runtime pins. The compiled executable and static payload-import report are pinned; complete Windows API-set and OS-internal closure is not claimed. Nine focused source tests pass. No driver, model, BIOS, voltage or global WSL setting is changed by this study.

The old GPU server had already failed when the initial bulk attempt stopped at preflight, before any NPU call. A normal lifecycle recovery established a fresh server before this study. This incident is not attributed to the new NPU component, and the wall-clock watchdog defect is not presented as a proven cause of that particular shutdown. The recovery's short `READY` response is a functional smoke, not a performance benchmark.

All three owned NPU jobs close without automatic retries or overlap. Entry admission is 22/22 GiB and runtime reserve is 18/18 GiB, with a 120-second deadline per process. Six GPU admission receipts pass. Minimum observed reserves are 21.3358 GiB physical and 112.4244 GiB commit.

During the actual NPU jobs, the fresh GPU server retains controller 42440/backend 43816 and its paired8192 profile/run seal. It is ready on port 8840 at the terminal snapshot. Later server lifecycle changes are separate. No bulk producer or resident NPU helper remains enabled.

Independent terminal audit SHA256: `edec19de7b0782d3861ba2ef36a882ea8b5248ce0ae22794b6a928f005874f09`. Raw rows, provider observations, QPC values and failed comparisons remain preserved locally. NPU engine prefill/decode rates, native acceptance, target readiness and full-engine gain remain null. These two vector-prefill implementations are rejected; the full acceleration goal remains open.
