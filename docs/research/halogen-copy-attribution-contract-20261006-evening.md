# Halogen copy-attribution contract — 2026-10-06 evening

**Status: not attributed. `trace=false`; no qualified speed gain.** This read-only work inspected retained source, installed provider metadata and official primary sources. No live event records, traces, hardware operations, privilege changes or lifecycle actions were performed. Only this Markdown note and its JSON companion were saved at root's request.

The native ETW/TDH route is technically feasible without GPUView/WPA. Installed metadata contains guest process identity, so attribution is potentially stronger than VM-only. Linux origin remains conditional on a complete packet/allocation/device/guest join; no current evidence supplies that complete join.

## Historical evidence

The watcher rejected PID4 copy utilization **2.628345930526%** at `2026-10-06T10:07:29.2052859Z`, instance `pid_4_luid_0x00000000_0x00011884_phys_0_eng_1_engtype_copy`. It records Windows UTC after `Get-Counter`, losing the original PDH timestamp and integration interval. Requests retain WSL UTC and separate QPC values. UTC proximity cannot retrospectively prove packet ownership. The PID4 rejection remains valid; no whitelist or discarded sample is proposed.

The candidate's partial measured deltas, **+1.185202% prefill / +2.168056% decode**, lack the stock-after window and complete hit/skip coverage. They are **not qualified gains**. No adoption or speed gain is claimed.

## Installed metadata receipt and exact retained field inventory

Provider: `Microsoft-Windows-DxgKrnl`; GUID `802ec45a-1e99-4b83-9920-87c98277ba9d`; resource `%SystemRoot%\system32\drivers\dxgkrnl.sys`. Read with `Get-WinEvent -ListProvider 'Microsoft-Windows-DxgKrnl'`; **706 registered event descriptors**. Relevant schemas were `win:LogAlways`.

No separate persisted raw metadata receipt path is known. The original metadata inspection was retained in tool output. This note records exact selected field names; **explicitly marked partial inventories must not be mistaken for full templates**. Unretained field spellings or numeric packet-type enumerants are not reconstructed.

Keywords: Base `0x1`, References `0x4`, Resource `0x40`, LongHaul `0x800`, GPUVA `0x100000`, VirtualGpu `0x800000`, HardwareSchedulingLog `0x4000000`.

| Installed descriptors | Task | Exact retained fields / scope |
|---|---|---|
| 27/v2 Start, 29/v2 DC_Start | Device | `hProcessId`, `pDxgAdapter`, `ClientType`, `hDevice`, `RequestVSync`, `DisableGpuTimeout`, `hThunkHandle`, `DxgProcess`, `HostDeviceHandle`, `VirtualGpu`. |
| 30/v0 Start, 31/v0 Stop, 32/v0 DC_Start | Context | `hDevice`, `NodeOrdinal`, `EngineAffinity`, `Flags`, `hContext`, `ContextHandle`, `ParentDxgContext`. Exact selected attribution fields; DMA/allocation-size fields were also present but were not retained verbatim in this note. |
| 33/v3 Start, 34/v3 Stop, 35/v3 DC_Start | AdapterAllocation | `hProcessId`, `hDevice`, `pDxgAdapter`, `hVidMmGlobalAlloc`, `hDxgGlobalAlloc`, `hDxgSharedResource`. Exact selected attribution fields; additional flags, size, segment, format and geometry fields were present. |
| 36/v2 Start, 38/v2 DC_Start | DeviceAllocation | `hProcessId`, `hDevice`, `pDxgAdapter`, `hVidMmAlloc`, `hVidMmGlobalAlloc`, `hDxgResource`, `hDxgSharedResource`, `hThunkAllocation`, `hThunkResource`, `PrivateRuntimeResourceHandle`, `pVirtualAddress`, `hProcessAllocDetails`, `hOtherPartitionHandle`. |
| 43/v0 Info | ReferenceAllocations | `hContext`, `pDmaBuffer`, `uiNbAllocations`, `Allocations`, `Write`. |
| 50/v0 Info | MemoryTransfer | `hProcessId`, `hAllocationGlobalHandle`, `pDmaBuffer`, `offset`, `size`, `uiType`. |
| 53/v0 Info | PagingOpTransfer | `pDxgAdapter`, `hDmaBuffer`, `ContinueNextBuffer`, `hAllocationGlobalHandle`, `TransferOffset`, `TransferSize`, `Flags`. Exact selected fields; source/destination segment IDs and offsets were also present. |
| 54/v0 Info | PagingOpFill | See scope note. Installed schema also has DMA/global-allocation references; complete verbatim fields were not retained. |
| 76/v0 Start, 77/v0 Stop | AddDmaBuffer | `hContext`, `pDxgAdapter`, `pDmaBuffer`, `DmaSize`, `AllocationListSize`, `PatchLocationListSize`, `hAllocationGlobalHandle`. |
| 110/v1 Info | DpiReportAdapter | `pDxgAdapter`, `AdapterLuid`. Exact selected fields; configuration, bus and vendor fields were also present. |
| 175/v1 Start | DmaPacket | `hContext`, `hQueuePacketContext`, `PacketType`, `uliSubmissionId`, `ulQueueSubmitSequence`, `pDmaBuffer`, `QuantumStatus`. |
| 176/v0 Stop | DmaPacket | `hContext`, `PacketType`, `uliCompletionId`, `ulQueueSubmitSequence`, `bPreempted`. |
| 177/v1 Info | DmaPacket | `hContext`, `PacketType`, `uliCompletionId`, `ulQueueSubmitSequence`, `bPreempted`, `InterruptType`, `QuantumStatus`, `FaultedVirtualAddress`, `PageFaultFlags`, `FaultedProcessHandle`. |
| 178/v1 Start | QueuePacket | `hContext`, `PacketType`, `SubmitSequence`, `DmaBufferSize`, `AllocationListSize`, `PatchLocationListSize`, `bPresent`, `hDmaBuffer`, `pQueuePacket`, `ProgressFenceValue`. |
| 179/v0 Info | QueuePacket | `hContext`, `PacketType`, `SubmitSequence`. |
| 180/v1 Stop | QueuePacket | `hContext`, `PacketType`, `SubmitSequence`, `pQueuePacket`. Exact selected fields; preempted/timed-out fields were also present. |
| 250/v0 Info | NodeMetadata | `pDxgAdapter`, `NodeOrdinal`, `EngineType`, `FriendlyName`. |
| 288/v0 Start | ProcessAllocationDetails | `ProcessId`, `Handle`, `Size`, `hProcessAlloc`. |
| 306/v1 Info | PagingOpVirtualTransfer | See scope note. Installed schema also has DMA/global-allocation references; complete verbatim fields were not retained. |
| 309/v1 | PagingOpUpdatePageTable | `hProcess`. Exact selected field; allocation/DMA references were also present. |
| 310/v0 | PagingOpFlushTlb | `hProcess`. Exact selected field; allocation/DMA references were also present. |
| 422/v0 Start, 423/v0 Stop, 424/v0 DC_Start | HwQueue | `hContext`, `hHwQueue`, `ParentDxgHwQueue`. |
| 450/v0 Info | DmaPacket | `hHwQueue`, `ProgressFenceValue`, `pDmaBuffer`, `ntStatus`, `NumberOfQueuedPendingFlip`. |
| 472/v0 Start, 477/v0 Stop, 492/v0 DC_Start | Process | `DxgProcess`, `ProcessId`, `HostProcessHandle`, `ProcessFlags`, `ProcessIdInVm`, `DxgProcessInVm`, `DxgVirtualMachine`, `ProcessNameInVm`. |
| 474/v0 Start, 493/v0 DC_Start | VirtualMachine | `DxgVirtualMachine`, `VmwpProcess`, `VmmemProcess`, `VmGuid`. |
| 476/v0 Start | VirtualGpu | `DxgVirtualGpu`, `VirtualGpuLuid`, `DxgVirtualMachine`, `DxgAdapter`, `VirtualFunctionIndex`, `VirtualGpuType`. |

For `43/v0`, `Allocations` is a pointer array and `Write` a Boolean array; both are counted by `uiNbAllocations`. Exact event/version schemas must be decoded through TDH rather than guessed offsets. [TDH event metadata](https://learn.microsoft.com/en-us/windows/win32/api/tdh/nf-tdh-tdhgeteventinformation)

## Conditional ownership join

1. DMA `175/176/177` exposes `hContext`, queue-submit sequence, submission/completion identifiers and DMA reference. Queue `178/179/180`, hardware queue `422/424` and `450` expose queue/fence/context links.
2. Context `30/32.hDevice` can join Device `27/29.hDevice`; Device `DxgProcess` can join Process `472/492.DxgProcess`.
3. Process `472/492` exposes `ProcessIdInVm`, `ProcessNameInVm`, `DxgProcessInVm` and `DxgVirtualMachine`; VM `474/493` exposes `VmGuid` and host VM-process identities.
4. For a **System paging DMA**, allocation provenance must replace context-owner inference: `43/50/53/76` expose allocation/DMA references; `33/35/36/38` expose global/local allocation and owning-device candidates.
5. Adapter `110` and node `250` can resolve `AdapterLuid`/`NodeOrdinal`/`EngineType` only with complete captured mappings.

All objects require adapter scope and start/stop/rundown lifetimes. Shared or multi-owner allocations cannot establish exclusive Halogen origin. Metadata alone does not prove that `hAllocationGlobalHandle` equals `hVidMmGlobalAlloc`, the handle namespace of `43.Allocations[]`, equality of differently named DMA fields, or equality of differently named sequence/fence fields. These bridges require supported captured relationships; missing evidence remains unresolved.

Windows uses its own paging contexts and DMA buffers for transfers and page-table operations affecting other processes. Thus PID4 or its context owner is insufficient. [System paging process](https://learn.microsoft.com/en-us/windows-hardware/drivers/display/system-paging-process) GPU-PV also preserves per-guest DXG process objects whose host EPROCESS is vmmem, so host PID alone loses guest identity. [GPU paravirtualization](https://learn.microsoft.com/en-us/windows-hardware/drivers/display/gpu-paravirtualization)

Microsoft's WSL `linux-msft-wsl-6.6.y` source sends `process->pid`, `linux_process=1` and current task name to the host. The PID comes from `current->pid`; TGID, namespace PID and PID namespace are separate. Host guest PID may therefore represent an initial-namespace task ID/TID rather than container PID/TGID. Retained task birth, initial-namespace TID/PID, TGID, namespace mapping and container identity are required. Task name alone is insufficient. This is source-version evidence, not proof that the current running kernel populates these fields for a relevant packet. [VMBus source](https://raw.githubusercontent.com/microsoft/WSL2-Linux-Kernel/linux-msft-wsl-6.6.y/drivers/hv/dxgkrnl/dxgvmbus.c), [process source](https://raw.githubusercontent.com/microsoft/WSL2-Linux-Kernel/linux-msft-wsl-6.6.y/drivers/hv/dxgkrnl/dxgprocess.c)

## Checked-copy source contract

The retained candidate source uses `checked_copy` at line 434 and `process_vm_readv(getpid(), ...)` at line 448, accepts only an exact full-byte copy, permits at most eight queries and bounds bytes by `MODEL_BYTES + 128u`. Checked launch values are submitted from owned temporary arguments. These checks supply no Windows GPU packet/allocation ownership identity and do not explain the System-copy sample.

Source: [halogen0162_mtp_embedding_cache.c](C:/Users/Marcel/.codex/worktrees/npu-ready-embedding/strix-alloy-clean/scripts/benchmarks/halogen0162_mtp_embedding_cache.c:434).

## Prospective bounded file-mode path

This path was **outside the metadata-only subtask's execution scope and was not implemented or executed**. Root must use a reviewed recorder/decoder and apply the user's existing authorization to any future capture. This note does not require renewed server or measurement permission. Actual session/provider access remains a separate technical prerequisite.

- Sequential file mode; request **64 KiB × 64 buffers = 4 MiB pool**, minimum=maximum=64, with `EVENT_TRACE_NO_PER_PROCESSOR_BUFFERING`. Verify actual adjusted sizes/counts.
- Cap sequential ETL at **64 MiB on disk**. File-full, early stop or loss means incomplete evidence. Avoid circular overwrite of lifecycle records. A file cap is not a RAM cap.
- Prospective controller/decoder private-commit ceilings: **16/32 MiB**, with offline decoding after collection. These are implementation ceilings, not measured or enforced here.
- Decode incrementally using `OpenTrace`, `ProcessTrace`, `EventRecordCallback` and TDH. Bound metadata/per-event allocations and use external indexes for object lifetimes. Do not load or map the whole ETL.
- No stacks or general CPU sampling. Base | References | Resource | LongHaul = `0x845` is only a candidate selection. Actual guest/lifecycle/rundown coverage must be confirmed; VirtualGpu, GPUVA or hardware-scheduler events may be needed within budget.
- Reject ownership conclusions on event/buffer loss, missing lifecycle records, unresolved mappings, shared allocations or unresolved guest identity. TDH failures leave events undecoded/unresolved.

These controlled components can be budgeted below **0.1 GiB**, but this is not a hard guarantee on total Windows physical memory: ETW adjustments, native overhead and file-cache usage remain material. Preserve existing reserve gates and observe total memory independently. [ETW properties](https://learn.microsoft.com/en-us/windows/win32/api/evntrace/ns-evntrace-event_trace_properties)

Precise prerequisites: authorized session/provider access without bypassing the retained token limitation; reviewed native collection and decode; supported full lifecycle/rundown on this installed provider; complete zero-loss packet/context/device/allocation/guest records; Linux identity attestation; QPC/UTC calibration and original PDH intervals; and satisfied memory reserves. Session access follows [StartTrace restrictions](https://learn.microsoft.com/en-us/windows/win32/api/evntrace/nf-evntrace-starttracew). GPUView/WPA is optional because [ETW consumption](https://learn.microsoft.com/en-us/windows/win32/etw/consuming-events) and TDH are supported APIs.

With all prerequisites met, evidence could establish per-packet execution intervals, host/VM scope, and Linux-task or exclusive Halogen allocation origin. It cannot recover historical ownership from the retained sample or establish a speed gain by itself.

## Retained local source paths

- `C:\Projects\strix-alloy-clean\docs\research\halogen-checked-copy-completion-20261006.md`
- `C:\Projects\strix-alloy-clean\docs\research\halogen-checked-copy-completion-20261006.json`
- `C:\Projects\strix-alloy-clean\docs\research\halogen-gpu-copy-attribution-20261006.md`
- `C:\Projects\strix-alloy-clean\server\.local\optimization9h-20261004\remaining-frontier-triage-a12936663b244e9486b24a34602040c1.json`
- `C:\Projects\strix-alloy-clean\server\.local\optimization9h-20261004\checked-copy-natural16k-eddb92fa20a94e7882bf6a14e1f13f95\candidate_checked_copy\gpu-watch.ps1`
- `C:\Projects\strix-alloy-clean\server\.local\optimization9h-20261004\checked-copy-natural16k-eddb92fa20a94e7882bf6a14e1f13f95\plan.json`
- `C:\Projects\strix-alloy-clean\server\.local\optimization9h-20261004\prepare_checked_copy_candidate_20261006.py`
- `C:\Users\Marcel\.codex\worktrees\npu-ready-embedding\strix-alloy-clean\scripts\benchmarks\halogen0162_mtp_embedding_cache.c`

## Primary source URLs

- [gpu_pv](https://learn.microsoft.com/en-us/windows-hardware/drivers/display/gpu-paravirtualization): Guest GPU processes have corresponding host DXGPROCESS objects backed by vmmem EPROCESS.
- [system_paging](https://learn.microsoft.com/en-us/windows-hardware/drivers/display/system-paging-process): System paging has its own contexts and DMA buffers and performs operations affecting other processes.
- [gpuview_packet](https://learn.microsoft.com/en-us/windows-hardware/drivers/display/selections-in-the-gpu-hardware-queue): Packet inspection exposes process/context, fence/timing and allocation references; it does not establish all ETW handle-field equalities.
- [tdh_enumerate](https://learn.microsoft.com/en-us/windows/win32/api/tdh/nf-tdh-tdhenumeratemanifestproviderevents): Supported enumeration of installed manifest event descriptors.
- [tdh_manifest](https://learn.microsoft.com/en-us/windows/win32/api/tdh/nf-tdh-tdhgetmanifesteventinformation): Supported manifest metadata retrieval by event descriptor.
- [tdh_event](https://learn.microsoft.com/en-us/windows/win32/api/tdh/nf-tdh-tdhgeteventinformation): Supported decoding metadata for actual EVENT_RECORD values.
- [etw_consume](https://learn.microsoft.com/en-us/windows/win32/etw/consuming-events): OpenTrace/ProcessTrace and EventRecordCallback consumption without GPUView/WPA.
- [etw_properties](https://learn.microsoft.com/en-us/windows/win32/api/evntrace/ns-evntrace-event_trace_properties): Buffer units, OS adjustments, pool limits, file cap and lost-event/buffer counters.
- [etw_modes](https://learn.microsoft.com/en-us/windows/win32/etw/logging-mode-constants): Sequential versus circular file logging and NO_PER_PROCESSOR_BUFFERING.
- [wpr_collector](https://learn.microsoft.com/en-us/windows-hardware/test/wpt/eventcollector): Custom collector BufferSize, Buffers and MaximumFileSize settings.
- [start_trace](https://learn.microsoft.com/en-us/windows/win32/api/evntrace/nf-evntrace-starttracew): Session access restrictions; no privilege workaround proposed.
- [createprocess_ddi](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/d3dkmddi/ns-d3dkmddi-_dxgkarg_createprocess): VirtualMachineProcess process-name semantics; process name may be null.
- [wsl_vmbus](https://raw.githubusercontent.com/microsoft/WSL2-Linux-Kernel/linux-msft-wsl-6.6.y/drivers/hv/dxgkrnl/dxgvmbus.c): Creates guest process with process->pid, linux_process=1 and current task name.
- [wsl_process](https://raw.githubusercontent.com/microsoft/WSL2-Linux-Kernel/linux-msft-wsl-6.6.y/drivers/hv/dxgkrnl/dxgprocess.c): pid=current->pid; tgid, namespace PID and PID namespace retained separately.
- [wsl_vmbus_header](https://raw.githubusercontent.com/microsoft/WSL2-Linux-Kernel/linux-msft-wsl-6.6.y/drivers/hv/dxgkrnl/dxgvmbus.h): Create-process message contains process_id, process_name and Linux-process flag.

No native-controller audit was repeated or inspected. No trace, privilege workaround, installation, engine/GPU/NPU operation, service restart or shutdown occurred. Root retains the running HistoricalStock instance and handles review, commit and state.
