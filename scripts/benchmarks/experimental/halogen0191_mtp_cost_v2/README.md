# Halogen 0.19.1 MTP cost-rule source archive

This directory preserves the owned source implementation of the V2 cost-rule
comparison and a portable replay of its trace-counter correction. It does not
enable an experimental policy or start an engine.

## Portable CPU replay

From a fresh repository clone, use any suitable Python 3 interpreter; only the
standard library is required. This command does not use the local service,
models, credentials, network, GPU or NPU:

```powershell
python -B -m unittest discover -s scripts/benchmarks/experimental/halogen0191_mtp_cost_v2 -p test_trace_replay.py
```

The sanitized fixture retains one real startup banner and the four request
trace lines with matching API speculation counters. The native aggregate
`accepted` was 45 while the head accepted-token counter was 69. V1 incorrectly
equated them. V2 retains `legacy_accepted` diagnostically and reconciles only
fields with corresponding API counters. The aggregate's underlying unit is
not asserted. Tests reproduce V1's failure, exercise V2 with all four real
requests and reject altered counters, IDs and startup rules.

No prompt/response text, timestamps, credentials, machine paths or process/run
identities are present in the fixture. Derivation source hashes and exact
archived file identities are recorded in `source-manifest.json`.

## Exact snapshots and their limits

`snapshots/` contains byte-for-byte copies of Root8, the trace helper, exporter,
integration preparer and focused tests. `snapshots/v1/mtp_cost_trace.py` is the
frozen failing helper used for the regression. The snapshots have not been
rewritten to run from this archive.

The coordinator, exporter, preparer and original focused tests depend on the
original machine-local `server/.local/` layout and additional pinned helpers,
profiles, RAW observer assets and run evidence. A fresh clone cannot execute
the full hardware campaign from these snapshots alone. Their original paths,
hashes and byte counts are recorded for archival comparison; the standalone
portable test above is the reproducible CPU check supplied here. Do not run
the archived coordinator as a relocated server launcher.

Models, credentials, full private logs, native binaries and generated runtime
state are not archived. The comparison protocol and source identities remain
in the unchanged [V2 plan](../../../../docs/benchmarks/halogen0191-mtp-cost-gate-plan-20261107-v2.md)
and its JSON companion. A successful CPU replay is not a throughput benchmark,
a complete cost-policy comparison or evidence of a speedup.
