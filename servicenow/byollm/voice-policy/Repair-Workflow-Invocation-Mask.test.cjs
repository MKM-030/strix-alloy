const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const target = path.join(__dirname, 'Repair-Workflow-Invocation-Mask.fix.js');
// External ServiceNow is replaced at the ordinary GlideRecord/public DAO boundary.
// Frozen business-only fixture was authored from independent retained receipts.
// It is not read or generated from the production guard data or API.
const businessFixture = require('./Repair-Workflow-Invocation-Mask.fixture.json');
const clone = x => JSON.parse(JSON.stringify(x));
const outer = '884cca39931093185c8132d47aba1082';
const set = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const roles = ['282bf1fac6112285017366cb5f867469','de69200f93485750e7f2b9fa6aba1043','2831a114c611228501d4ea6c309d626d'];
function fixture() {
 const db = clone(businessFixture);
 db.sys_user_role=roles.map((sys_id,i)=>({sys_id,name:['itil','scc_voice_context_reader','admin'][i]}));
 db.sys_update_set=[{sys_id:set,name:'Custom LLM Voice 3.0 - Workflow Invoke Mask Repair - NO DELETE 20261103',application:'global',state:'in progress'}];
 db.sys_update_xml=[];
 const ctx={uid:'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',name:'approved.admin',admin:true,impersonating:false,instance:'soprasteriaassvsdemo14',scope:'rhino.global',application:'global',userSet:set,systemSet:set};
 const state={calls:[],reads:0,denied:null,denyField:null,partial:false,resultNull:false,throwUpdate:false,missingCapture:false,postReadDenied:false};
 function GR(table){this.table=table;this.conditions=[];this.row=null;this.rights=new Set();}
 GR.prototype.isValid=()=>true; GR.prototype.isValidField=()=>true;
 GR.prototype.canRead=function(){return this.table!==state.denied&&!(state.postReadDenied&&state.calls.length&&this.table==='sn_aia_agent_config');};
 GR.prototype.getElement=function(field){return {canRead:()=>{this.rights.add(field);return field!==state.denyField;}};};
 GR.prototype.getValue=function(field){assert(this.rights.has(field),'rights before value');return this.row ? this.row[field] ?? '' : '';};
 GR.prototype.addQuery=function(...c){this.conditions.push(c);};
 GR.prototype.setLimit=function(n){this.limit=n;};
 GR.prototype.query=function(){state.reads++;this.rows=(db[this.table]||[]).filter(r=>this.conditions.every(([f,op,v])=>op==='='?String(r[f]??'')===v:op==='IN'?v.split(',').includes(String(r[f])):false)).slice(0,this.limit);this.index=0;};
 GR.prototype.next=function(){this.row=this.rows[this.index++];this.rights=new Set();return !!this.row;};
 const gs={getUserID:()=>ctx.uid,getUserName:()=>ctx.name,hasRole:()=>ctx.admin,getProperty:()=>ctx.instance,getCurrentScopeName:()=>ctx.scope,getCurrentApplicationId:()=>ctx.application,getUser:()=>({getPreference:()=>ctx.userSet}),getPreference:()=>ctx.systemSet};
 function DAO(){}
 DAO.prototype.updateAgentRoleConfig=function(id,map){state.calls.push([id,clone(map)]);if(state.throwUpdate)throw Error('unknown outcome');if(!state.partial){db.sys_agent_access_role_mapping.push({sys_id:'cccccccccccccccccccccccccccccccc',agent_access_config:outer,role:roles[2],sys_scope:'global'});if(!state.missingCapture)db.sys_update_xml.push(...[outer,'cccccccccccccccccccccccccccccccc'].map((id,i)=>({sys_id:(i?'e':'d').repeat(32),update_set:set,name:['sys_agent_access_role_configuration_','sys_agent_access_role_mapping_'][i]+id,action:'INSERT_OR_UPDATE',payload:'<record_update/>'})));}return state.resultNull?null:{sysId:outer,roleList:roles};};
 const api=fs.existsSync(target)?require(target):null;
 assert(api,'preview-first repair module is not implemented');
 const deps=api.nativeDependencies(gs,GR,function(){this.isImpersonating=()=>ctx.impersonating;},{AgentAccessRoleConfigDAO:DAO});
 const driver=api.create(deps); return {api,db,ctx,state,run:(p={})=>driver.run(p)};
}
test('default preview in Code context reads without writing and is never apply ready',()=>{const f=fixture();f.ctx.application='6d99fe72474f211082179725126d4308';const r=f.run();assert.equal(r.status,'preview',r.code);assert.equal(r.applyReady,false);assert.equal(f.state.calls.length,0);assert(f.state.reads>0);});
for(const [field,value] of [['application','code'],['scope','global'],['name','guest'],['impersonating',true],['admin',false],['systemSet','f'.repeat(32)]]) test('apply refuses wrong '+field,()=>{const f=fixture();f.ctx[field]=value;assert.equal(f.run({apply:true,updateSetId:set}).status,'refused');assert.equal(f.state.calls.length,0);});
for(const field of ['name','application','state']) test('apply refuses capture set '+field+' drift',()=>{const f=fixture();f.db.sys_update_set[0][field]='wrong';assert.equal(f.run({apply:true,updateSetId:set}).status,'refused');assert.equal(f.state.calls.length,0);});
test('apply requires a concrete set id',()=>{const f=fixture();assert.equal(f.run({apply:true}).status,'refused');assert.equal(f.state.calls.length,0);});
for(const table of ['sys_agent_access_role_mapping','sys_security_acl','sn_aia_agent_config']) test('ordinary read denial refuses '+table,()=>{const f=fixture();f.state.denied=table;assert.equal(f.run({apply:true,updateSetId:set}).status,'refused');assert.equal(f.state.calls.length,0);});
test('all field rights checked before values; ACL field denial refuses',()=>{const f=fixture();f.state.denyField='script';assert.equal(f.run({apply:true,updateSetId:set}).status,'refused');assert.equal(f.state.calls.length,0);});
for(const mutate of [f=>f.db.sys_agent_access_role_mapping.pop(),f=>f.db.sys_security_acl[1].script='true',f=>f.db.sn_aia_agent_config[0].run_as_user='admin',f=>f.db.sys_agent_access_role_mapping.push({...f.db.sys_agent_access_role_mapping[0],sys_id:'f'.repeat(32)})]) test('frozen child/ACL/mapping drift refuses',()=>{const f=fixture();mutate(f);assert.equal(f.run({apply:true,updateSetId:set}).status,'refused');assert.equal(f.state.calls.length,0);});
test('one public native update uses the full role list and verifies preserved state/capture',()=>{const f=fixture();const before=clone(f.db.sys_agent_access_role_mapping);const r=f.run({apply:true,updateSetId:set});assert.equal(r.status,'applied',r.code);assert.deepEqual(f.state.calls,[[outer,{roleList:roles}]]);for(const row of before)assert.deepEqual(f.db.sys_agent_access_role_mapping.find(x=>x.sys_id===row.sys_id),row);assert.equal(r.retryAllowed,false);});
for(const flag of ['partial','resultNull','throwUpdate','missingCapture','postReadDenied']) test(flag+' outcome is uncertain and cannot be retried by the same driver',()=>{const f=fixture();f.state[flag]=true;const r=f.run({apply:true,updateSetId:set});assert.equal(r.status,'uncertain',r.code);assert.equal(r.retryAllowed,false);assert.equal(f.state.calls.length,1);assert.equal(f.run({apply:true,updateSetId:set}).status,'refused');assert.equal(f.state.calls.length,1);});
test('extra matching hidden/denied row cannot certify absence',()=>{const f=fixture();f.db.sys_agent_access_role_mapping.push({...f.db.sys_agent_access_role_mapping[0],sys_id:'f'.repeat(32)});assert.equal(f.run().status,'refused');assert.equal(f.state.calls.length,0);});
test('fresh set with existing capture refuses before native update',()=>{const f=fixture();f.db.sys_update_xml.push({sys_id:'d'.repeat(32),update_set:set,name:'earlier',action:'INSERT_OR_UPDATE',payload:'x'});assert.equal(f.run({apply:true,updateSetId:set}).status,'refused');assert.equal(f.state.calls.length,0);});
test('already configured outer mask causes no update',()=>{const f=fixture();f.db.sys_agent_access_role_mapping.push({sys_id:'c'.repeat(32),agent_access_config:outer,role:roles[2],sys_scope:'global'});assert.equal(f.run({apply:true,updateSetId:set}).status,'already-configured');assert.equal(f.state.calls.length,0);});

