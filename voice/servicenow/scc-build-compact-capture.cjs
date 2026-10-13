// Produce a compact executable from the reviewed full capture implementation.
// FROZEN_MANIFEST remains empty: the final browser-reviewed plan must be injected.
const fs = require('fs');
const path = require('path');
const base = __dirname;
let source = fs.readFileSync(path.join(base, 'scc-batch-capture.js'), 'utf8');
source = source.replace(/^\/\*[\s\S]*?\*\//, '');
source = source.split('\n').map(line => line.trim()).filter(line => line && !line.startsWith('//'))
  .map(line => line.replace(/^(var (?:MODE|FROZEN_MANIFEST) = .*?;)\s*\/\/.*$/, '$1')).join(' ');
source = source.replace("var MODE = 'plan';", "var MODE = 'capture';");
if (!source.includes('var FROZEN_MANIFEST = [];') || !source.includes('var COMPLETE_AFTER_VERIFICATION = false;'))
  throw new Error('Expected frozen-manifest/WIP controls missing');
if (/SCC_SHAPE_START|SCC Canonical Inputs/.test(source)) throw new Error('Unexpected runtime diagnostics in capture source');
new (require('vm').Script)(source);
const output = path.join(base, 'scc-batch-capture-compact.js');
fs.writeFileSync(output, '/* Generated capture; inject final reviewed FROZEN_MANIFEST. Leaves all sets WIP. */\n' + source + '\n');
console.log('Generated ' + output + ' (' + Buffer.byteLength(source) + ' bytes before frozen manifest)');
