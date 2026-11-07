# Halogen 0.19.1 managed WSL2 backend

This package binds the immutable 0.19.1 image, executable, API and entrypoint.
The WSL memory bridge uses fresh executable-byte, frame and transfer checks.
Four CPU products were rebuilt against the selected image headers.

The local v2 text runtime was verified with two 32768-position slots, a
65536-position KV pool, concurrency two and paired 2048 prefill settings.
The API advertises `halogen-v2` on port 8840 and uses the existing public
ServiceNow credential. The normal start command and authentication contract
are documented in the [integration guide](../../docs/integrations/halogen-servicenow.md).

Startup admission is 30 GiB physical availability and 131 GiB commit headroom.
Runtime reserve is 18 GiB for both counters. The two-slot request-entry guard
requires 22 GiB for both. The installer reuses complete model receipts after
file identity checks. `Install.ps1` accepts the local model and DXG paths.

The [update record](../../docs/research/halogen0191-update-20261107.md) retains
image provenance, compatibility work and local runtime evidence. The
[8K/16K observations](../../docs/benchmarks/halogen0191-natural-8k16k-20261107.md)
report API phase values and Windows QPC whole-request times.
