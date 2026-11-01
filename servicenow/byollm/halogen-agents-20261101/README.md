# Halogen Agent model selection — 1 November 2026

Product changes are prepared offline. The first ACL-checked native run stopped before any configuration write. No model, speech service, microphone, or business process was started.

Marcel selected **Halogen for the business Agent steps as well as the local conversation**, retaining separate configuration for each role. The technical model identifier is `halogen-v2`. ServiceNow remains the sole business executor.

## Configuration scope

| Role | Selection and configuration |
| --- | --- |
| Speech synthesis | Existing own-voice TTS selection; unchanged by this change. |
| Speech recognition | Existing Qwen3-ASR 0.6B / CrispASR selection; unchanged. |
| Local conversation | Saved central Halogen selection, consumed through controller 8840. |
| Agent reasoning and input/output processing | Existing Custom LLM capability graphs; the prepared change selects Halogen on 66 active, published prompt configurations. |

The four capability graphs are ReAct Engine, Agent Execution, Data Extractor, and the Output Refiner reachable conditionally through the native Communicator. Five inactive prompt configurations remain untouched. Definitions, provider defaults, usage conditions, prompt text, validators, published state, and the Prompt Mirror's three disabled execution gates remain unchanged.

The actual selected ReAct topic establishes ReAct and Data Extractor calls. Native Communicator establishes a conditional Output Refiner call. Its protected task-mapping helper did not expose source, so the conditional branch could not be proven disabled. The SCC Agent's `research` field is false. These observations do not establish every nested native implementation or every installed Agent route.

## Required adapter changes

Changing the model selector alone would bypass existing SCC name-confirmation, caller-context and execution-ledger handling embedded in the Gemma transformer. The Halogen candidate carries those same rules through an explicit Halogen/SCC configuration gate. The existing Gemma transformer remains intact.

The Halogen transformer also accepts the observed JSON-string form of `response_format`, preserving its complete schema as an object. Existing legacy Vision dispatch and unrelated transport behavior remain intact. The Ledger adds only the explicit Halogen opt-in and retains its request-model, configuration, persona and structured-observation gates.

Ten focused offline checks passed after four expected failures against the original source. They cover SCC prompt/context/name/ledger parity, schema preservation, identity rejection, existing transport and Vision behavior. Platform dependencies use synthetic doubles; these checks do not prove model inference, ServiceNow execution, or iPhone playback.

Nineteen deployment checks also passed. They cover complete preflight before writes, intended-field changes, native side-effect detection, exact capture membership, deletion/identity/revision rejection, the two observed script-language companions and a zero-write successful repeat. Root independently verified both test groups and the frozen artifact's hash.

```powershell
node --test servicenow/byollm/halogen-agents-20261101/halogen-agents.test.cjs
```

The migration checks require the private prechange snapshots under `server/.local/voice-goal-halogen-agents-20261101`. They are scoped migration evidence rather than a standalone fresh-instance installer.

## Instance application and capture

The frozen application script is prepared separately from the product sources. Its intended changes are 66 prompt model fields, the existing Halogen request-transformer field, and the existing Ledger script field: **68 source records**. It checks the whole preimage before writing, retains normal Business Rules, verifies the resulting records, and captures them through native Update Set APIs.

The new capture is **Custom LLM Platform 2.3 - Halogen Agent Delta - NO DELETE 20261101**, with Global and AI Agents scope children. It remains work in progress and contains no deletion actions. Completed historical sets and the sealed 2.2 Fresh Instance delivery remain intact. This delta is not itself a full replacement platform delivery.

The SDK run must retain its reason and native rollback context. Exact private preimages and the script hash identify the reviewed operation. If execution times out, inspect its actual execution-history record before deciding any next action; do not start a second copy.

The first frozen executable is `server/.local/voice-goal-halogen-agents-20261101/apply-halogen-agent-configuration.js`, SHA-256 `b14dd89fcc6114cdf311c6c6f09795d7ea2b3c93f9fc49414258e8fbc413b649`. After explicit approval it ran once in Global scope with native rollback recording. Execution `771610a5935cd314e7f2b9fa6aba105a` stopped on `target_write_denied` in preflight: zero source writes, zero Update Set attempts and zero captures. The previous current Update Set was preserved. No rollback context was created because no configuration changed. The normal record ACLs deny these edits; no role or ACL was changed to alter that result.

An additional administrator-maintenance variant is separately prepared, SHA-256 `6fbeab7c5b99bf02c53e886c5c432d1e1806c09645dcd96a11c54a76c6bb2dd9`. It needs explicit per-run approval for its different authority: ACL-enforced reads/guards/readback/capture remain, but the same frozen source-field assignments use the native admin Background Script database API independently of UI record-write permission. It requires admin role, explicit maintenance mode, and a readable empty protection policy on every source; protected vendor records are refused. Roles, ACLs, security properties and business permissions remain unchanged. Twelve additional tests cover the authority boundary and native boolean representation; all three offline groups passed, 41 checks total. Private `EXECUTION-REVIEW-ADMIN-MAINTENANCE.md` contains the full script, exact diff, target/flags and authority explanation. This additional run has not executed; its approval question is pending.

## Runtime acceptance remains open

The original retained Halogen run still requires its exact ownership reconciliation and five-frame memory recovery before startup. The saved model profile and safety thresholds remain unchanged. Current preparation does not release an iPhone test.

After actual runtime readiness, verify one harmless structured-output request, then a short phone check for own voice, name/spelling, background noise, interruption and a second call. One genuine ServiceNow sequence must separately establish context consumption, timely progress and the business outcome. Preserve the complete Voice objective recorded in `TASK80_FOLLOWUP.md`.
