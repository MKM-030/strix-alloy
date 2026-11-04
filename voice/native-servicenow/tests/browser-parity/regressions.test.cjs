'use strict';
// Portable offline Node tests: no browser, SDK, network, device or instance API.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const crypto = require('node:crypto');
const {derive} = require('./build-candidate.cjs');
const original = fs.readFileSync(path.join(__dirname, 'Start-voice-session.original.js'));
const candidate = derive(original);
const baseline = process.env.VOICE_PARITY_BASELINE === '1';
const production = fs.readFileSync(path.join(__dirname, '../../Start-voice-session.js'), 'utf8');
const source = baseline ? original.toString('utf8') : production;
const cleanup = fs.readFileSync(path.join(__dirname, 'disconnectVoice.original.js'), 'utf8');
assert.equal(crypto.createHash('sha256').update(cleanup).digest('hex'),
    '80e18fb2aa6b5eee449ae5af62df5b5d7fe0610376884cf9af84ac1d484cdb29');
const flush = () => new Promise(resolve => setImmediate(resolve));
function deferred() {let resolve; const promise = new Promise(r => {resolve = r;}); return {promise, resolve};}

async function setup(options = {}) {
    const observations = {sockets: [], peers: [], contexts: [], notices: [], timers: [], timerStarts: 0,
        cleanup: 0, stopped: 0, played: 0, resumed: 0, order: [], remoteStreams: [], analysisStreams: []};
    const track = {readyState: 'live', stop() {observations.stopped++;}};
    const stream = {getAudioTracks: () => [track], getTracks: () => [track]};
    const audio = {srcObject: null, play() {
        observations.played++; observations.order.push('play');
        return options.playFailure ? Promise.reject(new Error('private-media-sentinel')) : Promise.resolve();
    }};
    class Context {
        constructor() {
            if (options.constructorFailure) throw new Error('private-analysis-sentinel');
            this.state = options.contextState || 'running'; this.closes = 0; observations.contexts.push(this);
        }
        createMediaStreamSource(stream) {
            observations.analysisStreams.push(stream);
            if (options.sourceFailure) throw new Error('private-analysis-sentinel');
            return {connect() {}};
        }
        createAnalyser() {
            if (options.analyserFailure) throw new Error('private-analysis-sentinel');
            return {};
        }
        resume() {
            observations.resumed++; observations.order.push('resume');
            if (options.resumeFailure) return Promise.reject(new Error('private-media-sentinel'));
            const finish = () => {if (!options.stillSuspended) this.state = 'running';};
            if (options.resumeWait) return options.resumeWait.promise.then(finish);
            finish(); return Promise.resolve();
        }
        close() {this.closes++; this.state = 'closed'; return Promise.resolve();}
    }
    class Peer {
        constructor() {this.iceConnectionState = 'new'; this.closed = false; observations.peers.push(this);}
        addTrack() {}
        createDataChannel() {return {};}
        createOffer() {
            if (options.offerFailure) return Promise.reject(new Error('private-sdp-sentinel'));
            return Promise.resolve({type: 'offer', sdp: 'synthetic-offer'});
        }
        setConfiguration() {observations.order.push('configuration');}
        setLocalDescription() {
            observations.order.push('local');
            return options.localFailure ? Promise.reject(new Error('private-sdp-sentinel')) : Promise.resolve();
        }
        setRemoteDescription() {
            observations.order.push('remote');
            return options.remoteFailure ? Promise.reject(new Error('private-sdp-sentinel')) : Promise.resolve();
        }
        addIceCandidate() {
            return options.candidateFailure ? Promise.reject(new Error('private-candidate-sentinel')) : Promise.resolve();
        }
        close() {this.closed = true;}
    }
    class Socket {
        static OPEN = 1;
        constructor(url) {this.url = url; this.readyState = 1; this.sent = []; this.closes = 0; observations.sockets.push(this);}
        send(raw) {this.sent.push(JSON.parse(raw));}
        close() {this.closes++; this.readyState = 3;}
    }
    class RemoteStream {
        constructor(tracks) {
            if (options.streamFailure) throw new Error('private-stream-sentinel');
            this.tracks = [...tracks]; observations.remoteStreams.push(this);
        }
        getTracks() {return this.tracks;}
        getAudioTracks() {return this.tracks.filter(track => track.kind === 'audio');}
    }
    const window = {testVoiceUI: {}, navigator: {permissions: {query: async () => {
        if (options.permissionApiMissing) throw new TypeError('API unavailable');
        return {state: options.permissionDenied ? 'denied' : 'granted'};
    }}, mediaDevices: {getUserMedia: async () => stream}},
        document: {getElementById: () => audio}, RTCPeerConnection: Peer, WebSocket: Socket,
        AudioContext: Context, MediaStream: RemoteStream, URLSearchParams,
        RTCSessionDescription: class {constructor(value) {Object.assign(this, value);}},
        RTCIceCandidate: class {constructor(value) {Object.assign(this, value);}}};
    const api = {state: {auth_token: 'synthetic-credential', instanceName: 'synthetic-instance', repeaterItems: []},
        data: {assistant_config_attributes: {output: {orchestratorUrl: 'https://synthetic.example.invalid/scc-native',
            attrs: {language: 'de'}}}}, context: {props: {voiceAssistantId: 'synthetic-service'}},
        setState(name, value) {this.state[name] = value;},
        emit(name, value) {observations.notices.push({name, value});}};
    const helpers = {translate: async value => {
        if (options.translateFailure) throw new Error('private-translation-sentinel');
        return value;
    }, timing: {setTimeout(fn) {const t = {fn, cleared: false}; observations.timers.push(t); return t;},
        clearTimeout(t) {if (t) t.cleared = true;}, clearInterval() {}}};
    const nativeDisconnect = vm.runInNewContext(cleanup + '\n;disconnectVoice;', {
        api, helpers, structuredClone, markAnalysisComplete() {}});
    const uiUtils = {getWindowObject: () => window,
        disconnectVoice(win, rtc) {observations.cleanup++; return nativeDisconnect(win, rtc);},
        startCallTimer() {observations.timerStarts++;}, handleDataChannelMessage() {}, updateVoiceAnalysisTabData() {}};
    const handler = vm.runInNewContext(source + '\n;handler;', {console, URLSearchParams, setTimeout});
    await handler({api, helpers, event: {}, imports: {'sn_nowassist_va.VoiceTestingUIUtils': () => uiUtils,
        'sn_uxf.core_libraries': () => ({})}});
    const socket = observations.sockets[0];
    if (socket && !options.deferOpen) await socket.onopen();
    return {observations, window, api, helpers, uiUtils, socket, audio,
        get peer() {return window.testVoiceUI.webrtc.pc;}, get rtc() {return window.testVoiceUI.webrtc;}};
}
function remoteEvent() {return {track: {kind: 'audio'}, streams: [{id: 'synthetic-remote'}]};}
function bareRemoteEvent(kind = 'audio', readyState = 'live') {return {track: {kind, readyState}, streams: []};}
function answer() {return {data: JSON.stringify({type: 'answer', sdp: 'synthetic-answer',
    iceServers: [{urls: ['stun:synthetic.example.invalid']}]})};}

test('production script is the exact reviewed original-source derivative', () => {
    assert.equal(production, candidate);
    assert.throws(() => derive(Buffer.from(original.toString('utf8') + ' ')), /identity changed/);
});
test('created AudioContext belongs to the native cleanup owner', async () => {
    const env = await setup(); await env.peer.ontrack(remoteEvent());
    assert.equal(env.rtc.audioContext, env.observations.contexts[0]);
    env.uiUtils.disconnectVoice(env.window, env.rtc);
    assert.equal(env.observations.contexts[0].closes, 1);
    assert.equal(env.observations.stopped, 1);
    assert.equal(env.rtc.audioContext, null);
});

test('live bare remote audio reaches playback and the same optional analyzer stream', async () => {
    const env = await setup(); const event = bareRemoteEvent();
    await env.peer.ontrack(event);
    assert.equal(env.observations.played, 1);
    assert.equal(env.observations.remoteStreams.length, 1);
    assert.equal(env.audio.srcObject, env.observations.remoteStreams[0]);
    assert.equal(env.audio.srcObject.getTracks()[0], event.track);
    assert.equal(env.observations.analysisStreams[0], env.audio.srcObject);
    assert.equal(env.observations.cleanup, 0);
});

test('an existing remote stream is used without allocating a fallback wrapper', async () => {
    const env = await setup(); const event = remoteEvent();
    await env.peer.ontrack(event);
    assert.equal(env.observations.played, 1);
    assert.equal(env.observations.remoteStreams.length, 0);
    assert.equal(env.audio.srcObject, event.streams[0]);
    assert.equal(env.observations.analysisStreams[0], event.streams[0]);
});

for (const stale of ['owner', 'peer']) {
    test(`stale ${stale} cannot allocate or play bare remote audio`, async () => {
        const env = await setup(); const ontrack = env.peer.ontrack;
        if (stale === 'owner') env.window.testVoiceUI.webrtc = {replacement: true};
        else env.rtc.pc = {replacement: true};
        await ontrack(bareRemoteEvent());
        assert.equal(env.observations.played, 0); assert.equal(env.observations.remoteStreams.length, 0);
        assert.equal(env.observations.contexts.length, 0); assert.equal(env.observations.cleanup, 0);
        assert.equal(env.audio.srcObject, null);
    });
}

for (const [kind, readyState] of [['video', 'live'], ['audio', 'ended']]) {
    test(`bare ${kind}/${readyState} track is not admitted to playback`, async () => {
        const env = await setup(); await env.peer.ontrack(bareRemoteEvent(kind, readyState));
        assert.equal(env.observations.played, 0); assert.equal(env.observations.remoteStreams.length, 0);
        assert.equal(env.observations.contexts.length, 0); assert.equal(env.observations.cleanup, 0);
    });
}

for (const failure of ['streamFailure', 'playFailure']) {
    test(`bare audio ${failure} uses the existing owned media failure cleanup`, async () => {
        const env = await setup({[failure]: true});
        await assert.doesNotReject(async () => env.peer.ontrack(bareRemoteEvent())); await flush();
        assert.equal(env.observations.cleanup, 1); assert.equal(env.observations.stopped, 1);
        assert.equal(env.audio.srcObject, null); assert.equal(env.api.state.callStarted, false);
        assert.equal(env.observations.notices.length, 1);
        assert.equal(JSON.stringify(env.observations.notices).includes('sentinel'), false);
    });
}

test('bare audio playback survives an optional analysis failure', async () => {
    const env = await setup({constructorFailure: true}); await env.peer.ontrack(bareRemoteEvent());
    assert.equal(env.observations.played, 1); assert.equal(env.observations.remoteStreams.length, 1);
    assert.equal(env.audio.srcObject, env.observations.remoteStreams[0]);
    assert.equal(env.observations.cleanup, 0); assert.equal(env.observations.notices.length, 0);
});

test('disconnect clears the bare audio wrapper through the existing media owner', async () => {
    const env = await setup(); const event = bareRemoteEvent(); let remoteStops = 0;
    event.track.stop = () => remoteStops++;
    const peer = env.peer; await peer.ontrack(event);
    env.uiUtils.disconnectVoice(env.window, env.rtc);
    assert.equal(peer.closed, true); assert.equal(env.observations.stopped, 1);
    assert.equal(env.observations.contexts[0].closes, 1); assert.equal(env.audio.srcObject, null);
    assert.equal(remoteStops, 0);
});
test('suspended analysis resume is attempted independently and repeated track reuses its owner', async () => {
    const env = await setup({contextState: 'suspended'}); const peer = env.peer;
    await peer.ontrack(remoteEvent()); await peer.ontrack(remoteEvent());
    assert.equal(env.observations.resumed, 1);
    assert.equal(env.observations.contexts.length, 1);
    assert.deepEqual(env.observations.order.filter(x => ['resume', 'play'].includes(x)), ['play', 'resume', 'play']);
});
test('completed alone counts as ICE success; connected then completed starts one timer', async () => {
    const env = await setup(); env.peer.iceConnectionState = 'completed'; env.peer.oniceconnectionstatechange();
    assert.equal(env.rtc.isConnected, true); assert.equal(env.observations.timerStarts, 1);
    env.peer.iceConnectionState = 'connected'; env.peer.oniceconnectionstatechange();
    env.peer.iceConnectionState = 'completed'; env.peer.oniceconnectionstatechange();
    assert.equal(env.observations.timerStarts, 1); assert.equal(env.observations.timers[0].cleared, true);
});
test('timeout observes completed without requiring a prior connected event or creating retry', async () => {
    const env = await setup(); env.peer.iceConnectionState = 'completed';
    await env.observations.timers[0].fn();
    assert.equal(env.rtc.isConnected, true);
    assert.equal(env.observations.sockets.length, 1); assert.equal(env.observations.timerStarts, 1);
});
test('async signaling handler promise is observed', async () => {
    const env = await setup();
    const pending = env.socket.onmessage({data: JSON.stringify({type: 'ignored'})});
    assert.ok(pending && typeof pending.then === 'function'); await pending;
});
test('native offer deferral and configuration/local/remote answer order remain intact', async () => {
    const env = await setup(); assert.equal(env.observations.order.includes('local'), false);
    assert.equal(env.socket.sent[0].type, 'offer'); assert.equal(env.socket.sent[0].sdp.type, 'offer');
    await env.socket.onmessage(answer()); await flush();
    assert.deepEqual(env.observations.order, ['configuration', 'local', 'remote']);
});
test('native authenticated WSS route and query stay unchanged', async () => {
    const env = await setup(); const url = new URL(env.socket.url);
    assert.equal(url.origin, 'wss://synthetic.example.invalid');
    assert.equal(url.pathname, '/scc-native/webrtc/connect/agent_operator');
    assert.equal(url.searchParams.get('auth_token'), 'synthetic-credential');
    assert.equal(url.searchParams.get('voice_service_id'), 'synthetic-service');
    assert.equal(url.searchParams.get('instance_name'), 'synthetic-instance');
    assert.equal(url.searchParams.get('client_app'), 'admin_test');
});
test('unready ICE retains its original two retry limit', async () => {
    const env = await setup();
    await env.observations.timers[0].fn();
    await env.observations.sockets[1].onopen();
    await env.observations.timers[1].fn();
    await env.observations.sockets[2].onopen();
    await env.observations.timers[2].fn();
    assert.equal(env.observations.sockets.length, 3);
    assert.equal(env.observations.notices.length, 1);
    assert.equal(env.api.state.isConnectionInProgress, false);
});
for (const failure of ['playFailure']) {
    test(`audio failure is contained and closes current owned call: ${failure}`, {skip: baseline}, async () => {
        const env = await setup({[failure]: true, contextState: 'suspended'});
        await assert.doesNotReject(async () => env.peer.ontrack(remoteEvent())); await flush();
        assert.equal(env.observations.cleanup, 1); assert.equal(env.observations.stopped, 1);
        assert.equal(env.observations.contexts[0].closes, 1); assert.equal(env.api.state.callStarted, false);
        assert.equal(env.observations.notices.length, 1);
        assert.equal(JSON.stringify(env.observations.notices).includes('sentinel'), false);
    });
}
for (const failure of ['resumeFailure', 'stillSuspended', 'constructorFailure', 'sourceFailure', 'analyserFailure']) {
    test(`successful media survives optional analysis failure with owned context retirement: ${failure}`, {skip: baseline}, async () => {
        const env = await setup({[failure]: true, contextState: 'suspended'});
        const peer = env.peer; await peer.ontrack(remoteEvent()); await flush();
        assert.equal(env.observations.played, 1);
        assert.equal(env.observations.cleanup, 0); assert.equal(env.observations.stopped, 0);
        assert.equal(peer.closed, false); assert.equal(env.api.state.callStarted, true);
        assert.equal(env.observations.notices.length, 0);
        assert.equal(env.rtc.audioContext == null, true);
        if (failure !== 'constructorFailure') assert.equal(env.observations.contexts[0].closes, 1);
        env.uiUtils.disconnectVoice(env.window, env.rtc);
        if (failure !== 'constructorFailure') assert.equal(env.observations.contexts[0].closes, 1);
    });
}
for (const failure of ['localFailure', 'remoteFailure', 'candidateFailure']) {
    test(`async signaling rejection is contained and closes current owned call: ${failure}`, {skip: baseline}, async () => {
        const env = await setup({[failure]: true}); const socket = env.socket;
        if (failure === 'candidateFailure') {
            await socket.onmessage(answer());
            await socket.onmessage({data: JSON.stringify({type: 'candidate', candidate: {candidate: 'synthetic'}})});
        } else await socket.onmessage(answer());
        await flush(); assert.equal(env.observations.cleanup, 1); assert.equal(env.observations.stopped, 1);
        assert.equal(env.observations.notices.length, 1);
        assert.equal(JSON.stringify(env.observations.notices).includes('sentinel'), false);
    });
}
test('offer creation rejection is contained without retry', {skip: baseline}, async () => {
    const env = await setup({offerFailure: true}); await flush();
    assert.equal(env.observations.cleanup, 1); assert.equal(env.observations.sockets.length, 1);
    assert.equal(env.observations.notices.length, 1);
});
test('translation failure still produces fixed safe notice', {skip: baseline}, async () => {
    const env = await setup({playFailure: true, translateFailure: true});
    await env.peer.ontrack(remoteEvent()); await flush();
    assert.equal(env.observations.notices.length, 1);
    assert.equal(JSON.stringify(env.observations.notices).includes('sentinel'), false);
});
test('old socket callback cannot damage a replacement call', {skip: baseline}, async () => {
    const env = await setup({remoteFailure: true});
    const old = env.socket; const replacement = {marker: true}; env.rtc.signalingWs = replacement;
    await old.onmessage(answer()); await flush();
    assert.equal(env.rtc.signalingWs, replacement); assert.equal(env.observations.cleanup, 0);
});
test('media playback starts even while resume waits; later completion cannot affect a newer call', {skip: baseline}, async () => {
    const wait = deferred(); const env = await setup({contextState: 'suspended', resumeWait: wait});
    const pending = env.peer.ontrack(remoteEvent());
    assert.equal(env.observations.played, 1);
    env.uiUtils.disconnectVoice(env.window, env.rtc);
    env.window.testVoiceUI.webrtc = {replacement: true}; wait.resolve(); await pending; await flush();
    assert.equal(env.observations.played, 1); assert.equal(env.observations.cleanup, 1);
});
test('successful media completes without waiting for optional resume; native cleanup owns pending context', {skip: baseline}, async () => {
    const wait = deferred(); const env = await setup({contextState: 'suspended', resumeWait: wait});
    const pending = env.peer.ontrack(remoteEvent());
    let deadline;
    const completed = await Promise.race([pending.then(() => true),
        new Promise(resolve => {deadline = setTimeout(() => resolve(false), 100);})]);
    clearTimeout(deadline); assert.equal(completed, true);
    assert.equal(env.observations.played, 1); assert.equal(env.observations.cleanup, 0);
    assert.equal(env.observations.notices.length, 0);
    assert.equal(env.rtc.audioContext, env.observations.contexts[0]);
    env.uiUtils.disconnectVoice(env.window, env.rtc);
    assert.equal(env.observations.contexts[0].closes, 1);
});
test('late optional analysis rejection cannot close a new call or double-close detached context', {skip: baseline}, async () => {
    let rejectResume;
    const wait = {promise: new Promise((resolve, reject) => {rejectResume = reject;})};
    const env = await setup({contextState: 'suspended', resumeWait: wait});
    const pending = env.peer.ontrack(remoteEvent()); await flush();
    env.uiUtils.disconnectVoice(env.window, env.rtc);
    const replacement = {audioContext: {marker: true}}; env.window.testVoiceUI.webrtc = replacement;
    rejectResume(new Error('private-analysis-sentinel')); await pending; await flush();
    assert.equal(env.observations.cleanup, 1); assert.equal(env.observations.contexts[0].closes, 1);
    assert.equal(env.observations.notices.length, 0); assert.equal(env.window.testVoiceUI.webrtc, replacement);
});
test('blocked playback closes the owned call even when analysis resume never settles', {skip: baseline}, async () => {
    const wait = deferred(); const env = await setup({contextState: 'suspended', resumeWait: wait, playFailure: true});
    await env.peer.ontrack(remoteEvent()); await flush();
    assert.equal(env.observations.cleanup, 1); assert.equal(env.observations.contexts[0].closes, 1);
    assert.equal(env.observations.notices.length, 1);
});
test('permission API fallback and explicit denial stay native', async () => {
    const env = await setup({permissionApiMissing: true}); assert.equal(env.observations.sockets.length, 1);
    const denied = await setup({permissionDenied: true}); assert.equal(denied.observations.sockets.length, 0);
    assert.equal(denied.api.state.callStarted, false);
});

test('failed WSS before a peer exists retires the owned call and matching cached token once', {skip: baseline}, async () => {
    const env = await setup({deferOpen: true}); const oldOpen = env.socket.onopen;
    await env.socket.onerror({message: 'private-wss-error-sentinel'}); await flush();
    assert.equal(env.observations.cleanup, 1); assert.equal(env.observations.stopped, 1);
    assert.equal(env.observations.peers.length, 0); assert.equal(env.api.state.callStarted, false);
    assert.equal(env.api.state.isConnectionInProgress, false); assert.equal(env.api.state.auth_token, '');
    assert.equal(env.observations.notices.length, 1); assert.equal(env.socket.closes, 1);
    assert.equal(JSON.stringify(env.observations.notices).includes('sentinel'), false);
    await oldOpen(); assert.equal(env.observations.peers.length, 0);
    assert.equal(env.observations.sockets.length, 1, 'failure cannot reconnect automatically');
});

test('early WSS close followed by error cleans once and permits a fresh login next time', {skip: baseline}, async () => {
    const env = await setup({deferOpen: true}), oldClose = env.socket.onclose, oldError = env.socket.onerror;
    oldClose({code: 1006, reason: 'private-close-sentinel'}); await oldError({message: 'late error'}); await flush();
    oldClose({code: 1006, reason: 'late close'}); await flush();
    assert.equal(env.observations.cleanup, 1); assert.equal(env.observations.stopped, 1);
    assert.equal(env.api.state.callStarted, false); assert.equal(env.api.state.auth_token, '');
    assert.equal(env.api.state.isConnectionInProgress, false); assert.equal(env.observations.notices.length, 1);
    assert.equal(env.observations.sockets.length, 1);
});

test('preconnection WSS failure closes its peer and timer without replaying its offer', {skip: baseline}, async () => {
    const env = await setup(), peer = env.peer; const sent = env.socket.sent.length;
    await env.socket.onerror({}); await flush();
    assert.equal(peer.closed, true); assert.equal(env.rtc.pc, null);
    assert.equal(env.observations.timers.every(timer => timer.cleared), true);
    assert.equal(env.api.state.auth_token, ''); assert.equal(env.observations.cleanup, 1);
    assert.equal(env.socket.sent.length, sent); assert.equal(env.observations.sockets.length, 1);
});

test('failed owned WSS preserves a newer cached login token', {skip: baseline}, async () => {
    const env = await setup({deferOpen: true}); env.api.state.auth_token = 'newer-login-credential';
    await env.socket.onerror({}); await flush();
    assert.equal(env.observations.cleanup, 1); assert.equal(env.api.state.callStarted, false);
    assert.equal(env.api.state.auth_token, 'newer-login-credential');
});

test('superseded socket failure callbacks cannot close the current socket or clear its token', {skip: baseline}, async () => {
    const env = await setup(), oldError = env.socket.onerror, oldClose = env.socket.onclose, peer = env.peer;
    const replacement = {closes: 0, close() {this.closes++;}}; env.rtc.signalingWs = replacement;
    env.api.state.auth_token = 'newer-socket-credential';
    await oldError({}); oldClose({code: 1006, reason: ''}); await flush();
    assert.equal(env.rtc.signalingWs, replacement); assert.equal(replacement.closes, 0);
    assert.equal(peer.closed, false); assert.equal(env.observations.cleanup, 0);
    assert.equal(env.api.state.callStarted, true); assert.equal(env.api.state.auth_token, 'newer-socket-credential');
    assert.equal(env.observations.notices.length, 0);
});

test('superseded call failure callbacks leave the current call and login state untouched', {skip: baseline}, async () => {
    const env = await setup(), oldError = env.socket.onerror, oldClose = env.socket.onclose;
    const replacement = {marker: true}; env.window.testVoiceUI.webrtc = replacement;
    env.api.state.auth_token = 'current-call-credential'; env.api.state.isConnectionInProgress = true;
    await oldError({}); oldClose({code: 1006, reason: ''}); await flush();
    assert.equal(env.window.testVoiceUI.webrtc, replacement); assert.equal(env.observations.cleanup, 0);
    assert.equal(env.api.state.auth_token, 'current-call-credential');
    assert.equal(env.api.state.callStarted, true); assert.equal(env.api.state.isConnectionInProgress, true);
    assert.equal(env.observations.notices.length, 0);
});

test('established WSS close and error preserve native normal-close behavior', {skip: baseline}, async () => {
    const env = await setup(); env.peer.iceConnectionState = 'connected';
    await env.peer.oniceconnectionstatechange(); assert.equal(env.rtc.isConnected, true);
    await env.socket.onerror({}); env.socket.onclose({code: 1000, reason: 'normal'}); await flush();
    assert.equal(env.observations.cleanup, 0); assert.equal(env.observations.stopped, 0);
    assert.equal(env.api.state.callStarted, true); assert.equal(env.api.state.auth_token, 'synthetic-credential');
    assert.equal(env.observations.notices.length, 0); assert.equal(env.observations.sockets.length, 1);
});
