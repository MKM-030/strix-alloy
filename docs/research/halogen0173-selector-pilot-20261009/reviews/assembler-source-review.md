# Independent assembler review

Source and retained-artifact review on 2026-10-09. Reviewed
`../npu-selector-real-cohort-20261009/assemble_cohort.py` at SHA-256
`452d0df59eebd4f5093117e06fda8587f86fbbef740270ca00d8780a0a5b68a6`.
No assembler, verifier, model fitting, tests, hardware probe, API, or lifecycle
operation was executed by this reviewer. Root still executes the completed
cohort's offline review before fitting.

No remaining concrete ingestion blocker was found against the corrected
`check_cohort.py` contract. Two findings were sent promptly and resolved by the
assembler's owner before this final source hash:

1. The evidence originally named launch-sealed `collect_requests.py` as the
   capture client. Root actually executed its separately reviewed derivative
   `collect_requests_v2.py` (root-reported execution 19869), SHA-256
   `55d95c1f287a7c9e7a6f02dd59ce1f93a23b9d467f86a8a442d0895858ca2bd3`.
   The corrected assembler retains an immutable copy of v2, requires its exact
   root-recorded hash, and explicitly states that it is not launch-sealed. The
   original v1 is retained only as the historical launch-sealed parent. The
   launch seal must not be relabeled as a seal of the later v2 client.
2. The copied manifest retained `frozen-inputs-not-collected` status despite
   filled native bindings. The corrected assembler now uses
   `observed-collected-pilot-awaiting-offline-review`, preserving the original
   prepared manifest and all frozen payload/document bytes.

## Concrete evidence inspected

The capture summary contains the exact 16 frozen IDs in their original order,
10 train and six test. Actual API prompt usage is 550–734 tokens. All requests
completed 128 output tokens, totaling 2048. Their unique native log IDs are
3 through 18; startup serial probes account for the preceding IDs. The retained
decoded journal has 797 complete rows: 701 neural and 96 PLD. Neural causal
depth_low values are [2], depth_high values [0], and adaptive values [0]. The cost
reader reports complete round costs and verified qualified closure. These are
retained observations, not a new decoder execution by this reviewer.

The before/after source and mounted identities are unchanged for the checkpoint,
N-gram source, tokenizer file set, and tokenizer per-file identities. The
checkpoint and N-gram source identities are tied to the complete-file integrity
receipts. Actual inspected mounts select the named source paths; mounted/source
model identities match, with any device-number distinction explicitly retained.
The six actual frontend tokenizer files and their hashes match between mounted
and source directories, before and after collection. Their compact sorted-file
hash rule matches the offline reviewer's rule.

The actual native engine identity is container PID 87, start_ticks 270076,
`/usr/local/bin/flash_serve`, unchanged across the snapshots. The retained maps
include the named checkpoint and N-gram files. The assembler accurately labels
its other process identity as the Windows private gateway controller. It does
not claim a sampled container frontend PID, native GPU byte attestation, or
in-process tokenizer equivalence that the snapshots did not obtain.

## Request/receipt contract

The assembler verifies the original prepared manifest hash before resolving the
exact payload and document hashes. It keeps the public model alias in the frozen
payload; the gateway's existing model rewrite is the understood upstream step.
Actual v2 source reads and submits that frozen payload unchanged, disables
redirects, and retains the root's private 8842 route and ownership checks.
Credential references remain scoped to the private profile/backend files. No
credential contents are read by the assembler. Private-route and normal-port
exclusion statements are attributed to root's recorded client execution and
retained terminal/profile evidence rather than fabricated as new runtime probes.

For every request, byte-aligned native intervals contain exactly one matching
Birth and Retire owner. Full native wire IDs are matched to the unique ID in the
retained log interval, normalized modulo 2^64 only when parsing a signed native
log integer. Per-request idle health completed increases by one, with cancelled
unchanged. Actual decoded Begin/Outcome rows must lie strictly inside that
owner's sequence interval. A new request cannot reuse the same nonce/wire/owner
triple. The original decoded JSON is retained and hash-bound without assigning
caller-supplied document or tokenizer metadata to its rows.

Fixed width proof uses the actual low=2/adaptive=0 Begin fields and root's loaded
depth-two profile; high=0 is retained rather than rejected or rewritten. Native
allowance remains an independent per-row eligibility condition for the policy.
The assembler does not derive causal width from the later attempted count and
does not convert PLD rows into neural labels.

All path references are absolute or resolved from their containing JSON, so the
assembled loaded-assets, request provenance and manifest references match the
offline reviewer's expected roles. Actual response text hashes, API usage and
full-request accepted/drafted counters retain their scope separately from the
complete native label-row aggregates.

## Parity and limits

A normal bookend is considered complete only when its response, passed result,
and both health files exist. Completed comparisons use exact unstripped UTF-8
response content hash and accepted/drafted API counters. A missing bookend keeps
`observed=false`, `passed=false`, and `normal_response=null`; a partial response
is preserved under a separate evidence field. The assembler does not pretend
that absent normal outputs prove parity. The offline reviewer independently
compares any present normal response and rejects a mismatch.

This parity scope is text/counter equality on the paired retained calls. It does
not claim a full native output-token tape, complete frontend process attestation,
statistical generalization, performance qualification, or policy speed gain.
Actual native cost intervals include observer overhead and remain stock-only
observations. No CPU/GPU/NPU placement result is produced by assembly.
