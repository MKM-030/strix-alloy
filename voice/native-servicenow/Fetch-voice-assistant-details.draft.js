function transform(input) {
    const { voiceAssistantSysId } = input;

    try {
        if (gs.nil(voiceAssistantSysId)) {
            gs.error("Deployment id cannot be null");
            throw "Deployment id cannot be null";
        }
        /* 
         * instance name can be name.service-now.com or name.lab.service-now.com
         * glide.servlet.uri returns the full URL, e.g., https://name.service-now.com or https://name.lab.service-now.com
         * we need to extract the instance name from the URL
         * e.g., name or name.lab
         */
        const instanceUri = gs.getProperty("glide.servlet.uri");
        const instanceName = instanceUri.slice(instanceUri.indexOf("//") + 2, instanceUri.indexOf(".service-now.com"));
        let orchestratorUrl = new sn_nowassist_va.NowAssistVoiceTestingUtil().getOrchestratorBaseUrl();
        // SCC native voice demo: disabled by default, restricted to one dedicated
        // assistant and the approved adapter endpoint. Retain native OAuth PKCE.
        const sccVoiceEnabled = gs.getProperty('sn_nowassist_va.scc_native_voice.enabled', 'false') === 'true';
        const sccVoiceAssistantId = gs.getProperty('sn_nowassist_va.scc_native_voice.assistant_id', '');
        const sccVoiceEndpoint = gs.getProperty('sn_nowassist_va.scc_native_voice.orchestrator_url', '').replace(/\/$/, '');
        const sccApprovedEndpoint = 'https://strix-alloy.tail7f425a.ts.net/scc-native';
        if (sccVoiceEnabled && gs.hasRole('admin') &&
            /^[0-9a-f]{32}$/.test(sccVoiceAssistantId) &&
            sccVoiceAssistantId === voiceAssistantSysId &&
            sccVoiceEndpoint === sccApprovedEndpoint) {
            orchestratorUrl = sccApprovedEndpoint;
        }
        const deployment = global.NowAssistDeployment.getBySysId(voiceAssistantSysId);
        const firstDeploymentConfig = deployment.deploymentConfigList[0];
        const returned_attrs = ["language", "voice_profile"];
        const attrs = {};
        const configLanguages = [];
        const langGr = new GlideRecord(sn_voice_aia.VoiceAgentConstants.TABLES.VOICE_LANGUAGE_CONFIG);
        let selectedLanguageDisplayValue;
        langGr.addQuery('deployment', voiceAssistantSysId);
        langGr.addActiveQuery();
        langGr.addNotNullQuery('tts_config');
        langGr.orderBy('sequence');
        langGr.query();

        while (langGr.next()) {
            const ttsConfigId = langGr.getValue('tts_config');
            const ttsGr = new GlideRecord(sn_voice_aia.VoiceAgentConstants.TABLES.VOICE_TTS_CONFIG);
            ttsGr.get(ttsConfigId);    
            configLanguages.push({
                "code": ttsGr.getValue('language'), 
                "label": ttsGr.getDisplayValue('language'),
				"persona": ttsGr.getValue("name") 
            });
        }
        returned_attrs.forEach((attr, index) => {
            let key = returned_attrs[index];
            if (firstDeploymentConfig.attributeNameValueMap[key])
                attrs[key] = firstDeploymentConfig.attributeNameValueMap[key];
        });
        const gr = new GlideRecord(sn_voice_aia.VoiceAgentConstants.TABLES.VOICE_TTS_CONFIG);
        gr.addQuery("language", attrs["language"]);
        gr.setLimit(1);
        gr.query();
        if (gr.next()) {
            selectedLanguageDisplayValue = gr.getDisplayValue("language");
        }
        return {
            name: deployment.name,
            contextProfileId: firstDeploymentConfig.contextProfile.sysId,
            attrs,
            selectedLanguageDisplayValue,
            configLanguages,
            instanceName,
            orchestratorUrl
        };
    } catch (e) {
        gs.error(gs.getMessage("Unable to retrieve deployment config attributes")); 
        return {
            success: false
        };
    }
}