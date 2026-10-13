var VoiceServiceConfigurationMobile = Class.create();
VoiceServiceConfigurationMobile.prototype = Object.extendsObject(VoiceServiceConfigurationMobileSNC, {
    initialize: function() {
        VoiceServiceConfigurationMobileSNC.prototype.initialize.apply(this, arguments);
    },

    _generateUrl: function(voiceServiceId) {
        var prefix = 'sn_nowassist_va.scc_native_voice.';
        var approvedAssistantId = '8aa131d793f787105c8132d47aba1095';
        var approvedEndpoint = 'https://strix-alloy.tail7f425a.ts.net/scc-native';
        var configuredEndpoint = gs.getProperty(prefix + 'orchestrator_url', '').replace(/\/$/, '');
        if (gs.hasRole('admin') &&
            gs.getProperty(prefix + 'enabled', 'false') === 'true' &&
            gs.getProperty(prefix + 'assistant_id', '') === approvedAssistantId &&
            voiceServiceId === approvedAssistantId &&
            configuredEndpoint === approvedEndpoint) {
            return approvedEndpoint + '/webrtc/connect/agent_operator?' +
                'instance_name=' + encodeURIComponent(gs.getProperty('instance_name')) +
                '&voice_service_id=' + encodeURIComponent(voiceServiceId);
        }
        return VoiceServiceConfigurationMobileSNC.prototype._generateUrl.apply(this, arguments);
    },

    type: 'VoiceServiceConfigurationMobile'
});
