'use strict';
// Full native handler, real S256 crypto, mocked HTTP/browser boundaries only.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {webcrypto, createHash} = require('node:crypto');
const {derive} = require('./build-oauth-candidate.cjs');
const original = fs.readFileSync(path.join(__dirname, 'Oauth-flow.original.js'));
const OWN = '11111111111111111111111111111111'; // Offline fixture only; never a deployment ID.
const NATIVE = '78e47507c6744b9ca5806e2c7d1a12bb';
const SERVICE = '8aa131d793f787105c8132d47aba1095';
const ENDPOINT = 'https://strix-alloy.tail7f425a.ts.net/scc-native';

async function run(options = {}) {
    const requests = [], events = [], writes = [];
    const api = {
        state: {isVoiceMode: Object.hasOwn(options, 'voiceMode') ? options.voiceMode : true},
        context: {props: {voiceAssistantId: options.service || SERVICE}},
        data: Object.hasOwn(options, 'data') ? options.data : {
            assistant_config_attributes: {output: {orchestratorUrl: options.endpoint || ENDPOINT}}},
        setState(key, value) {writes.push([key, value]); this.state[key] = value;},
        emit(name) {events.push(name);}
    };
    const window = {crypto: webcrypto, Uint8Array, TextEncoder, URLSearchParams,
        btoa: value => Buffer.from(value, 'binary').toString('base64'),
        fetch: async (url, init) => {
            requests.push({url, init});
            if (requests.length === 1) {
                const auth = new URL(url, 'https://instance.example.invalid');
                return {ok: true, json: async () => ({result: {code: 'fixture-code',
                    state: options.stateMismatch ? 'foreign-state' : auth.searchParams.get('state')}})};
            }
            assert.equal(requests.length, 2, 'native flow must not add another HTTP request');
            return {ok: true, json: async () => ({access_token: 'fixture-access'})};
        }};
    const handler = vm.runInNewContext(derive(original, OWN) + '\n;handler;', {console});
    await handler({api, event: {}, helpers: {translate: async value => value},
        imports: {'sn_nowassist_va.VoiceTestingUIUtils': () => ({getWindowObject: () => window})}});
    return {api, requests, events, writes};
}

function selectedClients(result) {
    return [new URL(result.requests[0].url, 'https://instance.example.invalid').searchParams.get('client_id'),
        new URLSearchParams(result.requests[1].init.body).get('client_id')];
}

test('exact local Voice uses own client in both authorization and token exchange', async () => {
    const result = await run();
    assert.deepEqual(selectedClients(result), [OWN, OWN]);
    assert.deepEqual(result.events, ['START_VOICE_SESSION']);
    assert.deepEqual(result.writes, [['auth_token', 'fixture-access']]);
});

for (const [name, options, event] of [
    ['chat', {voiceMode: false}, 'START_NEW_CHAT'],
    ['nonboolean Voice mode', {voiceMode: 'true'}, 'START_VOICE_SESSION'],
    ['missing Voice mode', {voiceMode: undefined}, 'START_NEW_CHAT'],
    ['other service', {service: '22222222222222222222222222222222'}, 'START_VOICE_SESSION'],
    ['native orchestrator', {endpoint: 'https://native.example.invalid'}, 'START_VOICE_SESSION'],
    ['endpoint trailing slash', {endpoint: ENDPOINT + '/'}, 'START_VOICE_SESSION'],
    ['endpoint suffix', {endpoint: ENDPOINT + '?other=1'}, 'START_VOICE_SESSION'],
    ['missing assistant data', {data: undefined}, 'START_VOICE_SESSION'],
    ['missing configuration output', {data: {assistant_config_attributes: {}}}, 'START_VOICE_SESSION'],
    ['missing orchestrator', {data: {assistant_config_attributes: {output: {}}}}, 'START_VOICE_SESSION']
]) {
    test(`${name} retains native client and its existing start event`, async () => {
        const result = await run(options);
        assert.deepEqual(selectedClients(result), [NATIVE, NATIVE]);
        assert.deepEqual(result.events, [event]);
    });
}

test('selection preserves same-instance endpoints, callback, real S256 and requested service claim', async () => {
    const result = await run(); const [authRequest, tokenRequest] = result.requests;
    const auth = new URL(authRequest.url, 'https://instance.example.invalid');
    const form = new URLSearchParams(tokenRequest.init.body);
    assert.equal(authRequest.url.startsWith('/oauth_auth.do?'), true);
    assert.equal(tokenRequest.url, '/oauth_token.do');
    assert.equal(tokenRequest.init.method, 'POST');
    assert.equal(tokenRequest.init.headers['Content-Type'], 'application/x-www-form-urlencoded');
    assert.equal(auth.searchParams.get('response_type'), 'code');
    assert.equal(auth.searchParams.get('redirect_uri'), '/api/sn_nowassist_va/voiceauth/oauth/authorize');
    assert.equal(form.get('redirect_uri'), '/api/sn_nowassist_va/voiceauth/oauth/authorize');
    assert.equal(form.get('grant_type'), 'authorization_code'); assert.equal(form.get('code'), 'fixture-code');
    const verifier = form.get('code_verifier'); assert.match(verifier, /^[A-Za-z0-9._~-]{64}$/);
    assert.equal(auth.searchParams.get('code_challenge_method'), 'S256');
    assert.equal(auth.searchParams.get('code_challenge'), createHash('sha256').update(verifier).digest('base64url'));
    assert.ok(auth.searchParams.get('state').length >= 32);
    assert.deepEqual(JSON.parse(Buffer.from(form.get('requested_claims'), 'base64').toString('utf8')),
        {voice_service_id: SERVICE});
    assert.equal(auth.searchParams.has('scope'), false); assert.equal(form.has('scope'), false);
});

test('a mismatched returned state still prevents token publication and start events', async () => {
    const result = await run({stateMismatch: true});
    assert.equal(result.requests.length, 2); // Preserve the native exchange-before-state-check ordering.
    assert.deepEqual(result.writes, []); assert.deepEqual(result.events, []);
});

test('factory refuses malformed or vendor-reused own client IDs', () => {
    for (const client of [undefined, null, '', NATIVE, 'x', OWN + ' ', OWN.toUpperCase().replace('1', 'A'),
        '1111111111111111111111111111111g', "'; globalThis.changed = true; '"])
        assert.throws(() => derive(original, client), /client identity/);
});

test('factory refuses original source drift and preserves the retained fixture identity', () => {
    assert.equal(createHash('sha256').update(original).digest('hex'),
        '9673f9b61867a007d14114976f7a9e11e78b8b8d1dcbd0758816a5c56357bef1');
    assert.throws(() => derive(Buffer.concat([original, Buffer.from(' ')]), OWN), /source identity/);
});
