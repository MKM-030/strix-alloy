# ServiceNow Voice configuration and artifact documentation

Marcel authorizes autonomous implementation, instance updates and the existing consented own-voice upload. ServiceNow remains the source of configuration and the only business executor. The implementation must preserve the use-case prompt, greeting, selected local model and existing voice identity while making their administration traceable.

## Deliverables

1. An exact live inventory of the owned platform batch, Voice repair deltas, source artifacts and Customer Updates. Each selected Customer Update gets an individual purpose/version explanation in its native Comments field. Source Description/documentation fields are populated where they are administrative. Runtime descriptions, prompts and tool instructions remain operational content; their administrative explanation goes in Customer Update Comments and the linked change documentation.
2. A complete parameter matrix with actual source field, native default, local consumer or native delegation, effective limits and unsupported engine/transport cases. Correct misleading capability flags. Parameter projection is not described as enforcement.
3. Own/custom voice references stored as ServiceNow attachments linked to their exact native TTS configuration. The existing `parameters.scc` metadata is extended with an explicit versioned attachment/transcript/hash/provenance descriptor. Download, local cache and registration retain per-service/voice authorization and exact voice identity. Cache presence never grants access. German and English use request-local synthesis language independently from reference-recording language.
4. Locale-selected Qwen ASR key terms through the existing exported hotwords API, with per-session locking and unconditional clearing to prevent carryover between callers.
5. Analysis of the user's actual iPhone call and restoration of the selected local Halogen through its owned lifecycle. The latest incident is a memory-reserve failure, not an invitation to lower the guard or repeat inference benchmarks.

## Approach and boundaries

Use the existing native Voice configuration, existing ServiceNow authorization/resource and existing Qwen/ASR services. Creating a second local settings authority would cause drift. Cloud voice/inference services would violate the agreed deployment; duplicating ServiceNow authentication, SIP or order logic locally would change authority. Therefore preserve native delegation and expose accurate engine/transport limits.

The `sys_update_xml` table has Comments, not Description. The Voice deployment Description is the actual conversation policy. Completed Update Set header writes can reopen the batch through native Business Rules. Documentation consequently annotates the exact live CU wrappers, preserves their payload/topology, and captures source documentation updates in dedicated in-progress per-application documentation sets. Historical transport/retrieval IDs are not live authoring IDs. Sealed exports stay unchanged.

All ServiceNow mutations require current preimages, field permissions, specific text and readback. Business Rules and capture remain enabled. No role/ACL relaxation or new dictionary field is justified merely to add descriptions. Exact source scripts and an inventory of documentation exceptions accompany the instance changes.

Reference WAV data stays in ServiceNow and on the local machine. The existing approved own recording is reused; no microphone is opened. The runtime uses the original authorized caller/service context through a fixed same-instance endpoint, no arbitrary URL or admin credential forwarded as caller. Require attachment-parent relationship, selected TTS record/voice, bounded PCM WAV, reference transcript, digest, size and provenance. Register only validated bytes under the exact selected voice ID before speech; preserve existing registrations for ongoing calls.

The TTS native API already has per-request `qt_tts_params.lang`; the HTTP adapter needs to expose it and advertise support. Until paired server support is verified, the bridge must not pretend that an ignored language property is honored. Initially support German and English explicitly; additional languages require the model's actual catalog. Sampling and existing375-token/EOS/error bounds remain unchanged.

ASR hotwords use the documented `crispasr_session_set_hotwords`, not audio question answering. No new DLL/model is downloaded. Native-only authentication, telephony, transfer and fallback settings remain native authority. Do not invent equivalence for vendor phonemes, minimum-volume units or noise-strength levels that the local engine does not support.

## Verification budget

Use readback and payload/source invariants for documentation. Use a small grouped offline test set for new attachment authorization/cache, language adapter and ASR carryover behavior. Reuse established tests where they exercise these boundaries. No broad native discovery, memory benchmark, repeated voice smoke test or test order. One necessary bounded activation/readiness check is separate from inference testing. The user's actual iPhone transcript supplies the live conversation evidence; ask for a further human test only after the changes are active and a concrete gap remains.
