# Voice startup cleanup implementation plan

> Execute in the existing isolated browser worktree. User delegated design and implementation and requested no questions.

**Goal:** A failed or superseded start must leave no input stream, extra socket or stuck connection indicator.

**Design:** Keep the deployed OAuth, successful WebRTC/audio path and established signaling-close behavior. Use the existing call owner and failure cleanup. Check ownership after permission/media promises and stop an input acquired for a retired start. Contain synchronous signaling construction failures. Suppress delayed failure notices belonging to a replaced call.

**Files:** `Start-voice-session.js`, its exact native-preimage derivative builder, the portable `regressions.test.cjs` fixture/tests, and two lines in `VoiceTestingUIUtils.disconnectVoice`. Native Stop marks the same window-local RTC owner as cancelled and clears progress. Start never assumes the captured framework state reflects later updates. No backend, model, microphone or SDK call is needed for source validation.

- [x] Baseline: existing 43 portable regression tests pass.
- [x] Add real-handler failing regressions for denied/rejected/empty media, synchronous socket construction, late permission results, late streams and old delayed notices.
- [x] Observe the failures before editing product behavior.
- [x] Implement the smallest owner/cleanup changes and update the exact derivative builder.
- [ ] Run browser regressions, obtain independent source review, then integrate after normal model recovery.
- [ ] Deploy reviewed native Start/helper records with readback and capture verification; update the integrated consent/audio proof to those exact sources before its one actual run.

**Acceptance:** Current early failures clear call/progress and release owned input once. Superseded promises never open another socket, emit stale errors, or alter the replacement call. Existing real media/playback, cached-token recovery and healthy RTC after signaling-close tests remain unchanged. No autoplay repair is inferred from these bugs.
