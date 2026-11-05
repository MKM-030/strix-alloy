'use strict';

const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const CAP = 'aca5634f4312121038520464dbb8f236';
const SERVICE = '8aa131d793f787105c8132d47aba1095';
const DEF = 'e0f1b0cb9373cf14e7f2b9fa6aba1073';
const PROMPT = 'e8f1b0cb9373cf14e7f2b9fa6aba1074';
const MODEL = 'ff74fcef93a70350e7f2b9fa6aba10ea';
const MAP = '07ca9d94c3550210b0939bc8a840ddeb';
const IMPL = 'af9702d0c3110210b0939bc8a840dd2c';
const PROVIDER = '1e163d62ff1a2210ed26ffffffffffca';
const SOURCE = fs.readFileSync(path.join(__dirname, 'LocalLLMVoiceAssistantSettings.js'), 'utf8');

function fixture(change = () => {}, denied = '') {
    const db = {
        sys_one_extend_capability: [{sys_id: CAP, active: 'true', sys_mod_count: '2'}],
        sys_one_extend_definition_config: [{sys_id: '2cf1b0cb9373cf14e7f2b9fa6aba1073',
            capability: CAP, definition: DEF, active: 'true', default: 'true', sys_mod_count: '3'}],
        sys_one_extend_capability_definition: [{sys_id: DEF, capability: CAP, api: IMPL,
            api_type: 'sys_hub_flow', advanced: 'true',
            filter_properties: '{"provider":"Custom LLMcustom_api"}', sys_mod_count: '0'}],
        sys_generative_ai_prompt_config: [{sys_id: '24f1b0cb9373cf14e7f2b9fa6aba1076',
            definition: DEF, ai_config: PROMPT, is_default: 'true', filter_type: 'default',
            filter_properties: '', sys_mod_count: '0'}],
        sys_generative_ai_config: [{sys_id: PROMPT, definition: DEF,
            definition_table: 'sys_one_extend_capability_definition', active: 'true',
            state: 'published', model: 'halogen-v2', sys_mod_count: '5', prompt: 'PRIVATE_PROMPT'}],
        sys_generative_ai_model_config: [{sys_id: MODEL, model: 'halogen-v2', provider: MAP,
            active: 'true', lifecycle_state: 'active', usage_mode: 'none', sys_mod_count: '2',
            connection: 'PRIVATE_CONNECTION', model_display_name: 'PRIVATE_DISPLAY_NAME'}],
        sys_generative_ai_provider_mapping: [{sys_id: MAP, active: 'true', provider: 'Custom LLM',
            provider_api: 'custom_api', provider_implementation: IMPL,
            provider_implementation_document: 'sys_hub_flow', gen_ai_provider: PROVIDER, sys_mod_count: '6'}],
        sys_gen_ai_provider: [{sys_id: PROVIDER, gen_ai_provider: 'Custom LLM Provider', sys_mod_count: '7'}],
        sys_hub_flow: [{sys_id: IMPL, status: 'draft', sys_mod_count: '0'}]
    };
    change(db);
    const reads = [], queries = [];
    function Record(table) {
        assert.ok(db[table], 'Only the metadata tables may be read');
        let row, found = [], index = -1, limit, filters = [], checked = new Set(), allowed = false;
        return {
            isValid: () => true,
            isValidField: field => db[table].some(value => Object.hasOwn(value, field)),
            addQuery(field, value) { filters.push([field, String(value)]); },
            setLimit(value) { assert.ok(value > 0 && value <= 33); limit = value; },
            query() {
                assert.ok(limit, 'Bound every query');
                queries.push({table, filters, limit});
                found = db[table].filter(value => filters.every(([key, expected]) =>
                    String(value[key]) === expected || expected === 'true' && String(value[key]) === '1'))
                    .slice(0, limit);
            },
            next() {
                index++;
                row = found[index]; checked = new Set(); allowed = false;
                return !!row;
            },
            canRead() { allowed = denied !== table && denied !== table + ':' + row.sys_id; return allowed; },
            getElement(field) { return {canRead() { checked.add(field); return denied !== table + '.' + field; }}; },
            getValue(field) {
                assert.ok(allowed && checked.has(field), 'Normal rights precede metadata reads');
                assert.notEqual(denied, table + '.' + field);
                assert.ok(!['prompt', 'connection', 'model_display_name', 'request_transformer',
                    'response_transformer', 'script', 'endpoint', 'credential'].includes(field));
                reads.push([table, field]);
                return row[field];
            }
        };
    }
    const context = {Class: {create: () => function Settings() {}}, GlideRecord: Record,
        GlideDigest: function () { return {getSHA256Hex: value => crypto.createHash('sha256').update(value).digest('hex')}; }};
    vm.runInNewContext(SOURCE, context);
    const helper = new context.LocalLLMVoiceAssistantSettings();
    assert.equal(typeof helper.getConversationModel, 'function', 'The existing settings reader must expose selection');
    return {value: JSON.parse(JSON.stringify(helper.getConversationModel(SERVICE))), reads, queries};
}

test('exact current published default resolves metadata only, including advanced definition and draft flow', () => {
    const result = fixture();
    assert.deepEqual(Object.keys(result.value).sort(), ['version', 'status', 'capability_id',
        'definition_config_id', 'definition_id', 'prompt_binding_id', 'prompt_id', 'model_config_id',
        'provider_mapping_id', 'provider_id', 'implementation_id', 'model_identifier', 'binding_sha256'].sort());
    assert.equal(result.value.status, 'selected');
    assert.equal(result.value.version, 1);
    assert.equal(result.value.capability_id, CAP);
    assert.equal(result.value.definition_id, DEF);
    assert.equal(result.value.prompt_id, PROMPT);
    assert.equal(result.value.model_config_id, MODEL);
    assert.equal(result.value.provider_mapping_id, MAP);
    assert.equal(result.value.implementation_id, IMPL);
    assert.equal(result.value.model_identifier, 'halogen-v2');
    assert.match(result.value.binding_sha256, /^[0-9a-f]{64}$/);
    assert.ok(!JSON.stringify(result.value).includes('PRIVATE'));
});

test('active alternative prompt is never selected by row order or model display name', () => {
    const result = fixture(db => {
        db.sys_generative_ai_prompt_config.unshift({...db.sys_generative_ai_prompt_config[0],
            sys_id: 'a'.repeat(32), ai_config: 'b'.repeat(32), is_default: 'false'});
        db.sys_generative_ai_config.unshift({...db.sys_generative_ai_config[0],
            sys_id: 'b'.repeat(32), model: 'Other active model'});
    });
    assert.equal(result.value.prompt_id, PROMPT);
    assert.equal(result.value.model_identifier, 'halogen-v2');
});

test('ambiguous, conditional, inactive, unpublished and wrong-implementation graphs are unavailable', () => {
    const changes = [
        db => db.sys_one_extend_definition_config.push({...db.sys_one_extend_definition_config[0], sys_id: 'a'.repeat(32)}),
        db => { db.sys_one_extend_definition_config[0].active = 'false'; },
        db => { db.sys_one_extend_capability_definition[0].filter_properties = '{"provider":"Custom LLMcustom_api","location":"Berlin"}'; },
        db => { db.sys_generative_ai_prompt_config[0].filter_type = 'condition'; },
        db => { db.sys_generative_ai_prompt_config[0].filter_properties = '{"condition":"active=true"}'; },
        db => db.sys_generative_ai_prompt_config.push({...db.sys_generative_ai_prompt_config[0], sys_id: 'a'.repeat(32)}),
        db => { db.sys_generative_ai_config[0].active = 'false'; },
        db => { db.sys_generative_ai_config[0].state = 'draft'; },
        db => { db.sys_generative_ai_config[0].definition_table = 'wrong_table'; },
        db => { db.sys_generative_ai_model_config[0].active = 'false'; },
        db => { db.sys_generative_ai_model_config[0].lifecycle_state = ''; },
        db => { db.sys_generative_ai_model_config[0].usage_mode = 'restricted'; },
        db => db.sys_generative_ai_model_config.push({...db.sys_generative_ai_model_config[0], sys_id: 'a'.repeat(32)}),
        db => { db.sys_generative_ai_provider_mapping[0].active = 'false'; },
        db => { db.sys_generative_ai_provider_mapping[0].provider_implementation = 'b'.repeat(32); },
        db => { db.sys_generative_ai_provider_mapping[0].provider = 'Another provider'; },
        db => { db.sys_generative_ai_config[0].model = 'PRIVATE_DISPLAY_NAME'; },
        db => { db.sys_one_extend_capability[0].active = 'false'; }
    ];
    for (const change of changes) assert.deepEqual(fixture(change).value, {version: 1, status: 'unavailable'});
});

test('denied row and required-field reads fail closed without exposing denied values', () => {
    for (const denied of ['sys_generative_ai_config', 'sys_generative_ai_config.model',
        'sys_generative_ai_model_config.provider', 'sys_generative_ai_provider_mapping.provider_implementation']) {
        assert.deepEqual(fixture(() => {}, denied).value, {version: 1, status: 'unavailable'});
    }
});

test('descriptor revision changes when the selected native row revision changes', () => {
    const first = fixture().value;
    const next = fixture(db => { db.sys_generative_ai_config[0].sys_mod_count = '6'; }).value;
    assert.notEqual(first.binding_sha256, next.binding_sha256);
    assert.equal(first.model_identifier, next.model_identifier);
});

test('inactive and nonactive-lifecycle registrations do not compete with the active native selection', () => {
    for (const change of [{active: 'false'}, {lifecycle_state: ''}, {usage_mode: 'restricted'}]) {
        const result = fixture(db => db.sys_generative_ai_model_config.push({
            ...db.sys_generative_ai_model_config[0], sys_id: 'a'.repeat(32), ...change}));
        assert.equal(result.value.status, 'selected');
        assert.equal(result.value.model_config_id, MODEL);
    }
});

test('oversized metadata fails selection before returning a descriptor', () => {
    for (const change of [
        db => { db.sys_one_extend_capability_definition[0].filter_properties = ' '.repeat(4097) + '{"provider":"Custom LLMcustom_api"}'; },
        db => { db.sys_generative_ai_provider_mapping[0].provider = 'x'.repeat(129); }
    ]) assert.deepEqual(fixture(change).value, {version: 1, status: 'unavailable'});
});

test('native getValue boolean strings retain the same selected graph', () => {
    const result = fixture(db => {
        for (const rows of Object.values(db)) for (const row of rows) {
            for (const key of ['active', 'default', 'is_default']) if (row[key] === 'true') row[key] = '1';
        }
    });
    assert.equal(result.value.status, 'selected');
    assert.equal(result.value.model_config_id, MODEL);
});

test('a denied competing default cannot be hidden to manufacture uniqueness', () => {
    const result = fixture(db => db.sys_one_extend_definition_config.push({
        ...db.sys_one_extend_definition_config[0], sys_id: 'a'.repeat(32)}),
    'sys_one_extend_definition_config:' + 'a'.repeat(32));
    assert.deepEqual(result.value, {version: 1, status: 'unavailable'});
});

test('bounded registration overflow fails closed', () => {
    const result = fixture(db => {
        const original = db.sys_generative_ai_model_config[0];
        db.sys_generative_ai_model_config = Array.from({length: 33}, (_, index) =>
            ({...original, sys_id: index.toString(16).padStart(32, '0')}));
    });
    assert.deepEqual(result.value, {version: 1, status: 'unavailable'});
    assert.ok(result.queries.every(query => query.limit <= 33));
});
