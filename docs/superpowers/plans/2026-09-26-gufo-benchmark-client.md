# GUFO bounded benchmark measurement client implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan. Steps use checkbox syntax. The user already chose parallel implementation/review; do not ask for design or execution approval again.

**Goal:** Implement reusable bounded HTTP measurement of actual token counts, raw streamed/non-streamed answers, tools and distinct HTTP/engine rates against an explicitly supplied local endpoint, without launching or stopping it.

**Architecture:** Reuse the existing tested transport and counter validation with explicit optional parameters whose defaults retain the v3 smoke behavior. Generalize SSE normalization once, leaving the legacy tuple API as a wrapper. Add a request-once benchmark API which does not manage a process or retry and returns JSON-serializable sanitized evidence, plus focused offline tests. The following integration phase will feed this client a separately reviewed finite recipe under the existing guardian; this client alone never grants runtime admission.

**Tech Stack:** Python3.12 standard library; existing gufo_control.smoke_http transport, unittest and local fake HTTP peers.

## Global Constraints

- Work only in C:\Projects\strix-alloy-research\integration, branch codex/gufo-native-integration. Preserve working deployments, clean reference sources, existing weights/SDK and raw evidence.
- No model/GPU/WSL process or real inference HTTP request in this task. No global settings, BIOS, carve, driver, services, security, pagefile or D: changes. No push/release.
- Runtime floors remain49GiBprelaunch,24GiBphysical,12GiBcommit reserve; this client neither grants nor modifies admission. Profile fit review and guardian lifecycle changes are separate prerequisites before live benchmark use.
- Do not count SSE chunks as tokens, retokenize visible output for native counts, or infer common-window concurrency from whole-request rates. Store actual logical/fresh/cached/output counters and reject inconsistencies.
- Raw request body/response and receive timestamps must remain available. Never persist the bearer secret or Authorization header; recursively redact echoed secrets in returned failures/responses.
- HTTP PP uses actual newly processed prompt tokens divided by submission-to-complete-response wall time. Only one-output-token requests may be labelled HTTP PP1. Engine PP/TG and TTFT are separate. Missing optional metrics are null with diagnostics, never zero.
- Max request body262144bytes, response1048576bytes, existing bounded framing/wire limits, socket slices0.25s, monotonic absolute deadline and cancellation. Exactly one POST per request-once invocation; any transport,401,503,unsupported sampler or malformed-response failure ends it. No retry/warmup/autotokenizer calls.

## Task 1: Reusable protocol and request-once client

**Owned files:** modify scripts/gufo_control/smoke_http.py and tests/gufo/test_smoke_http.py; create scripts/gufo_control/benchmark_http.py and tests/gufo/test_benchmark_http.py. No other production file may change.

**Interfaces:**

```python
# smoke_http.py: default calls and legacy error spellings stay unchanged.
def _exchange(method, path, body, key, deadline, cancel, *,
              host=None, port=None, request_limit=None): ...
# None resolves to existing HOST/PORT/MAX_REQUEST at call time (fake tests patch these).
# Explicit host must be '127.0.0.1'; explicit port integer1..65535, not bool.
# Explicit request_limit integer1..262144; existing default remains16384.

def _validate_usage(usage, timings, *, max_prompt_tokens=512,
                    max_completion_tokens=64, cache_policy='cold'): ...
# Bounds positive non-bool integers; policy 'cold' or 'allow'. Retain tuple
# (metrics, validation_errors, unavailable_metrics), legacy default checks.
# Under 'allow', cache reuse is recorded, not a failure; all count consistency
# checks remain. Error labels use actual configured limits.

def parse_sse_response(parts, submitted): ...
# Dict with visible_answer, reasoning_content, first_visible_content_ms,
# finish_reason, tool_calls, usage, timings, observed_models. Strict framing,
# JSON finite-number and terminal/usage consistency rules remain unchanged.
# _parse_sse(parts,submitted) wraps this and returns its original five-tuple.

# benchmark_http.py: frozen object, no mutable request storage in configuration.
@dataclass(frozen=True)
class RequestLimits:
    max_prompt_tokens: int
    max_completion_tokens: int
    cache_policy: str = 'cold'
    request_bytes: int = 262144

def request_once(*, port: int, api_key: str, path: str, request: dict,
                 limits: RequestLimits, deadline: float,
                 cancel: threading.Event | None = None) -> dict: ...
```

The only accepted paths are /v1/chat/completions and /v1/completions. Endpoint is always127.0.0.1; never resolve remote DNS or follow redirects. Validate request has nonempty model, positive integer max_tokens<=limit and explicit stream bool, and retains caller-specified sampler/cache/tools exactly (no silentdefaults). Require chat messages array or legacy prompt string as appropriate. Serialize allow_nan=False and UTF8. Pre-transport validation failure sends no request. Never include key in result. Propagate programmer KeyboardInterrupt/SystemExit; return normal protocol/network/validation errors as structured failed results.

Result records success/error, request, endpoint/path, status, raw_response, raw body receive parts as UTF8-safe/base64 representation with monotonic arrival times (do not count them as tokens), submitted/completed times, visible answer/reasoning/tool calls, finish reason, usage/timings, validation errors, unavailable metrics and normalized rates. HTTP failed bodies retained. Partial wire on exceptions retained from SmokeError.raw_response. Response headers may be recorded only with credential echoes redacted. If every present response model matches requested model, record; conflicting model is failure. Missing response model is unknown, not a fabricated match.

For SSE, merge tool-call fragments by nonnegative integer index; each has function name/argument string fragments, optional stable id/type. Reject wrong types, conflicting id/type, malformed function fragments and multiple unsupported choices. Do not execute tool calls. Preserve incomplete argument strings on finish_reason length. Record reasoning_content separately and never treat reasoning or tool deltas as visible-content TTFT. For JSON completion responses, normalize choices[0].text or choices[0].message content/tool_calls, top-level usage/timings, require exactly one choice and terminal finish reason. Client first-visible TTFT is unknown/null for nonstreaming JSON; full-response arrival is not first-token arrival. A well-formed finish_reason length is a valid measured bounded output, labelled truncated=true; semantic correctness is a later recipe gate. A valid stop/tool_calls terminal is truncated=false. Null/duplicate/conflicting terminal, missing usage, nonfinite numbers, or servererror fail.

Derive rates only from validated native counters and strictlypositive finite denominators; use engine gufo ms where present, otherwise matching timings ms, checking conflicting present duplicates. Never convert an unknown counter/rate to0. Record MTP acceptance accepted/proposed only with valid integers and accepted<=proposed; zero proposals =>null. Keep HTTP elapsed meaningful even if native metrics are invalid, but invalidate token-derived rates. Common-window aggregate decode is always unavailable in this API. Do not claim a1-token answer is sustaineddecode.

```python
# Canonical derivation, using seconds/milliseconds explicitly:
http_pp = fresh * 1000 / http_ms if pp1 and valid and http_ms > 0 else None
engine_pp = fresh * 1000 / prefill_ms if valid and prefill_ms and prefill_ms > 0 else None
engine_tg = output * 1000 / decode_ms if valid and decode_ms and decode_ms > 0 else None
acceptance = accepted / proposed if valid and proposed and proposed > 0 else None
```

- [ ] RED: add fake-server tests covering actual calls, arbitrary local test port, chatSSE and legacyJSON, custom bound2048/8192 and256output, cold-vs-cached validation, splitUTF8/SSE/CRLF/tool fragments, reasoningTTFT distinction, explicit sampled request preserved, HTTPPP1 vs multi-output request, engine-rate denominator, MTP accepted<=proposed, finishlength, missingoptionalnulls, mismatchedcounters/model, malformedusage, unknownfreshcounter, response/request caps,401/503/timeout/cancel no retry and redaction of echoed secret. Change new shared-helper tests first and demonstrate expectedfailure with old code. Existing smoke tests must remain meaningful.
- [ ] GREEN: implement the narrow protocol extensions and request-once API. No controller, launcher, arbitrary profile CLI, fixture generation or output-file writing here. Workload-specific correctness/three-repeat statistics belong to the suite layer, not transport.
- [ ] Run focused tests from tests/gufo with absolute PYTHONPATH=C:\Projects\strix-alloy-research\integration\scripts and C:\Users\Marcel\AppData\Local\Programs\Python\Python312\python.exe -m unittest test_smoke_http test_benchmark_http.
- [ ] Run whole tests/gufo unittest discovery once, diff-check, self-review. Locally commit only four owned files. Full report .superpowers/sdd/benchmark-client-report.md includes RED/GREEN commands/output, interface details, changedfiles and concerns. Return shortstatus/commit/testsummary.
- [ ] Parent independently reviews recorded-base diff and reruns fullsuite while reviewing the memory/recipe audit. No live traffic until the next finite-run guardian integration is reviewed.

## Self-review / continuation

This phase covers the specified independent benchmark client's protocol and evidence foundations, including comparison ports and tool deltas. It does not complete setup/start/status/stop packaging, qualify8k/16k orMTP, run benchmarks, or validate common-window concurrency. Next phase uses audited finite recipes and unchanged guarded memory controls; preserve the completed v3 one-shot result rather than resetting it. All broader objective items remain active.
