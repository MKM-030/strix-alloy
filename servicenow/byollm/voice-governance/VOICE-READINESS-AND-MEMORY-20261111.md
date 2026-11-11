# Voice readiness and memory repair — 11 November 2026

The Native bridge now refuses a voice call when the selected TTS server is missing. Previously its readiness endpoint checked the conversation model and ASR only, so it returned HTTP200 even with no process on the configured speech port. That was reproduced against the live installation after a separate Engineering task unloaded TTS for memory recovery.

## Installed behavior

`tts_health.py` reads only the configured loopback TTS origin's `/v1/models`. The expected model alias is shared with speech synthesis. The request has a two-second total deadline, a16KiB body limit, no redirects, no decompression and no inference. Missing, malformed or wrong-model metadata produces `ttsReady:false` and HTTP503; private errors are not returned to the client.

SDK and browser admission check TTS before reference preparation and call allocation. Browser admission retains its capacity recheck after the asynchronous probe. Typed Chat stays independent of TTS. `nativeSessions` is refreshed after asynchronous readiness probes, rather than returning a count captured before them. Per-call voice-reference authorization and registration remain separate; model metadata alone does not prove an individual voice is registered.

The configured greeting, language, own voice, selected Halogen, agent prompts and business execution were not changed. Task101's overlapping greeting/ICE startup and current-input/context repairs remain present.

## Verification and actual activation

- The regression first reproduced false200 with absent/wrong TTS. The final focused run passed two TTS-readiness tests and the existing SDK audio test (three tests,6.707s). It used local metadata stubs and synthetic audio, not actual model inference or a ServiceNow conversation. It covers timeout, redirects, size limits, cancellation, pre-allocation rejection, current session counts and the existing greeting/transcript/audio contract.
- The ordinary startup check-only passed after the reviewed Native artifact pin update. Only the Native role changed in the private manifest; ASR binaries, model and configuration were preserved. Manifest SHA256:20955c65b43727389e59cf5b02a865994f5e354086d71addb8d29f836c4d974f.
- One authorized Native maintenance restart installed the source in process25548 at07:55:25local. Exact model/ASR/Bot/Gateway process identities and configuration were preserved. The maintenance operation observed no active sessions; its snapshot does not guarantee that a concurrently arriving attempt could not have been interrupted.
- Public HTTPS verification at06:55:53UTC returned HTTP503 in2312ms, with `modelReady:true`, `asrReady:true`, `ttsReady:false`, and zero sessions. This is the correct unavailable state while TTS remains absent, **not a restored working call or a measured greeting latency**.

Private evidence is under `server/.local/voice-repair-20261102/task102-voice-restoration-20261111/`: the baseline, independent review, SPENT marker, activation result, focused test receipts and `public-health-after-tts-readiness.json`. The activation helper is consumed and must never be replayed.

## Why the speech service is still absent

Ordinary Voice startup earlier restored speech alongside selected Halogen0.20.1. The model subsequently crossed its18GiB host-memory reserve and stopped. The separate active Engineering task then unloaded TTS19156 and restored the same selected model. Its v1/v2 post-Voice memory recovery receipts document that action. This repair did not stop that model or restart speech into concurrent hardware work.

Host diagnosis also found MediaTek Bluetooth Service MTKBTSVC retaining over4.33million handles. At07:35:44local, resident kernel pools were18.180GiB. File/filter allocation tags dominate, but this does not prove every pool byte belongs to that process. A normal-token service-access probe returned Windows access denied5. An administrator restart has been requested from Marcel; no completion reply has been received. It requires a fresh memory/handle comparison afterward and is not a demonstrated permanent driver remedy.

An isolated TTS source repair gives reference extraction a temporary scheduler, releasing graph allocations after registration. CPU compilation and one real allocator-lifetime test passed. Production source provenance, including earlier EOS and German/English fixes, is verified in `C:/AI/qwentts-reference-scratch-20261111/qualification/PRODUCTION-PROVENANCE-RECONCILIATION.md`. Actual own-reference memory savings and Vulkan output remain unqualified; no memory-saving claim or production replacement is made here.

## ServiceNow changes and remaining acceptance

No ServiceNow configuration, business record or Customer Update was changed in this continuation. A genuine native Request caller-auth precheck passed in1203ms with zero sessions/inputs/audio/inference. Its transient OAuth access and refresh credentials were revoked, and the original access then returned401. The consumed auth attempt must not be replayed.

Current settings still select German, own voice81959ffa-c2ef-4db5-bf95-5df2a24c9404 and the147-character configured introduction. The distinct Voice conversation capability is `aca5634f4312121038520464dbb8f236`; its current model configuration is `ff74fcef93a70350e7f2b9fa6aba10ea` (`halogen-v2`). Agent execution remains ServiceNow-owned.

Before a new call: reconcile host memory and concurrent speech/model ownership, qualify the isolated TTS candidate with the existing own reference, and restore speech through the normal owner-aware lifecycle. A new bounded two-call draft exists but has not been armed or executed. Real iPhone playback, name corrections, noise behavior, device parity and business completion remain open. No employee/order inputs, microphone capture, cloud inference or model downloads were used for these checks.
