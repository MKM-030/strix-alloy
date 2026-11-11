# Scalar catch-up for an NPU proposal worker

This disabled experiment addresses the late proposals observed in the first
real NPU handoff. The worker takes up to 16 authoritative commit events already
in its queue, without waiting to collect more. It validates each intermediate
prefix hash, sequence and identity before invoking the model.

The recurrent model still executes one scalar forward per actual token.
Intermediate forwards omit the host logit-row copy, finite/argmax scans and
state snapshot. The final forward returns a complete owned BF16 row and saves
one snapshot before releasing the preceding anchor. Cached state promotion,
rollback and END/BEGIN ordering remain covered by the CPU tests.

The 18 portable tests use fake engines and C bindings:

```powershell
python -B -m unittest discover -s scripts/benchmarks/halogen_flm_streaming_producer/catchup_v2 -p "test_*.py"
```

The new Windows C wrapper compiles with the qualified FLM 1.0.12 SDK and exports
`sl1012_append_only`. Native endpoint parity and timing remain unqualified at
publication. No native binary or model is included. See the unchanged-source
hashes in `source-manifest.json` and the [first live result](../../../../docs/benchmarks/halogen0201-real-npu-partial-20261111.md).

The GPU target retains its existing kernels. Potential benefits are earlier
NPU proposals and less shared-memory traffic. GPU-only speed, whole-engine
prefill/decode rates and MTP acceptance require their own measured evidence.
