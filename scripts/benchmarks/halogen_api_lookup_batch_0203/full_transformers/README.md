# Halogen 0.20.3 HF tool-view batching: rejected CPU candidate

**Keep this path disabled.** Exact LOOK IDs/cache state passed with the actual
serving Hugging Face tokenizer, but list batching increased CPU preparation
time in all 21 pairs of every multi-section case. No active backend or NPU
comparison used this candidate. The normal server remained online and unchanged.

## Actual result

The isolated Root-run used Python 3.12.15, Transformers 5.15.0, Tokenizers 0.22.2
and `transformers.models.qwen2.tokenization_qwen2.Qwen2Tokenizer` from the exact
0.20.3 image. It executed the actual serving loader without added kwargs and
used the actual six tokenizer files. `HF_HUB_OFFLINE=1` was retained;
TOKENIZERS_PARALLELISM, OMP_NUM_THREADS, RAYON_NUM_THREADS and the template
override remained unset. No dependency was installed and no model weights,
HTTP endpoint, GPU or NPU were accessed.

The original eight fixture bodies and three untimed fallback/cache checks
passed. Untimed encode calls still fell from 85 to 6. That call reduction did
not translate into lower CPU lookup time with the full HF wrapper.

Each case excluded one warmup per arm, then completed 21 interleaved pairs.
Stock/batch order alternated; 84 pairs started stock and 84 started batch over
all cases. AST/namespace construction, tokenizer/fixture loading, regex setup,
cache reset and count instrumentation stayed outside timed calls. Cold cases
had independent empty view caches. The warm case was primed outside timing and
records the sum of three warm lookup calls per observation.

| Case | Stock mean, ms | HF batch mean, ms | Change | Slower pairs |
| --- | ---: | ---: | ---: | ---: |
| no-tool-block | 0.003470 | 0.003457 | -0.37% | 13/21 |
| unrecognized-tool-text | 0.028540 | 0.031916 | +11.83% | 19/21 |
| one-json-output | 0.112208 | 0.112667 | +0.41% | 11/21 |
| four-numbered-segments | 0.326732 | 0.762496 | +133.37% | 21/21 |
| twelve-numbered-segments | 0.646672 | 1.465432 | +126.61% | 21/21 |
| fortyeight-numbered-segments | 2.264150 | 3.241422 | +43.16% | 21/21 |
| warm-view-cache (three warm calls) | 0.031183 | 0.034745 | +11.42% | 17/21 |
| json-numbered-segments | 0.480606 | 1.212641 | +152.32% | 21/21 |

Positive change means **slower**. These are arithmetic means of complete
`lookup_view` CPU calls: decode, section extraction, encoding and cache work.
The four multi-section cases regress by 43.16–152.32%; each has 21/21 slower
candidate pairs. The small control cases and all raw observations remain
reported rather than selecting only favorable rows. No statistical confidence
interval or cross-machine generalization is claimed.

There is no new engine prefill/decode, MTP acceptance or NPU token-rate result.
Component nanoseconds are not converted into engine tok/s. The earlier Rust
facade used Tokenizers 0.23.2; it established call counts/ID parity, not latency
of this actual 0.22.2/Transformers stack. A direct native-backend variant would
be a new candidate, not a reinterpretation of this rejected HF-list-batch arm.

## Recalculation and source

[`evidence/result.json`](evidence/result.json) is an unchanged copy of Root's
complete 277,238-byte ledger, including all 16 excluded warmups and 168 measured
pairs. [`evidence/recalculated.json`](evidence/recalculated.json) independently
recomputes every saved mean, median, range, standard deviation and paired
difference from the individual nanoseconds. It checks order, output hashes,
call counts and direct-tokenizer timing. Complete cache equality was checked
in memory by the actual harness; the audit retains that parity flag and does
not claim to reconstruct unrecorded cache arrays from timing rows.

```powershell
python -B audit_result.py --audit --result evidence/result.json --output new-recalculation.json
```

`full_transformers_harness.py` is byte-identical to the executed source. The
batch adapter is the separate published `halogen_api_lookup_batch_0203` source
at SHA-256 `c262083f18eea8df0e5cf5e03bc710a721ddc0f7882f95333979265fae6d0e18`.
No full vendor API, tokenizer/model bytes, binary or wheel is included here.
The copied fake tests use explicit `HALOGEN0203_LOOKUP_API_SOURCE` and
`HALOGEN0203_LOOKUP_ADAPTER_SOURCE` paths; they load no actual tokenizer.

The preserved lifecycle summary confirms completion, owned-container cleanup,
normal-server preservation and a minimum observed physical/commit reserve of
22.762447 GiB. Root's original files were read and copied, never modified by
this export. The harness remains explicit-run and source-only by default.
