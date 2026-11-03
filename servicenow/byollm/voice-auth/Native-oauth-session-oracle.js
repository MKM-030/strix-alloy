/* Portable, read-only native CS metadata oracle. No work is performed on load. */
(function (root, factory) {
    var api = factory();
    if (typeof module === 'object' && module.exports) module.exports = api;
    else root.SccNativeOAuthOracle = api;
}(this, function () {
    'use strict';
    var ID = /^[0-9a-f]{32}$/;
    var UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
    var ACTIVE = ['open', 'chatInProgress', 'autoPilotInProgress'];
    var TERMINAL = ['completed', 'faulted', 'canceled', 'chatEnded', 'deleted'];
    var CONVERSATION_FIELDS = ['sys_id', 'consumer', 'consumer_account', 'vendor', 'context_profile',
        'current_device', 'state', 'sys_created_on', 'sys_updated_on', 'sys_mod_count'];
    var SESSION_FIELDS = ['sys_id', 'consumer', 'consumer_account', 'vendor', 'device_id', 'device_type', 'sys_created_on'];

    function str(value) { return value === null || typeof value === 'undefined' ? '' : String(value); }
    function has(object, key) { return Object.prototype.hasOwnProperty.call(object, key); }
    function validUuid(value) { return typeof value === 'string' && UUID.test(value); }
    function unavailable() { return {available: false, messages: null, plans: null, genai: null, tools: null}; }
    function need(value, code) { if (!value) throw {oracleFailure: code}; }
    function reference(value) {
        need(value === '' || ID.test(value), 'INVALID_DATA');
        return value === '' ? null : value;
    }
    function ids(rows) {
        var result = [], i;
        for (i = 0; i < rows.length; i++) result.push(rows[i].sys_id);
        return result;
    }
    function mapIds(rows) {
        var result = {}, i;
        for (i = 0; i < rows.length; i++) result[rows[i].sys_id] = true;
        return result;
    }
    function empty(request) {
        request = request || {};
        return {version: 1, phase: ['before', 'after', 'terminal'].indexOf(request.phase) >= 0 ? request.phase : null,
            attemptId: validUuid(request.attemptId) ? request.attemptId : null,
            deviceId: validUuid(request.deviceId) ? request.deviceId : null,
            ok: false, failureCode: null, principalHash: null, server: {startedMs: null, finishedMs: null},
            contextUnchanged: false, counts: {activeConversations: null, unknownStates: null},
            conversations: [], sessions: [], deviceConversations: [], deviceSessions: [], unownedDeviceRows: null,
            activity: unavailable(), messageSessionLinks: []};
    }

    function createNativeOAuthOracle(dependencies) {
        return {inspect: function (request) {
            var result, initial = null, gs, seen = {}, d = dependencies || {};
            // All raw identities, context and historical device strings stay in this invocation.
            function context() {
                var user = gs.getUser(), impersonation = new d.GlideImpersonate();
                need(user && typeof user.getPreference === 'function' && impersonation &&
                    typeof impersonation.isImpersonating === 'function', 'INVALID_DEPENDENCIES');
                return {uid: str(gs.getUserID()), name: str(gs.getUserName()), admin: gs.hasRole('admin') === true,
                    impersonating: impersonation.isImpersonating(), instance: str(gs.getProperty('instance_name')),
                    scope: str(gs.getCurrentScopeName()), application: str(gs.getCurrentApplicationId()),
                    userSet: str(user.getPreference('sys_update_set')), systemSet: str(gs.getPreference('sys_update_set'))};
            }
            function unchanged() {
                if (initial) need(JSON.stringify(context()) === JSON.stringify(initial), 'CONTEXT_DRIFT');
            }
            function clock() {
                var date = new d.GlideDateTime(), value = Number(date.getNumericValue());
                need(isFinite(value) && value >= 0 && Math.floor(value) === value && value <= 9007199254740991, 'INVALID_DATA');
                return value;
            }
            function timestamp(value) {
                need(/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/.test(value), 'INVALID_DATA');
                var date = new d.GlideDateTime();
                date.setValue(value);
                need(str(date.getValue()) === value, 'INVALID_DATA');
                var numeric = Number(date.getNumericValue());
                need(isFinite(numeric) && numeric >= 0 && Math.floor(numeric) === numeric && numeric <= 9007199254740991, 'INVALID_DATA');
                return numeric;
            }
            function rights(record, fields) {
                need(record.canRead() === true, 'READ_DENIED');
                for (var i = 0; i < fields.length; i++) {
                    var element = record.getElement(fields[i]);
                    need(element !== null && typeof element !== 'undefined' && element.canRead() === true, 'READ_DENIED');
                }
            }
            function read(table, conditions, fields, cap) {
                unchanged();
                var record = new d.GlideRecord(table), allFields = fields.slice(0), rows = [], i, row, key, previous;
                need(record.isValid() === true, 'SCHEMA_UNAVAILABLE');
                for (i = 0; i < conditions.length; i++) if (allFields.indexOf(conditions[i][0]) < 0) allFields.push(conditions[i][0]);
                for (i = 0; i < allFields.length; i++) need(record.isValidField(allFields[i]) === true, 'SCHEMA_UNAVAILABLE');
                // Table/element checks before query; every returned row gets its own checks as well.
                rights(record, allFields);
                for (i = 0; i < conditions.length; i++) record.addQuery(conditions[i][0], conditions[i][1], conditions[i][2]);
                record.orderBy('sys_id');
                record.setLimit(cap + 1);
                record.query();
                unchanged();
                var count = 0;
                while (record.next()) {
                    need(++count <= cap, 'READ_LIMIT');
                    rights(record, allFields);
                    row = {};
                    for (i = 0; i < allFields.length; i++) row[allFields[i]] = str(record.getValue(allFields[i]));
                    need(ID.test(row.sys_id), 'INVALID_DATA');
                    // Check the observed filters too: a query cannot confer ownership by itself.
                    for (i = 0; i < conditions.length; i++) {
                        need(conditions[i][1] === 'IN' ? conditions[i][2].split(',').indexOf(row[conditions[i][0]]) >= 0 :
                            row[conditions[i][0]] === conditions[i][2], 'INVALID_DATA');
                    }
                    key = table + ':' + row.sys_id;
                    previous = seen[key];
                    if (previous) need(previous === JSON.stringify(row), 'INVALID_DATA');
                    else seen[key] = JSON.stringify(row);
                    rows.push(row);
                }
                unchanged();
                return union(rows, [], cap);
            }
            function union(a, b, cap) {
                var output = [], found = {}, all = a.concat(b), i, row;
                for (i = 0; i < all.length; i++) {
                    row = all[i];
                    if (has(found, row.sys_id)) need(found[row.sys_id] === JSON.stringify(row), 'INVALID_DATA');
                    else {
                        found[row.sys_id] = JSON.stringify(row);
                        output.push(row);
                        need(output.length <= cap, 'READ_LIMIT');
                    }
                }
                output.sort(function (x, y) {return x.sys_id < y.sys_id ? -1 : x.sys_id > y.sys_id ? 1 : 0;});
                return output;
            }
            function by(table, field, values, fields, cap) {
                return values.length ? read(table, [[field, 'IN', values.join(',')]], fields, cap) : [];
            }
            function owned(row, consumerMap, accountMap) {
                reference(row.consumer); reference(row.consumer_account);
                return has(consumerMap, row.consumer) || has(accountMap, row.consumer_account);
            }
            function conversation(row) {
                var mod = row.sys_mod_count;
                need(/^(0|[1-9][0-9]*)$/.test(mod) && Number(mod) <= 9007199254740991, 'INVALID_DATA');
                var created = timestamp(row.sys_created_on), updated = timestamp(row.sys_updated_on);
                need(updated >= created, 'INVALID_DATA');
                return {id: row.sys_id, consumerId: reference(row.consumer), accountId: reference(row.consumer_account),
                    vendorId: reference(row.vendor), profileId: reference(row.context_profile),
                    deviceId: row.current_device === request.deviceId ? request.deviceId : null,
                    state: row.state, createdMs: created, updatedMs: updated, modCount: Number(mod)};
            }
            function session(row) {
                return {id: row.sys_id, consumerId: reference(row.consumer), accountId: reference(row.consumer_account),
                    vendorId: reference(row.vendor), deviceId: row.device_id === request.deviceId ? request.deviceId : null,
                    deviceType: ['mweb', 'ios', 'android', 'nowassistpanel'].indexOf(row.device_type) >= 0 ? row.device_type : null,
                    createdMs: timestamp(row.sys_created_on)};
            }
            function activity(deviceRows) {
                if (!deviceRows.length) return {counts: {available: true, messages: 0, plans: 0, genai: 0, tools: 0}, links: []};
                try {
                    var values = ids(deviceRows), messages = by('sys_cs_message', 'conversation', values, ['sys_id', 'conversation', 'session'], 512),
                        plans = by('sn_aia_execution_plan', 'conversation', values, ['sys_id', 'conversation'], 512),
                        genai = by('sys_generative_ai_log', 'conversation', values, ['sys_id', 'conversation'], 512),
                        tools = by('sn_aia_tools_execution', 'execution_plan_id', ids(plans), ['sys_id', 'execution_plan_id'], 512),
                        links = [], linkMap = {}, i, referenceId, key;
                    for (i = 0; i < messages.length; i++) {
                        referenceId = reference(messages[i].session);
                        need(ID.test(messages[i].conversation), 'INVALID_DATA');
                        key = messages[i].conversation + ':' + (referenceId || '');
                        if (!has(linkMap, key)) {
                            linkMap[key] = true;
                            links.push({conversationId: messages[i].conversation, sessionId: referenceId});
                        }
                    }
                    return {counts: {available: true, messages: messages.length, plans: plans.length, genai: genai.length, tools: tools.length}, links: links};
                } catch (ignoredActivity) {
                    // Activity is optional evidence, never a reason to invent zero or weaken snapshot checks.
                    unchanged();
                    return {counts: unavailable(), links: []};
                }
            }
            try {
                result = empty(request);
                need(request && typeof request === 'object' && request.version === 1 && result.phase !== null &&
                    result.attemptId !== null && result.deviceId !== null, 'INVALID_REQUEST');
                var keys = Object.keys(request), i;
                need(keys.length === 4, 'INVALID_REQUEST');
                for (i = 0; i < keys.length; i++) need(['version', 'phase', 'attemptId', 'deviceId'].indexOf(keys[i]) >= 0, 'INVALID_REQUEST');
                gs = d.gs;
                need(gs && typeof d.GlideRecord === 'function' && typeof d.GlideDateTime === 'function' &&
                    typeof d.GlideDigest === 'function' && typeof d.GlideImpersonate === 'function', 'INVALID_DEPENDENCIES');
                var methods = ['getUserID', 'getUserName', 'hasRole', 'getProperty', 'getCurrentScopeName', 'getCurrentApplicationId', 'getUser', 'getPreference'];
                for (i = 0; i < methods.length; i++) need(typeof gs[methods[i]] === 'function', 'INVALID_DEPENDENCIES');
                initial = context();
                need(ID.test(initial.uid) && initial.name && initial.name.toLowerCase() !== 'guest' && initial.admin &&
                    initial.impersonating === false, 'PRINCIPAL_REFUSED');
                var started = clock(), digest = new d.GlideDigest();
                need(digest && typeof digest.getSHA256Hex === 'function', 'INVALID_DEPENDENCIES');
                var principalHash = str(digest.getSHA256Hex(initial.uid)).toLowerCase();
                need(/^[0-9a-f]{64}$/.test(principalHash), 'INVALID_DATA');
                var consumers = read('sys_cs_consumer', [['user_id', '=', initial.uid]], ['sys_id', 'user_id'], 16),
                    profiles = read('sys_cs_channel_user_profile', [['user_table', '=', 'sys_user'], ['user_document', '=', initial.uid]],
                        ['sys_id', 'user_table', 'user_document'], 512),
                    consumerIds = ids(consumers), profileIds = ids(profiles), consumerMap = mapIds(consumers), profileMap = mapIds(profiles),
                    accountFields = ['sys_id', 'consumer', 'channel_user_profile', 'vendor'],
                    accounts = union(by('sys_cs_consumer_account', 'consumer', consumerIds, accountFields, 512),
                        by('sys_cs_consumer_account', 'channel_user_profile', profileIds, accountFields, 512), 512);
                for (i = 0; i < accounts.length; i++) {
                    reference(accounts[i].consumer); reference(accounts[i].channel_user_profile); reference(accounts[i].vendor);
                    need(has(consumerMap, accounts[i].consumer) || has(profileMap, accounts[i].channel_user_profile), 'INVALID_DATA');
                }
                var accountIds = ids(accounts), accountMap = mapIds(accounts),
                    conversations = union(by('sys_cs_conversation', 'consumer', consumerIds, CONVERSATION_FIELDS, 512),
                        by('sys_cs_conversation', 'consumer_account', accountIds, CONVERSATION_FIELDS, 512), 512),
                    sessions = union(by('sys_cs_session', 'consumer', consumerIds, SESSION_FIELDS, 512),
                        by('sys_cs_session', 'consumer_account', accountIds, SESSION_FIELDS, 512), 512),
                    deviceConversations = read('sys_cs_conversation', [['current_device', '=', request.deviceId]], CONVERSATION_FIELDS, 512),
                    deviceSessions = read('sys_cs_session', [['device_id', '=', request.deviceId]], SESSION_FIELDS, 512),
                    active = 0, unknown = 0, unowned = 0, safeConversations = [], safeSessions = [], safeDeviceConversations = [], safeDeviceSessions = [];
                // An owned device match must also have been present in the complete ownership union.
                var conversationMap = mapIds(conversations), sessionMap = mapIds(sessions);
                for (i = 0; i < conversations.length; i++) {
                    need(owned(conversations[i], consumerMap, accountMap), 'INVALID_DATA');
                    safeConversations.push(conversation(conversations[i]));
                    if (ACTIVE.indexOf(conversations[i].state) >= 0) active++;
                    else if (TERMINAL.indexOf(conversations[i].state) < 0) unknown++;
                }
                for (i = 0; i < sessions.length; i++) {
                    need(owned(sessions[i], consumerMap, accountMap), 'INVALID_DATA');
                    safeSessions.push(session(sessions[i]));
                }
                for (i = 0; i < deviceConversations.length; i++) {
                    var safeConversation = conversation(deviceConversations[i]);
                    if (owned(deviceConversations[i], consumerMap, accountMap)) {
                        need(has(conversationMap, deviceConversations[i].sys_id), 'INVALID_DATA');
                        safeDeviceConversations.push(safeConversation);
                    } else unowned++;
                }
                for (i = 0; i < deviceSessions.length; i++) {
                    var safeSession = session(deviceSessions[i]);
                    if (owned(deviceSessions[i], consumerMap, accountMap)) {
                        need(has(sessionMap, deviceSessions[i].sys_id), 'INVALID_DATA');
                        safeDeviceSessions.push(safeSession);
                    } else unowned++;
                }
                var activityResult = activity(deviceConversations.filter(function (row) {return has(conversationMap, row.sys_id);}));
                unchanged();
                var finished = clock();
                need(finished >= started, 'INVALID_DATA');
                unchanged();
                result.ok = true;
                result.principalHash = principalHash;
                result.server = {startedMs: started, finishedMs: finished};
                result.contextUnchanged = true;
                result.counts = {activeConversations: active, unknownStates: unknown};
                result.conversations = safeConversations;
                result.sessions = safeSessions;
                result.deviceConversations = safeDeviceConversations;
                result.deviceSessions = safeDeviceSessions;
                result.unownedDeviceRows = unowned;
                result.activity = activityResult.counts;
                result.messageSessionLinks = activityResult.links;
                return result;
            } catch (failure) {
                var code = failure && failure.oracleFailure;
                if (initial) {
                    try {unchanged();} catch (contextFailure) {code = contextFailure && contextFailure.oracleFailure || 'READ_FAILED';}
                }
                result = empty(request);
                result.failureCode = ['INVALID_REQUEST', 'INVALID_DEPENDENCIES', 'PRINCIPAL_REFUSED', 'CONTEXT_DRIFT',
                    'READ_DENIED', 'SCHEMA_UNAVAILABLE', 'READ_LIMIT', 'INVALID_DATA', 'READ_FAILED'].indexOf(code) >= 0 ? code : 'READ_FAILED';
                return result;
            }
        }};
    }
    return {createNativeOAuthOracle: createNativeOAuthOracle};
}));
