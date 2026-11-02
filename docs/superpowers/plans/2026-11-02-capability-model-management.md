# Capability model maintenance implementation plan

> **For agentic workers:** Use test-driven development and independent review. User requested autonomous execution; root coordinates native mutations and Voice tests. Builders must not execute bulk scripts.

**Goal:** Complete the authorized VA Input repair and deliver reusable capability model switch/add scripts with correct model lineage.

**Architecture:** Two standalone native ES5 entry files, explicit parameters and preview mode; derive relationships from the existing provider graph and native audited schema. Preserve historical sources and existing provider selections.

**Tech stack:** ServiceNow GlideRecord/GlideRecordSecure/native generators, existing SDK 4.14 alias, Node VM boundary tests, existing local Voice SDK probe.

**Spec:** `docs/superpowers/specs/2026-11-02-capability-model-management-design.md`.

## Constraints and review focus

- No model/speech lifecycle change or automatic model adoption for these metadata operations.
- No bulk apply is implied by creation of a reusable script; only the already authorized one-field live repair is executed now.
- Preserve source/vendor history, secrets, all other model alternatives, prompt contracts and native calculated fields.
- Cover duplicate labels, nonexistent capability IDs, empty selection, inactive alternatives, protected targets, repeated apply, revision drift and partial native failure.
- A complete preflight is not transactional atomicity. Capture/readback each intended mutation; stop on partial or unproved native child generation.

## Task 1 — live repair and native history audit

- [x] Freshly read target/39 guards and exact empty header; establish native version-lineage relationship and copying cause (literal UI label unconfirmed).
- [x] Execute approved one-model correction and guarded bookkeeping continuations exactly once, preserving normal business rules, rollback and one no-delete CU.
- [x] Fresh complete typed source/guard/header/capture readback: 40 rows, 1,030 fields, seven memberships, one correct XML capture.
- [x] Prove actual VA Input success. Actual native conversation3081bdb9... and synthetic-name payload correlate VA Input logefa1f5f9...: Halogen success7,307ms/no error. Host/table clock offset~88s explains initially missed time-window query. Bounded positive-name SDK probe still failed after that: two downstream error200000 invocations, no returned content within40s; cleanup1.078s/capacity0. Diagnose downstream failures before another probe; full Voice acceptance remains open.

## Task 2 — capability switch Fix Script

Files: `servicenow/byollm/capability-model-management/SwitchCapabilityModels.fix.js` and `switch-capability-models.test.cjs`.

- [x] Reproduce selection/model/lineage errors with native-boundary tests, then implement preview/apply and all-or-selected model switching.
- [x] Keep only intended active/published custom model assignments mutable; report missing/protected/inactive alternatives, preserve provider/prompt routing and real history.
- [x] 62 Switch tests, independent review and actual read-only VA Input preview (zero writes). Explicit selectors cannot hide same-implementation native model-string ambiguity.

## Task 3 — add-model Background Script

Files: `servicenow/byollm/capability-model-management/AddCapabilityModel.background.js` and `add-capability-model.test.cjs`.

- [x] Reproduce wrong source-model/version-history copying; implement additive registered-model configuration with verified native binding generation.
- [x] 47 Add tests cover parent/history/model references, calculated fields, no source modification, duplicate/no-op behavior, native empty-element truthiness, actual Global picker and partial failures.
- [x] Independently review scripts together; no bulk mutation run on the instance.

## Task 4 — integration and durable delivery

- [x] Write `docs/servicenow-byollm/capability-model-management.md` with examples for Gemma/Halogen/arbitrary registered models and exact selection/preview/apply/maintenance semantics.
- [x] Current full byollm run231/231 and both syntax checks; final independent Add/Switch review109/109. Native Switch and Add-existing/new-draft previews pass with zero writes; original context restored.
- [x] Stage the explicit owned source/test/docs for local delivery and update current follow-up. Continue the original Voice goal; do not mark complete from metadata alone.
