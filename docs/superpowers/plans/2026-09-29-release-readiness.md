# Strix Alloy release readiness

> Continue approved integrations using subagent-driven development and independent review. This is a release checklist, not permission to replace measured history or disable guards.

**Goal:** qualify the missing release behavior, publish only reviewed supported functionality and comparable evidence, and state the actual relationship between native Strix Alloy, Halogen WSL2, GUFO and CIRU.

**Architecture:** retain independently versioned inference engines and model formats. `strix-alloy` is the proposed common front door; PROJFIX is a native llama.cpp model profile, not a fourth kernel. Existing native and WSL2 entry points remain intact until a reviewed migration is qualified. The current repository already targets `MKM-030/strix-alloy` on `codex/gufo-native-integration`.

## Global constraints

- User authorized missing tests and commit/push on 29 September. Publish a stable release only after its actual gates pass; a source branch or research checkpoint is not a qualified runtime release.
- Preserve working installations and unrelated dirty changes in `C:/Projects/strix-alloy-clean` and `C:/Projects/strix-alloy-wsl2`.
- No XL model download, D: operation, BIOS/VGM/driver/security/service/pagefile change, reboot or unrequested external post.
- Only one inference engine at a time. New Halogen candidate retains 12 GiB Windows physical/commit runtime floors, bounded reviewed admission, exact owned-container shutdown and verified recovery. GUFO profiles retain their own reviewed limits; do not silently transfer the Halogen-only waiver.
- Original Halogen 0.14.2 trace/smoke/replay source seals and completed evidence remain unchanged. Revised lifecycle code goes into a separately sealed release candidate.
- Reuse existing completed benchmarks. New runs must close a specific gap: changed binary/controller qualification, cold PP2048/8192, or genuinely missing backend comparison. Do not rerun the two completed deep replay tables.
- Distinguish engine-reported rates from HTTP rates; actual tokens from configured context; cached prefixes from fresh prefill; upstream claims from local measurements; quantization differences from engine effects.

## Release tasks

- [x] Inventory backend entrypoints, packaging and repository remotes. Evidence: parent `reports/release-backend-inventory-20260929.md`.
- [x] Inventory actual local versus upstream measurements. Evidence: parent `reports/release-measurement-inventory-20260929.md`.
- [x] Check official GUFO release/Windows-port heads. Stable upstream has advanced; Windows fork has not. Evidence: parent `reports/release-gufo-update-audit-20260929.md`.
- [x] Run the complete existing offline suite from the integration worktree with absolute child-process import paths. Final frozen run: 817 tests in 644.605 seconds, OK (3 skips), exit 0; `reports/release-offline-frozen-20260929.log`. Command used `-q` output verbosity; same full discovery, no test exclusions. New candidate bindings outside `tests/gufo` require their own focused tests.
- [x] Repair the Halogen stop/sampler coordination in `experimental/halogen0142_release` with deterministic failing-before-fix offline tests, retained diagnostics and an independent review. Detailed implementation requirements and evidence: parent `reports/halogen0142-release-fix-brief-20260929.md` and `reports/halogen0142-release-fix-20260929.md`.
- [x] Qualify only the reviewed release controller: real 4K serial smoke `halogen-flash-hybrid-0142-smoke-ac8ad25ef630410c845f96abf8fa21de` passed correct answers, quiescence, terminal state, recovery and guard exit on 29 September. Old failed attempts are unchanged; the exact old lock was separately reconciled and archived. This does not qualify larger profiles or a portable installer.
- [ ] Verify latest Halogen/native/CIRU version availability and local model assets. CIRU Flash is not the installed Ornith model. A missing large CIRU checkpoint is a release-scope decision, not permission to substitute another model.
- [ ] Assess GUFO latest stable port feasibility in a separate pinned source checkout. Rebuild and remeasure only a selected reviewed update; no changed binary may inherit old qualification.
- [ ] Fill missing current-build cold PP2048/8192 cells using the existing Halogen filler/calibration, cache bypass, greedy/thinking off, one generated token and three counterbalanced repetitions. Retain both engine and complete HTTP timing. Context capacity must fit the actual token counts plus output.
  - Halogen portion complete: attempt `halogen-flash-hybrid-0142-pp-7f75a8cb47964d989179c228d4283556`, independently audited. HTTP PP2048 1314.83 ± 15.26, PP8192 1310.73 ± 4.93 tok/s. All six engine times exceed HTTP; preserve discrepancy. Cleanup/recovery/guard exit passed. Do not repeat this workload. Native/new-GUFO cells remain open.
- [ ] Resolve supported-backend packaging: common selector must preserve separate runtimes/model formats and refuse unavailable or unqualified profiles. Do not advertise a runnable CIRU/GUFO service just because a comparison row exists.
- [ ] Review staged artifact dependencies, portability, licenses, rollback, secrets/local paths and all explicit file additions. Never use `git add .` for the dirty research tree.
- [ ] Independently review the scoped release diff; commit and push only after tests pass for the stated scope. Verify the remote commit. Do not tag/release an unqualified four-backend package.

## Current blockers and evidence policy

The latest Halogen engine produced correct smoke answers and 16 benchmark responses, but its original repetitive shutdown sampler failed. The repaired release controller has now passed a separate real 4K correctness/stop/recovery test. The timing discrepancy in historical benchmark rows remains unresolved, so those rates are observations rather than validated performance superiority. The GUFO persistent service is explicitly unqualified. CIRU Flash currently has no first-party release entrypoint or local matching checkpoint. Those facts must stay visible in the release notes.

The first complete correctly configured offline run executed 797 tests in 642.237 seconds, with 3 failures, 1 error and 3 skips. Two reproducible HTTP-test clock errors were fixed by explicitly injecting the simulated clock; two non-reproduced release-test timing hazards were removed without changing the frozen controller. Parent independently verified the affected 46 tests passing in 21.459 seconds. A final frozen full run subsequently passed as recorded above; the earlier failed run remains unchanged.

Initial full-suite invocation omitted the documented absolute `PYTHONPATH`, producing import/child-process problems; the exact owned test process was terminated and the corrected invocation started. This setup mistake is not a product pass or a reason to weaken tests.
