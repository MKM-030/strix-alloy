# Halogen 0.20.7 WSL memory probe and N-Gram verification

## GPU allocation reads

The standalone HIP probe was built in the pinned Halogen 0.20.7 image for
gfx1151. It compares the same 256 MiB of synthetic data in `hipMalloc` device
memory and in a private native ext4 mapping registered through HIP. The probe
checks the GPU result against exact integer checksums and keeps device-event
time separate from host time. Each arm runs in its own process.

The probe identified the AMD GPU after it received the same DXCore library as
the serving container. In the admitted configuration, `hipStreamCreateWithFlags`
returned `hipErrorOutOfMemory` with Halogen running and again with Halogen
unloaded. A final attempt used the serving container's ROCm flags and 44 GiB
cgroup limit and produced the same error. All three runs exited before
allocating the source buffer. HIP's stream
creation code also uses this error when internal stream creation fails, so the
error code alone cannot identify the unavailable resource.
[HIP stream implementation](https://github.com/ROCm/clr/blob/develop/hipamd/src/hip_stream.cpp)

Windows exposed Local, Dedicated and Shared adapter counters. The Non Local
counter set had no instance. The counters describe adapter totals. Assigning
Halogen's weight reads to an allocation requires per-allocation evidence. The
ROCm report covers a discrete R9700. The 8060S integrated GPU uses UMA.
[Microsoft UMA memory pools](https://learn.microsoft.com/en-us/windows/win32/api/d3d12/ne-d3d12-d3d12_memory_pool) · [ROCm R9700 report](https://github.com/ROCm/rocm-systems/issues/13006)

## N-Gram startup integrity

The normal restoration triggered a complete SHA-256 verification of the
124,068,083,904-byte N-Gram source on Windows NTFS via WSL. The source and its
size, inode, mtime and ctime matched the saved Linux receipt. The projected
`st_dev` differed. The new matching SHA-256 receipt was written **11 min 46 s**
after verification began. Model loading followed the integrity check.

A read-only prototype retrieved the NTFS volume identity, 128-bit file ID,
size, timestamps, journal ID and per-file USN for the real source twice, with
equal results. A separate synthetic fixture linked a full WSL SHA-256 check
to the native read lease. It rejected a same-size edit after the last-write
time was restored, a replacement at the same path, a different journal ID
and changed mount provenance. A real WSL write-open was denied while the
Windows lease was held. A simulated change to the projected Linux device
number was accepted only with the unchanged native generation and matching
DrvFS provenance. The metadata observation took about 0.55 s on the synthetic
fixture. A CPU-only launch of the pinned image confirmed that the read-only
container bind reported the same file identity and SHA-256 as the WSL source.
[Windows file identity](https://learn.microsoft.com/en-us/windows/win32/api/winbase/ns-winbase-file_id_info) · [Windows file USN](https://learn.microsoft.com/en-us/windows/win32/api/winioctl/ni-winioctl-fsctl_read_file_usn_data)

## Managed NTFS receipt

The 0.20.7 managed startup now supports a second receipt for the stock v2 NTFS
bind. A required full hash seeds the NTFS receipt under the same native read
lease. A current Linux-only receipt keeps its original behavior. The approved
NTFS path sends the fresh WSL file identity to the container and keeps the native
lease until readiness. The supervisor checks the file bind before it launches
the engine. If the native witness is unavailable and an NTFS receipt already
exists, the service performs a full content check. A Windows file lock or
write-sharing conflict refuses startup.

The managed code was exercised with a small NTFS file in the pinned image,
with CPU only. It read the fixture once to seed the receipt. After simulating an
older WSL device number in the saved receipt, the metadata check took 0.32 s
and reused the pinned hash. A wrong file identity, a writable bind and a
different selected engine path each stopped the supervisor before the child.
Rewriting the fixture while preserving its size and last-write timestamp
forced a full hash and that hash was rejected.

The running stock instance predated this change. A background Windows verifier
read all **124,068,083,904 bytes** directly from the NTFS source, using aligned,
unbuffered reads under one native read lease. It matched the pinned SHA-256 and
published the managed receipt after checking both the Windows and WSL file
generations. The summed time inside `ReadFile` was **199.57 s**. The full
verification took **793.41 s** with a 160 MiB/s cap and pauses for serving
traffic. The earlier full WSL hash took **706.05 s**. These measurements use
different I/O conditions.

The managed reader reused the production receipt in **0.912 s** with the
full-content reader disabled for verification. A separately copied receipt
with a simulated older WSL device number also reused the verified generation.
The receipt applies to startup. Prefill, Decode and MTP rates belong to the
separate inference benchmarks.

After both checks, the same Halogen instance on port 8840 was ready and idle.
Native Voice, TTS and ASR also reported ready.

## Managed launch with the production receipt

The later [grouped INT4 campaign](../benchmarks/halogen0207-publisher-gap-and-i4r-20261123.md)
used this receipt in all four launches. The launch intents and authenticated
readiness records use Windows UTC timestamps. Their elapsed times include
preflight, model loading and API readiness. The private stock controls
took **152.38 s** and **150.67 s**. The private grouping trial took **154.08 s**.
The ordinary service on port 8840 took **162.43 s** and remained online.

All four manifests selected `ntfs_receipt` for the exact same source
generation. The earlier **706.05 s** observation covered only full WSL
content verification. The retained records give actual startup durations
with receipt reuse. A matched complete launch with forced rehash is outside
this comparison.

| Local evidence | SHA-256 |
| --- | --- |
| HIP build receipt | `da60a75b89cadc9e7d55b81c5c6d52fd0ce99f8769fd76b2e1debc2de6f8be87` |
| Terminal device arm with Halogen loaded | `8461aee67bef69288dbff712f22e5d07515994f307f6a25ae6ef45edf9a9f480` |
| Terminal device arm with Halogen unloaded | `51d7ada191dd2a226e101e7911ec3622733fef204153db827826c254b9f1037f` |
| Terminal device arm with stock container flags | `635c0b4c2a542bf45143b1efcda6e1595cc3dc8e79d8b5a60542b8ebe9392071` |
| Native NTFS witness smoke | `b7eec1aa4a2420ac4e4de749f72e9f84e91fe9e1cb5d7e2d6f0da4f8b8ad10ab` |
| Cross-namespace synthetic receipt smoke | `4929e5a9818ac38dbc679ff9e5c1bae24b69db0ef760b6f08e0fafd17f9a79af` |
| Read-only container-bind smoke | `855af54ca6e1b46113900d4c79167c7e44edfaa3991c9e243dd2550e66e901aa` |
| Production direct-read terminal record | `a6226d39af29bcc637ad7fc0d9f55c13b1be0baf767f7322c119bbc3a397afe0` |
| Managed NTFS production receipt | `ea343d0c8c61a94fa12e3bba84d117a22dad25302f2c1ab0c6639899a7b88a97` |
| Managed production receipt reuse verification | `61538db37489042bad46f709038e592b3d5d24547a9a78d4513d8ff1c861dd5a` |
| Serving status after receipt verification | `7edc46693dbd84e231a8c1d4a67fd9004317a4e98aa3c9bae526d0aaff782493` |
| Four managed launch observations and manifest bindings | `21ff7108f4ab0b8bde1fa4fd08f325f9b14eb3783cc6efa430f4f8dd92bc70e7` |
| Managed synthetic seed, reuse and mount gate | `8deadb3765d4977fc40d174a92a857e5b8eea1411a60722eec4b2beb0c65b81c` |
| Passive production NTFS metadata check | `8b4d8b3ed9db1bb5cc868c1d1e8756ab9dbd793c17299596e12d85fca459476e` |

## Targeted reads before a known request

The current 0.20.7 CPU lookup code computes 16 rows per token from the
current token ID and the two preceding IDs. A frozen 2,048-token prefix
produced 32,768 visits and 5,352 unique rows. The plan covers 5,516
distinct 4 KiB pages on the native ext4 table, or 21.55 MiB. This is the
planned file-page footprint. Filesystem read-ahead may add I/O.

On the verified ext4 inode, all 5,516 planned pages initially reported
nonresident in a read-free `mincore` sweep. A bounded test then sampled
128 of those offsets across the file. It read **512 KiB** using
`pread` in **58.99 ms** of guest wall time, including the reader's
checks. All 128 pages reported resident afterward. A separate disposable
ext4 fixture demonstrated that the same reader skipped the pages on its
second pass. The model table and ordinary server configuration were
preserved.

This component test used the ext4 inode outside the serving container.
The regular Halogen process maps its NTFS lookup source. The reader's
NTFS mode validates only the page plan. The private ext4 trial below
checks the engine's actual mapping and the residency of a known request.

The bounded reader, offline calculations and raw receipts are under
`server/.local/halogen-update-20261122/primary0207/ngram-prearrival-pages-prep-v1`.

| Evidence | SHA-256 |
| --- | --- |
| Current native row formula | `42f6f92e30a4749a6987dc180494bf41625c73e5ce1d10f8df40e7471a91e16f` |
| Frozen prefix page plan | `6203c4945df547021f4f89ffc017322a8a350895946e590219cbce3b2f9365d0` |
| Disposable ext4 syscall proof | `19a9b59a5f6ab3646cc7f3b0a43f1db919aa86c065604be11c6b81190e7b9155` |
| Full plan residency sweep | `f1d113a3da6553baa063faaffddb455a7673a47b1bc15c657b3a7756c6453eb3` |
| Canonical ext4 128-page read | `532157385eb26d771dabcde9695235f6d1b9de3ab6577f867933538759ac55d9` |

## Engine-mapped ext4 cold control

A private Halogen 0.20.7 instance mapped the pinned 47.68 GiB N-Gram
table through an exact read-only ext4 bind. The guest verified the
engine's mapping for all 34,916 pages of the first frozen request.
Immediately before dispatch, **34,711 pages (99.41%) were nonresident**.
The reader observed residency in **1.95 s** of guest time and performed
zero payload reads. The Windows observation took **2.79 s**. The gap
from the end of that observation to HTTP dispatch was **0.149 s**.

The non-streaming Responses API returned the expected answer `23` for
the first 2,329-token *War and Peace* input. Greedy MTP, Cache Off and
zero reused prompt tokens were observed. These are the rates from this
one control request, without preload.

| Input tokens | Output tokens | Prefill tok/s | Decode tok/s | MTP accepted / proposed | HTTP wall |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 2,329 | 3 | 959.90 | 63.16 | 2 / 2 | 2.311 s |

The collector had required intermediate prefill progress lines for every
request. This prompt fit within one 8,192-token chunk and emitted a
native completion and Responses POST without an intermediate progress
line. The collector stopped after that response and closed the guest
staging directory. The revised collector replayed the original log bytes,
HTTP response and gateway counters, and matched the request to one
native completion. The subsequent host-only residency check found
**34,916 of 34,916** control pages resident. The other seven plans still
had at least 90.4% of pages missing. The prescribed four pairs and warm
repeats therefore have no qualified effect estimate. TTFT and NPU token
rate change are unmeasured.

In a CPU-only test using the same image and WSL kernel, the read-only file
belonged to UID 1000. That UID received `EACCES` on the root child's process
mapping and mount namespace. The image's existing root credentials
could prove the mapping and report a cold page accurately. A single
4 KiB read changed the selected page from absent to resident while the
last page stayed absent. The private reader used those existing rights
and checked them again inside each operation. The regular Halogen
server on port 8840, Native Voice, ASR and TTS were verified ready after
the trial.

| Local evidence | SHA-256 |
| --- | --- |
| Same-image CPU-only permission and residency check | `51c9fa67353690bab1aa0e8c5c853fd6d65a6b37e1deb26870095804a308e9a3` |
| Private guest and runtime binding | `059124e469038346094be98950be5637e2837ab82589614f82f88162f2f7e9cb` |
| Full cold residency observation | `afe73053d5bddcfc1b932b5633d3a70b5fc966b578364ab4ccf88147d264f678` |
| HTTP clock and gateway counts | `2affda4e7f8b857c7a3199b926fc02ac7afbe2b47a1a1fc3bc0695546d037936` |
| API response | `55d7c5ff2032d128d7d780e45b05a73007773b1ee0fb88cd8ba89061f94ea32f` |
| Independent native completion | `2597d2878c4f953ceb18db782ba81ee6b01519466ad037280481fb3b874c84ef` |
| Host file residency after the request | `f686395eea88aaa91c94bdba4fd6320f5c926dd4e1cb540b3f62fa3c1c4858f8` |
| Regular Halogen readiness | `882c687776ac52feef6fb4c27e6b1bb2c09de4c08a2d3f261b135d54d30752ba` |
