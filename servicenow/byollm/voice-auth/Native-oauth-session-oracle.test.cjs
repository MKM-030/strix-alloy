'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const crypto = require('node:crypto');
const file = path.join(__dirname, 'Native-oauth-session-oracle.js');
const create = fs.existsSync(file) ? require(file).createNativeOAuthOracle : undefined;
const id = n => n.toString(16).padStart(32, '0');
const UID = id(9000), OTHER = id(9001), VENDOR = 'c2f0b8f187033200246ddd4c97cb0bb9';
const PROFILE = 'c623e20f93374354e7f2b9fa6aba1081';
const DEVICE = '00000000-0000-4000-8000-000000000001';
const ATTEMPT = '00000000-0000-4000-8000-000000000002';
const OLD_DEVICE = '00000000-0000-4000-8000-000000000003';
const STAMP = '2026-11-03 12:00:00', NOW = 1793707200000;
const request = changes => ({version: 1, phase: 'before', attemptId: ATTEMPT, deviceId: DEVICE, ...changes});
const conversation = (n, changes = {}) => ({sys_id: id(n), consumer: id(1), consumer_account: id(3),
  vendor: VENDOR, context_profile: PROFILE, current_device: OLD_DEVICE, state: 'completed',
  sys_created_on: STAMP, sys_updated_on: STAMP, sys_mod_count: '0', ...changes});
const session = (n, changes = {}) => ({sys_id: id(n), consumer: id(1), consumer_account: id(3),
  vendor: VENDOR, device_id: OLD_DEVICE, device_type: 'mweb', sys_created_on: STAMP, end_time: '', ...changes});
const schemas = {
  sys_cs_consumer: ['sys_id', 'user_id'],
  sys_cs_channel_user_profile: ['sys_id', 'user_table', 'user_document'],
  sys_cs_consumer_account: ['sys_id', 'consumer', 'channel_user_profile', 'vendor'],
  sys_cs_conversation: Object.keys(conversation(1)),
  sys_cs_session: Object.keys(session(1)).filter(f => f !== 'end_time'),
  sys_cs_message: ['sys_id', 'conversation', 'session'],
  sn_aia_execution_plan: ['sys_id', 'conversation'],
  sys_generative_ai_log: ['sys_id', 'conversation'],
  sn_aia_tools_execution: ['sys_id', 'execution_plan_id']
};
function fixture(options = {}) {
  const db = {
    sys_cs_consumer: [{sys_id: id(1), user_id: UID}, {sys_id: id(99), user_id: OTHER}],
    sys_cs_channel_user_profile: [{sys_id: id(2), user_table: 'sys_user', user_document: UID}],
    sys_cs_consumer_account: [{sys_id: id(3), consumer: id(1), channel_user_profile: '', vendor: VENDOR},
      {sys_id: id(4), consumer: id(99), channel_user_profile: id(2), vendor: VENDOR}],
    sys_cs_conversation: [conversation(10), conversation(11, {consumer: id(99), consumer_account: id(4), context_profile: id(77)})],
    sys_cs_session: [session(20), session(21, {consumer: id(99), consumer_account: id(4)})],
    sys_cs_message: [], sn_aia_execution_plan: [], sys_generative_ai_log: [], sn_aia_tools_execution: [],
    ...options.db
  };
  const context = {uid: UID, name: 'PRIVATE_NAME_SENTINEL', admin: true, impersonating: false,
    scope: 'rhino.global', application: id(80), userSet: id(81), systemSet: id(82), ...options.context};
  const queries = [], hashes = [];
  function Record(table) {
    let current, rows, position = 0, limit, tableRight = false, rowRight = false, checked = new Set();
    const conditions = [];
    const validField = field => (schemas[table] || []).includes(field) && options.missingField !== table + '.' + field;
    const record = {
      isValid: () => options.missingTable !== table && Object.hasOwn(schemas, table),
      isValidField: validField,
      canRead() {
        if (!current) {tableRight = options.deniedTable !== table; return tableRight;}
        rowRight = !current._denied && options.deniedRows !== table; return rowRight;
      },
      getElement(field) {
        assert.ok(validField(field), 'no unknown fields');
        if (options.missingElement === table + '.' + field) return null;
        return {canRead() {checked.add(field); return current?._deniedField !== field && options.deniedField !== table + '.' + field;}};
      },
      getValue(field) {
        assert.ok(tableRight && rowRight && checked.has(field), 'table, row and field read right required first');
        assert.ok(validField(field), 'no payload, text, worker context or end_time read');
        if (current._deniedField) assert.ok(checked.has(current._deniedField), 'check all fields before values');
        return current[field] ?? '';
      },
      addQuery(field, operator, value) {
        assert.ok(validField(field), 'known condition');
        if (value === undefined) {value = operator; operator = '=';}
        assert.ok(['=', 'IN'].includes(operator)); conditions.push([field, operator, String(value)]);
      },
      orderBy(field) {assert.equal(field, 'sys_id');},
      setLimit(value) {assert.ok(Number.isInteger(value) && value >= 1 && value <= 513); limit = value;},
      query() {
        assert.ok(tableRight, 'explicit table read check before querying');
        assert.ok(limit, 'every query bounded');
        queries.push({table, conditions, limit});
        if (options.throwQuery === table) throw Error('PRIVATE_ERROR_TOKEN_SENTINEL ' + UID);
        rows = (db[table] || []).filter(row => conditions.every(([f, op, v]) => op === '=' ? row[f] === v : v.split(',').includes(row[f]))).slice(0, limit);
        if (options.onQuery) options.onQuery({table, db, context, queries});
      },
      next() {current = rows[position++]; rowRight = false; checked = new Set(); return !!current;}
    };
    for (const method of ['initialize', 'newRecord', 'insert', 'update', 'updateMultiple', 'deleteRecord', 'deleteMultiple', 'setValue', 'setWorkflow', 'setUseEngines', 'queryNoDomain']) {
      record[method] = () => assert.fail('persisted mutation or privilege bypass attempted: ' + method);
    }
    return record;
  }
  function DateTime() {
    let stamp = NOW;
    return {setValue(value) {stamp = Date.parse(value.replace(' ', 'T') + 'Z');},
      getValue() {return Number.isFinite(stamp) ? new Date(stamp).toISOString().slice(0, 19).replace('T', ' ') : 'INVALID';},
      getNumericValue() {return options.invalidClock ? NaN : stamp;}};
  }
  const deps = {gs: {getUserID: () => context.uid, getUserName: () => context.name,
    hasRole: role => role === 'admin' && context.admin, getProperty: () => 'test_instance',
    getCurrentScopeName: () => context.scope, getCurrentApplicationId: () => context.application,
    getUser: () => ({getPreference: () => context.userSet}), getPreference: () => context.systemSet},
  GlideRecord: Record, GlideDateTime: DateTime,
  GlideDigest: function () {this.getSHA256Hex = value => {hashes.push(value); return crypto.createHash('sha256').update(value).digest('hex');};},
  GlideImpersonate: function () {this.isImpersonating = () => context.impersonating;}};
  function inspect(args = request(), override) {
    assert.equal(typeof create, 'function', 'portable metadata oracle factory exists');
    return create(override || deps).inspect(args);
  }
  return {db, deps, context, queries, hashes, inspect};
}
function refused(result, code) {
  assert.equal(result.ok, false); assert.equal(result.failureCode, code);
  assert.equal(result.principalHash, null); assert.deepEqual(result.server, {startedMs: null, finishedMs: null});
  assert.equal(result.contextUnchanged, false); assert.deepEqual(result.counts, {activeConversations: null, unknownStates: null});
  for (const field of ['conversations', 'sessions', 'deviceConversations', 'deviceSessions', 'messageSessionLinks']) assert.deepEqual(result[field], []);
  assert.equal(result.unownedDeviceRows, null);
  assert.deepEqual(result.activity, {available: false, messages: null, plans: null, genai: null, tools: null});
  assert.doesNotMatch(JSON.stringify(result), /PRIVATE_|00000000000000000000000000002328/);
}

test('complete metadata includes direct and profile account ownership across every profile', () => {
  const f = fixture(), result = f.inspect();
  assert.equal(result.ok, true); assert.equal(result.failureCode, null);
  assert.deepEqual(result.conversations.map(r => r.id), [id(10), id(11)]);
  assert.deepEqual(result.sessions.map(r => r.id), [id(20), id(21)]);
  assert.deepEqual(result.conversations[0], {id: id(10), consumerId: id(1), accountId: id(3), vendorId: VENDOR,
    profileId: PROFILE, deviceId: null, state: 'completed', createdMs: NOW, updatedMs: NOW, modCount: 0});
  assert.deepEqual(result.sessions[1], {id: id(21), consumerId: id(99), accountId: id(4), vendorId: VENDOR,
    deviceId: null, deviceType: 'mweb', createdMs: NOW});
  assert.deepEqual(result.counts, {activeConversations: 0, unknownStates: 0});
  assert.deepEqual(result.activity, {available: true, messages: 0, plans: 0, genai: 0, tools: 0});
  assert.deepEqual(result.server, {startedMs: NOW, finishedMs: NOW});
  assert.equal(result.principalHash, crypto.createHash('sha256').update(UID).digest('hex'));
  assert.deepEqual(f.hashes, [UID]); assert.equal(result.contextUnchanged, true);
  assert.deepEqual(Object.keys(result).sort(), ['version','phase','attemptId','deviceId','ok','failureCode','principalHash','server','contextUnchanged','counts','conversations','sessions','deviceConversations','deviceSessions','unownedDeviceRows','activity','messageSessionLinks'].sort());
  assert.doesNotMatch(JSON.stringify(result), /PRIVATE_|test_instance|rhino\.global/);
  assert.equal(f.queries.some(q => q.table === 'sys_cs_message'), false, 'no activity queries without owned device conversations');
});

test('no load-time global or dependency access; inline global and CommonJS expose the same factory contract', () => {
  assert.ok(fs.existsSync(file), 'portable source exists');
  const sandbox = {};
  for (const key of ['gs','GlideRecord','GlideDateTime','GlideDigest','GlideImpersonate','fetch','process']) Object.defineProperty(sandbox, key, {get() {assert.fail('load-time access: ' + key);}});
  vm.runInNewContext(fs.readFileSync(file, 'utf8'), sandbox);
  assert.equal(typeof sandbox.SccNativeOAuthOracle.createNativeOAuthOracle, 'function');
  const f = fixture();
  const result = sandbox.SccNativeOAuthOracle.createNativeOAuthOracle(f.deps).inspect(request());
  assert.equal(result.ok, true);
});

for (const [name, changes] of [['guest', {name: 'guest'}], ['non-admin', {admin: false}], ['impersonation', {impersonating: true}], ['empty principal', {uid: ''}]]) {
  test('refuses ' + name + ' before database reads', () => {const f = fixture({context: changes}); refused(f.inspect(), 'PRINCIPAL_REFUSED'); assert.equal(f.queries.length, 0);});
}
for (const field of ['uid','name','admin','impersonating','scope','application','userSet','systemSet']) {
  test('detects changed effective context: ' + field, () => {
    const f = fixture({onQuery({context}) {context[field] = typeof context[field] === 'boolean' ? !context[field] : 'CHANGED_PRIVATE_VALUE';}});
    refused(f.inspect(), 'CONTEXT_DRIFT');
  });
}
for (const [kind, opts, code] of [
  ['table denial', {deniedTable: 'sys_cs_consumer'}, 'READ_DENIED'],
  ['row denial', {deniedRows: 'sys_cs_conversation'}, 'READ_DENIED'],
  ['field denial', {deniedField: 'sys_cs_conversation.current_device'}, 'READ_DENIED'],
  ['condition denial', {deniedField: 'sys_cs_consumer.user_id'}, 'READ_DENIED'],
  ['missing table', {missingTable: 'sys_cs_session'}, 'SCHEMA_UNAVAILABLE'],
  ['missing field', {missingField: 'sys_cs_conversation.sys_mod_count'}, 'SCHEMA_UNAVAILABLE'],
  ['missing element', {missingElement: 'sys_cs_session.vendor'}, 'READ_DENIED'],
  ['query exception', {throwQuery: 'sys_cs_session'}, 'READ_FAILED']
]) test('fails closed without partial data on ' + kind, () => refused(fixture(opts).inspect(), code));

test('a denied duplicate cannot disappear behind a readable row', () => {
  const f = fixture(); f.db.sys_cs_conversation.push(conversation(10, {_denied: true}));
  refused(f.inspect(), 'READ_DENIED');
});
test('a later row field denial is checked before any value is read from that row',()=>{
  const f=fixture(); f.db.sys_cs_conversation[1]._deniedField='sys_mod_count';
  refused(f.inspect(),'READ_DENIED');
});
test('identical union duplicates collapse; conflicting duplicates fail', () => {
  const f = fixture(); f.db.sys_cs_conversation.push(conversation(10));
  assert.equal(f.inspect().conversations.length, 2);
  f.db.sys_cs_conversation.push(conversation(10, {state: 'open'})); refused(f.inspect(), 'INVALID_DATA');
});
for (const [table, cap, make] of [
  ['sys_cs_consumer',16,n => ({sys_id:id(n+100),user_id:UID})],
  ['sys_cs_channel_user_profile',512,n => ({sys_id:id(n+100),user_table:'sys_user',user_document:UID})],
  ['sys_cs_consumer_account',512,n => ({sys_id:id(n+100),consumer:id(1),channel_user_profile:'',vendor:VENDOR})],
  ['sys_cs_conversation',512,n => conversation(n+100)],
  ['sys_cs_session',512,n => session(n+100)]
]) test(table + ' allows the bound and refuses one more row with a cap+1 query', () => {
  const f = fixture(); f.db[table] = Array.from({length:cap}, (_,n) => make(n));
  assert.equal(f.inspect().ok, true);
  assert.ok(f.queries.some(q => q.table === table && q.limit === cap+1));
  f.db[table].push(make(cap)); refused(f.inspect(), 'READ_LIMIT');
});
test('deduplicated union limit applies across separately bounded ownership paths', () => {
  const f = fixture();
  f.db.sys_cs_conversation = Array.from({length:300}, (_,n) => conversation(n+100));
  f.db.sys_cs_conversation.push(...Array.from({length:213}, (_,n) => conversation(n+1000, {consumer:id(99), consumer_account:id(4)})));
  refused(f.inspect(), 'READ_LIMIT');
});
test('account union refuses a total above 512 even when both source queries fit',()=>{
  const f=fixture(); f.db.sys_cs_consumer_account=Array.from({length:300},(_,n)=>({sys_id:id(n+100),consumer:id(1),channel_user_profile:'',vendor:VENDOR}));
  f.db.sys_cs_consumer_account.push(...Array.from({length:213},(_,n)=>({sys_id:id(n+1000),consumer:id(99),channel_user_profile:id(2),vendor:VENDOR})));
  refused(f.inspect(),'READ_LIMIT');
});
test('all exact active states count; missing or unexpected states count as unknown', () => {
  const states = ['open','chatInProgress','autoPilotInProgress','completed','faulted','canceled','chatEnded','deleted','','OPEN'];
  const f = fixture({db:{sys_cs_conversation:states.map((state,n) => conversation(n+100,{state}))}});
  const r = f.inspect(); assert.equal(r.ok,true); assert.deepEqual(r.counts,{activeConversations:3,unknownStates:2});
});
test('empty historical session end_time never marks a conversation active or gets read', () => {
  const r = fixture().inspect(); assert.equal(r.ok,true); assert.equal(r.sessions.length,2); assert.equal(r.counts.activeConversations,0);
});
test('historical opaque device data and unknown device types stay private; empty references become null',()=>{
  const f=fixture(); Object.assign(f.db.sys_cs_conversation[0],{current_device:'PRIVATE_OPAQUE_SESSION',consumer:'',vendor:'',context_profile:''});
  Object.assign(f.db.sys_cs_session[0],{device_id:'PRIVATE_DEVICE',device_type:'PRIVATE_TYPE',consumer_account:''});
  const r=f.inspect(); assert.equal(r.ok,true); assert.equal(r.conversations[0].deviceId,null);
  assert.equal(r.conversations[0].consumerId,null); assert.equal(r.conversations[0].vendorId,null); assert.equal(r.conversations[0].profileId,null);
  assert.equal(r.sessions[0].deviceId,null); assert.equal(r.sessions[0].deviceType,null); assert.equal(r.sessions[0].accountId,null);
  assert.doesNotMatch(JSON.stringify(r),/PRIVATE_/);
});
test('device-only queries inspect owned and foreign matches while exporting only foreign count', () => {
  const f = fixture();
  f.db.sys_cs_conversation[0].current_device=DEVICE;
  f.db.sys_cs_session[0].device_id=DEVICE;
  f.db.sys_cs_conversation.push(conversation(700,{consumer:id(99),consumer_account:id(701),current_device:DEVICE}));
  f.db.sys_cs_session.push(session(702,{consumer:id(99),consumer_account:id(701),device_id:DEVICE}));
  const r=f.inspect(); assert.equal(r.ok,true); assert.equal(r.unownedDeviceRows,2);
  assert.deepEqual(r.deviceConversations.map(c=>c.id),[id(10)]); assert.deepEqual(r.deviceSessions.map(s=>s.id),[id(20)]);
  assert.equal(JSON.stringify(r).includes(id(700)),false); assert.equal(JSON.stringify(r).includes(id(702)),false);
});
test('denied foreign device rows refuse snapshot instead of hiding a collision', () => {
  const f=fixture(); f.db.sys_cs_session.push(session(700,{consumer:id(99),consumer_account:id(701),device_id:DEVICE,_denied:true}));
  refused(f.inspect(),'READ_DENIED');
});
test('device query itself refuses overflow', () => {
  const f=fixture(); f.db.sys_cs_conversation.push(...Array.from({length:513},(_,n)=>conversation(n+100,{consumer:id(99),consumer_account:id(701),current_device:DEVICE})));
  refused(f.inspect(),'READ_LIMIT');
});
for (const [name, change] of [
  ['ID',{sys_id:'PRIVATE_SESSION_STRING'}], ['consumer',{consumer:'bad'}], ['vendor',{vendor:'bad'}],
  ['created timestamp',{sys_created_on:'2026-02-30 12:00:00'}], ['updated timestamp',{sys_updated_on:''}],
  ['mod count',{sys_mod_count:'1.1'}], ['negative mod count',{sys_mod_count:'-1'}]
]) test('rejects malformed required '+name,()=>{const f=fixture(); Object.assign(f.db.sys_cs_conversation[0],change); refused(f.inspect(),'INVALID_DATA');});

function withActivity(options={}) {
  const f=fixture(options); f.db.sys_cs_conversation[0].current_device=DEVICE;
  f.db.sys_cs_message=[{sys_id:id(30),conversation:id(10),session:id(20)},{sys_id:id(31),conversation:id(10),session:id(20)},
    {sys_id:id(32),conversation:id(10),session:''},{sys_id:id(33),conversation:id(11),session:id(21)}];
  f.db.sn_aia_execution_plan=[{sys_id:id(40),conversation:id(10)},{sys_id:id(41),conversation:id(11)}];
  f.db.sys_generative_ai_log=[{sys_id:id(50),conversation:id(10)}];
  f.db.sn_aia_tools_execution=[{sys_id:id(60),execution_plan_id:id(40)},{sys_id:id(61),execution_plan_id:id(41)}];
  return f;
}
test('activity uses exact generated-device conversation paths and actual deduplicated session refs',()=>{
  const r=withActivity().inspect(); assert.equal(r.ok,true);
  assert.deepEqual(r.activity,{available:true,messages:3,plans:1,genai:1,tools:1});
  assert.deepEqual(r.messageSessionLinks,[{conversationId:id(10),sessionId:id(20)},{conversationId:id(10),sessionId:null}]);
});
for(const [name,options] of [
  ['missing message table',{missingTable:'sys_cs_message'}],['denied plan table',{deniedTable:'sn_aia_execution_plan'}],
  ['message ref denied',{deniedField:'sys_cs_message.session'}],['tool row denied',{deniedRows:'sn_aia_tools_execution'}],
  ['query error',{throwQuery:'sys_generative_ai_log'}]
]) test('activity unavailable on '+name+' resets all counts and links but preserves snapshot',()=>{
  const r=withActivity(options).inspect(); assert.equal(r.ok,true); assert.equal(r.conversations.length,2);
  assert.deepEqual(r.activity,{available:false,messages:null,plans:null,genai:null,tools:null}); assert.deepEqual(r.messageSessionLinks,[]);
});
test('activity overflow is unknown rather than zero or truncated success',()=>{
  const f=withActivity(); f.db.sys_cs_message=Array.from({length:513},(_,n)=>({sys_id:id(n+100),conversation:id(10),session:''}));
  const r=f.inspect(); assert.equal(r.ok,true); assert.equal(r.activity.available,false); assert.equal(r.activity.messages,null); assert.deepEqual(r.messageSessionLinks,[]);
});
for(const [table,row] of [
  ['sn_aia_execution_plan',{conversation:id(10)}], ['sys_generative_ai_log',{conversation:id(10)}],
  ['sn_aia_tools_execution',{execution_plan_id:id(40)}]
]) test(table+' activity limit is independent and never yields partial evidence',()=>{
  const f=withActivity(); f.db[table]=Array.from({length:513},(_,n)=>({sys_id:id(n+100),...row}));
  const r=f.inspect(); assert.equal(r.ok,true); assert.deepEqual(r.activity,{available:false,messages:null,plans:null,genai:null,tools:null}); assert.deepEqual(r.messageSessionLinks,[]);
});
test('activity context drift is a mandatory failure rather than optional unavailable evidence',()=>{
  const f=withActivity({onQuery({table,context}){if(table==='sys_cs_message')context.scope='PRIVATE_DRIFT';}});
  refused(f.inspect(),'CONTEXT_DRIFT');
});
test('an ownership-only snapshot with no own rows is complete and reports foreign device count only',()=>{
  const f=fixture({db:{sys_cs_consumer:[],sys_cs_channel_user_profile:[]}});
  f.db.sys_cs_session[0].device_id=DEVICE;
  const r=f.inspect(); assert.equal(r.ok,true); assert.deepEqual(r.conversations,[]); assert.deepEqual(r.sessions,[]); assert.equal(r.unownedDeviceRows,1);
});
test('invalid message session reference cannot leak opaque native strings',()=>{
  const f=withActivity(); f.db.sys_cs_message[0].session='PRIVATE_OPAQUE_SESSION'; const r=f.inspect();
  assert.equal(r.ok,true); assert.equal(r.activity.available,false); assert.deepEqual(r.messageSessionLinks,[]); assert.doesNotMatch(JSON.stringify(r),/PRIVATE_/);
});
test('invalid request is scrubbed and causes no query or hash',()=>{
  const f=fixture(); const r=f.inspect(request({phase:'PRIVATE_PHASE',deviceId:'PRIVATE_DEVICE',userId:UID}));
  refused(r,'INVALID_REQUEST'); assert.equal(r.phase,null); assert.equal(r.deviceId,null); assert.equal(r.attemptId,ATTEMPT);
  assert.equal(f.queries.length,0); assert.equal(f.hashes.length,0);
});
test('missing dependencies and malformed clock fail with fixed metadata only',()=>{
  const f=fixture(); refused(f.inspect(request(),{}),'INVALID_DEPENDENCIES'); refused(fixture({invalidClock:true}).inspect(),'INVALID_DATA');
});
