(function process(/*RESTAPIRequest*/ request, /*RESTAPIResponse*/ response) {
    const voiceRestUtils = new VoiceRestUtils();
    if (!voiceRestUtils.validateServiceId(request, response))
        return;

    if (!voiceRestUtils.validateServiceAuthorization(request, response))
        return;

	var payload = request.body.data;
	var serviceId = payload.serviceId;

	var testMode = voiceRestUtils.isTestMode(request);
	var agentUtils = new VoiceAgentUtils();
	var authorizedAgentIds = agentUtils.getAuthorizedAgentIds(serviceId, testMode);
    // Explicit opt-in keeps the native authorized-agent array contract unchanged.
    if (payload.assistantSettingsVersion === 1) {
        var header = String(request.getHeader('Authorization') || '');
        var jwt = /^Bearer ([A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)$/i.exec(header);
        var validAgents = Array.isArray(authorizedAgentIds) && authorizedAgentIds.length > 0;
        if (validAgents) {
            for (var i = 0; i < authorizedAgentIds.length; i++) {
                if (typeof authorizedAgentIds[i] !== 'string' || !/^[0-9a-f]{32}$/.test(authorizedAgentIds[i])) {
                    validAgents = false;
                    break;
                }
            }
        }
        var audienceMatches = false;
        // Platform authentication and native validation above authenticate the JWT.
        // Require the native service binding again; opaque OAuth has no such binding.
        if (jwt && header.length <= 8192 && gs.getUserID() && gs.getUserName() !== 'guest' && validAgents) {
            try {
                var bound = JSON.parse(new sn_auth.VoiceServiceInfoRequestor().getVoiceServiceInfo() || '{}');
                audienceMatches = bound.voice_service_id === serviceId;
            } catch (ignored) {}
        }
        if (!audienceMatches) {
            response.setStatus(403);
            response.setBody({detail:'Assistant settings authorization rejected'});
            return;
        }
        try {
            var settings = new LocalLLMVoiceAssistantSettings().getSettings(serviceId);
            response.setBody({authorized_agents:authorizedAgentIds,assistant_settings:settings});
            response.setStatus(200);
        } catch (ignoredSettingsError) {
            response.setStatus(503);
            response.setBody({detail:'Assistant settings unavailable'});
        }
        return;
    }
	response.setBody(authorizedAgentIds);
	response.setStatus(200);

})(request, response);