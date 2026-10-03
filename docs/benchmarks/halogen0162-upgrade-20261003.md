# Halogen 0.16.2 upgrade and controlled tuning — 2026-10-03

Status: investigation and selection complete. Retain **pristine stock compute, MTP depth 2 and prompt cache Off**, with prefill chunk and token arena overrides unset; the selected stock profile SHA256 is `e535484cdfd5ce3de4afc110a630296e5e5c556e2968ee22d118416cc6e37c1a`. Late stock removes a useful kernel-tuning advantage. Flexible fails correctness; Exact supplies no observed reuse benefit or warm-hit qualification. The focused default-cache cells are validated through a separate derived receipt after parent aggregation fails; that infrastructure failure remains explicit. No tuned kernel or optional Exact recipe is promoted.

The adjacent [sanitized JSON evidence](halogen0162-upgrade-20261003-evidence.json) retains artifact digests, experimental identities, actual token counts, descriptive timing statistics, counters, and lifecycle proof. It excludes secrets, private absolute paths, full prompts, and output text. Full raw artifacts remain local and ignored.

## Machine and isolation

Ryzen AI Max+ 395 / Radeon 8060S (gfx1151), 128 GiB unified memory, Windows 11 and Ubuntu 24.04 WSL2 through DXG. All inference uses the authenticated Alloy controller, one v2 engine, one slot, context capacity 262144, and at least 18 GiB physical RAM and commit headroom. No model download, BIOS, driver, firmware, global WSL change, or NPU contention run.

Raw artifacts are retained under ignored `server/.local/upgrade0162`. The populated w4b lookup source was reused; the native w4b path was an empty sparse placeholder and was not used. Existing checksum receipts were checked against file identities.

## Exact release and bridge binding

- Image digest: `sha256:0c61bf84ac22308a53f5d1ca6b86806702d7039e5ebc51cae4c66621b92fe04a`.
- Engine SHA256: `ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b`.
- Entrypoint SHA256: `ae2face04d9fcaaab3df0cd6a3cab047c6acd6322bc69e8d3d632632508b8f1b`.
- Adapted entrypoint SHA256: `e68722b13e6d5f5cb43fbda89f3ea3c92c13be5a8da96113c91b4cfee08a1033`.
- DXG SHA256: `0de8e26350933754d3d9ead9446c39e04792a2bef68d1b6df97950d07312b9d6`.
- The handover's `0x1876a40` is a **file offset**. The reviewed executable mapping places the hook at **RVA `0x1877a40`**. Exact bytes, enclosing function identity, stack offsets, trampoline preservation, and CPU fixtures were checked.
- Populated w4b SHA256: `9c116bbc01f77b7a15464c1a124eb3325b286089b8a2a6f2856c9b246a235bd6`.
- v2 core: 66687678432 bytes, SHA256 `71246c6ab3fc1de2cf06326f18e275fe9c2a18366d646ed3357d194c884fc687`. Populated w4b source: 124068083904 bytes.

The v2 bridge, private-RW registration, source manifests, image/API identities, ownership checks, and cleanup/recovery checks remain fail closed.

## Fresh sealed stock control

`stock-sealed-fixed` is the candidate timing control after the reviewed service, n-gram integrity, token-arena and agent-grading fixes. Its profile SHA256 is `e535484cdfd5ce3de4afc110a630296e5e5c556e2968ee22d118416cc6e37c1a`; cold prompt manifest SHA256 is `a799260384b71e1df6cbf011d3378d9a85f01a6d0d36e16b354f7bebee7c7ca7`. The frozen workload/tokenizer and source pins are retained with the raw identity artifacts. Cache is Off, MTP depth is 2, prefill chunk is unset/auto, and the token arena is 32768.

Cold inputs are exact server counts. Each cell has one warmup and three retained repetitions, alternating serial/MTP order. TG requests generate exactly 128 tokens, intentionally ending at the benchmark cap; this is throughput evidence, separate from completed coding outputs. Rates below apply the measured monotonic/raw clock ratio; values are mean ± sample standard deviation. Raw phase rates, independent client wall intervals and individual calibration ratios are retained in the public evidence.

| Input tokens | PP only, tok/s | Serial TG128, tok/s | MTP depth 2 TG128, tok/s | MTP acceptance |
|---:|---:|---:|---:|---:|
| 512 | 1227.13 ± 5.24 | 35.65 ± 2.09 | 50.27 ± 0.72 | 63.96% |
| 2048 | 1447.08 ± 195.70 | 35.95 ± 0.19 | 49.24 ± 0.11 | 63.96% |
| 8192 | 1555.45 ± 8.44 | 35.54 ± 0.32 | 47.04 ± 0.04 | 60.00% |
| 16384 | 1508.43 ± 11.49 | 35.69 ± 0.09 | 44.87 ± 0.23 | 56.30% |

All 36 retained cold samples and 12 recorded warmups completed with zero cached input. Twelve within-cell repeat checks and sixteen serial/MTP warmup/retained output comparisons passed. The PP2048 samples were 1568.40, 1551.53 and 1221.31 tok/s; the slower sample is retained. No temperature/power telemetry establishes the cause of this variation.

Clock correction remains an approximation over the full request window, not proof that each phase has the same clock rate. Material stock windows include PP512-only repetition 3 (`monotonic_per_raw=1.083342`) and serial TG512 repetition 1 (`1.036183`). Their original raw measurements remain intact; deterministic output, memory and lifecycle qualification do not remove this phase-timing uncertainty.

Structured quality passes **10/10 functional and strict checks in each mode**, with matching full output hashes. The six available first-token top-5 proxy comparisons have zero reported probability difference. The two grammar-masked JSON probes remain unavailable by design. Each mode retains all 27 successful auxiliary/probe/repetition calls.

The fresh agent recordings reuse the earlier immutable 8456-token system fixture under the strengthened grader. All eighteen outputs finish with `stop`, pass grading and retain complete actual assistant messages. The nine serial/MTP input/message hashes, actual counts and finish reasons match. Actual input/output counts remain 8532/88, 8841/44 and 8953/208.

| Agent turn | Serial wall, s | MTP wall, s |
|---|---:|---:|
| Initial function edit | 9.80 ± 2.45 | 7.68 ± 0.11 |
| Synthetic tool result and tests | 7.44 ± 0.13 | 7.02 ± 0.03 |
| Follow-up complete function | 12.23 ± 0.09 | 9.86 ± 0.13 |

Mean conversation time is **29.47 ± 2.45 s serial** versus **24.55 ± 0.22 s MTP**; total measured-call wall time is 88.42 versus 73.65 s. MTP accepts 699 of 792 drafted tokens (88.26%). All agent cache/disk-restore counters are present and zero. Serial draft counters are present and zero, with acceptance undefined. These sequential serial-then-MTP timings are descriptive, with three conversations per mode.

Across all recorded cold calls, sampled minima are **26.99 GiB physical** and **117.31 GiB commit headroom**. Across the fresh agent/quality calls, the minima are **25.70 GiB physical** and **115.99 GiB commit headroom**. The independent controller full-run physical minimum is **25.81 GiB**; its sampling intervals differ, so this need not equal the per-call minimum. The controller does not retain a full-run commit minimum. All retained samples exceed the 18 GiB reserve.

The retained controller exited normally. Terminal controller/backend states are both `stopped`, and backend outcome records `ready=true`, `cleanup=true`, `recovery=true`; result records `passed=true`, `cleanup_proven=true`, `promoted=false`. Startup took 207.48 s, and the complete startup/measurement/cleanup sequence took 909.35 s. This qualifies the stock control; it does not select a tuned candidate. The fresh control does not include the broad suite, which remains required for selected finalists.

## Earlier stock cold measurements

These are the completed `stock-cold` measurements from before the final service, n-gram verification, and agent-grading fixes. They remain evidence of that exact run. Candidate timing comparisons use `stock-sealed-fixed/cold`, measured after the source fixes; the earlier numbers are not substituted for that control.

Stock means the pinned image's compute defaults, with the necessary WSL/DXG memory bridge and authenticated gateway. Inherited 2048 prefill/arena, route-GEMM, and top-k replay overrides were removed. Effective MTP depth is 2 and the upstream token arena is 32768. Prompt cache is Off.

Exact server input token counts, TG128, temperature 0, one warmup and three retained repetitions per cell; serial/MTP order alternates. Phase rates are corrected with the existing WSL monotonic/raw/Windows-QPC probe. Values are mean ± sample standard deviation.
| Input tokens | PP only, tok/s | Serial TG128, tok/s | MTP depth 2 TG128, tok/s | MTP acceptance |
|---:|---:|---:|---:|---:|
| 512 | 1216.26 ± 4.58 | 36.38 ± 0.37 | 49.26 ± 0.68 | 63.96% |
| 2048 | 1448.77 ± 10.83 | 35.63 ± 0.31 | 48.25 ± 0.04 | 63.96% |
| 8192 | 1511.14 ± 1.63 | 36.02 ± 0.68 | 46.05 ± 0.05 | 60.00% |
| 16384 | 1463.91 ± 3.90 | 35.40 ± 0.03 | 44.48 ± 0.11 | 56.30% |

The 36 retained cold samples completed, with 12 additional recorded warmup samples. Their sampled physical-memory minimum was 28.71 GiB, with approximately 119.34 GiB commit headroom. The cold summary excludes warmup/calibration calls from its minimum. The evidence file also computes the minimum over all 48 recorded calls; calibration calls require controller telemetry. The controller retains a full-run physical-memory minimum, but does not retain a full-run commit minimum, so terminal commit snapshots are not reported as commit minima.

The 1650–1750 PP8192 range was an engineering target for these earlier measurements. The later pristine-stock confirmation below records 1714.94 ± 17.55 tok/s under its own retained conditions. External upstream measurements and historical 0.15.1 results use different conditions and are not matched controls here.

## Quality evidence and API limits

The original harness artifacts remain: 8/10 strict checks in both modes. One code result was a harness false negative: valid `isinstance(v, int)` was rejected by the restricted evaluator. The corrected evaluator runs bounded Python unit checks and keeps raw outputs/hashes.

Corrected unconstrained stock: **10/10 functional, 9/10 strict** in both modes. The tool JSON has the correct object inside a Markdown fence; its strict format failure is preserved. Serial/MTP full output hashes match across the ten cases, including five interleaved state-leakage repetitions. The suite also covers arithmetic, German, Cyrillic, JSON, executable Python, long-context retrieval, and multi-turn memory.

With `response_format={"type":"json_object"}` on the two JSON cases, stock achieves **10/10 functional and strict checks in serial and MTP**. Full output hashes match between those constrained modes. The earlier failed structured artifacts are retained: their functional JSON request succeeded, then an incompatible logprob probe returned HTTP 400.

The pinned API explicitly rejects logprobs with response_format because the grammar mask selects the token. The corrected harness skips those two constrained probability probes and labels them unavailable due to the grammar mask. Free-form requests expose top-5 probabilities for one generated token. This provides a first-token target-model prefill proxy; it does **not** prove MTP draft-logit equivalence or full-logit equivalence.

Quality minima include every successful auxiliary/probe/ACK/distractor/repetition call (29 unconstrained, 27 constrained). Controller observations cover the full managed run. Long-needle labels 8192/16384 are approximate text cases: actual stock API counts are 9870/19698, distinct from the exact cold benchmark.

## Earlier broad and agent workloads

The broad suite retained three repetitions of each of ten cases in each mode, plus one separate warmup call per mode. All 30 main-call input/output hashes and actual token counts match between serial and MTP. Its PP labels are text targets: actual API input counts are 522/2058/8202/16392. The occupied 8192/32768 cases report 8200/32776 actual input tokens and exactly 128 generated tokens. These remain historical stock results; they are not matched timing controls for the later source revision.

| Broad case | Actual input/output tokens | Serial wall, s | MTP wall, s |
|---|---:|---:|---:|
| Short TG128 | 28 / 128 | 4.04 ± 0.71 | 3.21 ± 0.30 |
| Occupied 8192 TG128 | 8200 / 128 | 10.05 ± 0.52 | 9.28 ± 0.18 |
| Occupied 32768 TG128 | 32776 / 128 | 27.51 ± 1.90 | 27.27 ± 0.69 |

The separate agent workload uses an immutable shared system prefix of **8456 tokenizer text tokens**, repository-source snapshots, deterministic corpus records, a code edit, an explicit synthetic read-file/test-report payload, and a follow-up edit. Every actual assistant message is retained in the next request, and the complete three-turn conversation repeats three times. All nine calls per mode are measured; this workload has no separate warmup request.

| Agent turn | Actual input/output tokens | Serial wall, s | MTP wall, s |
|---|---:|---:|---:|
| Initial function edit | 8532 / 88 | 10.55 ± 2.31 | 8.09 ± 0.07 |
| Synthetic tool result and tests | 8841 / 44 | 7.98 ± 0.11 | 7.61 ± 0.05 |
| Follow-up complete function | 8953 / 208 | 13.05 ± 0.47 | 10.43 ± 0.02 |

All eighteen agent outputs finish with `stop` and pass the recorded grading checks. Serial/MTP actual assistant-message hashes, preserved prefixes, token counts, and finish reasons match, with one distinct output hash per turn across repetitions. The third turn needs 208 tokens; the fixed 256-token cap avoids the truncation that a 128-token cap would cause. A `length` result is retained as incomplete and cannot pass completion grading.

Mean complete-conversation wall time was **31.58 ± 2.71 s serial** versus **26.13 ± 0.10 s MTP**; total measured-call wall time was 94.73 versus 78.39 s. This is descriptive evidence from sequential serial-then-MTP runs, not an isolated causal estimate: the first serial call was slower. MTP reported 792 drafted tokens and 699 accepted tokens, **88.26% acceptance**. Cache Off reported `cache_n=0` on every call. Serial draft counters were present and zero; its acceptance is undefined, not a measured zero-percent acceptance. Missing counters remain unknown.

Every agent call has sampled physical/commit telemetry. Across both modes the minimum was **28.02 GiB physical headroom** and **118.45 GiB commit headroom**. These are sampled host-memory minima, not VRAM peaks. The original agent artifacts remain intact and their six turn-two outputs still pass the strengthened straight-line grader; the fresh recordings above provide the later harness identity for matched comparisons.

## Reviewed fixes before the sealed control

Independent review found and reproduced an agent-grading false positive: unreachable pytest assertions after an early return could pass. The grader now requires two distinct straight-line test functions containing the reviewed raises/call shape; the regression fails before the fix and passes after it. The original six turn-two outputs still pass the stronger grader, and a fresh recording is used for later matched comparisons.

The direct service guard now enforces 18 GiB physical and commit reserve, matching the managed controller. Every v2 startup also verifies the selected/default n-gram source against its pinned expected SHA256, complete file identity, and source path. The verified existing receipt was seeded into the package-local receipt only after a fresh WSL stat matched; no extra full-model hash was needed.

Explicit prefill chunks now retain `HALOGEN_MAX_TOK=32768`. Lower chunk sizes previously also lowered the arena; those would have changed two variables. Stock with no explicit chunk retains the pinned image defaults. Only the reviewed service and checkpoint-integrity source pins were refreshed.

The first `stock-sealed` attempt failed before measurement because the Windows venv executable was a launcher stub and its retained PID did not match the native controller child. Ownership checks rejected the mismatch and refused an unproven stop. The original failure, process-ancestry proof, and subsequent ordinary-stop proof remain archived. Manual cleanup proof records both controller/backend `stopped` and backend `cleanup=true`, `recovery=true`. The retry uses a verified interpreter/runtime and a new evidence directory; the failed attempt contributes no benchmark samples.

Verified offline checks after the fixes: **146 backend tests on Windows (19 skipped), 146 backend tests on WSL (3 skipped), 61 server tests, and 84 benchmark tests (1 skipped)**. Installed preflight passed without a build, download, configuration write, or model launch. Skips are retained as skips, not counted as exercised platform behavior.

Final offline checks of the unchanged measured public source repeat those same counts before any deferred reader patch. Separate ignored-helper checks pass eleven auto-cache checks, fifteen retry-bootstrap checks and nine derived-finalization checks; these are not added to the public-source suite counts. The evidence retains the final log digests.

## Controlled screening matrix

Each profile is independently derived from pristine stock, retaining depth 2 except the depth tests, cache Off, context/slot/model placement, authentication, and the 18 GiB reserve. Stock is remeasured after the reviewed source changes. The runner retains its controller process, pins profile/source/prompt identities, and verifies normal stop plus cleanup/recovery before the next engine.

- MTP depths 1 and 3: exact 512/2048/8192 inputs.
- Explicit prefill chunks 8192/16384/32768, arena held 32768: exact 8192/16384 inputs.
- Keep-trunk ON: exact 8192/16384 inputs; additional memory remains subject to the same reserve.
- Single internal controls at exact 8192 input: DN_SCAN=1, DN_FUSED=0, ATTN_QS=0, FA_OPT=7, FLASH_MOE_GEMM=0, FLASH_MOE_V2=2.

Every cell includes PP-only, serial TG128 and MTP TG128, one warmup and three retained repetitions. Cold repeat, cross-mode, prompt/request, and candidate/control hashes are compared explicitly. A cold `passed` summary alone does not prove cross-mode parity. Changed-hash candidates remain unpromoted; finalists need the broader functional/format/proxy gate.

Internal numeric limits are experiment-interface budgets, not advertised upstream ranges. Verified stock defaults include DN_SCAN=0, DN_FUSED=1, ATTN_FA=64, ATTN_QS=1, FA_OPT=5, FLASH_MOE_GEMM=8, and FLASH_MOE_V2=1. FA_OPT is a low-three-bit mask; V2=2 is a mode comparison and V2=0 does not universally disable that path. CACHE_RESERVE_MB defaults/bounds were not established, so it is not tuned.

The [pinned upstream flags reference](https://github.com/peonist-ai/halogen-flash-server/blob/7f31bbd4021f217a1be9776bdb7304bcf8eca62d/docs/FLAGS.md) identifies depth 2 as stock and separates documented deployment flags from additional internal kernel controls. The internal defaults above come from the pinned ELF audit; they are experimental screening controls here.

Three retained repetitions offer descriptive variation estimates. Sequential runs can be confounded with time; temperature/power telemetry was not captured, so no thermal-causation claim is made.

The first matrix sequence stopped after eight completed cells. Its `attn-qs0` attempt failed with `PermissionError` while reading controller state during readiness; no cold benchmark ran and no cold comparison exists. Terminal controller/backend states are `stopped`, with backend `ready=false`, `cleanup=true`, `recovery=true`. The failed attempt is retained in the evidence's failure section and excluded from completed-cell counts and performance selection. The fresh continuation uses `matrix-remaining-sealed`, preserving the first eight raw artifacts and the failed attempt.

The two matrix plans have identical source seals, pristine-stock profile identity, cold-control seal, native controller-runtime receipt and prompt-manifest digest. Each continuation profile also matches its original planned profile. Together the twelve completed cells retain 180 measured cold requests and 60 warmups. Cleanup/recovery passes for every measured cell; nine match stock cold output hashes, while Chunk 8192, DN_FUSED=0 and ATTN_QS=0 retain measured output drift.

### Completed screening results

The following rows include only completed cells. Positive wall change means slower than the fresh depth-2 stock control, negative means faster. Hash/lifecycle checks cover cold input/request/output parity, serial/MTP/repetition parity and ordinary cleanup/recovery; passing them does not supply finalist functional/format/broad qualification. Every candidate remains unpromoted.

<!-- SCREENING_RESULTS_START -->
Completed cells: **12/12**.

| Setting | Exact input | PP only, tok/s | MTP TG128, tok/s | MTP acceptance | MTP wall change vs stock | Cell parity / cleanup |
|---|---:|---:|---:|---:|---:|---|
| Depth 1 | 512 | 1211.81 ± 21.90 | 42.95 ± 2.77 | 67.11% | +14.70% | pass / pass |
| Depth 1 | 2048 | 1471.07 ± 209.00 | 43.01 ± 1.01 | 68.00% | +8.16% | pass / pass |
| Depth 1 | 8192 | 1622.92 ± 9.66 | 43.01 ± 0.64 | 67.11% | +0.99% | pass / pass |
| Depth 3 | 512 | 1191.08 ± 4.97 | 46.07 ± 0.83 | 50.33% | +7.92% | pass / pass |
| Depth 3 | 2048 | 1611.82 ± 13.51 | 46.08 ± 0.15 | 52.38% | +4.78% | pass / pass |
| Depth 3 | 8192 | 1705.36 ± 26.81 | 43.90 ± 0.10 | 49.02% | -3.09% | pass / pass |
| Chunk 8192 | 8192 | 1676.48 ± 79.10 | 46.65 ± 1.85 | 60.00% | -4.51% | fail / pass |
| Chunk 8192 | 16384 | 1679.76 ± 16.40 | 45.15 ± 2.24 | 62.50% | -6.31% | fail / pass |
| Chunk 16384 | 8192 | 1202.05 ± 20.98 | 47.07 ± 2.07 | 60.00% | +16.35% | pass / pass |
| Chunk 16384 | 16384 | 1263.76 ± 3.31 | 45.17 ± 0.85 | 56.30% | +16.74% | pass / pass |
| Chunk 32768 | 8192 | 1692.25 ± 80.76 | 44.64 ± 0.90 | 60.00% | -4.45% | pass / pass |
| Chunk 32768 | 16384 | 1706.94 ± 28.05 | 43.06 ± 1.19 | 56.30% | -6.68% | pass / pass |
| Keep trunk | 8192 | 1466.02 ± 13.68 | 44.55 ± 3.92 | 60.00% | +8.15% | pass / pass |
| Keep trunk | 16384 | 1431.31 ± 14.20 | 44.98 ± 0.65 | 56.30% | +5.83% | pass / pass |
| DN_SCAN=1 | 8192 | 1698.87 ± 75.63 | 46.75 ± 0.27 | 60.00% | -6.03% | pass / pass |
| DN_FUSED=0 | 8192 | 1476.96 ± 58.36 | 44.26 ± 0.11 | 54.55% | +3.71% | fail / pass |
| ATTN_QS=0 | 8192 | 1636.49 ± 12.84 | 44.84 ± 0.04 | 55.00% | -0.01% | fail / pass |
| FA_OPT=7 | 8192 | 1690.34 ± 77.39 | 46.84 ± 0.25 | 60.00% | -5.53% | pass / pass |
| FLASH_MOE_GEMM=0 | 8192 | 1672.43 ± 96.72 | 46.61 ± 0.34 | 60.00% | -5.15% | pass / pass |
| FLASH_MOE_V2=2 | 8192 | 1618.40 ± 86.15 | 46.41 ± 1.35 | 60.00% | -4.57% | pass / pass |
<!-- SCREENING_RESULTS_END -->

Depth 1 has higher acceptance but lower MTP decode throughput at every measured input. Its PP8192-only rate is 4.34% above this stock control, while its TG128 request takes 0.99% longer; the isolated cold screening does not support selecting it as the default.

Depth 3 records PP8192 at 1705.36 ± 26.81 tok/s, within the engineering target band, but MTP decode is 6.69% slower and acceptance falls to 49.02%. Its 8192-input TG128 wall time falls 3.09%, while 512/2048 wall times rise 7.92%/4.78%. Higher prefill rates also appear in the serial requests in this later run; sequential timing prevents attributing that PP increase to draft depth alone. This tradeoff requires broader matched qualification before any selection.

Depth 3 serial TG8192 has a material calibration difference: corrected PP is 1714.63 ± 35.41 versus raw 1667.21 ± 47.39 tok/s. Repetitions 2/3 have monotonic/raw ratios 1.057297/1.029213, while raw/QPC is approximately 0.999997/0.999990 and handshake uncertainty is below 0.0007 s. Depth 3 PP2048 repetition 3 has ratio 1.062263, and all six retained serial/MTP TG2048 windows are approximately 1.083333. Those measurements are retained with this caveat. The PP8192-only progression—stock 1555.43, depth 1 1622.93, depth 3 1705.36 raw tok/s—is also visible in raw prompt phases and independent client wall intervals; it is not explained by clock scaling, but remains confounded with run order. The completed later pristine-stock confirmation below records similar prefill improvement without a tuned kernel.

Chunk 8192 preserves the 8192-input cold output hashes, but all three retained TG128 outputs at input 16384 differ from stock in both serial and MTP. Prompt/request hashes match, and the candidate's own repeat/cross-mode hashes match. This is measured candidate/control output drift; the cell remains unpromoted despite successful cleanup. Its timing improvements cannot substitute for the required output/quality gates.

Chunk 16384 matches cold hashes but is slower in both modes: PP8192-only is 1202.05 ± 20.98 tok/s, 22.72% below stock, while its PP-only client wall rises 29.28%. Its MTP TG128 request walls rise 16.35%/16.74% at input 8192/16384, and every-call sampled physical headroom falls to 23.13 GiB. The observed directions also appear in raw phase rates and client wall; their cause is not isolated by these sequential runs.

The chunk cells also have material calibration windows. Chunk 8192 serial TG8192 PP is raw 1622.50 ± 77.60 versus corrected 1710.15 ± 3.27 tok/s; decode is raw 33.67 ± 1.68 versus corrected 35.49 ± 0.15. Two windows have ratio 1.083333. Chunk 16384 MTP TG8192 decode is raw 44.39 ± 2.03 versus corrected 47.07 ± 2.07, with ratios 1.083333/1.054271/1.043855. The independent request-wall comparisons and full raw/calibrated metadata remain visible alongside corrected phase results.

Chunk 32768 matches all cold hashes and records PP-only 1692.25 ± 80.76 / 1706.94 ± 28.05 tok/s at input 8192/16384. Independent PP-only request walls fall 7.81%/11.68%, and MTP TG128 walls fall 4.45%/6.68%. MTP decode rates nevertheless fall 5.10%/4.05% versus the earlier fresh stock control. Its every-call physical/commit minima are 25.34/115.74 GiB. Raw phase rates and client wall support the observed directions versus that earlier control without resolving the run-order confound. The later stock comparison below removes its MTP wall advantage, so it remains unpromoted.

Keep-trunk matches cold hashes but all six measured cohort request-wall means regress. MTP TG128 walls rise 8.15%/5.83% at input 8192/16384, and sampled physical/commit minima are 20.54/111.12 GiB. This run remains above the 18 GiB reserve but supplies no observed speed benefit for the extra retained trunk. Calibration differences, including 1.048543/1.083333 in serial TG16384, remain in the evidence.

DN_SCAN=1 matches all screened 8192-input hashes and has no material clock-ratio anomaly. PP-only is 1698.87 ± 75.63 tok/s, MTP decode 46.75 ± 0.27, and MTP/serial TG128 request walls fall 6.03%/5.17%. Sampled physical/commit minima are 22.81/113.10 GiB. This is 8192-only screening evidence. The later stock comparison below leaves only a 0.37% descriptive MTP wall difference; full-range and broad qualification are not pursued because no useful tuned advantage is established.

DN_FUSED=0 matches its own repeats/cross-mode outputs but differs from stock in every retained serial/MTP TG128 output at input 8192. Prompt/request hashes match and cleanup succeeds. Every request-wall mean is slower: PP-only +5.41%, MTP TG128 +3.71%, serial TG128 +1.18%. It remains unpromoted; the output incompatibility is preserved independently of its timing regression.

The fresh ATTN_QS=0 continuation completes and cleans up normally, but all three retained TG128 output hashes differ from stock in both serial and MTP; its own repeat/cross-mode hashes and prompt/request hashes match. PP-only is 1636.49 ± 12.84 corrected versus 1510.55 ± 11.85 raw tok/s; all three PP-only clock ratios are approximately 1.083369 and its independent request wall falls only 1.18%. MTP decode is 44.84 ± 0.04 tok/s and acceptance is 55.00%. MTP request wall is effectively unchanged (−0.01%), while decode falls 4.68%; serial request wall falls 2.57%. Output drift keeps this cell unpromoted independently of timing.

FA_OPT=7 matches all screened 8192-input hashes and completes ordinary cleanup. PP-only is 1690.34 ± 77.39 tok/s; its retained samples are 1733.09, 1736.92 and 1601.00, with the slower third sample retained. MTP decode is 46.84 ± 0.25 tok/s and acceptance remains 60.00%. Independent PP-only/MTP/serial request walls fall 7.79%/5.53%/6.12% versus the earlier fresh stock control, with all clock ratios approximately 1. The later pristine-stock comparison below removes that 8192-only MTP wall advantage, so no full-range or broad tuned-kernel finalist is pursued.

FLASH_MOE_GEMM=0 matches all screened hashes and ordinary cleanup at input 8192. PP-only is 1672.43 ± 96.72 corrected versus 1616.95 ± 107.23 raw tok/s; its PP-only windows include material clock ratios up to 1.072070. Independent PP-only/MTP/serial request walls fall 6.73%/5.15%/5.06%. MTP decode is 46.61 ± 0.34 tok/s, 0.91% below stock, with 60.00% acceptance. These are 8192-only screening observations with retained variation and timing confounds; they do not qualify this setting as a default.

FLASH_MOE_V2=2 matches screened hashes and ordinary cleanup at input 8192. PP-only is 1618.40 ± 86.15 tok/s and MTP decode is 46.41 ± 1.35 corrected versus 46.03 ± 1.97 raw tok/s, with 60.00% acceptance. Material TG128 ratios reach 1.026175 in MTP and 1.043354 in serial. Independent PP-only/MTP/serial walls fall 3.67%/4.57%/5.48% versus the earlier stock control. This final 8192-only cell remains unpromoted and supplies no stronger qualified default choice after the later stock confirmation.

## Late pristine-stock cold confirmation

`stock-cold-late` repeats the pristine stock profile and the earlier fresh stock's exact source, runtime and prompt pins. It completes 36 measured cold requests and 12 recorded warmups, with all 48 prompt/request/output hashes matching the fresh stock control. Twelve repeat checks and sixteen serial/MTP output comparisons pass. Controller/backend terminal states are `stopped`; backend `ready`, `cleanup` and `recovery` are true, and the result records `passed_execution=true`, `confirmed=true`, `cleanup_proven=true`, `promoted=false`.

| Exact input tokens | PP only, tok/s | Serial TG128, tok/s | MTP TG128, tok/s | PP-only wall change vs early stock | MTP TG128 wall change vs early stock |
|---:|---:|---:|---:|---:|---:|
| 8192 | 1714.94 ± 17.55 | 35.83 ± 0.55 | 47.06 ± 0.60 | −9.25% | −5.68% |
| 16384 | 1680.80 ± 14.41 | 35.49 ± 0.47 | 45.34 ± 0.11 | −10.32% | −8.96% |

The later stock prefill improvement also appears in raw phase means: PP8192-only rises from 1555.43 to 1714.94 tok/s, and PP16384-only rises from 1508.41 to 1680.80. Relevant PP-only and MTP windows have clock ratios approximately 1. Serial TG8192 includes a retained material clock-ratio window; raw/calibrated phase statistics and request walls remain separate in the evidence. The changed stock timing demonstrates that earlier screening improvements cannot be attributed to a setting without resolving the sequential timing confound; no temperature/power telemetry identifies its cause.

Against this later stock mean, FA_OPT=7's screened 8192 MTP wall is 0.16% slower and DN_SCAN=1 is 0.37% faster. Chunk32768's MTP walls are 1.31%/2.50% slower at input 8192/16384. These direct comparisons remain descriptive, with three retained repetitions per cohort. They supply no useful qualified kernel advantage, so no tuned kernel finalist or kernel promotion follows. The public evidence retains all screening/late cohort wall comparisons and their hash/count scope.

Across all 48 recorded cold calls, sampled minima are 24.76 GiB physical and 115.70 GiB commit headroom. The independent controller full-run physical minimum is 24.63 GiB; no full-run commit minimum is retained. Startup takes 201.50 s and the complete startup/measurement/cleanup sequence takes 602.20 s. Its finalized retry child receipt records 114 mutable-state reads, zero retries and zero failures; parent counts remain unavailable. This is a **cold-only confirmation**: structured quality, broad and agent gates are not repeated, and no full qualification or promotion is implied.

## Matched cache series

The first `cache-finalists-sealed/off` attempt failed with `PermissionError` while reading controller state during readiness, before any benchmark stage. Its result retains no completed stages and is unqualified. Terminal controller/backend states are `stopped`, with backend `ready=false`, `cleanup=true`, `recovery=true`. This attempt is preserved separately from policy statistics and supplies no matched cache timing, counter or output evidence. The completed fresh series uses `cache-finalists-retried` and retains separate provenance.

The fresh cache and late-stock orchestration use separately pinned ignored launcher/bootstrap helpers. They retry `PermissionError` for exactly two mutable controller/backend state files with a 1 s deadline and 25 ms pause. Benchmark/runtime/client source bytes remain unchanged; the wrapper is a separately recorded execution behavior. Supplemental receipts retain launcher/bootstrap/offline-check/helper/interpreter/target hashes and completed benchmark-child read/retry/failure counts. Parent retry counts are explicitly unavailable. Full argv and mutable/control paths remain private; their receipts are hashed. In the reviewed clients, these identity reads occur before or after the sampled per-request wall interval; stage elapsed time includes bootstrap and control overhead. This control-flow observation does not establish zero wrapper overhead.

The completed Off/Exact/Flexible series holds an explicit **32768 prefill chunk and 32768 arena** across all three profiles, reusing the original immutable agent workload and the same 256-token output cap. Only `engine.prompt_cache` changes between these cache profiles. Explicitly fixing the chunk controls inherited behavior; this series does not establish the effective chunk when it is unset.

The explicit-32768 Off run supplies the cache timing control. It may additionally be checked against the earlier Off/auto outputs for raw-hash parity, but that does not make the earlier run a matched cache timing baseline. Actual hits, misses, disk-restore and draft counters, every-call physical/commit samples, controller physical minimum, and ordinary cleanup/recovery must be retained. Cache branches and entries remain at inherited defaults until a policy effect is established; `CACHE_RESERVE_MB` is not set.

The fresh fixed-32768 Off control is complete and qualified for the cache series. All eighteen agent outputs finish with `stop`, pass grading and preserve the 8532/88, 8841/44 and 8953/208 actual input/output counts. Serial/MTP hashes match, and each mode's raw agent hashes/counts also match the earlier auto-chunk stock recording. Each mode's structured quality passes 10/10 functional and strict checks over 27 observations, with six available first-token proxy deltas of zero. Every agent/quality cache counter is zero; agent disk-restore counters are zero and MTP accepts 699 of 792 drafted tokens (88.26%). It supplies the fixed-32768 cache baseline.

Exact is complete and qualified under its fixed-32768 profile. Its nine MTP agent calls match Off input/output hashes, actual counts and finish reasons, with zero cached input and zero disk restores throughout. Both structured quality modes also pass 10/10 functional/strict checks and raw/proxy comparisons. Mean MTP conversation wall is 24.75 ± 2.37 s versus Off's 22.83 ± 0.16 s, an observed 8.39% increase; no reuse benefit is observed. This does not establish a causal Exact penalty, and it does not characterize Exact with its chunk unset.

Flexible completes execution and ordinary cleanup but **fails qualification**. Eight of nine MTP agent calls report cache hits, with no disk restores. Only five of nine outputs pass the agent grader: repetition 0 turn 2 produces 53 tokens instead of 44 and fails `expected_two_tests`; all three turn 3 outputs produce 175 instead of 208 tokens and fail `safe_function_cases` with `case_exit_1`. These four outputs/counts differ from Off. The changed assistant reply is preserved in the next request, so repetition 0 turn 3 also changes its input count to 8962 instead of 8953. Every output finishes with `stop`, which does not establish correctness.

Flexible's mean MTP conversation wall is 10.49 ± 6.65 s, an apparent 2.177× ratio or 54.06% reduction versus Off, but it performs unequal and failed work: total completion tokens are 930 versus Off's 1020. Its 645/714 accepted draft tokens (90.34%) describe that changed workload and cannot substitute for grading. Reported cached-input counts span {0, 8512} on turn 1, {8532, 8788} on turn 2, and {8841, 8905} on turn 3. The apparent wall improvement is **unqualified**, so it does not support choosing Flexible.

Flexible serial quality matches Off. Its MTP quality main outputs pass 10/10 functional and strict checks and retain matching full hashes, but the overall candidate/control and internal serial/MTP quality gates fail first-token probability proxies. Maximum absolute deltas are 0.328108 for `long_needle_8192` and 0.215729 for `long_needle_16384`, exceeding the 0.05 tolerance. Every-call sampled physical/commit minima are 24.36/115.31 GiB, above the reserve; sufficient memory and successful cleanup do not repair these correctness failures.

All three policies complete ordinary cleanup and remain unpromoted. The finalized launcher verifies ten child receipt hashes, with 406 observed mutable-state reads, zero retries and zero failures; parent retry counts remain unavailable. These receipts establish the recorded child behavior, not zero wrapper overhead. Off retains the strongest qualified performance evidence for this fixed-32768 cache series. The separate default deployment comparison below also supplies no useful Exact benefit.

Off includes nine serial agent calls before its nine MTP calls; Exact/Flexible record the MTP agent workload only, followed by quality in both modes. Off's MTP timing therefore has prior serial-call history that the candidate MTP timing does not. All recorded agent calls are retained, including the first call; there is no separate warmup. These timings are descriptive. Zero cache counters remain evidence for this exact workload, profile and request policy.

Agent requests explicitly use `cold=False`, and quality requests use that same client default. They omit `cache_prompt` rather than setting it false. The request construction therefore does not force cold execution, but omission does not establish an explicit cache opt-in. When observed counters remain zero, the functional/format/proxy checks do not demonstrate correctness after a warm cache hit. The public evidence retains the actual counters instead of inferring reuse from the selected policy name.

Positive wall change means slower than fixed-32768 Off; every conversation comprises three measured turns, repeated three times with no separate warmup. Per-call memory minima span agent and quality observations. Additional controller memory telemetry covers READY measurement stages, excluding loading and stop teardown; the controller's full-run physical minimum is retained separately.

<!-- CACHE_RESULTS_START -->
Completed cache cells: **3/3**.

| Policy | Serial conversation, s | MTP conversation, s | Agent hits / calls, serial; MTP | MTP wall change vs Off | Per-call physical / commit minimum, GiB | Cell qualification / cleanup |
|---|---:|---:|---|---:|---:|---|
| Off | 28.04 ± 2.37 | 22.83 ± 0.16 | 0/9; 0/9 | +0.00% | 25.40 / 116.30 | pass / pass |
| Exact | — | 24.75 ± 2.37 | —; 0/9 | +8.39% | 24.03 / 114.60 | pass / pass |
| Flexible | — | 10.49 ± 6.65 | —; 8/9 | -54.06% (unequal work; unqualified) | 24.36 / 115.31 | fail / pass |
<!-- CACHE_RESULTS_END -->

## Focused Off/Exact default deployment comparison

`cache-auto-sealed` compares fresh Off and Exact profiles with prefill chunk, token arena, draft/kernel and cache-resource overrides unset. Its frozen helper records the effective native arena, admission and cache settings from owned terminal engine logs. This evaluates the observed deployment configuration: it does not assume a particular unset chunk or isolate a policy effect if native settings differ.

The completed cells retain serial/MTP agent and structured quality for Off, and MTP agent plus both structured quality modes for Exact. Every call, matching raw hashes/counts/grades and per-call/controller memory is retained with ordinary cleanup. Off's MTP stage follows serial agent calls; Exact's MTP stage starts its agent workload. Sequential timing and prior-call history remain descriptive confounds. This focused comparison includes **agent and structured quality only**; cold and broad suites are not repeated.

Both owned policy cells finish their measurements and ordinary stops, but the original parent aggregation fails with `PermissionError` replacing `cache-state.tmp` with `cache-state.json`; its exception-handler aggregation write also fails. No original parent `result.json` exists. The original launcher receipt remains `phase=failed` and has no exit-code field; the separately observed outer wrapper exits 1. All original bytes are preserved.

A **new derived finalization receipt** verifies all seven completed stage recordings, two policy cells, source/profile/input/runtime seals, native-log digests, owned stopped states, seven child receipt hashes and 119 fresh Off control files. It records `finalized_from_retained_cells=true`, `passed_execution=true` for the retained cells, and **`orchestration_complete=false`**. The public evidence preserves both this usable completed-cell proof and the original aggregate-publication failure. Child receipts record 277 mutable-state reads, zero retries and zero failures; parent retry counts remain unavailable.

The retained native logs establish **32768 token arena and admission chunk in both policies**, with all explicit overrides unset. Exact also reports cache checkpoint chunk 32768, six entries of 111 MiB each, and final native counters of **0 hits, 65 misses, 0 stores and 0 reused tokens**. These are observed native values; no unset-1024 claim follows. Every Exact agent call and every quality observation reports zero cached input, so this run supplies no warm-hit correctness qualification.

Off and Exact agent outputs match complete assistant/prefix hashes, actual counts, finish reasons and all nine grades. Counts remain 8532/88, 8841/44 and 8953/208; both MTP recordings accept 699/792 drafted tokens (88.26%). Each structured quality mode passes 10/10 functional and strict checks over 27 observations, with all six available first-token proxy deltas zero and internal serial/MTP parity passing. Exact therefore passes the recorded stage checks but remains overall unqualified for cache reuse because no cache opportunity occurs.

Exact's nine MTP calls total **74.30584 s** versus fresh Off's **68.24486 s**, an observed **8.88% longer wall time**. Conversation means are 24.77 ± 2.20 s and 22.75 ± 0.14 s respectively, with every first call retained. This is descriptive evidence rather than a causal cache penalty. Per-call physical/commit minima are 24.46/115.14 GiB for Off and 24.53/115.26 GiB for Exact; READY controller observations and full-run physical minima remain separately scoped in the JSON. Successful grading, adequate memory and cleanup do not establish reuse when counters are zero.

<!-- DEFAULT_CACHE_RESULTS_START -->
Completed default deployment cells: **2/2**.

| Policy | Serial conversation, s | MTP conversation, s | MTP agent hits / calls | MTP wall change vs fresh Off | Native arena / admission / cache chunk | Checks / warm-hit proof / cleanup |
|---|---:|---:|---:|---:|---|---|
| Off | 27.95 ± 2.74 | 22.75 ± 0.14 | 0/9 | +0.00% | 32768 / 32768 / — | pass / — / pass |
| Exact | — | 24.77 ± 2.20 | 0/9 | +8.88% | 32768 / 32768 / 32768 | pass / unproven / pass |
<!-- DEFAULT_CACHE_RESULTS_END -->

The finalized decision retains stock compute, depth 2, cache Off and unset prefill/arena overrides. No optional Exact recipe is selected, and no additional live experiment is planned for this investigation. The decision receipt and its limits are published in the JSON: late-stock cold confirmation removes useful kernel evidence, Flexible fails correctness, and both fixed-chunk and default Exact provide no observed agent benefit. This selection does not infer Exact warm-hit behavior or general cold/broad qualification from the focused cache comparison.

## Measured source and later reader robustness

The fresh sealed stock control, twelve screening cells, matched cache series, late stock confirmation and focused default-cache cells use the public source in measured commit `b77a3bddb4a84bb4af0388c476ee686de3aa1362`. Their immutable source seals match that commit; historical artifacts retain their earlier source/harness identities. Separately recorded ignored wrappers supply the measured execution retry behavior.

After the sealed measurements ended and that source was committed, a separate reader robustness change makes `gateway_cold.py` and `reddit_runtime.py` delegate mutable controller-state reads to the existing bounded reader. The source diff contains two imports and five read delegations; `server/controller.py` is unchanged. The original recorded source/recording seals remain intact in the JSON, with the later source hashes added only as separate publication provenance.

| Client | Measured SHA256 | Later reader SHA256 |
|---|---|---|
| gateway_cold.py | `ca968c1b7140f556baa3f63e7ac5885852cdf83b9c176149509a3e703553332f` | `fcbb75c8f02018ecd68b13d2160173c415a4a809f3b759012f001f36ff73403d` |
| reddit_runtime.py | `9e9fb05c83677fbe319e3b9437d25444792c077256fb2b3cf3385f378a8fabc2` | `8bc974964b3eb32205db96aee94a761f9774bac7411cbec7efe2fcd5920ea9a5` |

Eight added reader regression tests expose the expected retry/delegation failures against the measured source, then all eight pass with the new reader source. The RED run retains nine assertion failures and six errors across subtests; two immediate-error methods already pass before the change. The full later benchmark suite passes **92 tests with one skip**. Actual RED/GREEN/full-suite log hashes are retained in the separate provenance. **No live inference rerun follows this reader change**; reported timings describe the measured commit and its sealed wrappers.

## Qualification scope and remaining work

0.16.1 artifacts are archival and do not establish an upgrade performance comparison. Historical 0.15.1 results are also unmatched references. The q8g64/HGN slicing and n-gram extraction utilities are research tools; they do not imply a deployed model variant, completed large-table extraction, or measured q8g64 engine performance.

- [x] Pin the 0.16.2 image, executable, entrypoint, model sources, and bridge site; verify offline tests and installed preflight.
- [x] Preserve original harness/format/API failures and the failed sealed ownership attempt with cleanup proof.
- [x] Publish sanitized earlier-stock timings, actual counts, hashes, counters, and clearly scoped memory evidence.
- [x] Complete the fresh sealed stock control with matching source/profile/input/harness identities and cleanup/recovery proof.
- [x] Complete all twelve screening cells, compare candidate/control and cross-mode raw hashes, and retain failed or drifted candidates as unpromoted.
- [x] Complete the matched fixed-32768 cache series and its every-call memory/counter review; preserve Flexible's failed qualification.
- [x] Complete late pristine-stock cold confirmation and decline tuned kernel promotion after its screening advantage disappears; no tuned kernel finalist is selected.
- [x] Validate the focused Off/Exact retained cells through a new derived receipt, preserve the original failed parent aggregation, and retain the combined deployment scope.
- [x] Record stock/cache-Off selection, uncertainty, ordinary-stop lifecycle proof and reproducible public evidence; no tuned kernel or optional Exact recipe is promoted.

## Later occupied-context follow-up

At the user's later request, [128K and 260K synthetic measurements](halogen0162-long-context-20261003.md) were run on commit `2bb5642f266dae3030ab95b2ca18d033da73be33`, after the reader changes described above. This separate follow-up preserves the original upgrade measurements and records per-workload MTP acceptance.
