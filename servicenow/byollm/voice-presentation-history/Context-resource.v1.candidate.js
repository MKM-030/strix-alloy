/* TASK46 owned Global context STORE / read-only STATUS. Same existing Bot token and CREATE ownership. */
(function process(request, response) {
    var IN = 'scc-local-voice', APP = '200af60f93fb4354e7f2b9fa6aba107d';
    var tried = false, stage = 'provider_auth';
    function reply(status, body) { response.setStatus(status); response.setBody(body); }
    function need(value, status, code) { if (!value) throw {scc: true, status: status, code: code}; }
    function sysId(value) { return typeof value === 'string' && /^[0-9a-f]{32}$/.test(value); }
    function exactKeys(value, allowed) {
        return value && typeof value === 'object' && !Array.isArray(value) && Object.keys(value).every(function(key) { return allowed.indexOf(key) !== -1; });
    }
    function exactRow(pid, role, message, allowMissing) {
        var row = new GlideRecord('sn_aia_message');
        if (pid) row.addQuery('execution_plan', pid);
        row.addQuery('role', role); row.addQuery('message', message); row.addQuery('user_message', message);
        row.setLimit(2); row.query();
        if (!row.next()) { need(allowMissing, 409, 'context_note_missing'); return null; }
        var found = {planId: String(row.getValue('execution_plan'))};
        need(sysId(found.planId) && !row.next(), 503, 'context_storage_ambiguous');
        return found;
    }
    function planNotes(pid, role, protocol) {
        var rows = [], row = new GlideRecord('sn_aia_message');
        row.addQuery('execution_plan', pid); row.addQuery('role', role); row.addQuery('message', 'STARTSWITH', protocol.notePrefix);
        row.setLimit(33); row.query();
        while (row.next()) {
            rows.push({message: String(row.getValue('message')), user_message: String(row.getValue('user_message'))});
            need(rows.length <= 32, 409, 'context_snapshot_conflict');
        }
        try { return protocol.orderedNotes(rows); }
        catch (error) { need(false, 409, 'context_snapshot_conflict'); }
    }
    function diagnostic(error, known) {
        try {
            var errorName = known ? 'SCCGuardFailure' : 'UnknownError';
            if (!known && error && typeof error.name === 'string' && /^[A-Za-z_$][A-Za-z0-9_.$]{0,95}$/.test(error.name)) errorName = error.name;
            gs.error('[SCC_VOICE_CONTEXT_STAGE_V1] ' + JSON.stringify({stage: stage, errorName: errorName,
                failureClass: tried ? 'append_attempted_uncertain' : 'operation_failed_before_append'}));
        } catch (ignoredDiagnostic) {}
    }
    try {
        var token = request.getHeader('token');
        need(typeof token === 'string' && token.length > 0 && token.length <= 8192, 401, 'provider_auth_failed');
        need(new sn_cs.CustomAdapterAuthUtil().validateToken(APP, JSON.stringify({token: token})), 401, 'provider_auth_failed');
        stage = 'provider_binding';
        var provider = new GlideRecord('sys_cs_provider_application');
        need(provider.get(APP) && String(provider.getValue('inbound_id') || '') === IN, 503, 'provider_binding_unavailable');
        stage = 'request_validation';
        var data = request.body.nextEntry();
    // BEGIN SCC_PRESENTATION_HISTORY_V1
    if (data && data.operation === 'presentation_history_store') {
        // Original token validation has already succeeded. The separate helper
        // verifies the issued finite grant through public provider context only.
        try {
            var historyResult = JSON.parse(String(new global.SCCVoicePresentationHistoryV1().storeJSON(JSON.stringify(data))));
            reply(historyResult && historyResult.status === 'success' && historyResult.stored === true ? 200 : 503, historyResult);
        } catch (ignoredOptionalHistory) {
            reply(503, {status:'failure',state:'presentation_history_unavailable',stored:false,hostEmitted:false,heard:false,promptIncluded:false});
        }
        return;
    }
    // END SCC_PRESENTATION_HISTORY_V1
        need(exactKeys(data, ['operation', 'requestId', 'appInboundId', 'clientSessionId', 'userId', 'conversationBinding', 'revision', 'caller_updates']), 400, 'invalid_context_request');
        var operation = typeof data.operation === 'undefined' ? 'store' : data.operation;
        var binding = data.conversationBinding;
        need((operation === 'store' || operation === 'status') && data.appInboundId === IN && sysId(data.requestId) && sysId(data.clientSessionId) &&
            typeof data.userId === 'string' && data.userId.length > 0 && data.userId.length <= 128 &&
            exactKeys(binding, ['source', 'conversationId', 'creationMessageId', 'createRequestId', 'interactionId']) && binding.source === 'servicenow_create_conversation' &&
            sysId(binding.conversationId) && sysId(binding.creationMessageId) && sysId(binding.createRequestId) &&
            (!Object.prototype.hasOwnProperty.call(binding, 'interactionId') || sysId(binding.interactionId)) &&
            typeof data.revision === 'number' && data.revision % 1 === 0 && data.revision > 0 && data.revision <= 2147483647 &&
            typeof data.caller_updates === 'string' && data.caller_updates.length > 0 && data.caller_updates.length <= 8000 &&
            unescape(encodeURIComponent(data.caller_updates)).length <= 12000, 400, 'invalid_context_request');
        stage = 'ownership_validation';
        var cm = new GlideRecord('sys_cs_message');
        need(cm.get(binding.creationMessageId) && String(cm.getValue('conversation') || '') === binding.conversationId, 403, 'conversation_binding_mismatch');
        var cv = new GlideRecord('sys_cs_conversation');
        need(cv.get(binding.conversationId), 403, 'conversation_binding_mismatch');
        var pu = cv.consumer_account && cv.consumer_account.channel_user_profile && cv.consumer_account.channel_user_profile.channel_user_id;
        need(String(pu || '') === data.userId, 403, 'conversation_binding_mismatch');
        var ix = new GlideRecord('interaction');
        ix.addQuery('channel_metadata_document', binding.conversationId); ix.setLimit(2); ix.query();
        need(ix.next() && String(ix.getValue('provider_application') || '') === APP && (!binding.interactionId || ix.getUniqueValue() === binding.interactionId) && !ix.next(), 403, 'conversation_binding_mismatch');
        stage = 'user_role';
        var role = sn_aia.AIAgentConstants.ROLES.USER;
        need(typeof role === 'string' && /^[a-z_]{1,32}$/.test(role), 503, 'user_role_unavailable');
        stage = 'context_protocol';
        var protocol = new global.SCCVoiceCallerContext();
        var message = protocol.noteText(data.requestId, data.revision, data.caller_updates);
        var plan = new GlideRecord('sn_aia_execution_plan'), pid, alreadyPresent = false, promptIncluded = false;
        if (operation === 'status') {
            stage = 'status_note_read';
            var found = exactRow(null, role, message, false); pid = found.planId;
            need(plan.get(pid) && String(plan.getValue('conversation') || '') === binding.conversationId, 403, 'conversation_binding_mismatch');
            stage = 'status_receipt_read';
            promptIncluded = !!exactRow(pid, role, protocol.ackText(protocol.parseNote(message)), true);
        } else {
            stage = 'active_plan';
            plan.addQuery('conversation', binding.conversationId); plan.addQuery('state', 'in_progress'); plan.setLimit(2); plan.query();
            need(plan.next(), 409, 'one_active_plan_required'); pid = plan.getUniqueValue();
            need(sysId(pid) && !plan.next(), 409, 'one_active_plan_required');
            stage = 'storage_read';
            var notes = planNotes(pid, role, protocol);
            alreadyPresent = !!exactRow(pid, role, message, true);
            if (!alreadyPresent) {
                for (var n = 0; n < notes.length; n++) need(notes[n].contextRequestId !== data.requestId && notes[n].revision !== data.revision, 409, 'context_snapshot_conflict');
                if (notes.length) {
                    var latest = notes[notes.length - 1];
                    need(data.revision > latest.revision && data.caller_updates.length > latest.text.length && data.caller_updates.indexOf(latest.text) === 0, 409, 'context_snapshot_conflict');
                }
                need(notes.length < 32, 409, 'context_snapshot_conflict');
                stage = 'append_guard';
                need(plan.get(pid) && String(plan.getValue('conversation') || '') === binding.conversationId && String(plan.getValue('state') || '') === 'in_progress', 409, 'one_active_plan_required');
                stage = 'memory_append'; tried = true;
                new sn_aia.AgentCommunicationUtil().addMessageToShortTermMemory(pid, role, message, message);
                stage = 'storage_readback';
                need(!!exactRow(pid, role, message, true), 502, 'context_append_uncertain');
            }
        }
        reply(200, {status: 'success', state: operation === 'status' ? 'caller_context_status' : 'caller_context_stored',
            requestId: data.requestId, contextRequestId: data.requestId, revision: data.revision, conversationId: binding.conversationId,
            executionPlanId: pid, contextStored: true, alreadyPresent: operation === 'status' ? true : alreadyPresent,
            promptIncluded: promptIncluded, ingested: promptIncluded});
    } catch (error) {
        var known = error && error.scc === true;
        var rejected = known && !tried && [401, 400, 403, 409].indexOf(error.status) !== -1;
        if (!rejected) diagnostic(error, known);
        reply(rejected ? error.status : 200, {status: 'failure', state: 'caller_context_uncertain', contextStored: false,
            promptIncluded: false, ingested: false, code: known ? error.code : 'context_operation_failed', stage: stage});
    }
})(request, response);
