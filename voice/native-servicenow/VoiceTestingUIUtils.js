/**
 * VoiceTestingUIUtils — singleton client script include for the Voice Test Page.
 *
 * Provides shared utilities for both Chat and Voice testing modes.
 * Mode is determined externally by the caller; this script exposes
 * separate chat and voice entry points.
 *
 * --- Architecture ---
 * - Singleton pattern: a single instance is stored on _window._voiceTestingUIUtils
 *   so closure state persists across event invocations.
 * - Mutable refs: api/helpers are updated on each invocation via _updateRefs()
 *   to ensure the singleton always operates on the latest framework references.
 * - UI state flushing is debounced via requestAnimationFrame (flushAnalysisState)
 *   to coalesce rapid WebSocket/DataChannel messages into a single structuredClone.
 *
 * --- Chat Mode (WebSocket) ---
 * - Entry points: handleWebSocketMessage(message, t, websocket),
 *   updateChatAnalysisTabData(message, t, websocket)
 * - handleWebSocketMessage handles connection lifecycle (connected, error,
 *   close_event, metadata, end_call) and routes content messages to the UI.
 * - updateChatAnalysisTabData handles the analysis tab: analytics tool_call
 *   messages trigger HTTP fetches to resolve tool node data; bot responses
 *   are routed to the matching agent node via sequence (from sequenceAgentMap).
 * - Bot responses include timestamp only.
 * - Tool nodes show execution_time_ms when available, otherwise a status label.
 *
 * --- Voice Mode (WebRTC DataChannel) ---
 * - Entry points: updateVoiceAnalysisTabData(event, parsedData, t, webrtc),
 *   handleDataChannelMessage(parsedData, allMessages, t, webrtc)
 * - Messages arrive via RTCDataChannel (transcripts, analytics).
 * - Uses diagnostics=admin: orchestrator enriches transcript messages with
 *   latency_ms, caller_turn_id, turn_num.
 * - Bot responses are routed to the correct agent node via caller_turn_id (from sequenceAgentMap).
 * - Bot responses show timestamp + latency_ms from the transcript payload.
 * - Perf analytics (perceived_latency, processed_latency, stt_latency, tts_latency)
 *   are ignored; latency is sourced from the transcript payload's latency_ms field.
 * - Tool nodes show execution_time_ms (latency).
 *
 * --- Shared Helpers ---
 * - ensureNoAgentNode: creates/finds the "Voice Assistant" parent
 * - findOrCreateAgentNode: creates/finds an agent parent node (returns {node, created})
 * - upsertToolNode: creates or updates a tool child node under an agent
 * - createBotResponseNode: builds a bot response tree item
 * - createContentTreeItem: builds a generic tree item (tool, etc.)
 * - flushAnalysisState: debounced setState for repeaterItems + sequenceAgentMap
 * - addChatMessage: emits a SAVE_MESSAGE event for chat-mode messages
 * - markAnalysisComplete: marks all analysis tree nodes as completed (called on disconnect)
 *
 * --- Connection Management ---
 * - disconnectChat: closes WebSocket, clears timer, resets chat state
 * - disconnectVoice: closes RTCPeerConnection, stops media tracks, clears timer
 * - startCallTimer: starts an interval-based call duration timer (exposed on instance)
 */
function include({ imports }, _inApi, _inHelpers) {
    // Singleton: reuse existing instance so closure state (e.g. _currentVoiceSequence) persists across events
    var _window = getWindowObject();
    if (_window._voiceTestingUIUtils) {
        _window._voiceTestingUIUtils._updateRefs(_inApi, _inHelpers);
        return _window._voiceTestingUIUtils;
    }

    const {
        NowDateTime
    } = imports['sn_uxf.core_libraries']();

    // Mutable refs so the singleton always uses the latest api/helpers from each event invocation
    let api = _inApi;
    let helpers = _inHelpers;
    let _flushScheduled = false;
    let _currentVoiceAgentId = null;

    // Analytics event types to ignore (built once, not per-message)
    const IGNORED_CHAT_EVENTS = new Set(["llm_prompt_call", "wait_message", "perceived_latency", "metadata"]);
    const IGNORED_VOICE_EVENTS = new Set(["llm_prompt_call", "wait_message", "processed_latency", "metadata"]);

    function _updateRefs(newApi, newHelpers) {
        api = newApi;
        helpers = newHelpers;
    }

    const handleDataChannelMessage = (parsedData, allMessages, t, webrtc) => {
        try {
            const message = parsedData;
            if (webrtc.debug)
                console.log(`[DataChannel] Received: ${JSON.stringify(message)}`);

            // Handle different message types
            switch (message.type) {
                case "metadata":
                    api.setState("conversationId", message.data.conversation_id);
                    api.setState("interactionId", message.data.interaction_id);
                    _currentVoiceAgentId = null;
                    break;
                case "agent-name":
                    if (webrtc.debug)
                        console.log(`[Metadata] agentName: ${message.data.agent_name}`);
                    break;
                case "transcript":
                    displayTranscript(message, allMessages, t, webrtc);
                    break;
                case "error":
                    handleServerError(message, webrtc);
                    break;
                default:
                    if (webrtc.debug)
                        console.log(`[DataChannel] Unknown message type: ${message.type}`);
                    break;
            }
        } catch (e) {
            // Not JSON, log as plain text
            if (webrtc.debug)
                console.log(`[DataChannel] Received (raw): ${parsedData}`);
        }
    }

    const displayTranscript = (message, allMessages, t, webrtc) => {
        message.data.t = t || NowDateTime(+new Date()).format(api.context.session.user.timeFormat);
        allMessages.push(message);
        api.setState("messages", allMessages);
        if (webrtc.debug)
            console.log(`[Transcript] ${JSON.stringify(message)}`);
    }

    const handleServerError = (message, webrtc) => {
        const errorMessage = message.data?.message || "Unknown server error";
        const errorCode = message.data?.code || "UNKNOWN";

        if (webrtc.debug)
            console.error(`[Server Error] ${errorCode}: ${errorMessage}`);

        // Close signaling WebSocket — server cleans up session on WS close
        if (webrtc.signalingWs) {
            webrtc.signalingWs.close();
            webrtc.signalingWs = null;
        }
    }

    const handleWebSocketMessage = async (message, t, websocket) => {
        if (websocket.debug)
            console.log(`Received: ${message.type}`);

        switch (message.type) {
            case "connected":
                api.setState("chatSessionId", message.call_sid);
                api.setState("chatCallSid", message.call_sid);
                api.setState("callStarted", true);
                api.setState("sequenceAgentMap", {});
                startCallTimer();
                break;

            case "error":
            case "close_event":
                if (websocket.debug)
                    console.log(`Error: ${message.message || message.reason}`);

                api.emit('NOW_UXF_PAGE#ADD_NOTIFICATIONS', {
                    items: [{
                        id: 'error_message_received',
                        status: 'critical',
                        icon: 'exclamation-triangle-outline',
                        content: {
                            type: "html",
                            value: await helpers.translate("Error occurred. Try again later.")
                        },
                        action: {
                            type: 'dismiss'
                        }
                    }]
                });
                break;

            case "metadata":
                api.setState("interactionId", message.metadata.interaction_id);
                api.setState("conversationId", message.metadata.conversation_id);
                break;

            case "end_call":
                addChatMessage("assistant", t, "Session ended by orchestrator");
                if (websocket.debug)
                    console.log("Session ended by orchestrator");
                disconnectChat(websocket);
                break;

            default:
                if (websocket.debug)
                    console.log("Message content: ", message.content);

                // Agent response or other message
                if (message.content) {
                    addChatMessage("assistant", t, message.content, message);
                }
                break;
        }
    }

    function addChatMessage(sender, t, content, message) {
        api.emit("SAVE_MESSAGE", {
            "sender": sender,
            "message": { msg: content, t: t, message_id: message?.message_id || null }
        });
    }

    function formatDuration(ms) {
        const seconds = ms / 1000;  // keep full decimal
        const minutes = Math.floor(seconds / 60);
        const hours = Math.floor(minutes / 60);
        const days = Math.floor(hours / 24);

        if (days > 0) return `${days} day${days !== 1 ? 's' : ''}`;
        if (hours > 0) return `${hours} hour${hours !== 1 ? 's' : ''}`;
        if (minutes > 0) return `${minutes} minute${minutes !== 1 ? 's' : ''}`;

        const label = seconds === 1 ? 'second' : 'seconds';
        return `${parseFloat(seconds.toFixed(2))} ${label}`;
    }

    function fmtTimestamp(timestamp) {
        return NowDateTime(timestamp).format(api.context.session.user.timeFormat);
    }

    function addTimestampNode(timestamp) {
        return {
            label: fmtTimestamp(timestamp),
            color: "positive",
            variant: "tertiary",
            icon: ""
        };
    }

    function addDurationNode(duration) {
        return {
            label: formatDuration(duration),
            color: getStatusColor('latency'),
            variant: "tertiary",
            icon: "clock-outline"
        };
    }

    function createToolDetailNodes(taskId, taskData, toolExeData) {
        const nodes = [];

        // Parse inputs from task.metadata.inputs
        const metadataSrc = taskData?.metadata;
        try {
            const metadata = typeof metadataSrc === 'string' ? JSON.parse(metadataSrc) : (metadataSrc || {});
            const inputs = metadata.inputs || [];
            const inputChildren = inputs.map((input, idx) => {
                const props = [];
                const displayName = input.label || input.name;
                if (displayName) props.push({ sublabel: `${api.state.translations.nameLabel}: ${displayName}`, id: `input_name_${idx}`, children: [] });
                if (input.description) props.push({ sublabel: `${api.state.translations.descriptionLabel}: ${input.description}`, id: `input_desc_${idx}`, children: [] });
                if (input.value !== undefined) props.push({ sublabel: `${api.state.translations.valueLabel}: ${input.value}`, id: `input_val_${idx}`, children: [] });
                return {
                    id: `input_${idx}_${input.name || idx}`,
                    label: input.name || `${api.state.translations.inputLabel} ${idx}`,
                    children: props
                };
            });
            nodes.push({
                id: `tool_inputs_${taskId}`,
                label: `${api.state.translations.inputsLabel} (${inputs.length})`,
                children: inputChildren
            });
        } catch (e) {
            nodes.push({ id: `tool_inputs_${taskId}`, label: `${api.state.translations.inputsLabel} (0)`, children: [] });
        }

        // Parse outputs from tools_execution fields
        const outputChildren = [];
        if (toolExeData?.request) {
            outputChildren.push({ id: `tool_output_request_${taskId}`, label: api.state.translations.requestLabel, children: [{ sublabel: toolExeData.request, id: `tool_output_request_val_${taskId}`, children: [] }] });
        }
        if (toolExeData?.execution_mode) {
            outputChildren.push({ id: `tool_output_mode_${taskId}`, label: api.state.translations.executionModeLabel, children: [{ sublabel: toolExeData.execution_mode, id: `tool_output_mode_val_${taskId}`, children: [] }] });
        }
        if (toolExeData?.execution_plan_id) {
            outputChildren.push({ id: `tool_output_exe_plan_ref_${taskId}`, label: api.state.translations.executionPlanLabel, children: [{ sublabel: toolExeData.execution_plan_id.value, id: `tool_output_exe_plan_ref_val_${taskId}`, children: [] }] });
        }
        if (taskId) {
            outputChildren.push({ id: `tool_output_exe_task_ref_${taskId}`, label: api.state.translations.executionTaskLabel, children: [{ sublabel: taskId, id: `tool_output_exe_task_ref_val_${taskId}`, children: [] }] });
        }
        nodes.push({
            id: `tool_outputs_${taskId}`,
            label: `${api.state.translations.outputsLabel} (${outputChildren.length})`,
            children: outputChildren
        });

        return nodes;
    }

    function updateToolDetailNodes(toolNode, taskId, taskData, toolExeData) {
        const freshNodes = createToolDetailNodes(taskId, taskData, toolExeData);

        freshNodes.forEach(freshNode => {
            const existingIdx = toolNode.children.findIndex(c => c.id === freshNode.id);
            if (existingIdx > -1) {
                // Replace existing Inputs/Outputs node with updated data
                toolNode.children[existingIdx] = freshNode;
            } else {
                toolNode.children.push(freshNode);
            }
        });
    }

    function createBotResponseNode(messageId, callerTurnId, agentId, content, timestamp, latencyMs) {
        const highlightedValueProps = [];
        if (timestamp) highlightedValueProps.push(addTimestampNode(timestamp));
        if (latencyMs != null) highlightedValueProps.push(addDurationNode(latencyMs));
        return {
            id: `bot_response_${messageId}`,
            label: api.state.translations.botResponseLabel,
            icon: "circle-check-outline",
            // data-caller-turn-id stored as a property so perf annotation can find nodes by turn
            callerTurnId,
            children: [{ id: `message_${messageId}`, sublabel: content, children: [] }],
            highlightedValueProps
        };
    }

    function ensureNoAgentNode(repeaterItems) {
        let idx = findParent(repeaterItems, "parent-no-agent");
        if (idx === -1) {
            repeaterItems.push({
                tree: {
                    id: "parent-no-agent",
                    label: api.state.translations.voiceAssistantLabel,
                    caption: "",
                    icon: "sync-outline",
                    children: [],
                    highlightedValueProps: [{
                        label: api.state.translations.ongoingLabel,
                        color: getStatusColor('ongoing'),
                        variant: "tertiary",
                        icon: "sync-outline"
                    }],
                    showSpinner: true
                }
            });
            idx = repeaterItems.length - 1;
        }
        return repeaterItems[idx];
    }

    function upsertToolNode(agentNode, taskId, taskData, toolExeData) {
        const toolMetadata = typeof taskData.metadata === 'string' ? JSON.parse(taskData.metadata) : (taskData.metadata || {});
        const toolName = toolMetadata.name || taskData.description;
        const existingToolIdx = findChild(agentNode.tree.children, `childItem_${taskId}`);
        if (existingToolIdx === -1) {
            const toolLabel = `Tool - ${capitalizeFirstLetter(toolName)}`;
            agentNode.tree.children.push(
                createContentTreeItem(toolLabel, `childItem_${taskId}`, "wrench-outline", createToolDetailNodes(taskId, taskData, toolExeData), "success", toolExeData.execution_time_ms)
            );
        } else {
            updateToolDetailNodes(agentNode.tree.children[existingToolIdx], taskId, taskData, toolExeData);
        }
    }

    function findOrCreateAgentNode(repeaterItems, agentId, agentName) {
        const idx = findParent(repeaterItems, `parent-agent-${agentId}`);
        if (idx > -1) return { node: repeaterItems[idx], created: false };
        const node = {
            tree: {
                id: `parent-agent-${agentId}`,
                label: agentName,
                caption: api.state.translations.aiVoiceAgent,
                icon: "sync-outline",
                children: [],
                highlightedValueProps: [{
                    label: api.state.translations.ongoingLabel,
                    color: getStatusColor('ongoing'),
                    variant: "tertiary",
                    icon: "sync-outline"
                }],
                showSpinner: true
            }
        };
        repeaterItems.push(node);
        return { node, created: true };
    }

    function flushAnalysisState(repeaterItems, sequenceAgentMap) {
        api.setState("sequenceAgentMap", sequenceAgentMap);
        if (!_flushScheduled) {
            _flushScheduled = true;
            _window.requestAnimationFrame(() => {
                _flushScheduled = false;
                const snap = api.state.repeaterItems;
                api.setState("repeaterItems", structuredClone(snap));
            });
        }
    }

    const snGet = (url) => helpers.snHttp(url, { method: 'GET', body: {} });

    // Fetch the agent, execution task, and tools execution records for a tool_call event.
    // Returns { agentData, taskData, toolExeData }; throws if any request fails.
    async function fetchToolCallData(agentId, taskId, toolExeId) {
        const [agent, exTask, toolExe] = await Promise.all([
            snGet(`/api/now/table/sn_aia_agent/${agentId}`),
            snGet(`/api/now/table/sn_aia_execution_task/${taskId}`),
            snGet(`/api/now/table/sn_aia_tools_execution/${toolExeId}`)
        ]);
        return {
            agentData: agent.response.result,
            taskData: exTask.response.result,
            toolExeData: toolExe.response.result
        };
    }

    async function updateChatAnalysisTabData(message, t, websocket) {
        const repeaterItems = api.state.repeaterItems;
        const sequenceAgentMap = api.state.sequenceAgentMap;
        // Handle perf / llm Activity detection messages – annotate matching bot response with timestamp/duration
        const isPerfMsg = message.type === "analytics" && message.data?.category === "perf";
        const isLlmActivityMsg = message.type === "analytics" && message.data?.event_type === "llm_prompt_call" && message.data?.capability === "Activity detection";
        if (isPerfMsg || isLlmActivityMsg) {
            flushAnalysisState(repeaterItems, sequenceAgentMap);
            return;
        }

        if (IGNORED_CHAT_EVENTS.has(message.data?.event_type) || IGNORED_CHAT_EVENTS.has(message.data?.type)) return;

        const parentNode = ensureNoAgentNode(repeaterItems);

        if (message.type === "analytics" && message.data?.event_type === "tool_call") {
            const { agent_id, tool_id, execution_task_id: task_id, tools_execution_id: tool_exe_id } = message.data.metadata;

            // Register mapping and create agent node BEFORE async fetches so that
            // bot responses arriving while we await land under the correct agent bucket.
            // Keyed by sequence: chat bot responses arrive as "static" messages, whose only
            // shared turn identifier with this event is `sequence` (they carry no caller_turn_id).
            sequenceAgentMap[message.data.sequence] = { agent_id, tool_id, task_id, tool_exe_id };
            findOrCreateAgentNode(repeaterItems, agent_id, message.data.capability);

            let agentData, taskData, toolExeData;
            try {
                ({ agentData, taskData, toolExeData } = await fetchToolCallData(agent_id, task_id, tool_exe_id));
            } catch (e) {
                if (websocket.debug)
                    console.error(`[Chat] tool_call HTTP fetch failed for sequence=${message.data.sequence}:`, e);
                flushAnalysisState(api.state.repeaterItems, api.state.sequenceAgentMap);
                return;
            }

            // Re-read state after await — structuredClone in flushAnalysisState may have replaced the reference
            const freshRepeaterItems = api.state.repeaterItems;
            ensureNoAgentNode(freshRepeaterItems);

            const { node: agentNode } = findOrCreateAgentNode(freshRepeaterItems, agent_id, agentData.name);
            upsertToolNode(agentNode, task_id, taskData, toolExeData);

            flushAnalysisState(freshRepeaterItems, api.state.sequenceAgentMap);
            return;
        }

        // Bot response — sourced from the "static" message (top-level content), routed to the
        // correct agent node via the sequence mapping registered by the tool_call handler.
        if (message.content) {
            const messageId = message?.message_id;
            const sequence = message?.sequence;
            const mapped = sequence ? sequenceAgentMap[sequence] : null;
            const agentId = mapped?.agent_id;
            let targetNode;
            if (agentId) {
                const agentIdx = findParent(repeaterItems, `parent-agent-${agentId}`);
                if (agentIdx > -1) targetNode = repeaterItems[agentIdx];
            }
            if (!targetNode) targetNode = ensureNoAgentNode(repeaterItems);
            targetNode.tree.children.push(
                createBotResponseNode(messageId, null, agentId || "no_agent", message.content, t)
            );
        }

        flushAnalysisState(repeaterItems, sequenceAgentMap);
    }

    async function updateVoiceAnalysisTabData(event, parsedData, t, webrtc) {
        const message = parsedData;
        const repeaterItems = api.state.repeaterItems;
        const sequenceAgentMap = api.state.sequenceAgentMap;

        // Perf analytics events (perceived_latency, processed_latency, stt_latency, tts_latency)
        // are ignored — bot response nodes already carry latency_ms from the transcript payload.
        if (message.type === "analytics" && message.data?.category === "perf") {
            return;
        }

        // Handle tool_call analytics messages
        if (message.type === "analytics" && message.data?.event_type === "tool_call") {
            const { agent_id, tool_id, execution_task_id: task_id, tools_execution_id: tool_exe_id } = message.data.metadata;
            const callerTurnId = message.data.caller_turn_id;

            // Register mapping keyed by caller_turn_id and create agent node BEFORE async fetches
            // so that transcript messages arriving while we await land under the correct agent bucket.
            sequenceAgentMap[callerTurnId] = { agent_id, tool_id, task_id, tool_exe_id };
            _currentVoiceAgentId = agent_id;
            api.setState("currentVoiceAgentId", agent_id);
            findOrCreateAgentNode(repeaterItems, agent_id, message.data.capability);

            let agentData, taskData, toolExeData;
            try {
                ({ agentData, taskData, toolExeData } = await fetchToolCallData(agent_id, task_id, tool_exe_id));
            } catch (e) {
                 flushAnalysisState(api.state.repeaterItems, api.state.sequenceAgentMap);
                return;
            }

            // Re-read state after await — other message handlers may have run during the HTTP
            // fetches and replaced api.state.repeaterItems with a structuredClone, making the
            // local `repeaterItems` reference stale. Without this, upsertToolNode mutates the
            // stale array and the tool node is never reflected in the UI.
            const freshRepeaterItems = api.state.repeaterItems;
            const freshSequenceAgentMap = api.state.sequenceAgentMap;

            const { node: agentNode } = findOrCreateAgentNode(freshRepeaterItems, agent_id, agentData.name);
            upsertToolNode(agentNode, task_id, taskData, toolExeData);

            flushAnalysisState(freshRepeaterItems, freshSequenceAgentMap);
            return;
        }

        // Ignore non-relevant analytics messages
        if (IGNORED_VOICE_EVENTS.has(message.data?.event_type) || IGNORED_VOICE_EVENTS.has(message.data?.type)) return;

        // For transcript messages: route bot responses to the correct agent node via caller_turn_id.
        if (message.type === "transcript" && message.data?.role === "assistant") {
            const content = message.data?.content || message.content;
            if (!content) {
                flushAnalysisState(repeaterItems, sequenceAgentMap);
                return;
            }
            const callerTurnId = message.data.caller_turn_id;
            const messageId = message.data.message_id;
            const latencyMs = message.data?.latency_ms ?? null;

            // Look up which agent node owns this caller turn; fall back to the current voice agent
            const mapped = callerTurnId != null ? sequenceAgentMap[callerTurnId] : null;
            const agentId = mapped?.agent_id || _currentVoiceAgentId;
            let parentNode;
            if (agentId) {
                const agentIdx = findParent(repeaterItems, `parent-agent-${agentId}`);
                if (agentIdx > -1) parentNode = repeaterItems[agentIdx];
            }
            if (!parentNode) parentNode = ensureNoAgentNode(repeaterItems);

            parentNode.tree.children.push(
                createBotResponseNode(messageId, callerTurnId, agentId || "no_agent", content, t, latencyMs)
            );
        }
        flushAnalysisState(repeaterItems, sequenceAgentMap);
    }

    function findParent(tree, nodeId) {
        return tree.findIndex(item => item.tree.id.includes(nodeId));
    }

    function findChild(tree, nodeId) {
        return tree.findIndex(item => item.id.includes(nodeId));
    }

    function capitalizeFirstLetter(str) {
        return (str && str.length > 0) ? str[0].toUpperCase() + str.slice(1) : '';
    }

    function startCallTimer() {
        // Clear any existing timer to prevent orphaned intervals when switching modes
        helpers.timing.clearInterval(api.state.timerIntervalId);
        let elapsedTime = 0;
        let startTime = Date.now() - elapsedTime;
        let intervalId = helpers.timing.setInterval(function () {
            elapsedTime = Date.now() - startTime;
            const totalSeconds = Math.floor(elapsedTime / 1000);
            const minutes = Math.floor(totalSeconds / 60);
            const seconds = totalSeconds % 60;

            api.setState("timer", `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`);
        }, 1000);
        api.setState("timerIntervalId", intervalId);
    }

    function getStatusColor(status) {
        switch (status) {
            case 'latency':
                return 'blue';
            default:
                return 'positive';
        }
    }

    function createContentTreeItem(label, id, iconDefault, children, status, durationMs) {
        status = status == "log" ? "success" : status?.toLowerCase();
        const statusColor = getStatusColor(status);
        let icon = iconDefault;
        let completedLabel = api.state.translations.completedLabel;
        switch (status) {
            case "success": icon = "circle-check-outline"; break;
            case "ongoing": icon = "sync-outline"; break;
            case "cancelled": icon = "circle-stop-outline"; break;
            default: icon = "clock-outline"; break;
        }
        const highlightedValueProps = (durationMs)
            ? [addDurationNode(durationMs)]
            : [{
                "label": status === "success" ? completedLabel : capitalizeFirstLetter(status),
                "color": statusColor,
                "variant": statusColor === "orange" ? "secondary" : "tertiary",
                "icon": icon
            }];
        return {
            id: id,
            label: capitalizeFirstLetter(label),
            icon: icon,
            children: children,
            highlightedValueProps
        };
    }

    function disconnectChat(websocket) {
        if (api.state.pollingIntervalId) {
            helpers.timing.clearInterval(api.state.pollingIntervalId);
            api.setState("pollingIntervalId", 0);
        }
        helpers.timing.clearInterval(api.state.timerIntervalId);
        if (websocket) {
            if (websocket.debug)
                console.log("Closing WebSocket connection...");
            if (websocket.ws) {
                websocket.ws.close();
                websocket.ws = null;
            }
        }

        api.setState("sessionId", "");
        api.setState("chatCallSid", "");
        api.setState("chatConnected", false);
        api.setState("callStarted", false);
        api.setState("timer", "-");
        api.setState("timerIntervalId", 0);

        markAnalysisComplete();
    }

    function disconnectVoice(window, webrtc) {
        // Send disconnect signal then close signaling WebSocket
        if (webrtc.signalingWs) {
            if (webrtc.signalingWs.readyState === window.WebSocket.OPEN) {
                try {
                    webrtc.signalingWs.send(JSON.stringify({ type: "disconnect" }));
                } catch (e) { /* ignore send errors during teardown */ }
            }
            webrtc.signalingWs.close();
            webrtc.signalingWs = null;
        }
        helpers.timing.clearInterval(api.state.timerIntervalId);

        if (webrtc.localStream) {
            webrtc.localStream.getTracks().forEach(track => track.stop());
            webrtc.localStream = null;
        }
        if (webrtc.pc) {
            webrtc.pc.onicecandidate = null;
            webrtc.pc.oniceconnectionstatechange = null;
            webrtc.pc.onicecandidateerror = null;
            webrtc.pc.ontrack = null;
            webrtc.pc.close();
            webrtc.pc = null;
        }
        if (webrtc.audioContext) {
            webrtc.audioContext.close();
            webrtc.audioContext = null;
        }
        webrtc.isConnected = false;

        var audio = window.document.getElementById("webrtc-audio");
        if (audio) {
            audio.srcObject = null;
        }

        api.setState("callStarted", false);
        api.setState("activeInteractionId", "");
        api.setState("timer", "-");
        api.setState("timerIntervalId", 0);

        markAnalysisComplete();
    }

    function markAnalysisComplete() {
        const repeaterItems = api.state.repeaterItems;
        for (const item of repeaterItems) {
            item.tree.highlightedValueProps = [{
                label: api.state.translations.completedLabel,
                color: getStatusColor('completed'),
                variant: "tertiary",
                icon: "circle-check-outline"
            }];
            item.tree.icon = "circle-check-outline";
            item.tree.showSpinner = false;
        }
        api.setState("repeaterItems", structuredClone(repeaterItems));
    }

    function getWindowObject() {
        var fnConstr = (function () { }).constructor;
        return fnConstr('return this')();
    }

    const _instance = {
        _updateRefs,
        getWindowObject,
        handleDataChannelMessage,
        handleWebSocketMessage,
        updateChatAnalysisTabData,
        updateVoiceAnalysisTabData,
        addChatMessage,
        markAnalysisComplete,
        disconnectVoice,
        disconnectChat,
        startCallTimer
    };
    _window._voiceTestingUIUtils = _instance;
    return _instance;
}