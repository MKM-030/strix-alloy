(function process( /*RESTAPIRequest*/ request, /*RESTAPIResponse*/ response) {
    if (!new VoiceRestUtils().isKaaAuthenticated(request, response))
        return;

    if (!new VoiceRestUtils().validateServiceId(request, response))
        return;

    const payload = request.body.nextEntry();
    response = new sn_voice_aia.VoiceConversationManager().endConversation(payload, request.headers, response);

})(request, response);