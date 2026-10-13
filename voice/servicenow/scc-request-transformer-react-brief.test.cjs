const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const crypto = require('node:crypto');

const beforeFile = path.join(__dirname, 'evidence/scc-request-transformer-react-brief-before-20261013.js');
const proposedFile = path.join(__dirname, 'evidence/scc-request-transformer-react-brief-proposed-20261013.js');
const before = fs.readFileSync(beforeFile, 'utf8');
const proposed = fs.existsSync(proposedFile) ? fs.readFileSync(proposedFile, 'utf8') : before;
const suffix = '\n\n<scc_react_brief_20261013>\nFuer den SCC-Laptop-Onboarding-Agenten enthaelt jedes Thought-Feld nur einen kurzen Satz mit hoechstens 25 Woertern als knappe Entscheidungsbegruendung. Wiederhole darin weder die Aufgabe noch bekannte Gespraechsdaten oder Werkzeugbeschreibungen. Alle vorgeschriebenen JSON-Felder, Aktionsnamen, Berechtigungen und Referenzen sowie alle vollstaendigen Action-Eingaben bleiben unveraendert. Die bestehenden Regeln zur Aktionsauswahl, ausdruecklichen Bestellbestaetigung und Vermeidung automatischer Wiederholungen bleiben verbindlich.\n</scc_react_brief_20261013>';
const react = '4780c7e193f747d0e7f2b9fa6aba1030';

function run(source, aiConfig, prompt) {
  return JSON.parse(JSON.stringify(vm.runInNewContext(source, { inputs: { prompt_data: {
    aiConfig, prompt, model: 'halogen-v2', max_tokens: 4096, temperature: 0
  } } })));
}

test('fresh adapter baseline matches reviewed live hash', () => {
  assert.equal(crypto.createHash('sha256').update(before).digest('hex'),
    '7462cb47ff804bfd72fb89c2ab08c9d4cb4d68255e47e4a744a8e3aea2997c02');
});

test('only own SCC ReAct prompts append concise Thought instructions while preserving all request settings', () => {
  for (const name of ['SCC Laptop Onboarding', 'SCC Laptop Onboarding Voice']) {
    const prompt = `Stable private template\nAgent: ${name}\nMission and tools`;
    const baseline = run(before, react, prompt);
    const output = run(proposed, react, prompt);
    assert.equal(output.body.messages[0].content, prompt + suffix);
    output.body.messages[0].content = prompt;
    assert.deepEqual(output, baseline);
    assert.deepEqual(output.body.response_format, { type: 'json_object' });
  }
});

test('unrelated ReAct agents and all other configurations keep byte-identical serialized request behavior', () => {
  for (const [config, prompt] of [
    [react, 'Other agent with a German laptop request'],
    [react, 'SCC Laptop Bestellkontext tool only'],
    ['8380c7e193f747d0e7f2b9fa6aba10b6', 'Agent: SCC Laptop Onboarding'],
    ['another-config', 'Agent: SCC Laptop Onboarding'],
    [undefined, 'Agent: SCC Laptop Onboarding']
  ]) {
    assert.equal(JSON.stringify(run(proposed, config, prompt)),
      JSON.stringify(run(before, config, prompt)));
  }
});
