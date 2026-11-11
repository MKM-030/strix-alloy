# Halogen 0.20.3: CPU tool-view preparation comparisons

Both experiments are complete and remain disabled in normal serving. The
actual tokenizer produced identical ordered LOOK IDs and cache state. This
checks CPU preparation of tool-response views; it is not a model throughput
benchmark. The normal 0.20.3 server stayed online throughout.

The experiments used the installed image's Python 3.12.15, Transformers 5.15.0,
Tokenizers 0.22.2, actual serving loader and six tokenizer files. Each experiment
used eight fixed cases, one excluded warmup per arm/case and 21 alternating
stock/candidate pairs per case. Timed calls used genuine tokenizer objects,
without count wrappers or profiling. Initialization, AST construction and cache
reset were outside timing. No model weights, GPU, NPU or HTTP requests were used.

## HF list batching: rejected

All four cold multi-section cases were slower in every one of their 21 pairs.
Their CPU time increased by 43.16–152.32%, despite the earlier demonstrated
reduction from 85 to six encode calls. Keep this candidate disabled; these
results do not justify a model cohort.

[Complete results, raw pairs and reproduction](../../scripts/benchmarks/halogen_api_lookup_batch_0203/full_transformers/README.md).

## Direct scalar native backend: component improvement only

This separate adapter bypasses HF wrapper dispatch while retaining the same
native scalar encodes. Untimed inspection proves 85 stock HF dispatches versus
zero direct-arm HF dispatches; it does not claim fewer native encodes.

| CPU lookup case | Stock mean, ms | Direct mean, ms | CPU time change |
| --- | ---: | ---: | ---: |
| One JSON output | 0.119412 | 0.099943 | -16.30% |
| Four sections | 0.292263 | 0.246908 | -15.52% |
| Twelve sections | 0.623387 | 0.552281 | -11.41% |
| Forty-eight sections | 2.196808 | 1.948915 | -11.28% |
| JSON, eight sections | 0.500478 | 0.452643 | -9.56% |

The largest mean saving is approximately **0.248 ms per lookup**. Controls
remain reported in the full ledger: no-tool input is 0.38% slower, unrecognized
tool text 13.26% slower, and three warm-cache calls together 0.92% slower. The
relative improvements apply to these CPU cases and exclude one-time binding.
They do not establish first-token or complete-request improvement.

[Direct source, complete controls, raw pairs and reproduction](../../scripts/benchmarks/halogen_api_lookup_direct_0203/README.md).

Both owned CPU containers finished, were removed, and preserved the original
server identities/source files. Their lifecycle records report minimum reserve
22.76245 and 22.76699 GiB respectively; individual polling frames were not
retained, so these minima are reported aggregates. Neither experiment qualifies
new native prefill/decode tok/s, MTP acceptance or an NPU speed difference.
The small direct-path saving alone does not justify another engine restart or
promotion. Normal serving continues without either experimental adapter.
