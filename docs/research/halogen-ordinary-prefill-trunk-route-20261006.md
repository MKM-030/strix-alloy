# Ordinary Prefill packed-trunk route, 2026-10-06

A finite source audit binds an ordinary DeltaNet bulk projection to logical
`M8192/N10240/K2560`, descriptor `layer+0x8`, and a conditional hipblasLt
route. It also finds a concrete alternate GPU pipeline that the default
large-batch policy skips. Neither the current live route nor a speed gain is
proved. No runtime, build, hardware request, model payload read, or lifecycle
operation was performed.

The source is the retained pristine host disassembly in
`server/.local/optimization9h-20261004/mtp-route-static-20261004/` and its
registration/frame index. The executable SHA-256 is
`ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b`;
host-text SHA-256 is
`523467ac08e576e770a9fcffdb59ffa9542f82d58958bd03d74743f8caccb8f9`.
Addresses below are virtual addresses before ASLR.

## Ordinary bulk binding

Chunk `0x17dd020` retains count in `r14d`; `0x17dd791` calls ordinary layer
routine `0x17d9eb0` with model, layer index and count. The layer table is
`*(model+0x4d8)` with stride `0xc68`. After normalization at `0x17da10c`,
the layer tag test at `0x17da127` selects attention for tag1, otherwise
DeltaNet `0x1791030` at `0x17da148`. This is separate from the count1 MTP FC.

Inside DeltaNet, `0x1791041/0x1791043` retain count/model in `ebp/r12` and
`0x1791058..0x179105f` form layer descriptor `L`. The two bulk FCs are:

| Call to `0x178cf90` | Descriptor | Input | Output | Logical M/N/K |
|---|---|---|---|---|
| `0x17913fb` | `L+0x8` | `*(model+0x6e8)` | `*(0x18db268)` | `8192/10240/2560` |
| `0x1791420` | `L+0x80` | Same input | `*(0x18db278)` | `8192/6144/2560` |

The descriptor offsets are explicit at `0x1791347/0x179134b`; dimensions are
immediates at `0x17913ea..0x1791420`. Executable tensor specifications at
`0x1891b39..0x1891bab` and `0x1891bd6..0x1891c46` pair names
`linear_attn.in_proj_qkv.weight` and `linear_attn.in_proj_z.weight` with
`[10240,2560]` and `[6144,2560]`. This corroborates the projection names but
does not bind a current checkpoint allocation's packed bytes to either offset.

The preceding helpers cannot bypass these FC calls for 8192 tokens:
`0x178ae5a..0x178ae5f` and `0x1796732..0x179673c` both require unsigned
`(count-1)<=7`. Ordinary DeltaNet admission itself remains conditional on
layer tag and source controls.

## Existing packed path and library

The FC dispatcher first calls packed helper `0x17f8280` at `0x178cfbb`.
Admission requires populated descriptor fields `+0x30/+0x38/+0x40`, N/K
divisible by 128 and matching descriptor fields `+0x4c/+0x50`
(`0x17f82b2..0x17f8305`). Mode is read at descriptor `+0x48`. The arithmetic
checks fit N10240/K2560, but current descriptor pointer fields/mode are unbound.

One large-M branch prepares the original packed weight through
`0x17f865c -> 0x17ec6e0`, or obtains a prepared weight through
`0x17f8629 -> 0x180c4e0`. Its library call at `0x17f8696 -> 0x18c6b80`
passes M/count, N, K, prepared weight, input and output. Library chain:
`0x18c6b80 -> 0x18c4f60 -> optional 0x18c6290 -> 0x18c6850`, with imported
`hipblasLtMatmul` call at `0x18c68e7`. Other source branches transform input,
call the library at `0x17f88f4` or `0x17f8a27`, then reverse the transform.
Current route, library algorithm and internal shader are not captured here.

## Alternate pipeline and bounded next experiment

`0x17f83ec..0x17f841f` can try native GPU packed-trunk routine `0x18092f0`
before full weight preparation/library execution. It only tries when count
does not exceed `HALOGEN_HT_TRUNK_GEMM`. Getter `0x1813d60` defaults to 1280;
with `HALOGEN_PREFILL_KEEP_TRUNK` it defaults to 192. Therefore an 8192-token
bulk call skips this native route under the defaults. A positive explicit
setting changes the threshold; it does not prove that the native call admits.

The callee's independent scratch check at `0x1809301..0x1809321` requires
`*(0x18dcf30)` populated and compares **M*K directly** with `*(0x18dcf28)`.
There is no byte multiplier in this comparison. The input-rotation path
uses 16-bit elements, so the M8192/K2560 input contains 20,971,520 elements,
or 40 MiB at 16 bits. The assignment/allocation defining `0x18dcf28` was not
bound in this finite audit: do not treat its raw value as an established
number of bytes or bypass its capacity check.

Static registrations within this alternate routine include
`k_ht_rot_rows_h` at `0x180943d` and `k_ht_tg<3>/<4>` at
`0x1809791/0x18098b4`, plus a sum helper at `0x1809a36`. They describe
existing conditional source branches, not shaders observed in live Prefill.

The next useful experiment is one complete component comparison for the first
bound shape: original preparation-plus-library versus existing native HT at
`M8192/N10240/K2560`, with frozen actual input, original packed tensor/auxiliary
parameters, and identical descriptor mode. Include input transformation,
scratch, sum/completion and output comparison in the measured cost. Root must
first establish the current descriptor/layout/scratch capacity and check that
this route has not already been rejected. No new broad shader disassembly or
whole-trunk retention benchmark is justified by this note.

This candidate belongs on **GPU**, where its existing packed representation
can avoid intermediate prepared-weight traffic. **CPU** can validate the
descriptor and outputs. **NPU** lacks a qualified equivalent packed-HT
boundary or direct GPU scratch contract, so no NPU offload benefit is established.

This is a **Prefill** candidate. It supplies no Decode or native-acceptance
gain. A component win must precede an engine comparison with actual Prefill
tok/s, Decode tok/s and accepted/drafted counts at unchanged tolerances and
workloads. No such new rates were measured in this source audit.
