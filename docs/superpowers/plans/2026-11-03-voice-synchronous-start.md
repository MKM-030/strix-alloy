# Voice synchronous-start implementation

Spec: `docs/superpowers/specs/2026-11-03-voice-synchronous-start-design.md`.
Execute autonomously under Marcel's existing repair instruction. One implementer and one independent review; use the existing feature checkout, no runtime activation.

## Global Constraints

- Only START_CREATED_CONVERSATION requests add syncResponse:true. Ordinary messages, CREATE and END retain their current contracts.
- Empty success is not input readiness. Actual content must match the exact outstanding startup request/user and any supplied session identifier.
- Preserve callback authentication/deduplication, caller-ticket retirement, uncertain-delivery no-retry behavior, name confirmation, native business authority and capacity/cleanup ownership.
- No new payload/credential logging, real auth/native/model/audio/business request, service restart or configuration write. Use local fixtures only.

## Task 1: Support the native synchronous START response

Files: modify `voice/bridge.py`; add `voice/native-bridge/test_voice_synchronous_start.py`; change existing local fixture tests only where necessary to assert the new startup wire flag.

Read retained installed sources in `server/.local/voice-repair-20261102/entry-workflow/`: `local-caller-auth-readonly-preflight/VABotToBotSyncResponseBuilder.native.private.js`, `v3-failed-entry-trace/VABotToBotUtil.native.private.js`, and `synchronous-start-contract/DESIGN.md` when present. Native output contains requestId/clientSessionId/userId/body; empty output is status:success. Standard REST wrapping may add result. No fabricated native IDs.

1. Add failing real-Bridge local HTTP tests for direct and result-wrapped content without a status field. Assert START flag, real offered choices/input boundary and exactly one transition. Record the expected pre-fix failures.
2. Implement the smallest START-only request/response change. Reuse the matched-output/deduplication path instead of a divergent state machine. Keep existing callback authorization checks outside any shared helper. Require successful HTTP, no errors/failure status, and exact content correlation; retain empty success without manufacturing readiness.
3. Add negative and interleaving tests from the spec, including duplicate callback in either arrival order, HTTP failure after an early callback, END/cancellation and subsequent asynchronous ordinary turns. Use no real audio or platform calls.
4. Run the focused new/lifecycle/caller/startup-overlap tests with `voice/native-bridge/.venv/Scripts/python.exe`. Then run the native-bridge offline suite once. Report each failure by name and whether unchanged baseline reproduction is needed; no repeated broad tests without a change/failure reason.
5. Self-review and commit only this task's explicit source/test files. Write `.superpowers/sdd/2026-11-03-voice-synchronous-start/task-1-report.md` with status, commit, RED/GREEN evidence, exact commands/results and concerns. Do not dispatch subagents or execute a live test.

## Review Focus

Check content-versus-empty acknowledgement classification, exact correlation before consumption, callback/HTTP arrival races, cleanup after uncertain delivery, and ordinary-turn async preservation. No claim of authenticated worker/device acceptance follows from offline tests.
