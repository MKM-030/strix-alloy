(function process(/*RESTAPIRequest*/ request, /*RESTAPIResponse*/ response) {
    if (!new VoiceRestUtils().isKaaAuthenticated(request, response))
        return;

    if (!new VoiceRestUtils().validateServiceId(request, response))
        return;

    const payload = request.body.data;
    const serviceId = payload.serviceId;
    let cacheDate = payload.cacheDate; //optional

    if (cacheDate) {
        //converting to correct format to use within glide - '2025-05-06T21:27:07.292Z' to '2025-05-06 21:27:07'
        cacheDate = cacheDate.split('.')[0].replace('T',' ');
    }

    const callSource = request.getHeader(VoiceAgentConstants.VOICE_SOURCE_HEADER) ?? VoiceAgentConstants.VOICE_SOURCE.PHONE;
    const testMode = new VoiceRestUtils().isTestMode(request);
    const agentUtils = new VoiceAgentUtils();
    const agentsObject = agentUtils.processGetAllAgents(cacheDate, serviceId, callSource, testMode);

    if (agentsObject.error) {
        response.setBody({
            detail: agentsObject.error.message
        });
        response.setStatus(agentsObject.status);
        return;
    }

    response.setBody(agentsObject);
    response.setStatus(200);

})(request, response);