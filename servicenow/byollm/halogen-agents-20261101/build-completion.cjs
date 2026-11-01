'use strict';
// OFFLINE ONLY: preparation never loads an SDK, opens a connection, or executes
// the rendered script. Original plans/scripts and earlier evidence are inputs.
const fs=require('node:fs');
const path=require('node:path');
const crypto=require('node:crypto');
const sha=x=>crypto.createHash('sha256').update(x).digest('hex');
const need=(ok,message)=>{if(!ok)throw Error(message);};
const ADMIN_SCRIPT_SHA='6fbeab7c5b99bf02c53e886c5c432d1e1806c09645dcd96a11c54a76c6bb2dd9';
const ADMIN_PLAN_SHA='3c36a2428c2257fabb62a84134be69d3c4020e45ee070633635ca3593c04b0fc';
const IDS={parent:'4de124e993101714e7f2b9fa6aba1079',global:'09e124e993101714e7f2b9fa6aba107c',aia:'89e124e993101714e7f2b9fa6aba1097',ledger:'121f7b69934c93d05c8132d47aba1077',transformer:'bc126377936f8750e7f2b9fa6aba1012',flag:'ede164e993101714e7f2b9fa6aba1011'};
const CODE={
  'bc126377936f8750e7f2b9fa6aba1012:request_transformer':['99cb5d8733faca9955ec274f21dc4b5f46f0b2c4159cbb63b9c5954bf85c4e58','6e23750a5df2ba87e9a1b1498290286010d509bea1ab672472a5b6cf849b93d0'],
  '121f7b69934c93d05c8132d47aba1077:script':['8d1a900054b03a504cd9cdbf2144037e4c34d1d1eaa6fd1c62f9ab5faa014f4d','911105ce3c7a57305154eae80b29658db9f399eadf0597b4a102c076869c7580']
};
function prepare(directory,candidateDirectory=__dirname){
  const evidence={};
  const load=name=>{const bytes=fs.readFileSync(path.join(directory,name));evidence[name]=sha(bytes);return JSON.parse(bytes.toString('utf8').replace(/^\uFEFF/,''));};
  const records=name=>{const data=load(name);need(data.ok===true&&data.hasMore===false&&Array.isArray(data.records),'incomplete_query:'+name);return data.records;};
  const batchRules=records('batch-native-business-rules.json'),cuRules=records('cu-native-business-rules.json');
  need(batchRules.some(r=>r.sys_id==='04ec6e23d7222100600949d48e6103e6'&&r.name==='Prevent application inconsistency'&&r.condition==='current.application.changes()'&&r.script.includes("updateXmlGR.addQuery('update_set', current.sys_id)")&&r.script.includes('current.setAbortAction(true)')),'native_nonempty_header_rule_evidence_required');
  need(cuRules.some(r=>r.sys_id==='0914e5b9ef001100a61d5a3615c0fb4e'&&r.name==='Handle updates moving between sets'&&r.script.includes('newUpdateSet.application.scope != current.application.scope')&&r.script.includes('versions.setValue("source", current.update_set)')),'native_scope_and_version_rule_evidence_required');
  const base=load('frozen-plan.admin-maintenance.private.json');
  need(evidence['frozen-plan.admin-maintenance.private.json']===ADMIN_PLAN_SHA,'immutable_admin_plan_hash_changed');
  const adminScript=fs.readFileSync(path.join(directory,'apply-halogen-agent-configuration.admin-maintenance.js'));
  evidence['apply-halogen-agent-configuration.admin-maintenance.js']=sha(adminScript);
  need(sha(adminScript)===ADMIN_SCRIPT_SHA,'immutable_admin_script_hash_changed');
  need(base.schema===1&&base.targets.length===68&&base.guards.length===21&&base.companions.length===2&&base.authorityMode==='approved_admin_maintenance','unapproved_original_plan');
  const result=load('SDK-ADMIN-EXECUTION-RESULT.json');
  need(result.executionHistoryId==='30e120a993dcd314e7f2b9fa6aba10fd'&&result.rollbackContextId==='b0e120a993dcd314e7f2b9fa6aba10fc','original_execution_identity_changed');
  need(result.ok===true&&result.scope==='global'&&result.errors.length===0&&result.output.length===1,'unexpected_original_outer_result');
  const inner=JSON.parse(result.output[0].slice(result.output[0].indexOf('{')));
  need(inner.ok===false&&inner.status==='partial_or_uncertain'&&inner.verified===67&&inner.source_writes===67&&inner.captured===66&&inner.set_writes===3&&inner.set_attempts===3&&inner.error==='captured_contract_mismatch:'+IDS.transformer+':request_transformer'&&inner.batch===IDS.parent&&inner.children.global===IDS.global&&inner.children[base.aiaScope]===IDS.aia&&inner.attempted.length===67&&!inner.attempted.includes(IDS.ledger)&&inner.attempted.at(-1)===IDS.transformer,'unexpected_original_partial_result');
  const proof=load('NATIVE-CODE-CR-CANONICALIZATION-PROOF.json');
  need(proof.proof.length===2,'code_proof_scope');
  for(const p of proof.proof){const hashes=CODE[p.id+':'+p.field];need(hashes&&p.exact_source_sha256===hashes[0]&&p.native_CR_removed_sha256===hashes[1]&&p.ES5_AST_equal===true&&p.no_standalone_CR===true,'unqualified_code_proof');}
  const sources={};
  for(const [table,file] of Object.entries({sys_generative_ai_config:'prompts.full.after-admin.json',sys_script_include:'ledger.full.after-admin.json',sys_generative_ai_custom_llm_transformer:'transformers.full.after-admin.json'}))for(const row of records(file)){const key=table+':'+row.sys_id;need(!sources[key],'duplicate_source_snapshot');sources[key]=row;}
  const metadata=new Set(['sys_updated_on','sys_updated_by','sys_mod_count','request_tokens']);
  const targets=base.targets.map(t=>{
    const row=sources[t.table+':'+t.id];need(row&&row.sys_id===t.id&&row.sys_scope===t.scope&&typeof row.sys_mod_count==='string'&&typeof row.sys_updated_on==='string','missing_target_revision:'+t.id);
    need(Object.hasOwn(row,'sys_policy')&&row.sys_policy===''&&Object.hasOwn(row,'sys_created_by'),'full_readable_unprotected_source_required:'+t.id);
    const ledger=t.id===IDS.ledger;
    need(t.table!=='sys_script_include'||ledger,'unexpected_script_include');
    for(const [k,v] of Object.entries(t.before))if(ledger||!metadata.has(k))need(row[k]===(k===t.field&&!ledger?t.desired:v),'target_snapshot_drift:'+t.id+':'+k);
    const code=CODE[t.id+':'+t.field];if(code)need(sha(t.desired)===code[0]&&sha(t.desired.replace(/\r/g,''))===code[1],'frozen_code_value_changed');
    return {...t,current:row};
  });
  need(targets.filter(t=>t.table==='sys_generative_ai_config').length===66&&targets.filter(t=>t.id===IDS.transformer).length===1,'completion_target_scope');
  const guardFiles=new Set(base.guards.map(g=>g.table+'.guards.after-admin.json'));
  const guards={};for(const file of guardFiles)for(const row of records(file))guards[file.split('.guards.')[0]+':'+row.sys_id]=row;
  for(const g of base.guards){const row=guards[g.table+':'+g.id];need(row,'missing_guard:'+g.id);for(const [k,v] of Object.entries(g.before))need(row[k]===v,'guard_snapshot_drift:'+g.id+':'+k);}
  const companions=records('sys_es_latest_script.guards.after-admin.json');
  for(const c of base.companions){const row=companions.find(r=>r.sys_id===c.id);need(row,'missing_companion');for(const [k,v]of Object.entries(c.before))need(row[k]===v,'companion_snapshot_drift:'+c.id+':'+k);}
  const headers=records('batch-headers.full.after-admin.json'),cus=records('customer-updates.full.after-admin.json');
  need(headers.length===3&&cus.length===68,'partial_wrapper_inventory');
  const headerScopes={[IDS.parent]:'global',[IDS.global]:'global',[IDS.aia]:base.aiaScope};
  for(const row of headers){need(Object.hasOwn(headerScopes,row.sys_id)&&row.application==='6d99fe72474f211082179725126d4308'&&row.state==='in progress'&&row.is_default==='false'&&row.base_update_set===IDS.parent&&row.parent===(row.sys_id===IDS.parent?'':IDS.parent),'header_preimage_shape');need(Object.hasOwn(row,'sys_updated_by')&&Object.hasOwn(row,'sys_mod_count')&&Object.hasOwn(row,'sys_created_by'),'full_header_snapshot_required');}
  const names=new Map(targets.filter(t=>t.id!==IDS.ledger).map(t=>[t.current.sys_update_name||t.table+'_'+t.id,t]));
  const seen=new Set();let promptCUs=0,globalCUs=0;
  for(const cu of cus){need(!seen.has(cu.sys_id),'duplicate_cu_identity');seen.add(cu.sys_id);need(cu.action==='INSERT_OR_UPDATE'&&Object.hasOwn(cu,'sys_mod_count')&&Object.hasOwn(cu,'payload_hash')&&Object.hasOwn(cu,'update_guid_history')&&Object.hasOwn(cu,'sys_created_by'),'full_cu_snapshot_required');
    if(cu.sys_id===IDS.flag){need(cu.name==='sys_gen_ai_control_setting_data_32ee2ed0fff53210c3fcffffffffff09'&&cu.application==='global'&&cu.update_set===IDS.aia,'unexpected_native_flag_wrapper');globalCUs++;}
    else{const t=names.get(cu.name);need(t&&!t.capture,'unexpected_or_duplicate_cu_name');need(cu.application===t.scope&&cu.update_set===(t.scope==='global'?IDS.global:IDS.aia),'cu_preimage_scope');t.capture=cu.sys_id;if(t.scope==='global')globalCUs++;else promptCUs++;}
  }
  need(promptCUs===66&&globalCUs===2&&targets.filter(t=>t.id!==IDS.ledger).every(t=>t.capture),'missing_applied_capture');
  const plan={schema:1,authorityMode:'separately_approved_admin_completion',name:base.name,aiaScope:base.aiaScope,baseline:base.baseline,originalMarker:base.marker,ids:IDS,targets,guards:base.guards,companions:base.companions,headers,cus,headerScopes,codeFields:Object.keys(CODE),stagingName:base.name+' / Completion staging AI Agents (one-shot 20261101)',originalExecutionHistoryId:result.executionHistoryId,originalRollbackContextId:result.rollbackContextId};
  plan.marker='HALOGEN_AGENT_COMPLETION_V1_'+sha(JSON.stringify(plan));
  plan.stagingDescription=plan.marker+'\nTemporary outside-batch AI Agents staging; empty and ignored after completion. No source mutation except the one frozen ledger script assignment.';
  const template=fs.readFileSync(path.join(candidateDirectory,'complete-halogen-agent-configuration.template.js'),'utf8');
  need(template.split('/*__COMPLETION_PLAN__*/').length===2,'completion_plan_marker');
  const script=template.replace('/*__COMPLETION_PLAN__*/',JSON.stringify(plan));new Function(script);
  const review={offline_only:true,instance_executed:false,requires_separate_user_approval:true,script:'complete-halogen-agent-configuration.js',script_sha256:sha(script),script_bytes:Buffer.byteLength(script),input_sha256:evidence,source_assignments:1,readonly_applied_sources:67,guards:21,es_companions:2,existing_cus:68,expected_final_cus:69,expected_cu_move_updates:136,temporary_headers_created:1,temporary_final_state:'ignore',temporary_final_membership:0,final_active_headers:3,strict_native_flag_payload:true,original_execution_history:result.executionHistoryId,original_rollback_context:result.rollbackContextId,authority_boundary:'Secure read preflight freezes all 68 sources, 21 guards, 2 ES companions, full 3 headers and 68 CUs including revisions before any write. Bounded ordinary GlideRecord changes only header application (and one temporary header creation/state), existing CU update_set wrappers, and the exact frozen ledger script. Normal native rules remain enabled; source assignment/capture occurs once only for ledger. Any failure stops without retry and restores the original update-set preference.',native_side_effect:'Native Handle updates moving between sets moves matching sys_update_version associations; the script never edits version records. Native origin-cleaner effects must preserve every non-revision field of the existing CU row. Any native flag CU payload refresh fails the final audit.',assumptions:['Run once in Global under separately reviewed admin maintenance authorization with SDK rollback recording.','All exact private input hashes must be reviewed; runtime preflight aborts on any source/header/CU revision, membership, payload, guard, companion or topology drift.','Opaque native hierarchy/origin hooks are not proven by offline doubles; unexpected header revision or non-wrapper CU changes intentionally fail closed.','Native ledger update must leave the existing flag CU payload byte-for-byte unchanged; refresh is a failure requiring fresh investigation.','Fresh post-run queries and offline verifier are required before claiming completion.']};
  return {plan,script,review};
}
function writeVariant(directory,candidateDirectory=__dirname){const p=prepare(directory,candidateDirectory),outputs=[[p.review.script,p.script],['frozen-plan.completion.private.json',JSON.stringify(p.plan,null,2)+'\n'],['deployment-review.completion.json',JSON.stringify(p.review,null,2)+'\n']];for(const [name]of outputs)need(!fs.existsSync(path.join(directory,name)),'completion_output_already_exists:'+name);for(const [name,value]of outputs)fs.writeFileSync(path.join(directory,name),value,{encoding:'utf8',flag:'wx'});return p.review;}
if(require.main===module)console.log(JSON.stringify(writeVariant(path.resolve(__dirname,'../../../server/.local/voice-goal-halogen-agents-20261101')),null,2));
module.exports={prepare,writeVariant,IDS};
