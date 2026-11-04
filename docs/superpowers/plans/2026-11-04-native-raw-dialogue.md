# Native raw dialogue repair implementation plan

Goal: restore lossless raw caller input to the one ServiceNow conversation while keeping asynchronous local conversation governed by current assistant settings.

Scope: only native_duplex.py, conversation_repair.py, servicenow_voice_context.py and related tests/design. Existing browser worktree reused; browser agent owns native_bridge.py, assistant_settings.py, JS settings and voice mapping. No runtime/SDK/auth/model/Voice operations. Root owns later three-utterance acceptance without name/order approval.

The pre-Duplex path forwarded original text once to Dialog.turn. Restore that FIFO contract; local conversation and context acknowledgements never consume it. ServiceNow owns name validation and business confirmation. Keep generation, request, callback settlement, uncertain-send no-replay and narrow stale native-confirmation protection.

1. Add failing regressions: name/free/digit/correction text enters FIFO without local name readback; early intent remains pending after bootstrap; busy fallback is short and preserves input; actual native confirmation remains onset/request-bound; configured prompt and emitted dialogue history reach context.
2. Simplify acceptance/queue/bootstrap settlement. Remove mandatory local name/readback/spelling/correction workflow. Keep raw FIFO and one active backend request. Do not retire raw FIFO items based on separate context-prompt uptake. Keep uncertain-delivery terminal behavior.
3. Carry validated CallSettings presentation systemMessage/language into conversation; remove static SDK/A2A/demo facts. Keep immutable business-authority/evidence boundaries. Add bounded complete emitted assistant replies as scoped dialogue evidence, excluding queued/interrupted candidates.
4. Answer ordinary questions in context rather than forcing the current name question. Keep only short truthful feedback when the local model is unavailable/busy; no synthetic result or retry.
5. Run focused and complete relevant offline tests. Revise tests whose mandatory local name-state behavior is intentionally superseded; preserve native confirmation/replay/output ownership coverage. Review and commit only owned paths.

Success: exact input is delivered once in order; no synthetic name/approval step; early intent is not stranded; stale bare approval cannot bind to a future native question; configured presentation and complete emitted context are visible without developer demo pollution. Offline checks do not certify actual runtime behavior.

Implementation notes:

- The restored native ServiceNow greeting remains authoritative, including its configured employee-name question. This repair removes only the local extra readback/spelling/yes workflow.
- Native polar confirmations bind pure answers (including Okay/in Ordnung/verstanden) to the complete current emitted question, request and onset. A later local question cannot approve an older native question. Mixed corrections and ordinary utterances remain unchanged.
- Optional emitted-speech history is budgeted after current public/processing observations and capability limits; the final 10000-character/32768-byte snapshot contract remains unchanged.
- Configured systemMessage has an explicit local consumer limit of 8000 characters (maximum combined seed 9524, below the existing 10000-character seed limit). Oversized settings make only the optional local conversation unavailable; they are never silently truncated. The native settings contract can admit longer prompts, so this remains an integration limitation.
- Independent source review found the snapshot-overflow and stale-Okay cases above. Both were reproduced with failing tests and corrected. Reviewer reran49 raw/name/confirmation tests successfully and found no open blockers. No live behavior or physical-device parity is certified by this review.

Final offline verification:

- Native discovery with the existing Voice venv and existing local test-deps:1220 tests in196.057s;1219 passed. The one failure was in unchanged test_token_admission.test_count_and_inference_share_absolute_deadline (only one request reached the fixture within its140ms absolute deadline, rather than two). No deadline was relaxed.
- Immediate focused run of the complete token-admission module plus all NativeDuplex, name, confirmation, static-help and metadata-publication modules:152 tests in9.831s, all passed. This includes the formerly timing-sensitive case unchanged.
- Earlier expanded context/binding/grounded/history/profile suite:94 tests passed using existing local test-deps; no dependencies installed.
- git diff --check passed. Root owns the final combined-source run, deployment and bounded natural-dialogue acceptance. No live SDK, authentication, Voice or lifecycle operation was performed by this implementation task.
