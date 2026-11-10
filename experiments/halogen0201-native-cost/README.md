# Halogen 0.20.1 native MTP cost-rule experiment

**Status: inert source candidate; not deployed or performance-qualified.**

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

## Controlled runtime comparison remains separate

The [opportunity report](../../docs/research/halogen0201-opportunities-20261110.md) explains why acceptance alone is insufficient. The existing [prospective study](../../docs/benchmarks/halogen0191-mtp-cost-gate-plan-20261107-v2.md) supplies the comparison shape; its old engine identity must be replaced with fresh combined-source registration before execution.

All projected arms explicitly set `HALOGEN_DRAFT_VOCAB_Q8=0`; this common Q4 declaration is separate from the sole across-arm rule change. Keep PLD `3,3`, positive gate `0.90`, one 32K slot/pool, paired 2048 prefill settings, Cache Off and Thinking Off. Use the frozen nonrepetitive 8192/16384-token inputs and exact 128-token outputs, with an excluded warmup and three measurements per size and arm. Reconcile native banner, request IDs and scoped neural-head counters separately from lookup/grammar counters. Preserve output bytes and finish semantics, and require useful-output throughput gains beyond observed bookend variability before adoption.

Root owns any combined observer transformation, new manifest registration, normal lifecycle comparison and restoration. This artifact does not run that comparison. Startup admission stays 30/131 GiB physical/commit, runtime reserve 18/18 GiB, and measurement entry 22/22 GiB. The original selected server profile must be restored and left online afterward. No local cost-rule throughput or acceptance improvement is claimed.
