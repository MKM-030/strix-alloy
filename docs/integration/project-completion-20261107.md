# Halogen update and project consolidation, 7 November 2026

Halogen 0.19.1 was installed and qualified with the normal v2 text profile on
`http://127.0.0.1:8840/v1`. The dated runtime receipts recorded matching API and
engine versions, authenticated discovery of `halogen-v2` and the persistent
Voice selection of the verified profile. The normal Voice startup check
completed successfully. The **13:04 UTC** and **15:31 UTC** readiness records
are historical snapshots. The **7 November 17:09:37 UTC** functional
check recorded the selected one-slot, pool-32768, concurrency-one, paired-2048
profile ready with controller/backend PIDs **28972/24440**. Model discovery
returned HTTP 401 without authentication and HTTP 200 with authentication.
Authenticated chat returned HTTP 200 and `READY`. The same runtime identities
were ready and idle before and after that functional availability request.
The private proof is
`server/.local/halogen-update-20261107/primary0191/completion-closure/final-functional/proof.json`.
[Update record](../research/halogen0191-update-20261107.md).

The later two-slot restoration reported `physical_low` at request admission
with about 21.57 GiB available against its 22 GiB floor. The supported one-slot
selection retains 32K context capacity and serializes requests. Its persistent
Voice selection was refreshed through the existing controller-consumer contract.

The qualification flags in the package's `release.json` retain static
prequalification artifact metadata. The separate dated runtime and provider
receipts supply the observed qualification evidence.

The bounded source refresh completed at **17:17:34 UTC** retained **0.19.1**
as the latest official tag and image with the same immutable identities.
AMD GPU, Ryzen AI, XRT and WHIRL release fields were unchanged. The refresh
identified libosmos 0.5.4 and retained its separate upstream 16K expert-table
placement result for further compatibility work. Direct Reddit access returned
HTTP 403 and cached web listings left current subreddit freshness unverified.
The next refresh is due at or after **19:17:35 UTC**.
[Official package](https://github.com/peonist-ai/halogen-flash-server/pkgs/container/halogen-flash-server),
[official tag](https://github.com/peonist-ai/halogen-flash-server/tree/v0.19.1).

## Source consolidation

All original local branch tips are ancestors of the completion branch. The
integration retained missing admission diagnostics, pending regression tests
and planning documents. Patch-equivalent histories were recorded in an audited
merge whose resulting source tree matched the reviewed integrated tree.

The completion fixes cover owned legacy acknowledgement preemption, provider
identity in context fixtures, current HTTP-session ownership and deterministic
reserved-slot test handshakes. Source guards and cancellation deadlines retain
their production checks. The private ASR manifest and its launcher pin were
refreshed for the two integrated source members.

Sixteen clean, merged worktrees were physically removed through Git. Before
removal, 146 unique ignored files totaling 2,421,437 bytes were archived with
individually verified hashes. The private archive inventory is
`server/.local/halogen-update-20261107/worktree-preservation/inventory.json`.
Its SHA256 is
`8e670090107d2e866dbb6db5d8be6fe688f482c28b7cb63c2f8f222a163fa37e`.
Observed free space on C increased by 1,309,507,584 bytes during cleanup.
The primary checkout is the remaining Git worktree.

## Verification

| Scope | Result |
| --- | --- |
| Native Voice suite | 1,705 passed, zero failures, errors or skips |
| Server suite | 236 passed |
| PowerShell 5.1 launcher suites | 18 passed |
| Focused version forwarding and capacity checks | 25 passed, also covered by the server suite |
| New backend capacity checks | 15 passed |
| Final campaign, collector, QPC and exporter checks | 115 passed |
| Migration checks | 4 passed |
| Normal Voice startup check | Exit 0 |
| Frozen model requests | Eight complete requests, one excluded warmup and three measurements per input |

The optional `jsonschema==4.26.0` test dependency was installed into an ignored
test target and supplied through `PYTHONPATH`. The private test logs, final
summary and startup-check receipt are retained under
`server/.local/halogen-update-20261107/voice-completion/`.

The earlier serving profile selected two 32768-position slots, pool 65536,
concurrency two and paired 2048 prefill settings. Its complete 8K/16K
observations used synthetic prose and a contiguous novel excerpt respectively,
and retain actual input lengths, API phase values, acceptance counts and
Windows QPC whole-request times. A separate larger-arena candidate stopped at
request admission after its excluded warmup. The 2048 configuration is the current
launcher default. [Measurement report](../benchmarks/halogen0191-natural-8k16k-20261107.md).

A later genuine natural **8192-token RAW cohort** completed one excluded warmup
and three measurements. The two-slot, pool-65536, paired-2048 PLD `3,3` before
arm recorded RAW midpoint means of
**1185.559992 prefill tok/s** and **48.802438 decode tok/s**, with pooled
native-head acceptance **207/327, or 63.30275%**. The full PLD comparison failed
before a matched three-arm result qualified. Its 16K case completed only the
excluded warmup, and the code oracle failed. RAW bounds include observer
overhead and API phase clocks remain unqualified.
[PLD RAW report](../benchmarks/halogen0191-pld34-raw-20261107.md).

The separate prefill comparison completed genuine natural 8K and 16K before
cohorts with **one slot, pool 32768, concurrency one and paired 2048 prefill
settings**. Each excluded one warmup and included three measurements with 128
actual output tokens. RAW midpoint prefill/decode means were
**1143.700731/48.574773 tok/s** and **1124.357529/49.677162 tok/s**, with pooled
native-head counts **207/327 (63.30275%)** and **210/321 (65.42056%)** respectively.
Its paired-4096 candidate completed only the 8K excluded warmup before failing
the 22 GiB request-entry gate. The campaign ended and restored the normal
two-slot/2048 profile.
[Prefill RAW report](../benchmarks/halogen0191-prefill4096-raw-20261107.md).

A copied-log performance study completed one before cohort with one excluded
warmup and three measurements. Each used 3539 input and 1259 generated tokens.
RAW midpoint means were **1161.93 prefill / 105.33 decode tok/s**, with native
head acceptance **69/84 (82.14%)** and lookup acceptance **3228/3234 (99.81%)**.
The frozen reference preserves a recorded serial response with one missing
canonical final LF. The PLD `3,4` candidate failed the unchanged startup
admission before generation, leaving the three-arm comparison incomplete.
[Single-condition result](../benchmarks/halogen0191-pld34log-reference-retry1-raw-20261107.md),
[GPU-gated earlier attempt](../benchmarks/halogen0191-pld34log-reference-raw-20261107.md),
[original failed task oracle](../benchmarks/halogen0191-pld34log-raw-20261107.md).

## Remaining optimization scope

The current qualified natural-text RAW prefill measurements span
**1124.36–1185.56 tok/s**. The retained 0.18.22 cohorts recorded
**1917.24/1913.00 tok/s** at 8K/16K. The cause of this shortfall remains
unresolved across the separate profiles and request records. The 4096 candidate
has no qualified gain. [Current PLD cohorts](../benchmarks/halogen0191-pld34-raw-20261107.md),
[current prefill cohorts](../benchmarks/halogen0191-prefill4096-raw-20261107.md),
[retained 0.18.22 cohorts](../benchmarks/halogen01822-raw-8k16k-20261101.md).

Retained NPU screens include an M8192 producer that changed **88,572,989 of
104,857,600 native BF16 words**, and a ready64 whole-embedding consumer
substitution measured **21.8% slower**. Those candidates remain closed. A
separate historical Halogen 0.15.1 helper-coexistence test reduced MTP decode
from **43.13 to 39.93 tok/s**. These observations retain their original
component and coexistence scopes. [NPU producer assessment](../research/npu-independent-roi-20261010.md),
[retained consumer result](../research/halogen0185-npu-table-disposition-20261015.md),
[historical coexistence and component results](../benchmarks/halogen-npu-practical-result-20261005.md).

The installed update, source consolidation and validation establish the delivery
record. Broader prefill/decode acceleration and a beneficial end-to-end NPU
contribution remain unqualified. Any qualified copied-log gain retains that
workload and profile scope. API phase-clock qualification and a matched
engine-only comparison remain open. OEM mode readback requires an elevated
process.
