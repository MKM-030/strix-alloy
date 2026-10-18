# Android Now SDK 2.26.0 static voice contract evidence

Scope: supplied android-nowSdk-2.26.0-release.zip, read-only class analysis. No SDK execution, installation, download, or live-service access. Existing OpenJDK javap was invoked as `java -m jdk.jdeps/com.sun.tools.javap.Main`. Extraction selected only the two classes.jar files and voice class members into this directory after absolute/traversal/member-size checks; bytes were written as regular files, not archive-mode extraction. Source hashes and bounded constant-pool inventory are in source-evidence.json.

## Endpoint identity

The exact literal `/api/webrtc/sessions` exists in `nowsdk/libs/nowsdk.aar` → `classes.jar` → `com/servicenow/voice/network/WebRtcHttpApi.class`, companion, and `WebRtcHttpClient$createSession$2.class`. The implementation is in the main AAR; nowsdk-voice.aar holds its configuration adapter. This proves the supplied SDK targets the observed endpoint path. It does not alone prove the phone runs these exact archive bytes.

## Create request

`WebRtcHttpClient$createSession$2.invokeSuspend` uses original configured scheme and host (40–58), path `/api/webrtc/sessions` (61), query `instance_name` (74–80), `receive_data=true` (83–87), and only if nonnull `voice_service_id` (103–128). It sends POST (320–324), header `Authorization: Bearer <token>` (301–310 plus verbose BootstrapMethods #219), header `Content-Type: application/json` (313–317), and body `{"agent_id":"agent_operator"}` (167–176). A null auth token throws IOException before HTTP (263–289). SDK emission behavior does not establish server-side acceptance of unknown keys or malformed requests.

`NowVoiceConfigurationsKt.toVoiceConnectionConfiguration` obtains instance_name from instanceUrl by substringAfter("://"), substringBefore("/"), substringBefore(".") (private helper offsets 1–25). For a normal ServiceNow host this is its first DNS label. Exception fallback is "unknown". The voice_service_id is passed unchanged from NowVoiceEndpoint.voiceServiceId (22–26). `NowVoiceService.fetchAvailableConfigurations` reads Settings.voice.configurations entries' `voiceServiceId`, `voiceWebhookURL`, `mobileChannelType`, and `mobileChannelId`; all four must be nonblank (310–419) to produce a standard endpoint. There is no evidenced assistant/VoiceAgent ID translation. ConnectionConfiguration derives scheme and host from voiceWebhookURL, defaulting scheme to https and falling back host to the provided string if Uri host is absent.

## Create response

`createSession$2.invokeSuspend` offsets 402–417 calls default Gson.fromJson(responseString, SessionResponse.class), directly at top level. SessionResponse verbose field annotations prove these exact keys:

| Wire key | Model type | Declared nullability |
|---|---|---|
| session_id | string | nonnull |
| agent_id | string | nonnull |
| created_at | string | nonnull |
| iceServers | list of IceServerConfig | nonnull |
| endpoint_url | string | nullable, default null |

Gson's deserialization behavior should not be confused with constructor-level validation. No timestamp format or identifier format is established by these types. Each IceServerConfig uses exact Gson keys `urls` (list<string>, nonnull), `username` (nullable string), and `credential` (nullable string).

If endpoint_url is nonnull, createSession stores it as dynamicEndpointUrl (422–450). Subsequent offer, candidate, poll, and delete use only its parsed scheme and host; they rebuild canonical endpoint paths. Dynamic path/query/nondefault port are not propagated. Invalid parsed scheme falls back to original scheme; an unparsed host falls back to the entire endpoint_url string. For any returned ICE server whose URLs contain case-sensitive substring `turn`, SDK overrides its username with `{instanceName}:{serviceId}:{oauthToken}` (serviceId empty if null) and credential with literal `oauth` (642–722), preserving URLs; other servers are unchanged.

## HTTP signaling wire

Every operation below fetches the same cached/provider Bearer token; none includes create's query arguments. POST operations include Content-Type application/json.

| Operation | Exact wire request | Exact response consumed |
|---|---|---|
| Offer | POST /api/webrtc/sessions/{id}/offer; flat JSON `{"type":offerType,"sdp":offerSdp}` | **Nested** top-level `sdp` object: `{"sdp":{"type":"answer","sdp":"..."}}`; parser calls getJSONObject("sdp"), then inner getString("type") and getString("sdp") |
| Local ICE | POST /api/webrtc/sessions/{id}/candidate; `{"candidate":string,"sdpMid":string,"sdpMLineIndex":int}` | Successful body ignored |
| Remote ICE | GET /api/webrtc/sessions/{id}/candidates | top-level `candidates` array containing exact candidate/sdpMid/sdpMLineIndex keys; absent/nonarray becomes empty list |
| End | DELETE /api/webrtc/sessions/{id}; no body | Successful body ignored |

Evidence: `WebRtcHttpClient$sendOffer$2.invokeSuspend` request 147–163 and response 385–456; `sendCandidate$2` body 153–179; `getIceCandidates$2` parser 268–374; `deleteSession$2` request builder 177–205.

## Authentication, cookies, cleanup

WebRtcHttpClient caches VoiceAuthTokenProvider.getToken() result. HTTP401 is represented as a null result; executeRequestWithRetry performs exactly one refreshToken() call and replays the same request with replaced Authorization header. Another401 or no refreshed token yields IOException. All other unsuccessful HTTP status codes also throw IOException. A404 for candidate POST or session DELETE only suppresses telemetry; it is still an error. Status-body error schemas are not parsed. Successful null response body is treated as empty string.

The SDK CookieJar saves response cookies (replaces previous list) and returns the full stored list for later requests. Preserve Set-Cookie/Cookie behavior when implementing a compatible route. onCleared clears cachedAuthToken, cookieStore and dynamicEndpointUrl. OkHttp configured connect timeout60s, read/write30s.

There are no WebSocket/wss/ws or ticket UTF8 constants in all315 main-AAR voice classes and33 voice-AAR classes checked. The concrete SDK path is HTTP signaling plus WebRTC media/data; no native ticket field or WSS message schema can be claimed from this archive. Server implementation is unavailable, so server ticket expiry, admission status codes, allowed origins, acceptance strictness, identifier formats, and external platform mappings remain unproven.

## Peer/data-channel lifecycle (additional static findings)

Transport disassemblies are in subagent-transport/. `ConnectionController$connect$1.invokeSuspend` sets CONNECTING, cleans prior peer, invokes connectToSignalingServer, setupPeerConnection, createAndSendOffer, then starts ICE polling (offsets93–186). connectToSignalingServer independently rejects blank webhookURL/voiceServiceId/instanceName before createSession, stores sessionId and iceServers, and sets signaling CONNECTED. Thus nullable low-level voice_service_id argument is not used by the standard controller path.

Peer setup: UNIFIED_PLAN, GATHER_CONTINUALLY, ICE transports ALL; local audio track with stream ID local_stream. Offer constraints OfferToReceiveAudio=true, OfferToReceiveVideo=false. Sets local description before POST offer. After response, controller validates answer and always constructs native SessionDescription Type.ANSWER (response type string is not consulted at this stage). After remote SDP is set successfully, pending local ICE candidates are flushed and future candidates are POSTed immediately.

Remote candidate polling starts with500ms delay, then loops while signaling CONNECTED. Each success adds all received candidates; no controller deduplication is visible. Wait2000ms between requests/errors. ICE DISCONNECTED starts a10000ms timeout before FAILED; successful reconnection cancels it.

Transcript data channel is created with exact label transcripts and Init.ordered=true. Incoming bytes are decoded UTF-8 into JSON. No outbound channel send is visible in inspected controller classes.

| Incoming JSON | SDK behavior |
|---|---|
| {"type":"transcript","data":{"role":"...","content":"..."}} | Appends message; missing fields default empty strings. Arbitrary role strings accepted. conversationId/interactionId null and local currentTimeMillis timestamp in transcript model. |
| {"type":"metadata","data":{"conversation_id":"..."}} | Updates separate conversation ID state when nonempty. |
| {"type":"clear"} | Logs user interruption only; does not clear transcript list. |
| {"type":"end_call"} | Emits server-ended-call event then disconnects. |
| {"type":"error","data":{"message":"..."}} | Emits nonempty message, falling back to original JSON text. Does not disconnect. |
| Unknown/missing type or invalid JSON | Logs only. |

SDP validator: outgoing offer <=8192 UTF-8 bytes, starts v=0, <=2 media sections, no m=video. Incoming answer <=8192 UTF-8 bytes; CRLF normalized and empty lines removed; starts v=0; remaining lines >=3chars with letter at index0 and '=' at index1; session v/o/s/t required;1–2 media sections; only audio/application. Audio codec names allow opus/pcmu/pcma/g722/telephone-event/cn/red, at most2 distinct SSRC IDs, rejects simulcast/RID, bandwidth AS<=510 and TIAS<=510000. Attribute names use explicit allowlists. Sixth answer validation in a call fails renegotiation storm check; disconnect resets counter. These are client checks, not a guarantee that a structurally valid SDP will negotiate successfully.

Disconnect has atomic once-only guard and runs NonCancellable cleanup: cancel/join ICE poll, HTTP DELETE session, clear session ID, disable/clean audio, close/unregister transcript channel, dispose peer and factory, reset SDP tracking, set DISCONNECTED, call HTTP onCleared. Blocking session deletion uses5000ms timeout.

## Exact SDP attribute-name sets

From SdpValidator.<clinit> (session66–119, audio122–287, application290–385). Names are extracted after a= and before first colon; checks are case-sensitive and do not trim. Nonblank SDP lines are not trimmed.

- Session: group, msid-semantic, fingerprint, extmap-allow-mixed, ice-lite, ice-options, setup.
- Audio: ice-ufrag, ice-pwd, candidate, end-of-candidates, fingerprint, setup, rtcp, rtcp-mux, rtcp-rsize, rtcp-fb, rtpmap, fmtp, ptime, maxptime, mid, msid, ssrc, ssrc-group, extmap, sendrecv, sendonly, recvonly, inactive.
- Application: ice-ufrag, ice-pwd, candidate, end-of-candidates, fingerprint, setup, mid, sctp-port, max-message-size, sendrecv, sendonly, recvonly, inactive.

Compatibility implications inferred from client checks: media-level ice-options or extmap-allow-mixed fail although allowed at session level; session-level ICE credentials/candidates fail; legacy sctpmap fails. SCTP port and max-message-size values are not parsed/bounded by application validator. Group/msid-semantic values are not validated. Actual generated answer SDP should be checked against this validator; no arbitrary aiortc version compatibility is established by the archive.
