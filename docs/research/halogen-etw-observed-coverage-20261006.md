# Halogen ETW observed idle coverage — 2026-10-06

**8,454 Dxg events materialized across 95 ID/version pairs; all nine provenance edges remain unresolved.** This inspection streamed only the completed own JSONL, one record at a time, retaining counters and schema signatures. No new capture, live API, hardware, inference, lifecycle action or implementation edit occurred.

Root's capture was an idle five-second window with zero final reported recorder losses, no CAPTURE_STATE/rundown and no Halogen request. Root retains the raw receipt combination in [the bounded result](C:/Projects/strix-alloy-clean/docs/research/halogen-etw-bounded-result-20261006.json). Zero loss applies to enabled/emitted records during this session; it does not establish complete ownership or lifecycle coverage.

## Source and materialization

Source: [decoded.jsonl](C:/Projects/strix-alloy-clean/server/.local/optimization9h-20261004/etw-native-build-3bc6e3f283a541b9afd2c4a47d7f7bdc/decoded.jsonl). Header: [line 1](C:/Projects/strix-alloy-clean/server/.local/optimization9h-20261004/etw-native-build-3bc6e3f283a541b9afd2c4a47d7f7bdc/decoded.jsonl:1); decoder summary: [line 8456](C:/Projects/strix-alloy-clean/server/.local/optimization9h-20261004/etw-native-build-3bc6e3f283a541b9afd2c4a47d7f7bdc/decoded.jsonl:8456). The file is 20,401,644 bytes and 8,456 JSONL rows: one header, 8,454 event rows and one summary. Maximum input line: 10,882 bytes. The header records a 1,179,648-byte ETL, QPC clock with frequency 10,000,000, 18 buffers and header loss statistics of zero. Event QPC range: `1956662125660` through `1956712703323`.

Every event has `status=materialized`; decoder summary reports zero unresolved events/properties, successful ProcessTrace/CloseTrace and no abort. Its `zero_loss_evidence=not-supplied` remains accurate: the separate recorder receipt supplies the loss observation. Decode success supplies neither ownership nor rundown completeness.

## Requested coverage

| Family | Observed count | First record |
|---|---:|---|
| Adapter allocation 33/v3, 34/v3 | 5, 10 | [line 197](C:/Projects/strix-alloy-clean/server/.local/optimization9h-20261004/etw-native-build-3bc6e3f283a541b9afd2c4a47d7f7bdc/decoded.jsonl:197), [line 651](C:/Projects/strix-alloy-clean/server/.local/optimization9h-20261004/etw-native-build-3bc6e3f283a541b9afd2c4a47d7f7bdc/decoded.jsonl:651) |
| Device allocation 36/v2, 37/v2 | 10, 15 | [line 199](C:/Projects/strix-alloy-clean/server/.local/optimization9h-20261004/etw-native-build-3bc6e3f283a541b9afd2c4a47d7f7bdc/decoded.jsonl:199), [line 648](C:/Projects/strix-alloy-clean/server/.local/optimization9h-20261004/etw-native-build-3bc6e3f283a541b9afd2c4a47d7f7bdc/decoded.jsonl:648) |
| Reference allocations 43/v0 | 15 | [line 387](C:/Projects/strix-alloy-clean/server/.local/optimization9h-20261004/etw-native-build-3bc6e3f283a541b9afd2c4a47d7f7bdc/decoded.jsonl:387) |
| Memory transfer 50/v0 | 15 | [line 313](C:/Projects/strix-alloy-clean/server/.local/optimization9h-20261004/etw-native-build-3bc6e3f283a541b9afd2c4a47d7f7bdc/decoded.jsonl:313) |
| DMA 175/v1, 176/v0, 177/v1 | 35, 35, 35 | [line 225](C:/Projects/strix-alloy-clean/server/.local/optimization9h-20261004/etw-native-build-3bc6e3f283a541b9afd2c4a47d7f7bdc/decoded.jsonl:225), [line 230](C:/Projects/strix-alloy-clean/server/.local/optimization9h-20261004/etw-native-build-3bc6e3f283a541b9afd2c4a47d7f7bdc/decoded.jsonl:230), [line 229](C:/Projects/strix-alloy-clean/server/.local/optimization9h-20261004/etw-native-build-3bc6e3f283a541b9afd2c4a47d7f7bdc/decoded.jsonl:229) |
| Queue 178/v1, 179/v0, 180/v1 | 124, 187, 423 | [line 16](C:/Projects/strix-alloy-clean/server/.local/optimization9h-20261004/etw-native-build-3bc6e3f283a541b9afd2c4a47d7f7bdc/decoded.jsonl:16), [line 34](C:/Projects/strix-alloy-clean/server/.local/optimization9h-20261004/etw-native-build-3bc6e3f283a541b9afd2c4a47d7f7bdc/decoded.jsonl:34), [line 58](C:/Projects/strix-alloy-clean/server/.local/optimization9h-20261004/etw-native-build-3bc6e3f283a541b9afd2c4a47d7f7bdc/decoded.jsonl:58) |
| Guest process 472/492; VM 474/493 | 0 | Absent from all 8,454 events |
| Allocation rundown 35/38; transfer 53; AddDmaBuffer 76/77 | 0 | Absent |
| Adapter/node 110/250 | 0 | Absent |
| Device/context 27/29, 30/31/32; detail 288; HwQueue 422/423/424; VirtualGpu 476; Process stop 477 | 0 | Absent |
| Hardware packet 450/v0 | 52 | [line 20](C:/Projects/strix-alloy-clean/server/.local/optimization9h-20261004/etw-native-build-3bc6e3f283a541b9afd2c4a47d7f7bdc/decoded.jsonl:20) |
| Paging page-table 309/v1, TLB 310/v0 | 133, 117 | [line 203](C:/Projects/strix-alloy-clean/server/.local/optimization9h-20261004/etw-native-build-3bc6e3f283a541b9afd2c4a47d7f7bdc/decoded.jsonl:203), [line 204](C:/Projects/strix-alloy-clean/server/.local/optimization9h-20261004/etw-native-build-3bc6e3f283a541b9afd2c4a47d7f7bdc/decoded.jsonl:204) |

Absence describes this enabled idle window. It does not show that the installed provider cannot emit a descriptor. Allocation start/stop counts differ across the window; this alone proves neither loss nor complete lifetime pairing.

## Exact observed schemas

Below, `name(InType/OutType:length)` records numeric TDH schema types and lengths. All fields have `flags=0,count=1` unless shown. `count=@2` denotes the schema count-property index 2, `uiNbAllocations`. Map names are recorded metadata; map contents and enumerant labels were not materialized. The JSON companion preserves the full ordered tuples, including null indexes and each schema's observed count/first/last line. Each listed requested descriptor has one observed schema variant.

| Exact descriptor and reference | Ordered top-level field schema |
|---|---|
| 33/v3 op1, n=5 ([line 197](C:/Projects/strix-alloy-clean/server/.local/optimization9h-20261004/etw-native-build-3bc6e3f283a541b9afd2c4a47d7f7bdc/decoded.jsonl:197)); 34/v3 op2, n=10 ([line 651](C:/Projects/strix-alloy-clean/server/.local/optimization9h-20261004/etw-native-build-3bc6e3f283a541b9afd2c4a47d7f7bdc/decoded.jsonl:651)) | `hProcessId(16/19:8)`, `hDevice(16/19:8)`, `pDxgAdapter(16/19:8)`, `Flags(8/8:4;map=AllocationFlags)`, `allocSize(10/10:8)`, `ulAlignment(8/8:4)`, `dwReadSegment(8/8:4)`, `dwWriteSegment(8/8:4)`, `PreferredSegment(8/8:4)`, `HintedBank(8/8:4)`, `dwEvictionSegment(8/8:4)`, `Priority(8/18:4)`, `hVidMmGlobalAlloc(16/19:8)`, `hDxgGlobalAlloc(16/19:8)`, `hDxgSharedResource(16/19:8)`, `UsageVersion(8/8:4)`, `UsageFlags(8/8:4;map=UsageFlags)`, `Format(8/8:4;map=D3DFormat)`, `SwizzledFormat(8/8:4)`, `ByteOffset(8/8:4)`, `Width(8/8:4)`, `Height(8/8:4)`, `Pitch(8/8:4)`, `Depth(8/8:4)`, `SlicePitch(8/8:4)`, `BackingStoreWasPinned(13/13:4)`, `pSectionObject(16/19:8)`, `PhysicalAdapterIndex(6/6:2)`, `PageTableOrDirectory(13/13:4)` |
| 36/v2 op1, n=10 ([line 199](C:/Projects/strix-alloy-clean/server/.local/optimization9h-20261004/etw-native-build-3bc6e3f283a541b9afd2c4a47d7f7bdc/decoded.jsonl:199)); 37/v2 op2, n=15 ([line 648](C:/Projects/strix-alloy-clean/server/.local/optimization9h-20261004/etw-native-build-3bc6e3f283a541b9afd2c4a47d7f7bdc/decoded.jsonl:648)) | `hProcessId(16/19:8)`, `hDevice(16/19:8)`, `pDxgAdapter(16/19:8)`, `hVidMmAlloc(16/19:8)`, `hVidMmGlobalAlloc(16/19:8)`, `hDxgResource(16/19:8)`, `hDxgSharedResource(16/19:8)`, `hThunkAllocation(16/19:8)`, `hThunkResource(16/19:8)`, `PrivateRuntimeResourceHandle(16/19:8)`, `pVirtualAddress(16/19:8)`, `hProcessAllocDetails(16/19:8)`, `hOtherPartitionHandle(8/18:4)` |
| 43/v0 op0, n=15 ([line 387](C:/Projects/strix-alloy-clean/server/.local/optimization9h-20261004/etw-native-build-3bc6e3f283a541b9afd2c4a47d7f7bdc/decoded.jsonl:387)) | `hContext(16/19:8)`, `pDmaBuffer(16/19:8)`, `uiNbAllocations(8/8:4)`, `Allocations(16/19:8;flags=4;count=@2)`, `Write(13/13:4;flags=4;count=@2)` |
| 50/v0 op0, n=15 ([line 313](C:/Projects/strix-alloy-clean/server/.local/optimization9h-20261004/etw-native-build-3bc6e3f283a541b9afd2c4a47d7f7bdc/decoded.jsonl:313)) | `hProcessId(16/19:8)`, `hAllocationGlobalHandle(16/19:8)`, `pDmaBuffer(16/19:8)`, `offset(10/10:8)`, `size(10/10:8)`, `uiType(8/8:4;map=MemoryTransferType)` |
| 175/v1 op1, n=35 ([line 225](C:/Projects/strix-alloy-clean/server/.local/optimization9h-20261004/etw-native-build-3bc6e3f283a541b9afd2c4a47d7f7bdc/decoded.jsonl:225)) | `hContext(16/19:8)`, `hQueuePacketContext(16/19:8)`, `PacketType(8/8:4;map=DmaPacketType)`, `uliSubmissionId(10/10:8)`, `ulQueueSubmitSequence(8/8:4)`, `pDmaBuffer(16/19:8)`, `QuantumStatus(8/8:4;map=QuantumStatus)` |
| 176/v0 op2, n=35 ([line 230](C:/Projects/strix-alloy-clean/server/.local/optimization9h-20261004/etw-native-build-3bc6e3f283a541b9afd2c4a47d7f7bdc/decoded.jsonl:230)) | `hContext(16/19:8)`, `PacketType(8/8:4;map=DmaPacketType)`, `uliCompletionId(10/10:8)`, `ulQueueSubmitSequence(8/8:4)`, `bPreempted(13/13:4)` |
| 177/v1 op0, n=35 ([line 229](C:/Projects/strix-alloy-clean/server/.local/optimization9h-20261004/etw-native-build-3bc6e3f283a541b9afd2c4a47d7f7bdc/decoded.jsonl:229)) | `hContext(16/19:8)`, `PacketType(8/8:4;map=DmaPacketType)`, `uliCompletionId(10/10:8)`, `ulQueueSubmitSequence(8/8:4)`, `InterruptType(8/8:4;map=DmaInterruptType)`, `QuantumStatus(8/8:4;map=QuantumStatus)`, `FaultedVirtualAddress(10/19:8)`, `PageFaultFlags(8/8:4;map=DmaPageFaultFlags)`, `FaultedProcessHandle(16/19:8)` |
| 178/v1 op1, n=124 ([line 16](C:/Projects/strix-alloy-clean/server/.local/optimization9h-20261004/etw-native-build-3bc6e3f283a541b9afd2c4a47d7f7bdc/decoded.jsonl:16)) | `hContext(16/19:8)`, `PacketType(8/8:4;map=QueuePacketType)`, `SubmitSequence(8/8:4)`, `DmaBufferSize(10/10:8)`, `AllocationListSize(8/8:4)`, `PatchLocationListSize(8/8:4)`, `bPresent(13/13:4)`, `hDmaBuffer(16/19:8)`, `pQueuePacket(16/19:8)`, `ProgressFenceValue(10/10:8)` |
| 179/v0 op0, n=187 ([line 34](C:/Projects/strix-alloy-clean/server/.local/optimization9h-20261004/etw-native-build-3bc6e3f283a541b9afd2c4a47d7f7bdc/decoded.jsonl:34)) | `hContext(16/19:8)`, `PacketType(8/8:4;map=QueuePacketType)`, `SubmitSequence(8/8:4)` |
| 180/v1 op2, n=423 ([line 58](C:/Projects/strix-alloy-clean/server/.local/optimization9h-20261004/etw-native-build-3bc6e3f283a541b9afd2c4a47d7f7bdc/decoded.jsonl:58)) | `hContext(16/19:8)`, `PacketType(8/8:4;map=QueuePacketType)`, `SubmitSequence(8/8:4)`, `bPreempted(13/13:4)`, `bTimeouted(13/13:4)`, `pQueuePacket(16/19:8)` |
| 450/v0 op0, n=52 ([line 20](C:/Projects/strix-alloy-clean/server/.local/optimization9h-20261004/etw-native-build-3bc6e3f283a541b9afd2c4a47d7f7bdc/decoded.jsonl:20)) | `hHwQueue(16/19:8)`, `ProgressFenceValue(10/10:8)`, `pDmaBuffer(16/19:8)`, `ntStatus(8/8:4)`, `NumberOfQueuedPendingFlip(8/8:4)` |

Actual `37/v2` supplies the device-allocation stop schema that was not retained previously. Actual `177/v1` has nine fields and **no `bPreempted`**; `176/v0` includes that field. These actual receipts take precedence over the earlier selected inventory.

The first observed `309/v1` and `310/v0` records also fill partial inventories. Their exact first-record tuples appear below and in JSON; variants across all records of these optional families were not separately inventoried. Every field below has `flags=0,count=1`, no count/length property index and no map name.

| First observed paging descriptor | Ordered field schema |
|---|---|
| 309/v1 ([line 203](C:/Projects/strix-alloy-clean/server/.local/optimization9h-20261004/etw-native-build-3bc6e3f283a541b9afd2c4a47d7f7bdc/decoded.jsonl:203)) | `pDxgAdapter(16/19:8)`, `hDmaBuffer(16/19:8)`, `ContinueNextBuffer(13/13:4)`, `hAllocationGlobalHandle(16/19:8)`, `PageTableLevel(8/8:4)`, `PageTableAddress(10/19:8)`, `SegmentId(8/8:4)`, `NumPageTableUpdateEntries(8/8:4)`, `PageTableEntries(16/19:8)`, `PageTableEntries64KB(16/19:8)`, `StartIndex(8/8:4)`, `Flags(8/8:4)`, `DriverProtection(10/10:8)`, `AllocationOffsetInBytes(10/10:8)`, `hProcess(16/19:8)`, `UpdateMode(8/8:4)`, `FirstPteVirtualAddress(10/19:8)`, `PageTableObject(16/19:8)` |
| 310/v0 ([line 204](C:/Projects/strix-alloy-clean/server/.local/optimization9h-20261004/etw-native-build-3bc6e3f283a541b9afd2c4a47d7f7bdc/decoded.jsonl:204)) | `pDxgAdapter(16/19:8)`, `hDmaBuffer(16/19:8)`, `ContinueNextBuffer(13/13:4)`, `hAllocationGlobalHandle(16/19:8)`, `RootPageTableSegmentId(8/8:4)`, `RootPageTableSegmentOffset(10/10:8)`, `hProcess(16/19:8)`, `StartVirtualAddress(10/19:8)`, `EndVirtualAddress(10/19:8)` |

Pointer fields, including `PageTableEntries`, remain recorded raw values. They were not dereferenced, treated as an inferred array, or joined by equality.

## Effect on the nine provenance edges

| Edge | Observed effect | Result |
|---|---|---|
| Referenced allocation namespace | 43/v0 arrays and 36/v2 local/global fields now have actual records. No supported Allocations[] namespace bridge is supplied. [line 387](C:/Projects/strix-alloy-clean/server/.local/optimization9h-20261004/etw-native-build-3bc6e3f283a541b9afd2c4a47d7f7bdc/decoded.jsonl:387), [line 199](C:/Projects/strix-alloy-clean/server/.local/optimization9h-20261004/etw-native-build-3bc6e3f283a541b9afd2c4a47d7f7bdc/decoded.jsonl:199) | Unresolved |
| Global allocation alias | 50/v0.hAllocationGlobalHandle and 33/36 global allocation fields are observed; 53/76/77 are absent. Names/raw values do not establish either global alias. [line 313](C:/Projects/strix-alloy-clean/server/.local/optimization9h-20261004/etw-native-build-3bc6e3f283a541b9afd2c4a47d7f7bdc/decoded.jsonl:313), [line 197](C:/Projects/strix-alloy-clean/server/.local/optimization9h-20261004/etw-native-build-3bc6e3f283a541b9afd2c4a47d7f7bdc/decoded.jsonl:197), [line 199](C:/Projects/strix-alloy-clean/server/.local/optimization9h-20261004/etw-native-build-3bc6e3f283a541b9afd2c4a47d7f7bdc/decoded.jsonl:199) | Unresolved |
| DMA alias | 175/43/50 contain pDmaBuffer; 178 and first 309/310 records contain hDmaBuffer. Both namespaces are observed, with no supported bridge between them. [line 225](C:/Projects/strix-alloy-clean/server/.local/optimization9h-20261004/etw-native-build-3bc6e3f283a541b9afd2c4a47d7f7bdc/decoded.jsonl:225), [line 387](C:/Projects/strix-alloy-clean/server/.local/optimization9h-20261004/etw-native-build-3bc6e3f283a541b9afd2c4a47d7f7bdc/decoded.jsonl:387), [line 313](C:/Projects/strix-alloy-clean/server/.local/optimization9h-20261004/etw-native-build-3bc6e3f283a541b9afd2c4a47d7f7bdc/decoded.jsonl:313), [line 16](C:/Projects/strix-alloy-clean/server/.local/optimization9h-20261004/etw-native-build-3bc6e3f283a541b9afd2c4a47d7f7bdc/decoded.jsonl:16), [line 203](C:/Projects/strix-alloy-clean/server/.local/optimization9h-20261004/etw-native-build-3bc6e3f283a541b9afd2c4a47d7f7bdc/decoded.jsonl:203), [line 204](C:/Projects/strix-alloy-clean/server/.local/optimization9h-20261004/etw-native-build-3bc6e3f283a541b9afd2c4a47d7f7bdc/decoded.jsonl:204) | Unresolved |
| Queue/execute pairing | 175-180 materialize sequences, packet-context/packet handles and fence fields. Counts or equal values do not establish pairing, scope or reuse. [line 225](C:/Projects/strix-alloy-clean/server/.local/optimization9h-20261004/etw-native-build-3bc6e3f283a541b9afd2c4a47d7f7bdc/decoded.jsonl:225), [line 230](C:/Projects/strix-alloy-clean/server/.local/optimization9h-20261004/etw-native-build-3bc6e3f283a541b9afd2c4a47d7f7bdc/decoded.jsonl:230), [line 229](C:/Projects/strix-alloy-clean/server/.local/optimization9h-20261004/etw-native-build-3bc6e3f283a541b9afd2c4a47d7f7bdc/decoded.jsonl:229), [line 16](C:/Projects/strix-alloy-clean/server/.local/optimization9h-20261004/etw-native-build-3bc6e3f283a541b9afd2c4a47d7f7bdc/decoded.jsonl:16), [line 34](C:/Projects/strix-alloy-clean/server/.local/optimization9h-20261004/etw-native-build-3bc6e3f283a541b9afd2c4a47d7f7bdc/decoded.jsonl:34), [line 58](C:/Projects/strix-alloy-clean/server/.local/optimization9h-20261004/etw-native-build-3bc6e3f283a541b9afd2c4a47d7f7bdc/decoded.jsonl:58) | Unresolved |
| Classification/execution interval | PacketType/uiType map names and raw values are recorded. Map contents/enumerant labels and exact GPU execution/preemption timing semantics are not supplied; 250 is absent. [line 225](C:/Projects/strix-alloy-clean/server/.local/optimization9h-20261004/etw-native-build-3bc6e3f283a541b9afd2c4a47d7f7bdc/decoded.jsonl:225), [line 313](C:/Projects/strix-alloy-clean/server/.local/optimization9h-20261004/etw-native-build-3bc6e3f283a541b9afd2c4a47d7f7bdc/decoded.jsonl:313), [line 16](C:/Projects/strix-alloy-clean/server/.local/optimization9h-20261004/etw-native-build-3bc6e3f283a541b9afd2c4a47d7f7bdc/decoded.jsonl:16) | Unresolved |
| Allocation owner/lifetime | 33/34 and 36/37 start/stop schemas are observed; 37/v2 fills the formerly missing stop inventory. Device/context/process lifecycles, all owners/shares and pre-existing-object rundown are absent. Natural bounded lifetimes may be inspectable later, but this review makes no object joins. [line 197](C:/Projects/strix-alloy-clean/server/.local/optimization9h-20261004/etw-native-build-3bc6e3f283a541b9afd2c4a47d7f7bdc/decoded.jsonl:197), [line 651](C:/Projects/strix-alloy-clean/server/.local/optimization9h-20261004/etw-native-build-3bc6e3f283a541b9afd2c4a47d7f7bdc/decoded.jsonl:651), [line 199](C:/Projects/strix-alloy-clean/server/.local/optimization9h-20261004/etw-native-build-3bc6e3f283a541b9afd2c4a47d7f7bdc/decoded.jsonl:199), [line 648](C:/Projects/strix-alloy-clean/server/.local/optimization9h-20261004/etw-native-build-3bc6e3f283a541b9afd2c4a47d7f7bdc/decoded.jsonl:648) | Unresolved |
| Process/allocation detail shortcut | 50.hProcessId and 36.hProcessAllocDetails are materialized with in_type=16, out_type=19, length=8. These typed raw fields do not define a numeric PID or beneficiary bridge; 288 is absent. [line 313](C:/Projects/strix-alloy-clean/server/.local/optimization9h-20261004/etw-native-build-3bc6e3f283a541b9afd2c4a47d7f7bdc/decoded.jsonl:313), [line 199](C:/Projects/strix-alloy-clean/server/.local/optimization9h-20261004/etw-native-build-3bc6e3f283a541b9afd2c4a47d7f7bdc/decoded.jsonl:199) | Unresolved |
| Guest process to Linux task | 472/492 and 474/493 are absent; no Halogen request or matching Linux task/container attestation was captured. | Unresolved |
| ETW engine to PDH interval | 110/250 adapter/node mapping records and original PDH integration interval are absent. QPC clock calibration alone does not supply engine/workload attribution. [line 1](C:/Projects/strix-alloy-clean/server/.local/optimization9h-20261004/etw-native-build-3bc6e3f283a541b9afd2c4a47d7f7bdc/decoded.jsonl:1) | Unresolved |

The [existing criteria](C:/Projects/strix-alloy-clean/docs/research/halogen-etw-implementation-scope-review-20261006.md:41) remain unchanged. Missing rundown leaves pre-existing objects unresolved; it does not invalidate every naturally captured bounded lifetime. This inspection performs no object matching. Numeric pointer equality, sequence equality and timestamp proximity supply no missing semantics. No Halogen request, guest/task attestation or PDH interval was captured, so this development increment demonstrates bounded collection/materialization only. The historical System-copy veto and unqualified prior performance observations remain unchanged.

## Full ID/version histogram

Total: **8,454 events**, **95 pairs**. Counts cover the full event rows, including IDs whose semantic role was not examined here.

| ID/version | Count | ID/version | Count | ID/version | Count |
|---|---:|---|---:|---|---:|
| 17/v0 | 168 | 18/v0 | 140 | 19/v0 | 140 |
| 22/v0 | 52 | 33/v3 | 5 | 34/v3 | 10 |
| 36/v2 | 10 | 37/v2 | 15 | 39/v0 | 15 |
| 43/v0 | 15 | 50/v0 | 15 | 55/v0 | 10 |
| 67/v0 | 5 | 68/v0 | 5 | 71/v2 | 88 |
| 72/v0 | 90 | 73/v2 | 92 | 74/v0 | 89 |
| 92/v0 | 5 | 94/v0 | 5 | 170/v0 | 15 |
| 171/v2 | 5 | 172/v2 | 27 | 173/v2 | 27 |
| 175/v1 | 35 | 176/v0 | 35 | 177/v1 | 35 |
| 178/v1 | 124 | 179/v0 | 187 | 180/v1 | 423 |
| 181/v0 | 168 | 182/v0 | 69 | 184/v1 | 12 |
| 215/v2 | 22 | 238/v0 | 80 | 242/v0 | 5 |
| 244/v2 | 80 | 245/v3 | 219 | 247/v0 | 33 |
| 248/v0 | 34 | 252/v0 | 10 | 259/v3 | 10 |
| 273/v4 | 168 | 274/v0 | 15 | 277/v0 | 5 |
| 278/v0 | 5 | 281/v0 | 221 | 282/v0 | 221 |
| 287/v0 | 5 | 289/v0 | 6 | 294/v1 | 110 |
| 295/v0 | 80 | 297/v0 | 66 | 300/v1 | 86 |
| 305/v1 | 27 | 307/v1 | 5 | 309/v1 | 133 |
| 310/v0 | 117 | 318/v0 | 47 | 319/v0 | 168 |
| 320/v0 | 92 | 321/v0 | 89 | 322/v1 | 191 |
| 323/v1 | 15 | 324/v0 | 206 | 325/v0 | 206 |
| 338/v0 | 35 | 339/v0 | 35 | 366/v0 | 840 |
| 367/v0 | 129 | 371/v0 | 186 | 386/v8 | 10 |
| 437/v0 | 10 | 450/v0 | 52 | 451/v0 | 52 |
| 458/v0 | 97 | 461/v0 | 15 | 466/v0 | 25 |
| 471/v0 | 17 | 473/v0 | 20 | 496/v0 | 53 |
| 502/v1 | 345 | 503/v0 | 97 | 505/v1 | 10 |
| 506/v0 | 158 | 507/v0 | 258 | 514/v0 | 313 |
| 527/v0 | 10 | 528/v0 | 10 | 529/v0 | 208 |
| 530/v0 | 208 | 550/v0 | 57 | 551/v0 | 174 |
| 552/v0 | 112 | 1069/v2 | 5 | — | — |

Validation: all 8,456 JSONL rows parsed; histogram sum and materialized-event count match the decoder's 8,454 events. No pointer values or ownership relationships were inferred.
