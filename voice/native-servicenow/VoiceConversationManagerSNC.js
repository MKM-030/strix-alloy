var VoiceConversationManagerSNC = Class.create();
VoiceConversationManagerSNC.prototype = {
    initialize: function() {
        const source = 'VAVOICEAPI';
        const logContext = {
            app: 'NOWASSISTVOICE',
            track: 'VAVOICEAPI',
            source: source
        };
        this.conversationUtils = new VoiceConversationUtils();
        this.restUtils = new VoiceRestUtils();
        this.LOGGER = new sn_log.GlideLogger(source, logContext, ['app', 'track', 'userId', 'inboundId']);
    },

    initializeWithServiceId: function(serviceId, isInTestMode) {
        if (!serviceId) {
            this.LOGGER.error(gs.getMessage('Service ID is required to initialize configuration.'));
            return false;
        }

        try {
            this.serviceId = serviceId;
            this.conversationConfig = new sn_voice_aia.VoiceServiceConfiguration().getConversationConfig(serviceId, isInTestMode);

            if (!this.conversationConfig) {
                this.LOGGER.error(gs.getMessage('Conversation config not found for service: {0}', [serviceId]));
                return false;
            }

            const appInboundId = this.conversationConfig?.providerAppId;
            if (!appInboundId) {
                this.LOGGER.error(gs.getMessage('Provider App ID not found in conversation config for service: {0}', [serviceId]));
                return false;
            }

            this.APP_INBOUND_ID = appInboundId;
            return true;
        } catch (e) {
            this.LOGGER.error(gs.getMessage('Error initializing service config: {0}', [e.message]));
            return false;
        }
    },

    createConversation: function(request, response) {
        const payload = request.body.nextEntry();
        const testMode = this.restUtils.isTestMode(request);
        if (!payload?.serviceId || !this.initializeWithServiceId(payload.serviceId, testMode))
            return this._handleError(response, gs.getMessage('Service ID missing or invalid in createConversation'), 422);

        if (this.validateProvider(request, response))
            return this._processConversation(payload, request.headers, response, 'CREATE_CONVERSATION');
        return this._handleError(response, 'Request signature validation failed', 403);
    },

    /**
     * Main validation entry point that routes to appropriate validation method based on source.
     * CCaaS signature validation is authoritative when a provider is configured for the service.
     * WebRTC and SoftPhone paths are only used as fallback when no CCaaS provider applies,
     * preventing isSoftPhone or voice_service_source from bypassing signature validation.
     * @param {Object} request - The incoming request object
     * @param {Object} response - The response object
     * @returns {Boolean} - True if validation succeeds
     */
    validateProvider: function(request, response) {
        if (this.validateWebRTCProvider(request)) return true;

        const ccaasResult = this.validateCCaaSProvider(request, response);
        if (ccaasResult !== undefined) {
            return ccaasResult;
        }
        return this.validateSoftPhoneProvider(request);
    },

    /**
     * Validates WebRTC provider requests
     * @param {Object} request - The incoming request object
     * @returns {Boolean} - True if this is a WebRTC conversation
     */
    validateWebRTCProvider: function(request) {
        if (!request)
            return false;
        const voiceSource = request.getHeader(VoiceAgentConstants.VOICE_SOURCE_HEADER);
        return this.restUtils.isWebRTCConversation(voiceSource);
    },

    /**
     * Validates SoftPhone provider requests based on a custom parameter sent
     * @param {Object} payload - The request payload
     * @returns {Boolean} - True if this is a SoftPhone conversation
     */
    validateSoftPhoneProvider: function(request) {
        const payload = request.body.nextEntry();
        return payload?.providerDataBlock?.parameters?.isSoftPhone === 'true';
    },

    /**
     * Validates CCaaS provider request signature
     * @param {Object} request - The incoming request object
     * @param {Object} response - The response object
     * @returns {Boolean} - True if validation succeeds
     */
    validateCCaaSProvider: function(request, response) {
        const payload = request.body.nextEntry();
        if (!payload || Object.keys(payload).length === 0)
            return this._handleError(response, gs.getMessage('Invalid or missing payload'), 422);
        const serviceId = payload.serviceId;
        if (!serviceId)
            return this._handleError(response, gs.getMessage('Service Id not found {0}.', [serviceId]), 422);

        const providerConfig = new sn_voice_aia.VoiceServiceConfiguration().getCCaaSProviderConfig(serviceId);

        const allExtensionPoints = new GlideScriptedExtensionPoint().getExtensions('sn_voice_aia.VoiceCCaaSRequestProcessor');
        for (const j in allExtensionPoints) {
            const ep = allExtensionPoints[j];
            ep.initialize(providerConfig);
            if (ep.appliesToProvider() && this._appliesToChannel(ep, providerConfig))
                return ep.validateRequest(request);
        }
    },

    /**
     * Resolve the channel check for an extension point.
     * Out-of-tree implementations may not have implemented appliesToChannel yet; treat those as
     * web_socket-only to preserve legacy behavior (deployments configured before the channel
     * attribute existed have an empty communicationChannel, which resolves to web_socket).
     * @param {Object} ep - Extension point instance
     * @param {Object} providerConfig - Provider config
     * @returns {boolean}
     * @private
     */
    _appliesToChannel: function(ep, providerConfig) {
        if (typeof ep.appliesToChannel === 'function')
            return ep.appliesToChannel();
        const channel = providerConfig?.communicationChannel || VoiceAgentConstants.COMMUNICATION_CHANNELS.WEB_SOCKET;
        return channel === VoiceAgentConstants.COMMUNICATION_CHANNELS.WEB_SOCKET;
    },

    endConversation: function(payload, headers, response) {
        const isInTestMode = payload?.clientApp === 'admin_test';
        if (!payload?.serviceId || !this.initializeWithServiceId(payload.serviceId, isInTestMode))
            return this._handleError(response, gs.getMessage('Service ID missing or invalid in endConversation'), 422);

        return this._processConversation(payload, headers, response, 'END_CONVERSATION');
    },

    elevateConversationSession: function(sysUserId, conversationId) {
        try {
            const interaction = this.conversationUtils.getInteractionFromConversation(conversationId);
            const providerAppId = interaction.getValue('provider_application');
            if (!providerAppId) {
                this.LOGGER.error(gs.getMessage('Provider app record not found for elevateConversationSession.'));
                return;
            }
            this.APP_INBOUND_ID = interaction.provider_application.inbound_id;
            let tokenJSON = {};

            if (interaction) {
                const messageForHash = {
                    sysUserId: sysUserId
                };
                const token = this._getToken(JSON.stringify(messageForHash));
                if (!token) {
                    this.LOGGER.error(gs.getMessage('Auth token retrieval failed for app: {0}', [this.APP_INBOUND_ID]));
                    return;
                }
                if (token.type === 'static')
                    tokenJSON = {
                        token: token.value
                    };
                else if (token.type === 'hash') {
                    tokenJSON = {
                        attributes: {
                            'Signature': token.value,
                            'Algorithm': 'HMAC-SHA1',
                            'Message': JSON.stringify(messageForHash)
                        },
                    };
                }
                interaction.verified = 'true';
                interaction.update();
                const providerUserId = this.conversationUtils.getProviderUserId(conversationId);
                return new sn_cs_adapter.VaLinkAccountUtil().elevateSession(providerAppId, providerUserId, sysUserId, JSON.stringify(tokenJSON), interaction.getUniqueValue());
            } else
                this.LOGGER.error(gs.getMessage('Interaction not found for conversationId: {0}', [conversationId]));

        } catch (e) {
            this.LOGGER.error(e);
        }
    },

    /**
     * Process a conversation request and forward it to the Virtual Agent service
     * @param {Object} payload - The incoming payload
     * @param {Object} headers - The headers of the REST request
     * @param {Object} response - The response object to write to
     * @param {String} action - The action type being performed
     * @returns {Object} - The response from the Virtual Agent or an error response
     */

    _processConversation: function(payload, headers, response, action) {
        try {
            // Extract and validate payload
            if (!payload || Object.keys(payload).length === 0)
                return this._handleError(response, `Invalid or missing payload in ${action}.`, 422);

            // Build request body
            const voiceSource = headers[VoiceAgentConstants.VOICE_SOURCE_HEADER.toLowerCase()];
            const requestBody = this._buildConversationRequestBody(payload, response, action, voiceSource);

            // Add authentication to headers
            headers = this._addTokenToHeader(headers, JSON.stringify(requestBody));
            if (!headers['token'] && !headers['x-b2b-signature'])
                return this._handleError(response, `Internal Error: Auth token retrieval failed for app: ${this.APP_INBOUND_ID}.`, 500);

            // Process the payload through VABotToBot API
            const restMessageHandler = new sn_va_as_service.VABotToBotRestMessageHandler();
            let vaResponse = restMessageHandler.processPayload(requestBody, headers);

            // Handle transferred state
            let liveTransferError = null;
            if (payload.state === VoiceAgentConstants.CONV_STATES.TRANSFERRED) {
                try {
                    new VoiceLiveAgentTransferHandler().processLiveAgentTransfer(payload);
                } catch (e) {
                    liveTransferError = e;
                    this.LOGGER.error(gs.getMessage('VoiceConversationManagerSNC: Live agent transfer failed, proceeding with post-processing: {0}', [e.message || e.toString()]));
                } finally {
                    vaResponse = {
                        status: 200,
                        content: {
                            completed: 'true'
                        }
                    };
                }
            }

            this._postProcess(action, payload, vaResponse, voiceSource);

            if (liveTransferError)
                return this._handleError(response, liveTransferError);

            return this._writeResponse(response, vaResponse, action, payload);
        } catch (e) {
            return this._handleError(response, e);
        }
    },

    _processFaultConversation: function(payload) {
        sn_cs.VASystemObject.faultConversation(payload.conversationId, payload.stateReason, null, payload.stateReason, true);
    },

    _postProcess: function(action, payload, vaResponse, voiceSource) {
        if (!vaResponse?.content) {
            this.LOGGER.warn('No content in VA response during _postProcess');
            return;
        }

        const {
            body,
            completed,
            takeControl
        } = vaResponse.content;

        if (action === 'CREATE_CONVERSATION' && body?.[0]?.conversationId) {
            const conversationId = body?.[0]?.conversationId;
            // Elevate session for WebRTC conversations (mobile or platform)
            if (this.restUtils.isWebRTCConversation(voiceSource)) {
                const userId = gs.getUserID();
                if (userId)
                    this.elevateConversationSession(userId, conversationId);
            }
            this.processCustomConversationFlows(conversationId, action, payload);
        } else if (action === 'END_CONVERSATION' && (completed || takeControl) && payload) {
            this._fireConversationProcessor(payload);

            vaResponse.sessionVariables = this.conversationUtils.getSessionVariables(vaResponse.status, payload);

            // Merge cachedData into sessionVariables (flows to both API response and saved record)
            if (payload.cachedData)
                vaResponse.sessionVariables = this.conversationUtils.mergeObjects(vaResponse.sessionVariables || {}, payload.cachedData);
        }
    },

    /**
     * Fires a background worker to handle asynchronous processing for conversation closure.
     * Falls back to synchronous processing if the worker fails to start.
     *
     * @param {Object} payload - Payload for handling conversation closure
     */
    _fireConversationProcessor: function(payload) {
        try {
            const worker = new GlideScriptedHierarchicalWorker();
            worker.setProgressName('Voice Post-Transfer Processing: ' + payload.conversationId);
            worker.setScriptIncludeName('sn_voice_aia.VoiceConversationProcessor');
            worker.setScriptIncludeMethod('processEndConversation');
            worker.putMethodArg('payload', JSON.stringify(payload));
            worker.setBackground(true);
            worker.start();
        } catch (e) {
            this.LOGGER.error(gs.getMessage('VoiceConversationManagerSNC: Failed to start async worker for conversation {0}, running synchronously: {1}',
                [payload.conversationId, e.message || e.toString()]));
            // Fallback: run synchronously if worker fails to start
            try {
                new VoiceConversationProcessor().processEndConversation(JSON.stringify(payload));
            } catch (fallbackErr) {
                this.LOGGER.error(gs.getMessage('VoiceConversationManagerSNC: Sync fallback also failed for conversation {0}: {1}',
                    [payload.conversationId, fallbackErr.message || fallbackErr.toString()]));
            }
        }
    },

    processCustomConversationFlows: function(conversationId, action, payload) {
        const allExtensionPoints = new GlideScriptedExtensionPoint().getExtensions('sn_voice_aia.VoiceConversationExt');
        for (const j in allExtensionPoints) {
            const ep = allExtensionPoints[j];
            ep.initialize();
            if (ep.shouldProcessConversation(payload)) {
                if (action === 'CREATE_CONVERSATION')
                    return ep.processConversationCreation(conversationId, payload);
                else if (action === 'END_CONVERSATION') {
                    if (payload.state === VoiceAgentConstants.CONV_STATES.FAULTED)
                        return ep.processFaultedConversation(conversationId, payload);
                    else if (payload.state === VoiceAgentConstants.CONV_STATES.TRANSFERRED)
                        return ep.postProcessLiveAgentTransfer(conversationId, payload);
                    return ep.processConversationCloser(conversationId, payload);
                }
            }
        }
    },

    _getCustomStoreConversationFields: function(conversationId, payload, vaResponse) {
        const extensions = new GlideScriptedExtensionPoint().getExtensions('sn_voice_aia.VoiceConversationExt');
        for (const ep of extensions) {
            ep.initialize();
            if (ep.shouldProcessConversation(payload) && typeof ep.getStoreConversationResponseFields === 'function') {
                const returned = ep.getStoreConversationResponseFields(conversationId, payload, vaResponse);
                if (returned && typeof returned === 'object') {
                    // Backwards compatibility: old return-value contract
                    vaResponse = this.conversationUtils.mergeObjects(vaResponse, returned);
                }
            }
        }
        return vaResponse;
    },

    _buildConversationRequestBody: function(payload, response, action, voiceSource) {
        const baseRequestBody = {
            userId: payload.conversationUserId,
            externalConversationId: payload.conversationUserId,
            clientSessionId: payload.conversationUserId,
            action: action,
            message: {
                text: '',
                typed: true
            },
            appInboundId: this.APP_INBOUND_ID
        };

        const serviceConfigUtils = new sn_voice_aia.VoiceServiceConfiguration();
        const serviceId = payload.serviceId;
        const restUtils = new sn_voice_aia.VoiceRestUtils();
        const voiceServiceLanguage = restUtils.getVoiceServiceLanguage(serviceId);
        const service = serviceConfigUtils.getDeploymentRecord(payload.serviceId);
        if (!payload.serviceId || !service || !service.isValid())
            return this._handleError(response, `Service Id not found ${payload.serviceId}.`, 422);

        if (!payload.providerDataBlock)
            return this._handleError(response, 'Request is missing providerDataBlock.', 422);

        if (action === 'CREATE_CONVERSATION') {
            const userAgent = payload?.providerDataBlock?.headers?.['User-Agent'];

            baseRequestBody.contextVariables = {
                interaction_requester_session_language: payload?.language || voiceServiceLanguage,
                interaction_user_language: payload?.language || voiceServiceLanguage,
                requester_session_language: payload?.language || voiceServiceLanguage,
                interaction_client_session_id: payload.conversationUserId,
                interaction_ai_voice: 'true',
                interaction_virtual_agent: 'true',
                interaction_caller_phone_number: payload.callerPhoneNumber,
                interaction_short_description: this.conversationConfig?.shortDescription,
                interaction_voice_origin: this.conversationUtils.determineVoiceOrigin(voiceSource, userAgent),
                live_agent_only: 'false',
                global_context_profile: serviceConfigUtils.getContextProfile(serviceId),
                voice_assistant: serviceId
            };

            const channelName = this.conversationUtils.getChannelName(this.APP_INBOUND_ID);
            if (channelName) {
                baseRequestBody.clientVariables = {
                    channelId: channelName
                };
            }
        } else if (action === 'END_CONVERSATION') {
            if (payload.state === VoiceAgentConstants.CONV_STATES.FAULTED) {
                baseRequestBody.action = 'FAULT_CONVERSATION';
                baseRequestBody.cause = payload.stateReason || 'EXTERNAL_FAILURE';
            }
            if (payload.state === VoiceAgentConstants.CONV_STATES.TRANSFERRED)
                baseRequestBody.action = 'ADD_TRANSCRIPTS';
            baseRequestBody.history = payload.transcript;
        }

        return baseRequestBody;
    },

    /**
     * @param {Object} payload - conversation payload (must include conversationId)
     * @param {Object} [options]
     * @param {boolean} [options.skipUsageLogging] - Skip usage logging for this call. Used by
     *   store_execution_plan, which invokes this same closure a second time after store_conversation
     *   has already run it once (see call flow in store_conversation's END_CONVERSATION handling and
     *   store_execution_plan's REST operation) — without this guard, usage logging would run twice
     *   per conversation and create a duplicate billing entry.
     */
    handleConversationClosure: function(payload, options) {
        const conversationId = payload.conversationId;
        if (!conversationId)
            return;

        const endTime = new GlideDateTime();
        const skipUsageLogging = !!(options && options.skipUsageLogging);

        this.conversationUtils.closeExecutionPlan(conversationId, endTime);
        // Update interaction short_description and state reason
        this._updateInteraction(payload);

        if (skipUsageLogging)
            this.LOGGER.debug(gs.getMessage('handleConversationClosure: skipping usage logging for conversationId={0} — already handled by store_conversation', [conversationId]));
        else
            this._handleUsageLogging(conversationId, endTime);

        try {
            // Stop polling Okta for push notification status and revoke the JWT access token
            const voiceAuthService = new sn_voice_auth.VoiceFactorAuthenticator();
            voiceAuthService.wrapUpConversation(payload);
        } catch (e) {
            gs.error('Error while wrapping up conversation: ' + e.message);
        }
    },

    _updateInteraction(payload) {
        const interaction = this.conversationUtils.getInteractionFromConversation(payload.conversationId);
        if (interaction) {
            payload.shortDescription && interaction.setValue('short_description', payload.shortDescription);
            interaction.setValue('state_reason', payload.stateReason);
            payload.callSummary && interaction.setValue('chat_summary', payload.callSummary);
            interaction.update();
        }
    },

    /**
     * Checks whether the persist_context_data deployment config attribute is enabled
     * for the current voice service. Returns false on error (fail-safe).
     * @returns {boolean} true if persistence is enabled for this service
     */
    _isPersistContextDataEnabled: function() {
        try {
            const serviceConfigUtils = new sn_voice_aia.VoiceServiceConfiguration();
            const config = serviceConfigUtils._getDeploymentConfig(this.serviceId);
            return config && config.getAttributeValue(VoiceAgentConstants.CONFIG_ATTRIBUTES.PERSIST_CONTEXT_DATA) === 'true';
        } catch (e) {
            this.LOGGER.warn(gs.getMessage('VoiceConversationManagerSNC: Error checking persist_context_data config: {0}', [e.message || e.toString()]));
            return false;
        }
    },

    _writeResponse: function(response, vaResponse, action, payload) {
        response.setContentType('application/json');
        const writer = response.getStreamWriter();

        if (vaResponse?.content) {
            const {
                body,
                status,
                completed,
                takeControl
            } = vaResponse.content;

            let responseBody = {
                result: {}
            };

            // Resolve conversationId from body (CREATE/UPDATE) or payload (END_CONVERSATION has empty body)
            const conversationId = body?.[0]?.conversationId || payload?.conversationId;
            if (conversationId) {
                responseBody.result.conversationId = conversationId;
                const interactionRecord = this.conversationUtils.getInteractionFromConversation(conversationId);
                if (interactionRecord && interactionRecord.isValidRecord()) {
                    responseBody.result.interactionId = interactionRecord.getUniqueValue();
                }
            }

            if (status)
                responseBody.result.status = status;
            if (completed || takeControl)
                responseBody.result.completed = completed || takeControl;

            if (vaResponse.sessionVariables)
                responseBody.result.sessionVariables = vaResponse.sessionVariables;

            responseBody.result = this._getCustomStoreConversationFields(conversationId, payload, responseBody.result);

            // Persist formatted API result to interaction_context for END_CONVERSATION
            if (action === 'END_CONVERSATION' && responseBody.result.interactionId && this._isPersistContextDataEnabled()) {
                try {
                    this.conversationUtils.saveInteractionContext(
                        responseBody.result.interactionId,
                        VoiceAgentConstants.CONTEXT_KEYS.BOT_CONTEXT_DATA,
                        responseBody.result
                    );
                } catch (e) {
                    this.LOGGER.error(gs.getMessage('VoiceConversationManagerSNC: Error persisting end-conversation context data: {0}', [e.message || e.toString()]));
                }
            }

            if (action === 'CREATE_CONVERSATION')
                responseBody = this._runPostCreationResponseExtensions(payload, responseBody);
            else if (action === 'END_CONVERSATION')
                this._runPostEndConversationExtensions(conversationId, payload, responseBody.result);

            writer.writeString(JSON.stringify(responseBody));
            response.setStatus(vaResponse.status);
        }

        return response;
    },

    _runPostCreationResponseExtensions: function(payload, responseBody) {
        try {
            const allExtensionPoints = new GlideScriptedExtensionPoint().getExtensions('sn_voice_aia.VoiceConversationExt');
            for (let i = 0; i < allExtensionPoints.length; i++) {
                const ep = allExtensionPoints[i];
                ep.initialize();
                if (ep.shouldProcessConversation(payload) && typeof ep.postProcessConversationResponse === 'function')
                    responseBody = ep.postProcessConversationResponse(payload, responseBody) || responseBody;
            }
        } catch (e) {
            this.LOGGER.error(gs.getMessage('VoiceConversationManagerSNC: Error in post-creation response extension: {0}', [e.message || e.toString()]));
        }
        return responseBody;
    },

    _runPostEndConversationExtensions: function(conversationId, payload, botContextData) {
        const allExtensionPoints = new GlideScriptedExtensionPoint()
            .getExtensions('sn_voice_aia.VoiceConversationExt');
        for (const ep of allExtensionPoints) {
            ep.initialize();
            // Guard allows existing implementations that pre-date this method to coexist safely.
            if (ep.shouldProcessConversation(payload) &&
                typeof ep.processPostEndConversation === 'function') {
                try {
                    ep.processPostEndConversation(conversationId, payload, botContextData);
                } catch (e) {
                    this.LOGGER.error(gs.getMessage(
                        'VoiceConversationManagerSNC: Error in processPostEndConversation: {0}',
                        [e.message || e.toString()]
                    ));
                }
                return;
            }
        }
    },

    _handleUsageLogging: function(conversationId, endTime) {
        if (!conversationId) {
            this.LOGGER.warn(gs.getMessage('No conversation ID provided for usage logging'));
            return;
        }

        const usageManager = new VoiceUsageLogsManager();
        usageManager.logUsageIfThresholdMet(conversationId, endTime);
    },

    _handleError: function(response, error, statusCode) {
        this.LOGGER.error(gs.getMessage('Error in AI Voice Agent conversation Rest API: {0}', [JSON.stringify(error)]));
        response.setContentType('application/json');
        const responseStatus = statusCode || error.status || 400;
        response.setStatus(responseStatus);
        const writer = response.getStreamWriter();
        const errorResponse = {
            detail: [{
                msg: error.message || error.toString(),
                type: 'error'
            }]
        };

        writer.writeString(JSON.stringify(errorResponse));
        return response;
    },

    _getToken: function(requestBody) {
        const providerId = this.APP_INBOUND_ID;
        const channelProvider = this.conversationUtils.getProviderAppRecord(providerId);
        if (!channelProvider) {
            this.LOGGER.error(gs.getMessage('Channel provider not found for token retrieval.'));
            return null;
        }

        const tokenType = channelProvider.message_auth?.inbound_message_verification?.sys_class_name;
        if (!tokenType) {
            this.LOGGER.error(gs.getMessage('Message verification config not found.'));
            return null;
        }

        if (tokenType == 'hash_message_verification') {
            const secret = channelProvider.message_auth.inbound_message_verification.secret;
            const base64Secret = gs.base64Encode(this.decryptToken(secret));
            const encryptionUtil = new CertificateEncryption();
            /* generateMac() will
            1. UTF-8 encode the input String
            2. Generate the Hash with the desired algorithm
            3. Base 64 enocde the generated hash and returns it
            */
            let base64SignedHeader = encryptionUtil.generateMac(base64Secret, 'HmacSHA1', requestBody);
            const hexSignedHeader = _base64ToHex(base64SignedHeader);
            return {
                type: 'hash',
                value: hexSignedHeader
            };
        } else if (tokenType == 'token_verification') {
            const valueToDecrypt = channelProvider.message_auth.inbound_message_verification.token;
            return {
                type: 'static',
                value: this.decryptToken(valueToDecrypt)
            };
        }
    },

    _addTokenToHeader: function(headers, requestBody) {
        const token = this._getToken(requestBody);
        if (!token) {
            this.LOGGER.error(`Auth token retrieval failed for app: ${this.APP_INBOUND_ID}.`);
            return headers;
        }
        if (token.type === 'static')
            headers['token'] = token.value;
        else if (token.type === 'hash')
            headers['x-b2b-signature'] = token.value;
        return headers;
    },

    /**
     * @description Decrypts a KMF-encrypted value via the glideencrypter crypto module.
     * Exposed as a public method so other script includes (e.g. VoiceNICEHelper) can reuse it
     * through an instance instead of relying on a module-level function leaking into scope.
     * @param {string} valueToDecrypt - The encrypted value to decrypt
     * @returns {string|null} The decrypted value, or null if decryption fails
     */
    decryptToken: function(valueToDecrypt) {
        try {
            const API_KMF_CRYPTO_MODULE = 'global.com_snc_platform_security_api_auth_glideencrypter';
            if (!gs.nil(valueToDecrypt)) {
                valueToDecrypt = valueToDecrypt.toString();
            }
            const kmfdecrypter = new sn_kmf_ns.KMFCryptoOperation(API_KMF_CRYPTO_MODULE, 'SYMMETRIC_UNWRAPPING')
                .withAlgorithm('AES')
                .withInputFormat('FORMATTED')
                .withOutputFormat('KMFNone');
            return kmfdecrypter.doOperation(valueToDecrypt);
        } catch (e) {
            gs.error(gs.getMessage('Error decrypting token: {0}', [e.message]));
            return null;
        }
    },

    type: 'VoiceConversationManagerSNC'
};

var _base64ToHex = function(base64Str) {
    var values = [];
    var output = [];
    if (output.length <= 0) populateLookups();
    var result = [];
    var v1, v2, v3, v4;
    for (var i = 0, len = base64Str.length; i < len; i += 4) {
        // Map four chars to values.
        v1 = values[base64Str.charCodeAt(i)];
        v2 = values[base64Str.charCodeAt(i + 1)];
        v3 = values[base64Str.charCodeAt(i + 2)];
        v4 = values[base64Str.charCodeAt(i + 3)];
        // Split and merge bits, then map and push to output.
        result.push(
            output[v1 << 2 | v2 >> 4],
            output[(v2 & 15) << 4 | v3 >> 2],
            output[(v3 & 3) << 6 | v4]
        );
    }
    // Trim result if the last values are '='.
    if (v4 === 64) result.splice(v3 === 64 ? -2 : -1);
    return result.join('');

    function populateLookups() {
        var keys = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=';
        for (var i = 0; i < 256; i++) {
            output.push(('0' + i.toString(16)).slice(-2));
            values.push(0);
        }
        for (var i = 0; i < 65; i++)
            values[keys.charCodeAt(i)] = i;
    }
};