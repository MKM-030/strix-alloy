# Voice Response Retirement Implementation Plan

> **For agentic workers:** Use the assigned implementers in the existing isolated worktree; Root integrates and activates after independent review. User explicitly requests autonomous execution without questions.

**Goal:** Retain a valid quick reply across the dispatch-only retirement of an answered input and suppress the observed technical advisory in speech.

**Architecture:** Keep business state authoritative. Add a narrowly owned fingerprint equivalence in NativeDuplex and a generic-advisory projection at the Bridge boundary. Keep these changes independently testable.

**Tech Stack:** Existing Python, asyncio, aiohttp and Pipecat; no dependencies or models added.

**Spec:** `docs/superpowers/specs/2026-11-05-voice-response-retirement-design.md`

## Global Constraints

- Only local inference; ServiceNow performs business actions.
- Preserve model/profile, Gateway, ASR/TTS generations, own voice and assistant settings.
- Preserve raw inputs, freshness, controls, claims, output ownership and original deadlines.
- No extra inference, replay, order consent, broad source staging, or reuse of spent runs.

## Review Focus

- Fresh same-shaped input must invalidate an old observation.
- Boundary replacement followed by clearing must not resurrect the old observation.
- Polar or choice controls must retain their existing guards.
- A generic update must replace an earlier specific advisory without speaking technical English.
- An incomplete automatic test must not be presented as full workflow or device acceptance.

## Task 1: Owned answered-input retirement

Files: `voice/native-bridge/native_duplex.py`, `voice/native-bridge/test_native_duplex_boundary_retirement.py`.

- [ ] Preserve the captured real-Dialog RED reproduction and ownership guard failures.
- [ ] Implement only the exact nonpolar owned-retirement sentinel from the spec.
- [ ] Run the dedicated tests and relevant existing dialogue, ordering, claim, control, processing and output tests.
- [ ] Freeze exact files and evidence for independent review.

## Task 2: Generic advisory projection

Files: `voice/callback_progress.py` and the two focused Bridge regression files identified in its handoff.

- [x] Reproduce the exact English advisory and the prior-specific replacement case before implementation.
- [x] Apply the narrow cleaned whole-label projection and verify focused regressions.
- [ ] Verify the integration with the finalized NativeDuplex and independently review exact source pins.

## Task 3: Integrate, activate and qualify

- [ ] Integrate only reviewed files and these documents; preserve unrelated audit-only work.
- [ ] Verify canonical promotion and fresh idle owners; reload only Bot and Native with new identities.
- [ ] Keep the unchanged ASR manifest when its bridge pin remains unchanged; prove every manifest role.
- [ ] Use a fresh test packet whose factual name-question grammar admits the remotely observed clarification without treating it as identity or consent proof.
- [ ] Run one bounded dialog and inspect ServiceNow outcomes, history inclusion, timings, full PCM and cleanup. Retain all limitations and failures explicitly.
