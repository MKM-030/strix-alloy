(function process(/*RESTAPIRequest*/ request, /*RESTAPIResponse*/ response) {
    if (!new VoiceRestUtils().isKaaAuthenticated(request, response) && !new VoiceRestUtils().validateServiceAuthorization(request, response))
        return;

	if (!new VoiceRestUtils().validateServiceId(request, response))
		return;

    response = new sn_voice_aia.VoiceConversationManager().createConversation(request, response);

})(request, response);