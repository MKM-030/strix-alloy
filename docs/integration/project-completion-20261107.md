# Halogen update and project consolidation, 7 November 2026

Halogen 0.19.1 was installed and qualified with the normal v2 text profile on
`http://127.0.0.1:8840/v1`. The dated runtime receipts recorded matching API and
engine versions, authenticated discovery of `halogen-v2` and the persistent
Voice selection of the verified profile. The normal Voice startup check
completed successfully. The **13:04 UTC** readiness record is a historical
snapshot. After the later campaigns, the **7 November 15:31:03 UTC** functional
check recorded the normal two-slot, pool-65536, concurrency-two, paired-2048
profile ready with controller/backend PIDs **25272/28248**. Model discovery
returned HTTP 401 without authentication and HTTP 200 with authentication.
Authenticated chat returned HTTP 200 and `READY`. The same runtime identities
were ready and idle before and after that functional availability request.
The private proof is
`server/.local/halogen-update-20261107/primary0191/final-functional-check/proof.json`.
[Update record](../research/halogen0191-update-20261107.md).

The qualification flags in the package's `release.json` retain static
prequalification artifact metadata. The separate dated runtime and provider
receipts supply the observed qualification evidence.

The **15:13 UTC** bounded source check retained **0.19.1** as the latest official
tag and image with the same immutable identities. Direct Reddit access returned
HTTP 403 and cached web listings left current subreddit freshness unverified.
The next refresh is due at or after **17:13:05 UTC**.
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
| Migration checks | 4 passed |
| Normal Voice startup check | Exit 0 |
| Frozen model requests | Eight complete requests, one excluded warmup and three measurements per input |

The optional `jsonschema==4.26.0` test dependency was installed into an ignored
test target and supplied through `PYTHONPATH`. The private test logs, final
summary and startup-check receipt are retained under
`server/.local/halogen-update-20261107/voice-completion/`.

The normal serving profile selects two 32768-position slots, pool 65536,
concurrency two and paired 2048 prefill settings. Its earlier complete 8K/16K
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

## Remaining optimization scope

Independent qualification of the API phase clocks, a completed matched PLD
comparison, qualified 4096-prefill gain, a matched engine-only comparison and a
beneficial NPU contribution remain required for the broader project acceleration
goal. The OEM mode
readback requires an elevated process. The source refresh identified further
kernel and speculative-verification mechanisms in WHIRL and libosmos for
separate qualification. [WHIRL release](https://github.com/tsaipifong/whirl-llm/releases/tag/v0.2.5.1),
[libosmos](https://github.com/mrsirg97-rgb/libosmos).
