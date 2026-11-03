'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const file = __dirname + '/Native-oauth-session-probe.js';
const create = fs.existsSync(file) ? require(file).createNativeOAuthSessionProbe : undefined;
const ORIGIN = 'https://soprasteriaassvsdemo14.service-now.com';
const VENDOR = 'c2f0b8f187033200246ddd4c97cb0bb9', PROFILE = 'c623e20f93374354e7f2b9fa6aba1081';
const id = n => n.toString(16).padStart(32, '0'), HASH = 'a'.repeat(64), TIME = 1793707200000;
const json = (value, status = 200) => new Response(JSON.stringify(value), {status, headers: {'Content-Type': 'application/json'}});
function fixture(changes = {}) {
  let sequence = 0, elapsed = 0, device, attempt, dto, afterSnapshot;
  const calls = [], inspections = [], controller = new AbortController();
  const old = {id: id(10), consumerId: id(1), accountId: id(2), vendorId: VENDOR, profileId: PROFILE,
    deviceId: null, state: 'completed', createdMs: TIME - 10000, updatedMs: TIME - 10000, modCount: 0};
  const conv = () => ({...old, id: id(11), deviceId: device, state: 'open', createdMs: TIME, updatedMs: TIME});
  const session = () => ({id: id(21), consumerId: id(1), accountId: id(2), vendorId: VENDOR, deviceId: device, deviceType: 'mweb', createdMs: TIME});
  const options = {origin: ORIGIN, callerHash: HASH, uuid: () => '00000000-0000-4000-8000-' + String(++sequence).padStart(12, '0'),
    now: () => TIME + elapsed, monotonic: () => elapsed, sleep: async ms => {elapsed += ms;},
    inspect: async req => {
      inspections.push(req); device = req.deviceId; attempt = req.attemptId;
      const isBefore = req.phase === 'before', terminal = req.phase === 'terminal';
      const c = conv(); if (terminal) {c.state = 'completed'; c.modCount = 1;}
      const rows = isBefore ? [structuredClone(old)] : [structuredClone(old), c];
      const sessions = isBefore ? [] : [session()];
      const value = {version: 1, ...req, ok: true, failureCode: null, principalHash: HASH,
        server: {startedMs: TIME + elapsed, finishedMs: TIME + elapsed}, contextUnchanged: true,
        counts: {activeConversations: isBefore || terminal ? 0 : 1, unknownStates: 0}, conversations: rows,
        sessions, deviceConversations: isBefore ? [] : [structuredClone(c)], deviceSessions: structuredClone(sessions),
        unownedDeviceRows: 0, activity: {available: true, messages: 0, plans: 0, genai: 0, tools: 0}, messageSessionLinks: []};
      if (changes.oracle) changes.oracle(value, req, {old, afterSnapshot, controller});
      if (!isBefore) afterSnapshot = value;
      return value;
    },
    fetchNative: async (url, init) => {
      calls.push({url, init});
      if (url.endsWith('/api/now/v2/cs/session')) {
        dto = {sessionId: id(21), consumerId: id(1), consumerAccountId: id(2), conversationId: id(11), channelId: '/cs/conversation/channel', serialNumber: -1, guestSessionIdentifier: null, conversationState: 'CONVERSATION_STARTED'};
        if (changes.dto) changes.dto(dto);
        if (changes.create) return changes.create(dto, controller);
        return json(dto);
      }
      if (url.endsWith('/api/now/cs_message')) {
        if (changes.end) return changes.end(controller);
        return json({});
      }
      const message = {queueMsgDataType: 'actionMessage', serialNumber: 1, messageId: 'msg1', conversationId: id(11), actionMessage: {type: 'TopicFinished'}};
      if (changes.message) changes.message(message);
      return json({messages: changes.messages || [message]});
    }};
  Object.assign(options, changes.options);
  return {options, calls, inspections, controller, run() {assert.equal(typeof create, 'function', 'inactive OAuth protocol factory exists'); return create(options).run({signal: controller.signal});}, get device() {return device;}, get attempt() {return attempt;}};
}
test('inactive portable factory and exact one-shot promise', async () => {
  assert.equal(typeof create, 'function', 'inactive OAuth protocol factory exists');
  const context = {};
  for (const key of ['fetch', 'process', 'crypto', 'gs']) Object.defineProperty(context, key, {get() {assert.fail('load access ' + key);}});
  vm.runInNewContext(fs.readFileSync(file, 'utf8'), context);
  assert.equal(typeof context.SccNativeOAuthSessionProbe.createNativeOAuthSessionProbe, 'function');
  const f = fixture(), probe = create(f.options), first = probe.run(); assert.equal(first, probe.run());
  const result = await first; assert.equal(result.report.status, 'passed');
});
test('exact native create End and false-init sync with public-safe separate result', async () => {
  const f = fixture(), {report, residue} = await f.run();
  assert.equal(report.status, 'passed'); assert.equal(report.failureCode, null);
  assert.deepEqual(Object.keys(report), ['version','status','failureCode','native','metadata','durations','limitations']);
  assert.deepEqual(Object.keys(residue), ['attemptId','deviceId','conversationIds','sessionIds']);
  assert.deepEqual(residue.conversationIds, [id(11)]); assert.deepEqual(residue.sessionIds, [id(21)]);
  assert.doesNotMatch(JSON.stringify(report), new RegExp(HASH + '|' + id(21) + '|' + f.device));
  assert.deepEqual(JSON.parse(f.calls[0].init.body), {requestTime: TIME, deviceId: f.device, direction: 'inbound', vendorId: VENDOR,
    consumerId: '', consumerAccountId: '', deviceType: 'mweb', contextData: {global_context_profile: PROFILE, nowassist: 'true'}});
  const end = JSON.parse(f.calls[1].init.body); assert.deepEqual(end.data.actionMessage, {topicId:id(11),systemActionName:'endChat',type:'EndChat'});
  assert.equal(end.data.sessionId,id(21)); assert.equal(f.calls[1].init.headers['amb-channel'],'/cs/messages/channel');
  const sync = new URL(f.calls[2].url); assert.equal(sync.searchParams.get('shouldInitializeConversation'),'false');
  assert.equal(sync.searchParams.get('serialNumber'),'0'); assert.equal(f.calls[2].init.headers['Session-Id'],id(21));
  assert.equal(f.calls[2].init.headers['Guest-Session-Identifier'],'null');
  assert.deepEqual(f.inspections.map(x=>x.phase),['before','after','terminal']);
  assert.equal(report.limitations.sessionRetirementProven,false);
});
for (const [name, change, code] of [
  ['envelope',d=>{d.result={};},'INVALID_RESPONSE'], ['missing guest flag',d=>{delete d.guestSessionIdentifier;},'UNAUTHENTICATED'],
  ['guest',d=>{d.guestSessionIdentifier='guest';},'UNAUTHENTICATED'], ['history empty',d=>{d.messages=[];},'EXISTING_CONVERSATION'],
  ['last message',d=>{d.lastMessage={};},'EXISTING_CONVERSATION'], ['history',d=>{d.history=[];},'EXISTING_CONVERSATION'],
  ['resume',d=>{d.resume=false;},'EXISTING_CONVERSATION'], ['nonfresh state',d=>{d.conversationState='';},'EXISTING_CONVERSATION'],
  ['partial',d=>{delete d.sessionId;},'INVALID_BINDING'], ['raw session mismatch',d=>{d.sessionId='HTTP_SESSION_PRIVATE_SENTINEL';},'BINDING_UNPROVEN'],
  ['wrong consumer',d=>{d.consumerId=id(90);},'BINDING_UNPROVEN'], ['wrong account',d=>{d.consumerAccountId=id(90);},'BINDING_UNPROVEN'],
  ['aliases conflict',d=>{d.consumerAcctId=id(90);},'INVALID_BINDING'], ['sequence',d=>{d.serialNumber=-2;},'INVALID_SEQUENCE']
]) test('refuses unsafe DTO: '+name, async()=>{
  const f=fixture({dto:change}), result=await f.run(); assert.equal(result.report.failureCode,code);
  assert.equal(result.report.status,'uncertain'); assert.equal(result.report.native.endAttempted,false);
  assert.deepEqual(f.inspections.map(x=>x.phase),['before','after','terminal']);
  assert.doesNotMatch(JSON.stringify(result),/HTTP_SESSION_PRIVATE_SENTINEL/);
});
test('absent fresh state accepted only with independent complete equality',async()=>{const f=fixture({dto:d=>delete d.conversationState});assert.equal((await f.run()).report.status,'passed');});
test('null optional message-session link supplies no contradiction to mandatory DTO equality',async()=>{
  const f=fixture({oracle:(v,r)=>{if(r.phase!=='before'){v.activity.messages=1;v.messageSessionLinks=[{conversationId:id(11),sessionId:null}];}}});
  assert.equal((await f.run()).report.status,'passed');
});
test('principalMatches is false after observed caller hash drift',async()=>{
  const f=fixture({oracle:(v,r)=>{if(r.phase==='after')v.principalHash='b'.repeat(64);}});
  const r=(await f.run()).report;assert.equal(r.metadata.principalMatches,false);assert.equal(r.native.endAttempted,false);
});
test('terminal metadata cannot hide a competing device row or deleted proven session',async()=>{
  for(const kind of ['competing','deleted session']){const f=fixture({oracle:(v,r)=>{if(r.phase==='terminal'){
    if(kind==='competing'){const c={...v.deviceConversations[0],id:id(90)};v.deviceConversations.push(c);v.conversations.push(c);}
    else{v.sessions=[];v.deviceSessions=[];}
  }}});const r=(await f.run()).report;assert.equal(r.status,'uncertain');assert.equal(r.failureCode,'TERMINAL_UNCONFIRMED');}
});
test('later mutation of returned before snapshot cannot change retained freshness baseline',async()=>{
  let baseline;const f=fixture({oracle:(v,r)=>{if(r.phase==='before')baseline=v;if(r.phase==='after')baseline.conversations.length=0;}});
  assert.equal((await f.run()).report.status,'passed');
});
for(const kind of ['bytes','redirect','too many messages'])test('native limit '+kind+' is bounded and public safe',async()=>{
  const f=fixture(kind==='bytes'?{create:()=>json({private:'x'.repeat(65536)})}:kind==='redirect'?{create:()=>({ok:true,status:200,redirected:true,body:{cancel:async()=>{}}})}:{messages:Array.from({length:129},()=>({}))});
  const r=(await f.run()).report;assert.equal(r.failureCode,kind==='redirect'?'REDIRECT':'RESPONSE_LIMIT');assert.equal(r.status,'uncertain');
  assert.equal(f.inspections.at(-1).phase,'terminal');assert.equal(r.native.endAttempted,kind==='too many messages');
});
test('whole-second creation floor allows exactly 999ms and avoids host-server absolute equality',async()=>{
  const f=fixture({oracle:(v,r)=>{v.server.startedMs+=999;v.server.finishedMs+=999;}});
  assert.equal((await f.run()).report.status,'passed');
});
for(const name of ['hash','active','unknown','incomplete','duplicate','clock','device','unowned']) test('before refuses '+name,async()=>{
  const f=fixture({oracle:(v,r)=>{if(r.phase!=='before')return;
    if(name==='hash')v.principalHash='b'.repeat(64); if(name==='active'){v.conversations[0].state='open';v.counts.activeConversations=1;}
    if(name==='unknown'){v.conversations[0].state='x';v.counts.unknownStates=1;} if(name==='incomplete')delete v.activity;
    if(name==='duplicate')v.conversations.push({...v.conversations[0]}); if(name==='clock')v.server.startedMs++;
    if(name==='device'){v.conversations[0].deviceId=r.deviceId;v.deviceConversations=[{...v.conversations[0]}];}
    if(name==='unowned')v.unownedDeviceRows=1;
  }});const result=await f.run();assert.equal(result.report.status,'refused');assert.equal(f.calls.length,0);
});
for(const name of ['hash','old changed','deleted old','competing','wrong profile','wrong vendor','wrong device type','wrong binding','stale','links']) test('after refuses '+name,async()=>{
  const f=fixture({oracle:(v,r)=>{if(r.phase!=='after')return;
    if(name==='hash')v.principalHash='b'.repeat(64); if(name==='old changed')v.conversations[0].modCount++;
    if(name==='deleted old')v.conversations.shift(); if(name==='competing')v.sessions.push({...v.sessions[0],id:id(90)});
    const c=v.conversations.find(x=>x.id===id(11));
    if(name==='wrong profile')c.profileId=id(99); if(name==='wrong vendor')c.vendorId=id(99);
    if(name==='wrong device type')v.sessions[0].deviceType='ios'; if(name==='wrong binding')v.sessions[0].consumerId=id(99);
    if(name==='stale')c.createdMs=TIME-1000;
    if(name==='links')v.messageSessionLinks=[{conversationId:id(11),sessionId:id(99)}];
    if(c)v.deviceConversations=[{...c}];v.deviceSessions=structuredClone(v.sessions.filter(x=>x.deviceId===r.deviceId));
  }});const result=await f.run();assert.equal(result.report.native.endAttempted,false);assert.equal(result.report.status,'uncertain');
});
for(const [name,createResponse] of [['http',()=>json({},403)],['throw',()=>{throw Error('PRIVATE_ERROR');}],['cancel',(d,c)=>{c.abort();return json(d);}]]) test('attempted '+name+' always after-correlates, no unsafe End',async()=>{
  const f=fixture({create:createResponse});const result=await f.run();assert.equal(result.report.native.createAttempted,true);
  assert.equal(result.report.native.endAttempted,false);assert.deepEqual(f.inspections.map(x=>x.phase),['before','after','terminal']);
  assert.deepEqual(result.residue.sessionIds,[id(21)]);assert.doesNotMatch(JSON.stringify(result),/PRIVATE_ERROR/);
});
test('cancellation after proof does not cancel legitimate End or terminal',async()=>{
  const f=fixture({oracle:(v,r,{controller})=>{if(r.phase==='after')controller.abort();}}),result=await f.run();
  assert.equal(result.report.native.endAttempted,true);assert.equal(result.report.native.endAcknowledged,true);assert.equal(result.report.status,'failed');
  assert.equal(result.report.failureCode,'CANCELLED');
});
for(const activity of ['unknown','plans','genai','tools']) test('activity '+activity+' prevents pass but retains legitimate cleanup',async()=>{
  const f=fixture({oracle:(v,r)=>{if(r.phase==='before')return;if(activity==='unknown')v.activity={available:false,messages:null,plans:null,genai:null,tools:null};else v.activity[activity]=1;}});
  const r=(await f.run()).report;assert.equal(r.status,'failed');assert.equal(r.native.endAttempted,true);assert.equal(r.metadata.unexpectedInitialization,activity==='unknown'?null:true);
});
for(const name of ['gap','duplicate','conversation','session','channel','topic']) test('invalid sync '+name+' cannot witness TopicFinished',async()=>{
  const f=fixture({message:m=>{if(name==='gap')m.serialNumber=2;if(name==='conversation')m.conversationId=id(99);
    if(name==='session')m.sessionId='private';if(name==='channel')m.channelId='/other';if(name==='topic')m.actionMessage.topicId=id(99);},
    ...(name==='duplicate'?{messages:[{queueMsgDataType:'actionMessage',serialNumber:1,messageId:'x',conversationId:id(11),actionMessage:{type:'other'}},{queueMsgDataType:'actionMessage',serialNumber:2,messageId:'x',conversationId:id(11),actionMessage:{type:'TopicFinished'}}]}:{})});
  const r=(await f.run()).report;assert.equal(r.native.topicFinished,false);assert.equal(r.status,'uncertain');assert.equal(r.failureCode,'INVALID_SEQUENCE');
});
test('terminal failure independent of End ACK and TopicFinished',async()=>{
  const f=fixture({oracle:(v,r)=>{if(r.phase==='terminal')delete v.counts;}}),r=(await f.run()).report;
  assert.equal(r.native.endAcknowledged,true);assert.equal(r.native.topicFinished,true);assert.equal(r.status,'uncertain');assert.equal(r.metadata.terminalComplete,false);
});
test('operation budgets protect final fifteen seconds of forty-five-second cleanup',async t=>{
  t.mock.timers.enable({apis:['setTimeout','Date'],now:TIME});let terminalStart=null;
  const wait=ms=>new Promise(resolve=>setTimeout(resolve,ms));
  const f=fixture(),baseInspect=f.options.inspect,baseFetch=f.options.fetchNative;
  f.options.monotonic=()=>Date.now()-TIME;f.options.now=()=>Date.now();
  f.options.inspect=async req=>{if(req.phase==='after')await wait(14900);if(req.phase==='terminal'){terminalStart=Date.now()-TIME;await wait(14000);}
    const v=await baseInspect(req);v.server={startedMs:Date.now(),finishedMs:Date.now()};return v;};
  f.options.fetchNative=async(url,init)=>{if(url.endsWith('/cs_message'))await wait(9900);if(url.includes('/sync?')){await wait(2900);return json({messages:[]});}return baseFetch(url,init);};
  f.options.sleep=wait;const promise=f.run();let done=false;promise.then(()=>{done=true;});
  for(let i=0;i<50&&!done;i++){await new Promise(r=>setImmediate(r));t.mock.timers.tick(1000);}
  const r=(await promise).report;assert.ok(terminalStart<=30000,'nonterminal operations cannot consume terminal reserve');
  assert.equal(r.metadata.terminalComplete,true);assert.ok(r.durations.totalMs<=45000);assert.equal(r.status,'uncertain');
});
// Fake timers advance only operation deadlines; transport remains injected and offline.
for(const hanging of ['oracle','reader','fetch','sleeper','end']) test('uncooperative '+hanging+' stays bounded and preserves terminal reserve',async t=>{
  t.mock.timers.enable({apis:['setTimeout']});
  const never=()=>new Promise(()=>{}); let nativeCalls=0;
  const f=fixture({...(hanging==='fetch'?{create:never}:{}),...(hanging==='reader'?{create:()=>({ok:true,status:200,headers:new Headers(),body:{getReader:()=>({read:never,cancel:never})}})}:{}),
    ...(hanging==='end'?{end:never}:{}),...(hanging==='sleeper'?{messages:[],options:{sleep:never}}:{}),
    ...(hanging==='oracle'?{options:{inspect:never}}:{})});
  const promise=f.run();let done=false;promise.then(()=>{done=true;});
  for(let i=0;i<20&&!done;i++){await new Promise(resolve=>setImmediate(resolve));t.mock.timers.tick(15001);}
  assert.equal(done,true,'wallclock timeout bounds uncooperative dependencies'); const r=await promise;
  assert.ok(['refused','uncertain'].includes(r.report.status));
  if(hanging!=='oracle')assert.ok(f.inspections.some(x=>x.phase==='terminal'));
  if(hanging==='end')assert.equal(f.calls.filter(x=>x.url.endsWith('/cs_message')).length,1);
});
