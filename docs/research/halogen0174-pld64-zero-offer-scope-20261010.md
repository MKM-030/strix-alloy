# 0.17.4 PLD64: zero substitutions on the retained natural16k cohort

Date: 2026-10-10. This is a source/evidence review of the causal window, not the final three-window performance comparison.

The retained cohort has **four observed copied PLD offers, zero changed tails, and zero native PLD attempts**. Each request reaches the same stock offer once. The causal policy has no compatible match longer than three IDs, so it preserves that offer; its opening also differs from the native cached opening. The evidence supports a workload/policy nonmatch, rather than a missing copied-hit hook or a provider eligibility fix.

Paths below use `PREP = server/.local/optimization9h-20261004/halogen0172-backend-preparation-20261008`, `WORK = PREP/causal-pld64-native0174-launch-20261010`, and `COLLECTOR = PREP/causal-pld64-native0174-collector-20261010`.

## Retained offers and provider decision

`WORK/causal/pld64-verification.json` names request 3 as the excluded warmup and 4/5/6 as the three measured requests. Every request has 68 paired rounds: 66 attempted neural rounds, one copied PLD offer at round 29 closed without an attempt, and one terminal neural round with zero source-specific draft-counter delta. The measured scope is therefore 204 paired outcomes and six censored outcomes; censorship does not mean an unpaired or missing record.

The copied PLD Begins have sequences 59, 199, 339 and 479; their corresponding explicit skipped Outcomes have sequences 60, 200, 340 and 480. The public verification rows are at lines 821, 2753, 4685 and 6617. Direct read-only decoding of the frozen v2 wire gives the same values for all four:

| Field | Value |
| --- | --- |
| Round | 29 |
| Begin flags | 55: ContextAvailable, ContextTruncated, OfferAvailable, TransportAvailable, CountersAvailable |
| Copied context | 64 IDs of 16,437 total IDs |
| Current committed ID / suffix last ID | 6092 / 6092 |
| Copied stock offer / width | `[1040,264,38936]` / 3 |
| Native cached opening | 11 |
| Native allowance | 3 |
| Transported output before offer | 53 |
| TailApplied | false |
| Outcome attempted / accepted / transported delta | 0 / 0 / 0 |

All 272 Begin records divide into 268 neural Begins with flags 51 and four PLD Begins with flags 55. Thus the PLD seam was observed. These flags do not indicate an incomplete offer: `shadow_collector.cpp:208-209` requires ContextAvailable and OfferAvailable and rejects Censored or OfferTruncated; it intentionally permits ContextTruncated because the causal input is the last 64 IDs.

The frozen policy in `longmatch64.h:35-60` searches the copied suffix for an earlier occurrence of its last three IDs, followed by the unchanged stock opening and two already committed ordinary continuation IDs. At this frontier, the only such occurrence has zero-based continuation index 35 and continuation `[1040,264,38936]`. Its preceding ID is 79797; the current suffix's preceding ID is 62144. The match therefore stops at exactly three IDs. All three continuation IDs pass the pinned ordinary-ID bitmap. Since `longmatch64.h:55` requires `best_match > 3`, the result stays equal to stock. `tail_adapter.h:121` returns Unchanged before mutation for such a result.

The copied inputs meet the visible width/context/current-ID/native-allowance conditions in `causal_provider.h:21-26`. The retained ready manifest records `HALOGEN0174_PLD64_MODE=causal64-v1`; frozen startup code initializes and attaches the enabled adapter before collector configuration (`shadow_install.cpp:288-290`). No source wiring defect is indicated. The wire does not record provider mode or non-applied adapter status, however, so Unchanged is an inference from the pinned source and retained copied inputs, not a separately logged adapter-status event.

The stock opening 1040 also differs from the recorded native cached opening 11. The frozen native mapping documents the opening comparison in `PREP/causal-pld64-native0174-design-20261010/design.md:20`. The observed zero-attempt PLD closure followed by a neural Begin matches the collector's explicit native-opening fallback handling (`shadow_collector.cpp:182-188`). The candidate preserves opening and cannot turn this copied offer into a native-accepted PLD attempt by changing only its tail.

## API 399/180 and journal 396/177 have different scopes

Every retained API response reports `draft_n=133` and `draft_n_accepted=60`. The measured qualification therefore reports drafted 399, accepted 180 and acceptance 45.1127819548872%. Its recorded acceptance scope remains combined API MTP+PLD draft-token accounting.

The exact retained API source is `PREP/halogen0174-normal-bridge-preparation-20261010/artifacts/tools/serve_api.py`, SHA-256 `c037988bd6a18ebffa8fe22bd3ce85d6ab4c2350aa0814b56087565bea1f5621`, matching the native D audit's API pin. Its D parser maps rounds from field 8, commit from field 9, PLD counters from fields 12-14, and head_drafted from field 26 (`:1148-1160`, `:1177-1178`). Its timings calculation uses these fields (`:2791-2799`):

```text
draft_n          = head_drafted + pld_drafted
draft_n_accepted = max(0, commit - rounds - shared - pld_accepted) + pld_accepted
```

Retained D fields for every request are rounds 67, commit 127, shared 0, all PLD counters 0, and head_drafted 133. Those values produce API 133/60 without requiring an additional inferred PLD attempt.

The journal instead retains the Request's source-specific counters and sums paired Begin/Outcome deltas (`verify_pld64_journal.py:278-299`). Per request, its final values are:

| Counter scope | Drafted | Accepted |
| --- | ---: | ---: |
| D/API aggregate | 133 | 60 |
| Journal native neural counters | 132 | 59 |
| Journal native PLD counters | 0 | 0 |

Immediately before terminal round 68, the journal has decode_rounds 66, output_attempted 125, neural_drafted 132 and neural_accepted 59. Its terminal Outcome changes decode_rounds to 67 and output_attempted to 127, while both neural and PLD drafted/accepted counters stay unchanged. Thus the API's inferred accepted count changes from `125-66=59` to `127-67=60`; the source-specific neural accepted count stays 59.

The D head_drafted field is 133 while the journal's final neural_drafted counter is 132. The retained journal contains no source-specific delta assigning that additional aggregate drafted unit to a neural or PLD attempt. Preserve that scope distinction rather than invent an omitted attempt, missing acceptance, or corrective count. Across measured requests 4/5/6, this is exactly the API 399/180 versus journal 396/177 difference: 45.11% API aggregate acceptance versus 44.70% paired native neural acceptance. The verifier includes the censored rounds' actual counter deltas; it did not drop a nonzero source-specific count merely because the rounds were censored.

## The earlier 96-frontier result came from another workload

The earlier screen is `PREP/causal-pld-longmatch64-20261009/initial-result.json`. It used the 0.17.3 selector pilot capture `docs/research/halogen0173-selector-pilot-20261009/native-capture/decoded.json`: 96 complete width-three PLD frontiers, 14 longer compatible matches, one changed proposal and 94 reconstructible labels. Its reconstructed stock-prefix total was 235; the frozen candidate total was 237.

The sole changed frontier is bound by `docs/research/halogen0173-selector-pilot-20261009/request-provenance/test-03-reasoning.json` to the original `PREP/selector-real-request-provenance-20261009/payloads/test-03-reasoning.json` and `documents/workshop-kits.txt`. It had 635 input tokens and 128 output tokens, session `cf194e1fb733d624cdbf08fa47612ed3`, wire request 15, owner 13, epoch 49, round 44, Begin 1409 and Outcome 1410. Stock `[256,2972,3440]` became candidate `[256,10342,303]` from a four-ID match at prior suffix index 14. Its recorded stock prefix was one ID; the offline candidate prefix was three.

The current 0.17.4 request repeats the sealed War-and-Peace prefix plus river-town story task with 16,384 input tokens and 128 output tokens. `PREP/power-recovery-20261009/natural_window.py:77-98` binds that corpus, task and framing. It does not reproduce the workshop frontier or the earlier sample's 96 completed PLD attempts.

The earlier predictions froze in memory before scoring; durable archival followed afterward, as retained in `PREP/causal-pld-longmatch64-20261009/proposal-recovery.json`. That stock-trajectory screen establishes neither a changed native rollout nor a realized acceptance or timing gain.

## Narrow consequence

No provider correction, relaxed eligibility rule, policy refit or new test grid follows from this evidence. The current tail-only mechanism needs both a compatible committed match longer than three IDs and a stock opening that survives native validation; this cohort supplies neither at its only copied PLD frontier. It supports a no-substitution control outcome. A different proposal-ingress mechanism would be a separate design requiring its own causal and native-verification argument; this review does not justify introducing one.

The retained causal qualification records raw means of 1661.3901705050903 prefill tokens/s and 43.45480094764241 decode tokens/s. These are cohort measurements with zero TailApplied evidence, not realized PLD64 substitution performance. The parent/root agent owns the complete native-before/causal/native-after comparison and restoration.

## Evidence pins and method

| Artifact | SHA-256 |
| --- | --- |
| Current `causal/raw-extracted/pld64-owned-ledger.bin` | `c613705d5e8e94fe12195b15918f45c022c0d75668d8e830ddc930818e68c3a8` |
| Current `causal/pld64-verification.json` | `f29f8599baab243d0cdb124ec9cc4b60619801c0aa1728d507d11e01f1d8fe05` |
| Current `causal/root-qualification.json` | `6d10225abe28af66a6f9fcd5eda6ec28c81bf749b52c9985a7bb0c88eb3c2510` |
| Current `causal/natural16k/request.json` | `4a2cf7a39ac6d1f5efba542f40b90affe827e91b60f296f4c1eb93873f6826ca` |
| Collector `shadow_collector.cpp` | `6bf63fabef8fe1bc5d0a876bc9f1bdf7fd5d6b591531f44bf42f38fd18b6ccf3` |
| Collector `causal_provider.h` | `cb4e277a49d50fbfe21a230f9c2299a3b0ebdd8711a338f70656846a56bd2d42` |
| Collector `longmatch64.h` | `d4c8589452d40996fffb373abd5420c0905be9184ea44512311fedb8d9f28fe2` |
| Collector `tail_adapter.h` | `c0d0fdda3d070c8fa9f586807c9e9d58ef8d3c7516ed0c55aeec48fc9aa4b405` |
| Ordinary-ID bitmap | `33df00238ff2bf01a96b3c7d4aa8782ba38925b9e7114b311c9e3d830ba81b83` |
| Earlier workshop request | `48f93c780112dde571eb704606b75eef3266484c06027317385f194e3b1d64cb` |
| Earlier workshop document | `569a392ab07008e9c06ab6cfc703bf39267c35274e6a53197d64df54d4f39b7d` |
| Earlier decoded journal | `6e4036db6dc008c206badac7101c28fcf46cda90033f5a44723a00668751bd67` |
| Earlier binary journal | `2d265215676ad672452caf4805e4ac3d81ce313407de8c9acec42746614df776` |
| Earlier frozen predictions | `be54505c785271d76f1808b27f72618df9f2a0b82e6730c0a7b2d37488157c62` |
| Earlier initial result | `648e5bbd35c56b0a71add4f1a213225f5d9e64398ffdc86333e7b4f425d56244` |

Review used retained JSON, source text, source hashes and read-only v2 wire decoding in PowerShell. The copied-offer match was inspected against its retained suffix and bitmap; the frozen predictor was not executed. Collector source hashes also match their retained `root-build-v2` copies. No Python execution/import, hardware/API/WSL access, request replay, build, sealed-source/evidence edit, or STATE update was performed by this source-review agent.
