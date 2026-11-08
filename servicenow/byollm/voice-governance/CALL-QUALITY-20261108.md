# Voice call quality — 8 November 2026

Analyzed call `6b6af2413cff`, ServiceNow conversation `0876b93f9318df94e7f2b9fa6aba10de`. Host log interval: approximately 20:55–21:01 Europe/Berlin. The conversation completed; the final END was acknowledged at 21:01:06. No business request should be replayed.

## Measured delays

| Stage | Observed time | Interpretation |
| --- | ---: | --- |
| First greeting PCM after dialog open began | 0.506 s | Server audio emission, not a phone playback acknowledgement |
| Native ServiceNow startup to first input boundary | 37.735 s | Three caller inputs accumulated during startup |
| Two sequential startup planner calls | 14.343 s + 11.001 s | First selected the laptop agent; second asked for the employee name |
| Recognizer, ten utterances | Median 0.6715 s; range 0.282–2.047 s | Recognition quality was poor, but this was not the main processing delay |
| Speech endpoint silence | Approximately 1.2 s | Lowering this without acoustic evidence could split spelling further |
| Native response intervals | 8.733–43.671 s | Repeated serial runs accumulated a substantial backlog |
| TTS first chunk, after greeting | Median 0.063 s; range 0.047–0.172 s | Fast synthesis startup; greeting separately about 0.5 s |

The year/name correction was recognized at 20:57:35.130. A native reply followed at 20:59:03.129, and the order summary at 20:59:19.600. These are host times. ServiceNow/inner-engine clocks differ by approximately 118 seconds; timestamps from different clocks must not be subtracted directly. Gateway/controller duration differences are estimates of queue plus overhead, not isolated queue measurements.

## Proven faults

1. **Serial backlog:** distinct raw caller fragments were queued and each produced a separate ServiceNow message, even when several were already available before the first open question.
2. **Context overtook input:** newer raw corrections were published through the optional context path before their original queued messages were sent. ServiceNow could therefore ask about the newer year and then receive an older factual utterance as the answer to that newer confirmation. Classifier log `c3f675fb…` demonstrates the mismatch. A context acknowledgement did not retire the original queued input.
3. **Wrong spelling data type:** the final suffix correction reached ServiceNow. InputCollector log `4487b97f93941b985c8132d47aba1004` collected only `name_confirmation:boolean`, interpreted the correction as `true`, and returned to the agent. Planner log `b787f1bf93941b985c8132d47aba10dc` then repeated the old spelling in the order summary. The handoff itself worked; the interpretation was wrong.

No order approval was supplied by the user in this transcript. A successful order is not claimed.

## Repair scope

The Bridge repair groups compatible, already queued originals at an authoritative open text question into a single ordered message. It preserves the individual transcript entries and original strings, adds no waiting timer, and does not group Boolean, selection or confirmation responses. Different language/context, owner or question bindings remain separate. Newer unsent raw inputs must not also be published into the running agent's context. A pre-question input must not answer a later confirmation.

The ServiceNow repair belongs to the existing active **SCC Laptop Onboarding** agent, not the unused legacy Voice agent. Unresolved spelling uses the native plain-text input contract (`FALLBACK`, `collect_input_from_user`, `Datatypes=[]`, `last_objective=false`). Explicit spelling amendments are corrections, even if an input classifier returns Boolean true. The current original utterance and the actual resolved spelling remain authoritative. The separate order approval, authorized manager lookup and no-retry rules remain.

The agent's Description, the update-set Description and the Customer Update's native **Comments** field document the purpose. `sys_update_xml` has no Description column on this instance. No new column is needed. Exact installation and activation receipts are recorded in the continuation document.

ServiceNow installation is independently verified: agent `a4a9438393738354e7f2b9fa6aba101d`, revision **18**, instructions SHA-256 `53498339d8364b36b50e29696ab9ef179c296c4cc8d747d2b87db61e686c207b`. The revised instructions are 7,899 characters, within the declared 8,000-character field capacity; the previous value had 8,475 characters. Manager lookup, separate approval and submission/result rules are byte-identical. Capture `1e68435293981754e7f2b9fa6aba1023` remains in the existing owning-application update set `f06f27f1939cd3185c8132d47aba1087` (**SCC Voice Welcome Repair 2026-11-03**). Its payload and explanatory comments match the installed artifact.

The initially created empty set `788bfdb79398df94e7f2b9fa6aba10aa` was assigned to Global by the platform. Its application field was not writable. No agent change occurred in either preparatory attempt. The final operation used the existing correct application set; the empty preparation set was documented and marked ignored. No scope/security restriction was bypassed. All three execution attempts are consumed and must not be replayed.

The final native execution envelope reports the pre-existing business-rule error `The undefined value has no properties.` Rule `f7c8f9e6430022101dbab69d4bb8f20c` accesses `current.active` during the agent update. The operation receipt, independent agent/CU readback and native cache-flush log confirm the intended metadata changes; the error is not treated as a reason to repeat the update. Its broader search-signal effect is not resolved by this repair. Execution history: `864c7d7793181b985c8132d47aba10f0`; rollback context: `0a4c7d7793181b985c8132d47aba10ee`.

## Recognition and remaining limits

The native Qwen3-ASR 0.6B path supports configured language and ServiceNow key terms through the native decoder. No silent-drop defect was found. No original audio for this call was retained, so the wrong surname/year cannot be attributed to quantization, microphone quality or endpointing from this transcript alone. Existing `segments=0` diagnostics mean segment metadata was not returned by this adapter; they are not proof of an empty recognition result or high confidence.

The cached F16 recognizer is not acoustically or operationally qualified. It was not selected, loaded or downloaded. The selected Halogen generation, own TTS voice, central settings and memory reserve are preserved.

The startup still contains two expensive native planner calls with approximately 50k and 62k prompt characters. Streamlining that native route needs a separate measured configuration change; this repair does not claim to eliminate that cost. New phone evidence is still required to quantify the latency improvement and verify natural spelling recovery. Source regressions and configuration readback do not prove acoustic or cross-device acceptance.

## Activation and validation

The source is active in Native PID **13704**, launcher **26808**, from approximately 21:28 local time. Only idle Native was replaced. The selected Halogen, Bot, gateway, ASR, own TTS and configuration identities were compared before and after and preserved. The activation helper initially omitted the HTTP status from its health callback, so it reported failure after the new process had already started correctly. Read-only verification of that same process confirmed HTTP 200 and completed its ownership receipt; no second restart occurred.

Eleven focused offline input-sequencing regressions passed in 0.175 seconds after the final source change. They cover exact raw batching, the future-context race, stale factual inputs at later controls, delayed recognition, uncertain delivery without replay and late optional replies that otherwise displace a native question. The relevant existing control/context checks were also exercised by the implementation agent. The normal deployment preflight passed using the installed runtime interpreter. No live-model prompt loop or automated order was run.

Public `/scc-native/health` returned HTTP 200 in **0.375 s** at **2026-11-08 20:30:31 UTC**, with model and ASR ready. This is availability evidence, not a measured new conversation latency. The prior call was not replayed. Full phone, spelling and cross-device acceptance remain open.

Private evidence: `server/.local/voice-repair-20261102/task100-call-quality-20261108/`. It contains exact native/ServiceNow excerpts, scoped SDK snapshots, timing data, source preimages and operation receipts. Private transcript data is not copied into this report.
