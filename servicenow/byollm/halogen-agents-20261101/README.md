# Halogen Agent model selection — 1 November 2026

**The approved Halogen Agent configuration and capture reconciliation are complete.** All 66 active prompts select `halogen-v2`; both the Halogen request transformer and Ledger match their approved source exactly. Full native readbacks and independent offline audits verify 68 intended sources and 69 unique no-delete Customer Updates, including one preserved native metadata signal. The batch remains a WIP delta, separate from the sealed 2.2 Fresh Instance package. See [the execution and capture audit](POSTRUN.md). No model, speech service, microphone, inference or business operation was started by this maintenance.

Marcel selected **Halogen for the business Agent steps as well as the local conversation**, retaining separate configuration for each role. The technical model identifier is `halogen-v2`. ServiceNow remains the sole business executor.

## Configuration scope

| Role | Selection and configuration |
| --- | --- |
| Speech synthesis | Existing own-voice TTS selection; unchanged by this change. |
| Speech recognition | Existing Qwen3-ASR 0.6B / CrispASR selection; unchanged. |
| Local conversation | Saved central Halogen selection, consumed through controller 8840. |
| Agent reasoning and input/output processing | Existing Custom LLM capability graphs; 66 active, published prompt configurations now select Halogen. |

The four capability graphs are ReAct Engine, Agent Execution, Data Extractor, and the Output Refiner reachable conditionally through the native Communicator. Five inactive prompt configurations remain untouched. Definitions, provider defaults, usage conditions, prompt text, validators, published state, and the Prompt Mirror's three disabled execution gates remain unchanged.

The actual selected ReAct topic establishes ReAct and Data Extractor calls. Native Communicator establishes a conditional Output Refiner call. Its protected task-mapping helper did not expose source, so the conditional branch could not be proven disabled. The SCC Agent's `research` field is false. These observations do not establish every nested native implementation or every installed Agent route.

## Required adapter changes

Changing the model selector alone would bypass existing SCC name-confirmation, caller-context and execution-ledger handling embedded in the Gemma transformer. The applied Halogen transformer carries those same rules through an explicit Halogen/SCC configuration gate. The existing Gemma transformer remains intact.

The Halogen transformer also accepts the observed JSON-string form of `response_format`, preserving its complete schema as an object. Existing legacy Vision dispatch and unrelated transport behavior remain intact. The Ledger adds only the explicit Halogen opt-in and retains its request-model, configuration, persona and structured-observation gates.

Ten focused offline checks passed after four expected failures against the original source. They cover SCC prompt/context/name/ledger parity, schema preservation, identity rejection, existing transport and Vision behavior. Platform dependencies use synthetic doubles; these checks do not prove model inference, ServiceNow execution, or iPhone playback.

Nineteen deployment checks also passed. They cover complete preflight before writes, intended-field changes, native side-effect detection, exact capture membership, deletion/identity/revision rejection, the two observed script-language companions and a zero-write successful repeat. Root independently verified both test groups and the frozen artifact's hash.

```powershell
node --test servicenow/byollm/halogen-agents-20261101/halogen-agents.test.cjs
```

The migration checks require the private prechange snapshots under `server/.local/voice-goal-halogen-agents-20261101`. They are scoped migration evidence rather than a standalone fresh-instance installer.

## Instance application and capture

The completed change comprises 66 prompt model fields, the existing Halogen request-transformer field and the existing Ledger script field: **68 source records**. Frozen per-run preimages, normal Business Rules, exact native readback and native Update Set capture were retained throughout. The earlier partial attempts and their rollback records remain immutable; do not rerun any submitted script.

The verified capture is **Custom LLM Platform 2.3 - Halogen Agent Delta - NO DELETE 20261101**, with 66 updates in the AI Agents child, three in the Global child and none in the parent. All 69 actions are `INSERT_OR_UPDATE`; no outer/embedded deletes, duplicate update names or insert/delete conflicts were found. The holding set is empty, ignored and outside both the parent tree and native base batch. Completed historical sets and the sealed 2.2 Fresh Instance delivery remain intact. This WIP delta is not itself a full replacement platform delivery or proof of target import.

The SDK run must retain its reason and native rollback context. Exact private preimages and the script hash identify the reviewed operation. If execution times out, inspect its actual execution-history record before deciding any next action; do not start a second copy.

The first frozen executable is `server/.local/voice-goal-halogen-agents-20261101/apply-halogen-agent-configuration.js`, SHA-256 `b14dd89fcc6114cdf311c6c6f09795d7ea2b3c93f9fc49414258e8fbc413b649`. After explicit approval it ran once in Global scope with native rollback recording. Execution `771610a5935cd314e7f2b9fa6aba105a` stopped on `target_write_denied` in preflight: zero source writes, zero Update Set attempts and zero captures. The previous current Update Set was preserved. No rollback context was created because no configuration changed. The normal record ACLs deny these edits; no role or ACL was changed to alter that result.

Marcel explicitly approved the additional administrator-maintenance variant, SHA-256 `6fbeab7c5b99bf02c53e886c5c432d1e1806c09645dcd96a11c54a76c6bb2dd9`. It ran once: native history `30e120a993dcd314e7f2b9fa6aba10fd`, rollback context `b0e120a993dcd314e7f2b9fa6aba10fc`. ACL-enforced reads/guards/readback/capture and empty protection-policy checks remained; only the frozen assignments used the approved native administrator database authority. Twelve additional tests covered that boundary and native boolean representation; the pre-run suite had 41 passing offline checks. Roles, ACLs, security properties and business permissions were unchanged.

The first admin run stopped after 67 correct changes at native carriage-return serialization verification. Its later compact completion corrected the parent and created a holding set, then stopped on the native name field's 80-character limit. The separately approved reuse-only continuation completed once: history `363239a593581fd45c8132d47aba103d`, rollback `b63239a593581fd45c8132d47aba103c`. It made one Ledger assignment/capture, three header updates and 136 capture-wrapper moves. All 67 previously correct source rows and the corrected parent remain exactly unchanged, including revisions. All 21 guards, both ES companions and all 68 previous capture payloads are unchanged. The original current Update Set was restored. Root and independent full-column/XML audits exited successfully; [POSTRUN.md](POSTRUN.md) distinguishes current proof from the earlier attempts.

## Runtime acceptance remains open

Engineering owns the current normal Halogen 0.18.22 runtime and its finite measurement windows. Consult `TASK80_FOLLOWUP.md` for the latest handback and ownership; older 0.18.16 lock/memory observations are historical and must not be replayed as startup instructions. Wait for the current hardware-window handback before Voice inference or lifecycle actions. Configuration/capture completion does not release an iPhone test or establish end-to-end Voice readiness.

After actual runtime readiness, verify one harmless structured-output request, then a short phone check for own voice, name/spelling, background noise, interruption and a second call. One genuine ServiceNow sequence must separately establish context consumption, timely progress and the business outcome. Preserve the complete Voice objective recorded in `TASK80_FOLLOWUP.md`.
