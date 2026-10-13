var VABotToBotUtil = Class.create();
(function() {
    VABotToBotUtil.prototype = {
        initialize: function() {
            this.LOGGER = new VAAPILogger("VABotToBotUtil");
            this.inputControls = ["Boolean", "Picker", "Date", "InputText", "FileUpload", "TopicPickerControl", "Picture", "DateTime", "Time"];
            this.generalSettings = {};
            this.skipRetryCount = false;
            this.botConfig = null;
            this.appInboundId = null;
            this._setGeneralSettings();
            this.warnBeforeFault = false;
        },

        _getConversationId: function(adapterConversationContext) {
            return adapterConversationContext ? adapterConversationContext.conversation_id : null;
        },

        _getUniqueKey: function(key, conversationId) {
            return key + "_" + conversationId;
        },

        getFromProviderUserContext: function(key, payload, adapterConversationContext) {
            var conversationId = this._getConversationId(adapterConversationContext);
            var uniqueKey = this._getUniqueKey(key, conversationId);
            this.LOGGER.debug("Fetching key: {0} from provider user context", uniqueKey);
            var value = sn_cs.VASystemObject.getProviderUserContext(uniqueKey, payload.appInboundId, payload.userId, null);
            this.LOGGER.debug("Fetched key: {0} with value: {1} from provider user context", uniqueKey, value);
            return value;
        },

        addToProviderUserContext: function(key, input, payload, adapterConversationContext) {
            var conversationId = this._getConversationId(adapterConversationContext);
            var uniqueKey = this._getUniqueKey(key, conversationId);
            this.LOGGER.debug("Setting key: {0} with value: {1} to provider user context", uniqueKey, JSON.stringify(input));
            return sn_cs.VASystemObject.setProviderUserContext(uniqueKey, input, payload.appInboundId, payload.userId, null);
        },

        getPreviousMessage: function(payload, adapterConversationContext) {
            var previousMessageJson = this.getFromProviderUserContext(VABotToBotConstants.PREVIOUS_MESSAGE_KEY, payload, adapterConversationContext);

            if (!previousMessageJson) {
                return null;
            }

            return JSON.parse(previousMessageJson);
        },

        getPreviousMessageWithType: function(previousMessageType, payload, adapterConversationContext) {
            var previousMessage = this.getPreviousMessage(payload, adapterConversationContext);

            if (!previousMessage || previousMessage.type !== previousMessageType) {
                return null;
            }

            return previousMessage;
        },

        /*
        Used by both sync and async api : changes here will impact both API's
        */
        generateOutput: function(richControls, payload, additionalAttributes) {
            this.LOGGER.debug("List of richControls and additionalAttributes received from server : {0} {1}", [JSON.stringify(richControls), JSON.stringify(additionalAttributes)]);

            try {
                this._initBotConfig(payload);
                this._initAppInboundId();
                var providerAppId = this.getProviderAppSysId(this.appInboundId);

                var response = this._setPassThroughVariablesInResponse(payload);
				
                if (payload.isOffGlideResponse) {
					for (var key in additionalAttributes) {
                        if (additionalAttributes.hasOwnProperty(key)) {
                            response[key] = additionalAttributes[key];
                        }
                    }
                    response.body = richControls;
                    delete payload.isOffGlideResponse;
                } else {
					this.setAdditionalAttributesInResponse(response, additionalAttributes);
                    var controlInfos = this._setResponseBodyWithRichControls(response, richControls, payload);
                    this.setStreamingResponse(response, payload);
                    this.LOGGER.debug("ControlInfo JSON String : {0}", [JSON.stringify(controlInfos)]);

                    if (richControls[0].messageId) {
                        var conversationGr = this._getConversationFromMessageId(richControls[0].messageId);
                        this.LOGGER.debug("conversation state : {0}", [conversationGr.state]);

                        this._updateResponseFromConversationState(conversationGr, response, controlInfos.containsTopicFinishedActionMessage);

                        this._processTakeControl(response, providerAppId, controlInfos, conversationGr);

                        this._processScore(response, providerAppId, payload, conversationGr, controlInfos);
                    }
                }
                var transformedResponse = this._transformResponsePayload({
                    inputPayload: payload,
                    responsePayload: response
                });
                return transformedResponse;
            } catch (e) {
                gs.error("Error in Bot to Bot generateOutput : " + e.message);
            }
        },

        _processTakeControl: function(response, providerAppId, controlInfos, conversationGr) {
			if(this._isLLMEnabled(conversationGr)) {
				return;
			}
            var enableTakeControl = this.appInboundId ? this.getCustomAdapterPropertyWithHierarchy("enable_take_control", providerAppId, "true") == "true" : true;

            if (enableTakeControl) {
                this._setskipRetryCount(response);
                if (controlInfos.inputControlMsgId != "" && this.trackBotProgress(controlInfos.inputControlMsgId, controlInfos.inputControlUIType)) {
                    response.takeControl = true;
                    this._faultConversation(response, conversationGr);
                    this._markControlTrackerAsCompleted(conversationGr.getUniqueValue());
                    this.log("trackBotProgress returned true and returning score as 0. " + conversationGr.getUniqueValue());
                } else {
                    if (this.warnBeforeFault)
                        response.warnBeforeFault = true;
                }
            }
        },

        _isLLMEnabled: function(conversationGr) {
			try {
				if(conversationGr.getValue('model_type') === 'llm') {
					return true;
				}
				return false;
			} catch(e) {
				this.LOGGER.error("Unable to fetch model type from conversation: {0}", conversationGr.getUniqueValue());
                return false;
			}
        },

        _processScore: function(response, providerAppId, payload, conversationGr, controlInfos) {
			if(this._isLLMEnabled(conversationGr)) {
				return;
			}
            var sendNLUScore = this.appInboundId ? this.getCustomAdapterPropertyWithHierarchy("send_nlu_score", providerAppId, "true") == "true" : true;
            if (sendNLUScore) {
                if (response.takeControl) {
                    response.score = 0
                } else {
                    var text = gs.nil(payload.message) ? '' : gs.nil(payload.message.text) ? '' : payload.message.text;
                    var nlu_score = this.getNluScore(text, conversationGr.getUniqueValue());
                    if (!gs.nil(nlu_score)) {
                        this.log("nlu score found : " + nlu_score);
                        response.score = nlu_score;
                    } else {
                        this.log("nlu score not defined switching to old logic");
                        response.score = this.getScore(controlInfos.messageIds, conversationGr);
                    }
                }
            }
        },

        _transformResponsePayload: function(response) {
            // calling response transformation extension point for transforming responses if extension point implementations exist
            var transformedPayload = response.responsePayload;
            try {
                var payloadTransformExtensions = new GlideScriptedExtensionPoint().getExtensions("sn_va_as_service.va_api_output_transformation");
                if (payloadTransformExtensions) {
                    for (var index = 0; index < payloadTransformExtensions.length; index++) {
                        var extensionPoint = payloadTransformExtensions[index];
                        if (extensionPoint.shouldTransform(response)) {
                            transformedPayload = extensionPoint.transform(response);
                            break;
                        }
                    }
                }
                return transformedPayload;
            } catch (ex) {
                this.LOGGER.error("transformResponsePayload: Error in transforming response payload : {0}", ex);
                return transformedPayload;
            }
        },

        _setskipRetryCount: function(response) {
            var userContext = sn_cs.VASystemObject.getProviderUserContext(VABotToBotConstants.SENT_PREV_MAP_KEY, this.appInboundId, response.userId);
            userContext = userContext || '{}';
            userContext = JSON.parse(userContext);
            this.skipRetryCount = !gs.nil(userContext) ? (userContext.sentPrevReason == "pagination") : false;
            this.LOGGER.debug("Skip retry count for pagination: userContext: {0}, skipRetryCount? {1}", [userContext, this.skipRetryCount]);
        },

        _getConversationFromMessageId: function(messageId) {
            var messageGr = new GlideRecord("sys_cs_message");
            messageGr.get(messageId);
            this.LOGGER.debug("Message Id : {0}, messageGr.task : {1}", [messageId, messageGr.task]);

            var conversationGr = new GlideRecord("sys_cs_conversation");
            conversationGr.get(messageGr.conversation.toString());
            return conversationGr;
        },

        _updateResponseFromConversationState: function(conversationGr, response, containsTopicFinishedActionMessage) {
            var state = conversationGr.state.toString();
            var conversationId = conversationGr.getUniqueValue();

            switch (state) {
                case "faulted":
                    this._updateResponseForFaultedConversation(response, conversationId, containsTopicFinishedActionMessage);
                    break;

                case "completed":
                    this._updateResponseForCompletedConversation(response, conversationId, containsTopicFinishedActionMessage);
                    break;

                case "chatInProgress":
                    this._updateResponseForChatInProgressConversation(response, conversationId);
                    break;
            }
        },

        _updateResponseForFaultedConversation: function(response, conversationId, containsTopicFinishedActionMessage) {
            if (!this._shouldUpdateControlTrackerAsCompleted(containsTopicFinishedActionMessage))
                return;

            this._markControlTrackerAsCompleted(conversationId);
            this.LOGGER.debug("Conversation : {0} is faulted so sending takeControl true", [conversationId]);

            response.takeControl = true;
        },

        _updateResponseForCompletedConversation: function(response, conversationId, containsTopicFinishedActionMessage) {
            if (!this._shouldUpdateControlTrackerAsCompleted(containsTopicFinishedActionMessage))
                return;

            this._markControlTrackerAsCompleted(conversationId);
            this.LOGGER.debug("Conversation : {0} is completed so sending completed true", [conversationId]);

            response.completed = true;
        },

        _shouldUpdateControlTrackerAsCompleted: function(containsTopicFinishedActionMessage) {
            var topicFinishAsFinal = gs.getProperty("sn_va_as_service.enable_topic_finished_action_msg_as_final_state", true);
            if (topicFinishAsFinal == "true") {
                return containsTopicFinishedActionMessage;
            } else {
                return true;
            }
        },

        _updateResponseForChatInProgressConversation: function(response, conversationId) {
            this.LOGGER.debug("Conversation : {0} is chatInProgress so sending agentChat true", [conversationId]);
            response.agentChat = true;
        },

        _initBotConfig: function(payload) {
            if (!this.botConfig) {
                this.botConfig = new VABotToBotConfig(payload.appInboundId);
            }
        },

        _initAppInboundId: function() {
            this.appInboundId = this.botConfig.getInboundId();
        },

        _setPassThroughVariablesInResponse: function(payload) {
            var response = {
                requestId: payload.requestId,
                clientSessionId: payload.clientSessionId,
                nowSessionId: payload.nowSessionId,
                message: payload.message,
                userId: payload.userId,
                clientVariables: payload.clientVariables
            };
            if (payload.appInboundId != 'ServiceNow') {
                response.appInboundId = payload.appInboundId;
            }
            return response;
        },

        setStreamingResponse: function(response, payload) {
            if (!payload || payload.isDynamicLoader) return;

            if (payload.streamActive == true) {
                response.streamActive = true;
                response.streamState = payload.streamState;
                return;
            }

            var savedStreamId = this._getStreamIdFromProviderUserContext(payload.userId);
            if (savedStreamId && !payload.streamActive) { // This is the last message for streaming.
                response.streamState = "END";
                response.streamActive = false;
                sn_cs.VASystemObject.removeProviderUserContext(VABotToBotConstants.STREAM_ID, this.appInboundId, payload.userId, payload.requestId);
            }
        },

        _setStreamIdInProviderUserContext: function(streamId, userId) {
            sn_cs.VASystemObject.setProviderUserContext(VABotToBotConstants.STREAM_ID, streamId, this.appInboundId, userId);
        },

        _getStreamIdFromProviderUserContext: function(userId) {
            var streamId = sn_cs.VASystemObject.getProviderUserContext(VABotToBotConstants.STREAM_ID, this.appInboundId, userId);
            return streamId ? streamId : null;
        },

        setAdditionalAttributesInResponse: function(response, additionalAttributes) {
            if (additionalAttributes) {
                response.interactionId = additionalAttributes.interaction_id;
                if (additionalAttributes.is_agent_initiated_chat) {
                    response.isAgentInitiatedChat = true;
                }
            }
        },

        _setResponseBodyWithRichControls: function(response, results, payload) {
            var flattenedControls = [];
            var messageIds = [];

            // Step 1: Parse all rich controls and collect message IDs
            for (var i = 0; i < results.length; i++) {
                var messageId = results[i].messageId;
                messageIds.push(messageId);

                var parsedControls = this._parseRichControl(results[i].result);

                for (var j = 0; j < parsedControls.length; j++) {
                    parsedControls[j].messageId = messageId;
                    flattenedControls.push(parsedControls[j]);
                }
            }

            var body = [];
            var inputControlMsgId = "";
            var inputControlUIType = "";
            var containsTopicFinishedActionMessage = false;

            for (var k = 0; k < flattenedControls.length; k++) {
                var control = flattenedControls[k];

                if (control.actionType == "DynamicLoader") {
                    payload.isDynamicLoader = true;
                }

                if (control.actionType != "TopicFinished") {
                    body.push(control);
                } else {
                    containsTopicFinishedActionMessage = true;
                }

                if (this.inputControls.indexOf(control.uiType) >= 0) {
                    inputControlMsgId = control.messageId;
                    inputControlUIType = control.uiType;
                }
            }
            this._setStreamIdInBody(body, payload);

            response.body = body;

            return {
                messageIds: messageIds,
                inputControlMsgId: inputControlMsgId,
                inputControlUIType: inputControlUIType,
                containsTopicFinishedActionMessage: containsTopicFinishedActionMessage
            };
        },

        _setStreamIdInBody: function(body, payload) {
            // At the moment, we only have 1 object in body array for streaming use-cases
            // So assuming that, we're going to add the streamId in the first object of the body array.
            if (!body || !body.length || body.length <= 0 || !payload || payload.isDynamicLoader) return;

            var savedStreamId = this._getStreamIdFromProviderUserContext(payload.userId);
            if (payload.streamId) {
                // Update the stream ID everytime incase there are two duplicate stream starts.
                this._setStreamIdInProviderUserContext(payload.streamId, payload.userId);
            }

            if (savedStreamId && !payload.streamId) { // This is the last message for streaming
                payload.streamId = JSON.parse(savedStreamId);
            }

            if (payload.streamId) {
                body[0].streamId = payload.streamId;
            }
        },

        _parseRichControl: function(result) {
            var parseRichControl;
            try {
                parseRichControl = JSON.parse(result);
            } catch (e) {
                // This exception is added to handle Live Agent Chat (text message)
                parseRichControl = {
                    "uiType": "OutputText",
                    "value": result
                };
            }

            return Array.isArray(parseRichControl) ? parseRichControl : [parseRichControl];
        },


        //Once controlTracker is marked as completed, no messages will be sent for this conversation
        _markControlTrackerAsCompleted: function(conversationId) {
            var controlTrackerGr = new GlideRecord("sys_cs_bot_to_bot_control");
            controlTrackerGr.addQuery("conversation", conversationId);
            controlTrackerGr.query();
            if (controlTrackerGr.next()) {
                controlTrackerGr.setValue("completed", true);
                controlTrackerGr.update();
            } else {
                controlTrackerGr.setValue("conversation", conversationId);
                controlTrackerGr.setValue("completed", true);
                controlTrackerGr.insert();
            }
        },

        getScore: function(messageIds, conversationGr) {
            var messageTopicIds = [];
            var score = 1;
            var fallback_topic = sn_cs.VASystemObject.getContextProfileParamsForConversationId(conversationGr.getUniqueValue(), 'fallback');
            var error_topic = sn_cs.VASystemObject.getContextProfileParamsForConversationId(conversationGr.getUniqueValue(), 'error');
            var aiSearchFallback_topic = sn_cs.VASystemObject.getContextProfileParamsForConversationId(conversationGr.getUniqueValue(), 'ai_search_fallback');
            var messageGr = new GlideRecord("sys_cs_message");
            messageGr.addQuery('sys_id', 'IN', messageIds.join());
            messageGr.query();
            while (messageGr.next()) {
                messageTopicIds.push("" + messageGr.task.topic_type);
            }
            this.log("messageIds for score calculation " + messageIds);
            if (messageTopicIds.indexOf(fallback_topic) >= 0 || messageTopicIds.indexOf(error_topic) >= 0 || messageTopicIds.indexOf(aiSearchFallback_topic) >= 0) {
                score = 0;
                this.log("Either it's a fallback topic or error topic hence returning score as zero" + messageTopicIds);
            }
            var normalization_factor = gs.getProperty("va.bot.to.bot.score.normalization_factor", 1);
            score = score * normalization_factor;
            return score;
        },

        log: function(text, args) {
            this.LOGGER.debug(text, args);
        },

        error: function(text, args) {
            this.LOGGER.error(text, args);
        },

        getNluScore: function(text, conversationId) {
            try {
                if (!this.isNluEnabled())
                    return null;

                this.log("calculating nlu score for : CUSTOMER_INPUT");

                var nluIntentFeedback = new GlideRecord('open_nlu_predict_intent_feedback');
                nluIntentFeedback.addQuery('app_document_table', 'sys_cs_conversation_task');
                nluIntentFeedback.addQuery('utterance', text);

                var conversationTask = nluIntentFeedback.addJoinQuery('sys_cs_conversation_task', 'app_document', 'sys_id');
                conversationTask.addCondition('conversation', conversationId);

                nluIntentFeedback.setLimit(1);
                nluIntentFeedback.orderByDesc("sys_created_on");
                nluIntentFeedback.query();
                if (nluIntentFeedback.next()) {
                    var confidence = nluIntentFeedback.getValue('confidence');
                    if (confidence) {
                        return parseFloat(confidence).toFixed(2);
                    }
                }
                return null;
            } catch (e) {
                gs.error("Error in Calculating NLU Score : " + e.message);
                return null;
            }
        },

        checkTopicEnabled: function(topicId) {
            var topicGr = new GlideRecord('sys_cs_topic');
            topicGr.get(topicId);
            return topicGr.active;
        },

        trackBotProgress: function(messageId, inputControlUIType) {
            this.LOGGER.info("trackBotProgress:: input control message ID is: {0}", messageId);
            var exceed_limit = false;
            try {
                var messageGr = new GlideRecord("sys_cs_message");
                messageGr.get(messageId);
                this.log("messageGr.task " + messageGr.task);

                var taskGr = new GlideRecord("sys_cs_conversation_task");
                taskGr.get(messageGr.getValue("task"));
                this.log("taskGr.pending_progress " + taskGr.getValue("pending_progress"));

                var topic_id = taskGr.getValue("topic_type");
                //ignore invalid retires for topic with loops. The same control will repeat if there are loops in the topic.
                // Hence ignoring the takeControl flag for topics having loops.
                if (this._ignoreInvalidRetries(topic_id)) {
                    this.log("Ignoring invalid retires check for topic id: " + topic_id);
                    return false;
                }

                // State machine is updating it's state and pending_progress later on so we should ignore it for the first hit as this 
                // value will be null.
                if (taskGr.getValue("pending_progress") == null || taskGr.getValue("pending_progress") == "null") {
                    this.log("Newly created task so returning.");
                    return false;
                }
                var control_name = JSON.parse("" + taskGr.getValue("pending_progress")).todoFields[0];
                var control_ui_type = inputControlUIType ? inputControlUIType : "";
                this.log("control_name is " + control_name);
                this.LOGGER.info("trackBotProgress:: control_ui_type is: {0}", control_ui_type);
                var controlTrackerGr = new GlideRecord("sys_cs_bot_to_bot_control");
                controlTrackerGr.addQuery('conversation', "" + messageGr.getValue("conversation"));
                controlTrackerGr.query();
                if (!controlTrackerGr.next()) {
                    // This control tracker record is created for each and every conversation.
                    controlTrackerGr.setValue("conversation", "" + messageGr.conversation);
                    controlTrackerGr.setValue("task", "" + messageGr.task);

                    // This _topic_switcher_ condition occurs when user directly enter keyword associated with a topic.
                    if (taskGr.calling_task.getDisplayValue() == "_topic_switcher_") {
                        controlTrackerGr.setValue("count", 0);
                    } else {
                        controlTrackerGr.setValue("count", 1);
                    }
                    controlTrackerGr.setValue("control_name", control_name);
                    controlTrackerGr.setValue("u_control_ui_type", control_ui_type);
                    controlTrackerGr.insert();
                } else if (control_name == controlTrackerGr.control_name && (control_ui_type == controlTrackerGr.u_control_ui_type)) {
                    // Tracker count changes when same control is presented to user when wrong input is entered.
                    // The count is not incremented when control is presented to the user with next or previous buttons.
                    // The control type check is kept to handle the scneario when control is presented with default value.
                    // There are some edge scenarios where count tracker is not incremented correctly before takeControl flag becomes true.
                    // 1. When invalid input is given for topic pikcer after typing hi, one more additional attempt is given to user since the control name is different for invalid input.
                    // 2. In case of boolean with default option, one less attempt given since same boolean control is presented twice to the user.
                    if (!this.skipRetryCount) {
                        controlTrackerGr.setValue("count", ++controlTrackerGr.count);
                        controlTrackerGr.update();
                    }

                    var take_control_times = parseInt(gs.getProperty("va.bot.to.bot.take.control_times", 2));
                    if (parseInt(controlTrackerGr.count) == take_control_times)
                        this.warnBeforeFault = true;
                    if (parseInt(controlTrackerGr.count) > take_control_times) {
                        this.log("Same topic control is repeating hence asking master bot to take control." + controlTrackerGr.control_name + " message id " + messageId);
                        exceed_limit = true;
                    }

                } else {
                    // Reset the track counter when the control changes after user enters valid input.
                    controlTrackerGr.setValue("task", "" + messageGr.task);
                    controlTrackerGr.setValue("count", 1);
                    controlTrackerGr.setValue("control_name", control_name);
                    controlTrackerGr.setValue("u_control_ui_type", control_ui_type);
                    controlTrackerGr.update();
                }
            } catch (e) {
                gs.error("Error in Bot to Bot trackBotProgress : " + e.message);
                return true;
            }
            return exceed_limit;
        },

        _faultConversation: function(response, conversationGr) {
            if (conversationGr.state == 'faulted' || conversationGr.state == 'completed')
                return;
            if (response.takeControl == true) {
                var message = "Invalid user input";
                this._faultConversationAction(conversationGr.getUniqueValue(), "", message);
                this.log("TakeControl flag is true. Closing the conversation : " + conversationGr.getUniqueValue());
            }
        },

        _faultConversationAction: function(conversationId, messageToUser, cause) {
            this.log("_faultConversationAction:: faulting the conversation: {0}", conversationId);
            try {
                var inputs = {};
                inputs['conversationid'] = conversationId;
                inputs['messagetouser'] = messageToUser;
                inputs['cause'] = cause;
                var result = sn_fd.FlowAPI.getRunner().action('sn_va_as_service.virtual_agent__bot_to_bot_fault_conversation').inForeground().withInputs(inputs).run();
                var outputs = result.getOutputs();
            } catch (ex) {
                var message = ex.getMessage();
                this.LOGGER.error("faultConversationAction:: failed to start action: {0}", message);
            }
        },

        _ignoreInvalidRetries: function(topic_id) {
            //26baac293b77330074bc456993efc4dd - survey topic 
            //88c75499532000106e61ddeeff7b121f - IBM WatsonV2 topic
            //decd38545382011017c3ddeeff7b127f - SoftPIN topic - for retry invalid pin
            var property = gs.getProperty('sn_va_as_service.ignore_invalid_retries', "26baac293b77330074bc456993efc4dd, 88c75499532000106e61ddeeff7b121f, decd38545382011017c3ddeeff7b127f");
            if (property.indexOf(topic_id) >= 0)
                return true;

            return false;
        },

        isHistoryValid: function(history) {
            if (history == null || history == "" || history == undefined) {
                this.log("BTB message history validation failed. history : " + history);
                return false;
            }

            var valid = true;
            history.forEach(function(message) {
                if (!message.hasOwnProperty('value') && !message.hasOwnProperty('attachment'))
                    valid = false;
                if (!message.hasOwnProperty('isBotMessage'))
                    valid = false;
                if (!message.hasOwnProperty('displayName'))
                    valid = false;
                if (!message.hasOwnProperty('type'))
                    valid = false;
            });
            if (!valid)
                gs.error("BTB message history validation failed. history : " + JSON.stringify(history));
            return valid;
        },

        isValidDateTime: function(dateTime) {
            //matches pattern YYYY-MM-DD HH:MM:SS (time in 24 hrs format )
            var dateTime_regex = /^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|1\d|2\d|3[01])\s([0-1][0-9]|2[0-3]):([0-5][0-9]):([0-5][0-9])$/;
            var isValidDateTime = dateTime_regex.test(dateTime);
            if (!isValidDateTime) {
                this.log('The passed in datetime ' + dateTime + ' should be in the format YYYY-MM-DD HH:MM:SS (time in 24 hrs format )');
            }
            return isValidDateTime;
        },

        isValidTime: function(time) {
            //matches pattern HH:MM:SS (time in 24 hrs format )
            var time_regex = /^([0-1][0-9]|2[0-3]):([0-5][0-9]):([0-5][0-9])$/;
            var isValidTime = time_regex.test(time);
            if (!isValidTime) {
                this.log('The passed in time ' + time + ' should be in the format HH:MM:SS (time in 24 hrs format )');
            }
            return isValidTime;
        },

        getCurrentTimeInMillis: function() {
            var glideDateTime = new GlideDateTime();
            return glideDateTime.getNumericValue();
        },

        getCustomAdapterPropertyWithHierarchy: function(propertyName, providerAppId, defaultValue) {
            var propertyVal = sn_cs.VASystemObject.getCustomAdapterPropertyWithHierarchy(propertyName, providerAppId);
            if (!propertyVal) return defaultValue ? defaultValue : propertyVal;
            return propertyVal;
        },

        isPaginationEnabled: function(appInboundId) {
            return ("true" === this.getCustomAdapterPropertyWithHierarchy(VABotToBotConstants.PAGINATION_ENABLED, this.getProviderAppSysId(appInboundId)));
        },

        shouldSkipHiddenControl: function(appInboundId) {
            return ("true" === this.getCustomAdapterPropertyWithHierarchy(VABotToBotConstants.SHOULD_SKIP_HIDDEN_CONTROL, this.getProviderAppSysId(appInboundId)));
        },

        getMaxChoiceLimit: function(appInboundId) {
            var maxChoiceLimitV1 = this.getCustomAdapterPropertyWithHierarchy(VABotToBotConstants.MAX_CHOICE_LIMIT, this.getProviderAppSysId(appInboundId), 10);
            var maxChoiceLimit = this.getCustomAdapterPropertyWithHierarchy(VABotToBotConstants.MAX_CHOICE_LIMIT_v2, this.getProviderAppSysId(appInboundId), maxChoiceLimitV1);
            return parseInt(maxChoiceLimit);
        },

        getProviderAppSysId: function(appInboundId) {
            if (!this.botConfig) {
                this.botConfig = new VABotToBotConfig(appInboundId);
                return this.botConfig.providerAppSysId;
            }
            return this.botConfig.providerAppSysId;
        },

        getNextKeyword: function(appInboundId) {
            return this.getCustomAdapterPropertyWithHierarchy(VABotToBotConstants.NEXT, this.getProviderAppSysId(appInboundId), 'next');
        },

        getRepeatKeyword: function(appInboundId) {
            return this.getCustomAdapterPropertyWithHierarchy(VABotToBotConstants.REPEAT, this.getProviderAppSysId(appInboundId), 'repeat');
        },

        getBackKeyword: function(appInboundId) {
            return this.getCustomAdapterPropertyWithHierarchy(VABotToBotConstants.BACK, this.getProviderAppSysId(appInboundId), 'back');
        },

        getSkipKeyword: function(appInboundId) {
            return this.getCustomAdapterPropertyWithHierarchy(VABotToBotConstants.SKIP, this.getProviderAppSysId(appInboundId), 'skip');
        },

        isNluEnabled: function() {
            if (this.generalSettings && this.generalSettings.nluEnabled && this.generalSettings.nluDriver) {
                return true;
            }
            return false;
        },

        _setGeneralSettings: function() {
            var settings = sn_cs.VASystemObject.getGeneralSettings();
            if (settings) {
                this.generalSettings = JSON.parse(settings);
            }
        },

        getSessionLang: function(appInboundId, providerUserId) {
            try {
                var providerAppId = this.getProviderAppSysId(appInboundId);
                var providerUserDetails = sn_cs.VASystemObject.getProviderUserDetails(providerAppId, providerUserId);
                return providerUserDetails.provider_user_session_language;
            } catch (e) {
                this.LOGGER.error("Exception occured while fetching provider user details {0}", e);
                return gs.getSession().getLanguage();
            }
        },

        handleSetUserTzAction: function(payload, headers) {
            try {
                var responseBuilder;
                var vaResponse = {
                    status: 200,
                    content: {
                        status: "success"
                    }
                };
                var providerAppId = this.getProviderAppSysId(payload.appInboundId);
                var tokenString = this.getTokenString(payload, headers);
                var isValidRequest = new sn_cs.CustomAdapterAuthUtil().validateToken(providerAppId, tokenString);
                if (isValidRequest) {
                    if (!this._doesChannelUserProfileExist(payload)) {
                        this._createChanneluserProfile(payload);
                    }
                    sn_cs.VASystemObject.setProviderUserTimeZone(payload.appInboundId, payload.userId, payload.timezone);
                    if (this.botConfig.isSyncResponseEnabled()) {
                        responseBuilder = new sn_va_as_service.VABotToBotSyncResponseBuilder();
                        return responseBuilder.buildResponseForSetTzAction(payload);
                    } else {
                        return vaResponse;
                    }
                } else {
                    vaResponse.status = 401;
                    vaResponse.content.status = "failure";
                    vaResponse.content.error = {
                        message: "Failed to authenticate request."
                    };
                    return vaResponse;
                }
            } catch (e) {
                this.LOGGER.error("Error in VA Bot to Bot Rest API." + e);
                vaResponse.status = 500;
                vaResponse.content.status = "failure";
                vaResponse.content.error = {
                    message: "Failed to process request."
                };
            }
            return vaResponse;
        },

        _createChanneluserProfile: function(payload) {
            var channelUserProfileGr = new GlideRecord("sys_cs_channel_user_profile");
            channelUserProfileGr.initialize();
            channelUserProfileGr.setValue("channel", VABotToBotConstants.CHANNEL_ID);
            channelUserProfileGr.setValue("channel_user_id", payload.userId);
            channelUserProfileGr.insert();
        },

        _doesChannelUserProfileExist: function(payload) {
            var channelUserProfileGr = new GlideRecord("sys_cs_channel_user_profile");
            channelUserProfileGr.addQuery("channel", VABotToBotConstants.CHANNEL_ID);
            channelUserProfileGr.addQuery("channel_user_id", payload.userId);
            channelUserProfileGr.addActiveQuery();
            channelUserProfileGr.query();
            return channelUserProfileGr.next();
        },

        getTokenString: function(payload, headers) {
            var tokenJSON;
            if (headers["x-b2b-signature"]) {
                var inputAlgorithm = headers["x-b2b-algorithm"] || VABotToBotConstants.DEFAULT_HASHING_ALGORITHM;
                var formattedInputAlgorithm = this.formatAlgorithm(inputAlgorithm);
                var selectedAlgorithm = VABotToBotConstants.ALLOWED_HASHING_ALGORITHMS[formattedInputAlgorithm];
                if (!selectedAlgorithm) {
                    this.LOGGER.error("Hashing algorithm {0} is not supported.", inputAlgorithm);
                    throw new Error("Hashing algorithm " + inputAlgorithm + " is not supported.");
                }
                tokenJSON = {
                    attributes: {
                        "Signature": headers["x-b2b-signature"],
                        "Algorithm": selectedAlgorithm,
                        "Message": headers["x-b2b-hash-message"]
                    },
                };
            } else {
                tokenJSON = {
                    token: headers["token"] || payload.token
                };
            }
            return JSON.stringify(tokenJSON);
        },

        formatAlgorithm: function(algorithm) {
            return algorithm.replace(/-/g, '').toLowerCase();
        },

        type: 'VABotToBotUtil'
    };
})();