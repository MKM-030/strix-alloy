# Halogen 0.19.1 native MTP cost-rule study

This prospective study compares the native confidence rule with the existing
internal cost rule. The cost rule estimates joint draft-prefix survival and
compares its value with marginal drafting and verification costs. Its tables
and configuration fields already exist in the pinned engine. The rule adds
no model or KV reservation. Whole-engine benefit requires measurement.

## Frozen comparison

| Parameter | Value |
| --- | --- |
| Actual input tokens | 8192 and 16384, existing contiguous novel prefixes |
| Actual output tokens | Exactly 128 per request |
| Sampler | Temperature 0, seed 1, MTP, Thinking Off |
| Cache | Off, zero reused tokens |
| Capacity | One 32768-position slot and pool, concurrency one |
| Prefill chunk and arena | Both 2048 |
| Other speculation | PLD 3,3 and positive MTP gate 0.90 |
| Draft-vocabulary control | `HALOGEN_DRAFT_VOCAB_Q8=0` in every arm |
| Rule across arms | Literal `gate`, `cost`, `gate` |
| Native trace across arms | `HALOGEN_SERVE_TRACE=1` |
| RAW observation across arms | Enabled identically |
| Prefetch | 0 |
| Per input and arm | One excluded warmup and three measurements |
| Complete cohort comparison | 24 cohort generation requests |

The companion JSON freezes request hashes, source identities, the combined
inactive observation/policy bundle and the selected normal profile before
execution. The original Q8 study retains its own frozen protocol.
[Frozen parameters](halogen0191-mtp-cost-gate-plan-20261107.json).

The managed startup path also performs two serial correctness requests per
successful launch. These inherited qualification requests and any upstream
startup warmup remain outside the comparison cohorts and their timing means.

## Qualification

Both inputs require all three complete arms. Every response must preserve
exact output bytes, token counts, finish behavior and output-cap semantics.
Warmups remain excluded from timing summaries. A failed or partial cohort
retains its evidence and leaves the whole comparison unqualified.

The saved service manifest and a single native startup banner must establish
the declared rule for each engine. Native request traces must reconcile with
the exact API/RAW request IDs and neural, lookup and grammar counters. The
eight requests across both inputs must have unique IDs within each engine
arm. Neural-head activity must be positive. Lookup and grammar rounds,
drafted tokens and accepted tokens must all be zero for this neural-policy
study. A full-vocabulary fallback remains eligible for the native cost rule.

The exporter recomputes these checks from saved files and pinned sources.
The fixed Q4 declaration follows the manifest and native loader path. Direct
dtype observation at every dispatch remains outside this study's evidence.

Report RAW prefill/decode bounds, complete-request Windows QPC time and pooled
neural-head acceptance separately. RAW brackets include observer overhead.
API phase clocks retain their existing qualification limits. Selection
requires a complete comparison with useful-output throughput gains beyond
observed run and bookend variability, together with output preservation.
Acceptance remains a separate descriptive metric. The normal serving
profile remains selected pending broader performance review.

## Lifecycle and source registration

Root verifies actual processes, existing sessions, idle state, games and other
GPU activity before hardware work. The coordinator requires 22/22 GiB
physical and commit headroom before creating a run or stopping the online
server. Normal startup retains 30/131 GiB admission, every cohort request
retains 22/22 GiB entry admission, and runtime guards retain 18/18 GiB.

The coordinator verifies the committed prospective plan and finite source
pins, then records executed-source identities before the first server stop.
Confirmed live lifecycle handles continue across observation timeouts. Each
terminal comparison restores the exact selected normal profile through the
existing managed lifecycle and leaves the endpoint ready and open.

The source-only command prepares and validates the experiment.

```powershell
.\server\.local\venv\Scripts\python.exe -B .\server\.local\halogen-update-20261107\primary0191\cost-gate-cohort-prep\root_campaign.py --experiment mtp_gate_cost
```

Root adds `--run` after source registration, current handles and actual
resource admission have been verified. The study has generated zero model
requests at registration.
