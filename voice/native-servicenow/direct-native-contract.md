# Direct native orchestration feasibility — read-only evidence

Observed in the signed-in native ServiceNow UI on 2026-10-13. No REST requests were executed and no instance changes were made during this investigation. This is an implementation contract assessment, not proof of a working alternative.

## Result

Native voice JWT authorization is accepted by create_conversation and execute_tool, but the existing agents and store_conversation endpoints require KAA authentication. Therefore the browser's native OAuth token alone does not provide a complete native orchestration lifecycle. Do not weaken those native checks or bypass protected source. Current implementation remains the native UI/media adapter with the existing SCC Bot API backend.

## Execute existing tools

POST `/api/sn_voice_aia/ai_voice_agent/execute_tool`, resource `4a5c3582ff38e6108628ffffffffffac`, `Execute-tool-resource.js`.

- Requires authentication: true. Requires SNC Internal: false. Resource ACL authorization: false.
- Calls validateServiceId then validateServiceAuthorization. JWT claims are verified by native VoiceServiceInfoRequestor, as preserved in VoiceRestUtilsSNC.js.
- JSON body: serviceId, clientApp='admin_test' for the inactive test assistant, toolId, conversationId, agentId, toolParameters.
- `VoiceExecuteToolsSNC` (`ca932354ff4e62108628ffffffffff87`) requires nonempty toolId and conversationId explicitly. toolId is the **agent-tool M2M ID**, not the original sn_aia_tool ID.
- Provide the fixed native agentId `a6337ddf93f787105c8132d47aba1058`. It triggers `gs.hasRightsTo('gen_ai_agent/<internal_name>/execute', null)`; an inaccessible agent returns 403. Omitting agentId would omit this wrapper check and is not an acceptable adapter design.
- The fixed eligible M2Ms are `f1d4319b933b87105c8132d47aba10ff` (read context) and `0ed4b19b933b87105c8132d47aba1030` (confirmed order). They reference the original SCC tool definitions.
- The script calls `new sn_aia.AIAToolExecutor().executeTool(agentToolM2MId, conversationId, toolParameters)`. Tool response override hooks run when applicable.
- Success body passed to setBody is `{tool_response, execution_plan_id?, execution_task_id?, tools_execution_id?}` with status 200; conventional outer result envelope has not been wire-tested. Error statuses: 400 missing required fields, 404 M2M missing, 403 agent rights, 422 tool is_error, 500 caught exception.
- The wrapper shown does not explicitly compare M2M.agent to supplied agentId or bind the conversation to serviceId. The adapter would need to fix service, agent, allowed M2Ms, and the conversation it just created, after agents_authorized membership verification. No inference is made about additional checks in AIAToolExecutor.

## Create native conversation and interaction

POST `/api/sn_voice_aia/ai_voice_agent/create_conversation`, resource `aa417772ff8122108628ffffffffff32`, `Create-conversation-resource.js`. Requires authentication=true, SNC Internal=false, resource ACL=false. Script accepts KAA **or** validateServiceAuthorization, then validates serviceId.

`VoiceConversationManagerSNC` (`07e2f3f2ff8122108628ffffffffff88`) is preserved in full. It uses getConversationConfig(serviceId,testMode), not the full LLM configuration endpoint.

- Body consumed through request.body.nextEntry(): serviceId, clientApp='admin_test', conversationUserId, providerDataBlock; language='de' optional; callerPhoneNumber optional for phone-origin records.
- serviceId and providerDataBlock are explicitly required in the shown source. conversationUserId supplies userId, externalConversationId and clientSessionId internally, so a stable unique value per owned session is needed even though there is no dedicated missing-value check in this method.
- WebRTC validation reads the header named by VoiceAgentConstants.VOICE_SOURCE_HEADER and checks PLATFORM_WEBRTC, MOBILE_WEBRTC or PLATFORM_TEXTCHAT. Exact literal header/value strings remain unverified: the constants Script Include (`a4cf5164efdd22108a03959cfd97d77d`) is Protected and its code is not visible. No guessed values should be sent.
- It internally uses the configured native provider's BotToBot handler to create the conversation and interaction. WebRTC sessions are then elevated to `gs.getUserID()` via the native account utility.
- Direct streamed response is `{result:{conversationId,interactionId?,status?,completed?,...extensionFields}}`; final HTTP status is vaResponse.status. Extensions can adjust the response. Require actual returned IDs, never synthesize native record IDs.

## Configuration and closure blockers

POST `/api/sn_voice_aia/ai_voice_agent/agents`, resource `df018802ffa022102557ffffffffff34`, `Agents-resource.js`, calls isKaaAuthenticated before validateServiceId. Requires authentication, SNC Internal and API ACL. It returns processGetAllAgents(cacheDate,serviceId,callSource,testMode), containing native agent definitions. Native OAuth alone is insufficient. An explicitly approved, pinned demo config snapshot could contain the UI-exported dedicated instructions and exact tools, but would not be dynamic native configuration discovery.

POST `/api/sn_voice_aia/ai_voice_agent/store_conversation`, resource `eab8c63affa422102557ffffffffff42`, `Store-conversation-resource.js`, is also KAA-only with authentication, SNC Internal and API ACL required. Calls VoiceConversationManager.endConversation(payload,headers,response).

The manager's ending payload includes the same serviceId, conversationUserId, providerDataBlock, clientApp plus conversationId, state, transcript, and optional stateReason/summary/cache. End processing closes execution plans, updates interactions, logs usage and wraps up authentication. A proper lifecycle cannot silently omit this step. Exact state enum literals are not verified here. There is no dedicated end_conversation resource among the twelve observed AI voice agent resources; normal closure is store_conversation.

## Remaining evidence gates

No native authenticated wire response, create call, tool call, or closure call was attempted. Header literals and complete KAA-capable lifecycle remain unavailable. A supported KAA integration or explicitly secured platform extension would require a separate design, authorization and testing; it is not part of the deployed routing patch.
