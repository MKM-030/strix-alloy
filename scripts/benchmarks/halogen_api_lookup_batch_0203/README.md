# Halogen 0.20.3 CPU tool-view batching — inactive source experiment

This adapter groups two or more complete tool-response sections into one
tokenizer call inside `lookup_view`. It retains per-section BPE boundaries,
exact ordered LOOK IDs and negative-one separators, cache/LRU policy and limits.
Zero or one section uses the original scalar path. Unsupported or malformed
batch results fall back to the original scalar calls and their errors.

**The adapter is not enabled in the installed backend.** It was not part of the
separate NPU comparison. Importing these modules or invoking their default CLI
does not read the API/tokenizer, load a model, start a server or call hardware.
The package contains no full upstream API copy, tokenizer/model data, binaries
or dependency wheels. Nothing is installed or downloaded by these scripts.

## Evidence and limits

The subsequent [full serving-Transformers comparison](full_transformers/README.md)
is complete. Exact LOOK-ID/cache parity passed, but HF list batching made all
four cold multi-section cases **43.16–152.32% slower**, with 21/21 slower pairs
in each case. This candidate is rejected and remains disabled. The earlier
85-to-6 native-call result below establishes parity and call counts only.

The adapter requires this exact extracted `serve_api.py` SHA-256:
`7f529cd224e973265237d70e8b9157350302a19faffdc70c05eee3a884e2f4f4`.
It isolates the real upstream `view_segments` and `lookup_view` functions for
CPU tests without importing the API application.

The **17 preserved parity/error tests pass** with that explicitly supplied API.
They cover Unicode, empty-section separators, multiple/unclosed tool blocks,
cache hits/order/budgets, unsupported/malformed batches and original scalar/
decode errors. Original red/green logs and the independent inactive-prototype
review are retained under [`evidence/`](evidence/).

Six additional metadata-only tests check the explicit vendor binding without
loading native code. A future harness run binds both the imported package and
the actually used native tokenizer file to `--vendor`, verifies that its
`Tokenizer` class is the native export and pins both files. An empty or wrong
vendor cannot silently select a system-installed or previously imported package.

The retained [eight-case CPU receipt](evidence/cpu-harness-result.json) used the
existing target tokenizer and real `tokenizers 0.23.2` Rust backend, through a
small facade implementing the API callable/decode interface. **The complete
Transformers wrapper was not loaded and still needs qualification before use.**

| Owned synthetic tool case | Original encode calls | Candidate encode calls |
| --- | ---: | ---: |
| Four / twelve / forty-eight numbered sections | 4 / 12 / 48 scalar | 1 batch each |
| Twelve sections, three repeated requests | 12 scalar | 1 batch; subsequent cache hits |
| Eight sections in JSON `output` | 8 scalar | 1 batch |
| One JSON output section | 1 scalar | 1 scalar |
| No tool block / unrecognized tool text | 0 / 0 | 0 / 0 |
| Total | **85** | **6** |

All eight cases preserve exact LOOK IDs and cache state. This is **92.94% fewer
encode calls**, not a measured reduction in latency. No prefill, decode,
acceptance or NPU engine-speed improvement is established. The original CPU
receipt is unchanged; this export did not rerun the tokenizer harness.
That run predates the stricter module-origin binding; the new loader checks
are not retroactively claimed as observations from the retained run.

## Explicit inputs and reproduction

Inputs are supplied by CLI or these environment variables:

| Input | CLI | Environment |
| --- | --- | --- |
| Exact extracted API | `--api` | `HALOGEN0203_LOOKUP_API_SOURCE` |
| Existing target tokenizer JSON | `--tokenizer` | `HALOGEN0203_LOOKUP_TOKENIZER_JSON` |
| Existing CPU tokenizer package directory | `--vendor` | `HALOGEN0203_LOOKUP_TOKENIZER_VENDOR` |
| Fresh output path/directory | `--output` | None; explicit CLI only |

Set the API path before the CPU unit tests; an unconfigured test run skips the
17 tests instead of searching private directories or loading dependencies.

```powershell
$env:HALOGEN0203_LOOKUP_API_SOURCE = 'C:\path\to\extracted\serve_api.py'
python -B -m unittest discover -s scripts/benchmarks/halogen_api_lookup_batch_0203 -p 'test_*.py' -v
```

[`lookup-segment-batch.patch`](lookup-segment-batch.patch) is the standalone
unified diff. To export a candidate API copy and the diff into a **new, private**
directory, explicitly invoke the adapter:

```powershell
python -B -m scripts.benchmarks.halogen_api_lookup_batch_0203.adapter --prepare --api 'C:\path\to\extracted\serve_api.py' --output 'C:\path\to\new-private-output'
```

The optional real-tokenizer harness requires explicit `--run`, all three input
paths and a fresh output JSON path. It verifies the recorded tokenizer hash and
`tokenizers 0.23.2`, performs no installation and refuses to overwrite evidence.
Its CLI without `--run` is inert. The completed eight-case receipt above is the
result currently established; a new run is a separate CPU experiment.

The actual Transformers wrapper is now qualified for parity and rejected for
performance. Do not promote this batch adapter or run an engine cohort from
the call-count result. The separate [direct scalar-backend experiment](../halogen_api_lookup_direct_0203/README.md)
retains native scalar encodes while bypassing HF wrapper work. Its CPU component
timings do not establish native prefill/decode, acceptance or end-to-end gain.
