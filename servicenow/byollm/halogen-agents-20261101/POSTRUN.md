# Halogen Agent delta: partial-run audit

The approved maintenance run is terminal and partially applied. **67 of 68 intended source changes are correct; the Ledger remains unchanged. The WIP delta is not ready for transfer.** Runtime and iPhone acceptance remain separate and open.

The later completion was explicitly approved and sent once. The SDK returned `The instance did not return a script execution response`, with no inner result, execution-history ID or rollback ID. No second copy was sent. Fresh full readbacks confirm all 68 source rows, all three headers and all 68 Customer Updates remain exactly equal to the frozen pre-run state, including revisions. All 21 guards and both ES companions are unchanged; the complete staging-name query returns zero rows, as does the completion-marker history query. These observations establish no observed configuration change; they do not by themselves prove native execution never began.

Read-only SDK access to the authenticated script form and CSRF endpoint succeeds. The failed request's form encoding was 2,948,295 bytes, compared with 1,009,379 bytes for the earlier successful admin request. The newest native transaction returned the same 2,347-byte length as the empty script form, recorded only 40 parameter bytes, and ran no Business Rules. A form-size/parameter-parsing failure is a strong inference; the actual instance limit has not been exposed or changed. A lossless compact representation is now frozen privately as `complete-halogen-agent-configuration.compact.js`, SHA-256 `d4d05aff4562b9918d3613aa100a3b1aa4ec670b58723da5a6b2949aa6f4a819`: 377,631 bytes, calculated full form 598,943 bytes. Exact reconstructed JSON text and unchanged execution prefix/suffix are verified, with 32 passing offline tests and independent review. Private `EXECUTION-REVIEW-COMPLETION-COMPACT.md` links the full new file, original readable source/plan and exact parameters. It has not been executed; separate approval is pending.

## Verified instance state

The administrator-maintenance script ran once with native execution history `30e120a993dcd314e7f2b9fa6aba10fd` and rollback context `b0e120a993dcd314e7f2b9fa6aba10fc`. Its frozen SHA-256 is `6fbeab7c5b99bf02c53e886c5c432d1e1806c09645dcd96a11c54a76c6bb2dd9`. The SDK envelope reported `ok:true`, but the script's own result reported `ok:false`, `partial_or_uncertain` at transformer capture verification. No second run was started.

Authoritative post-run reads establish:

- All 66 active, published prompts across the four reviewed capability graphs have exactly `halogen-v2`. All other queried prompt fields match their preimages, apart from expected revision metadata.
- All five inactive prompts are unchanged.
- The Halogen request transformer is byte-exact against the approved desired source: SHA-256 `99cb5d8733faca9955ec274f21dc4b5f46f0b2c4159cbb63b9c5954bf85c4e58`.
- `LocalLLMReActExecutionLedger` still matches its original source. The approved desired script, SHA-256 `8d1a900054b03a504cd9cdbf2144037e4c34d1d1eaa6fd1c62f9ab5faa014f4d`, was not attempted.
- All 21 guards match their frozen preimages, including the three false Prompt Mirror gates, model registrations, definitions/defaults and both script-language companion records.
- The original current Update Set `83c415cb933fcf14e7f2b9fa6aba10de` was restored.

These are configuration checks. They do not establish inference, Agent consumption, phone audio or business success.

## Why capture verification stopped

The actual native Customer Update's raw CDATA contains the transformer with every carriage return removed. Its text equals the stored source with `\r` removed, exactly. This differs from XML 1.0 newline normalization for the frozen source's `CRCRLF` sequences.

An offline Acorn ES5 AST comparison established equivalent syntax trees for each of the two frozen code fields before and after this observed serialization. Neither contains a standalone carriage return outside a run immediately preceding LF. The native CR-removed hashes are:

| Field | Native serialized SHA-256 |
| --- | --- |
| Halogen `request_transformer` | `6e23750a5df2ba87e9a1b1498290286010d509bea1ab672472a5b6cf849b93d0` |
| Desired Ledger `script` | `911105ce3c7a57305154eae80b29658db9f399eadf0597b4a102c076869c7580` |

Source-record comparisons must remain byte-exact. Any native capture allowance is restricted to those exact two frozen JavaScript fields and hashes. Do not trim text, collapse line runs or apply this exception to prompts, guards or other fields.

## Current batch findings

**Custom LLM Platform 2.3 - Halogen Agent Delta - NO DELETE 20261101** is separate from the sealed 2.2 Fresh Instance delivery.

| Header | Instance ID | Required application |
| --- | --- | --- |
| Parent | `4de124e993101714e7f2b9fa6aba1079` | Global |
| Global child | `09e124e993101714e7f2b9fa6aba107c` | Global |
| AI Agents child | `89e124e993101714e7f2b9fa6aba1097` | `sn_aia` |

Fresh header reads show all three currently have application `sn_now_assist_code`, inherited from the session despite the original Secure setter assignments. Their names, hierarchy, descriptions and WIP state remain intact. The scope error must be corrected before this delta is a usable transfer.

The batch currently contains 68 unique Customer Updates: 66 prompts, the Halogen transformer and one native AI metadata signal. The Ledger capture is missing. The signal's wrapper is in the AI Agents child despite its Global application. It is `sys_gen_ai_control_setting_data_32ee2ed0fff53210c3fcffffffffff09`, Customer Update `ede164e993101714e7f2b9fa6aba1011`. Native processing created it; it is not an extra hand-authored configuration assignment. Its captured `true`/revision 313 has already been consumed/reset to live `false`/revision 314 by background processing. Never assign its live value or delete its capture to force the original count.

The native Business Rule **Prevent application inconsistency** refuses an application change on a nonempty Update Set. **Handle updates moving between sets** requires each moved Customer Update to match its destination's application and maintains native version associations. Both rules must remain enabled. A correction therefore needs a scope-correct temporary holding set for the 66 AI Agents updates while the original children are empty; the empty parent can hold the two Global updates. A temporary set must end empty and ignored, with no deletion.

Expected final source/capture census, only after a verified completion: 68 intended sources, 69 unique no-delete Customer Updates including the one native signal; 66 in AI Agents, three in Global, none in the parent. Preserve the signal's identity, action and payload when moving its wrapper. Preserve all existing run artifacts and rollback contexts.

## Bounded completion and remaining acceptance

Prepare a new completion script against this exact partial state. Freeze the 67 desired source records and their revisions as read-only preconditions, the Ledger's original preimage, all 21 guards, both ES companions, all headers and all 68 current Customer Updates. Correct only the reviewed capture/header membership, then write and natively capture only the already-intended Ledger script. Keep normal Business Rules and native rollback recording. Reject drift, unexpected membership, deletes or changed payloads. Restore the current Update Set in `finally`.

Neither prior frozen script accepts this mixed state. Do not retry them or blanket-roll back correct changes. The new script requires its own concrete per-run SDK approval. The original and admin approval/run evidence must remain immutable.

The first one-shot completion is preserved privately as `complete-halogen-agent-configuration.js`, SHA-256 `6ec46a1827df35ff6e4deb6c2ccf961a70dfc8b969aafefb681debeabb1fe3b1` (2,393,573 bytes). Its builder, template and 22 passing offline tests are retained in this directory. Root and an independent reviewer checked the capture movement, scope rules and both native parent/base membership checks. Its later approved request failed as described above. The frozen review, attempt and SDK result remain unchanged; do not retry or rebuild this file. The separate post-run verifier has 13 passing fixture tests. Private `COMPLETION-RESPONSE-FAILURE-AUDIT.json` and the fresh readbacks record the observed unchanged state.

No model/service startup, inference, microphone/audio or business operation occurred during this maintenance. The retained model lock, original memory recovery threshold and pending RAM response remain in force. After actual runtime readiness, physical iPhone own-voice/name/spelling/noise/interruption/repeat-call acceptance and one genuine source-bound ServiceNow context/progress sequence are still required.
