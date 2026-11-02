'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {test} = require('node:test');

const scriptPath = path.join(__dirname, 'SwitchCapabilityModels.fix.js');
const id = n => n.toString(16).padStart(32, '0');
const ids = {cap: id(1), cap2: id(2), def: id(11), def2: id(12), config: id(21), config2: id(22),
    binding: id(31), binding2: id(32), selection: id(41), selection2: id(42), model: id(51),
    mapping: id(61), provider: id(71), flow: id(81), alias: id(91), transformer: id(101), updateSet: id(121), originalSet: id(122)};
const clone = value => JSON.parse(JSON.stringify(value));
function metadata(sys_id, values = {}) {
    return {sys_id, sys_mod_count: '0', sys_scope: 'global', sys_package: 'global', sys_policy: '',
        sys_domain: 'global', sys_created_by: 'admin', sys_updated_by: 'admin', sys_updated_on: '2026-11-02 00:00:00', ...values};
}
function database() {
    return {
        sys_properties: [metadata(id(111), {name: 'custom_llm.clone.map.' + id(501), value: JSON.stringify({table: 'sys_one_extend_capability_definition', source: id(501), target: ids.def, capability: ids.cap, definition: ids.def, providerFlow: ids.flow})}),
            metadata(id(112), {name: 'custom_llm.clone.map.' + id(502), value: JSON.stringify({table: 'sys_generative_ai_config', source: id(502), target: ids.config, capability: ids.cap, definition: ids.def, providerFlow: ids.flow})})],
        sys_one_extend_capability: [metadata(ids.cap, {name: 'VA Input'}), metadata(ids.cap2, {name: 'Second skill'})],
        sys_gen_ai_provider: [metadata(ids.provider, {gen_ai_provider: 'Custom LLM Provider'})],
        sys_generative_ai_provider_mapping: [metadata(ids.mapping, {gen_ai_provider: ids.provider, provider: 'Custom LLM', provider_api: 'custom_api', active: '1', provider_implementation_document: 'sys_hub_flow', provider_implementation: ids.flow, connection: ids.alias})],
        sys_generative_ai_model_config: [metadata(ids.model, {model: 'halogen-v2', provider: ids.mapping, active: '1', lifecycle_state: 'active', usage_mode: '', connection: ids.alias})],
        sys_generative_ai_custom_llm_transformer: [metadata(ids.transformer, {model: ids.model, request_transformer: 'request();', response_transformer: 'response();'})],
        sys_hub_flow: [metadata(ids.flow, {name: 'Custom LLM request'})],
        sys_alias: [metadata(ids.alias, {name: 'Local model connection'})],
        sys_update_set: [metadata(ids.updateSet, {name: 'Model maintenance', application: 'global', state: 'in progress'})],
        sys_update_xml: [],
        sys_one_extend_definition_attribute: [metadata(id(301), {capability: ids.cap, definition: ids.def, name: 'input', schema: 'preserve schema'})],
        sys_generative_ai_request_validator: [metadata(id(302), {definition: ids.def, document_id: ids.def, document_table: 'sys_one_extend_capability_definition', validator: id(304)})],
        sys_generative_ai_response_validator: [metadata(id(303), {definition: ids.def, definition_table: 'sys_one_extend_capability_definition', validator: id(304)})],
        sys_generative_ai_validator: [metadata(id(304), {name: 'Contract validation', validator_script: 'return true;'})],
        sys_one_extend_capability_definition: [metadata(ids.def, {capability: ids.cap, api_type: 'sys_hub_flow', api: ids.flow, connection: ids.alias})],
        sys_one_extend_definition_config: [metadata(ids.selection, {capability: ids.cap, definition: ids.def, active: '1', default: '1'})],
        sys_generative_ai_config: [metadata(ids.config, {definition: ids.def, definition_table: 'sys_one_extend_capability_definition', active: '1', state: 'published', model: 'Gemma 4 26B-A4B', prompt: 'Keep exact {{input}}', parent: '', version: '1', provider_company: '', request_tokens: '42', structured_output_schema: '{"type":"object"}'})],
        sys_generative_ai_prompt_config: [metadata(ids.binding, {definition: ids.def, ai_config: ids.config, is_default: '1', filter_properties: '{"condition":"keep exact"}', filter_type: '', order: '100'})]
    };
}
function run(parameters = {}, change, controls = {}) {
    const db = controls.database || database();
    if (change) change(db);
    const before = clone(db), writes = [], ordinary = [], logs = [];
    let reads = 0, currentSet = controls.initialSet || ids.originalSet;
    const selectedSets = [], captures = [];
    function recordClass(secure) {
        return class NativeRecord {
            constructor(table) { this.table = table; this.conditions = []; this.row = null; this.rows = []; this.index = 0; if (!secure) ordinary.push(table); }
            isValid() { return Object.hasOwn(db, this.table); }
            getTableName() { return this.table; }
            getRecordClassName() { return this.table; }
            getUniqueValue() { return this.row?.sys_id; }
            get(key) { reads++; if (controls.onRead) controls.onRead({reads, table: this.table, key, db, writes}); this.row = clone((db[this.table] || []).find(r => r.sys_id === key) || null); return !!this.row; }
            isValidField(field) { return !!this.row && Object.hasOwn(this.row, field); }
            getValue(field) { return this.row[field] ?? null; }
            canRead() { return !controls.unreadableRecords?.includes(this.row.sys_id); }
            canWrite() { return !(controls.deniedWrite || controls.deniedWriteIds?.includes(this.row.sys_id)); }
            getElement(field) { const r = this; return {getName() { return field; }, canRead() { return !controls.unreadableFields?.includes(field) && !controls.unreadableById?.[r.row.sys_id]?.includes(field); }, canWrite() { return r.canWrite(); }, getED() { return {getInternalType() { return ['active', 'default', 'is_default'].includes(field) ? 'boolean' : 'string'; }}; }}; }
            getElements() { const fields = Object.keys(this.row); return {size() { return fields.length; }, get: index => this.getElement(fields[index])}; }
            addQuery(field, operator, value) { if (arguments.length === 2) { value = operator; operator = '='; } this.conditions.push({field, operator, value}); }
            setLimit(limit) { this.limit = limit; }
            query() { this.rows = (db[this.table] || []).filter(row => this.conditions.every(q => q.operator === 'IN' ? q.value.split(',').includes(row[q.field]) : q.operator === 'STARTSWITH' ? String(row[q.field]).startsWith(q.value) : String(row[q.field]) === String(q.value))); this.rows = this.rows.slice(0, this.limit); this.index = 0; }
            next() { if (this.index >= this.rows.length) return false; this.row = clone(this.rows[this.index++]); return true; }
            setValue(field, value) { this.row[field] = String(value); }
            update() {
                assert.equal(this.table, 'sys_generative_ai_config', 'only existing prompt model assignments may be written');
                if (controls.failWriteNumber === writes.length + 1) return null;
                const current = db[this.table].find(r => r.sys_id === this.row.sys_id);
                const changed = Object.keys(this.row).filter(k => this.row[k] !== current[k]);
                writes.push({table: this.table, id: this.row.sys_id, changed, secure});
                Object.assign(current, this.row, {sys_mod_count: String(Number(current.sys_mod_count) + 1), request_tokens: '43'});
                if (controls.afterWrite) controls.afterWrite({db, current, writes});
                return current.sys_id;
            }
        };
    }
    const context = vm.createContext({GlideRecordSecure: recordClass(true), GlideRecord: recordClass(false),
        GlideUpdateSet: class { set(setId) { selectedSets.push(setId); if (controls.restoreFailure && setId === ids.originalSet) return; currentSet = setId; } },
        GlideUpdateManager2: class { saveRecord(record) {
            captures.push(record.getUniqueValue());
            if (controls.captureFailure) return;
            const fields = Object.keys(record.row).map(field => {
                let value = record.getValue(field);
                if (['active', 'default', 'is_default'].includes(field)) value = value === '1' || value === 'true' ? 'true' : 'false';
                if (field === 'model' && controls.wrongCapturedModel || field === 'prompt' && controls.wrongCapturedPrompt) value = 'wrong';
                return '<' + field + '><![CDATA[' + value + ']]></' + field + '>';
            }).join('');
            const extra = controls.extraCaptureRecord ? '<sys_user action="INSERT_OR_UPDATE"><sys_id>' + id(999) + '</sys_id></sys_user>' : '';
            const capture = {sys_id: id(700 + captures.length), update_set: currentSet, name: 'sys_generative_ai_config_' + record.getUniqueValue(), application: record.getValue('sys_scope'), action: controls.deleteCapture ? 'DELETE' : 'INSERT_OR_UPDATE', payload: '<record_update table="sys_generative_ai_config"><sys_generative_ai_config action="INSERT_OR_UPDATE">' + fields + '</sys_generative_ai_config>' + extra + '</record_update>'};
            const existing = db.sys_update_xml.find(r => r.update_set === currentSet && r.name === capture.name);
            if (existing) Object.assign(existing, capture, {sys_id: existing.sys_id}); else db.sys_update_xml.push(capture);
            if (controls.captureSelectDrift) currentSet = id(779);
        } },
        XMLDocument2: class { parseXML(xml) { this.xml = xml; } getDocumentElement() { return {getAttribute: name => /<record_update table="([^"]+)">/.exec(this.xml)?.[1]}; } getNodeText(xpath) { const tag = xpath.split('/').at(-1); return (new RegExp('<' + tag + '>([\\s\\S]*?)</' + tag + '>').exec(this.xml)?.[1] || '').replace(/^<!\[CDATA\[/, '').replace(/\]\]>$/, ''); } },
        gs: {hasRole(role) { return role === 'admin' && controls.admin !== false; }, info(message) { logs.push(message); }, getPreference() { return currentSet; }}
    });
    const source = fs.existsSync(scriptPath) ? fs.readFileSync(scriptPath, 'utf8') : '';
    vm.runInContext(source.replace(/var PARAMETERS = \{[\s\S]*?\n\};/, 'var PARAMETERS = ' + JSON.stringify({capabilityIds: [ids.cap], targetModel: 'halogen-v2', updateSetId: ids.updateSet, ...parameters}) + ';'), context, {timeout: 1000});
    const resultLog = logs.find(line => line.startsWith('[CAPABILITY_MODEL_SWITCH] '));
    return {result: resultLog ? JSON.parse(resultLog.slice('[CAPABILITY_MODEL_SWITCH] '.length)) : null, db, before, writes, ordinary, captures, currentSet, selectedSets};
}
function secondPrompt(db) {
    db.sys_properties.push(metadata(id(113), {name: 'custom_llm.clone.map.' + id(503), value: JSON.stringify({table: 'sys_one_extend_capability_definition', source: id(503), target: ids.def2, capability: ids.cap2, definition: ids.def2, providerFlow: ids.flow})}), metadata(id(114), {name: 'custom_llm.clone.map.' + id(504), value: JSON.stringify({table: 'sys_generative_ai_config', source: id(504), target: ids.config2, capability: ids.cap2, definition: ids.def2, providerFlow: ids.flow})}));
    db.sys_one_extend_capability_definition.push(metadata(ids.def2, {capability: ids.cap2, api_type: 'sys_hub_flow', api: ids.flow, connection: ids.alias}));
    db.sys_one_extend_definition_config.push(metadata(ids.selection2, {capability: ids.cap2, definition: ids.def2, active: '1', default: '0'}));
    db.sys_generative_ai_config.push(metadata(ids.config2, {...db.sys_generative_ai_config[0], sys_id: ids.config2, definition: ids.def2}));
    db.sys_generative_ai_prompt_config.push(metadata(ids.binding2, {definition: ids.def2, ai_config: ids.config2, is_default: '1', filter_properties: '', filter_type: '', order: '100'}));
}

test('default preview plans an exact model change without any native writes', () => {
    const actual = run();
    assert.equal(actual.result?.status, 'preview');
    assert.equal(actual.result.targets[0].beforeModel, 'Gemma 4 26B-A4B');
    assert.equal(actual.result.targets[0].targetModel, 'halogen-v2');
    assert.equal(actual.writes.length, 0);
    assert.equal(actual.ordinary.length, 0);
    assert.deepEqual(actual.db, actual.before);
});
test('empty selection does not accidentally mean all capabilities', () => {
    const actual = run({apply: true, capabilityIds: []});
    assert.equal(actual.result?.status, 'aborted');
    assert.match(actual.result.error, /explicit_selection_required/);
    assert.equal(actual.writes.length, 0);
});
test('secure apply writes only the model and preserves prompt, selection, filters and old alternatives', () => {
    const actual = run({apply: true}, db => { const old = clone(db.sys_generative_ai_config[0]); old.sys_id = id(201); old.active = '0'; old.state = 'retired'; db.sys_generative_ai_config.push(old); });
    assert.equal(actual.result?.status, 'applied');
    assert.deepEqual(actual.writes, [{table: 'sys_generative_ai_config', id: ids.config, changed: ['model'], secure: true}]);
    assert.equal(actual.db.sys_generative_ai_config[0].model, 'halogen-v2');
    assert.equal(actual.db.sys_generative_ai_config[1].model, 'Gemma 4 26B-A4B');
    for (const table of Object.keys(actual.db).filter(t => !['sys_generative_ai_config', 'sys_update_xml'].includes(t))) assert.deepEqual(actual.db[table], actual.before[table]);
});
test('denied native write ACL remains a useful preview and requires explicit maintenance to apply', () => {
    const preview = run({}, null, {deniedWrite: true});
    assert.equal(preview.result?.status, 'preview');
    assert.equal(preview.result.targets[0].requiresAdminMaintenance, true);
    const denied = run({apply: true}, null, {deniedWrite: true});
    assert.equal(denied.result?.status, 'aborted');
    assert.match(denied.result.error, /admin_maintenance_required/);
    assert.equal(denied.ordinary.length, 0);
    const permitted = run({apply: true, allowAdminMaintenance: true}, null, {deniedWrite: true});
    assert.equal(permitted.result?.status, 'applied');
    assert.equal(permitted.writes[0].secure, false);
});
test('copied source parent identity is blocked without rewriting genuine history', () => {
    const actual = run({apply: true}, db => { db.sys_generative_ai_config[0].parent = id(999); db.sys_generative_ai_config[0].version = '4'; });
    assert.equal(actual.result?.status, 'aborted');
    assert.match(actual.result.error, /history_parent_unavailable/);
    assert.equal(actual.writes.length, 0);
    assert.deepEqual(actual.db, actual.before);
});
test('whole-selection preflight rejects an unknown capability before the first write', () => {
    const actual = run({apply: true, capabilityIds: [ids.cap, id(999)]});
    assert.equal(actual.result?.status, 'aborted');
    assert.match(actual.result.error, /capability_unavailable/);
    assert.equal(actual.writes.length, 0);
});
test('repeated apply is a no-op with no duplicate captures or update-set changes', () => {
    const first = run({apply: true});
    const second = run({apply: true}, null, {database: first.db});
    assert.equal(second.result.status, 'no_op');
    assert.equal(second.writes.length, 0);
    assert.equal(second.captures.length, 0);
    assert.equal(second.selectedSets.length, 0);
});
test('explicit all selection switches two capabilities and selected mode switches only its own identity', () => {
    const all = run({apply: true, allCapabilities: true, capabilityIds: []}, secondPrompt);
    assert.equal(all.result.status, 'applied');
    assert.deepEqual(all.writes.map(w => w.id), [ids.config, ids.config2]);
    const selected = run({apply: true}, secondPrompt);
    assert.deepEqual(selected.writes.map(w => w.id), [ids.config]);
    assert.equal(selected.db.sys_generative_ai_config[1].model, 'Gemma 4 26B-A4B');
});
for (const parameters of [{capabilityIds: [ids.cap, ids.cap]}, {capabilityIds: ['not-an-id']}, {allCapabilities: true}, {capabilityIds: 'all'}]) {
    test('rejects invalid or ambiguous explicit selection ' + JSON.stringify(parameters), () => {
        const actual = run({apply: true, ...parameters});
        assert.equal(actual.result.status, 'aborted'); assert.equal(actual.writes.length, 0);
    });
}
for (const [label, change, pattern] of [
    ['missing model', db => db.sys_generative_ai_model_config.splice(0), /model_registration_missing/],
    ['duplicate model labels', db => db.sys_generative_ai_model_config.push({...db.sys_generative_ai_model_config[0], sys_id: id(52)}), /ambiguous_model/],
    ['inactive model', db => { db.sys_generative_ai_model_config[0].active = '0'; }, /ineligible/],
    ['retired lifecycle', db => { db.sys_generative_ai_model_config[0].lifecycle_state = 'retired'; }, /ineligible/],
    ['restricted usage', db => { db.sys_generative_ai_model_config[0].usage_mode = 'restricted'; }, /ineligible/],
    ['wrong provider API', db => { db.sys_generative_ai_provider_mapping[0].provider_api = 'now_llm'; }, /unsupported_model_provider/],
    ['wrong provider identity', db => { db.sys_gen_ai_provider[0].gen_ai_provider = 'Now LLM Service'; }, /wrong_model_provider_identity/],
    ['missing transformer', db => db.sys_generative_ai_custom_llm_transformer.splice(0), /transformer_missing/],
    ['protected prompt', db => { db.sys_generative_ai_config[0].sys_policy = 'protected'; }, /protected_target/],
    ['unproved customer origin', db => db.sys_properties.splice(0), /ownership_unproved/]
]) {
    test('preflight rejects ' + label + ' before writes', () => {
        const actual = run({apply: true}, change);
        assert.equal(actual.result.status, 'aborted'); assert.match(actual.result.error, pattern); assert.equal(actual.writes.length, 0);
    });
}
test('explicit model registration resolves duplicate names across implementations but cannot bypass a wrong provider mapping', () => {
    const change = db => {
        db.sys_generative_ai_model_config.push({...db.sys_generative_ai_model_config[0], sys_id: id(52), provider: id(62)});
        db.sys_generative_ai_provider_mapping.push({...db.sys_generative_ai_provider_mapping[0], sys_id: id(62), provider_implementation: id(82)});
    };
    assert.equal(run({modelConfigId: ids.model, providerMappingId: ids.mapping}, change).result.status, 'preview');
    const wrong = run({apply: true, modelConfigId: ids.model, providerMappingId: id(999)}, change);
    assert.equal(wrong.result.status, 'aborted'); assert.equal(wrong.writes.length, 0);
});
test('provider identity resolves same-name models registered by different implementations', () => {
    const actual = run({providerId: ids.provider}, db => {
        db.sys_generative_ai_model_config.push({...db.sys_generative_ai_model_config[0], sys_id: id(52), provider: id(62)});
        db.sys_generative_ai_provider_mapping.push({...db.sys_generative_ai_provider_mapping[0], sys_id: id(62), gen_ai_provider: id(72), provider_implementation: id(82)});
        db.sys_gen_ai_provider.push({...db.sys_gen_ai_provider[0], sys_id: id(72)});
    });
    assert.equal(actual.result.status, 'preview'); assert.equal(actual.result.model.registrationId, ids.model);
});

for (const selectors of [{modelConfigId: ids.model}, {providerMappingId: ids.mapping}, {providerId: ids.provider}]) {
    test('explicit selection cannot hide a same-string registration under the same native implementation ' + JSON.stringify(selectors), () => {
        const actual = run({apply: true, ...selectors}, db => {
            db.sys_generative_ai_model_config.push({...db.sys_generative_ai_model_config[0], sys_id: id(52), provider: id(62)});
            db.sys_generative_ai_provider_mapping.push({...db.sys_generative_ai_provider_mapping[0], sys_id: id(62), gen_ai_provider: id(72)});
            db.sys_gen_ai_provider.push({...db.sys_gen_ai_provider[0], sys_id: id(72)});
        });
        assert.equal(actual.result.status, 'aborted');
        assert.match(actual.result.error, /ambiguous_native_model_string_within_implementation/);
        assert.equal(actual.writes.length, 0); assert.equal(actual.selectedSets.length, 0);
        assert.deepEqual(actual.db, actual.before);
    });
}

test('unreadable peer model mapping prevents proving native string uniqueness before writes', () => {
    const actual = run({apply: true, modelConfigId: ids.model}, db => {
        db.sys_generative_ai_model_config.push({...db.sys_generative_ai_model_config[0], sys_id: id(52), provider: id(62)});
        db.sys_generative_ai_provider_mapping.push({...db.sys_generative_ai_provider_mapping[0], sys_id: id(62), provider_implementation: id(82)});
    }, {unreadableRecords: [id(62)]});
    assert.equal(actual.result.status, 'aborted');
    assert.match(actual.result.error, /peer_model_provider_unavailable/);
    assert.equal(actual.writes.length, 0); assert.equal(actual.selectedSets.length, 0);
    assert.deepEqual(actual.db, actual.before);
});

for (const [label, peer, mapping, expected] of [
    ['missing provider reference', {provider: ''}, null, /peer_model_provider_unavailable/],
    ['missing provider mapping', {provider: id(62)}, null, /peer_model_provider_unavailable/],
    ['missing native implementation', {provider: id(62)}, {provider_implementation: ''}, /peer_model_implementation_unavailable/]
]) {
    test('unclear peer registration fails closed: ' + label, () => {
        const actual = run({apply: true, modelConfigId: ids.model}, db => {
            db.sys_generative_ai_model_config.push({...db.sys_generative_ai_model_config[0], sys_id: id(52), ...peer});
            if (mapping) db.sys_generative_ai_provider_mapping.push({...db.sys_generative_ai_provider_mapping[0], sys_id: id(62), ...mapping});
        });
        assert.equal(actual.result.status, 'aborted'); assert.match(actual.result.error, expected);
        assert.equal(actual.writes.length, 0); assert.equal(actual.selectedSets.length, 0);
        assert.deepEqual(actual.db, actual.before);
    });
}
test('reviewed explicit customer definition permits unmapped local prompts without using creator as proof', () => {
    const actual = run({apply: true, customerDefinitionIds: [ids.def]}, db => { db.sys_properties.splice(0); db.sys_generative_ai_config[0].sys_created_by = 'system'; });
    assert.equal(actual.result.status, 'applied');
});
test('maintenance requires admin even when ownership is proven', () => {
    const actual = run({apply: true, allowAdminMaintenance: true}, null, {admin: false, deniedWrite: true});
    assert.equal(actual.result.status, 'aborted'); assert.match(actual.result.error, /admin_required/); assert.equal(actual.writes.length, 0);
});
test('includeInactive includes disabled definition selections while always retaining inactive prompt alternatives', () => {
    const change = db => { db.sys_one_extend_definition_config[0].active = '0'; };
    assert.equal(run({apply: true}, change).writes.length, 0);
    assert.equal(run({apply: true, includeInactive: true}, change).writes.length, 1);
    const inactive = run({apply: true, includeInactive: true}, db => { db.sys_generative_ai_config[0].active = '0'; });
    assert.equal(inactive.writes.length, 0);
});
test('all mode reports and excludes protected customer definitions', () => {
    const actual = run({apply: true, allCapabilities: true, capabilityIds: []}, db => { secondPrompt(db); db.sys_generative_ai_config[1].sys_policy = 'protected'; });
    assert.equal(actual.result.status, 'applied'); assert.deepEqual(actual.writes.map(w => w.id), [ids.config]);
    assert.ok(actual.result.excluded.some(e => /protected_target/.test(e.reason)));
});
test('unreadable fields prevent incomplete snapshots and all writes', () => {
    const actual = run({apply: true}, null, {unreadableFields: ['prompt']});
    assert.equal(actual.result.status, 'aborted'); assert.match(actual.result.error, /field_read_denied/); assert.equal(actual.writes.length, 0);
});
test('snapshot drift before the first update prevents any writes', () => {
    let targetReads = 0;
    const actual = run({apply: true}, null, {onRead({table, db}) { if (table === 'sys_generative_ai_config' && ++targetReads === 2) db.sys_generative_ai_config[0].prompt = 'someone edited this'; }});
    assert.equal(actual.result.status, 'aborted'); assert.match(actual.result.error, /drift/); assert.equal(actual.writes.length, 0);
});
test('native failure after one successful update is reported as partial without touching the remaining target', () => {
    const actual = run({apply: true, capabilityIds: [ids.cap, ids.cap2]}, secondPrompt, {failWriteNumber: 2});
    assert.equal(actual.result.status, 'partial_or_uncertain'); assert.equal(actual.writes.length, 1);
    assert.deepEqual(actual.result.completed, [ids.config]); assert.equal(actual.db.sys_generative_ai_config[1].model, 'Gemma 4 26B-A4B');
});
test('a business rule modifying a validator is detected after the first model assignment', () => {
    const actual = run({apply: true}, null, {afterWrite({db}) { db.sys_generative_ai_validator[0].validator_script = 'changed();'; }});
    assert.equal(actual.result.status, 'partial_or_uncertain'); assert.match(actual.result.error, /snapshot_drift/);
});
test('a business rule changing another provider default is detected without repairing that selection', () => {
    const actual = run({apply: true}, db => {
        db.sys_one_extend_definition_config.push(metadata(id(499), {capability: ids.cap, definition: id(498), active: '1', default: '0'}));
    }, {afterWrite({db}) { db.sys_one_extend_definition_config[1].default = '1'; }});
    assert.equal(actual.result.status, 'partial_or_uncertain'); assert.match(actual.result.error, /snapshot_drift/);
});
test('native capture uses the compatible existing set and restores the prior selection', () => {
    const actual = run({apply: true});
    assert.equal(actual.result.status, 'applied'); assert.deepEqual(actual.captures, [ids.config]);
    assert.equal(actual.currentSet, ids.originalSet); assert.equal(actual.db.sys_update_set.length, 1);
    assert.equal(actual.db.sys_update_xml[0].application, 'global'); assert.equal(actual.db.sys_update_xml[0].action, 'INSERT_OR_UPDATE');
});
test('preview reports required ownership scopes without selecting or creating an update set', () => {
    const actual = run({updateSetId: ''});
    assert.deepEqual(actual.result.requiredScopes, ['global']); assert.equal(actual.selectedSets.length, 0); assert.equal(actual.captures.length, 0);
});
for (const [label, change, parameters] of [
    ['missing update-set choice', null, {updateSetId: ''}],
    ['completed update set', db => { db.sys_update_set[0].state = 'complete'; }, {}],
    ['wrong application', db => { db.sys_update_set[0].application = id(777); }, {}],
    ['delete already in update set', db => db.sys_update_xml.push({sys_id: id(888), update_set: ids.updateSet, name: 'other', application: 'global', action: 'DELETE', payload: '<record_update/>'}), {}]
]) {
    test('apply preflight rejects ' + label + ' before any writes', () => {
        const actual = run({apply: true, ...parameters}, change);
        assert.equal(actual.result.status, 'aborted'); assert.equal(actual.writes.length, 0); assert.equal(actual.selectedSets.length, 0);
    });
}
for (const controls of [{captureFailure: true}, {deleteCapture: true}, {wrongCapturedModel: true}, {restoreFailure: true}]) {
    test('capture or restoration failure remains partial and never claims success ' + JSON.stringify(controls), () => {
        const actual = run({apply: true}, null, controls);
        assert.equal(actual.result.status, 'partial_or_uncertain'); assert.equal(actual.writes.length, 1);
        if (!controls.restoreFailure) assert.equal(actual.currentSet, ids.originalSet);
    });
}
test('genuine target history retains its prior model and every historical field', () => {
    const actual = run({apply: true}, db => {
        const ancestor = clone(db.sys_generative_ai_config[0]); ancestor.sys_id = id(401); ancestor.active = '0'; ancestor.state = 'retired';
        db.sys_generative_ai_config.push(ancestor); db.sys_generative_ai_config[0].parent = ancestor.sys_id; db.sys_generative_ai_config[0].version = '2';
    });
    assert.equal(actual.result.status, 'applied');
    assert.equal(actual.db.sys_generative_ai_config[0].parent, id(401)); assert.equal(actual.db.sys_generative_ai_config[0].version, '2');
    assert.deepEqual(actual.db.sys_generative_ai_config[1], actual.before.sys_generative_ai_config[1]);
});
for (const [label, change, expected] of [
    ['cross-definition ancestry', db => { const ancestor = clone(db.sys_generative_ai_config[0]); ancestor.sys_id = id(401); ancestor.definition = ids.def2; ancestor.active = '0'; db.sys_generative_ai_config.push(ancestor); db.sys_generative_ai_config[0].parent = id(401); db.sys_generative_ai_config[0].version = '2'; }, /history_cross_definition/],
    ['unanchored source version', db => { db.sys_generative_ai_config[0].version = '4'; }, /history_unanchored_version/],
    ['cyclic ancestry', db => { db.sys_generative_ai_config[0].parent = ids.config; }, /history_non_descending_version|history_cycle/],
    ['copied remapped source chronology', db => {
        const ancestor = clone(db.sys_generative_ai_config[0]); ancestor.sys_id = id(401); ancestor.active = '0'; ancestor.state = 'retired';
        db.sys_generative_ai_config.push(ancestor); db.sys_generative_ai_config[0].parent = id(401); db.sys_generative_ai_config[0].version = '2';
        db.sys_properties.push(metadata(id(115), {name: 'custom_llm.clone.map.' + id(503), value: JSON.stringify({table: 'sys_generative_ai_config', source: id(503), target: id(401), capability: ids.cap, definition: ids.def, providerFlow: ids.flow})}));
        db.sys_generative_ai_config.push(metadata(id(502), {...db.sys_generative_ai_config[0], sys_id: id(502), definition: id(900), parent: id(503)}));
    }, /copied_source_history_requires_review/]
]) {
    test('incompatible ' + label + ' is blocked without editing history', () => {
        const actual = run({apply: true}, change);
        assert.equal(actual.result.status, 'aborted'); assert.match(actual.result.error, expected); assert.equal(actual.writes.length, 0);
    });
}
test('all scopes must have compatible capture headers before any model change', () => {
    const scope = id(550), scopedSet = id(551);
    const change = db => {
        secondPrompt(db); db.sys_one_extend_capability_definition[1].sys_scope = scope; db.sys_generative_ai_config[1].sys_scope = scope;
        db.sys_one_extend_capability_definition[1].sys_package = scope; db.sys_generative_ai_config[1].sys_package = scope;
        db.sys_update_set.push(metadata(scopedSet, {name: 'Scoped maintenance', application: scope, state: 'in progress'}));
    };
    const denied = run({apply: true, allCapabilities: true, capabilityIds: []}, change);
    assert.equal(denied.result.status, 'aborted'); assert.equal(denied.writes.length, 0);
    const actual = run({apply: true, allCapabilities: true, capabilityIds: [], updateSetIdsByScope: {global: ids.updateSet, [scope]: scopedSet}}, change);
    assert.equal(actual.result.status, 'applied'); assert.equal(actual.currentSet, ids.originalSet);
    assert.deepEqual(actual.db.sys_update_xml.map(r => r.application), ['global', scope]);
});
for (const controls of [{wrongCapturedPrompt: true}, {extraCaptureRecord: true}]) {
    test('capture cannot silently transport a changed prompt or extra record ' + JSON.stringify(controls), () => {
        const actual = run({apply: true}, null, controls);
        assert.equal(actual.result.status, 'partial_or_uncertain'); assert.equal(actual.currentSet, ids.originalSet);
    });
}
for (const parameters of [{}, {allCapabilities: true, capabilityIds: []}]) {
    test('protected vendor scripts do not block qualified custom discovery ' + JSON.stringify(parameters), () => {
        const actual = run(parameters, db => {
            db.sys_one_extend_capability_definition.push(metadata(id(650), {capability: ids.cap, api_type: 'sys_hub_flow', api: id(651), connection: ids.alias, sys_policy: 'protected', preprocessor: 'vendor_script();'}));
        }, {unreadableById: {[id(650)]: ['preprocessor']}});
        assert.equal(actual.result.status, 'preview'); assert.deepEqual(actual.result.targets.map(t => t.configId), [ids.config]);
        assert.ok(actual.result.excluded.some(t => t.definitionId === id(650)));
    });
}
test('restores original set after native preference drift even when target was initially selected', () => {
    const actual = run({apply: true}, null, {initialSet: ids.updateSet, captureSelectDrift: true});
    assert.equal(actual.result.status, 'applied'); assert.equal(actual.currentSet, ids.updateSet);
});
test('normal native calculated request_tokens change is accepted without writing that field', () => {
    const actual = run({apply: true});
    assert.equal(actual.result.status, 'applied');
    assert.equal(actual.before.sys_generative_ai_config[0].request_tokens, '42');
    assert.equal(actual.db.sys_generative_ai_config[0].request_tokens, '43');
    assert.deepEqual(actual.writes[0].changed, ['model']);
    const unrelated = run({apply: true}, null, {afterWrite({current}) { current.prompt = 'unapproved native side effect'; }});
    assert.equal(unrelated.result.status, 'partial_or_uncertain'); assert.match(unrelated.result.error, /native_readback_contract_changed/);
});
