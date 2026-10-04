# Original Halogen 0.16.2 count1 D FC dispatch

Static inspection identifies the original native Q8 kernels for the normalized
embedding and hidden FC boundaries of count1 wire D. It also exposes a numerical
boundary absent from the retained FP32 decoder/reference: the native shader
rounds each decoded affine Q8 weight to BF16 before its BF16 dot products.

This is a contract for the native normal store7 path with
`HALOGEN_LQ8_WAVE` absent or enabled as `1`, `K=N=2560`, and explicit wire D.
It does not establish which path a historical complete-head run executed.
No model payload, GPU, NPU, WSL, provider or engine was started for this audit.
Root owns the separate original-kernel replay, frozen inputs and qualification.

## Retained code and receipts

The static artifacts are under
`server/.local/optimization9h-20261004/mtp-route-static-20261004/`.
The following seals were independently rechecked on October 4 using local
PowerShell `Get-FileHash`; shader symbols and metadata were inspected using
Windows AMD LLVM `llvm-objdump` / `llvm-readobj`.

| Artifact | SHA256 |
|---|---|
| `backends/halogen-wsl2-0.16.2/.local/flash_serve` | `ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b` |
| `engine-gfx1151.hsaco` | `45941c0579dc3487d07978a50c85cbaa141bbb674b225e708e82d81397334a83` |
| `host-text-disassembly.txt` | `523467ac08e576e770a9fcffdb59ffa9542f82d58958bd03d74743f8caccb8f9` |
| `kernel-registrations.json` | `c38287607691b58e618fb5e1b9f31cb5150daa85d82ecc0d22ecd46171732c2f` |
| `cpu-d-input-static-audit.json` | `ece0f957bcd39016cf48398346475b5658a23c20bcdd8fa27319018c2de55be2` |
| `scripts/benchmarks/hgn_q8g64_slice.py` | `1bb7c274688d77f4d2181866cbebfd170e33031934aaeb32f43b0cdf73a65d23` |
| `C:/AI/halogen-mtp-npu/v2-d-prepare-20261004/weights.json` | `dbf679c94c75439638b01058c2c6915d43dd211c69b27918f7caa77d826e8fb7` |
| `docs/research/halogen-mtp-standalone-manifest-20261002.json` | `63f95c03fc06157f0ad1aa5a9f687ac8d760dff7b599f3e12e6db34e1947c031` |

The engine has 26,052,768 bytes. Its original gfx1151 raw code object has
17,704,408 bytes and begins at engine file offset `0x51000`, within the
`.hip_fatbin` at `0x50000`. The retained original fatbin registration binding is
described in [the hidden RMS replay audit](halogen-hidden-rms-standalone-replay-20261004.md).
The ELF is little-endian AMDGPU HSA ABI4 for gfx1151. Addresses below are native
host RVAs or GPU ELF symbol/instruction addresses, not process addresses.

## Weight descriptor and raw storage

The MTP loader constructs `mtp.fc_embedding.weight` at host `0x1777f80`
(name bytes at `0x36a19`) and calls `0x17daa10` at `0x1777fb5`; it copies the
returned descriptor into `model+0x908` at `0x1777fba..0x1778025`.
For `mtp.fc_hidden.weight`, the name bytes are at `0x1b342`, the call is
`0x177809f`, and the descriptor copy into `model+0x980` ends at `0x177810f`.

The lookup wrapper `0x17daa10` resolves the tensor, then calls the core loader
`0x17eefa0` at `0x17daa59`. The core clears descriptor offsets `0..0x6f`
at `0x17eefba..0x17eefdc`. Its normal storage dispatch reads tensor store at
`tensor+0x10` (`0x17ef41e`) and indexes the relative table at `0x45e7c`.
A bounded read of the index7 entry at engine offset `0x45e98` gives relative
offset 24,811,178 and target `0x17ef526`.

That store7 path checks the existing tensor data pointer at `tensor+0x8`,
innermost dimension divisible by 64, and pointer alignment of 16 bytes
(`0x17ef526..0x17ef550`). It checks the tensor byte count at `tensor+0x38`
against `(product(dims)*17)>>4` (`0x17ef556..0x17ef91e`). It then writes the
same pointer directly to `descriptor+0x10` at `0x17ef924` and returns.
No dequantization, transpose or repacking occurs on this descriptor path.
The competing descriptor fields `+0x00` and `+0x30` retain their cleared values
on this path. This proves the descriptor seam conditional on the normal
store7 route; it does not prove historical override configuration or upstream
checkpoint loading from a runtime trace.

Both retained FC entries are store7 / variant0, shape `[out=2560,in=2560]`.
Each row consists of 2,560 unsigned code bytes followed by 40 little-endian
FP16 `[scale,bias]` pairs, one pair per group of 64 columns:

`decoded[o,i] = FP32(code[o,i]) * FP32(scale[o,i/64]) + FP32(bias[o,i/64])`.

Row stride is `K + K/16 = 2720` bytes; each matrix occupies 6,963,200 bytes.
The shader independently uses stride `K+(K>>4)` and reads packed affine words
after the code plane, for example embedding GPU `0x2d12cc..0x2d1314`.
The existing Python decoder validates this extent and exposes the stored row
orientation. A native replay must supply the original raw bytes unchanged,
not the decoder's 26,214,400-byte FP32 matrix.

## Native head calls and order

The full native MTP head starts at host `0x17db310`. In the inspected wire-D
branch, the call order is gather, embedding RMS, embedding FC, whole-row hidden
RMS, hidden FC, then seed addition. The FC boundaries are:

| Boundary | Embedding | Hidden in explicit D |
|---|---|---|
| Host call site | `0x17db520..0x17db543` | `0x17db636..0x17db65e` |
| Dispatcher | `0x178cf90` | `0x178cf90` |
| Weight descriptor | `model+0x908` | `model+0x980` |
| Input pointer | `*(model+0x6c8)` after in-place RMS2560 | `*(base+0x18db210)` after whole-row RMS10240 |
| Output pointer | `*(model+0xb00)` | `*(base+0x18db228)` |
| Scalar registers | `ecx=N=2560`, `r8d=count`, `r9d=K=2560` | `ecx=N=2560`, `r8d=4*count`, `r9d=K=2560` |
| Count1 input/output | one contiguous row, 5,120 bytes each | four contiguous rows, 20,480 bytes each |

The `uint16_t` words at both boundaries are BF16, not FP16. Hidden RMS normalizes
the complete 10,240-element row before the FC interprets it as four contiguous
2,560-element streams and applies the same hidden matrix independently to each.
It is not four independently normalized rows. The earlier static RMS audit
retains epsilon, raw-gamma-plus-one and intermediate BF16 rounding evidence.

## Dispatcher and exact registered functions

Dispatcher `0x178cf90` first tries `0x17f8280` gated by descriptor `+0x30`,
then `0x17f8df0` gated by descriptor `+0x00`. It calls the Q8 wrapper
`0x17fd9a0` at `0x178d051`, gated by descriptor `+0x10`. This wrapper accepts
batches 1 through 8 and reads `HALOGEN_LQ8_WAVE` through helper `0x17f08c0`
(environment-name bytes at `0x39c3d`). The absent-value branch returns 1 at
`0x17f08e3`; a value of 0 selects scalar `k_linear_q8` instead.

For the enabled wave path with `K=N=2560`, the exact selected symbols are:

```text
embedding: _ZN7halogen12_GLOBAL__N_16k_lq8wILi1ELi16ELi1EEEvPKhPKtPtll
hidden:    _ZN7halogen12_GLOBAL__N_16k_lq8wILi4ELi16ELi1EEEvPKhPKtPtll
```

| Binding | Embedding `M=1` | Hidden `M=4` |
|---|---|---|
| Host wrapper route | `0x17fda0f -> 0x17fe4c5 -> 0x17febb3..0x17fec85` | `0x17fdd42 -> 0x17fe2f5 -> 0x17fea05..0x17fead7` |
| Identity load | `0x17fec7e` | `0x17fead0` |
| Registered host identity | `0x18d6690` | `0x18d66f0` |
| HIP registration call | `0x184b596` | `0x184b7be` |
| Name RVA | `0x262d0` | `0x1b8b1` |
| GPU function / size | `0x2d1200` / 1,660 bytes | `0x2d7800` / 2,360 bytes |
| GPU `.kd` / size | `0x1fa340` / 64 bytes | `0x1fa640` / 64 bytes |
| SGPR / VGPR metadata | 16 / 58 | 21 / 88 |

The unrelated wrapper at `0x17ff560` is Q6; it is not the Q8 route above.

For both calls, grid is `(ceil(N/16),1,1) = (160,1,1)`, block is
`(256,1,1)`, dynamic shared memory is zero and the stream is default stream 0.
The configuration push at `0x18d38f0` receives zero shared-memory and stream
arguments (`r8d/r9d=0`). The common launch at `0x17fdb8e..0x17fdb9b` calls
HIP launch stub `0x18d3810` and returns at `0x17fdba0`. The default stream
preserves the native stage ordering; this static observation is not a latency
measurement.

Both GPU metadata blocks have fixed LDS0, private0, maximum workgroup256,
wave32, kernarg40 bytes aligned to8, and **no hidden arguments**. Their five
public arguments are:

| Offset | Size | Argument |
|---|---|---|
| 0 | 8 | `const uint8_t *W` (raw Q8) |
| 8 | 8 | `const uint16_t *X` (BF16) |
| 16 | 8 | `uint16_t *Y` (BF16) |
| 24 | 8 | `int64_t K` |
| 32 | 8 | `int64_t N` |

HIP module `kernelParams` therefore supplies pointer-value addresses and two
64-bit scalar addresses. The hidden M4 template handles all four contiguous
streams in one launch; count1 does not require four hidden kernel launches.

## Arithmetic boundary recovered from original shaders

The embedding shader's affine dequantization at `0x2d13f4..0x2d146c` uses
`v_fma_mix_f32` with FP16 scale/bias and converted unsigned codes. The sequence
at `0x2d1474..0x2d16a4` rounds the resulting FP32 values to BF16 using bit16
and `0x7fff`, then packs their upper words. The dot products use
`v_dot2_f32_bf16` (`0x2d15e0..0x2d16c4`). Wave reductions use FP32 additions
at `0x2d17bc..0x2d1838`; output is rounded to BF16 and stored at
`0x2d1840..0x2d1870`, including `global_store_d16_hi_b16`.

The hidden shader has the same relevant arithmetic boundary: affine dequant
FMA at `0x2d7a9c..0x2d7b18`, BF16 weight-rounding beginning at `0x2d7b20`,
packed BF16 dot products and FP32 reductions, followed by BF16 RNE output
stores at `0x2d8080..0x2d812c`.

The retained NumPy/ORT reference decodes weights to FP32 and leaves them FP32
for its FC operation. Native weight rounding is therefore a concrete missing
boundary in that reference. FMA versus separate FP32 operations and the
original dot/reduction order also need to remain explicit. This finding alone
does not prove why the frozen seed screen failed or establish FC parity.
No tolerance, epsilon, gamma, reference arithmetic or frozen fixture was changed.

## Retained tensor-region metadata

The JSON preparation receipt binds the current full v2 checkpoint to:

| Receipt field | Identity |
|---|---|
| Checkpoint source | `/home/revn/halogen-models-native/qwen38-flash-next-v2.hgn` |
| Checkpoint bytes | 66,687,678,432 |
| Checkpoint SHA256 | `71246c6ab3fc1de2cf06326f18e275fe9c2a18366d646ed3357d194c884fc687` |
| Prepared plan SHA256 | `850341ce237de0d48e995af5b0c3f913ad23369b2ddd99c25231b10ff156fe36` |
| Metadata receipt SHA256 | `4159d1ddb9094907ba82b62940777317d9bc89e4c7a8cb881809ecb17912e3cb` |
| Header SHA256 | `9e522122a6deedf7f966108b1902939d376126f4888c28ec183f3f6460a937c7` |
| Table SHA256 | `2302900dfe860fd7a689c90bdf1d3fe674d78aa8bf3c166e05000c9d5e5e9ceb` |

| Full-checkpoint tensor | Offset | Raw bytes | xor32 | Store / variant / dims |
|---|---:|---:|---:|---|
| `mtp.fc_embedding.weight` | 65,164,116,864 | 6,963,200 | 2,728,841,776 | 7 / 0 / `[2560,2560]` |
| `mtp.fc_hidden.weight` | 65,171,080,064 | 6,963,200 | 3,727,055,716 | 7 / 0 / `[2560,2560]` |

The older standalone v2 manifest describes the same named geometry at offsets
5,120 (embedding) and 6,968,320 (hidden), and retains raw SHA256s
`ec6ac9d2e6111b3cf9df7cc408afd555cd33ac291e5613d4000d58cd8a51107d` and
`018511894df3996e3a2fcb1dff60860c45a808b65036fd38db472b6e985bdd3f` respectively.
Those are receipt values, not newly rehashed payloads. Standalone offsets must
not be applied to the full checkpoint, and this v2 manifest is not the w4b model.
The current full-checkpoint preparation receipt also retains raw-range hashes
for four chunks per FC (819/819/819/103 rows), which root can use to bind a
separate bounded raw extraction.

## Original FC replay scope

The peer-authored [FC replay source](../../scripts/benchmarks/halogen0162_fc_replay.c)
uses these exact M1/M4 functions and ABI for four calls: A embedding, A hidden,
B embedding, B hidden. It copies two original raw Q8 matrices unchanged and
consumes explicit normalized BF16 inputs. Hidden A/B inputs are supplied from
the separate original hidden-RMS replay; embedding A/B inputs are explicitly
CPU-prepared from retained tiled CPU outputs. It does not qualify native
embedding RMS, full D preparation, seed addition, the complete head, target
verification, MTP acceptance, NPU execution or end-to-end speed.

This audit reviewed only the source contract. Successful native launches,
output parity and all runtime/resource guards require root's separate receipts.
