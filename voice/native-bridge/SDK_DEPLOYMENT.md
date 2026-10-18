# SDK deployment policy candidate

The SDK adapter accepts one explicit operator-configured ServiceNow deployment.
`Config` builds an immutable `SDKDeploymentPolicy` from the existing
`instance_name`, `voice_service_id` (assistant sys_id), `required_agent_id` (voice
agent sys_id), and the new `sdk_public_origin`. The same startup snapshot binds
OAuth admission, allowed Origin, verified context checks, session operations,
and the SDK response's `endpoint_url`.

All four SDK deployment fields must be explicit. The legacy browser-only
instance default is unavailable when configuring SDK policy. `instance_name`
is a lowercase DNS label of at most 63 characters. Both sys_ids
must be 32 lowercase hexadecimal characters. The authorization origin is always
`https://<instance_name>.service-now.com` and the authorization path is fixed in
code. Arbitrary instance URLs and caller-selected authorization destinations
are unsupported. The original opaque Bearer is sent unchanged to that instance
on each session creation. There is no JWT interpretation, local acceptance,
cookie credential, environment credential, redirect, test-mode field, or
fallback deployment. Existing request/response bounds remain unchanged.

`sdk_public_origin` must be a canonical lowercase HTTPS DNS origin with no
credentials, port, path, trailing slash, query, or fragment. IP literals and local
hostnames are rejected. The installed SDK retains only scheme and host for
subsequent requests, so a proxy must expose the route at the origin root on
standard HTTPS. Host/Forwarded headers never select this endpoint. Validation
does not verify DNS or TLS reachability; the operator must control the proxy
and its DNS.

## Configure another instance

Copy `config.community.example.json`; replace the instance name, both placeholder
sys_ids, and the public HTTPS origin with your own values. Keep `auth_mode` set
to `servicenow`, provide no development token, and use a finite call duration
between 0 and 3600 seconds. Set `native_sdk_enabled` to `true` only after configuring
the matching native SDK endpoint and TLS proxy for your deployment. The example
starts with SDK routes disabled. A missing or invalid policy cannot enable SDK
admission; contradictory startup settings raise `ValueError`. Changing deployment
configuration requires a process restart. Runtime field mutation cannot rebind
an already registered manager.

## Existing deployment migration

The existing explicit demo values in `config.example.json` now include
`sdk_public_origin: "https://strix-alloy.tail7f425a.ts.net"`. Before adopting this
candidate, an existing configuration with `native_sdk_enabled: true` must add
its intended public HTTPS origin. The previous implicit hardcoded deployment
and endpoint are removed. Direct callers of `admit_sdk_session` must pass the
validated policy; omitting it returns generic forbidden without HTTP traffic.
This change does not restart a service or change any platform record.

## Scope and identity limitation

The SDK 2.26 protocol identity is still the fixed literal `agent_operator`, with
one assistant-to-voice-agent allowlist pair per process. Multi-instance routing,
arbitrary custom ServiceNow domains, multi-agent selection, and runtime policy
reload are unsupported. The Bot backend still owns a separate fixed conversation
identity; caller OAuth authorization does not establish caller-identity execution
by that backend. Browser authorization and the demo `/launch` shortcut are unchanged.

## Offline verification

Run `python -m unittest discover -v` with the existing native-bridge dependencies.
`test_deployment_policy.py` covers explicit second-instance admission, wrong
first-instance query/Origin/context/agent rejection, upstream rejection of a
synthetic first-instance token, fixed auth destinations, immutable startup
binding, endpoint spoofing, malformed configuration, disabled defaults, and
contradictory configuration. The existing admission/wire/audio tests use an
explicit fixture policy and retain their prior behavioral assertions. These
offline checks do not prove live OAuth trust, TLS routing, or SDK audio behavior
against a second real instance.
