# Halogen 0.20.6 Update Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate the exact Halogen 0.20.6 image through the WSL bridge, promote it as the managed ServiceNow backend, verify it, and push the repository update.

**Architecture:** Add an independently pinned `halogen-wsl2-0.20.6` package based on the established fail-closed adapter design. Rebind the engine seam, entrypoint and API transforms from passively extracted 0.20.6 artifacts, then promote the version through the managed server and launcher only after offline tests and installation checks pass.

**Tech Stack:** Windows PowerShell 5.1, Python 3.12/3.13, C/x86-64 ELF analysis, WSL2/DXG, Docker in Ubuntu-24.04, unittest/pytest, Git/GitHub.

**Spec:** `docs/superpowers/specs/2026-11-18-halogen-0206-update-design.md`

## Global Constraints

- Use immutable OCI manifest `sha256:f68892a56d8a1182645042574d702374bff402bb986ec4d49304cbe89483dbaf` and config `sha256:3f5f2337842b8003f9826e226adcd4ad4a620dd3ed2e3f780dfb9f00dae4dfa6`.
- Preserve default `CurrentText32K` startup 30/124 GiB, capacity-opt-in startup 30/131 GiB, request-entry 22/22 GiB, and runtime 18/18 GiB floors.
- Preserve port 8840, alias `halogen-v2`, stable token file, text-only 32K/8192 profile, PLD `3,3`, gate `0.90`, and cache/thinking/vision/prefetch off.
- Do not terminate foreign processes or overwrite historical packages and evidence.
- Unknown engine, entrypoint, API, provider or ABI inputs must fail closed.

## Review Focus

- A same-version tag pointing to different bytes must be rejected by immutable digest and file hashes.
- A changed bridge instruction sequence or live-register/frame contract must fail before a runtime start.
- API cache-stat layout changes must either be explicitly adapted or rejected without silently deleting the wrong field.
- The PowerShell launcher must keep historical versions usable while selecting 0.20.6 for current profiles.
- A failed or inadmissible live start must preserve exact evidence, clean only owned resources, and never disturb the foreign model.

---

### Task 1: Capture exact 0.20.6 inputs

**Files:**
- Create locally retained evidence under `server/.local/halogen-update-20261118/primary0206/`
- Create: `docs/research/halogen0206-update-20261118.md`
- Create: `docs/research/halogen0206-update-20261118.json`

**Interfaces:**
- Consumes: official tag/OCI identities from the design.
- Produces: exact engine, entrypoint, API, provider, and header pins consumed by Task 2.

- [ ] Write/update passive extraction tests that reject a mutable tag, wrong raw manifest/config, started extraction container, missing API files, or changed preservation evidence.
- [ ] Run the tests and verify they fail against an unconfigured 0.20.6 preparation.
- [ ] Pull the immutable image with the owned WSL Docker client while monitoring the 18 GiB floor; create a never-started, networkless, read-only extraction container.
- [ ] Copy and hash `flash_serve`, upstream entrypoint, API tools, HIP headers and runtime providers; remove only the owned never-started container.
- [ ] Verify tag, manifest/config, labels, platform and every extracted file independently; record the results in the dated report.

### Task 2: Rebind the bridge and frontend adapters

**Files:**
- Create: `backends/halogen-wsl2-0.20.6/**`
- Test: `backends/halogen-wsl2-0.20.6/tests/test_release_contract.py`
- Test: `backends/halogen-wsl2-0.20.6/tests/test_halogen_preflight_bridge.py`
- Test: `backends/halogen-wsl2-0.20.6/tests/test_entrypoint_adapter.py`
- Test: `backends/halogen-wsl2-0.20.6/tests/test_auth_api.py`

**Interfaces:**
- Consumes: Task 1 exact artifacts and pins.
- Produces: versioned source package and locally built bridge/API/entrypoint products with verified hashes.

- [ ] Add tests first for altered engine/hash/signature/function bounds, changed frame/register contract, entrypoint clock substitutions, API cache-stat layouts, complete source inventory, and absence of experimental hooks.
- [ ] Run the new tests and verify they fail because the 0.20.6 package/pins do not exist.
- [ ] Passively disassemble the 0.20.6 engine; locate the semantic demand seam, prove the overwritten instruction span/direct-transfer exclusions, and record the fresh frame/live-register contract.
- [ ] Adapt the bridge source and trampoline only if the proven ABI requires it; update exact binary and function hashes/RVAs.
- [ ] Rebase the entrypoint adapter on the 100,721-byte 0.20.6 script and preserve only reviewed WSL/watchdog changes.
- [ ] Compare the real 0.20.6 API cache protocol and retain, change, or remove normalization based on producer/parser evidence; preserve authentication and redaction.
- [ ] Build CPU products against the exact 0.20.6 headers/providers, pin all artifacts, generate `release.json` and `sources.json`, and run the package suite to green.

### Task 3: Promote 0.20.6 through managed serving

**Files:**
- Modify: `server/manage.py`
- Modify: `server/controller.py`
- Modify: `scripts/Start-Halogen-ServiceNow.ps1`
- Create: `server/tests/test_halogen0206_forwarding.py`
- Create: `server/tests/fixtures/halogen0206-capacity-text32k-profile.json`
- Modify: relevant launcher portability tests under `tests/gufo/`
- Modify: root `README.md`

**Interfaces:**
- Consumes: Task 2 package path and release contract.
- Produces: default current profile resolving to installed Halogen 0.20.6.

- [ ] Write forwarding and launcher tests first for default 0.20.6 selection, 2048/8192 paired prefill, one/two-slot validation, cache variants, API controls, stable credentials and historical explicit versions.
- [ ] Run the focused tests and verify they fail on the current 0.20.3 default/allowlists.
- [ ] Add 0.20.6 to every managed capability/forwarding allowlist and make current profiles select it without changing historical presets.
- [ ] Update help text and root documentation with the new default and upstream-vs-local qualification distinction.
- [ ] Run focused backend/server/launcher tests and the full practical project suite; record any unrelated pre-existing failures.

### Task 4: Install and verify the managed runtime

**Files:**
- Update local installed state under `backends/halogen-wsl2-0.20.6/.local/`
- Update local runtime receipts under `server/.local/halogen-update-20261118/primary0206/`
- Finalize: `docs/research/halogen0206-update-20261118.{md,json}`

**Interfaces:**
- Consumes: Task 2 build artifacts and Task 3 managed profile.
- Produces: verified final runtime identity and evidence.

- [ ] Install with full source/artifact/provider hash verification and generate the current 32K/8192 profile without printing credentials.
- [ ] Recheck exact owned/foreign processes, ports, GPU interference and the selected admission floor before start: 30/124 GiB for default one-slot `CurrentText32K`, or 30/131 GiB with capacity opt-in.
- [ ] Start only the managed 0.20.6 instance; observe the same confirmed lifecycle handle until ready or authoritative terminal state.
- [ ] Verify engine/API version agreement, authenticated `/v1/models`, expected health/capacity controls, one bounded deterministic request, console trace and 18/18 GiB runtime reserve.
- [ ] Leave a qualifying instance ready on port 8840; if coexistence cannot satisfy the preserved reserve, retain the installed update and record the exact foreign-resource blocker without terminating it.

### Task 5: Review, commit and push

**Files:**
- Review all tracked files changed by Tasks 1-4.

**Interfaces:**
- Consumes: green test/build/runtime evidence.
- Produces: reviewed commit on `main` and matching `origin/main`.

- [ ] Run fresh final verification: source manifests, focused/full tests, PowerShell `-PrintOnly`, installed hashes, health/request or terminal blocker evidence, and `git diff --check`.
- [ ] Request an independent whole-change review and fix all Critical/Important findings with test-first proof.
- [ ] Confirm no secrets, `.local` runtime payloads, model files, logs, or unrelated user changes are staged.
- [ ] Commit the intended update and push explicitly to `origin main`.
- [ ] Verify local HEAD equals `refs/heads/main` on the remote and report the exact live/offline state without overstating performance.
