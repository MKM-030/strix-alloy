# Halogen 0.20.3 direct scalar tokenizer: bounded CPU result

The direct Rust scalar path preserves exact LOOK IDs/cache state and reduces
CPU lookup preparation time in five cold tokenized tool cases. **It remains
inactive and default off.** No engine prefill/decode, MTP acceptance, NPU speed
or whole-request improvement was measured. This result does not establish a
route to the manufacturer's language-model token rates.

## Actual paired CPU observations

The completed isolated Root run used the exact Halogen 0.20.3 image, Python
3.12.15, Transformers 5.15.0, Tokenizers 0.22.2 and the actual Qwen2Tokenizer.
The original serving loader, all six actual tokenizer files and its environment
were retained. No tokenizer setting, thread configuration, model weight,
installed backend or live-server profile was changed.

The same eight synthetic tool fixtures each excluded one warmup per arm and
retained 21 paired observations. AB/BA order alternated, balanced 84/84 over all
cases. AST/namespace setup, file hashing, regex initialization, fixture encoding
and cache reset were outside timing. Cold view caches were independent; the
warm-cache case was primed outside timing and measures three warm calls.

| Case | Stock mean, ms | Direct scalar mean, ms | Saved mean, ms | CPU-time change | Faster pairs |
| --- | ---: | ---: | ---: | ---: | ---: |
| no-tool-block | 0.003075 | 0.003087 | -0.000012 | +0.38% | 9/21 |
| unrecognized-tool-text | 0.028419 | 0.032187 | -0.003768 | +13.26% | 3/21 |
| one-json-output | 0.119412 | 0.099943 | +0.019468 | -16.30% | 19/21 |
| four-numbered-segments | 0.292263 | 0.246908 | +0.045355 | -15.52% | 20/21 |
| twelve-numbered-segments | 0.623387 | 0.552281 | +0.071106 | -11.41% | 19/21 |
| fortyeight-numbered-segments | 2.196808 | 1.948915 | +0.247893 | -11.28% | 21/21 |
| warm-view-cache (three warm lookups) | 0.030731 | 0.031013 | -0.000282 | +0.92% | 7/21 |
| json-numbered-segments | 0.500478 | 0.452643 | +0.047835 | -9.56% | 18/21 |

Negative CPU-time change means faster. The five cold cases that actually encode
segments save 9.56–16.30% of this component's mean time. The largest **mean** saving
is 247,892.524 ns (**0.247893 ms**) for 48 sections; its median paired saving is
0.248564 ms, with 21/21 faster pairs. The other changed cases win 18–20/21 pairs.
All controls remain in the table: unrecognized tool text and the warm-cache case
do not improve. These are complete `lookup_view` CPU times, including decode,
section extraction, native encoding and view-cache work, with observer overhead.
No statistical confidence interval or universal request/machine claim is made.

## Real path and parity

Untimed profiling observed the exact real HF object's dispatch, without a
counter facade. Stock entered the HF wrapper 85 times; the direct arm entered
it 0 times and retained the actual Qwen2Tokenizer/nativeTokenizer/BPE binding.
The original scalar native encodes still occur; no reduction in their count is
claimed. Profiling was restored before timing, and timed calls reject an active
profiler. All measured pair outputs match exactly. The harness also checked
complete ordered cache state in memory; the saved audit preserves those parity
flags and independently compares each saved output hash/count.

The guard binds the three actual HF source files/software versions and checks
the exact types, backend alias, deterministic BPE, padding/truncation and special-
token state. Unknown or changed state uses the original HF scalar fallback,
including original errors and overlength warnings. Arbitrary monkeypatches or
concurrent tokenizer mutation are not qualified. The source-design note is
retained as historical context in CONCEPT.md.

## Evidence and reproduction

The unchanged 283,621-byte [`evidence/result.json`](evidence/result.json) contains
all 16 excluded warmups and 168 raw measured pairs. The standalone
[`audit_result.py`](audit_result.py) independently recalculates every aggregate
from raw integer nanoseconds and validates the real-path proof/order/parity:

```powershell
python -B audit_result.py --audit --result evidence/result.json --output new-recalculation.json
```

[`evidence/recalculated.json`](evidence/recalculated.json) records those checks.
`full_transformers_harness.py` and `direct_backend_adapter.py` are byte-identical
to the executed sources. No full upstream API, tokenizer/model files, native
binaries or wheels are included. The fake tests require explicit
`HALOGEN0203_LOOKUP_API_SOURCE` and `HALOGEN0203_LOOKUP_HF_SOURCE` paths and patch
all actual HF/native imports to fakes.

The lifecycle summary confirms successful completion, owned-container cleanup,
normal-server preservation and minimum reserve 22.766987 GiB. This export only
read/copied Root's files; it did not launch another tokenizer/container run.
The rejected HF-list-batch experiment remains separate. Any future integration
needs a distinct opt-in source manifest and whole-request tool-workload evidence;
component milliseconds are not converted into engine tok/s or a fabricated
zero/nonzero acceptance delta.

The intended repository destination is
`scripts/benchmarks/halogen_api_lookup_direct_0203/`. All source/test pairs here
are self-contained except the deliberately unbundled, exact upstream API and
three pinned HF source files. No sibling batch-harness path is assumed. For
fake CPU verification from the repository root:

```powershell
$env:HALOGEN0203_LOOKUP_API_SOURCE = 'C:\path\to\extracted\serve_api.py'
$env:HALOGEN0203_LOOKUP_HF_SOURCE = 'C:\path\to\pinned\hf-source'
python -B -m unittest discover -s scripts/benchmarks/halogen_api_lookup_direct_0203 -p 'test_*.py' -v
```

For a future Root-owned isolated CPU run, the harness accepts explicit
`--api`, `--adapter`, `--tokenizer`, `--tokenizer-source`, `--output` and
`--iterations` arguments with `--run`. It uses its local direct adapter; it
does not require the rejected list-batch experiment. Default invocation is inert.
