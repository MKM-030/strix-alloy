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
	response.setBody(authorizedAgentIds);
	response.setStatus(200);

})(request, response);