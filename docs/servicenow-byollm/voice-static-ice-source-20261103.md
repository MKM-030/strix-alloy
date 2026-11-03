# Optional Voice static ICE: isolated source result

The isolated `codex/voice-static-ice-20261103` branch adds an optional explicit nonsecret ICE-URL selection to managed TURN configuration. The behavior edit is `voice/native-bridge/managed_turn.py`; two additional one-literal starter edits preserve normal startup with the candidate configuration. No active configuration, runtime source, service, model, authentication metadata or operational session was changed. This work does not activate static mode.

Legacy files with the original three keys retain per-call discovery and awaited exact metadata-session deletion. A fourth `static_ice_urls` key opts into an explicit ordered list of one to four unique exact allowlisted TURNS/TCP443 URLs. Explicit null, an empty list, duplicate/unknown fields or destinations, credentials and altered URL syntax fail closed. Static mode returns fresh URL-only rows after the existing caller syntax checks and creates no HTTP client. Caller admission, capacity, fresh OAuth TURN identity, SDK/WSS behavior and credential clearing remain owned by the unchanged call paths. There is no response/token cache, detached cleanup or automatic fallback.

Fresh offline verification:

- Before changes: 43 existing managed TURN/configuration/host-ICE tests passed.
- The initial nine new tests failed against e8c2688 because the static option was absent (missing field and constructor argument); the implementation then passed them.
- Final new suite: 14/14 passed. It includes strict file/constructor bounds, zero discovery HTTP, fresh copies, fresh caller syntax/OAuth identity, actual local SDK/WSS fixture admission/capacity and owned credential cleanup.
- Final focused cohort: 201/201 passed; `git diff --check` passed.

The exact focused command, from this worktree's `voice/native-bridge` directory, was:

```powershell
& 'C:\Projects\strix-alloy-clean\voice\native-bridge\.venv\Scripts\python.exe' -m unittest -q test_managed_turn_static test_managed_turn test_ice_configuration test_host_ice test_instance_configuration test_sdk_sessions test_sdk_admission test_wss_managed_turn test_wss_authorization test_caller_create_preflight
```

The existing venv was used without installing packages. Tests use synthetic boundaries and local test HTTP fixtures; they do not invoke ServiceNow, live TURN, a model, ASR/TTS or actual Voice sessions. Expected denial/failure logs are negative test evidence. No full repository test-suite claim is made; the unrelated historical timing failure in the separate diagnostics campaign is not reclassified by this targeted result.

This is speculative source awaiting independent review and later operational qualification. An explicit fixed YCG endpoint may only be selected after the fresh-token TURN discriminator and a qualified actual SDK startup. Neither experiment ran here. Ordered multiple URLs do not promise automatic region failover, and allowlist membership does not establish region equivalence. Physical iPhone/Android/desktop playback and measured optimized latency remain unproven by these offline tests.

The first config-only activation preparation is retained as HOLD. The normal user starter pins managed-config bytes, and the private ASR manifest pins that starter. The necessary acyclic cascade changes only the managed-config hash literal in `start_current_voice.py`, that one manifest role's hash, then the manifest hash literal in `qwen_asr_start.py`. Other twelve manifest roles and every path are unchanged; the manifest does not pin the Qwen launcher. This does not require restarting the running ASR worker.

The new exact private postimages and seven cascade tests are under `server/.local/voice-repair-20261102/native-static-ice-activation-v2-20261103`. Two positive pin tests were observed failing against the old literals before the change. All seven then passed, including the actual fresh-module normal Voice preflight and Qwen `ensure` paths with the same existing-worker metadata (`ready`, CPU, `crispasr`, `mixed-gguf`, not busy, one slot). Actual metadata was obtained by one authenticated local readiness GET without audio or inference. Test boundaries project only the planned starter source postimage and use the retained independent full-hash/stat proof for large files. No live `ensure`, process start, weight rehash or service mutation was performed.

The existing starter cohort passed 21/21 both before and after the literal changes. Candidate managed-config SHA is `40f71726c0f4493cf0bba3e520d509c8dc8ae08e61cf4fbeb068c124edb7afee`; candidate ASR-manifest SHA is `b9a3c60fe096c1cefb080705d144953d841d0be991f2d8480bf8dbdbbac0676c`. A new independently reviewed v2 activation must bind these exact bytes, the final source commit and a real qualified startup baseline before any lifecycle action.
