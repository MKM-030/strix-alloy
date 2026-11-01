'use strict';
// Offline preparation only. The approved original, original plan and execution
// evidence are immutable inputs; all new outputs have separate variant names.
const fs=require('node:fs');
const path=require('node:path');
const crypto=require('node:crypto');
const base=require('./build-deployment.cjs');
const originalHash='b14dd89fcc6114cdf311c6c6f09795d7ea2b3c93f9fc49414258e8fbc413b649';
const sha=x=>crypto.createHash('sha256').update(x).digest('hex');
function need(ok,message){if(!ok)throw Error(message);}
function prepare(snapshotDirectory,candidateDirectory=__dirname){
  const original=fs.readFileSync(path.join(snapshotDirectory,'apply-halogen-agent-configuration.js'));
  need(sha(original)===originalHash,'original_approved_script_hash_changed');
  const originalPlan=JSON.parse(fs.readFileSync(path.join(snapshotDirectory,'frozen-plan.private.json'),'utf8'));
  const originalTemplate=fs.readFileSync(path.join(candidateDirectory,'apply-halogen-agent-configuration.template.js'),'utf8');
  need(sha(base.render(originalPlan,originalTemplate))===originalHash,'original_frozen_plan_or_template_changed');
  need(originalPlan.targets.length===68&&originalPlan.guards.length===21&&originalPlan.companions.length===2,'original_scope_changed');
  const plan=JSON.parse(JSON.stringify(originalPlan));
  plan.authorityMode='approved_admin_maintenance';plan.originalApprovedScriptSha256=originalHash;
  delete plan.marker;plan.marker='HALOGEN_AGENT_DELTA_ADMIN_MAINTENANCE_V1_'+sha(JSON.stringify(plan));
  const template=fs.readFileSync(path.join(candidateDirectory,'apply-halogen-agent-configuration.admin-maintenance.template.js'),'utf8');
  const script=base.render(plan,template);new Function(script);
  const review={prepared_offline:true,instance_executed:false,requires_separate_user_approval:true,authority_mode:plan.authorityMode,
    original_approved_script_sha256:originalHash,original_native_history:'771610a5935cd314e7f2b9fa6aba105a',original_inner_result:'preflight target_write_denied; zero source writes, zero set attempts, zero captures; no retry',
    script:'apply-halogen-agent-configuration.admin-maintenance.js',script_sha256:sha(script),script_bytes:Buffer.byteLength(script),target_count:68,active_prompt_count:66,guard_count:21,native_es_companions:2,
    authority_boundary:'One-off separately approved admin Scripts - Background maintenance. GlideRecordSecure supplies all readable source preconditions, snapshots, guards, readback and capture. Every target must have readable empty sys_policy; any vendor/read/protected policy aborts before writes. Only each exact frozen source assignment uses ordinary GlideRecord.get(id), setValue(approvedField,approvedValue), update(), with normal Business Rules. UI write-restricted target IDs/count are logged.',
    native_boolean_normalization:'Only element.getED().getInternalType() === boolean is normalized: native 1/0 and SDK true/false become canonical true/false for comparison with snapshots/native XML. Invalid dictionary booleans abort. String property values and string revision zero remain unchanged.',
    excluded_actions:['ACL changes','role or user changes','security-property changes','impersonation','persistent endpoint creation','unreadable-data access','runtime or business/session calls','automatic retry'],
    native_rollback:'Root must execute with SDK --record-for-rollback and explicit per-run reason/approval; hard native policy/update failures remain failures.',
    marker:plan.marker};
  return {plan,script,review};
}
function writeVariant(snapshotDirectory,candidateDirectory=__dirname){
  const prepared=prepare(snapshotDirectory,candidateDirectory),out=prepared.review;
  fs.writeFileSync(path.join(snapshotDirectory,out.script),prepared.script,'utf8');
  fs.writeFileSync(path.join(snapshotDirectory,'frozen-plan.admin-maintenance.private.json'),JSON.stringify(prepared.plan,null,2)+'\n','utf8');
  fs.writeFileSync(path.join(snapshotDirectory,'deployment-review.admin-maintenance.json'),JSON.stringify(out,null,2)+'\n','utf8');
  need(sha(fs.readFileSync(path.join(snapshotDirectory,'apply-halogen-agent-configuration.js')))===originalHash,'original_artifact_changed_during_variant_build');
  return out;
}
if(require.main===module){const r=writeVariant(path.resolve(__dirname,'../../../server/.local/voice-goal-halogen-agents-20261101'));console.log(JSON.stringify({script:r.script,sha256:r.script_sha256,bytes:r.script_bytes,targets:r.target_count,guards:r.guard_count,instance_executed:false}));}
module.exports={prepare,writeVariant};
