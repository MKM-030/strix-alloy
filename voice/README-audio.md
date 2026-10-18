# Local Qwen speech workers

Two isolated Python 3.12 environments keep the upstream Transformers pins compatible.
The current implementation uses CPU inference, six compute threads per process, and
an 18 GiB available-memory admission check. It does not change GPU drivers or HaloGen.

| Worker | Environment | Model | HTTP port |
| --- | --- | --- | --- |
| Recognition | E:\SCC-Voice\asr-env | Qwen/Qwen3-ASR-0.6B | 127.0.0.1:8851 |
| Synthesis | E:\SCC-Voice\tts-env | Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice | 127.0.0.1:8852 |

Model downloads are cached in E:\SCC-Voice\models. Keep these environments outside
the repository. Install torch==2.9.1 and torchaudio==2.9.1 from
https://download.pytorch.org/whl/cpu before installing the corresponding requirements file.
Use uv pip install --python ENV\Scripts\python.exe -r voice\requirements-asr.txt
or requirements-tts.txt. Use uv pip check --python ENV\Scripts\python.exe to validate.

Run from the repository, using the appropriate environment:

```powershell
& 'E:\SCC-Voice\asr-env\Scripts\python.exe' -u voice/audio_service.py --mode asr --threads 6
& 'E:\SCC-Voice\tts-env\Scripts\python.exe' -u voice/audio_service.py --mode tts --threads 6 --dtype bfloat16
```

Use separate terminals. The top-level voice launcher can run them in the background.
The CLI defaults to float32. This host has AVX512 BF16 support, so the measured TTS
configuration uses --dtype bfloat16; unsupported CPUs are rejected before loading.
ASR remains float32. The workers load the downloaded local snapshot directories,
including the speech tokenizer, so cached startup works with HF_HUB_OFFLINE=1.
Default authentication reads the existing local ServiceNow token file:
C:\Projects\strix-alloy-clean\server\.local\servicenow-api-token.txt.
The value is never printed, embedded in code, or passed on the command line.
A different token file can be supplied with --token-file.

All endpoints require Authorization: Bearer TOKEN, including GET /health.
There is no direct browser CORS interface; the local bridge/gateway handles browser requests.
Models finish loading before the worker opens its listening socket. Health reports the exact
model, CPU device, readiness and busy state. Startup logs contain model loading diagnostics;
HTTP access logs and request-content logging are disabled.

## API contract

POST /v1/audio/transcriptions accepts multipart:
- file: audio upload, at most 20 MiB and 60 seconds; PCM WAV is the supported browser path.
- model: qwen3-asr-0.6b or the exact recognition model ID above.
- language: de (default), en, or auto.
- response_format: json (default).

The response is {"text":"recognized words"}. Invalid codecs return 415. Remote audio URLs
are not accepted. The browser should encode mono PCM WAV before upload.

POST /v1/audio/speech accepts JSON:
```json
{"model":"qwen3-tts-0.6b","input":"Guten Tag. Wie kann ich helfen?","voice":"Ryan","response_format":"wav"}
```

Input is limited to 1500 characters. Synthesis always uses German. Output is a complete
16-bit PCM WAV, with the model-provided sample rate. Ryan is the default preset.
Other presets: Aiden, Vivian, Serena, Uncle_Fu, Dylan, Eric, Ono_Anna, Sohee.
Unknown voices, arbitrary model IDs, and non-WAV output requests are rejected.
This CustomVoice model uses supplied presets; it does not clone a person's voice.

Each worker processes one request at a time. Concurrent requests receive 503 with
Retry-After: 1; memory-reserve rejection uses Retry-After: 10. There is no unbounded queue.
The gate releases on failures. Internal inference errors return a generic 500.
This version supports complete utterances and full WAV responses, not audio streaming.

## Verification

```powershell
& 'E:\SCC-Voice\asr-env\Scripts\python.exe' -m pytest voice/tests/test_audio_contract.py -q
```

The contract suite exercises actual HTTP parsing, authentication, validation, WAV decoding,
response encoding, failure recovery, and concurrent busy responses. It replaces only model
inference to keep those cases deterministic. All 12 audio contract tests pass.

Actual-model verification on this host, 2026-10-12 (CPU, six threads per worker):

| TTS dtype / run | TTS latency | Generated audio | ASR latency | Transcript |
| --- | --- | --- | --- | --- |
| FP32 first request | 15.525 s | 3.84 s, 24 kHz | 2.869 s | Exact input recovered |
| FP32 second request | 19.637 s | 4.88 s, 24 kHz | 2.141 s | Exact input recovered |
| BF16 first request | 6.864 s | 3.76 s, 24 kHz | 1.667 s | Exact input recovered |
| BF16 second request | 8.361 s | 4.64 s, 24 kHz | 2.088 s | Exact input recovered |

The prompts were short German service-assistant sentences, synthesized by preset Ryan.
These are full-response latencies, not time to first streamed audio. Keep demo answers short.
BF16 reduced synthesis time by about 2.2x after normalizing for generated duration.
ASR stayed FP32 throughout. Free RAM after BF16 testing was 25.06 GiB, above the
18 GiB admission reserve (FP32 baseline: 22.75 GiB).
Measurements: E:\SCC-Voice\logs\audio-smoke.json; audio: smoke-cold.wav and smoke-warm.wav
in the same directory. BF16 results: audio-smoke-bf16.json and
smoke-bf16-cold.wav / smoke-bf16-warm.wav. Model inference was verified separately
from the deterministic tests. One overlapping bridge request correctly received busy 503;
the second BF16 measurement was rerun alone and succeeded.
The ASR cache revision is 5eb144179a02acc5e5ba31e748d22b0cf3e303b0; TTS is
85e237c12c027371202489a0ec509ded67b5e4b5. For offline startup after downloading,
set HF_HUB_OFFLINE=1 before launching the workers.

A repository-wide pytest run in the isolated ASR environment stopped during collection
with 75 errors from historical duplicate backend test names and unrelated missing
server/benchmark dependencies. It is not a whole-repository test environment.

## Official references

- https://github.com/QwenLM/Qwen3-ASR
- https://github.com/QwenLM/Qwen3-TTS
- https://huggingface.co/Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice
- https://pytorch.org/get-started/previous-versions/
