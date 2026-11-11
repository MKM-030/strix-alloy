# Halogen 0.20.1 ready integer-proposal consumer

The registered Stock / Oracle / Stock experiment completed all 12 requests and restored authenticated normal serving on 11 November 2026. An ideal ready-ID consumer reaches **65.43 RAW decode tok/s**, versus 46.46 and 43.82 in the two stock controls, with exact matching target output IDs and text. This demonstrates a useful GPU consumer mechanism. **Future target IDs come from the excluded first stock warmup; no NPU prediction or NPU speedup was measured.** The oracle remains disabled for normal users.

| Variant | Actual input / output tokens | RAW prefill tok/s | RAW decode tok/s | Whole HTTP mean, s | API neural head accepted/drafted | Native/API lookup accepted/drafted |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Stock before | 8192 / 128 | 1323.32 | 46.46 | 8.9832 | 189/318 = 59.43% | 0/0 |
| Ready future-ID oracle | 8192 / 128 | 1384.93 | 65.43 | 7.9166 | 0/33 = 0% | 261/261 = 100% |
| Stock after | 8192 / 128 | 1220.61 | 43.82 | 9.7163 | 189/318 = 59.43% | 0/0 |

Each arm excludes one warmup and includes all three measured requests. No individual best run is selected. Input prefix, 128 output IDs, output text, finish-at-length and output cap match across all twelve captures. Decode rises 40.82% and 49.30% against the respective controls. These are finite-run comparisons; RAW clock brackets in the [numeric export](halogen0201-external-oracle-20261111.json) represent measurement-clock bounds, not statistical confidence intervals. Both controls drift, and all rates include the retained observer/trace overhead.

Prefill configuration is unchanged. The table preserves observed prefill rates without attributing their variation to the decode-only consumer. Neither phase result is a claim about a real predictor's end-to-end performance.

## What was actually consumed

Each candidate request records 39 same-process queries, 39 oracle hits and 117 copied IDs, using one 592-byte pre-generation datagram. No request records rejected datagrams, fallback, lead mismatch or receive errors. The original target still verifies proposals and supplies corrections; the oracle does not change target logits, weights or rollback.

Native lookup counters show 29 verification rounds and 87 drafted/accepted IDs per candidate request, pooled to 261/261 for the three measured requests. Ten copied batches per request therefore do not become lookup-verification rounds. Existing opening/constraint admission remains active; these counters alone do not uniquely attribute that gap to one branch. The residual neural path has 10 rounds and 11 drafts with no accepted draft per request. Its 0/33 head counter is a different routed workload from the stock head counter; this is **not 100% MTP acceptance** and does not establish a neural-head quality regression. Copied IDs, lookup drafts and all-neural head counters remain separate. Independent reconstruction of full API neural accepted counts remains unavailable.

The oracle selects the before arm's excluded warmup0 prospectively, never the fastest run. All stock repeats produce the same IDs. The derived bundle and the API/native ID captures bind exact request IDs, epochs, input prefixes, output counts and cancellation state. The engine socket and stats page avoid Windows per-token calls. No NPU producer was attached or invoked.

## Protocol and evidence

The exact non-repeated War and Peace request uses temperature0/seed1, Cache Off/no_store and a 128-token cap. Fixed settings are 0.20.1 v2, context/pool32768, one slot/concurrency one, paired2048, native gate0.90, Q4 draft vocabulary, PLD3,3, Thinking/Vision Off and prefetch zero. [Preregistered protocol](halogen0201-external-oracle-plan-20261111.md), plan SHA256 `4f5fcd6a0cb002972449c3814d80bf134c3690107ebef280299044e7f126d71e`.

All 38 explicit plan source roles retain their hashes. Independent review identified two consumed support roles omitted from that plan's list: the shared export helper and RAW binding JSON. A supplemental observation saved during before startup pins their exact bytes; both also match the hashes already registered in the earlier paired4096 protocol. The executing plan was not changed. This source-coverage omission is retained rather than claiming every transitive source was prospectively listed.

Root reran 28 focused CPU tests before launch. Independent final audit reruns native-ID and RAW validation for all twelve requests, confirms resource evidence and exact restoration of all 47 normal source-manifest members, and binds authenticated health/models plus the restored consumer selection. Audit SHA256: `f3f8f04879c38e44152e63b8bf6a7683a85a5254c5d0a029a8702e85b406c5f3`. Session92122 is terminal with exit0. The original normal server was restored at 03:50 UTC, before the separately authorized paired8192 serving promotion.

The result justifies further work on a real prefix-bound, asynchronous proposer. That producer still needs native numerical parity, actual readiness before target demand, and a full on/off engine comparison. Existing slow projection/ready64 candidates remain off. The full acceleration objective is unachieved.
