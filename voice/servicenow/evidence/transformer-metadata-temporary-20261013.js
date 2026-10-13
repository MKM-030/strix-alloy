(function(inputs) {
(function(inputs) {
    // Temporary structural diagnostic; expires automatically and changes no request.
    try {
        if (new Date().getTime() > 1791887387562) return;
        var p = inputs && inputs.prompt_data;
        if (!p || String(p.aiConfig) !== "4780c7e193f747d0e7f2b9fa6aba1030") return;
        var containers = ["prompt_data","request_data","requestData","inputs","payload","data","metadata","context","params","parameters","attributes","additional_context","additionalContext","executionContext","execution_context","agentContext","agent_context","clientVariables","client_variables","conversation","aiAgentContext","ai_agent_context"];
        var fields = ["agent_id","agentId","ai_agent_id","aiAgentId","agent","execution_plan_id","executionPlanId","execution_plan","executionPlan","context_id","contextId","conversation_id","conversationId","session_id","sessionId","nowSessionId","clientSessionId","voiceSessionId","voice_service_id","voiceServiceId","voice_assistant","assistant_id","assistantId","assistant","providerAppId","provider_app_id","inbound_id","inboundId","channel","conversationChannel","conversation_channel","deploymentChannel","deployment_channel","clientApp","client_app","isTest","skill_id","skillId","capability_id","capabilityId","aiConfig","model","requestId","request_id"];
        var rows = [], seen = [], remaining = 100;
        function walk(value, path, depth) {
            if (depth > 5 || remaining <= 0 || !value || typeof value !== "object") return;
            for (var s = 0; s < seen.length; s++) if (seen[s] === value) return;
            seen.push(value);
            var keys = containers.concat(fields);
            for (var i = 0; i < keys.length && remaining > 0; i++) {
                var key = keys[i], child;
                try { if (!(key in value)) continue; child = value[key]; } catch (ignoredAccess) { continue; }
                var type = child === null ? "null" : typeof child;
                rows.push({path:path+"."+key,type:type,
                    sccAgent:typeof child==="string" && child==="a4a9438393738354e7f2b9fa6aba101d",
                    sccChannel:typeof child==="string" && child==="a40a3a0f93fb4354e7f2b9fa6aba1001",
                    sccContext:typeof child==="string" && child==="c623e20f93374354e7f2b9fa6aba1081",
                    sccInbound:typeof child==="string" && child==="scc-local-voice"});
                remaining--;
                if (containers.indexOf(key) !== -1) {
                    if ((key==="request_data" || key==="requestData") && typeof child==="string" && child.length <= 1048576) {
                        try { child=JSON.parse(child); } catch (ignoredJson) { child=null; }
                    }
                    walk(child,path+"."+key,depth+1);
                }
            }
        }
        walk(inputs,"inputs",0);
        gs.info("[SCC_META_20261013_A] "+JSON.stringify({rows:rows}));
    } catch (ignoredDiagnostic) {}
})(inputs);
    var p = inputs && inputs.prompt_data;
    if (!p || p.prompt === null || typeof p.prompt === "undefined") {
        throw new Error("Strix Alloy: inputs.prompt_data.prompt fehlt.");
    }
    var prompt = String(p.prompt);
    if (!prompt.replace(/\s/g, "")) {
        throw new Error("Strix Alloy: Der Prompt ist leer.");
    }
    var model = p.model ? String(p.model) : "halogen-v2";
    var maxTokens = parseInt(p.max_tokens, 10);
    if (!isFinite(maxTokens) || maxTokens < 1) { maxTokens = 1024; }
    maxTokens = Math.min(maxTokens, 2048);
    var temperature = parseFloat(p.temperature);
    if (!isFinite(temperature)) { temperature = 0; }
    temperature = Math.max(0, Math.min(temperature, 2));
    var body = {model:model,messages:[{role:"user",content:prompt}],max_tokens:maxTokens,temperature:temperature,stream:false};
    // ReAct V3 expects an object; keep other skills and older array templates unchanged.
    if (String(p.aiConfig) === "4780c7e193f747d0e7f2b9fa6aba1030") { body.response_format = {type:"json_object"}; }
    return {body:body,headers:{}};
})(inputs);