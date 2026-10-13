(function process( /*RESTAPIRequest*/ request, /*RESTAPIResponse*/ response) {
    if (!new VoiceRestUtils().isKaaAuthenticated(request, response))
        return;

    if (!new VoiceRestUtils().validateServiceId(request, response))
        return;

    var payload = request.body.data;
    var requiredParameters = ['serviceId'];
    var restUtils = new VoiceRestUtils();

    var errors = restUtils.validatePayload(payload, requiredParameters);
    if (errors.length > 0) {
        response.setStatus(422);
        response.setBody({
            detail: errors
        });
        return;
    }

    var serviceId = payload.serviceId;
    var cacheDate = payload.cacheDate; //optional
    if (cacheDate) {
        //converting to correct format to use within glide - "2025-05-06T21:27:07.292Z" to "2025-05-06 21:27:07"
        cacheDate = cacheDate.split('.')[0].replace('T', ' ');
    }
    var testMode = restUtils.isTestMode(request);
    var voiceSystemConfig = {};

    var configBuilder = new VoiceServiceConfiguration();
    voiceSystemConfig = configBuilder.getVoiceSystemConfig(serviceId, cacheDate, testMode);

    if (voiceSystemConfig.error) {
        response.setStatus(voiceSystemConfig.error.status);
        response.setBody({
            detail: voiceSystemConfig.error.message
        });
        return;
    }

    response.setBody(voiceSystemConfig);
    response.setStatus(200);

})(request, response);