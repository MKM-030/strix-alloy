/* STAGED ONLY. Server-only Global Script Include. No writes, impersonation or elevated reads.
 * Current-row field values are normal ACL policy inputs. Lookup dependencies use GlideRecordSecure.
 * Lookup graph: message -> active plan -> conversation -> interaction; interaction does no lookup.
 */
var SCCVoiceContextReadPolicy = Class.create();
SCCVoiceContextReadPolicy.prototype = {
    initialize: function() {},
    readerRole: 'scc_voice_context_reader',
    initialUserId: '6a0690b893d00b105c8132d47aba1022',
    providerId: '200af60f93fb4354e7f2b9fa6aba107d',
    contextProfileId: 'c623e20f93374354e7f2b9fa6aba1081',
    usecaseId: '2f3c8a39931093185c8132d47aba1014',
    notePrefix: 'SCC_VOICE_USER_CONTEXT_V2\nrequestId:',
    ackPrefix: 'SCC_VOICE_PROMPT_INCLUDED_V1\nrequestId:',
    // Temporary fixed-code access diagnostics. No record content or record IDs.
    _diagnostic: function(table, stage, field, readerRole) {
        try {
            if (String(gs.getUserID()) !== this.initialUserId ||
                    ['interaction', 'sys_cs_conversation', 'sn_aia_execution_plan', 'sn_aia_message'].indexOf(table) === -1 ||
                    ['entry', 'row_denied', 'field_absent', 'field_denied', 'current_table_unavailable',
                     'current_id_unavailable', 'interaction_lookup_empty', 'policy_rejected', 'policy_exception'].indexOf(stage) === -1) return;
            var event = {table: table, stage: stage};
            if (typeof field !== 'undefined') {
                if (['sys_id', 'opened_for', 'provider_application', 'channel_metadata_table',
                     'channel_metadata_document', 'conversation', 'state', 'execution_plan',
                     'role', 'message', 'user_message'].indexOf(field) === -1) return;
                event.field = field;
            }
            if (typeof readerRole === 'boolean') event.readerRole = readerRole;
            gs.info('[SCC_VOICE_CONTEXT_POLICY_V1] ' + JSON.stringify(event));
        } catch (ignoredDiagnostic) {}
    },
    _rowDiagnostic: function(row, stage, field) {
        try { this._diagnostic(String(row.getTableName()), stage, field); } catch (ignoredDiagnostic) {}
    },
    _observedDecision: function(table, allowed) {
        if (allowed === false) this._diagnostic(table, 'policy_rejected');
        return allowed;
    },
    _id: function(value) { return typeof value === 'string' && /^[0-9a-f]{32}$/.test(value); },
    _value: function(row, field) {
        if (!row || !row.isValidField(field)) throw new Error('SCCVoicePolicyFieldUnavailable');
        var value = row.getValue(field);
        return value === null || typeof value === 'undefined' ? '' : String(value);
    },
    _currentId: function(row, table) {
        if (!row || String(row.getTableName()) !== table) {
            this._diagnostic(table, 'current_table_unavailable'); return '';
        }
        var id = String(row.getUniqueValue());
        if (!this._id(id)) this._diagnostic(table, 'current_id_unavailable');
        return this._id(id) ? id : '';
    },
    _readable: function(row, fields) {
        if (!row.canRead()) { this._rowDiagnostic(row, 'row_denied'); return false; }
        for (var i = 0; i < fields.length; i++) {
            var element = row.getElement(fields[i]);
            if (!element) {
                // Diagnostic only: preserve the existing denial and emit no field values or record IDs.
                try {
                    if (fields[i] === 'provider_application' && String(row.getTableName()) === 'interaction' &&
                            String(gs.getUserID()) === this.initialUserId) {
                        var shape = {table: 'interaction', field: 'provider_application', legacyWouldReject: true,
                            validField: row.isValidField(fields[i]) === true, elementType: typeof element,
                            elementIsNull: element === null, elementIsUndefined: typeof element === 'undefined',
                            explicitPresent: element !== null && typeof element !== 'undefined',
                            readerRole: gs.hasRole(this.readerRole) === true,
                            effectiveAdmin: gs.hasRole('admin') === true, canReadCalled: false};
                        if (shape.explicitPresent) {
                            shape.canReadCalled = true;
                            try { shape.elementCanRead = element.canRead() === true; }
                            catch (ignoredElementReadProbe) { shape.elementCanReadProbe = 'exception'; }
                        }
                        gs.info('[SCC_VOICE_CONTEXT_ELEMENT_V1] ' + JSON.stringify(shape));
                    }
                } catch (ignoredElementShapeDiagnostic) {}
                this._rowDiagnostic(row, 'field_absent', fields[i]); return false;
            }
            if (!element.canRead()) { this._rowDiagnostic(row, 'field_denied', fields[i]); return false; }
        }
        return true;
    },
    _ownInteraction: function(row, userId) {
        // No canRead/current-row lookup here: that would recurse into this ACL.
        return !!this._currentId(row, 'interaction') &&
            this._value(row, 'opened_for') === userId &&
            this._value(row, 'provider_application') === this.providerId &&
            this._value(row, 'channel_metadata_table') === 'sys_cs_conversation' &&
            this._id(this._value(row, 'channel_metadata_document'));
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
    _ownedConversation: function(conversationId, userId) {
        if (!this._id(conversationId)) return false;
        var interaction = new GlideRecordSecure('interaction');
        interaction.addQuery('opened_for', userId);
        interaction.addQuery('provider_application', this.providerId);
        interaction.addQuery('channel_metadata_table', 'sys_cs_conversation');
        interaction.addQuery('channel_metadata_document', conversationId);
        interaction.setLimit(2); interaction.query();
        if (!interaction.next()) { this._diagnostic('interaction', 'interaction_lookup_empty'); return false; }
        if (!this._readable(interaction, ['sys_id', 'opened_for', 'channel_metadata_table', 'channel_metadata_document'])) return false;
        var interactionId = this._currentId(interaction, 'interaction');
        if (!interactionId || this._value(interaction, 'opened_for') !== userId ||
                this._value(interaction, 'channel_metadata_table') !== 'sys_cs_conversation' ||
                this._value(interaction, 'channel_metadata_document') !== conversationId || interaction.next()) return false;
        // The raw current-row interaction ACL remains unchanged. Its protected
        // provider reference is not re-read from a projected secure record.
        return !this._referenceFilterIgnored('interaction', interactionId, conversationId);
    },
    _secureOwnedConversation: function(conversationId, userId) {
        if (!this._id(conversationId)) return false;
        var conversation = new GlideRecordSecure('sys_cs_conversation');
        conversation.addQuery('sys_id', conversationId);
        conversation.addQuery('context_profile', this.contextProfileId);
        conversation.setLimit(2); conversation.query();
        if (!conversation.next() || !this._readable(conversation, ['sys_id', 'state']) ||
                this._currentId(conversation, 'sys_cs_conversation') !== conversationId ||
                ['open', 'chatInProgress', 'autoPilotInProgress'].indexOf(this._value(conversation, 'state')) === -1 ||
                conversation.next() || this._referenceFilterIgnored('sys_cs_conversation', conversationId)) return false;
        return this._ownedConversation(conversationId, userId);
    },
    _ownActivePlan: function(row, userId) {
        return !!this._currentId(row, 'sn_aia_execution_plan') &&
            this._value(row, 'state') === 'in_progress' &&
            this._value(row, 'usecase') === this.usecaseId &&
            this._secureOwnedConversation(this._value(row, 'conversation'), userId);
    },
    _secureOwnActivePlan: function(planId, userId) {
        if (!this._id(planId)) return false;
        var plan = new GlideRecordSecure('sn_aia_execution_plan');
        plan.addQuery('sys_id', planId);
        plan.addQuery('state', 'in_progress');
        plan.addQuery('usecase', this.usecaseId);
        plan.setLimit(2); plan.query();
        if (!plan.next() || !this._readable(plan, ['sys_id', 'conversation', 'state']) ||
                this._currentId(plan, 'sn_aia_execution_plan') !== planId || this._value(plan, 'state') !== 'in_progress') return false;
        var conversationId = this._value(plan, 'conversation');
        if (!this._id(conversationId) || plan.next() || this._referenceFilterIgnored('sn_aia_execution_plan', planId, conversationId)) return false;
        return this._secureOwnedConversation(conversationId, userId);
    },
    _ownContextMessage: function(row, userId) {
        if (!this._currentId(row, 'sn_aia_message')) return false;
        var userRole = sn_aia.AIAgentConstants.ROLES.USER;
        if (typeof userRole !== 'string' || !/^[a-z_]{1,32}$/.test(userRole) ||
                this._value(row, 'role') !== userRole) return false;
        var message = this._value(row, 'message');
        if (message !== this._value(row, 'user_message') ||
                (message.indexOf(this.notePrefix) !== 0 && message.indexOf(this.ackPrefix) !== 0)) return false;
        return this._secureOwnActivePlan(this._value(row, 'execution_plan'), userId);
    },
    canRead: function(table, currentRow) {
        try {
            var userId = String(gs.getUserID());
            if (!this._id(userId) || userId !== this.initialUserId) return false;
            var readerRole = gs.hasRole(this.readerRole);
            this._diagnostic(table, 'entry', undefined, readerRole === true);
            if (readerRole !== true) return false;
            if (table === 'interaction') return this._observedDecision(table, this._ownInteraction(currentRow, userId) === true);
            if (table === 'sys_cs_conversation')
                return this._observedDecision(table, this._value(currentRow, 'context_profile') === this.contextProfileId &&
                    ['open', 'chatInProgress', 'autoPilotInProgress'].indexOf(this._value(currentRow, 'state')) !== -1 &&
                    this._ownedConversation(this._currentId(currentRow, table), userId) === true);
            if (table === 'sn_aia_execution_plan') return this._observedDecision(table, this._ownActivePlan(currentRow, userId) === true);
            if (table === 'sn_aia_message') return this._observedDecision(table, this._ownContextMessage(currentRow, userId) === true);
        } catch (ignoredSCCVoicePolicy) { this._diagnostic(table, 'policy_exception'); }
        return false;
    },
    type: 'SCCVoiceContextReadPolicy'
};
