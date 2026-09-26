# MTP4k stage implementation report

## Scope and implementation

Implemented the one-request native MTP profile on branch `codex/gufo-native-integration` from base `564ee5805e55eed13ec87e67cb2205beb59ff26f`. The MTP profile binds 71/4/20 GiB, the reviewed envelope hash, exact AR4k-v2 predecessor result and acceptance, and the fixed sidecar descriptor and stamp. AR profiles retain 68/4/20 and their original manifest shapes. The stage recipe pins the entire canonical request, 243-byte complete rendering and source revision; qualification carries the recipe and sidecar stamp. Store static recheck watches that stamp. The existing Guardian, source/binary/DLL pins, telemetry, and recovery were not changed.

The CLI has `status`, `print-only`, and `run` only. `run` injects the existing private Guardian with exact MTP argv and a worker using existing readiness, one-request transport, evidence persistence, cancellation and deadlines. The worker validates the request before the only POST and checks all required native MTP, lookup, cache, model, concurrency and structural bilingual response evidence. Manual bilingual semantic review remains pending. No qualification or live run was created by this implementation.

## RED and GREEN evidence

Command environment for all commands: `$env:PYTHONPATH='C:\Projects\strix-alloy-research\integration\scripts;C:\Projects\strix-alloy-research\integration\tests\gufo'`; Python: `C:\Users\Marcel\AppData\Local\Programs\Python\Python312\python.exe`.

RED 1: `python -m unittest tests/gufo/test_mtp_stage.py` yielded `ImportError: cannot import name 'mtp_stage' from 'gufo_control'`, `Ran 1 test`, `FAILED (errors=1)`. RED 2: `python -m unittest tests/gufo/test_mtp_stage_http.py` yielded `ModuleNotFoundError: No module named 'gufo_control.mtp_stage_http'`, `Ran 1 test`, `FAILED (errors=1)`. These were missing-feature failures before the respective modules existed.

Initial GREEN: `python -m unittest tests/gufo/test_mtp_stage.py tests/gufo/test_mtp_stage_http.py` yielded `Ran 5 tests in 0.007s`, `OK`. Expanded focused check: `python -m unittest tests/gufo/test_mtp_stage.py tests/gufo/test_mtp_stage_http.py tests/gufo/test_model_identity.py tests/gufo/test_smoke_store.py tests/gufo/test_smoke_policy.py` yielded `Ran 54 tests in 2.263s`, `OK`. A policy-boundary test initially failed because its synthetic host commit limit omitted the existing 16 GiB commitment; the fixture was corrected to 103 GiB for exactly 87 GiB headroom.

Full offline suite (once): `python -m unittest discover -s tests/gufo -p 'test_*.py'` yielded `Ran 322 tests in 40.603s`, `OK`.

Read-only CLI: `python -m gufo_control.mtp_stage status` returned profile `mtp4k-iq4xs-draft1-bilingual-v1`, 71/4/20 and 49/24/12 bounds, the fixed MTP argv and exact recipe. `git diff --check` produced no output.

## Changed files

- `scripts/gufo_control/model_identity.py`: bounded MTP sidecar descriptor identity.
- `scripts/gufo_control/smoke_store.py`: exact profile allowlist, provenance, qualification and recheck.
- `scripts/gufo_control/smoke_policy.py`: authenticated profile-specific demand.
- `scripts/gufo_control/mtp_stage.py`: immutable recipe, request proof, profile, Guardian injection and CLI.
- `scripts/gufo_control/mtp_stage_http.py`: one-shot worker and response validator.
- `tests/gufo/test_model_identity.py`, `test_smoke_store.py`, `test_mtp_stage.py`, `test_mtp_stage_http.py`: offline coverage.

## Self-review and concerns

Reviewed the diff for profile crossing, integer/bool equality, sidecar path escape and stamp recheck, qualification shape preservation, request mutation, duplicate POST paths, raw evidence handling and manual semantics separation. No GPU, model execution, HTTP request, telemetry, build, download, system setting, historical artifact or qualification was changed. The bounded descriptor pin authenticates layout/geometry rather than full tensor payload, as specified. A positive drafted-minus-accepted count is reported as unaccepted proposals, not rejection events; throughput remains request-local with no common-window claim. The parent must independently review code and bind qualification before any actual run.

## Consolidated review fixes (26 September 2026)

Fixed only the two Important findings in `reports/gufo-mtp4k-stage-code-review-20260926.md`. The MTP profile now records an immutable `(path, size, mtime_ns)` sidecar stamp when pins are created, before any freshness clock is sampled. `_binding` rejects missing or malformed stamp types, path, size, and timestamp without filesystem access; `expected_qualification` and policy validation use only that recorded stamp. `_verify_static` compares the freshly inspected descriptor's stamp to the recorded stamp, and `_recheck_static` compares both the manifest and live stamp to it. AR qualification record shapes remain unchanged. The response validator now rejects visible XML-style control tags and single-underscore emphasis, including underscores inside an emphasized phrase, without using language keywords.

All commands below ran from `integration` with `PYTHONDONTWRITEBYTECODE=1`, `PYTHONPATH=C:\Projects\strix-alloy-research\integration\scripts;C:\Projects\strix-alloy-research\integration\tests\gufo`, and `C:\Users\Marcel\AppData\Local\Programs\Python\Python312\python.exe`.

RED: `python -m unittest test_mtp_stage.MtpStageTests.test_recorded_sidecar_stamp_keeps_policy_validation_and_admission_pure test_mtp_stage.MtpStageTests.test_recorded_sidecar_stamp_rejects_bad_types_path_and_size test_mtp_stage_http.ResponseTests.test_rejects_visible_control_tags test_mtp_stage_http.ResponseTests.test_rejects_single_underscore_emphasis` produced `Ran 4 tests`, `FAILED (failures=4, errors=3)`. The no-I/O policy test failed on the live `operator_store.stamp` call; the control-tag and emphasis cases were incorrectly accepted. The malformed-stamp test initially errored because the recorded field did not yet exist. After making its RED assertion explicit, `python -m unittest test_mtp_stage.MtpStageTests.test_recorded_sidecar_stamp_rejects_bad_types_path_and_size` produced `Ran 1 test`, `FAILED (failures=1)` for the missing field. An added `_saved_copy_` emphasis probe also produced `Ran 1 test`, `FAILED (failures=1)` before broadening the structural pattern. A later malformed-`None` probe exposed `TypeError` before binding; validation was moved ahead of record construction so malformed input now raises `ValueError`.

GREEN: `python -m unittest tests/gufo/test_mtp_stage.py tests/gufo/test_mtp_stage_http.py tests/gufo/test_smoke_store.py tests/gufo/test_smoke_policy.py` produced `Ran 50 tests in 2.305s`, `OK`. This includes profile validation/admission/runtime with both `stamp` and `Path.stat` forced to raise; static verification and recheck rejecting sidecar drift; malformed recorded stamp rejection; and the forbidden visible-output cases. Full offline suite, once after final edits: `python -m unittest discover -s tests/gufo -p 'test_*.py'` produced `Ran 327 tests in 40.156s`, `OK`. `git diff --check` produced no output.

Self-review: inspected the focused diff for post-clock I/O, qualification shape drift, recorded-versus-live stamp gaps, path/type loopholes, response false positives, and scope. The policy path now uses no sidecar stat; static paths retain live stamp and descriptor validation. No Guardian, GPU, HTTP, telemetry, qualification, system, historical artifact, or source/binary changes were made. Actual native counters and bilingual meaning still require the parent's planned one-request run and manual review.
