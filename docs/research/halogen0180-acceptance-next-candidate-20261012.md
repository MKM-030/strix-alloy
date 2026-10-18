# Halogen 0.18.0: next acceptance candidate, 12 October 2026

**The new supported `HALOGEN_PLD=2,3` candidate fails its conditional natural16K usefulness screen. No live cohort or managed allowlist change is recommended.** It produces many more copied offers, but only one matching first retokenized token and no useful third token across the frozen trajectory. The native head opening and real drafting-round coverage remain unknown. Retain fixed2/PLD3,3; no new qualified acceptance or committed-token-per-second gain was found.

Shortening the lookup key can create a causal copied chain where stock `3,3` has no match. The native head must still agree with its first token, and the native linear target verifier must authorize every committed token. This differs from the closed PLD64 experiment, which could only replace tails at already existing stock hits. The bounded screen below supplies a new negative result, not a repeat of that experiment.

Work included local source/report reads, bounded primary web reads, a new offline script, causal/source-boundary fixture verification and two explicitly root-authorized CPU tokenizer attempts with limits on their own processes. Only this report, the new script and one private research result were written. No model inference, hardware access, WSL/Docker action, serving HTTP request, credential read, production source/profile edit, service lifecycle action or STATE operation occurred.

## Fixed evidence and novelty boundary

The installed engine remains 0.18.0, image digest `sha256:de3b47d2e5f24f98a38ba5fb66b0075b0cd8a3219c38917c78fb4bbeb42b88d9`, engine SHA256 `71d72b283f0937aec024baf6b6ec919e27dacd57cfc043832468ffdd603c8e08`. The completed matched natural16K fixed2 and adaptive-depth cohorts both returned combined API counters **180/399 = 45.11278%**, with mean request times **16.6656914** and **19.5828629 seconds**. Fixed2 remains the control. These are 32K-capacity, 8K-chunk/arena results, not Current4K/full262 results. [Matched report](halogen0180-acceptance-comparison-20261011.md).

The root-authorized closed routes stay closed: second full drafter, full-vocabulary native projection, expanded DFlash slots, causalPLD64 and the completed adaptive-depth screen. The earlier exact2/latest CPU screen supplied zero first-target matches at its two hits in a different fifteen-case shifted synthetic family; it is negative evidence, not a natural16K result. This report does not propose rerunning that screen. [Earlier short-key exclusion](halogen-next-acceptance-mechanism-20261006.md).

The retained natural16K 0.17.4 journal observed one copied stock PLD offer per request, refused before a PLD attempt because its opening differed from the cached native head. Its source-specific neural count was 177/396; the API total was 180/399. This establishes no stock PLD acceptance opportunity on that trajectory, and no benefit from tail-only changes. It does **not** count two-token-key occurrences across the complete causal 16K prefix. Its copied suffix is only 64 IDs. [Scope audit](halogen0174-pld64-zero-offer-scope-20261010.md).

## Mechanism and complete cost case

The official 0.18.0 contract supports PLD `N,K`, greedy single-request generation, the native opening gate, and a maximum shipped K of three. It also states that native v2 carries its own head: `HALOGEN_MTP_HEAD` is a GGUF-head path, not an override for v2. Tokenizer configuration relocates the tokenizer directory. [Versioned flags](https://raw.githubusercontent.com/peonist-ai/halogen-flash-server/v0.18.0/docs/FLAGS.md).

Changing N from three to two increases the set of context matches. It can also select a poorer continuation at a boundary where stock already had a useful match. There is no hindsight choice between stock and candidate chains. A public-contract test must execute the engine's own occurrence selection; it cannot choose whichever earlier occurrence later matches the target.

The potential saving is narrow: a newly opening-compatible copied chain can replace subsequent neural proposal work and offer a third draft to the existing verifier. A successful length-three prefix can commit four tokens including the target bonus, rather than the three of a fully accepted depth-two neural round. That is an upper opportunity for such a continuing round, not a request-wide forecast. Remaining cap, EOS, corrections, backoff and native bounds control actual work.

No second model, IPC path, additional trained head or larger verification reservation is needed. Cost includes more short-key collisions, native lookup/opening work, the third verifier row on eligible offers, rejected chains and accepted-prefix replay. Shortening the key does not make those costs free. CPU owns lookup/index work; GPU retains the existing head and target verifier; no NPU component is warranted for this native token lookup candidate.

For complete-request selection use actual committed/generated tokens divided by complete elapsed time, and separately record accepted drafts divided by complete elapsed time. A higher acceptance fraction can result from changed proposal counts without acceleration. If accepted count drops from A to A', accepted-draft throughput improves only if candidate wall time falls below `(A'/A) * stock_wall`; skipping work cannot be credited without that denominator.

## Completed conditional screen and exact data availability

The new [offline script](../../scripts/benchmarks/halogen0180_pld2_conditional_eligibility.py) implements one predeclared latest-earlier-exact-occurrence policy for N2/K3 and N3/K3. Each source continuation must already be in the committed prefix. The current suffix occurrence has no following token and is excluded. At a boundary both proposals freeze before the next authoritative token is appended to either index. All proposals freeze before evaluator scoring. Four fixtures verify the earlier-occurrence rule, bounded known continuation, causal freeze and null native metrics; they passed under Python3.13.

The full inputs were the frozen 0.18.0 `/v1/completions` prompt and the saved first measured fixed2 response. The flat Windows tokenizer at `C:/AI/models/halogen-flashnext/tokenizer/` matches all six retained tokenizer-file pins. The CPU extension is the already installed `tokenizers` **0.23.2** package at `PREP/npu-minilm-preparation-20261009/packages`, imported with existing `server/.local/venv/Scripts/python.exe` (Python3.12), `-B -I` and an explicit package path. No package was installed. `PREP` means `server/.local/optimization9h-20261004/halogen0172-backend-preparation-20261008`.

The first attempt enforced a **100 MiB own-process commit limit** through a Windows job. It exited1 at tokenizer construction with `memory allocation of 1048576 bytes failed` and produced no result file. Root explicitly changed the conservative offline bound to **512 MiB** for one new attempt. That attempt exited0 and created the result. No higher-memory attempt or loop followed. The 100 MiB failure is preserved here; its pre-attempt script hash was not separately captured, so none is invented. These are allocation bounds, not observed resident-memory peaks or serving memory measurements.

Tokenization reproduced **16,384 prompt IDs and 128 output IDs**, exact prompt-plus-output boundary concatenation, and exact output byte roundtrip. These checks make the retokenized trajectory useful for a conditional screen, but do not establish equality to a native generated-ID journal. The complete native generated IDs, 0.18.0 per-frontier cached head openings, true draft-round boundaries, native allowance and current occurrence/tie semantics are absent. All native eligibility and acceptance fields remain null.

| Conditional all-token-boundary result | N2/K3 | N3/K3 |
|---|---:|---:|
| Boundaries examined after first3 output tokens |125|125|
| Offers / full-width offers |35 / 35|6 / 6|
| Matching first retokenized tokens |1|0|
| Total consecutive retokenized prefix matches |1|0|
| Matched third retokenized tokens |0|0|
| Qualified native opening-compatible offers |unknown|unknown|

There are29 new N2 offers. The sole matching first token occurs at output boundary52, causal prefix length16,436: copied `[6092,1040,264]` from already known positions16,407..16,409 matches one token, then fails. It is not known to be a real 0.18.0 draft frontier. These are neither native attempts nor an oracle union with stock neural proposals. No candidate supplies a useful three-token copied prefix on this conditional trajectory. The screen therefore fails the predeclared positive useful-prefix opportunity requirement and supplies no credible reason to incur a native PLD2,3 cohort on this frozen story. It does not prove that every possible PLD2 policy, workload or unknown occurrence rule must fail.

| Retained input/output | SHA256 |
|---|---|
| Frozen `client/request-16384.json` |`0b616f5eb0aa779244cdbba4c2c7d42c8ee43ec200fc41f596e8331440f5a28c`|
| Fixed2 `response-1.raw` |`a15a11a769722a87802d063afc7305c1cbf1c94e0cd2fc4aa9d980b717b5465e`|
| Tokenizer JSON |`0997f410c57a1f4e53b09e4be8f4a172d90edd9564368fb0847030937229b9f3`|
| Successful screen script |`dc29b58014f6133eac1a18a3ce412fc7b97b75eaca47a1f78f56474d0dd8df2e`|
| Complete private result JSON |`424ce3e9455774c87e472282ae761b288363dfd3f273a2336fdce3b97ecf1ab2`|
| Proposal freeze before evaluator scoring |`ebdb1f90def27d72645d0bb8da58b0c789f43fb27b8bdb1f6ca792548cc5cc9f`|

The successful receipt is `server/.local/optimization9h-20261004/halogen0180-pld2-conditional-eligibility-20261012.json`. Its request/response paths are the exact `PREP/halogen0180-adaptive-option-20261011/{client/request-16384.json,fixed2-32k-cohort/response-1.raw}`. The different old exact2/latest exclusion involved15 shifted synthetic frontiers and two exact2 hits; this new pass uses the full pinned natural16K prompt,128 authoritative saved output tokens and125 all-token boundaries. Neither screen establishes current native opening eligibility.

## Required preparation, before any live comparison

The managed backend's `scripts/speculation_policy.py` currently allows only PLD `0` and `3,3`; `2,3` is rejected. The profile/controller/launcher already transport this policy object. Do not bypass validation with a private environment injection. A bounded preparation would allow precisely `2,3` for 0.18.0 in the backend validator, preserve the existing omission/off/stock behavior, and check profile copying, rejection of malformed/duplicate input, unchanged legacy admission, exact PowerShell forwarding and generated-manifest environment. Refresh the ordinary source pins through the established process. This document makes no source change. [Existing policy contract](halogen-mtp-next-action-20261004.md), [supported-options review](halogen0180-mtp-supported-options-20261011.md).

A future qualified eligibility gate would need recorded native generated IDs, the engine's actual occurrence rule, actual frontier/allowance and cached opening references. Freeze proposals using only prefix tokens committed before each frontier before evaluator-only target labels are considered. Report new opening-compatible offers and useful consecutive prefixes, including losses at existing stock offers. Preserve stock on a failed opening. Require a positive net useful-prefix opportunity, rather than a union of possible matches, before recommending hardware work.

That stronger gate is **not established by the reviewed evidence**. Do not relabel the old 0.17.4 truncated ledger or the new all-token retokenization as a full current-version proof, or add a new observer to a speed cohort just to get attribution. The concrete missing capability is a qualified 0.18.0 causal frontier ledger with raw IDs, head openings, allowance and actual occurrence selection. Collecting it is not recommended merely to rescue this negative candidate.

## Deferred finite protocol, not recommended after this screen

Only distinct new evidence of a qualified useful-prefix opportunity would reopen this candidate. The finite protocol would be **one `3,3` -> `2,3` -> `3,3` bracket**, with fixed depth2 throughout. Each arm has one excluded warmup and three measured requests: twelve calls total, then stop. No parameter grid and no unchanged rerun after a negative result.

Freeze the exact request from the completed 0.18.0 packet:

`server/.local/optimization9h-20261004/halogen0172-backend-preparation-20261008/halogen0180-adaptive-option-20261011/client/request-16384.json`

Its SHA256 is `0b616f5eb0aa779244cdbba4c2c7d42c8ee43ec200fc41f596e8331440f5a28c`. Preserve v2/checkpoint and tokenizer, one slot, context/slot/pool capacity **32,768**, prefill chunk/arena **8,192/8,192**, actual input **16,384**, output cap **128**, temperature0, seed1, nonstream completion, Thinking Off, Cache Off, the existing native backoff default, normal kernel choices and all root-owned memory/admission/recovery gates. The only policy difference is PLD N. If this 32K/8K setup cannot be admitted, create and freeze a new common profile for all three arms; do not compare its values with the historical packet as matched controls.

Retain whole-request QPC wall, exact output hashes, input/output counts, finish reason, raw reply/source/profile/request identities, and combined accepted/proposed counters. Source-specific neural/PLD attribution requires independent current-version qualification; absent that, call them combined API counters. Keep phase timings as unqualified observations unless their current mapping is qualified. There is no license to rescale them into decode throughput.

Require identical greedy output and finish/cap behavior across all arms. The selection objective is **committed/generated tokens per complete elapsed second**, improved against each stock bookend. Report accepted drafts per summed wall second separately. Report stock drift and overlapping timing ranges candidly; three calls do not establish statistical significance. An increase in fraction alone is insufficient. Any correctness failure, no improvement, or zero demonstrated opportunity closes this exact candidate and retains stock.

## Why the other supported routes do not replace this candidate

The 0.18.0 README rejects a llama.cpp MTP-draft GGUF as a Halogen head. GGUF trunks continue to use the existing Halogen head fitted to its own trunk, with worse upstream prose acceptance in the cited comparison. Greedy schema masking is supported, but constrains a different requested output and cannot improve the frozen unconstrained story while preserving its semantics. Existing structured JSON quality checks already exercise that path. Neither documented head relocation nor tokenizer relocation trains a better same-target proposal. [Versioned README](https://raw.githubusercontent.com/peonist-ai/halogen-flash-server/v0.18.0/README.md), [retained structured quality checks](../benchmarks/halogen0162-upgrade-20261003.md).

Several sampled proposals require the true selected-proposal distribution and a corresponding accept/reject correction; greedy alternatives require branch-conditioned verification or a causal single-chain selector. The reviewed supported interface still supplies one head and one linear chain, not that capability. An oracle union, cloned deterministic heads, or session forks do not supply it. [Multiple-draft analysis](halogen-multiple-drafts-20261011.md).

During this review, main's changelog showed **0.18.1**, including newly supported sampled structured output. Public main still documents the same PLD N,K opening/linear-verification contract; that is documented compatibility, not executed 0.18.1 validation or a positive candidate result. 0.18.0 refuses sampled schemas. No update/install recommendation or chronology claim follows from this browser observation. Versioned 0.18.0 docs were used for the completed candidate screen. [Current changelog](https://raw.githubusercontent.com/peonist-ai/halogen-flash-server/main/CHANGELOG.md), [current public flags](https://raw.githubusercontent.com/peonist-ai/halogen-flash-server/main/docs/FLAGS.md).
