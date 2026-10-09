# Halogen 0.17.3: causal longer-match PLD prototype

A bounded CPU prototype changes one retained PLD offer and improves its exact
prefix from one to three IDs. It is not integrated into serving. No Prefill,
Decode, latency, NPU result or changed-trajectory acceptance was measured.

The policy scans only the copied 64 already committed IDs. It finds earlier
exact trigrams whose full three-ID continuation is already committed and whose
first ID equals stock proposal zero. It chooses the longest backward match,
breaking ties by the newest occurrence, and changes tail slots only when the
match exceeds three. Width and opening stay unchanged. Ordinary-token metadata
is frozen from the pinned tokenizer. No future labels enter prediction.

| First fixed offline screen | Count |
| --- | ---: |
| Complete stock PLD frontiers | 96 |
| Longer compatible matches | 14 |
| Changed offers | 1 |
| Reconstructible future-label frontiers | 94 |
| Stock / candidate exact-prefix ID totals | 235 / 237 |
| Improved / worsened frontiers | 1 / 0 |

The sole improvement is native wire 15, round 44, with cached opening equal to
stock proposal zero, stock width three and native allowance three. Wires 9/37
and 13/54 remain unscorable. Labels use exact suffix overlap within the same
session, owner birth, slot cookie and epoch. All 94 reconstructed stock prefix
lengths agree with recorded native outcomes. These are scores on frozen stock
frontiers, not a rollout: a changed accepted length can change later boundaries.

All 96 proposals were serialized and SHA256-sealed in memory before the sole
future-label scoring pass. Durable archival and recovery of the exact executed
source occurred afterward. Predictor-only recovery reproduced the original
proposal hash `be54505c785271d76f1808b27f72618df9f2a0b82e6730c0a7b2d37488157c62`.
The allocation-free [C++ predictor](../../scripts/research/halogen0173_causal_pld64/longmatch64.h)
then matched all 96 frozen proposals, with zero mismatches and unchanged
openings. No policy sweep, refitting, second scoring pass or device runtime ran.

The [first result](halogen0173-causal-pld64-20261009/initial-result.json),
[eligibility assessment](halogen0173-causal-pld64-20261009/eligibility.json),
[C++ match](halogen0173-causal-pld64-20261009/cpp-match.json) and
[publication manifest](halogen0173-causal-pld64-20261009/publication-manifest.json)
retain exact source/evidence hashes. Root verified all 15 private sealed files
and copied an explicit whitelist of 11 source/evidence snapshots byte for byte.
Snapshots retain their original local paths and historical private-scope text;
the manifest identifies this subsequent publication. DLL/object/model files and
tokenizer payloads are excluded. The six source snapshots are an archive, not
a portable installed provider or live benchmark harness.

One positive frontier gives limited utility evidence. The complete guarded
same-owner consumer transaction, immediate provider integration, invalidation,
relay draining, native state/output parity and total added overhead remain
unqualified. No serving cohort is recommended solely from this small result.
This tiny CPU scan supplies no plausible reason for NPU placement; no NPU
producer was added. The current server stays available with fixed MTP2 and
PLD3,3. The broader acceleration goal remains unachieved.
