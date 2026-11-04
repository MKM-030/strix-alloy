# Halogen cache wire correction implementation plan

> **For agentic workers:** Implement this single source-only task inline; Root owns independent review and any later integration/runtime action.

**Goal:** Parse the exact pinned engine's CacheOff counters without shifting or fabricating live pool values.

**Architecture:** Preserve the pinned upstream API and binary. At the existing uvicorn interception, replace only Engine.cache_stats in memory with its exact pinned AST plus one strict token-normalization call before parsing. Correct only the known51-token zero-cache producer prefix by removing its redundant field35; enabled57 remains unchanged and unknown formats refuse.

**Tech stack:** Python standard library AST/unittest/asyncio; existing authenticated ASGI wrapper.

**Spec:** Primary saved INDEPENDENT-CACHE-OFF-CSTAT-DIAGNOSIS.json SHA3e632c5dd9fb637c18036882bf4d653bfce67ce5a21b73f3079fd00ace89647c and Root's4Nov delegated instruction.

## Constraints

No primary/runtime edits, HTTP/WSL, starts/stops, image work, downloads or commit. Preserve Bearer auth, upstream source pin, guard refusal of busy/stale/noninteger counters and both slot modes. Only auth_api.py plus its sources.json hash change in runtime inventory; tests stay outside that inventory. api_defaults.py unchanged.

## Review focus

- Unknown/truncated/nonliteral CacheOff formats refuse instead of approximate coercion.
- Distinct busy/held/used/positions/packed counters retain their original values for slots1 and2.
- Enabled57-token parsing remains byte/behavior equivalent.
- Existing asynchronous I/O, timeout/stale behavior and authentication remain intact.
- API/binary identity drift and duplicate interception refuse before serving.

## One task

- [x] Compile the actual retained Engine.cache_stats AST for offline tests with fake in-memory I/O, literal producer fixtures and distinct live suffix values; run RED reproduction first.
- [x] Implement strict normalization and a narrowly bound in-memory method installation in backends/halogen-wsl2-0.18.22/scripts/auth_api.py; verify both actual-method paths and interception/auth behavior.
- [x] Update only the auth_api.py digest in profiles/sources.json; verify unchanged inventory and upstream/defaults; run focused and relevant existing offline suites.
- [ ] Freeze patch/tests/evidence for two independent reviews; do not commit or activate.
