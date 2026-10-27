'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const crypto = require('node:crypto');
const path = require('node:path');
const file = path.join(__dirname, 'scc-name-confirmation-patch.js');
const scope = '7cc4ec81533121106b38ddeeff7b12ee';
const ids = ['a4a9438393738354e7f2b9fa6aba101d', 'a6337ddf93f787105c8132d47aba1058'];
const sha = value => crypto.createHash('sha256').update(value, 'utf8').digest('hex');
// Synthetic instruction records: deliberately do not use an old live export as current truth.
function fixture() {
  const before = '1. Originale Anfrage exakt erhalten.\n2. Angemeldeten Anforderer und Vorgesetzten autorisiert nachschlagen.\n3. Fehlende Angaben erfragen.\n4. Vollständige Bestellzusammenfassung ausdrücklich bestätigen lassen.\n5. Genau einmal absenden; bei unklarem Ergebnis niemals automatisch wiederholen.\n6. Nur tatsächliche Ergebnisse nennen.\n';
  const records = ids.map((id, index) => ({table:'sn_aia_agent',sys_id:id,sys_scope:scope,
    name:'SCC synthetic ' + index,role:'Unveränderte Rolle ' + index,instructions:before + 'Original ' + index,
    instructions_sha256:sha(before + 'Original ' + index)}));
  const binding = {version:1,source:'fresh_authenticated_ui_read',captured_at:'2026-10-24T12:00:00Z',records};
  const rows = Object.fromEntries(records.map(row=>[row.sys_id,{...row}]));
  return {binding, rows};
}
function run(state, mode='dry_run', options={}) {
  const writes=[],logs=[],loads={};
  class GR {
    constructor(table) { this.table=table; this.pending={}; }
    get(id) {
      this.id=id; loads[id]=(loads[id]||0)+1;
      if (options.onGet) options.onGet(id,loads[id],state.rows);
      this.row=state.rows[id]; return !!this.row && this.table===this.row.table;
    }
    isValidField(field) { return Object.hasOwn(this.row,field); }
    getValue(field) { return this.row[field]; }
    canWrite() { return this.id!==options.denyRecord; }
    getElement() { return {canWrite:()=>this.id!==options.denyField,getED:()=>({getLength:()=>this.id===options.shortField?100:65535})}; }
    setValue(field,value) { this.pending[field]=value; }
    update() {
      if(this.id===options.failUpdate) return null;
      Object.assign(this.row,this.pending);
      writes.push({id:this.id,fields:Object.keys(this.pending)});
      if(options.afterUpdate) options.afterUpdate(this.id,state.rows);
      return this.id;
    }
  }
  // Missing implementation is represented as an empty patch, so RED is behavioral.
  const source=fs.existsSync(file)?fs.readFileSync(file,'utf8'):'';
  vm.runInNewContext(source,{SCC_NAME_CONFIRMATION_BINDING:options.unbound?undefined:state.binding,
    SCC_NAME_CONFIRMATION_MODE:mode,GlideRecord:GR,
    GlideDigest:class{getSHA256Hex(value){return sha(String(value));}},
    gs:{hasRole:()=>options.admin!==false,getCurrentScopeName:()=>options.namespace||'global',info:value=>logs.push(value)}});
  const last=logs.at(-1);
  return {writes,loads,receipt:last?JSON.parse(last.replace(/^\[SCC NAME PATCH\] /,'')):null};
}
test('dry run binds both exact fresh records, plans only instructions, and performs no writes',()=>{
  const state=fixture(), result=run(state);
  assert.ok(result.receipt,'patch must produce a bounded reviewable receipt');
  assert.equal(result.receipt.status,'dry_run');
  assert.equal(result.receipt.planned.length,2); assert.deepEqual(result.writes,[]);
  for(const item of result.receipt.planned){assert.equal(item.field,'instructions');assert.equal(item.before,sha(state.rows[item.id].instructions));assert.notEqual(item.after,item.before);}
});
test('apply appends one name gate and preserves all original instructions and roles; exact rerun is no-op',()=>{
  const state=fixture(), originals=structuredClone(state.rows), result=run(state,'apply');
  assert.equal(result.receipt.status,'applied');
  assert.deepEqual(result.writes,ids.map(id=>({id,fields:['instructions']})));
  for(const id of ids){
    const actual=state.rows[id].instructions;
    assert.ok(actual.startsWith(originals[id].instructions+'\n\n'));
    assert.equal(state.rows[id].role,originals[id].role);
    assert.match(actual,/scc_name_confirmation_20261024/);
    assert.match(actual,/buchstabieren/i); assert.match(actual,/Bestellbestätigung/);
    assert.match(actual,/Original.*unverändert/);
  }
  const again=run(state,'apply');assert.equal(again.receipt.status,'already_applied');assert.deepEqual(again.writes,[]);
});
test('last target instruction, role, name, scope, missing record or field drift prevents every write',()=>{
  for(const change of [s=>s.rows[ids[1]].instructions+=' drift',s=>s.rows[ids[1]].role+=' drift',s=>s.rows[ids[1]].name+=' drift',s=>s.rows[ids[1]].sys_scope='wrong',s=>delete s.rows[ids[1]],s=>delete s.rows[ids[1]].instructions]){
    const state=fixture();change(state);const result=run(state,'apply');
    assert.equal(result.receipt.status,'aborted');assert.deepEqual(result.writes,[]);
  }
});
test('binding must contain both distinct approved targets, authentic fresh-read provenance and exact before hashes',()=>{
  for(const change of [s=>s.binding.records.pop(),s=>s.binding.records[1]=s.binding.records[0],s=>s.binding.records[1].sys_id='unapproved',s=>s.binding.records[0].instructions_sha256='0'.repeat(64),s=>s.binding.source='historical_export',s=>s.binding.captured_at='unknown']){
    const state=fixture();change(state);const result=run(state,'apply');
    assert.equal(result.receipt.status,'aborted');assert.deepEqual(result.writes,[]);
  }
  const unbound=run(fixture(),'apply',{unbound:true});assert.equal(unbound.receipt.status,'aborted');assert.deepEqual(unbound.writes,[]);
});
test('admin, Global scope and all field ACLs are checked before writes',()=>{
  for(const options of [{admin:false},{namespace:'sn_generative_ai'},{denyRecord:ids[1]},{denyField:ids[1]}]){
    const result=run(fixture(),'apply',options);assert.equal(result.receipt.status,'aborted');assert.deepEqual(result.writes,[]);
  }
});
test('drift after all-target preflight but before first update is rejected without writes',()=>{
  const result=run(fixture(),'apply',{onGet:(id,count,rows)=>{if(id===ids[1]&&count===2)rows[id].instructions+=' concurrent';}});
  assert.equal(result.receipt.status,'aborted');assert.deepEqual(result.writes,[]);
});
test('partial failure is explicit, never auto retried or rolled back; mixed exact state can be resumed',()=>{
  const state=fixture(), result=run(state,'apply',{failUpdate:ids[1]});
  assert.equal(result.receipt.status,'partial_or_uncertain');assert.deepEqual(result.writes.map(x=>x.id),[ids[0]]);
  assert.equal(result.receipt.attempted.length,2);
  const retry=run(state,'apply');assert.equal(retry.receipt.status,'applied');assert.deepEqual(retry.writes.map(x=>x.id),[ids[1]]);
});
test('exact guarded rollback restores original instructions only, repeats no-op and preflights last-target drift',()=>{
  const state=fixture(), originals=structuredClone(state.rows);assert.equal(run(state,'apply').receipt.status,'applied');
  const review=run(state,'rollback_dry_run');assert.equal(review.receipt.status,'dry_run');assert.deepEqual(review.writes,[]);
  state.rows[ids[1]].instructions+=' edit';const rejected=run(state,'rollback');assert.equal(rejected.receipt.status,'aborted');assert.deepEqual(rejected.writes,[]);
  state.rows[ids[1]].instructions=originals[ids[1]].instructions;
  const rollback=run(state,'rollback');assert.equal(rollback.receipt.status,'rolled_back');assert.deepEqual(rollback.writes.map(x=>x.id),[ids[0]]);
  assert.deepEqual(state.rows,originals);const again=run(state,'rollback');assert.equal(again.receipt.status,'already_rolled_back');assert.deepEqual(again.writes,[]);
});
test('complete rollback restores both exact originals and never changes roles, names or other metadata',()=>{
  const state=fixture(), originals=structuredClone(state.rows);
  state.rows[ids[0]].unrelated='preserve me';originals[ids[0]].unrelated='preserve me';
  assert.equal(run(state,'apply').receipt.status,'applied');
  const result=run(state,'rollback');assert.equal(result.receipt.status,'rolled_back');
  assert.deepEqual(result.writes,ids.map(id=>({id,fields:['instructions']})));assert.deepEqual(state.rows,originals);
});
test('concurrent edit after first update is retained and prevents touching the second target',()=>{
  const state=fixture(), original=state.rows[ids[1]].instructions;
  const result=run(state,'apply',{afterUpdate:(id,rows)=>{if(id===ids[0])rows[ids[1]].instructions+=' administrator edit';}});
  assert.equal(result.receipt.status,'partial_or_uncertain');assert.deepEqual(result.writes.map(x=>x.id),[ids[0]]);
  assert.equal(state.rows[ids[1]].instructions,original+' administrator edit');
});
test('reversed binding order is stable and unsupported extra fields or before truncation fail closed',()=>{
  const state=fixture();state.binding.records.reverse();
  assert.deepEqual(run(state,'apply').writes.map(x=>x.id),ids);
  for(const change of [s=>s.binding.records[0].unexpected='x',s=>s.binding.unexpected='x',s=>s.binding.records[0].instructions=s.binding.records[0].instructions.slice(0,-1)]){
    const changed=fixture();change(changed);const result=run(changed,'apply');assert.equal(result.receipt.status,'aborted');assert.deepEqual(result.writes,[]);
  }
});
test('readback mutation produces uncertainty and never another attempt',()=>{
  const result=run(fixture(),'apply',{afterUpdate:(id,rows)=>{rows[id].instructions+=' business rule edit';}});
  assert.equal(result.receipt.status,'partial_or_uncertain');assert.equal(result.writes.length,1);assert.equal(result.receipt.attempted.length,1);
});
test('unknown mode and an already-marked before binding cannot trigger any update',()=>{
  let result=run(fixture(),'unknown');assert.equal(result.receipt.status,'aborted');assert.deepEqual(result.writes,[]);
  const state=fixture();state.binding.records[1].instructions+='\n<scc_name_confirmation_20261024>';state.binding.records[1].instructions_sha256=sha(state.binding.records[1].instructions);
  result=run(state,'apply');assert.equal(result.receipt.status,'aborted');assert.deepEqual(result.writes,[]);
});
test('insufficient last-target dictionary field length rejects all writes before possible truncation',()=>{
  const result=run(fixture(),'apply',{shortField:ids[1]});
  assert.equal(result.receipt.status,'aborted');assert.deepEqual(result.writes,[]);
});
test('actual ISO UTC offset with microseconds is valid fresh-read metadata',()=>{
  const state=fixture();state.binding.captured_at='2026-10-24T08:08:00.773221+00:00';
  const result=run(state);assert.equal(result.receipt.status,'dry_run');assert.deepEqual(result.writes,[]);
});
