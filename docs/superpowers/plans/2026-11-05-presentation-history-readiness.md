# Presentation feedback readiness and pending conversation state

Continue the authorized Voice repair from source `6e4cc2d`. This change preserves the selected model, own speech, original caller inputs and ServiceNow business authority.

The optional feedback worker previously consumed a completely emitted local answer before the Dialog had its private CREATE binding. A False result permanently disabled this lane. Wait for the exact private binding generation before dequeuing or starting the existing two-second publication budget. Retire and cancel old work at reset, end, close and shutdown; check again when a scheduled publisher actually enters. Neither startup, audio nor business dispatch waits for this optional lane. Keep the 16-event bound and no retries after uncertain publication.

Add bounded stage/status/timing/size diagnostics for local grant transport and feedback publication. Native grant refusal diagnostics are enabled only after exact input, actual non-Guest caller equality and conversation proof validation. They add no authorization, provider reads/writes or business authority. The canonical helper retains both feature and diagnostic flags false. All original grant, alias, Secure-reader and consumer checks remain unchanged.

The saved actual Q3 answer preceded ServiceNow's manager proposal by about 22 seconds. The configured description's instruction to list missing fields was therefore ambiguous about unmentioned caller input versus authoritative missing fields. Root installed description8 in the own ServiceNow deployment, preserving all 53 configuration rows and the computed greeting/voice/language. A reconstructed local-text check showed description8 alone still generated the incorrect definitive inventory. A model-neutral pending-context rule then produced an answer that distinguishes caller-provided data from information still unknown. Independent review narrowed the rule to also permit applicable ServiceNow findings already received. This changes presentation guidance only; genuine backend output and input/control ownership remain intact.

Verification:

- 134 selected Python tests passed for the readiness/transport changes before the later pending wording addition.
- 95 native helper tests passed, including fixed failure stages, no diagnostics before caller/proof validation, privacy and logger failures.
- The 26 pending-context/raw-delivery tests passed with the pending wording addition. A mistaken nonexistent extra test-module name caused a loader error, not a product failure.
- An additional profile test exposed the same three fixture errors on the unchanged primary baseline. The synthetic input-ready callback omitted its required requestId. Supplying the actual START request correlation fixes this fixture; all 5 profile tests pass.
- The native helper is ES5 parsed. Source diff checks pass. The qwen launcher change is only the digest of a proposed 13-entry manifest whose sole changed entry is native_bridge. No ASR/model restart is needed for this source repair.

The two local text checks used reconstructed snapshots, one model request each, no speech or ServiceNow requests. They do not prove full Voice behavior. The spent public v1.2 qualification had successful media, exactly-once input delivery, full backend PCM and cleanup, but no positive grant/store/worker inclusion proof. Post-call alias changes are a separate observed seam; they do not establish the exact call-time failure. Fresh coordinated Bot/Native-only activation and a new bounded qualification are still required. Preserve all nine model/gateway/ASR/TTS generations. Physical-device hearing and external-network acceptance remain open.
