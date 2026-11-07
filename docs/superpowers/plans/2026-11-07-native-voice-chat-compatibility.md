# Native Voice Test Chat compatibility

Goal: repair the existing ServiceNow Test Assistant Chat path, so a typed name-clarification dialog can exercise the same authorized ServiceNow Dialog without microphone or a second business implementation. User has explicitly authorized autonomous repairs and opted out of additional design questions.

## Evidence and design

Fresh sys_ux_client_script c73ae446b7323a1081fee3fdde11a97f revision9 opens /text/chat/agent_operator with fixed assistant, instance, language, diagnostics=admin, client_app=admin_test and original OAuth bearer query. Send script099af946b7fe7a1081fee3fdde11a94f revision4 emits user_query/content. Current includeef074e8d0fe48310380dd9e530d1b2df revision8 equals canonical VoiceTestingUIUtils.js after LF normalization: connected/call_sid establishes chatSessionId; metadata carries actual conversation/interaction; static/content displays output; end_call closes. Current local router has no text route. This proves a local compatibility gap. Historical routeother404 cannot be assigned to this path because paths were redacted.

Use a narrow text adapter around existing authorize(with_settings=True) and Dialog. Preserve original caller binding, model readiness and shared WSS/SDK capacity. No NativeCall, Speech, ASR, TTS, TURN or reference download. Emit only actual settings/introduction, Dialog output and metadata. Do not invent analytics, user facts, transcript corrections or approvals. Serialize exact user input once; no uncertain-operation retry. Disconnect cancels owned work and retains capacity until remote cleanup is acknowledged; ordinary application shutdown must drain the same owner. Browser use remains disabled: this repair can be prepared and checked offline, but does not prove live Chat admission or physical audio/device acceptance.

## Implementation plan

1. Agent owns new native_text_chat.py and one focused offline test module in isolated worktree. Establish native connected/static/metadata contract, raw single submission, auth denial, capacity exclusion and disconnect/cleanup with fake Dialogs before acceptance. No inference or live dialog during this stage.
2. Root reviews lifecycle and authentication behavior, integrates only the new route registration and fixed diagnostic route classification in native_bridge.py, and runs the focused integration checks once. Preserve unrelated canonical edits.
3. Document exact remaining limits, reconcile only affected source pins through the existing manifest workflow, and activate through normal idle Native lifecycle only after source/lifecycle review. No model restart or profile change. Do not replay consumed activation helpers.
4. Use the ordinary native Chat UI with an already admitted Voice identity when browser access is available. One bounded dialog exercises uncertain name, correction/spelling and next native question, stopping at any order-approval boundary. Text success is separate from iPhone/Android/desktop acoustic acceptance.
