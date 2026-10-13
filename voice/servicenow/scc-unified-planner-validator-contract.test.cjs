const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const crypto = require('node:crypto');

const evidence = JSON.parse(fs.readFileSync(`${__dirname}/evidence/scc-unified-planner-validator-contract-20261013.json`, 'utf8'));
const [now, third] = evidence.validators;
const direct = JSON.stringify({ action_name: 'executor_agent', action_inputs: { agent_id: 'demo-agent' }, thoughts: 'German demo' });

function run(validator, response) {
  const errors = [];
  // These inputs are valid JSON. This is exactly the observed OOTB parser's
  // fast path; markdown and brace-extraction fallbacks are outside this test.
  function PlannerParser() {}
  PlannerParser.prototype._isValidJson = function(str) {
    if (!str) return false;
    try { JSON.parse(str); return true; } catch (e) { return false; }
  };
  PlannerParser.prototype.parseAllJsonFormats = function(response) {
    if (!response || typeof response !== 'string') return null;
    var trimmed = response.trim();
    if (this._isValidJson(trimmed)) return trimmed;
    throw new Error('This reproduction covers the valid-JSON fast path only');
  };
  const payload = { response: [response], status: 'success' };
  const result = vm.runInNewContext(validator.script, {
    payload,
    sn_aia: {
      AIAgentsLogger: function() { this.error = (...args) => errors.push(args); this.info = () => {}; },
      AgentUnifiedPlannerUtil: PlannerParser
    }
  });
  return { result, errors };
}

test('the copied sources match exact live ServiceNow hashes', () => {
  for (const v of evidence.validators) {
    assert.equal(crypto.createHash('sha256').update(v.script).digest('hex'), v.sha256);
  }
});
test('NowLLM validator destroys direct planner JSON when model_output is absent', () => {
  const { result, errors } = run(now, direct);
  assert.equal(result.response[0], '{}');
  assert.equal(errors.length, 1);
  assert.match(errors[0][1][0], /undefined/);
});
test('NowLLM validator succeeds for its wrapped response contract', () => {
  const { result, errors } = run(now, JSON.stringify({ model_output: direct }));
  assert.equal(result.response[0], direct);
  assert.equal(errors.length, 0);
});
test('OOTB third-party validator preserves direct planner JSON', () => {
  const { result, errors } = run(third, direct);
  assert.equal(result.response[0], direct);
  assert.equal(errors.length, 0);
});
test('third-party validator does not unwrap NowLLM-shaped JSON', () => {
  const wrapped = JSON.stringify({ model_output: direct });
  const { result, errors } = run(third, wrapped);
  assert.equal(result.response[0], wrapped);
  assert.equal(errors.length, 0);
});
