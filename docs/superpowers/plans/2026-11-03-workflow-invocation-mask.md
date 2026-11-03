# Workflow invocation mask repair plan

> **For agentic workers:** Use superpowers:subagent-driven-development. Steps use checkbox syntax for tracking.

**Goal:** Prepare the smallest supported correction for the exact denied child, then seek the required specific outer-authority approval.

**Architecture:** Preview-first guarded fix script calls the verified public native DAO once with the full three-role list. The child data mask stays at two roles.

**Tech Stack:** Native ServiceNow JavaScript, Node injected local tests, ordinary SDK.

**Spec:** docs/superpowers/specs/2026-11-03-workflow-invocation-mask-design.md

## Global Constraints

- One outer admin mapping addition; existing roles, child mask, invoke ACLs and Dynamic users preserved.
- No user-role grants, child ACL relaxation, service user or direct/private native helper.
- Preview default; apply only in verified normal Global creation/capture context after specific approval.
- Normal domain/row/field rights, complete exact readbacks and immutable operation receipt.
- No replay of any old probe or automatic test/model/service change.

## Review Focus

- Passing only the newly added role would remove existing roles through native full-set delta.
- Wrong active application can stamp the new mapping into the wrong scope.
- Partial native success must not permit a second update.
- Changed child mask/ACL must stop the operation before application.
- Outer authority expansion must be disclosed despite the preserved child data intersection.

### Task 1: Prepare and independently review the exact fix

- [ ] Write failing tests for preview/no side effects, drift/rights/context refusal, full role-list call once and uncertain post-state.
- [ ] Implement new preview-first source and focused tests only.
- [ ] Write exact execution review/parameters and preservation/capture limits.
- [ ] Independently review source and native side-effect footprint.
- [ ] Ask the specific outer-authority approval with the finished review linked.

### Task 2: Apply after approval and validate changed Voice route

- [ ] Normally select Global and create the exact ordinary WIP capture container; verify real current context.
- [ ] Freeze fresh exact preimages and execute the public native update once with rollback logging.
- [ ] Independently verify parent addition, child/ACL preservation and native capture.
- [ ] Prepare one new bounded no-order Voice test for the actually changed role chain; never replay V7 or the executed Background probe.
