# 0.17.3 native bulk BN64 engine cohort

Frozen synthetic pseudoprose uses8192 input tokens from116 repeated calibration units and128 ordinary output tokens. Each before/candidate/after arm has one excluded warmup and three measured requests. This is not a natural long-input result and no NPU execution is claimed.

| Arm | Native prefill tokens/s | Native decode tokens/s | Accepted/drafted |
|---|---:|---:|---:|
| Before | {before_native_pp} | {before_native_tg} | {before_accepted}/{before_drafted} |
| Candidate | {candidate_native_pp} | {candidate_native_tg} | {candidate_accepted}/{candidate_drafted} |
| After | {after_native_pp} | {after_native_tg} | {after_accepted}/{after_drafted} |

Actual rates are measured native API response timings. Acceptance counters combine native MTP and PLD and remain separate from Prefill and Decode rates.

Request hashes: {identical_request_hashes}. Output hashes: {identical_output_hashes}. Acceptance counters: {identical_acceptance}. Native audit before/after proves {actual_affected_transactions} committed bounded transactions, with started=committed, complete contiguous hit logs and no rollback/failure. The rejected counter measures stock-forwarded launches and is not a failure counter. No universal or all-layer hit claim is made.

Three-arm clock scaling comparable within0.1%: {three_arm_clock_comparable}. Candidate/before: {before_pair_clock_comparable}. Candidate/after: {after_pair_clock_comparable}. Report monotonic/raw ranges and raw/QPC checks. Apply no clock normalization. Unequal clocks leave corresponding raw percentage deltas descriptive and unqualified.

Candidate versus before: native prefill {pp_delta_before}%, native decode {tg_delta_before}%. Candidate versus after: native prefill {pp_delta_after}%, native decode {tg_delta_after}%. Pooled stock means use all six measured stock requests, with native rate ranges {stock_ranges}.

Bounded comparison qualification: {qualification}. Qualification issues: {issues}. Component evidence justifies the trial; the full-engine cohort supplies the net serving evidence. Candidate activation and final disposition remain root-owned. These observations do not qualify the broader goal.

Evidence: `{before,candidate,after}/summary.json`, `candidate-audit-before.jsonl`, `candidate-audit-after.jsonl`; generated `cohort-analysis.json` retains input hashes and `cohort-report.md` supplies the filled report. Run `python analyze.py` only after all three summaries and audit snapshots are frozen.
