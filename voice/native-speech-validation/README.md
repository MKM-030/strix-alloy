# Native speech engine validation — 13 October 2026

Two independently owned, loopback-only services are ready for a native transport
adapter. This probe does not implement ServiceNow signaling, invoke ServiceNow,
or establish native Voice Assistant compatibility.

## Current services

| Service | Address | PID at verification | Readiness |
| --- | --- | --- | --- |
| Whisper Vulkan, German Turbo F16 | 127.0.0.1:8861 | 6764 | GET /health -> 200, status ok |
| Qwen3-TTS Vulkan, Base 0.6B Q8_0 | 127.0.0.1:8862 | 23104 | GET /v1/models -> 200, scc-native-qwen3 |

The PID numbers are historical evidence. Always use the recorded executable,
command line and process creation time checks in speech_probe.py before stopping.
Current ownership records, stdout/stderr and the generated WAV are in ignored runtime/.
The initial speech validation did not stop any existing process. The later,
authorized HaloGen recovery retired the two redundant CPU audio workers, as
recorded below. No dependencies, models, firewall settings or permissions were
installed or changed by this validation/recovery work.

## Reproduce and stop safely

Use the existing Python environment with psutil already installed:

~~~powershell
$probe = 'C:\Projects\strix-alloy-scc-voice\voice\native-speech-validation\speech_probe.py'
& 'E:\SCC-Voice\asr-env\Scripts\python.exe' $probe status
& 'E:\SCC-Voice\asr-env\Scripts\python.exe' $probe start
& 'E:\SCC-Voice\asr-env\Scripts\python.exe' $probe validate
& 'E:\SCC-Voice\asr-env\Scripts\python.exe' $probe warm
& 'E:\SCC-Voice\asr-env\Scripts\python.exe' $probe stop
~~~

Start refuses occupied ports and configuration changes; it never adopts an
unrelated process. HTTP probes check listener PID and loopback bind first.
Stop targets only processes matching this probe's PID, creation time, executable
and command line. Launch requires at least 18 GiB available system RAM.

The exact launched argument arrays are in validation-result.json. Their commands:

~~~powershell
& 'C:\AI\build\whisper.cpp\build\bin\whisper-server.exe' --model 'C:\AI\models\stt\ggml-turbo-german.bin' --host 127.0.0.1 --port 8861 -l de -t 6 -fa -nf
& 'C:\AI\qwentts.cpp\build\Release\tts-server.exe' --model 'C:\AI\models\qwen3-tts-gguf\qwen-talker-0.6b-base-Q8_0.gguf' --codec 'C:\AI\models\qwen3-tts-gguf\qwen-tokenizer-12hz-Q8_0.gguf' --alias scc-native-qwen3 --host 127.0.0.1 --port 8862 --lang German --max-batch 1
~~~

Prefer the launcher to these raw commands so ownership remains recorded.
This is the documented qwentts.cpp server interface, independent of the REV:N
Python supervisor. The latter was neither started nor modified.

## Actual measurements

One cold TTS synthesis was performed, followed by ASR of its output and one
explicitly requested warm synthesis of the same brief phrase:

| Operation | First body byte | Complete response |
| --- | ---: | ---: |
| Existing synthetic SCC sample -> ASR | 1.6707 s | 1.6707 s |
| Register SCC Demo synthetic reference | 3.2106 s | 3.2107 s |
| TTS: Guten Tag. Wie kann ich helfen? | 3.6055 s | 4.1390 s |
| Generated TTS audio -> ASR | 0.3407 s | 0.3408 s |
| Warm TTS, same phrase | 0.2304 s | 0.7608 s |

TTS returned headers at 0.0236 s; headers are not playable audio.
Output: 2.64 seconds, mono PCM16 little-endian, 24 kHz, 126720 raw bytes.
ASR returned "Guten Tag, wie kann ich helfen?" (same words).
The server reached codec EOS at frame 33; it did not hit the 96-token safety cap.
The cold codec path dominated latency. Warm output was 2.96 seconds of audio,
142080 raw bytes; first PCM arrived in 230.4 ms and generation finished in
760.8 ms, faster than playback. This is one warm sample, not a distribution or
concurrent-load result. Post-validation free system RAM was 31.44 GiB.

SCC Demo reused the original designed synthetic reference in ../assets/scc-demo.
Its verified SHA256 is
293fe81f27f3fb904bab2ef7d54013aaef57b2d3d64f1293b6c9bbd5c48da778.
The Base model extracted and registered its reference directly; no person's
voice was introduced. This establishes generation and intelligibility, not a
new subjective listening assessment.

## Contracts for the native adapter

ASR: POST http://127.0.0.1:8861/inference, multipart fields file (PCM WAV),
language=de, temperature=0, response_format=json. Response {"text":"..."}.

TTS voice registration after each server restart:
POST http://127.0.0.1:8862/v1/audio/voices with name="scc-demo",
ref_text from the existing voice.json and wav_b64 from its verified reference.wav.
The probe performs this registration in validate.

TTS: POST http://127.0.0.1:8862/v1/audio/speech with
{"input":"Guten Tag. Wie kann ich helfen?","voice":"scc-demo","response_format":"pcm","seed":42,"max_new_tokens":96}.
The response is audio/pcm, streamed PCM16 little-endian at 24 kHz. It is not a WAV.
The native adapter must provide its own authenticated external transport,
turn management, cancellation and conversion from its negotiated media format.
No browser UI was created. Direct inference endpoints stay on loopback.

## WebRTC dependency inventory

Read-only import-spec checks found no aiortc in the SCC ASR/TTS environments,
the existing bridge environment, or the REV:N Omni environment. The bridge
venv has aiohttp; SCC ASR and REV:N Omni have PyAV; Omni has websockets.
No wrtc, werift, mediasoup, node-datachannel, @roamhq/wrtc or @koush/wrtc
package was found in REV:N node_modules/.pnpm. This is a bounded inventory,
not a whole-disk search. No package installation was attempted.


## HaloGen recovery and native startup

At 11:38:12 local time on 13 October, the existing HaloGen runtime guard observed
17.804 GiB physical reserve, below its unchanged 18 GiB limit, and stopped the
owned model container. The container exited with code 0 and OOMKilled=false.
Gateway 8841 then returned ClientConnectorError/502 because its upstream 8731
was absent. A native greeting could reach ServiceNow's StreamStart while no
text completion was available. This failure was not a TTS generation delay.

The idle original CPU workers (ASR 8851, PID 9260; TTS 8852, PID 12808) were
explicitly authorized for retirement. Their project path, executable, complete
argument arrays, creation times and authenticated idle health were captured
before identity-checked termination. Rollback evidence is retained in
runtime/retired-cpu-workers-20261013T095837Z.json. No new GPU speech service was
stopped. Do not run legacy voice/Start-Voice.ps1 for the native demo: it can
relaunch these redundant CPU models and consume the HaloGen memory reserve.
The native launcher must reject duplicate legacy workers with an actionable
message instead of silently starting both audio stacks.

The failed HaloGen run retained its ownership lock. Recovery followed the
existing project's documented supplemental-recovery precedent in
docs/benchmarks/halogen-cache-gufo-followup-20260930.md. The exact old container
identity and terminal state were checked live; no owners, guards or running
containers remained. The inspection-created WSL VM was returned to its original
stopped state. Five fresh samples at 47.20–47.21 GiB exceeded the original
45.559 GiB recovery floor (original baseline minus 2 GiB). Only that stale lock
was archived; the old failed guard, recovery and outcome receipts were preserved.
The separate receipt and lock backup are under ignored runtime/, including
halogen-reconciliation-20261013T100645Z.json.

Restore uses the exact existing 0.18.1 profile, without changing its model,
context 262144, one slot, CacheOff, MTP2, PLD3/3, prefill 4096, thinking
medium/2048, or 18 GiB physical/commit runtime guard. The profile SHA256 remains
cf02e2e695160c3e199a2efbf81920192d77f538616b4a3a00153e33927333c4.

Use the project controller, not a generic backend default:

~~~powershell
$repo = 'C:\Projects\strix-alloy-clean'
$python = "$repo\server\.local\venv\Scripts\python.exe"
$controller = "$repo\server\controller.py"
$profile = "$repo\server\.local\optimization9h-20261004\halogen0172-backend-preparation-20261008\halogen0181-version-bracket-20261012\serving0181-full262-profile.json"
& $python -u -B $controller run --config $profile
# In a second shell:
& $python -B $controller status
# Only when stopping the owned model is intended:
& $python -B $controller stop
~~~

The managed start runs its existing admission, independent memory guard,
version/context checks and two benign startup self-checks. Stop requests the
current owned run's normal cleanup and memory recovery; do not kill by image
name or automatically delete a retained runner.lock. Readiness is recorded in
halogen-recovery-result.json; historical PIDs in reports must never be used as
an unverified stop target.

Restoration verification at 10:11:13 UTC: both controllers stayed ready, and
8731 returned authenticated status ok with matching API/engine 0.18.1, full
262144 context and one slot. The project's arithmetic and German startup checks
passed. Seven samples across 60 seconds had 27.892–27.964 GiB free physical
memory and at least 120.877 GiB commit headroom; the 18 GiB guard remained active.
ASR 8861 and TTS 8862 health remained HTTP 200. No additional inference prompt
was sent by this recovery validation. Current historical controller PIDs:
outer 19736, model controller 21040; readiness evidence includes exact run IDs.
