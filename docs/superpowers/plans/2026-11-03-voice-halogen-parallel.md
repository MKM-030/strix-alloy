# Voice Halogen Parallel Capacity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox syntax for tracking.

**Goal:** Reuse and integrate bounded managed Halogen capacity so a distinct short-Voice/long-AIA overlap can be qualified safely.

**Architecture:** Default serving remains unchanged. Explicit0.18.22 v2 text32k capacity selectors flow through generator, controller, launcher and backend, with exact health and memory checks. A later finite qualification determines whether any normal profile change is useful.

**Tech Stack:** Python, PowerShell5.1, existing Halogen0.18.22 API/engine and unit tests.

**Spec:** `docs/superpowers/specs/2026-11-03-voice-halogen-parallel-design.md`.

## Global Constraints

Slots integer1/2; explicit pool integer32768/65536; opt-in only0.18.22/v2/text-only/context32768. CacheOff and all existing model/binary/token pins preserved. Default selectors unchanged. Preserve `FollowupText32K`. Startup floors at least30/131GiB; runtime18/18; request-entry22/22. No live action by implementers. Root alone prepares/executes any new finite window after review, with exact normal restoration and no Voice calls in flight.

## Review Focus

Boolean/string selectors and implicit mismatched health must fail before launch. Historical backends and non-Halogen profiles must not acquire capacity options. Default/FollowupText32K PowerShell output must remain equivalent. All manifest/source members must include the new module without deleting old members. Partial qualification must restore the actual original profile and preserve speech owners without replaying old experiments.

### Task1: Backend capacity policy and propagation

**Files:** `backends/halogen-wsl2-0.18.22/Start.ps1`, `profiles/release.json`, `profiles/sources.json`, `scripts/capacity_policy.py`, `scripts/memory_budget.py`, `scripts/service.py`; tracked backend capacity tests/fixtures.

**Interfaces:** Produce retained `capacity_policy.resolve` and `validate_manifest`; service `capacity_options`, `explicit_capacity`, `resolve_capacity`; keyword slots/pool arguments to environment/floors/health/manifests. Exact retained candidate interface is the source of truth; keep all existing calls backwards compatible.

- [ ] Run relevant existing memory/vision/service tests as baseline; write failing portable tests for slots2/pool65536 propagation, malformed selectors, manifest/health mismatch and unchanged default outputs.
- [ ] Port only the six backend capacity files from the retained candidate, after verifying each original preimage. Preserve all unrelated source and pins.
- [ ] Run new tests plus relevant existing backend regressions, without WSL/model/endpoint effects. Record RED/GREEN and changed-file hashes. Do not commit shared worktree before Root coordinates.

### Task2: Generator, controller and PowerShell compatibility

**Files:** `server/manage.py`, `server/controller.py`, `scripts/Start-Halogen-ServiceNow.ps1`, `server/tests/test_halogen01822_capacity_portable.py`, tracked capacity fixtures, `tests/gufo/test_halogen01822_capacity_launcher_portable.py`.

**Interfaces:** Consume Task1 policy; expose retained generator slots/pool/concurrency keyword options, controller validation/argument forwarding, and PowerShell explicit selectors. Match the retained candidate contract; Python launcher receives `--slots` and `--kv-pool-positions` only for explicit capacity.

- [ ] Run current forwarding/launcher tests as baseline. Adapt retained private tests to tracked portable fixtures and demonstrate failure on the existing default source.
- [ ] Port controller/manage deltas. Merge launcher capacity changes into the current source, preserving every FollowupText32K path; do not copy the older full launcher.
- [ ] Verify default profiles, CurrentText32K and FollowupText32K, both launcher types, invalid combinations and PS5.1 PrintOnly. Run existing related regressions and record evidence. No credentials, live starts or runtime files.

### Task3: Review, integration and distinct qualification

**Files:** Existing private finite-coordinator/collector patterns under `server/.local/halogen-update-20261101/primary01822`; new private Voice-overlap protocol/collector/owner plan; public summary only after actual measurements.

- [ ] Root reviews both diffs and requests an independent whole-feature review, then runs integrated source/launcher checks and verifies all source manifests. Commit the opt-in feature in the isolated branch.
- [ ] Prepare a distinct bounded Voice192-output plus read-only AIA-like8K/16K overlap protocol, including exact reservation/dispatch count, per-request response/latency criteria, memory and cancellation, owner/source pins and guaranteed normal-profile restoration. Use completed concurrency2/cache evidence as prior evidence, without repeating their raw cohorts.
- [ ] Review and test the new finite helper/collector with injected effects. Then Root independently admits one real window only when actual owners, memory, Native idle and restoration guards pass. Preserve speech services and existing own voice.
- [ ] Independently read back actual outcomes and restored normal owners; decide profile adoption only from this workload's evidence. Update Voice continuation/report and capabilities documentation truthfully, with physical-device and worker-identity limits retained.
