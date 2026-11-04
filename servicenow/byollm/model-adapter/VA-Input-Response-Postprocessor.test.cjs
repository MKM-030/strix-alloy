'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const source = fs.readFileSync(__dirname + '/VA-Input-Response-Postprocessor.js', 'utf8');
const classifier = {
    classification: 'ANSWER',
    changed_field_values: [],
    trying_to_skip: false,
    done: false,
    field: 'employee_name',
    return_to_agent: true,
    response: 'Die Verbindung funktioniert. Welche Angaben fehlen noch?'
};
function process(response) {
    return vm.runInNewContext(source, {
        outputs: JSON.stringify({result: {response, preserved: 'result'}, preserved: 'envelope'})
    });
}
function result(response) {
    return JSON.parse(process(response).result.response);
}

test('raw Chat Completions classifier JSON retains its native routing and result fields', () => {
    const output = process(JSON.stringify(classifier));
    assert.deepEqual(JSON.parse(output.result.response), classifier);
    assert.equal(output.result.preserved, 'result');
    assert.equal(output.preserved, 'envelope');
});

test('legacy model_output envelope retains the same classifier result', () => {
    assert.deepEqual(result(JSON.stringify({model_output: JSON.stringify(classifier)})), classifier);
});

test('previous model_output-only assumption silently discarded a valid raw classifier', () => {
    function previousBehavior(outputs) {
        try {
            const envelope = JSON.parse(outputs);
            const response = JSON.parse(envelope.result.response);
            const modelOutput = response.model_output || '';
            envelope.result.response = JSON.stringify(JSON.parse(modelOutput));
            return envelope;
        } catch (_) {
            return undefined;
        }
    }
    const input = JSON.stringify({result: {response: JSON.stringify(classifier)}});
    assert.equal(previousBehavior(input), undefined);
    assert.equal(result(JSON.stringify(classifier)).return_to_agent, true);
});

test('empty or malformed classifier data throws a safe error instead of returning undefined', () => {
    for (const invalid of ['', 'private-sentinel', '{}', '[]', '{"model_output":""}']) {
        assert.throws(() => process(invalid), error =>
            String(error.message).startsWith('Custom VA Input Response Generation:') &&
            !String(error.message).includes('private-sentinel'));
    }
});

test('skip normalization keeps the established skip-or-trying_to_skip precedence', () => {
    assert.equal(result(JSON.stringify({...classifier, skip: true})).trying_to_skip, true);
    assert.equal(result(JSON.stringify({...classifier, trying_to_skip: 'true'})).trying_to_skip, true);
    assert.equal(result(JSON.stringify({...classifier, skip: 'false', trying_to_skip: true})).trying_to_skip, false);
});
