const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');

const file = process.env.TRANSFORMER_FILE ||
    path.join(__dirname, 'scc-halogen-request-transformer.js');
const source = fs.readFileSync(file, 'utf8');
const reactV3 = '4780c7e193f747d0e7f2b9fa6aba1030';

function transform(promptData) {
    const value = vm.runInNewContext(source, {
        inputs: { prompt_data: promptData }
    }, { timeout: 1000 });
    return JSON.parse(JSON.stringify(value));
}

test('ordinary skills retain the complete existing request contract', () => {
    assert.deepEqual(transform({
        prompt: 'Bitte diesen Text zusammenfassen.',
        model: 'another-model', max_tokens: '700', temperature: '0.25',
        aiConfig: 'ordinary-skill'
    }), {
        body: {
            model: 'another-model',
            messages: [{ role: 'user', content: 'Bitte diesen Text zusammenfassen.' }],
            max_tokens: 700, temperature: 0.25, stream: false
        },
        headers: {}
    });
});

test('only the exact ReAct V3 configuration requests a JSON object', () => {
    const result = transform({ prompt: 'Return the next ReAct step.', aiConfig: reactV3 });
    assert.deepEqual(result.body.response_format, { type: 'json_object' });
    assert.equal(result.body.model, 'halogen-v2');
    assert.equal(result.body.max_tokens, 1024);
    assert.equal(result.body.temperature, 0);
    assert.equal(result.body.stream, false);
    assert.deepEqual(result.headers, {});
});

test('other ReAct configurations and missing identifiers are not constrained', () => {
    for (const aiConfig of [undefined, null, '', 'older-react-array-template', reactV3 + 'x']) {
        const result = transform({ prompt: 'Return a JSON array of steps.', aiConfig });
        assert.equal(Object.hasOwn(result.body, 'response_format'), false);
    }
});

test('configuration identifiers support the required String conversion', () => {
    const result = transform({ prompt: 'Next step.', aiConfig: { toString: () => reactV3 } });
    assert.deepEqual(result.body.response_format, { type: 'json_object' });
});

test('token ceiling and temperature limits stay unchanged', () => {
    const high = transform({ prompt: 'Next step.', aiConfig: reactV3, max_tokens: '9999', temperature: '3.5' });
    assert.equal(high.body.max_tokens, 2048);
    assert.equal(high.body.temperature, 2);
    const low = transform({ prompt: 'Next step.', max_tokens: '1', temperature: '-0.5' });
    assert.equal(low.body.max_tokens, 1);
    assert.equal(low.body.temperature, 0);
    const invalid = transform({ prompt: 'Next step.', max_tokens: 'invalid', temperature: 'invalid' });
    assert.equal(invalid.body.max_tokens, 1024);
    assert.equal(invalid.body.temperature, 0);
});

test('empty or whitespace prompts are rejected before inference', () => {
    for (const prompt of [undefined, null, '', ' \t\r\n ']) {
        assert.throws(() => transform({ prompt, aiConfig: reactV3 }));
    }
});
