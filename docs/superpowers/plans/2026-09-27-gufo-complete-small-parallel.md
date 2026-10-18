# Complete answers and small parallel GUFO execution

> **For agentic workers:** use subagent-driven implementation/review. User approved immediate execution; do not ask again or expand unit-test scaffolding.

**Goal:** Measure useful complete native GUFO answers, then qualify two small simultaneous requests while Windows remains usable.

**Architecture:** Reuse the pinned binary, weights, native telemetry, bounded HTTP transport and owned-process Guardian. New one-use workloads retain historical evidence under separate identities. No public launcher/profile change.

**Tech Stack:** Existing Python standard-library control and native Windows HIP GUFO.

## Global constraints

- At least 49 GiB available Windows physical memory before launch.
- A 24 GiB available Windows physical-memory stop floor during testing.
- At least 12 GiB system commit headroom; existing d3 envelope needs 89 GiB before launch.
- No concurrent inference model during qualification; no BIOS, carve, driver, service, security, pagefile, D: or reboot changes.
- No publication or push. Preserve unrelated work and historical attempts. Missing/stale telemetry fails closed; only owned test process tree may be terminated.
- No 2x260k or three-full-context attempt. No fake common-window counters or streamed-chunk token counts.
- Do not grow a unit-test suite. Use source review, model-free import/artifact checks and actual bounded measurements.

## Task 1: fixed complete-answer recipe

- [x] Create `scripts/gufo_control/complete_answer_recipe.py` only, following the separate task brief.
- [x] Seven requests: original arithmetic warmup64; original Halogen code_a, proof_a, proc_b, prose_b plus existing DE fixture and exact arithmetic JSON fixture, each max1024. Greedy, thinking off, cache bypass, context4096. Fixed bodies; manual semantic review after completion.
- [x] Independently review extension of historical d3 envelope to these longer outputs before launching. No graph/snapshot capacity growth is assumed without source review.

## Task 2: one-use execution and audit

- [x] Create `scripts/gufo_control/complete_answer_run.py`, using the same lifecycle/policy/helper pins as the completed Halogen MTP run, with unique approval/evidence identity and explicit new workload binding.
- [x] Authenticate last successful Halogen-corpus result and current-boot PP anchor; preserve all previous failures. Update cross-block roots only additively.
- [x] Set request output default1024 explicitly and keep context4096/draft3/full vocabulary/length policy. After independent source review, record exact module/helper/recipe/argv/review hashes and run once.
- [x] Verify all native counts, final answers, process exit and memory recovery; retain failures and incomplete answers honestly.

## Task 3: two smaller sessions

- [x] Independently audit C2 context4096/source allocation, including shared weights, per-session state, MTP, scratch, snapshots and allocator/driver uncertainty.
- [x] After C1 inference and cleanup evidence passes the relevant gates, prepare one bounded pair using existing transport and the reviewed C2 envelope. Require evidence of actual overlapping resident/execution states; simultaneous clients alone are not proof of batching.
- [x] Report native per-request counts/rates and complete group wall-time throughput. Common-window decode remains unavailable without separately audited native boundary counters. Do not invent instrumentation or expand to long-context tests.
- [x] Preserve raw evidence and write concise results/limitations; no public changes.

## Execution disposition, 27 September 2026

Superseded for current C2 status by the successful 28 September checkpoint below; historical refusals remain unchanged.

C1 actually completed seven requests with owned exit 0 and confirmed memory recovery. Code/proof are complete and correct by inspection, German/arithmetic fixtures pass, RAID remains truncated and contains a contradictory warning. See `docs/benchmarks/gufo-complete-small-parallel-20260927.md` and the independent C1 audit.

C2 is NOT measured. First admission stopped before process creation on a 512-KiB monotonic GPU-accounting step. One separately reviewed, unchanged-guard admission2 then failed baseline physical/commit stability. No model was created and no generation POST was made in either admission. Admission2 also retains `cleanup_confirmed=false` and an incomplete latch because its absent current baseline forces comparison against the older original host-memory baseline. All 69 queries terminated; no GUFO/probe process or port 8836 listener remained at 19:53:05 UTC. Preserve the latch, result and history; no third attempt. The remaining unchecked throughput item is genuinely unfinished.

## Renewed user instruction: correct no-model admission and measure C2

The user subsequently explicitly requested the measurement again. This is a reviewed correction, not replay of either consumed adapter. Preserve both original results/latches/markers. The new exact no-owned-allocation certificate classifies admission2's historical no-child outcome without claiming recovery and is recognized only by the new private adapter.

The selected active-desktop policy uses a fixed eleven-frame, >=10-second, <=30-second window. It permits up to 1 GiB physical and 2 GiB host-commit variation while reserving an additional 1/2 GiB at admission: every frame and final create/resume check now needs 50 GiB physical and 91 GiB commit headroom. GPU variation stays 256 MiB. Model envelope 73/4/20, original/current strict runtime comparisons, 24/12 runtime floors, process ownership, deadlines and post-model recovery remain unchanged. Only this reviewed subclass omits the zero-amplitude prelaunch trend veto; default launchers remain unchanged.

- [x] Diagnose both saved refusals, separately review disposition and fixed-window admission arithmetic.
- [x] Implement narrow default-preserving Guardian hooks, private policy and exact historical certificate/adapter.
- [x] Reproduce old baseline refusal with saved telemetry; verify new bounded variation and rejection of over-cap inputs. Existing offline Guardian regression: 43/43 passed, no new test framework.
- [x] Complete exact independent launch review, bind approval and invoke the unchanged three-request C2 workload once. The attempt refused before model creation; the requests did not run.
- [x] Audit the saved refusal and update the report. No native batching, answers or rates exist for this attempt; the C2 measurement item above remains incomplete.

At 20:37 UTC, the first frame reported 49.786701 GiB available, 218.417969 MiB below the reviewed 50 GiB requirement. Commit headroom was 207.299442 GiB. The run recorded no owned child, resume or HTTP work and all 59 telemetry queries terminated. Historical-baseline recovery remained unconfirmed, so its new latch is preserved. Evidence: `small-c2-active-desktop-20260927-v1-runs/20260927T203739Z-df3bb0bc60474298a15928a86e934e54`, result SHA256 `36D2835AEB1190E46574AE0BF4115FD67A935384B5BEF444BF9C1A17C72BB252`. Do not create another automatic retry adapter or lower the reserve merely to fit this desktop state. No GUFO capacity comparison follows from a pre-create refusal.

## Explicit user-requested reduction and successful C2, 28 September

The user requested a reduced start requirement and actual numbers. Independent numerical/source reviews approved 50->49 GiB physical admission, retaining the 1 GiB desktop reserve and all other bounds: 49-4-20-1=24 GiB. The new private adapter authenticates the latest exact no-child refusal in its immutable manifest without erasing latches or claiming historical recovery. Existing Guardian regressions: 43/43 passed; saved-frame and boundary checks prove the intended change and unchanged argv.

The guarded attempt actually completed warmup plus both requests. Result SHA256 `E74A933449429E7D4F580464A923820BB8CC7F8BA6FA5EC9BDC4ABED31F420CE`, run `small-c2-49-20260928-v1-runs/20260928T065810Z-385d45173c3e417c9143b8153a9e6ed8`. Code/proof: 376/703 tokens, 32.6013/39.0841 native decode tok/s, both stop naturally, same answers as C1. Both native execution widths2/batched-w2 and HTTP overlap confirmed. Group 1079/18.656=57.8366 tok/s vs sequential49.5022 (+16.84%); not common-window decode. Minimum free physical42.726 GiB, adapter committed peak67.895 GiB. Exit0, 66/66 telemetry queries, cleanup/recovery true. See `docs/benchmarks/gufo-parallel-20260928.md` and independent saved-evidence audit. No large-context expansion, persistent setting change or public write.
