var VoiceExecuteToolsSNC = Class.create();
VoiceExecuteToolsSNC.prototype = {
    initialize: function() {},

    executeTool(request, response, isGuestSession) {
        const payload = request.body.data;
        const requiredParameters = ['toolId', 'conversationId'];
        const restUtils = new VoiceRestUtils();
        const errors = restUtils.validatePayload(payload, requiredParameters);

        if (errors.length > 0) {
            response.setStatus(400);
            response.setBody({
                detail: errors
            });
            return;
        }

        const conversationId = payload.conversationId;
        const agentId = payload.agentId;
        const agentToolM2MId = payload.toolId;
        let toolId;
        let toolResponse;
        let toolParameters = payload.toolParameters;

        if (isGuestSession) {
            const extensions = new GlideScriptedExtensionPoint().getExtensions('sn_voice_aia.VoiceToolParametersExt');
            for (let i = 0; i < extensions.length; i++) {
                extensions[i].initialize();
                toolParameters = extensions[i].getToolParameters(payload, toolParameters);
            }
        }

        try {
            if (agentId === 'fallback_agent') {
                const voiceFallbackUtils = new VoiceFallbackUtils();
                toolResponse = voiceFallbackUtils.executeFallbackAgent(agentToolM2MId, toolParameters, conversationId);
            } else {
                let agentToolM2MGr = new GlideRecord(VoiceAgentConstants.TABLES.AGENT_TOOL_M2M);

                if (!agentToolM2MGr.get(agentToolM2MId)) {
                    response.setBody({
                        message: `Agent Tool M2M record not found for ID : ${agentToolM2MId}`,
                    });
                    response.setStatus(404);
                    return;
                }

                if (agentId && !this._canAccessAgent(agentId)) {
                    response.setBody({
                        message: 'Access denied: step-up authentication required for this agent.'
                    });
                    response.setStatus(403);
                    return;
                }

                toolId = agentToolM2MGr.tool + '';
                const toolExecutor = new sn_aia.AIAToolExecutor();
                const toolOverrides = new ToolOverrides();
                const toolsHavingRequestOverrides = toolOverrides.getToolRequestOverridesList();

                if (toolsHavingRequestOverrides.indexOf(toolId) > -1)
                    toolParameters = toolOverrides.resolveRequest(agentToolM2MId, toolParameters);

                if (agentToolM2MGr.tool.type.toString() === VoiceAgentConstants.TOOL_TYPE_CRUD)
                    toolParameters = toolOverrides.resolveCRUDRequest(agentToolM2MGr, toolParameters);

                toolResponse = toolExecutor.executeTool(agentToolM2MId, conversationId, toolParameters);

                const toolsHavingResponseOverrides = toolOverrides.getToolResponseOverridesList();
                if (toolsHavingResponseOverrides.indexOf(toolId) > -1)
                    toolResponse = toolOverrides.resolveResponse(toolId, toolResponse);
            }

            const executionRecords = {};

            const conversationUtils = new VoiceConversationUtils();
            const executionPlan = conversationUtils.getExecutionPlanByConversationId(conversationId);
            if (executionPlan) {
                const executionPlanId = executionPlan.getUniqueValue();
                executionRecords.execution_plan_id = executionPlanId;

                const executionTask = conversationUtils.getLatestExecutionTaskForTool(executionPlanId, toolId);
                if (executionTask)
                    executionRecords.execution_task_id = executionTask.getUniqueValue();

                const toolsExecution = conversationUtils.getLatestToolsExecutionForTool(executionPlanId, agentToolM2MId);
                if (toolsExecution)
                    executionRecords.tools_execution_id = toolsExecution.getUniqueValue();
            }

            if (toolResponse.is_error) {
                toolResponse.message = toolResponse.error_msg;
                delete toolResponse.error_msg;
                response.setBody({
                    ...toolResponse,
                    ...executionRecords
                });
                response.setStatus(422);
                return;
            }

            response.setBody({
                tool_response: toolResponse.tool_response,
                ...executionRecords
            });
            response.setStatus(200);
        } catch (e) {
            response.setBody({
                message: `Internal server error occurred during tool execution: ${e.message}`,
            });
            response.setStatus(500);
        }
    },

    _canAccessAgent: function(agentId) {
        const agentGr = new GlideRecord(VoiceAgentConstants.TABLES.AIA_AGENT);

        if (agentGr.get(agentId))
            return gs.hasRightsTo(`${VoiceAgentConstants.ACL_TYPE.AGENT}/${agentGr.internal_name}/execute`, null);

        return false;
    },

    type: 'VoiceExecuteToolsSNC'
};