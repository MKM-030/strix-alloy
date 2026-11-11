# Stateful NPU proposal producer

This default-off experiment uses a serial FLM 1.0.12 NPU actor to propose up to
three shared-vocabulary token IDs. It commits only authoritative target IDs.
An exact matching prefix promotes its cached state; a correction restores the
last matching state and forwards the actual suffix. Publication contains full
prefix hashes and never supplies recorded future target IDs to Halogen.

The core source is copied unchanged from the locally qualified producer. Its
retained-prefix replay compared 129 states and 32,001,030 BF16 values exactly.
That replay used recorded target feedback to test state correctness. It did not
measure proposal arrival before GPU demand, Halogen MTP acceptance, prefill or
decode throughput. See [the qualification report](../../../docs/benchmarks/halogen0201-streaming-npu-qualification-20261111.md).

`service_request_scoped_v2.py` creates the native context lazily after a valid
BEGIN, releases it on request retirement and accepts a nonce-bound stop file.
The Windows service makes one reverse TCP connection to an explicitly owned
listener; it neither reconnects nor changes firewall or global WSL settings.
The caller must own admission, the finite process lifetime, loaded-provider
verification, the paired GPU comparison and normal-server restoration.

The native wrapper requires the matching FLM SDK, model, kernel bundle and
runtime, supplied separately through explicit command arguments. No native
binary, model, driver or kernel bundle is included. Merely importing these
modules does not start a native engine. The normal Halogen server does not
enable this producer.

CPU-only tests use fake engines and transports:

```powershell
python -B -m unittest discover -s scripts/benchmarks/halogen_flm_streaming_producer -p "test_*.py"
```

`source-manifest.json` records the unchanged publication hashes. The native
wrapper, actor and transport still require an actual controlled live comparison
before any serving-speed claim or deployment.
