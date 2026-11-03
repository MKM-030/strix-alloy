# Stable Voice help implementation plan

> **For agentic workers:** Use subagent-driven-development. Marcel authorizes autonomous repair without further questions.

**Goal:** Finish a general help answer while unrelated ServiceNow progress updates arrive, preserving all caller and business-state safeguards.

**Architecture / design:** The S6 synthetic SDK call received a correct welcome and first help PCM 0.794 seconds after ASR, but the fallback ended with `current=False` before client teardown. The real `Dialog.observe_state` and `NativeDuplex._synthesize` reproduce this failure when a progress update changes `observation_revision`. Static capability explanation contains no mutable business fact. Bind that static explanation to the existing call, epoch and task revision, while retaining observation/question binding for any current-question suffix. Do not accept interrupted output as a passed test. Generated model output, status and business responses keep their existing observation guards.

**Tech Stack:** Existing Python asyncio Native bridge, unittest/pytest and own TTS. No new dependency.

## Constraints and review focus

- Preserve ServiceNow business authority, current input and confirmation state, queue capacity and no-replay behavior.
- Preserve cancellation by new user input, changed task, closed/failed call, and changed playback generation.
- Static explanation must not include a current question or other mutable fact without its guard.
- Progress-only changes may not truncate an invariant explanation.
- Stale question suffix, generated response and status must remain invalid after a relevant change.
- S6 is spent and remains uncertain. No existing result, harness, plan or fixture may be rewritten. Reuse fixture bytes, never synthesize again for this change.

## Task 1: Narrow regression and implementation

Files: `voice/native-bridge/native_duplex.py` and a focused `test_static_help.py` (or existing relevant test module).

- [x] Reproduce with real `Dialog.observe_state`, `_general_help` fallback and controlled multi-chunk `_synthesize`; observe failure before code change.
- [x] Implement the smallest distinction between invariant help text and mutable question-derived text. Keep `_valid` unchanged unless independent evidence requires otherwise.
- [x] Verify progress updates during queued and active TTS; verify stale question suffix and user/task/close interruption still reject output; verify no extra Bot business turn.
- [ ] Run focused Native tests, then the full Native suite once; independent source review; commit isolated change.

## Task 2: Activate and measure once

- [ ] Root integrates reviewed source and prepares one exact Native-only activation preserving current model/ASR/TTS/Bot/Gateway process generations, updating only necessary startup pins.
- [ ] Use a fresh one-use reviewed activation and independent current source/owner/health observation. Never replay spent activation helpers.
- [ ] Prepare one new async-help SDK campaign from the corrected production contract with unchanged strict `current=True`/received PCM/full drain gates, reuse existing fixed help PCM, then execute once and verify actual cleanup and separate access/refresh revocation.
- [ ] Record outcome and limitations in the canonical handoff. Device playback remains separately unverified.

## Task 1 execution notes

- RED observed before implementation: a real processing observation truncated active generic fallback after its first PCM chunk; queued invariant output became invalid; a current-question quote shared the same output. The end-to-end local worker also stopped the fallback while the one owned bootstrap stayed pending.
- Ruling: retain a single invariant output when there is no current question; only a separate current-question quote retains the mutable observation pin. This avoids splitting the common generic answer while preserving the existing stale-question policy. Call/epoch/task/playback guards and `_valid` are unchanged.
- The outer local-worker exception boundary now uses the same static fallback path; its status branch retains the normal status kind and observation binding.
- Per-call fallback diagnostics contain only the owned call id and fixed `controller_busy`, `unavailable` or `model_failed` reason, with no prompt, provider detail, token or request body and no retry. RED tests cover all reason branches and the outer error boundary.
- New focused tests: 8 passed. Existing focused Duplex regressions plus the new module: 68 passed. Full Native discovery uses the already available external test-deps through only the test process's PYTHONPATH; no dependencies are installed. Source review and commit remain pending.

### Complete Native discovery result

The single full Native unittest discovery ran 1195 tests in 189.773 seconds: 1194 passed; `test_reserved_slots.ReservedSlots.test_delayed_server_submission_idle_first_then_busy_never_borrows_role` failed because its narrow observer window returned `observer_unavailable` instead of `no_terminal_or_active_witness`. That test and `conversation_admission.py` are unchanged by this branch. The one targeted follow-up run passed in 1.758 seconds. This supports a timing-sensitive observation, not a claim that the full suite was green or a proven baseline failure. No second full discovery or out-of-scope fix was performed. Full output: `C:/Users/Marcel/AppData/Local/Temp/codex-voice-static-help-native-20261103.log`. Independent review remains pending; no commit, live reload or model/service operation was performed by the implementer.
