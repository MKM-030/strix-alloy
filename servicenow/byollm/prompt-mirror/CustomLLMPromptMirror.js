/* Global, server only, ES5. Copies provider-specific prompt configuration,
 * never a capability/skill and never a provider's active/default selection.
 * No inference calls, schema changes, ACL changes or ACL bypasses.
 * Revision checks/readback do NOT prove atomicity. Native apply is gated until
 * serialized execution has been independently validated on the target instance.
 */
var CustomLLMPromptMirror = Class.create();
CustomLLMPromptMirror.prototype = {
    initialize: function (dependencies) {
        dependencies = dependencies || {};
        this.version = '1.0.0';
        this.namespace = 'custom_llm.prompt_mirror';
        this._native = typeof gs !== 'undefined' && typeof GlideRecordSecure !== 'undefined';
        this._schema = this._fieldSchema();
        this._store = this._native ? this._nativeStore() : dependencies.store;
        this._config = this._native ? this._readConfiguration() : (dependencies.config || {});
    },

    scan: function (selection) {
        this._authorize();
        selection = selection || {};
        var selected = selection.capabilityIds || [], seen = {}, variants = [], issues = [], i, j, k, maps, p, m, defs, d;
        this._require(Object.prototype.toString.call(selected) === '[object Array]', 'Conflict', 'CapabilitySelectionMustBeArray');
        this._require(selected.length <= 500, 'Conflict', 'SelectionLimit');
        for (i = 0; i < selected.length; i++) { this._require(this._validId(selected[i]), 'Conflict', 'InvalidCapabilityId'); }
        maps = this._query('sys_generative_ai_provider_mapping', [['provider', '=', 'Now LLM Generic'], ['provider_api', '=', 'Now LLM Generic'], ['active', '=', '1']]);
        for (i = 0; i < maps.length; i++) {
            m = maps[i]; p = this._read('sys_gen_ai_provider', m.gen_ai_provider);
            if (!p || p.gen_ai_provider !== 'Now LLM Service') { continue; }
            this._require(m.provider_implementation_document === 'sys_hub_flow' && this._validId(m.provider_implementation), 'BlockedPrerequisite', 'UnsupportedSourceImplementation');
            // Discover identities without touching another capability's protected
            // script fields. Complete readability is checked per variant in plan.
            defs = this._store.query('sys_one_extend_capability_definition', [['api', '=', m.provider_implementation], ['api_type', '=', m.provider_implementation_document]], this._store.fields('sys_one_extend_capability_definition', ['sys_id', 'capability']));
            for (j = 0; j < defs.length; j++) {
                d = defs[j]; if (selected.length && selected.indexOf(d.capability) === -1) { continue; }
                if (seen[d.sys_id]) { seen[d.sys_id].status = 'Conflict'; seen[d.sys_id].reason = 'AmbiguousSourceProviderJoin'; continue; }
                k = {definitionId: d.sys_id, capabilityId: d.capability, mappingId: m.sys_id, status: 'Discovered'};
                seen[d.sys_id] = k; variants.push(k);
            }
        }
        variants.sort(function (a, b) { return a.definitionId < b.definitionId ? -1 : a.definitionId > b.definitionId ? 1 : 0; });
        return {version: this.version, variants: variants, issues: issues, readOnly: true, writes: 0};
    },

    plan: function (definitionId) {
        this._authorize();
        var p = {version: this.version, definitionId: definitionId, status: 'Ready', artifacts: [], dependencies: [], issues: [], readOnly: true, writes: 0}, i, j, variant, source, profile, graph, ids = {}, a, target, state, desired, key, fields, changed, op;
        try {
            this._require(this._validId(definitionId), 'Conflict', 'InvalidDefinitionId');
            op = this._store.stateGet(this._operationKey(definitionId));
            this._require(!op || op.status === 'Verified', 'NeedsRecovery', 'UnfinishedPreviousApply');
            var discovered = this.scan({});
            for (i = 0; i < discovered.variants.length; i++) { if (discovered.variants[i].definitionId === definitionId) { variant = discovered.variants[i]; } }
            this._require(variant, 'Ignored', 'DefinitionNotQualifiedNowLLMGeneric');
            this._require(variant.status !== 'Conflict', 'Conflict', variant.reason);
            source = this._read('sys_one_extend_capability_definition', definitionId);
            this._require(source && source.capability === variant.capabilityId, 'Conflict', 'SourceIdentityChanged');
            this._require(this._read('sys_one_extend_capability', source.capability), 'BlockedPrerequisite', 'CapabilityMissing');
            profile = this._store.resolveTargetProfile(); this._profile(profile);
            p.profile = profile;
            p.mapping = this._read('sys_generative_ai_provider_mapping', variant.mappingId);
            this._require(p.mapping && p.mapping.provider === 'Now LLM Generic' && p.mapping.provider_api === 'Now LLM Generic', 'Conflict', 'SourceMappingChanged');
            p.dependencies.push({table: 'sys_generative_ai_provider_mapping', id: p.mapping.sys_id, hash: this._hash(p.mapping)});
            p.dependencies.push({table: 'sys_one_extend_capability', id: source.capability, hash: this._hash(this._read('sys_one_extend_capability', source.capability))});
            var providerRow = this._read('sys_gen_ai_provider', p.mapping.gen_ai_provider);
            this._require(providerRow && providerRow.gen_ai_provider === 'Now LLM Service', 'Conflict', 'SourceProviderChanged');
            p.dependencies.push({table: 'sys_gen_ai_provider', id: providerRow.sys_id, hash: this._hash(providerRow)});
            if (this._store.nativeDefinitionConfigContract) { p.nativeConfigContract = this._store.nativeDefinitionConfigContract(); }
            graph = this._graph(source, p);
            if (p.nativeConfigContract) {
                var nativeConfigCount = 0, promptBindingCounts = {};
                for (i = 0; i < graph.length; i++) { if (graph[i].table === 'sys_one_extend_definition_config') { nativeConfigCount++; } }
                this._require(nativeConfigCount === 1, 'Conflict', 'NativeSourceDefinitionConfigMustBeUnique');
                if (p.nativeConfigContract.promptBinding) {
                    for (i = 0; i < graph.length; i++) { if (graph[i].table === 'sys_generative_ai_prompt_config') { key = graph[i].row.ai_config; promptBindingCounts[key] = (promptBindingCounts[key] || 0) + 1; } }
                    for (i = 0; i < graph.length; i++) { if (graph[i].table === 'sys_generative_ai_config') { this._require(promptBindingCounts[graph[i].row.sys_id] === 1, 'Conflict', 'NativePromptBindingSourceMustBeUniquePerPrompt'); } }
                }
                var selections = this._query('sys_one_extend_definition_config', [['capability', '=', source.capability]]); p.selectionSnapshot = [];
                for (i = 0; i < selections.length; i++) { p.selectionSnapshot.push({sys_id: selections[i].sys_id, definition: selections[i].definition, capability: selections[i].capability, active: selections[i].active, 'default': selections[i]['default']}); }
                p.selectionSnapshot.sort(function (left, right) { return left.sys_id < right.sys_id ? -1 : left.sys_id > right.sys_id ? 1 : 0; });
            }
            for (i = 0; i < graph.length; i++) {
                a = graph[i];
                if (p.nativeConfigContract && (a.table === 'sys_one_extend_definition_config' || p.nativeConfigContract.promptBinding && a.table === 'sys_generative_ai_prompt_config')) {
                    state = this._store.stateGet(this._originKey(definitionId, a.table, a.row.sys_id));
                    this._require(!state || this._validId(state.targetId), 'Conflict', 'InvalidNativeConfigOwnershipId');
                    ids[a.row.sys_id] = state ? state.targetId : '';
                } else { ids[a.row.sys_id] = this._hash('mirror-v1|' + definitionId + '|' + a.table + '|' + a.row.sys_id).substr(0, 32); }
            }
            var owned = this._store.stateList('origin|' + definitionId + '|'), graphKeys = {};
            for (i = 0; i < graph.length; i++) { graphKeys[this._originKey(definitionId, graph[i].table, graph[i].row.sys_id)] = true; }
            for (i = 0; i < owned.length; i++) { this._require(graphKeys[owned[i].key], 'Conflict', 'SourceArtifactRemovedRequiresReview:' + owned[i].body.sourceId); }
            var existing = this._query('sys_one_extend_capability_definition', [['capability', '=', source.capability], ['api', '=', profile.implementationId], ['api_type', '=', profile.implementationTable]]);
            for (i = 0; i < existing.length; i++) {
                this._require(existing[i].sys_id === ids[definitionId] && this._store.stateGet(this._originKey(definitionId, 'sys_one_extend_capability_definition', definitionId)), 'NeedsAdoption', 'ExistingCustomDefinitionRequiresExplicitAdoption:' + existing[i].sys_id);
            }
            for (i = 0; i < graph.length; i++) {
                a = graph[i]; key = this._originKey(definitionId, a.table, a.row.sys_id); state = this._store.stateGet(key); target = this._read(a.table, ids[a.row.sys_id]);
                var nativeGenerated = !!p.nativeConfigContract && (a.table === 'sys_one_extend_definition_config' || !!p.nativeConfigContract.promptBinding && a.table === 'sys_generative_ai_prompt_config');
                if (nativeGenerated) {
                    var generatedParentField = a.table === 'sys_generative_ai_prompt_config' ? 'ai_config' : 'definition';
                    var generatedRows = this._query(a.table, [[generatedParentField, '=', ids[a.row[generatedParentField]]]]);
                    this._require(state ? generatedRows.length === 1 && generatedRows[0].sys_id === state.targetId : generatedRows.length === 0, 'Conflict', 'UnownedOrAmbiguousNativeDefinitionConfig');
                }
                this._require(!target || state, 'Conflict', 'DeterministicIdentityOccupied:' + a.table + ':' + ids[a.row.sys_id]);
                this._require(!state || target, 'Conflict', 'ManagedTargetMissing:' + a.row.sys_id);
                this._require(!target || !target.sys_policy, 'Protected', 'ProtectedTarget:' + ids[a.row.sys_id]);
                if (state) {
                    this._require(state.v === 1 && state.table === a.table && state.sourceId === a.row.sys_id && state.targetId === ids[a.row.sys_id] && state.definitionId === definitionId, 'Conflict', 'OriginIdentityMismatch');
                    this._require(state.scope === (target.sys_scope || '') && state.packageId === (target.sys_package || '') && state.domain === (target.sys_domain || ''), 'Conflict', 'TargetOwnershipChanged');
                    this._require(state.baseline === this._managedHash(a.table, target), 'Conflict', 'ManualTargetDrift:' + a.row.sys_id);
                }
                desired = this._desired(a.table, a.row, target, ids, profile, p);
                if (nativeGenerated && !target && a.table === 'sys_one_extend_definition_config') { desired.active = p.nativeConfigContract.defaults.active; desired['default'] = p.nativeConfigContract.defaults['default']; }
                fields = this._keys(desired); changed = {};
                for (j = 0; j < fields.length; j++) { if (!target || this._value(target[fields[j]]) !== this._value(desired[fields[j]])) { changed[fields[j]] = desired[fields[j]]; } }
                if (nativeGenerated) { changed = this._nativeConfigChanges(desired, target || (a.table === 'sys_one_extend_definition_config' ? p.nativeConfigContract.defaults : {}), a.table); }
                var defaults = target || (nativeGenerated ? (a.table === 'sys_generative_ai_prompt_config' ? this._store.preflightNativePromptBinding(desired) : this._store.preflightNativeDefinitionConfig(ids[definitionId], source.capability, changed)) : this._store.preflight(a.table, ids[a.row.sys_id], desired, true));
                this._require((defaults.sys_domain || '') === (source.sys_domain || ''), 'BlockedPermission', 'CreationDomainMismatch:' + a.table);
                this._require((defaults.sys_scope || '') === (a.row.sys_scope || ''), 'BlockedPermission', 'CreationScopeMismatch:' + a.table + '; use a supported owning application context');
                var next = {v: 1, definitionId: definitionId, table: a.table, sourceId: a.row.sys_id, targetId: ids[a.row.sys_id], scope: defaults.sys_scope || '', packageId: defaults.sys_package || '', domain: defaults.sys_domain || '', baseline: this._managedHash(a.table, desired), profileHash: this._hash(profile)};
                var item = {table: a.table, sourceId: a.row.sys_id, targetId: ids[a.row.sys_id], source: a.row, target: target, desired: desired, changes: changed, insert: !target, originKey: key, nextOrigin: next, originChanged: this._hash(state) !== this._hash(next)};
                if (nativeGenerated) { item.nativeGenerated = true; item.pendingNativeGeneration = !target; item.insert = false; item.originChanged = !state || item.originChanged; if (target && this._keys(changed).length) { this._store.preflight(item.table, item.targetId, changed, false); } }
                else if (item.insert || this._keys(changed).length) { this._store.preflight(item.table, item.targetId, item.insert ? desired : changed, item.insert); }
                this._require(this._canonical(next).length <= 4000, 'BlockedPrerequisite', 'OriginStateTooLargeNoTruncation');
                if (item.originChanged) { this._store.statePreflight(key, next); }
                p.artifacts.push(item);
            }
            var changes = false;
            for (i = 0; i < p.artifacts.length; i++) { if (p.artifacts[i].insert || p.artifacts[i].pendingNativeGeneration || this._keys(p.artifacts[i].changes).length || p.artifacts[i].originChanged) { changes = true; } }
            if (!changes) { p.status = 'NoOp'; }
            else {
                this._store.statePreflight(this._operationKey(definitionId), {v: 1, definitionId: definitionId, status: 'Applying', planHash: '', completed: 0});
                this._store.claimPreflight(definitionId, this._planningClaim || null);
            }
        } catch (e) { p.status = e.mirrorStatus || 'BlockedPermission'; p.issues.push(String(e.message || e)); }
        p.hash = this._planHash(p);
        return p;
    },

    apply: function (receipt) {
        this._authorize();
        var r = {status: 'StalePlan', productWrites: 0, stateWrites: 0, completed: [], nativeGeneratedArtifacts: []}, fresh, claim, i, j, a, actual, fields, op, opKey;
        if (!receipt || !receipt.definitionId || receipt.hash !== this._planHash(receipt)) { return r; }
        fresh = this.plan(receipt.definitionId);
        if (fresh.hash !== receipt.hash) { return r; }
        if (fresh.status === 'NoOp') { r.status = 'NoOp'; return r; }
        if (fresh.status !== 'Ready') { r.status = fresh.status; r.issues = fresh.issues; return r; }
        if (this._config.applyEnabled !== true) { r.status = 'ApplyDisabled'; return r; }
        if (this._config.serializedExecutionVerified !== true) { r.status = 'BlockedConcurrencyGate'; r.issues = ['Serialized execution has not been validated; revision checks are not atomic.']; return r; }
        opKey = this._operationKey(receipt.definitionId);
        try {
            claim = this._store.claim(receipt.definitionId);
            var underClaim;
            this._planningClaim = claim;
            try { underClaim = this.plan(receipt.definitionId); } finally { this._planningClaim = null; }
            this._require(underClaim.hash === fresh.hash, 'StalePlan', 'DriftAfterClaim');
            op = {v: 1, definitionId: receipt.definitionId, status: 'Applying', planHash: fresh.hash, completed: 0};
            this._store.stateWrite(opKey, op); r.stateWrites++;
            for (i = 0; i < fresh.artifacts.length; i++) {
                a = fresh.artifacts[i]; this._require(this._store.owns(claim), 'NeedsRecovery', 'ClaimOwnershipLost');
                this._assertFresh(fresh, r.completed);
                if (a.pendingNativeGeneration) {
                    var parentField = a.table === 'sys_generative_ai_prompt_config' ? 'ai_config' : 'definition';
                    var generated = this._query(a.table, [[parentField, '=', a.desired[parentField]]]);
                    this._require(r.completed.indexOf(a.desired[parentField]) !== -1 && generated.length === 1, 'NeedsRecovery', 'NativeChildNotUniquelyGenerated:' + a.table);
                    actual = generated[0];
                    this._require(this._validId(actual.sys_id) && actual[parentField] === a.desired[parentField] && actual.definition === a.desired.definition && (a.table !== 'sys_one_extend_definition_config' || actual.capability === a.desired.capability && this._value(actual['default']) === '0') && !actual.sys_policy && actual.sys_scope === a.nextOrigin.scope && actual.sys_package === a.nextOrigin.packageId && actual.sys_domain === a.nextOrigin.domain, 'NeedsRecovery', 'NativeGeneratedConfigIdentityOrOwnershipMismatch');
                    a.targetId = actual.sys_id; a.target = actual; a.pendingNativeGeneration = false; a.nextOrigin.targetId = actual.sys_id;
                    if (a.table === 'sys_one_extend_definition_config') { a.desired.active = actual.active; a.desired['default'] = actual['default']; }
                    a.changes = this._nativeConfigChanges(a.desired, actual, a.table); a.nextOrigin.baseline = this._managedHash(a.table, a.desired);
                    if (this._keys(a.changes).length) { this._store.preflight(a.table, a.targetId, a.changes, false); }
                    r.nativeGeneratedArtifacts.push({table: a.table, sourceId: a.sourceId, targetId: a.targetId, parent: a.desired[parentField], readOnlyLinksVerified: true, skillProviderSelectionUnchanged: true});
                }
                if (a.insert || this._keys(a.changes).length) {
                    this._store.preflight(a.table, a.targetId, a.insert ? a.desired : a.changes, a.insert);
                    this._store.write(a.table, a.targetId, a.insert ? a.desired : a.changes, a.target ? a.target.sys_mod_count : null, a.insert); r.productWrites++;
                }
                actual = this._read(a.table, a.targetId); this._require(actual, 'NeedsRecovery', 'WriteReadbackMissing:' + a.targetId);
                fields = this._keys(a.desired);
                for (j = 0; j < fields.length; j++) { this._require(this._value(actual[fields[j]]) === this._value(a.desired[fields[j]]), 'NeedsRecovery', 'FieldReadbackMismatch:' + a.table + '.' + fields[j]); }
                this._require(actual.sys_scope === a.nextOrigin.scope && actual.sys_package === a.nextOrigin.packageId && actual.sys_domain === a.nextOrigin.domain, 'NeedsRecovery', 'OwnershipReadbackMismatch');
                this._require(this._managedHash(a.table, actual) === a.nextOrigin.baseline, 'NeedsRecovery', 'ArtifactHashReadbackMismatch');
                if (a.originChanged) { this._store.stateWrite(a.originKey, a.nextOrigin); r.stateWrites++; }
                r.completed.push(a.targetId);
                op.completed = r.completed.length; this._store.stateWrite(opKey, op); r.stateWrites++;
            }
            this._assertFresh(fresh, r.completed);
            op.status = 'Verified'; this._store.stateWrite(opKey, op); r.stateWrites++;
            this._store.release(claim); r.status = 'Applied';
        } catch (e) {
            r.status = claim ? 'NeedsRecovery' : (e.mirrorStatus || 'NeedsRecovery'); r.issues = [String(e.message || e)];
            r.operationKey = opKey; r.claimRetained = !!claim;
        }
        return r;
    },

    run: function (options) {
        this._authorize(); options = options || {};
        var scan = this.scan({capabilityIds: options.capabilityIds || []}), out = {version: this.version, mode: options.apply === true ? 'apply' : 'dry_run', results: [], skillActivationChanged: false}, i, p;
        for (i = 0; i < scan.variants.length; i++) {
            p = this.plan(scan.variants[i].definitionId);
            if (options.apply === true && (p.status === 'Ready' || p.status === 'NoOp')) { out.results.push({definitionId: p.definitionId, result: this.apply(p)}); }
            else { out.results.push({definitionId: p.definitionId, status: p.status, hash: p.hash, artifactCount: p.artifacts.length, issues: p.issues}); }
        }
        return out;
    },

    onPromptChange: function (promptId) { return this.onSourceChange('sys_generative_ai_config', promptId, null); },

    onSourceChange: function (table, recordId, previous) {
        this._authorize();
        if (this._config.automationEnabled !== true) { return {status: 'AutomationDisabled', writes: 0}; }
        this._require(['sys_one_extend_capability_definition', 'sys_one_extend_definition_config', 'sys_generative_ai_config', 'sys_generative_ai_prompt_config', 'sys_one_extend_definition_attribute', 'sys_generative_ai_request_validator', 'sys_generative_ai_response_validator', 'sys_generative_ai_validator'].indexOf(table) !== -1, 'Conflict', 'UnsupportedTriggerTable');
        var current = this._read(table, recordId), ids = this._affectedDefinitions(table, current), old = this._affectedDefinitions(table, previous), i, p, plans = [], results = [], block = false;
        for (i = 0; i < old.length; i++) { if (ids.indexOf(old[i]) === -1) { ids.push(old[i]); } }
        ids.sort();
        for (i = 0; i < ids.length; i++) {
            p = this.plan(ids[i]);
            if (p.status === 'Ignored') {
                if (this._store.stateList('origin|' + ids[i] + '|').length) { p.status = 'Conflict'; p.issues.push('ManagedSourceNoLongerQualifiesRequiresReview'); }
                else { continue; }
            }
            plans.push(p); results.push({definitionId: ids[i], status: p.status, issues: p.issues});
            if (p.status !== 'Ready' && p.status !== 'NoOp') { block = true; }
        }
        if (!plans.length) { return {status: 'Ignored', writes: 0}; }
        if (block) { return {status: plans.length > 1 ? 'Conflict' : plans[0].status, results: results, issues: ['Affected source definitions require review; no partial event apply performed.'], writes: 0}; }
        if (plans.length === 1) { return this.apply(plans[0]); }
        results = [];
        for (i = 0; i < plans.length; i++) { results.push({definitionId: plans[i].definitionId, result: this.apply(plans[i])}); }
        return {status: 'Processed', results: results, skillActivationChanged: false};
    },

    _affectedDefinitions: function (table, row) {
        var ids = [], self = this, records, i;
        function add(id) { if (self._validId(id) && ids.indexOf(id) === -1) { ids.push(id); } }
        function prompt(id) { var p = self._read('sys_generative_ai_config', id); if (p && p.definition_table === 'sys_one_extend_capability_definition') { add(p.definition); } }
        if (!row) { return ids; }
        if (table === 'sys_one_extend_capability_definition') { add(row.sys_id); }
        else if (table === 'sys_generative_ai_config') { if (row.definition_table === 'sys_one_extend_capability_definition') { add(row.definition); } }
        else if (table === 'sys_generative_ai_prompt_config') { add(row.definition); prompt(row.ai_config); }
        else if (table === 'sys_generative_ai_request_validator') { add(row.definition); if (row.document_table === 'sys_one_extend_capability_definition') { add(row.document_id); } else if (row.document_table === 'sys_generative_ai_config') { prompt(row.document_id); } }
        else if (table === 'sys_generative_ai_response_validator') { if (row.definition_table === 'sys_generative_ai_config') { prompt(row.definition); } else { add(row.definition); } }
        else if (table === 'sys_generative_ai_validator') {
            records = this._query('sys_generative_ai_request_validator', [['validator', '=', row.sys_id]]).concat(this._query('sys_generative_ai_response_validator', [['validator', '=', row.sys_id]]));
            for (i = 0; i < records.length; i++) {
                var nested = this._affectedDefinitions(this._own(records[i], 'document_id') ? 'sys_generative_ai_request_validator' : 'sys_generative_ai_response_validator', records[i]), j;
                for (j = 0; j < nested.length; j++) { add(nested[j]); }
            }
        } else if (table === 'sys_one_extend_definition_attribute' && row.capability) {
            records = this._query('sys_one_extend_capability_definition', [['capability', '=', row.capability]]);
            for (i = 0; i < records.length; i++) { add(records[i].sys_id); }
        } else { add(row.definition); }
        return ids;
    },

    _graph: function (definition, plan) {
        var specs = [['sys_one_extend_definition_config', 'definition'], ['sys_generative_ai_config', 'definition'], ['sys_generative_ai_prompt_config', 'definition'], ['sys_one_extend_definition_attribute', 'definition'], ['sys_generative_ai_request_validator', 'document_id'], ['sys_generative_ai_response_validator', 'definition']], graph = [{table: 'sys_one_extend_capability_definition', row: definition}], i, j, rows, r, promptIds = [], allPrompts = {}, validators = {}, d = definition.sys_id;
        for (i = 0; i < specs.length; i++) {
            rows = this._query(specs[i][0], [[specs[i][1], '=', d]]);
            if (specs[i][0] === 'sys_one_extend_definition_attribute' && plan.nativeConfigContract) {
                rows = this._query(specs[i][0], [['capability', '=', definition.capability]]); plan.sharedInputs = [];
                for (j = 0; j < rows.length; j++) { r = rows[j]; this._require(r.capability === definition.capability, 'Conflict', 'SharedInputCapabilityMismatch'); plan.dependencies.push({table: specs[i][0], id: r.sys_id, hash: this._hash(r)}); plan.sharedInputs.push({id: r.sys_id, capability: r.capability, legacyDefinition: r.definition || ''}); }
                continue;
            }
            if (specs[i][0] === 'sys_generative_ai_request_validator') {
                rows = this._query(specs[i][0], [['document_id', '=', d], ['document_table', '=', 'sys_one_extend_capability_definition']]);
                rows = this._union(rows, this._query(specs[i][0], [['definition', '=', d]]));
                if (promptIds.length) { rows = this._union(rows, this._query(specs[i][0], [['document_id', 'IN', promptIds.join(',')], ['document_table', '=', 'sys_generative_ai_config']])); }
            }
            if (specs[i][0] === 'sys_generative_ai_response_validator' && promptIds.length) { rows = this._union(rows, this._query(specs[i][0], [['definition', 'IN', promptIds.join(',')], ['definition_table', '=', 'sys_generative_ai_config']])); }
            if (specs[i][0] === 'sys_generative_ai_prompt_config') {
                this._require(promptIds.length, 'BlockedPrerequisite', 'NoPromptConfigurations');
                rows = this._union(rows, this._query(specs[i][0], [['ai_config', 'IN', promptIds.join(',')]]));
            }
            for (j = 0; j < rows.length; j++) {
                r = rows[j];
                if (specs[i][0] === 'sys_generative_ai_config') {
                    this._require(r.definition === d && r.definition_table === 'sys_one_extend_capability_definition', 'Conflict', 'PromptDefinitionMismatch:' + r.sys_id);
                    promptIds.push(r.sys_id); allPrompts[r.sys_id] = true;
                }
                if (specs[i][0] === 'sys_generative_ai_prompt_config') { this._require((!r.definition || r.definition === d) && allPrompts[r.ai_config], 'Conflict', 'PromptBindingMismatch:' + r.sys_id); }
                if (specs[i][0] === 'sys_one_extend_definition_config' || specs[i][0] === 'sys_one_extend_definition_attribute') { this._require(r.capability === definition.capability, 'Conflict', 'CapabilityLinkMismatch:' + r.sys_id); }
                if (specs[i][0] === 'sys_generative_ai_request_validator') {
                    var legacyOnly = r.definition === d && !r.document_id && !r.document_table;
                    var definitionLevel = r.document_id === d && r.document_table === 'sys_one_extend_capability_definition';
                    var promptLevel = allPrompts[r.document_id] && r.document_table === 'sys_generative_ai_config';
                    this._require((legacyOnly || definitionLevel || promptLevel) && (!r.definition || r.definition === d), 'Conflict', 'RequestValidatorBindingMismatch:' + r.sys_id);
                }
                if (specs[i][0] === 'sys_generative_ai_response_validator') { this._require((r.definition === d && r.definition_table === 'sys_one_extend_capability_definition') || (allPrompts[r.definition] && r.definition_table === 'sys_generative_ai_config'), 'Conflict', 'ResponseValidatorBindingMismatch:' + r.sys_id); }
                if (specs[i][0] === 'sys_generative_ai_request_validator' || specs[i][0] === 'sys_generative_ai_response_validator') {
                    var v = this._read('sys_generative_ai_validator', r.validator);
                    this._require(v && typeof v.validator_script === 'string' && v.validator_script.replace(/\s/g, ''), 'BlockedPrerequisite', 'SharedValidatorMissingOrUnreadable:' + r.validator);
                    if (!validators[r.validator]) { plan.dependencies.push({table: 'sys_generative_ai_validator', id: r.validator, hash: this._hash(v)}); validators[r.validator] = true; }
                }
                graph.push({table: specs[i][0], row: r});
            }
        }
        this._require(promptIds.length, 'BlockedPrerequisite', 'NoPromptConfigurations');
        var ordered = [], pending = graph.slice(0), known = {}, graphIds = {}, progress = true;
        for (i = 0; i < graph.length; i++) { graphIds[graph[i].row.sys_id] = true; }
        while (pending.length && progress) {
            progress = false;
            for (i = 0; i < pending.length; i++) {
                r = pending[i]; var refs = this._internalReferences(r.table), ready = true, f;
                for (j = 0; j < refs.length; j++) { f = refs[j]; if (r.row[f] && graphIds[r.row[f]] && !known[r.row[f]]) { ready = false; } }
                if (ready) { ordered.push(r); known[r.row.sys_id] = true; pending.splice(i, 1); i--; progress = true; }
            }
        }
        this._require(!pending.length, 'Conflict', 'CyclicNativeGraphReferences');
        return ordered;
    },

    _desired: function (table, source, target, ids, profile, plan) {
        var fields = this._fields(table), out = {}, i, f, value, refs = this._references(table), prerequisite, isDef = table === 'sys_one_extend_capability_definition';
        for (i = 0; i < fields.length; i++) {
            f = fields[i]; value = this._value(source[f]);
            if (refs[f] && value) {
                if (ids[value]) { value = ids[value]; }
                else {
                    this._require(this._internalReferences(table).indexOf(f) === -1, 'Conflict', 'ExternalGraphReferenceRequiresReview:' + table + '.' + f);
                    prerequisite = this._read(refs[f], value); this._require(prerequisite, 'BlockedPrerequisite', 'ReferencedRecordMissing:' + refs[f] + ':' + value);
                    plan.dependencies.push({table: refs[f], id: value, hash: this._hash(prerequisite)});
                }
            }
            out[f] = value;
        }
        if ((isDef || table === 'sys_generative_ai_config') && this._own(out, 'name')) { out.name = this._providerName(source.name); }
        if (isDef) { out.api = profile.implementationId; out.api_type = profile.implementationTable; out.connection = profile.definitionConnectionId; }
        if (table === 'sys_generative_ai_config') { out.model = profile.modelString; out.active = target ? this._value(target.active) : this._value(source.active); }
        if (table === 'sys_one_extend_definition_config') { out.active = target ? this._value(target.active) : '0'; out['default'] = target ? this._value(target['default']) : '0'; }
        if (this._own(out, 'filter_properties')) { out.filter_properties = this._filters(source.filter_properties, plan.mapping, profile, isDef); }
        return out;
    },

    _filters: function (text, mapping, profile, definition) {
        var v, oldSelector = mapping.provider + mapping.provider_api, newSelector = profile.provider + profile.providerApi;
        if (!text) { v = {}; }
        else { try { v = JSON.parse(text); } catch (e) { this._require(false, 'Conflict', 'FilterPropertiesMustBeJSONObject'); } }
        this._require(v && Object.prototype.toString.call(v) === '[object Object]', 'Conflict', 'FilterPropertiesMustBeJSONObject');
        if (this._own(v, 'provider')) { this._require(typeof v.provider === 'string' && v.provider === oldSelector, 'Conflict', 'AmbiguousProviderFilter'); v.provider = newSelector; }
        else if (definition) { v.provider = newSelector; }
        if (this._own(v, 'provider_api')) { this._require(v.provider_api === mapping.provider_api, 'Conflict', 'AmbiguousProviderAPIFilter'); v.provider_api = profile.providerApi; }
        return this._canonical(v);
    },

    _profile: function (p) {
        this._require(p && this._validId(p.providerId) && this._validId(p.mappingId) && this._validId(p.implementationId) && this._validId(p.modelId) && this._validId(p.transformerId) && this._validId(p.definitionConnectionId) && p.implementationTable === 'sys_hub_flow' && p.provider === 'Custom LLM' && p.providerApi === 'custom_api' && p.modelString && p.fingerprint, 'BlockedPrerequisite', 'IncompleteConfiguredCustomModelProfile');
    },
    _assertFresh: function (plan, completed) {
        var i, a, current;
        if (plan.nativeConfigContract) { this._require(this._hash(this._store.nativeDefinitionConfigContract()) === this._hash(plan.nativeConfigContract), 'NeedsRecovery', 'NativeDefinitionConfigContractChanged'); }
        for (i = 0; i < (plan.selectionSnapshot || []).length; i++) {
            a = plan.selectionSnapshot[i]; current = this._read('sys_one_extend_definition_config', a.sys_id);
            this._require(current && this._value(current.definition) === this._value(a.definition) && this._value(current.capability) === this._value(a.capability) && this._value(current.active) === this._value(a.active) && this._value(current['default']) === this._value(a['default']), 'NeedsRecovery', 'ExistingSkillProviderSelectionChanged:' + a.sys_id);
        }
        this._require(this._hash(this._store.resolveTargetProfile()) === this._hash(plan.profile), 'NeedsRecovery', 'TargetProfileChangedDuringApply');
        for (i = 0; i < plan.dependencies.length; i++) { a = plan.dependencies[i]; this._require(this._hash(this._read(a.table, a.id)) === a.hash, 'NeedsRecovery', 'DependencyChangedDuringApply:' + a.table); }
        for (i = 0; i < plan.artifacts.length; i++) {
            a = plan.artifacts[i]; this._require(this._hash(this._read(a.table, a.sourceId)) === this._hash(a.source), 'NeedsRecovery', 'SourceChangedDuringApply:' + a.sourceId);
            if (a.pendingNativeGeneration) {
                var parentField = a.table === 'sys_generative_ai_prompt_config' ? 'ai_config' : 'definition';
                var rows = this._query(a.table, [[parentField, '=', a.desired[parentField]]]);
                this._require(completed.indexOf(a.desired[parentField]) === -1 ? rows.length === 0 : rows.length === 1 && rows[0][parentField] === a.desired[parentField] && rows[0].definition === a.desired.definition && (a.table !== 'sys_one_extend_definition_config' || rows[0].capability === a.desired.capability), 'NeedsRecovery', 'PendingNativeChildDrift:' + a.table);
                continue;
            }
            current = this._read(a.table, a.targetId);
            if (completed.indexOf(a.targetId) !== -1) { this._require(current && this._managedHash(a.table, current) === a.nextOrigin.baseline, 'NeedsRecovery', 'CompletedTargetChangedDuringApply'); }
            else { this._require(this._hash(current) === this._hash(a.target), 'NeedsRecovery', 'TargetChangedDuringApply:' + a.targetId); }
        }
    },
    _managedHash: function (table, row) {
        if (!row) { return this._hash(null); }
        var fields = this._fields(table), out = {}, i, f;
        for (i = 0; i < fields.length; i++) { f = fields[i]; if ((table === 'sys_one_extend_definition_config' && (f === 'active' || f === 'default')) || (table === 'sys_generative_ai_config' && f === 'active')) { continue; } out[f] = this._value(row[f]); }
        return this._hash(out);
    },
    _nativeConfigChanges: function (desired, current, table) {
        var allowed = table === 'sys_generative_ai_prompt_config' ? ['filter_properties', 'filter_type', 'is_default', 'order'] : ['enable_large_input_support', 'sys_overrides'], changes = {}, i, f;
        for (i = 0; i < allowed.length; i++) { f = allowed[i]; if (this._own(desired, f) && this._value(desired[f]) !== this._value(current[f])) { changes[f] = desired[f]; } }
        return changes;
    },
    _providerName: function (name) {
        name = this._value(name); var found = false, replaced = name.replace(/\bNow\s+LLM(?:\s+(?:Generic|Service))?\b/gi, function () { found = true; return 'Custom LLM'; });
        return found || /\bCustom LLM\b/.test(replaced) ? replaced : replaced + ' (Custom LLM)';
    },
    _originKey: function (d, t, s) { return 'origin|' + d + '|' + t + '|' + s; },
    _operationKey: function (d) { return 'operation|' + d; },
    _authorize: function () { this._require(this._store && this._store.authorized(), 'BlockedPermission', 'AdminRequired'); },
    _read: function (table, id) { if (!id) { return null; } return this._store.read(table, id, this._readFields(table)); },
    _query: function (table, filters) { return this._store.query(table, filters, this._readFields(table)); },
    _readFields: function (table) { return this._store.fields(table, ['sys_id', 'sys_mod_count', 'sys_scope', 'sys_package', 'sys_domain', 'sys_policy'].concat(this._schema[table] || [])); },
    _fields: function (table) { this._require(this._schema[table], 'BlockedPrerequisite', 'UnreviewedTable:' + table); return this._store.fields(table, this._schema[table]); },
    _internalReferences: function (t) { var m = {sys_one_extend_definition_config: ['definition', 'sys_overrides'], sys_generative_ai_config: ['definition', 'parent', 'sys_overrides'], sys_generative_ai_prompt_config: ['definition', 'ai_config'], sys_one_extend_definition_attribute: ['definition'], sys_generative_ai_request_validator: ['definition', 'document_id', 'sys_overrides'], sys_generative_ai_response_validator: ['definition', 'sys_overrides']}; return m[t] || []; },
    _references: function (t) {
        var d = 'sys_one_extend_capability_definition', p = 'sys_generative_ai_config', c = 'sys_one_extend_capability', v = 'sys_generative_ai_validator', m = {};
        m[d] = {capability: c, category: 'sys_one_extend_definition_category', truncate_strategy: 'sys_one_extend_truncate_strategy'};
        m.sys_one_extend_definition_config = {capability: c, definition: d, sys_overrides: 'sys_one_extend_definition_config'};
        m[p] = {definition: d, parent: p, sys_overrides: p};
        m.sys_generative_ai_prompt_config = {ai_config: p, definition: d};
        m.sys_one_extend_definition_attribute = {definition: d, capability: c, group: 'sys_one_extend_attribute_group'};
        m.sys_generative_ai_request_validator = {document_id: d, definition: d, validator: v, sys_overrides: 'sys_generative_ai_request_validator'};
        m.sys_generative_ai_response_validator = {definition: d, validator: v, sys_overrides: 'sys_generative_ai_response_validator'};
        return m[t] || {};
    },
    _fieldSchema: function () {
        return {
            sys_one_extend_capability_definition: 'advanced,api,api_type,capability,category,connection,description,filter_properties,metadata,name,order,postprocessor,preprocessor,truncate_strategy'.split(','),
            sys_one_extend_definition_config: 'active,capability,default,definition,enable_large_input_support,sys_overrides'.split(','),
            sys_generative_ai_config: 'active,additional_configurations,ai_suggested,definition,definition_table,documentation,max_tokens,min_word_count,model,name,parent,prompt,prompt_template_role,provider_company,show_in_prompt_library,state,structured_output_enabled,structured_output_schema,sys_overrides,temperature,thinking_tokens,version'.split(','),
            sys_generative_ai_prompt_config: 'ai_config,definition,filter_properties,filter_type,is_default,order'.split(','),
            sys_one_extend_definition_attribute: 'active,advanced,apply_filter,attribute_label,capability,choice_list,contains_large_input,data_type,default_value,definition,description,group,hidden,info,label,mandatory,name,order,schema,translate,truncate,type,user_query'.split(','),
            sys_generative_ai_request_validator: 'document_id,document_table,definition,validator,order,active,sys_overrides'.split(','),
            sys_generative_ai_response_validator: 'definition,definition_table,validator,order,active,sys_overrides'.split(','),
            sys_generative_ai_validator: 'name,validator_script,active,sys_overrides'.split(','),
            sys_gen_ai_provider: 'gen_ai_provider,integration_type'.split(','),
            sys_generative_ai_provider_mapping: 'gen_ai_provider,provider,provider_api,provider_implementation,provider_implementation_document,active,connection'.split(','),
            sys_generative_ai_model_config: 'provider,model,connection,active,lifecycle_state,usage_mode,request_transformation_script'.split(','),
            sys_generative_ai_custom_llm_transformer: 'model,request_transformer,response_transformer'.split(','),
            sys_one_extend_capability: 'name,active'.split(','),
            sys_one_extend_definition_category: ['name'], sys_one_extend_truncate_strategy: ['name', 'strategy'], sys_one_extend_attribute_group: ['name'], sys_hub_flow: ['name', 'status'], sys_alias: ['name', 'type']
        };
    },
    _planHash: function (p) { var copy = JSON.parse(JSON.stringify(p)); delete copy.hash; return this._hash(copy); },
    _hash: function (value) { return this._store.hash(this._canonical(value)); },
    _canonical: function (v) { if (v === null || typeof v === 'undefined') { return 'null'; } if (typeof v !== 'object') { return JSON.stringify(v); } var out = [], i, keys; if (Object.prototype.toString.call(v) === '[object Array]') { for (i = 0; i < v.length; i++) { out.push(this._canonical(v[i])); } return '[' + out.join(',') + ']'; } keys = this._keys(v).sort(); for (i = 0; i < keys.length; i++) { out.push(JSON.stringify(keys[i]) + ':' + this._canonical(v[keys[i]])); } return '{' + out.join(',') + '}'; },
    _keys: function (v) { var out = [], k; if (v) { for (k in v) { if (this._own(v, k)) { out.push(k); } } } return out; },
    _own: function (o, k) { return Object.prototype.hasOwnProperty.call(o, k); },
    _value: function (v) { return v === null || typeof v === 'undefined' ? '' : String(v); },
    _validId: function (id) { return /^[0-9a-f]{32}$/.test(String(id || '')); },
    _require: function (condition, status, message) { if (!condition) { var e = new Error(message); e.mirrorStatus = status; throw e; } },
    _union: function (a, b) { var out = a.slice(0), seen = {}, i; for (i = 0; i < a.length; i++) { seen[a[i].sys_id] = true; } for (i = 0; i < b.length; i++) { if (!seen[b[i].sys_id]) { out.push(b[i]); seen[b[i].sys_id] = true; } } out.sort(function (x, y) { return x.sys_id < y.sys_id ? -1 : x.sys_id > y.sys_id ? 1 : 0; }); return out; },

    _readConfiguration: function () {
        return {automationEnabled: this._store.setting('automation_enabled') === 'true', applyEnabled: this._store.setting('apply_enabled') === 'true', serializedExecutionVerified: this._store.setting('serialized_execution_verified') === 'true'};
    },

    _nativeStore: function () {
        var mirror = this, prefix = this.namespace + '.', propertyFields = ['sys_id', 'sys_mod_count', 'name', 'value', 'type', 'is_private', 'ignore_cache', 'read_roles', 'write_roles'], stateTable = 'u_custom_llm_prompt_mirror_state', stateFields = ['sys_id', 'sys_mod_count', 'u_key', 'u_kind', 'u_payload'];
        function gr(table) { var r = new GlideRecordSecure(table); mirror._require(r.isValid(), 'BlockedPrerequisite', 'InvalidTable:' + table); return r; }
        function field(r, f, read) { mirror._require(r.isValidField(f), 'BlockedPrerequisite', 'InvalidField:' + r.getTableName() + '.' + f); var e = r.getElement(f); mirror._require(e !== null && typeof e !== 'undefined' && (read ? e.canRead() : e.canWrite()), 'BlockedPermission', (read ? 'Read' : 'Write') + 'Denied:' + r.getTableName() + '.' + f); return e; }
        function snapshot(r, fields) { mirror._require(r.canRead(), 'BlockedPermission', 'RecordReadDenied:' + r.getTableName()); var o = {}, i; for (i = 0; i < fields.length; i++) { field(r, fields[i], true); o[fields[i]] = mirror._value(r.getValue(fields[i])); } return o; }
        function set(r, values) { var k; for (k in values) { if (mirror._own(values, k)) { r.setValue(k, values[k]); } } }
        function protectedProperty(r) { var values = snapshot(r, propertyFields); mirror._require(values.is_private === '1' || values.is_private === 'true', 'BlockedPermission', 'StatePropertyMustBePrivate'); mirror._require(values.read_roles === 'admin' && values.write_roles === 'admin', 'BlockedPermission', 'StatePropertyMustBeAdminOnly'); return values; }
        function byName(name) { var r = gr('sys_properties'); field(r, 'name', true); r.addQuery('name', name); r.query(); if (!r.next()) { return null; } var values = protectedProperty(r); mirror._require(!r.next(), 'Conflict', 'DuplicateStateProperty:' + name); return values; }
        function valueLength(r, name, value, element) {
            var label = r.getTableName() + '.' + name, descriptor = typeof element.getED === 'function' ? element.getED() : null;
            mirror._require(descriptor && typeof descriptor.getInternalType === 'function' && typeof descriptor.getLength === 'function', 'BlockedPrerequisite', 'NativeFieldDescriptorUnavailable:' + label);
            var type = String(descriptor.getInternalType()), nonCharacter = ['boolean', 'integer', 'long', 'longint', 'numeric', 'decimal', 'float', 'double', 'currency', 'price', 'percent_complete', 'order_index', 'date', 'glide_date', 'glide_date_time', 'glide_time', 'glide_duration', 'due_date', 'timer', 'reference', 'domain_id', 'GUID', 'guid'];
            if (nonCharacter.indexOf(type) !== -1) { return; }
            var limit = Number(descriptor.getLength()), length = mirror._value(value).length;
            mirror._require(type && isFinite(limit) && limit > 0 && Math.floor(limit) === limit, 'BlockedPrerequisite', 'NativeFieldLengthUnavailable:' + label);
            mirror._require(length <= limit, 'BlockedPrerequisite', 'FieldValueTooLong:' + label + '; intended=' + length + '; maximum=' + limit);
        }
        function productPreflight(r, values, insert) { var k; if (!insert && r.isValidField('sys_policy')) { field(r, 'sys_policy', true); mirror._require(!r.getValue('sys_policy'), 'Protected', 'ProtectedTarget'); } set(r, values); mirror._require(insert ? r.canCreate() : r.canWrite(), 'BlockedPermission', 'RecordWriteDenied:' + r.getTableName()); for (k in values) { if (mirror._own(values, k)) { valueLength(r, k, values[k], field(r, k, false)); } } }
        function creationOwnership(r) {
            var result = snapshot(r, store.fields(r.getTableName(), ['sys_scope', 'sys_package', 'sys_domain']));
            if (mirror._own(result, 'sys_package') && !result.sys_package) {
                // Native metadata persistence supplies the current application's
                // package. Resolve the actual scope/package records; never set
                // ownership fields or copy the source record's package.
                var app = String(gs.getCurrentApplicationId()), scope = gr('sys_scope'), pkg = gr('sys_package');
                mirror._require(app === 'global' && result.sys_scope === app && scope.get(app) && pkg.get(app), 'BlockedPrerequisite', 'NativeCreationPackageNotResolvableOrUnverifiedScope');
                var scopeValues = snapshot(scope, ['sys_id', 'scope']), packageValues = snapshot(pkg, ['sys_id', 'source']);
                mirror._require(scopeValues.sys_id === app && packageValues.sys_id === app && scopeValues.scope && scopeValues.scope === packageValues.source, 'BlockedPrerequisite', 'NativeCreationPackageScopeMismatch');
                result.sys_package = packageValues.sys_id;
            }
            return result;
        }
        function digest(key) { return String(new GlideDigest().getSHA256Hex(key)).toLowerCase(); }
        function stateValues(key, body) {
            var kind = String(key).split('|')[0], payload = mirror._canonical({key: key, body: body});
            mirror._require(['origin', 'operation', 'claim'].indexOf(kind) !== -1, 'Conflict', 'UnknownStateKind');
            mirror._require(payload.length <= 4000, 'BlockedPrerequisite', 'StatePayloadTooLargeNoTruncation');
            return {u_key: digest(key), u_kind: kind, u_payload: payload};
        }
        function decodeState(values, expectedKey) {
            var data; try { data = JSON.parse(values.u_payload); } catch (e) { mirror._require(false, 'NeedsRecovery', 'InvalidStateJSON'); }
            mirror._require(data && typeof data.key === 'string' && data.body && values.u_key === digest(data.key) && values.u_kind === data.key.split('|')[0] && (!expectedKey || data.key === expectedKey), 'Conflict', 'StateKeyCollisionOrInvalidEnvelope');
            return data;
        }
        function stateRead(key) {
            var r = gr(stateTable); field(r, 'u_key', true); r.addQuery('u_key', digest(key)); r.query(); if (!r.next()) { return null; }
            var values = snapshot(r, stateFields); decodeState(values, key); mirror._require(!r.next(), 'Conflict', 'DuplicateStateKey'); return values;
        }
        function statePreflight(key, body) {
            var old = stateRead(key), r = gr(stateTable), values = stateValues(key, body);
            if (old) { mirror._require(r.get(old.sys_id), 'NeedsRecovery', 'StateMissing'); } else { r.newRecord(); r.setNewGuidValue(digest('mirror-state-v1|' + key).substr(0, 32)); }
            productPreflight(r, values, !old); return old;
        }
        function stateWrite(key, body, insertOnly) {
            var old = statePreflight(key, body), r = gr(stateTable), values = stateValues(key, body);
            if (insertOnly) { mirror._require(!old, 'NeedsRecovery', 'BusyOrNeedsRecovery'); }
            if (old) { mirror._require(r.get(old.sys_id) && mirror._value(r.getValue('sys_mod_count')) === old.sys_mod_count, 'NeedsRecovery', 'StateRevisionChanged'); productPreflight(r, values, false); mirror._require(r.update(), 'NeedsRecovery', 'StateUpdateFailed'); }
            else { r.newRecord(); r.setNewGuidValue(digest('mirror-state-v1|' + key).substr(0, 32)); productPreflight(r, values, true); mirror._require(r.insert(), 'NeedsRecovery', 'StateInsertFailed'); }
            var readback = stateRead(key); mirror._require(readback && readback.u_key === values.u_key && readback.u_kind === values.u_kind && readback.u_payload === values.u_payload, 'NeedsRecovery', 'StateReadbackMismatch'); return readback;
        }
        var store = {
            authorized: function () { return gs.hasRole('admin'); },
            hash: function (s) { return String(new GlideDigest().getSHA256Hex(s)).toLowerCase(); },
            now: function () { return Number(new GlideDateTime().getNumericValue()); },
            fields: function (t, allow) { var r = gr(t), out = [], i; for (i = 0; i < allow.length; i++) { if (r.isValidField(allow[i])) { out.push(allow[i]); } } return out; },
            read: function (t, id, fields) { var r = gr(t); if (!r.get(id)) { return null; } return snapshot(r, fields); },
            query: function (t, predicates, fields) { var r = gr(t), out = [], i; for (i = 0; i < predicates.length; i++) { field(r, predicates[i][0], true); mirror._require(['=', 'IN'].indexOf(predicates[i][1]) !== -1, 'Conflict', 'QueryOperatorNotAllowed'); r.addQuery(predicates[i][0], predicates[i][1], predicates[i][2]); } r.query(); while (r.next()) { out.push(snapshot(r, fields)); } return out; },
            preflight: function (t, id, values, insert) { var r = gr(t); if (insert) { r.newRecord(); r.setNewGuidValue(id); } else { mirror._require(r.get(id), 'Conflict', 'TargetMissing'); } productPreflight(r, values, insert); return insert ? creationOwnership(r) : snapshot(r, this.fields(t, ['sys_scope', 'sys_package', 'sys_domain'])); },
            nativeDefinitionConfigContract: function () {
                var r = gr('sys_script'); r.addQuery('name', 'Auto-add definition config record'); r.addQuery('collection', 'sys_one_extend_capability_definition'); r.addQuery('active', '1'); r.query();
                mirror._require(r.next(), 'BlockedPrerequisite', 'NativeDefinitionConfigGeneratorMissing');
                var recipe = snapshot(r, ['sys_id', 'sys_mod_count', 'name', 'collection', 'active', 'when', 'order', 'advanced', 'condition', 'filter_condition', 'action_insert', 'action_update', 'script']);
                mirror._require(!r.next(), 'Conflict', 'NativeDefinitionConfigGeneratorAmbiguous');
                mirror._require(recipe.when === 'after' && recipe.order === '100' && (recipe.advanced === '1' || recipe.advanced === 'true') && !recipe.condition && !recipe.filter_condition && (recipe.action_insert === '1' || recipe.action_insert === 'true') && digest(recipe.script) === '06aee715244f8a495dce6feed79ae76946c57cd9e38a5fdde3280792702c9e3e', 'BlockedPrerequisite', 'UnsupportedNativeDefinitionConfigGeneratorRecipe');
                var d = gr('sys_dictionary'); d.addQuery('name', 'sys_one_extend_definition_config'); d.addQuery('element', 'capability'); d.query(); mirror._require(d.next(), 'BlockedPrerequisite', 'NativeDefinitionConfigCapabilityDictionaryMissing');
                var dictionary = snapshot(d, ['sys_id', 'sys_mod_count', 'name', 'element', 'read_only', 'read_only_option', 'reference']); mirror._require(!d.next(), 'Conflict', 'NativeDefinitionConfigCapabilityDictionaryAmbiguous');
                mirror._require((dictionary.read_only === '1' || dictionary.read_only === 'true') && dictionary.read_only_option === 'strict_read_only' && dictionary.reference === 'sys_one_extend_capability', 'BlockedPrerequisite', 'UnsupportedNativeDefinitionConfigCapabilityContract');
                var fresh = gr('sys_one_extend_definition_config'); fresh.newRecord(); var defaults = snapshot(fresh, ['active', 'enable_large_input_support', 'sys_overrides']); defaults['default'] = '0';
                mirror._require((defaults.active === '1' || defaults.active === 'true') && !defaults.sys_overrides, 'BlockedPrerequisite', 'UnsupportedNativeDefinitionConfigDefaults');
                var pr = gr('sys_script'); pr.addQuery('name', 'Insert New Prompt Config '); pr.addQuery('collection', 'sys_generative_ai_config'); pr.addQuery('active', '1'); pr.query(); mirror._require(pr.next(), 'BlockedPrerequisite', 'NativePromptBindingGeneratorMissing');
                var promptRecipe = snapshot(pr, ['sys_id', 'sys_mod_count', 'name', 'collection', 'active', 'when', 'order', 'condition', 'filter_condition', 'action_insert', 'action_update', 'script']); mirror._require(!pr.next(), 'Conflict', 'NativePromptBindingGeneratorAmbiguous');
                mirror._require(promptRecipe.when === 'after' && promptRecipe.order === '100' && !promptRecipe.condition && !promptRecipe.filter_condition && (promptRecipe.action_insert === '1' || promptRecipe.action_insert === 'true') && (promptRecipe.action_update === '0' || promptRecipe.action_update === 'false') && digest(promptRecipe.script) === '334abe1489f494fa8ef6bf46cf71b76c6f84c7862b0e01ed1bc98fca5a280b9b', 'BlockedPrerequisite', 'UnsupportedNativePromptBindingGeneratorRecipe');
                var pd = gr('sys_dictionary'); pd.addQuery('name', 'sys_generative_ai_prompt_config'); pd.addQuery('element', 'definition'); pd.query(); mirror._require(pd.next(), 'BlockedPrerequisite', 'NativePromptBindingDefinitionDictionaryMissing');
                var promptDictionary = snapshot(pd, ['sys_id', 'sys_mod_count', 'name', 'element', 'read_only', 'read_only_option', 'reference', 'calculation']); mirror._require(!pd.next(), 'Conflict', 'NativePromptBindingDefinitionDictionaryAmbiguous');
                mirror._require((promptDictionary.read_only === '1' || promptDictionary.read_only === 'true') && promptDictionary.read_only_option === 'strict_read_only' && promptDictionary.reference === 'sys_one_extend_capability_definition' && digest(promptDictionary.calculation) === '99e7fc3ac44a635144359b13258e345831c67d9f972fd3b2d632d4a7a15f1963', 'BlockedPrerequisite', 'UnsupportedNativePromptBindingDefinitionContract');
                return {version: 1, fingerprint: mirror._hash({recipe: recipe, dictionary: dictionary, defaults: defaults}), defaults: defaults, promptBinding: {fingerprint: mirror._hash({recipe: promptRecipe, dictionary: promptDictionary})}};
            },
            preflightNativeDefinitionConfig: function (definitionId, capabilityId, changes) {
                var r = gr('sys_one_extend_definition_config'); r.newRecord();
                // Context-only populated prototype: never insert this record,
                // and never persist its read-only capability/reference fields.
                set(r, {definition: definitionId, capability: capabilityId});
                mirror._require(mirror._value(r.getValue('definition')) === definitionId && mirror._value(r.getValue('capability')) === capabilityId, 'BlockedPrerequisite', 'NativeConfigAclContextNotRepresentable');
                if (mirror._keys(changes).length) { productPreflight(r, changes, false); }
                return creationOwnership(r);
            },
            preflightNativePromptBinding: function (desired) {
                var r = gr('sys_generative_ai_prompt_config'); r.newRecord();
                // The actual native child is inserted by the prompt's after
                // rule. This object is only the intended ACL/update prototype.
                set(r, {ai_config: desired.ai_config, definition: desired.definition});
                var options = mirror._nativeConfigChanges(desired, {}, 'sys_generative_ai_prompt_config');
                if (mirror._keys(options).length) { productPreflight(r, options, false); }
                return creationOwnership(r);
            },
            write: function (t, id, values, revision, insert) {
                this.preflight(t, id, values, insert); var r = gr(t);
                if (insert) { r.newRecord(); r.setNewGuidValue(id); productPreflight(r, values, true); mirror._require(String(r.insert() || '') === id, 'NeedsRecovery', 'ProductInsertFailed:' + t); }
                else { mirror._require(r.get(id) && mirror._value(r.getValue('sys_mod_count')) === revision, 'NeedsRecovery', 'ProductRevisionChanged:' + t); productPreflight(r, values, false); mirror._require(r.update(), 'NeedsRecovery', 'ProductUpdateFailed:' + t); }
            },
            setting: function (key) { var p = byName(prefix + key); return p ? p.value : ''; },
            stateGet: function (key) { var row = stateRead(key); return row ? decodeState(row, key).body : null; },
            stateList: function (keyPrefix) { var r = gr(stateTable), out = [], data; field(r, 'u_kind', true); r.addQuery('u_kind', String(keyPrefix).split('|')[0]); r.query(); while (r.next()) { data = decodeState(snapshot(r, stateFields)); if (data.key.indexOf(keyPrefix) === 0) { out.push({key: data.key, body: data.body}); } } return out; },
            statePreflight: function (key, body) { statePreflight(key, body); },
            stateWrite: function (key, body) { stateWrite(key, body, false); },
            claimPreflight: function (key, ownClaim) { var stateKey = 'claim|' + key, old = stateRead(stateKey), r; mirror._require(!old || (ownClaim && ownClaim.stateKey === stateKey && this.owns(ownClaim)), 'NeedsRecovery', 'BusyOrNeedsRecovery'); statePreflight(stateKey, {owner: 'preflight'}); r = gr(stateTable); if (old) { mirror._require(r.get(old.sys_id), 'NeedsRecovery', 'ClaimMissing'); } else { r.newRecord(); r.setNewGuidValue(digest('mirror-state-v1|' + stateKey).substr(0, 32)); set(r, stateValues(stateKey, {owner: 'preflight'})); } mirror._require(r.canDelete(), 'BlockedPermission', 'ClaimDeleteDenied'); },
            claim: function (key) { var owner = String(gs.generateGUID()), stateKey = 'claim|' + key; stateWrite(stateKey, {owner: owner}, true); return {stateKey: stateKey, owner: owner}; },
            owns: function (c) { var row = stateRead(c.stateKey); return !!row && decodeState(row, c.stateKey).body.owner === c.owner; },
            release: function (c) { mirror._require(this.owns(c), 'NeedsRecovery', 'ClaimOwnershipLost'); var row = stateRead(c.stateKey), r = gr(stateTable); mirror._require(r.get(row.sys_id) && r.canDelete(), 'BlockedPermission', 'ClaimDeleteDenied'); mirror._require(mirror._value(r.getValue('u_payload')) === row.u_payload, 'NeedsRecovery', 'ClaimChangedBeforeRelease'); mirror._require(r.deleteRecord(), 'NeedsRecovery', 'ClaimDeleteFailed'); },
            resolveTargetProfile: function () { return mirror._resolveNativeTargetProfile(this); }
        };
        return store;
    },

    _resolveNativeTargetProfile: function (store) {
        var providers = this._query('sys_gen_ai_provider', [['gen_ai_provider', '=', 'Custom LLM Provider']]), mappings, models = [], requested = store.setting('default_model'), i, j, m, c, selected, mapping, transformers, provider, alias, mappingAlias, implementation;
        this._require(providers.length === 1, 'BlockedPrerequisite', 'CustomProviderMustBeUnique'); provider = providers[0];
        mappings = this._query('sys_generative_ai_provider_mapping', [['gen_ai_provider', '=', provider.sys_id], ['provider', '=', 'Custom LLM'], ['provider_api', '=', 'custom_api'], ['active', '=', '1']]);
        for (i = 0; i < mappings.length; i++) {
            m = mappings[i]; c = this._query('sys_generative_ai_model_config', [['provider', '=', m.sys_id]]);
            for (j = 0; j < c.length; j++) {
                if ((c[j].active !== '1' && c[j].active !== 'true') || String(c[j].usage_mode || '').toLowerCase() === 'restricted' || c[j].lifecycle_state !== 'active') { continue; }
                models.push(c[j]);
            }
        }
        if (requested) {
            this._require(this._validId(requested), 'BlockedPrerequisite', 'ConfiguredDefaultModelMustBeSysId');
            for (i = 0; i < models.length; i++) { if (models[i].sys_id === requested) { this._require(!selected, 'BlockedPrerequisite', 'ConfiguredDefaultModelAmbiguous'); selected = models[i]; } }
            this._require(selected, 'BlockedPrerequisite', 'ConfiguredDefaultModelNotEligible');
        } else { this._require(false, 'BlockedPrerequisite', 'ConfigureExplicitLocalCustomDefaultModel'); }
        for (i = 0; i < mappings.length; i++) { if (mappings[i].sys_id === selected.provider) { mapping = mappings[i]; } }
        this._require(mapping && mapping.provider_implementation_document === 'sys_hub_flow', 'BlockedPrerequisite', 'UnsupportedCustomImplementation');
        transformers = this._query('sys_generative_ai_custom_llm_transformer', [['model', '=', selected.sys_id]]);
        this._require(transformers.length === 1 && transformers[0].request_transformer && transformers[0].response_transformer, 'BlockedPrerequisite', 'CustomModelTransformerMustBeUniqueAndComplete');
        implementation = this._read(mapping.provider_implementation_document, mapping.provider_implementation);
        alias = this._read('sys_alias', selected.connection);
        mappingAlias = this._read('sys_alias', mapping.connection);
        this._require(implementation && alias && mappingAlias && selected.model && selected.connection && mapping.connection, 'BlockedPrerequisite', 'CustomModelConnectionOrImplementationMissing');
        // Native before rules populate the definition from the mapping alias.
        // The selected model keeps its own independently verified HTTP alias.
        return {providerId: provider.sys_id, mappingId: mapping.sys_id, implementationId: mapping.provider_implementation, implementationTable: mapping.provider_implementation_document, definitionConnectionId: mapping.connection, modelConnectionId: selected.connection, modelId: selected.sys_id, modelString: selected.model, transformerId: transformers[0].sys_id, provider: mapping.provider, providerApi: mapping.provider_api,
            selectionEvidence: 'explicit_local_default_model_property', fingerprint: this._hash({provider: provider, mapping: mapping, model: selected, transformer: transformers[0], implementation: implementation, modelAlias: alias, mappingAlias: mappingAlias})};
    },
    type: 'CustomLLMPromptMirror'
};
