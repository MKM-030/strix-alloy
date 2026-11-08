# Halogen 0.20.0 installation and qualification status - 8 November 2026

Halogen **0.20.0**, using the upstream **ROCm 10.1** image, is installed locally.
The version-specific integration and focused CPU checks have passed. Runtime,
authenticated generation and performance qualification remain pending: no
0.20.0 ready endpoint or benchmark result is claimed.

The latest physical free-memory checkpoint was **27.028 GiB**, below the
user-authorized **30 GiB** startup floor. Startup also requires 131 GiB free
commit. The physical/commit runtime reserve remains 18/18 GiB, and new
measurement or request entry requires 22/22 GiB. Installation success does not
waive these limits.

## Pinned installation

- [Official release tag](https://github.com/peonist-ai/halogen-flash-server/tree/v0.20.0).
- Image: `ghcr.io/peonist-ai/halogen-flash-server@sha256:2d2c55a17e71f1aaf812b4e4cf0783dc5a8258461f8b3d9d7d84a9697fcfe637`.
- Engine SHA256: `b40c3983c6c02f82a6f2e7b0cd4c2db92dbe0a09190d5d73057de14855f6cfdd`.
- [Release metadata](../../backends/halogen-wsl2-0.20.0/profiles/release.json)
  retains migration pins separately from runtime qualification.

## Local launch configuration

From the repository root, using Windows PowerShell 5.1:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\Start-Halogen-ServiceNow.ps1 -Profile CurrentText32K -Slots 1 -KvPoolPositions 32768 -Concurrency 1 -PrefillTokens 2048 -ConsoleTrace
```

This selects v2, one slot and concurrency 1, a 32768-position context and KV
pool, paired 2048-token prefill chunk/arena, adaptive MTP gate 0.90, PLD `3,3`,
Cache Off, Thinking Off/low, Vision Off and prefetch 0. The existing ServiceNow
credential, model alias `halogen-v2` and configured API base
`http://127.0.0.1:8840/v1` are preserved. A configured endpoint is not evidence
that it is listening; wait for `gateway_listening` and successful readiness.
The normal controller owns lifecycle, singleton enforcement and memory checks.

## Last qualified measurements belong to 0.19.1

These historical results are **not 0.20.0 measurements or expected rates**.
They used genuine contiguous novel inputs, one 32768-position slot, paired
2048 prefill settings, 128 actual output tokens, one excluded warmup and three
measured requests per input length. RAW rates include observer overhead.

| Actual input tokens | RAW prefill tok/s | RAW decode tok/s | Native head accepted/drafted |
| ---: | ---: | ---: | ---: |
| 8192 | 1143.700731 | 48.574773 | 207/327 (63.30275%) |
| 16384 | 1124.357529 | 49.677162 | 210/321 (65.42056%) |

See the [0.19.1 update](halogen0191-update-20261107.md) and
[qualified prefill-control report](../benchmarks/halogen0191-prefill4096-raw-20261107.md).
A fresh release needs its own output hashes, exact native counters, excluded
warmup and repeated measurements before a performance comparison is published.
No NPU throughput gain or newly qualified cost-gate result is claimed.
