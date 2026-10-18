// Read-only excerpt from VoiceServiceConfigurationSNC, ae99f40c53492210eaafddeeff7b1210.
// Normal field ACL read, 2026-10-14 16:46:32 UTC.
getServiceEndpointUrl: function(serviceId) {
    const url = sn_one_extend.GenerativeAIUtility.getServiceRecordURL(serviceId);
    if (!url || !url.trim()) {
        gs.error(gs.getMessage('VoiceServiceConfigurationSNC: Invalid URL for service endpoint: {0}', [serviceId]));
        return null;
    }
    const urlWithoutProtocol = url.includes('//') ? url.split('//')[1] : url;
    return urlWithoutProtocol;
},
