'use strict';
// OFFLINE ONLY. New continuation of the confirmed compact partial run. All
// earlier plans/scripts/attempts are immutable inputs; never retry those scripts.
const fs=require('node:fs');
const path=require('node:path');
const crypto=require('node:crypto');
const vm=require('node:vm');
const compact=require('./build-compact-completion.cjs');
const sha=x=>crypto.createHash('sha256').update(x).digest('hex');
const need=(ok,message)=>{if(!ok)throw Error(message);};
const STAGE='0a94f0219318dbd45c8132d47aba1018';
const COMPACT_SHA='d4d05aff4562b9918d3613aa100a3b1aa4ec670b58723da5a6b2949aa6f4a819';
const same=(a,b)=>Object.keys(a).length===Object.keys(b).length&&Object.entries(b).every(([k,v])=>Object.hasOwn(a,k)&&a[k]===v);
function prepare(directory,candidateDirectory=__dirname){
  const frozen=compact.loadFrozen(directory,candidateDirectory),base=frozen.plan,evidence={};
  const load=name=>{const bytes=fs.readFileSync(path.join(directory,name));evidence[name]=sha(bytes);return JSON.parse(bytes.toString('utf8').replace(/^\uFEFF/,''));};
  const records=name=>{const data=load(name);need(data.ok===true&&data.hasMore===false&&Array.isArray(data.records),'incomplete_query:'+name);return data.records;};
  const priorCompact=fs.readFileSync(path.join(directory,'complete-halogen-agent-configuration.compact.js'));
  need(sha(priorCompact)===COMPACT_SHA,'immutable_approved_compact_hash_changed');evidence['complete-halogen-agent-configuration.compact.js']=sha(priorCompact);
  const prior=load('SDK-COMPACT-COMPLETION-EXECUTION-RESULT.json');
  need(prior.ok===true&&prior.scope==='global'&&prior.errors.length===0&&prior.output.length===1&&prior.executionHistoryId==='7094f8219394dbd45c8132d47aba1049'&&prior.rollbackContextId==='f094f8219394dbd45c8132d47aba1047','unexpected_compact_execution_identity');
  const inner=JSON.parse(prior.output[0].slice(prior.output[0].indexOf('{')));
  need(inner.ok===false&&inner.status==='partial_or_uncertain'&&inner.stage==='create_one_external_aia_staging_header'&&inner.error==='staging_scope_or_header_contract'&&inner.header_writes===2&&inner.write_attempts===2&&inner.source_writes===0&&inner.captures===0&&inner.cu_moves===0,'unexpected_compact_partial_shape');
  const contracts=records('update-set-field-contracts.after-compact.json');
  need(contracts.find(r=>r.element==='name')?.max_length==='80'&&contracts.find(r=>r.element==='name')?.read_only==='false'&&contracts.find(r=>r.element==='description')?.max_length==='4000'&&contracts.find(r=>r.element==='description')?.read_only==='false','native_name_length_evidence_required');
  const freshSources={};for(const [table,file]of Object.entries({sys_generative_ai_config:'prompts.after-compact.json',sys_generative_ai_custom_llm_transformer:'transformer.after-compact.json',sys_script_include:'ledger.after-compact.json'}))for(const row of records(file)){const key=table+':'+row.sys_id;need(!freshSources[key],'duplicate_fresh_source');freshSources[key]=row;}
  const plan=JSON.parse(JSON.stringify(base));
  for(const t of plan.targets){const row=freshSources[t.table+':'+t.id];need(row&&same(row,t.current),'fresh_source_or_revision_drift:'+t.id);t.current=row;}
  need(Object.keys(freshSources).length===68,'fresh_source_inventory');
  const guardTables=new Set(plan.guards.map(g=>g.table)),guardRows={};for(const table of guardTables)for(const row of records(table+'.guards.after-compact.json'))guardRows[table+':'+row.sys_id]=row;
  for(const g of plan.guards){const row=guardRows[g.table+':'+g.id];need(row&&same(row,g.before),'fresh_guard_drift:'+g.id);}
  for(const c of plan.companions){const row=guardRows[c.table+':'+c.id];need(row&&same(row,c.before),'fresh_companion_drift:'+c.id);}
  const cus=records('customer-updates.after-compact.json');need(cus.length===68&&new Set(cus.map(c=>c.sys_id)).size===68,'fresh_cu_inventory');
  const oldCus=new Map(base.cus.map(c=>[c.sys_id,c]));for(const cu of cus)need(oldCus.has(cu.sys_id)&&same(cu,oldCus.get(cu.sys_id)),'fresh_cu_contract_or_revision_drift:'+cu.sys_id);plan.cus=cus;
  const headers=records('headers.after-compact.json');need(headers.length===4&&new Set(headers.map(h=>h.sys_id)).size===4,'fresh_four_header_inventory');
  const parent=headers.find(h=>h.sys_id===base.ids.parent),oldParent=base.headers.find(h=>h.sys_id===base.ids.parent),stage=headers.find(h=>h.sys_id===STAGE);
  need(parent&&parent.application==='global'&&parent.sys_mod_count===String(Number(oldParent.sys_mod_count)+1),'confirmed_parent_correction_required');
  for(const [k,v]of Object.entries(oldParent))if(!['application','sys_mod_count','sys_updated_on','sys_updated_by'].includes(k))need(parent[k]===v,'parent_nonapplication_drift:'+k);
  for(const id of [base.ids.global,base.ids.aia])need(same(headers.find(h=>h.sys_id===id)||{},base.headers.find(h=>h.sys_id===id)),'child_header_drift:'+id);
  need(stage&&base.stagingName.length===117&&stage.name===base.stagingName.slice(0,80)&&stage.name.length===80&&stage.description===base.stagingDescription&&stage.description.length<4000&&stage.description.startsWith(base.marker+'\n')&&stage.application===base.aiaScope&&stage.parent===''&&stage.base_update_set===''&&stage.state==='in progress'&&stage.is_default==='false'&&stage.sys_mod_count==='0','exact_existing_native_stage_required');
  need(stage.sys_created_by===oldParent.sys_created_by&&stage.sys_updated_by===stage.sys_created_by&&stage.sys_created_on===stage.sys_updated_on,'stage_ownership_or_revision_drift');
  for(const file of ['stage-name-uniqueness.after-compact.json','stage-owner-uniqueness.after-compact.json']){
    const proof=records(file);need(proof.length===1&&proof[0].sys_id===STAGE,'existing_stage_uniqueness_evidence:'+file);
    need(Object.entries(proof[0]).every(([k,v])=>Object.hasOwn(stage,k)&&stage[k]===v),'existing_stage_uniqueness_projection_drift:'+file);
  }
  need(!cus.some(c=>c.update_set===STAGE||c.update_set===base.ids.parent),'parent_and_existing_stage_must_be_empty');
  plan.headers=headers;plan.authorityMode='separately_approved_existing_stage_completion';plan.existingStageId=STAGE;plan.headerFieldLimits={name:80,description:4000};
  plan.priorCompletionMarker=base.marker;plan.priorIntendedStagingName=base.stagingName;
  plan.stagingName=stage.name;plan.stagingDescription=stage.description;
  plan.headerScopes={[base.ids.global]:'global',[base.ids.aia]:base.aiaScope};
  plan.priorCompactExecutionHistoryId=prior.executionHistoryId;plan.priorCompactRollbackContextId=prior.rollbackContextId;
  delete plan.marker;plan.marker='HALOGEN_AGENT_EXISTING_STAGE_COMPLETION_V1_'+sha(JSON.stringify(plan));
  const template=fs.readFileSync(path.join(candidateDirectory,'complete-halogen-agent-existing-stage.template.js'),'utf8');
  need(template.split('/*__EXISTING_STAGE_PLAN__*/').length===2,'existing_stage_template_marker');
  need(!/\.insert\s*\(|function createStage|setWorkflow|deleteRecord|updateMultiple/.test(template),'existing_stage_template_forbidden_operation');
  const text=JSON.stringify(plan),expression=compact.expressionForText(text),script=template.replace('/*__EXISTING_STAGE_PLAN__*/',expression);
  new vm.Script(script);const check={};vm.runInNewContext('decoded='+expression,check,{timeout:10000});need(JSON.stringify(check.decoded)===text,'existing_stage_plan_codec_roundtrip');
  const review={offline_only:true,instance_executed:false,requires_separate_user_approval:true,script:'complete-halogen-agent-existing-stage.compact.js',script_sha256:sha(script),script_bytes:Buffer.byteLength(script),script_form_encoded_bytes:Buffer.byteLength(new URLSearchParams({script}).toString()),input_sha256:evidence,approved_6ec_script_sha256:compact.SCRIPT_SHA,approved_d4_script_sha256:COMPACT_SHA,prior_compact_execution_history:prior.executionHistoryId,prior_compact_rollback_context:prior.rollbackContextId,existing_stage_id:STAGE,existing_stage_name:stage.name,existing_stage_name_chars:stage.name.length,prior_intended_name_chars:base.stagingName.length,exact_existing_stage_description:true,readonly_parent_id:parent.sys_id,readonly_parent_revision:parent.sys_mod_count,source_assignments:1,readonly_applied_sources:67,source_count:68,guard_count:21,es_companions:2,existing_cus:68,expected_final_cus:69,expected_cu_moves:136,expected_header_writes:3,new_headers:0,renames:0,parent_writes:0,expected_staging_state:'ignore',authority_boundary:'One exact existing owned empty AIA stage is reused by frozen ID/name/description/full revision. Parent already corrected to Global is read-only. Only two empty child applications are corrected, 136 existing CU wrapper moves occur, the same empty stage is ignored, and the frozen ledger script is assigned/captured once. All normal native rules stay enabled; no insert, rename, delete, source recapture, role/ACL/security change or runtime/business call.',strict_native_flag_payload:true,exact_expanded_json_text:true,expanded_json_sha256:sha(text),original_artifacts_immutable:true,limitations:['Requires separate review/approval and native rollback recording; previous scripts must not be retried.','Native opaque hierarchy/origin/flag side effects remain strict failure conditions; offline doubles do not prove instance success.']};
  need(review.script_form_encoded_bytes<900000,'existing_stage_form_size_target');
  return {plan,text,expression,script,review,template};
}
function renderPlan(plan,template){return template.replace('/*__EXISTING_STAGE_PLAN__*/',compact.expressionForText(JSON.stringify(plan)));}
function writeVariant(directory,candidateDirectory=__dirname){const p=prepare(directory,candidateDirectory),outputs=[[p.review.script,p.script],['frozen-plan.existing-stage-completion.private.json',JSON.stringify(p.plan,null,2)+'\n'],['deployment-review.existing-stage-completion.json',JSON.stringify(p.review,null,2)+'\n']];for(const [name]of outputs)need(!fs.existsSync(path.join(directory,name)),'existing_stage_output_already_exists:'+name);for(const [name,value]of outputs)fs.writeFileSync(path.join(directory,name),value,{encoding:'utf8',flag:'wx'});return p.review;}
if(require.main===module)console.log(JSON.stringify(writeVariant(path.resolve(__dirname,'../../../server/.local/voice-goal-halogen-agents-20261101')),null,2));
module.exports={prepare,renderPlan,writeVariant,STAGE,COMPACT_SHA};
