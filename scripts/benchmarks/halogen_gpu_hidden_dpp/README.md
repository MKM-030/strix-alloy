# Compact Q8 selected-H DPP candidate

`patch.py` creates a separate gfx1151 code object from the retained original.
It replaces only sixteen eight-byte `ds_bpermute_b32` instructions in selected
count1 MTP hidden FC with assembled eight-byte `v_mov_b32_dpp row_xmask`
instructions. All original compact Q8 loads, affine decode, BF16 rounding,
DOT2 chains, FP32 ADD operand order, waits, delays, branches, descriptors and
metadata remain byte-for-byte unchanged. The original file is immutable.

The finite GPU replay passed exact frozen output equality. Component mean was
140.444 microseconds original versus141.222 DPP. Each second arm won regardless
of kernel, so this screen establishes no intrinsic slowdown or speed advantage.
The candidate remains disabled. There is no serving Prefill/Decode measurement
or native acceptance result for it. The original server was restored ready/open.
See [the saved screen and device assessment](../../../docs/research/halogen-gpu-compact-h-mechanisms-20261006.md).

## Fixed scope

| Field | Binding |
|---|---|
| Target | gfx1151, physical wave32 |
| Selected symbol | `_ZN7halogen12_GLOBAL__N_16k_lq8wILi4ELi16ELi1EEEvPKhPKtPtll` |
| H virtual address / file offset / bytes | `0x2d7800` / `0x2d6800` / 2360 |
| Descriptor address / file offset / bytes | `0x1fa640` / `0x1fa640` / 64 |
| Intended replay shape | K=2560, N=2560, M=4 |
| Grid / block / shared / stream | 160 / 256 / 0 / 0 |
| Original weight layout | 2560 unsigned codes +40 FP16 affine pairs/row; 2720-byte stride |

Each wave has two independent16-lane output-row groups. The original exchange
addresses are `4*(lane XOR distance)` for distances8,4,2,1. These distances stay
inside a16-lane DPP row, so DPP copies the same32-bit register payload without
floating-point arithmetic. The original ADDs after each copy remain intact.
Original EXEC restoration before reduction remains intact; the p0 store mask
is applied after the last exchange. Correctness is conditional on the fixed
launch/shape and active-lane contract above and still needs native replay.

The original16-slot schedule interleaves streams and stages; `EXCHANGES` lists
the exact order. The patch retains even the now-redundant address computation
and LDS wait counters. This first version changes only the exchange mechanism;
removing extra instructions would be a separate implementation and comparison.

## Seals and reviewed fixture

| Artifact | SHA256 |
|---|---|
| Original17704408-byte HSACO | `45941c0579dc3487d07978a50c85cbaa141bbb674b225e708e82d81397334a83` |
| Original selected H | `e1c4867af30e56b1809ddfc407f679e45f034ab135ec1fa3801eecc58f765269` |
| Original selected H descriptor | `74caae65394734af5d319d6aab6b33b905644d7c1815f152b06c22868e2f498b` |
| Coordinator assembled128-byte DPP fixture | `602cde275166ac1097e6b5cc27ea7e2e3efb6ebeb83d109f4c44288fe0845540` |

The retained original is under
`server/.local/optimization9h-20261004/mtp-route-static-20261004/engine-gfx1151.hsaco`.
The fixture, root-owned build receipt and decoded instructions are under
`server/.local/optimization9h-20261004/gpu-hidden-dpp-fixture-9828cb2bff1845e183f389038e41b563/`.
The installed compiler SHA is
`b99a59bfbd1a878c2938f7c7c6b6c056399111bcffe9e157be1d6d9e30f1bc7b`;
the objdump SHA is
`abb4332b579bc183eed0843d6ac6cffcebf8879e300a55b3693394fed0580536`.
All sixteen fixture instructions decode as `v_mov_b32_dpp` with the original
source/destination registers, `row_xmask`, full row/bank masks and bound_ctrl1.
Both the whole fixture hash and every instruction encoding are enforced.

The source review found modern gfx11 `NoDataDepHazard` and AMD ISA §5.7 describes
`S_DELAY_ALU` as an optional performance mechanism. The byte patch preserves
the original wait/delay schedule; this source assessment does not establish
numerical or performance qualification on the actual hardware.

## Offline generation

Run `python patch.py` with explicit `--input-codeobject`, `--fixture`,
`--fixture-sha256`, `--output`, and `--receipt` paths. The fixture hash must equal
the reviewed value above. Put the output and receipt in a fresh private `.local`
measurement directory. Candidate and receipt must not already exist; all four
paths must be distinct. No default live path or installation command is provided.

The patcher requires the full original seal, exact selected-H and descriptor
seals, each original DS instruction, and each exact replacement DPP encoding.
It proves unchanged length and all bytes outside the sixteen ranges, then
writes a receipt with both image hashes and every changed range. Root must
inspect the resulting disassembly before a guarded native replay.

Pure host contract tests:

```powershell
& server/.local/venv/Scripts/python.exe -m unittest discover `
  -s scripts/benchmarks/halogen_gpu_hidden_dpp -p test_patch.py
```

## GPU / CPU / NPU and metric assessment

This candidate operates entirely inside the existing GPU MTP H kernel and keeps
the compact weight footprint. It could reduce exchange latency or contention;
that hypothesis was not supported by the completed component screen. It does not accelerate
the ordinary target Prefill kernel directly, and no PP/Decode tok/s change can
be inferred from the exchange count or component milliseconds.

CPU and NPU versions would add transfers and synchronization at this small
device-resident boundary. No supporting return is established for either, so
this version does not add either crossing. Earlier NPU H/component routes stay
disabled. If native outputs remain exact, this transformation has no intended
change to MTP guesses or acceptance. Actual acceptance must still be measured
in a comparable complete-engine run before any serving benefit is claimed.
