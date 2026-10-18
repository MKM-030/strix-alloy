// Local behavioral checks. No ServiceNow/network access.
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');
const path = require('node:path').join(__dirname, 'scc-batch-capture.js');
const original = fs.readFileSync(path, 'utf8');
function run(options = {}, state) {
  let source = options.compactSource || original;
  if (!options.plan) source = source.replace("var MODE = 'plan';", "var MODE = 'capture';");
  if (options.frozen) source = source.replace('var FROZEN_MANIFEST = [];', 'var FROZEN_MANIFEST = ' + JSON.stringify(options.frozen) + ';');
  if (options.complete) source = source.replace('var COMPLETE_AFTER_VERIFICATION = false;', 'var COMPLETE_AFTER_VERIFICATION = true;');
  if (options.confirmed) source = source.replace('var FINAL_MANIFEST_CONFIRMED = false;', 'var FINAL_MANIFEST_CONFIRMED = true;');
  const seeds = vm.runInNewContext('[' + original.match(/var SEEDS = \[([\s\S]*?)\n    \];/)[1] + ']');
  const db = state?.db || {};
  const types = {}, fields = {};
  let selected = 'original', seq = state?.seq || 1000, writes = 0, output;
  function put(table, row) { (db[table] ||= []).push(row); return row; }
  function make(table, id, extra = {}) { return {sys_id:id, sys_scope:'global', sys_updated_on:'2026-10-12 15:00:00',sys_mod_count:'1', ...extra}; }
  if (!state) {
    const extra = vm.runInNewContext('[' + original.match(/var EXTRA_MANIFEST = \[([\s\S]*?)\n    \];/)[1] + ']');
    for (const [table,id] of [...seeds,...extra]) put(table,make(table,id));
    db.sys_agent_access_role_mapping[0].role='282bf1fac6112285017366cb5f867469';
    db.sys_agent_access_role_mapping[1].role='2831a114c611228501d4ea6c309d626d';
    put('sys_security_acl_role',make('sys_security_acl_role','55555555555555555555555555555555',{sys_security_acl:'115c870393b38354e7f2b9fa6aba10a6',sys_user_role:'2831a114c611228501d4ea6c309d626d'}));
    put('sys_security_acl_role',make('sys_security_acl_role','66666666666666666666666666666666',{sys_security_acl:'c9393ac793fb4354e7f2b9fa6aba108d',sys_user_role:'2831a114c611228501d4ea6c309d626d'}));
    put('sys_security_acl_role',make('sys_security_acl_role','77777777777777777777777777777777',{sys_security_acl:'88888888888888888888888888888888',sys_user_role:'2831a114c611228501d4ea6c309d626d'}));
    for (const row of db.sn_aia_agent) row.sys_scope='aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
    put('sys_scope', {sys_id:'global',scope:'global'});
    put('sys_scope', {sys_id:'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',scope:'sn_test'});
    for (const table of ['sys_db_object','sys_dictionary','sys_update_set','sys_update_xml','question_choice','catalog_script_client','catalog_ui_policy','catalog_ui_policy_action','sc_cat_item_category','sc_cat_item_catalog']) db[table] ||= [];
    put('sys_dictionary',{name:'sys_agent_access_role_mapping',element:'role',reference:'sys_user_role'});
    put('sys_dictionary',{name:'sys_security_acl_role',element:'sys_user_role',reference:'sys_user_role'});
    const newAgent='a4a9438393738354e7f2b9fa6aba101d';
    put('sn_aia_skill_metadata',make('sn_aia_skill_metadata','11111111111111111111111111111111',{document_table:'sn_aia_agent',document_id:newAgent}));
    put('sn_aia_skill_metadata',make('sn_aia_skill_metadata','22222222222222222222222222222222',{document_table:'sn_aia_agent',document_id:'e850ba4f933b4354e7f2b9fa6aba105d'}));
    put('sn_aia_skill_metadata',make('sn_aia_skill_metadata','33333333333333333333333333333333',{document_table:'sn_aia_agent',document_id:'5287ce9c93d64f145c8132d47aba1060'}));
    put('sn_aia_skill_metadata',make('sn_aia_skill_metadata','44444444444444444444444444444444',{document_table:'unrelated_table',document_id:newAgent}));
    put('sn_aia_agent_config',make('sn_aia_agent_config','bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',{agent:newAgent,sys_scope:'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'}));
    put('sn_aia_version',make('sn_aia_version','cccccccccccccccccccccccccccccccc',{agent:newAgent,sys_scope:'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'}));
    put('sn_aia_agent_tool_m2m',make('sn_aia_agent_tool_m2m','dddddddddddddddddddddddddddddddd',{agent:newAgent,tool:'eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee',sys_scope:'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'}));
    for (const table of ['sn_aia_agent_config','sn_aia_version','sn_aia_agent_tool_m2m']) put('sys_dictionary',{name:table,element:'agent',reference:'sn_aia_agent'});
  }
  for (const table of Object.keys(db)) {
    fields[table]=new Set(['sys_id']);
    for (const row of db[table]) for(const k of Object.keys(row)) fields[table].add(k);
  }
  for (const table of ['sn_aia_agent_config','sn_aia_version','sn_aia_agent_tool_m2m']) fields[table].add('agent');
  fields.sn_aia_agent_tool_m2m.add('tool');
  ['name','application','state','parent','batch_base','description'].forEach(f=>fields.sys_update_set.add(f));
  if (options.sourceSecret) { db.sc_cat_item[0].client_secret='DO_NOT_LEAK'; fields.sc_cat_item.add('client_secret'); }
  const op = (v,o,x) => o==='IN' ? String(x).split(',').includes(String(v)) : o==='STARTSWITH' ? String(v ?? '').startsWith(String(x)) : o==='NOTNULL' ? v!==undefined && v!==null && v!=='' : String(v ?? '')===String(x);
  class GR {
    constructor(table) {this.table=table;this.filters=[];this.limit=Infinity;this.row=null;}
    isValid(){return !!db[this.table];}
    isValidField(f){return !!fields[this.table]?.has(f);}
    get(id){this.row=db[this.table]?.find(r=>r.sys_id===String(id));return !!this.row;}
    addQuery(f,o,x){if(arguments.length===2){x=o;o='=';}this.filters.push(r=>op(r[f],o,x));return this;}
    addNotNullQuery(f){this.filters.push(r=>op(r[f],'NOTNULL'));}
    setLimit(n){this.limit=n;}
    query(){this.rows=db[this.table].filter(r=>this.filters.every(f=>f(r))).slice(0,this.limit);this.index=0;}
    next(){this.row=this.rows[this.index++];return !!this.row;}
    getUniqueValue(){return this.row.sys_id;}
    getRecordClassName(){return this.table;}
    getValue(f){return this.row[f] ?? '';}
    initialize(){this.row={};}
    setValue(k,v){this.row[k]=v;}
    insert(){this.row.sys_id=(++seq).toString(16).padStart(32,'0');if(this.table==='sys_update_set')this.row.batch_base=this.row.parent||'';db[this.table].push(this.row);writes++;return this.row.sys_id;}
    update(){writes++;return this.row.sys_id;}
    getElements(){const row=this.row;const a=Object.keys(row).map(f=>({getName:()=>f,getED:()=>({getInternalType:()=>f==='sys_scope'||f==='tool'||f==='agent'?'reference':'string'})}));return {size:()=>a.length,get:i=>a[i]};}
  }
  let saves=0;
  function GlideSet(){this.set=function(id){if(!options.selectionFailure||id==='original')selected=String(id);};}
  function Manager(){this.saveRecord=function(gr){
    saves++;
    const name=gr.table+'_'+gr.row.sys_id;
    let row=db.sys_update_xml.find(r=>r.name===name&&r.update_set===selected);
    if(options.stale && row)return;
    if(!row){row={sys_id:(++seq).toString(16).padStart(32,'0'),name,update_set:selected};db.sys_update_xml.push(row);}
    row.application=options.scopeMismatch?'wrong':gr.row.sys_scope;
    row.action='INSERT_OR_UPDATE';
    row.payload='<record_update><'+gr.table+'><sys_id>'+gr.row.sys_id+'</sys_id><sys_updated_on>'+gr.row.sys_updated_on+'</sys_updated_on><sys_mod_count>'+gr.row.sys_mod_count+'</sys_mod_count><client_secret><![CDATA['+(options.xmlSecret?'DO_NOT_LEAK':'')+']]></client_secret></'+gr.table+'></record_update>';
    writes++;
    if(options.driftBeforeLaterSave&&saves===1)db.sc_cat_item[0].sys_mod_count='2';
    if(options.driftAfterLastSave&&saves===51)db.sn_aia_agent[0].sys_mod_count='2';
    if(options.xmlScopeDriftAfterLastSave&&saves===51)db.sys_update_xml[0].application='wrong';
    if(options.extraUpdate&&saves===1)db.sys_update_xml.push({sys_id:'99999999999999999999999999999999',update_set:selected,name:'unplanned',payload:''});
    if(options.extraChild&&saves===1)db.sys_update_set.push({sys_id:'99999999999999999999999999999999',parent:db.sys_update_set.find(r=>r.sys_id===selected).parent,application:'global',state:'in progress'});
  };}
  function XML(){this.parseXML=x=>this.xml=x;this.getNodeText=x=>{const field=x.split('/').pop();return (this.xml.match(new RegExp('<'+field+'>([^<]*)</'+field+'>'))||[])[1]||'';};}
  const gs={hasRole:()=>true,getPreference:()=>selected,info:s=>{output=JSON.parse(s.replace(/^\[SCC (?:(?:Batch (?:Capture|Plan))|(?:Frozen Capture))\] /,''));}};
  vm.runInNewContext(source,{GlideRecord:GR,GlideUpdateSet:GlideSet,GlideUpdateManager2:Manager,XMLDocument2:XML,gs});
  return {output,db,selected,seq,writes,saves};
}
const plan=run({plan:true});
assert.equal(plan.output.ok,true,plan.output.error);assert.equal(plan.writes,0);assert.equal(plan.output.status,'planned');
const frozen=plan.output.frozen_manifest_candidate;
const compact=run({plan:true,compactSource:fs.readFileSync(require('node:path').join(__dirname, 'scc-batch-plan-compact.js'),'utf8')});
assert.equal(compact.output.ok,true,compact.output.error);assert.equal(compact.writes,0);assert.deepEqual(compact.output.frozen_manifest_candidate,frozen);
assert.deepEqual(compact.output.prerequisites,plan.output.prerequisites);
assert.equal(plan.output.prerequisites.filter(r=>r.kind==='existing_role').length,2);
assert(!frozen.some(r=>['6882f6c7937b4354e7f2b9fa6aba105e','5782fac7937b4354e7f2b9fa6aba10ea'].includes(r[1])));
const compactCaptureSource=fs.readFileSync(require('node:path').join(__dirname, 'scc-batch-capture-compact.js'),'utf8');
const compactCapture=run({frozen,compactSource:compactCaptureSource});
assert.equal(compactCapture.output.ok,true,compactCapture.output.error);
assert.equal(compactCapture.output.status,'in progress');assert.equal(compactCapture.selected,'original');
assert.deepEqual(compactCapture.output.frozen_manifest_candidate,frozen);
const compactUnfrozen=run({compactSource:compactCaptureSource});
assert.equal(compactUnfrozen.output.ok,false);assert.equal(compactUnfrozen.writes,0);
const frozenExecutorSource=fs.readFileSync(require('node:path').join(__dirname, 'scc-batch-capture-frozen.js'),'utf8');
const exact=run({frozen,compactSource:frozenExecutorSource});
assert.equal(exact.output.ok,true,JSON.stringify(exact.output));assert.equal(exact.output.status,'in progress');
assert.equal(exact.output.captured,51);assert.equal(exact.selected,'original');assert(exact.db.sys_update_set.every(r=>r.state==='in progress'));
const exactAgain=run({frozen,compactSource:frozenExecutorSource},exact);
assert.equal(exactAgain.output.ok,true,exactAgain.output.error);assert.equal(exactAgain.db.sys_update_set.length,3);assert.equal(exactAgain.db.sys_update_xml.length,51);
for(const bad of [{},{selectionFailure:true},{scopeMismatch:true},{sourceSecret:true},{xmlSecret:true}]){
 const x=run({...bad,...(Object.keys(bad).length?{frozen}:{}),compactSource:frozenExecutorSource});
 assert.equal(x.output.ok,false,JSON.stringify(bad));assert.equal(x.selected,'original');
 if(!Object.keys(bad).length||bad.sourceSecret)assert.equal(x.writes,0);
 assert(!JSON.stringify(x.output).includes('DO_NOT_LEAK'));
}
exact.db.sc_cat_item[0].sys_mod_count='2';
const exactDrift=run({frozen,compactSource:frozenExecutorSource},exact);
assert.equal(exactDrift.output.ok,false);assert.equal(exactDrift.writes,0);assert(exactDrift.output.error.includes('differs from frozen'));
const exactReplan=run({plan:true},exact);
const exactStale=run({stale:true,frozen:exactReplan.output.frozen_manifest_candidate,compactSource:frozenExecutorSource},exact);
assert.equal(exactStale.output.ok,false);assert(exactStale.output.error.includes('identity/revision mismatch'));assert.equal(exactStale.selected,'original');
for(const mutation of ['driftBeforeLaterSave','driftAfterLastSave','xmlScopeDriftAfterLastSave','extraUpdate','extraChild']){
 const x=run({[mutation]:true,frozen,compactSource:frozenExecutorSource});
 assert.equal(x.output.ok,false,mutation);assert.equal(x.output.status,'requires review');assert.equal(x.selected,'original',mutation);
 if(mutation.startsWith('drift'))assert(x.output.error.includes('differs from frozen'),x.output.error);
 if(mutation==='extraUpdate')assert(x.output.error.includes('Unexpected customer update'));
 if(mutation==='extraChild')assert(x.output.error.includes('Unexpected batch descendant'));
}
const valid=run({frozen},plan);
assert.equal(valid.output.ok,true,JSON.stringify(valid.output));
assert.equal(valid.output.status,'in progress');assert.equal(valid.selected,'original');
assert.equal(valid.output.manifest.length,51);assert.equal(valid.db.sys_update_set.length,3);
assert.deepEqual(valid.output.manifest.filter(r=>r.table==='sys_security_acl_role').map(r=>r.sys_id).sort(),['55555555555555555555555555555555','66666666666666666666666666666666']);
assert(valid.output.manifest.some(r=>r.table==='sys_generative_ai_custom_llm_transformer'&&r.sys_id==='bc126377936f8750e7f2b9fa6aba1012'&&r.scope==='global'));
assert(valid.output.manifest.some(r=>r.table==='sys_generative_ai_config'&&r.sys_id==='4780c7e193f747d0e7f2b9fa6aba1030'));
assert.deepEqual(valid.output.manifest.filter(r=>r.table==='sn_aia_skill_metadata').map(r=>r.sys_id).sort(),['11111111111111111111111111111111','22222222222222222222222222222222']);
assert.equal(valid.output.discovery.find(r=>r.status==='queried_exact_polymorphic_agent_ids').included.length,2);
assert(valid.db.sys_update_set.every(r=>r.state==='in progress'));assert(!JSON.stringify(valid.output).includes('DO_NOT_LEAK'));
const again=run({frozen},valid);
assert.equal(again.output.ok,true,again.output.error);assert.equal(again.db.sys_update_set.length,3);assert.equal(again.db.sys_update_xml.length,51);
const unfrozen=run();assert.equal(unfrozen.output.ok,false);assert.equal(unfrozen.writes,0);
const secret=run({sourceSecret:true,frozen});assert.equal(secret.output.ok,false);assert.equal(secret.writes,0);assert(!JSON.stringify(secret.output).includes('DO_NOT_LEAK'));
const badSelect=run({selectionFailure:true,frozen});assert.equal(badSelect.output.ok,false);assert.equal(badSelect.saves,0);assert.equal(badSelect.selected,'original');
const wrongScope=run({scopeMismatch:true,frozen});assert.equal(wrongScope.output.ok,false);assert.equal(wrongScope.selected,'original');
const xmlSecret=run({xmlSecret:true,frozen});assert.equal(xmlSecret.output.ok,false);assert.equal(xmlSecret.selected,'original');assert(!JSON.stringify(xmlSecret.output).includes('DO_NOT_LEAK'));
const unconfirmed=run({complete:true,frozen});assert.equal(unconfirmed.output.ok,false);assert.equal(unconfirmed.writes,0);
const completed=run({complete:true,confirmed:true,frozen});assert.equal(completed.output.ok,true,completed.output.error);assert(completed.db.sys_update_set.every(r=>r.state==='complete'));assert.equal(completed.selected,'original');
valid.db.sc_cat_item[0].sys_mod_count='2';
const changed=run({frozen},valid);assert.equal(changed.output.ok,false);assert.equal(changed.writes,0);assert(changed.output.error.includes('differs from frozen'));
const revisedPlan=run({plan:true},valid);
const stale=run({stale:true,frozen:revisedPlan.output.frozen_manifest_candidate},valid);assert.equal(stale.output.ok,false);assert(stale.output.error.includes('current source revision'));assert.equal(stale.selected,'original');
console.log('PASS: read-only plan, frozen capture routing/discovery, WIP default, idempotent rerun, source-secret rejection, selection/scope failures, empty/secret CDATA, completion gate, restoration, source drift and stale XML rejection.');
