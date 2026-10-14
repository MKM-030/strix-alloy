# SDK session admission candidate — inactive

This directory contains a separately testable authorization unit for the observed
`POST /api/webrtc/sessions` request with one Bearer header and JSON
`{"agent_id":"<approved ID>"}`. It registers no endpoint and creates no session,
SDP, WebSocket ticket, or SDK success response. The SDK transport contract remains
unavailable. This candidate does not fix or activate the native integration.

The only approved instance is
`https://soprasteriaassvsdemo14.service-now.com`. The assistant
`8aa131d793f787105c8132d47aba1095` and its voice agent
`a6337ddf93f787105c8132d47aba1058` are two accepted request aliases for the same
pinned service. They never select a different platform URL or authorization
service. Policy lives separately in `sdk_admission_policy.py`.

`admit_sdk_session(raw_headers, body, query_string="")` accepts duplicate-preserving
string header pairs and complete raw body bytes. The existing `core.py` is copied
unchanged solely to reuse `core.authorized_agents`. All bearer forms, including
opaque OAuth tokens and JWTs, require the fixed platform authorization POST.
The original header is forwarded unchanged with JSON `{"serviceId":"8aa..."}`
using the full pinned ID. No `clientApp`, `admin_test`, test-mode option, redirect,
cookie, environment credential, or locally decoded JWT claim is used.

Successful admission returns a frozen internal `VerifiedContext` containing the
three pinned policy values and two request classification booleans. It contains
no credential and is not an HTTP or SDK wire DTO. This module performs no logging.
`AdmissionDenied` exposes only status 400/401/403 and the fixed error codes
`bad_request`/`unauthorized`/`forbidden`. Platform/network/parser details are
suppressed. Cancellation propagates.

Bounds are 32 KiB request/authorization-response bodies, 8 KiB Authorization
header including its scheme, 16 KiB total headers, 64 raw header pairs, and
10 seconds for the entire platform authorization operation. Any query, cookie,
recognized competing auth header, content/transfer encoding, duplicate security
header, malformed JSON, duplicate JSON key, or extra JSON property is rejected.
Origin is optional; a present value must exactly equal the pinned instance origin.

An eventual adapter must enforce the POST route itself and bound the still-encoded
body while reading it. It must pass original header pairs without flattening
duplicates. It must omit the test-only `http_factory` seam so admission owns a new
aiohttp session. Wire success handling must wait for the actual SDK contract.

Run offline tests from this directory:

```powershell
& 'C:\Projects\strix-alloy-scc-voice\voice\native-bridge\.venv\Scripts\python.exe' -m unittest -v test_sdk_admission
```

All test tokens are synthetic fixtures. Tests use fake HTTP only, without a real
ServiceNow request, user token, dependency install, or production activation.
Red/green logs and `VALIDATION.json` record evidence. Only this isolated stage and
its local mirror were written; live native/browser/gateway/provider/config files
were untouched. The existing browser Origin/query-JWT/admin-test path remains
separate from this candidate.
