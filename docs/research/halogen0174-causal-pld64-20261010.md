# Halogen 0.17.4: committed-history PLD64 candidate

**Completed: no serving gain is qualified; the candidate remains disabled.** All three native/candidate/native windows finished with matching output hashes and zero actual tail substitutions. The results and accounting scopes are recorded below; the normal server was restored ready and open.

The candidate extends the native width-three prompt lookup using at most the last 64 already committed token IDs. It runs a bounded CPU lookup at the existing copied-offer boundary. It preserves the stock offer's opening token, offer width and verifier. It changes only the two tail IDs when a longer compatible historical match exists. Model weights and original GPU kernels stay unchanged; no NPU, separate model, learned predictor or oracle is used.

## Mechanism and bounded scope

The allocation-free `longmatch64.h` scans earlier exact trigrams within the copied committed suffix. A candidate occurrence must have all three continuation IDs already committed, its opening must equal stock proposal zero, and all continuation IDs must pass the startup-frozen ordinary-token bitmap. The policy selects the longest backward match, using the newest occurrence to break ties. A match must exceed three IDs before the two tail slots can change. Otherwise it returns the original stock offer. At the 64-ID limit, the scan checks at most 59 occurrence positions.

The synchronous provider consumes copied committed history and the copied stock offer only. It copies the full request/slot/round binding into its result. The existing guarded adapter remains the sole writer: it rechecks owner birth, slot epoch, round, model/tokenizer/session identity, current committed ID, native allowance and unchanged stock input immediately before writing tail slots. Missing, stale, ineligible or unchanged results preserve stock execution. There is no device dispatch, wait, native callback or allocation inside the provider.

The 0.17.4 collector uses independently mapped birth, record-move, slot, offer, outcome and destructor boundaries. Startup verifies the exact native ELF and instruction pins before publishing relays. Activation is cold and opt-in; native windows carry no PLD64 library/environment/mount override. The candidate constructor-order shim delegates the unchanged phase launcher checks and ensures the phase adapter checks original instruction bytes before the CPU collector installs its relays.

## Prior offline evidence

The [published 0.17.3 screen](<C:/Projects/strix-alloy-clean/docs/research/halogen0173-causal-pld64-20261009.md>) froze proposals before its sole future-label scoring pass. Prediction used only causal copied inputs; labels were used afterward to score those frozen proposals.

| Frozen stock-frontier screen | Result |
| --- | ---: |
| Complete PLD frontiers | 96 |
| Longer compatible matches | 14 |
| Changed offers / improved frontiers | 1 / 1 |
| Reconstructible labelled frontiers | 94 |
| Stock / candidate exact-prefix ID totals | 235 / 237 |
| Worsened frontiers | 0 |

The sole changed offer improved its exact prefix from one to three IDs. Two frontiers were unscorable. All 94 reconstructed stock-prefix lengths agreed with recorded native outcomes, and the C++ implementation reproduced all 96 frozen proposals. This is limited offline utility evidence: one changed frontier out of 96 does not establish changed-trajectory acceptance, engine throughput or a general gain. No policy sweep or refitting was performed.

## Genuine transaction evidence

Journal v2 retains a 128-byte header and 512-byte events. Only an actually applied PLD Begin sets `TailApplied` (`1 << 10`). Its first three offer slots contain the post-write offer; slots 3–5 retain the original three stock IDs. This permits an offline verifier to establish an unchanged opening and at least one genuinely changed tail ID rather than infer substitution from a lookup hit. Outcome events carry neither copied offers nor `TailApplied`.

The verifier pairs each Begin with its exact owned Outcome, checks contiguous event sequence, session nonce, owner/slot/epoch/round lineage, native request identity and zero dropped events, then derives attempted/accepted deltas from the native cumulative counters. Warmup request IDs are excluded explicitly from measured totals. The journal contains no clocks: substitutions and their native outcomes are separate evidence from throughput.

Root's [provider receipt](<C:/Projects/strix-alloy-clean/server/.local/optimization9h-20261004/halogen0172-backend-preparation-20261008/causal-pld64-native0174-provider-20261010/root-green/receipt.json>) records a passing focused CPU harness. The [v2 build receipt](<C:/Projects/strix-alloy-clean/server/.local/optimization9h-20261004/halogen0172-backend-preparation-20261008/causal-pld64-native0174-collector-20261010/root-build-v2/receipt.json>) records passing strict-warning compilation and the mapped collector transaction/ownership harness. Its library is 266,056 bytes, SHA256 `7956d44d3b574a372bed858b5a0c2193e905e490965dbd6061c2b7c8978c3ff9`. Those CPU/build checks do not qualify native serving gains.

## Serving comparison and reporting

Each of the three cold windows—native-before, causal64-v1, native-after—uses the same frozen natural-text request: **16,384 actual input tokens, 128 output tokens, temperature 0, seed 1, Thinking Off, Cache Off, MTP2/PLD3,3**. Context capacity remains 262,144. Each window has one excluded warmup and three measured repetitions. Measured output hashes, finish reason and draft counters must match that window's own warmup. Cross-policy output parity is required; cross-policy accepted/drafted counter equality is not required.

Raw API responses are retained before qualification. Phase-specific `CLOCK_MONOTONIC_RAW` records must match the complete audited native D records by signed native request ID, order, counts and duration fields. Prefill and Decode statistics use the separately paired RAW phases. The whole-request RAW/QPC observation must agree within 0.1%; its ratio is not used to rescale API rates or invent phase durations. API rates remain recorded observations. Acceptance is pooled over the three measured repetitions and retains its explicit scope: **combined API MTP+PLD draft-token accounting; native MTP-only acceptance is not isolated**.

Root also checks exact runtime/source/manifest ownership, no unrelated API traffic, valid idle GPU samples, 22 GiB physical/commit request-entry reserve and 18 GiB runtime reserve. The two sealed background Riot client identities may be admitted only after fresh exact identity verification; gaming activity or other/new Riot processes remain inadmissible.

The saved source-validation object adds `window=<selected window>` and `mode=causal64-v1` for causal, or `mode=native` for either control, after the frozen workload validation returns. The initial CPU qualifier omitted those two fields from its expected object. Root preserved the completed request evidence and sealed inputs, restored the normal server, and qualified the retained cohort with the isolated supplemental CPU qualifier containing the exact augmentation. This repaired the metadata expectation without modifying raw evidence or replaying completed requests; the unstarted windows subsequently used separately sealed continuations.

All three windows are now complete and qualified; rates and native journal results follow below. A candidate benefit must exceed both native controls and observed scatter, with bounded native-control drift, genuine substitutions, unchanged greedy output and no material Prefill regression. **No serving gain is qualified and the candidate is not adopted.** The normal server is restored ready and left open after the comparison.

## Completed native serving comparison

Halogen 0.17.4; frozen natural 16,384-token input, 128 output tokens, one excluded warmup and three measured repetitions per window. Rates use qualified paired RAW phases; acceptance below retains the API aggregate MTP+PLD scope.

| Window | Prefill tok/s | Decode tok/s | API acceptance |
| --- | ---: | ---: | ---: |
| native-before | 1679.63 | 42.75 | 45.11% (180/399) |
| causal | 1661.39 | 43.45 | 45.11% (180/399) |
| native-after | 1657.02 | 43.22 | 45.11% (180/399) |

The candidate was +1.10% versus the control Decode mean, below the 2.72% observed-scatter margin. Native control drift was 1.09%; Prefill changed -0.42%. All greedy output hashes matched. There were **zero actual tail substitutions**, so the rate difference cannot establish algorithm benefit.

The candidate journal measured neural acceptance of 177/396 = **44.70%** over paired source-specific deltas, with zero PLD attempted tokens. This is distinct from API aggregate acceptance (180/399 = 45.11%). There was one copied width-three PLD offer per request; its stock opening differed from the native opening, its longer-match condition failed, and its outcome was explicitly censored with zero attempts. Hook activity is present; this is not a failed or absent installation.

The metadata expectation repair replayed no requests. After the candidate stopped, immediate admission briefly saw 34.85 GiB physical free; memory subsequently released normally to 44.98 GiB. The supplemental recovery ran only the unstarted native-after window, retained the failure evidence, preserved the 35/131 GiB startup floor, and waited for asynchronous release before normal admission. The normal 0.17.3 server is verified ready on port 8840 with its visible console open. No NPU was used, no driver or global WSL setting changed, and no public commit or push was made.

Machine-readable evidence: [halogen0174-causal-pld64-native-20261010.json](C:/Projects/strix-alloy-clean/docs/research/halogen0174-causal-pld64-native-20261010.json).
