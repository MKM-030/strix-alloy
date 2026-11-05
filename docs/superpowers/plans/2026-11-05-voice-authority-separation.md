# Voice Authority Separation Implementation Plan

> **For agentic workers:** Use the existing source implementer and independent reviewer in the existing isolated worktree. Root integrates and activates. Marcel authorizes autonomous execution without questions.

**Goal:** Preserve natural conversation while keeping prior speech and advisory status separate from evidence of business execution.

**Architecture:** Project the existing validated snapshot only at the local model wire boundary, and corroborate recognized current-action claims against the actual current typed backend event. Keep application observation and dispatch contracts intact.

**Tech Stack:** Existing Python, asyncio, local SSE controller, Pipecat and unittest; no new dependencies or inference.

**Spec:** `docs/superpowers/specs/2026-11-05-voice-authority-separation.md`

## Global Constraints

- Only local inference; ServiceNow remains business executor.
- Preserve configured system prompt, raw inputs, complete history text and all existing freshness/claim/control guards.
- No extra model request or automatic retry.
- Physical-device and complete-workflow acceptance require actual evidence.

## Review Focus

- Own completed speech must remain available without acquiring business authority.
- Processing observations must not corroborate actions.
- Matching text from an old request or changed owner must not corroborate a current claim.
- Questions, quotations, negation, conditional explanations and real current native outputs remain usable.
- Invalid wire context must fail before inference; no silent permissive fallback.

## Task 1: Wire authority projection and recorded claim regression

Files: `voice/native-bridge/local_llm_socket.py`, `conversation_claims.py`, `native_duplex.py`, new `test_native_authority_projection.py`, and existing local socket test fixtures as necessary.

- [ ] Preserve RED reproduction of actual prior spoken text appearing as model-facing business findings and the actual V7 claim passing release.
- [ ] Implement a pure bounded wire-message projection, preserving seed, constraints, texts and provenance while separating native findings, history and advisory observations.
- [ ] Add the bounded current-action claim predicate and exact current typed OutputText/request/owner corroboration.
- [ ] Verify recorded positive/negative cases, real socket request body, prompt/raw preservation, hard freshness/control precedence and soft streaming continuation.
- [ ] Run focused regressions and existing socket/duplex/output/history suites; freeze source pins for independent review.

## Task 2: Integrate and verify actual behavior

- [ ] Independently review only the frozen source, commit named files and promote to clean canonical.
- [ ] Perform one fresh exact-owned idle Native-only activation; preserve Bot, Controller, backend, ASR, TTS and settings.
- [ ] Use a fresh bounded test with immutable caller facts and Root-steered fixture selection, so ordinary question paraphrases do not terminate a test.
- [ ] Inspect native transcript, actual model speech, full host audio, timing, cleanup and current role diagnostics. Do not convert a safe test stop into a workflow pass.

