# GUFO isolated no-snapshot 2x260k experiment

> **For agentic workers:** Use superpowers:subagent-driven-development for the focused patch and independent review. Continue execution without repeating approved design decisions.

**Goal:** Measure two genuinely occupied approximately 260000-token sessions in native GUFO without retained RAM prompt snapshots.

**Architecture:** An isolated experimental build of the pinned Windows port disables Flash-Next serving snapshots through its existing runner capability contract. Reuse owned-process monitoring, native counters and existing request handling; preserve all historical binaries and evidence.

**Tech Stack:** C++20/HIP gfx1151, TheRock 10.2, CMake/Ninja, Python 3.12 Windows controller.

## Global Constraints

- Do not change existing working GUFO or Halogen installations, weights, or pinned source checkouts.
- User waived the 49/50 GiB startup threshold for this experiment. Runtime stop floors remain 24 GiB physical available and 12 GiB commit headroom.
- Fresh scoped telemetry; fail closed when missing/stale; terminate only owned test processes; verify recovery before another run.
- No BIOS, drivers, services, security, pagefile, D: operations, reboot, push or publication.
- Preserve numerical kernels, MTP behavior, multilingual tokenization and unrelated changes.
- Two 262144-capacity sessions must receive actual approximately 260000-token prompts; short prompts in large slots do not satisfy the task.

### Task 1: Isolated Flash-Next snapshot disable

**Files:** `C:/Projects/strix-alloy-research/engine/gufo-no-snapshot-260k/src/cli/serve/inference_backend.cpp`.

**Interfaces:** Existing `QwenFlashNextTextRunner::Descriptor()` and `ResourceClaim()`; no new public flag. This dedicated experimental build has caching disabled for this runner only.

- [ ] Inspect capability validation, capture and commit paths; use smallest existing CPU checks covering no-snapshot runners.
- [ ] Change this runner's `.snapshot`, `.fork`, `.prefix_reuse` to `false`; omit persistence advertisement; set retained snapshot capacity to zero. Retain inference code unchanged. If source contract requires a different minimal implementation, report the concrete conflict.
- [ ] Verify all prompt snapshot entry paths are gated and no disabled capability causes normal inference rejection. Run scoped existing CPU checks; no model launch by the implementer.
- [ ] Format changed C++ using available matching clang-format and commit only owned changes. Preserve base `cff564964e8506c0abb3e530cecb55332187ac6c`.
- [ ] Report source commit, actual test evidence and capture-path reasoning to `C:/Projects/strix-alloy-research/reports/no-snapshot-260k-task1-report.md` for independent review.

### Task 2: Build and finite workload adaptation

- [ ] Independently review Task 1 before GPU execution. Build isolated binary with the proven HIP `-O2 -DNDEBUG -g0`, at most two jobs; reuse installed dependencies and process-local environment.
- [ ] Reuse existing finite guardian and native collector for the new source/binary. Bind two actual bodies with finite enlarged body/time limits and actual native prompt counts. No old consumed adapter or certificate replay.
- [ ] Archive build identity, exact request settings and revised memory accounting; independently review runtime scope. Do not restore waived startup veto.

### Task 3: Execute and report

- [ ] Bounded small no-snapshot correctness request; verify shutdown/recovery.
- [ ] One real cold C2 wave near 260000 tokens each with output cap fitting 262144, finite long deadlines and live 24/12 floors.
- [ ] Preserve native counts/timers, raw responses, batching evidence, memory and cleanup. No chunk-as-token counting or estimated throughput.
- [ ] Report measured results or precise failure honestly; update checkpoint and concise benchmark documentation. No publication.
