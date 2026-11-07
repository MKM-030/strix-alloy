# Halogen 0.19.1 draft-vocabulary precision study

This prospective study compares the existing GPU draft-vocabulary control at
Q4, Q8 and Q4 again. The target checkpoint and verification path retain their
current precision. Q8 uses 2720 logical bytes per packed row against 1440 for
Q4. Its additional accuracy and whole-engine performance require measurement.
The native automatic bank selector retains its existing cost coefficients.

## Frozen comparison

| Parameter | Value |
| --- | --- |
| Actual input tokens | 8192 and 16384, existing contiguous novel prefixes |
| Actual output tokens | Exactly 128 per request |
| Sampler | Temperature 0, seed 1, MTP, Thinking Off |
| Cache | Off, zero reused tokens |
| Capacity | One 32768-position slot and pool, concurrency one |
| Prefill chunk and arena | Both 2048 |
| Other speculation | PLD 3,3 and MTP gate 0.90 |
| Q8 control across arms | Integer 0, 1, 0 |
| Native trace across arms | `HALOGEN_SERVE_TRACE=1` |
| RAW observation across arms | Enabled identically |
| Per input and arm | One excluded warmup and three measurements |
| Complete experiment | 24 generation requests |

The accompanying JSON freezes request hashes, source identities, the inactive
candidate bundle and the selected serving profile before execution.
[Frozen parameters](halogen0191-draft-vocab-q8-plan-20261107.json).

## Qualification and reporting

Both inputs require all three complete arms. Every response must preserve
exact output bytes and token counts across the comparison. Report unadjusted
RAW phase bounds, complete-request QPC time and pooled native-head acceptance
separately. API phase clocks retain their existing qualification limits.

Each saved native trace must join to the exact API/RAW request ID and match
head, lookup and grammar counters. Positive head work and selected-bank target
counts are required. Lookup rounds, drafted tokens and accepted tokens must
all equal zero for this natural-text head study. Failed and partial cohorts
remain recorded.

The existing trace corroborates bank selection over emitted targets. It does
not directly observe dtype at every GEMV dispatch. Declared Q8 precision is
bound through the manifest environment and pinned native loader/consumer
branch. The full native output-ID sequence remains unobserved.

Configuration selection follows measured whole-engine performance and exact
output preservation. Effects within run or bookend variability remain
inconclusive. A higher acceptance ratio alone supplies insufficient throughput
evidence. The current serving profile remains selected pending broader review.

## Lifecycle

Root checks current identities, existing sessions, actual games and other GPU
activity before a hardware campaign. The coordinator checks 22/22 GiB physical
and commit headroom before creating the run or stopping the online server.
Normal startup still requires 30/131 GiB. Each measured request requires
22/22 GiB and the runtime guard retains 18/18 GiB.

The current one-slot serving profile is restored through the existing normal
lifecycle after the finite experiment. Models, drivers, BIOS, voltages and
global WSL settings retain their existing configuration.

The preparation command performs source checks only.

```powershell
.\server\.local\venv\Scripts\python.exe -B .\server\.local\halogen-update-20261107\primary0191\raw-phase-prep\root_campaign.py --experiment draft_vocab_q8
```

Root adds `--run` after current handles and resource admission have been
verified. Observation timeouts continue the same confirmed handle. The
experiment has generated no model requests at registration.
