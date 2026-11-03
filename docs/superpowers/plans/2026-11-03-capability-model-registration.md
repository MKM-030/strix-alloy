# Local model registration implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox syntax.

**Goal:** Supply the missing reusable ServiceNow registration stage for a new local-model identity, then hand it to the existing selected-capability Add stage.

**Architecture:** One standalone ES5 secure registrar creates model configuration and its own transformer under existing Custom-LLM infrastructure. Preview first; explicit field whitelist/default/rights/context/history/capture checks; unchanged Add handoff.

**Tech Stack:** ServiceNow GlideRecordSecure/native metadata capture; Node stdlib vm/test for injected platform contracts.

**Spec:** docs/superpowers/specs/2026-11-03-capability-model-registration-design.md

## Global Constraints

Standalone ES5; apply:false default; secure whitelisted insert only after actual prototype/default/rights preflight; Global root In-progress update set for apply; normal BR/capture retained. Switch/Add unchanged. No source/vendor history clone, no read-only identity writes, no repointing source transformer, no role/ACL change, deletion, automatic retry, model start/download/inference or business action. Preserve sealed2.2 and historical audit-only copiers. Any uncertainty is explicit Partial/refusal; never claim native apply or end-to-end model operation from source tests.

## Review Focus

- Native empty GlideElements/prototype defaults/field canWrite may differ from plain JS truthiness; refuse rather than write read-only identity.
- Duplicate identifier across same implementation and concurrent/uncertain inserts must not silently create or repair an ambiguous graph.
- Transformer scripts can drift or exceed4000; reject before first insert and compare exact readback.
- Inactive registration must remain inactive; native wrappers' `false || true` coercion must not enter this path.
- Capture or update-set restoration can fail after first insert; report Partial with immutable attempt evidence, no second insert/delete.

### Task1: Standalone registrar, meaningful regression fixtures and guide

Files: create `servicenow/byollm/capability-model-management/RegisterCapabilityModel.background.js`, `register-capability-model.test.cjs`; modify only `docs/servicenow-byollm/capability-model-management.md` for the third entry point and true scope boundaries. Existing Switch/Add code/tests unchanged.

Interface: internal parameterized ES5 registrar and JSON report tagged `[CAPABILITY_MODEL_REGISTER]`, statuses Preview/Applied/NoOp/Refused/Partial; handoff contains exact targetModel/modelConfigId/providerMappingId/providerId/selected capabilityIds plus readyForAdd. Use native proof field names and current supported graph from existing Add as evidence, not guesses. Report has no token/credential values or transformer bodies, only exact hashes/IDs/planned allowlisted values.

- [ ] Read current native evidence and dictionary/BR/payload snapshots plus existing Add's safe graph/capture patterns. Write tests for real registrar behavior under injected GlideRecordSecure/query/native metadata behavior before implementation; demonstrate RED for missing registrar, then substantive failing edge cases before guards.
- [ ] Implement the spec's bounded registrar without copying Add's whole orchestration or changing existing files. Tests cover default preview no writes, valid two inserts, own empty history, inactive preservation, exact source transformer/content references, RO/default/context/rights refusal, duplicate/partial/racing graph, source drift, limit/truncation, wrong ownership/mapping, uncertain first/second insert, capture/restore failures and idempotent NoOp. Verify source graph unchanged after all paths.
- [ ] Run new targeted tests and existing switch/add tests once after final changes; run syntax/whitespace checks. Report exact RED/GREEN commands, results and hashes. Root performs independent spec/quality review, fresh verification and local commit; implementer never commits/indexes or executes native script.

### Task2: Root review and truthful native preflight delivery

- [ ] Independent whole-registrar review of owned diff and exact source-backed platform choices; one focused fix loop if needed.
- [ ] Root may exercise a newly reviewed read-only prototype Preview through an ordinary authorized native interface if available; never substitute a vendor-copy apply or require a model inference. If unavailable, state unexercised native rights/capture limits explicitly.
- [ ] Deliver registrar plus unchanged Switch/Add and German handoff instructions. No new registered target is invented/applied, since user requested reusable tooling without a new target identifier. No existing model history cleanup is implied.
