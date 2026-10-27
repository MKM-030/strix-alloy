# Halogen gate0.95 measurement implementation plan

> **For agentic workers:** Execute the finite steps below with test-first development and independent review. Root alone owns hardware and lifecycle.

**Goal:** Test whether the supported greedy MTP confidence gate0.95 improves the complete unchanged8K and16K requests against gate0.90 controls.

**Architecture:** Prepare private packets and a reversible two-file policy allowlist transition. Run normal0.90 before, candidate0.95, and restored normal0.90 after. Use the existing owned lifecycle, complete HTTP QPC measurement, native draft counters and unchanged output accounting. Restore and leave the normal server online even after a terminal failed cohort.

**Tech stack:** Local Windows PowerShell/Python3.12; existing pinned0.18.16 Docker/WSL engine and measurement clients.

**Spec:** `server/.local/halogen-update-20261025/primary01816/mtp-gate095-20261026/DESIGN.md`

## Constraints and review focus

- User authorized autonomous measurement restarts,30GiB startup and18GiB physical/commit runtime reserve;22GiB before each new cohort. Keep normal admission/lease policies.
- One engine; no NPU, model, driver, BIOS, voltage or global WSL changes. Voice owner acknowledged source-only coordination.
- Only `scripts/speculation_policy.py` and `profiles/sources.json` may change while the verified engine is terminal. Candidate profile changes only gate0.90 to0.95; MTP depth remains absent.
- Runtime source domain is31, static closure45 for the normal engine. RAW's32/46 does not apply. Preserve full static closure independently.
- Frozen natural requests:8192/16384 actual input,128 output, one excluded warmup and three measurements per workload/window;24 total requests, no retries.
- Require identical request/output hashes, finish reasons and token counts. Draft/accepted counts may genuinely differ. Acceptance alone is not a speed result.
- Candidate promotion requires at least3% whole-request improvement against both controls on both workloads; no statistical-significance or clock-corrected phase-rate claim.
- Failure handling: foreign bytes prevent transitions; partial known transitions can roll back; live pending handles must be continued, never replaced after observation timeout.

## Tasks

- [x] Agent: test-first shadow allowlist; exact profile/payload lineage; derive31/45 source domains, attest and freeze both packets.
- [x] Root: test two-file transition safety (prevalidate all inputs, reject foreign rollback, recover partial owned apply). Implement finite driver from existing fixed2 comparison/lifecycle helpers; add no device or callback hooks.
- [x] Independent reviewer: inspect transition, packet pins, accounting and restoration. Root repeats relevant CPU tests and verifies live identities/GPU load before hardware work.
- [x] Root: execute the single matched cohort; continue actual sessions until terminal. Verify source rollback and normal ready generation; close only own terminal measurement helpers.
- [x] Independently audit saved results. Save raw evidence/report and continuation, inform Voice owner of actual restored generation. Do not commit mixed foreign workspace changes or claim the full optimization goal achieved.

The prior source-only assessment had deferred this value without measuring it. This experiment tests the uncertainty; it does not claim new confidence or per-round cost evidence, nor reopen a negative measured0.95 cohort.

Source checkpoint: the per-arm GPU preflight now uses the same reviewed predicate
as the separate PLD trial. A successful high-load receipt failed its regression
before the fix;27 gate tests and33 PLD tests now pass. Independent narrow review
confirmed unchanged lifecycle/retirement/restoration code and a PLD-only refresh
of its parent driver hash. Both trials remain unexecuted while the verified
Grounded2 process occupies the GPU. Normal0.18.16 remains online.

Current source pins and superseding preparation:
`server/.local/halogen-update-20261025/primary01816/mtp-gate095-20261026/coupled-gpu-preflight-root-receipt.json`.

Completed result:24 benchmark requests, all output/request/count/finish parity
passed. Candidate whole-HTTP means were6.8953015s at8K and11.9355431s at16K;
final0.90 controls were6.6633314s and11.8662518s. Candidate failed promotion.
The8K head acceptance fraction rose66.04 to67.35percent while accepted tokens
per native round fell1.2281 to1.0820. Native phase clocks remain unqualified;
no new headline token rates or NPU gain are inferred. Full independent saved
audit and exact raw reconstruction are retained in the live cohort folder.
