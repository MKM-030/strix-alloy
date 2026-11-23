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

The production path still verifies the whole file when its WSL identity
changes. A production receipt would first have to bind the full pinned digest
to the native Windows generation under a read lease and verify the fresh guest
identity at the actual read-only container mount before model startup. The old
Linux-only receipt is insufficient for that shortcut. This addresses repeat
startup time. It has no demonstrated effect on Prefill, Decode or MTP acceptance.

The normal service returned to port 8840. The gateway, TTS, ASR and Native
reported ready, and the allocation probe exited.

| Local evidence | SHA-256 |
| --- | --- |
| HIP build receipt | `da60a75b89cadc9e7d55b81c5c6d52fd0ce99f8769fd76b2e1debc2de6f8be87` |
| Terminal device arm with Halogen loaded | `8461aee67bef69288dbff712f22e5d07515994f307f6a25ae6ef45edf9a9f480` |
| Terminal device arm with Halogen unloaded | `51d7ada191dd2a226e101e7911ec3622733fef204153db827826c254b9f1037f` |
| Terminal device arm with stock container flags | `635c0b4c2a542bf45143b1efcda6e1595cc3dc8e79d8b5a60542b8ebe9392071` |
| Native NTFS witness smoke | `b7eec1aa4a2420ac4e4de749f72e9f84e91fe9e1cb5d7e2d6f0da4f8b8ad10ab` |
| Cross-namespace synthetic receipt smoke | `4929e5a9818ac38dbc679ff9e5c1bae24b69db0ef760b6f08e0fafd17f9a79af` |
| Read-only container-bind smoke | `855af54ca6e1b46113900d4c79167c7e44edfaa3991c9e243dd2550e66e901aa` |
