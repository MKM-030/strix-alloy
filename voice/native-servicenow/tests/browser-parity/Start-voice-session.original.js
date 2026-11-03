/**
 * @param {params} params
 * @param {api} params.api
 * @param {any} params.event
 * @param {any} params.imports
 * @param {ApiHelpers} params.helpers
 */
async function handler({ api, event, helpers, imports }) {
    const uiUtils = imports["sn_nowassist_va.VoiceTestingUIUtils"](api, helpers);
    const { NowDateTime } = imports['sn_uxf.core_libraries']();
    const window = uiUtils.getWindowObject();

    // Close any existing WebRTC connection before creating a new one
    const oldWebrtc = window.testVoiceUI.webrtc;
    if (oldWebrtc) {
        uiUtils.disconnectVoice(window, oldWebrtc);
    }

    const webrtc = {
        "debug": false,
        "isConnected": false,
        "pc": null,
        "pendingCandidates": [],
        "localStream": null,
        "processedCandidates": new Set(),
        "token": api.state.auth_token,
        "signalingWs": null
    };
    const messages = [];
    const MAX_ICE_RETRIES = 2;
    let iceRetryCount = 0;
    let iceTimeoutId = null;
    let answerReceived = false;
    const remoteCandidateQueue = [];
    window.testVoiceUI.webrtc = webrtc;
    api.setState("callStarted", true);
    api.setState("timer", "-");
    api.setState("timerIntervalId", 0);
    api.setState("messages", []);
    const repeaterItems = api.state.repeaterItems;
    repeaterItems.length = 0;
    api.setState("sequenceAgentMap", {});

    // Pre-check microphone permission
    try {
        const permResult = await window.navigator.permissions.query({ name: 'microphone' });
        if (permResult.state === 'denied') {
            api.emit('NOW_UXF_PAGE#ADD_NOTIFICATIONS', {
                items: [{
                    id: 'auth_request_failure',
                    status: 'critical',
                    icon: 'exclamation-triangle-outline',
                    content: {
                        type: "html",
                        value: await helpers.translate("Microphone access is blocked by browser permissions.")
                    },
                    action: {
                        type: 'dismiss'
                    }
                }]
            });
            api.setState("callStarted", false);
            return;
        }
    } catch (permErr) {
        // Permissions API not supported — proceed to getUserMedia
    }

    try {
        webrtc.localStream = await window.navigator.mediaDevices.getUserMedia({
            audio: {
                echoCancellation: true,
                noiseSuppression: true,
                autoGainControl: true
            },
            video: false
        });
    } catch (mediaErr) {
        let error;
        api.setState("callStarted", false);
        if (mediaErr.name === 'NotAllowedError')
            error = await helpers.translate("Microphone permission was denied. Please allow microphone access and try again.");
        else if (mediaErr.name === 'NotFoundError')
            error = await helpers.translate("No microphone found. Please connect a microphone and try again.");
        else
            error = await helpers.translate("Microphone error. Please check your device and try again.");

        api.emit('NOW_UXF_PAGE#ADD_NOTIFICATIONS', {
            items: [{
                id: 'auth_request_failure',
                status: 'critical',
                icon: 'exclamation-triangle-outline',
                content: {
                    type: "html",
                    value: error
                },
                action: {
                    type: 'dismiss'
                }
            }]
        });
        return;
    }

    // Validate stream has active audio tracks
    const audioTracks = webrtc.localStream.getAudioTracks();
    if (audioTracks.length === 0 || audioTracks[0].readyState !== 'live') {
        api.emit('NOW_UXF_PAGE#ADD_NOTIFICATIONS', {
            items: [{
                id: 'auth_request_failure',
                status: 'critical',
                icon: 'exclamation-triangle-outline',
                content: {
                    type: "html",
                    value: await helpers.translate("Microphone stream is not active. Please reset audio permissions and refresh the page.")
                },
                action: {
                    type: 'dismiss'
                }
            }]
        });
        return;
    }

    function setupPeerConnection() {
        if (webrtc.debug)
            console.log(`Setting up peer connection. (retry: ${iceRetryCount})`);

        // Close existing PC if retrying
        if (webrtc.pc) {
            webrtc.pc.onicecandidate = null;
            webrtc.pc.oniceconnectionstatechange = null;
            webrtc.pc.onicecandidateerror = null;
            webrtc.pc.ontrack = null;
            webrtc.pc.close();
        }
        webrtc.isConnected = false;
        webrtc.pendingCandidates = [];
        webrtc.processedCandidates = new Set();

        // Create peer connection without ICE servers — they arrive with the answer
        webrtc.pc = new window.RTCPeerConnection();

        webrtc.localStream.getTracks().forEach(track => {
            webrtc.pc.addTrack(track, webrtc.localStream);
        });

        // Handle ICE candidates — send via WebSocket
        webrtc.pc.onicecandidate = (event) => {
            if (event.candidate) {
                if (webrtc.signalingWs && webrtc.signalingWs.readyState === window.WebSocket.OPEN) {
                    webrtc.signalingWs.send(JSON.stringify({
                        type: "candidate",
                        candidate: {
                            candidate: event.candidate.candidate,
                            sdpMLineIndex: event.candidate.sdpMLineIndex,
                            sdpMid: event.candidate.sdpMid
                        }
                    }));
                }
            } else {
                if (webrtc.debug)
                    console.log('ICE gathering finished.');
            }
        };

        // ICE connection timeout — detect silent failures (e.g. stale permissions)
        const ICE_TIMEOUT_MS = 15000;
        if (iceTimeoutId) {
            helpers.timing.clearTimeout(iceTimeoutId);
        }
        iceTimeoutId = helpers.timing.setTimeout(async () => {
            if (!webrtc.isConnected && webrtc.pc && webrtc.pc.iceConnectionState !== 'connected') {
                if (iceRetryCount < MAX_ICE_RETRIES) {
                    iceRetryCount++;
                    if (webrtc.debug)
                        console.warn(`[Voice] ICE connection timed out (state: ${webrtc.pc.iceConnectionState}). Retry ${iceRetryCount}/${MAX_ICE_RETRIES}...`);
                    connectSignalingWebSocket();
                } else {
                    api.emit('NOW_UXF_PAGE#ADD_NOTIFICATIONS', {
                        items: [{
                            id: 'auth_request_failure',
                            status: 'critical',
                            icon: 'exclamation-triangle-outline',
                            content: {
                                type: "html",
                                value: await helpers.translate("Connection timed out. Please check your microphone permissions and network, then try again.")
                            },
                            action: {
                                type: 'dismiss'
                            }
                        }]
                    });
                    api.setState("isConnectionInProgress", false);
                    disconnect();
                }
            }
        }, ICE_TIMEOUT_MS);

        // Handle connection state changes
        webrtc.pc.oniceconnectionstatechange = () => {
            if (webrtc.debug)
                console.log(`ICE Connection State: ${webrtc.pc.iceConnectionState}`);

            if (webrtc.pc.iceConnectionState === 'connected') {
                webrtc.isConnected = true;
                helpers.timing.clearTimeout(iceTimeoutId);
                iceTimeoutId = null;
                uiUtils.startCallTimer();
                api.setState("isConnectionInProgress", false);
            } else if (webrtc.pc.iceConnectionState === 'disconnected' || webrtc.pc.iceConnectionState === 'failed') {
                helpers.timing.clearTimeout(iceTimeoutId);
                iceTimeoutId = null;
                api.setState("isConnectionInProgress", false);
                disconnect();
            }
        };

        webrtc.pc.onicecandidateerror = (event) => {
            if (webrtc.debug) {
                console.error(`ICE Candidate Error: ${event.errorText || 'Unknown error'}`);
                console.log(`   Error Code: ${event.errorCode}`);
                console.log(`   URL: ${event.url || 'N/A'}`);
                console.log(`   Host Candidate: ${event.hostCandidate || 'N/A'}`);
            }
        };

        // Handle incoming audio (from server)
        webrtc.pc.ontrack = (event) => {
            if (webrtc.debug) {
                console.log("ontrack event fired!");
                console.log(`   Track kind: ${event.track.kind}`);
                console.log(`   Track id: ${event.track.id}`);
                console.log(`   Track label: ${event.track.label}`);
                console.log(`   Streams: ${event.streams.map(s => s.id).join(',')}`);
                console.log(`   Track readyState: ${event.track.readyState}`);
            }

            if (event.streams && event.streams.length > 0) {
                var audio = window.document.getElementById("webrtc-audio");
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
                audio.play();
            } else {
                if (webrtc.debug)
                    console.error('No streams in ontrack event!');
            }
        };

        const dataChannel = webrtc.pc.createDataChannel("transcripts");

        dataChannel.onopen = (event) => {
            if (webrtc.debug)
                console.log('Data channel opened');
        };

        dataChannel.onmessage = (event) => {
            const parsedData = JSON.parse(event.data);
            const tStamp = event?.unix_timestamp_ms || +new Date();
            uiUtils.handleDataChannelMessage(parsedData, messages, event?.unix_timestamp_ms, webrtc);
            uiUtils.updateVoiceAnalysisTabData(event, parsedData, tStamp, webrtc);
        };

        dataChannel.onclose = () => {
            if (webrtc.debug)
                console.log('Data channel closed');
        };

        dataChannel.onerror = (error) => {
            if (webrtc.debug)
                console.log(`Data channel error: ${error}`);
        };
    }

    async function createAndSendOffer() {
        const offer = await webrtc.pc.createOffer();

        // Defer setLocalDescription — ICE gathering must not start until TURN is configured.
        // The offer is stored and committed after iceServers arrive with the answer.
        webrtc.pendingOffer = offer;

        if (webrtc.debug)
            console.log("Created offer (local description deferred, waiting for ICE servers)");

        // Send the offer via WebSocket — sdp must be a nested { type, sdp } object
        if (webrtc.signalingWs && webrtc.signalingWs.readyState === window.WebSocket.OPEN) {
            webrtc.signalingWs.send(JSON.stringify({
                type: "offer",
                sdp: { type: offer.type, sdp: offer.sdp },
                client_timestamp: Date.now()
            }));
        }
    }

    async function handleSignalingMessage(message) {
        if (webrtc.debug)
            console.log(`[Signaling WS] Received: ${message.type}`);

        switch (message.type) {
            case "answer": {
                // Update ICE configuration with TURN servers if provided
                if (message.iceServers && message.iceServers.length > 0) {
                    const iceConfig = {
                        iceServers: message.iceServers.map(server => {
                            const isTurnServer = server.urls && server.urls.some(url =>
                                url.startsWith('turn:') || url.startsWith('turns:')
                            );
                            if (isTurnServer) {                                
                                if (webrtc.debug) {
                                    console.log("[TURN Config] Server-provided TURN server:");
                                    console.log(`  URLs: ${JSON.stringify(server.urls)}`);
                                }
                                //User credentials provided by gateway
                                return {
                                    urls: server.urls,
                                    username: server.username,
                                    credential: server.credential
                                };
                            }
                            return { urls: server.urls };
                        })
                    };
                    webrtc.pc.setConfiguration(iceConfig);
                    if (webrtc.debug)
                        console.log(`ICE Configuration updated: ${JSON.stringify(iceConfig)}`);
                }

                // Commit the deferred local description — ICE gathering starts NOW with TURN configured
                if (webrtc.pendingOffer) {
                    if (webrtc.debug)
                        console.log("Committing deferred local description (ICE gathering starts now)");
                    await webrtc.pc.setLocalDescription(webrtc.pendingOffer);
                    webrtc.pendingOffer = null;
                }

                // Handle both formats: nested { type, sdp } or direct string
                const sdpString = typeof message.sdp === "string" ? message.sdp : message.sdp?.sdp;
                await webrtc.pc.setRemoteDescription(new window.RTCSessionDescription({
                    type: "answer",
                    sdp: sdpString
                }));
                answerReceived = true;
                if (webrtc.debug)
                    console.log("Remote description set");

                // Flush queued remote candidates
                if (remoteCandidateQueue.length > 0) {
                    if (webrtc.debug)
                        console.log(`Processing ${remoteCandidateQueue.length} queued remote candidate(s)`);
                    for (const c of remoteCandidateQueue) {
                        try {
                            await webrtc.pc.addIceCandidate(new window.RTCIceCandidate(c));
                        } catch (e) {
                            if (webrtc.debug)
                                console.warn(`Failed to add queued candidate: ${e}`);
                        }
                    }
                    remoteCandidateQueue.length = 0;
                }

                // Send any pending local ICE candidates
                for (const candidate of webrtc.pendingCandidates) {
                    webrtc.signalingWs.send(JSON.stringify({
                        type: "candidate",
                        candidate: {
                            candidate: candidate.candidate,
                            sdpMLineIndex: candidate.sdpMLineIndex,
                            sdpMid: candidate.sdpMid
                        }
                    }));
                }
                webrtc.pendingCandidates = [];
                break;
            }

            case "candidate": {
                // Remote ICE candidate from the server
                if (!answerReceived) {
                    // Queue candidates that arrive before setRemoteDescription completes
                    remoteCandidateQueue.push(message.candidate);
                    if (webrtc.debug)
                        console.log(`[Signaling WS] Queued remote candidate (${remoteCandidateQueue.length} pending)`);
                } else if (message.candidate) {
                    await webrtc.pc.addIceCandidate(new window.RTCIceCandidate(message.candidate));
                }
                break;
            }

            default:
                if (webrtc.debug)
                    console.log(`[Signaling WS] Unknown message type: ${message.type}`);
                break;
        }
    }

    function disconnect() {
        if (iceTimeoutId) {
            helpers.timing.clearTimeout(iceTimeoutId);
            iceTimeoutId = null;
        }
        // Close signaling WebSocket — server cleans up the session on WS close
        if (webrtc.signalingWs) {
            webrtc.signalingWs.close();
            webrtc.signalingWs = null;
        }
    }

    function connectSignalingWebSocket() {
        answerReceived = false;
        remoteCandidateQueue.length = 0;
        // Close existing WebSocket if any
        if (webrtc.signalingWs) {
            webrtc.signalingWs.onclose = null;
            webrtc.signalingWs.close();
            webrtc.signalingWs = null;
        }

        // Build WebSocket URL for WebRTC signaling
        const orchestratorHost = api.data.assistant_config_attributes.output.orchestratorUrl.split("//")[1];
        const oauthToken = api.state.auth_token;
        const instanceName = api.state.instanceName;
        const voiceServiceId = api.context.props.voiceAssistantId;
        const voiceServiceLanguage = api.data.assistant_config_attributes.output.attrs.language;

        const params = new window.URLSearchParams({
            instance_name: instanceName,
            voice_service_id: voiceServiceId,
            voice_service_language: voiceServiceLanguage,
            receive_data: "true",
            data_channel: "true",
            diagnostics: "admin",
            client_app: "admin_test"
        });
        if (oauthToken) {
            params.set("auth_token", oauthToken);
        }

        const wsUrl = `wss://${orchestratorHost}/webrtc/connect/agent_operator?${params.toString()}`;
        if (webrtc.debug)
            console.log(`Signaling WebSocket URL: ${wsUrl}`);
        webrtc.signalingWs = new window.WebSocket(wsUrl);

        webrtc.signalingWs.onopen = async () => {
            if (webrtc.debug)
                console.log("Signaling WebSocket connected");

            // Create peer connection and send offer
            setupPeerConnection();
            await createAndSendOffer();
        };

        webrtc.signalingWs.onmessage = (event) => {
            if (webrtc.debug)
                console.log(`[Signaling WS] Raw message: ${event.data}`);
            try {
                const message = JSON.parse(event.data);
                handleSignalingMessage(message);
            } catch (e) {
                if (webrtc.debug)
                    console.log(`[Signaling WS] Non-JSON message: ${event.data}`);
            }
        };

        webrtc.signalingWs.onerror = async (error) => {
            if (webrtc.debug)
                console.error(`Signaling WebSocket error: ${error.message || "Connection failed"}`);
            if (!webrtc.isConnected) {
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
            }
        };

        webrtc.signalingWs.onclose = (event) => {
            if (webrtc.debug)
                console.log(`Signaling WebSocket closed: ${event.code} ${event.reason}`);
        };
    }

    // Start the connection
    connectSignalingWebSocket();
}