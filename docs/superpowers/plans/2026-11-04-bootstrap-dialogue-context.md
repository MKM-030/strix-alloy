# Bootstrap Dialogue Context Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve an optional local answer across bootstrap progress changes that were excluded from its prompt.

**Architecture:** Keep the model protocol's raw observation revision. NativeDuplex alone binds bootstrap release to a detached fingerprint of unchanged public replies, actual exposed question/source, native input control, caller context and startup state. Processing and own emitted speech history are excluded; settled startup retains the existing strict revision guard.

**Tech Stack:** Python asyncio, dataclasses, hashlib, unittest; existing fake call/model and actual Dialog observation method, with no service or inference calls.

**Spec:** Root's approved targeted implementation, 2026-11-04; design GO explicitly covers admission, completion, queued output and every PCM chunk.

## Global Constraints

- Modify only native_duplex.py, its related offline regression and this plan in the existing worktree at e6457d6.
- Preserve native_bridge.py, raw caller FIFO, one model attempt per caller input, source settings, all services and model processes.
- Meaningful public, input-control, question, caller or bootstrap state changes must invalidate output; processing included after bootstrap remains guarded.
- Discard diagnostics contain fixed reason codes only, at most eight per call.

## Review Focus

- A loader changes after admission but before TTS, or between PCM chunks: output remains valid only for unchanged bootstrap context.
- A hidden input control changes without a global revision increment: stale output is rejected.
- Bootstrap settles or fails without a revision increment: old startup wording is rejected.
- First sentence drains and adds own emitted history: the second sentence remains eligible.
- Public/question/caller context changes: stale candidate and queued output are rejected without replay.

### Task 1: Bind bootstrap output to its relevant context

**Files:** Modify voice/native-bridge/native_duplex.py; create voice/native-bridge/test_native_duplex_bootstrap_context.py.

**Interfaces:** Preserve model response keys and snapshot schema. The private observation binding may carry a bootstrap fingerprint; all Native release/playback checks consume the same binding.

- [x] Write offline tests for the five review conditions, including actual Dialog processing updates.
- [x] Run the new test file before implementation and confirm the loader regression fails because no answer reaches TTS.
- [x] Add a detached bootstrap observation binding and shared validity predicate; retain strict ordinary revision behavior after startup.
- [x] Add bounded fixed-code logs at actual candidate/queue/PCM discard points.
- [x] Run the new regression and existing NativeDuplex tests; verify native_bridge.py's hash is unchanged.
- [x] Commit only this scope for Root's independent review and later activation.

## Verification

The 15 new regressions run against base e6457d6 report 9 assertion failures and 3 missing-output timeouts. The implementation passes all 89 `test_native_duplex*.py` checks, including all 15 new regressions. `native_bridge.py` remains SHA256 `7315f2a24a868166388dc27dc9f9460c3ebfc0a41ef14428541298aab443891e`. These are offline fake-call/model/media checks; no runtime activation or performance measurement was performed.
