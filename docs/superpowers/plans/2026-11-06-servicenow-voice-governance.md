# ServiceNow Voice governance implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. The user already opted for autonomous execution; no further design approval is pending.

**Goal:** Document every owned captured artifact in ServiceNow, honor native Voice configuration locally, store and resolve custom reference voices from ServiceNow, and close the current runtime incident.

**Architecture:** Extend the existing authorized settings/resource, exact voice registry and native language/ASR adapters. Maintain per-call snapshots and ServiceNow business authority. Administrative documentation is written separately from runtime prompt content.

**Tech Stack:** ServiceNow SDK4.14/Glide APIs, existing Python/aiohttp bridge, CrispASR C API, Qwen C++ TTS HTTP adapter, local immutable WAV profiles.

**Spec:** `docs/superpowers/specs/2026-11-06-servicenow-voice-governance-design.md`.

## Global constraints

- No test order, microphone capture, cloud inference, new model download or broad benchmark.
- Serialized instance SDK operations; preserve current application/Update Set selection.
- No edits to sealed exports or completed header state/topology; CU payloads remain unchanged for Comments-only updates.
- Use exact current source/sys_id/update-name relationships, not exported transport IDs.
- Preserve18GiB memory guard, existing375-token/EOS bounds and original caller authorization.

## Review focus

- An attachment linked to another service/voice must never become authorized through local cache reuse.
- Missing/malformed/stale reference bytes must not silently choose a different voice.
- Simultaneous German/English calls must not mutate global language or another caller's ASR hotwords.
- Description fields used in prompts must not acquire administrative bookkeeping text.
- A failed memory cleanup must be reconciled with exact owned identities, not a stale PID or generic lock removal.

### Task1: Restore the owned model and analyze the real iPhone call

- [ ] Freeze current failure, native call and ServiceNow7-table readbacks; join timestamps with clock offsets.
- [ ] Review a new one-shot recovery proposal using fresh exact identities, owned Docker/container state and original memory recovery predicate.
- [ ] Reconcile only the exact failed run and start the unchanged selected profile once; no inference smoke test.
- [ ] Document availability and the concrete remaining iPhone test gap.

### Task2: Live artifact inventory and per-record descriptions

**Files:** evidence and guarded installer under `server/.local/voice-repair-20261102/servicenow-documentation-config-20261106-v1`; committed documentation under `servicenow/byollm/docs`.

- [ ] Freeze owned set trees and later repair IDs; read live CU metadata/payloads with complete pagination and current source documentation fields.
- [ ] Produce unique descriptions per captured artifact/version; preserve functional prompt text and mark unsupported/absent Description fields explicitly.
- [ ] Review preimage-bound source documentation and CU Comments mutations; use dedicated in-progress per-scope documentation captures.
- [ ] Apply bounded batches once and read back complete coverage, payload hashes and set membership/state invariants.

### Task3: ServiceNow voice reference records and authorized projection

**Files:** `servicenow/byollm/voice-policy/LocalLLMVoiceAssistantSettings.js`, existing authorized Voice resource, new focused reference resource/installer if needed, `voice/native-bridge/assistant_settings.py`, a focused reference/cache module.

- [ ] Read exact selected TTS/config/attachment fields and native provider choices; preserve the current German default.
- [ ] Define and implement one bounded versioned `parameters.scc` reference descriptor with attachment identity, digest, reference transcript/language and provenance.
- [ ] Upload the existing approved WAV to its exact native TTS record, link the descriptor and capture transportable metadata. Document attachment transport separately.
- [ ] Extend authorized projection and same-instance download authorization; validate parent/voice/service and cache immutable verified bytes without retaining caller credentials.
- [ ] Offline grouped tests: unauthorized parent/cache hit, hash/size mismatch and successful exact selected reference.

### Task4: Per-call TTS language and ASR key terms

**Files:** Qwen `src/tts-server.h`, `tools/tts-server.cpp`; `voice/native-bridge/native_bridge.py`; `voice/audio_service.py`; `voice/native_qwen_asr.py`; relevant settings/consumer modules.

- [ ] Add advertised, validated request-local TTS language using existing native `qt_tts_params.lang`; omission preserves old callers.
- [ ] Map native German/English locales explicitly after verifying paired server capability. Preserve selected voice and sampling/EOS bounds.
- [ ] Bind documented ASR hotwords export, validate bounded locale-selected terms and set/clear within the existing transcription lock.
- [ ] Correct stale capability-report flags and publish the exhaustive parameter matrix, including native delegation and justified engine limits.
- [ ] Run only grouped boundary regressions and build the affected TTS server once; no real synthesis benchmark.

### Task5: Integrate and activate once

- [ ] Independently review actual source/config changes and instance capture/readback.
- [ ] Commit/cherry-pick focused changes, update all affected startup artifact pins and preserve rollback originals.
- [ ] Perform an idle coordinated activation only after the actual user call is closed; preserve unmodified services/voices/model identity where possible.
- [ ] Run the normal read-only startup/readiness check once, then give Marcel a precise real-device validation request only if necessary.
- [ ] Final report separates installed behavior, successful readback, intentionally stopped order boundary and remaining unsupported native engine/transport options.
