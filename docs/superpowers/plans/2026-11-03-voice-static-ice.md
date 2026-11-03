# Optional Voice static ICE implementation plan

> **For agentic workers:** Implement inline with the executing-plans and TDD workflows. Root performs independent review before any integration or activation.

**Goal:** Add an explicit validated URL option that skips metadata discovery while retaining legacy behavior by default.

**Architecture:** Only managed TURN configuration and its bootstrap gain an optional immutable selection. Both modes continue through existing fresh caller and transport ownership code.

**Tech Stack:** Existing Python 3.12 venv, dataclasses, aiohttp and unittest; no dependencies added.

## Global constraints

- Isolated worktree at e8c2688; managed TURN behavior change plus two required startup hash literals in `start_current_voice.py` and `qwen_asr_start.py`.
- No active configuration, token, network, model, audio, session, metadata or service operation.
- Static selection is optional `None`; explicit tuple/list is one to four unique ordered allowlisted exact TURNS/TCP443 URLs.
- No token cache, detached cleanup, automatic mode fallback or region-equivalence claim.

### Task 1: Configuration and bootstrap

Files: modify `voice/native-bridge/managed_turn.py`; create `voice/native-bridge/test_managed_turn_static.py`.

- [x] Add failing tests: omitted field retains discovery and awaited deletion; static returns URL rows with zero HTTP; mutations cannot affect later calls; invalid tuple/list/URL/disabled combinations fail closed; invalid caller syntax never opens HTTP.
- [x] Run the new tests against the unmodified implementation and record the expected missing-option failures.
- [x] Add `static_ice_urls: tuple | None`, exact URL validation shared with discovery parsing, loader optional-key handling, and the static return after existing caller checks.
- [x] Run new tests and existing managed TURN/configuration tests using the canonical existing venv.

### Task 2: Contract checks and report

Files: update this plan and the design document with actual verification; create `docs/servicenow-byollm/voice-static-ice-source-20261103.md`.

- [x] Run SDK-session, WSS/caller entry and host-ICE tests relevant to unchanged admission/capacity/identity cleanup.
- [x] Inspect the complete diff, source hashes and canonical status; report any baseline failures separately.
- [x] Commit only this worktree's source/tests/docs, leaving canonical e8c2688 and active configuration unchanged.

### Task 3: Required normal-startup pin chain

- [x] Inspect the full graph and prove no Qwen-launcher self-reference in the ASR manifest.
- [x] Prepare exact private candidate config, starter, one-role ASR manifest and Qwen-launcher postimages in a new v2 activation directory, preserving the v1 HOLD preparation.
- [x] Observe both new pin tests failing against the original literals, then make the two exact literal replacements only in this worktree.
- [x] Exercise freshly loaded actual normal-start and Qwen modules against planned postimages. Reuse one captured real unchanged-worker readiness metadata response; use retained full-hash/stat proof instead of rehashing large weights. Require old/drifted config, manifest and ASR-state rejection without startup.
- [x] Run the seven new cascade tests and the existing 21 starter tests; preserve canonical services and source.
- [x] Commit the additive source/docs change after cfb0785; actual activation remains separately gated on a qualified baseline and independent v2 review.
