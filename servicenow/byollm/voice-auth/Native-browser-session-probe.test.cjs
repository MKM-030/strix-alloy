'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const util = require('node:util');
const sourcePath = path.join(__dirname, 'Native-browser-session-probe.js');
// A missing module is represented as a missing capability so RED is an assertion failure.
const createNativeSessionProbe = fs.existsSync(sourcePath)
  ? require(sourcePath).createNativeSessionProbe : undefined;
const ORIGIN = 'https://soprasteriaassvsdemo14.service-now.com';
const CSRF = 'CSRF_PRIVATE_SENTINEL_73';
const SID = '11111111111111111111111111111111';
const ACCOUNT = '22222222222222222222222222222222';
const CONVERSATION = '33333333333333333333333333333333';
const CHANNEL = '44444444444444444444444444444444';
const OTHER = '55555555555555555555555555555555';
const UUIDS = [1, 2, 3, 4, 5, 6, 7, 8].map(n => '00000000-0000-4000-8000-' + String(n).padStart(12, '0'));
const session = changes => ({sessionId: SID, consumerAccountId: ACCOUNT,
  conversationId: CONVERSATION, channelId: '/cs/messages/' + CHANNEL,
  guestSessionIdentifier: null, serialNumber: 10, ...changes});
const finished = changes => ({queueMsgDataType: 'actionMessage', messageId: OTHER,
  serialNumber: 11, sessionId: SID, conversationId: CONVERSATION,
  actionMessage: {type: 'TopicFinished', topicId: CONVERSATION}, ...changes});
// Observed Ft -> Pe -> Fm -> vv -> SESSION_FETCH_SUCCEEDED preserves direct JSON DTOs.
const wire = value => value;
const reply = (value, status = 200) => new Response(JSON.stringify(wire(value)), {
  status, headers: {'Content-Type': 'application/json'}
});
function setup({created = session(), syncs = [{messages: [finished()], lastReadMessageSerialNum: 11}],
  endStatus = 200, onFetch, config = {}} = {}) {
  assert.equal(typeof createNativeSessionProbe, 'function', 'portable probe capability exists');
  const requests = []; let clock = 0, id = 0, polls = 0;
  const fetchImpl = async (url, options) => {
    const request = {url: new URL(url), ...options, abortedAtFetch: options.signal.aborted,
      parsedBody: options.body === undefined ? undefined : JSON.parse(options.body)};
    requests.push(request);
    if (onFetch) { const response = await onFetch(request, requests.length); if (response) return response; }
    if (request.url.pathname === '/api/now/v2/cs/session') return reply(created);
    if (request.url.pathname === '/api/now/cs_message') return new Response(null, {status: endStatus});
    assert.equal(request.url.pathname, '/api/now/v1/cs/consumerAccount/' + ACCOUNT + '/sync');
    return reply(syncs[Math.min(polls++, syncs.length - 1)]);
  };
  const probe = createNativeSessionProbe({origin: ORIGIN, csrfToken: CSRF, fetchImpl,
    uuid: () => UUIDS[id++], now: () => 1793620800000,
    monotonic: () => clock, sleep: async ms => {clock += ms;}, ...config});
  return {probe, requests};
}
function noSecrets(value) {
  assert.equal(util.inspect(value, {depth: 8}).includes(CSRF), false);
  assert.equal(JSON.stringify(value).includes(CSRF), false);
}
test('authenticated diagnostic emits only native create, bound EndChat and false-initialization GET sync', async () => {
  const {probe, requests} = setup(); const result = await probe.run();
  assert.equal(result.passed, true); assert.equal(result.authenticated, true);
  assert.equal(result.version, 1); assert.equal(result.failureCode, null);
  assert.deepEqual(result.binding, {sessionId: SID, consumerAccountId: ACCOUNT,
    conversationId: CONVERSATION, channelSuffix: CHANNEL});
  assert.deepEqual(result.cleanup, {attempted: true, acknowledged: true, completed: true, uncertain: false});
  assert.equal(requests.length, 3);
  for (const request of requests) {
    assert.equal(request.url.origin, ORIGIN); assert.equal(request.credentials, 'same-origin');
    assert.equal(request.redirect, 'error'); assert.equal(request.mode, 'same-origin');
    assert.equal(request.headers['X-UserToken'], CSRF);
    assert.equal(Object.keys(request.headers).some(name => /authorization|cookie/i.test(name)), false);
  }
  assert.equal(requests[0].method, 'POST');
  assert.deepEqual(requests[0].parsedBody, {requestTime: 1793620800000, deviceId: UUIDS[0],
    direction: 'inbound', vendorId: 'c2f0b8f187033200246ddd4c97cb0bb9', consumerId: '',
    consumerAccountId: '', deviceType: 'mweb', contextData: {
      global_context_profile: 'c623e20f93374354e7f2b9fa6aba1081', nowassist: 'true'}});
  assert.equal(requests[1].method, 'POST');
  assert.equal(requests[1].headers['amb-channel'], '/cs/messages/' + CHANNEL);
  assert.equal(requests[1].headers['X-User-Activity'], 'true');
  assert.deepEqual(requests[1].parsedBody, {type: 'actionMessage', source: 'client', data: {
    actionMessage: {topicId: CONVERSATION, systemActionName: 'endChat', type: 'EndChat'},
    conversationId: CONVERSATION, deviceType: 'mweb', sessionId: SID,
    messageId: UUIDS[1], direction: 'inbound', sendTime: 1793620800000}});
  assert.equal(requests[2].method, 'GET'); assert.equal(requests[2].body, undefined);
  assert.deepEqual(Object.fromEntries(requests[2].url.searchParams), {serialNumber: '10',
    iefix: UUIDS[2], shouldInitializeConversation: 'false', conversationId: CONVERSATION});
  assert.equal(requests[2].headers['Session-Id'], SID);
  assert.equal(requests[2].headers['Guest-Session-Identifier'], 'null');
  assert.ok(result.phases.length >= 3);
  for (const phase of result.phases) assert.ok(Number.isFinite(phase.elapsed_ms) && phase.elapsed_ms >= 0);
  noSecrets(probe); noSecrets(result);
});
test('loading CommonJS and browser global never accesses fetch or credentials', () => {
  assert.ok(fs.existsSync(sourcePath), 'portable source exists');
  const context = {get fetch() {assert.fail('no load-time fetch access');},
    get g_ck() {assert.fail('no load-time credential access');}};
  vm.runInNewContext(fs.readFileSync(sourcePath, 'utf8'), context);
  assert.equal(typeof context.SccNativeSessionProbe.createNativeSessionProbe, 'function');
});
for (const [name, changes] of [
  ['missing session', {sessionId: undefined}], ['missing conversation', {conversationId: undefined}],
  ['missing account', {consumerAccountId: undefined}], ['wrong channel', {channelId: '/other/' + CHANNEL}],
  ['unsafe channel', {channelId: '/cs/messages/../x'}],
  ['contradictory accounts', {consumerAcctId: OTHER}],
  ['missing authentication', {guestSessionIdentifier: undefined}],
  ['guest authentication', {guestSessionIdentifier: 'guest-fixture'}],
  ['false authentication', {guestSessionIdentifier: false}],
  ['credential-shaped binding', {conversationId: CSRF}]
]) test(name + ' never authenticates or fabricates cleanup', async () => {
  const {probe, requests} = setup({created: session(changes)}); const result = await probe.run();
  assert.equal(result.passed, false); assert.equal(result.authenticated, false);
  assert.equal(result.cleanup.attempted, false); assert.equal(result.cleanup.uncertain, true);
  assert.equal(requests.length, 1); noSecrets(result);
});
test('native consumerAcctId alias is accepted without inventing an account', async () => {
  const {probe} = setup({created: session({consumerAccountId: undefined, consumerAcctId: ACCOUNT})});
  assert.equal((await probe.run()).passed, true);
});
test('an invented REST result envelope cannot authenticate a native session', async () => {
  const {probe, requests} = setup({created: {result: session()}});
  const result = await probe.run(); assert.equal(result.passed, false);
  assert.equal(result.authenticated, false); assert.equal(requests.length, 1);
});
test('an ambiguous result envelope beside direct native fields cannot authorize cleanup', async () => {
  const {probe, requests} = setup({created: {...session(), result: session({sessionId: OTHER})}});
  const result = await probe.run(); assert.equal(result.authenticated, false);
  assert.equal(result.cleanup.attempted, false); assert.equal(requests.length, 1);
});
test('TopicFinished may omit optional topic metadata when its native conversation and sequence match', async () => {
  const {probe} = setup({syncs: [{messages: [finished({actionMessage: {type: 'TopicFinished'}})]}]});
  assert.equal((await probe.run()).cleanup.completed, true);
});
for (const [name, changes] of [
  ['another conversation', {conversationId: OTHER}], ['another session', {sessionId: OTHER}],
  ['another topic', {actionMessage: {type: 'TopicFinished', topicId: OTHER}}],
  ['stale serial', {serialNumber: 10}], ['out-of-order serial', {serialNumber: 12}],
  ['wrong channel', {channelId: '/cs/messages/' + OTHER}],
  ['non-action DTO', {queueMsgDataType: 'consumerTextMessage'}],
  ['unrelated action', {actionMessage: {type: 'ShowTopic', ready: false}}]
]) test(name + ' cannot establish cleanup or publish an input/control acknowledgement', async () => {
  const {probe, requests} = setup({syncs: [{messages: [finished(changes)]}]});
  const result = await probe.run();
  assert.equal(result.passed, false); assert.equal(result.cleanup.completed, false);
  assert.equal(result.cleanup.uncertain, true);
  assert.equal(requests.filter(r => r.method === 'POST').length, 2);
  assert.ok(requests.length <= 8);
  assert.ok(requests.filter(r => r.method === 'GET').every(r => r.url.searchParams.get('shouldInitializeConversation') === 'false'));
});
test('sequential native DTOs advance cursor and only matching fresh TopicFinished completes', async () => {
  const {probe, requests} = setup({syncs: [
    {messages: [finished({actionMessage: {type: 'ShowTopic', ready: false}})], lastReadMessageSerialNum: 99},
    {messages: [finished({messageId: '66666666666666666666666666666666', serialNumber: 12})]}
  ]});
  assert.equal((await probe.run()).passed, true);
  assert.equal(requests[3].url.searchParams.get('serialNumber'), '11');
});
test('a reused message ID cannot turn a later serial into a cleanup witness', async () => {
  const {probe} = setup({syncs: [
    {messages: [finished({actionMessage: {type: 'ShowTopic', ready: false}})]},
    {messages: [finished({serialNumber: 12})]}
  ]});
  assert.equal((await probe.run()).cleanup.completed, false);
});
test('cancellation during sync cannot cancel the legitimate cleanup readback', async () => {
  const controller = new AbortController();
  const {probe, requests} = setup({onFetch(request, n) {if (n === 3) controller.abort(CSRF);}});
  const result = await probe.run({signal: controller.signal});
  assert.equal(result.passed, false); assert.equal(result.failureCode, 'CANCELLED');
  assert.equal(result.cleanup.completed, true); assert.equal(requests[2].abortedAtFetch, false);
  noSecrets(result);
});
test('cleanup reserve expiration prevents another GET even when polling budget remains', async () => {
  let clock = 0;
  const {probe, requests} = setup({syncs: [{messages: []}], config: {
    monotonic: () => clock, sleep: async () => {clock += 10000;}
  }});
  const result = await probe.run(); assert.equal(result.failureCode, 'TIMEOUT');
  assert.equal(result.cleanup.completed, false); assert.equal(result.cleanup.uncertain, true);
  assert.equal(requests.filter(r => r.method === 'GET').length, 2);
});
test('POST acknowledgement alone never completes cleanup', async () => {
  const {probe} = setup({syncs: [{messages: [], conversationState: 'CONVERSATION_COMPLETE'}]});
  const result = await probe.run(); assert.equal(result.cleanup.acknowledged, true);
  assert.equal(result.cleanup.completed, false); assert.equal(result.passed, false);
});
test('EndChat failure is never replayed but still permits bounded cleanup readback', async () => {
  const {probe, requests} = setup({endStatus: 403}); const result = await probe.run();
  assert.equal(result.passed, false); assert.equal(result.cleanup.acknowledged, false);
  assert.equal(result.cleanup.attempted, true);
  assert.equal(requests.filter(r => r.url.pathname === '/api/now/cs_message').length, 1);
});
test('cancellation just after creation retains an independent cleanup reserve', async () => {
  const controller = new AbortController();
  const {probe, requests} = setup({onFetch(request, n) {if (n === 1) controller.abort(CSRF);}});
  const result = await probe.run({signal: controller.signal});
  assert.equal(result.passed, false); assert.equal(result.failureCode, 'CANCELLED');
  assert.equal(result.cleanup.completed, true);
  assert.equal(requests[1].abortedAtFetch, false); assert.equal(requests[2].abortedAtFetch, false);
  noSecrets(result);
});
test('pre-cancelled run performs no request', async () => {
  const {probe, requests} = setup(); const controller = new AbortController(); controller.abort(CSRF);
  const result = await probe.run({signal: controller.signal});
  assert.equal(requests.length, 0); assert.equal(result.failureCode, 'CANCELLED'); noSecrets(result);
});
test('invalid serial after authenticated creation still sends one legitimate cleanup', async () => {
  const {probe, requests} = setup({created: session({serialNumber: 'stale'})});
  const result = await probe.run(); assert.equal(result.passed, false);
  assert.equal(result.cleanup.attempted, true); assert.equal(result.cleanup.completed, false);
  assert.equal(requests.filter(r => r.url.pathname === '/api/now/cs_message').length, 1);
});
test('duplicate and concurrent runs cannot replay a session or EndChat', async () => {
  const {probe, requests} = setup(); const [a, b] = await Promise.all([probe.run(), probe.run()]);
  const c = await probe.run(); assert.deepEqual(a, b); assert.deepEqual(b, c);
  assert.equal(requests.filter(r => r.url.pathname === '/api/now/v2/cs/session').length, 1);
  assert.equal(requests.filter(r => r.url.pathname === '/api/now/cs_message').length, 1);
});
for (const [name, makeResponse] of [
  ['oversized body', () => new Response(' '.repeat(65537) + CSRF)],
  ['malformed JSON', () => new Response(CSRF)],
  ['HTTP error', () => new Response(CSRF, {status: 500})],
  ['redirect response', () => ({ok: true, status: 200, redirected: true, body: null})],
  ['remote exception', () => {throw new Error(CSRF);}]
]) test(name + ' becomes a bounded credential-free uncertain create failure', async () => {
  const {probe, requests} = setup({onFetch: () => makeResponse()}); const result = await probe.run();
  assert.equal(result.passed, false); assert.equal(result.cleanup.attempted, false);
  assert.equal(result.cleanup.uncertain, true); assert.equal(requests.length, 1);
  assert.match(result.failureCode, /^[A-Z_]+$/); noSecrets(result); noSecrets(probe);
});
test('sync parse failure preserves attempted cleanup and hides response diagnostics', async () => {
  const {probe, requests} = setup({onFetch: (request, n) => n === 3 ? new Response(CSRF) : undefined});
  const result = await probe.run(); assert.equal(result.cleanup.attempted, true);
  assert.equal(result.cleanup.acknowledged, true); assert.equal(result.cleanup.uncertain, true);
  assert.equal(requests.length, 3); noSecrets(result);
});
test('too many sync messages cannot establish a completion witness', async () => {
  const {probe} = setup({syncs: [{messages: Array.from({length: 129}, () => finished())}]});
  const result = await probe.run(); assert.equal(result.passed, false);
  assert.equal(result.cleanup.completed, false); assert.equal(result.cleanup.uncertain, true);
});
test('a stalled create is aborted at its finite deadline without replay', async t => {
  t.mock.timers.enable({apis: ['setTimeout']});
  const {probe, requests} = setup({onFetch: () => new Promise(() => {})});
  const pending = probe.run();
  await new Promise(resolve => setImmediate(resolve));
  t.mock.timers.tick(15001);
  const result = await pending;
  assert.equal(requests.length, 1); assert.equal(requests[0].signal.aborted, true);
  assert.equal(result.failureCode, 'TIMEOUT'); assert.equal(result.cleanup.uncertain, true);
});
test('a fetch that ignores timeout cannot consume a late response body', async t => {
  t.mock.timers.enable({apis: ['setTimeout']});
  let resolveFetch, reads = 0;
  const response = reply(session());
  const original = response.body.getReader.bind(response.body);
  response.body.getReader = () => {reads++; return original();};
  const {probe, requests} = setup({onFetch: () => new Promise(resolve => {resolveFetch = resolve;})});
  const pending = probe.run(); await new Promise(resolve => setImmediate(resolve));
  t.mock.timers.tick(15001); const result = await pending;
  resolveFetch(response); await new Promise(resolve => setImmediate(resolve));
  assert.equal(result.failureCode, 'TIMEOUT'); assert.equal(reads, 0); assert.equal(requests.length, 1);
});
test('a stalled EndChat gets one deadline and bounded sync readback, never another EndChat', async t => {
  t.mock.timers.enable({apis: ['setTimeout']});
  const {probe, requests} = setup({onFetch: (request, n) => n === 2 ? new Promise(() => {}) : undefined});
  const pending = probe.run();
  await new Promise(resolve => setImmediate(resolve));
  t.mock.timers.tick(4001);
  const result = await pending;
  assert.equal(result.passed, false); assert.equal(result.cleanup.attempted, true);
  assert.equal(result.cleanup.acknowledged, false);
  assert.equal(requests.filter(r => r.url.pathname === '/api/now/cs_message').length, 1);
  assert.equal(requests[1].signal.aborted, true);
});
for (const config of [{origin: 'https://example.invalid'}, {origin: ORIGIN + '/extra'},
  {csrfToken: ''}, {csrfToken: 'bad\r\nheader'}, {uuid: () => 'not-a-uuid'}]) {
  test('invalid configuration fails closed before any request: ' + Object.keys(config)[0], async () => {
    const {probe, requests} = setup({config}); const result = await probe.run();
    assert.equal(result.failureCode, 'INVALID_CONFIG'); assert.equal(requests.length, 0); noSecrets(result);
  });
}
