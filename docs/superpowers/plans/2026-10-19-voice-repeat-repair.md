# Voice callback and repeat-call repair

Goal: Restore audible replies and repeated native SDK calls using evidence from the 21:02–21:04 phone test.

Evidence: ASR succeeded; request 7f069a7a2cfd431dafd99301965bd3e7 completed before its final OutputText callback. Bridge discarded the text after marking ended. Later creates returned 503; nativeSessions is now zero, so persistent capacity leakage is not yet established.

- [x] Preserve live logs and inspect exact running source/processes.
- [ ] Reproduce terminal-before-output through real local Bridge callback/event routes; implement bounded terminal draining while preserving request/session identity and explicit-end fences.
- [ ] Add bounded non-sensitive SDK/Managed TURN stage diagnostics; reproduce 503 and repair only the confirmed failure.
- [ ] Run relevant event, cleanup, SDK and dialog regressions on isolated candidates.
- [ ] Review diffs, back up exact live files, deploy only while nativeSessions=0, and restart only owned Native/Bridge processes as required.
- [ ] Verify real configured SDK greeting, spoken user input and bot output, then cleanup and immediate repeat calls. Report phone audibility separately from synthetic checks.

Constraints: Preserve current authentication, origin restrictions, TURN TLS validation, user settings and unrelated uncommitted changes. No aggregate model launcher restart; retain current Gemma backend. Do not log credentials, raw callback payloads, or user audio.
