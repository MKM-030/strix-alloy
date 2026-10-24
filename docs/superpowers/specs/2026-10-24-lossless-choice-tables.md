# Lossless closed-choice context tables

Root-ratified24October2026 under the user's delegated design and implementation instruction. This is a new source design, not model qualification or permission to repeat the consumed Task17 admission reservation.

## Problem and choice

The actual Task17 admission result `1fd5edbe0ec1cf0d690df6d953d02df07e8c1a1d9ca62cce072e31c12366d7aa` ended inconclusive: the first3146-input-token classifier request produced no response bytes within the original2s. Process cleanup succeeded. This establishes a failed deadline for that implementation; it does not distinguish cold initialization, prefill, decode or backend waiting. Its reservation and evidence remain terminal and unchanged.

Three approaches were considered. Additional timing instrumentation can locate a later bottleneck but by itself cannot reduce the workload. Explicit startup prewarming may help a cold path, but the current evidence does not establish that as the cause. Lossless table encoding removes repeated JSON keys on every request and preserves the existing semantic and authority contract. Root selects the latter source change first. No speed claim follows from byte reduction. Later model testing must be a separately reviewed prospective implementation/campaign, with the earlier failure preserved and the unchanged2s user-turn deadline.

An input-only spike on the public maximum8-task/16-agent/70-option fixture roundtripped exactly and reduced context7915→6046UTF8bytes and payload11790→9689bytes. Those values omit the final marker and are not final implementation measurements, token counts or performance evidence.

## One serialization boundary

Keep `ProposalContract.model_data()` as the sole production context builder. It first constructs exactly the same canonical facts as before and then encodes repeated collections. No runtime legacy/new-format switch, second serializer, decoder, cache, alternate prompt or retry is introduced. Keep `PRODUCTION_SYSTEM_PROMPT` byte-identical, and preserve the choice schema, ordered options, IDs, decoding, policy snapshot, candidate generation, target binding and durable acceptance.

The fixed descriptor is `context_format: "route_proposal.columnar.v1"`.

- `task_columns` is exactly `["task_ref","agent_ref","details"]`; each task is `[task_ref,agent_ref,details_dict]`. Details retains every canonical task key/value except the two ref keys. Preserve missing versus null, empty string, false, all text bytes and future canonical detail fields. Never default or normalize details.
- `candidate_columns` is exactly `["candidate","intent","task_ref","agent_ref","question_relation"]`; rows contain those values in that order. Only the three optional generated candidate fields encode absence as `""`. Present refs and relation are nonempty in the current canonical builder; reject unsupported candidate keys or present empty optional values instead of silently losing information. Mandatory fields are always retained. Local-only candidate exclusion and all resulting ID gaps remain unchanged.
- `agent_columns` is exactly `["agent_ref","alias","name","description","routing_aliases"]`; each row contains all five existing fields, including empty values and ordered alias lists. Reject unsupported canonical agent fields instead of dropping them.
- Preserve all other semantic context keys/values, including scope, question_task_ref, option_columns and every option row/order. No pruning, authority-bearing additions, shortened/translated strings or changes to task/agent limits.

All descriptors are ordinary JSON data. Strings resembling instructions, table delimiters, message roles or choice objects remain data in the same system/user envelope. Structural isolation tests are not a model prompt-injection guarantee.

## Unchanged operational limits

Actual context cap12000UTF8bytes, body and both complete request frames16384bytes, classifier3584input/24output, planner3072/128, one Conversation8192/2 with4096perSlot, classifier0/planner1, Main32768/1, reserve18GiB. The same prepared payload/catalog is counted and sent, with the same hashes and original absolute2s including preparation/count/inference/validation. Same-role unresolved ownership stays latched. No extra model request, filter, token estimate, timer, fallback representation or output authority.

## Source slice and verification

Task19 first changes Product only: route_proposal.py; a new focused test_route_proposal_wire.py; direct wire-reader assertions in test_responsive_semantic.py, test_token_admission.py and test_grounded_conversation_integration.py. test_unified_routing_policy.py may only update an over-limit fixture if compression makes its old fixture genuinely fit; preserve the zero-send and actual cap assertion. Other application/runtime/Consumer/profile/Store files remain outside this slice.

Before the source change, capture a failing explicit version/column/row contract test and the independent old system-prompt UTF8 hash. Independent test-only decoding must reconstruct hand-authored canonical expectations, not call the production encoder as its oracle. Cover all optional-presence distinctions, Unicode/whitespace/injection-shaped strings, current/previous/no question relation, nonconsecutive candidateIDs, sequence order, empty agent fields and unsupported-field rejection. Repeated model_data calls and mutation of returned containers must not alter the frozen contract or later results.

Strengthen the existing public8/16/70 transport fixture to cover every fact and option, retain the separate grounded-enabled70-option fixture, and verify all three forwarding APIs agree. Retain body identity/count usage checks, catalog/payload hashes, exact token rejection, complete frame boundaries, reserved slot0 and existing timeout/cancellation tests. Run the new wire suite plus closed-choice, responsive semantic/router, unified policy, token admission, grounded integration and reserved-slot suites. No broad native rerun merely for logging; the final Task7 release suite remains required after final changes.

## Later framework and qualification boundary

The separate public PREP fake readers identified by `task19-wire-design-impact.md` require descriptor-aware conversion before a future new-source fake integration: v4_pinned_child.py; test_task18_driver.py; test_closed_choice_preparation.py. Their implementation is a separate bounded support migration after the Product slice review. Existing historical snapshots and their fixtures remain untouched. Do not run the old full-chain snapshots against new-only fake readers or alter consumed records to obtain a pass.

New actual source bytes require a fresh truthful source/commit/review applicability binding, support migration, complete new artifact/dependency maps and explicit Root authorization. The existing reviewed_tasks12..17 stage and its Task17 row may be used only with an independently reviewed derivation that actually covers this source delta and commit; no review-string substitution. A prospective source-version campaign must name and preserve the prior failed result. No184authoring, inference, runtime/profile change or new reservation is authorized here. Whole-branch review, actual model qualification, current readiness and physical iPhone evidence remain required.
