'use strict';
// CPU-only full-handler tests. Candidate protocol is agreed with the source author;
// all browser/HTTP effects below are local fakes. Never navigates a real browser.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {webcrypto} = require('node:crypto');
const FACTORY = path.join(__dirname, 'build-oauth-consent-candidate.cjs');
const ORIGINAL = fs.readFileSync(path.join(__dirname, 'Oauth-flow.original.js'));
const OWN = '11111111111111111111111111111111'; // Offline identity only.
const SERVICE = '8aa131d793f787105c8132d47aba1095';
const ENDPOINT = 'https://strix-alloy.tail7f425a.ts.net/scc-native';
const ORIGIN = 'https://instance.example.invalid';
const CALLBACK = '/api/sn_nowassist_va/voiceauth/oauth/authorize';
const ENTITY = '78e3391e93dc9354e7f2b9fa6aba1019';
const CONSENT = '/oauth_auth_check.do?sysparm_oauthapp_id=' + ENTITY;

class FakeTarget {
    constructor() { this.listeners = new Map(); }
    addEventListener(name, fn) {
        const values = this.listeners.get(name) || new Set();
        values.add(fn); this.listeners.set(name, values);
    }
    removeEventListener(name, fn) { this.listeners.get(name)?.delete(fn); }
    dispatch(name) {
        const event = {type: name, target: this, defaultPrevented: false,
            preventDefault() { this.defaultPrevented = true; }};
        for (const fn of [...(this.listeners.get(name) || [])]) fn(event);
        return event;
    }
    listenerCount() { return [...this.listeners.values()].reduce((sum, row) => sum + row.size, 0); }
}

function fakeDocument() {
    const nodes = [], timers = [];
    class Node extends FakeTarget {
        constructor(tag) {
            super(); this.tagName = tag.toUpperCase(); this.children = [];
            this.parentNode = null; this.attributes = {}; this.style = {};
            this.textContent = ''; this.open = false; this.isConnected = false;
            if (tag === 'iframe') {
                let href = 'about:blank';
                const location = {get href() { return href; }, set href(value) { href = value; },
                    get origin() { return new URL(href).origin; },
                    get pathname() { return new URL(href).pathname; }};
                this.contentDocument = {body: {textContent: '', innerText: ''}};
                this.contentWindow = {location, document: this.contentDocument};
            }
            nodes.push(this);
        }
        set innerHTML(_value) { throw Error('raw HTML insertion forbidden'); }
        get innerHTML() { throw Error('raw HTML reading forbidden'); }
        setAttribute(key, value) { this.attributes[key] = String(value); this[key] = String(value); }
        appendChild(node) { node.parentNode = this; node.isConnected = this.isConnected;
            this.children.push(node); return node; }
        append(...values) { for (const value of values) this.appendChild(value); }
        removeChild(node) { this.children = this.children.filter(value => value !== node);
            node.parentNode = null; node.isConnected = false; return node; }
        remove() { this.parentNode?.removeChild(this); }
        showModal() { this.open = true; }
        close() { this.open = false; this.dispatch('close'); }
        click() { this.dispatch('click'); }
    }
    const body = new Node('body'); body.isConnected = true;
    const document = {body, createElement: tag => new Node(tag)};
    return {document, nodes, timers,
        setTimeout(fn, ms) { const timer = {fn, ms, cleared: false}; timers.push(timer); return timer; },
        clearTimeout(timer) { if (timer) timer.cleared = true; },
        frame() { return nodes.filter(node => node.tagName === 'IFRAME').at(-1); },
        dialog() { return nodes.filter(node => node.tagName === 'DIALOG').at(-1); },
        callback(value, url = ORIGIN + CALLBACK) {
            const frame = this.frame(); assert.ok(frame, 'consent iframe must already exist');
            frame.contentWindow.location.href = url;
            frame.contentDocument.body.textContent = typeof value === 'string' ? value : JSON.stringify(value);
            frame.contentDocument.body.innerText = frame.contentDocument.body.textContent;
            frame.dispatch('load');
        }};
}

function startFlow(options = {}) {
    assert.ok(fs.existsSync(FACTORY), 'Own first-user consent candidate is missing');
    const {derive} = require(FACTORY);
    assert.equal(typeof derive, 'function', 'Own consent source factory must export derive');
    const dom = fakeDocument(), requests = [], events = [], writes = [], payloads=[];
    const api = {state: {isVoiceMode: options.voiceMode ?? true,isConnectionInProgress:true,callStarted:options.callStarted===true},
        context: {props: {voiceAssistantId: options.service || SERVICE}},
        data: {assistant_config_attributes: {output: {orchestratorUrl: options.endpoint || ENDPOINT}}},
        setState(key, value) { writes.push([key, value]); this.state[key] = value; },
        emit(name,payload) { events.push(name);payloads.push(payload); }};
    const window = {document: dom.document, location: {origin: ORIGIN, href: ORIGIN + '/voice-test'},
        crypto: webcrypto, Uint8Array, TextEncoder, URL, URLSearchParams,
        setTimeout: dom.setTimeout, clearTimeout: dom.clearTimeout,
        btoa: value => Buffer.from(value, 'binary').toString('base64'),
        fetch: async (url, init) => {
            requests.push({url, init});
            if (url.startsWith('/oauth_auth.do?')) {
                const auth = new URL(url, ORIGIN);
                const result = {code: 'fixture-code', state: options.stateMismatch
                    ? 'foreign-state' : auth.searchParams.get('state')};
                return {ok: true, status: 200, url: ORIGIN + (options.html ? CONSENT : CALLBACK
                    + '?code=' + result.code + '&state=' + result.state), redirected: true,
                    headers: {get: name => name.toLowerCase() === 'content-type'
                        ? options.html ? 'text/html; charset=UTF-8' : 'application/json' : null},
                    json: async () => { assert.ok(!options.html, 'HTML must not be read as JSON'); return {result}; },
                    text: async () => { throw Error('consent HTML must be rendered from original auth URL'); }};
            }
            assert.equal(url,'/oauth_token.do','only the native token endpoint can be exchanged');
            return {ok: options.tokenOk!==false, status: options.tokenOk===false?401:200, json: async () => options.tokenData || {access_token: 'fixture-access-valid-0123456789'}};
        }};
    const handler = vm.runInNewContext(derive(ORIGINAL, OWN) + '\n;handler;',
        {console, URL, document: dom.document, setTimeout: dom.setTimeout, clearTimeout: dom.clearTimeout});
    const invoke=(invocationApi=api)=>Promise.resolve(handler({api:invocationApi, event: {}, helpers: {translate: async value => {if(options.translationFails)throw Error('fixture_translation_failure');return value;}},
        imports: {'sn_nowassist_va.VoiceTestingUIUtils': () => ({getWindowObject: () => window})}}))
        .then(() => null, error => error);
    const finished=invoke();
    return {dom, requests, events, writes, finished,invoke,api,payloads};
}

async function waitFor(check) {
    const deadline = Date.now() + 3000;
    while (!check()) {
        assert.ok(Date.now() < deadline, 'bounded fake protocol wait expired');
        await new Promise(resolve => setImmediate(resolve));
    }
}

function assertClean(flow) {
    assert.equal(flow.dom.document.body.children.length, 0, 'consent nodes removed');
    assert.equal(flow.dom.nodes.reduce((sum, node) => sum + node.listenerCount(), 0), 0,
        'consent event listeners removed');
    assert.ok(flow.dom.timers.every(timer => timer.cleared), 'consent timers cleared');
}

function stateOf(flow) { return new URL(flow.requests[0].url, ORIGIN).searchParams.get('state'); }
function assertNoStart(flow) {
    assert.equal(flow.requests.length, 1, 'failure must occur before authorization-code exchange');
    assert.deepEqual(flow.writes.filter(([key])=>key==='auth_token'), [], 'failed authorization cannot publish a token');
    assert.ok(!flow.events.some(name => name === 'START_VOICE_SESSION' || name === 'START_NEW_CHAT'));
}
async function consentFlow(options = {}) {
    const flow = startFlow({html: true, ...options});
    await waitFor(() => flow.dom.frame());
    return flow;
}

test('first-user consent factory is implemented as an inert source derivative', () => {
    assert.ok(fs.existsSync(FACTORY), 'Own first-user consent candidate is missing');
    assert.equal(typeof require(FACTORY).derive, 'function');
});

test('own direct JSON publishes the returned token once and starts Voice without a dialog', async () => {
    const flow = startFlow(); assert.equal(await flow.finished, null);
    assert.equal(new URL(flow.requests[0].url, ORIGIN).searchParams.get('client_id'), OWN);
    assert.equal(new URLSearchParams(flow.requests[1].init.body).get('client_id'), OWN);
    assert.deepEqual(flow.writes, [['auth_token', 'fixture-access-valid-0123456789']]);
    assert.deepEqual(flow.events, ['START_VOICE_SESSION']);
    assert.equal(flow.dom.frame(), undefined); assertClean(flow);
});

test('own direct JSON mismatched state refuses code exchange, token publication and Start', async () => {
    const flow = startFlow({stateMismatch: true}); await flow.finished;
    assertNoStart(flow); assertClean(flow);
});

test('HTML consent uses the complete original auth URL in a native modal iframe then callback body JSON', async () => {
    const flow = await consentFlow(), frame = flow.dom.frame(), dialog = flow.dom.dialog();
    assert.ok(dialog); assert.equal(dialog.open, true);
    assert.equal(new URL(frame.src, ORIGIN).href, new URL(flow.requests[0].url, ORIGIN).href);
    assert.equal(new URL(frame.src, ORIGIN).searchParams.has('scope'), false);
    assertNoStart(flow);
    flow.dom.callback({result: {code: 'native-callback-code', state: stateOf(flow)}});
    assert.equal(await flow.finished, null);
    assert.equal(new URLSearchParams(flow.requests[1].init.body).get('code'), 'native-callback-code');
    assert.deepEqual(flow.writes, [['auth_token', 'fixture-access-valid-0123456789']]);
    assert.deepEqual(flow.events, ['START_VOICE_SESSION']); assertClean(flow);
});

test('authorization-page iframe load cannot treat its body as a callback', async () => {
    const flow = await consentFlow(), frame = flow.dom.frame();
    frame.contentWindow.location.href = new URL(flow.requests[0].url, ORIGIN).href;
    frame.contentDocument.body.textContent = JSON.stringify({result: {code: 'forged', state: stateOf(flow)}});
    frame.dispatch('load'); await new Promise(resolve => setImmediate(resolve));
    assertNoStart(flow);
    flow.dom.callback({result: {code: 'real', state: stateOf(flow)}});
    assert.equal(await flow.finished, null); assertClean(flow);
});

test('exact observed native check page is an intermediate load until the JSON callback arrives', async () => {
    const flow = await consentFlow(), frame = flow.dom.frame();
    frame.contentWindow.location.href = ORIGIN + CONSENT;
    frame.contentDocument.body.textContent = 'SCC Local Browser Voice (Opaque PKCE) AI Voice SCC Local Voice Caller';
    frame.dispatch('load'); await new Promise(resolve => setImmediate(resolve));
    assertNoStart(flow);
    flow.dom.callback({result: {code: 'real', state: stateOf(flow)}}, ORIGIN + CALLBACK
        + '?code=real&state=' + stateOf(flow));
    assert.equal(await flow.finished, null); assertClean(flow);
});

test('a check-page load for another OAuth entity cannot continue local authorization', async () => {
    const flow = await consentFlow();
    flow.dom.callback('native consent page', ORIGIN + '/oauth_auth_check.do?sysparm_oauthapp_id=' + '0'.repeat(32));
    await flow.finished; assertNoStart(flow); assertClean(flow);
});

test('a native check-page load with extra query fields cannot continue local authorization', async () => {
    const flow = await consentFlow();
    flow.dom.callback('native consent page', ORIGIN + CONSENT + '&scope=useraccount');
    await flow.finished; assertNoStart(flow); assertClean(flow);
});

test('callback state mismatch is rejected before exchange and cleans the modal', async () => {
    const flow = await consentFlow();
    flow.dom.callback({result: {code: 'native-code', state: 'foreign-state'}});
    await flow.finished; assertNoStart(flow); assertClean(flow);
});

test('native dialog cancel prevents exchange and removes listeners and timers', async () => {
    const flow = await consentFlow(); flow.dom.dialog().dispatch('cancel');
    await flow.finished; assertNoStart(flow); assertClean(flow);
    assert.equal(flow.api.state.isConnectionInProgress,false);
});

test('visible Cancel button prevents exchange and removes the modal', async () => {
    const flow = await consentFlow();
    const button = flow.dom.nodes.find(node => node.tagName === 'BUTTON');
    assert.ok(button, 'consent must expose a keyboard accessible Cancel button'); button.click();
    await flow.finished; assertNoStart(flow); assertClean(flow);
});

test('bounded consent timeout prevents exchange and cleans modal resources', async () => {
    const flow = await consentFlow(), timer = flow.dom.timers.find(value => !value.cleared);
    assert.ok(timer && Number.isFinite(timer.ms) && timer.ms > 0, 'consent timeout must be bounded');
    timer.fn(); await flow.finished; assertNoStart(flow); assertClean(flow);
    assert.equal(flow.api.state.isConnectionInProgress,false);
});

test('native callback denial prevents exchange and cleans modal resources', async () => {
    const flow = await consentFlow();
    flow.dom.callback({result: {error: 'access_denied', state: stateOf(flow)}});
    await flow.finished; assertNoStart(flow); assertClean(flow);
});

test('foreign origin with the same callback path cannot authorize local Voice', async () => {
    const flow = await consentFlow();
    flow.dom.callback({result: {code: 'foreign-code', state: stateOf(flow)}}, 'https://foreign.invalid' + CALLBACK);
    await flow.finished; assertNoStart(flow); assertClean(flow);
});

test('callback malformed body cannot publish tokens or start Voice', async () => {
    const flow = await consentFlow(); flow.dom.callback('<html>native callback error</html>');
    await flow.finished; assertNoStart(flow); assertClean(flow);
});

test('callback extra query fields cannot change the fixed authorization response path', async () => {
    const flow = await consentFlow();
    flow.dom.callback({result: {code: 'native-code', state: stateOf(flow)}}, ORIGIN + CALLBACK
        + '?code=native-code&state=' + stateOf(flow) + '&scope=useraccount');
    await flow.finished; assertNoStart(flow); assertClean(flow);
});

test('token exchange denial never publishes an auth token or emits Start', async () => {
    const flow = startFlow({tokenData: {error: 'access_denied', error_description: 'access_denied'}});
    await flow.finished; assert.equal(flow.requests.length, 2); assert.deepEqual(flow.writes.filter(([key])=>key==='auth_token'), []);
    assert.ok(!flow.events.some(name => name === 'START_VOICE_SESSION' || name === 'START_NEW_CHAT'));
    assertClean(flow);
});

test('own token HTTP failure or malformed success never publishes a token or starts Voice',async()=>{
    for(const options of [{tokenOk:false},{tokenData:{}},{tokenData:{access_token:'short'}},{tokenData:{access_token:'valid-token-0123456789',error:'server_error'}}]){
        const flow=startFlow(options);assert.equal(await flow.finished,null);
        assert.deepEqual(flow.writes.filter(([key])=>key==='auth_token'),[]);
        assert.equal(flow.events.includes('START_VOICE_SESSION'),false);
        assert.equal(flow.api.state.isConnectionInProgress,false);
        assert.equal(flow.events.filter(name=>name==='NOW_UXF_PAGE#ADD_NOTIFICATIONS').length,1);
    }
});

test('new attempt closes the old modal and only the newest callback can publish or Start',async()=>{
    const flow=await consentFlow(),oldFrame=flow.dom.frame(),oldState=stateOf(flow);
    const newer=flow.invoke();await waitFor(()=>flow.requests.length===2&&flow.dom.frame()!==oldFrame);
    oldFrame.contentWindow.location.href=ORIGIN+CALLBACK;
    oldFrame.contentDocument.body.textContent=JSON.stringify({result:{code:'old-code',state:oldState}});
    oldFrame.dispatch('load');await new Promise(resolve=>setImmediate(resolve));
    assert.equal(flow.requests.filter(r=>r.url==='/oauth_token.do').length,0);
    const nextState=new URL(flow.requests[1].url,ORIGIN).searchParams.get('state');
    flow.dom.callback({result:{code:'new-code',state:nextState}});
    assert.equal(await flow.finished,null);assert.equal(await newer,null);
    assert.equal(flow.requests.filter(r=>r.url==='/oauth_token.do').length,1);
    assert.equal(flow.events.filter(name=>name==='START_VOICE_SESSION').length,1);
    assert.deepEqual(flow.writes.filter(([key])=>key==='auth_token'),[['auth_token','fixture-access-valid-0123456789']]);
    assertClean(flow);
});

test('a stale assistant context cannot exchange its late consent callback',async()=>{
    const flow=await consentFlow();flow.api.context.props.voiceAssistantId='2'.repeat(32);
    flow.dom.callback({result:{code:'stale-code',state:stateOf(flow)}});
    assert.equal(await flow.finished,null);assertNoStart(flow);assertClean(flow);
});

test('fixed visible failure notice survives translation failure and clears connection progress',async()=>{
    const flow=await consentFlow({translationFails:true});flow.dom.dialog().dispatch('cancel');
    assert.equal(await flow.finished,null);assertNoStart(flow);assertClean(flow);
    assert.equal(flow.api.state.isConnectionInProgress,false);
    assert.equal(flow.events.filter(name=>name==='NOW_UXF_PAGE#ADD_NOTIFICATIONS').length,1);
    const notice=flow.payloads.find(Boolean);
    assert.match(notice.items[0].content.value,/Anmeldung/);
});

test('an already started call cannot emit another authorization or Start',async()=>{
    const flow=startFlow({callStarted:true});assert.equal(await flow.finished,null);
    assert.equal(flow.requests.length,0);assert.deepEqual(flow.events,[]);assert.deepEqual(flow.writes,[]);assertClean(flow);
});

test('a new API wrapper for the same Voice window supersedes its old modal',async()=>{
    const flow=await consentFlow(),oldDialog=flow.dom.dialog(),oldFrame=flow.dom.frame();
    const newer=flow.invoke({...flow.api});await waitFor(()=>flow.requests.length===2&&flow.dom.frame()!==oldFrame);
    assert.equal(oldDialog.open,false,'window-level Voice ownership must not depend on API wrapper identity');
    const state=new URL(flow.requests[1].url,ORIGIN).searchParams.get('state');
    flow.dom.callback({result:{code:'new-wrapper-code',state}});
    assert.equal(await flow.finished,null);assert.equal(await newer,null);
    assert.equal(flow.events.filter(name=>name==='START_VOICE_SESSION').length,1);assertClean(flow);
});

test('other assistant retains native client and native exchange-before-state-check behavior', async () => {
    const flow = startFlow({service: '22222222222222222222222222222222', stateMismatch: true});
    assert.equal(await flow.finished, null); assert.equal(flow.requests.length, 2);
    for (const request of flow.requests) {
        const client = request.init ? new URLSearchParams(request.init.body).get('client_id')
            : new URL(request.url, ORIGIN).searchParams.get('client_id');
        assert.equal(client, '78e47507c6744b9ca5806e2c7d1a12bb');
    }
    assert.deepEqual(flow.writes, []); assert.deepEqual(flow.events, []);
    assert.equal(flow.dom.frame(), undefined); assertClean(flow);
});
