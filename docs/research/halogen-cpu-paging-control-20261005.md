# Normal frozen control: CPU, paging and GPU evidence — 5 October 2026

The unchanged normal Halogen control passed at **1253.224684 prefill / 42.418748
decode tok/s**, with **60% acceptance (207/345)**. It is another operating-state
measurement, not an optimization or NPU result. The measured requests show no
new engine major faults or attributable storage reads, and no guest reclaim or
swap activity. Separately, two engine threads consume nearly two CPU cores while
the root-reported completed-request count stays unchanged.

The control uses 8192 actual input tokens, 128 output tokens, capacity 262144,
one warmup and three measured requests. Every output retains the frozen hash;
each request accepts 69 of 115 proposals. GPU prefill/native MTP remain active,
the NPU is not integrated, and the colleague server stays open. The measurement
finished at `2026-10-04T23:17:24Z`.

| Request | Phase | Prefill tok/s | Decode tok/s | Engine CPU seconds | Engine average cores |
|---:|---|---:|---:|---:|---:|
| 0 | Warmup | 1399.536650 | 41.562365 | 27.99 | 2.9805 |
| 1 | Measured | 1329.621733 | 42.287409 | 28.78 | 2.9776 |
| 2 | Measured | 1263.781907 | 42.389412 | 29.59 | 2.9861 |
| 3 | Measured | 1166.270412 | 42.579425 | 31.44 | 2.9791 |

Against historical Stock A (1866.537225 / 48.423621 tok/s), the measured mean is
lower by **613.312541 tok/s (32.8583%) prefill** and **6.004872 tok/s (12.4007%)
decode**. The historical comparison is retained in the
[performance-gap audit](halogen-performance-gap-audit-20261005.md).

## CPU and paging bookends

All four host and guest snapshots/deltas are valid at the system/engine level.
Guest PID87 keeps the same boot, PID namespace and start-tick identity. The
counter intervals include telemetry acquisition/transport margins outside engine
timers; they are not separate prefill and decode measurements.

Across the three measured bookends, engine CPU is 89.81 seconds over 30.128113
seconds, or 2.98094 average logical cores. **Each of all four requests has 600
engine minor faults, zero engine major faults, zero `read_bytes`, and zero
`rchar`**. Engine RSS stays 1.40098 GiB, its six-thread count is unchanged,
and its VmSwap is zero. Linux `read_bytes` means attributable storage reads;
`rchar` counts read characters including cache hits. Neither identifies the
lookup file or GPU memory traffic.

Guest cache is 2.52903–2.52905 GiB and MemAvailable 52.95086–52.98150 GiB at
the bookends. Swap used, swap-in/out, `pgpgin`, scan/steal, allocstall,
workingset refault, compaction and OOM deltas are zero. There are six *system*
major faults per bookend (18 in the measured cohort), while engine major faults
remain zero. The observations provide no evidence of recurrent engine storage
reads or guest paging pressure during these requests; they do not refute startup
cache warnings or establish file-specific residency.

Windows system cache is 19.73502–19.78404 GiB at the bookends. The owned control
guardian's root-confirmed result minima are 27.43206 GiB available physical
memory and 119.91372 GiB commit headroom; the separate ADLX guardian minima are
retained separately in JSON. Measured host system busy time is 14.10–14.91%.
Controller PID28488 uses 0–0.01334 cores and backend PID2504 0.00471–0.00593
cores; both retained priority class `32`. vmmem PID15260 is **unqualified**:
`OpenProcess` returns Win32 error5 (access denied), not a zero CPU result or
evidence of PID reuse.

Only 137 of the fixed 212 supplied PIDs have qualified process deltas in each
window; 75 remain unqualified. The largest readable background processes over
the measured cohort are:

| PID | Image basename | CPU seconds | Average logical cores |
|---:|---|---:|---:|
| 26548 | dllhost.exe | 4.03125 | 0.13344 |
| 1940 | ChatGPT.exe | 1.25000 | 0.04139 |
| 17104 | pythonw.exe | 1.04688 | 0.03465 |
| 16216 | ChatGPT.exe | 0.67188 | 0.02224 |
| 9488 | OsdShowV2.4.exe | 0.53125 | 0.01759 |

These are readable-process observations, not complete attribution of host load.
Windows process faults combine soft/hard faults and its IO counters are not
physical-disk counters. Host and guest CPU accounting must not be added together.

## Request-aligned ADLX evidence

All 90 sensor queries succeed, and 440 host epoch/QPC anchors cover every request
and sensor query. Host epoch is interpolated between adjacent QPC anchors without
extrapolation. Only complete successful query intervals within each request's
calibrated before/after QPC window are selected: **9 warmup, then 9/9/10 measured
samples**, yielding 28 measured samples. Guest UTC and ADLX driver timestamps are
not used for alignment.

| Measured sensor | Minimum | Mean | Maximum |
|---|---:|---:|---:|
| GPU clock, MHz | 976 | 1642.04 | 2134 |
| Reported GPU power, W | 39 | 54.25 | 59 |
| GPU usage, % | 19 | 82.14 | 100 |
| GPU temperature, °C | 46 | 53.82 | 57 |

VRAM clock is 1000 MHz throughout; NPU activity/frequency are zero. This remains
a lower clock/power operating range than the separate historical cohort; no
thermal or package-power-limit cause is established.

## Distinct idle-thread observation and disposition

The separate retained idle pair spans 167.634579 seconds on the same engine
PID/start identity. TID 90 consumes 167.45 CPU seconds (0.998899 cores) and TID 91
167.46 CPU seconds (0.998959 cores); both retain their start ticks and appear
running with wchan `0`. Root reports completed_count `16` unchanged across this pair;
the thread receipt itself contains no request counters. This is a concrete CPU
overhead lead, separate from the request cohort, with no demonstrated throughput
or package-power effect.

The control and logger exited `0`; root confirms the control job closed and its
memory monitor stopped, and the ADLX receipt confirms its owned job closed with
no cleanup pending. No settings or engine change was made for this control.
The optimization goal remains active.

The [machine-readable report](halogen-cpu-paging-control-20261005.json) retains
per-request counter/gauge data, PID attribution limits, exact sensor membership,
and SHA-256 identities for all 21 source receipts. Raw evidence stays in the
ignored local control and ADLX windows named there; prompts, response text and
credentials are not reproduced.
