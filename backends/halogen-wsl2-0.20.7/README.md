# Halogen 0.20.7 WSL2 backend

The exact image, engine, API, entrypoint and finite memory bridge are pinned. Four GCC 13.3 CPU products are bound to a complete build receipt. The installed one-slot 32K text profile passed a managed ready start, exact preflight-phase checks, authenticated model discovery and an authenticated functional request. No model, provider or engine was executed during source preparation or the CPU build; the later runtime qualification is recorded separately.

The default one-slot service retains 30/124 GiB startup admission; explicit capacity opt-in retains 30/131 GiB. The 18/18 GiB runtime reserves, text capacity policy and bearer authentication remain. The unchanged 59-field cached wire and CacheOff correction are retained. The preferred `qwen38-flash-next-drafter-r2-ht4.hgn` is verified before start. `HALOGEN_CONC_MODE` remains unset so the pinned 0.20.7 entrypoint owns its compatible v2 default. The qualified run selected both paths, registered `65,163,800,576` main bytes and then `1,488,268,672` HT4 bytes, and returned `HALOGEN_0207_FINAL_READY`. Capacity opt-in, two slots and vision remain separately unqualified.

The subsequent [OEM Performance natural 8K/16K benchmark](../../docs/benchmarks/halogen0207-performance-natural-8k16k-20261120.md)
uses the same one-slot 32K text profile, paired 8192 prefill controls, Cache
Off/`no_store`, Thinking and Vision Off, cost-based MTP gate 0.90 and PLD `3,3`. One warmup
is excluded before three measured requests per size. At 8192 actual input tokens
the means are 1210.161667 prefill / 49.209667 decode tok/s, 8.555664 seconds HTTP
QPC and 192/291 = 65.9794% native-head acceptance; at 16384 they are 1216.505 /
49.717 tok/s, 14.611266 seconds and 180/279 = 64.5161%. Outputs and acceptance
match the [earlier same-release cohort](../../docs/benchmarks/halogen0207-natural-8k16k-20261120.md);
the separate OEM transition, restart and measurement window prevent a causal
power-mode attribution. The prefill/decode
figures come from API phase clocks without a RAW observer and therefore remain
unqualified as absolute phase throughput; all eight API phase sums exceeded
their whole-HTTP QPC durations. The matched 0.20.2 rows are a
non-causal reference rather than a measured version effect.

## Persistent prompt cache

In Windows PowerShell 5.1, start the opt-in text profile from the repository root.

```powershell
powershell.exe -NoProfile -File .\scripts\Start-Halogen-ServiceNow.ps1 -Profile CurrentCachedText32K -PersistPromptCache -ConsoleTrace
```

The switch selects Flexible cache and paired 8192 prefill controls for the single-slot 32K v2
configuration. The controller setting is `engine.persist_prompt_cache` and the direct Python
service flag is `--persist-prompt-cache`. Add `-PrintOnly` to preview the launcher configuration.

Halogen stores reusable prompt state under `.strix-alloy-halogen-prompt-cache` in the configured
WSL user's home. The directory must be on writable native ext4, owned by that user and set to
mode `0700`. The backend verifies the live bind and cache path before readiness. The engine
applies a 1 GiB cache budget. Cache state can persist across restarts, so enable it only for
workloads whose prompt state may be retained on disk. Use request-level `cache_control` with
`{"type":"no_store"}` for requests that must skip cache reuse and storage.

[Restart evidence](../../docs/benchmarks/halogen0207-ssd-prompt-cache-20261123.md) records
8,448 of 8,498 tokens restored with byte-identical output. The SSD and RAM latency samples
were single observations. Cold Prefill, Decode and MTP performance need their own comparison.

## N-Gram verification on Windows NTFS

The stock v2 service can reuse a complete N-Gram SHA-256 result across changes to the
projected WSL device number. This applies to the explicit local NTFS/DrvFS bind. The
next required full hash can create `.local/ngram-ntfs-integrity.json` while holding a
native read lease. An existing Linux-only receipt can still start the same WSL file
generation. Building the NTFS receipt requires a full hash under the native lease.

Reuse checks the NTFS file and volume identity, timestamps, size, journal and file USN,
along with the current WSL filename, mount provenance and file identity. The native
handle denies writes and replacement until readiness. Before launching Halogen, the
container checks the current file identity and read-only mount. When the native witness
is unavailable before verification, the existing SHA-256 policy applies. The separate
native-lookup option retains its own source checks.

[N-Gram verification evidence](../../docs/research/halogen0207-wsl-memory-and-ntfs-20261123.md)

Run CPU checks with `python -m unittest discover -s backends/halogen-wsl2-0.20.7/tests`. Set HALOGEN0207_CAPTURE to a passive extracted image directory for the exact ELF/API/entrypoint cases; absent captures are explicit skips. Linux compilation fixtures are separate and may skip on Windows.
