'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),crypto=require('node:crypto');
const SOURCE=fs.readFileSync(path.join(__dirname,'Local-caller-create-resource.js'),'utf8');
const ID='11111111111111111111111111111111',OTHER='22222222222222222222222222222222',RID='33333333333333333333333333333333',SID='44444444444444444444444444444444',MID='55555555555555555555555555555555';
const SERVICE='8aa131d793f787105c8132d47aba1095',PROFILE='c623e20f93374354e7f2b9fa6aba1081',AGENT='a6337ddf93f787105c8132d47aba1058';
const APP='200af60f93fb4354e7f2b9fa6aba107d',CHANNEL='51cdaa4c53a710105893ddeeff7b129c';
const C='66666666666666666666666666666666',I='77777777777777777777777777777777',M='88888888888888888888888888888888',A='99999999999999999999999999999999';
const P='aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',U='bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',S='cccccccccccccccccccccccccccccccc',D='dddddddddddddddddddddddddddddddd';
const AUTH='Bearer original_fixture',TOKEN='provider_fixture',ALIAS='voice-'+SID,CREATED='2026-11-02 12:00:00',NOW=Date.parse('2026-11-02T12:00:10Z');
const USER={sys_id:ID,user_name:'original.fixture',email:'original@example.invalid',active:'1',locked_out:'0'};
const clone=value=>JSON.parse(JSON.stringify(value)),hash=value=>crypto.createHash('sha256').update(value).digest('hex');
const payload=()=>({version:1,requestId:RID,clientSessionId:SID,clientMessageId:MID});
function run(options={}){
 const input=options.input===undefined?payload():clone(options.input),initialInput=clone(input);
 const settings=options.settings===undefined?{version:1,service_id:SERVICE,context_profile:PROFILE,language:'de',prompt:{systemMessage:'UNCHANGED'}}:clone(options.settings),initialSettings=clone(settings);
 const user={...USER,...options.user};let created=false,gsDrift=false;
 const db={sys_user:{[ID]:user},
  sys_cs_conversation:{[C]:{sys_id:C,consumer_account:A,context_profile:PROFILE,current_device:D,state:'open',sys_created_on:CREATED}},
  sys_cs_consumer_account:{[A]:{sys_id:A,provider_application:APP,channel_user_profile:P,consumer:U}},
  sys_cs_provider_application:{[APP]:{sys_id:APP,inbound_id:'scc-local-voice',provider:'d6eadc7a53301010ad77ddeeff7b124a'}},
  sys_cs_channel_user_profile:{[P]:{sys_id:P,active:'1',user_table:'sys_user',user_document:ID,channel_user_id:ALIAS,channel:CHANNEL}},
  sys_cs_consumer:{[U]:{sys_id:U,user_id:ID,inactive:'0'}},
  interaction:{[I]:{sys_id:I,channel_metadata_document:C,provider_application:APP,state:'new',active:'1',type:'chat',sys_created_on:CREATED}},
  sys_cs_message:{[M]:{sys_id:M,conversation:C,consumer_account:A,session:S,direction:'outbound',message_type:'action',payload:JSON.stringify({type:'CreateConversation',topicId:C,interactionId:I}),sys_created_on:CREATED}},
  sys_cs_session:{[S]:{sys_id:S,consumer_account:A,consumer:U,device_id:D,device_type:'Bot to Bot',end_time:''}}};
 for(const [table,changes]of Object.entries(options.proofChanges||{}))Object.assign(db[table][Object.keys(db[table])[0]],changes);
 const schema=Object.fromEntries(Object.entries(db).map(([table,rows])=>[table,Object.keys(Object.values(rows)[0])]));
 const calls=[],valueReads=[],queries=[],rights=[],getCounts={},counters={service:0,authorization:0,agents:0,settings:0,constructors:0};
 function Record(table,secure){
  assert.ok(db[table],'only declared normal ownership/identity tables are used');let current=null,ordinal=-1,conditions=[],rows=[],limit,recordRight=false,checked=new Set();
  const reset=row=>{current=clone(row);recordRight=false;checked=new Set();};
  return {
   isValid:()=>options.invalidTable!==table,isValidField:key=>schema[table].includes(key)&&options.invalidField!==table+':'+key,
   get(id){getCounts[table]=(getCounts[table]||0)+1;if(options.missingRecord===table||(!created&&table!=='sys_user')||!db[table][id])return false;
    if(options.proofDrift===table&&getCounts[table]===2)db[table][id][schema[table].at(-1)]='DRIFT';
    reset(db[table][id]);ordinal=0;return true;},
   canRead(){recordRight=options.deniedRecord!==table&&!current?._denied;rights.push(['record',table,ordinal,recordRight]);return recordRight;},
   getElement(key){if(options.missingElement===table+':'+key)return null;return {canRead(){checked.add(key);rights.push(['field',table,ordinal,key]);return options.deniedField!==table+':'+key&&!(current?._deniedField===key);}};},
   getValue(key){assert.equal(recordRight,true,'normal record read right before any value');assert.ok(schema[table].every(name=>checked.has(name)),'all requested field rights before any value');
    assert.notEqual(options.deniedField,table+':'+key);assert.equal(!!current?._denied,false);assert.equal(!!current?._deniedField,false);valueReads.push([table,ordinal,key]);return current[key]??null;},
   addQuery(key,value){assert.equal(secure,false,'only explicit complete ordinary uniqueness/existence queries');assert.ok(schema[table].includes(key));conditions.push([key,value]);},
   setLimit:n=>{limit=n;},
   query(){assert.ok(limit===1||limit===2);queries.push({table,conditions:clone(conditions),limit,created});
    if(table==='sys_user'){
      rows=options.matches===undefined?[user]:clone(options.matches);
    }else if(table==='sys_cs_channel_user_profile'){
      rows=created?Object.values(db[table]):options.existingAlias?[{...db[table][P],_denied:!!options.hiddenExistingAlias}]:[];
      if(created&&options.duplicateProfile)rows.push({...clone(db[table][P]),sys_id:OTHER,_denied:!!options.hiddenDuplicate});
    }else if(table==='interaction'){
      rows=Object.values(db[table]);if(options.duplicateInteraction)rows.push({...clone(db[table][I]),sys_id:OTHER,_denied:!!options.hiddenDuplicate});
    }else assert.fail('unexpected ordinary query '+table);
    rows=rows.filter(row=>conditions.every(([key,value])=>row[key]===(value===true?'1':value===false?'0':value))).slice(0,limit);ordinal=-1;
   },
   next(){const n=ordinal+1;if(n>=rows.length)return false;ordinal=n;reset(rows[n]);return true;},
   insert(){assert.fail('no manual insert');},update(){assert.fail('no manual update');},deleteRecord(){assert.fail('no deletion');},setValue(){assert.fail('no record setValue');}
  };
 }
 const response={setStatus(value){this.status=value;},setBody(value){this.body=value;}};
 function nativeResponse(nativePayload){
  const control={uiType:'ActionMsg',actionType:'CreateConversation',conversationId:C,messageId:M};
  if(!options.envelopeInteractionOnly)control.interactionId=I;
  const content={requestId:RID,clientSessionId:SID,userId:ALIAS,appInboundId:'scc-local-voice',message:clone(nativePayload.message),interactionId:I,body:[control]};
  if(options.controlInteractionOnly)delete content.interactionId;
  if(options.emptyAck)return {status:200,content:{status:'success'}};
  if(options.extraPII){content.userDetails={name:'PRIVATE_PERSON',email:'PRIVATE_EMAIL',user_id:'PRIVATE_UID'};control.userDetails=clone(content.userDetails);content.body.push({uiType:'ActionMsg',actionType:'UserDetails',value:'PRIVATE_PERSON'});content.body.push({uiType:'OutputText',value:'PRIVATE_UTTERANCE'});}
  if(options.duplicateCreate)content.body.push(clone(control));
  if(options.nativeChanges)Object.assign(content,clone(options.nativeChanges));
  if(options.controlChanges)Object.assign(control,clone(options.controlChanges));
  if(options.removeControlKey)delete control[options.removeControlKey];
  if(options.removeEnvelopeKey)delete content[options.removeEnvelopeKey];
  if(options.nowSession!==undefined)content.nowSessionId=options.nowSession;
  return {status:options.nativeStatus===undefined?200:options.nativeStatus,content};
 }
 function DateTime(){let stamp=options.now===undefined?NOW:options.now;return {setValue(value){stamp=Date.parse(value.replace(' ','T')+'Z');},getValue(){return Number.isFinite(stamp)?new Date(stamp).toISOString().slice(0,19).replace('T',' '):'INVALID';},getNumericValue(){return stamp;}};}
 const context={request:{body:{data:input},getHeader(name){if(name==='Authorization')return options.authorization===undefined?AUTH:options.authorization;if(name==='token')return options.providerToken===undefined?TOKEN:options.providerToken;assert.fail('no arbitrary header lookup');}},response,
  gs:{getUserID(){return gsDrift&&options.driftUser?OTHER:options.currentId===undefined?ID:options.currentId;},getUserName(){return gsDrift&&options.driftName?'different.fixture':options.currentName===undefined?USER.user_name:options.currentName;},hasRole(name){assert.equal(name,'admin');return !options.noAdmin&&!(gsDrift&&options.driftRole);},
   info(){assert.fail('no logs');},warn(){assert.fail('no logs');},error(){assert.fail('no logs');},setProperty(){assert.fail('no properties');}},
  VoiceRestUtils:function(){return {
   validateServiceId(req,sink){counters.service++;assert.deepEqual(clone(req.body),{data:{serviceId:SERVICE}});assert.equal(req.getHeader('Authorization'),options.authorization===undefined?AUTH:options.authorization);if(options.serviceDenied){sink.setBody({detail:'PRIVATE_NATIVE_DETAIL'});return false;}return true;},
   validateServiceAuthorization(req,sink){counters.authorization++;assert.deepEqual(clone(req.body),{data:{serviceId:SERVICE}});assert.equal(req.getHeader('Authorization'),options.authorization===undefined?AUTH:options.authorization);if(options.authorizationDenied){sink.setStatus(401);sink.setBody({detail:'PRIVATE_NATIVE_DETAIL'});return false;}return true;}};},
  VoiceAgentUtils:function(){return {getAuthorizedAgentIds(service,testMode){counters.agents++;assert.equal(service,SERVICE);assert.equal(testMode,false);return options.agents===undefined?[AGENT]:clone(options.agents);}};},
  LocalLLMVoiceAssistantSettings:function(){return {getSettings(service){counters.settings++;assert.equal(service,SERVICE);if(options.settingsThrows)throw new Error('PRIVATE_SETTINGS');return settings;}};},
  GlideRecordSecure:function(table){return Record(table,true);},GlideRecord:function(table){return Record(table,false);},GlideDateTime:DateTime,
  sn_va_as_service:{VABotToBotRestMessageHandler:function(){counters.constructors++;if(options.constructorDenied)throw new Error('PRIVATE_CROSS_SCOPE_DENIED');return {processPayload(nativePayload,headers){
   calls.push({payload:clone(nativePayload),headers:clone(headers),originalGSUser:context.gs.getUserID(),originalGSAdmin:context.gs.hasRole('admin')});created=true;
   if(options.handlerThrows)throw new Error('PRIVATE_NATIVE_EXCEPTION');if(options.settingsDrift)settings[options.settingsDrift]=OTHER;gsDrift=true;
   return nativeResponse(nativePayload);
  }};}}
 };
 vm.runInNewContext(SOURCE,context,{timeout:1000});
 return {status:response.status,body:clone(response.body),calls,counters,valueReads,queries,rights,getCounts,input:clone(input),initialInput,settings:clone(settings),initialSettings,created};
}
function denied(options,status=403){const r=run(options);assert.equal(r.status,status);assert.deepEqual(r.body,{status:'failure',detail:'Local caller create unavailable'});assert.equal(r.calls.length,0);assert.equal(JSON.stringify(r.body).includes('PRIVATE'),false);return r;}
function uncertain(options){const r=run(options);assert.equal(r.status,503);assert.deepEqual(r.body,{status:'failure',detail:'Local caller create unavailable'});assert.equal(r.calls.length,1);assert.equal(JSON.stringify(r.body).includes('PRIVATE'),false);return r;}

test('one normal public synchronous CREATE uses original GS/headers and exact fixed server payload',()=>{
 const r=run();assert.equal(r.status,200);assert.equal(r.calls.length,1);assert.equal(r.counters.constructors,1);
 assert.deepEqual(r.calls[0],{originalGSUser:ID,originalGSAdmin:true,headers:{token:TOKEN,authorization:AUTH},payload:{requestId:RID,appInboundId:'scc-local-voice',clientSessionId:SID,userId:ALIAS,emailId:USER.email,action:'CREATE_CONVERSATION',syncResponse:true,
  message:{text:'',typed:true,clientMessageId:MID},clientVariables:{voiceSessionId:SID},contextVariables:{interaction_requester_session_language:'de',interaction_user_language:'de',requester_session_language:'de',voice_assistant:SERVICE,interaction_ai_voice:'true',global_context_profile:PROFILE}}});
 assert.deepEqual(r.body,{status:'success',created:{requestId:RID,clientSessionId:SID,userId:ALIAS,body:[{uiType:'ActionMsg',actionType:'CreateConversation',conversationId:C,messageId:M,interactionId:I}]}});
 assert.deepEqual(r.input,r.initialInput);assert.deepEqual(r.settings,r.initialSettings);assert.equal(r.counters.settings,1);
 assert.equal(r.queries.find(q=>q.table==='sys_cs_channel_user_profile'&&!q.created).limit,1);
});
test('actual envelope interactionId is normalized into the single action only after ownership proof',()=>{assert.equal(run({envelopeInteractionOnly:true}).status,200);assert.equal(run({controlInteractionOnly:true}).status,200);});
test('projection strips all native names/emails/userDetails/output text and unrelated controls',()=>{
 const r=run({extraPII:true});assert.equal(r.status,200);assert.equal(r.body.created.body.length,1);assert.equal(JSON.stringify(r.body).includes('PRIVATE'),false);assert.equal(JSON.stringify(r.body).includes(USER.email),false);assert.equal(JSON.stringify(r.body).includes(ID),false);
});
for(const value of [undefined,null,[],{},'wrong'])test('exact versioned body rejects noncontract shape '+String(value),()=>{denied({input:value===undefined?{}:value},400);});
for(const key of ['version','requestId','clientSessionId','clientMessageId'])test('missing required field '+key,()=>{const p=payload();delete p[key];denied({input:p},400);});
for(const version of [0,2,'1',true,null])test('exact numeric version1 '+JSON.stringify(version),()=>{denied({input:{...payload(),version}},400);});
for(const key of ['requestId','clientSessionId','clientMessageId'])for(const value of ['not-a-guid','A'.repeat(32),null,{}])test('strict client nonce '+key+' '+JSON.stringify(value),()=>{denied({input:{...payload(),[key]:value}},400);});
for(const key of ['serviceId','userId','email','contextVariables','action','text','syncResponse','profile','model','tool'])test('client cannot add '+key,()=>{denied({input:{...payload(),[key]:'INJECTED'}},400);});
for(const changes of [{requestId:SID},{requestId:MID},{clientSessionId:MID}])test('client nonce roles cannot collapse '+JSON.stringify(changes),()=>{denied({input:{...payload(),...changes}},400);});
for(const authorization of ['',null,{},'Bearer fixture\r\nInjected','Bearer fixture ','Basic fixture'])test('original bearer syntax is mandatory '+JSON.stringify(authorization),()=>{denied({authorization});});
for(const authorization of ['bearer original_fixture','bEaReR original_fixture'])test('RFC bearer scheme is case insensitive while original bytes are preserved '+authorization,()=>{
 const r=run({authorization});assert.equal(r.status,200);assert.equal(r.calls.length,1);assert.equal(r.calls[0].headers.authorization,authorization);
});
for(const authorization of ['Bearer fixture, Bearer duplicate','Bearer fixture Bearer duplicate'])test('duplicate credential-shaped header is still refused '+authorization,()=>{denied({authorization});});
for(const providerToken of ['',null,{},'fixture token','fixture\r\nInjected'])test('existing provider token is mandatory '+JSON.stringify(providerToken),()=>{denied({providerToken});});
for(const options of [{currentName:'guest'},{currentId:''},{currentId:'bad'},{noAdmin:true},{serviceDenied:true},{authorizationDenied:true},{agents:[]},{agents:[OTHER]},{agents:['bad']},{agents:Array(257).fill(AGENT)}])test('normal original caller/service/admission gate '+JSON.stringify(options).slice(0,70),()=>{denied(options);});
for(const user of [{user_name:'other'}, {email:''},{email:'unsafe\r\n@example.invalid'},{active:'0'},{locked_out:'1'},{sys_id:OTHER}])test('active unlocked original self mapping required '+JSON.stringify(user),()=>{denied({user});});
for(const options of [{matches:[]},{matches:[{...USER,sys_id:OTHER}]},{matches:[USER,{...USER,sys_id:OTHER}]},{matches:[USER,{...USER,sys_id:OTHER,_denied:true}]}])test('complete native email match must be readable and unique '+JSON.stringify(options).slice(0,90),()=>{denied(options);});
for(const field of Object.keys(USER))test('denied own field prevents all values '+field,()=>{const r=denied({deniedField:'sys_user:'+field});assert.equal(r.valueReads.length,0);});
for(const settings of [null,{}, {version:2,service_id:SERVICE,context_profile:PROFILE,language:'de'}, {version:1,service_id:OTHER,context_profile:PROFILE,language:'de'},
 {version:1,service_id:SERVICE,context_profile:OTHER,language:'de'},{version:1,service_id:SERVICE,context_profile:PROFILE,language:'bad\r\nlang'}])test('fixed central settings contract '+JSON.stringify(settings),()=>{denied({settings},503);});
test('central language is used without hardcoding a client language',()=>{const r=run({settings:{version:1,service_id:SERVICE,context_profile:PROFILE,language:'en-GB'}});assert.equal(r.status,200);assert.equal(r.calls[0].payload.contextVariables.requester_session_language,'en-GB');});
test('settings exception is generic and performs no native call',()=>{denied({settingsThrows:true},503);});
for(const hiddenExistingAlias of [false,true])test('any existing alias prevents reuse without reading its values hidden='+hiddenExistingAlias,()=>{const r=denied({existingAlias:true,hiddenExistingAlias},409);assert.equal(r.valueReads.some(([table])=>table==='sys_cs_channel_user_profile'),false);});
test('normal public runtime access refusal stops without alternate namespace or invocation',()=>{const r=denied({constructorDenied:true},503);assert.equal(r.counters.constructors,1);});
for(const options of [{handlerThrows:true},{emptyAck:true},{nativeStatus:202},{nativeStatus:401},{nativeChanges:{status:'failure'}},{nativeChanges:{error:{message:'PRIVATE_NATIVE'}}},
 {nativeChanges:{requestId:OTHER}},{nativeChanges:{clientSessionId:OTHER}},{nativeChanges:{userId:'voice-'+OTHER}},{nativeChanges:{appInboundId:'other'}},
 {nativeChanges:{message:{clientMessageId:OTHER}}},{nativeChanges:{body:[]}},{nativeChanges:{body:Array(33).fill({})}},{duplicateCreate:true},
 {removeControlKey:'conversationId'},{removeControlKey:'messageId'},{controlChanges:{conversationId:'A'.repeat(32)}},{controlChanges:{interactionId:OTHER}},
 {nativeChanges:{interactionId:OTHER}},{controlChanges:{uiType:'OutputText'}}])test('incomplete or mismatched native result is uncertain, never retried '+JSON.stringify(options).slice(0,100),()=>{uncertain(options);});
test('empty native success ACK is never treated as created and never enters stored-ID fallback',()=>{const r=uncertain({emptyAck:true});assert.equal(r.getCounts.sys_cs_conversation,undefined);});
const proofFields={sys_cs_conversation:['sys_id','consumer_account','context_profile','current_device','state','sys_created_on'],sys_cs_consumer_account:['sys_id','provider_application','channel_user_profile','consumer'],
 sys_cs_provider_application:['sys_id','inbound_id','provider'],sys_cs_channel_user_profile:['sys_id','active','user_table','user_document','channel_user_id','channel'],sys_cs_consumer:['sys_id','user_id','inactive'],
 interaction:['sys_id','channel_metadata_document','provider_application','state','active','type','sys_created_on'],sys_cs_message:['sys_id','conversation','consumer_account','session','direction','message_type','payload','sys_created_on'],sys_cs_session:['sys_id','consumer_account','consumer','device_id','device_type','end_time']};
for(const [table,fields]of Object.entries(proofFields)){
 test('missing stored ownership row '+table,()=>{uncertain({missingRecord:table});});
 test('stored record read denied '+table,()=>{const r=uncertain({deniedRecord:table});assert.equal(r.valueReads.some(([t])=>t===table),false);});
 for(const field of fields)test('stored field read denial blocks all row values '+table+'.'+field,()=>{const r=uncertain({deniedField:table+':'+field});assert.equal(r.valueReads.some(([t])=>t===table),false);});
 test('final ownership reread detects drift '+table,()=>{uncertain({proofDrift:table});});
}
for(const [name,proofChanges]of Object.entries({wrongProfile:{sys_cs_conversation:{context_profile:OTHER}},started:{sys_cs_conversation:{state:'chatInProgress'}},blankDevice:{sys_cs_conversation:{current_device:'  '}},wrongApp:{sys_cs_consumer_account:{provider_application:OTHER}},wrongInbound:{sys_cs_provider_application:{inbound_id:'other'}},
 wrongProvider:{sys_cs_provider_application:{provider:OTHER}},inactiveProfile:{sys_cs_channel_user_profile:{active:'0'}},wrongAlias:{sys_cs_channel_user_profile:{channel_user_id:'voice-'+OTHER}},wrongOwner:{sys_cs_channel_user_profile:{user_document:OTHER}},wrongConsumer:{sys_cs_consumer:{user_id:OTHER}},
 wrongInteraction:{interaction:{channel_metadata_document:OTHER}},closedInteraction:{interaction:{state:'closed_complete'}},wrongMessage:{sys_cs_message:{conversation:OTHER}},inboundMessage:{sys_cs_message:{direction:'inbound'}},wrongSession:{sys_cs_session:{device_id:OTHER}},endedSession:{sys_cs_session:{end_time:CREATED}},
 wrongCreate:{sys_cs_message:{payload:JSON.stringify({type:'StartConversation',topicId:C,interactionId:I})}}}))test('genuine native tuple ownership mismatch '+name,()=>{uncertain({proofChanges});});
for(const options of [{duplicateInteraction:true},{duplicateInteraction:true,hiddenDuplicate:true},{duplicateProfile:true},{duplicateProfile:true,hiddenDuplicate:true}])test('complete native uniqueness proof rejects duplicates/hidden rows '+JSON.stringify(options),()=>{uncertain(options);});
test('exact server freshness limit45s is accepted',()=>{assert.equal(run({now:Date.parse('2026-11-02T12:00:45Z')}).status,200);});
for(const now of [Date.parse('2026-11-02T12:00:45.001Z'),Date.parse('2026-11-02T11:59:59Z')])test('expired/future ownership metadata is uncertain '+now,()=>{uncertain({now});});
for(const flag of ['driftUser','driftName','driftRole'])test('original GS authority must survive native public call '+flag,()=>{uncertain({[flag]:true});});
for(const field of ['language','service_id','context_profile'])test('native settings drift is refused after CREATE '+field,()=>{uncertain({settingsDrift:field});});
test('bounded genuine native continuation ID alone is optionally retained',()=>{const r=run({nowSession:'native_fixture_123'});assert.equal(r.status,200);assert.equal(r.body.created.nowSessionId,'native_fixture_123');});
for(const nowSession of [{},'bad\r\nvalue','ü',' padded','x'.repeat(256)])test('malformed optional continuation ID is uncertain '+JSON.stringify(nowSession).slice(0,70),()=>{uncertain({nowSession});});
test('the candidate contains exactly one public CREATE site, no escalation/private/runtime alternatives',()=>{
 assert.equal((SOURCE.match(/handler\.processPayload\(nativePayload,nativeHeaders\)/g)||[]).length,1);
 assert.equal((SOURCE.match(/new sn_va_as_service\.VABotToBotRestMessageHandler\(\)/g)||[]).length,1);
 assert.doesNotMatch(SOURCE,/\.elevate|VoiceConversationManager|USER_REF|actual_user|GlideImpersonate|setWorkflow|setUseEngines|queryNoDomain|sys_script_include|decrypt|setPreference|savePreference|\.insert\(|\.update\(|deleteRecord|deleteMultiple/);
 assert.equal((SOURCE.match(/action:'CREATE_CONVERSATION'/g)||[]).length,1);assert.match(SOURCE,/syncResponse:true/);
});
