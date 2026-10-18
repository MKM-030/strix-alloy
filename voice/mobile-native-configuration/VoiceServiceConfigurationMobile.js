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
            this._logSccRoute('local', true, true);
            return approvedEndpoint + '/webrtc/connect/agent_operator?' +
                'instance_name=' + encodeURIComponent(gs.getProperty('instance_name')) +
                '&voice_service_id=' + encodeURIComponent(voiceServiceId);
        }
        this._logSccRoute('snc', voiceServiceId === approvedAssistantId,
            configuredEndpoint === approvedEndpoint);
        return VoiceServiceConfigurationMobileSNC.prototype._generateUrl.apply(this, arguments);
    },

    _logSccRoute: function(route, approvedService, endpointMatches) {
        // Bounded route facts only; never log caller IDs, URLs or credentials.
        // Diagnostics must not alter the existing routing or authentication.
        try {
            gs.info('[SCC Mobile Voice Route] ' + JSON.stringify({
                route: route,
                approved_service: approvedService,
                admin: gs.hasRole('admin') === true,
                enabled: gs.getProperty('sn_nowassist_va.scc_native_voice.enabled', 'false') === 'true',
                endpoint_matches: endpointMatches
            }));
        } catch (ignored) {}
    },

    type: 'VoiceServiceConfigurationMobile'
});
