/* READ ONLY: SCC exact-record plan. No inserts, updates, capture, property/cache changes, or secrets printed.
 * Generated from the reviewed full capture script; same seeds and discovery/preflight functions.
 * Copy frozen_manifest_candidate into FROZEN_MANIFEST in scc-batch-capture.js after reviewing discovery.
 */
(function(){
var MAX_RECORDS=200, MAX_PER_RELATION=50;
var SEEDS = [
['sys_now_assist_deployment', 'c623a20f93374354e7f2b9fa6aba10fd'],
['sys_now_assist_deployment_config', '9e23e20f93374354e7f2b9fa6aba1087'],
['sys_cs_context_profile', 'c623e20f93374354e7f2b9fa6aba1081'],
['sn_aia_agent', 'e850ba4f933b4354e7f2b9fa6aba105d'],
['sn_aia_agent_config', '2fa13ec3937b4354e7f2b9fa6aba1068'],
['sn_aia_version', '6fa1fac3937b4354e7f2b9fa6aba1035'],
['sn_aia_agent_tool_m2m', '9842fa47937b4354e7f2b9fa6aba10f6'],
['sn_aia_agent_tool_m2m', '14427687937b4354e7f2b9fa6aba10bf'],
['sn_aia_agent_tool_m2m', '98427687937b4354e7f2b9fa6aba10c0'],
['sn_aia_agent_tool_m2m', '10427687937b4354e7f2b9fa6aba10c2'],
['sn_aia_agent_tool_m2m', '18427687937b4354e7f2b9fa6aba10c3'],
['sys_cs_provider_application', '200af60f93fb4354e7f2b9fa6aba107d'],
['sys_alias', '600af60f93fb4354e7f2b9fa6aba107f'],
['http_connection', '680af60f93fb4354e7f2b9fa6aba1081'],
['sn_va_as_service_outbound_configuration', 'e40af60f93fb4354e7f2b9fa6aba10ff'],
['sys_now_assist_deployment_channel', 'a40a3a0f93fb4354e7f2b9fa6aba1001'],
['sc_cat_item', '401b878b93738354e7f2b9fa6aba102f'],
['item_option_new', '981b0f8b93738354e7f2b9fa6aba1018'],
['item_option_new', 'd01b0f8b93738354e7f2b9fa6aba103f'],
['item_option_new', '181b0f8b93738354e7f2b9fa6aba1059'],
['item_option_new', 'dc1b0f8b93738354e7f2b9fa6aba108c'],
['sn_aia_agent', 'a4a9438393738354e7f2b9fa6aba101d']
];
var EXTRA_MANIFEST = [
['sys_sg_button', 'b0e217cf93b78354e7f2b9fa6aba1028'],
['sys_sg_button_instance', '74e2df0393f78354e7f2b9fa6aba1000'],
['sys_sg_alp_quick_action_map', '78e2df0393f78354e7f2b9fa6aba1003'],
['message_auth', 'a80af60f93fb4354e7f2b9fa6aba107b'],
['sc_cat_item_catalog', '676d438793b38354e7f2b9fa6aba1010'],
['sys_script', 'a211df8f93378354e7f2b9fa6aba10da'],
['sys_generative_ai_custom_llm_transformer', 'bc126377936f8750e7f2b9fa6aba1012'],
['sys_generative_ai_config', '4780c7e193f747d0e7f2b9fa6aba1030'],
['sys_agent_access_role_configuration', 'a6bc4f8393b38354e7f2b9fa6aba1022'],
['sys_agent_access_role_configuration', 'aa39bec793fb4354e7f2b9fa6aba1065'],
['sys_agent_access_role_mapping', '3abc4f8393b38354e7f2b9fa6aba1032'],
['sys_agent_access_role_mapping', 'fe39320b93fb4354e7f2b9fa6aba100b'],
['sys_security_acl', '115c870393b38354e7f2b9fa6aba10a6'],
['sys_security_acl', 'c9393ac793fb4354e7f2b9fa6aba108d'],
['ais_search_source', '1723a60f93374354e7f2b9fa6aba10b0'],
['ais_search_source', '4b23a60f93374354e7f2b9fa6aba106f'],
['sn_aia_agent_config', 'f21ac78793738354e7f2b9fa6aba106e'],
['sn_aia_version', 'f61ac78793738354e7f2b9fa6aba104b'],
['sn_aia_tool', '15ebcb8f93738354e7f2b9fa6aba1072'],
['sn_aia_agent_tool_m2m', '55ebcb8f93738354e7f2b9fa6aba107b'],
['sn_aia_tool', '8b5c4f0393b38354e7f2b9fa6aba10f7'],
['sn_aia_agent_tool_m2m', '835c4f0393b38354e7f2b9fa6aba10f9']
];
var PENDING_RECORDS = [];
var EXCLUDED_IDS = {
'6882f6c7937b4354e7f2b9fa6aba105e': true,
'5782fac7937b4354e7f2b9fa6aba10ea': true,
'60b9ea4893c68350e7f2b9fa6aba1090': true,
'5287ce9c93d64f145c8132d47aba1060': true
};
var PREREQUISITES = [
{kind: 'existing_homepage', sys_id: 'ad7cc08177a72300454792718a1061ab', action: 'Existing mobile Homepage remains unchanged; target mobile endpoint must be verified before enabling the button instance'},
{kind: 'existing_custom_field', table: 'interaction', field: 'u_resolution_required', action: 'Existing field used by the SCC-specific legacy auto-close exclusion; not changed or captured'},
{kind: 'context_value', name: 'u_liveagent_devicetype', action: 'Existing device context condition inherited by the SCC assistant; verify the target environment supplies this context value'},
{kind: 'existing_model', sys_id: 'ff74fcef93a70350e7f2b9fa6aba10ea', action: 'Existing halogen-v2 model configuration used by the captured transformer; model/provider setup and credentials remain destination prerequisites'},
{kind: 'credential', sys_id: '6882f6c7937b4354e7f2b9fa6aba105e', action: 'Provision securely on destination; never captured'},
{kind: 'credential', sys_id: '5782fac7937b4354e7f2b9fa6aba10ea', action: 'Provision securely on destination; never captured'},
{kind: 'runtime', action: 'Local gateway, network reachability, model/provider configuration, and authentication must be configured on destination'},
{kind: 'application', action: 'Matching installed application scopes and required ServiceNow plugin/app versions must exist on destination'}
];
var AGENT_CHILD_TABLES = [
'sn_aia_agent_config', 'sn_aia_version', 'sn_aia_agent_tool_m2m', 'sn_aia_agent_child'
];
var PROFILE_CHILD_TABLES = [
'sys_gen_ai_skill_applicability', 'sys_cs_context_profile_promoted_skill',
'sys_cs_context_profile_message', 'sys_cs_context_profile_visible_discoverable_skill',
'sys_cs_context_profile_preferred_skill', 'sys_cs_context_profile_search',
'sys_cs_context_profile_tool_m2m', 'sys_cs_document_context_profile',
'sys_cb_document_context_profile', 'sys_cs_context_profile_topic',
'sys_cs_context_profile_promotion', 'sys_cs_context_profile_skill', 'sys_cs_context_profile_tool'
];
var DEPLOYMENT_CHILD_TABLES = [
'sys_now_assist_va_persona_detail', 'sys_now_assist_deployment_menu_item',
'sys_now_assist_deployment_config', 'sys_now_assist_deployment_channel'
];
var CATALOG_EDGES = [
['item_option_new', 'cat_item', 'sc_cat_item'],
['question_choice', 'question', 'item_option_new'],
['sc_cat_item_category', 'sc_cat_item', 'sc_cat_item'],
['sc_cat_item_catalog', 'sc_cat_item', 'sc_cat_item'],
['catalog_script_client', 'cat_item', 'sc_cat_item'],
['catalog_ui_policy', 'catalog_item', 'sc_cat_item'],
['catalog_ui_policy_action', 'ui_policy', 'catalog_ui_policy']
];
var records=[],recordMap={},scopes={},scopeNames={},prereqMap={},discoveryEvidence=[];
var result={ok:false,mode:'plan'};
try {
if(!gs.hasRole('admin')) fail('Admin required.');
var i;for(i=0;i<SEEDS.length;i++)add(SEEDS[i][0],SEEDS[i][1],'Exact seed');
for(i=0;i<EXTRA_MANIFEST.length;i++)add(EXTRA_MANIFEST[i][0],EXTRA_MANIFEST[i][1],'Exact owned addition');
discoverAgentGraph();
discoverAgentSkillMetadata();
discoverVerifiedReferences(PROFILE_CHILD_TABLES,['sys_cs_context_profile']);
discoverVerifiedReferences(DEPLOYMENT_CHILD_TABLES,['sys_now_assist_deployment','sys_now_assist_deployment_config']);
discoverSearchSourceRelations();discoverOwnedForwardReferences();
discoverRelation('sys_security_acl_role','sys_security_acl','sys_security_acl');
discoverOwnedForwardReferences();discoverCatalogChildren();collectSharedToolPrerequisites();
records.sort(function(a,b){return(a.scope+a.table+a.sys_id)<(b.scope+b.table+b.sys_id)?-1:1;});
for(i=0;i<records.length;i++)assertNoSecrets(read(records[i].table,records[i].sys_id));
result.ok=true;
}catch(e){result.error=String(e.message||e);}
result.manifest_count=records.length;result.frozen_manifest_candidate=frozenCandidate();
var seenEvidence={},uniqueEvidence=[];for(var j=0;j<discoveryEvidence.length;j++){var ev=JSON.stringify(discoveryEvidence[j]);if(!seenEvidence[ev]){seenEvidence[ev]=true;uniqueEvidence.push(discoveryEvidence[j]);}}
result.discovery=uniqueEvidence;result.prerequisites=PREREQUISITES;
result.scope_sources=[];for(var k=0;k<records.length;k++)if(records[k].scope_source!=='record.sys_scope')result.scope_sources.push({table:records[k].table,sys_id:records[k].sys_id,scope:records[k].scope,source:records[k].scope_source});
gs.info('[SCC Batch Plan] '+JSON.stringify(result));
function own(obj, key) { return Object.prototype.hasOwnProperty.call(obj, key); }
function fail(message) { throw new Error(message); }
function tableAllowed(table) { return !/(credential|oauth|token|password|secret|certificate|private_key)/i.test(table) && !/(execution|session|conversation|message_log|audit|history|cache|runtime)/i.test(table); }
function open(table) { var gr = new GlideRecord(table); if (!gr.isValid()) fail('Table does not exist: ' + table); return gr; }
function read(table, id) { var gr = open(table); if (!gr.get(id)) fail('Missing record: ' + table + '/' + id); return gr; }
function add(table, id, reason) { id = String(id || ''); if (!/^[0-9a-f]{32}$/.test(id)) fail('Invalid manifest sys_id for ' + table); if (!tableAllowed(table) || EXCLUDED_IDS[id]) fail('Excluded record requested: ' + table + '/' + id); var gr = read(table, id); table = String(gr.getRecordClassName()); if (!tableAllowed(table)) fail('Excluded record class: ' + table); var key = table + ':' + id; if (recordMap[key]) return; if (records.length >= MAX_RECORDS) fail('Manifest record safety limit reached.'); var scope = gr.isValidField('sys_scope') ? String(gr.getValue('sys_scope') || 'global') : 'global'; if (scope !== 'global' && !/^[0-9a-f]{32}$/.test(scope)) fail('Invalid actual scope: ' + key); if (!scopeNames[scope]) { var s = read('sys_scope', scope); scopeNames[scope] = String(s.getValue('scope') || s.getValue('name') || scope); } var updateName = gr.isValidField('sys_update_name') ? String(gr.getValue('sys_update_name') || '') : ''; var entry = {table: table, sys_id: id, scope: scope, reason: reason, update_name: updateName || table + '_' + id, updated_on: String(gr.getValue('sys_updated_on') || ''), mod_count: String(gr.getValue('sys_mod_count') || ''), scope_source: gr.isValidField('sys_scope') ? 'record.sys_scope' : 'global fallback; verify captured application'}; records.push(entry); recordMap[key] = entry; scopes[scope] = true; }
function idsFor(table) { var ids = []; for (var i = 0; i < records.length; i++) if (records[i].table === table) ids.push(records[i].sys_id); return ids; }
function discoverRelation(table, field, parentTable) { var ids = idsFor(parentTable); if (!ids.length) return; var q = new GlideRecord(table); if (!q.isValid() || !q.isValidField(field)) { discoveryEvidence.push({table: table, field: field, parent_table: parentTable, status: 'schema_not_present'}); return; } q.addQuery(field, 'IN', ids.join(',')); q.setLimit(MAX_PER_RELATION + 1); q.query(); var count = 0; while (q.next()) { if (++count > MAX_PER_RELATION) fail('Relationship safety limit: ' + table + '.' + field); add(table, String(q.getUniqueValue()), 'Owned relation: ' + field + ' references exact ' + parentTable + ' manifest IDs'); } discoveryEvidence.push({table: table, field: field, parent_table: parentTable, status: 'queried_exact_parent_ids', count: count}); }
function frozenCandidate() { var frozen = []; for (var i = 0; i < records.length; i++) frozen.push([records[i].table, records[i].sys_id, records[i].scope, records[i].updated_on, records[i].mod_count]); return frozen; }
function discoverVerifiedReferences(tables, parentTables) { var d = open('sys_dictionary'), found = {}; d.addQuery('name', 'IN', tables.join(',')); d.addQuery('reference', 'IN', parentTables.join(',')); d.addNotNullQuery('element'); d.query(); while (d.next()) { var name = String(d.getValue('name')); found[name] = true; discoverRelation(name, String(d.getValue('element')), String(d.getValue('reference'))); } for (var i = 0; i < tables.length; i++) if (!found[tables[i]]) discoveryEvidence.push({table: tables[i], parent_tables: parentTables.join(','), status: 'no_dictionary_reference_found; review exact schema before final confirmation'}); }
function discoverSearchSourceRelations() { var d = open('sys_dictionary'); d.addQuery('name', 'STARTSWITH', 'ais_'); d.addQuery('reference', 'ais_search_source'); d.addNotNullQuery('element'); d.query(); while (d.next()) { var table = String(d.getValue('name')); if (tableAllowed(table)) discoverRelation(table, String(d.getValue('element')), 'ais_search_source'); } }
function discoverAgentChildren() { var previousCount = -1; for (var pass = 0; pass < 4 && records.length !== previousCount; pass++) { previousCount = records.length; var d = open('sys_dictionary'); d.addQuery('name', 'IN', AGENT_CHILD_TABLES.join(',')); d.addQuery('reference', 'IN', 'sn_aia_agent,sn_aia_agent_config,sn_aia_version'); d.addNotNullQuery('element'); d.query(); while (d.next()) discoverRelation(String(d.getValue('name')), String(d.getValue('element')), String(d.getValue('reference'))); } if (records.length !== previousCount) fail('Agent relationship discovery did not converge.'); }
function discoverAgentGraph() { var previousCount = -1; for (var pass = 0; pass < 5 && records.length !== previousCount; pass++) { previousCount = records.length; discoverRelation('sn_aia_version', 'target_id', 'sn_aia_agent'); discoverAgentChildren(); discoverOwnedForwardReferences(); } if (records.length !== previousCount) fail('Agent/version dependency discovery did not converge.'); }
function discoverCatalogChildren() { for (var i = 0; i < CATALOG_EDGES.length; i++) discoverRelation(CATALOG_EDGES[i][0], CATALOG_EDGES[i][1], CATALOG_EDGES[i][2]); }
function discoverAgentSkillMetadata() { var table='sn_aia_skill_metadata',ids=idsFor('sn_aia_agent'),included=[]; if(!ids.length)return; var q=new GlideRecord(table); if(!q.isValid()||!q.isValidField('document_table')||!q.isValidField('document_id')){discoveryEvidence.push({table:table,status:'polymorphic_metadata_schema_not_present'});return;} q.addQuery('document_table','sn_aia_agent');q.addQuery('document_id','IN',ids.join(','));q.setLimit(MAX_PER_RELATION+1);q.query();while(q.next()){if(included.length>=MAX_PER_RELATION)fail('Relationship safety limit: '+table);var id=String(q.getUniqueValue()),agentId=String(q.getValue('document_id'));add(table,id,'Exact owned agent metadata: document_table=sn_aia_agent, document_id='+agentId);included.push({sys_id:id,agent:agentId});}discoveryEvidence.push({table:table,status:'queried_exact_polymorphic_agent_ids',count:included.length,included:included}); }
function discoverOwnedForwardReferences() { for (var index = 0; index < records.length; index++) { var entry = records[index]; if (!/^sn_aia_(agent|agent_config|version)$/.test(entry.table) && entry.table !== 'sys_security_acl_role' && !/^sys_agent_access_role_(configuration|mapping)$/.test(entry.table)) continue; var source = read(entry.table, entry.sys_id); var names = [entry.table], cursor = entry.table, ancestry = {}; for (var depth = 0; depth < 8 && cursor; depth++) { if (ancestry[cursor]) fail('Table inheritance cycle: ' + cursor); ancestry[cursor] = true; var dbo = open('sys_db_object'); dbo.addQuery('name', cursor); dbo.setLimit(1); dbo.query(); if (!dbo.next() || !dbo.getValue('super_class')) break; var parent = read('sys_db_object', String(dbo.getValue('super_class'))); cursor = String(parent.getValue('name')); names.push(cursor); } var d = open('sys_dictionary'); d.addQuery('name', 'IN', names.join(',')); d.addQuery('reference', 'IN', 'sn_aia_version,sys_security_acl,sys_user,sys_user_role'); d.addNotNullQuery('element'); d.query(); while (d.next()) { var field = String(d.getValue('element')), target = String(d.getValue('reference')); if (!source.isValidField(field)) continue; var ids = String(source.getValue(field) || '').split(','); for (var n = 0; n < ids.length; n++) { var id = ids[n].replace(/^\s+|\s+$/g, ''); if (!id) continue; if (!/^[a-f0-9]{32}$/.test(id)) fail('Unexpected reference format: ' + entry.table + '.' + field); if (target === 'sn_aia_version' || target === 'sys_security_acl') { add(target, id, 'Exact owned reference from ' + entry.table + '/' + entry.sys_id + '.' + field); } else if (!prereqMap[target + ':' + id]) { prereqMap[target + ':' + id] = true; PREREQUISITES.push({kind: target === 'sys_user' ? 'run_as_or_access_user' : 'existing_role', table: target, sys_id: id, referenced_by: entry.table + '/' + entry.sys_id + '.' + field, action: 'Existing identity/role prerequisite; not captured and no roles granted'}); } } } } }
function collectSharedToolPrerequisites() { var ids = idsFor('sn_aia_agent_tool_m2m'); for (var i = 0; i < ids.length; i++) { var gr = read('sn_aia_agent_tool_m2m', ids[i]); if (!gr.isValidField('tool')) fail('Expected tool field missing on agent binding.'); var toolId = String(gr.getValue('tool') || ''); if (toolId && !recordMap['sn_aia_tool:' + toolId] && !prereqMap[toolId]) { prereqMap[toolId] = true; PREREQUISITES.push({kind: 'shared_tool', table: 'sn_aia_tool', sys_id: toolId, action: 'Must exist on destination; not captured unless explicitly owned in EXTRA_MANIFEST'}); } } }
function assertNoSecrets(gr) { var elements = gr.getElements(); for (var i = 0; i < elements.size(); i++) { var element = elements.get(i), field = String(element.getName()); var value = String(gr.getValue(field) || ''); if (!value) continue; var type = String(element.getED().getInternalType()); var isReference = type === 'reference' || type === 'glide_list'; if (/(password|encrypted|secret)/i.test(type) || (!isReference && /(^|_)(password|client_secret|api_key|access_token|refresh_token|auth_token|bearer_token|private_key|shared_secret|shared_key|hmac_key|secret)($|_)/i.test(field))) fail('Secret-bearing field blocks capture: ' + gr.getRecordClassName() + '/' + gr.getUniqueValue() + '.' + field); if (/"(?:password|client_secret|api_key|access_token|refresh_token|auth_token|bearer_token|private_key|shared_secret|shared_key|hmac_key|secret)"\s*:\s*"[^"\s][^"]*"/i.test(value) || /-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----/.test(value) || /^Bearer\s+\S{12,}/i.test(value)) fail('Potential embedded secret blocks capture: ' + gr.getRecordClassName() + '/' + gr.getUniqueValue() + '.' + field); } }
})();
