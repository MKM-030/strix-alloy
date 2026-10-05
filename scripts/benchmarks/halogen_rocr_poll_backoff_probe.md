# Minimal ROCR component qualification window

Root owns admission, builds, hardware, retained process/container handles, deadline, cleanup, and the colleague service. The probe does not acquire a window or operate Docker. Reuse the reviewed ownership/reserve mechanics in `halogen0162_embedding_rms_owned_run.py`; do not invoke that controller, because its stopped-user-controller check is incompatible with preserving the existing colleague service.

Use exactly three small windows, with no model mount or new large engine:

1. `stock`: the exact installed/exported HSA library, SHA256 `1961df7d395b62d9b7c0086e0a247a02d0e97129eb9d8b28acb0e0a597e819f5`.
2. `source_stock`: an unpatched source build at SDK source pin `2b22ab0195cc1461cd9abf3b969e9dd7c10af350`, made with the same compiler, dependency inputs, build flags and layout as the candidate. Supply its independently computed SHA256.
3. `candidate`: that same source build with only the narrow PR #7898 backport. Supply its independently computed SHA256.

Root retains matching source/build/patch metadata in outer receipts. Only `source_stock` versus `candidate` can isolate this patch from build differences. `stock` versus `candidate` measures the whole private build's difference from the installed runtime.

Before each window, confirm actual process/session/agent handles, no active inference request or competing GPU/NPU work, and at least 22 GiB admission headroom. Continuously retain at least 18 GiB physical and commit headroom. Preserve the colleague process and all global runtime, WSL, driver and model settings. An unavailable measurement window is not resolved by killing or modifying another service.

## Fixed probe contents

The pure Python probe needs no new probe compilation. It validates its independent source SHA and each input before loading exact HSA and HIP paths. After GPU initialization and module loading, it verifies the SHA256 of the actually mapped HSA, HIP and DXG bridge using `/proc/self/maps`; it repeats those checks before exiting.

- Original embedded Halogen codeobject and original `k_rmsnorm_grouped` symbol, unchanged.
- Frozen width 2560/group 1 A/B inputs and raw BF16 gamma from the existing embedding RMS fixture directory.
- Original in-place input/output alias; grid 1, block 256, shared bytes 0, default stream.
- Eight warmups and 64 timed repetitions per fixture. Restore frozen input before each repetition. Timing is wall time for launch plus synchronization; upload/readback are excluded. All repeated BF16 outputs must match exactly and remain finite.
- One 10-second idle CPU bracket after the replay.
- One 10-second idle CPU bracket with a deliberately pending same-process IPC signal/async EQ0 handler. IPC attribute 2 permits CPU consumption and forces `DefaultSignal` at the exact SDK pin. The public value-pointer API confirms `BusyWaitSignal::IsType`; the returned pointer is never dereferenced. This is a polling diagnostic, not a claim that Halogen uses IPC signals.
- Complete the pending signal once, retain the Python callback, record its single observed wake latency, return false from the callback, and destroy the signal. That single latency includes Python callback entry and is informational.
- Free the two tiny GPU buffers, unload the original module, release the owned HSA reference, and report cleanup failures. The process exits after reporting. Failure to write the receipt preserves the full original error/cleanup receipt in stderr and exits unsuccessfully.

The ctypes callback remains rooted for the process lifetime. If a registered callback remains unconfirmed after the two bounded observation waits, skip signal/GPU/module/HSA teardown, write a failed cleanup receipt, and exit with `os._exit(1)` so Python finalization cannot free its trampoline. Root still closes the retained owned container/job. Offline comparison rejects missing, extra, duplicated or reordered A/B timing rows and either fixed idle label.

Each run should fit within about 21 seconds plus initialization/replay overhead. Use the existing outer timeout style with an explicit 60-second deadline and 5-second kill grace; a timeout fails the window rather than initiating a retry.

## Exact image, mounts, and environment

Pinned image:

```text
ghcr.io/peonist-ai/halogen-flash-server@sha256:0c61bf84ac22308a53f5d1ca6b86806702d7039e5ebc51cae4c66621b92fe04a
```

Keep the container read-only, network none, restart no, memory/memory-swap 2 GiB, pids 128, IPC private, shm 64 MiB, core limit 0, memlock unlimited, existing reviewed security options, and tmpfs `/tmp` 64 MiB. Use exact UUID name/label ownership and a new empty result directory for every run. Retain container ID and Windows `OwnedProcess` job identity before starting. Stop/remove only that verified owned ID and close only that owned job afterward.

Read-only mounts for all three runs (Linux source paths obtained by the existing `backend.linux_path` for Windows files):

| Container destination | Source |
| --- | --- |
| `/candidate/probe.py` | `scripts/benchmarks/halogen_rocr_poll_backoff_probe.py` |
| `/candidate/flash_serve` | `backends/halogen-wsl2-0.16.2/.local/flash_serve` (read only, never executed) |
| `/candidate/engine-gfx1151.hsaco` | `server/.local/optimization9h-20261004/mtp-route-static-20261004/engine-gfx1151.hsaco` |
| `/fixtures` | `server/.local/optimization9h-20261004/embedding-rms-fixtures-78c49b8e265c4de9adb9c0cf3cc8254e` |
| `/usr/lib/libdxcore.so` | `/usr/lib/wsl/lib/libdxcore.so` |
| `/usr/lib/librocdxg.so` | Existing pinned `backend.MACHINE['dxg']` |
| `/usr/local/lib/python3.12/site-packages/_rocm_sdk_libraries/lib/librocroller.so.1` | Existing pinned `.local/librocroller-compat.so.1` |
| `/usr/local/lib/python3.12/site-packages/_rocm_sdk_core/lib/libhsa-runtime64.so.1` | Independently hashed stock, source-stock or candidate regular library file |

Only `/result` is a writable bind mount. Expose `/dev/dxg`; no model/NPU asset mount is needed. All HSA variants replace only the same isolated SONAME path inside this container. They do not replace the installed host/WSL library or the colleague container's library.

Use the same environment for all runs:

```text
HSA_ENABLE_DXG_DETECTION=1
HSA_ENABLE_SDMA=1
HALOGEN_LQ8_WAVE=1
HSA_DISABLE_COREDUMP_ON_EXCEPTION=1
LD_LIBRARY_PATH=/usr/lib:/usr/local/lib/python3.12/site-packages/_rocm_sdk_core/lib:/usr/local/lib/python3.12/site-packages/_rocm_sdk_libraries/lib
```

Leave `HSA_WAIT_ANY_DEBUG` and `HSA_ENABLE_INTERRUPT` unset. The probe rejects changing their default path. Root records the source/patch/build identity in separate outer receipts and passes independent source/runtime SHA values as individual arguments, avoiding shell-built command strings.

Container entrypoint argument vector, after owned `docker create` options/mounts/env/image:

```text
--entrypoint=timeout IMAGE --signal=TERM --kill-after=5s 60s
python3 /candidate/probe.py probe
--variant stock|source_stock|candidate
--source-sha256 INDEPENDENT_FROZEN_PROBE_SHA256
--hsa-sha256 INDEPENDENT_VARIANT_LIBRARY_SHA256
--output /result
--outer-owned-gpu-guard
```

The guard flag acknowledges root's actual outer guard; it is not a replacement for one. Start using retained `OwnedProcess([wsl.exe, ..., 'docker', 'start', '-a', verified_cid])`. Retain stdout/stderr, terminal state, reserve trace, source/runtime SHA, and cleanup evidence.

## Offline comparison and decision

Run only these two offline comparisons after all three receipts pass:

```text
python scripts/benchmarks/halogen_rocr_poll_backoff_probe.py compare --stock ABSOLUTE_STOCK/probe.json --candidate ABSOLUTE_CANDIDATE/probe.json --output NEW_INSTALLED_COMPARISON.json
python scripts/benchmarks/halogen_rocr_poll_backoff_probe.py compare --stock ABSOLUTE_SOURCE_STOCK/probe.json --candidate ABSOLUTE_CANDIDATE/probe.json --output NEW_PATCH_COMPARISON.json
```

The comparison verifies shared frozen configuration/input hashes, retained exact BF16 output hashes, and prints launch/synchronization medians/p95, both idle CPU brackets, and the single callback latency. A discrepancy or cleanup/timeout failure rejects qualification; preserve the receipts and do not silently adjust arithmetic, tolerance, workload or runtime settings.

Root decides whether the matched source-build comparison shows reduced idle CPU with acceptable kernel/wake behavior. These small component results do not qualify prefill, decode, MTP acceptance or a speedup claim. Those require a subsequently admitted owned engine workload while preserving the colleague service and the reserve.

Prepared offline only: no container, library, hardware, provider, build or model execution was performed while writing this probe and plan.
