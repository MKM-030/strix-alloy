# Halogen 0.18.16: OEM Performance restoration, 26 October 2026

The independently captured 8,192-input / 128-output MTP cohort averages **1858.90 prefill tok/s, 54.37 decode tok/s, and 66.04% acceptance** (210/318). One warmup is excluded; all three measured requests complete and match the plain Performance run's output and scoped speculation counts.

The actual local firmware interface reported **Quiet (2)** while Windows selected its performance power plan. The local BIOS 3.10 AML and signed OEM event mapping establish Quiet2 / Performance1. Root used the normal elevated OEM WMI method with fresh readback, never a driver, voltage, direct EC or BIOS modification. Performance1 is active after restoration.

## Controlled same-engine comparison

Same engine and profile, exactly frozen non-repetitive prompts, temperature 0 / seed 1, CacheOff/no_store, ThinkingOff, TextOnly, one slot, context 32K, chunk/arena 8192, adaptive MTP gate 0.90, PLD 3,3, prefetchOff. Each window has one excluded warmup and three measured repetitions per case. Values below are complete HTTP response times measured with Windows QPC, including request overhead; they are not token phase rates.

| Workload | Quiet before, s | Performance, s | Quiet after, s | Shorter response vs both controls |
|---|---:|---:|---:|---:|
| historical8k | 9.2532 | 6.8273 | 9.9072 | 26.22-31.09% |
| natural16k | 16.1876 | 12.2024 | 16.9924 | 24.62-28.19% |
| pp8k | 6.4383 | 4.7231 | 6.6303 | 26.64-28.76% |

All 36 requests have exact request/output/token-count parity. All 27 measured requests additionally have exact draft/accepted/scoped-counter parity. The very first excluded 8K warmup drafts 107 instead of 106 (both accept 70). The original overly strict all-ordinal analysis failure remains unchanged. A separate, peer-reviewed offline analysis applies the packet's already specified warmup exclusion to both timings and counters; no measurement was rerun or discarded.

## Independent phase capture

The separate Performance cohort retains four journals, four distinct request IDs and four bound phase endpoints per request. Native API phase durations agree with the capture. No overhead subtraction or time scaling is applied.

| Clock | Prefill tok/s | Decode tok/s | Acceptance |
|---|---:|---:|---:|
| CLOCK_MONOTONIC_RAW endpoints | 1858.8981 | 54.3690 | 66.0377% |
| Native endpoints, same intervals | 1858.8977 | 54.3690 | same counts |

The decode numerator 128 follows Halogen's reporting convention; generated count moves1->128 during that interval, an observed delta 127. Observer bracketing bounds do not describe run-to-run uncertainty. Measured individual RAW prefill values are 1791.99, 1819.78, 1964.92; decode values are 57.47, 56.62, 49.02. Whole-HTTP mean is 6.826476s, versus 6.827305s for the separate plain Performance cohort.

The new native/RAW ratios agree within 0.000031%. The earlier RAW cohort had a different clock ratio; this is not evidence for a general scaling factor or for attributing a clock change to OEM mode. Old results are not rescaled.

The historical comparable MTP128 native pair was 1,866.54 /48.42 tok/s. The new native pair differs by -0.41% /+12.28%. Historical context capacity was 262144, current 32768, and engine/speculation/workspace settings differ. Historical logs and cached integrity receipts identify the same v2 file/layout; a per-run old model content hash was not found.

**The historical standalone PP1 maximum 1,925.16 is separate.** Current Performance PP1 native mean is 1,613.36, but its reported prefill duration exceeds the complete HTTP duration; it cannot establish the true phase-speed gap. A separate saved-input/timing audit confirms identical prompt content and identifies the need for a prefill-only capture. No HTTP-to-phase rescaling is applied. The 16K plain Performance native observations are 1,789.78 prefill /42.77 decode tok/s and 52.68% acceptance, also without separate RAW qualification. The full all-workload/NPU optimization goal remains unachieved.

## Reproduce the software profile

From Windows PowerShell 5.1 in the repository:

```powershell
.\scripts\Start-Halogen-ServiceNow.ps1 -Profile MeasuredText32K -ConsoleTrace
```

Use `-PrintOnly` to inspect the resolved profile without starting an engine or creating a session. This new opt-in profile matches the tested plain configuration; nine targeted checks pass, including exact profile parity and unchanged old presets/defaults. Actual OEM Performance mode is a separate prerequisite; this launcher does not switch it. The public endpoint remains `http://127.0.0.1:8840/v1`, model `halogen-v2`, with the existing ServiceNow token file. Request/response trace is displayed in the console when selected.

The normal uninstrumented 0.18.16 server is left ready and visible. Temporary RAW source changes have been rolled back; NPU helpers remain disabled. Root closed 18 proven ended own launch windows across recovery/finalization; the active server window and unrelated programs remain open. No commit or push was performed. The accompanying JSON pins the raw evidence and final authenticated readiness receipt.
