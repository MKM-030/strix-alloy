# Pending Dialogue Context Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve a new pending caller's local answer when an older business callback changes only observation metadata.

**Architecture:** Pending-input output uses an immutable hash of the actual exposed snapshot, excluding observation revision metadata and own emitted-history facts only from comparison. Full native control, pending IDs, caller/epoch/task/context key and business/readiness/closed state remain guarded. The same signature prevents redundant Pipecat observations; raw wire keys/history remain unchanged. Existing bootstrap binding and unmasked strict revision guards remain.

**Tech Stack:** Existing Python asyncio, hashlib and fake-call/model offline unittest fixtures.

**Spec:** Root's explicit design GO after the saved mixed-input call showed an old Q1 reply invalidating Q2 eight milliseconds after ASR.

## Constraints and review focus

- No changes to FIFO, business dispatch, local busy policy, ServiceNow state, source guard grammar, native_bridge.py or live services.
- Record the signature before respond's first await; dedup before scheduling observe.
- Capture the owned conversation and use a unique scheduled-operation identity so an older failed update cannot clear a newer matching signature.
- Failed/cancelled observations may be tried again; genuinely changed controls/callers/state must invalidate output.
- Own history stays in the wire prompt and must not self-invalidate the current answer.

### Task 1: Pending binding and observation dedup

**Files:** native_duplex.py; new test_native_duplex_pending_context.py.

- [x] Reproduce in RAM: snapshots differ only by observation_revision; redundant observations use revisions 0,1,1; Q2 binding falsely becomes stale.
- [x] Add offline regressions; six of the initial seven fail before implementation.
- [x] Implement pending-only binding and synchronous semantic observation dedup with matching failure/cancellation clearing.
- [x] Add pending identity, ABA scheduling and cancellation regressions; cancellation regression fails before its fix.
- [ ] Run all related checks, commit this scope, and obtain independent review before Root's later activation.
