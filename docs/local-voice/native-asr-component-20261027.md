# Native CPU ASR component observations, 27 October 2026

One saved C-ABI qualification and one separate synthetic TTS-to-ASR HTTP check
completed. These observations measure speech components. They establish no
matched speedup, LLM token throughput or physical phone-call quality.

## Single C-ABI qualification

The retained model is Qwen3-ASR-0.6B, `qwen3-asr-0.6b-q4_k.gguf`, 631,026,336
bytes, through `crispasr` with `mixed-gguf` storage. The request used six CPU
threads, GPU/Flash Attention off, German and a 256-token output budget. Actual
dynamic-UCRT readback recorded chunk seconds 60, autochunk 1 and fused QKV 1.
There was one model load and one decode of an 8.72-second synthetic German
fixture: 139,520 mono PCM16 samples at 16 kHz.

| Recorded component | Seconds |
| --- | ---: |
| Model load | 0.1575 |
| Decode | 0.8276 |
| Session close | 0.1163 |

Recorded real-time factor is **0.0949**: decode seconds divided by input audio
seconds. RSS after decode was 975,646,720 bytes. The supervisor records exit 0,
terminal ownership, an empty final Job and process unload proof. This check
recorded zero microphone captures, business requests, network requests and
service changes.

## Separate synthetic HTTP roundtrip

One synthesis and one ASR HTTP request processed 2.88 seconds of synthetic
audio using the selected local reference voice and actual Native Speech methods.

| Recorded component | Seconds |
| --- | ---: |
| TTS first chunk | 0.2500 |
| TTS completion | 0.7914 |
| ASR HTTP call | 0.4622 |

The receipt records an exact match for that synthetic phrase, zero microphone
captures and business requests, and zero service restarts. The component times
are separate intervals; they are not summed into a phone-call latency claim.

## Evidence and limits

The [sanitized JSON report](native-asr-component-20261027.json) pins the three
private saved receipts and retains their exact numeric/configuration fields.
It includes no transcript, personal name, audio, credential or private host path.
No model payload was read or benchmark repeated for this documentation update.

The standalone qualification worker and the supervisor's embedded worker copy
match on every field when decoded as UTF-8. Transcripts and personal names are
omitted for privacy; no accuracy score is derived from the single fixture.
The saved observation flags record first name exact, spelling sequence present
and surname not exact. One fixture cannot establish general ASR
accuracy, noise tolerance, interruptions, audibility or successive phone calls.
The separate short roundtrip does not resolve that limitation.

Halogen's latest engine phase measurements remain the
[26 October natural 8K/16K cohort](../benchmarks/halogen01816-natural-8k16k-20261026-evening.md).
No conversion from these speech-component timings to engine tok/s is made.
