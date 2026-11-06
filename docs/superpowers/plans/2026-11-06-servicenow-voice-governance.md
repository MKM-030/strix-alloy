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

## Actual progress ledger — 6 November 2026

The original native TTS record remains unchanged. The final reference source is a valid inline `parameters.scc.reference`, or, only when inline metadata is absent, the own Global property `local_llm.voice.reference.<serviceId>.<ttsConfigId>`. The native local-engine/profile/WAV-hash binding and original-caller secure reads remain mandatory. No additional WAV/sidecar upload, role, ACL or cross-scope grant is part of this design.

The final and independent audits pass: 1,081 commented CUs in 56 sets (1,015 original plus 66 new; 50 existing sets plus four documentation and two functional sets). Property `631c110393d85b585c8132d47aba1023` is installed in Global set `b9995583931c1394e7f2b9fa6aba10c0`; the two installed Voice code captures belong to `e967c98f93541394e7f2b9fa6aba1091`. Native TTS, ACL and WAV remain unchanged. One original native `IsMetadataUpdated` CU has an explicit audit-only payload exception: `sys_mod_count` 321→325 and `sys_updated_on`; semantic fields are unchanged and its purpose comment was corrected. Do not claim all old XML payloads are byte-identical.

Local activation is complete: Native 23168, TTS 5644 and ASR 16592, with the original voice and selected Halogen profile preserved. Installed native stream validation and the actual Python DTO agree on German, original voice/reference, the 147-character greeting and `halogen-v2`. No original-caller HTTP Bearer roundtrip, real-device audio or business-order completion was verified; these remain explicit validation limits.

### Task1: Restore the owned model and analyze the real iPhone call

- [x] Freeze current failure, native call and ServiceNow7-table readbacks; join timestamps with clock offsets.
- [x] Review a new one-shot recovery proposal using fresh exact identities, owned Docker/container state and original memory recovery predicate.
- [x] Reconcile only the exact failed run and start the unchanged selected profile once; no inference smoke test.
- [x] Document availability and the concrete remaining iPhone test gap.

### Task2: Live artifact inventory and per-record descriptions

**Files:** evidence and guarded installer under `server/.local/voice-repair-20261102/servicenow-documentation-config-20261106-v1`; committed documentation under `servicenow/byollm/voice-governance`.

- [x] Freeze owned set trees and later repair IDs; read live CU metadata/payloads with complete pagination and current source documentation fields.
- [x] Produce unique descriptions per captured artifact/version; preserve functional prompt text and mark unsupported/absent Description fields explicitly.
- [x] Review preimage-bound source documentation and CU Comments mutations; use dedicated in-progress per-scope documentation captures.
- [x] Apply the historical documentation batches and read back their coverage, payload hashes and set membership/state invariants: 1,015 CU Comments and 63 source documentation fields across four new documentation sets.
- [x] Complete the final functional property/code capture readback and documentation after installation; reconcile all 1,081 CUs and the bounded native audit-field exception.

### Task3: ServiceNow voice reference records and authorized projection

**Files:** `servicenow/byollm/voice-policy/LocalLLMVoiceAssistantSettings.js`, existing authorized Voice resource, new focused reference resource/installer if needed, `voice/native-bridge/assistant_settings.py`, a focused reference/cache module.

- [x] Read exact selected TTS/config/attachment fields and native provider choices; preserve the current German default.
- [x] Define the bounded versioned reference descriptor and implement its local validation/cache/registration consumer.
- [x] Verify the existing approved WAV on its selected native TTS parent and its matching hash; reuse it without another upload. Document attachment transport separately.
- [x] Finish and install the source resolver: inline reference when present, otherwise own Global property only under the existing explicit local-engine/profile/hash binding. Keep the native TTS record unchanged.
- [x] Publish the own Global property and validate the installed secure-read/stream path and functional capture server-side; no secrets or audio in `sys_properties`. A real original-caller HTTP roundtrip remains unverified.
- [x] Offline grouped local tests: unauthorized cache reuse, hash/size/PCM mismatch, exact selected reference, prepared-handle binding and caller preparation boundaries.
- [x] Complete the focused ServiceNow property-resolver verification and installation readback, independent attachment hash and actual native-to-Python DTO validation.

### Task4: Per-call TTS language and ASR key terms

**Files:** Qwen `src/tts-server.h`, `tools/tts-server.cpp`; `voice/native-bridge/native_bridge.py`; `voice/audio_service.py`; `voice/native_qwen_asr.py`; relevant settings/consumer modules.

- [x] Add advertised, validated request-local TTS language using existing native `qt_tts_params.lang`; omission preserves old callers.
- [x] Map native German/English locales explicitly after verifying paired server capability. Preserve selected voice and sampling/EOS bounds.
- [x] Bind documented ASR hotwords export, validate bounded locale-selected terms and set/clear within the existing transcription lock.
- [x] Correct stale capability-report flags and publish the parameter matrix, including native delegation and justified engine limits.
- [x] Run only grouped boundary regressions and build the affected TTS server once; no real synthesis benchmark.

### Task5: Integrate and activate once

- [x] Review and promote the local consumer changes, update startup artifact pins and preserve rollback originals.
- [x] Perform one idle coordinated local activation: stop only the three verified workers, let redirectors exit naturally, replace the five reviewed TTS binaries and start the normal stack once.
- [x] Confirm local readiness and preserved Bot/Gateway/Halogen/profile/original-voice identities from the activation result and post-activation audit.
- [x] Independently review, install and read back the final ServiceNow property/code changes and their captures.
- [x] Commit the final installed ServiceNow source/documentation changes and give Marcel a precise real-device validation request if a concrete gap remains.
- [x] Final report separates installed behavior, successful readback, intentionally stopped order boundary and remaining unsupported native engine/transport options.
