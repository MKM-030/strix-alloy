var VoiceConversationUtilsSNC = Class.create();
VoiceConversationUtilsSNC.prototype = {
    initialize: function() {},

    /**
     * Retrieves the interaction record associated with a conversation.
     * Returns undefined when no record is found — callers must null-check.
     * Logs at debug level only, because absence is valid on guest calls and
     * the fallback to sys_cs_conversation is expected (see _getRelatedTask).
     * Callers that treat absence as a real error should log gs.error themselves.
     *
     * @param {string} conversationId - The ID of the conversation to look up
     * @returns {GlideRecord|undefined} - The interaction record if found, undefined otherwise
     */
    getInteractionFromConversation: function(conversationId) {
        const interaction = new GlideRecord('interaction');
        if (interaction.get('channel_metadata_document', conversationId))
            return interaction;
        gs.debug('VoiceConversationUtilsSNC.getInteractionFromConversation: Interaction not found for conversationId={0}', [conversationId]);
    },

    /**
     * Formats a transcript array into a readable string format
     *
     * @typedef {Object} TranscriptEntry
     * @property {boolean} isBotMessage - Whether the message is from the bot
     * @property {string} value - The message content
     * @property {string} displayName - The name of the sender
     * @property {string} type - The message type (e.g., "text")
     * @property {number} [timestamp] - Optional timestamp in milliseconds
     *
     * @param {Array<TranscriptEntry>} transcript - Array of transcript entries
     * @example
     * const transcript = [
     *     {
     *         "isBotMessage": true,
     *         "value": "How can I help you?",
     *         "displayName": "Bot",
     * @property {string} type - The message type (e.g., "text")
     *     },
     *     {
     *         "isBotMessage": false,
     *         "value": "Can you tell me about the PTO policy?",
     *         "displayName": "User",
     *         "type": "text"
     *     }
     * ];
     * const formatted = formatTranscript(transcript);
     * // Returns: "[HH:MM] Bot: How can I help you?\n[HH:MM] User: Can you tell me about the PTO policy?"
     *
     * @returns {string} - Formatted transcript string with timestamps and display names
     */
    formatTranscript: function(transcript) {
        return transcript.map(entry => {
            // Use current time if no timestamp is provided
            const date = entry.timestamp ?
                new Date(parseInt(entry.timestamp)) :
                new Date();

            const hours = date.getHours().toString().padStart(2, '0');
            const minutes = date.getMinutes().toString().padStart(2, '0');
            const formattedTime = `[${hours}:${minutes}]`;

            return `${formattedTime} ${entry.displayName}: ${entry.value}`;
        }).join('\n');
    },

    /**
     * Retrieves the provider user ID from a conversation
     *
     * @param {string} conversationId - The ID of the conversation
     * @returns {string|null} - The provider user ID if found, null otherwise
     */
    getProviderUserId: function(conversationId) {
        const conversation = new GlideRecord('sys_cs_conversation');
        if (conversation.get(conversationId)) {
            return conversation?.consumer_account?.channel_user_profile?.channel_user_id;
        }
        return null;
    },

    /**
     * Retrieves the execution plan record for a conversation
     *
     * @param {string} conversationId - The ID of the conversation
     * @returns {GlideRecord|null} - The execution plan record if found, null otherwise
     */
    getExecutionPlanByConversationId: function(conversationId) {
        const execPlan = new GlideRecord('sn_aia_execution_plan');
        execPlan.addQuery('conversation', conversationId);
        execPlan.query();

        if (!execPlan.next())
            return null;

        if (execPlan.hasNext())
            gs.error('VoiceConversationUtilsSNC.getExecutionPlanByConversationId: Multiple execution plans found for conversationId={0}. Expected only one.', [conversationId]);

        return execPlan;
    },

    /**
     * Gets the most recent execution task for the given execution plan and tool
     *
     * @param {string} executionPlanId - The sys_id of the sn_aia_execution_plan
     * @param {string} toolId - The sys_id of the sn_aia_tool
     * @returns {GlideRecord|null} - The sn_aia_execution_task if found
     */
    getLatestExecutionTaskForTool: function(executionPlanId, toolId) {
        const executionTask = new GlideRecord('sn_aia_execution_task');
        executionTask.addQuery('execution_plan', executionPlanId);
        executionTask.addQuery('target_document_id', toolId);
        executionTask.addQuery('target_document_table', 'sn_aia_tool');
        executionTask.orderByDesc('sys_created_on');
        executionTask.setLimit(1);
        executionTask.query();

        if (executionTask.next())
            return executionTask;

        return null;
    },

    /**
     * Gets the most recent tools execution for the given execution plan and tool
     *
     * @param {string} executionPlanId - The sys_id of the sn_aia_execution_plan
     * @param {string} m2mtoolId - The sys_id of the sn_aia_agent_tool_m2m
     * @returns {GlideRecord|null} - The sn_aia_tools_execution if found
     */
    getLatestToolsExecutionForTool: function(executionPlanId, m2mtoolId) {
        const toolExecution = new GlideRecord('sn_aia_tools_execution');
        toolExecution.addQuery('execution_plan_id', executionPlanId);
        toolExecution.addQuery('tool', m2mtoolId);
        toolExecution.orderByDesc('sys_created_on');
        toolExecution.setLimit(1);
        toolExecution.query();

        if (toolExecution.next())
            return toolExecution;

        return null;
    },

    /**
     * Closes the execution plan for a conversation
     *
     * @param {string} conversationId - The ID of the conversation
     * @param {GlideDateTime} endTime - The end time to record
     */
    closeExecutionPlan: function(conversationId, endTime) {
        const execPlan = this.getExecutionPlanByConversationId(conversationId);
        if (execPlan) {
            execPlan.setValue('state', 'completed');
            execPlan.setValue('status', 'wrap_up');
            execPlan.setValue('end_time', endTime);
            execPlan.update();
        }
    },

    /**
     * Creates the execution plan record for a completed agentic voice call. One plan is
     * created per conversation, regardless of how many agents participate — each agent's own
     * work is added afterward via addAgentSegmentToPlan, not by this function (see DEF0849110;
     * a prior design created one plan per agent segment, which was incorrect since AO/NextWave
     * uses a single execution-plan UUID for the whole conversation).
     *
     * Creates the execution plan directly via GlideRecord. sn_aia.ExecutionPlanDao
     * is package_private and cannot be called from sn_voice_aia scope, so derived_scope
     * is not auto-resolved — all fields are set explicitly instead.
     *
     * Sets related_task_record and related_task_table to the interaction record for
     * the call (falling back to sys_cs_conversation when no interaction is found).
     *
     * Also sets context to {"taskRecordId": ..., "taskRecordTable": ...} with the same
     * values. This is intentional duplication: getCompleteExecutionEval (in sn_aia) returns
     * the context field in its API response but does NOT expose related_task_record or
     * related_task_table. context is therefore the only way for eval API consumers to
     * discover which task record this execution plan relates to.
     *
     * @param {string} conversationId - The sys_id of the sys_cs_conversation
     * @param {string} agenticConversationId - The AO-internal conversation ID (may be empty)
     * @param {string} agentId - The sys_id of the first agent to participate in the call;
     *   recorded on the plan's own `agent` field, matching the base sn_aia framework's
     *   convention (AIAToolExecutorSNC._createExecutionPlan) of the first agent to touch the
     *   plan "owning" that field, even though other agents may add tasks to it afterward.
     * @param {Array} history - The first agent segment's history, used to derive the objective
     * @param {number} [executionTimeMs] - Total call wall-clock time in ms; used to populate
     *   execution_time_sec on the plan for getExecutionLatencyDetails. This is a whole-call
     *   total (identical across every segment in the request), so it is set once here rather
     *   than accumulated per segment.
     * @returns {string} The sys_id of the newly created execution plan record
     */
    createExecutionPlan: function(conversationId, agenticConversationId, agentId, history, executionTimeMs) {
        gs.info('VoiceConversationUtilsSNC.createExecutionPlan: called conversationId={0} agentId={1} agenticConversationId={2} historyLen={3}',
            [conversationId, agentId, agenticConversationId || '(none)', history ? history.length : 0]);

        // Extract objective from the first user utterance in PAVA's history.
        var objective = '';
        if (history && history.length > 0) {
            for (var i = 0; i < history.length; i++) {
                if (history[i].type === 'user' && history[i].content) {
                    objective = history[i].content;
                    break;
                }
            }
        }
        gs.debug('VoiceConversationUtilsSNC.createExecutionPlan: extracted objective len={0}', [objective.length]);

        var relatedTask = this._getRelatedTask(conversationId);

        var fieldValues = {
            state: 'in_progress',
            conversation: conversationId,
            agent: agentId,
            objective: objective,
            related_task_record: relatedTask.id,
            related_task_table: relatedTask.table,
            context: JSON.stringify({
                taskRecordId: relatedTask.id,
                taskRecordTable: relatedTask.table
            })
        };

        // Create execution plan directly via GlideRecord — ExecutionPlanDao is
        // package_private to scope sn_aia and cannot be called from sn_voice_aia.
        var execPlanGr = new GlideRecord('sn_aia_execution_plan');
        execPlanGr.initialize();
        for (var f in fieldValues) {
            execPlanGr.setValue(f, fieldValues[f]);
        }
        var execTimeMs = parseInt(executionTimeMs, 10) || 0;
        if (execTimeMs > 0) {
            execPlanGr.setValue('execution_time_ms', execTimeMs);
            execPlanGr.setValue('execution_time_sec', Math.round(execTimeMs / 1000));
        }
        var executionPlanId = execPlanGr.insert();
        gs.info('VoiceConversationUtilsSNC.createExecutionPlan: plan insert result={0}', [executionPlanId || 'FAILED']);

        return executionPlanId;
    },

    /**
     * Creates an agent-type execution task under an execution plan so the record structure
     * matches a normal tool-driven call. Status is set to 'success' since the call has ended.
     *
     * Extracted from createExecutionPlan (DEF0849110) so the same task-creation logic can be
     * reused for every agent segment in a multi-agent call, not just whichever one happened to
     * create the plan.
     *
     * @param {string} planId - The execution plan sys_id
     * @param {string} agentId - The sys_id of the AI agent
     * @param {string} agentName - The display name of the agent
     * @param {Array} history - This segment's history, used to derive the task's objective
     * @returns {string} The sys_id of the newly created agent execution task
     * @private
     */
    _createAgentTask: function(planId, agentId, agentName, history) {
        var objective = '';
        if (history && history.length > 0) {
            for (var i = 0; i < history.length; i++) {
                if (history[i].type === 'user' && history[i].content) {
                    objective = history[i].content;
                    break;
                }
            }
        }

        // Look up agent's strategy name for agentDetails metadata.
        var agentStrategy = '';
        var agentLookup = new GlideRecord('sn_aia_agent');
        if (agentLookup.get(agentId)) {
            agentStrategy = agentLookup.getDisplayValue('strategy') || '';
        }

        var execTaskGr = new GlideRecord('sn_aia_execution_task');
        execTaskGr.initialize();
        execTaskGr.setValue('execution_plan', planId);
        execTaskGr.setValue('type', 'agent');
        execTaskGr.setValue('status', 'success');
        execTaskGr.setValue('description', agentName || agentId);
        execTaskGr.setValue('metadata', JSON.stringify({
            type: 'agent',
            id: agentId,
            name: agentName || '',
            agentDetails: { sys_id: agentId, name: agentName || '', strategy: agentStrategy },
            task: objective
        }));
        var agentTaskId = execTaskGr.insert();
        gs.info('VoiceConversationUtilsSNC._createAgentTask: agent task insert result={0} planId={1} agentId={2}',
            [agentTaskId || 'FAILED', planId, agentId]);

        return agentTaskId;
    },

    /**
     * Adds one agent's segment of a multi-agent voice call to a single, shared execution plan.
     * Called once per segment in store_execution_plan's segments array — including the first —
     * so every agent's tool/communicator activity lands under the same plan as tasks, instead
     * of each agent getting its own plan (see DEF0849110).
     *
     * Looks for an existing agent-type task for this agent under the plan first and reuses it
     * rather than creating a duplicate; a fresh task is only created when none exists yet.
     *
     * Confirmed against snc-pava (conversation.py / unified_orchestrator.py): Glide's own
     * /execute_tool is never called for relay-enabled conversations — UnifiedOrchestrator is a
     * standalone class that doesn't inherit or call it, and PAVA's own docs state tool history
     * for these calls arrives via gRPC events forwarded by the relay/AO service instead. So an
     * agent task can only already exist here because this same segment was already processed by
     * a prior call to this endpoint (a retry) — not from Glide-side execution racing this one —
     * which is why a single "most recent match, any status" lookup is sufficient; there's no
     * need to special-case an 'ongoing' status the way AIAToolExecutorSNC's
     * _getOngoingAgentExecutionTaskId does for the live standalone (non-relay) path it serves.
     *
     * Accumulates system_execution_time_ms on the plan across every call rather than
     * overwriting it, since each segment only knows its own share of tool time.
     *
     * @param {string} planId - The shared execution plan sys_id for the conversation
     * @param {string} agentId - The sys_id of this segment's agent
     * @param {string} agentName - The display name of this segment's agent
     * @param {Array} history - This segment's history (PII-redacted by PAVA)
     * @param {string} [incomingPlanId] - This segment's AO-supplied plan id, if any and if
     *   different from planId — used only to retarget orphan sn_aia_tools_execution rows (the
     *   FK case described in createExecutionPlan's original docs) onto the real plan id.
     * @returns {string} The sys_id of the agent task that was found or created
     */
    addAgentSegmentToPlan: function(planId, agentId, agentName, history, incomingPlanId) {
        gs.info('VoiceConversationUtilsSNC.addAgentSegmentToPlan: called planId={0} agentId={1} agentName={2} historyLen={3} incomingPlanId={4}',
            [planId, agentId, agentName, history ? history.length : 0, incomingPlanId || '(none)']);

        var taskDescription = agentName || agentId;
        var agentTaskId = null;

        // Most recent agent-type task matching this agent, regardless of status — see docstring
        // for why a single status-agnostic lookup is sufficient here.
        var existingTask = new GlideRecord('sn_aia_execution_task');
        existingTask.addQuery('execution_plan', planId);
        existingTask.addQuery('type', 'agent');
        existingTask.addQuery('description', taskDescription);
        existingTask.orderByDesc('sys_created_on');
        existingTask.setLimit(1);
        existingTask.query();

        if (existingTask.next()) {
            agentTaskId = existingTask.getUniqueValue();
            if (existingTask.getValue('status') !== 'success') {
                existingTask.setValue('status', 'success');
                existingTask.update();
            }
            gs.debug('VoiceConversationUtilsSNC.addAgentSegmentToPlan: reusing existing agent task={0} planId={1} agentId={2}',
                [agentTaskId, planId, agentId]);
        } else {
            agentTaskId = this._createAgentTask(planId, agentId, agentName, history);
        }

        if (agentTaskId && history && history.length > 0) {
            this._createToolTasksFromHistory(history, planId, agentTaskId);
            this._createCommunicatorTasksFromHistory(history, planId, agentTaskId);
        } else {
            gs.debug('VoiceConversationUtilsSNC.addAgentSegmentToPlan: skipping tool/communicator task creation agentTaskId={0} historyLen={1}',
                [agentTaskId || 'null', history ? history.length : 0]);
        }

        // Accumulate this segment's tool time onto the plan's running total rather than
        // overwriting it — each segment only knows its own share.
        var segmentSystemTimeMs = this._sumToolDurationsMs(history);
        if (segmentSystemTimeMs > 0) {
            var planGr = new GlideRecord('sn_aia_execution_plan');
            if (planGr.get(planId)) {
                var totalSystemTimeMs = (parseInt(planGr.getValue('system_execution_time_ms'), 10) || 0) + segmentSystemTimeMs;
                planGr.setValue('system_execution_time_ms', totalSystemTimeMs);
                planGr.setValue('system_execution_time_sec', Math.round(totalSystemTimeMs / 1000));
                planGr.update();
            }
        }

        // Repair the orphan FK case: when AO wrote its own UUID onto
        // sn_aia_tools_execution.execution_plan_id for this segment without a matching plan
        // existing yet, retarget those rows onto the real plan id now that it exists.
        if (incomingPlanId && planId && /^[0-9a-f]{32}$/.test(incomingPlanId) && incomingPlanId !== planId) {
            // Collect the set of tool_id values (sn_aia_agent_tool_m2m sys_ids) from this segment.
            var segmentToolIds = {};
            if (history && history.length > 0) {
                for (var ti = 0; ti < history.length; ti++) {
                    var toolId = history[ti].tool_id;
                    if (toolId && /^[0-9a-f]{32}$/.test(toolId))
                        segmentToolIds[toolId] = true;
                }
            }
            var toolIdList = Object.keys(segmentToolIds);

            if (toolIdList.length === 0) {
                // No hex tool_ids in this segment — cannot safely identify which rows belong
                // here without risking cross-agent contamination. Skip retargeting.
                gs.debug('VoiceConversationUtilsSNC.addAgentSegmentToPlan: skipping retarget for incomingPlanId={0} — no hex tool_ids in segment', [incomingPlanId]);
            } else {
                var orphanTools = new GlideRecord('sn_aia_tools_execution');
                orphanTools.addQuery('execution_plan_id', incomingPlanId);
                // Narrow to only the tool rows that belong to this segment's agent.
                orphanTools.addQuery('tool', 'IN', toolIdList.join(','));
                orphanTools.query();
                var retargetCount = 0;
                while (orphanTools.next()) {
                    orphanTools.setValue('execution_plan_id', planId);
                    if (orphanTools.update())
                        retargetCount += 1;
                }
                gs.info('VoiceConversationUtilsSNC.addAgentSegmentToPlan: retargeted {0} sn_aia_tools_execution row(s) from incoming planId={1} to planId={2} (filtered by {3} tool ids)',
                    [retargetCount, incomingPlanId, planId, toolIdList.length]);
            }
        }

        return agentTaskId;
    },

    /**
     * Creates TOOL-type execution tasks from tool_executed entries in PAVA's agentic history.
     *
     * During an agentic voice call, Nextwave (AO) emits a 'tool_executed' SSE event for each
     * tool invocation. PAVA captures these in its _agentic_history and includes them in the
     * history array passed to store_execution_plan. This function reads those entries and creates
     * sn_aia_execution_task records so that getCompleteExecutionEval can return tool_inputs.
     *
     * Each tool_executed entry has: tool_name, tool_id (toolM2mId), inputs (filled_slots), output.
     *
     * @param {Array} history - PAVA's agentic history array (may contain tool_executed entries)
     * @param {string} targetPlanId - PAVA execution plan sys_id
     * @param {string} agentTaskId - PAVA agent task sys_id (parent for tool tasks)
     * @private
     */
    _createToolTasksFromHistory: function(history, targetPlanId, agentTaskId) {
        gs.info('VoiceConversationUtilsSNC._createToolTasksFromHistory: start targetPlanId={0} agentTaskId={1} historyLen={2}',
            [targetPlanId, agentTaskId, history ? history.length : 0]);
        try {
            // Log a summary of entry types in history to aid debugging when tool tasks are missing.
            var typeCounts = {};
            for (var j = 0; j < history.length; j++) {
                var t = history[j].type || '(no type)';
                typeCounts[t] = (typeCounts[t] || 0) + 1;
            }
            gs.debug('VoiceConversationUtilsSNC._createToolTasksFromHistory: history type breakdown={0}',
                [JSON.stringify(typeCounts)]);

            var order = 100;
            var createdCount = 0;
            var skippedCount = 0;
            for (var i = 0; i < history.length; i++) {
                var entry = history[i];
                if (entry.type !== 'tool_executed') {
                    skippedCount += 1;
                    continue;
                }
                var toolName = entry.tool_name || '';
                var toolId = entry.tool_id || '';
                var toolSysId = entry.tool_sys_id || '';
                var inputs = entry.inputs || {};
                var output = entry.output || {};
                var execDurationMs = entry.exec_duration_ms !== null && entry.exec_duration_ms !== undefined
                    ? parseInt(entry.exec_duration_ms, 10) : null;
                // Map Nextwave's 'failure' to ServiceNow's 'error' enum value; default to 'success'.
                var toolStatus = entry.status === 'failure' ? 'error' : 'success';
                var inputKeys = Object.keys(inputs);
                var hasOutput = !gs.nil(output) && JSON.stringify(output) !== '{}';
                gs.debug('VoiceConversationUtilsSNC._createToolTasksFromHistory: processing entry i={0} toolName={1} toolId={2} inputKeys={3} hasOutput={4} execDurationMs={5} order={6}',
                    [i, toolName, toolId || '(none)', JSON.stringify(inputKeys), hasOutput, execDurationMs !== null ? execDurationMs : '(none)', order]);
                if (!toolName) {
                    gs.warn('VoiceConversationUtilsSNC._createToolTasksFromHistory: tool_executed entry at i={0} has empty tool_name — task will be created with blank description',
                        [i]);
                }
                // name and id align with _trackToolExecution metadata schema.
                // tool_sys_id is the sn_aia_tool sys_id (dereferenced from M2M by offglide);
                // fall back to toolId (M2M sys_id) for older payloads that predate this field.
                // type is omitted — not available from the SSE history payload without a DB lookup.
                var metadataJson = JSON.stringify({
                    name: toolName,
                    id: toolSysId || toolId,
                    inputs: inputs
                });
                var outputJson = JSON.stringify({
                    result: JSON.stringify({
                        'Output Fields': output
                    })
                });
                gs.debug('VoiceConversationUtilsSNC._createToolTasksFromHistory: metadata preview={0} outputPreview={1}',
                    [metadataJson.substring(0, 200), outputJson.substring(0, 200)]);

                // Resolve the best available sn_aia_tool sys_id for target_document linking.
                // tool_id has two possible formats depending on the caller:
                //   - Nextwave path: tool_id is the sn_aia_agent_tool_m2m sys_id (32-char hex) — usable as a sys_id
                //   - Relay path:    tool_id is the SDK call_id (not a sys_id; may contain dashes or other non-hex chars)
                // The hex check distinguishes the two: only promote toolId to resolvedSysId if it looks like a sys_id.
                var resolvedSysId = toolSysId;
                if (!resolvedSysId && toolId && toolId.length === 32 && /^[0-9a-f]+$/i.test(toolId)) {
                    resolvedSysId = toolId;
                }
                if (!resolvedSysId && toolName) {
                    var toolLookup = new GlideRecord('sn_aia_tool');
                    toolLookup.addQuery('name', toolName);
                    toolLookup.setLimit(1);
                    toolLookup.query();
                    if (toolLookup.next()) {
                        resolvedSysId = toolLookup.getUniqueValue();
                        gs.debug('VoiceConversationUtilsSNC._createToolTasksFromHistory: resolved toolSysId={0} for toolName={1} via name lookup',
                            [resolvedSysId, toolName]);
                    }
                }

                var newTask = new GlideRecord('sn_aia_execution_task');
                newTask.initialize();
                newTask.setValue('execution_plan', targetPlanId);
                newTask.setValue('parent', agentTaskId);
                newTask.setValue('type', 'tool');
                newTask.setValue('status', toolStatus);
                newTask.setValue('description', toolName);
                newTask.setValue('metadata', metadataJson);
                newTask.setValue('output', outputJson);
                newTask.setValue('order', order);
                if (execDurationMs !== null && !isNaN(execDurationMs)) {
                    newTask.setValue('execution_time_ms', execDurationMs);
                }
                if (resolvedSysId) {
                    newTask.setValue('target_document_id', resolvedSysId);
                    newTask.setValue('target_document_table', 'sn_aia_tool');
                } else if (toolId) {
                    // Last resort: store whatever toolId we have against the M2M table
                    newTask.setValue('target_document_id', toolId);
                    newTask.setValue('target_document_table', 'sn_aia_agent_tool_m2m');
                } else {
                    gs.debug('VoiceConversationUtilsSNC._createToolTasksFromHistory: no toolId for toolName={0} — target_document_id will be empty',
                        [toolName]);
                }
                var newTaskId = newTask.insert();
                if (newTaskId) {
                    createdCount += 1;
                    gs.info('VoiceConversationUtilsSNC._createToolTasksFromHistory: inserted tool task newTaskId={0} toolName={1} inputKeys={2} order={3}',
                        [newTaskId, toolName, JSON.stringify(inputKeys), order]);
                } else {
                    gs.warn('VoiceConversationUtilsSNC._createToolTasksFromHistory: insert failed for tool task toolName={0} order={1} — getLastErrorMessage={2}',
                        [toolName, order, newTask.getLastErrorMessage()]);
                }
                order += 100;
            }
            gs.info('VoiceConversationUtilsSNC._createToolTasksFromHistory: done createdCount={0} skippedCount={1} targetPlanId={2}',
                [createdCount, skippedCount, targetPlanId]);
            if (createdCount === 0 && typeCounts['tool_executed'] > 0) {
                gs.warn('VoiceConversationUtilsSNC._createToolTasksFromHistory: no tool tasks created despite historyLen={0} — check that Nextwave is emitting tool_executed SSE events and PAVA is capturing them. History type breakdown={1}',
                    [history.length, JSON.stringify(typeCounts)]);
            }
        } catch (e) {
            gs.error('VoiceConversationUtilsSNC._createToolTasksFromHistory failed for targetPlanId={0}: {1}',
                [targetPlanId, e.message || String(e)]);
        }
    },

    /**
     * Creates COMMUNICATOR-type execution tasks from conversation entries in PAVA's agentic history.
     *
     * Maps history entries to sn_aia_execution_task records so that getCompleteExecutionEval
     * can return user_input and user_output events:
     *
     *   Paired collect_inputs + user entries → description='Get user input'
     *     metadata.task = clarifying_question, output.result = user's answer (plain string)
     *
     *   Standalone user entries               → description='Get user input'
     *     metadata.task = '' (no preceding question), output.result = user's message
     *     Maps to event_type='user_input' in getCompleteExecutionEval with content.user_input set.
     *
     *   Standalone assistant entries          → description='Show response to user'
     *     metadata.task = assistant message content
     *
     *   Unpaired collect_inputs (call ended before user replied)
     *                                         → description='Show response to user'
     *     metadata.task = clarifying_question
     *
     * tool_executed and close_conversation entries are skipped.
     *
     * IMPORTANT: output.result for 'Get user input' tasks must be a plain string value, NOT
     * double-JSON-stringified. getCompleteExecutionEval reads child?.output?.result directly
     * after JSON.parse(task.output) — no second parse step.
     *
     * Tasks are assigned orders starting at 1000 (tool tasks start at 100) to avoid collisions.
     *
     * @param {Array} history - PAVA's agentic history array
     * @param {string} targetPlanId - execution plan sys_id
     * @param {string} agentTaskId - agent task sys_id (parent for communicator tasks)
     * @private
     */
    _createCommunicatorTasksFromHistory: function(history, targetPlanId, agentTaskId) {
        gs.info('VoiceConversationUtilsSNC._createCommunicatorTasksFromHistory: start targetPlanId={0} agentTaskId={1} historyLen={2}',
            [targetPlanId, agentTaskId, history ? history.length : 0]);
        try {
            var order = 1000;
            var createdCount = 0;
            var i = 0;
            while (i < history.length) {
                var entry = history[i];
                var taskDesc = null;
                var taskMetaJson = null;
                var taskOutputJson = null;
                var skipNext = false;

                if (entry.type === 'collect_inputs') {
                    var question = entry.clarifying_question || '';
                    var nextEntry = i + 1 < history.length ? history[i + 1] : null;
                    if (nextEntry && nextEntry.type === 'user') {
                        // Paired: bot question + user answer → "Get user input"
                        var userAnswer = nextEntry.content || '';
                        taskDesc = 'Get user input';
                        taskMetaJson = JSON.stringify({ task: question });
                        // output.result is read directly by the eval (child?.output?.result),
                        // so store the answer as a plain string — NOT double-JSON-stringified.
                        taskOutputJson = JSON.stringify({ result: userAnswer });
                        skipNext = true;
                        gs.debug('VoiceConversationUtilsSNC._createCommunicatorTasksFromHistory: pairing collect_inputs[{0}] with user[{1}] question_len={2} answer_len={3}',
                            [i, i + 1, question.length, userAnswer.length]);
                    } else {
                        // Unpaired: question with no following user reply → "Show response to user"
                        taskDesc = 'Show response to user';
                        taskMetaJson = JSON.stringify({ task: question });
                        gs.debug('VoiceConversationUtilsSNC._createCommunicatorTasksFromHistory: unpaired collect_inputs[{0}] → Show response to user question_len={1}',
                            [i, question.length]);
                    }
                } else if (entry.type === 'assistant') {
                    var message = entry.content || '';
                    taskDesc = 'Show response to user';
                    taskMetaJson = JSON.stringify({ task: message });
                    gs.debug('VoiceConversationUtilsSNC._createCommunicatorTasksFromHistory: assistant[{0}] → Show response to user message_len={1}',
                        [i, message.length]);
                } else if (entry.type === 'user') {
                    // Standalone user turn (relay path has no collect_inputs) → "Get user input".
                    // output.result populates content.user_input in getCompleteExecutionEval.
                    var userContent = entry.content || '';
                    taskDesc = 'Get user input';
                    taskMetaJson = JSON.stringify({ task: '' });
                    taskOutputJson = JSON.stringify({ result: userContent });
                    gs.debug('VoiceConversationUtilsSNC._createCommunicatorTasksFromHistory: user[{0}] → Get user input content_len={1}',
                        [i, userContent.length]);
                }
                // tool_executed, close_conversation: skip

                if (taskDesc) {
                    var newTask = new GlideRecord('sn_aia_execution_task');
                    newTask.initialize();
                    newTask.setValue('execution_plan', targetPlanId);
                    newTask.setValue('parent', agentTaskId);
                    newTask.setValue('type', 'communicator');
                    newTask.setValue('status', 'success');
                    newTask.setValue('description', taskDesc);
                    newTask.setValue('metadata', taskMetaJson);
                    if (taskOutputJson) {
                        newTask.setValue('output', taskOutputJson);
                    }
                    newTask.setValue('order', order);
                    var newTaskId = newTask.insert();
                    if (newTaskId) {
                        createdCount += 1;
                        gs.info('VoiceConversationUtilsSNC._createCommunicatorTasksFromHistory: inserted type=communicator description={0} newTaskId={1} order={2}',
                            [taskDesc, newTaskId, order]);
                    } else {
                        gs.warn('VoiceConversationUtilsSNC._createCommunicatorTasksFromHistory: insert failed description={0} order={1} getLastErrorMessage={2}',
                            [taskDesc, order, newTask.getLastErrorMessage()]);
                    }
                    order += 100;
                }

                i += skipNext ? 2 : 1;
            }
            gs.info('VoiceConversationUtilsSNC._createCommunicatorTasksFromHistory: done createdCount={0} targetPlanId={1}',
                [createdCount, targetPlanId]);
        } catch (e) {
            gs.error('VoiceConversationUtilsSNC._createCommunicatorTasksFromHistory failed for targetPlanId={0}: {1}',
                [targetPlanId, e.message || String(e)]);
        }
    },

    /**
     * Sums exec_duration_ms across all tool_executed entries in history.
     * Used as an approximation of system processing time for voice execution plans.
     *
     * @param {Array} history - Relay history entries
     * @returns {number} Total tool execution time in milliseconds
     */
    _sumToolDurationsMs: function(history) {
        var total = 0;
        if (!history || !history.length) return total;
        for (var i = 0; i < history.length; i++) {
            var entry = history[i];
            if (entry.type === 'tool_executed' && entry.exec_duration_ms) {
                total += parseInt(entry.exec_duration_ms, 10) || 0;
            }
        }
        return total;
    },

    /**
     * Updates plan-level context and related-task fields on an existing execution plan at call
     * end. Called when a plan already exists for the conversation — either Glide's own
     * /execute_tool created it live for some agent's tool call, or a prior call to
     * store_execution_plan already created it for this conversation.
     *
     * Per-agent task creation/enrichment is NOT this function's responsibility — that's handled
     * uniformly for every segment (including the first) by addAgentSegmentToPlan, so this
     * function only ever touches plan-level fields (see DEF0849110).
     *
     * Sets context = {"taskRecordId": ..., "taskRecordTable": ...} pointing to the
     * interaction record (falling back to sys_cs_conversation). If related_task_record
     * is already set on the plan (e.g. by AIAToolExecutorSNC), that value is used as-is
     * and no interaction lookup is performed.
     *
     * Also backfills the objective from the first user utterance if it was not set
     * by AIAToolExecutorSNC (which does not set objective on the voice path).
     *
     * @param {GlideRecord} execPlan - The existing execution plan GlideRecord
     * @param {string} agenticConversationId - The AO-internal conversation ID (retained for signature compatibility)
     * @param {Array} history - The first agent segment's history, used to derive the objective
     * @param {number} [executionTimeMs] - Total call wall-clock time in ms; a whole-call total
     *   (identical across every segment in the request), so it is set once here rather than
     *   accumulated per segment.
     */
    updateExecutionPlanContext: function(execPlan, agenticConversationId, history, executionTimeMs) {
        // Always backfill objective from first user utterance — AIAToolExecutorSNC does not set
        // it on the voice path, and this function is only called from the voice store_execution_plan
        // endpoint so overwriting is safe.
        var objective = '';
        if (history && history.length > 0) {
            for (var i = 0; i < history.length; i++) {
                if (history[i].type === 'user' && history[i].content) {
                    objective = history[i].content;
                    break;
                }
            }
        }
        if (objective) {
            execPlan.setValue('objective', objective);
        }

        // Resolve related task: use existing value if already set (e.g. by AIAToolExecutorSNC),
        // otherwise look up the interaction record from the conversation.
        var relatedTaskId = execPlan.getValue('related_task_record');
        var relatedTaskTable = execPlan.getValue('related_task_table');
        if (!relatedTaskId) {
            var conversationId = execPlan.getValue('conversation');
            var interactionGr = this.getInteractionFromConversation(conversationId);
            if (interactionGr) {
                relatedTaskId = interactionGr.getUniqueValue();
                relatedTaskTable = 'interaction';
                execPlan.setValue('related_task_record', relatedTaskId);
                execPlan.setValue('related_task_table', relatedTaskTable);
            }
        }

        execPlan.setValue('context', JSON.stringify({
            taskRecordId: relatedTaskId,
            taskRecordTable: relatedTaskTable
        }));

        // Set execution time fields when available.
        var execTimeMs = parseInt(executionTimeMs, 10) || 0;
        if (execTimeMs > 0) {
            execPlan.setValue('execution_time_ms', execTimeMs);
            execPlan.setValue('execution_time_sec', Math.round(execTimeMs / 1000));
        }

        execPlan.update();
    },

    /**
     * Updates the usage log ID for an execution plan
     *
     * @param {GlideRecord} executionPlanGr - The execution plan GlideRecord to update
     * @param {string} usageLogId - The ID of the usage log to associate
     */
    updateUsageLogForPlanId: function(executionPlanGr, usageLogId) {
        executionPlanGr.setValue('gen_ai_usage_log', usageLogId);
        executionPlanGr.update();
    },

    /**
     * Gets the count of unique external agents for an execution plan
     *
     * @param {string} executionPlanId - The ID of the execution plan
     * @returns {number} - The count of unique external agents
     */
    getExternalAgentCount: function(executionPlanId) {
        if (!executionPlanId) {
            return 0;
        }
        var uniqueExternalAgents = {};
        try {
            var taskGr = new GlideRecord('sn_aia_execution_task');
            taskGr.addQuery('execution_plan', executionPlanId);
            taskGr.addQuery('type', 'agent');
            taskGr.addQuery('metadata', 'LIKE', '"agent_type":"external"');
            taskGr.query();

            while (taskGr.next()) {
                try {
                    var metadataStr = taskGr.getValue('metadata');
                    if (!gs.nil(metadataStr)) {
                        var metadata = JSON.parse(metadataStr);
                        var agentDetails = metadata.agentDetails;
                        if (!gs.nil(agentDetails.sys_id)) {
                            // Only count unique external agents by sys_id
                            uniqueExternalAgents[agentDetails.sys_id] = true;
                        }
                    }
                } catch (ex) {
                    // Log error for individual task but continue processing
                    gs.error('Error processing task {0} in execution plan {1}: {2}',
                        [taskGr.getUniqueValue(), executionPlanId, ex.toString()]);
                }
            }
        } catch (e) {
            gs.error('Error in getExternalAgentCount for execution plan {0}: {1}',
                [executionPlanId, e.toString()]);
        }
        return Object.keys(uniqueExternalAgents).length;
    },

    /**
     * Gets the count of tool executions for a given execution plan ID
     *
     * @param {string} executionPlanId - The ID of the execution plan
     * @returns {number} - The count of tool executions, or 0 if none found
     */
    getToolExecutionsCountByPlanId: function(executionPlanId) {
        var ga = new GlideAggregate(VoiceAgentConstants.TABLES.TOOLS_EXECUTION);

        ga.addQuery('execution_plan_id', executionPlanId);
        ga.addNotNullQuery('tool');
        ga.addAggregate('COUNT');
        ga.query();

        if (ga.next())
            return ga.getAggregate('COUNT');

        return 0;
    },

    /**
     * Retrieves the provider application record
     *
     * @param {string} providerId - The ID of the provider
     * @returns {GlideRecord|null} - The provider application record if found, null otherwise
     */
    getProviderAppRecord: function(providerId) {
        const channelProvider = new GlideRecord('sys_cs_provider_application');
        if (!providerId || !channelProvider.get('inbound_id', providerId)) {
            gs.error('VoiceConversationUtilsSNC.getProviderAppRecord: Provider app record not found for providerId={0}', [providerId]);
            return null;
        }
        return channelProvider;
    },

    /**
     * Gets the channel name for a provider
     *
     * @param {string} providerId - The ID of the provider
     * @returns {string} - The channel name
     */
    getChannelName: function(providerId) {
        const channelProvider = this.getProviderAppRecord(providerId);
        // getProviderAppRecord already logs gs.error on null — no second log needed here.
        if (!channelProvider)
            return '';
        return channelProvider.provider.channel.getDisplayValue();
    },

    /**
     * Retrieves session variables for a conversation
     *
     * @param {string} status - The status code
     * @param {Object} payload - The conversation payload containing conversationId and stateReason
     * @returns {Object} - Object containing session variables
     */
    getSessionVariables: function(status, payload) {
        let sessionVariables = {};

        const {
            conversationId,
            stateReason
        } = payload;

        const interaction = this.getInteractionFromConversation(conversationId);
        sessionVariables.snStatusCode = status.toString();
        sessionVariables.snTransferReason = stateReason;
        sessionVariables.snConversationId = conversationId;

        if (!interaction) {
            gs.error('VoiceConversationUtilsSNC.getSessionVariables: no interaction found for conversationId={0} — interaction-dependent fields will be empty', [conversationId]);
            sessionVariables.snInteractionId = '';
            sessionVariables.snIsAuthenticated = '';
            Object.assign(sessionVariables, this._getCustomSessionVariables(conversationId, payload));
            return sessionVariables;
        }

        sessionVariables.snInteractionId = interaction.getUniqueValue();
        sessionVariables.snIsAuthenticated = interaction.verified.toString();

        if (interaction.verified && interaction.opened_for) {
            sessionVariables.snFirstName = interaction.opened_for.first_name.toString();
            sessionVariables.snLastName = interaction.opened_for.last_name.toString();
        }

        Object.assign(sessionVariables, this._getCustomSessionVariables(conversationId, payload));

        return sessionVariables;
    },

    isAgentChatPluginInstalled: function() {
        const pluginId = 'com.glide.interaction.awa';
        const pluginManager = new GlidePluginManager();
        return pluginManager.isActive(pluginId);
    },

    /**
     * Retrieves custom session variables from extension points
     *
     * @param {string} conversationId - The conversation ID
     * @param {Object} payload - The conversation payload
     * @returns {Object} - Custom session variables from extension points
     * @private
     */
    _getCustomSessionVariables: function(conversationId, payload) {
        const allExtensionPoints = new GlideScriptedExtensionPoint().getExtensions('sn_voice_aia.VoiceConversationExt');
        for (var j in allExtensionPoints) {
            var ep = allExtensionPoints[j];
            ep.initialize();
            if (ep.shouldProcessConversation(payload)) {
                return this._ensureStringValues(ep.getCustomSessionVariables(conversationId, payload));
            }
        }
        return {};
    },

    /**
     * Ensures all values in an object are strings
     *
     * @param {Object} obj - The object to process
     * @returns {Object} - New object with all values converted to strings
     * @private
     */
    _ensureStringValues: function(obj) {
        if (!obj || typeof obj !== 'object') {
            return obj;
        }

        const result = {};
        for (var key in obj) {
            if (obj.hasOwnProperty(key)) {
                // Convert each value to string, handling null/undefined gracefully
                result[key] = obj[key] != null ? String(obj[key]) : '';
            }
        }
        return result;
    },


    /**
     * Contains the context information for the utterance, matching fields in sys_generative_ai_log
     * @typedef {Object} Utterance
     * @property {GlideDateTime} started_at - Time that the utterance started
     * @property {GlideDateTime} completed_at - Time when the interaction with the utterance ended
     * @property {string} state - Ending state of the utterance
     * @property {string} prompt - Prompt for the LLM
     * @property {string} response - Response from the LLM
     */

    /**
     * Builds Utterance objects from the AI Voice Orchestrator payload
     *
     * @param {Object} payload - JSON object passed from the orchestrator
     * @returns {Array<Utterance>}
     */
    buildUtterancesFromOrchestratorPayload: function(payload) {
        const utterances = [];
        payload?.forEach(prompt => {
            const started_at = new GlideDateTime();
            started_at.setValue(Number(prompt.start_time));
            const completed_at = new GlideDateTime();
            completed_at.setValue(Number(prompt.end_time));
            utterances.push({
                started_at,
                completed_at,
                status: prompt.status,
                prompt: JSON.stringify(prompt.prompt, null, 2),
                response: prompt.response,
                model: prompt.model,
            });
        });
        return utterances;
    },

    /**
     * Create sys_generative_ai_logs for the utterances
     *
     * @param {sys_id} conversationId - sys_id of the sys_cs_conversation
     * @param {Array<Utterance>} utterances - JSON containing an array of 'llm_prompts' which contains logging information
     *                           for every utterance
     */
    createLogs: function(conversationId, utterances) {
        if (utterances?.length) {
            const log = new GlideRecord('sys_generative_ai_log');
            utterances.forEach(utterance => {
                log.initialize();

                for (const [key, value] of Object.entries(utterance)) {
                    if (key === 'model') continue;
                    log.setValue(key, value);
                }

                if (utterance.model)
                    log.setValue('model_name', utterance.model);

                log.setValue('conversation', conversationId);
                log.setValue('caller', 'AI Voice Orchestrator');
                log.setValue('definition', VoiceAgentConstants.CAPABILITY_DEFINITION);
                log.setValue('external', true);
                log.insert();
            });
        }
    },

    /**
     * Determine which device is being used from the User-Agent
     *
     * @param {String} voiceSource - Source of the incoming request
     * @param {String} [userAgent] - The device/browser of the incoming request
     */
    determineVoiceOrigin: function(voiceSource, userAgent) {
        if (voiceSource === VoiceAgentConstants.VOICE_SOURCE.MOBILE_WEBRTC) {
            // iOS User-Agent contains "iOS" (e.g., "SpeakNow-iOS-Version x.x")
            if (userAgent && userAgent.includes(VoiceAgentConstants.VOICE_ORIGIN_IDENTIFIERS.IOS))
                return VoiceAgentConstants.VOICE_ORIGIN.MOBILE_APP_IOS;
            return VoiceAgentConstants.VOICE_ORIGIN.MOBILE_APP_ANDROID;
        } else if (voiceSource === VoiceAgentConstants.VOICE_SOURCE.PLATFORM_WEBRTC || voiceSource === VoiceAgentConstants.VOICE_SOURCE.PLATFORM_TEXTCHAT) {
            // All browser-based WebRTC calls are categorized as Web Browser
            return VoiceAgentConstants.VOICE_ORIGIN.WEB_BROWSER;
        }

        return VoiceAgentConstants.VOICE_ORIGIN.PHONE;
    },

    /**
     * Builds a merged, deep copy object from the target and source objects
     *
     * @param {Object} target object
     * @param {Object} source object
     * @returns {Object} merged, deep copy object
     */
    mergeObjects: function(target, source) {
        const result = {};
        for (let key in target) {
            if (target.hasOwnProperty(key))
                result[key] = target[key];
        }
        for (let key in source) {
            if (source.hasOwnProperty(key)) {
                if (source[key] !== null && typeof source[key] === 'object' && !Array.isArray(source[key]) &&
                    result[key] !== null && typeof result[key] === 'object' && !Array.isArray(result[key])) {
                    result[key] = this.mergeObjects(result[key], source[key]);
                } else {
                    result[key] = source[key];
                }
            }
        }
        return result;
    },

    /**
     * Resolves the best related-task reference for the execution plan's context field.
     * Prefers the interaction record (the voice call itself); falls back to the
     * sys_cs_conversation record when no interaction is found.
     *
     * @param {string} conversationId - The sys_id of the sys_cs_conversation
     * @returns {{id: string, table: string}} Object with id and table fields
     * @private
     */
    _getRelatedTask: function(conversationId) {
        if (conversationId) {
            var interactionGr = this.getInteractionFromConversation(conversationId);
            if (interactionGr) {
                return { id: interactionGr.getUniqueValue(), table: 'interaction' };
            }
        }
        return { id: conversationId || '', table: 'sys_cs_conversation' };
    },

    /**
     * Inserts a single record into the interaction_context table.
     * @param {string} interactionSysId - sys_id of the parent interaction record
     * @param {string} key - context key (stored in the 'name' column)
     * @param {*} value - context value; objects are JSON-stringified, primitives are cast to String
     * @returns {string|null} sys_id of the inserted record, or null on failure
     */
    saveInteractionContext: function(interactionSysId, key, value) {
        if (!interactionSysId || !key) {
            gs.warn('VoiceConversationUtilsSNC.saveInteractionContext: Missing required parameters — interactionSysId={0}, key={1}', [interactionSysId, key]);
            return null;
        }
        try {
            var contextGr = new GlideRecord(VoiceAgentConstants.TABLES.INTERACTION_CONTEXT);
            contextGr.initialize();
            contextGr.setValue('interaction', interactionSysId);
            contextGr.setValue('name', key);
            contextGr.setValue('value', typeof value === 'object' ? JSON.stringify(value) : String(value));
            var sysId = contextGr.insert();
            if (!sysId)
                gs.error('VoiceConversationUtilsSNC.saveInteractionContext: Insert failed for interaction={0}, key={1}', [interactionSysId, key]);
            return sysId;
        } catch (e) {
            gs.error('VoiceConversationUtilsSNC.saveInteractionContext: Error for interaction={0}, key={1}: {2}', [interactionSysId, key, e.toString()]);
            return null;
        }
    },

    type: 'VoiceConversationUtilsSNC'
};