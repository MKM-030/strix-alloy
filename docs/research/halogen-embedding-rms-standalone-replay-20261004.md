# Original embedding RMS replay preparation

The new host source
[halogen0162_embedding_rms_replay.c](../../scripts/benchmarks/halogen0162_embedding_rms_replay.c)
replays two fixed embedding RMS calls through the original retained Halogen
0.16.2 shader. Host compilation and CPU fixture preparation have completed.
Original GPU execution, numerical comparison and NPU qualification remain for
root's exclusive guarded window.
Existing hidden RMS and FC sources and their receipts are unchanged.

Retained host disassembly at `0x17db475..0x17db517` loads the embedding row
from `model+0x6c8` and raw norm weights from `model+0xae8`. Instructions
`0x17db483` and `0x17db48d` put the same embedding pointer in the input and
output argument slots. `0x17db492` supplies width `0xa00` (2560), and
`0x17db49a` supplies groups 1. Configuration registers established at
`0x17db38f..0x17db3a0` give one block of 256 workitems for count1. The call
at `0x17db468` supplies zero dynamic shared memory and the default stream;
the exact launch returns at `0x17db51c`.

The replay preserves this input/output alias, with one 5120-byte device tensor
and one 5120-byte raw gamma buffer. For each A/B call it copies input and gamma
to the device, launches the original kernel once, synchronizes once and copies
5120 output bytes back. It never poisons the aliased device buffer: doing so
would destroy the input. Host output poison is overwritten by the complete
device-to-host copy. Numerical validity still requires comparison with the
separate frozen CPU and native reference receipts.

| Contract | Exact value |
|---|---|
| Kernel | `_ZN7halogen12_GLOBAL__N_117k_rmsnorm_groupedEPKtS2_Ptii` |
| Host identity / registration | `0x18d5160` / `0x1848906` |
| GPU entry / descriptor | `0x22d200` / `0x1f6cc0` |
| Width / groups | 2560 / 1 |
| Grid / block | `[1,1,1]` / `[256,1,1]` |
| Dynamic / static LDS | 0 / 1024 bytes |
| Wave size | 32 |
| Kernarg size / alignment | 288 / 8 bytes, hidden ABI4 arguments supplied by HIP |
| Public arguments | X, raw gamma, Y pointers at offsets 0/8/16; i32 width/groups at 24/28 |
| X/Y pointers | Same device allocation, matching the original embedding launch |
| Input / gamma / output | 2560 little-endian BF16 words, 5120 bytes each |

The exact retained disassembly has SHA256
`dbd3c9ea1e560f13aad9156fb7867bfe441872b8591ee87b6fc2d15d1b2bba95`.
It shows raw BF16 widening, strided FP32 square FMA partials and LDS pairwise
reduction. The mean divides by the public width argument, adds epsilon bits
`0x358637bd`, and uses the native `v_rsq_f32` path. Raw BF16 gamma is widened
and then incremented by 1 in FP32 inside the shader. Two FP32 products precede
the BF16 round-to-nearest-even store. The host source copies all words unchanged
and implements none of this tensor arithmetic itself.

The shader has SHA256
`45941c0579dc3487d07978a50c85cbaa141bbb674b225e708e82d81397334a83`,
17704408 bytes, at offset `0x51000` in the 26052768-byte engine with SHA256
`ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b`.
The replay hashes the files and compares every shader byte with the original
engine payload. Engine, shader, installed HIP library and A/B input/gamma
identities and hashes are checked again after execution. Paths must be absolute
regular files and are opened without following final symlinks.

The CLI parallels the original hidden RMS replay, with 13 arguments after the
executable:

```text
replay ENGINE HSACO HIP_LIBRARY HIP_SHA A_INPUT A_INPUT_SHA A_GAMMA
  A_GAMMA_SHA B_INPUT B_INPUT_SHA B_GAMMA B_GAMMA_SHA NEW_OUTPUT_DIRECTORY
```

Successful execution requires exactly 2 launches, 2 synchronizations, 6 copies,
2 allocations/frees, 1 module load/unload and no cleanup or input-file errors.
The exclusive fresh directory receives `A-embedding-rms-u16.bin`,
`B-embedding-rms-u16.bin` and `replay.json`, schema
`halogen0162.embedding-rms-original-kernel-replay.v1`. The receipt binds each
input, raw gamma and output hash, exact dispatch and alias, immutable file
rechecks and output writes. The root controller's process exit and cleanup
receipt remain authoritative if closing or persisting the report fails.
Every copied output is retained even if the finite-output check or hashing
fails; such a replay remains failed. An output that was never copied is not
written from its initialized host buffer.

Root owns fixture provenance, compilation and all runtime work. Use the pinned
Linux image and the original installed HIP library/DXG bridge, under exclusive
GPU ownership, 22 GiB admission, continuous 18 GiB physical and commit reserve
and a bounded owned process/container deadline. The source needs no model mount,
table payload, engine server, provider or NPU session. This preparation supplies
no full-D/head/verifier integration, acceptance improvement or speed claim.
