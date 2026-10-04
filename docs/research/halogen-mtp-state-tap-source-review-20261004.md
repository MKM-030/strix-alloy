# Halogen 0.16.2 host-only MTP state observer: source review

The separate source `scripts/benchmarks/halogen0162_mtp_state_tap.c` implements an eight-call host metadata observer for complete MTP forward entry. The existing full-event tap and launcher are unchanged. Root reports a warning-free build with `-O2 -Wall -Wextra -Werror -fno-optimize-sibling-calls` and full objdump review confirming the four native arguments are retained and the call is not a tail call. The fixed SO is `/home/revn/halogen-re/mtp-state-tap-20261004.so`, SHA-256 `f65a557b62e2bfac5d4ba349b8a4b31f2153a927196acb2fb68206bf68697dd6`; source SHA-256 remains `bcfe3a3448eac9d5001e9cc5a5b053e01ccbdbe108cd3f3764573378ffa04789`.

The separate launcher `scripts/benchmarks/halogen0162_mtp_state_tap_launcher.py` and ignored coordinator `server/.local/mtp-state-20261004/run_mtp_state_capture.py` are now prepared as source. Launch remains pending root review and an exclusive admitted hardware window. This source task performed no compilation, tests, launch, model/checkpoint read, device payload copy, HIP synchronization, or native model-state write.

## Root-only build and control contract

From the repository root in the owned Linux build environment:

```sh
gcc -O2 -Wall -Wextra -Werror -shared -fPIC -fno-optimize-sibling-calls \
  scripts/benchmarks/halogen0162_mtp_state_tap.c \
  -ldl -lcrypto -pthread -o /home/revn/halogen-re/mtp-state-tap-20261004.so
sha256sum scripts/benchmarks/halogen0162_mtp_state_tap.c /home/revn/halogen-re/mtp-state-tap-20261004.so
```

Root owns any further build or launch. The observer is a separate `LD_PRELOAD` artifact. Do not combine it with the full-event tap: both hook the same native full-forward entry.

The coordinator has a static preparation path that imports no service, runtime, telemetry, providers, or model readers and starts no process. It writes a fresh UUID plan directory and requires the exact root SO binding even during preparation:

```powershell
& C:\Projects\strix-alloy-clean\server\.local\venv\Scripts\python.exe -B `
  C:\Projects\strix-alloy-clean\server\.local\mtp-state-20261004\run_mtp_state_capture.py `
  --prepare-only --tap-so-sha256 f65a557b62e2bfac5d4ba349b8a4b31f2153a927196acb2fb68206bf68697dd6
```

The live path retains the native interpreter from the pinned venv so `Popen.pid` remains the original controller PID. Only `service.build_manifest` is patched. The launch fixes v2, capacity262144, cacheOff, draft depth2, reserve18 GiB, and the original request/input/output hashes. The `mtp_state_tap` manifest binds the source, SO, launcher, engine, function/wrapper hashes, read-only mount, state environment, five-file/65,536-byte trace bounds, and exact triggers. Startup, source/ownership, direct-memory monitoring, output parity, normal stop, and cleanup/recovery guards are retained from the frozen coordinator. Export requires eight complete valid metadata records and performs no event calculations or device payload processing. This preparation command and both new Python files have not been executed or tested by this source task.

Configuration is `HALOGEN_MTP_STATE_TAP=state8-v1` and `HALOGEN_MTP_STATE_TAP_DIR=/tmp/alloy-mtp-state-tap-<32 lowercase hex digits>`. The directory must not already exist; the serving process exclusively creates it with mode 0700. `HALOGEN_MTP_STATE_TAP_FD_ROWS` is absent or `none` for no raw descriptor copy; `copy160-v1` enables the optional copy. Other values fail the constructor guard.

The constructor writes `activation.json`, exclusively opens and retains the process-owned `records.json` fd, and starts a host harvest worker. The launcher must wait for successful serving-process startup and activation, then create the exclusive regular file `armed` containing exactly `state8-v1-ready\n`. After the selected request has returned, it must create the exclusive regular file `harvest` containing exactly `state8-v1-harvest\n`. The files must be owned by the serving uid and have one link. Content, inode, device, size, and mtime are checked before and after each trigger read. No trigger or record writes occur within sampled native calls.

The worker freezes new reservations, waits for sampled native host calls to return using a host condition variable, writes `records.json` through its retained fd, fsyncs/closes it, and exclusively writes `complete.json`. It does not synchronize HIP. Harvest expires after approximately 30 minutes without a trigger; absent completion is a failed observation. The total artifact contract is five files and 65,536 bytes, including the two triggers. The launcher must retain and check `complete.json`, entry-valid flags, sample errors, source/SO pins, request parity, cleanup, and response/harvest ordering before interpreting records.

## Observation and identity guards

- Eight preallocated samples, selected only for armed ABI `count == 1`. Other counts and calls beyond the limit are counted and execute unchanged. Samples retain ABI count/position, return RVA, native result, and completion flags; no latency is measured.
- Entry host reads include model byte `+0xa4`, int32 `+0xa0` and `+0x220`, and raw pointer presence/value at `+0x108`. The `model+0x108` pointee is never followed.
- Native table begin/end are `model+0x4d8/+0x4e0`. Retained disassembly `0x176ecd1..0x176ece6` subtracts these fields to obtain descriptor count; the allocation loop advances `0xc68` at `0x176ed2d` and tests layer index48 at `0x176ed3d`. The observer requires a nonnull, ordered range whose length is divisible by `0xc68` and contains at least 49 descriptors, then validates the readable host span `49*0xc68` before reading L48.
- L48 byte kind and raw pointer fields `+0xb98`, `+0xba0`, `+0x4f8`, and `+0x500` are recorded. Field-offset labels remain valid metadata for any kind; their interpretation as K/V/compressed-key/carry history is conditional on observed kind1. The observer never follows these pointer values.
- Full-head TLS counts kernel launches, nondefault streams, scatter identity `base+0x18d5338`, and FD attention identities `base+0x18d5348/+0x18d5350`. Optional raw capture additionally requires native launch return RVA `0x17a0b70`, a readable three-pointer argument array, and readable 160-byte `args[2]` host object. It attempts one copy per selected call, before forwarding the identical launch arguments. Any embedded pointers remain raw bytes. Multiple launches are counted; no further descriptor is copied.
- Engine SHA-256 `ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b`, exact 26,052,768-byte size, full-forward hash `132f2da76d86694ffe5f120d61e304e57c685f3db72935c6d5e61bf7b0d5cc20`, and wrapper hash `2c6dc2832f047253b7459303253da0199e35c6944afb629f381b42d47c986892` are retained. The constructor verifies ELF64 little-endian x86-64 ET_DYN identity, file consistency, PT_LOAD RVA/file-offset correspondence, full-forward and wrapper signatures, and kernel identity readable span.
- Only the full-forward text is hooked. Its complete first five instruction bytes are relocated through a near RW-to-RX trampoline. The wrapper is verified and remains unhooked. Pinned full-forward return RVAs remain `0x17dcc08`, `0x17dcd54`, `0x17dcf49`, and `0x17de236`.
- Original full-forward and `hipLaunchKernel` arguments and return values are forwarded unchanged. Incoming errno is restored before native execution and native result errno before returning. Invalid observation spans disable future reservations while native execution continues. Nested full-forward calls execute with outer TLS observation suspended and invalidate the enclosing observation; samples cannot be reused or exported while in flight.

The `/proc/self/maps` check is a conservative readable-mapping guard, not a pin against concurrent host allocation changes. No independent allocation lifetime or concurrency contract is established. Root's reported build/objdump review establishes compilation and emitted call behavior for its exact SO; runtime observation remains pending. Static source inspection is not runtime verification.

## Interpretation limits

The run is separately instrumented. Request-time `/proc` reads, mutexes, TLS, and metadata copies have unmeasured overhead; no performance conclusion follows. Missing scatter/FD attention kernels must be considered with observed L48 kind and entry scatter flag. Absence alone does not establish contiguous ownership. Raw `FdRows` bytes establish observed host argument metadata, not FD slot ownership or lifetime.

The accepted residual snapshot does not cover separate layer48 K/V and compressed-key histories. The carry snapshot covers only 768 bytes. Accepted-prefix helper `0x17def00` iterates target layers0–47; layer48 commit/discard and FD slot lifetime remain unresolved. Future NPU draft integration still needs isolated mutable head state, a position contract, accepted-prefix commit, rejected-suffix discard, and native target verification. Approximate internal draft arithmetic is allowed; exact internal FP32 parity is not a production gate. This source observer establishes none of those rollback contracts.
