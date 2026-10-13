// Run: node --expose-internals scc-react-context-fix-check.cjs
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const acorn = require('internal/deps/acorn/acorn/dist/acorn');
const script = fs.readFileSync(__dirname + '/scc-react-context-fix.js', 'utf8');
acorn.parse(script, {ecmaVersion: 5});

const targetId = '4780c7e193f747d0e7f2b9fa6aba1030';
const sourceId = 'ef46ebab935cbe105c21b7cd1dba10ab';
const marker = '<!-- SCC custom connector: rendered conversation context -->';
const original = 'Synthetic original prompt\n<inputs>\n{{tools}}';
const addition = '\n\n' + marker + '\n' +
    'Here is your <mission>{{question}}</mission>\n' +
    'Here is your <scratchpad>{{agent_scratchpad}}</scratchpad>\n' +
    'Here is your <memory>{{short_term_memory}}</memory>\n' +
    'Here is your <session_archive>{{previous_scratchpad}}</session_archive>\n' +
    '</inputs>\n';

function run(current, action = 'apply', dryRun = true, sourcePrompt = original, failUpdate = false) {
    const records = {[sourceId]: sourcePrompt, [targetId]: current};
    const writes = [];
    const workflowCalls = [];
    let output;
    function GlideRecord(table) {
        assert.equal(table, 'sys_generative_ai_config');
        this.get = function(id) { this.id = id; return Object.hasOwn(records, id); };
        this.getValue = function(field) { assert.equal(field, 'prompt'); return records[this.id]; };
        this.setWorkflow = function(value) { workflowCalls.push([this.id, value]); };
        this.setValue = function(field, value) {
            assert.equal(this.id, targetId);
            assert.equal(field, 'prompt');
            this.pending = value;
        };
        this.update = function() {
            assert.deepEqual(workflowCalls, [[targetId, false]]);
            if (failUpdate) return null;
            records[this.id] = this.pending;
            writes.push(this.id);
            return this.id;
        };
    }
    function log(message) { output = JSON.parse(message.slice(message.indexOf('{'))); }
    vm.runInNewContext(script.replace('var DRY_RUN = true;', 'var DRY_RUN = ' + dryRun + ';')
        .replace("var ACTION = 'apply';", 'var ACTION = ' + JSON.stringify(action) + ';'),
        {GlideRecord, gs: {info: log, error: log}});
    assert.equal(records[sourceId], sourcePrompt, 'Source never changes');
    return {output, records, writes, workflowCalls};
}

let r = run(original);
assert.equal(r.output.ok, true);
assert.equal(r.output.changed, true);
assert.equal(r.output.writes, 0);
assert.deepEqual(r.workflowCalls, []);
assert.equal(r.records[targetId], original);

r = run(original, 'apply', false);
assert.equal(r.output.writes, 1);
assert.equal(r.records[targetId], original + addition);
assert.equal(r.records[targetId].slice(0, original.length), original, 'Original prefix preserved byte-for-byte');
assert.equal(r.records[targetId].slice(original.length), addition, 'Only the reviewed suffix is added');

r = run(original + addition, 'apply', false);
assert.equal(r.output.changed, false);
assert.equal(r.output.writes, 0);

r = run(original + addition, 'rollback');
assert.equal(r.output.changed, true);
assert.equal(r.output.writes, 0);
assert.equal(r.records[targetId], original + addition);

r = run(original + addition, 'rollback', false);
assert.equal(r.output.writes, 1);
assert.equal(r.records[targetId], original);

r = run(original, 'rollback', false);
assert.equal(r.output.changed, false);
assert.equal(r.output.writes, 0);

for (const edited of [original + addition + 'edit', original + addition.replace('{{question}}', '{{other}}'),
    'edited ' + original + addition, original + '\n' + marker]) {
    r = run(edited, 'rollback', false);
    assert.equal(r.output.ok, false);
    assert.equal(r.output.writes, 0);
    assert.equal(r.records[targetId], edited);
}

r = run(original, 'apply', false, original + marker);
assert.equal(r.output.ok, false);
assert.equal(r.output.writes, 0);
r = run(original, 'unknown', false);
assert.equal(r.output.ok, false);
assert.equal(r.output.writes, 0);
r = run(original, 'apply', false, original, true);
assert.equal(r.output.ok, false);
assert.equal(r.output.writes, 0);
assert.equal(r.records[targetId], original);

console.log('PASS: ES5 parse, dry run, exact suffix/prefix, apply/rollback idempotence, drift refusal, source preservation, workflow flag, update failure.');
