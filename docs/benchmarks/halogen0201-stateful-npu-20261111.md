# FLM 1.0.12 NPU state save/restore: exact component parity

The finite stateful component passes the original exact BF16 comparison: **32,001,030 values match across all 129 committed states**, with zero differing words and no relaxed tolerance. This qualifies the tested full-snapshot/always-restore path after speculative branches. **It establishes no Halogen speedup or native MTP acceptance.**

| Component observation | Sequential reference | Stateful scenario |
| --- | ---: | ---: |
| Seed 512 IDs through owned logits, ms | 395.5901 | 394.9269 |
| Authoritative one-ID append, mean ms | 21.0698 | 21.2687 |
| Authoritative appends | 128 | 128 |
| State-read calls / mean ms | — | 128 / 2.8180 |
| State-write calls / mean ms | — | 128 / 5.0369 |
| Speculative forward calls / mean ms | — | 253 / 21.1509 |

Each mode ran once in a separate fresh process. Means describe the calls in that finite run. Windows QPC records state API call intervals and forward-through-owned-logits intervals; the latter include CPU copy/argmax. Row-file writes are separate. These are not pure NPU kernel timings and are not converted into measured engine tok/s. The additional scenario work tests correctness; it is not an optimized engine on/off comparison. [Exact numbers and evidence](halogen0201-stateful-npu-20261111.json).

## What is qualified

The component uses the coherent FLM 1.0.12 Windows XRT Qwen3.5-0.8B-NPU2 runtime. Its exported state API returns version 1 and an AMD64 table size of 72 bytes. A library-owned opaque state is allocated and freed through that table before engine destruction. Each snapshot uses `kv_from=0`; full restore recovers the recorded context length and recurrent/KV state. Owned logits are retained separately because the state API does not restore them.

Both modes seed the same last 512 prompt IDs and commit the same 128 recorded target IDs through local context 640. The scenario obtains up to three proposed IDs, consumes at most two speculative inputs, always restores its full snapshot, then appends only the true next target ID. The final proposal narrows safely to one ID. All 248,070 shared-vocabulary BF16 values at every committed state are finite-checked and compared to the sequential reference; the comparator also reconstructs lowest-index greedy IDs from the complete rows.

Forced zero-, partial- and full-match fixtures at steps 0, 15 and 16 exercise rollback. Their verified prefix lengths are 0, 1 and 3. They deliberately use recorded labels and **are not prediction-quality samples**. Even the full-match fixture restores its snapshot: retaining a successful speculative state or using `state_write_kv` is not qualified by this test.

The committed-state next-ID agreement, evaluated before fixture changes, is **66/128 = 51.56% offline**. Separately, the 125 non-forced proposal cycles have matching-prefix lengths 0/1/2/3 in 61/37/16/11 cycles. Neither result is native MTP acceptance. The teacher trajectory is the excluded paired2048 target warmup of one exact, non-repeated 8,192-token document, distinct from the promoted paired8192 output trajectory. No 16K family is included.

The state API estimates 25,829,376–27,389,952 bytes for the saved contexts. These are **API size estimates, not independently measured allocated bytes**. Actual memory admission and runtime reserves were monitored separately.

## Execution, scope and source provenance

Both owned native jobs exit 0 without overlap or automatic retry. Actual loaded Qwen/Q4 DLL and System32 XRT paths and hashes match the selected inputs. Entry admission is 22/22 GiB, runtime reserve 18/18 GiB and the deadline is 120 seconds per process. All four GPU admission receipts pass; minimum observed reserves are 21.5451 GiB physical and 111.1175 GiB commit. The GPU profile/run seal remains unchanged during the jobs, and port 8840 is ready at their terminal snapshot. No resident stateful NPU producer is enabled.

The [canonical source package](../../scripts/benchmarks/halogen_flm_stateful_replay/README.md) contains the byte-identical measured C++ host, comparator and 13 CPU fixtures. Relocation changes only the comparator's repository-root index; normalized AST equality and exact host/test bytes are checked. All 13 canonical CPU tests pass. There is no canonical native rebuild or repeated hardware measurement. The frozen private executable and raw evidence remain intact.

Independent native audit SHA256: `bbd9cb310715398d7e0fea29a560eeadafc012081eef219db7d8cb6993d4122c`. Native acceptance, NPU engine prefill/decode rates, arrival before target demand and full-engine gain remain null. Live publication, retained-state optimization and an actual engine benefit require separate evidence; the full acceleration goal remains open.
