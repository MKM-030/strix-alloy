# Native Voice recovery and responsiveness implementation plan

> **For agentic workers:** Use systematic debugging and test-driven development for each demonstrated defect. Keep independently owned changes separate until reviewed together.

**Goal:** Restore the configured own-voice welcome, eliminate the observed conversation error, shorten perceived connection delay, and retain responsive local conversation while ServiceNow alone executes business work, consistently across iPhone, Android and desktop.

**Architecture:** Preserve the native Assistant/Test/SDK entry points, authenticated local adapter and selected Halogen controller. Separate the native introduction from the asynchronous VA bootstrap and its real input-control question; preserve request identities, cancellation and per-call ownership. Determine Voice model authority from native implementation and current records before proposing a separate configuration.

**Tech stack:** ServiceNow AI Voice/AI Agents/OneExtend, Python asyncio/aiohttp/aiortc, local Halogen/CrispASR/own TTS, native browser/SDK clients.

**Spec:** Marcel's 2 November request in this chat plus the full existing Voice objective and `docs/local-voice/RESUME-20261101.md`. The user explicitly requests autonomous investigation, implementation, lifecycle management and self-testing. Physical-device equivalence must not be claimed from a desktop-only result.

## Global constraints

- Keep TTS, STT, conversation model and Agent skill configuration separate.
- Preserve own voice and user programs. Use actual process ownership for lifecycle actions.
- ServiceNow remains the sole business executor; no duplicate or fabricated business action/progress.
- Never replay the completed 69-CU Halogen Agent maintenance or alter the sealed 2.2 delivery.
- Use local inference only. Do not assume an OOTB capability exists merely from its name.
- Bound self-tests and correlate actual native transcript, request and receiving-model evidence.

## Review focus

- Introduction must precede the employee-name question even when an initial topic is configured.
- Early caller input and interruptions must not permit stale welcome/question speech or lose input.
- Cancelling startup must drain the one owned task and release resources for the next call.
- Actual ServiceNow input questions must retain their business request/input-boundary identity.
- Native SDK and WSS clients must share semantics without weakening auth, TURN or admission.

## Evidence before changes

- Current `Dialog.open()` auto-selects the offered SCC topic, clears pre-topic greetings and returns its first question. This behavior dates to Task73, rather than the November Agent delta.
- Native calls currently treat this real question as a greeting, bypassing its input-control binding.
- Actual 2 November calls spend 14,000–29,266ms in `Dialog.open()` before greeting. TTS first chunks then take 47–264ms. Local-dialogue workers start only after that wait and speech.
- Native `VoiceServiceConfigurationSNC._getLLMProvider()` resolves provider through the shared AIA ReAct capability `f6f9e6e71bc38210f4200d81ec4bcb30`. Current local conversation separately bypasses native VoiceLLM.
- A failed morning execution has GenAI error `200000` on a different definition/prompt from the successful Halogen ReAct invocation. Resolve the precise cause before changing its mapping.
- Initial native/bot logs and scoped SDK transcript/execution evidence are preserved privately in `server/.local/voice-repair-20261102/`.

## Task 1: Restore introduction ordering and overlap VA startup

Files: `voice/native-bridge/native_bridge.py` and targeted tests under `tests/voice/` (use actual existing test locations).

- [x] Add and run failing tests using native introduction plus a real offered initial topic/InputText boundary; cover delayed bootstrap, early input, cancellation and second-call isolation.
- [x] Start exactly one owned `Dialog.open()` task, emit the native introduction while it runs, pass that same task to the independent lane and preserve subsequent question source/binding. Keep legacy no-call-settings behavior compatible.
- [x] Run targeted lifecycle/input/output tests and independently review the diff before activation.

## Task 2: Repair the observed native execution error

Files/records: determined from the failed GenAI log, its capability/definition/prompt, transformer and execution-plan transcript.

- [x] Trace the exact failed invocation and its response, including the selected provider/model and expected input/output contract.
- [ ] Reproduce that defect with a bounded harmless test, then make the smallest reviewed correction with rollback and update capture where applicable.
- [ ] Verify the actual execution succeeds through the native path; do not infer success from ReAct's separate successful call.

## Task 3: Preserve independent conversation and identify model authority

Files/records: `native_duplex.py`, conversation transport/selection, native Voice provider source and existing Skill Kit/ACT configuration, as evidence requires.

- [x] Document the actual OOTB shared provider dependency and current independent local conversation path with exact identities.
- [x] Implement any necessary bootstrap readiness gate so local conversation can proceed while business initialization/execution remains owned and asynchronous.
- [ ] Test that caller corrections reach the correct request boundary, with `contextStored`, `inputBoundaryConfirmed`, `promptIncluded`, `ingested` and matching request bindings; keep progress speech source-bound.

## Task 4: Activate and exercise native self-tests

- [x] Review the complete change, preserve active configuration and replace only the exact owned affected adapter generation after proving its old input-free test call was stuck. Other six service generations remain identical; normal venv launcher is required.
- [x] Attempt authenticated native Test Assistant Voice. Its embedded browser has no microphone; ordinary native PKCE and real SDK HTTP/RTC synthetic calls provide the bounded autonomous fallback.
- [ ] Exercise welcome, harmless name/spelling, interruption/noise, clean close and a second call, then one controlled real context/progress sequence. Record timing and observed failures.
- [ ] Verify common SDK/WSS contract coverage and available browser/device variants; state any remaining physical-device evidence honestly.

## Task 5: Consolidate durable evidence

- [x] Update the current Voice runbook/follow-up and related technical documentation with root causes, changes, regression coverage, exact live generation and remaining acceptance.
- [x] Save only owned explicit source/test/document paths in the local repair branch; preserve other Engineering work and original incident evidence. Pending model maintenance and remaining runtime acceptance stay explicitly open.
