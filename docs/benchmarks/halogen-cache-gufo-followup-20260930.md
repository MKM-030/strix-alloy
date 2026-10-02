# Cache reuse and GUFO correctness follow-up

The [262K w4b/v2 benchmark](halogen0151-v2-262k-20260930.md) remains the source for
PP512/PP2048 and TG128 rates. This follow-up tests prefix reuse, not faster cold
kernel throughput. The new data are Halogen 0.15.1, v2, one slot, 262144 capacity.

## Cache-shape results

The original exactly-8192-token test missed despite repeated identical requests.
The expanded test keeps that case and adds a slightly longer single message, a
shared system document and a document in conversation history. Do not silently
pad or rearrange user messages as a supposed optimization: these are distinct,
explicitly defined workloads. Within each row, all repetitions use identical bytes.

Wall time is measured on Windows across the HTTP request, including prefill and
up to 64 generated tokens. It is not decode-only tokens/second. One initial request
and two repeats are retained; the first request is not a statistically matched
cold-cache distribution. A first request may reuse a prefix from an earlier case;
its cached-token count is shown explicitly. Counts prove reuse independently of time.

| Mode / drafter | Shape | Full input tokens | First request s | First cached tokens | Repeat mean s | Repeat cached tokens | Identical output |
|---|---|---:|---:|---:|---:|---|---|
| Exact / serial | exact-single | 8192 | 9.834 | 0 | 8.007 | 0 | True |
| Exact / serial | longer-single | 8203 | 10.560 | 0 | 2.052 | 8192 | True |
| Exact / serial | system-document | 8227 | 10.947 | 0 | 2.085 | 8192 | True |
| Exact / serial | history-document | 8242 | 8.943 | 0 | 2.144 | 8192 | True |
| Flexible / serial | exact-single | 8192 | 10.023 | 0 | 1.857 | 8192 | True |
| Flexible / serial | longer-single | 8203 | 2.751 | 8128 | 1.847 | 8203 | True |
| Flexible / serial | system-document | 8227 | 8.663 | 0 | 1.857 | 8227 | True |
| Flexible / serial | history-document | 8242 | 8.539 | 0 | 1.847 | 8242 | True |
| Exact-MTP / mtp | exact-single | 8192 | 9.781 | 0 | 7.911 | 0 | True |
| Exact-MTP / mtp | longer-single | 8203 | 11.119 | 0 | 1.780 | 8192 | True |
| Exact-MTP / mtp | system-document | 8227 | 11.214 | 0 | 1.801 | 8192 | True |
| Exact-MTP / mtp | history-document | 8242 | 8.402 | 0 | 1.723 | 8192 | True |

Exact-cache mode guarantees the narrower cold/warm reproducibility contract in
upstream documentation; Flexible may alter numerical results. Matching output in a
small test is not a universal quality guarantee. The default cache mode is not
silently changed by this experiment. The original miss is retained, not discarded.

## GUFO operator qualification

The original Thomas Windows-port/TheRock 10.2 combination passed 26 of 30 operator
runs. Attention preparation and fused projection failed with tuning on and off.
Three isolated changes were checked by the original test programs, without editing
assertions or tolerances. The attention test retains its separate-operation oracle.
The projection test uses the selected PrepareAttention variant as its reference,
so these are diagnostics, not fixed-reference full-model A/B tests. Results:

| Candidate | Attention operators | Projection operators |
|---|---|---|
| Reference-style rotary expression | FAIL | FAIL |
| Angle rounding barriers | FAIL | FAIL |
| Existing single-head preparation path | PASS | FAIL |

Selecting the existing single-head path passed the full attention regression,
including chunk boundaries, replay and long positions. The fused projection
remains unresolved. This localizes one failure to the four-head batched path;
it does not prove the precise compiler transformation responsible, nor qualify
whole-model inference. No GUFO PP512/PP2048 or decode score is asserted. Candidate
patches/logs were retained locally; the research source and original build were
restored, and the published native runtime was not replaced.

## Shutdown reporting corrections

The initial stop completed engine teardown but did not meet the strict memory
baseline-recovery target inside its window. Later measurements met the original
criterion; the failed record was retained and the stale lock was archived only
after owned-container identity, terminal state and five fresh memory frames passed.

Two reporting defects were fixed without changing memory admission or runtime
limits: a running guard (`poll() is None`) is no longer classified as an abnormal
exit, and both controllers publish `stopping` before cleanup rather than continuing
to display `ready`. Recovery diagnostics retain the exact required and observed
memory values. Failure to write the stopping state cannot skip owned cleanup.

The subsequent live Flexible-mode shutdown showed `ready -> stopping -> stopped`
in both controllers and confirmed container cleanup plus memory recovery.
Regression checks: 20 gateway/controller tests passed; 108 backend tests discovered,
89 executed successfully and 19 platform-specific checks skipped. Unit tests are
not model quality or endurance benchmarks.
The fresh-source export also passed: 20 controller tests, 14 shared-helper tests,
86 backend tests (22 skipped because platform or installed artifacts were absent),
and 26 PowerShell source parses. This used the existing Python test environment;
it was not a new model/runtime installation.

## Reproduce and inspect

See [cache-shape commands](../../scripts/benchmarks/README.md#prefix-cache-shape-test).
The [machine-readable report](halogen-cache-gufo-followup-20260930.json) contains
all retained cache requests, output hashes, actual token counts, operator exits
and live lifecycle observations. The larger original benchmark remains unchanged.

[Upstream cache-mode semantics](https://github.com/peonist-ai/halogen-flash-server/blob/82c92af2289f6f1086ab8362b18669ccff36968b/docs/FLAGS.md)
and [the upstream prefix discussion](https://github.com/peonist-ai/halogen-flash-server/issues/31)
provide context; neither is used as proof of this host's measured results.

## Final verified running state

```json
{
  "phase": "ready",
  "version": "0.15.1",
  "checkpoint": "v2",
  "context": 262144,
  "cache": "Exact",
  "continuous": true,
  "model": "halogen-v2",
  "local_api": "http://127.0.0.1:8840/v1",
  "public_api": "https://strix-alloy.tail7f425a.ts.net/v1",
  "token_changed": false,
  "local_answer": "OK",
  "https_answer": "OK",
  "missing_and_wrong_token_status": 401,
  "public_test_origin": "Windows PC through the HTTPS hostname; external cloud instance not tested",
  "managed_run": "86b58bc5a2fa45469e64455486bca490",
  "backend_run": "d21787ce11614621b81e93d7c855a24e",
  "minimum_free_windows_gib": 36.93903732299805,
  "checked_at": "2026-09-30T11:10:29.235393+00:00",
  "initial_https_errors": [
    "initial_enable_validation_SSL_UNEXPECTED_EOF"
  ]
}
```
