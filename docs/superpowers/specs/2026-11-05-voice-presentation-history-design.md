# Own SCC conversation presentation history, v2 design only

This is a source/saved-artifact assessment of Root's narrower alternative. It supersedes v1 only for the proposed scope: conversation history, not feedback claimed to belong to the current native task. No implementation or native operation was performed.

## Assessment

The bounded history variant is reasonable as advisory conversation presentation. A history item says only that this local assistant text completed host PCM emission during this owned conversation. It does not say the user heard it, that it answers the current native question, or that any business fact, confirmation, result or workflow step is complete. A native current-task/request join is therefore not needed to describe this history honestly, and must not be implied.

It can help the SCC model generate a short next response without a repeated preface. It cannot guarantee the absence of repetition. Every genuine resulting backend output still passes unchanged through its existing event receipt, control, queue, synthesis and drain path. There is no local semantic suppression, shortening, deduplication or backend event retirement.

The present late-consumer is an SCC ReAct planner prompt, not a separately isolated prose renderer. Additional text can influence model generation and potentially action selection. Explicit style/data provenance is useful but is not a hard information-flow or security proof. Preserve all existing business authority, original input and confirmation protections, and qualify the behavior with mandatory-question/result counterexamples before claiming improvement. If hard isolation from planning is required, the current seam is insufficient; a separately established own presentation-only stage would be needed.

## What remains mandatory

Own usecase policy must explicitly say that presentation history never satisfies, skips or replaces a current required question, name/spelling confirmation, full current order summary, separate explicit order approval, correction, error or final result. Those must be produced from authoritative ServiceNow state even when similar text appears in the history. Local text is never a user response, consent, trusted data or tool observation. Prior or partial local speech never becomes confirmation of any later question.

Treat every quoted history string as untrusted data. Delimit it separately from business facts, tool history and native conversation memory. Use bounded escaped JSON, including escaping tag delimiters, so content cannot close the surrounding block. Structural escaping is not itself a semantic injection guarantee. Do not expand local output validation into fuzzy backend suppression.

## Minimal own changes

1. `voice/native-bridge/native_duplex.py`: at the existing full host-emission boundary, capture an immutable history item only for genuine local `conversation` output. Preserve the source lease's epoch/generation and actual originating turn, rather than relabeling it with current state. Exclude backend output, configured welcome, native control/question, confirmation acknowledgement, partial speech and interrupted output. Queue the optional publication asynchronously; never block audio or ordinary input.
2. Add one separate optional history-publisher method to `Dialog` in `native_bridge.py`, and a narrowly validated internal history route in `voice/bridge.py` using its existing cookie/CSRF-owned session. Do not change `nativeInput`, original `message.text`, greeting history or the vendor MESSAGE envelope. The session supplies the established CREATE/conversation/provider binding; it never accepts another caller's conversation.
3. Extend only the own context resource with a disjoint versioned `presentation_history_store` operation under the existing token authorization. Existing raw caller-note schemas remain exact. Validate the token, fixed provider/profile and actual CREATE/account/channel-profile/consumer/interaction/user/session chain through ordinary secure reads; reject closed/foreign conversations, ambiguous aliases, changed validated bindings, unknown fields and oversized metadata. The service ID is fixed route metadata, not an independently read current service/usecase-record relationship. Consumption remains behind the existing exact SCC/model/AI-config/agent-name gate. No USER/SYSTEM/assistant memory messages are created for history.
4. Store separately through the observed `sn_cs.VASystemObject.getProviderUserContext(key, appInboundId, userId, null)` / `setProviderUserContext(key, value, appInboundId, userId, null)` primitives. Derive the provider-user key from the verified existing chain. Call primitives directly from owned code: the native VABotToBotUtil wrapper logs values. No new table/column/ACL, whole-plan-context update or native role is necessary.
5. Extend the existing own SCC request-transformer/helper seam after its exact SCC/model/config gates. Securely derive the same provider-user identity using ordinary readable conversation/account/profile/interaction fields and current-user binding. Read only the finite own namespace. Return a separate typed `local_presentation_history` block outside authoritative business memory. Unrelated/vendor prompts and all response/action schemas remain byte-for-byte unchanged. The configured own usecase supplies the limited presentation rule; do not edit a global generic prompt or vendor definition.

## Finite event and storage contract

Each item carries a fixed version/type, `local_output_state=host_emitted`, producer owner, sequence, unique output event ID, exact local output text/SHA-256, caller turn ID and original ASR SHA-256 where actually known, source task revision, output epoch, playback generation and positive matching accepted/emitted sample counts. Preserve actual identity formats. These fields are provenance, not a native current-task join.

An exact host-known business request ID may be included only if a real accepted-request mapping already exists. Otherwise use explicit unavailable/null provenance. Never use the latest business request as a substitute. This variant does not require implementing nativeInput v2 or fabricating a native `_meta` field.

Use at most 16 separately keyed events per conversation, no cyclic reuse and no mutable cumulative/latest overwrite. The local single-writer claims every attempt before I/O and does not replay uncertain delivery. The resource reads an existing slot before writing; exact conflicting content disables the optional lane. The observed native setter has no established compare-and-set contract, so describe this as write-once-by-protocol, not an atomic immutability guarantee. Any conflicting/mixed-owner slots are unavailable to the consumer. They never affect business state.

The consumer reads only a bounded recent subset, at most three items/4,000 total Unicode code points, from finite own keys, ordered by sequence. Per-item text must be nonblank well-formed Unicode, at most 2,000 UTF-16 code units and at most 8,000 UTF-8 bytes; this permits1,000astral characters but rejects1,001. The stricter UTF-16 bound also keeps default ensure_ascii JSON with full metadata within the existing16,384-byte local body limit. Server expiry uses ServiceNow time recorded at store; host monotonic times must not be compared with native wall time. A short freshness window is a UX retention policy, not current-request proof. Expired, malformed, denied, ambiguous or unavailable history is omitted and genuine backend delivery continues normally. Exhausting the finite budget disables optional history without failing the call.

Store acknowledgement means only exact metadata readback. Prompt inclusion means only that exact typed history was present in that particular returned own prompt. It proves neither understanding nor hearing. The helper can return inclusion IDs/hashes and safe scalar diagnostics without creating short-term-memory receipts for this new type or requiring worker-side metadata writes. Never log answer text, raw prompts or credentials.

## No-write native preflight before implementation

Root can prepare one bounded read-only preflight, with no model call or current call required:

* Read exact current own REST resource, helper and SCC transformer identities/source/revisions through normal secure access; compare the known binding and current hashes. Confirm the original caller-note contract and exact SCC gate remain installed.
* Read the exact fixed app/profile/usecase and one already-owned saved conversation's normal ownership chain. Do not enumerate other users or use denied references. Only derive the provider-user identifier through normally readable fields.
* Confirm normal availability/signatures of the two observed public-named VASystemObject methods and, if ordinary access permits, invoke only the getter for one exact unused own namespaced key under that already-verified provider/user/conversation. Report only absent/type/size/hash and a bounded error classification. Do not call the setter, even with identical or empty data; do not update/capture any record.
* Check cross-scope behavior in the actual intended Global resource/helper environment without altering artifacts or impersonating. An SDK-current-user success is not proof of the dynamically masked worker's effective access. Record this remaining qualification limit explicitly.

The method signatures are observed in installed `VABotToBotUtil.native.private.js:23-36`; they are not invented new OOTB fields. Source/method presence and a successful getter do not prove setter rights, storage lifetime, atomicity, masked-worker access or final consumer inclusion. Those remain later bounded qualification checks after reviewed source exists. A denial is an ordinary unavailable result, never justification for ACL grants or bypass.

## Acceptance focus

CPU verification should retain all original input/controls/results and cover malformed/hostile history, wrong conversation/owner, unavailable request provenance, stale epochs used only as history, interrupted/partial speech, duplicate/conflicting slots, unknown delivery, bounded retention, getter/setter failure, unrelated-prompt preservation and mandatory name/order/final-output counterexamples.

The later limited Root-owned no-approval conversation should establish actual store/read/include provenance and whether the Q3 preface overlap improves, while proving all originals exactly once, configured welcome/own voice, full genuine native outputs and complete cleanup. This remains an experiment in conversational quality, not a claim that style metadata guarantees semantic correctness.
