var VoiceRestUtilsSNC = Class.create();
VoiceRestUtilsSNC.prototype = {
    initialize: function() {},

    /**
     * Constructs the expected REST error response.
     *
     * @param {VoiceErrorCode} error - One of the specified errors in VoiceAgentConstants.ERROR_CODES,
     *                                 containing the code and message
     * @param {string} statusCode - The HTTP status code for the error
     * @returns {Object} The error response
     */
    constructErrorResponse: function(error, statusCode) {
        return {
            error: {
                code: error.code,
                message: error.message,
            },
            status: statusCode
        };
    },

    validatePayload: function(payload, params) {
        var errors = [];
        for (var i = 0; i < params.length; i++) {
            var param = params[i];
            var paramValue = payload[param];
            if (paramValue === undefined || paramValue === null || paramValue === '') {
                errors.push({
                    loc: ['body', param],
                    msg: 'Missing required field',
                    type: 'value_error.missing'
                });
            }
        }
        return errors;
    },

    isKaaAuthenticated: function(request, response) {
        if (gs.getSession().getKaaProfile())
            return true;

        response.setStatus(401);
        response.setBody({
            error: gs.getMessage('KAA authentication required')
        });
        return false;
    },

    /**
     * Determines whether the current request originates from the Voice testing UI.
     * The testing UI sends clientApp = 'admin_test' so a voice assistant can be tested
     * while still Inactive.
     *
     * @param {RESTAPIRequest} request - The incoming REST request
     * @returns {boolean} true if the request is flagged as coming from the testing UI
     */
    isTestMode: function(request) {
        var data = (request && request.body && request.body.data) ? request.body.data : {};
        return data.clientApp === 'admin_test';
    },

    validateServiceId: function(request, response) {
        const serviceId = request.body.data.serviceId;
        try {
            // Check if serviceId is provided
            if (!serviceId || serviceId === null || serviceId === undefined || serviceId === '') {
                if (response) {
                    response.setStatus(400);
                    response.setBody({
                        detail: 'Missing required parameter: serviceId. A valid voice service ID must be provided.'
                    });
                }
                return false;
            }

            // Query the sys_now_assist_deployment table
            var gr = new GlideRecord('sys_now_assist_deployment');
            gr.addQuery('sys_id', serviceId);
            gr.addQuery('assistant_type', 'voice');
            gr.query();

            if (!gr.next()) {
                if (response) {
                    response.setStatus(404);
                    response.setBody({
                        detail: 'Invalid serviceId. The provided service ID does not correspond to an existing voice service.'
                    });
                }
                return false;
            }

            // Check if the service is active. The active-state check is bypassed when the
            // request originates from the Voice testing UI (flag relayed back by the orchestrator),
            // allowing an Inactive voice assistant to be tested without activating it first.
            var activeValue = gr.getValue('active');
            var isInactive = !activeValue || activeValue === 'false' || activeValue === false || activeValue === '0';
            if (isInactive && !this.isTestMode(request)) {
                if (response) {
                    response.setStatus(422);
                    response.setBody({
                        detail: 'Invalid serviceId. The provided service ID corresponds to a voice service that is inactive.'
                    });
                }
                return false;
            }

            // Set voice session language
            const conversationId = request?.body?.data?.conversationId || '';
            if (conversationId) {
                const interaction = new VoiceConversationUtils().getInteractionFromConversation(conversationId);
                const language = (interaction && interaction.getValue('user_language')) || this.getVoiceServiceLanguage(serviceId);
                gs.getSession().putClientData(VoiceAgentConstants.VOICE_SESSION_LANGUAGE, language);
            }

            return true;

        } catch (e) {
            gs.error('Error validating serviceId: ' + e.message);
            if (response) {
                response.setStatus(500);
                response.setBody({
                    detail: 'Internal server error during serviceId validation.'
                });
            }
            return false;
        }
    },

    validateServiceAuthorization: function(request, response) {
        const serviceId = request.body.data.serviceId;
        if (!serviceId || serviceId === null || serviceId === undefined || serviceId === '') {
            if (response) {
                response.setStatus(400);
                response.setBody({
                    detail: 'Missing required parameter: serviceId. A valid voice service ID must be provided.'
                });
            }
            return false;
        }

        const authHeader = request.getHeader("Authorization") || "";
        const token = authHeader.replace(/^Bearer\s+/i, "");

        // Ensure we actually have a token
        if (!token || token === authHeader) {
            // No Bearer token found (shouldn't happen if auth passed, but defensive)
            response.setStatus(403);
            response.setBody({
                detail: `User is not authorized for voice service ${serviceId}`
            });
            return false;
        }

        const tokenParts = token.split('.');
        const isJWT = tokenParts.length === 3 && tokenParts.every(part => part.length > 0);
        const isOpaqueOAuth = !isJWT;

        if (isOpaqueOAuth) {
            gs.warn("ServiceNow Otto For Voice: Opaque OAuth token detected - bypassing per-service authentication validation.");
            return true;
        }
        const serviceInfoRequestor = new sn_auth.VoiceServiceInfoRequestor();

        let authorizedService;
        try {
            authorizedService = JSON.parse(serviceInfoRequestor.getVoiceServiceInfo() || '{}');
        } catch (e) {
            gs.error(`Failed to parse VoiceServiceInfo: ${e}`);
            authorizedService = null; // treat parse errors as unauthorized
        }

        const isAuthorized =
            authorizedService?.voice_service_id &&
            authorizedService.voice_service_id === serviceId;

        if (!isAuthorized) {
            if (response) {
                response.setStatus(403);
                response.setBody({
                    detail: `User is not authorized for voice service ${serviceId}`
                });
            }
            return false;
        }

        return true;
    },

    /**
     * Checks if a voice source is from a WebRTC source (mobile, platform, or textchat)
     * @param {string} voiceSource - The voice source value
     * @returns {boolean} - True if the source is WebRTC-based, false otherwise
     */
    isWebRTCConversation: function(voiceSource) {
        if (!voiceSource) {
            return false;
        }
        return voiceSource === VoiceAgentConstants.VOICE_SOURCE.MOBILE_WEBRTC ||
            voiceSource === VoiceAgentConstants.VOICE_SOURCE.PLATFORM_WEBRTC ||
            voiceSource === VoiceAgentConstants.VOICE_SOURCE.PLATFORM_TEXTCHAT;
    },

    /**
     * Retreives the language set for the voice service.
     * 
     * @param {string} serviceId - ServiceId used to retrieve language
     * @returns {string} language code
     */
    getVoiceServiceLanguage: function(serviceId) {
        const interactionLanguage = gs.getSession().getClientData(VoiceAgentConstants.VOICE_SESSION_LANGUAGE);
        if (interactionLanguage)
            return interactionLanguage;

        const deployment = global.NowAssistDeploymentConfig.getByDeploymentSysId(serviceId);
        var config = deployment && deployment.length ? deployment[0] : null;
        return config && config.getAttributeValue(VoiceAgentConstants.CONFIG_ATTRIBUTES.LANGUAGE) ? config.getAttributeValue(VoiceAgentConstants.CONFIG_ATTRIBUTES.LANGUAGE) : gs.getSession().getLanguage();
    },

    /**
     * Queries and retrieves translated text values
     * 
     * @param {object} docSysId - The sysID of the document the field is from
     * @param {string} fieldName - Name of the field
     * @param {string} serviceId - ServiceId used to retrieve language
     * @param {string} fallback - The fallback message if text could not be found
     * @returns {string} translated text
     */
    getTranslatedText: function(docSysId, fieldName, serviceId, fallback) {
        var gr = new GlideRecord(VoiceAgentConstants.TABLES.TRANSLATED_TEXT);
        gr.addQuery("documentkey", docSysId);
        gr.addQuery("fieldname", fieldName);
        gr.addQuery("language", this.getVoiceServiceLanguage(serviceId));
        gr.setLimit(1);
        gr.query();
        return gr.next() ? gr.getValue("value") : fallback;
    },

    /**
     * Queries and retrieves translated field values
     * 
     * @param {object} value - The value of the field to translate
     * @param {string} element - element name of the field
     * @param {string} table - name of table the field is in
     * @param {string} serviceId - ServiceId used to retrieve language
     * @param {string} fallback - The fallback message if text could not be found
     * @returns {string} translated text
     */
    getTranslatedField: function(value, table, element, serviceId) {
        var gr = new GlideRecord(VoiceAgentConstants.TABLES.TRANSLATED_FIELD);
        gr.addQuery("value", value);
        gr.addQuery("element", element);
        gr.addQuery("name", table);
        gr.addQuery("language", this.getVoiceServiceLanguage(serviceId));
        gr.setLimit(1);
        gr.query();
        return gr.next() ? gr.getValue("label") : value;
    },

    /**
     * Retreives the greeting message in the right language set by voice service config
     * 
     * @param {string} contextId - Id of the context profile
     * @param {string} serviceId - ServiceId used to retrieve language
     * @returns {string} translated greeting message or translated default greeting
     */
    getGreetingMessage: function(contextId, serviceId) {
        var gr = new GlideRecord(VoiceAgentConstants.TABLES.CS_CONTEXT_PROFILE_MESSAGE);
        gr.addQuery("context_profile", contextId);
        gr.addQuery("type", "greeting");
        gr.setLimit(1);
        gr.query();
        if (gr.next()) {
            return this.getTranslatedText(gr.getUniqueValue(), "message", serviceId, gr.getValue("message"));
        }

        // fallback - use the default greeting
        var language = this.getVoiceServiceLanguage(serviceId) || gs.getSession().getLanguage();
        return gs.getMessageLang("Hi, I am your AI Assistant. How can I help you today? This call is recorded for quality purposes.", language);
    },

	/**
     * Retrieves key details about the current ServiceNow instance.
     * @returns {Object} An object containing instance information.
     */
    getInstanceInfo: function() {
        var res = {};
        res.install_name = gs.getProperty('glide.installation.name', '');
        res.instance_name = gs.getProperty('instance_name', ''); 
        res.instance_id = gs.getProperty('instance_id', ''); 
        res.build_tag = gs.getProperty('glide.buildtag', '');
        res.build_date = gs.getProperty('glide.builddate', '');
        res.release_candidate = gs.getProperty('glide.release_candidate', 'false');
        res.version = this._getBuildVersion();
        return res;
    },

    /**
     * Retrieves information for a list of specified voice plugins.
     * @returns {Array} An array of objects, each containing a voice plugin's details.
     */
	getVoicePluginsInfo: function() {
        try {
		
            var VOICE_PLUGIN_IDS = [
                'sn_voice_aia',
                'sn_itsm_voice_aia',
                'sn_hr_voice_aia'
            ];

            // Initialize a map with all plugins in a 'not installed' state.
            var pluginMap = {};
            VOICE_PLUGIN_IDS.forEach(function(pluginId) {
                pluginMap[pluginId] = {
                    plugin_id: pluginId,
                    installed_version: 'not installed'
                };
            });

            // Query for the plugins that are actually installed.
            var gr = new GlideRecord('sys_store_app');
            gr.addQuery('source', 'IN', VOICE_PLUGIN_IDS.join(','));
            gr.query();

            // Update the map with details for the installed plugins.
            while (gr.next()) {
                var id = gr.getValue('source');
                if (pluginMap[id]) {
					pluginMap[id].name = gr.getValue('name') || '',
                    pluginMap[id].installed_version = gr.getValue('version') || '';
                }
            }

            // Convert the map back to an array for the final result.
            var results = [];
            VOICE_PLUGIN_IDS.forEach(function(pluginId) {
                results.push(pluginMap[pluginId]);
            });

            return results;
        } catch (e) {
            gs.error(gs.getMessage('VoiceRestUtilsSNC: Failed to retrieve voice plugin infos: {0}', [e.message]));
            return [];
        }
    },

    /**
     * Parses the build tag to get a more readable version string.
     * @private
     */
	_getBuildVersion: function() {
        var buildTag = gs.getProperty('glide.buildtag');
        if (gs.nil(buildTag)) {
            return "";
        }

        try {
            var buildTagParts = buildTag.split('-');
            if (buildTagParts.length < 2) {
                return buildTag; // Return original 
            }
            var family = buildTagParts[1]; // e.g., "zurich"

            var patchParts = buildTag.split('__');
            if (patchParts.length < 2 || gs.nil(patchParts[1])) {
                return family; // No patch info, return family only
            }

            var patchTokens = patchParts[1].split('-');
            if (patchTokens.length < 1) {
                return family; // No patch info, return family only
            }

            var patch = patchTokens[0]; // e.g., "patch6" or "patch4"
            // Only add the second part if it's a hotfix
            if (patchTokens.length >= 2 && patchTokens[1].indexOf('hotfix') === 0) {
                patch += '-' + patchTokens[1]; // e.g., "patch4-hotfix3a"
            }

            return family + '-' + patch;

        } catch (e) {
            gs.error('VoiceRestUtilsSNC: Failed to parse build tag. buildTag=' + buildTag + ', Error=' + e.message);
            return buildTag; // Return original
        }
    },
	
    type: 'VoiceRestUtilsSNC'
};