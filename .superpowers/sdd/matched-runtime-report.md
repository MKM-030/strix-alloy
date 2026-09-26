# Matched AR/MTP runtime implementation report

Date: 2026-09-26. Base: `f0f462e866fd57554fe8dd387e57b71345b154d2`.

## Scope and contracts

Implemented the fixed 36-request paired AR/MTP profiles on the existing Guardian and sequential HTTP suite. No GPU run, model load, source/binary/settings change, qualification creation, or network request was made. The accepted margin report hash was independently checked as `49433BB54E71F7F27418FEC63E71DA98F4C372F31E19E6A95292E21148874344`; the native response contract hash was checked as `820F53B9D454A58D641283FE8C1383F3891C2F75E9CE859F903F25BEC5D3D3F3`.

The two profiles share the pinned historical 36-request manifest, AR4k result and semantic acceptance. AR retains 68/4/20 GiB. The new matched MTP profile uses 72/4/20 GiB, commit charge 76 GiB and fresh commit headroom 88 GiB. The earlier staged MTP profile remains 71/4/20 GiB. The accepted response contract is encoded by `matched_validation.RESPONSE_CONTRACT_SHA256` for review traceability; the report itself is not a new runtime artifact or qualification.

## RED and GREEN evidence

Environment for commands: `PYTHONPATH=C:\Projects\strix-alloy-research\integration\scripts;C:\Projects\strix-alloy-research\integration\tests\gufo`, Python `C:\Users\Marcel\AppData\Local\Programs\Python\Python312\python.exe`.

- RED: `python -m unittest discover -s tests/gufo -p 'test_matched_*.py' -v` failed with expected imports of missing `matched_profile` and `matched_validation` (11 tests, two import errors).
- RED: `python -m unittest discover -s tests/gufo -p 'test_matched_suite.py' -v` failed with `start_suite() got an unexpected keyword argument 'recipe_provider'` (four tests, five subtest errors).
- RED: `python -m unittest test_matched_profile.MatchedProfileTests.test_guard_routing_and_cross_profile_latch -v` failed with `unknown_profile` from old guard routing.
- RED: the later native-snapshot/summary classification tests failed with missing `invalid_cache_snapshot_bytes` and `transport_failed` as expected.
- GREEN: `python -m unittest discover -s tests/gufo -p 'test_matched_*.py' -v` ran 28 tests, `OK`.
- Full offline: `python -m unittest discover -s tests/gufo -p 'test_*.py'` ran 355 tests in 41.292 seconds, `OK`.
- `git diff --check` found no whitespace errors.

## Files and behavior

- `scripts/gufo_control/matched_profile.py`: exact profile paths, experiment identity and MTP argv; derives the checked AR predecessor/acceptance from the existing 16k pins.
- `scripts/gufo_control/matched_validation.py`: exact native draft, prompt, output, cache, lookup, concurrency and model checks. It keeps quality failures separate from fatal evidence errors and records compact provenance and 256-token eligibility.
- `scripts/gufo_control/benchmark_guard.py`: routes only the two new IDs to matched pins, argv and private suite hooks. Original IDs retain their existing route.
- `scripts/gufo_control/benchmark_suite.py`: optional recipe/request/assessment hooks; validates the final request before the sole POST. Native-valid poor-quality rows are persisted and later rows continue; fatal responses are persisted and the rest remain `not_run`. Matched summaries label quality-eligible aggregates, while raw row timing remains available. LONG draft-path and accepted-token coverage uses all native-valid LONG rows; correct sustained 256 rows are separately identified. The original suite's result shape remains unchanged.
- `scripts/gufo_control/smoke_store.py`, `smoke_policy.py`: fixed allowlist, exact new bounds/paths/margin/sidecar/experiment binding, global latch participation, and one shared pure bounds selector.
- `tests/gufo/test_matched_profile.py`, `test_matched_validation.py`, `test_matched_suite.py`: binding/admission/qualification, native evidence edge cases, and 36-row offline fake suite progression.

## Review notes

The full offline suite proves the local control flow and regressions, not live throughput or safe placement on this machine. An independent diff review is still required before the parent creates exact qualifications or starts either GPU run. The suite does not derive aggregate common-window decode throughput. A correct-useful throughput comparison must use quality-eligible matching rows and the raw HTTP/engine timing fields; draft-path coverage alone does not establish speedup.

## Independent review follow-up: malformed nested native shape

The reviewer found that a nonempty list or string in `usage.gufo` could reach `matched_validation.assess` after transport validation failed. The validator's `.get` raised before `_persist`, leaving the attempted row `not_run` and omitting the raw artifact. Direct inspection confirmed the same access pattern for non-dict `usage`; adjacent `prompt_tokens_details` and `timings` were checked in the focused regression.

- RED: `python -m unittest test_matched_validation.MatchedValidationTests.test_non_dict_native_sections_return_fatal_errors test_matched_suite.MatchedSuiteTests.test_malformed_gufo_is_persisted_then_stops -v` failed: list/string `usage.gufo` raised `AttributeError` at `matched_validation.py:96`; non-dict `usage` raised at line 16; suite assertions found attempted row `not_run` with no artifact.
- Fix: record `native_counters_missing` from the raw section shapes, then read fields through local safe dict views. `observation` and its raw nested values remain unchanged for persistence.
- GREEN: `python -m unittest test_matched_validation test_matched_suite -v` ran 16 tests in 0.963 seconds, `OK`. The suite regression verifies one attempted failed row, the exact raw malformed `usage.gufo` in its artifact, and 35 later rows `not_run`.
- This follow-up ran only the two affected focused test files. The prior 355-test offline run remains the baseline for the original commit; it was not repeated for this narrow fix.

## AR SSE identity correction and distinct rerun profile

The attempted matched AR v1 warmup in `gufo-matched-ar4k-v1-runs/20260926T211821Z-6c62ce30e4ba4c32998c7e71a04c2768/request-000.json` returned HTTP 200, answer `4`, valid native counts and four identical `gufo-flash-next` model IDs, one per SSE event. Its only suite error was the matched assessor's singleton-model check. The existing HTTP transport already accepts a nonempty model list when every entry matches the requested alias. No v1 marker or evidence was changed.

- RED: `python -m unittest test_matched_validation.MatchedValidationTests.test_repeated_sse_model_aliases_from_ar_warmup test_matched_profile.MatchedProfileTests.test_ar_v2_is_distinct_fixed_identity_with_same_requests -v` failed with `identity_or_reasoning_invalid` for four correct aliases and missing `PROFILE_AR_V2`.
- Fix: require a nonempty list whose every entry is exactly the pinned alias; keep empty, wrong and mixed aliases fatal. Add `matched4k-iq4xs-ar-v2`, `gufo-matched-ar4k-v2-runs`, and `gufo-matched-ar4k-v2-qualification.json` to the existing fixed recipe/profile/store/guard routing. V1 and MTP v1 identities, roots, limits and qualifications remain unchanged. The new root participates in global incomplete-latch exclusion.
- GREEN for the two RED tests: 2 tests, `OK`.
- Read-only replay: the updated assessor over all 36 preserved AR4k benchmark v2 `request-000.json` through `request-035.json` at `gufo-ar4k-benchmark-v2-runs/20260926T183712Z-b77b8ac01bb54275aa4786db89478a69` found `fatal_rows=[]` and `quality_failed_ordinals=[]` using the matched AR v2 definition and pinned counts. Replaying the failed matched AR v1 warmup yielded `errors=[]`, quality `passed`, four matching model aliases, answer `4`. No artifact was rewritten.
- Scoped regression: `python -m unittest test_matched_recipes test_matched_profile test_matched_validation test_matched_suite test_smoke_store test_smoke_policy test_benchmark_guard test_benchmark_runtime test_benchmark_suite` initially ran 97 tests with two failures because an old test assumed the v1/MTP qualifications were absent; the files had since been created. That test now simulates the missing-file read. The same command then ran 97 tests in 7.041 seconds, `OK`.
- No model call, qualification creation, marker reset or broad suite rerun was performed in this follow-up.
