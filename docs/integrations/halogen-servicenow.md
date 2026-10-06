# Halogen foreground console and ServiceNow REST integration

The retained **48.423621 tok/s** result is an 8,192-input-token, 128-output-token
greedy prose measurement from 4 October 2026. The engine had **262,144 positions
of capacity**. Capacity is the space available for input plus output; it does not
mean that every request occupies that space. Three measured repetitions followed
an excluded warmup, with thinking off, seed 1, cache Off and native MTP depth 2.
[Retained 8K report](../benchmarks/halogen0162-pld-stock8k-20261004.md).

| Actual input tokens | Prefill tok/s | Regular MTP decode tok/s | Accepted / drafted |
| ---: | ---: | ---: | ---: |
| 8,192, historical Stock A | 1866.537 | 48.424 | 207 / 345 = 60% |
| 131,072, natural long input | 1177.60 | 36.67 | 186 / 393 = 47.33% |
| 260,000, natural long input | 1104.87 | 36.81 | 192 / 375 = 51.20% |

The long-input rows are separate, three-repetition measurements using natural
novel text and a different arena setting. They are not a speed comparison against
Stock A. A new ServiceNow prompt is also a different workload; the launcher
selects the configuration, without promising the historical rate.
[Natural long-input report](../benchmarks/halogen0162-natural-long-20261005.md).

The last measured stock 8K control was **41.586631 tok/s** decode and
1281.714232 tok/s prefill, still 207 / 345 = 60% accepted, in the 5 October
`stock_after` cohort. No fresh throughput trial is claimed for this integration
work. The older 48.42 result remains historical; selecting its startup settings
does not establish that this host will reproduce its operating state or rate.
[Last measured stock control](../benchmarks/halogen0162-rocr-arena8192-20261005.md),
[cohort evidence](../benchmarks/halogen0162-rocr-arena8192-20261005.json).

## Start from Windows PowerShell 5.1

Run from `C:\Projects\strix-alloy-clean` in the console that should display the
server and API trace:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\Start-Halogen-ServiceNow.ps1 -ConsoleTrace
```

The default `Current8K` profile pairs an 8,192-token prefill chunk with an
8,192-token prefill arena. To select the native arena settings of the historical
Stock A profile:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\Start-Halogen-ServiceNow.ps1 -Profile HistoricalStock -ConsoleTrace
```

This entry script accepts PowerShell 5.1. Its explicit Python launch route uses
the existing project Python environment and the trusted Windows PowerShell 5.1
host for the installed backend's helpers; PowerShell 7 is not required by this
route. Wait for `gateway_listening` before sending a
request. Press Ctrl+C once and wait for `STOPPED` and backend cleanup. The normal
controller owns the singleton session, memory admission and cleanup. An already
running managed session must be stopped through its normal controls before a
different profile can start.
[Launcher](../../scripts/Start-Halogen-ServiceNow.ps1).

```powershell
.\scripts\Start-Halogen-ServiceNow.ps1 -PrintOnly
.\scripts\Start-Halogen-ServiceNow.ps1 -Status
.\scripts\Start-Halogen-ServiceNow.ps1 -Stop
```

`-PrintOnly` displays configuration without writing a session profile or starting
an engine. `-Port` defaults to `8840`. `-ConsoleTrace` enables the content trace;
without it, the normal operational logs are used.

## What the profiles actually select

Both profiles select Halogen **0.16.2**, native
`qwen38-flash-next-v2.hgn`, one slot, a 262,144-position pool and context capacity,
MTP depth 2, stock PLD `3,3`, prompt cache Off, one active API request, and an
18 GiB physical/commit runtime reserve. They retain the stock compute path and
the normal WSL2 adaptation. The image is pinned as:

```text
ghcr.io/peonist-ai/halogen-flash-server@sha256:0c61bf84ac22308a53f5d1ca6b86806702d7039e5ebc51cae4c66621b92fe04a
```

| Startup control | HistoricalStock | Current8K |
| --- | --- | --- |
| `HALOGEN_CTX` / `HALOGEN_KV_POOL_POSITIONS` | `262144` / `262144` | `262144` / `262144` |
| `HALOGEN_KV_SLOTS` | `1` | `1` |
| `HALOGEN_MTP_DEPTH` / `HALOGEN_PLD` | `2` / `3,3` | `2` / `3,3` |
| `HALOGEN_PROMPT_CACHE` | `0` | `0` |
| `HALOGEN_PREFILL_CHUNK` | Native default `32768` | Explicit `8192` |
| `HALOGEN_MAX_TOK` | Native default `32768` | Explicit `8192` |

Stock A's retained profile did not set either prefill control. Its actual startup
log records `max_tok 32768` and 12.3 GiB working memory. The later natural long
profile explicitly used `8192` for both, with 5.6 GiB working memory. These arena
settings size work buffers and prefill calls; they are separate from the JSON
answer budget `max_tokens`.
[Version pin](../../backends/halogen-wsl2-0.16.2/profiles/release.json),
[upstream 0.16.2 flags](https://github.com/peonist-ai/halogen-flash-server/blob/v0.16.2/docs/FLAGS.md).

The v2 checkpoint uses mixed precision: 4-bit experts and other weights, 6-bit
mixing layers, and 8-bit dense draft-head projections. Its 62.1 GiB checkpoint
has a separate, paged FP8 n-gram lookup table of about 47.7 GiB. It is a native
HGN checkpoint, with its own trunk precision; the historical run loaded no
additional quality overlay.
[Upstream v2 precision description](https://github.com/peonist-ai/halogen-flash-server/blob/v0.16.2/docs/QUANT.md).

The local retained Stock A evidence is under
`server/.local/optimization9h-20261004/pld-stock8k-bookend-1742f9e165de45bea641446004e9733e/stocka/`:
`plan.json`, `backend-manifest.json` and `controller.log`. Its source profile is
`server/.local/optimization9h-20261004/pld-stock8k.json`. The public report and
[sanitized measurements](../benchmarks/halogen0162-pld-stock8k-20261004.json)
remain the portable measurement record.

## HTTP contract

```text
POST https://strix-alloy.tail7f425a.ts.net/v1/chat/completions
Local base URL: http://127.0.0.1:8840/v1
Public model alias: halogen-v2
```

The observed Tailscale configuration forwards HTTPS port 443 to
`http://127.0.0.1:8840` and has Funnel enabled for
`strix-alloy.tail7f425a.ts.net:443`. This is configured for internet access;
authenticated requests from a hosted ServiceNow instance can use the HTTPS
endpoint once outbound reachability is verified. Preserve the existing network
configuration. For a deployment using private Tailscale Serve without Funnel,
route requests through a MID Server whose host can resolve and reach the tailnet.
The `ts.net` suffix alone does not establish whether routing is private or public.
[Tailscale Serve](https://tailscale.com/docs/reference/tailscale-cli/serve),
[Tailscale Funnel](https://tailscale.com/docs/features/tailscale-funnel).

Authenticated `GET /v1/models` is the discovery source for the gateway alias.
The managed configuration maps `halogen-v2` to the backend model
`halogen-qwen3.8-flash-next`. The gateway validates the model and rewrites that
field before passing the JSON to Halogen. Public requests must reach port 8840
through the configured forwarding route for the gateway console to observe
them. A route pointing directly at backend port 8731 bypasses this console.
[Gateway implementation](../../server/gateway.py).

| HTTP header | Value |
| --- | --- |
| `Authorization` | `Bearer <protected API key>` |
| `Content-Type` | `application/json` |
| `Accept` | `application/json` for the example below |

The gateway also accepts `x-api-key`, but one Bearer header is sufficient.
Credentials belong in the authentication header. Generation controls belong in
the JSON body: custom `temperature`, `seed` or thinking headers do not configure
the engine. The gateway passes body fields through and does not forward arbitrary
client headers to Halogen.

| JSON body field | Effect for this pinned backend |
| --- | --- |
| `temperature: 0` | Greedy continuation, matching the historical request mode |
| `seed: 1` | Explicit sampling seed; useful for repeatability on the same configuration |
| `drafter: "mtp"` | Select native MTP; `"serial"` selects the serial control |
| `enable_thinking: false` | Disable the generated thinking block |
| `reasoning_effort: "none"` | The supported equivalent off control |
| `max_tokens: 128` | Maximum generated budget, including reasoning when enabled |
| `stream: false` | One JSON response for simple ServiceNow parsing |

Thinking controls also support `chat_template_kwargs`; agreeing duplicate controls
are accepted. Send explicit controls so that server defaults cannot unexpectedly
enable thinking. The pinned official documentation describes the sampling,
thinking and token-budget behavior.
[Halogen 0.16.2 API guidance](https://github.com/peonist-ai/halogen-flash-server/blob/v0.16.2/README.md#using-it).

**Cache is a startup setting here.** Although the historical benchmark request
included `cache_prompt: false`, the retained 0.16.2 `ChatReq` schema does not
declare or read `cache_prompt`; its unknown fields are ignored. This field is
therefore not a supported per-request cache switch for this pin. The effective
cache-off control is `HALOGEN_PROMPT_CACHE=0` in both launch profiles. Do not infer
support for a parameter merely because a request returns HTTP 200.

This schema check used the retained official-image API extract at
`server/.local/optimization9h-20261004/upstream-api-source-9b538f902be94004b711bf878a78219e/source-stdout.txt`,
SHA256 `8607cc429448b7eaa51c1bad68fe24c5c59f4bf8662eb28bbf21b130236ac4f1`.
Its `ChatReq`, `DRAFTERS` and `drafter_id` definitions confirm the body controls.
Unknown or unavailable drafters produce a 400. Use the loaded model's advertised
MTP capability; an additional drafter name does not imply that its assets exist.

Copyable fast-mode body:

```json
{
  "model": "halogen-v2",
  "messages": [
    {"role": "user", "content": "Summarize the incident in three concise sentences."}
  ],
  "temperature": 0,
  "seed": 1,
  "drafter": "mtp",
  "enable_thinking": false,
  "reasoning_effort": "none",
  "max_tokens": 128,
  "stream": false
}
```

Increase `max_tokens` when a longer answer is required. This short example selects
the greedy fast mode; reproducing the benchmark also requires its frozen actual
8K prompt, warmup and measurement procedure. Thinking off removes generated
reasoning tokens; it does not establish an additional decode-rate improvement.

For a local PowerShell 5.1 smoke request while the server console is open, the
following reads the existing token without printing it and sends the same body.
Use the HTTPS hostname instead of loopback from a caller that can reach the
configured endpoint. This is an example to run manually, not a retained benchmark.

```powershell
$tokenPath = 'C:\Projects\strix-alloy-clean\backends\halogen-wsl2-0.16.2\.local\api-token.txt'
$apiKey = (Get-Content -LiteralPath $tokenPath -Raw).Trim()
$headers = @{ Authorization = 'Bearer ' + $apiKey; Accept = 'application/json' }
$body = @{
    model = 'halogen-v2'
    messages = @(@{ role = 'user'; content = 'Reply with one short greeting.' })
    temperature = 0
    seed = 1
    drafter = 'mtp'
    enable_thinking = $false
    reasoning_effort = 'none'
    max_tokens = 128
    stream = $false
} | ConvertTo-Json -Depth 8
$result = Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8840/v1/chat/completions' `
    -Headers $headers -ContentType 'application/json; charset=utf-8' -Body $body -TimeoutSec 600
$result.choices[0].message.content
```

## ServiceNow server-side example

Use this in a server-side Script Include or an integration action. Store the API
token in a ServiceNow **API key credential record**, connected through the
application's Connection & Credential Alias. Pass the token resolved by the
configured credential step as `protectedApiKey`; resolution is instance-specific
and is intentionally not replaced with a guessed credential lookup. Pass the
reachable MID Server's **name** as `midServerName` only when a MID Server is
needed, such as for a private tailnet deployment; leave it empty for direct HTTPS.
[ServiceNow API key credentials](https://www.servicenow.com/docs/r/platform-security/connections-and-credentials/API-key-credential-form.html),
[Connection & Credential Aliases](https://servicenow.github.io/sdk/guides/alias-guide).

```javascript
function callStrixAlloy(promptText, protectedApiKey, midServerName) {
    // protectedApiKey is supplied by the configured credential step.
    var apiKey = String(protectedApiKey || '');
    if (!apiKey) {
        throw new Error('The protected Strix Alloy API credential is missing.');
    }

    var payload = {
        model: 'halogen-v2',
        messages: [{role: 'user', content: String(promptText)}],
        temperature: 0,
        seed: 1,
        drafter: 'mtp',
        enable_thinking: false,
        reasoning_effort: 'none',
        max_tokens: 128,
        stream: false
    };

    var request = new sn_ws.RESTMessageV2();
    request.setEndpoint('https://strix-alloy.tail7f425a.ts.net/v1/chat/completions');
    request.setHttpMethod('POST');
    if (midServerName) {
        request.setMIDServer(String(midServerName));
    }
    request.setRequestHeader('Authorization', 'Bearer ' + apiKey);
    request.setRequestHeader('Content-Type', 'application/json');
    request.setRequestHeader('Accept', 'application/json');
    request.setHttpTimeout(600000);
    request.disableForcedVariableSubstitution();
    request.setRequestBody(JSON.stringify(payload));

    var response = request.execute();
    var status = response.getStatusCode();
    if (response.haveError() || status < 200 || status >= 300) {
        // Keep credentials and prompt/response text out of system logs.
        throw new Error('Strix Alloy request failed; HTTP ' + status);
    }

    var result = JSON.parse(response.getBody());
    if (!result.choices || !result.choices.length || !result.choices[0].message) {
        throw new Error('Strix Alloy returned no assistant message.');
    }
    return {
        text: result.choices[0].message.content || '',
        finishReason: result.choices[0].finish_reason,
        usage: result.usage
    };
}
```

An empty `RESTMessageV2` requires an explicit endpoint and method.
`setRequestHeader` sets HTTP headers; `setRequestBody(JSON.stringify(payload))`
sets the JSON body without REST-record variable substitution. The timeout is in
milliseconds and controls socket inactivity; instance execution limits can still
apply. These methods and synchronous `execute()` are documented by ServiceNow.
[RESTMessageV2 reference](https://www.servicenow.com/docs/r/api-reference/server-api-reference/c_RESTMessageV2API.html).

Check HTTP status and `finish_reason`. `length` means the requested generated
budget was reached. A gateway busy/draining response is 429 with `Retry-After: 1`;
401 means authentication failed, and 503 means readiness/upstream availability
failed. Keep retry policy bounded and appropriate for the calling action.
This repository contains no ServiceNow Fluent application or live-instance test;
the example is an integration template, not a deployment into an instance.

## What appears in the foreground console

With `-ConsoleTrace`, the gateway prints `[api]` JSON events to stdout. Events
carry a UTC timestamp, a gateway-session identifier and a request identifier.
They show request arrival and body, upstream status, returned answer text, tool
calls, usage and completion. Authentication headers are excluded; known API
secrets and credential fields in payloads are redacted. Terminal controls are
escaped. Display values are capped at 65,536 characters and parsed response events at
256 KiB, with truncation or `trace_skipped` notices. Transport bytes and
backpressure still follow the normal gateway path. Content events are not sent
to the rotating operational log handler.

The trace's stdout writes are synchronous. A slow console can add API latency
even when parsing and displayed values stay bounded. `console_trace` defaults
to false; disable content tracing for throughput benchmarks.

For the ServiceNow `stream: false` example, arrival is visible immediately and
answer content becomes visible when the upstream JSON response arrives. For
token-by-token console output, an SSE-aware caller can send `stream: true` and
use `Accept: text/event-stream`; optional
`stream_options: {"include_usage": true}` requests streamed usage. SSE is not a
single JSON document, so the ServiceNow parser above must retain `stream: false`.
The regular `execute()/getBody()` example does not provide a token callback to
a ServiceNow browser UI.

Only reasoning explicitly returned by the backend, such as `reasoning_content`
or a returned reasoning/thinking event, can be shown. Internal latent computation
is not exposed by the REST API. Fast mode disables the generated thinking block,
so that mode normally has no reasoning text to display. The console observes the
response; it does not create or infer additional reasoning.

To request generated reasoning, change **both** fast-mode controls in the JSON
body to `enable_thinking: true` and `reasoning_effort: "medium"`. Do not leave
`reasoning_effort: "none"` in that request: it disables thinking. Allow a larger
`max_tokens` budget, for example `1024`, because reasoning and the answer share
that budget. This is a different generation workload from the historical
thinking-off benchmark; its latency and rate have not been measured here.
