# Halogen 0.18.16: bounded independent compute observation

The standalone diagnostic completed once, with valid output and successful cleanup. It did **not** establish a sustained high-utilization clock range or resolve the cause of Halogen's performance gap. No inference requests, settings changes, or repeat trial were made. The [JSON companion](halogen01816-operating-range-20261026.json) records the independent saved-file checks and 15 evidence hashes.

The fixed gfx1151 kernel uses eight FP32 FMA chains, 32,768 iterations and grid 320/block 256. After one excluded warmup, 432 measured launches occupied **3.003339755 seconds** of guest MONOTONIC_RAW time. Their HIP event durations summed to **2.330643176 seconds**, with per-launch minimum/median/maximum **3.481874 / 5.516464 / 10.953123 ms**. The sum of host launch brackets was 2.487472109 seconds. These are distinct intervals; their ratios are not measured hardware utilization or GPU frequency. No token rates are derived.

The loader reports validation of all 81,920 output floats: finite, positive, below 20, nonconstant and exactly 1,024-periodic. Its 327,680-byte output allocation was freed; final synchronization, both event destructions and module unload returned zero. The saved output hash is retained, but raw output values were not saved for independent numerical replay. Loader, supervisor and Windows process elapsed times were respectively 3.123369, 3.306279 and 3.701276 seconds; the owned child exited normally with status zero.

The sensor ran for 70 reads, requesting 100 ms spacing. **34 valid reads were fully contained in the broader Windows process window**, using each read's requested/completed Windows epoch timestamps. Their actual spacing was 108–113 ms:

| ADLX metric | Minimum | Median | Maximum |
|---|---:|---:|---:|
| GPU usage (%) | 1 | 37 | 73 |
| GPU clock (MHz) | 660 | 1,355 | 1,401 |
| Reported GPU power (W) | 44 | 68 | 73 |
| GPU temperature (°C) | 52 | 58 | 61 |

**Zero reads met usage ≥90%; a high-utilization clock statistic is unavailable.** The process-window metric states were usage/clock/power 1%/660 MHz/44 W, 1%/680 MHz/44 W, 37%/1,355 MHz/73 W, 64%/1,401 MHz/68 W and 73%/1,372 MHz/61 W. Several states persisted across 9–10 polls despite advancing ADLX timestamps. Polling every roughly 100 ms therefore does not prove independently refreshed driver measurements at that cadence.

These statistics are not an exact measured-kernel-phase range. Guest UTC reports 02:22:45–48 while the Windows process timestamps report 02:23:56–02:24:00; no cross-clock mapping was established. The process window also contains startup, warmup, readback and cleanup. ADLX's GPU power metric does not establish package power or a configured limit; total-board-power reporting was unsupported. Neither an always-low global clock cap nor a firmware/power cause is demonstrated or eliminated by this result.

The 155 saved memory frames cover the process window, with a maximum observed polling gap of 103 ms. Request-entry available memory/commit headroom were 23.025/114.270 GiB; observed minima were 22.954/114.154 GiB, above the 22 GiB entry and 18 GiB sampled guard requirements. Before/after receipts preserve controller/backend identities and both run IDs, with completed requests unchanged at 48, cancelled at zero, and native/gateway active and queued counts zero. The normal server was left online in the saved final receipt at **2026-10-26 02:24:03.758533 UTC**; this is a historical receipt, not a current readiness claim.

Primary saved evidence: [probe and cleanup](../../server/.local/halogen-update-20261025/primary01816/live-independent-compute/probe.ndjson), [sensor series](../../server/.local/halogen-update-20261025/primary01816/live-independent-compute/samples.ndjson), [owned process state](../../server/.local/halogen-update-20261025/primary01816/live-independent-compute/state.json), [memory series](../../server/.local/halogen-update-20261025/primary01816/live-independent-compute/memory-series.json), and [final server receipt](../../server/.local/halogen-update-20261025/primary01816/live-independent-compute/ready-left-online.json).
