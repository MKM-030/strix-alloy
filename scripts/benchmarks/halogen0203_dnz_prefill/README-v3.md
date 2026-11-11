# Prepared DNZ paired2048-arena v3 sources

This is a **source-only preparation**, separate from the closed v1/v2 attempts.
No v3 inference, warmup, candidate or performance result has been measured.
The original `source-manifest.json` and historical v1/v2 archive are unchanged;
`source-manifest-v3.json` binds these additional exact-byte source copies.

The new common private profile uses context/pool8192 and both Prefill controls
2048. Only native DN_Z_STREAM0/1/0 differs between the planned three arms. The
actual request remains2048 natural nonrepeated input tokens and128 outputs.
The [prospective protocol](../../../docs/benchmarks/halogen0203-dnz-prefill-plan-20261111-v3.md)
defines unchanged30/131-GiB startup,22/22-GiB entry and18/18-GiB runtime floors.
The current preflight allocation estimate is not measured Windows RAM savings.

The coordinator inherits the reviewed finite lifecycle, RAW/QPC accounting,
native mode counter and exact output/scoped parity checks. It adds exact
failed-entry memory-frame evidence and a bounded real-frame margin before
one normal-server restoration launch. A peer-found deadline bug was fixed
before any execution: frame-read time counts toward300seconds, a frame after
300 cannot qualify, and a valid stable window can finish at exactly300.

Root verified28 private coordinator/helper tests and19 offline auditor tests.
The final private execution seal binds287 exact dependencies. That seal does
not override the live game/GPU/memory checks and is not distributed as a
portable launcher. A passing source review is not an executed model test.
The normal0.20.3 instance remains separate, with32K capacity and paired8192.

`archive/dnz-arena2048-v3/` contains the prepared source, source-generation
provenance, focused tests and unchanged RAW source dependencies.
`archive/dnz-analysis-v3/` contains the separate terminal-only auditor and fake
tests. Evidence JSON files preserve source-review results, not token rates.
No DSO, model, tokenizer or complete287-member execution payload is included.
Literal private lifecycle paths and historical source bindings are intentional;
the coordinator tests need their original private fixtures and are nonportable.
Default coordinator/preparation CLI is inert. Do not activate archival code or
repin a historical cohort merely by copying this folder.

The offline fake checks can be run without a model or serving process:

```powershell
python -B -m unittest discover -s scripts/benchmarks/halogen0203_dnz_prefill/archive/dnz-analysis-v3 -p "test_*.py" -v
```

These19 tests use synthetic responses/frames and temporary RAW journals. Their
synthetic rates are assertions, not measurements. An actual terminal audit
requires Root's independently confirmed terminal process state, immutable
execution-seal SHA and exact reviewed dependency count, plus all original
private evidence. Partial or failed cohorts yield no qualified performance.
