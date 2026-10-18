# Halogen 0.18.5 strict-tool grammar drafting — 15 October 2026

**Retain on.** Both ON bookends beat OFF beyond their relative drift.

One frozen read-only fictional incident-summary request is compared with grammar drafting ON → OFF → ON, while strict schema enforcement remains enabled. No tool is dispatched. The first/final profiles omit the drafting flag (shipped default 1); OFF only adds HALOGEN_GRAMMAR_DRAFT=0. All use greedy MTP, Thinking Off, no_store, fixed 2/gate 0, PLD3,3, native 64 readers and full 262K. Different lifecycle identities are expected; image/context/settings/source pins are matched.

| Window | Actual input/output per measured request | All measured HTTP walls (s) | HTTP mean ± SD (s) | Exact successful tasks | Tokens / whole HTTP s |
|---|---|---|---:|---:|---:|
| on-before | 547/135, 547/135, 547/135 | 2.2167870, 2.2059965, 2.2081561 | 2.210313 ± 0.005710 | 3/3 | 61.077317 |
| off | 547/135, 547/135, 547/135 | 2.6597372, 2.4697050, 2.6282408 | 2.585894 ± 0.101848 | 3/3 | 52.206310 |
| on-after | 547/135, 547/135, 547/135 | 2.3785731, 2.2125109, 2.2345763 | 2.275220 ± 0.090184 | 3/3 | 59.334919 |

OFF HTTP changes by +16.992213% versus first ON, +13.654689% versus final ON and +15.299304% versus their mean. Absolute ON bookend drift is 2.936548%.

The symmetric directional rule was frozen before collection: let d=abs(ONafter/ONbefore−1). ON wins only if 1−ONi/OFF>d for both bookends; OFF wins only if 1−OFF/ONi>d for both. Inconclusive retains ON. Root owns final serving selection; the report changes no profile.

One warmup per window is excluded from the table and retained separately with its HTTP wall, full quality and strict/path evidence. All 12 raw attempts and all 9 measurements remain. There is no statistical-significance, general ServiceNow workload, sampler or quality-distribution claim.

Exact frozen API request: [incident-summary.request.json](../../server/.local/halogen0185-goal-continuation-20261015/next-grammar-prep/incident-summary.request.json), SHA-256 `568e8e617b0d34d2b0da15d4f3e97e4fc73b7cc94b22976f6890f2a3e9226eea`. It uses a forced `emit_incident_summary` function with `strict:true`, eight freely typed required fields, and no schema enum/const answer oracle. The actual request body is also retained in the JSON report.

Every response has exactly one API `tool_calls` entry for `emit_incident_summary`; the `function.arguments` field is a JSON string. Its expected decoded value is:

```json
{
  "incident_number": "INC0010427",
  "priority": "2",
  "state": "2",
  "business_service": "Employee onboarding",
  "assignment_group": "Identity Operations",
  "affected_users": 27,
  "contains_pii": false,
  "short_description": "New starters get HTTP 403 at /api/now/table/incident"
}
```

The complete exact argument string is identical across all 12 replies and retained per reply in JSON, alongside parsed values and types. The call is inspected as an extraction artifact and never dispatched.

| Window/source | Accepted/drafted (three measured replies) | Acceptance | Rounds | Accepted/round |
|---|---:|---:|---:|---:|
| on-before / head | 75/75 | 100.000000% | 39 | 1.923077 |
| on-before / lookup | 66/69 | 95.652174% | 24 | 2.750000 |
| on-before / grammar | 156/162 | 96.296296% | 45 | 3.466667 |
| off / head | 153/153 | 100.000000% | 78 | 1.961538 |
| off / lookup | 120/132 | 90.909091% | 54 | 2.222222 |
| off / grammar | 0/0 | unavailable | 0 | unavailable |
| on-after / head | 75/75 | 100.000000% | 39 | 1.923077 |
| on-after / lookup | 66/69 | 95.652174% | 24 | 2.750000 |
| on-after / grammar | 156/162 | 96.296296% | 45 | 3.466667 |

| Window | Combined accepted/drafted | Combined acceptance |
|---|---:|---:|
| on-before | 297/306 | 97.058824% |
| off | 273/285 | 95.789474% |
| on-after | 297/306 | 97.058824% |

Head, lookup and grammar scopes remain separate. A head-only 100% describes accepted head drafts divided by drafted head tokens on this fixture. Combined acceptance includes all three sources: each ON bookend is 297/306 = 97.058824%. Neither counter is a general quality or population guarantee. Positive ON grammar rounds and zero OFF rounds/drafts/accepts establish that the selected path was exercised. API head accepted counts derive from committed/round/shared/lookup/grammar accounting; grammar fields map native D counters when supplied. These are not per-position marginals or an independently measured component-cost decomposition. No universal output=1+rounds+accepted identity is assumed for terminal tool calls.

**API phase rates remain independently unqualified observations.** Pooled values divide summed actual tokens by summed reported API phase seconds; arithmetic means, all per-request phase/HTTP discrepancies and raw fields remain in JSON. No phase scaling, subtraction or outlier attribution is applied.

| Window | Pooled API prefill* | Mean API prefill* | Pooled API decode* | Mean API decode* |
|---|---:|---:|---:|---:|
| on-before | 991.301196 | 991.351000 | 73.761087 | 73.761000 |
| off | 1068.289825 | 1068.331667 | 65.472534 | 65.581667 |
| on-after | 977.833393 | 978.177333 | 71.340497 | 71.482667 |

Full qualification: True. Every warmup and measured reply is checked for exactly one declared function, exact eight field values/primitive types, full tool_calls finish below 512 tokens, no content/reasoning/cache/clamp, exact function/arguments TEXT/payload/input/output/finish parity, and native 1-of-1 strict enforcement. Random call IDs/created timestamps are excluded from parity. Strictness is proved from newly appended bounded engine-log slices and per-request exclusive gateway counts, rather than parsed HTTP JSON alone.

This validates one complete structured extraction artifact; grammar drafting does not supply factual values. Both arms enforce the same strict target. The collector never executes model-generated code or the returned function. General code quality and incident diagnostic-plan quality from the separate sampled screen are not improved or pooled by this fixture.

Raw/client/request/log hashes, bounded log offsets/statuses, all errors and failed-attempt HTTP costs, memory/traffic guards, source/profile/manifests and the predeclared selection protocol are retained in JSON. Reporting performed no live API, hardware, lifecycle or production mutation. Root separately owns readiness and the final selected serving profile.
