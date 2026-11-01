'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const templatePath=path.join(__dirname,'apply-halogen-agent-configuration.template.js');
const clone=x=>JSON.parse(JSON.stringify(x));
const id=n=>n.toString(16).padStart(32,'0');
function fixture(){
  const targets=Array.from({length:66},(_,n)=>({table:'sys_generative_ai_config',id:id(n+1),scope:'32808450431302106c3603295bb8f245',field:'model',before:{sys_id:id(n+1),sys_scope:'32808450431302106c3603295bb8f245',sys_updated_on:'2026-11-01 12:00:00',sys_mod_count:'1',name:'Prompt '+n,model:'Gemma 4 26B-A4B',active:'true',state:'published',prompt:'Keep <instructions> & schema '+n,definition:'4f80c7e193f747d0e7f2b9fa6aba1027',definition_table:'sys_one_extend_capability_definition'},desired:'halogen-v2'}));
  for(const [n,table,field] of [[67,'sys_generative_ai_custom_llm_transformer','request_transformer'],[68,'sys_script_include','script']])targets.push({table,id:id(n),scope:'global',field,before:{sys_id:id(n),sys_scope:'global',sys_updated_on:'2026-11-01 12:00:00',sys_mod_count:'1',[field]:'old code '+n},desired:'new code '+n});
  const gates=['automation_enabled','apply_enabled','serialized_execution_verified'].map((n,i)=>({table:'sys_properties',id:id(101+i),before:{sys_id:id(101+i),name:'custom_llm.prompt_mirror.'+n,value:'false',sys_mod_count:'1'}}));
  const model={table:'sys_generative_ai_model_config',id:'ff74fcef93a70350e7f2b9fa6aba10ea',before:{sys_id:'ff74fcef93a70350e7f2b9fa6aba10ea',model:'halogen-v2',active:'true',lifecycle_state:'active',provider:'07ca9d94c3550210b0939bc8a840ddeb',connection:'7040f46393a70350e7f2b9fa6aba1083',sys_mod_count:'2'}};
  const inactive={table:'sys_generative_ai_config',id:id(199),before:{sys_id:id(199),active:'false',model:'Gemma 4 26B-A4B',sys_mod_count:'1'}};
  return {schema:1,targetCount:68,promptCount:66,name:'Custom LLM Platform 2.3 - Halogen Agent Delta - NO DELETE 20261101',marker:'HALOGEN_AGENT_DELTA_V1_TEST',aiaScope:'32808450431302106c3603295bb8f245',baseline:'310e1af39388db545c8132d47aba104b',targets,guards:[...gates,model,inactive],companions:[]};
}
// Only the native database/capture boundary is simulated. The real deployment
// algorithm runs unchanged; unexpected methods and constructor arguments throw.
function platform(plan,options={}){
  const db={sys_update_set:[],sys_update_xml:[],sys_es_latest_script:[]};
  for(const item of [...plan.targets,...plan.guards]){db[item.table]??=[];db[item.table].push({...clone(item.before),unqueried_contract:'must survive'});}
  let selected='original-set',seq=1000,writes=[],receipt=null,captures=0;
  const enc=s=>String(s).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;');
  const dec=s=>s.replaceAll('&lt;','<').replaceAll('&gt;','>').replaceAll('&amp;','&');
  class GR{
    constructor(table){this.table=table;this.filters=[];this.row=null;this.limit=Infinity;}
    isValid(){return !!db[this.table];} isValidField(f){return !!this.row&&Object.hasOwn(this.row,f);}
    get(key){this.row=db[this.table]?.find(r=>r.sys_id===key);return !!this.row;}
    getUniqueValue(){return this.row.sys_id;} getRecordClassName(){return this.table;}
    canRead(){return true;} canWrite(){return !options.denyWrite;}
    getValue(f){return this.row[f]??'';} setValue(f,v){this.row[f]=String(v);}
    getElement(f){return {canRead:()=>true,canWrite:()=>!options.denyWrite,getName:()=>f};}
    getElements(){const fields=Object.keys(this.row).map(f=>this.getElement(f));return {size:()=>fields.length,get:i=>fields[i]};}
    addQuery(f,op,v){this.filters.push([f,v===undefined?'=':op,v===undefined?op:v]);}
    setLimit(n){this.limit=n;} query(){this.results=(db[this.table]||[]).filter(r=>this.filters.every(([f,op,v])=>op==='IN'?String(v).split(',').includes(r[f]??''):(r[f]??'')===String(v))).slice(0,this.limit);this.cursor=0;}
    next(){this.row=this.results[this.cursor++];return !!this.row;}
    initialize(){this.row={};}
    insert(){this.row.sys_id=id(++seq);if(this.table==='sys_update_set')this.row.batch_base=this.row.parent||'';db[this.table].push(this.row);writes.push({table:this.table,id:this.row.sys_id,kind:'insert'});options.afterInsert?.(this.row,this.table,db);return this.row.sys_id;}
    update(){
      writes.push({table:this.table,id:this.row.sys_id,kind:'update'});
      this.row.sys_mod_count=String(Number(this.row.sys_mod_count||0)+1);this.row.sys_updated_on='2026-11-01 13:00:00';this.row.sys_updated_by='native-user';
      if(this.table==='sys_generative_ai_config')this.row.request_tokens='8192';
      options.afterUpdate?.(this.row,this.table,writes);
      return this.row.sys_id;
    }
  }
  class UpdateSet{set(value){selected=value;options.afterSelect?.(value,db);}}
  class Manager{
    constructor(){assert.equal(arguments.length,0,'manager must use selected context, not constructor argument');}
    saveRecord(gr){
      captures++;
      if(options.captureThrow===captures)throw Error('simulated native capture failure');
      const name=gr.row.sys_update_name||gr.table+'_'+gr.row.sys_id;
      let u=db.sys_update_xml.find(r=>r.name===name&&r.update_set===selected);
      if(!u){u={sys_id:id(++seq),name,update_set:selected};db.sys_update_xml.push(u);writes.push({table:'sys_update_xml',id:u.sys_id,kind:'capture'});}
      Object.assign(u,{application:gr.row.sys_scope,action:'INSERT_OR_UPDATE',payload:'<record_update table="'+gr.table+'"><'+gr.table+' action="INSERT_OR_UPDATE">'+Object.entries(gr.row).map(([k,v])=>'<'+k+'>'+enc(v)+'</'+k+'>').join('')+'</'+gr.table+'></record_update>'});
      if(options.serializeCompanions)for(const c of plan.companions||[])if(c.owner===gr.row.sys_id){const row=db.sys_es_latest_script.find(r=>r.sys_id===c.id);u.payload=u.payload.replace('</record_update>','<sys_es_latest_script action="INSERT_OR_UPDATE">'+Object.entries(row).map(([k,v])=>'<'+k+'>'+enc(v)+'</'+k+'>').join('')+'</sys_es_latest_script></record_update>');}
      options.afterCapture?.(u,captures,db);
    }
  }
  class XML{
    parseXML(xml){this.xml=xml;return true;}
    getDocumentElement(){const m=this.xml.match(/^<record_update table="([^"]+)">/);return m?{getAttribute:n=>n==='table'?m[1]:'',getNodeName:()=>'record_update'}:null;}
    getNodeText(xpath){const parts=xpath.split('/').filter(Boolean),field=parts.at(-1),table=parts.at(-2),record=this.xml.match(new RegExp('<'+table+'(?:\\s[^>]*?)?>([\\s\\S]*?)</'+table+'>'));const m=record?.[1].match(new RegExp('<'+field+'>([\\s\\S]*?)</'+field+'>'));return m?dec(m[1]):'';}
  }
  const context={GlideRecordSecure:GR,GlideRecord:GR,GlideUpdateSet:UpdateSet,GlideUpdateManager2:Manager,XMLDocument2:XML,
    gs:{hasRole:r=>r==='admin',getPreference:()=>selected,info:message=>{receipt=JSON.parse(message.slice(message.indexOf('{')));}}};
  function run(){receipt=null;const template=fs.existsSync(templatePath)?fs.readFileSync(templatePath,'utf8'):'';vm.runInNewContext(template.replace('/*__FROZEN_PLAN__*/',JSON.stringify(plan)),context);return receipt;}
  return {db,writes,run,get selected(){return selected;},get captures(){return captures;}};
}
test('last-target drift prevents every database write',()=>{
  const plan=fixture(),p=platform(plan);p.db.sys_script_include[0].script='concurrent edit';
  const r=p.run();assert.ok(r,'deployment must emit its review receipt');assert.equal(r.ok,false);assert.match(r.error,/drift|preimage/i);assert.equal(p.writes.length,0);assert.equal(p.selected,'original-set');
});
test('successful apply changes only intended contract and captures exactly68 records; rerun writes nothing',()=>{
  const plan=fixture(),p=platform(plan),original=clone(p.db);const r=p.run();assert.ok(r,'deployment must emit receipt');assert.equal(r.ok,true,r.error);assert.equal(r.verified,68);assert.equal(r.captured,68);assert.equal(p.db.sys_update_set.length,3);assert.equal(p.db.sys_update_xml.length,68);assert.equal(p.selected,'original-set');
  for(const t of plan.targets){const row=p.db[t.table].find(x=>x.sys_id===t.id);assert.equal(row[t.field],t.desired);for(const [k,v] of Object.entries(original[t.table].find(x=>x.sys_id===t.id)))if(k!==t.field&&!['sys_updated_on','sys_mod_count'].includes(k))assert.equal(row[k],v,'unintended '+k);}
  const count=p.writes.length,again=p.run();assert.equal(again.ok,true,again.error);assert.equal(again.status,'already_applied');assert.equal(p.writes.length,count);assert.equal(p.selected,'original-set');
});
test('native side effect on an unrelated readable field is detected and original context restored',()=>{
  const p=platform(fixture(),{afterUpdate:row=>{row.unqueried_contract='BR modified';}});const r=p.run();assert.ok(r);assert.equal(r.ok,false);assert.match(r.error,/contract/i);assert.equal(p.selected,'original-set');
});
test('capture failure restores context and reports partial writes without automatic retry',()=>{
  const p=platform(fixture(),{captureThrow:2});const r=p.run();assert.ok(r);assert.equal(r.ok,false);assert.equal(r.status,'partial_or_uncertain');assert.equal(p.selected,'original-set');assert.equal(p.captures,2);
});
test('an uncertain first set insert is reported as partial even when no source update began',()=>{
  const p=platform(fixture(),{afterInsert:()=>{throw Error('native insert failed after committing');}}),r=p.run();assert.equal(r.ok,false);assert.equal(r.status,'partial_or_uncertain');assert.equal(r.source_writes,0);assert.equal(p.db.sys_update_set.length,1);assert.equal(p.selected,'original-set');
});
test('captures only an explicitly frozen native ES companion tied to the exact owned code record',()=>{
  const plan=fixture(),before={sys_id:id(301),id:id(67),table:'sys_generative_ai_custom_llm_transformer',use_es_latest:'true',sys_mod_count:'0',sys_updated_on:'2026-11-01 12:00:00'};
  plan.guards.push({table:'sys_es_latest_script',id:before.sys_id,before});plan.companions.push({table:'sys_es_latest_script',id:before.sys_id,owner:before.id,before});
  const append=(u,n,db)=>{if(!u.name.endsWith('_'+id(67)))return;const row=db.sys_es_latest_script[0];u.payload=u.payload.replace('</record_update>','<sys_es_latest_script action="INSERT_OR_UPDATE">'+Object.entries(row).map(([k,v])=>'<'+k+'>'+v+'</'+k+'>').join('')+'</sys_es_latest_script></record_update>');};
  const good=platform(plan,{afterCapture:append}),r=good.run();assert.equal(r.ok,true,r.error);assert.equal(r.captured,68);assert.equal(good.db.sys_update_xml.length,68);
  const bad=platform(plan,{afterCapture:(u,n,db)=>{append(u,n,db);u.payload=u.payload.replace('<id>'+id(67)+'</id>','<id>wrong-owner</id>');}}),badResult=bad.run();assert.equal(badResult.ok,false);assert.match(badResult.error,/companion_contract/);assert.equal(bad.selected,'original-set');
});
for(const [name,change,reason] of [
  ['wrong capture scope',u=>u.application='wrong',/capture_scope_or_action/],
  ['outer DELETE',u=>u.action='DELETE',/capture_scope_or_action/],
  ['embedded delete_multiple',u=>u.payload=u.payload.replace('</record_update>','<child action="delete_multiple"/></record_update>'),/embedded_delete/],
  ['encoded embedded DELETE',u=>u.payload=u.payload.replace('action="INSERT_OR_UPDATE"','action="D&#69;LETE"'),/transport_record_action/],
  ['extra transport record',u=>u.payload=u.payload.replace('</record_update>','<sys_script action="INSERT_OR_UPDATE"><sys_id>evil</sys_id></sys_script></record_update>'),/transport_record/],
  ['extra unknown captured field',u=>u.payload=u.payload.replace('</sys_generative_ai_config>','<unapproved>evil</unapproved></sys_generative_ai_config>'),/transport_field/],
  ['wrong captured model',u=>u.payload=u.payload.replace('<model>halogen-v2</model>','<model>wrong</model>'),/captured_contract_mismatch/],
  ['stale captured revision',u=>u.payload=u.payload.replace('<sys_mod_count>2</sys_mod_count>','<sys_mod_count>1</sys_mod_count>'),/captured_revision_mismatch/]
])test('rejects '+name,()=>{const p=platform(fixture(),{afterCapture:change});const r=p.run();assert.ok(r);assert.equal(r.ok,false);assert.match(r.error,reason);assert.equal(p.selected,'original-set');});
test('unexpected existing batch is rejected before writes',()=>{
  const plan=fixture(),p=platform(plan);p.db.sys_update_set.push({sys_id:id(999),name:plan.name,application:'global',parent:'',state:'in progress',description:'foreign'});const r=p.run();assert.ok(r);assert.equal(r.ok,false);assert.equal(p.writes.length,0);
});
test('enabled Mirror gate prevents writes',()=>{const p=platform(fixture());p.db.sys_properties[0].value='true';const r=p.run();assert.ok(r);assert.equal(r.ok,false);assert.equal(p.writes.length,0);});
test('already-desired source values with arbitrary revisions require an existing verified batch before any writes',()=>{
  const plan=fixture(),p=platform(plan);for(const t of plan.targets){const r=p.db[t.table].find(r=>r.sys_id===t.id);r[t.field]=t.desired;r.sys_mod_count='999';r.sys_updated_on='2099-01-01 00:00:00';}
  const r=p.run();assert.equal(r.ok,false);assert.match(r.error,/already_desired_without_verified_batch/);assert.equal(p.writes.length,0);assert.equal(p.selected,'original-set');
});
test('unexpected customer update added during capture fails exact membership audit',()=>{
  const p=platform(fixture(),{afterCapture:(u,n,db)=>{if(n===68)db.sys_update_xml.push({sys_id:id(9999),name:'unplanned',update_set:u.update_set,application:u.application,action:'INSERT_OR_UPDATE',payload:''});}});const r=p.run();assert.ok(r);assert.equal(r.ok,false);assert.match(r.error,/unexpected|membership/i);assert.equal(p.selected,'original-set');
});
test('builder freezes exactly66 active prompts and two code fields while retaining five inactive guards',()=>{
  const builderPath=path.join(__dirname,'build-deployment.cjs');
  const builder=fs.existsSync(builderPath)?require(builderPath):{loadInputs:()=>null,createPlan:()=>null};
  const input=builder.loadInputs(path.resolve(__dirname,'../../../server/.local/voice-goal-halogen-agents-20261101'),__dirname);
  const plan=builder.createPlan(input);assert.ok(plan,'builder must produce a frozen deployment plan');
  assert.equal(plan.targets.length,68);assert.equal(plan.targets.filter(t=>t.table==='sys_generative_ai_config').length,66);
  assert.equal(plan.guards.filter(g=>g.table==='sys_generative_ai_config'&&g.before.active==='false').length,5);
  assert.equal(new Set(plan.targets.map(t=>t.id)).size,68);
  const code=plan.targets.filter(t=>t.table!=='sys_generative_ai_config');
  assert.deepEqual(code.map(t=>[t.id,t.field]).sort(),[['121f7b69934c93d05c8132d47aba1077','script'],['bc126377936f8750e7f2b9fa6aba1012','request_transformer']]);
  assert.equal(code.find(t=>t.field==='script').desired,fs.readFileSync(path.join(__dirname,'LocalLLMReActExecutionLedger.js'),'utf8'));
  for(const t of plan.targets.filter(t=>t.table==='sys_generative_ai_config'))assert.equal(t.before.model,'Gemma 4 26B-A4B');
  assert.throws(()=>builder.createPlan({...input,promptGroups:input.promptGroups.map((g,i)=>i?g:{...g,hasMore:true})}),/incomplete/);
  const actual=platform(plan,{serializeCompanions:true}),result=actual.run();assert.equal(result.ok,true,result.error);assert.equal(result.verified,68);assert.equal(actual.db.sys_update_xml.length,68);
  const before=actual.writes.length;assert.equal(actual.run().status,'already_applied');assert.equal(actual.writes.length,before);
});
module.exports={fixture,platform};
