# Planner generation and validation consistency

Root-ratified under the user's delegated design and full implementation instruction. BASE `903e06815d54458f8e6fb5ba4b88816176930221`. Independent measured diagnosis `task21-admission-measured-diagnosis.md` SHA `c3d013763646348d681bd72ec6961eca5a105f82da7f0cf7de98a63787bfc770` proves that C21 sent a schema permitting answer/none/nonempty-evidence/none, then correctly rejected that model response. That fourth terminal inconclusive experiment remains consumed and unchanged. The source defect is reproducible without inference.

Root chooses two complete disjoint object branches in a root `anyOf`, preserving the existing four-field wire representation. The alternatives are exhaustive complete-plan enumeration (too large at twelve refs), a wider representation change, and another instruction or response repair (does not resolve the contract mismatch). Design evidence: TASK/task22-planner-schema-design.md SHA `35ce0f029305abd3f77574cd9e201300fffbce9445246ec7cf77bc04a8ed534f`.

## Exact change

Only the schema construction in `GroundedAnswers.plan.prepare` changes in production. Root is `{'anyOf': [answer_object, nonanswer_object]}`. Each branch independently has type object, additionalProperties false, the four required keys, and its complete properties. Preserve property order outcome/form/evidence/gap and answer-first branch order.

| Field | Answer object | Nonanswer object |
| --- | --- | --- |
| outcome | const `answer` | string enum `insufficient`, `needs_business`, `ambiguous` |
| form | string enum `state`, `change`, `current_question`, `queue`, `attributed` | const `none` |
| evidence | array minItems1/maxItems4/uniqueItems true; string items enum of all request evidence refs in original order | const empty array |
| gap | const `none` | string enum of all existing GAPS keys in original order |

Do not add shared object constraints beside anyOf: the pinned converter does not intersect them there. Do not restrict the existing nonanswer outcome/gap cross product. No fixed ref, phrase rule, inferred form, output repair, new helper framework or semantic shortcut. The unchanged authoritative local decoder rejects invalid refs, duplicate refs, keys/types and combinations; renderer/provenance/publication checks still determine useful safe output.

Actual tagged b10690 C++ converter supports union, const, closed objects and min/max array cardinality. Source SHA `4d58b73438e97ac4e2d11dbb0309702d6899088d3c44a75a2dcb9c57697bb288`, 52894 bytes. This is source support evidence, not executed binary-language equivalence. `uniqueItems` is unsupported by that GBNF path; keep it in the intended schema and keep local uniqueness validation. [Pinned converter](https://github.com/ggml-org/llama.cpp/blob/b10690/common/json-schema-to-grammar.cpp#L855-L981), [pinned limitations](https://github.com/ggml-org/llama.cpp/blob/b10690/grammars/README.md#L120-L198).

## Tests and dependency boundary

Use independent `jsonschema==4.26.0` as an explicit test-only requirement in new `voice/native-bridge/requirements-test.txt`. Include short setup comments there. Install with NativePython `-B -m pip install --no-compile --target` into a new ignored SDD/task22-test-deps directory; record resolved versions and package hashes in supplementary evidence. Do not mutate the operational venv or runtime requirements. Test commands set PYTHONPATH to the supplementary target. Import Draft202012Validator locally inside the new test methods; full developer discovery requires test dependencies.

Extend existing `test_grounded_conversation_integration.py`; capture actual emitted wire schema through existing real preparation/loopback transaction fixtures. Before production edits, demonstrate independent-validator RED rejecting the measured invalid combination. Check schema validity and an independently specified outcome/form/gap/evidence matrix against both emitted schema and unchanged local decode. Include all five answer forms, all fifteen nonanswer combinations, empty/nonempty/duplicate/unknown/wrong-type/over-four evidence, distinct catalog requests, allowed ordering, absent/extra keys and invalid enums. Assert invalid raw model responses remain locally rejected. Retain the existing real transport/binding/attribution/no-write assertions; replace its obsolete flat-schema maxItems assertion with independent behavioral schema checks. No handwritten schema walker or prompt-recognizing fake.

Run the new focused tests RED then GREEN and covering grounded integration, token admission and reserved-slot tests once after final edits. These source/controlled-transport tests are not model semantic GREEN. No broad unchanged-native repeat is required for this bounded schema change; final integration/phone verification remains outstanding.

## Preserved boundaries and delivery

Prompt/catalog/decode/validate/render/contract hash, authority, Store/coordinator, release/latches and evaluator remain unchanged. Planner3072/128, classifier3584/24, two4096slots/8192parallel2, original absolute2s, frame16384, Main32768/1 and reserve18GiB remain. No live service, instance, model, template, profile or support change. Preserve every foreign dirty/index byte.

Commit only production file, existing test file, test-only requirements, this Rootspec and the Task22 plan appendix. Produce actual report, exact patch and RED/GREEN evidence. One independent combined Product-quality/actual-RAW review precedes a separately authorized new source/configuration chain. Any future inference needs a fresh finite prospective source GO, current exclusion of all four predecessor owners and unchanged semantic admission/drain/184/coexistence/Native/Desktop/iPhone gates. No model replay or next-stage authority follows from this specification.
