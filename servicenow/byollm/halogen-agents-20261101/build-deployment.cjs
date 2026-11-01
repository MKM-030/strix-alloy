'use strict';
// Offline only. This builder never loads an SDK, reads credentials or calls a
// service. Private before-images and the generated executable stay in .local.
const fs=require('node:fs');
const path=require('node:path');
const crypto=require('node:crypto');
const aiaScope='32808450431302106c3603295bb8f245';
const definitions=new Set(['4f80c7e193f747d0e7f2b9fa6aba1027','0380c7e193f747d0e7f2b9fa6aba10c9','3e8087e193f747d0e7f2b9fa6aba104c','b28087e193f747d0e7f2b9fa6aba10a0']);
const sha=s=>crypto.createHash('sha256').update(s,'utf8').digest('hex');
function need(ok,message){if(!ok)throw Error(message);}
function readJSON(p){return JSON.parse(fs.readFileSync(p,'utf8').replace(/^\uFEFF/,''));}
function complete(data,label){need(data&&data.ok===true&&data.hasMore===false&&Array.isArray(data.records),'incomplete_snapshot:'+label);return data.records;}
function frozen(row){const copy={};for(const [k,v] of Object.entries(row)){need(typeof v==='string','non_string_snapshot_field:'+k);copy[k]=v;}need(copy.sys_id,'missing_source_identity');return copy;}
function loadInputs(snapshotDirectory,candidateDirectory=__dirname){
  const read=name=>readJSON(path.join(snapshotDirectory,name));
  return {promptGroups:['agent-prompts.before.json','data-extractor-prompts.before.json','output-refiner-prompts.before.json'].map(read),helpers:read('helpers.before.json'),transformers:read('transformers.before.json'),models:read('models.before.json'),gates:read('mirror-gates.before.json'),selectedDefinitions:read('selected-definitions.before.json'),dataDefault:read('data-extractor-default.before.json'),outputDefault:read('output-refiner-default.before.json'),
    reactDefaults:readJSON(path.join(snapshotDirectory,'../voice-goal-resume-20261101/routing-q03-two-capability-defaults.json')),esMetadata:read('es-latest-companions.before.json'),
    desiredLedger:fs.readFileSync(path.join(candidateDirectory,'LocalLLMReActExecutionLedger.js'),'utf8'),desiredTransformer:fs.readFileSync(path.join(candidateDirectory,'Halogen-Request-Transformer.js'),'utf8')};
}
function createPlan(input){
  need(input&&input.promptGroups.length===3,'three_prompt_snapshots_required');
  const targets=[],guards=[],seen=new Set();let inactive=0;
  for(const [i,group] of input.promptGroups.entries())for(const row of complete(group,'prompts'+i)){
    need(!seen.has(row.sys_id),'duplicate_prompt_identity');seen.add(row.sys_id);
    need(definitions.has(row.definition)&&row.definition_table==='sys_one_extend_capability_definition'&&row.sys_scope===aiaScope,'unexpected_prompt_definition_or_scope');
    const before=frozen(row);
    if(row.active==='true'){
      need(row.state==='published'&&row.model==='Gemma 4 26B-A4B','active_prompt_not_expected_published_gemma');
      targets.push({table:'sys_generative_ai_config',id:row.sys_id,scope:aiaScope,field:'model',before,desired:'halogen-v2'});
    }else{need(row.active==='false','invalid_prompt_active_state');guards.push({table:'sys_generative_ai_config',id:row.sys_id,before});inactive++;}
  }
  need(seen.size===71&&targets.length===66&&inactive===5,'unexpected_frozen_prompt_counts');
  function addCode(table,rows,id,field,desired){
    const row=rows.find(r=>r.sys_id===id);need(row&&row.sys_scope==='global'&&typeof row[field]==='string','owned_code_preimage_missing');
    need(typeof desired==='string'&&desired.trim()&&desired!==row[field],'candidate_code_missing_or_unchanged');
    targets.push({table,id,scope:'global',field,before:frozen(row),desired});
  }
  addCode('sys_generative_ai_custom_llm_transformer',complete(input.transformers,'transformers'),'bc126377936f8750e7f2b9fa6aba1012','request_transformer',input.desiredTransformer);
  addCode('sys_script_include',complete(input.helpers,'helpers'),'121f7b69934c93d05c8132d47aba1077','script',input.desiredLedger);
  function addGuards(table,snapshot,label){for(const row of complete(snapshot,label))guards.push({table,id:row.sys_id,before:frozen(row)});}
  addGuards('sys_properties',input.gates,'mirror-gates');
  addGuards('sys_generative_ai_model_config',input.models,'models');
  addGuards('sys_one_extend_capability_definition',input.selectedDefinitions,'selected-definitions');
  addGuards('sys_one_extend_definition_config',input.dataDefault,'data-default');
  addGuards('sys_one_extend_definition_config',input.outputDefault,'output-default');
  addGuards('sys_one_extend_definition_config',input.reactDefaults,'react-defaults');
  // Independently freeze unchanged owned adapter/context and Gemma transformer.
  for(const row of complete(input.helpers,'helpers'))if(row.sys_id!=='121f7b69934c93d05c8132d47aba1077')guards.push({table:'sys_script_include',id:row.sys_id,before:frozen(row)});
  for(const row of complete(input.transformers,'transformers'))if(row.sys_id!=='bc126377936f8750e7f2b9fa6aba1012')guards.push({table:'sys_generative_ai_custom_llm_transformer',id:row.sys_id,before:frozen(row)});
  const companions=[];
  for(const row of complete(input.esMetadata,'es-latest-companions')){
    const owner=targets.find(t=>t.id===row.id&&t.scope==='global');
    need(owner&&row.table===owner.table&&row.use_es_latest==='true'&&!companions.some(c=>c.owner===row.id),'unexpected_es_companion');
    const before=frozen(row);companions.push({table:'sys_es_latest_script',id:row.sys_id,owner:row.id,before});guards.push({table:'sys_es_latest_script',id:row.sys_id,before});
  }
  need(companions.length===2,'two_exact_es_companions_required');
  targets.sort((a,b)=>(a.scope+a.table+a.id).localeCompare(b.scope+b.table+b.id));
  const plan={schema:1,targetCount:68,promptCount:66,name:'Custom LLM Platform 2.3 - Halogen Agent Delta - NO DELETE 20261101',aiaScope,baseline:'310e1af39388db545c8132d47aba104b',targets,guards,companions};
  plan.marker='HALOGEN_AGENT_DELTA_V1_'+sha(JSON.stringify(plan));
  return plan;
}
function render(plan,template){need(template.split('/*__FROZEN_PLAN__*/').length===2,'single_plan_placeholder_required');return template.replace('/*__FROZEN_PLAN__*/',JSON.stringify(plan));}
function writeDeployment(snapshotDirectory,candidateDirectory=__dirname){
  const plan=createPlan(loadInputs(snapshotDirectory,candidateDirectory));
  const template=fs.readFileSync(path.join(candidateDirectory,'apply-halogen-agent-configuration.template.js'),'utf8');
  const script=render(plan,template);new Function(script);
  const scriptName='apply-halogen-agent-configuration.js';
  const summary={prepared_offline:true,instance_executed:false,script:scriptName,script_sha256:sha(script),script_bytes:Buffer.byteLength(script),target_count:68,active_prompt_count:66,inactive_prompt_guards:5,guard_count:plan.guards.length,native_es_companions:plan.companions.length,capability_count:4,model:'halogen-v2',marker:plan.marker,
    source_precondition_boundary:'New apply requires every supplied frozen field and revision exact. Already-desired revisions are accepted only against an existing fully verified owned batch, with zero writes. Every readable live source field is snapshotted before writes and checked after; expected sys_updated_on/sys_updated_by/sys_mod_count and calculated request_tokens may change only for intended source updates.',
    native_rollback:'Root must execute with SDK --record-for-rollback; this is separate from update-set capture.',
    targets:plan.targets.map(t=>({table:t.table,id:t.id,scope:t.scope,field:t.field,before_sha256:sha(JSON.stringify(t.before)),desired_sha256:sha(t.desired)}))};
  fs.writeFileSync(path.join(snapshotDirectory,scriptName),script,'utf8');
  fs.writeFileSync(path.join(snapshotDirectory,'frozen-plan.private.json'),JSON.stringify(plan,null,2)+'\n','utf8');
  fs.writeFileSync(path.join(snapshotDirectory,'deployment-review.json'),JSON.stringify(summary,null,2)+'\n','utf8');
  return summary;
}
if(require.main===module){const snapshotDirectory=path.resolve(__dirname,'../../../server/.local/voice-goal-halogen-agents-20261101');const r=writeDeployment(snapshotDirectory);console.log(JSON.stringify({script:path.join(snapshotDirectory,r.script),sha256:r.script_sha256,bytes:r.script_bytes,targets:r.target_count,prompts:r.active_prompt_count,guards:r.guard_count}));}
module.exports={loadInputs,createPlan,render,writeDeployment};
