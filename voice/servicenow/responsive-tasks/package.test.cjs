'use strict';
const test=require('node:test'), assert=require('node:assert/strict');
const fs=require('node:fs'), vm=require('node:vm'), path=require('node:path'), crypto=require('node:crypto');
const read=name=>fs.readFileSync(path.join(__dirname,name),'utf8');
const Class={create:()=>function(){this.initialize.apply(this,arguments);}};
test('platformBooleanCannotEnableAuthorityAndRegistryDisclaimsPrincipal',()=>{
    const env={Class,gs:{getUserID:()=> 'platform-user',getUserName:()=> 'integration',getProperty:()=> 'true'}};
    vm.runInNewContext(read('LocalLLMVoicePlatform.js'),env);
    const policy=new env.LocalLLMVoicePlatform();
    assert.equal(policy.registry().principal,null);assert.equal(policy.registry().capability_revision,null);
    assert.equal(policy.registry().capabilities.safe_write,false);
    assert.throws(()=>policy.authorize(true),/unqualified/);
    env.gs.getUserName=()=> 'guest';assert.throws(()=>policy.registry(),/denied/);
});
test('resourceRejectsDuplicateEscapedAndUnknownFieldsBeforeAuthorityUse',()=>{
    const env={Class};vm.runInNewContext(read('LocalLLMVoiceResource.js'),env);
    const resource=new env.LocalLLMVoiceResource();
    for(const dataString of ['{"x":1,"x":2}','{"x":1,"\\u0078":2}','{"p":{"x":1,"x":2}}','{"x":[]}']) {
        assert.throws(()=>resource._body({body:{dataString}}),/invalid_schema/);
    }
    assert.equal(resource._body({body:{dataString:'{"kind":"prepare"}'}}).kind,'prepare');
});
test('SCCExtractionExactlyMatchesSavedLegacyBody',()=>{
    const old=fs.readFileSync(path.join(__dirname,'..','scc-laptop-order-tool.js'));
    assert.equal(crypto.createHash('sha256').update(old).digest('hex'),'79f7a17ccc0887ade5004cf10bb12df4a78012ba583590474f84f6cb443f7ffe');
    assert.ok(read('LocalLLMSCCOrderBusiness.js').includes('return '+old.toString().trimEnd()));
    assert.ok(!read('LocalLLMVoiceOrderGuard.js').includes('new sn_sc.CartJS'));
});
function native(overrides={}) {
    let response={}, tests={guest:false,testMode:false,authorized:true,binding:true,opaque:false,...overrides};
    const env={request:{body:{data:{registryVersion:2,serviceId:'a'.repeat(32)}},getHeader:()=>tests.opaque?'Bearer opaque':'Bearer aaa.bbb.ccc'},
        response:{setStatus:s=>response.status=s,setBody:b=>response.body=b},
        VoiceRestUtils:function(){this.validateServiceId=()=>true;this.validateServiceAuthorization=()=>tests.authorized;this.isTestMode=()=>tests.testMode;},
        VoiceAgentUtils:function(){this.getAuthorizedAgentIds=()=>['b'.repeat(32)];},
        sn_auth:{VoiceServiceInfoRequestor:function(){this.getVoiceServiceInfo=()=>JSON.stringify({voice_service_id:(tests.binding?'a':'c').repeat(32)});}},
        gs:{getUserID:()=> 'd'.repeat(32),getUserName:()=>tests.guest?'guest':'integration'},
        GlideDateTime:function(){this.getNumericValue=()=>1000;},GlideDigest:function(){this.getSHA256Hex=s=>crypto.createHash('sha256').update(s).digest('hex');}};
    vm.runInNewContext(read('native-registry-v2.candidate.js'),env);return response;
}
test('nativeProjectionKeepsPlatformActorAndMembershipDistinctFromWriteAuthority',()=>{
    const r=native();assert.equal(r.status,200);
    assert.equal(r.body.principal.kind,'platform_actor');assert.equal(r.body.principal.human_caller_verified,false);
    assert.equal(r.body.capabilities.safe_write,false);assert.equal(r.body.authorized_agent_ids.length,1);
    assert.equal(r.body.snapshot_expires_at,61000);assert.ok(r.body.registry_revision);
});
test('nativeProjectionRejectsGuestOpaqueWrongServiceAndAdminTest',()=>{
    for(const setting of [{guest:true},{testMode:true},{binding:false},{opaque:true}]) assert.equal(native(setting).status,403);
    assert.equal(native({authorized:false}).body,undefined);
});
test('preparedToolCannotOrderAndDoesNotCreateConfirmation',()=>{
    const result=vm.runInNewContext(read('prepare-only-tool.js'),{inputs:{employee_name:'A',start_date:'2026-12-01',delivery_location:'B',manager_name:'C'}});
    assert.equal(result.order_submitted,false);assert.equal(result.authority,'untrusted_candidate');
    assert.equal(result.confirmation_id,undefined);
});
test('GlideRepositoryWritesMandatorySchemaAndReloadsImmutableReceipt',()=>{
    const manifest=JSON.parse(read('schema-manifest.json')), rows={}, actor={principal:'user',service:'service',agent:'agent',tool:'tool',registry_revision:'registry',expires_at:100000,execute:true,write:true};
    let count=0,calls=0;
    function Record(table) {this.table=table;this.filters=[];this.matches=[];this.cursor=-1;rows[table]=rows[table]||[];}
    Record.prototype={
        isValid(){return !!manifest.tables[this.table];},isValidField(name){return !!manifest.tables[this.table][name];},
        initialize(){this.value={};},setValue(k,v){assert.ok(this.isValidField(k));this.value[k]=String(v);},
        addQuery(k,v){this.filters.push([k,String(v)]);},setLimit(){},
        query(){this.matches=rows[this.table].filter(row=>this.filters.every(([k,v])=>row[k]===v));},
        next(){this.value=this.matches[++this.cursor];return !!this.value;},getValue(k){return this.value[k];},getUniqueValue(){return this.value.sys_id;},
        insert(){
            for(const [key,spec] of Object.entries(manifest.tables[this.table])) {
                if(spec.mandatory)assert.ok(this.value[key],`${this.table}.${key} mandatory`);
                if(spec.unique&&rows[this.table].some(row=>row[key]===this.value[key]))return null;
            }
            this.value.sys_id='row-'+(++count);rows[this.table].push({...this.value});return this.value.sys_id;
        }
    };
    const env={Class,GlideRecord:Record,gs:{generateGUID:()=> 'id-'+(++count)},GlideDateTime:function(){this.getNumericValue=()=>1000;},GlideDigest:function(){this.getSHA256Hex=s=>crypto.createHash('sha256').update(s).digest('hex');}};
    for(const name of ['LocalLLMVoiceRepository','LocalLLMVoiceTaskControl','LocalLLMVoiceOrderGuard'])vm.runInNewContext(read(name+'.js'),env);
    const repo=new env.LocalLLMVoiceRepository(),engine=new env.LocalLLMVoiceTaskControl(repo,{authorize:()=>actor},{submit:()=>{calls++;return {ok:true,request_id:'req',requested_item_id:'ritm'};}});
    const t=engine.create({command_id:'create',objective:'Laptop',context_version:1});
    const proposal={employee_name:'A',start_date:'2026-12-01',delivery_location:'B',manager_name:'C'};
    const p=engine.command(t.task_id,{command_id:'prepare',kind:'prepare',expected_revision:'root',context_version:1,proposal});
    const c=engine.command(t.task_id,{command_id:'confirm',kind:'confirm',expected_revision:p.revision,context_version:1,proposal_id:p.revision,utterance_ref:'u1'});
    const command={command_id:'commit',kind:'commit',expected_revision:c.revision,context_version:1,proposal_id:p.revision,confirmation_id:c.revision,operation_key:'op'};
    engine.command(t.task_id,command);engine.command(t.task_id,command);
    assert.equal(calls,1);assert.equal(engine.operation('op').receipt.execution_ref,'ritm');
    assert.equal(engine.status(t.task_id).events[0].operation_id,'op');
    assert.ok(rows.u_scc_voice_dispatch_claim[0].u_operation);
    assert.throws(()=>repo.get('sys_user','id','arbitrary'),/invalid_table/);
});
