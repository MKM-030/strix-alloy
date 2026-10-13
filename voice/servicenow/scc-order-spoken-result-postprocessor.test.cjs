const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, 'scc-order-spoken-result-postprocessor.js'), 'utf8');
const verified = JSON.parse(fs.readFileSync(path.join(__dirname, 'evidence', 'scc-philipp-order-verification-20261013.json'), 'utf8')).toolResponse[0].output;
function run(output) { return vm.runInNewContext(source, { output, context: {} }).processed_output; }
const expected = 'Die Demo-Anforderung für Philipp Borchert mit Artikel SCC Laptop zum Onboarding (Demo) wurde angelegt: REQ0010014, Position RITM0010013.';
for (const input of [verified, JSON.stringify(verified), { tool_response: verified }, { tool_response: JSON.stringify(verified) }])
    assert.equal(run(input), expected);
assert.ok(run({ ...verified, reused: true }).includes('ist bereits vorhanden'));
assert.ok(expected.split(/\s+/).length <= 40);
const failures = [null, 'invalid JSON', { ...verified, ok: false }, { ...verified, demo_only: false },
    { ...verified, catalog_item_id: 'other' }, { ...verified, catalog_item_name: '' },
    { ...verified, employee_name: '' }, { ...verified, request_number: 'invented' },
    { ...verified, requested_item_number: 'RITM123' }, { ...verified, request_id: '' },
    { ...verified, requested_item_id: 'other' }, { ...verified, reused: 'false' },
    { ...verified, catalog_item_name: '<speak>unsafe</speak>' }, { output: verified }];
for (const input of failures) {
    const text = run(input);
    assert.match(text, /Bestellergebnis ist unklar/);
    assert.match(text, /bestellen Sie nicht erneut/);
    assert.doesNotMatch(text, /REQ0010014|RITM0010013|wurde angelegt/);
}
console.log(`Formatter checks passed: 4 verified wire shapes, reused result, ${failures.length} invalid results; ${expected.split(/\s+/).length} words.`);
