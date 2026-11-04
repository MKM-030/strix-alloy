/* Standalone Global server-side ES5 Fix Script / Scripts - Background.
 * Change PARAMETERS, preview first, then set apply=true for that selection.
 * Existing prompt.model strings only: no provider/default/filter/history writes,
 * model loading, inference, credentials, ACL changes or workflow suppression.
 * Run without concurrent prompt editing. Revision checks are NOT a transaction;
 * a partial_or_uncertain result requires review, never an automatic retry.
 * Prompt ancestry uses parent/version and generated bindings. Native model
 * version mappings are separate and remain unchanged by this switch.
 * Incompatible copied ancestry is reported, never rewritten by this script.
 */
var PARAMETERS = {
    apply: false,
    allCapabilities: false,
    capabilityIds: [],
    targetModel: 'halogen-v2',
    modelConfigId: '',
    providerId: '',
    providerMappingId: '',
    includeInactive: false,
    allowAdminMaintenance: false,
    // Supply pre-existing, in-progress Update Sets in each target's own scope.
    // Preview reports requiredScopes. This script never creates/repairs headers.
    updateSetId: '',
    updateSetIdsByScope: {},
    // Optional reviewed customer definitions with no clone-map provenance.
    // These exact IDs assert customer ownership; scope/package/policy still apply.
    customerDefinitionIds: []
};

(function () {
    var p = PARAMETERS, out = {status: 'aborted', mode: p.apply === true ? 'apply' : 'preview', targets: [], excluded: [], warnings: [], attempted: [], completed: [], captureIds: [], requiredScopes: [], writes: 0};
    var guards = {}, discoveryGuards = {}, inventories = [], origins = {}, profile, definitions, capabilities, i, j;
    var definitionIdentityFields = ['sys_id', 'capability', 'api_type', 'api', 'connection'];
    var sets = {}, captures = {}, captureStates = {}, originalSet = '', selectionChanged = false;
    var revisionFields = {sys_updated_on: 1, sys_updated_by: 1, sys_mod_count: 1, request_tokens: 1};
    try {
        need(p.apply === undefined || typeof p.apply === 'boolean', 'apply_must_be_boolean');
        need(p.allCapabilities === undefined || typeof p.allCapabilities === 'boolean', 'all_capabilities_must_be_boolean');
        need(p.includeInactive === undefined || typeof p.includeInactive === 'boolean', 'include_inactive_must_be_boolean');
        need(p.allowAdminMaintenance === undefined || typeof p.allowAdminMaintenance === 'boolean', 'maintenance_must_be_boolean');
        capabilities = idList(p.capabilityIds || [], 'capability');
        p.customerDefinitionIds = idList(p.customerDefinitionIds || [], 'customer_definition');
        need(p.allCapabilities === true ? capabilities.length === 0 : capabilities.length > 0, p.allCapabilities === true ? 'all_and_selected_are_mutually_exclusive' : 'explicit_selection_required');
        need(typeof p.targetModel === 'string' && p.targetModel.length > 0, 'target_model_required');
        if (p.modelConfigId) need(validId(p.modelConfigId), 'invalid_model_config_id');
        if (p.providerId) need(validId(p.providerId), 'invalid_provider_id');
        if (p.providerMappingId) need(validId(p.providerMappingId), 'invalid_provider_mapping_id');
        profile = resolveProfile();
        out.model = {registrationId: profile.model.sys_id, name: profile.model.model, providerMappingId: profile.mapping.sys_id};
        readOrigins();
        if (p.allCapabilities === true) {
            definitions = query('sys_one_extend_capability_definition', [], definitionIdentityFields);
            capabilities = [];
            for (i = 0; i < definitions.length; i++) {
                if (definitionMatches(definitions[i])) {
                    if (capabilities.indexOf(definitions[i].capability) < 0) capabilities.push(definitions[i].capability);
                } else out.excluded.push({capabilityId: definitions[i].capability, definitionId: definitions[i].sys_id, reason: 'other_provider_or_implementation'});
            }
        }
        need(capabilities.length <= 500, 'capability_selection_limit_500');
        capabilities.sort();
        for (i = 0; i < capabilities.length; i++) {
            read('sys_one_extend_capability', capabilities[i], 'capability_unavailable');
            definitions = query('sys_one_extend_capability_definition', [['capability', capabilities[i]]], definitionIdentityFields);
            var count = out.targets.length;
            for (j = 0; j < definitions.length; j++) {
                var d = definitions[j];
                if (!definitionMatches(d)) { out.excluded.push({capabilityId: capabilities[i], definitionId: d.sys_id, reason: 'other_provider_or_implementation'}); continue; }
                try { planDefinition(read('sys_one_extend_capability_definition', d.sys_id)); }
                catch (definitionError) {
                    if (p.allCapabilities !== true) throw definitionError;
                    out.excluded.push({capabilityId: capabilities[i], definitionId: d.sys_id, reason: String(definitionError.message || definitionError)});
                }
            }
            if (out.targets.length === count) out.excluded.push({capabilityId: capabilities[i], reason: 'no_eligible_prompt_assignments'});
        }
        for (i = 0; i < out.targets.length; i++) {
            if (!out.targets[i].noOp && out.requiredScopes.indexOf(out.targets[i].scope) < 0) out.requiredScopes.push(out.targets[i].scope);
        }
        out.requiredScopes.sort();
        // Every selected capability, target, model/provider dependency, history
        // link and query membership is checked before the first possible write.
        assertFresh();
        if (p.apply !== true) { out.status = 'preview'; return; }
        preflightCapture();
        for (i = 0; i < out.targets.length; i++) {
            if (out.targets[i].beforeModel !== profile.model.model && out.targets[i].requiresAdminMaintenance) {
                need(p.allowAdminMaintenance === true, 'admin_maintenance_required:' + out.targets[i].configId);
                need(gs.hasRole('admin'), 'admin_required_for_maintenance');
            }
        }
        for (i = 0; i < out.targets.length; i++) {
            var t = out.targets[i];
            if (t.beforeModel === profile.model.model) continue;
            assertFresh();
            assertCaptureStates();
            selectSet(sets[t.scope]);
            var secure = open('sys_generative_ai_config');
            need(secure.get(t.configId) && secure.canRead(), 'target_unavailable_before_update:' + t.configId);
            need(same(snapshot(secure), guards[key('sys_generative_ai_config', t.configId)], false), 'target_drift_before_update:' + t.configId);
            var writer = secure;
            if (!(secure.canWrite() && secure.getElement('model').canWrite())) {
                need(p.allowAdminMaintenance === true && gs.hasRole('admin'), 'admin_maintenance_required:' + t.configId);
                // Ordinary GlideRecord supplies no guards or preimages. Its only
                // permitted mutation is this already securely checked model field.
                writer = new GlideRecord('sys_generative_ai_config');
                need(writer.get(t.configId) && String(writer.getUniqueValue()) === t.configId, 'maintenance_target_unavailable:' + t.configId);
            }
            need(same(snapshot(readRecord('sys_generative_ai_config', t.configId)), guards[key('sys_generative_ai_config', t.configId)], false), 'target_drift_before_write:' + t.configId);
            writer.setValue('model', profile.model.model);
            out.attempted.push(t.configId);
            need(String(writer.update() || '') === t.configId, 'native_update_failed:' + t.configId);
            out.writes++;
            var actual = snapshot(readRecord('sys_generative_ai_config', t.configId)), expected = copy(guards[key('sys_generative_ai_config', t.configId)]);
            expected.model = profile.model.model;
            need(same(actual, expected, true), 'native_readback_contract_changed:' + t.configId);
            guards[key('sys_generative_ai_config', t.configId)] = actual;
            captureRecord(t);
            out.completed.push(t.configId);
            assertFresh();
            assertCaptureStates();
        }
        out.status = out.writes ? 'applied' : 'no_op';
    } catch (error) {
        out.error = String(error.message || error);
        out.status = out.attempted.length ? 'partial_or_uncertain' : 'aborted';
    } finally {
        if (originalSet && (selectionChanged || String(gs.getPreference('sys_update_set') || '') !== originalSet)) {
            try {
                new GlideUpdateSet().set(originalSet);
                need(String(gs.getPreference('sys_update_set') || '') === originalSet, 'original_update_set_restore_failed');
            } catch (restoreError) {
                out.restoreError = String(restoreError.message || restoreError);
                out.status = 'partial_or_uncertain';
            }
        }
        gs.info('[CAPABILITY_MODEL_SWITCH] ' + JSON.stringify(out));
    }

    function need(condition, message) { if (!condition) throw new Error(message); }
    function own(o, k) { return Object.prototype.hasOwnProperty.call(o, k); }
    function key(table, id) { return table + ':' + id; }
    function validId(value) { return typeof value === 'string' && /^[0-9a-f]{32}$/.test(value); }
    function enabled(value) { return value === '1' || value === 'true'; }
    function idList(values, label) {
        need(Object.prototype.toString.call(values) === '[object Array]', label + '_ids_must_be_array');
        var seen = {}, n;
        for (n = 0; n < values.length; n++) { need(validId(values[n]), 'invalid_' + label + '_id'); need(!seen[values[n]], 'duplicate_' + label + '_id:' + values[n]); seen[values[n]] = true; }
        return values.slice(0);
    }
    function open(table) { var r = new GlideRecordSecure(table); need(r.isValid(), 'table_unavailable:' + table); return r; }
    function readRecord(table, id, message) {
        var r = open(table);
        need(validId(id) && r.get(id) && String(r.getUniqueValue()) === id && String(r.getRecordClassName()) === table && r.canRead(), (message || 'record_unavailable') + ':' + table + ':' + id);
        return r;
    }
    function snapshot(r) {
        need(r.canRead(), 'record_read_denied:' + r.getTableName());
        var fields = r.getElements(), result = {}, n, e, f, v;
        for (n = 0; n < fields.size(); n++) {
            e = fields.get(n); f = String(e.getName());
            need(e.canRead(), 'field_read_denied:' + r.getTableName() + '.' + f);
            v = r.getValue(f);
            if (String(e.getED().getInternalType()) === 'boolean') {
                need(v === true || v === false || v === '1' || v === '0' || v === 'true' || v === 'false' || v === 1 || v === 0, 'invalid_boolean:' + f);
                v = v === true || v === '1' || v === 'true' || v === 1 ? 'true' : 'false';
            }
            result[f] = v === null || typeof v === 'undefined' ? '' : String(v);
        }
        return result;
    }
    function read(table, id, message) {
        var value = snapshot(readRecord(table, id, message)), k = key(table, id);
        if (guards[k]) need(same(value, guards[k], false), 'record_changed_during_preflight:' + k);
        else guards[k] = value;
        return value;
    }
    function snapshotFields(r, fields) {
        need(r.canRead(), 'record_read_denied:' + r.getTableName());
        var result = {}, n;
        for (n = 0; n < fields.length; n++) {
            var field = fields[n];
            need(r.isValidField(field) && r.getElement(field).canRead(), 'identity_field_unavailable:' + r.getTableName() + '.' + field);
            var value = r.getValue(field); result[field] = value === null || typeof value === 'undefined' ? '' : String(value);
        }
        return result;
    }
    function query(table, conditions, identityFields) {
        var r = open(table), rows = [], n;
        for (n = 0; n < conditions.length; n++) {
            if (conditions[n].length === 3) r.addQuery(conditions[n][0], conditions[n][1], conditions[n][2]);
            else r.addQuery(conditions[n][0], conditions[n][1]);
        }
        r.query();
        while (r.next()) {
            need(String(r.getRecordClassName()) === table, 'unexpected_record_class:' + table);
            var row = identityFields ? snapshotFields(r, identityFields) : snapshot(r), k = key(table, row.sys_id);
            if (identityFields) {
                if (discoveryGuards[k]) need(same(row, discoveryGuards[k].values, false), 'identity_changed_during_preflight:' + k);
                else discoveryGuards[k] = {table: table, id: row.sys_id, fields: identityFields, values: row};
            } else if (guards[k]) need(same(row, guards[k], false), 'record_changed_during_preflight:' + k); else guards[k] = row;
            rows.push(row);
        }
        rows.sort(function (a, b) { return a.sys_id < b.sys_id ? -1 : a.sys_id > b.sys_id ? 1 : 0; });
        var ids = []; for (n = 0; n < rows.length; n++) ids.push(rows[n].sys_id);
        inventories.push({table: table, conditions: conditions, ids: ids.join(',')});
        return rows;
    }
    function resolveProfile() {
        var candidates = query('sys_generative_ai_model_config', [['model', p.targetModel]]), eligible = [], n, model;
        for (n = 0; n < candidates.length; n++) {
            model = candidates[n];
            if ((!p.modelConfigId || p.modelConfigId === model.sys_id) && (!p.providerMappingId || p.providerMappingId === model.provider)) {
                if (p.providerId && read('sys_generative_ai_provider_mapping', model.provider).gen_ai_provider !== p.providerId) continue;
                eligible.push(model);
            }
        }
        need(eligible.length === 1, eligible.length ? 'ambiguous_model_registration' : 'model_registration_missing_or_selection_mismatch');
        model = eligible[0];
        need(enabled(model.active) && model.lifecycle_state === 'active' && String(model.usage_mode || '').toLowerCase() !== 'restricted', 'model_registration_ineligible');
        var mapping = read('sys_generative_ai_provider_mapping', model.provider);
        need(enabled(mapping.active) && mapping.provider === 'Custom LLM' && mapping.provider_api === 'custom_api' && mapping.provider_implementation_document === 'sys_hub_flow', 'wrong_or_unsupported_model_provider');
        // Native prompt/model lookup (including calculated request_tokens)
        // resolves model STRING + definition API, not model registration ID.
        // Selectors cannot make that native key unique within one API flow.
        for (n = 0; n < candidates.length; n++) {
            if (candidates[n].sys_id === model.sys_id) continue;
            need(validId(candidates[n].provider), 'peer_model_provider_unavailable');
            var peerMapping = read('sys_generative_ai_provider_mapping', candidates[n].provider, 'peer_model_provider_unavailable');
            need(validId(peerMapping.provider_implementation), 'peer_model_implementation_unavailable');
            need(peerMapping.provider_implementation !== mapping.provider_implementation, 'ambiguous_native_model_string_within_implementation');
        }
        var provider = read('sys_gen_ai_provider', mapping.gen_ai_provider);
        need(!p.providerId || provider.sys_id === p.providerId, 'model_provider_selection_mismatch');
        need(provider.gen_ai_provider === 'Custom LLM Provider', 'wrong_model_provider_identity');
        need(validId(model.connection) && validId(mapping.connection), 'model_or_mapping_connection_required');
        read('sys_alias', model.connection); read('sys_alias', mapping.connection);
        read('sys_hub_flow', mapping.provider_implementation);
        var transformers = query('sys_generative_ai_custom_llm_transformer', [['model', model.sys_id]]);
        need(transformers.length === 1 && transformers[0].request_transformer && transformers[0].response_transformer, 'model_transformer_missing_or_ambiguous');
        return {model: model, mapping: mapping, provider: provider};
    }
    function readOrigins() {
        var props = query('sys_properties', [['name', 'STARTSWITH', 'custom_llm.clone.map.']]), n, body;
        for (n = 0; n < props.length; n++) {
            try { body = JSON.parse(props[n].value); } catch (ignoreMalformedUnrelatedOrigin) { continue; }
            if (body && (body.table === 'sys_one_extend_capability_definition' || body.table === 'sys_generative_ai_config') && validId(body.source) && validId(body.target)) {
                var k = key(body.table, body.target);
                need(!origins[k], 'ambiguous_customer_origin:' + k);
                need(props[n].name === 'custom_llm.clone.map.' + body.source, 'customer_origin_name_mismatch:' + k);
                origins[k] = body;
            }
        }
    }
    function definitionMatches(d) { return d.api_type === 'sys_hub_flow' && d.api === profile.mapping.provider_implementation && d.connection === profile.mapping.connection; }
    function assertOwned(row, table, definition) {
        need(own(row, 'sys_policy') && row.sys_policy === '', 'protected_target:' + table + ':' + row.sys_id);
        need(row.sys_scope && row.sys_package && row.sys_scope === definition.sys_scope && row.sys_package === definition.sys_package && row.sys_domain === definition.sys_domain, 'target_ownership_mismatch:' + row.sys_id);
        var origin = origins[key(table, row.sys_id)];
        need(p.customerDefinitionIds.indexOf(definition.sys_id) >= 0 || origin && origin.capability === definition.capability && origin.definition === definition.sys_id && origin.providerFlow === profile.mapping.provider_implementation, 'customer_ownership_unproved:' + table + ':' + row.sys_id);
    }
    function planDefinition(d) {
        assertOwned(d, 'sys_one_extend_capability_definition', d);
        var selections = query('sys_one_extend_definition_config', [['definition', d.sys_id]]);
        need(selections.length === 1 && selections[0].capability === d.capability, 'definition_selection_missing_or_ambiguous:' + d.sys_id);
        if (!enabled(selections[0].active) && p.includeInactive !== true) { out.excluded.push({definitionId: d.sys_id, reason: 'inactive_definition_selection'}); return; }
        var configs = query('sys_generative_ai_config', [['definition', d.sys_id]]), planned = [], n;
        preserveGraph(d, configs);
        for (n = 0; n < configs.length; n++) {
            var c = configs[n];
            // includeInactive concerns the provider definition selection, never
            // retired/draft prompt alternatives or historical config versions.
            if (!enabled(c.active) || c.state !== 'published') { out.excluded.push({definitionId: d.sys_id, configId: c.sys_id, reason: 'inactive_or_unpublished_prompt'}); continue; }
            need(c.definition_table === 'sys_one_extend_capability_definition', 'wrong_prompt_definition_table:' + c.sys_id);
            assertOwned(c, 'sys_generative_ai_config', d);
            var bindings = query('sys_generative_ai_prompt_config', [['ai_config', c.sys_id]]);
            need(bindings.length === 1 && bindings[0].definition === d.sys_id, 'prompt_binding_missing_or_ambiguous:' + c.sys_id);
            checkHistory(c, d);
            var r = readRecord('sys_generative_ai_config', c.sys_id);
            planned.push({capabilityId: d.capability, definitionId: d.sys_id, configId: c.sys_id, bindingId: bindings[0].sys_id, scope: c.sys_scope, beforeModel: c.model, targetModel: profile.model.model, noOp: c.model === profile.model.model, requiresAdminMaintenance: !(r.canWrite() && r.getElement('model').canWrite())});
        }
        for (n = 0; n < planned.length; n++) out.targets.push(planned[n]);
    }
    function preserveGraph(d, configs) {
        var ids = [], validators = [], n;
        for (n = 0; n < configs.length; n++) ids.push(configs[n].sys_id);
        query('sys_one_extend_definition_config', [['capability', d.capability]]);
        query('sys_one_extend_definition_attribute', [['capability', d.capability]]);
        query('sys_generative_ai_prompt_config', [['definition', d.sys_id]]);
        validators = validators.concat(query('sys_generative_ai_request_validator', [['definition', d.sys_id]]));
        validators = validators.concat(query('sys_generative_ai_request_validator', [['document_id', d.sys_id], ['document_table', 'sys_one_extend_capability_definition']]));
        validators = validators.concat(query('sys_generative_ai_response_validator', [['definition', d.sys_id]]));
        if (ids.length) {
            query('sys_generative_ai_prompt_config', [['ai_config', 'IN', ids.join(',')]]);
            validators = validators.concat(query('sys_generative_ai_request_validator', [['document_id', 'IN', ids.join(',')], ['document_table', 'sys_generative_ai_config']]));
            validators = validators.concat(query('sys_generative_ai_response_validator', [['definition', 'IN', ids.join(',')], ['definition_table', 'sys_generative_ai_config']]));
        }
        for (n = 0; n < validators.length; n++) {
            var v = read('sys_generative_ai_validator', validators[n].validator);
            need(v.validator_script && v.validator_script.replace(/\s/g, ''), 'validator_script_unavailable:' + v.sys_id);
        }
    }
    function checkHistory(config, definition) {
        var cursor = config, seen = {}, depth = 0;
        while (true) {
            need(!seen[cursor.sys_id] && depth++ < 1000, 'history_cycle_or_depth:' + config.sys_id); seen[cursor.sys_id] = true;
            need(/^[1-9][0-9]*$/.test(cursor.version), 'history_invalid_version:' + cursor.sys_id);
            if (!cursor.parent) {
                need(cursor.version === '1', 'history_unanchored_version_requires_review:' + cursor.sys_id);
                break;
            }
            var parent = read('sys_generative_ai_config', cursor.parent, 'history_parent_unavailable');
            need(parent.definition === definition.sys_id && parent.definition_table === 'sys_one_extend_capability_definition', 'history_cross_definition:' + cursor.sys_id);
            need(parent.provider_company === config.provider_company, 'history_provider_ancestry_mismatch:' + cursor.sys_id);
            need(Number(parent.version) < Number(cursor.version), 'history_non_descending_version:' + cursor.sys_id);
            var origin = origins[key('sys_generative_ai_config', cursor.sys_id)], parentOrigin = origins[key('sys_generative_ai_config', parent.sys_id)];
            if (origin && parentOrigin) {
                var sourceRecord = open('sys_generative_ai_config');
                if (sourceRecord.get(origin.source) && sourceRecord.canRead()) {
                    var source = read('sys_generative_ai_config', origin.source);
                    need(!(source.version === cursor.version && source.state === cursor.state && source.parent === parentOrigin.source), 'copied_source_history_requires_review:' + cursor.sys_id);
                } else out.warnings.push({configId: cursor.sys_id, reason: 'mapped_source_ancestry_unavailable_for_comparison'});
            }
            if (parent.model !== cursor.model) out.warnings.push({configId: config.sys_id, ancestorId: parent.sys_id, reason: 'prior_target_model_assignment_retained'});
            cursor = parent;
        }
    }
    function copy(value) { var result = {}, k; for (k in value) if (own(value, k)) result[k] = value[k]; return result; }
    function preflightCapture() {
        if (!out.requiredScopes.length) return;
        originalSet = String(gs.getPreference('sys_update_set') || '');
        need(originalSet, 'original_update_set_required');
        need(!p.updateSetId || validId(p.updateSetId), 'invalid_update_set_id');
        var byScope = p.updateSetIdsByScope || {};
        need(typeof byScope === 'object' && Object.prototype.toString.call(byScope) !== '[object Array]', 'update_set_scope_map_must_be_object');
        for (var n = 0; n < out.requiredScopes.length; n++) {
            var scope = out.requiredScopes[n], setId = byScope[scope] || (out.requiredScopes.length === 1 ? p.updateSetId : '');
            need(validId(setId), 'existing_update_set_required_for_scope:' + scope);
            var header = read('sys_update_set', setId);
            need(header.application === scope && header.state === 'in progress', 'update_set_scope_or_state_mismatch:' + scope);
            sets[scope] = setId;
            captureStates[setId] = captureInventory(setId, scope);
        }
    }
    function selectSet(setId) {
        need(validId(setId), 'capture_update_set_missing');
        if (String(gs.getPreference('sys_update_set') || '') !== setId) {
            selectionChanged = true;
            new GlideUpdateSet().set(setId);
            need(String(gs.getPreference('sys_update_set') || '') === setId, 'update_set_selection_failed');
        }
    }
    function safePayload(payload) {
        var markup = payload.replace(/<!\[CDATA\[[\s\S]*?\]\]>/g, '').replace(/<!--[\s\S]*?-->/g, '');
        need(!/<!DOCTYPE|<!ENTITY|\baction\s*=\s*(["'])\s*delete(?:_multiple)?\s*\1|<\s*\/?\s*delete(?:_multiple)?\b/i.test(markup), 'delete_or_unsafe_capture_payload');
    }
    function captureInventory(setId, scope) {
        var r = open('sys_update_xml'), rows = {};
        r.addQuery('update_set', setId); r.query();
        while (r.next()) {
            var row = snapshot(r);
            need(row.application === scope && row.action === 'INSERT_OR_UPDATE', 'update_set_contains_delete_or_wrong_scope:' + setId);
            safePayload(row.payload);
            need(!rows[row.sys_id], 'duplicate_capture_identity'); rows[row.sys_id] = row;
        }
        return rows;
    }
    function assertCaptureStates() {
        var scope, setId, actual, expected, k;
        for (scope in sets) if (own(sets, scope)) {
            setId = sets[scope]; actual = captureInventory(setId, scope); expected = captureStates[setId];
            for (k in expected) if (own(expected, k)) need(actual[k] && same(actual[k], expected[k], false), 'update_set_capture_drift:' + k);
            for (k in actual) if (own(actual, k)) need(own(expected, k), 'unexpected_update_set_capture:' + k);
        }
    }
    function captureRecord(target) {
        need(String(gs.getPreference('sys_update_set') || '') === sets[target.scope], 'capture_selected_set_drift');
        var r = readRecord('sys_generative_ai_config', target.configId);
        new GlideUpdateManager2().saveRecord(r);
        var rows = captureInventory(sets[target.scope], target.scope), prior = captureStates[sets[target.scope]], found = null, k;
        var expectedName = guards[key('sys_generative_ai_config', target.configId)].sys_update_name || 'sys_generative_ai_config_' + target.configId;
        for (k in rows) if (own(rows, k)) {
            if (rows[k].name === expectedName) { need(!found, 'duplicate_target_capture:' + target.configId); found = rows[k]; }
            else need(prior[k] && same(rows[k], prior[k], false), 'unexpected_capture_write:' + k);
        }
        for (k in prior) if (own(prior, k)) need(rows[k], 'existing_capture_removed:' + k);
        need(found, 'native_capture_missing:' + target.configId);
        var doc = new XMLDocument2(); doc.parseXML(found.payload);
        var root = doc.getDocumentElement();
        need(root && String(root.getAttribute('table')) === 'sys_generative_ai_config', 'captured_record_table_mismatch');
        need(String(doc.getNodeText('//sys_generative_ai_config/sys_id') || '') === target.configId && String(doc.getNodeText('//sys_generative_ai_config/model') || '') === profile.model.model, 'captured_model_or_identity_mismatch:' + target.configId);
        verifyCaptureShape(found.payload, guards[key('sys_generative_ai_config', target.configId)]);
        var expected = guards[key('sys_generative_ai_config', target.configId)];
        for (k in expected) if (own(expected, k) && k !== 'request_tokens') need(String(doc.getNodeText('//sys_generative_ai_config/' + k) || '') === expected[k], 'captured_field_mismatch:' + target.configId + ':' + k);
        need(!captures[found.sys_id], 'capture_identity_reused_for_different_target');
        captures[found.sys_id] = target.configId;
        out.captureIds.push(found.sys_id);
        captureStates[sets[target.scope]] = rows;
    }
    function verifyCaptureShape(payload, expected) {
        var markup = payload.replace(/<!\[CDATA\[[\s\S]*?\]\]>/g, '').replace(/<!--[\s\S]*?-->/g, '');
        var tokens = markup.match(/<[^>]+>/g) || [], stack = [], rootSeen = false, recordSeen = false, fieldsSeen = {}, n;
        for (n = 0; n < tokens.length; n++) {
            var token = tokens[n];
            if (/^<\?xml\s[^?]*\?>$/.test(token)) continue;
            var match = /^<(\/?)([A-Za-z_][A-Za-z0-9_.:-]*)(?:\s[^<>]*?)?\s*(\/?)>$/.exec(token);
            need(match, 'invalid_capture_markup');
            var closing = match[1] === '/', tag = match[2], selfClosing = match[3] === '/', depth = stack.length;
            if (closing) { need(!selfClosing && stack.pop() === tag, 'invalid_capture_nesting'); continue; }
            if (depth === 0) { need(!rootSeen && tag === 'record_update', 'extra_capture_root'); rootSeen = true; }
            else if (depth === 1) {
                need(!recordSeen && tag === 'sys_generative_ai_config', 'extra_capture_record'); recordSeen = true;
                need((token.match(/\baction\s*=/g) || []).length === 1 && /\saction\s*=\s*(["'])INSERT_OR_UPDATE\1(?:\s|\/?>)/.test(token), 'capture_record_action');
            } else if (depth === 2) {
                need(own(expected, tag) && !fieldsSeen[tag] && !/\baction\s*=/.test(token), 'unexpected_capture_field:' + tag); fieldsSeen[tag] = true;
            } else need(false, 'nested_capture_field');
            if (!selfClosing) stack.push(tag);
        }
        need(rootSeen && recordSeen && stack.length === 0, 'incomplete_capture_record');
    }
    function same(actual, expected, ignoreRevision) {
        var k;
        for (k in expected) if (own(expected, k) && !(ignoreRevision && revisionFields[k]) && (!own(actual, k) || actual[k] !== expected[k])) return false;
        for (k in actual) if (own(actual, k) && !(ignoreRevision && revisionFields[k]) && !own(expected, k)) return false;
        return true;
    }
    function assertFresh() {
        var k, split, n, inv, r, ids;
        for (k in discoveryGuards) if (own(discoveryGuards, k)) {
            var discovered = discoveryGuards[k];
            need(same(snapshotFields(readRecord(discovered.table, discovered.id), discovered.fields), discovered.values, false), 'definition_identity_drift:' + k);
        }
        for (k in guards) if (own(guards, k)) {
            split = k.indexOf(':');
            need(same(snapshot(readRecord(k.substring(0, split), k.substring(split + 1))), guards[k], false), 'snapshot_drift:' + k);
        }
        for (n = 0; n < inventories.length; n++) {
            inv = inventories[n]; r = open(inv.table);
            for (var c = 0; c < inv.conditions.length; c++) {
                var condition = inv.conditions[c];
                if (condition.length === 3) r.addQuery(condition[0], condition[1], condition[2]); else r.addQuery(condition[0], condition[1]);
            }
            r.query(); ids = [];
            while (r.next()) { need(r.canRead(), 'query_read_denied:' + inv.table); ids.push(String(r.getUniqueValue())); }
            ids.sort(); need(ids.join(',') === inv.ids, 'inventory_drift:' + inv.table);
        }
    }
})();
