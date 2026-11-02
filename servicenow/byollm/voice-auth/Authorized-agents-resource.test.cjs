'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const crypto = require('node:crypto');
const SOURCE = fs.readFileSync(path.join(__dirname, 'Authorized-agents-resource.js'), 'utf8');
const ID = '11111111111111111111111111111111';
const SERVICE = '22222222222222222222222222222222';
const PROFILE = '33333333333333333333333333333333';
const AGENT = '44444444444444444444444444444444';
const OTHER = '55555555555555555555555555555555';
const FIELDS = ['sys_id','user_name','email','active','locked_out'];
const SELF = {sys_id: ID,user_name: 'verified.username',email: 'real.email@example.invalid',active: '1',locked_out: '0'};
const clone = value => JSON.parse(JSON.stringify(value));
const AUTH_PROFILE='c623e20f93374354e7f2b9fa6aba1081';
const AUTH_SERVICE='8aa131d793f787105c8132d47aba1095';
const APP='200af60f93fb4354e7f2b9fa6aba107d';
const CONVERSATION='66666666666666666666666666666666',INTERACTION='77777777777777777777777777777777',MESSAGE='88888888888888888888888888888888';
const ACCOUNT='99999999999999999999999999999999',USER_PROFILE='aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',CONSUMER='bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb';
const SESSION='cccccccccccccccccccccccccccccccc',DEVICE='dddddddddddddddddddddddddddddddd';
const CREATED='2026-11-02 12:00:00',NOW=Date.parse('2026-11-02T12:00:10Z');
const authPayload=()=>({serviceId:AUTH_SERVICE,assistantSettingsVersion:1,callerBindingVersion:1,conversationAuthenticationVersion:1,conversationId:CONVERSATION,interactionId:INTERACTION,createMessageId:MESSAGE});
const authSettings=()=>({version:1,service_id:AUTH_SERVICE,context_profile:AUTH_PROFILE});

function ownershipEnvironment(options,events) {
  const db={
    sys_cs_conversation:{[CONVERSATION]:{sys_id:CONVERSATION,consumer_account:ACCOUNT,context_profile:AUTH_PROFILE,current_device:DEVICE,state:'open',sys_created_on:CREATED}},
    sys_cs_consumer_account:{[ACCOUNT]:{sys_id:ACCOUNT,provider_application:APP,channel_user_profile:USER_PROFILE,consumer:CONSUMER}},
    sys_cs_provider_application:{[APP]:{sys_id:APP,inbound_id:'scc-local-voice',provider:'d6eadc7a53301010ad77ddeeff7b124a'}},
    sys_cs_channel_user_profile:{[USER_PROFILE]:{sys_id:USER_PROFILE,active:'1',user_table:'sys_user',user_document:ID,channel_user_id:'synthetic-provider-user',channel:'51cdaa4c53a710105893ddeeff7b129c'}},
    sys_cs_consumer:{[CONSUMER]:{sys_id:CONSUMER,user_id:ID,inactive:'0'}},
    interaction:{[INTERACTION]:{sys_id:INTERACTION,channel_metadata_document:CONVERSATION,provider_application:APP,state:'new',active:'1',type:'chat',sys_created_on:CREATED,verified:'0'}},
    sys_cs_message:{[MESSAGE]:{sys_id:MESSAGE,conversation:CONVERSATION,consumer_account:ACCOUNT,session:SESSION,direction:'outbound',message_type:'action',payload:JSON.stringify({type:'CreateConversation',topicId:CONVERSATION,interactionId:INTERACTION}),sys_created_on:CREATED}},
    sys_cs_session:{[SESSION]:{sys_id:SESSION,consumer_account:ACCOUNT,consumer:CONSUMER,device_id:DEVICE,device_type:'Bot to Bot',end_time:''}}
  };
  for(const [table,changes]of Object.entries(options.proofChanges||{})){const id=Object.keys(db[table])[0];Object.assign(db[table][id],changes);}
  const fields=Object.fromEntries(Object.entries(db).map(([table,rows])=>[table,Object.keys(Object.values(rows)[0])]));
  const calls=[],reads=[],queries=[],getCounts={};
  function record(secure,table){
    assert.ok(db[table],'only known ownership tables are queried');
    let data=null,index=-1,conditions=[],result=[],limit,recordAllowed=false,checked=new Set();
    const key=()=>table+':'+(data?.sys_id||'');
    const denied=()=>options.denyRecord===table || (index===1&&options.hiddenInteractionDuplicate);
    return {
      isValid(){return options.badProofTable!==table;},
      isValidField(field){return fields[table].includes(field)&&options.badProofField!==table+':'+field&&!(table==='interaction'&&field==='verified'&&options.badVerifiedSchema);},
      get(id){getCounts[table]=(getCounts[table]||0)+1;if(options.missingProof===table||!db[table][id]||(table==='interaction'&&getCounts[table]===3&&options.missingWritableInteraction))return false;
        if(options.driftProof===table&&getCounts[table]===2)db[table][id][table==='interaction'?'state':fields[table].at(-1)]='CHANGED_DURING_PROOF';
        if(table==='interaction'&&getCounts[table]===3&&options.writableProofDrift)db[table][id].state='closed_complete';
        data=clone(db[table][id]);index=0;recordAllowed=false;checked=new Set();return true;},
      canRead(){recordAllowed=!denied();events.push(['proof-record-right',table,index]);return recordAllowed;},
      canWrite(){events.push(['proof-record-write-right',table,index]);return !(table==='interaction'&&options.interactionWriteDenied);},
      getElement(field){if(options.missingProofElement===table+':'+field||(table==='interaction'&&field==='verified'&&options.missingVerifiedElement))return undefined;return {canRead(){checked.add(field);events.push(['proof-field-right',table,index,field]);return options.denyProofField!==table+':'+field&&!(index===1&&options.deniedDuplicateField===field);},canWrite(){events.push(['proof-field-write-right',table,index,field]);return !(table==='interaction'&&field==='verified'&&options.verifiedWriteDenied);}};},
      getValue(field){assert.equal(recordAllowed,true,'ownership record right before values');assert.ok(fields[table].filter(f=>table!=='interaction'||f!=='verified').every(f=>checked.has(f)),'ALL ownership field rights before ANY value');
        assert.notEqual(options.denyProofField,table+':'+field);assert.equal(index===1&&!!options.deniedDuplicateField,false,'no duplicate values when a required field denied');reads.push([table,index,field]);return data[field]??null;},
      addQuery(field,value){assert.equal(secure,false);assert.equal(table,'interaction');assert.equal(field,'channel_metadata_document');conditions.push([field,value]);},
      setLimit(value){limit=value;},
      query(){assert.equal(secure,false);assert.equal(limit,2);assert.deepEqual(conditions,[['channel_metadata_document',CONVERSATION]]);queries.push({table,conditions:clone(conditions),limit});
        result=Object.values(db.interaction).map(clone);if(options.noInteractionMatch)result=[];
        if(options.duplicateInteraction||options.hiddenInteractionDuplicate||options.deniedDuplicateField)result.push({...clone(db.interaction[INTERACTION]),sys_id:OTHER});
        if(options.wrongInteractionMatch)result[0].sys_id=OTHER;result=result.slice(0,limit);index=-1;},
      next(){const next=index+1;if(next>=result.length)return false;index=next;data=result[index];recordAllowed=false;checked=new Set();return true;}
    };
  }
  let clockCalls=0;
  function DateTime(){clockCalls++;let stamp=options.now===undefined?NOW:options.now;if(options.lateExpiry&&clockCalls>6)stamp=NOW+60000;return {setValue(value){stamp=Date.parse(value.replace(' ','T')+'Z');},getValue(){return Number.isFinite(stamp)?new Date(stamp).toISOString().slice(0,19).replace('T',' '):'INVALID';},getNumericValue(){return stamp;}};}
  function elevate(user,conversation){calls.push([user,conversation]);if(options.elevationThrows)throw new Error('PRIVATE_NATIVE_FAILURE');return options.elevationReturn;}
  return {record,DateTime,elevate,calls,reads,queries,db};
}

function run(options = {}, source = SOURCE) {
  const own = {...SELF,...options.own};
  const payload = options.payload === undefined ? {serviceId: SERVICE,assistantSettingsVersion: 1,callerBindingVersion: 1} : clone(options.payload);
  const originalPayload = clone(payload);
  const settings = options.settings === undefined ? {version: 1,service_id: SERVICE,context_profile: PROFILE,prompt: {systemMessage: 'UNCHANGED'}} : clone(options.settings);
  const originalSettings = clone(settings);
  const events = [], instances = [], queries = [], valueReads = [];
  const ownership=ownershipEnvironment(options,events);
  const response = {setStatus(value) { this.status = value; },setBody(value) { this.body = value; }};
  const counters = {settings: 0,agents: 0,nativeService: 0};
  let currentIdReads=0;
  function record(secure, table) {
    if(table!=='sys_user')return ownership.record(secure,table);
    assert.equal(table, 'sys_user');
    const kind = secure ? 'self' : 'uniqueness';
    const instance = {kind,table}; instances.push(instance);
    let row = null, ordinal = -1, rights = false, checked = new Set(), conditions = [], limit;
    let rows = [];
    function reset(value, index) { row = value; ordinal = index; rights = false; checked = new Set(); }
    const api = {
      isValid() { return options.invalidTable !== kind; },
      isValidField(field) { return FIELDS.includes(field) && options.invalidField !== kind + ':' + field; },
      get(id) { assert.equal(kind, 'self'); assert.equal(id, options.currentId || ID); if (options.missingSelf) return false; reset({values: own,...options.ownRights},0); return true; },
      canRead() { events.push(['record-right',kind,ordinal]); rights = !row || row.canRead !== false; return rights; },
      getElement(field) {
        if (options.missingElement === kind + ':' + field) return null;
        return {canRead() { events.push(['field-right',kind,ordinal,field]); checked.add(field); return !(row?.deniedFields || []).includes(field); }};
      },
      getValue(field) {
        assert.equal(rights, true, 'record right must precede every value read');
        assert.ok(FIELDS.every(name => checked.has(name)), 'ALL field rights must precede ANY value read');
        assert.notEqual(row.canRead, false, 'denied record values must never be read');
        assert.ok(!(row.deniedFields || []).length, 'denied field set must prevent all value reads');
        valueReads.push([kind,ordinal,field]);
        if (options.throwValue === kind + ':' + field) throw new Error('PRIVATE_FAILURE_VALUE');
        return row.values[field] ?? null;
      },
      addQuery(field, value) { assert.equal(kind,'uniqueness'); assert.equal(api.isValidField(field),true); conditions.push([field,value]); },
      setLimit(value) { limit = value; },
      query() {
        assert.equal(kind,'uniqueness'); assert.equal(limit,2);
        assert.deepEqual(conditions,[['email',own.email],['active',true],['locked_out',false]]);
        queries.push({table,conditions: clone(conditions),limit});
        if (options.queryThrows) throw new Error('PRIVATE_QUERY_FAILURE');
        rows = options.matches === undefined ? [{values: own}] : options.matches.map(row => row.values ? clone(row) : {values: {...SELF,...row}});
        rows = rows.slice(0,limit); reset(null,-1);
      },
      next() { const next = ordinal + 1; if (next >= rows.length) return false; reset(rows[next],next); return true; }
    };
    for (const method of ['insert','update','deleteRecord','deleteMultiple','setValue','setWorkflow','setUseEngines','queryNoDomain','setQueryNoDomain','setLimitNoDomain']) {
      api[method] = () => assert.fail('forbidden mutation/bypass ' + method);
    }
    return api;
  }
  function deny(response) { response.setStatus(403); response.setBody({detail: 'Native authorization rejected'}); return false; }
  const context = {
    request: {body: {data: payload},getHeader() { return options.header === undefined ? 'Bearer aaa.bbb.ccc' : options.header; }},
    response,
    gs: {getUserID() { currentIdReads++;if(options.changedGsDuringProof&&currentIdReads>=4)return OTHER;return options.currentId === undefined ? ID : options.currentId; },getUserName() { return options.currentName === undefined ? SELF.user_name : options.currentName; },
      info() { assert.fail('no logs'); },warn() { assert.fail('no logs'); },error() { assert.fail('no logs'); },setProperty() { assert.fail('no property writes'); }},
    VoiceRestUtils: function () { return {
      validateServiceId(request,response) { return options.serviceDenied ? deny(response) : true; },
      validateServiceAuthorization(request,response) { return options.authDenied ? deny(response) : true; },
      isTestMode() { return false; }
    }; },
    VoiceAgentUtils: function () { return {getAuthorizedAgentIds() { counters.agents++; return options.agents === undefined ? [AGENT] : clone(options.agents); }}; },
    sn_auth: {VoiceServiceInfoRequestor: function () { return {getVoiceServiceInfo() { counters.nativeService++; if (options.nativeServiceThrows) throw new Error('PRIVATE_NATIVE_FAILURE'); return JSON.stringify({voice_service_id: options.boundService || SERVICE}); }}; }},
    LocalLLMVoiceAssistantSettings: function () { return {getSettings(id) { counters.settings++; assert.equal(id,options.requestService||SERVICE); if (options.settingsThrows) throw new Error('PRIVATE_SETTINGS_FAILURE'); return settings; }}; },
    GlideRecordSecure: function (table) { return record(true,table); },
    GlideRecord: function (table) { return record(false,table); },
    GlideDateTime: ownership.DateTime,
    VoiceConversationManager: function(){return {elevateConversationSession:ownership.elevate};}
  };
  vm.runInNewContext(source,context,{timeout:1000});
  return {status: response.status,body: response.body === undefined ? undefined : clone(response.body),instances,events,queries,valueReads,counters,
    payload: clone(payload),originalPayload,settings: clone(settings),originalSettings,ownership};
}

function refused(options) {
  const result = run(options);
  assert.equal(result.status,403);
  assert.deepEqual(result.body,{detail: 'Caller binding unavailable'});
  assert.equal(JSON.stringify(result.body).includes(SELF.email),false);
  assert.equal(JSON.stringify(result.body).includes('PRIVATE'),false);
  return result;
}

test('exact seven-key binding uses verified request self, real email and actual settings profile', () => {
  const result = run();
  assert.equal(result.status,200);
  assert.deepEqual(result.body.caller_binding,{version:1,service_id:SERVICE,user_id:ID,user_name:SELF.user_name,email:SELF.email,email_mapping_unique:true,context_profile:PROFILE});
  assert.deepEqual(Object.keys(result.body).sort(),['assistant_settings','authorized_agents','caller_binding']);
  assert.deepEqual(Object.keys(result.body.caller_binding).sort(),['context_profile','email','email_mapping_unique','service_id','user_id','user_name','version']);
  assert.deepEqual(result.body.assistant_settings,result.originalSettings);
  assert.deepEqual(result.settings,result.originalSettings);
  assert.deepEqual(result.payload,result.originalPayload);
  assert.deepEqual(result.queries,[{table:'sys_user',conditions:[['email',SELF.email],['active',true],['locked_out',false]],limit:2}]);
});
test('email-shaped username remains username; actual stored email supplies native mapping', () => {
  const result = run({currentName:'looks.like@email.invalid',own:{user_name:'looks.like@email.invalid',email:'actual.mail@example.invalid'}});
  assert.equal(result.body.caller_binding.email,'actual.mail@example.invalid');
  assert.equal(result.body.caller_binding.user_name,'looks.like@email.invalid');
  assert.equal(result.queries[0].conditions[0][1],'actual.mail@example.invalid');
});
test('profile is actual server settings profile and ignores request-selected identity/profile', () => {
  const profile = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
  const result = run({settings:{version:1,service_id:SERVICE,context_profile:profile},payload:{serviceId:SERVICE,assistantSettingsVersion:1,callerBindingVersion:1,user_id:OTHER,email:'spoof@example.invalid',context_profile:PROFILE}});
  assert.equal(result.body.caller_binding.user_id,ID);
  assert.equal(result.body.caller_binding.email,SELF.email);
  assert.equal(result.body.caller_binding.context_profile,profile);
});
for (const options of [{serviceDenied:true},{authDenied:true}]) test('native authorization failure stops before binding queries ' + JSON.stringify(options), () => {
  const result = run(options); assert.equal(result.status,403); assert.equal(result.instances.length,0); assert.equal(result.counters.settings,0);
});
for (const options of [{currentName:'guest'},{currentId:''},{header:''},{header:'Bearer aaa.bbb.ccc '},{agents:[]},{agents:['not-a-guid']},{boundService:OTHER},{nativeServiceThrows:true}]) test('existing authenticated settings guards remain intact ' + JSON.stringify(options), () => {
  const result = run(options); assert.equal(result.status,403); assert.equal(result.instances.length,0); assert.equal(result.counters.settings,0);
});
test('legacy bare agent array remains unchanged even with binding flag alone', () => {
  const payload = {serviceId:SERVICE,callerBindingVersion:1};
  const result = run({payload});
  assert.deepEqual(result.body,[AGENT]); assert.equal(result.instances.length,0); assert.equal(result.counters.settings,0);
});
test('existing settings response without new opt-in is byte-equivalent and never looks up users', () => {
  const payload = {serviceId:SERVICE,assistantSettingsVersion:1};
  const result = run({payload});
  assert.deepEqual(result.body,{authorized_agents:[AGENT],assistant_settings:result.originalSettings});
  assert.equal(result.instances.length,0); assert.equal('caller_binding' in result.body,false);
});
for (const version of [2,'1',null,false,{}]) test('wrong binding version fails generically ' + JSON.stringify(version), () => {
  const result = refused({payload:{serviceId:SERVICE,assistantSettingsVersion:1,callerBindingVersion:version}});
  assert.equal(result.instances.length,0); assert.equal(result.counters.settings,0);
});
for (const [label,options] of Object.entries({
  missingSelf:{missingSelf:true},recordDenied:{ownRights:{canRead:false}},wrongId:{own:{sys_id:OTHER}},wrongUsername:{own:{user_name:'other'}},
  noEmail:{own:{email:''}},inactive:{own:{active:'0'}},locked:{own:{locked_out:'1'}},badCurrentId:{currentId:'invalid'},
  missingSelfSchema:{invalidField:'self:email'},missingUniquenessSchema:{invalidField:'uniqueness:email'},missingElement:{missingElement:'self:email'},
  invalidSelfTable:{invalidTable:'self'},invalidUniquenessTable:{invalidTable:'uniqueness'},valueException:{throwValue:'self:email'},queryException:{queryThrows:true}
})) test('own identity and access failures refuse ' + label, () => { refused(options); });
for (const field of FIELDS) test('denied own field ' + field + ' prevents ALL value reads', () => {
  const result = refused({ownRights:{deniedFields:[field]}}); assert.equal(result.valueReads.length,0);
});
test('zero native email matches refuses', () => { refused({matches:[]}); });
test('single active email match must be the exact current user', () => { refused({matches:[{...SELF,sys_id:OTHER,user_name:'other'}]}); });
test('two readable native matches refuse and disclose no duplicate values', () => { refused({matches:[{...SELF},{...SELF,sys_id:OTHER,user_name:'other'}]}); });
for (const position of [0,1]) test('hidden native matching row ' + position + ' is visible to ordinary query but values are never read', () => {
  const rows = [{values:{...SELF}},{values:{...SELF,sys_id:OTHER,user_name:'HIDDEN_PRIVATE_NAME'}}];
  rows[position].canRead=false;
  const result = refused({matches:rows});
  assert.equal(result.valueReads.some(([kind,index]) => kind==='uniqueness' && index===position),false);
});
for (const field of FIELDS) test('denied duplicate-row field ' + field + ' prevents ANY values on that row', () => {
  const result = refused({matches:[{values:{...SELF}},{values:{...SELF,sys_id:OTHER},deniedFields:[field]}]});
  assert.equal(result.valueReads.some(([kind,index]) => kind==='uniqueness' && index===1),false);
});
for (const settings of [{version:1,service_id:SERVICE},{version:1,service_id:SERVICE,context_profile:'bad'},{version:2,service_id:SERVICE,context_profile:PROFILE},{version:1,service_id:OTHER,context_profile:PROFILE}]) test('binding rejects invalid actual settings/profile contract ' + JSON.stringify(settings), () => { refused({settings}); });
test('existing settings helper failure retains generic existing 503 response', () => {
  const result = run({settingsThrows:true}); assert.equal(result.status,503); assert.deepEqual(result.body,{detail:'Assistant settings unavailable'});
});
test('no new caller-binding data appears in settings, legacy response, logs, model or property APIs', () => {
  const result = run();
  assert.equal(JSON.stringify(result.body.assistant_settings).includes('caller_binding'),false);
  assert.equal(JSON.stringify(result.body.assistant_settings).includes(SELF.email),false);
  assert.doesNotMatch(SOURCE,/\.(?:setWorkflow|setUseEngines|queryNoDomain|setQueryNoDomain|insert|update|deleteRecord|deleteMultiple)\s*\(/);
  assert.equal((SOURCE.match(/\.setValue\(/g)||[]).length,1);
  assert.match(SOURCE,/when\.setValue\(created\)/);
  assert.doesNotMatch(SOURCE,/gs\.(?:info|warn|error|setProperty)|GlideImpersonate|GlideUpdateManager|new\s+global\./);
  assert.equal((SOURCE.match(/setLimit\(2\)/g)||[]).length,2);
  assert.match(SOURCE,/element === null \|\| typeof element === 'undefined'/);
});

function authenticate(options={}){return run({payload:authPayload(),settings:authSettings(),boundService:AUTH_SERVICE,requestService:AUTH_SERVICE,...options});}
function authRefused(options={}){
 const result=authenticate(options);assert.equal(result.status,403);assert.equal(result.ownership.calls.length,0);
 assert.equal('conversation_authentication' in result.body,false);assert.equal(JSON.stringify(result.body).includes(SELF.email),false);assert.equal(JSON.stringify(result.body).includes('PRIVATE'),false);
 return result;
}
test('owned fresh CREATE requests one public native refresh with exact seven-key non-authentication receipt',()=>{
 const result=authenticate();assert.equal(result.status,200);assert.deepEqual(result.ownership.calls,[[ID,CONVERSATION]]);
 assert.deepEqual(result.body.conversation_authentication,{version:1,refresh_requested:true,service_id:AUTH_SERVICE,context_profile:AUTH_PROFILE,conversation_id:CONVERSATION,interaction_id:INTERACTION,create_message_id:MESSAGE});
 assert.deepEqual(Object.keys(result.body.conversation_authentication).sort(),['context_profile','conversation_id','create_message_id','interaction_id','refresh_requested','service_id','version']);
 assert.equal('authenticated' in result.body.conversation_authentication,false);assert.equal('user_id' in result.body.conversation_authentication,false);
 assert.equal(result.body.caller_binding.user_id,ID);assert.deepEqual(result.settings,result.originalSettings);
});
test('refresh does not require clientApp admin_test and preserves native test-mode semantics',()=>{const payload=authPayload();assert.equal('clientApp'in payload,false);assert.equal(authenticate({payload}).status,200);});
test('another natively authorized service with the same profile cannot request this bounded refresh',()=>{authRefused({payload:{...authPayload(),serviceId:OTHER},settings:{...authSettings(),service_id:OTHER},boundService:OTHER,requestService:OTHER});});
test('without conversation authentication opt-in there is no native refresh or ownership query',()=>{const result=run();assert.equal(result.status,200);assert.equal(result.ownership.calls.length,0);assert.equal(result.ownership.queries.length,0);assert.equal('conversation_authentication'in result.body,false);});
for(const version of [2,'1',null,false])test('unsupported conversation authentication version refuses '+JSON.stringify(version),()=>{authRefused({payload:{...authPayload(),conversationAuthenticationVersion:version}});});
for(const key of ['conversationId','interactionId','createMessageId'])for(const value of [undefined,'not-a-guid'])test('mandatory CREATE GUID '+key+' refuses '+String(value),()=>{const payload=authPayload();if(value===undefined)delete payload[key];else payload[key]=value;authRefused({payload});});
test('refresh requires the caller-binding opt-in',()=>{const payload=authPayload();delete payload.callerBindingVersion;authRefused({payload});});
test('legacy agent array contract has no refresh even if new flag is supplied alone',()=>{const result=run({payload:{serviceId:SERVICE,conversationAuthenticationVersion:1,conversationId:CONVERSATION,interactionId:INTERACTION,createMessageId:MESSAGE}});assert.deepEqual(result.body,[AGENT]);assert.equal(result.ownership.calls.length,0);});
for(const state of ['chatInProgress','autoPilotInProgress','completed','chatEnded','canceled','faulted','deleted','', 'unknown'])test('non-creation conversation state refuses '+state,()=>{authRefused({proofChanges:{sys_cs_conversation:{state}}});});
for(const state of ['new','work_in_progress'])test('observed active interaction creation state accepts '+state,()=>{assert.equal(authenticate({proofChanges:{interaction:{state}}}).status,200);});
for(const state of ['on_hold','closed_complete','closed_abandoned','','unknown'])test('held, closed or unknown interaction refuses '+state,()=>{authRefused({proofChanges:{interaction:{state}}});});
for(const [label,proofChanges]of Object.entries({
 otherProfile:{sys_cs_conversation:{context_profile:PROFILE}},wrongApp:{sys_cs_consumer_account:{provider_application:OTHER}},wrongAppAlias:{sys_cs_provider_application:{inbound_id:'other-app'}},
 wrongProvider:{sys_cs_provider_application:{provider:OTHER}},inactiveProfile:{sys_cs_channel_user_profile:{active:'0'}},nonUserProfile:{sys_cs_channel_user_profile:{user_table:'other_table'}},
 otherLinkedUser:{sys_cs_channel_user_profile:{user_document:OTHER}},missingProviderAlias:{sys_cs_channel_user_profile:{channel_user_id:''}},wrongChannel:{sys_cs_channel_user_profile:{channel:OTHER}},
 otherConsumerUser:{sys_cs_consumer:{user_id:OTHER}},inactiveConsumer:{sys_cs_consumer:{inactive:'1'}},wrongInteractionConversation:{interaction:{channel_metadata_document:OTHER}},
 wrongInteractionApp:{interaction:{provider_application:OTHER}},inactiveInteraction:{interaction:{active:'0'}},nonChat:{interaction:{type:'voice'}},
 wrongMessageConversation:{sys_cs_message:{conversation:OTHER}},wrongMessageAccount:{sys_cs_message:{consumer_account:OTHER}},inboundMessage:{sys_cs_message:{direction:'inbound'}},
 textMessage:{sys_cs_message:{message_type:'text'}},wrongSessionAccount:{sys_cs_session:{consumer_account:OTHER}},wrongSessionConsumer:{sys_cs_session:{consumer:OTHER}},
 wrongDevice:{sys_cs_session:{device_id:OTHER}},wrongDeviceType:{sys_cs_session:{device_type:'Other'}},endedSession:{sys_cs_session:{end_time:CREATED}}
}))test('ownership mismatch refuses '+label,()=>{authRefused({proofChanges});});
for(const payload of [
 {type:'StartConversation',topicId:CONVERSATION,interactionId:INTERACTION},
 {type:'CreateConversation',topicId:OTHER,interactionId:INTERACTION},
 {type:'CreateConversation',topicId:CONVERSATION,interactionId:OTHER},
 {type:'CreateConversation',topicId:CONVERSATION,interactionId:INTERACTION,requestId:'unpersisted-correlation'},
 null
])test('native CREATE payload must match the observed exact tuple '+JSON.stringify(payload),()=>{authRefused({proofChanges:{sys_cs_message:{payload:JSON.stringify(payload)}}});});
test('malformed CREATE JSON refuses without disclosing payload',()=>{authRefused({proofChanges:{sys_cs_message:{payload:'PRIVATE malformed JSON'}}});});
test('server freshness allows exactly 45 seconds',()=>{assert.equal(authenticate({now:Date.parse('2026-11-02T12:00:45Z')}).status,200);});
test('server freshness rejects past 45 seconds',()=>{authRefused({now:Date.parse('2026-11-02T12:00:45.001Z')});});
test('server freshness rejects future creation time',()=>{authRefused({now:Date.parse('2026-11-02T11:59:59Z')});});
for(const table of ['sys_cs_conversation','interaction','sys_cs_message'])for(const created of ['2020-01-01 00:00:00','INVALID'])test('required native creation timestamp refuses '+table+' '+created,()=>{authRefused({proofChanges:{[table]:{sys_created_on:created}}});});
const proofFieldLists={sys_cs_conversation:['sys_id','consumer_account','context_profile','current_device','state','sys_created_on'],
 sys_cs_consumer_account:['sys_id','provider_application','channel_user_profile','consumer'],sys_cs_provider_application:['sys_id','inbound_id','provider'],
 sys_cs_channel_user_profile:['sys_id','active','user_table','user_document','channel_user_id','channel'],sys_cs_consumer:['sys_id','user_id','inactive'],
 interaction:['sys_id','channel_metadata_document','provider_application','state','active','type','sys_created_on'],
 sys_cs_message:['sys_id','conversation','consumer_account','session','direction','message_type','payload','sys_created_on'],sys_cs_session:['sys_id','consumer_account','consumer','device_id','device_type','end_time']};
for(const [table,fields]of Object.entries(proofFieldLists)){
 test('missing ownership record refuses '+table,()=>{authRefused({missingProof:table});});
 test('invalid ownership table schema refuses '+table,()=>{authRefused({badProofTable:table});});
 test('invalid ownership field schema refuses '+table,()=>{const r=authRefused({badProofField:table+':sys_id'});assert.equal(r.ownership.reads.some(([t])=>t===table),false);});
 test('missing ownership GlideElement refuses '+table,()=>{const r=authRefused({missingProofElement:table+':sys_id'});assert.equal(r.ownership.reads.some(([t])=>t===table),false);});
 test('denied ownership record refuses '+table,()=>{const r=authRefused({denyRecord:table});assert.equal(r.ownership.reads.some(([t])=>t===table),false);});
 for(const field of fields)test('denied ownership field prevents ALL values '+table+'.'+field,()=>{const r=authRefused({denyProofField:table+':'+field});assert.equal(r.ownership.reads.some(([t])=>t===table),false);});
 test('final ownership reread detects drift '+table,()=>{authRefused({driftProof:table});});
}
for(const options of [{noInteractionMatch:true},{wrongInteractionMatch:true},{duplicateInteraction:true},{hiddenInteractionDuplicate:true},{deniedDuplicateField:'provider_application'}])test('native interaction lookup is complete, readable and unique '+JSON.stringify(options),()=>{const r=authRefused(options);if(options.hiddenInteractionDuplicate||options.deniedDuplicateField)assert.equal(r.ownership.reads.some(([table,index])=>table==='interaction'&&index===1),false);});
test('native refresh exception produces generic refusal without retry',()=>{const r=authenticate({elevationThrows:true});assert.equal(r.status,403);assert.deepEqual(r.ownership.calls,[[ID,CONVERSATION]]);assert.equal('conversation_authentication'in r.body,false);assert.equal(JSON.stringify(r.body).includes('PRIVATE'),false);});
for(const nativeReturn of [undefined,false,{unknown:'native result'}])test('native result is not guessed into authentication success '+JSON.stringify(nativeReturn),()=>{const r=authenticate({elevationReturn:nativeReturn});assert.equal(r.status,200);assert.equal(r.body.conversation_authentication.refresh_requested,true);assert.equal('authenticated'in r.body.conversation_authentication,false);assert.equal(Object.keys(r.body.conversation_authentication).length,7);});
test('client identity and raw callback request ID are not used as server proof',()=>{const r=authenticate({payload:{...authPayload(),userId:OTHER,USER_REF:OTHER,actual_user:OTHER,createRequestId:'not-server-verified'}});assert.deepEqual(r.ownership.calls,[[ID,CONVERSATION]]);assert.equal(Object.keys(r.body.conversation_authentication).length,7);});
for(const empty of ['',null,'   '])test('equal missing or blank device identifiers do not prove ownership '+JSON.stringify(empty),()=>{authRefused({proofChanges:{sys_cs_conversation:{current_device:empty},sys_cs_session:{device_id:empty}}});});
test('freshness is checked again immediately before the native refresh',()=>{authRefused({lateExpiry:true});});
test('original gs user must remain the same immediately before the native refresh',()=>{authRefused({changedGsDuringProof:true});});
for(const options of [{interactionWriteDenied:true},{verifiedWriteDenied:true},{denyProofField:'interaction:verified'},{missingVerifiedElement:true},{badVerifiedSchema:true},{missingWritableInteraction:true},{writableProofDrift:true}])test('normal fresh interaction/verified write rights and unchanged ownership are mandatory '+JSON.stringify(options),()=>{authRefused(options);});
test('normal interaction record and verified field write rights are checked without manually setting any value',()=>{const r=authenticate();assert.equal(r.status,200);assert.ok(r.events.some(e=>e[0]==='proof-record-write-right'&&e[1]==='interaction'));assert.ok(r.events.some(e=>e[0]==='proof-field-write-right'&&e[1]==='interaction'&&e[3]==='verified'));assert.equal(r.ownership.reads.some(([table,index,field])=>table==='interaction'&&field==='verified'),false);});
test('public native refresh is the only side-effect site, never protected/private helper invocation',()=>{assert.equal((SOURCE.match(/new VoiceConversationManager\(\)\.elevateConversationSession\(currentId,conversationId\)/g)||[]).length,1);assert.doesNotMatch(SOURCE,/new VoiceConversationManagerSNC|new sn_cs_adapter|_getToken\(|\.elevateSession\(|decryptToken\(/);});
test('canonical resource matches the reviewed native script and retains its administrative settings boundary', () => {
  assert.equal(crypto.createHash('sha256').update(SOURCE).digest('hex'),'b9f11c0d659a34c5c200eeed5d212e7ed05ee204f364c6f3c14fa0fcdb44ea39');
  assert.equal((SOURCE.match(/new LocalLLMVoiceAssistantSettings\(\)\.getSettings\(serviceId\)/g)||[]).length,1);
  assert.doesNotMatch(SOURCE,/getSettingsJSON|LocalLLMVoiceAssistantSettings\.prototype/);
});
