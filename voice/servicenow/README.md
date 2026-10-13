# ServiceNow SCC source and maintenance files

These files document this configured demonstration. They are not an automatic installer for a different instance. Record IDs, installed applications, model/provider references and destination credentials must be reviewed for that target.

## Capture

Run `scc-batch-plan-compact.js` in Global Scripts - Background. Review its exact source manifest and prerequisites. After final metadata changes, inject the fresh `frozen_manifest_candidate` into `scc-batch-capture-frozen.js`. The executor verifies each source revision and captured XML, groups records by their actual scope, rejects unexpected updates and leaves all update sets in progress. Never reuse an old frozen manifest after changes.

The root capture script and generated compact variant are retained for reproducibility. The frozen executor is the shorter reviewed execution path. Capture evidence is a historical checkpoint, not proof that later edits were captured.

After final acceptance and a successful fresh capture, inject that capture result into `VERIFIED_CAPTURE` and its exact source manifest into `FROZEN_MANIFEST` in `scc-batch-complete.js`. Select an update set outside this batch before execution. The completion helper rechecks the exact owned parent/children, source and XML revisions, scope assignment and update membership before changing any state. It completes the three children before the parent and reports partial state changes if an update fails. Do not run it with historical evidence after subsequent metadata edits.

The included final evidence records 120 captured configuration records and a subsequently completed parent plus three children. The mobile entry is active. This metadata checkpoint is not a functional release: native ServiceNow Voice integration remains blocked, while the external speech client is a separate verified demonstration path. Public navigation/login was repaired in gateway commit `b8de643`; real-phone and repeated-start acceptance remain open. See `../SCC-NATIVE-VOICE-FINDINGS.md` and the current runbook.

## Runtime identity and unsuccessful diagnostics

Direct edits of the SCC consumer-account and adapter references did not fix the dialog and were overwritten by the runtime. The corresponding diagnostic repair script is deliberately excluded from this bundle and must not be deployed. No lasting runtime repair from those edits is claimed.

The first conversation with a fresh external user identifier created a correct binding and reached the agent, but reusing that stable identifier on a second start again selected an inactive consumer. This is not a durable identity fix. An optional per-dialog alias is implemented in the separately owned bridge runtime. The first configured full-audio conversation passed, while repeated-start and real-phone acceptance remain open. Consumer/account identities and their rows are instance-specific runtime data, not Update Set configuration. Do not copy them between instances.

## Local verification

From this directory:

```text
node scc-build-compact-capture.cjs
node scc-batch-capture-check.cjs
node scc-batch-complete-check.cjs
node --expose-internals scc-react-context-fix-check.cjs
node --test scc-halogen-request-transformer.test.cjs
```

The runbook is `../SCC-DEMO-RUNBOOK.md`. Audio and gateway runtime sources remain in their separately owned `voice/` files; this bundle does not overwrite them. Private context JSON exports, credentials and screenshots are not included.
