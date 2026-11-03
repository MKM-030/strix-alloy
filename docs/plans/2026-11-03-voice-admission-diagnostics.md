# Admission failure diagnostics

Base: `e8c268876dfabcddb0ef95ed1c798ccba8bf65ad`. This source-only change is
isolated on `codex/voice-admission-diagnostics-20261103`; it does not install or
activate source, change a runtime manifest, start services or create a Voice call.

An SDK 401 currently conflates local request rejection, metadata HTTP 401 and
the fixed malformed-body caller-access preflight's HTTP 401. WSS additionally
maps metadata/settings/preflight 403 and transport failures to its existing
outer 401. Root's fresh metadata transaction read returned 200, but linking
that transaction to the user's exact native request remains conditional. This
patch makes subsequent rejection stages observable without inferring expiry,
token type, issuer or changing authorization policy.

One terminal warning identifies transport, fixed stage/outcome, public status,
observed upstream HTTP status and elapsed milliseconds. Stages cover the local
request, metadata HTTP/body/settings/context close and caller preflight
HTTP/body/context close. No exception text, traceback, credential, header,
cookie, body, settings value, URL or caller/business ID enters this event.
Fields use closed enums and exact numeric type/range checks; elapsed time is
clamped to 0–10000 ms. Diagnostic-handler failure cannot change access.

The existing same-deadline HTTP context unwinding, cancellation propagation,
public SDK error envelopes/statuses and WSS False→401 behavior are retained.
Metadata HTTP denial is reported only after its contexts settle, so a later
close failure is logged as a close/transport failure rather than an already
final denial. Exact preflight 400 remains acceptable only after the exact
bounded envelope and both contexts close. No positive credential/access result
is cached. Valid alternate profiles still skip the fixed deployment preflight;
diagnostics do not add a profile restriction or parse credentials.

The SDK manager's early header/body guard has a small matching terminal hook
because it precedes the common admission function. Existing readiness, capacity,
TURN, peer, speech and business allocation remain downstream of admission.

The new logs deliberately do not add correlation IDs or a context mechanism.
Existing middleware HTTP IDs are unchanged; simultaneous preallocation
attempts can still make timestamp-only cross-line correlation ambiguous. WSS
could read that request-local ID directly, but carrying it through the SDK's
raw-header/body callback would add an API change outside this narrow patch.

Validation evidence:

- Baseline: 132 focused tests passed before edits.
- New diagnostics tests were observed failing before implementation; an
  additional response-close regression was also observed failing before its fix.
- All 13 new tests and 181 affected/focused tests passed after implementation.
- First full run: 1186 tests, four failures in two AST fixtures missing their
  newly required globals, plus five existing missing-jsonschema environment
  errors. The fixture namespaces were corrected without changing behavior.
- Full Native rerun uses the already existing test-only dependency directory
  `server/.local/voice-repair-20261102/test-deps`; no package installation or
  active dependency change is made. It ran 1186 tests in 185.597 seconds with
  zero errors and one failure:
  `test_reserved_slots.ReservedSlots.test_outstanding_planner_observer_never_blocks_classifier_or_overlaps_followup`.
  Its existing 0.5-second thread-event wait returned false. That unchanged test
  then passed in isolation (1 test, 1.522 seconds). The full run is explicitly
  not claimed clean; this timing result is retained for independent review.

Commands run from `voice/native-bridge` using the existing Native venv Python:

```text
python -B -m unittest test_admission_diagnostics test_sdk_admission test_caller_create_preflight test_voice_settings_integration test_sdk_sessions test_request_diagnostics test_input_lifecycle -q
PYTHONPATH=C:/Projects/strix-alloy-clean/server/.local/voice-repair-20261102/test-deps python -B -m unittest discover -q
PYTHONPATH=C:/Projects/strix-alloy-clean/server/.local/voice-repair-20261102/test-deps python -B -m unittest test_reserved_slots.ReservedSlots.test_outstanding_planner_observer_never_blocks_classifier_or_overlaps_followup -q
```

The suite uses its existing simulated HTTP/RTC fixtures; no actual ServiceNow,
Voice issuance/session, own-TTS synthesis or model inference was invoked.
Detailed test outputs remain in the isolated worktree's ignored
`server/.local/admission-diagnostics/` directory.

The new tests exercise both SDK and WSS metadata/preflight 401, public-status
parity, malformed JSON/settings, incorrect 400 bodies, response/client closure,
timeout, external cancellation, local rejection before authority/allocation,
privacy, clock clamping, logger failure and unchanged successful/alternate
profile admission. Three existing test files only update the structured-log
expectation or AST-fixture namespace imports.

Physical-device media behavior and the earlier silent call are not re-tested
or declared repaired by this source change. Root owns any later activation.
