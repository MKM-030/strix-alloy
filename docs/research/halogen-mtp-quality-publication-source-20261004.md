# Native complete-MLP quality publication: source receipt

The new `scripts/benchmarks/halogen0162_mtp_quality_publish.c` implements a
bounded complete-MLP publication seam for an explicitly supplied candidate.
It reuses the reviewed exact-version five-byte detour pattern in the existing
route tap, whose source remains unchanged. This preparation has **not** built
or loaded the shim, launched Halogen/WSL, initialized a provider, copied a real
device tensor, or measured acceptance. The eight packet checks use only
stdlib Python and synthetic bytes.

The seam calls the original MLP exactly once, then optionally replaces
`*(model+0x6d8)` before the dispatcher invokes HC combine at `0x17da3f7`.
The candidate must be a **complete** routed-plus-shared MLP result, BF16[2560],
not the routed output alone. Attention, HC, full-head continuation, vocabulary
projection, head histories, the controller and target verification remain
native. This is a short path to eventual output/acceptance qualification,
not full NPU MTP or a speed measurement: native MLP also executes.

## Exact source contract

- New C source: `scripts/benchmarks/halogen0162_mtp_quality_publish.c`.
- New packet utility: `scripts/benchmarks/halogen_mtp_quality_wire.py`.
- Checks: `scripts/benchmarks/tests/test_halogen_mtp_quality_wire.py`.
- C source SHA256:
  `91fead8839c6135ec45b7b47032b3b7c0a5c0812bbac3fedbad0d30a17bd445d`.
- Packet utility SHA256:
  `77e9cc365ce850faa2bbb98a490fe98dd5a50b0210be61bd0a2372c971ce71de`.
- Checks SHA256:
  `37319d8554dce59bb9d2e2be65b2167cdc63d3b2e649ba0f09bce635b9393bac`.
- Engine SHA256:
  `ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b`.
- MLP RVA `0x17bd410`, file offset `0x17bc410`, extent ending `0x17ca056`,
  function SHA256
  `e318b4639c8bd2e57d66b12b823fcafc1f5c5a5136e3651c06e2bac54e46c717`.
- Known callers `0x17da361`/`0x17da2e9`; scope is layer48/count1/kind1,
  MTP enabled, nonnegative position/slot and one serial owned request.
- Input `*(model+0x6e8)`, complete output `*(model+0x6d8)`, each 5120 bytes.
  Native IDs from global `0x18db400`, coefficients from `0x18db3e0`,
  ten int32/FP32 entries each. Pointer separation and unchanged entry/exit
  fields are checked. The actual numeric profile here is BF16 MLP storage;
  this does not establish the full-head residual's numeric interpretation.

Absent `HALOGEN_MTP_QUALITY`, the constructor returns before installing any
detour. The explicit mode is `HALOGEN_MTP_QUALITY=quality4-v1`, with a fresh
`HALOGEN_MTP_QUALITY_DIR=/tmp/alloy-mtp-quality-<32 lowercase hex digits>`.
The shim exclusively creates that directory. It additionally requires the
regular `armed` file to contain exactly `quality4-v1-ready\n`. Only a valid
response permits a device-output write. Four matching calls are the hard
sample cap. The response wait has a 200-ms cooperative deadline with 10-ms
polls; filesystem/scheduler delay and original HIP work require the root's
external hard deadline. With all responses absent, at most four waits occur.

## File protocol and failure behavior

Requests are named `000-request.bin` through `003-request.bin`; responses use
the same sequence plus `-response.bin`. Each request is 10400 bytes; each
response is 5232 bytes. Four complete pairs total 62528 bytes, plus arm,
activation and bounded result lines. The shim allocates one request and one
response on the stack (15632 bytes); no weights or provider objects are held.

The little-endian 80-byte header is `<8sIIiiiI16s32s>`: magic, version 1,
body bytes, sequence, position, slot, reserved 0, run UUID bytes and request
binding SHA256. Request magic is `HGNMLPQ1`, response `HGNMLPR1`.
The 10320-byte request body contains input BF16[2560], native IDs int32[10],
native coefficients FP32[10] and the saved original complete output
BF16[2560]. Binding SHA256 covers the first 48 header bytes plus that body.
The response retains the exact identity/binding fields, carries 5120 candidate
bytes, and ends with SHA256 of its full header plus candidate. Responses
from another sequence, position, slot, run or input are refused. All packets
have exact sizes; nonfinite BF16/coefficients and invalid/duplicate IDs fail.

Request publication uses a synced exclusive temporary and Linux
`renameat2(RENAME_NOREPLACE)`; response publication uses a synced temporary
and an atomic hard link that refuses an existing final response. The Python
helper then removes the temporary. The C reader treats the brief two-link
publication interval as pending. Regular-file ownership, one-link final
state, unchanged fstat identity/timestamps, `O_NOFOLLOW` and fixed reads
reject replaced, partial or malformed packets. A filesystem lacking the
required atomic operations fails without publishing a usable candidate.

No device write occurs until the entire response is validated. Capture,
request-write, timeout, invalid response and IPC failures retain the original
MLP output. Malformed/capture failures disable further publication. A
successful response is copied H2D to the same complete-output pointer and
synchronized. If that publication fails, the saved original output is copied
back and synchronized; a failed restore terminates the owned process with
exit 79 rather than continuing with ambiguous device state. Publication is
intrusive and cannot be used for throughput claims.

The helper consumes an explicit candidate; it performs no computation:

```text
python scripts/benchmarks/halogen_mtp_quality_wire.py \
  --request <owned-visible-directory>/000-request.bin \
  --candidate-output-u16 <explicit-complete-MLP-output.bin>
```

The request directory is inside the serving process/container namespace.
Root must establish a controlled coordinator path to it and qualify the
owner/visibility/atomic-operation behavior before arming. `/tmp` is not
automatically a Windows-accessible shared directory. No cross-WSL transport
or persistent Windows NPU responder has been launched or qualified here.

## Minimal verification and next gates

`python scripts/benchmarks/tests/test_halogen_mtp_quality_wire.py` passes 8
checks: exact roundtrip, stale sequence/position/slot/run, corrupted packets,
nonfinite candidate, wrong sizes, invalid request bounds, atomic overwrite
refusal with no partial leftovers, and invalid candidate creating no response.
The first six checks failed on the missing implementation before it was
created. These checks establish Python packet behavior only. C layout is
statically asserted to the same 80/10400/5232-byte contract and was reviewed
against the retained source; no C compilation or runtime claim follows.

Root's next build is a fresh owned `.so` with the command in the C header
(`-O2 -Wall -Wextra -Werror -shared -fPIC -fno-optimize-sibling-calls`,
`-ldl -lcrypto -pthread`). The shim must be the only detour on this MLP entry;
an already patched prologue fails installation. Root must pin the new sources
and build, enforce the existing 22-GiB admission/continuous 18-GiB reserves,
and retain cleanup/recovery receipts. Keep this source-only receipt unchanged
when adding a separate build or hardware receipt.

Remaining exact gates are C warning-clean build, root-owned absent/stale/
invalid-response and successful/failed-publication execution, coherent
namespace transport, real nonzero packed-QMoE output and routing/aggregation
semantics, shared contribution and final rounding, then matched greedy
acceptance/output with native verification. Native router inputs can differ
from a widened captured BF16 expert input; the packet deliberately retains
native selected IDs/coefficients. QMoE's 512-wide router interface still needs
proof of how to express those selected weights. No internal FP32 equality is
required for approximate drafts, but no acceptance improvement is established.
