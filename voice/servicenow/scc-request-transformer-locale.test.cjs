const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const beforeFile = `${__dirname}/evidence/scc-request-transformer-locale-before-20261013.js`;
const afterFile = `${__dirname}/evidence/scc-request-transformer-locale-proposed-20261013.js`;
const before = fs.readFileSync(beforeFile, 'utf8');
// The RED run uses the actual deployed adapter while the proposed file is absent.
const after = fs.existsSync(afterFile) ? fs.readFileSync(afterFile, 'utf8') : before;
const suffix = fs.readFileSync(`${__dirname}/evidence/scc-request-transformer-locale-suffix-20261013.txt`, 'utf8');
function run(source, aiConfig) {
  const value = vm.runInNewContext(source, { inputs: { prompt_data: {
    aiConfig, prompt: 'Stable base prompt\nGerman synthetic onboarding request',
    model: 'halogen-v2', max_tokens: 4096, temperature: 0
  } } });
  return JSON.parse(JSON.stringify(value));
}
test('target conversation appends final locale rule without changing base prefix or request settings', () => {
  const old = run(before, '8380c7e193f747d0e7f2b9fa6aba10b6');
  const updated = run(after, '8380c7e193f747d0e7f2b9fa6aba10b6');
  assert.equal(updated.body.messages[0].content, old.body.messages[0].content + suffix);
  updated.body.messages[0].content = old.body.messages[0].content;
  assert.deepEqual(updated, old);
});
test('all other configurations retain identical serialized request behavior including ReAct V3', () => {
  for (const config of ['4780c7e193f747d0e7f2b9fa6aba1030', 'other-config', undefined]) {
    assert.equal(JSON.stringify(run(after, config)), JSON.stringify(run(before, config)));
  }
});
