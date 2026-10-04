# Halogen CPU and SSD opportunities — 4 October 2026

The strongest new lead is the **active lookup table crossing WSL's Windows
filesystem boundary**. The v2 core is on native Linux storage, but the actual
gather64b manifest mounts its populated lookup source from `/mnt/c`. This is a
specific placement opportunity, not a demonstrated performance gain. No lookup
payload scan, copy, cache purge, affinity change, or inference run was performed
for this investigation. Stock compute, depth 2, and the 18-GiB physical/commit
reserve remain the controls.

## What the retained deployment actually reads

The retained manifest is
`server/.local/article0162-20261003/halogen-v2-c65536-gather64b/engine-manifest.json`.
Its bindings distinguish the core from the lookup source:

| Container path | Actual host source | Relevant boundary |
| --- | --- | --- |
| `/models` | `/home/revn/halogen-models-native` | Native Linux path |
| `/ngram-w4b.hgn` | `/mnt/c/AI/models/halogen-flashnext/qwen38-flash-next-w4b.hgn` | Windows drive mount |

`backends/halogen-wsl2-0.16.2/.local/machine.json` selects that same `ngram_source`.
Its `ngram-integrity.json` binds the Windows source's full identity to the pinned
SHA-256 `9c116bbc01f77b7a15464c1a124eb3325b286089b8a2a6f2856c9b246a235bd6`.
The core directory rule in `scripts/portable.py` refuses Windows-drive model
directories, but the separate lookup-source path does not impose that restriction.

Cheap Windows metadata inspection found only the v2 and w4b checkpoints in the
native model directory, with logical sizes 66,687,678,432 and 124,068,083,904
bytes. No standalone lookup file was present there. The [retained upgrade
report](../benchmarks/halogen0162-upgrade-20261003.md) explicitly identifies the
native w4b path as an empty sparse placeholder. A matching logical byte count
does not validate its contents; it must not replace the populated source.

Microsoft recommends storing files in the Linux filesystem when Linux programs
read them, to avoid the cross-filesystem path. This supports testing native lookup
placement, but supplies no Halogen-specific speed estimate. [WSL filesystem
guidance](https://learn.microsoft.com/en-us/windows/wsl/filesystems),
[WSL interop performance](https://learn.microsoft.com/en-us/windows/dev-environment/wsl-interop).

## Storage inventory and the next placement experiment

Observed Windows metadata, before the next root-owned baseline window:

| Device or file | Placement / capacity |
| --- | --- |
| C: | Disk 0, KINGSTON OM8TAP42048K1-A00 NVMe; about 60.34 GiB free |
| E: | Disk 1, XG7000-2TB-FB 2280 NVMe; about 1.099 TiB free |
| Ubuntu-24.04 VHDX | On C:, file length 632,131,944,448 bytes (588.72 GiB) |
| Populated Windows w4b | 124,068,083,904 bytes on C: |

The VHDX length is a host-file metadata observation, not guest free space or a
measurement of allocated extents. Both active core storage and the lookup source
therefore ultimately use C:'s physical SSD. E: is a separate physical NVMe, but no
native Linux lookup copy on it has been qualified.

A full w4b copy is unnecessary for lookup-only relocation. The existing reviewed
`scripts/benchmarks/halogen_ngram_extract.py` can preserve the lookup tensor in a
standalone HGN. It still writes a 51,200,245,764-byte payload (47.68 GiB), requires
source identity/checksum proof, and needs a root-authorized I/O window. This is
not a small metadata operation. No extraction or filesystem relocation is
authorized or performed here. Moving only to `/mnt/e` would change the SSD while
retaining the Windows filesystem boundary; those are separate experiments.

For any later placement comparison, retain the same lookup bytes, core weights,
prompt/request hashes, sampling, depth, context, cache policy, and guard. Measure
first-prompt lookup time, prefill, actual request wall, and subsequent warmed
calls separately. Existing OS cache residency and fixed run order remain
confounds; no cache purge is proposed.

## Bounded alternative to copying the whole table

Static inspection disproved the proposed `pread` interception point for the
actual prompt lookup gather. The pinned x86-64 ELF `flash_serve` is 26,052,768
bytes, SHA-256
`ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b`.
It imports `pread`, but the lookup rows are copied directly from a readonly
file mapping. The stripped binary's nearest displayed C++ symbol labels are not
function identities; the instruction RVAs below identify the observed paths.

| Instruction RVA | Observed behavior |
| --- | --- |
| `0x176c685` / `0x176c7f5` | Reads `HALOGEN_NGRAM_TABLE`, then calls HGN loader `0x1875ab0` with its skip-host-registration argument set to 1 |
| `0x1875af5` | Opens that source with flags 0 (`O_RDONLY`); no `O_DIRECT` on this source open |
| `0x1875b39` / `0x1875b44` | Maps the full `fstat` size with `PROT_READ=1`, `MAP_SHARED=1`, file offset 0, then closes the descriptor |
| `0x1875f7f` | Constructs each tensor's source pointer as mapping base plus its HGN tensor offset |
| `0x1775050` / `0x1775449` | Resolves `ngram_embedding.weight` from the separate lookup model and stores its source pointer at engine object offset `0x678` |
| `0x17d80ce` / `0x17d80fc` | Serial gather computes `source + row_id * row_bytes` and calls imported `memcpy` |
| `0x1847cb0` / `0x1847d3b` | Gather thread worker claims batches of 256 rows, computes the same source address, and calls imported `memcpy` |
| `0x17d92ff` | Emits the retained `lookup table: ... took ... to read` timing message for this gather |

The thread worker is selected by the thread-state vtable at `0x18d7ec0`;
its `_M_run` relocation resolves to `0x1847cb0`. The gather thread getter at
`0x17e5520` clamps to 1–256 and defaults to 64. Header/table parsers and core
upload routines have `pread` calls, but they do not establish a `pread` lookup-row
path. No `pread`/`pread64` cache prototype was implemented after this audit.

The lookup initializer already calls `madvise(MADV_RANDOM=1)` at `0x1775481`.
Its getter at `0x1780620` reads `HALOGEN_FLASH_NGRAM_RANDOM` and defaults to 1;
the retained manifest does not override it. This is static behavior of the
pinned binary, not a recommendation to change an undocumented flag. The only
other imported `madvise` call observed is `MADV_HUGEPAGE` on an anonymous buffer.
The lookup HGN loader and gather have no `POSIX_FADV_DONTNEED` call. Other core
upload/repack paths do use that advice, so the global import alone must not be
interpreted as lookup cache clearing.

A root-authorized 264-byte header/tensor-directory read of the populated Windows
source confirmed storage 10 (FP8 global scale), dimensions `[128, 2500012, 160]`,
tensor offset 1,882,122,624, length 51,200,245,764, and XOR32 metadata 4,135,773,463.
No model payload was read and no checksum was recomputed. The receipt is
`server/.local/halogen-lookup-header-audit-20261004.json`. Its Windows `fstat`
identity is deliberately kept separate from the retained WSL identity; device
and inode values differ across those namespaces.

For this source the binary selects a **160-byte row stride**, while a cold row
can fault one or two 4-KiB filesystem pages. With tensor offset `O` and actual row
ID `r`, the pages are from `floor((O + 160*r)/4096)` through
`floor((O + 160*r + 159)/4096)`. The tensor starts at page offset 2432, not a page
boundary. Four of the 128 possible row-start page offsets straddle a page;
this arithmetic is not a measured frequency for a request.

Targeted prefetch remains a conditional research direction: capture actual row
IDs after the gather's device-to-host copy (`0x17d7aa6`), derive and deduplicate
their pages, and determine residency/fault cost before changing scheduling.
Static inspection supplies neither actual duplicate-page counts nor cache-hit
telemetry. Native placement remains the concrete experiment with the clearest
mechanism. No blind pre-read, lookup-copy shim, anonymous LRU, sparse replacement
HGN, or live engine fault instrumentation was implemented. The Linux page cache
already supplies bytes for this mapping; another cache could merely duplicate
memory and reduce its capacity.

Linux `readahead` can populate an exact range without moving its file offset,
but may block while locating filesystem metadata. An independent deadline is
needed for any later experiment. Advice is only a hint: `MADV_RANDOM` suits
random references, while sequential advice can fetch unrelated pages. Therefore
blindly reading the first few hundred MiB of a 47.7-GiB random lookup table is
not a supported optimization. [readahead](https://man7.org/linux/man-pages/man2/readahead.2.html),
[madvise](https://man7.org/linux/man-pages/man2/madvise.2.html),
[pread](https://man7.org/linux/man-pages/man2/pread.2.html).

## CPU controls and acceptance

The host reports 16 physical cores and 32 logical processors. The documented
`HALOGEN_NGRAM_GATHER_THREADS` default of 64 is lookup I/O concurrency during
uncached prefill, not evidence that 64 CPU compute threads should be pinned to
32 logical processors. Upstream describes 4-KiB random row reads and says this
knob leaves decode unchanged. Its `HALOGEN_GGUF_THREADS` control is startup GGUF
repacking, irrelevant to the current HGN deployment. No supported general
Halogen CPU-affinity knob was found in the pinned flags. [Pinned 0.16.2
flags](https://github.com/peonist-ai/halogen-flash-server/blob/7f31bbd4021f217a1be9776bdb7304bcf8eca62d/docs/FLAGS.md).

The existing [64/32/64 gather experiment](../benchmarks/halogen0162-gather-20261004.md)
already found no winner against warmed 64. Lookup reads were 36.6/10.7 seconds
in the first 64 cell, 10.4/9.4 at 32, and 10.4/9.8 at final 64. It restarted
engines without flushing or measuring OS file-cache residency. Repeating that
thread comparison would not address the newly identified `/mnt/c` boundary.

Linux affinity is per thread and constrained by the process's allowed CPU set;
guest CPU identities are not proof of Windows physical-core placement. Affinity
remains lower priority until telemetry shows a CPU scheduling bottleneck. No
global WSL processor setting or affinity was changed. [Linux affinity
semantics](https://man7.org/linux/man-pages/man2/sched_setaffinity.2.html).

Exact storage placement, caching, and CPU scheduling should preserve lookup
bytes and outputs. They can reduce stalls; they do not improve the drafter's
prediction quality or establish higher acceptance. Current sampled acceptance
remains 2,094/2,497 (83.8606%) across the matched gather cells. Any future measured
acceptance change needs identical requests and explicit proposed/accepted
counters, rather than a storage optimization label.

## Implemented observation helper

`scripts/benchmarks/halogen_io_probe.py` is isolated from the sealed inference
clients and runners. It records the retained engine manifest's digest, selected
mounts and controls, Windows disk read rates/queue lengths, host CPU, vmmem
process counters when available, and physical/commit memory frames. It also
retains raw disk counters for later interval calculations. The default takes one
snapshot; `--seconds` permits at most 60 seconds. Counter queries have a timeout,
output is created exclusively, and the observation floor cannot be below 18 GiB.

The helper reads no model payload and invokes no WSL command. It does not kill
the engine or change caches, scheduling, memory reservations, or system settings.
Its reserve check is an observation floor; the root-owned engine guard remains
responsible for engine admission and cleanup.

Host disk counters include other applications and all WSL I/O on the same SSD.
vmmem counters aggregate the VM rather than identifying lookup reads. Raw
counters require interval differences and the proper Windows counter formula;
they are not already latency measurements. CPU process counters may exceed 100
across multiple logical processors. Record query duration so observation
overhead stays visible. [Windows performance counter
types](https://learn.microsoft.com/en-us/windows/win32/wmisdk/wmi-performance-counter-types).

Example for a root-authorized observation window, using an existing output
directory and a new evidence filename:

```powershell
& C:\AI\runtimes\winml-npu\Scripts\python.exe -B `
  .\scripts\benchmarks\halogen_io_probe.py `
  --manifest .\server\.local\article0162-20261003\halogen-v2-c65536-gather64b\engine-manifest.json `
  --out .\server\.local\halogen-io-observation-NEW.json --seconds 60 --interval 2
```

One root-authorized host snapshot completed after engine cleanup and is retained
in `server/.local/halogen-io-metadata-20261004.json`. This validates counter
collection only; it did not sample inference and supplies no engine speed or
lookup-fault conclusion. Query duration and reserve frames are in the receipt.
The query took 6.422 seconds; `--interval` is an additional pause after a query,
so this CIM helper is unsuitable for fine-grained per-token timing. The first
formatted counters returned zero and no vmmem instance; one snapshot cannot
validate rate initialization or establish guest idleness.
`--help` was also smoke-checked. The final deadline logic treats a counter query
clipped by the requested observation deadline as a bounded stop when earlier
samples succeeded. No broad tests or hardware inference run was launched during
this work.

## Online leads kept separate from evidence

A [Reddit SSD-offload report](https://www.reddit.com/r/LocalLLM/comments/1vz927j/got_qwen38nextflash_ngram_ssd_offload_working_in/)
is a lead about n-gram layout and demand paging in llama.cpp. It is not a matched
Halogen result, and its no-performance-impact assertion is not established on
this host. The primary WSL guidance and actual manifest above provide the
actionable reason to investigate placement here. A speculative change to
lookup contents or knowledge injection would change the model and is outside
this exact-weight performance investigation.
