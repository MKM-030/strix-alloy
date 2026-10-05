# Next operating-state diagnostic — 5 October 2026

The new bounded diagnostic is **Windows GPU Engine attribution across the complete
regular PP8192/TG128 cohort**. No supported power or queue-priority knob is selected.
Root's idle GPU Engine read returned no nonzero instances; that observation does
not test competition while inference runs. This note was prepared from retained
source and receipts only; its author made no hardware/provider acquisition,
process or runtime change, benchmark, network request, or model-payload read.

The [CPU/paging control](halogen-cpu-paging-control-20261005.md) retains host CPU
accounting and aggregate ADLX GPU usage, but no per-process GPU Engine activity.
Its 28 measured ADLX samples show a lower clock/power operating range (mean
1642.04 MHz / reported 54.25 W) without establishing why. CPU load, normal process
priority, adapter-memory usage, and an idle zero GPU-counter read cannot exclude
an active Windows GPU client during a request. The restored
[ROCr stock bookend](../benchmarks/halogen0162-rocr-stock8k-20261005.md) remains
41.6484 decode tok/s versus historical 48.4236.

## Root-owned sampler setup

Use the new bounded helper
[`halogen_windows_gpu_counter_probe.ps1`](../../scripts/benchmarks/halogen_windows_gpu_counter_probe.ps1)
in an owned hidden logger process, started before warmup and stopped after all
three measured requests. Keep the existing 18-GiB physical/commit guard and outer
hard timeout. The helper checks its deadline and stop file around each query;
the native query is synchronous. If coverage is incomplete, report it as such.
The root must review the collector source before invocation.

ROOT's eight-second availability run completed seven idle samples with source
SHA256 `e98f647b7c8f6ed0f1dd1607df333849f35ad2f02a8a8a38a3c8c911965ba978`.
The owned logger exited0 and its job closed; physical/commit minima were
27.239/120.007 GiB. Engine health and request counters stayed unchanged, and
no inference was submitted. This qualifies acquisition availability only;
it cannot exclude competing GPU work during a benchmark.

Its built-in getter is
`Get-Counter -Counter '\GPU Engine(*)\Utilization Percentage' -MaxSamples 1`.
Root independently verified the counter on this host: 367 instances, Status 0,
CounterType 542180608, raw durations and the native `Timestamp100NSec` property.
The audit author did not execute that read.

The root-owned invocation is structurally:

```powershell
powershell.exe -NoProfile -NonInteractive -File scripts/benchmarks/halogen_windows_gpu_counter_probe.ps1 `
    -OutFile <new-absolute-jsonl-path> -StopFile <owned-stop-file-path> `
    -MaximumSeconds 1200 -IntervalMilliseconds 1000
```

The caller supplies fresh paths in its existing evidence directory. Output is
CreateNew JSONL; the derived `<OutFile>.ready.json` is atomically published only
after the first sample is flushed and contains a valid counter. Admission waits
for this receipt. The helper retains every instance's Raw/Cooked/Status/type and
timestamps, bracketed host QPC and UTC nanoseconds, plus sanitized first-seen PID
identity. It has fixed ceilings of 4096 instances per tick and 256 MiB output.
The stop file is checked at every tick and during the bounded inter-tick wait.
The terminal record/exit status distinguishes stop, deadline and error. No
setting, engine, command line, or model payload is accessed or changed.

Source-only validation parsed the collector with zero PowerShell AST errors;
its SHA-256 is
`e98f647b7c8f6ed0f1dd1607df333849f35ad2f02a8a8a38a3c8c911965ba978`.
Root reviewed its mutation/credential boundary and completed the availability
test above, followed by all three regular8K windows. The
[completed counter report](halogen-gpu-counter-cohort-20261005.md) records actual
coverage and attribution limits. Nonterminating PDH errors are retained with any returned
batch, so an invalid instance remains visible rather than being silently dropped.

Retain zeros, failed counter statuses, and empty batches. A valid zero and an
unavailable observation are different outcomes. Preserve every instance's PID,
adapter LUID, physical adapter, engine index and engine type encoded in its name;
do not merge adapters or sum all engines into one percentage. Map observed PIDs
to image basename and process creation identity using the existing
`scripts/benchmarks/halogen_cpu_paging_snapshot.py::host_snapshot` getter, with
denied/exited PIDs left unqualified. Do not reuse an old PID/name association.

Counter query QPC bounds are not the utilization-interval boundary.
Use the retained Windows counter timestamps and the root's host UTC/QPC anchors
to align intervals. Keep one sample before and after each benchmark window; for
each unchanged instance, select only valid intervals whose consecutive sample
boundaries are both inside the warmup/measured request's Windows QPC bounds.
Do not extrapolate beyond the anchor span. Reject missing/reset instances,
invalid statuses and unusable timestamps rather than assigning them zero usage.
Retain boundary samples separately. One-second counters do not resolve individual
decode kernels or establish scheduler waiting time.

## Hypotheses and falsifiers

- **Concurrent Windows GPU work:** repeated valid non-WSL PID/engine activity
  overlaps slow requests. This identifies a competing client worth a separately
  authorized single-variable test; overlap alone does not prove the slowdown.
- **No material Windows GPU client activity in this cohort:** complete valid
  measured intervals show only the expected inference/WSL activity and negligible
  other PID activity. This weakens current Windows-client competition for the
  observed cohort. It does not establish the historical machine state, nor rule
  out unreported guest work, scheduler policy, or power distribution.
- **Counter coverage unavailable:** no inference activity is reported despite
  independent ADLX activity, missing identities, invalid statuses, or incomplete
  windows. That is a telemetry limitation, not a falsification of competition.

## DXG power-escape evidence boundary

The retained ROCr source is
`server/.local/rocr-private-source-52061e485927476c8aba16b0e941de14/source/projects/rocr-runtime`.
In `libhsakmt/src/dxg/wddm/device.cpp:90–100`, device creation calls
`SetPowerOptimization(false)` once and normal destruction restores `true`.
The function at line 342 allocates and zeroes the private buffer, then calls
`Wkmi::GetPowerOptPrivDataSize()` and
`Wkmi::FillinPowerOptPrivData(priv_data, restore)`. The original escape has
adapter/device handles, context zero, `Type=D3DKMT_ESCAPE_DRIVERPRIVATE` (0),
`Flags.HardwareAccess=true` (bit 0), and that private buffer/size. It invokes
`D3DKMTEscape` exactly once, stores the signed 32-bit `NTSTATUS`, prints it only
through `pr_debug`, then frees the buffer. It does not act on a failed status.

`dxcore_loader.h:67` declares the Linux call as `NTSTATUS (*)(void *args)`.
The outer `D3DKMT_ESCAPE` fields are handles/type/flags, pointer, private size,
context; the local Windows SDK 10.0.26100.0 definitions are in
`shared/d3dkmthk.h:3409` and `shared/d3dukmdt.h:594`. The private Wkmi encoder,
its header and library are absent from the retained source tree; the WSL CMake
file expects `shared/amdgpu-windows-interop/wkmi`. No payload opcode, byte size,
or effective power-policy value is established by this audit. The retained HSA
source is not an identity proof for the currently bound vendor `librocdxg`.

No existing escape-status observer was found. A plain preload wrapper is not a
qualified observer: the loader resolves the export from an explicit DXCore
handle, and `os_linux.cpp:283–311` verifies that the result belongs to that
library. Debug level 7 is also insufficient as a guarantee because `pr_debug`
is compiled away under `NDEBUG` (`librocdxg.h:199–219`). Its actual original
startup result remains unverified. No interposer, debugger, source patch,
additional escape call, or policy setter is proposed for this turn.

Similarly, `wddm/queue.h:81,107` initializes normal queue priority and maps the
three HSA priority levels. `wddm/queue.cpp:135–147` destroys/recreates a hardware
queue when changing priority; it returns success without doing so for software
queues. This is not evidence for a safe useful live performance adjustment.
The [Windows/ADLX readback](halogen-windows-power-readback-20261005.md) already
reports Best Performance/MaxPerformance and no qualified tuning route. No
retained OEM/SMU/STAPM telemetry helper was found in the checkout.
