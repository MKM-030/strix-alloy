# Windows power and ADLX system readback — 5 October 2026

The retained readbacks found Windows **Best Performance** configured on AC and
**MaxPerformance** effective. The ADLX discovery exposed no confirmed usable
SmartShift or system power-distribution route. These observations do not explain
the current throughput gap: no power mode, tuning setting, driver or firmware
was changed, and there was no matched performance intervention.

This report combines existing receipts executed by the root agent. Its author
only read the saved files and source, verified their hashes, and wrote this
report; no additional provider or hardware acquisition was performed.

## Windows readback

The Windows receipt was recorded at `2026-10-04T22:38:37.597483+00:00`.

| Readback | Retained result |
|---|---|
| AC line status | `1` (online) |
| Energy saver flag | `0` |
| Configured AC mode | Best Performance; GUID `ded574b5-45a0-4f42-8737-46345c09c238`; API status `0` |
| Configured DC mode | All-zero GUID; API status `0`; not an AC-mode observation |
| Effective mode | `4` (MaxPerformance), callback at `2026-10-04T22:38:37.598276+00:00` |
| Effective notification lifecycle | Registration `0`, initial callback received, unregistration `0` |
| Reported write counts | Policy `0`; driver or firmware `0` |

The reader calls the documented Windows power-mode getters, registers for an
initial effective-mode notification using version `2`, and unregisters the
notification. It contains no power-policy setter. The receipt also retains
battery flag `128` and battery percentage `255`; these are raw status fields,
not battery-load measurements.

## ADLX readback

The separate ADLX probe ran from `2026-10-04T22:51:18.3437935Z` to
`2026-10-04T22:51:18.6389041Z`, exited `0`, and terminated the provider with
result `0`. It reported ADLX `1.5`, with runtime and SDK full-version values
both `281496451547260`.

| Query | API result | Returned value | Interpretation |
|---|---:|---|---|
| `IsSupportedCPUUsage` | `0` | `true` | CPU usage readback available |
| `IsSupportedSmartShift` | `0` | `false` | Explicitly unsupported by this readback |
| `IsSupportedPowerDistribution` | `0` | `false` | Explicitly unsupported by this readback |
| `SmartShiftMax.IsSupported` | `3` | `null` | Query failed; capability remains unqualified |
| `CPUUsage` | `0` | `14.8640705984%` | One standalone system sample |

`GetPowerTuningServices` and `GetSmartShiftMax` both returned `0`, but that
does not establish usable support: the subsequent support query failed.
In the pinned `ADLXDefines.h`, result `3` is `ADLX_FAIL`, an unspecified
failure; `ADLX_NOT_SUPPORTED` is `12`. The failed query is therefore not
reported as a successful `false` response. No bias mode or bias value was
queried, and no SmartShift or power-distribution values were acquired, because
their corresponding support gates did not pass.

The CPU sample spans host epoch milliseconds `1791154278548` to
`1791154278577`. It is not aligned to an inference request and has no process
attribution. It cannot establish CPU idleness during inference, package-power
competition, a package watt limit, or a cause of the throughput decline.

The reviewed probe only obtains support information and gated current values.
It calls no setter and starts no metric tracking; its smart pointers leave
scope before provider termination. Unsupported or failed capability checks are
retained as discovery results, so exit `0` does not mean every feature is
supported. The probe uses the existing GPUOpen ADLX SDK pinned to commit
`d9f04a9bba022d6cf6333f005dd540b4ad19fb63`.

## Evidence identity and limits

The ADLX window is
`server/.local/optimization9h-20261004/adlx-system-power-c9c48b739d884064bf3cb014f1a11b22`;
the Windows receipt is
`server/.local/optimization9h-20261004/windows-power-mode-3b9e76481cd141dbbc4f9242df06784d.json`.
The raw local evidence is retained in that ignored workspace. All hashes below
are SHA-256 of the file bytes and were verified offline.

| Artifact | SHA-256 |
|---|---|
| ADLX `receipt.json` | `ff033f06775bcbf6558779fb08fefb9ecbcab82da8c414a37bdddbb22231ac69` |
| ADLX `stdout.jsonl` | `5a15d6ea171a621506dce36f99560d5c4ce7d8a51b3224b7661c2a9e2708ba5c` |
| ADLX `stderr.txt` (empty) | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| Windows power-mode receipt | `0e39707f18f3bac58efedea49b2ae98d8a2e0485655d0d33a0ba8e47d763a125` |
| `read-windows-power-mode.py` | `2163685d6d7553acf95489764e7da29c3095e9f6bb9ee8aa8b9bfc4238f7b1cb` |
| `halogen_adlx_power_probe.cpp` | `fea6f82f55a6dc544239edfc899b2bc3c6ea2926a6f07be9fe0c34bc68009efa` |
| Build-only `halogen_adlx_power_probe.ps1` | `91405fc1466411b05127592d065c88f161ecbbaff7f486afbca9b5a865476984` |
| Executed probe binary | `abc531e9e5ebf13fc83c0e19c8ea6a63a84c6452097ef04e6cba0fe603dbad67` |

These later standalone observations establish the reported state at their own
timestamps. They are not request-aligned telemetry for the earlier standard
control, and they do not establish that a Windows mode change would recover
the historical GPU clocks or throughput. No measured prefill or decode delta
is associated with this readback. The operating-state investigation and overall
optimization goal remain active.

[Machine-readable readbacks and evidence identities](halogen-windows-power-readback-20261005.json),
[performance-gap audit](halogen-performance-gap-audit-20261005.md),
[conditioned control](halogen-conditioned-control-20261005.md),
and [NPU placement decision](halogen-useful-npu-decision-20261005.md).
