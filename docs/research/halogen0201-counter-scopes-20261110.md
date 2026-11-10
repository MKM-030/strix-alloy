# Halogen 0.20.1 API head and native chain counters

The API's head counter and the diagnostic chain counter cover different paths.
The API includes single-step head drafts outside the chain path. The maintainer
defines accepted tokens as accepted proposals excluding base tokens, and the
per-source API counters as retaining the aggregate draft totals.
[Accepted/proposed definition](https://github.com/peonist-ai/halogen-flash-server/issues/124#issuecomment-5936194462),
[per-source accounting](https://github.com/peonist-ai/halogen-flash-server/issues/175#issuecomment-6172147051).

Four complete 8192-input / 128-output reference requests produced this exact
observation under 0.20.1:

| Counter | API head | Native chain trace |
| --- | ---: | ---: |
| Rounds | 64 | 63 |
| Drafted | 106 | 105 |
| Accepted | 63 | 62 |

Lookup and grammar counters were zero. The native total was 64 rounds. The
original comparison rejected exact equality, so that cost study did not qualify.
The reference phase journals and responses were independently validated; no cost
candidate was measured in that attempt.

Fresh native producer and consumer inspection for engine SHA256
`7a72e138f0090008d171e41358a23f86a875fe92fadbcbc5daf2d3225e426577`
establishes these mappings from the native statistics object:

```text
neural rounds       = stats[0x08]
chain rounds        = stats[0xa0]
chain drafted       = stats[0xa8]
chain accepted      = stats[0xb0]
API head drafted    = neural rounds - chain rounds + chain drafted
API head accepted   = stats[0x10] + stats[0xb8]  (no lookup/grammar activity)
```

The API obtains head rounds from the wire round total minus lookup/grammar
rounds. Its accepted total follows wire commit minus rounds, shared tokens and
lookup/grammar accepted tokens. The diagnostic chain trace omits `stats[0xb8]`.
Its accepted total therefore cannot independently reconstruct the full API
accepted total. The observed difference does not justify a fixed `+1`, a general
cross-scope acceptance bound or a claim about which initial/final step caused it.

The separately registered [V5 protocol](../benchmarks/halogen0201-mtp-cost-gate-plan-20261110-v5.json)
checks the exact source-derived rounds/drafted relations, lookup/grammar counts,
native rule banner and internal counter validity. It retains API head and native
chain counters separately. `acceptance_independently_reconciled` remains false.
Performance qualification still requires all six complete cohorts, independent
RAW/QPC timing, unchanged controls, identical outputs and the existing resource
checks. No old failed protocol is retrospectively declared successful.

The published API acceptance observations remain unchanged. They are labeled
API-reported; the unresolved independent full-acceptance reconstruction remains
an open item in the optimization goal.
