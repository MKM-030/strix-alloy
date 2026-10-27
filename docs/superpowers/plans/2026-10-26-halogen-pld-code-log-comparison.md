# Native PLD chain7 code/log comparison plan

> **For agentic workers:** Root owns all engine and hardware work. Use the frozen source preparation and workload receipts below; independent review precedes live execution.

**Goal:** Determine whether increasing native prompt-lookup draft length from3 to7 improves useful code-edit/log-quote requests, while keeping exact greedy answers and the existing MTP head policy.

**Architecture:** A separate0.18.16 whole-engine control/candidate/control comparison, derived from the current31-runtime/45-static-source protocol. This is an additional workload family, not a replacement for the frozen natural8K/16K benchmark. The earlier gate0.95 comparison remains separate.

**Tech stack:** Local PowerShell/Python, existing pinned0.18.16 v2 engine, CPU tokenizer and strict HTTP accounting. No new model, native callback, GPU kernel, NPU, driver or global setting.

**Source/design inputs:**

- `server/.local/halogen-update-20261025/primary01816/pld-chain7-source-20261026/preparation-receipt.json`
- `server/.local/halogen-update-20261025/primary01816/pld-copy-workload-20261026/DESIGN.md`
- `server/.local/halogen-update-20261025/primary01816/reddit-gufo-win030-20261026/assessment-receipt.json`
- Versioned native FLAGS declares K<=7 in8 verify rows. This does not expand the separate private external consumer's1..3 ABI.

## Constraints

- Current normal configuration: v2,32K capacity,chunk/arena8192,prefetchOff,ThinkingOff,CacheOff/no_store,gate0.90,PLD3,3. Candidate changes only PLD to3,7.
- The source stage adds only explicit `3,7` to the existing allowlist and updates its source-manifest hash. Preserve exact rollback. Rebase explicitly if the installed normal source later changes; never overwrite differing bytes.
- Preserve user-authorized30GiB startup,131GiB launcher commit admission,18GiB physical/commit runtime reserve and22GiB new-request entry reserve. One engine; no game/unrelated-program stops.
- Complete the separately prepared gate0.95 experiment first when GPU load permits. Do not combine gate and PLD changes.
- Before a new cohort, revalidate actual current processes, creation identities, sessions, idle API and background GPU load. Confirm terminal owners and containers before source transition. Live observation timeout is never restart permission.

## Tasks

- [x] Prepare and independently verify the exact two-file PLD7 source shadow; keep installed bytes unchanged.
- [x] Freeze representative public code-edit8K and authored log-diagnosis16K tasks with exact CPU-tokenized input lengths and provenance. These are fixtures, not observed ServiceNow production data. No looped token padding or manufactured100% acceptance.
- [x] Derive new control/candidate packets from the corrected normal protocol. Freeze new case names/payloads and exact policy delta. Preserve both31 runtime and45 static source domains; full actual Docker environment must prove PLD and absent MTP_DEPTH.
- [x] Adapt only case/request validation and the response-length contract:128 is an output cap, not required filler. Require0<actualOutput<=128, stop/length finish reason, consistent usage/timings, and identical count/hash/finish reason for matched requests in all arms. Keep native counter sums, memory checks and HTTP QPC arithmetic unchanged.
- [x] Add static task-quality checks for the required edit and quoted diagnostic facts. Never execute model-returned code.
- [x] Inspect actual first-control outputs for useful task completion; a parity match between two wrong answers is insufficient. Root's static review records a correct code function but truncated explanation, and a complete log answer.
- [x] Independently review packet lineage, quality/accounting and exact restoration. Use the reviewed nonsticky visible launcher and retirement fix from the gate0.95 driver; do not adopt an unobserved backend generation.
- [x] Run one excluded warmup plus three measured requests per task per arm,24 requests total, no request retries. Record head,lookup,grammar and combined draft acceptance separately. A chain length of7 does not imply seven accepted drafts.
- [x] Check exact output/task parity and at least3% lower whole-request QPC mean against both controls on both tasks before considering promotion. Numerical threshold failed. Sample spread is retained; no statistical significance or general prose acceleration is claimed.
- Phase qualification was not applicable: the complete comparison did not show a useful improvement. No new Prefill/Decode headline rates are published.
- [x] Restore exact normal source/profile, verify actual ready generation and leave it visible/online. Save raw evidence and continuation. Do not commit mixed foreign workspace edits or mark the full NPU/optimization goal complete.

## Source preparation checkpoint

Root repeated all33 CPU tests successfully. All161 sealed packet files and the
installed baseline policy/manifest hashes remain unchanged. Independent review
found one inherited GPU-admission gap; a focused RED-to-GREEN fix now rejects
malformed/failed telemetry and any unassessed engine row above5percent before
each collection. This is a conservative preflight, not a performance guarantee.
Lifecycle and retirement code remain unchanged.

The current0.18.16 server remains ready and online. No model requests or restarts
were performed for this preparation; Grounded2 is still active. The separate,
unexecuted gate0.95 driver now has the same reviewed per-arm GPU predicate and
the PLD parent hash has been refreshed. Root repeated27 gate and33 PLD tests.
The original experiment order remains; actual game exit and fresh quiet-GPU
clearance precede execution. Do not repeat completed natural-text measurements.

Evidence: `server/.local/halogen-update-20261025/primary01816/pld-code-log-aba-20261026/root-prepared-wait-receipt.json`.

Superseding source pins and resolved gate-preflight note:
`server/.local/halogen-update-20261025/primary01816/mtp-gate095-20261026/coupled-gpu-preflight-root-receipt.json`.

Completed result: code means6.2904866/6.3543373/6.3923368s and log means
10.6435671/10.9052714/10.8133404s (control/candidate/control). Neither meets
the numerical threshold. All24 output/request/count/finish checks pass.
Code outputs hit128tokens/length with a truncated explanation; log outputs
finish at115tokens/stop and total345 measured output tokens per arm.
Root manual review withholds full code-completion qualification; log quality
passes. Independent raw reconstruction confirms all summaries and comparison.
PLD3,3 remains in use.
