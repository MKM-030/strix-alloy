/* SOURCE ONLY. One fixed-service CREATE through the normal public native handler.
 * Requires the separately approved own API grant. No native deployment is implied.
 */
(function process(request, response) {
    'use strict';
    var SERVICE = '8aa131d793f787105c8132d47aba1095';
    var PROFILE = 'c623e20f93374354e7f2b9fa6aba1081';
    var REQUIRED_AGENT = 'a6337ddf93f787105c8132d47aba1058';
    var APP = '200af60f93fb4354e7f2b9fa6aba107d';
    var PROVIDER = 'd6eadc7a53301010ad77ddeeff7b124a';
    var CHANNEL = '51cdaa4c53a710105893ddeeff7b129c';
    var INBOUND = 'scc-local-voice';
    var GUID = /^[0-9a-f]{32}$/;
    var originalUser = '', originalName = '';
    function fail(status) {
        response.setStatus(status);
        response.setBody({status:'failure',detail:'Local caller create unavailable'});
    }
    function own(object, key) { return Object.prototype.hasOwnProperty.call(object,key); }
    function string(value) { return value === null || typeof value === 'undefined' ? '' : String(value); }
    function samePrincipal() {
        return String(gs.getUserID() || '') === originalUser && String(gs.getUserName() || '') === originalName &&
            originalName !== 'guest' && gs.hasRole('admin') === true;
    }
    function readable(record, fields) {
        if (record.canRead() !== true) return null;
        var values = {}, i, element, value;
        // Check every required right before reading any field value.
        for (i = 0; i < fields.length; i++) {
            if (record.isValidField(fields[i]) !== true) return null;
            element = record.getElement(fields[i]);
            if (element === null || typeof element === 'undefined' || element.canRead() !== true) return null;
        }
        for (i = 0; i < fields.length; i++) {
            value = record.getValue(fields[i]);
            values[fields[i]] = value === null || typeof value === 'undefined' ? '' : String(value);
        }
        return values;
    }
    function principal() {
        var fields = ['sys_id','user_name','email','active','locked_out'];
        var self = new GlideRecordSecure('sys_user');
        if (self.isValid() !== true || self.get(originalUser) !== true) return null;
        var value = readable(self,fields);
        if (value === null || value.sys_id !== originalUser || value.user_name !== originalName || !value.email ||
            value.active !== '1' || value.locked_out !== '0' || /[\r\n\x00]/.test(value.email)) return null;
        var matches = new GlideRecord('sys_user');
        if (matches.isValid() !== true || matches.isValidField('email') !== true ||
            matches.isValidField('active') !== true || matches.isValidField('locked_out') !== true) return null;
        matches.addQuery('email',value.email);
        matches.addQuery('active',true);
        matches.addQuery('locked_out',false);
        matches.setLimit(2);
        matches.query();
        var count = 0, candidate;
        while (matches.next()) {
            candidate = readable(matches,fields);
            if (candidate === null || ++count >= 2 || JSON.stringify(candidate) !== JSON.stringify(value)) return null;
        }
        return count === 1 ? value : null;
    }
    function validSettings(settings) {
        return !!settings && settings.version === 1 && settings.service_id === SERVICE && settings.context_profile === PROFILE &&
            typeof settings.language === 'string' && settings.language.length <= 64 &&
            /^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$/.test(settings.language);
    }
    function newAlias(alias) {
        // Complete ordinary existence check: any prior alias refuses, even if its row is hidden.
        // No values are read from a possibly denied row and no alias is reused or reassigned.
        var previous = new GlideRecord('sys_cs_channel_user_profile');
        if (previous.isValid() !== true || previous.isValidField('channel') !== true || previous.isValidField('channel_user_id') !== true) return false;
        previous.addQuery('channel',CHANNEL);
        previous.addQuery('channel_user_id',alias);
        previous.setLimit(1);
        previous.query();
        return previous.next() !== true;
    }
    function fresh(created) {
        if (!/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/.test(created)) return false;
        var when = new GlideDateTime();
        when.setValue(created);
        if (String(when.getValue()) !== created) return false;
        var age = Number(new GlideDateTime().getNumericValue()) - Number(when.getNumericValue());
        return isFinite(age) && age >= 0 && age <= 45000;
    }
    function ownedCreate(conversationId, interactionId, messageId, alias) {
        var proofs = [];
        function read(table, id, fields, remember) {
            if (!GUID.test(id)) return null;
            var record = new GlideRecordSecure(table);
            if (record.isValid() !== true || record.get(id) !== true) return null;
            var values = readable(record,fields);
            if (values === null || values.sys_id !== id) return null;
            if (remember) proofs.push({table:table,id:id,fields:fields,values:JSON.stringify(values)});
            return values;
        }
        var conversation = read('sys_cs_conversation',conversationId,
            ['sys_id','consumer_account','context_profile','current_device','state','sys_created_on'],true);
        if (conversation === null || conversation.state !== 'open' || conversation.context_profile !== PROFILE ||
            !conversation.current_device || !conversation.current_device.trim() || !fresh(conversation.sys_created_on)) return false;
        var account = read('sys_cs_consumer_account',conversation.consumer_account,
            ['sys_id','provider_application','channel_user_profile','consumer'],true);
        if (account === null || account.provider_application !== APP) return false;
        var app = read('sys_cs_provider_application',APP,['sys_id','inbound_id','provider'],true);
        if (app === null || app.inbound_id !== INBOUND || app.provider !== PROVIDER) return false;
        var profileFields = ['sys_id','active','user_table','user_document','channel_user_id','channel'];
        var profile = read('sys_cs_channel_user_profile',account.channel_user_profile,profileFields,true);
        if (profile === null || profile.active !== '1' || profile.user_table !== 'sys_user' ||
            profile.user_document !== originalUser || profile.channel_user_id !== alias || profile.channel !== CHANNEL) return false;
        var consumer = read('sys_cs_consumer',account.consumer,['sys_id','user_id','inactive'],true);
        if (consumer === null || consumer.user_id !== originalUser || consumer.inactive !== '0') return false;
        var interactionFields = ['sys_id','channel_metadata_document','provider_application','state','active','type','sys_created_on'];
        var interaction = read('interaction',interactionId,interactionFields,true);
        if (interaction === null || interaction.channel_metadata_document !== conversationId || interaction.provider_application !== APP ||
            (interaction.state !== 'new' && interaction.state !== 'work_in_progress') || interaction.active !== '1' ||
            interaction.type !== 'chat' || !fresh(interaction.sys_created_on)) return false;
        var message = read('sys_cs_message',messageId,
            ['sys_id','conversation','consumer_account','session','direction','message_type','payload','sys_created_on'],true);
        if (message === null || message.conversation !== conversationId || message.consumer_account !== account.sys_id ||
            message.direction !== 'outbound' || message.message_type !== 'action' || !fresh(message.sys_created_on)) return false;
        var create = JSON.parse(message.payload);
        if (!create || create.type !== 'CreateConversation' || create.topicId !== conversationId || create.interactionId !== interactionId ||
            Object.keys(create).sort().join(',') !== 'interactionId,topicId,type') return false;
        var session = read('sys_cs_session',message.session,
            ['sys_id','consumer_account','consumer','device_id','device_type','end_time'],true);
        if (session === null || session.consumer_account !== account.sys_id || session.consumer !== consumer.sys_id ||
            session.device_id !== conversation.current_device || session.device_type !== 'Bot to Bot' || session.end_time !== '') return false;
        function unique(table, conditions, fields, expected) {
            var record = new GlideRecord(table), i, count = 0, values;
            if (record.isValid() !== true) return false;
            for (i = 0; i < conditions.length; i++) {
                if (record.isValidField(conditions[i][0]) !== true) return false;
                record.addQuery(conditions[i][0],conditions[i][1]);
            }
            record.setLimit(2);
            record.query();
            while (record.next()) {
                values = readable(record,fields);
                if (values === null || ++count >= 2 || JSON.stringify(values) !== JSON.stringify(expected)) return false;
            }
            return count === 1;
        }
        if (!unique('interaction',[['channel_metadata_document',conversationId]],interactionFields,interaction) ||
            !unique('sys_cs_channel_user_profile',[['channel',CHANNEL],['channel_user_id',alias]],profileFields,profile)) return false;
        for (var i = 0; i < proofs.length; i++) {
            var proof = proofs[i], current = read(proof.table,proof.id,proof.fields,false);
            if (current === null || JSON.stringify(current) !== proof.values) return false;
        }
        return samePrincipal() && fresh(conversation.sys_created_on);
    }
    try {
        var input = request && request.body && request.body.data;
        if (!input || typeof input !== 'object' || Array.isArray(input) ||
            Object.keys(input).sort().join(',') !== 'clientMessageId,clientSessionId,requestId,version' || input.version !== 1 ||
            typeof input.requestId !== 'string' || !GUID.test(input.requestId) ||
            typeof input.clientSessionId !== 'string' || !GUID.test(input.clientSessionId) ||
            typeof input.clientMessageId !== 'string' || !GUID.test(input.clientMessageId) ||
            input.requestId === input.clientSessionId || input.requestId === input.clientMessageId || input.clientSessionId === input.clientMessageId) {
            fail(400); return;
        }
        var requestId = input.requestId, sessionId = input.clientSessionId, clientMessageId = input.clientMessageId;
        var alias = 'voice-' + sessionId;
        var authorization = request.getHeader('Authorization');
        var providerToken = request.getHeader('token');
        if (typeof authorization !== 'string' || authorization.length > 8192 ||
            !/^Bearer [A-Za-z0-9._~+\/-]+=*$/i.test(authorization) ||
            typeof providerToken !== 'string' || !/^[\x21-\x7e]{1,8192}$/.test(providerToken)) {
            fail(403); return;
        }
        originalUser = String(gs.getUserID() || '');
        originalName = String(gs.getUserName() || '');
        if (!GUID.test(originalUser) || !originalName || originalName === 'guest' || !samePrincipal()) { fail(403); return; }
        // A fixed server-owned view supplies only the existing native service argument.
        // Native checks still receive the unmodified original Bearer and the real GS caller.
        var nativeRequest = {body:{data:{serviceId:SERVICE}},getHeader:function(name) {
            return String(name).toLowerCase() === 'authorization' ? authorization : null;
        }};
        var nativeSink = {setStatus:function() {},setBody:function() {}};
        var voiceRest = new VoiceRestUtils();
        if (voiceRest.validateServiceId(nativeRequest,nativeSink) !== true ||
            voiceRest.validateServiceAuthorization(nativeRequest,nativeSink) !== true) { fail(403); return; }
        var agents = new VoiceAgentUtils().getAuthorizedAgentIds(SERVICE,false), includesRequired = false;
        if (!Array.isArray(agents) || agents.length < 1 || agents.length > 256) { fail(403); return; }
        for (var i = 0; i < agents.length; i++) {
            if (typeof agents[i] !== 'string' || !GUID.test(agents[i])) { fail(403); return; }
            if (agents[i] === REQUIRED_AGENT) includesRequired = true;
        }
        if (!includesRequired) { fail(403); return; }
        var caller = principal();
        if (caller === null) { fail(403); return; }
        var settings = new LocalLLMVoiceAssistantSettings().getSettings(SERVICE);
        if (!validSettings(settings)) { fail(503); return; }
        var language = settings.language;
        if (!newAlias(alias)) { fail(409); return; }
        var rechecked = principal();
        if (!samePrincipal() || rechecked === null || JSON.stringify(caller) !== JSON.stringify(rechecked) ||
            !validSettings(settings) || settings.language !== language) { fail(403); return; }
        var nativePayload = {requestId:requestId,appInboundId:INBOUND,clientSessionId:sessionId,userId:alias,
            emailId:caller.email,action:'CREATE_CONVERSATION',syncResponse:true,
            message:{text:'',typed:true,clientMessageId:clientMessageId},clientVariables:{voiceSessionId:sessionId},
            contextVariables:{interaction_requester_session_language:language,interaction_user_language:language,
                requester_session_language:language,voice_assistant:SERVICE,interaction_ai_voice:'true',global_context_profile:PROFILE}};
        var nativeHeaders = {token:providerToken,authorization:authorization};
        var handler = new sn_va_as_service.VABotToBotRestMessageHandler();
        if (!samePrincipal()) { fail(403); return; }
        // The only lifecycle invocation: normal public handler, exactly one CREATE, no retry.
        var nativeResult = handler.processPayload(nativePayload,nativeHeaders);
        if (!samePrincipal() || !nativeResult || nativeResult.status !== 200 || !nativeResult.content ||
            typeof nativeResult.content !== 'object' || Array.isArray(nativeResult.content)) { fail(503); return; }
        var content = nativeResult.content;
        if (content.error || (typeof content.status !== 'undefined' && content.status !== 'success') ||
            content.requestId !== requestId || content.clientSessionId !== sessionId || content.userId !== alias ||
            (typeof content.appInboundId !== 'undefined' && content.appInboundId !== INBOUND) ||
            !content.message || content.message.clientMessageId !== clientMessageId ||
            !Array.isArray(content.body) || content.body.length < 1 || content.body.length > 32) { fail(503); return; }
        var control = null;
        for (i = 0; i < content.body.length; i++) {
            var item = content.body[i];
            if (item && item.uiType === 'ActionMsg' && item.actionType === 'CreateConversation') {
                if (control !== null) { fail(503); return; }
                control = item;
            }
        }
        if (control === null || typeof control.conversationId !== 'string' || !GUID.test(control.conversationId) ||
            typeof control.messageId !== 'string' || !GUID.test(control.messageId)) { fail(503); return; }
        var interactionId = control.interactionId;
        if (typeof interactionId === 'undefined') interactionId = content.interactionId;
        if (typeof interactionId !== 'string' || !GUID.test(interactionId) ||
            (typeof content.interactionId !== 'undefined' && content.interactionId !== interactionId) ||
            !ownedCreate(control.conversationId,interactionId,control.messageId,alias)) { fail(503); return; }
        rechecked = principal();
        if (!samePrincipal() || rechecked === null || JSON.stringify(caller) !== JSON.stringify(rechecked) ||
            !validSettings(settings) || settings.language !== language) { fail(503); return; }
        var created = {requestId:requestId,clientSessionId:sessionId,userId:alias,body:[{
            uiType:'ActionMsg',actionType:'CreateConversation',conversationId:control.conversationId,
            messageId:control.messageId,interactionId:interactionId}]};
        if (typeof content.nowSessionId !== 'undefined' && content.nowSessionId !== null && content.nowSessionId !== '') {
            if (typeof content.nowSessionId !== 'string' || content.nowSessionId.length >= 256 ||
                !/^[\x20-\x7e]+$/.test(content.nowSessionId) || content.nowSessionId !== content.nowSessionId.trim()) { fail(503); return; }
            created.nowSessionId = content.nowSessionId;
        }
        response.setStatus(200);
        response.setBody({status:'success',created:created});
    } catch (ignoredLocalCallerCreateError) {
        // A native runtime/ACL/contract refusal is terminal. Never change scope or replay CREATE.
        fail(503);
    }
})(request, response);
