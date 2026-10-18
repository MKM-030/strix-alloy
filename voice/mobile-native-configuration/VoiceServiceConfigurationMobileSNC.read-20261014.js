const VoiceServiceConfigurationMobileSNC = Class.create();
VoiceServiceConfigurationMobileSNC.prototype = {
    initialize: function() {},

    getMobileVoiceConfigurations: function() {
        const deploymentChannelGr = new GlideRecord(VoiceAgentConstants.TABLES.NOW_ASSIST_DEPLOYMENT_CHANNEL);
        const mobileChannels = [];

        deploymentChannelGr.addQuery('document_table', 'IN', Object.values(VoiceAgentConstants.MOBILE_TABLES));
        deploymentChannelGr.addQuery('active', true);
        deploymentChannelGr.addQuery('now_assist_deployment.assistant_type', 'voice');
        deploymentChannelGr.addQuery('now_assist_deployment.active', true);
        deploymentChannelGr.query();

        while (deploymentChannelGr.next()) {
            const voiceServiceId = deploymentChannelGr.getValue('now_assist_deployment');
            const voiceWebhookURL = this._generateUrl(voiceServiceId);
            const table = deploymentChannelGr.getValue('document_table');

            const mobileConfig = {
                voiceServiceId,
                voiceWebhookURL,
                mobileChannelType: VoiceAgentConstants.MOBILE_TYPE_MAP[table],
                mobileChannelId: deploymentChannelGr.getValue('document_id'),
            };
            mobileChannels.push(mobileConfig);
        }

        return mobileChannels;
    },

    _generateUrl: function(voiceServiceId) {
        if (!voiceServiceId) {
            gs.error(gs.getMessage('Voice service ID is not provided.'));
            return null;
        }
        const instanceName = gs.getProperty('instance_name');
        const endPointUrl = new VoiceServiceConfiguration().getServiceEndpointUrl(VoiceAgentConstants.AVA_SERVICE_ID);

        if (!endPointUrl) return '-'; // so that UI can use this to trigger error/info message

        const instanceUrl = `https://${endPointUrl}/webrtc/connect/agent_operator?`;
        const params = [
            `instance_name=${instanceName}`,
            `voice_service_id=${voiceServiceId}`
        ];
        return instanceUrl + params.join('&');
    },

    type: 'VoiceServiceConfigurationMobileSNC'
};