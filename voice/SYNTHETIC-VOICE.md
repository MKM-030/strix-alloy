# SCC synthetic German voice

The SCC voice is an original synthetic adult German voice. It is not a clone of a person's recording. VoiceDesign generates a reference once; the smaller Base model then speaks arbitrary dialog text using the validated reference and cached speaker prompt.

## Models and files

- One-time design: `Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign`.
- Runtime synthesis: `Qwen/Qwen3-TTS-12Hz-0.6B-Base`.
- ASR remains `Qwen/Qwen3-ASR-0.6B`.
- Profile: `E:\SCC-Voice\voices\scc-demo` (`voice.json`, `reference.wav`, `prompt.pt`, `sample.wav`).
- The reference hash, transcript, model ID, package version and design seed are recorded. The tensor cache uses restricted `weights_only=True` loading and can be rebuilt from the reference.
- The portable synthetic reference and its manifest are versioned in `voice/assets/scc-demo`. Model weights, derived caches and validation audio stay outside Git. On a fresh host, copy those two reference files into the configured profile directory; startup rebuilds the prompt cache if needed. Preserve an existing profile rather than overwriting it.

## Prepare and verify

```powershell
E:\SCC-Voice\tts-env\Scripts\python.exe voice\prepare_demo_voice.py --output-dir E:\SCC-Voice\voices\scc-demo --cache-dir E:\SCC-Voice\models --dtype bfloat16 --threads 6
```

Run TTS with its existing arguments plus `--voice-profile E:\SCC-Voice\voices\scc-demo`. Set the bridge's TTS voice to `scc-demo`; retain model alias `qwen3-tts-0.6b`. The audio service requires its existing bearer token and listens only on localhost. No authentication change is needed.

```powershell
E:\SCC-Voice\tts-env\Scripts\python.exe voice\verify_demo_voice.py
```

The verifier makes a real synthesis request, transcribes the resulting WAV through the running ASR worker and records timing, transcript, WAV properties and word error rate in `service-validation.json`. It does not print credentials. This check establishes the local audio path, not the ServiceNow dialog, phone microphone or full ordering scenario.

Verified on 13 October 2026: fresh TTS worker loaded the existing prompt cache and produced a 24 kHz PCM WAV for “Wie heißt Ihr neuer Mitarbeiter? Ich plane die Lieferung nach Hamburg.” The 4.24-second audio took 17.067 seconds to generate on the CPU; ASR took 3.327 seconds and returned the exact words (word error rate 0). CPU synthesis adds noticeable delay and is not streaming. The 21 profile/audio contract tests passed.

Authenticated `/health` reports the real Base model and `voice: SCC Demo`. Unsupported voices fail explicitly; a request for `Ryan` does not silently produce a different voice.

## Recovery

The former preset worker remains available by omitting `--voice-profile` (or passing `-VoiceProfile ''` to `Start-Voice.ps1`), selecting bridge voice `Ryan` and restarting only the owned TTS worker plus the bridge if its configuration changed. Do not stop HaloGen or ASR. Preserve the synthetic profile so the switch is reversible and no reference regeneration is necessary.

Completion requires a generated profile, successful service verification and an end-to-end bridge test. The existence of these scripts alone is not evidence that the running voice has changed.
