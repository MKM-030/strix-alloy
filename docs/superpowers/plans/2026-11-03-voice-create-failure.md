# Voice CREATE failure implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans task by task, following the recorded owner split.

**Goal:** Preserve typed CREATE failures and safely settle proved no-creation while giving consistent auth feedback.
**Architecture:** Versioned own-resource negative receipt -> transport typed failure -> exact Bot owner receipt -> bound Native terminal handling. UNKNOWN never becomes absence.
**Tech Stack:** Existing Python asyncio/aiohttp and ServiceNow ES5; no dependencies.
**Spec:** docs/superpowers/specs/2026-11-03-voice-create-failure-design.md

## Global constraints

- One CREATE; no automatic auth, model or business replay.
- Platform401 and ambiguous transport/closure remain UNKNOWN.
- Preserve successful CREATE/refresh/START/END and own TTS/ASR.
- Do not retrofit receipts into the current running failed task.
- Source work isolated at .worktrees/voice-create-failure; no live promotion without reviewed finite maintenance.

## Review focus

- Source or caller drift must invalidate a negative receipt.
- Lost loopback initial error cannot produce unbound terminal release.
- Concurrent close or callback cannot bypass task completion/binding checks.
- Error bodies/credentials cannot become logs, spoken content or model context.
- Existing true-END tombstones and unknown retention remain compatible.

### Task1: Transport and native resource receipt (agent caller_create_contract_review)

Files: voice/caller_binding.py; servicenow/byollm/voice-auth/Local-caller-create-resource.js; focused tests.

Produces: CALLER_CREATE_FAILURE_CONTRACT, CallerCreateFailure, frozen CallerCreateFailureReceipt with spec fields. Explicit correlated403 envelope only before native handler construction.

- [x] Write and observe failing behavior tests.
- [x] Implement bounded strict transport/negative envelope.
- [x] Verify normal/error context-close cases and existing endpoint suite.

### Task2: Bot owner settlement and Native feedback (Root)

Files: voice/bridge.py; voice/native-bridge/native_bridge.py; startup_reason.py; native_duplex.py; focused tests.

Consumes: Task1 exception.receipt. Produces: exact private initial error and localTerminal payloads defined in spec.

- [x] Write and observe failing tests for typed401, proved no-create, foreign receipt and retained UNKNOWN.
- [x] Bind immutable receipt to exact owner/task and settle only under lock with no binding.
- [x] Preserve tombstone payload/CSRF/expiry and distinguish no-create from remote end.
- [x] Validate bounded loopback startup failure, nonce, typed reason and fixed spoken auth notice.
- [x] Run Voice and native suites; report all failures/skips.

### Task3: Review and integration

- [x] Fresh independent whole-change review; address actionable findings with red/green tests.
- [x] Run source/syntax/tests against final bytes; commit and integrate locally only after GO.
- [ ] Document current401 remains UNKNOWN and runtime activation/reconciliation prerequisites.
