# Prospective Windows GPU Copy attribution implementation — 2026-10-07

The recorder now requests DxgKrnl state before and after a bounded work window.
The decoder materializes installed TDH scalar map labels alongside raw bytes.
The offline analyzer joins actual captured guest/context lifetimes and reports
the remaining gaps per packet. The old idle capture is an offline regression
input, not the sole basis for the prospective result.

## Changed capture

Build `scripts/benchmarks/halogen_dxg_trace_record.c` and
`halogen_dxg_trace_decode.c` with installed MSVC/SDK, `/W4 /WX /O2 /MT`, and the
libraries named in each source. A pinned successful build and exact arguments
are retained in
`server/.local/optimization9h-20261004/gpu-copy-attribution-reviewed-build-dd9b48b341114a9399717802bf4a6b16/build.json`.

The root lifecycle owner runs this command, with fresh absolute paths and a
unique hexadecimal session suffix:

```text
record.exe --output <fresh.etl> --seconds 30 --keywords 0x04900845 --capture-state --session StrixAlloy-GpuCopy-<uuidhex> --stop-file <fresh.stop>
```

Wait for the flushed `capture_ready` JSONL record before creating the new WSL
GPU consumer or restarting the normal engine. Record Windows QPC brackets and
the exact Linux initial-namespace task ID, start ticks, boot ID, executable and
task name. Create the stop marker after the controlled work completes, or let
the 30-second bound stop the owned session. The recorder stops only its exact
returned handle. It never adopts a named session, elevates, or launches work.

The installed keyword inventory verifies the requested mask as Base `0x1`,
References `0x4`, Resource `0x40`, LongHaul `0x800`, GPUVA `0x100000`, VirtualGpu
`0x800000`, and HardwareSchedulingLog `0x4000000`. The installed descriptor and
keyword receipt is saved in the preceding
`gpu-copy-attribution-final-build-7ea99ae0d5454c57a20ca507b98fa759` directory as
`installed-dxg-schema-keywords.json`.
No PID filter excludes System or lifecycle records.

`EnableTraceEx2(EVENT_CONTROL_CODE_CAPTURE_STATE)` uses a bounded 1,000 ms
timeout. Both API return codes and QPC brackets are retained. Success requests
provider state; emitted records must establish coverage independently.
([Microsoft API contract](https://learn.microsoft.com/en-us/windows/win32/api/evntrace/nf-evntrace-enabletraceex2))
The default ETL cap remains 64 MiB, native buffer pool 4 MiB, recorder private
commit 16 MiB, decoder private commit 32 MiB, and memory reserves remain guarded.

## Native decode and offline joins

Decode only the completed owned ETL:

```text
decode.exe --input <completed.etl> --output <fresh-decoded.jsonl> --max-output-mib 256
python scripts/benchmarks/halogen_gpu_copy_attribution.py --decoded <fresh-decoded.jsonl> --recorder-receipts <recorder.jsonl> --output <fresh-analysis.json> --identities <optional-identities.json>
```

The output limit is explicit and bounded to 64–256 MiB; raising it changes the
streamed output cap, while input and memory caps remain fixed. The decoder keeps
all raw property bytes and schema types. `TdhGetEventMapInformation` and
`TdhFormatProperty` add map/format statuses and a formatted scalar value; arrays,
unknown maps, unsupported schemas and unsuccessful calls do not become guessed
labels. ([TDH map API](https://learn.microsoft.com/en-us/windows/win32/api/tdh/nf-tdh-tdhgeteventmapinformation))

The analyzer streams bounded JSONL and indexes at most 20,000 object lifetimes
and 20,000 DMA spans. It uses these captured relationships:

- DMA 175/v1 and 176/v0 pair by `hContext`, `ulQueueSubmitSequence` and matching
  `PacketType`; submission/completion ID equality is never presumed.
- Context 30/32/v0 supplies `hContext`, `hDevice`, and `NodeOrdinal`.
- Device 27/29/v2 supplies `hDevice`, `pDxgAdapter`, and `DxgProcess`.
- Guest Process 472/492/v0 supplies `DxgProcess`, `ProcessIdInVm`,
  `DxgProcessInVm`, `DxgVirtualMachine`, and `ProcessNameInVm`.
- VM 474/493/v0 supplies `DxgVirtualMachine` and `VmGuid`.
- Adapter 110/v1 and NodeMetadata 250/v0 supply adapter LUID and node type.
- HwQueue 422/424/v0 supplies local `hHwQueue`, `ParentDxgHwQueue` and `hContext`.
  Hardware Info450/v0 values match captured `ParentDxgHwQueue`, with the local
  handle retained separately. Producer pointer-origin proof can verify this
  parent namespace for its pinned Windows image; without it, the result remains
  an observed parent-value association. Info450 has no execution duration.

All joins require a unique active captured lifetime and span continuity. Each
child binds to the parent lifetime present at the child's captured birth,
using QPC and retained source-record order together. Reused ancestor handles
never relabel old children. The recorder's ETL path and byte size must match the
decoded header before its final loss counters qualify that trace.
Stop events prevent stale handle reuse; conflicting starts and repeated pending
sequences remain unresolved. Duplicate identical rundown records enrich the
same live object. Host Process 471/491 never substitutes for guest Process472/492.
Header PID 4 supplies no ownership whitelist.

NodeMetadata's `EngineType` has no installed manifest map. The analyzer reads
and hashes the primary installed SDK `d3dkmdt.h` enum; the retained enum places
`DXGK_ENGINE_TYPE_COPY` at value6. It applies that definition only through a
captured adapter/node mapping. Physical PDH adapter/index equivalence uses the
separate native collector below. ([Microsoft enum](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/d3dkmdt/ne-d3dkmdt-dxgk_engine_type))

An optional identity file is a JSON list. Each identity has `label`,
`process_id_in_vm`, `process_name_in_vm`, `vm_guid`, `qpc_before`, `qpc_after`, and
`linux_task_evidence` containing `initial_namespace_tid`, `start_ticks`, `boot_id`,
and `executable`. The lifecycle owner supplies this attestation; the analyzer
matches all values and enclosing packet bounds. Without it, a complete captured
guest chain is reported with `label=null`. A standalone consumer is labelled
separately from Halogen.

## Verification and limits

Thirty-six offline regressions pass, including positive new guest/context ownership,
PID4-only rejection, host/guest distinction, trace loss, stopped or reused handles,
process lifetime ending during a packet, window bounds, mismatched packet type,
sequence reuse, ancestor reuse, equal-QPC record order, unrelated loss receipts,
hardware queue ownership, prospective PDH criteria, unknown engine classification,
nullable object/DMA fields, failed or mismatched native mapping receipts, linked
adapter ambiguity, local/parent queue separation, bounded native receipt count,
full global/local allocation lifetimes, image-scoped namespace proof, scoped
parent-or-scheduler producer semantics, event53 proof isolation, and loss/window
requirements for allocation-origin qualification.
Materialized null object identities are retained as semantic
join gaps rather than malformed schemas. Null DMA pointers never alias allocation
provenance; null-context packets remain present and unresolved.
Native `/W4 /WX` builds pass.
Plan-mode CLI checks emit no session API calls and create no ETL. Invalid keyword
and output-cap options are rejected.

The new decoder materialized all 8,454 events in the retained completed idle ETL,
with zero unresolved events/properties, 25,104,798 bytes of JSONL and approximately
5.01 MiB peak private commit. The analyzer correctly retains 35 unresolved DMA
spans and no guest bridge in that old trace. These checks ran offline; this source
agent performed no capture, GPU work, server action or NPU work.

Captured packet ownership does not establish exclusive ownership of a PDH
integration interval. System paging allocation beneficiaries/sharing, referenced
allocation namespaces, global allocation and DMA aliases, physical adapter/index
mapping, GPU execution/preemption accounting, and unobserved rundown coverage
remain explicit independent questions unless an actual receipt closes the
particular mapping. The analyzer emits no performance gain
claim. Without `--pdh-intervals`, PDH qualification is `null/not-requested`.
With that optional JSON input, the evaluator checks interval enclosure, captured
engine/owner coverage, raw-pair validity, generation continuity, primary timing
binding and an exact native adapter/node metadata receipt. It records the actual
remaining criteria. Physical mapping can be supplied by `D3DKMTQueryAdapterInfo`
with `KMTQAITYPE_NODEMETADATA`: `NodeOrdinalAndAdapterIndex` uses the high word for
the physical adapter and low word for the node.
([Microsoft structure](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/d3dkmdt/ns-d3dkmdt-d3dkmt_nodemetadata))
Actual prospective traces and results belong to the root
lifecycle owner and are retained separately.

## Collected physical node mapping

`scripts/benchmarks/halogen_gpu_node_metadata.c` accepts one exact PDH Copy
instance and a fresh output path. It uses the installed SDK structs, opens only
the adapter selected by that instance's LUID, queries physical adapter count,
queries the packed physical-index/node ordinal, and closes that owned adapter
handle. It creates no device, context or queue and submits no GPU work. A bounded
SHA256 of its own executable, all API statuses, and QPC query bounds are retained.
`--plan` executes no D3DKMT calls and creates no receipt file.

The reviewed `/W4 /WX` native build is retained at
`server/.local/optimization9h-20261004/gpu-node-metadata-build-0f34ec92fdcd4e77a0d07998d047c9f7/build.json`.
Source SHA256 is `DB43C88B06C9E43314344542FD3955E9C551A66E2BB24F87BF8DAFADA2B25CE2`;
executable SHA256 is `7370C52B3199CC7D9A731939C85C78D9335D00A176735D6B94DD1B4CF1EC0D2D`.
Root executed the read-only query and retained `actual-node1-copy.jsonl` in that
build directory. It reports LUID `0x0000000000011884`, physical adapter 0,
node 1, `DXGK_ENGINE_TYPE_COPY=6`, physical adapter count 1, and zero
open/query/close status codes. The positive query enclosure is
QPC `2314743421653..2314743421936` at 10,000,000 Hz.

Pass the actual JSONL receipt with `--native-node-metadata`. The analyzer validates
the exact instance/PID, LUID, packed and explicit index/node fields, count,
query and cleanup success, QPC bounds/frequency and executable hash. It attaches
physical index 0 to matching captured Copy packets only for a single physical
adapter. A linked adapter needs an additional captured context physical-index
bridge. The receipt is a point observation; it does not attest the PDH PID or
prove instance generation continuity throughout a counter integration interval.

`--namespace-bindings` reads reviewed producer dataflow evidence. The analyzer
hashes every referenced installed driver image and public PDB before accepting
the exact descriptors, field names and pointer object types in that receipt.
A pinned proof for MemoryTransfer50/v0 and AdapterAllocation33/35/v3 can close
the `hAllocationGlobalHandle`/`hVidMmGlobalAlloc` namespace alias. A pinned proof
for DmaPacket450/v0 and HwQueue422/424/v0 can close the host parent-queue namespace.
Neither proof applies automatically to a different descriptor or installed image.

The reviewed installed writer proof is retained at
`server/.local/optimization9h-20261004/namespace-symbol-analysis-d36c2e93d7b04c4798800fb594ac01e5/field-namespace-bindings.json`
(SHA256 `35e998ba20270829df937c4716717d8868085e70f95a0eb5a37873321df423d7`).
Its readable evidence and independent validation are beside it as
`field-namespace-evidence.md` and `field-namespace-validation.json`. Both installed
drivers are version `10.0.26100.7462`; the pinned `dxgmms2.sys` SHA256 is
`46d997e3b29a9ec0deae812e1b94636b72341bc86602fe13e43fcc962310994f` and
`dxgkrnl.sys` SHA256 is
`9dc86363f49003fccd06e4acc01427b203af60cfe2cff47bd9308744b03c82f9`.
Validation independently checks image/PDB matching, eight schema fields, ten raw
descriptors, 159 instruction bytes/source lines, 26 symbol groups and the scheduler
interface dispatch pointer. PDB DBI age1 matches image RSDS age1; PDB Info age3 is
retained separately. The hardware producer emits its `DXGHWQUEUE*` parent when
present and its `VIDSCH_HW_QUEUE*` scheduler fallback when absent. The analyzer
admits only a captured nonzero parent lifetime; the fallback never licenses local
`hHwQueue` equality. Allocation-origin qualification also requires qualified native
trace integrity, enabled capture enclosure and exact Linux task evidence.

MemoryTransfer50's operation is preserved: `uiType0` is allocation fill, `uiType5`
is discard, and `uiType8` uses initialization-context allocation. A verified
allocation alias does not change these operation meanings into payload copies.

## Fresh capture evidence

Root's fresh CAPTURE_STATE trace `real-handoff-74920208312040b988d64829e87a8270`
decoded all 43,354 events with zero unresolved properties and zero ETW loss.
It contains actual VM/guest bridge schema: VM493/v0 at decoded line 204,
guest472/v0 at line 16027, and guest492/v0 at line 28649. The guest is Xwayland,
`ProcessIdInVm=2348`, VM GUID `d3a17be5-2bfb-4255-967a-70c201ecf413`.
`actual-schema-coverage.json` preserves those exact source records and null-field
counts. The corrected analyzer classifies 125 DMA spans as Copy and leaves all
125 guest owners unresolved. The attempted producer performed zero copies.

The next trace `real-handoff-dd92b430ee9d43a48cfecfd200151391` decoded all 57,586
events with qualified native integrity. With the actual node query receipt,
331 captured DMA Copy spans bind to physical adapter 0/node 1. All 331 still
lack a captured guest owner. The consumer exited before GPU initialization with
`owned-GPU-init-release-required` and zero copies. Its initial-namespace birth
receipt preserves PID 918, namespace PIDs `[918,1]`, start ticks 3615,
boot ID and executable; this does not invent a missing Dxg guest link.
No component ownership or speed gain follows from either failed producer run.

## Successful component and observed System Copy associations

The successful trace `real-handoff-15ce20218f854c5b862db86bcce14436` contains
62,234 fully decoded events with qualified native integrity. The consumer passed
12 measured rows with exact GPU output and 37 HIP copy calls. Captured guest
task 2264 (`consumer`) has 78 Info450 parent-queue associations, all through
captured Compute-class contexts. These API copies do not establish ownership of
the Windows Copy counter.

The trace also contains 325 DMA Copy spans: 322 use a device with `DxgProcess=0`
and three use host ProcessId2796. Consumer allocations are positively observed:
33 AdapterAllocation33 global objects, 33 DeviceAllocation36 local objects,
and 68 PagingQueuePacket322 starts whose `DxgDevice` names the consumer device.
Sixty-six paging `Alloc` values match the captured local allocation values.
Twenty-two Transfer50 global-handle associations resolve unique captured global
allocation create/free lifetimes, local-reference create/free lifetimes, the
consumer device lifecycle, guest lifecycle and VM lifecycle. Their first later
same-named `pDmaBuffer` matches are 18 distinct System Copy DMA spans.

`component-attribution-allocation-lifetimes.json` preserves every predicate and
source reference, including allocation sizes and transfer operation/byte fields.
`system-copy-beneficiary-evidence.json` preserves the initial concrete paging
investigation. The fresh `component-attribution-reviewed-native-proof.json` in
that same capture directory consumes both the pinned writer proof and actual
native node receipt. It verifies all 22 consumer allocation aliases and resolves
79 Info450 guest owners (78 consumer, one Xwayland), all through Compute-class
contexts. Linux task attestation remains zero. Matching a reusable DMA pointer and source order does not alone
prove DMA batch membership or PDH occupancy.

The v2 successful trace `real-handoff-v2-1559059fb91c48c1a063fa96814a4940` contains
67,641 events with qualified native integrity and 350 DMA Copy spans. It preserves
the system `/proc` chain `[979,914,1]`, executable SHA256, container cgroup, boot
ID and per-task birth records. Captured consumer `ProcessIdInVm=5214` does not
equal any supplied task ID, so its identity list remains empty. Root's separate
CPU-only self probe demonstrates that the visible `/proc` namespace can omit
the kernel PID. Its fresh `component-attribution-reviewed-native-proof.json`
likewise verifies 22 consumer allocation aliases and resolves 79 Info450 captured
guest owners, with zero Linux task attestations. The historical receipts cannot
be retroactively upgraded by a later PID probe. The subsequent native self-PID
mechanism supplies the prospective namespace binding.

`paging-dma-membership-observations.json` in each successful capture preserves a
bounded next mechanism. Of the 22 consumer MemoryTransfer50 records, seven are
fill, eight initialization-context and seven discard. Fifteen lie inside one
same-thread PagingQueuePacket324 dispatch /325 stop interval. Seven fill records
are followed within that dispatch by Queue178 with the matching DMA pointer;
its exact context and submit sequence resolve one DMA175/176 span and one
Queue180 completion carrying the same queue-packet pointer. These recorded chains
remain explicitly unqualified. The installed producer positively preserves the
DMA object through VIDMM_GLOBAL's current buffer, the submit structure, queue
packet and execution packet. Its fill logger nevertheless emits event50 before
checking the build HRESULT. A `STATUS_GRAPHICS_INSUFFICIENT_DMA_BUFFER` retry can
flush prior commands and then retry the attempted fill. Pointer and queue
generation evidence therefore establish a build-attempt association, while
successful per-fill byte commitment requires another predicate. These chains do
not imply exclusive counter ownership or GPU occupancy.

The fresh combined proof is
`server/.local/optimization9h-20261004/fill-paging-dma-native-review-b2fe4bc1baf842a98f5c5a9c6d4ce939/field-namespace-bindings-with-fill-membership.json`
(SHA256 `0a3a4c672235c6afc333b46569c26ed1076b3e2bbe563691cc2762ee95e0f440`).
It preserves the original proof as an exact prefix and appends 24 pinned native
instruction groups, buffer object type, queue generation and dispatch evidence.
Its `fill-paging-dma-membership.verified` is explicitly false. The readable
`review-findings.md` beside it records the positive producer aliases and concrete
precommit flush/retry counterexample.

## Native kernel-PID attested v3 result

Root's successful `real-handoff-v3-22915da8997c4a0891fe2c9fee7e3f84` capture has
62,406 fully decoded events and qualified native integrity. Its native
before-HIP own-socket probe observes kernel PID/TGID 2302, with all probe descriptors
closed and no persistent attachment. The separate system `/proc` view is
`926 -> 861 -> 1`; it is retained without substituting any of those IDs for the
kernel PID. Starting, ready, closed and before/after receipts preserve one boot
ID `06019efd-ff1b-4b8d-8c9f-24401e543bfd`, birth tick 4549 and executable SHA256
`e55e90b3eba7cdc5be9c31e5fb765c7532475a61affcfc488dc1e11978c3f020`.

Captured guest472 records at decoded lines 31268 and 31278 name `consumer` with
`ProcessIdInVm=2302`. Their VM pointer resolves captured493 line 197 to GUID
`e26026b2-5f6f-485e-a66a-dfa3c90d0e56`. Windows `perf_counter_ns` execution bounds
convert with floor/ceil to decoder QPC `2341794341874..2341843377106` at 10MHz.
`component-identities-native-kernel.json` preserves all source receipt hashes,
native helper/source pins, namespace views and captured guest/VM references.

`component-attribution-native-kernel-reviewed.json` consumes that identity, combined
namespace proof and actual node query. It attests all 78 consumer Info450 records
through Compute-class contexts and qualifies 22 consumer allocation origins:
seven fill, eight initialization-context and seven discard. No consumer event50
lies in measured rows QPC `2341829840190..2341830591716`. The 339 native
physical0/node1 Copy spans remain without attested exclusive consumer ownership.
`component-native-kernel-reviewed-summary.json` summarizes those exact scopes.
The reviewed analysis SHA256 is
`4dc002d15ab6272226ab8efce1850e60233ee7791e988bad19a6d41654fd4867`;
the summary SHA256 is
`39a98a74891270112227bcacca70d29300880557f9ffb7fc1e04a9c01541a208`.
The independent final review receipt is
`server/.local/optimization9h-20261004/fill-paging-dma-native-review-b2fe4bc1baf842a98f5c5a9c6d4ce939/v3-native-kernel-independent-review.json`
(SHA256 `79e52fa030763ddc41ef7769e70f4f93b1b85584cf8a6c57eaacf85d38cf76f7`).
It rechecks every input/source pin, exact native identity and VM join, all 62,406
records and 8,799 referenced source lines, and the admitted/unqualified boundaries.
The v3 `paging-dma-membership-observations.json` preserves seven bounded
fill/build-attempt queue chains; all precede measured rows and remain unqualified
for successful committed fill membership. Neither 37 HIP API copies nor the
allocation-origin milestone is converted into whole Copy-counter ownership or a
token throughput claim.
