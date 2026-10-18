'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const crypto = require('node:crypto');
const path = require('node:path');
const base = __dirname;
const evidence = JSON.parse(fs.readFileSync(path.join(base, 'evidence/scc-order-live-readback-20261013.json'), 'utf8'));
const draft = JSON.parse(fs.readFileSync(path.join(base, 'evidence/scc-order-item-response-proposed-20261013.json'), 'utf8'));
const scope = '7cc4ec81533121106b38ddeeff7b12ee';
const chat = 'a4a9438393738354e7f2b9fa6aba101d';
const voice = 'a6337ddf93f787105c8132d47aba1058';
const tool = '8b5c4f0393b38354e7f2b9fa6aba10f7';
const binding = '0ed4b19b933b87105c8132d47aba1030';
function fixture() {
  const rows = {};
  for (const row of evidence.records) rows[row.sys_id] = {table: row.table, values: Object.fromEntries(Object.entries(row.fields).map(([k,v]) => [k,v.value]))};
  for (const row of evidence.agent_instruction_readback.records) rows[row.sys_id].values.instructions = row.instructions;
  rows[scope] = {table:'sys_scope', values:{scope:'sn_generative_ai'}};
  return rows;
}
function run(rows, apply = false, options = {}) {
  const writes = [], logs = [];
  class GR {
    constructor(table) { this.table = table; this.pending = {}; }
    get(id) { this.id = id; this.row = rows[id]; return !!this.row && this.row.table === this.table; }
    isValidField(field) { return Object.hasOwn(this.row.values, field); }
    getValue(field) { return this.row.values[field]; }
    getUniqueValue() { return this.id; }
    canWrite() { return this.id !== options.denyRecord; }
    getElement(field) { return {canWrite: () => this.id !== options.denyField}; }
    setValue(field, value) { this.pending[field] = value; }
    update() {
      if (this.id === options.failUpdate) return null;
      Object.assign(this.row.values, this.pending);
      writes.push({id:this.id, fields:Object.keys(this.pending)});
      return this.id;
    }
  }
  let source = fs.readFileSync(path.join(base, 'scc-order-item-patch.js'), 'utf8');
  if (!apply) source = source.replace('var APPLY = true;', 'var APPLY = false;');
  vm.runInNewContext(source, {
    GlideRecord: GR,
    GlideDigest: class {getSHA256Hex(s) {return crypto.createHash('sha256').update(s).digest('hex');}},
    gs: {
      hasRole: () => options.admin !== false,
      getCurrentApplicationId: () => options.application || 'global',
      getCurrentScopeName: () => options.namespace || 'global',
      info: text => logs.push(text)
    }
  });
  return {writes, receipt:JSON.parse(logs.at(-1).replace(/^\[SCC ITEM PATCH\] /,''))};
}
test('dry run checks all records and plans exactly three changes without writes', () => {
  const {writes,receipt} = run(fixture());
  assert.equal(receipt.status, 'dry_run'); assert.equal(receipt.planned.length, 3); assert.deepEqual(writes, []);
});
test('actual live code updates only script and two instruction fields; repeat is a no-op', () => {
  const rows = fixture(); const first = run(rows, true);
  assert.equal(first.receipt.status, 'applied');
  assert.deepEqual(first.writes, [{id:tool,fields:['script']},{id:chat,fields:['instructions']},{id:voice,fields:['instructions']}]);
  assert.equal(rows[tool].values.script, fs.readFileSync(path.join(base,'scc-laptop-order-tool.js'),'utf8'));
  assert.equal(rows[chat].values.instructions, draft.after.instructions);
  assert.equal(rows[voice].values.instructions, draft.after.instructions);
  const again = run(rows,true); assert.equal(again.receipt.status,'already_applied'); assert.deepEqual(again.writes,[]);
});
test('last target drift stops before any preceding update', () => {
  const rows=fixture(); rows[voice].values.instructions += '\nChanged';
  const {writes,receipt}=run(rows,true); assert.deepEqual(writes,[]); assert.equal(receipt.status,'aborted');
});
test('binding drift, reference drift and record scope drift prevent all writes', () => {
  for (const [field,value] of [['post_processing_script','return input;'],['tool','different'],['sys_scope','different'],['requires_widget_transformation','0']]) {
    const rows=fixture(); rows[binding].values[field]=value;
    const result=run(rows,true); assert.deepEqual(result.writes,[]); assert.equal(result.receipt.status,'aborted');
  }
});
test('admin, current scope, missing fields and write ACLs are preflight gates', () => {
  for (const options of [{admin:false},{namespace:'wrong'},{denyRecord:voice},{denyField:voice}]) {
    const result=run(fixture(),true,options); assert.deepEqual(result.writes,[]); assert.equal(result.receipt.status,'aborted');
  }
  const rows=fixture(); delete rows[binding].values.post_processing_script;
  const result=run(rows,true); assert.deepEqual(result.writes,[]); assert.equal(result.receipt.status,'aborted');
});
test('failed second write reports possible partial state, no automatic rollback or retry', () => {
  const rows=fixture(); const first=run(rows,true,{failUpdate:chat});
  assert.equal(first.receipt.status,'partial_or_uncertain'); assert.equal(first.receipt.attempted.length,2); assert.equal(first.writes.length,1);
  const resumed=run(rows,true); assert.equal(resumed.receipt.status,'applied'); assert.deepEqual(resumed.writes.map(w=>w.id),[chat,voice]);
});

test('Global execution may update the exact scoped records and reports execution scope', () => {
  for (const namespace of ['global', 'rhino.global']) {
    const rows=fixture(); const result=run(rows,true,{application:'global',namespace});
    assert.equal(result.receipt.status,'applied',namespace);
    assert.equal(result.receipt.execution_scope,namespace);
    assert.equal(result.writes.length,3);
    for (const id of [tool,chat,voice,binding]) assert.equal(rows[id].values.sys_scope,scope);
  }
});
test('non-Global execution is rejected before any update, even in the target application', () => {
  const result=run(fixture(),true,{application:scope,namespace:'sn_generative_ai'});
  assert.equal(result.receipt.status,'aborted'); assert.equal(result.receipt.error,'global_scope_required');
  assert.equal(result.receipt.execution_scope,'sn_generative_ai'); assert.deepEqual(result.writes,[]);
});
