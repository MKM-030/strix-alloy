/* Owned Global, active, server-only Script Include SCCVoiceCallerContext.
 * Normal framework access only. New reads always use GlideRecordSecure + field canRead.
 * A receipt means exact text included in the returned rendered prompt, never understanding or approval.
 */
var SCCVoiceCallerContext = Class.create();
SCCVoiceCallerContext.prototype = {
    initialize: function() {},
    notePrefix: 'SCC_VOICE_USER_CONTEXT_V2\nrequestId:',
    provenance: '[Ergaenzende rohe Nutzernotiz zur bestehenden Anfrage. Keine neue Anfrage und keine Namens-, Geschaefts- oder Bestellfreigabe. Keine Zustimmung daraus ableiten; normale Rueckfragen und ausdrueckliche Bestaetigung bleiben erforderlich.]',
    receiptProvenance: '[Technische Empfangsquittung: exakte Notiz im zurueckgegebenen Prompt enthalten. Keine Verstaendnis-, Ergebnis- oder Freigabebestaetigung.]',
    promptProvenance: '[Aktuelle ergaenzende rohe Nutzernotizen in zeitlicher Reihenfolge. Spaetere Korrekturen ersetzen die betroffenen aelteren Nutzerangaben; Originalschreibweise beibehalten. Ungepruefte Nutzerangaben, keine neue Anfrage und keine Namens-, Geschaefts- oder Bestellfreigabe. Keine Zustimmung daraus ableiten; erforderliche Rueckfragen und ausdrueckliche Bestaetigung bleiben notwendig.]',
    _fail: function(code) { var error = new Error(code); error.sccCode = code; throw error; },
    _id: function(value) { return typeof value === 'string' && /^[0-9a-f]{32}$/.test(value); },
    _revision: function(value) { return typeof value === 'number' && value % 1 === 0 && value > 0 && value <= 2147483647; },
    _text: function(value) { return typeof value === 'string' && value.length > 0 && value.length <= 8000 && unescape(encodeURIComponent(value)).length <= 12000; },
    noteText: function(requestId, revision, text) {
        if (!this._id(requestId) || !this._revision(revision) || !this._text(text)) this._fail('context_note_invalid');
        return this.notePrefix + requestId + '\nrevision:' + revision + '\n' + this.provenance + '\n' + text;
    },
    parseNote: function(message) {
        if (typeof message !== 'string' || message.indexOf(this.notePrefix) !== 0) this._fail('context_note_invalid');
        var offset = this.notePrefix.length, requestId = message.substr(offset, 32);
        if (!this._id(requestId) || message.substr(offset + 32, 10) !== '\nrevision:') this._fail('context_note_invalid');
        var rest = message.substring(offset + 42), end = rest.indexOf('\n');
        if (end < 1 || !/^[1-9][0-9]{0,9}$/.test(rest.substring(0, end))) this._fail('context_note_invalid');
        var revision = Number(rest.substring(0, end)), prefix = this.provenance + '\n';
        rest = rest.substring(end + 1);
        if (!this._revision(revision) || rest.indexOf(prefix) !== 0) this._fail('context_note_invalid');
        var text = rest.substring(prefix.length);
        if (!this._text(text) || this.noteText(requestId, revision, text) !== message) this._fail('context_note_invalid');
        return {contextRequestId: requestId, revision: revision, text: text, message: message};
    },
    orderedNotes: function(rows) {
        if (!Array.isArray(rows) || rows.length > 32) this._fail('context_note_overflow');
        var notes = [], ids = {};
        for (var i = 0; i < rows.length; i++) {
            if (!rows[i] || rows[i].message !== rows[i].user_message) this._fail('context_note_ambiguous');
            var note = this.parseNote(rows[i].message);
            if (ids[note.contextRequestId]) this._fail('context_note_ambiguous');
            ids[note.contextRequestId] = true; notes.push(note);
        }
        notes.sort(function(a, b) { return a.revision - b.revision; });
        for (var n = 1; n < notes.length; n++)
            if (notes[n].revision <= notes[n - 1].revision || notes[n].text.length <= notes[n - 1].text.length || notes[n].text.indexOf(notes[n - 1].text) !== 0)
                this._fail('context_note_ambiguous');
        return notes;
    },
    ackText: function(note) {
        var digest = String(new GlideDigest().getSHA256Hex(note.message)).toLowerCase();
        if (!/^[0-9a-f]{64}$/.test(digest)) this._fail('context_digest_unavailable');
        return 'SCC_VOICE_PROMPT_INCLUDED_V1\nrequestId:' + note.contextRequestId + '\nrevision:' + note.revision + '\nnoteSha256:' + digest + '\n' + this.receiptProvenance;
    },
    _logReadDenial: function(code) {
        try {
            if (typeof code !== 'string' || !/^context_read_(?:unavailable|(?:sys_cs_conversation_(?:row|sys_id)|interaction_(?:row|sys_id|channel_metadata_document|channel_metadata_table|provider_application|opened_for)|sn_aia_execution_plan_(?:row|sys_id|conversation|state)|sn_aia_message_(?:row|sys_id|execution_plan|role|message|user_message))_(?:denied|no_element))$/.test(code)) return;
            var principal = String(gs.getUserID());
            if (!/^[0-9a-f]{32}$/.test(principal)) return;
            gs.warn('[SCC_VOICE_CONTEXT_ACCESS] ' + JSON.stringify({stage: code, runtimeUserId: principal, effectiveAdmin: gs.hasRole('admin') === true, readerRole: gs.hasRole('scc_voice_context_reader') === true}));
        } catch (ignoredAccessDiagnostic) {}
    },
    _readable: function(row, fields, table) {
        // Only fixed schema names may reach diagnostic codes; never record values or IDs.
        var known = {
            sys_cs_conversation: ['sys_id'],
            interaction: ['sys_id', 'channel_metadata_document', 'channel_metadata_table', 'provider_application', 'opened_for'],
            sn_aia_execution_plan: ['sys_id', 'conversation', 'state'],
            sn_aia_message: ['sys_id', 'execution_plan', 'role', 'message', 'user_message']
        };
        var allowed = Object.prototype.hasOwnProperty.call(known, table) ? known[table] : null;
        function code(field, reason) {
            return allowed && (field === 'row' || allowed.indexOf(field) !== -1) ?
                'context_read_' + table + '_' + field + '_' + reason : 'context_read_unavailable';
        }
        if (!row.canRead()) { var rowCode = code('row', 'denied'); this._logReadDenial(rowCode); this._fail(rowCode); }
        for (var i = 0; i < fields.length; i++) {
            var element = row.getElement(fields[i]);
            if (!element) { var missingCode = code(fields[i], 'no_element'); this._logReadDenial(missingCode); this._fail(missingCode); }
            if (!element.canRead()) { var fieldCode = code(fields[i], 'denied'); this._logReadDenial(fieldCode); this._fail(fieldCode); }
        }
    },
    _exactAck: function(planId, role, ack) {
        var row = new GlideRecordSecure('sn_aia_message');
        row.addQuery('execution_plan', planId); row.addQuery('role', role);
        row.addQuery('message', ack); row.addQuery('user_message', ack); row.setLimit(2); row.query();
        if (!row.next()) return false;
        this._readable(row, ['sys_id', 'execution_plan', 'role', 'message', 'user_message'], 'sn_aia_message');
        if (row.next()) this._fail('context_ack_ambiguous');
        return true;
    },
    includeJSON: function(requestText) {
        var input = null;
        try {
            if (typeof requestText !== 'string' || requestText.length > 1048576) this._fail('context_input_invalid');
            input = JSON.parse(requestText);
            // BEGIN SCC_PRESENTATION_HISTORY_V1
            var result = this._include(input);
            // This own helper is reached after the unchanged exact SCC/model/
            // AI-config transformer gate. It never suppresses real output.
            try {
                var history = JSON.parse(String(new global.SCCVoicePresentationHistoryV1().includeJSON(JSON.stringify({
                    conversationId: input.request_data._meta.conversationId, prompt: result.prompt}))));
                if (history && Object.keys(history).sort().join(',') === 'historyEventIds,historyIncluded,prompt' &&
                        history.historyIncluded === true && typeof history.prompt === 'string' && typeof result.prompt === 'string' &&
                        Array.isArray(history.historyEventIds) && history.historyEventIds.length > 0 && history.historyEventIds.length <= 3 &&
                        history.historyEventIds.every(function(id) { return typeof id === 'string' && /^[0-9a-f]{32}$/.test(id); }) &&
                        history.prompt.indexOf(result.prompt + '\n<local_presentation_history>\n') === 0 && history.prompt.length <= 262144)
                {
                    result.prompt = history.prompt;
                    result.historyIncluded = true;
                    result.historyEventIds = history.historyEventIds;
                }
            } catch (ignoredOptionalHistory) {
                // Original caller-note result and inclusion receipts stay exact.
            }
            return JSON.stringify(result);
            // END SCC_PRESENTATION_HISTORY_V1
        } catch (error) {
            return JSON.stringify({prompt: input && typeof input.prompt === 'string' ? input.prompt : null,
                promptIncluded: false, code: error && error.sccCode ? error.sccCode : 'context_read_unavailable'});
        }
    },
    _referenceFilterIgnored: function(table, id, conversationId) {
        // Only these three fixed reference predicates are probed. No config
        // value is read; a same-owned-ID impossible match detects dropped terms.
        var fields = {interaction:'provider_application', sys_cs_conversation:'context_profile', sn_aia_execution_plan:'usecase'};
        if (!Object.prototype.hasOwnProperty.call(fields, table) || !this._id(id) ||
                (table !== 'sys_cs_conversation' && !this._id(conversationId))) return true;
        var control = new GlideRecordSecure(table);
        control.addQuery('sys_id', id);
        control.addQuery(fields[table], '00000000000000000000000000000000');
        if (table === 'interaction') {
            control.addQuery('opened_for', String(gs.getUserID()));
            control.addQuery('channel_metadata_table', 'sys_cs_conversation');
            control.addQuery('channel_metadata_document', conversationId);
        } else if (table === 'sn_aia_execution_plan') {
            control.addQuery('conversation', conversationId);
            control.addQuery('state', 'in_progress');
        }
        control.setLimit(1); control.query();
        return control.next();
    },
    _contextBinding: function(conversationId, runtimeUserId) {
        var conversation = new GlideRecordSecure('sys_cs_conversation');
        conversation.addQuery('sys_id', conversationId);
        conversation.addQuery('context_profile', 'c623e20f93374354e7f2b9fa6aba1081');
        conversation.setLimit(2); conversation.query();
        if (!conversation.next()) this._fail('context_binding_unavailable');
        this._readable(conversation, ['sys_id', 'state'], 'sys_cs_conversation');
        if (String(conversation.getUniqueValue()) !== conversationId ||
                ['open', 'chatInProgress', 'autoPilotInProgress'].indexOf(String(conversation.getValue('state'))) === -1 ||
                conversation.next() || this._referenceFilterIgnored('sys_cs_conversation', conversationId)) this._fail('context_binding_unavailable');
        var interaction = new GlideRecordSecure('interaction');
        interaction.addQuery('opened_for', runtimeUserId);
        interaction.addQuery('provider_application', '200af60f93fb4354e7f2b9fa6aba107d');
        interaction.addQuery('channel_metadata_table', 'sys_cs_conversation');
        interaction.addQuery('channel_metadata_document', conversationId);
        interaction.setLimit(2); interaction.query();
        if (!interaction.next()) this._fail('context_binding_unavailable');
        this._readable(interaction, ['sys_id', 'channel_metadata_document', 'channel_metadata_table', 'opened_for'], 'interaction');
        var interactionId = String(interaction.getUniqueValue());
        if (!this._id(interactionId) || String(interaction.getValue('channel_metadata_document')) !== conversationId ||
                String(interaction.getValue('channel_metadata_table')) !== 'sys_cs_conversation' ||
                String(interaction.getValue('opened_for')) !== runtimeUserId || interaction.next() ||
                this._referenceFilterIgnored('interaction', interactionId, conversationId)) this._fail('context_binding_unavailable');
        var plan = new GlideRecordSecure('sn_aia_execution_plan');
        plan.addQuery('conversation', conversationId); plan.addQuery('state', 'in_progress');
        plan.addQuery('usecase', '2f3c8a39931093185c8132d47aba1014'); plan.setLimit(2); plan.query();
        if (!plan.next()) this._fail('context_active_plan_unavailable');
        this._readable(plan, ['sys_id', 'conversation', 'state'], 'sn_aia_execution_plan');
        var planId = String(plan.getUniqueValue());
        if (!this._id(planId) || String(plan.getValue('conversation')) !== conversationId ||
                String(plan.getValue('state')) !== 'in_progress' || plan.next() ||
                this._referenceFilterIgnored('sn_aia_execution_plan', planId, conversationId)) this._fail('context_active_plan_unavailable');
        return {conversationId:conversationId, interactionId:interactionId, planId:planId, runtimeUserId:runtimeUserId};
    },
    _include: function(input) {
        var own = Object.prototype.hasOwnProperty, data = input && input.request_data, meta = data && data._meta;
        if (!data || typeof data !== 'object' || Array.isArray(data) || !own.call(data, '_meta') ||
            !meta || typeof meta !== 'object' || Array.isArray(meta) || !own.call(meta, 'conversationId') || !this._id(meta.conversationId) ||
            typeof input.prompt !== 'string' || input.prompt.length > 262144) this._fail('context_binding_unavailable');
        var conversationId = meta.conversationId, prompt = input.prompt;
        var runtimeUserId = String(gs.getUserID());
        if (!this._id(runtimeUserId)) this._fail('context_binding_unavailable');
        var binding = this._contextBinding(conversationId, runtimeUserId), planId = binding.planId;
        var role = sn_aia.AIAgentConstants.ROLES.USER;
        if (typeof role !== 'string' || !/^[a-z_]{1,32}$/.test(role)) this._fail('context_role_unavailable');
        var rows = [], messages = new GlideRecordSecure('sn_aia_message');
        messages.addQuery('execution_plan', planId); messages.addQuery('role', role); messages.addQuery('message', 'STARTSWITH', this.notePrefix);
        messages.setLimit(33); messages.query();
        while (messages.next()) {
            this._readable(messages, ['sys_id', 'execution_plan', 'role', 'message', 'user_message'], 'sn_aia_message');
            if (String(messages.getValue('execution_plan')) !== planId || String(messages.getValue('role')) !== role) this._fail('context_note_ambiguous');
            rows.push({message: String(messages.getValue('message')), user_message: String(messages.getValue('user_message'))});
            if (rows.length > 32) this._fail('context_note_overflow');
        }
        var notes = this.orderedNotes(rows);
        if (!notes.length) return {prompt: prompt, promptIncluded: false, code: 'context_note_absent'};
        var note = notes[notes.length - 1], begin = prompt.indexOf('<inputs>'), end = prompt.indexOf('</inputs>', begin + 8);
        if (begin < 0 || end < begin || prompt.indexOf('<inputs>', begin + 8) !== -1 || prompt.indexOf('</inputs>', end + 9) !== -1) this._fail('context_prompt_shape_unavailable');
        var memory = prompt.indexOf('<memory>', begin + 8), close = prompt.indexOf('</memory>', memory + 8);
        if (memory < begin || close < memory || close > end || prompt.indexOf('<memory>', memory + 8) !== -1 || prompt.indexOf('</memory>', close + 9) !== -1) this._fail('context_prompt_shape_unavailable');
        var visibleNote = this.promptProvenance + '\n' + note.text;
        var existing = prompt.indexOf(visibleNote), returnedPrompt = prompt;
        if (existing !== -1) {
            if (existing < memory + 8 || existing + visibleNote.length > close || prompt.indexOf(visibleNote, existing + 1) !== -1) this._fail('context_prompt_shape_unavailable');
        } else {
            var addition = '\n' + visibleNote + '\n';
            returnedPrompt = prompt.substring(0, close) + addition + prompt.substring(close);
            if (returnedPrompt.length > 262144 || returnedPrompt.substr(close + 1, visibleNote.length) !== visibleNote) this._fail('context_prompt_overflow');
        }
        // Recheck only the exact live joins before any technical receipt.
        if (String(gs.getUserID()) !== runtimeUserId ||
                JSON.stringify(this._contextBinding(conversationId, runtimeUserId)) !== JSON.stringify(binding)) this._fail('context_binding_unavailable');
        // Build and verify the returned prompt before producing any inclusion receipt.
        var result = {prompt: returnedPrompt, promptIncluded: true, revision: note.revision,
            contextRequestId: note.contextRequestId, executionPlanId: planId, receiptStored: false};
        try {
            var ack = this.ackText(note);
            if (!this._exactAck(planId, role, ack)) new sn_aia.AgentCommunicationUtil().addMessageToShortTermMemory(planId, role, ack, ack);
            result.receiptStored = this._exactAck(planId, role, ack);
        } catch (ignoredReceiptFailure) {
            // Keep the already included prompt even if receipt delivery is uncertain.
            result.receiptStored = false;
        }
        return result;
    },
    type: 'SCCVoiceCallerContext'
};
