# Managed parallel capacity for local Voice

Marcel authorized autonomous Voice repair, model lifecycle work and tests, with no further questions. The current functional baseline passed V12: greeting, exact name readback, fresh native name confirmation, next date question and owned cleanup. Physical devices remain unverified. This design is an implementation decision under that authorization, not a separate user choice.

## Problem and approach

Local conversation and ServiceNow AIA both use controller8840. Its current concurrency1 and Halogen KVslot1 cannot produce a free conversational response while an AIA request occupies the engine. Fast deterministic feedback already works, but is not general conversation.

Reuse the existing reviewed 0.18.22 capacity implementation retained in `server/.local/halogen-update-20261101/primary01822/concurrency2-prep/candidate`, ported into this isolated worktree. Its old 8K+16K cohort completed and must not be repeated: throughput improved about5.7%, while individual long-request latency worsened17–25%. That evidence supports investigation of a different short-Voice/long-AIA workload, not automatic promotion.

The alternative cached Qwen3-1.7B sidecar is not production-qualified and requires different routing, capability and lifecycle integration. A two-slot Halogen candidate preserves the selected model and is the smaller first experiment. Merely increasing controller concurrency without a second engine slot is a control condition, not the proposed normal configuration.

## Scope

- Explicit selectors only: slots1/2 and pool32768/65536, constrained to0.18.22 v2 text-only context32768. Two independent full32K reservations use pool65536.
- Preserve CacheOff, PLD3,3/gate0.90, prefill8192/arena8192, ThinkingOff/low, prefetchOff and all binary/weight/credential/provider pins. No downloads, cloud inference or business execution.
- Preserve existing default output and behavior, including the later `FollowupText32K` Flexible-cache launcher option. Do not replace that launcher with its older complete candidate file.
- Reuse exact capacity policy, forwarding, source manifests and health/capability-probe contracts. Keep existing30GiB physical/131GiB commit opt-in startup floors,18/18 runtime reserves and22/22 request-entry checks. Never lower a floor to admit the candidate. The native allocator independently accounts for pool/slot growth; qualification must observe actual Windows memory.
- Keep the normal selected profile unchanged during source preparation. Preserve Voice Bot/Native, Gateway, ASR and own TTS generations during any later model-only qualification window.
- The backend/controller source integration is an opt-in feature. It is not evidence that parallel Voice is faster.

## Integration boundaries

Backend owns `capacity_policy.resolve(context, checkpoint='v2', *, slots=1, kv_pool_positions=None, disable_vision=False)` and `validate_manifest(manifest)`, plus `service.capacity_options`, `explicit_capacity` and `resolve_capacity`. These return the existing retained candidate contract. Environment, state, manifests and health must agree exactly; opt-in health requires native `capability_probe == 'ok'`.

Controller/profile integration accepts engine `slots`, `kv_pool_positions` and top-level `concurrency` through the retained candidate functions. Gateway2/engine1 remains valid for a queued control; engine2/gateway1 refuses before launch. Non-Halogen behavior and historical backend versions retain their existing rules. PowerShell5.1 explicit selectors are `-Slots`, `-KvPoolPositions` and `-Concurrency`, permitted only with `CurrentText32K`; `FollowupText32K` stays unchanged.

The six backend files, controller, generator and launcher comprise the production delta. The old candidate's private tests must be replaced with portable tracked tests and fixtures; they may not depend on ignored `.local` snapshots.

## Qualification and adoption boundary

After source review and offline checks, prepare a new finite private-port qualification using the existing owner-aware coordinator patterns. One engine only. Bind the actual normal profile/source/process identities, require no Native calls, retain exact normal restoration in `finally`, and preserve every speech/Gateway owner. Do not replay any old finite handle or raw cohort.

Use a frozen short conversational request (max192 output, no tools or business claims) arriving during one read-only synthetic AIA-like8K/16K request. Record actual input/output reservations, first-content time, completion, output identity/quality, admission errors and cancellation/drain behavior per request. Compare queued single-slot and two-slot behavior without changing cache or prompt content. Test pool65536 capacity and observed memory, rather than assuming the old shared32768 pool measurement qualifies it.

The candidate is eligible for normal use only if it produces correct separate responses, materially improves the short response under overlap, completes the AIA request without unacceptable degradation, stays above all reserves and restores normal reliably. Define the exact finite dispatch/acceptance plan before execution. If evidence is ambiguous or worse, keep normal one-slot serving and retain the opt-in source feature without claiming the Voice latency goal complete. No automatic later model/profile switch.

ServiceNow remains the sole business executor and owner of capability/model selection. This change creates no new business capability or provider and grants no access. Physical iPhone, Android and desktop playback remain separate acceptance.
