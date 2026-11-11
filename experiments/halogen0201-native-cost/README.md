# Halogen 0.20.1 native MTP cost-rule experiment

**V5 runtime comparison completed with mixed results. The experiment stays default off.**

This exports the narrow implementation prepared for the native `gate / cost / gate` study. It adds `HALOGEN_MTP_GATE_RULE=gate|cost` to the bounded speculation policy and verifies that a replayed manifest's environment exactly matches its declared rule. `HALOGEN_MTP_GATE_LINE` remains unsupported and is rejected even if injected into persisted environment data. Omitting the rule preserves the normal native gate default. The normal server does not import this experiment directory.

## Reviewable change and exact bytes

- [changes.patch](changes.patch) is the human-readable two-file diff.
- [changes.json](changes.json) is the authoritative byte patch. It records offsets, removed/inserted bytes, before/after SHA256 and CRLF counts.
- [prepare.py](prepare.py) verifies the exact original 0.20.1 source manifest and all 47 members before applying the two edits to a new temporary copy. It regenerates only the two changed hashes in `profiles/sources.json`; every other manifest field remains intact.
- [proof-summary.json](proof-summary.json) records the finite native source evidence and engine identity. This is static evidence, not proof of live rule selection or runtime behavior.

The baseline manifest SHA256 is `d238cf78549c0c2771fb436cbc4fab3d09e18c51004593e4d265c4727ba9ba76`; the regenerated candidate manifest is `a3ad3a4165291831a7925c609d7f078d0c23bd2a384824d0e48dc5db4b5b6f7e`. A different version, line-ending conversion or combined observer patch is rejected. The nested `.gitattributes` preserves the review diff and metadata exactly. Do not use a text-normalized application of the review diff to bypass byte validation.

The public artifact contains no complete backend copy, credentials, model files or installed state. Its exporter copies the original source members only, excluding `.local`, to a new directory outside this checkout and outside any `backends` directory. It refuses an existing output path. It cannot install, start, stop or contact an engine.

## CPU-only verification

From the repository root:

```powershell
.\server\.local\venv\Scripts\python.exe -B experiments/halogen0201-native-cost/prepare.py --source backends/halogen-wsl2-0.20.1
.\server\.local\venv\Scripts\python.exe -B -m unittest discover -s experiments/halogen0201-native-cost -p test_candidate.py -q
```

The first command checks the candidate entirely in memory. The twelve portable tests export a temporary source copy and test actual service option parsing, persisted policy consistency, container argv, shadow-controller forwarding, source-manifest verification and print-only capacity behavior. They reject invalid and duplicate policies, replayed `GATE_LINE`, baseline drift and unsafe/existing outputs. No model request or hardware call is made. The private precursor's ten behavioral tests failed against the unmodified source, then passed with this same two-file change.

For manual inspection of a temporary export, pass `--write-output` with a new path outside this checkout. That creates source files only; it does not create an installed `.local` directory or make the export runnable as an engine service.

## Fresh native proof

The exact engine SHA256 is `7a72e138f0090008d171e41358a23f86a875fe92fadbcbc5daf2d3225e426577`. Unique fresh code signatures and actual FDEs identify initializer `0x1ebc3e0` (379 bytes) and greedy consumer `0x1eb7e30` (5456 bytes). The initializer maps `cost` to mode 3 at offset `0x4c` and stores its table pointer at `0x58`; the configuration copy at `0x1ecd234` places these at model offsets `0x1cc` and `0x1d8`. The consumer reads that mode and table for its conditional greedy cost calculation. Both fresh 516-byte tables match the retained values. Their defaults have not been calibrated on this host's workloads. No old RVA shift, complete transitive helper equivalence or live dispatch is assumed.

## Completed runtime comparison

The V5 `gate / cost / gate` comparison completed all six cohorts, each with one excluded warmup and three measured requests. All 24 responses preserved the exact output bytes for their input size, and the normal authenticated server was restored on port 8840. RAW rates include observer and trace overhead. [Completed results](../../docs/benchmarks/halogen0201-mtp-cost-gate-20261110.md), [V5 protocol](../../docs/benchmarks/halogen0201-mtp-cost-gate-plan-20261110-v5.json).

At 8192 input tokens, cost raised API head acceptance from 59.43% to 64.95%, while decode reached 42.54 tok/s against gate controls of 46.82 and 45.38. At 16384 tokens, acceptance rose from 50.46% to 58.16%, and decode reached 44.19 tok/s against 42.71 and 39.09. The controls drifted materially. Candidate prefill and whole-HTTP results fell between the controls, leaving a general serving improvement unqualified. The normal profile uses the confidence gate, with no automatic promotion of the cost candidate. [Numeric evidence](../../docs/benchmarks/halogen0201-mtp-cost-gate-20261110.json).

All measured arms explicitly set `HALOGEN_DRAFT_VOCAB_Q8=0`, fixing the draft vocabulary at Q4. They used PLD `3,3`, gate threshold `0.90`, one 32K slot/pool, paired 2048 prefill settings, Cache Off and Thinking Off. The frozen nonrepetitive inputs contained 8192/16384 tokens and generated exactly 128 tokens. The cost rule was the sole treatment.

API all-neural head acceptance and the narrower native chain counters retain their declared scopes. Independent reconstruction of the full accepted count remains unavailable, and `acceptance_independently_reconciled` stays false. [Counter-scope evidence](../../docs/research/halogen0201-counter-scopes-20261110.md).

Root owns future observer transformations, source registration, lifecycle comparisons and restoration. Startup admission stays 30/131 GiB physical/commit, runtime reserve 18/18 GiB, and measurement entry 22/22 GiB. Each campaign must leave the selected normal server ready and online. Further arena and exact-history cache proposals are recorded in the opportunity report. [Opportunity report](../../docs/research/halogen0201-opportunities-20261110.md).
