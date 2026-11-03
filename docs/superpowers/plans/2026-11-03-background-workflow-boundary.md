# Native Background identity boundary implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish whether the installed native Background workflow preserves the authenticated caller, before implementing a replacement Voice business transport.

**Architecture:** One current-GS public RuntimeUtil start, followed by separately bounded secure metadata observations and one proven owned public close. No persistent metadata changes or production activation.

**Tech Stack:** ServiceNow public JS APIs, ordinary SDK exec, Node injected local tests.

**Spec:** docs/superpowers/specs/2026-11-03-background-workflow-boundary-design.md

## Global Constraints

- Preserve fixed workflow `2f3c8a39931093185c8132d47aba1014`, stock Background identity and all current access rules.
- Actual authenticated GS caller only; no impersonation or supplied user selection.
- One new invocation, no input, no names/consent, no resubmission after uncertainty.
- No service/model/audio changes, protected source or existing receipt modifications.
- Secure ordinary reads; use explicit null/undefined element presence checks.
- No more than one genuine owned conversation close; no cancellation claims.

## Review Focus

- Submission accepted but local response lost must remain uncertain without retry.
- Guest or changed caller and target drift must refuse before dispatch.
- Linked consumer identity must not be reported as authenticated worker proof.
- Missing/foreign conversation or denied field must prevent close.
- A close acknowledgement must not stand in for independently observed terminal cleanup.

### Task 1: Prepare bounded probe and test its refusal/cleanup behavior

**Files:** New private `server/.local/voice-repair-20261102/entry-workflow/background-workflow-boundary-probe/` only, plus this plan's ledger/report. No product code yet.

**Interfaces:** Probe actions `preflight`, `start`, `observe`, `close`; original native SDK replies and safe metadata retained in a unique new attempt folder. Helpers import without live work; execution requires one exact new flag. Native start uses only the public entry, close uses only the public end operation on a freshly reverified own chain.

- [ ] Write failing injected local tests for the specification and review focus.
- [ ] Implement minimal start/observe/close JS and sequential local SDK orchestration.
- [ ] Run focused tests and self-review; report exact files, commands, hashes, limitations.
- [ ] Obtain independent source/operational review before execution.

### Task 2: Execute one bounded boundary observation and decide transport

**Files:** Only the new attempt folder and this plan's ledger/report.

- [ ] Verify frozen source hashes, no existing attempt and fresh preflight identity/target.
- [ ] Dispatch the new start once; retain receipt before any dependent operation.
- [ ] Observe authentic same-plan outputs and worker identity; run proven close once.
- [ ] Independently observe terminal cleanup; record any uncertainty without guessing.
- [ ] Choose the next implementation from the actual identity result. Preserve the full Voice goal as open until continuation, platform and media acceptance exist.
