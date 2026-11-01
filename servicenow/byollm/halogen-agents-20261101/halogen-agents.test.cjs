'use strict';
// Pure offline contracts. Platform-only caller-context and Vision boundaries are
// represented by deterministic synthetic doubles; no ServiceNow or model calls.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {createHash} = require('node:crypto');
const {test} = require('node:test');
const fixture = require('./scc-rendered.fixture.json');
const snapshots = path.resolve(__dirname, '../../../server/.local/voice-goal-halogen-agents-20261101');
const read = name => fs.readFileSync(path.join(snapshots, name), 'utf8');
const halogenBefore = read('halogen.request_transformer.before.js');
const gemmaBefore = read('gemma.request_transformer.before.js');
const ledgerBefore = read('LocalLLMReActExecutionLedger.before.js');
const adapterBefore = read('LocalLLMChatCompletionsAdapter.before.js');
const candidate = fs.readFileSync(process.env.HALOGEN_SOURCE || path.join(__dirname, 'Halogen-Request-Transformer.js'), 'utf8');
const ledger = fs.readFileSync(process.env.LEDGER_SOURCE || path.join(__dirname, 'LocalLLMReActExecutionLedger.js'), 'utf8');
const SCC = '4780c7e193f747d0e7f2b9fa6aba1030';
const GEMMA = 'Gemma 4 26B-A4B';
const clone = value => JSON.parse(JSON.stringify(value));
const digest = value => createHash('sha256').update(value).digest('hex');

function makeContext(source) {
    const calls = {caller: [], ledger: [], vision: []};
    const context = vm.createContext({Class: {create() { return function() {}; }},
        gs: {info() {}, warn() {}}, global: {}});
    vm.runInContext(source, context, {timeout: 1000});
    const OwnedLedger = context.LocalLLMReActExecutionLedger;
    context.global.LocalLLMReActExecutionLedger = function() {
        this.transformJSON = (request, policy) => {
            calls.ledger.push({request: JSON.parse(request), policy: JSON.parse(policy)});
            return new OwnedLedger().transformJSON(request, policy);
        };
    };
    context.global.SCCVoiceCallerContext = function() {
        this.includeJSON = request => {
            const value = JSON.parse(request);
            calls.caller.push(value);
            return JSON.stringify({promptIncluded: true, revision: 1, receiptStored: false,
                prompt: value.prompt.replace('</memory>', fixture.rawCallerNote + '</memory>')});
        };
    };
    context.global.SCCVisionRequestTransformer = function() {
        this.build = request => {
            calls.vision.push(JSON.parse(request));
            return JSON.parse(request);
        };
    };
    vm.runInContext(adapterBefore, context, {timeout: 1000});
    context.global.LocalLLMChatCompletionsAdapter = context.LocalLLMChatCompletionsAdapter;
    return {context, calls};
}

function transform(source, request, ledgerSource = ledger) {
    const {context, calls} = makeContext(ledgerSource);
    context.inputs = clone(request);
    const result = vm.runInContext(source, context, {timeout: 1000});
    return {result: clone(result), calls};
}

function request(model = 'halogen-v2') {
    return {prompt_data: {...clone(fixture.promptData), model},
        request_data: {_meta: {conversationId: '0123456789abcdef0123456789abcdef'}}};
}

function ledgerTransform(value, policy, source = ledger) {
    const {context} = makeContext(source);
    return new context.LocalLLMReActExecutionLedger().transformJSON(value, JSON.stringify(policy));
}

function ledgerRequest(model = 'halogen-v2') {
    return {prompt_data: {...clone(fixture.promptData), model}};
}

test('observed SCC rendering retains exact Gemma prompt preparation, caller notes, and ledger', () => {
    const input = request();
    // Separately verify preparation so the baseline fails on missing behavior,
    // rather than stopping early on its known string-schema rejection.
    input.prompt_data.additional_configurations.response_format = clone(fixture.responseFormat);
    const actual = transform(candidate, input);
    const expected = transform(gemmaBefore, request(GEMMA));
    const content = actual.result.body.messages[0].content;
    assert.equal(digest(content), digest(expected.result.body.messages[0].content), 'complete rendered prompt parity');
    assert.equal(actual.calls.caller.length, 1);
    assert.equal(actual.calls.caller[0].request_data._meta.conversationId, input.request_data._meta.conversationId);
    assert.equal(actual.calls.ledger.length, 1);
    assert.deepEqual(actual.calls.ledger[0].policy, {version: 1, enabled: true, model: 'halogen-v2'});
    assert.ok(content.includes('<scc_name_confirmation_text_input_20261024>'));
    assert.ok(content.includes('Wie lautet der richtige Name? Bitte buchstabiere ihn.'));
    assert.ok(content.includes(fixture.rawCallerNote));
    assert.ok(content.includes('<recorded_execution_state>'));
    assert.equal(content.slice(content.indexOf('<inputs>'), content.indexOf('</inputs>') + 9),
        expected.result.body.messages[0].content.slice(expected.result.body.messages[0].content.indexOf('<inputs>'),
            expected.result.body.messages[0].content.indexOf('</inputs>') + 9));
    assert.deepEqual(actual.result.body.response_format, fixture.responseFormat);
    assert.equal(actual.result.body.model, 'halogen-v2');
    assert.equal(actual.result.body.max_tokens, 4096);
    assert.equal(actual.result.body.temperature, 0);
    assert.equal(Object.hasOwn(actual.result.body, 'reasoning_effort'), false);
    assert.deepEqual(input, {...request(), prompt_data: {...request().prompt_data,
        additional_configurations: {...request().prompt_data.additional_configurations,
            response_format: fixture.responseFormat}}});
});

test('the observed JSON-string schema is normalized without changing any schema field', () => {
    const actual = transform(candidate, request()).result.body;
    assert.deepEqual(actual.response_format, fixture.responseFormat);
    assert.equal(actual.response_format.json_schema.schema.properties.Action.minItems, 1);
    assert.equal(actual.response_format.json_schema.schema.properties.Action.maxItems, 4);
});

test('scoped SCC preparation preserves supported serialized and message wrappers', () => {
    for (const wrap of [prompt => [prompt], prompt => [{role: 'system', content: prompt}],
        prompt => JSON.stringify([{role: 'user', content: prompt}]),
        prompt => [JSON.stringify([{role: 'assistant', content: prompt}])]]) {
        const input = request();
        input.prompt_data.prompt = wrap(input.prompt_data.prompt);
        const expected = request(GEMMA);
        expected.prompt_data.prompt = wrap(expected.prompt_data.prompt);
        const actual = transform(candidate, input);
        assert.equal(digest(JSON.stringify(actual.result.body.messages)),
            digest(JSON.stringify(transform(gemmaBefore, expected).result.body.messages)), 'wrapped prompt parity');
        assert.equal(actual.calls.caller.length, 1);
        assert.equal(actual.calls.ledger.length, 1);
    }
});

test('wrong model or missing/foreign configuration does not invoke SCC preparation or ledger', () => {
    for (const mutate of [p => {p.model = GEMMA;}, p => {p.model = 'halogen-v2-other';},
        p => {delete p.aiConfig;}, p => {p.aiConfig = '';}, p => {p.aiConfig = 'other';},
        p => {p.aiConfig = SCC + 'x';}]) {
        const input = request();
        input.prompt_data.additional_configurations.response_format = fixture.responseFormat;
        mutate(input.prompt_data);
        const actual = transform(candidate, input);
        assert.deepEqual(actual.result, transform(halogenBefore, input).result);
        assert.equal(actual.calls.caller.length, 0);
        assert.equal(actual.calls.ledger.length, 0);
    }
});

test('ledger accepts Halogen only through the same existing evidence and identity gates', () => {
    const original = JSON.stringify(ledgerRequest());
    const policy = {version: 1, enabled: true, model: 'halogen-v2'};
    const actual = ledgerTransform(original, policy);
    assert.notEqual(digest(actual), digest(original), 'Halogen receives the execution appendix');
    const prompt = JSON.parse(actual).prompt_data.prompt;
    const escaped = prompt.split('<recorded_execution_state>\n')[1].split('\n')[1];
    const records = JSON.parse(escaped).completed_actions;
    assert.deepEqual(records, fixture.promptData.preprocessor_modified_input.agent_scratchpad[0].Action);
    assert.equal(ledgerTransform(actual, policy), actual, 'idempotence');
    for (const mutate of [p => {p.model = GEMMA;}, p => {p.aiConfig = 'other';},
        p => {p.definition = 'other';}, p => {p.preprocessor_modified_input.agent_name = 'another agent';},
        p => {p.preprocessor_modified_input.persona = 'missing policy marker';},
        p => {p.preprocessor_modified_input.agent_scratchpad = [];}]) {
        const input = ledgerRequest();
        mutate(input.prompt_data);
        const value = JSON.stringify(input);
        assert.equal(ledgerTransform(value, policy), value);
    }
    assert.equal(ledgerTransform(original, {...policy, enabled: false}), original);
    assert.equal(ledgerTransform(original, {...policy, model: 'halogen-v2-other'}), original);
});

test('Gemma ledger behavior is unchanged, including malformed and mismatched identities', () => {
    const policy = {version: 1, enabled: true, model: GEMMA};
    const value = JSON.stringify(ledgerRequest(GEMMA));
    assert.equal(ledgerTransform(value, policy), ledgerTransform(value, policy, ledgerBefore));
    assert.notEqual(ledgerTransform(value, policy), value);
    for (const invalid of ['not JSON', '{"prompt_data":{},"prompt_data":{}}',
        JSON.stringify(ledgerRequest('unknown'))]) {
        assert.equal(ledgerTransform(invalid, policy), invalid);
    }
});

test('invalid string and object response formats still reject', () => {
    for (const response_format of ['not JSON', '[]', 'null', '"json_schema"', '{}',
        {type: 'unknown'}, {type: 'json_schema'},
        JSON.stringify({type: 'json_schema', json_schema: {name: 'missing_schema'}}),
        JSON.stringify({type: 'json_schema', json_schema: {name: '', schema: {}}})]) {
        const input = {prompt_data: {model: 'halogen-v2', prompt: 'Ordinary prompt',
            additional_configurations: {response_format}}};
        assert.throws(() => transform(candidate, input), /Custom LLM:/);
    }
});

test('ordinary text, serialized history, typed content, and existing sampling transport are preserved', () => {
    for (const prompt of ['Ordinary text', ['Wrapped text'],
        [{role: 'system', content: 'policy'}, {role: 'user', content: 'question'}],
        JSON.stringify([{role: 'user', content: 'question'}, {role: 'assistant', content: 'answer'}]),
        [{role: 'user', content: [{type: 'text', text: 'image'},
            {type: 'image_url', image_url: {url: 'data:image/png;base64,YQ==', detail: 'low'}}]}]]) {
        const input = {prompt_data: {model: 'halogen-v2', aiConfig: 'ordinary', prompt,
            max_tokens: '512', temperature: '0.25', additional_configurations: {
                top_p: 0.1, stop: ['stop'], reasoning_effort: 'none', response_format: {type: 'json_object'}}}};
        const actual = transform(candidate, input);
        assert.deepEqual(actual.result, transform(halogenBefore, input).result);
        assert.equal(actual.calls.caller.length, 0);
        assert.equal(actual.calls.ledger.length, 0);
    }
});

test('legacy Vision dispatch and its rejection rules are unchanged', () => {
    const aiConfig = 'cb5533db937f0b54e7f2b9fa6aba1055';
    for (const prompt of ['attachment prompt', ['attachment prompt'],
        JSON.stringify([{role: 'user', content: 'attachment prompt'}])]) {
        const input = {prompt_data: {model: 'halogen-v2', aiConfig, prompt}};
        const actual = transform(candidate, input);
        assert.deepEqual(actual.result, transform(halogenBefore, input).result);
        assert.deepEqual(actual.calls.vision, transform(halogenBefore, input).calls.vision);
        assert.equal(actual.calls.caller.length, 0);
        assert.equal(actual.calls.ledger.length, 0);
    }
    for (const extra of [{model: GEMMA}, {additional_configurations: {VISION_CAPABILITY: true}},
        {functionCallRequest: {name: 'native-tool'}},
        {prompt: [{role: 'user', content: [{type: 'text', text: 'typed'}]}]}]) {
        const input = {prompt_data: {model: 'halogen-v2', aiConfig, prompt: 'attachment', ...extra}};
        let expected;
        try { transform(halogenBefore, input); } catch (error) { expected = error.message; }
        assert.ok(expected);
        assert.throws(() => transform(candidate, input), error => error.message === expected);
    }
});

test('native function calling remains unsupported', () => {
    assert.throws(() => transform(candidate, {prompt_data: {model: 'halogen-v2', prompt: 'text',
        functionCallRequest: {name: 'tool'}}}), /Native function calling/);
});
