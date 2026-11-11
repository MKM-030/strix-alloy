# Halogen 0.20.2 — installed and online, 11 November 2026

Engine and API both report **0.20.2**. The existing authenticated endpoint
`http://127.0.0.1:8840/v1` returned **READY** using model alias `halogen-v2`.
The normal server is left running in a visible Windows PowerShell 5.1 console.
The ServiceNow credential and endpoint remain unchanged.

The serving configuration retains 32,768 context/pool positions, one slot,
both prefill controls at 8,192, MTP gate 0.90, PLD `3,3`, prefetch off,
Cache Off, Thinking Off and Vision Off. Experimental NPU/RAW hooks are disabled.
Startup admission remains 30 GiB physical / 131 GiB commit, with an 18 GiB
physical/commit runtime reserve. No threshold was lowered for this update.

The immutable image is
`ghcr.io/peonist-ai/halogen-flash-server@sha256:ef239a9d5665c1c54872cb7761da355ab373df68d1eec0ec970e7f7dbda0ac1f`.
The fresh engine hash is
`bf84053705d1e89c214ff64c79ad1276c5fe353d80a9bb0f38ef3bac6645b97c`.
The WSL adapter was rebuilt after checking the new executable's memory seam,
headers and library identities. Read-only checks of the running engine matched
the new engine, HIP, crypto, C++ runtime and both loaded adapters. SSL was
inspected in the CPU preparation container; it is not a direct engine dependency
and was not force-loaded into the live engine. Existing model files were reused
after their file identities matched the complete-file integrity receipts.

The new frontend defaults, `HALOGEN_RENDER_ONCE=1` and
`HALOGEN_TOKENIZE_SPLIT=16384`, are retained. They optimize request preparation;
this update does not establish an MTP acceptance or token-throughput improvement.
See the [official release source](https://github.com/peonist-ai/halogen-flash-server/blob/2e05e1ffcd5bfb6c7169e6ce6546b4dda7ce34bc/CHANGELOG.md).

Verification includes fresh API/auth/cache/rendering/tokenizer tests, managed
profile forwarding, Windows PowerShell 5.1 launcher tests and the authenticated
17-input/2-output-token smoke request. **That request is not a benchmark.**
The subsequent [complete 8K/16K API observation series](../benchmarks/halogen0202-normal8192-20261111.md)
has an excluded warmup and three measured requests per input. Its phase clock
remains unqualified, with a retained warmup enclosure counterexample; no causal
release or NPU speed gain is established. The
[0.20.1 normal-serving measurements](../benchmarks/halogen0201-normal8192-20261111.md)
remain separately labelled historical results.

Before migration, the old 0.20.1 server stopped itself when its 18 GiB physical
reserve was crossed. Its failure and incomplete baseline-recovery outcome were
retained; its processes and engine were confirmed stopped before the new start.
The new launch passed the unchanged admission check and two fresh zero-GPU-load
observations. A temporary System Copy sample was observed rather than exempted.

Run after stopping an existing managed session through its normal controls:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\Start-Halogen-ServiceNow.ps1 -ConsoleTrace
```

The bare launcher now selects 0.20.2 with paired 8K prefill controls.
`CurrentCachedText32K` remains a separate Flexible-cache option with its own
paired 2K settings. [Machine-readable evidence](halogen0202-update-20261111.json)
records source/build/install/runtime receipts. The wider acceleration goal
remains unachieved; no NPU engine-speed gain is inferred from component timings.
