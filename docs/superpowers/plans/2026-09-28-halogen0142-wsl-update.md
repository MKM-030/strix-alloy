# Halogen 0.14.2 WSL2 update implementation plan

> **For agentic workers:** Use superpowers:subagent-driven-development for independent components and review. Continue this approved update without a new design-approval loop.

**Goal:** Combine the pinned Halogen 0.14.2 engine/API with our existing WSL2 mapping and memory-accounting patches, qualify it, and replay the preserved benchmark inputs.

**Architecture:** An isolated candidate under `integration/experimental/halogen0142` consumes the unchanged public 0.13.8 patch sources. Version-specific bindings and a narrowly scoped entrypoint adaptation are generated reproducibly. The old deployment and benchmark evidence remain intact.

**Tech stack:** C/x86-64 assembly, Python, PowerShell, WSL2/Docker.

## Global constraints

- Preserve `C:\Projects\strix-alloy-wsl2`, its 0.13.8 image and all unrelated dirty files.
- Candidate image is `ghcr.io/peonist-ai/halogen-flash-server@sha256:f3f99aa48f3a051f18da9ee24b333ca108fe745773fd036a365fe1875871d0be`.
- New engine SHA256 is `e8f74704f8148d9512cd33cc6abb46de21daac5385cb686285fc5ecbbf9cf70d`.
- No model download, especially no XL weights. Reuse read-only existing HGN and later IQ4_XS.
- No persistent system changes, reboot, publication, push or D: operations. No commits during this update.
- One model only; exact owned-container termination; finite deadline; fresh Windows/guest telemetry; cleanup and memory recovery before another run.
- Private runtime floors remain 12 GiB physical and 12 GiB commit; initial candidate admission at least 24 GiB physical/98 GiB commit. These are stops, not reservations. Review the new build's allocation delta before model execution.
- Never fix compatibility by falsifying total/free memory, bypassing the engine floor, accepting unknown registration ranges, or merely replacing a binary hash.
- Do not claim performance or WSL compatibility until correct live inference and cleanup are observed.

## Task 1: Version-bound binary bridge

Files: `experimental/halogen0142/` binding/generator and tests; detailed audit in `research/reports/halogen0142-binary-audit-20260928.md` (research root is parent of integration).

- [x] Inspect extracted engine at `C:\Projects\strix-alloy-research\artifacts\halogen0142\flash_serve`; locate corresponding preflight control flow and prove the frame/register/range/floor ABI against the old bridge.
- [x] Record disassembly addresses, exact signature, surrounding arithmetic/branches and HIP call sequence. Examine route-GEMM control and changes affecting memory.
- [x] Before implementation, add a failing version-binding test: old source rejects the new image; candidate generation must require exact original hashes and new ELF identity, site bytes and ABI evidence.
- [x] Generate candidate-only sources from unchanged public patches using exact checked substitutions. Preserve planner shape/caps and fail-closed controls. Reuse assembly only if proved equivalent.
- [x] Run candidate CPU fixtures for ABI, SHA/signature mismatch, floor, vector/order/placement, real HIP error propagation and cleanup. Build and seal candidate sources/binaries.
- [x] Independent review of the binding and evidence before a GPU run.

## Task 2: Narrow WSL2 entrypoint adaptation

Files: `experimental/halogen0142/entrypoint_adapter.py`, `tests/gufo/test_halogen0142_entrypoint.py`, candidate generated entrypoint under research artifacts.

- [x] Add failing tests for native KFD behavior preserved, verified WSL accepted, absent/wrong device or GPU rejected, changed upstream input rejected, download prohibited.
- [x] Implement an exact-hash transformer that replaces only `host_preflight()` in the extracted image entrypoint. Preserve upstream function as the native fallback. WSL branch requires explicit candidate profile, real accessible character `/dev/dxg`, no KFD, gfx1151 from a live HIP probe, exact DXG library hash, and no download setting. Production paths are fixed; fixture input injection exists only in tests.
- [x] Compile/run a bounded HIP device query in the candidate process environment without model allocations, or consume a fresh verified probe from the guarded controller; never trust `HALOGEN_ARCH` alone as GPU evidence.
- [x] Leave engine/API, checkpoint checks, pool sizing, GTT checks and other upstream code unchanged. Use same-image API, no old API mount.
- [x] Run focused offline fixtures and independent review.

## Task 3: Qualification and comparison

Files: candidate launch profile and bounded run integration, report `docs/benchmarks/halogen0142-wsl-20260928.md`.

- [x] Reuse reviewed telemetry/owned-cleanup primitives; separately seal candidate identities and new attempts, never mutate prior seals or consumed attempts.
- [x] Review 48 GiB copy/host placement, small 4096 context/pool and 2048 prefill arena budget. Trace first, terminating before registrations. Full-model qualification only once static and trace evidence agree.
- [x] Run bounded correctness requests, verify new engine/API versions, shutdown and recovery. Then replay exact preserved mixed/repetitive inputs, keeping chunk 2048 initially and explicitly recording routed-kernel/MTP settings. Execution is complete; benchmark controller outcomes remain failed for the recorded reasons, not clean qualification passes.
- [x] Record actual counters, memory, wall and engine times. Keep count-alignment and timing inconsistencies visible. Do not repeat old baseline runs or infer parity.
- [ ] After Halogen measurements, resume GUFO optimizations using existing IQ4_XS; no XL download.

## Progress

- Source tag and image acquired; previous deployment unchanged.
- Compatibility audit complete: new host preflight rejects WSL; binary bridge must be requalified.
- Extracted engine and entrypoint without starting container; models exist on current WSL ext4 root filesystem (directory is not a separate mounted filesystem).
- Closeout 29 September local time: corrected trace and 4K serial correctness passed. Both eight-request benchmark replays completed and independent audits are complete. See `docs/benchmarks/halogen0142-wsl-20260928.md` for all four old/new cells and limitations. Neither benchmark is a clean overall pass: count tolerance, timing discrepancy, mixed admission/recovery discrepancy and repetitive shutdown-sampler failure remain preserved.
- No candidate model/controller remains running. Keep the exact zero-byte candidate runner lock until reviewed controller repair and explicit lock reconciliation; do not rerun completed workloads or promote the candidate to default. GUFO tuning with existing IQ4_XS remains the next broader-goal phase; no XL download.
