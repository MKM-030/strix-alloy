# Halogen 0.20.7 draft-vocabulary Q8: bracketed 8K/16K campaign

The 22 November `Q4 before -> Q8 candidate -> Q4 after` campaign completed all
24 requests and restored the unchanged stock server. The candidate changed one
profile setting only: `HALOGEN_DRAFT_VOCAB_Q8=1`. Both controls omitted that
setting. Q8 increased native-head acceptance at both prompt sizes, but it did
not pass the speed promotion rule at 16K and therefore remains disabled.

## Result

| Arm | Actual input tokens | API prefill tok/s | API decode tok/s | Pooled decode tok/s | Native-head accepted/drafted | Whole HTTP mean, s |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| Q4 before | 8192 | 1973.278333 | 57.514333 | 57.514304 | 192/291 = 65.9794% | 6.423521 |
| Q8 candidate | 8192 | 2024.432333 | 58.325000 | 58.321436 | 198/279 = 70.9677% | 6.261488 |
| Q4 after | 8192 | 2035.000000 | 57.763667 | 57.763471 | 192/291 = 65.9794% | 6.269291 |
| Q4 before | 16384 | 1948.665667 | 55.645000 | 55.644916 | 180/279 = 64.5161% | 10.742251 |
| Q8 candidate | 16384 | 1986.288667 | 55.704000 | 55.703841 | 183/273 = 67.0330% | 10.571807 |
| Q4 after | 16384 | 2008.363000 | 55.729667 | 55.729711 | 180/279 = 64.5161% | 10.482233 |

Each row excludes one warmup and aggregates three measured requests. Every
request used the exact frozen non-repetitive input, 128 output tokens,
temperature 0, seed 1, Cache Off with `prompt_cache_policy=no_store`, Thinking
Off, Vision Off, MTP gate 0.90, PLD `3,3` and decode prefetch Off. Output hashes,
token counts and `finish_reason=length` match across all three arms at each
size.

Prefill and decode are native API phase-clock observations. No RAW observer was
present, so they are not independently qualified as absolute phase throughput.
The bracketed comparison uses the same collector and timing convention for all
arms. Whole-HTTP timing starts immediately before dispatch and ends after EOF.

## Candidate deltas

Decode deltas below use pooled phase time, which is the campaign's promotion
metric. HTTP improvement is positive when Q8 is faster. Prefill is diagnostic;
it is reported but is not a promotion gate.

| Input | Control | Prefill change | Pooled decode change | Acceptance change | HTTP improvement |
| ---: | :--- | ---: | ---: | ---: | ---: |
| 8192 | Q4 before | +2.5923% | +1.4034% | +4.9884 pp | +2.5225% |
| 8192 | Q4 after | -0.5193% | +0.9659% | +4.9884 pp | +0.1245% |
| 16384 | Q4 before | +1.9307% | +0.1059% | +2.5168 pp | +1.5867% |
| 16384 | Q4 after | -1.0991% | **-0.0464%** | +2.5168 pp | **-0.8545%** |

The promotion contract requires exact output parity plus higher pooled decode
throughput and lower whole-request time than **both** Q4 controls at **both**
input sizes. Q8 passes both speed gates at 8K, but fails both against the 16K
after-control. Acceptance is deliberately not sufficient on its own. Final
decision: `promote=false`.

The activation evidence is positive: the candidate service manifest contains
`HALOGEN_DRAFT_VOCAB_Q8=1`, both control manifests omit it, and all arms expose
positive native-head counters. Aggregate native-head rounds fall from 384 in
each Q4 control to 375 with Q8, consistent with the higher acceptance. This
mechanism result does not override the failed 16K speed gate.

## Fixed runtime and restoration

All arms used Halogen API/engine 0.20.7, v2, one slot, 32768 context/slot/KV
positions, paired 8192 prefill settings, the `r2-ht4` drafter and the
`REV:N Performance` Windows power profile. Stock profile SHA-256 was
`69d28caee11c0e23eb2e8dba4bc0910ffbbeef7bde9656186baa4abf7cac385d`;
the Q8 candidate profile was
`d5cf920b70583dbd5d1b525bffa46994a7e9b585825f5a2f053b54a9ffed9c87`;
source-manifest SHA-256 was
`574bfad341728635b13457cbdb1eb769f9f55be32a4d868f7ea1bad90e0970e0`.

The campaign ended at `2026-11-22T17:08:55.402173Z` with
`completed=true`, `restored=true` and no pending restoration. The restored
stock server was ready on port 8840 with controller run
`9b73b4f365b84b8d85baf106cecaf3f0` and backend run
`ce8976b3130f4a42aa7a339b0265c02a`. These are dated completion identities,
not durable live-state claims.

## Scope relative to other numbers

This report supersedes neither the earlier
[22 November deployment confirmation](halogen0207-performance-natural-8k16k-20261122.md)
nor its raw evidence. That separate collection recorded 1618.895333/51.575000
prefill/decode tok/s at 8K and 1534.869667/49.656333 at 16K. It was not a
bookend control for this campaign. The higher Q4 values here are an observed
later Performance-mode window; the separate runtime window prevents assigning
their difference to one optimization.

The upstream 0.20.7 table reports about 1983 prefill tok/s on its synthetic 8K
`sweep` workload and 70.2 decode tok/s on selected English prose. Those are
different prompts and benchmark procedures and are not matched comparisons to
this frozen natural-text cohort. See the
[publisher's benchmark conditions](https://peonist.ai/halogen/benchmarks.html).

The compact [machine-readable record](halogen0207-draft-vocab-q8-20261122.json)
contains the aggregate values, deltas, decision and evidence hashes.

## Evidence

Local evidence root:
`server/.local/halogen-update-20261122/primary0207/q8-cohort-prep-v1/q8-campaign-run-v3`

| File | SHA-256 |
| :--- | :--- |
| `handle.json` | `3f7b8c65e639895306952b8a6f3bccf9ebedb76250ad7a1cee02fbaa616e89e6` |
| `before/summary.json` | `e2b3d2b7cfa54611c9c098753993cea445da4777eeb736cb4702a8f640917f12` |
| `candidate/summary.json` | `dfacc0447bf8789106bb7da01fc1b812d75aa9f5f09755a2b7de1c669cc6f783` |
| `after/summary.json` | `691f41f8dfa88c70161d7901004feb43b2775e714c44db523a54a2e73c504db7` |

The live actor was independently approved at SHA-256
`fd8da2201672284e955f2d9a6d2afdf18316a515c388ba8dc3fdb643e49220c4`;
its test file was
`840ba18e04cdd65f6e05e48639bd6e7c96cee93ea65a1bc41e237642037058b1`.
All 92 offline contract tests passed before the single live campaign.
