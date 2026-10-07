# Halogen DN Gram / normalization frontier - 2026-10-07

The direct stock-norm -> Gram+norm handle substitution is rejected: the presumed Gram+norm shader is actually Gram+PAIR. A different complete native route is source-feasible: `HALOGEN_DN_FUSED_GRAM=1`, `HALOGEN_DN_FUSED_NORM=0`, `HALOGEN_DN_FUSED_PAIR=0`, with the current `HALOGEN_DN_NORM_FOLD=0`, selects Gram-only DN and then standalone gated RMS normalization. Arithmetic admission, equality, and net useful cost remain unmeasured.

This screen read retained files and disassembled an embedded object in memory. It did not run inference, change flags, patch the engine, alter service lifecycle, install tools, or change canonical controls. The open 0.16.2 service on port 8840 was untouched.

## Artifact bindings

| Artifact | Binding |
|---|---|
| Pristine `backends/halogen-wsl2-0.16.2/.local/flash_serve` | 26,052,768 bytes; SHA256 `ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b` |
| Retained `server/.local/optimization9h-20261004/mtp-route-static-20261004/host-text-disassembly.txt` | SHA256 `523467ac08e576e770a9fcffdb59ffa9542f82d58958bd03d74743f8caccb8f9` |
| `kernel-registrations.json` in that retained directory | SHA256 `c38287607691b58e618fb5e1b9f31cb5150daa85d82ecc0d22ecd46171732c2f`; independently verified by comparison agent |
| Embedded DN ELF | Engine offset `0x1499000`, length 422,544; SHA256 `5a82ad4cb1c64b6b6d7c464df70106763a09676bd55c7e3e19dd15c8eea242eb` |

This separate DN object is not `engine-gfx1151.hsaco`. Its ELF flags are `0x4a` and metadata target is `amdgcn-amd-amdhsa--gfx1151`; incidental `.gfx1250_revision=B0` metadata does not establish another target.

## Corrected shader interpretation

The Boolean template parameters map to GRAM, PAIR, and compiled NORM. Executable RVA `0x33a93` is `HALOGEN_DN_FUSED_GRAM`; `0x33aa9` is `HALOGEN_DN_FUSED_PAIR`. Globals `0x18de4d0` and `0x18de4e0` hold those flags.

| Handle | Specialization | Registration |
|---|---|---|
| `base+0x18d8d48` | `k_dn_fused16<0,false,false,true>`: actual stock fused norm | `0x18c4030` |
| `base+0x18d8d50` | `<0,true,true,false>`: Gram+PAIR | `0x18c405e` |
| `base+0x18d8d58` | `<0,true,false,false>`: Gram-only | `0x18c408c` |
| `base+0x18d8d60` | `<0,false,true,false>`: PAIR | `0x18c40ba` |

All 17 fused16 registrations were checked. Neither `<0,true,false,true>` nor `<0,true,true,true>` is registered. The actual stock-norm branch `0x18c319d..0x18c330d` copies all 24 `DnfNorm` bytes at `0x18c31d5..0x18c31ec` and selects `0x18d8d48`. Gram+PAIR zeroes those bytes at `0x18c305a..0x18c3065`; PAIR zeroes them at `0x18c34e6..0x18c34f1`. A compatible argument payload cannot add the missing compiled normalization operation.

Actual norm code: ELF value `0x8500`, file offset `0x7500`, size 28,452; SHA256 `b01189a38d12564a5fdf9a39bed17ed1bc10449982c61a156ffebf5e7f653e2b`. Visible scalar loads include normalization kernarg offsets `0x70` and `0x80`. Gram+PAIR (`0xf500`) and PAIR (`0x19f00`) have no visible loads of those normalization arguments.

The formerly labelled stock / Gram+norm code hashes actually describe PAIR / Gram+PAIR: `d6e31df26dd0cdad137973dd3d04adf97deda55ce7ab031a5902813c5de3eaa9` / `e3ccc315d4b1c9fa03b69a9697f5ed19ae453314eddfa34cc95092445da1dd95`. They are not a stock-norm comparison. Gram-only code value `0x15100`, file offset `0x14100`, size 19,840, SHA256 `831ce06e8ee12e99d9cbf3ba0571d373028ef40f9e269959a4796ab6174ea564`.

## Complete native alternate route

Ordinary prefill calls `0x1794b2a -> 0x18c38f0 -> 0x18c2f70`. With NORM_FOLD zero, `r14d` is cleared at `0x179493f`. FUSED_NORM is tested at `0x17949d3..0x17949d7`; zero skips the norm-descriptor fills and normalization-produced `r14b=1` at `0x17949d9..0x1794a1d`. After DN, `mov ebx,r14d` at `0x1794b36` leaves BL false.

GRAM true and PAIR false select Gram-only `0x18d8d58` at `0x18c34a6`, using the same normal descriptor operands and launch configuration construction: grid `48 x 1 x 1`, block `256 x 1 x 1`, current row-count argument. The caller checks positive rows at `0x18c38f0`; there is no host rejection of the current 8,192-row chunk on this route.

BL false at `0x17952e4` enters standalone normalization. The default width-128 path supplies DN output `0x18db298`, gamma `L+0x268`, gate projection `0x18db278`, result `0x18db2a0`, and width 128; it selects `k_rmsnorm_gated` handle `0x18d52e0` at `0x1795426`. The native width/batch option selects `k_rmsnorm_gated_w` handle `0x18d52d8` at `0x17955a0`, with the same buffers and `48 * rows` normalization rows. Both reach the public launch at `0x17955af`. This resolves the missing-normalization host contradiction for this exact combination.

Raw GRAM=1 with FUSED_NORM enabled remains ineligible: the caller sets normalization-produced true, while the outer helper clears norm arguments at `0x18c399e..0x18c39bf`, leaving the separate norm skipped.

## Produced operands and claim limits

The 240-byte descriptor is copied from `RSP+0x330` to `RSP+0x500` at `0x1794808..0x179481d`. Normal construction `0x179444a..0x17944eb` binds:

- Prepared BF16 input `P+0=0x18db270`.
- FP32 gates `P+8=0x18db2c8`, `P+0x10=0x18db2c0`.
- Mutable FP32 recurrent state `P+0x48=L+0xb88`.
- Index/cursor pointer `P+0x50=0x18db300`, offset `P+0x58=0`.
- BF16 DN output `P+0x60=0x18db298`, i32 row count `P+0x68=rows`.

Helper `0x1799840 -> k_dn_gates` handle `0x18d52a0` at `0x17998f4` produces `0x18db2c0/0x18db2c8` from raw projections `0x18db280/0x18db288` and parameters `L+0x270/L+0x278`. Normalization projection `0x18db278` is already produced. No new external Gram producer is established or required by the host selection; sibling arithmetic equality remains experimental.

Metadata parsed directly from the embedded DN ELF confirms that actual stock norm and Gram-only both have 11-argument, 136-byte, alignment-8 kernargs, including a 40-byte `DnfTaps` at offset 72 and 24-byte `DnfNorm` at 112. Argument offset 24 is mutable state. The previously examined PAIR / Gram+PAIR layouts also agree. A component replay oracle would need complete recurrent state, DN activation, and normalized result. No standalone replay was implemented.

The actual stock-norm metadata reports 28,864 bytes fixed LDS, 191 VGPRs, 81 SGPRs, zero private bytes, and no spills. Gram-only reports 24,512 bytes fixed LDS, 192 VGPRs, 64 SGPRs, 12 private bytes, and two VGPR spills. Both have maximum workgroup size 256 and wavefront size 32. These resource facts do not establish useful cost or occupancy of the full route.

## Native arena extents and access widths

Arena setup loads its row count into `r12` at `0x176cba3`. For positive rows, `0x176cbaa..0x176cbb7` forms `rows+63`; `0x176ce93` shifts by six. The resulting tile count `C=ceil(rows/64)` is copied to `r15` at `0x176ced6` and preserved in `rdi` at `0x176d139`. At 8,192 rows, `C=128` and rounded rows are 8,192. Independent review confirmed this binding and the extent arithmetic below.

| Native operand | Logical element width | Existing allocated span at 8,192 rows | Allocator / publication evidence |
|---|---|---|---|
| Prepared input `0x18db270` | BF16, 2 bytes | `5 * 2^18 * C` = 160 MiB | `0x176d15d..0x176d1ad`; `RSP+0x308` -> `r9` -> `0x176df37` |
| Normalization gate projection `0x18db278` | BF16, 2 bytes | `3 * 2^18 * C` = 96 MiB | Span `rsi` at `0x176d1b8..0x176d1d5`; `RSP+0x310` -> `r8` -> `0x176df3e` |
| DN activation `0x18db298` | BF16, 2 bytes | 96 MiB | Same `rsi` span; `RSP+0x300` at `0x176d27c`; publication `0x176df6a` |
| Normalized result `0x18db2a0` | BF16, 2 bytes | 96 MiB | Same `rsi` span; `RSP+0x2c8` at `0x176d287`; publication `0x176df71` |
| Transformed gates `0x18db2c0`, `0x18db2c8` | FP32, 4 bytes | `3 * 2^12 * C` = 1.5 MiB each | `0x176d22b..0x176d24c`, successive bases at `0x176d293/0x176d29f`; publications `0x176dfad/0x176dfbc` |
| Selected layer recurrent state `L+0xb88` | FP32, 4 bytes | 3 MiB | `edi=0x300000`, allocation call, and stored pointer at `0x176edfa..0x176ee0c` |
| Native cursor `0x18db300` | i32, 4 bytes | Native operation uses one 4-byte scalar; whole region not derived here | Publication `0x176e005`; four-byte reset `0x177940b..0x1779419` |
| Normalization gamma `L+0x268` | BF16, 2 bytes | Width-128 vector implies 256 bytes consumed | Native normalization signature and width argument at the standalone route |

The span sum for these large buffers plus one selected layer's state is 454 MiB. The upstream raw gate projections `0x18db280/0x18db288` each have `roundedRows * 96` bytes, or 768 KiB at 8,192 rows (`0x176d1df..0x176d200`), making 455.5 MiB if also counted. These are existing native spans, not additional candidate allocations or a service peak-memory estimate; other layers' states and other engine buffers are omitted. No capture or replay duplication is proposed.

Visible DN instructions include packed BF16 `b32`/`b128` loads, FP32 state `b32` access, and `b32` stores. The cursor scalar load is `b32`, meaning four bytes, not 32 bytes. Host span separation and native types establish ordinary operand allocation compatibility; partial ISA decoding does not certify every effective address or a complete shader read/write bound.

ROCm 7.2 `llvm-objdump --mcpu=gfx1151` is partial: 336 undecoded `.long` sites for actual stock norm, 373 for PAIR, and 328 for Gram+PAIR, despite zero exit status and empty stderr. Earlier BF16 WMMA 8/0 and exponential 19/4 counts were partial PAIR / Gram+PAIR listings; they establish neither an exact mathematical saving nor ROI.

The independent history screen found no retained exact GRAM=1 / FUSED_NORM=0 test in docs or private benchmark JSON/source receipts. Existing DN-FOLD and DN-PAIR defeats do not establish a defeat for this separate control pair. However, `kernel_controls.py` currently omits GRAM from its allowlist and rejects it in validation; FUSED_NORM is admitted. A normal service variant would require a reviewed explicit control entry and lineage. No ambient environment shortcut is proposed.

Useful cost is `t_stock_fused_norm` versus `t_Gram_only + t_native_standalone_norm`, including launch/synchronization and downstream behavior. The single empirical candidate is default-off and complete: GRAM=1, FUSED_NORM=0, PAIR=0, NORM_FOLD=0, DN_FUSED=1, DN_SCAN=0. After route/control admission, the proposed check is the actual natural 8,192-row full-engine stock-before / candidate / stock-after comparison through normal service lifecycle and smoke, with the frozen client unchanged and startup excluded from timing. Admission requires identical complete greedy output and acceptance counters; it does not relax the oracle or rely on synthetic replay. Full-engine parity is evidence for that workload, not a direct proof of all internal states or accesses.

No equality, startup admission, performance gain, or full memory bound is claimed by this source screen. This screen performed no hardware diagnostic or implementation and proposes no timer correction or chunk reopening.
