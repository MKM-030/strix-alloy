    function disconnectVoice(window, webrtc) {
        // Send disconnect signal then close signaling WebSocket
        if (webrtc.signalingWs) {
            if (webrtc.signalingWs.readyState === window.WebSocket.OPEN) {
                try {
                    webrtc.signalingWs.send(JSON.stringify({ type: "disconnect" }));
                } catch (e) { /* ignore send errors during teardown */ }
            }
            webrtc.signalingWs.close();
            webrtc.signalingWs = null;
        }
        helpers.timing.clearInterval(api.state.timerIntervalId);

        if (webrtc.localStream) {
            webrtc.localStream.getTracks().forEach(track => track.stop());
            webrtc.localStream = null;
        }
        if (webrtc.pc) {
            webrtc.pc.onicecandidate = null;
            webrtc.pc.oniceconnectionstatechange = null;
            webrtc.pc.onicecandidateerror = null;
            webrtc.pc.ontrack = null;
            webrtc.pc.close();
            webrtc.pc = null;
        }
        if (webrtc.audioContext) {
            webrtc.audioContext.close();
            webrtc.audioContext = null;
        }
        webrtc.isConnected = false;

        var audio = window.document.getElementById("webrtc-audio");
        if (audio) {
            audio.srcObject = null;
        }

        api.setState("callStarted", false);
        api.setState("activeInteractionId", "");
        api.setState("timer", "-");
        api.setState("timerIntervalId", 0);

        markAnalysisComplete();
    }

