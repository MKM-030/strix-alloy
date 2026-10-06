# Checked-copy comparison: unresolved System copy activity

The natural16K completion comparison remains unqualified. Its runtime watcher
observed PID 4 / System on the copy engine at 2.628345930526% and rejected the
comparison before the final stock window. Neither the process name nor a close
timestamp establishes whether this activity was foreign work or work induced
by the admitted WSL engine. No observer threshold or process whitelist changed.

The eight completed responses, including two excluded warmups, are identical.
That establishes output agreement for these requests, not an uncontaminated
speed comparison. See the [completion report](halogen-checked-copy-completion-20261006.md).

## Supported attribution path

Microsoft documents a [System Paging Process](https://learn.microsoft.com/en-us/windows-hardware/drivers/display/system-paging-process)
that performs allocation transfers, fills and page-table operations for other
processes. WSL [dxgkrnl forwards GPU work through VMBus to host WDDM](https://devblogs.microsoft.com/directx/directx-heart-linux/).
Thus own-work System activity is plausible; this is an inference, not ownership
evidence for this particular counter sample.

A contemporaneous ETL containing GPU and kernel events can support attribution.
Follow the copy/paging packet through its process, context, submission fence and
allocation references using [GPUView packet details](https://learn.microsoft.com/en-us/windows-hardware/drivers/display/selections-in-the-gpu-hardware-queue).
GPU-PV also uses [host DXGPROCESS objects associated with the VM](https://learn.microsoft.com/en-us/windows-hardware/drivers/display/gpu-paravirtualization);
a VM process label alone need not identify the Linux origin. If the trace lacks
the packet/context/allocation connection, ownership remains unresolved.

Microsoft documents [GPUView capture](https://learn.microsoft.com/en-us/windows-hardware/drivers/display/using-gpuview)
and WPR's built-in [GPU activity profile](https://learn.microsoft.com/en-us/windows-hardware/test/wpt/built-in-recording-profiles).
These are supported observation tools, not a driver modification.

## Current installed capability

The root performed only read-only checks on 6 October 2026:

- `C:\windows\system32\wpr.exe` exists; no WPR recording is running.
- `wpr -profiles` includes `GPU`; its detailed profile includes
  `Microsoft-Windows-DxgKrnl` and process/kernel providers.
- The current process is not elevated and its privilege inventory does not
  include `SeSystemProfilePrivilege`.
- GPUView and WPA were not found on PATH or at the standard checked Windows
  Performance Toolkit locations. This is not an exhaustive disk inventory.
- The displayed default `GPU.Verbose.Memory` profile describes 3,258 plus 3,278
  buffers of 1,024 KiB each, approximately 6.38 GiB. That is a profile budget,
  not measured trace memory consumption or a budget for every capture mode.

Raw receipt:
`server/.local/optimization9h-20261004/checked-copy-capture-feasibility-20261006.json`.
No trace was started, software installed, foreign trace altered or inference
request issued by these checks. A future capture needs an available supported
capture/analysis path and explicit accounting for its overhead and memory.
Trace-instrumented requests would serve attribution, not replace an unobserved
throughput cohort.

## What cannot be recovered from the existing sample

The watcher records Windows UTC after querying counters. Request UTC comes from
WSL `time.time()`; request QPC is retained separately. The watcher retains no GPU
QPC bracket, original PDH sample timestamp or counter integration interval.
Nominal UTC proximity to the warmup/first measured request therefore cannot
attribute the underlying GPU work or justify discarding a sample.

Keep both the previous failed screen and this completion attempt intact. Do not
repeat the unchanged consumer/observer comparison or whitelist System based on
plausibility. The useful next step is specific packet ownership evidence if a
supported capture path becomes available. No GPU, NPU, Prefill, Decode or
acceptance gain is established by this investigation.
