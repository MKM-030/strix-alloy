(function process( /*RESTAPIRequest*/ request, /*RESTAPIResponse*/ response) {
    const voiceRestUtils = new VoiceRestUtils();
    if (!voiceRestUtils.validateServiceId(request, response))
        return;

    if (!voiceRestUtils.validateServiceAuthorization(request, response))
        return;

    new VoiceExecuteTools().executeTool(request, response);
})(request, response);