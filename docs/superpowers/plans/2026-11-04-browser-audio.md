# Browser audio stream fallback implementation plan

> **For agentic workers:** Use superpowers:executing-plans to implement this single task with TDD. Root reviews and integrates the isolated result.

**Goal:** Play a valid incoming live audio track when its WebRTC event has no associated stream.

**Architecture:** Keep the existing stream path. For a bare live audio track, construct one `window.MediaStream([event.track])` after the current-call ownership check, inside the existing media failure boundary. Share the selected stream between the audio element and optional analyzer.

**Tech stack:** ServiceNow browser JavaScript; existing portable Node full-handler regression fixture.

**Spec:** Root-approved scope: Start handler, its exact original-source derivative builder, existing regression test, and this plan. No runtime/SDK/primary writes, original-fixture edits or commit.

## Constraints and review focus

- Preserve current-peer/current-call guards before allocating a stream or touching media.
- Accept only `kind=audio`, `readyState=live` for the new bare-track path; preserve existing stream behavior.
- Keep required `audio.play()` failure cleanup and optional analyzer failures independent.
- Existing disconnect owns peer/context/local input and clears the audio element; add no separate remote-track stop owner.
- This corrects a source defect, not the separately failed pre-WebSocket harness or physical-device playback evidence.

## Task: retain bare remote audio for playback

**Files:** `voice/native-servicenow/Start-voice-session.js`; `voice/native-servicenow/tests/browser-parity/build-candidate.cjs`; `voice/native-servicenow/tests/browser-parity/regressions.test.cjs`.

- [x] Add full-handler regressions: live bare track reaches playback and the same analyzer stream; existing stream is retained; stale owner/peer and bare video/ended track do nothing; failed wrapping/playback uses existing cleanup; optional analysis failure preserves media; normal disconnect retains existing ownership.
- [x] Run the live-bare regression against unchanged production and observe `played=0` versus expected1.
- [x] Add the minimal fallback in the builder and regenerate the production derivative without changing the frozen original.
- [x] Run the complete browser-parity suite and `git diff --check`; verify the original fixture hash and four-file scope.
- [x] Report exact source hashes, test result and limitations to Root without commit or deployment.

**Verification:** `node --test voice/native-servicenow/tests/browser-parity/regressions.test.cjs` exercises the real complete handler with browser dependencies replaced offline. No project-wide Node package/test command exists; this is the documented suite for the changed browser component.

**Results:** Targeted RED failed at `played=0` versus1. The complete browser-parity suite then passed36/36. Combined `node --test voice/native-servicenow/routing-draft.test.cjs voice/native-servicenow/tests/browser-parity/regressions.test.cjs` passed42/42 with no skips. `git diff --check` passed; the retained original fixture is unchanged. No commit, deployment or runtime test was performed; physical playback and end-to-end welcome latency remain separate acceptance work.
