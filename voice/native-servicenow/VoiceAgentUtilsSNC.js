var VoiceAgentUtilsSNC = Class.create();
VoiceAgentUtilsSNC.prototype = {
    initialize: function() {},

    processGetAllAgents: function(cacheDate, serviceId, callSource, testMode) {
        if (!serviceId) {
            return {
                error: {
                    message: 'No active voice service found.'
                },
                status: 404,
            };
        }

        var voiceFallbackUtils = new sn_voice_aia.VoiceFallbackUtils();
        var fallBackAgent = voiceFallbackUtils.createFallbackAgent(serviceId, callSource);

        if (cacheDate) {
            var agents = [];
            var isAllAgentsCached = false;
            var updateDate = new GlideDateTime(cacheDate);
            var agentsCacheGr = new GlideRecord(VoiceAgentConstants.TABLES.AGENTS_CACHE);
            agentsCacheGr.addQuery('last_refreshed_at', '>', updateDate);
            agentsCacheGr.addQuery('type', 'agents');
            agentsCacheGr.query();
            while (agentsCacheGr.next()) {
                var voiceService = agentsCacheGr.getValue('voice_service');
                try {
                    var cachedObject = JSON.parse(agentsCacheGr.getValue('json_object'));
                } catch (e) {
                    gs.error(gs.getMessage('Invalid json in {0}', [agentsCacheGr.getUniqueValue()]));
                }
                if (voiceService === serviceId) {
                    if (fallBackAgent)
                        cachedObject.agents.push(fallBackAgent);
                    return cachedObject;
                } else {
                    if (Array.isArray(cachedObject.agents)) {
                        for (var i = 0; i < cachedObject.agents.length; i++) {
                            var agent = cachedObject.agents[i];
                            if (agent.id) {
                                var exists = agents.some(function(existingAgent) {
                                    return existingAgent.id === agent.id;
                                });
                                if (!exists)
                                    agents.push(agent);
                            }
                        }
                    }
                    isAllAgentsCached = true;
                }
            }
            if (isAllAgentsCached) {
                if (fallBackAgent)
                    agents.push(fallBackAgent);
                return {
                    'agents': agents,
                    'lastModified': new Date().toISOString()
                };
            }
        }
        return this.refreshCacheAndFetchAgents(serviceId, fallBackAgent, testMode);
    },

    getAuthorizedAgentIds: function(serviceId, testMode) {
        if (!serviceId) {
            return {
                error: {
                    message: 'No voice service ID provided.'
                },
                status: 400,
            };
        }

        const agentIds = [];
        const depConfigGr = new GlideRecord(VoiceAgentConstants.TABLES.NOW_ASSIST_DEPLOYMENT_CONFIG);

        if (serviceId)
            depConfigGr.addQuery('now_assist_deployment', serviceId);

        depConfigGr.addQuery('now_assist_deployment.assistant_type', 'voice');
        if (!testMode)
            depConfigGr.addQuery('now_assist_deployment.active', 'true');
        depConfigGr.query();

        while (depConfigGr.next()) {
            const contextProfileID = depConfigGr.getValue('context_profile');
            const skillProfileM2M = new GlideRecord(VoiceAgentConstants.TABLES.CS_CONTEXT_PROFILE_SKILL);
            skillProfileM2M.addQuery('context_profile', contextProfileID);
            skillProfileM2M.query();

            // get skill profile m2m (aka chat exp and skill)
            while (skillProfileM2M.next()) {
                if (skillProfileM2M.skill_id.skill_table + '' === VoiceAgentConstants.TABLES.AIA_SKILL_METADATA) {
                    const agentMetadataGr = new GlideRecord(VoiceAgentConstants.TABLES.AIA_SKILL_METADATA);

                    if (agentMetadataGr.get(skillProfileM2M.skill_id.skill_document) &&
                        agentIds.indexOf(agentMetadataGr.document_id + '') === -1) {

                        const agentConfigGr = new GlideRecord(VoiceAgentConstants.TABLES.AIA_AGENT_CONFIG);
                        agentConfigGr.addQuery('active', true);
                        agentConfigGr.addQuery('agent', agentMetadataGr.document_id);
                        agentConfigGr.query();

                        if (agentConfigGr.next()) {
                            const agentsGr = new GlideRecord(VoiceAgentConstants.TABLES.AIA_AGENT);
                            const hasAgent = agentsGr.get(agentConfigGr.agent);
                            const hasRightsToAgent = gs.hasRightsTo(`${VoiceAgentConstants.ACL_TYPE.AGENT}/${agentsGr.internal_name}/execute`, null);

                            if (hasAgent && hasRightsToAgent)
                                agentIds.push(agentsGr.getUniqueValue());
                        }
                    }
                }
            }
        }

        return agentIds;
    },

    refreshCacheAndFetchAgents: function(serviceId, fallBackAgent, testMode) {
        var allAgents = [];
        var toolsHavingRequestOverrides = new ToolOverrides().getToolRequestOverridesList();
        var voiceUtils = new sn_voice_aia.VoiceRestUtils();

        var agentIDArr = [];
        var depConfigGr = new GlideRecord(VoiceAgentConstants.TABLES.NOW_ASSIST_DEPLOYMENT_CONFIG);

        if (serviceId)
            depConfigGr.addQuery('now_assist_deployment', serviceId);

        depConfigGr.addQuery('now_assist_deployment.assistant_type', 'voice');
        if (!testMode)
            depConfigGr.addQuery('now_assist_deployment.active', 'true');

        depConfigGr.query();
        if (!depConfigGr.hasNext()) {
            return {
                error: {
                    message: 'Voice service not found or inactive.'
                },
                status: 422,
            };
        }

        // get voice deployment type
        while (depConfigGr.next()) {
            var deploymentAgents = [];

            var contextProfileID = depConfigGr.getValue('context_profile');
            var skillProfileM2M = new GlideRecord(VoiceAgentConstants.TABLES.CS_CONTEXT_PROFILE_SKILL);
            skillProfileM2M.addQuery('context_profile', contextProfileID);
            skillProfileM2M.query();

            // get skill profile m2m (aka chat exp and skill)
            while (skillProfileM2M.next()) {
                if (skillProfileM2M.skill_id.skill_table + '' === VoiceAgentConstants.TABLES.AIA_SKILL_METADATA) {
                    var agentMetadataGr = new GlideRecord(VoiceAgentConstants.TABLES.AIA_SKILL_METADATA);
                    agentMetadataGr.get(skillProfileM2M.skill_id.skill_document);

                    // get agent metadata
                    // check if agent is already added. if not, add it
                    if (agentMetadataGr.document_id && agentIDArr.indexOf(agentMetadataGr.document_id + '') == -1) {
                        var agentConfigGr = new GlideRecord(VoiceAgentConstants.TABLES.AIA_AGENT_CONFIG);
                        agentConfigGr.addQuery('active', true);
                        agentConfigGr.addQuery('agent', agentMetadataGr.document_id);
                        agentConfigGr.query();

                        if (agentConfigGr.next()) {
                            agentIDArr.push(agentMetadataGr.document_id + '');
                            var agentsGr = agentConfigGr.agent.getRefRecord();
                            var tools = [];

                            var toolsM2MGr = new GlideRecord(VoiceAgentConstants.TABLES.AGENT_TOOL_M2M);
                            toolsM2MGr.addQuery('agent', agentsGr.getValue('sys_id'));
                            toolsM2MGr.query();

                            while (toolsM2MGr.next()) {
                                var toolGr = toolsM2MGr.tool.getRefRecord();

                                if (toolGr.isValidRecord()) {
                                    var inputParams = [];

                                    if (toolsHavingRequestOverrides.indexOf(toolGr.getUniqueValue()) > -1)
                                        inputParams = new ToolOverrides().getParametersForTool(toolGr.getUniqueValue());
                                    else
                                        inputParams = this.getInputParamsForTool(toolGr);

                                    //get the Agent Tool M2M description if it exists else get it from Tool record.
                                    var description = toolsM2MGr.getValue('description') || toolGr.getValue('description');
                                    var toolsObj = this.buildToolObj(toolsM2MGr.getUniqueValue(), toolsM2MGr.getValue('name'), description, toolGr.getValue('type'), inputParams.requiredParams, inputParams.optionalParams);
                                    tools.push(toolsObj);
                                }
                            }

                            var requiresStepAuth = this._hasAgentDescriptor(agentConfigGr.getValue('agent_descriptor'), VoiceAgentConstants.AGENT_DESCRIPTOR.REQUIRE_STEP_AUTH);

                            var agentObj = this.buildAgentObj(
                                agentsGr.getValue("sys_id"),
                                voiceUtils.getTranslatedText(agentsGr.getUniqueValue(), "name", serviceId, agentsGr.getDisplayValue("name")),
                                voiceUtils.getTranslatedText(agentsGr.getUniqueValue(), "description", serviceId, agentsGr.getDisplayValue("description")),
                                voiceUtils.getTranslatedText(agentsGr.getUniqueValue(), "role", serviceId, agentsGr.getDisplayValue("role")),
                                voiceUtils.getTranslatedText(agentsGr.getUniqueValue(), "instructions", serviceId, agentsGr.getDisplayValue("instructions")),
                                tools,
                                false,
                                null,
                                serviceId,
                                requiresStepAuth
                            );
                            deploymentAgents.push(agentObj);
                            allAgents.push(agentObj);
                        }
                    }
                }
            }

            var intersectionAgentIds = deploymentAgents.filter(agent => allAgents.some(a => a.id === agent.id)).map(agent => agent.id) || [];
            var publicAgentIds = sn_cs.VASystemObject.getPublicAgentIds(intersectionAgentIds);
            publicAgentIds.forEach(agentId => {
                var agent = deploymentAgents.find(agent => agent.id === agentId);
                agent.isPublic = true;
                agent.authenticationAgent = '';
                const agentConfig = new GlideRecord('sn_aia_agent_config');
                agentConfig.addQuery('agent', agentId);
                agentConfig.query();
                if (agentConfig.next()) {
                    const identifyOnly = this._hasAgentDescriptor(agentConfig.getValue('agent_descriptor'), VoiceAgentConstants.AGENT_DESCRIPTOR.REQUIRE_CALLER_ID);
                    if (identifyOnly)
                        agent.authenticationAgent = 'identification_' + serviceId;
                }
            });

            var lastModified = new Date().toISOString();
            var agentObject = {
                'agents': deploymentAgents,
                'lastModified': lastModified
            };

            var agentsCacheGr = new GlideRecord(VoiceAgentConstants.TABLES.AGENTS_CACHE);
            agentsCacheGr.addQuery('type', 'agents');
            agentsCacheGr.addQuery('voice_service', depConfigGr.getValue('now_assist_deployment'));
            agentsCacheGr.query();

            if (agentsCacheGr.next()) {
                agentsCacheGr.setValue('json_object', JSON.stringify(agentObject));
                agentsCacheGr.setValue('last_refreshed_at', new GlideDateTime());
                agentsCacheGr.update();
            } else {
                agentsCacheGr = new GlideRecord(VoiceAgentConstants.TABLES.AGENTS_CACHE);
                agentsCacheGr.initialize();
                agentsCacheGr.setValue('type', 'agents');
                agentsCacheGr.setValue('voice_service', depConfigGr.getValue('now_assist_deployment'));
                agentsCacheGr.setValue('json_object', JSON.stringify(agentObject));
                agentsCacheGr.setValue('last_refreshed_at', new GlideDateTime());
                agentsCacheGr.insert();
            }
        }

        if (fallBackAgent)
            allAgents.push(fallBackAgent);

        return {
            'agents': allAgents,
            'lastModified': lastModified
        };
    },

    refreshCacheAfterToolsUpdate: function(toolId) {
        var aggTools = new GlideAggregate(VoiceAgentConstants.TABLES.AGENT_TOOL_M2M);
        aggTools.addQuery('tool', toolId);
        aggTools.addQuery('agent.agent_type', 'voice');
        aggTools.addAggregate('COUNT');
        aggTools.query();
        aggTools.next();
        var updatedTools = parseInt(aggTools.getAggregate('COUNT'));
        if (updatedTools > 0)
            this.refreshCacheAndFetchAgents();
    },

    _hasAgentDescriptor: function(descriptorValue, flag) {
        return descriptorValue ? descriptorValue.split(',').some(function(descriptor) { return descriptor.trim() === flag; }) : false;
    },

    buildAgentObj: function(id, name, description, role, instructions, tools, isPublic, metadata, serviceId, requiresStepAuth) {
        const agentObj = {
            id,
            name,
            description,
            role,
            instructions,
            tools,
            isPublic,
        };

        if (metadata)
            agentObj.metadata = metadata;

        if (!isPublic) {
            agentObj.authenticationAgent = 'authentication_' + serviceId;
        }

        if (requiresStepAuth)
            agentObj.require_step_auth = true;

        return agentObj;
    },

    buildToolObj: function(agentToolM2MId, name, description, type, requiredParameters, optionalParameters, metadata, invokeCacheFlush) {
        const toolObj = {
            id: agentToolM2MId,
            name,
            description,
            type,
            invokeCacheFlush: invokeCacheFlush || false,
            'requiredParameters': requiredParameters || [],
            'optionalParameters': optionalParameters || []
        };

        if (metadata)
            toolObj['metadata'] = metadata;
        return toolObj;
    },

    getInputParamsForTool: function(toolGr) {
        if (!toolGr.isValidRecord())
            return;
        var toolType = toolGr.getValue('type');
        switch (toolType) {
            case VoiceAgentConstants.FDIH_TYPE_ACTION:
            case VoiceAgentConstants.FDIH_TYPE_FLOW:
            case VoiceAgentConstants.FDIH_TYPE_SUBFLOW:
                return this._getInputParamsForFDIH(toolGr);
            case VoiceAgentConstants.TOOL_TYPE_CRUD:
                return this._getInputParamsForCRUDTool(toolGr);
            case VoiceAgentConstants.TOOL_TYPE_SCRIPT:
                return this._getInputParamsForScriptTool(toolGr);
            case VoiceAgentConstants.TOOL_TYPE_CAPABILITY:
                return this._getInputParamsForCapabilityTool(toolGr);
            case VoiceAgentConstants.TOOL_TYPE_KNOWLEDGE_GRAPH:
                return this._getInputParamsForKnowledgeGraph(toolGr);
            default:
                return {
                    requiredParams: [],
                    optionalParams: []
                };
        }
    },

    isPublicAgent: function(agentId) {
        if (!agentId) return false;
        const publicAgentIds = sn_cs.VASystemObject.getPublicAgentIds([agentId]);
        return publicAgentIds.includes(agentId);
    },

    _getInputParamsForKnowledgeGraph: function(toolGr) {
        var inputParams = {
            requiredParams: ['query', 'knowledge_graph'],
            optionalParams: []
        };

        var toolM2MGr = new GlideRecord(VoiceAgentConstants.TABLES.AGENT_TOOL_M2M);
        toolM2MGr.addActiveQuery();
        toolM2MGr.query('tool', toolGr.getUniqueValue());
        toolM2MGr.setLimit(1);
        toolM2MGr.query();
        toolM2MGr.next();
        var paramList = toolM2MGr.inputs;

        if (paramList) {
            const paramArr = JSON.parse(paramList);
            if (paramArr.length > 0) {
                paramArr.forEach(param => {
                    var paramName = param.name;
                    if (param.mandatory && !inputParams.requiredParams.includes(paramName))
                        inputParams.requiredParams.push(paramName);
                    else {
                        inputParams.optionalParams.push(paramName);
                    }
                });
            }
        }

        return inputParams;
    },

    _getInputParamsForFDIH: function(toolGr) {
        const inputParams = {
            requiredParams: [],
            optionalParams: []
        };
        const inputTable = toolGr.getValue('type') === VoiceAgentConstants.FDIH_TYPE_ACTION ? VoiceAgentConstants.TABLES.ACTION_INPUT : VoiceAgentConstants.TABLES.FLOW_INPUT;
        const inputGr = new GlideRecord(inputTable);

        inputGr.addActiveQuery();
        inputGr.addQuery('model_id', toolGr.getValue('target_document'));
        inputGr.query();

        while (inputGr.next()) {
            const inputParamObj = {
                name: inputGr.getValue('element'),
                type: 'string',
                description: inputGr.getValue('description') || '',
            };

            if (inputGr.getValue('internal_type') === VoiceAgentConstants.FDIH_INPUT_TYPE_CHOICE) {
                const enumValues = [];
                const enumGr = new GlideRecord('sys_choice');
                enumGr.addQuery('name', inputGr.getValue('name'));
                enumGr.addQuery('element', inputGr.getValue('element'));
                enumGr.query();

                while (enumGr.next()) {
                    enumValues.push(enumGr.getValue('label'));
                }

                inputParamObj.enum = enumValues;
            }

            if (inputGr.getValue('mandatory') == true)
                inputParams.requiredParams.push(inputParamObj);
            else
                inputParams.optionalParams.push(inputParamObj);
        }

        return inputParams;
    },

    _getInputParamsForCRUDTool: function(toolGr) {
        var params = this._getInputParamsForScriptTool(toolGr);
        return {
            requiredParams: params.requiredParams,
            optionalParams: params.optionalParams.filter(tool => tool !== VoiceAgentConstants.TOOL_INPUT_CRUD)
        };
    },

    _getInputParamsForScriptTool: function(toolGr) {
        const inputParams = {
            requiredParams: [],
            optionalParams: []
        };
        const inputSchema = toolGr.getValue('input_schema');

        if (inputSchema) {
            const inputsArr = JSON.parse(inputSchema);

            if (inputsArr.length > 0) {
                inputsArr.forEach(input => {
                    const inputParamObj = {
                        name: input.name,
                        type: 'string',
                        description: input.description || '',
                    };

                    if (input.mandatory)
                        inputParams.requiredParams.push(inputParamObj);
                    else
                        inputParams.optionalParams.push(inputParamObj);
                });
            }
        }

        return inputParams;
    },

    _getInputParamsForCapabilityTool: function(toolGr) {
        const inputParams = {
            requiredParams: [],
            optionalParams: []
        };

        const capAttrGr = new GlideRecord(VoiceAgentConstants.TABLES.CAPABILITY_ATTR);
        capAttrGr.addActiveQuery();
        capAttrGr.addQuery('type', 'input');
        capAttrGr.addQuery('capability', toolGr.getValue('target_document'));
        capAttrGr.query();

        while (capAttrGr.next()) {
            const inputParamObj = {
                name: capAttrGr.getValue('name'),
                type: 'string',
                description: capAttrGr.getValue('description') || '',
            };

            if (capAttrGr.getValue('mandatory') == true)
                inputParams.requiredParams.push(inputParamObj);
            else
                inputParams.optionalParams.push(inputParamObj);
        }

        return inputParams;
    },

    type: 'VoiceAgentUtilsSNC'
};