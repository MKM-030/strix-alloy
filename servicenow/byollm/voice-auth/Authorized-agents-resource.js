(function process(/*RESTAPIRequest*/ request, /*RESTAPIResponse*/ response) {
    const voiceRestUtils = new VoiceRestUtils();
    if (!voiceRestUtils.validateServiceId(request, response)) {
        return;
    }

    if (!voiceRestUtils.validateServiceAuthorization(request, response)) {
        return;
    }

	var payload = request.body.data;
	var serviceId = payload.serviceId;

	var testMode = voiceRestUtils.isTestMode(request);
	var agentUtils = new VoiceAgentUtils();
	var authorizedAgentIds = agentUtils.getAuthorizedAgentIds(serviceId, testMode);
    // Explicit opt-in keeps the native authorized-agent array contract unchanged.
    if (payload.assistantSettingsVersion === 1) {
        var header = String(request.getHeader('Authorization') || '');
        var bearer = /^Bearer ([A-Za-z0-9._~+\/-]+=*)$/i.exec(header);
        var validBearer = !!bearer && bearer[0] === header && header.length <= 8192;
        var jwt = /^Bearer ([A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)$/i.exec(header);
        var validAgents = Array.isArray(authorizedAgentIds) && authorizedAgentIds.length > 0;
        if (validAgents) {
            for (var i = 0; i < authorizedAgentIds.length; i++) {
                if (typeof authorizedAgentIds[i] !== 'string' || !/^[0-9a-f]{32}$/.test(authorizedAgentIds[i])) {
                    validAgents = false;
                    break;
                }
            }
        }
        var audienceMatches = false;
        // Platform authentication and native validation above authenticate both token types.
        // Native agent authorization checks execution ACLs for this service. JWT credentials
        // additionally keep the native service binding; opaque OAuth has no JWT audience.
        var authenticatedUser = !!gs.getUserID() && gs.getUserName() !== 'guest';
        if (jwt && validBearer && authenticatedUser && validAgents) {
            try {
                var bound = JSON.parse(new sn_auth.VoiceServiceInfoRequestor().getVoiceServiceInfo() || '{}');
                audienceMatches = bound.voice_service_id === serviceId;
            } catch (ignored) {}
        }
        var settingsAuthorized = validBearer && authenticatedUser && validAgents && (!jwt || audienceMatches);
        if (!settingsAuthorized) {
            response.setStatus(403);
            response.setBody({detail:'Assistant settings authorization rejected'});
            return;
        }
        // Explicit binary reference opt-in reuses the existing native service/agent/Bearer gate above.
        if (typeof payload.voiceReferenceVersion !== 'undefined') {
            var referenceKeys = ['serviceId','assistantSettingsVersion','voiceReferenceVersion','language','reference'];
            if (payload.voiceReferenceVersion !== 1 ||
                    Object.keys(payload).sort().join(',') !== referenceKeys.sort().join(',')) {
                response.setStatus(403);
                response.setBody({detail:'Selected voice reference unavailable'});
                return;
            }
            var referenceStream;
            try {
                referenceStream = new LocalLLMVoiceAssistantSettings().getVoiceReferenceStream(serviceId, payload.language, payload.reference);
            } catch (ignoredReferenceFailure) {
                response.setStatus(403);
                response.setBody({detail:'Selected voice reference unavailable'});
                return;
            }
            response.setStatus(200);
            response.setContentType('audio/wav');
            response.setHeader('Cache-Control','no-store');
            response.getStreamWriter().writeStream(referenceStream);
            return;
        }
        if (typeof payload.conversationModelVersion !== 'undefined' && payload.conversationModelVersion !== 1) {
            response.setStatus(403);
            response.setBody({detail:'Conversation model selection unavailable'});
            return;
        }
        if (typeof payload.providerContextVersion !== 'undefined' &&
                (payload.providerContextVersion !== 1 || payload.conversationAuthenticationVersion !== 1)) {
            response.setStatus(403);
            response.setBody({detail:'Provider context binding unavailable'});
            return;
        }
        // Explicit caller binding is private to the authenticated adapter response.
        // It is never part of assistant settings or the legacy agent-array response.
        var callerBinding = null;
        if (typeof payload.callerBindingVersion !== 'undefined') {
            if (payload.callerBindingVersion !== 1) {
                response.setStatus(403);
                response.setBody({detail:'Caller binding unavailable'});
                return;
            }
            callerBinding = (function () {
                try {
                    var currentId = String(gs.getUserID() || '');
                    var currentName = String(gs.getUserName() || '');
                    if (!/^[0-9a-f]{32}$/.test(currentId) || !currentName || currentName === 'guest') return null;
                    var fields = ['sys_id','user_name','email','active','locked_out'];
                    function validSchema(record) {
                        if (record.isValid() !== true) return false;
                        for (var i = 0; i < fields.length; i++) if (record.isValidField(fields[i]) !== true) return false;
                        return true;
                    }
                    function readableValues(record) {
                        if (record.canRead() !== true) return null;
                        var i, element, values = {};
                        // Check every required right before reading any field value.
                        for (i = 0; i < fields.length; i++) {
                            element = record.getElement(fields[i]);
                            if (element === null || typeof element === 'undefined' || element.canRead() !== true) return null;
                        }
                        for (i = 0; i < fields.length; i++) {
                            var value = record.getValue(fields[i]);
                            values[fields[i]] = value === null || typeof value === 'undefined' ? '' : String(value);
                        }
                        return values;
                    }
                    var ownUser = new GlideRecordSecure('sys_user');
                    if (!validSchema(ownUser) || ownUser.get(currentId) !== true) return null;
                    var ownValues = readableValues(ownUser);
                    if (ownValues === null || ownValues.sys_id !== currentId || ownValues.user_name !== currentName ||
                        !ownValues.email || ownValues.active !== '1' || ownValues.locked_out !== '0') return null;

                    // Match native auto-link visibility, but manually enforce all read rights.
                    // A secure query alone could hide a conflicting native matching row.
                    var matches = new GlideRecord('sys_user');
                    if (!validSchema(matches)) return null;
                    matches.addQuery('email', ownValues.email);
                    matches.addQuery('active', true);
                    matches.addQuery('locked_out', false);
                    matches.setLimit(2);
                    matches.query();
                    var count = 0;
                    while (matches.next()) {
                        // Denied rows are a generic refusal; their values are never read.
                        var matchedValues = readableValues(matches);
                        if (matchedValues === null) return null;
                        count++;
                        if (count >= 2) return null;
                        if (matchedValues.sys_id !== currentId || matchedValues.user_name !== currentName ||
                            matchedValues.email !== ownValues.email || matchedValues.active !== '1' || matchedValues.locked_out !== '0') return null;
                    }
                    if (count !== 1) return null;
                    return {version:1,service_id:serviceId,user_id:currentId,
                        user_name:ownValues.user_name,email:ownValues.email,email_mapping_unique:true};
                } catch (ignoredCallerBindingError) {
                    return null;
                }
            })();
            if (callerBinding === null) {
                response.setStatus(403);
                response.setBody({detail:'Caller binding unavailable'});
                return;
            }
        }

        try {
            var settings = new LocalLLMVoiceAssistantSettings().getSettings(serviceId);
            if (callerBinding !== null) {
                if (!settings || settings.version !== 1 || settings.service_id !== serviceId ||
                    typeof settings.context_profile !== 'string' || !/^[0-9a-f]{32}$/.test(settings.context_profile)) {
                    response.setStatus(403);
                    response.setBody({detail:'Caller binding unavailable'});
                    return;
                }
                callerBinding.context_profile = settings.context_profile;
            }
            var providerContextBinding = null;
            var conversationAuthentication = null;
            if (typeof payload.conversationAuthenticationVersion !== 'undefined') {
                if (payload.conversationAuthenticationVersion !== 1 || payload.callerBindingVersion !== 1 || callerBinding === null) {
                    response.setStatus(403);
                    response.setBody({detail:'Conversation authentication unavailable'});
                    return;
                }
                conversationAuthentication = (function () {
                    try {
                        var currentId = String(gs.getUserID() || '');
                        if (currentId !== callerBinding.user_id || String(gs.getUserName() || '') !== callerBinding.user_name) return null;
                        var conversationId = payload.conversationId, interactionId = payload.interactionId, messageId = payload.createMessageId;
                        var guid = /^[0-9a-f]{32}$/;
                        if (typeof conversationId !== 'string' || !guid.test(conversationId) || typeof interactionId !== 'string' || !guid.test(interactionId) ||
                            typeof messageId !== 'string' || !guid.test(messageId)) return null;
                        var actualApp = '200af60f93fb4354e7f2b9fa6aba107d';
                        var actualProfile = 'c623e20f93374354e7f2b9fa6aba1081';
                        var actualService = '8aa131d793f787105c8132d47aba1095';
                        if (serviceId !== actualService || settings.context_profile !== actualProfile || settings.service_id !== serviceId || callerBinding.context_profile !== actualProfile) return null;
                        var proofs = [];
                        function values(record, fields) {
                            if (record.canRead() !== true) return null;
                            var out = {}, i, element, value;
                            for (i = 0; i < fields.length; i++) {
                                if (record.isValidField(fields[i]) !== true) return null;
                                element = record.getElement(fields[i]);
                                if (element === null || typeof element === 'undefined' || element.canRead() !== true) return null;
                            }
                            for (i = 0; i < fields.length; i++) {
                                value = record.getValue(fields[i]);
                                out[fields[i]] = value === null || typeof value === 'undefined' ? '' : String(value);
                            }
                            return out;
                        }
                        function readOwn(table, id, fields, remember) {
                            if (!guid.test(id)) return null;
                            var record = new GlideRecordSecure(table);
                            if (record.isValid() !== true || record.get(id) !== true) return null;
                            var data = values(record, fields);
                            if (data === null || data.sys_id !== id) return null;
                            if (remember) proofs.push({table:table,id:id,fields:fields,values:JSON.stringify(data)});
                            return data;
                        }
                        function fresh(created) {
                            if (!/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/.test(created)) return false;
                            var when = new GlideDateTime();
                            when.setValue(created);
                            if (String(when.getValue()) !== created) return false;
                            var age = Number(new GlideDateTime().getNumericValue()) - Number(when.getNumericValue());
                            return isFinite(age) && age >= 0 && age <= 45000;
                        }
                        var conversationFields = ['sys_id','consumer_account','context_profile','current_device','state','sys_created_on'];
                        var conversation = readOwn('sys_cs_conversation',conversationId,conversationFields,true);
                        // Native dictionary choice "open" only: no started, autopilot, closed or unknown state fallback.
                        if (conversation === null || conversation.state !== 'open' || conversation.context_profile !== actualProfile || !fresh(conversation.sys_created_on)) return null;
                        var account = readOwn('sys_cs_consumer_account',conversation.consumer_account,['sys_id','provider_application','channel_user_profile','consumer'],true);
                        if (account === null || account.provider_application !== actualApp) return null;
                        var app = readOwn('sys_cs_provider_application',actualApp,['sys_id','inbound_id','provider'],true);
                        if (app === null || app.inbound_id !== 'scc-local-voice' || app.provider !== 'd6eadc7a53301010ad77ddeeff7b124a') return null;
                        var profile = readOwn('sys_cs_channel_user_profile',account.channel_user_profile,['sys_id','active','user_table','user_document','channel_user_id','channel'],true);
                        if (profile === null || profile.active !== '1' || profile.user_table !== 'sys_user' || profile.user_document !== currentId ||
                            !profile.channel_user_id || profile.channel !== '51cdaa4c53a710105893ddeeff7b129c') return null;
                        var consumer = readOwn('sys_cs_consumer',account.consumer,['sys_id','user_id','inactive'],true);
                        if (consumer === null || consumer.user_id !== currentId || consumer.inactive !== '0') return null;
                        var interactionFields = ['sys_id','channel_metadata_document','provider_application','state','active','type','sys_created_on'];
                        var interaction = readOwn('interaction',interactionId,interactionFields,true);
                        // These two creation/working states are observed active native choices; hold/closed/unknown refuse.
                        if (interaction === null || interaction.channel_metadata_document !== conversationId || interaction.provider_application !== actualApp ||
                            (interaction.state !== 'new' && interaction.state !== 'work_in_progress') || interaction.active !== '1' ||
                            interaction.type !== 'chat' || !fresh(interaction.sys_created_on)) return null;
                        var messageFields = ['sys_id','conversation','consumer_account','session','direction','message_type','payload','sys_created_on'];
                        var message = readOwn('sys_cs_message',messageId,messageFields,true);
                        if (message === null || message.conversation !== conversationId || message.consumer_account !== account.sys_id ||
                            message.direction !== 'outbound' || message.message_type !== 'action' || !fresh(message.sys_created_on)) return null;
                        var create = JSON.parse(message.payload);
                        // Exact observed native CREATE action shape; no invented transport request-ID proof.
                        if (!create || create.type !== 'CreateConversation' || create.topicId !== conversationId || create.interactionId !== interactionId ||
                            Object.keys(create).sort().join(',') !== 'interactionId,topicId,type') return null;
                        var session = readOwn('sys_cs_session',message.session,['sys_id','consumer_account','consumer','device_id','device_type','end_time'],true);
                        if (session === null || session.consumer_account !== account.sys_id || session.consumer !== consumer.sys_id ||
                            !conversation.current_device.trim() || !session.device_id.trim() || session.device_id !== conversation.current_device ||
                            session.device_type !== 'Bot to Bot' || session.end_time !== '') return null;
                        function uniqueNativeInteraction() {
                            var nativeMatch = new GlideRecord('interaction');
                            if (nativeMatch.isValid() !== true || nativeMatch.isValidField('channel_metadata_document') !== true) return false;
                            nativeMatch.addQuery('channel_metadata_document',conversationId);
                            nativeMatch.setLimit(2);
                            nativeMatch.query();
                            var count = 0, data;
                            while (nativeMatch.next()) {
                                data = values(nativeMatch,interactionFields);
                                if (data === null) return false;
                                count++;
                                if (count >= 2 || data.sys_id !== interactionId || JSON.stringify(data) !== JSON.stringify(interaction)) return false;
                            }
                            return count === 1;
                        }
                        if (!uniqueNativeInteraction()) return null;
                        for (var i = 0; i < proofs.length; i++) {
                            var proof = proofs[i], current = readOwn(proof.table,proof.id,proof.fields,false);
                            if (current === null || JSON.stringify(current) !== proof.values) return null;
                        }
                        if (!uniqueNativeInteraction()) return null;
                        var writableInteraction = new GlideRecordSecure('interaction');
                        if (writableInteraction.isValid() !== true || writableInteraction.get(interactionId) !== true ||
                            writableInteraction.canRead() !== true || writableInteraction.canWrite() !== true ||
                            writableInteraction.isValidField('verified') !== true) return null;
                        var verifiedField = writableInteraction.getElement('verified');
                        if (verifiedField === null || typeof verifiedField === 'undefined' || verifiedField.canRead() !== true || verifiedField.canWrite() !== true) return null;
                        var writableProof = values(writableInteraction,interactionFields);
                        if (writableProof === null || JSON.stringify(writableProof) !== JSON.stringify(interaction) ||
                            String(gs.getUserID() || '') !== currentId || !fresh(conversation.sys_created_on)) return null;
                        // The return value is deliberately not interpreted as an authentication acknowledgement.
                        new VoiceConversationManager().elevateConversationSession(currentId,conversationId);
                        if (payload.providerContextVersion === 1) {
                            providerContextBinding = {version:1,status:'unavailable'};
                            // Optional authority is independently re-observed after elevation.
                            // Preserve the required refresh even if this read-only projection fails.
                            try {
                                var canonicalProfile = null;
                                function postRefreshGraph() {
                                    var observedProfile = null;
                                    for (var j = 0; j < proofs.length; j++) {
                                        var saved = proofs[j], observed = readOwn(saved.table,saved.id,saved.fields,false);
                                        if (observed === null) return null;
                                        if (saved.table === 'sys_cs_channel_user_profile') {
                                            if (!/^voice-[0-9a-f]{32}$/.test(observed.channel_user_id)) return null;
                                            observedProfile = observed;
                                            var stable = JSON.parse(JSON.stringify(observed));
                                            stable.channel_user_id = profile.channel_user_id;
                                            if (JSON.stringify(stable) !== saved.values) return null;
                                        } else if (JSON.stringify(observed) !== saved.values) return null;
                                    }
                                    if (observedProfile === null || String(gs.getUserID() || '') !== currentId ||
                                            String(gs.getUserName() || '') !== callerBinding.user_name || !uniqueNativeInteraction()) return null;
                                    var aliases = new GlideRecordSecure('sys_cs_channel_user_profile');
                                    if (aliases.isValid() !== true || aliases.isValidField('channel') !== true ||
                                            aliases.isValidField('channel_user_id') !== true) return null;
                                    aliases.addQuery('channel',observedProfile.channel);
                                    aliases.addQuery('channel_user_id',observedProfile.channel_user_id);
                                    aliases.setLimit(2); aliases.query();
                                    var matches = 0;
                                    while (aliases.next()) {
                                        var alias = values(aliases,['sys_id','active','user_table','user_document','channel_user_id','channel']);
                                        if (alias === null || ++matches > 1 || JSON.stringify(alias) !== JSON.stringify(observedProfile)) return null;
                                    }
                                    return matches === 1 ? observedProfile : null;
                                }
                                canonicalProfile = postRefreshGraph();
                                var finalProfile = canonicalProfile === null ? null : postRefreshGraph();
                                if (canonicalProfile !== null && finalProfile !== null && JSON.stringify(finalProfile) === JSON.stringify(canonicalProfile)) {
                                    providerContextBinding = {version:1,status:'available',service_id:serviceId,context_profile:settings.context_profile,
                                        conversation_id:conversationId,interaction_id:interactionId,create_message_id:messageId,
                                        caller_user_id:currentId,provider_user_id:canonicalProfile.channel_user_id};
                                }
                            } catch (ignoredProviderContext) {}
                        }
                        return {version:1,refresh_requested:true,service_id:serviceId,context_profile:settings.context_profile,
                            conversation_id:conversationId,interaction_id:interactionId,create_message_id:messageId};
                    } catch (ignoredConversationAuthenticationError) {
                        return null;
                    }
                })();
                if (conversationAuthentication === null) {
                    response.setStatus(403);
                    response.setBody({detail:'Conversation authentication unavailable'});
                    return;
                }
            }

            var authorizedResponse = {authorized_agents:authorizedAgentIds,assistant_settings:settings};
            if (callerBinding !== null) authorizedResponse.caller_binding = callerBinding;
            if (conversationAuthentication !== null) authorizedResponse.conversation_authentication = conversationAuthentication;
            if (providerContextBinding !== null) authorizedResponse.provider_context_binding = providerContextBinding;
            if (payload.conversationModelVersion === 1) {
                try {
                    authorizedResponse.conversation_model = new LocalLLMVoiceAssistantSettings().getConversationModel(serviceId);
                } catch (ignoredConversationModel) {
                    authorizedResponse.conversation_model = {version:1,status:'unavailable'};
                }
            }
            response.setBody(authorizedResponse);
            response.setStatus(200);
        } catch (ignoredSettingsError) {
            response.setStatus(503);
            response.setBody({detail:'Assistant settings unavailable'});
        }
        return;
    }
	response.setBody(authorizedAgentIds);
	response.setStatus(200);

})(request, response);