# Capability model Registrar v2 implementation plan

> **For agentic workers:** Execute inline with superpowers:executing-plans. Root owns final review/integration and every native/SDK/runtime operation.

**Goal:** Add a new reusable Registrar v2 that accepts the proven native ES companion safely and prepares a default-off reviewed long-script policy.

**Architecture:** Preserve the existing Registrar byte-for-byte and create a versioned standalone ES5 successor. Validate target and native ES companion separately with secure reads, exact parent binding and complete captured-value equality; never create the companion. Keep long-script support bounded at both guards and blocked until Root supplies the independently verified EOL policy.

**Tech Stack:** ES5 ServiceNow server script; Node fake CPU boundary tests; existing local Acorn for ES5 verification.

**Spec:** Existing `docs/superpowers/specs/2026-11-03-capability-model-registration-design.md`, amended by Root's 2026-11-05 assignment and saved `SAVED-NATIVE-CAPTURE-STRUCTURE.v1.ANALYSIS.json`. The old spec's global 4000-content assumption is superseded only for a separately reviewed finite opt-in policy; dictionary metadata remains unchanged.

## Global constraints

- Work only in this isolated branch from f1ba1930f5ff42a40415b1fe19bea2085001682b; create new versioned files.
- No native writes, model/service/SDK operation, downloads, scope/role/ACL changes, source writes, companion creation or canonical edits.
- Preserve inactive/default Preview, permissions, original content hashes, source graph freshness, target/history/capture checks, context restoration and honest Partial/no-retry behavior.
- Finite long-script ceiling: 65,536 UTF-16 units and UTF-8 bytes. Default off. Exact reviewed source identities/ownership/hash/length/graph required; no EOL relaxation chosen by this task.

## Review focus

Wrong/extra/stale/denied ES companion must fail; ordinary single-record captures must remain valid. Native XML siblings need separate direct-field dictionaries and exact identities. Source graph must include source companion presence/revision. Long policy cannot silently weaken both length gates. Source and derived target content must never be conflated.

### Task 1: Native ES companion compatibility

- [x] Verify clean isolated baseline: all 170 existing model-management CPU tests pass.
- [x] Copy the existing Registrar/tests to NEW `RegisterCapabilityModel.v2.background.js` and `register-capability-model.v2.test.cjs`; create RED tests using the saved real two-sibling shape plus wrong/extra/stale/denied companions.
- [x] Add the sole supported companion schema, secure unique reads and source graph watch; update bounded transport grammar to allow exactly one matching target plus at most one proven ES companion.
- [x] Require complete companion equality, preserve single-record grammar and run focused model-management CPU tests.

### Task 2: Bounded long-source policy

- [x] Add default-off interface and RED tests for exact reviewed identity/ownership/hash/length, source graph and both 65,536-unit/byte gates.
- [x] Root approved explicit LF derivation after the independently frozen LF spike; retain distinct source/derived hashes and exact native target/capture equality.
- [x] Create the v2 guide with parameters, Preview/Apply stages, history semantics, limits and truthful remaining native qualification.

### Task 3: Frozen source handoff

- [x] Run focused fake CPU tests and ES5 parsing; verify original Registrar and handed-off files unchanged.
- [x] Freeze source handoff for Root with exact branch/path/hashes and known limits for independent source review. No integration, publication or native execution.

Ruling: The managed create_worktree call did not return a path/operationId; Root authorized terminating only its waiting cell and reusing this already clean isolated worktree. The pending app-side request may still finish later; no duplicate create, reset, process kill or manual cleanup was performed.

Root policy refinements applied: the exact known request-code scanner exception is request-only, keeps current revisions bound through the manifest/graph and never exempts a response or arbitrary TODO text. All raw source facts precede normal policy refusal. The original Halogen source remains unchanged. LF evidence pins are recorded in the new guide and frozen handoff.

Verification so far: all 170 original model-management cases passed before changes; the final focused combined run passed 267/267 cases (97 in the new v2 suite). The native ES companion positive case and source-graph drift/denial cases were first RED against the old behavior. The LF positive cases were first RED at the old length guard. Request-only scanner/revision refinements were separately RED before GREEN. No SDK/native operation occurred.
