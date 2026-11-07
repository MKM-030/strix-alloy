# Halogen update and project consolidation, 7 November 2026

Halogen 0.19.1 is installed and the selected v2 text server is ready on
`http://127.0.0.1:8840/v1`. API and engine versions agree. Authenticated model
discovery advertises `halogen-v2`. The persistent Voice selection points to
the verified new profile. The normal Voice startup check completed successfully.
[Update record](../research/halogen0191-update-20261107.md).

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

The selected runtime uses two 32768-position slots, pool 65536, concurrency two
and paired 2048 prefill settings. Its complete 8K/16K observations retain the
actual input lengths, API phase values, acceptance counts and Windows QPC
whole-request times. A separate larger-arena candidate stopped at request
admission after its excluded warmup. The 2048 configuration is the current
launcher default. [Measurement report](../benchmarks/halogen0191-natural-8k16k-20261107.md).

## Remaining optimization scope

Independent RAW qualification for these new phase clocks, a matched engine-only
comparison and a beneficial NPU contribution remain open. The current OEM mode
readback requires an elevated process. The source refresh identified further
kernel and speculative-verification mechanisms in WHIRL and libosmos for
separate qualification. [WHIRL release](https://github.com/tsaipifong/whirl-llm/releases/tag/v0.2.5.1),
[libosmos](https://github.com/mrsirg97-rgb/libosmos).
