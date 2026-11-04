'use strict';
// Offline candidate derivation only. This module never writes production files.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const ORIGINAL_SHA256 = '3a2d26bda389b2dc40311f8feff9e81a1ebeacae8c37200adf506146d3336183';
function derive(raw) {
    if (crypto.createHash('sha256').update(raw).digest('hex') !== ORIGINAL_SHA256)
        throw new Error('Original native script identity changed');
    let source = raw.toString('utf8');
    function replace(before, after) {
        if (source.split(before).length !== 2) throw new Error('Expected one exact edit anchor');
        source = source.replace(before, after);
    }
    replace('    let answerReceived = false;', `    let answerReceived = false;
    let voiceFailed = false;

    function failVoice(message) {
        if (voiceFailed || window.testVoiceUI.webrtc !== webrtc) return;
        voiceFailed = true;
        disconnect();
        // Detach before native cleanup; observe the close promise ourselves.
        const context = webrtc.audioContext;
        webrtc.audioContext = null;
        if (context && context.state !== 'closed') {
            Promise.resolve().then(() => context.close()).catch(() => {});
        }
        uiUtils.disconnectVoice(window, webrtc);
        api.setState("isConnectionInProgress", false);
        Promise.resolve().then(() => helpers.translate(message)).catch(() => message)
            .then(value => api.emit('NOW_UXF_PAGE#ADD_NOTIFICATIONS', {
                items: [{ id: 'auth_request_failure', status: 'critical',
                    icon: 'exclamation-triangle-outline',
                    content: { type: 'html', value }, action: { type: 'dismiss' } }]
            })).catch(() => {});
    }

    function iceIsReady() {
        return webrtc.pc && (webrtc.pc.iceConnectionState === 'connected'
            || webrtc.pc.iceConnectionState === 'completed');
    }

    function markIceReady() {
        const firstConnection = !webrtc.isConnected;
        webrtc.isConnected = true;
        helpers.timing.clearTimeout(iceTimeoutId);
        iceTimeoutId = null;
        if (firstConnection) uiUtils.startCallTimer();
        api.setState("isConnectionInProgress", false);
    }`);
    replace('        webrtc.pc = new window.RTCPeerConnection();', `        webrtc.pc = new window.RTCPeerConnection();
        const peer = webrtc.pc;`);
    replace("            if (!webrtc.isConnected && webrtc.pc && webrtc.pc.iceConnectionState !== 'connected') {", `            if (voiceFailed || webrtc.pc !== peer || window.testVoiceUI.webrtc !== webrtc) return;
            if (iceIsReady()) {
                markIceReady();
                return;
            }
            if (!webrtc.isConnected && webrtc.pc) {`);
    replace(`            if (webrtc.pc.iceConnectionState === 'connected') {
                webrtc.isConnected = true;
                helpers.timing.clearTimeout(iceTimeoutId);
                iceTimeoutId = null;
                uiUtils.startCallTimer();
                api.setState("isConnectionInProgress", false);`, `            if (voiceFailed || webrtc.pc !== peer || window.testVoiceUI.webrtc !== webrtc) return;
            if (iceIsReady()) {
                markIceReady();`);
    replace('        webrtc.pc.ontrack = (event) => {', '        webrtc.pc.ontrack = async (event) => {');
    replace('            if (event.streams && event.streams.length > 0) {', `            const hasStream = event.streams && event.streams.length > 0;
            const bareLiveAudio = !hasStream && event.track && event.track.kind === 'audio'
                && event.track.readyState === 'live';
            if (hasStream || bareLiveAudio) {`);
    replace(`                var audio = window.document.getElementById("webrtc-audio");
                audio.srcObject = event.streams[0];

                // Close previous AudioContext if any
                if (webrtc.audioContext) {
                    webrtc.audioContext.close();
                }

                const audioContext = new (window.AudioContext || window.webkitAudioContext)();
                const source = audioContext.createMediaStreamSource(event.streams[0]);
                const analyser = audioContext.createAnalyser();
                analyser.fftSize = 256;
                source.connect(analyser);
                audio.play();`, `                if (voiceFailed || webrtc.pc !== peer || window.testVoiceUI.webrtc !== webrtc) return;
                try {
                    const audio = window.document.getElementById("webrtc-audio");
                    if (!audio) throw new Error('Audio element unavailable');
                    const remoteStream = hasStream ? event.streams[0] : new window.MediaStream([event.track]);
                    audio.srcObject = remoteStream;
                    // Required media playback is independent of the optional analysis graph.
                    const playback = (async () => audio.play())();
                    let audioContext;
                    function retireAnalysis() {
                        if (!audioContext || webrtc.audioContext !== audioContext) return;
                        webrtc.audioContext = null;
                        if (audioContext.state !== 'closed') {
                            Promise.resolve().then(() => audioContext.close()).catch(() => {});
                        }
                    }
                    try {
                        // Store ownership before graph setup; native cleanup owns pending resume too.
                        audioContext = webrtc.audioContext;
                        if (!audioContext || audioContext.state === 'closed') {
                            audioContext = new (window.AudioContext || window.webkitAudioContext)();
                            webrtc.audioContext = audioContext;
                        }
                        const source = audioContext.createMediaStreamSource(remoteStream);
                        const analyser = audioContext.createAnalyser();
                        analyser.fftSize = 256;
                        source.connect(analyser);
                        if (audioContext.state === 'suspended') {
                            // Observe separately: optional resume must never gate or delay media.
                            (async () => audioContext.resume())().then(() => {
                                if (voiceFailed || webrtc.pc !== peer || window.testVoiceUI.webrtc !== webrtc
                                        || audioContext.state !== 'running') retireAnalysis();
                            }, retireAnalysis);
                        } else if (audioContext.state !== 'running') {
                            retireAnalysis();
                        }
                    } catch (error) {
                        retireAnalysis();
                    }
                    await playback;
                } catch (error) {
                    if (webrtc.pc === peer && window.testVoiceUI.webrtc === webrtc) {
                        failVoice("Voice audio playback could not start. Check browser audio permissions and start a new call.");
                    }
                }`);
    replace(`        webrtc.signalingWs.onopen = async () => {`, `        const socket = webrtc.signalingWs;
        function failBeforeConnection() {
            if (voiceFailed || webrtc.isConnected || webrtc.signalingWs !== socket
                    || window.testVoiceUI.webrtc !== webrtc) return;
            if (api.state.auth_token === webrtc.token) api.setState("auth_token", "");
            failVoice("Voice signaling could not complete. Start a new call.");
        }
        webrtc.signalingWs.onopen = async () => {`);
    replace(`            setupPeerConnection();
            await createAndSendOffer();`, `            if (voiceFailed || webrtc.signalingWs !== socket || window.testVoiceUI.webrtc !== webrtc) return;
            try {
                setupPeerConnection();
                await createAndSendOffer();
            } catch (error) {
                if (webrtc.signalingWs === socket) {
                    failVoice("Voice signaling could not complete. Start a new call.");
                }
            }`);
    replace('        webrtc.signalingWs.onmessage = (event) => {', '        webrtc.signalingWs.onmessage = async (event) => {');
    replace(`            try {
                const message = JSON.parse(event.data);
                handleSignalingMessage(message);
            } catch (e) {
                if (webrtc.debug)
                    console.log(\x60[Signaling WS] Non-JSON message: \x24{event.data}\x60);
            }`, `            if (voiceFailed || webrtc.signalingWs !== socket || window.testVoiceUI.webrtc !== webrtc) return;
            try {
                const message = JSON.parse(event.data);
                await handleSignalingMessage(message);
            } catch (error) {
                if (webrtc.signalingWs === socket) {
                    failVoice("Voice signaling could not complete. Start a new call.");
                }
            }`);
    replace(`            if (!webrtc.isConnected) {
                api.setState("isConnectionInProgress", false);
                api.emit('NOW_UXF_PAGE#ADD_NOTIFICATIONS', {
                    items: [{
                        id: 'auth_request_failure',
                        status: 'critical',
                        icon: 'exclamation-triangle-outline',
                        content: {
                            type: "html",
                            value: await helpers.translate("Signaling WebSocket error occurred: connection failed.")
                        },
                        action: {
                            type: 'dismiss'
                        }
                    }]
                });
            }`, `            failBeforeConnection();`);
    replace(`                console.log(\x60Signaling WebSocket closed: \x24{event.code} \x24{event.reason}\x60);
        };`, `                console.log(\x60Signaling WebSocket closed: \x24{event.code} \x24{event.reason}\x60);
            failBeforeConnection();
        };`);
    replace('    function failVoice(message) {', `    function currentStart() {
        return !voiceFailed && !webrtc.sccStartCancelled
            && window.testVoiceUI.webrtc === webrtc;
    }

    function failVoice(message) {`);
    replace(`            .then(value => api.emit('NOW_UXF_PAGE#ADD_NOTIFICATIONS', {
                items: [{ id: 'auth_request_failure', status: 'critical',
                    icon: 'exclamation-triangle-outline',
                    content: { type: 'html', value }, action: { type: 'dismiss' } }]
            })).catch(() => {});`, `            .then(value => {
                if (window.testVoiceUI.webrtc !== webrtc) return;
                return api.emit('NOW_UXF_PAGE#ADD_NOTIFICATIONS', {
                    items: [{ id: 'auth_request_failure', status: 'critical',
                        icon: 'exclamation-triangle-outline',
                        content: { type: 'html', value }, action: { type: 'dismiss' } }]
                });
            }).catch(() => {});`);
    const permissionStart = source.indexOf('    // Pre-check microphone permission');
    const permissionEnd = source.indexOf('    function setupPeerConnection()');
    if (permissionStart < 0 || permissionEnd <= permissionStart) throw new Error('Native media block changed');
    replace(source.slice(permissionStart, permissionEnd), `    // Permission and media acquisition may settle after another Start owns the UI.
    try {
        const permResult = await window.navigator.permissions.query({ name: 'microphone' });
        if (!currentStart()) return;
        if (permResult.state === 'denied') {
            failVoice("Microphone access is blocked by browser permissions.");
            return;
        }
    } catch (permErr) {
        // Permissions API not supported — proceed to getUserMedia.
    }
    if (!currentStart()) return;

    try {
        const localStream = await window.navigator.mediaDevices.getUserMedia({
            audio: {
                echoCancellation: true,
                noiseSuppression: true,
                autoGainControl: true
            },
            video: false
        });
        if (!currentStart()) {
            localStream.getTracks().forEach(track => track.stop());
            return;
        }
        webrtc.localStream = localStream;
    } catch (mediaErr) {
        if (!currentStart()) return;
        if (mediaErr.name === 'NotAllowedError')
            failVoice("Microphone permission was denied. Please allow microphone access and try again.");
        else if (mediaErr.name === 'NotFoundError')
            failVoice("No microphone found. Please connect a microphone and try again.");
        else
            failVoice("Microphone error. Please check your device and try again.");
        return;
    }

    const audioTracks = webrtc.localStream.getAudioTracks();
    if (audioTracks.length === 0 || audioTracks[0].readyState !== 'live') {
        failVoice("Microphone stream is not active. Please reset audio permissions and refresh the page.");
        return;
    }

`);
    replace(`    function connectSignalingWebSocket() {
        answerReceived = false;`, `    function connectSignalingWebSocket() {
        if (!currentStart()) return;
        answerReceived = false;`);
    replace('    window.testVoiceUI.webrtc = webrtc;', `    window.testVoiceUI.webrtc = webrtc;
    api.setState("isConnectionInProgress", true);`);
    replace(`            if (voiceFailed || webrtc.isConnected || webrtc.signalingWs !== socket
                    || window.testVoiceUI.webrtc !== webrtc) return;`, `            if (!currentStart() || webrtc.isConnected || webrtc.signalingWs !== socket) return;`);
    replace('        webrtc.signalingWs = new window.WebSocket(wsUrl);', `        try {
            webrtc.signalingWs = new window.WebSocket(wsUrl);
        } catch (error) {
            failVoice("Voice signaling could not complete. Start a new call.");
            return;
        }`);
    replace('        "signalingWs": null', `        "signalingWs": null,
        "sccIceDisconnectTimeoutId": null`);
    replace('    function markIceReady() {', `    function cancelIceRecovery() {
        if (webrtc.sccIceDisconnectTimeoutId !== null) {
            helpers.timing.clearTimeout(webrtc.sccIceDisconnectTimeoutId);
            webrtc.sccIceDisconnectTimeoutId = null;
        }
    }

    function markIceReady() {
        cancelIceRecovery();`);
    replace(`            } else if (webrtc.pc.iceConnectionState === 'disconnected' || webrtc.pc.iceConnectionState === 'failed') {`,
        `            } else if (webrtc.pc.iceConnectionState === 'disconnected' && webrtc.isConnected) {
                if (webrtc.sccIceDisconnectTimeoutId === null) {
                    const recovery = helpers.timing.setTimeout(() => {
                        if (!currentStart() || webrtc.pc !== peer
                                || webrtc.sccIceDisconnectTimeoutId !== recovery) return;
                        webrtc.sccIceDisconnectTimeoutId = null;
                        if (!iceIsReady()) {
                            failVoice("Voice connection was lost. Start a new call.");
                        }
                    }, 10000);
                    webrtc.sccIceDisconnectTimeoutId = recovery;
                }
            } else if (webrtc.pc.iceConnectionState === 'failed') {
                failVoice("Voice connection was lost. Start a new call.");
            } else if (webrtc.pc.iceConnectionState === 'disconnected') {`);
    replace('    function disconnect() {', `    function disconnect() {
        cancelIceRecovery();`);
    return source;
}
module.exports = { derive, ORIGINAL_SHA256 };
if (require.main === module) {
    const source = derive(fs.readFileSync(path.join(__dirname, 'Start-voice-session.original.js')));
    fs.writeFileSync(path.join(__dirname, 'Start-voice-session.candidate.js'), source, {flag: 'wx'});
}
