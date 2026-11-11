# Halogen0.20.3 DNZ Prefill: closed experiment archive

**No DNZ speed improvement or new performance value was qualified.** This
archive preserves two finite GPU-only attempts and their recovery evidence.
DN_Z_STREAM remains default off. It is an existing native auxiliary-stream
Prefill projection mechanism; the tiny-M Decode/MTP path is not directly changed.

| Attempt | Actual input / output cap | Context capacity | Excluded warmups | Measured requests | DNZ candidate |
| --- | --- | ---: | ---: | ---: | --- |
|v1|2048 /128|32768|0|0|Never started|
|v2|2048 /128|8192|1 Stock warmup|0|Never started|

Both stopped at the unchanged22-GiB request-entry rule. No qualified Prefill,
Decode, acceptance or DNZ difference is exported: `outcome.json` contains null
rates and an empty arm table. The v2 warmup remains excluded; its throughput
and acceptance are not copied into this archive's result. Lower native rounded
KV accounting is not proof of Windows physical-memory release or speed gain.

## Preserve the recovery history

The v1 attempt restored its normal server in its own finally path. The original
v2 campaign ended with `phase=restoration_incomplete`, `terminal=false`,
`completed=false` and `restored=false`; these flags and its restoration error
remain unchanged in the pinned original evidence. A **separate later Root
recovery** succeeded and verified normal32768-context serving on8840 plus a
functional authenticated READY smoke. That smoke is not a benchmark. The
composite closure does not rewrite the failed campaign as a successful run.

The exact independent terminal audits, closed offline partial audit and later
recovery receipt are copied unchanged under `evidence/`. `source-manifest.json`
binds every copied original source/evidence path, byte size and SHA256. The
large original execution bindings and campaign handles are retained privately
and represented by their exact external pins rather than duplicated dependency
trees. Original files were not moved or changed.

## Source layout and limits

`archive/dnz-prefill-prep/` contains v1 preparation, coordinator, read-only
counter reader and fake tests. `archive/dnz-prefill-capacity8192-v2/` contains
the v2 variants, tests and a small private RAW collector/validator layout. Its
collector changes only two optional-slot reads to default1. Its private v2
commit floor remains at least131 GiB; Prefill chunk/max8192, startup30/131,
entry22 and runtime18 GiB remain fixed. v2 fits2048+128 and explicitly rejects
an8192+128 input workload. The intended normal restoration remains32768.

These are **archival Root-only sources, not a portable launcher**. Their literal
`C:\Projects\strix-alloy-clean` lifecycle paths, exact source hashes, provider
identities and private external inputs are intentional historical bindings.
The external lifecycle implementation, active credentials, prepared execution
trees and full dependencies are not included. Import/default CLI has no engine
activation; any original `--run` requires a separately reviewed Root seal and
the matching private workspace. Do not activate or repin historical sources
merely by copying this archive. The current serving configuration is separate.

No binary, model weight, tokenizer, full upstream API or262-member dependency
payload is distributed here. Copied `.py` files are source text; the `.bin`
capture mentioned in audit pins is not included. Synthetic token rates in fake
test fixtures are assertions, not measurements.

## Offline fake checks

The self-contained archived offline auditor and its fake tests can be checked
after installation at the intended public path:

```powershell
python -B -m unittest discover -s scripts/benchmarks/halogen0203_dnz_prefill/archive/dnz-analysis-v2 -p test_offline_audit.py -v
```

These tests use temporary synthetic files and a fake RAW journal. They make no
API, WSL, process, device, compiler or model call. The archived preparation/
coordinator test suites additionally require the historical private source
inputs and normal profile, so they are not portable tests of this thin package.

`audit_terminal.py` is unchanged archival offline analysis code. Its default
CLI opens no campaign evidence. A full historical audit needs explicit terminal
confirmation, the original private evidence and its exact dependency pins; it
is not a live liveness check and does not by itself authorize promotion.
