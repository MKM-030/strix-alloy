# Compact-weight GPU H candidates

The objective is higher actual Halogen Prefill and Decode throughput and native
draft acceptance. Each development must assess GPU, CPU and NPU usefulness.
Component latency and source instruction counts do not establish token rates.
The existing numerical tolerances, frozen workloads and original-server
restoration requirements remain. Automation stays paused.

## Selected-kernel source audit

Kyojin's WMMA staging padding from four to five dwords does not apply to the
selected MTP H shader. This exact shader has zero allocated LDS and no WMMA.
Its DS instructions exchange register values through the cross-lane routing
hardware; they do not implement a four-dword staged row. There is no relevant
row to pad. Ordinary target Prefill may contain other kernels, but the retained
natural16K evidence does not identify a matching WMMA/LDS dispatch. Its
applicability remains unknown; no whole-engine conclusion follows.

Evidence: [native shader binding](halogen-native-d-fc-dispatch-20261004.md),
[arithmetic schedule](halogen-native-fc-accumulation-20261004.md),
[AMD DS explanation](https://gpuopen.com/learn/amd-gcn-assembly-cross-lane-operations/),
[immutable Kyojin source](https://raw.githubusercontent.com/Yamz-Labs/kyojin/aa5a3e89356a4542f4d1c04c2673a59552e294ef/README.strix-halo.md).

## DPP exchange with original compact Q8 weights

The independently reviewed candidate replaces sixteen eight-byte
`ds_bpermute_b32` slots with same-length `v_mov_b32_dpp row_xmask` instructions.
Masks8/4/2/1 preserve the two sixteen-lane rows under the original wave32/full
EXEC contract. All Q8 decoding, BF16 rounding, native DOT2 chains, separate
FP32 ADD operand order, waits, branches, descriptor and other module bytes are
unchanged. It adds no weight expansion or per-launch host bridge.

The installed gfx1151 assembler successfully emitted the required instructions.
The isolated candidate's SHA256 is
`b2e4d0a2c0f88c42c1b59ea83d84719704097f6473f7bc4bc2927870873ef211`.
An independent byte comparison verifies exactly128 changed bytes in the
sixteen approved slots and unchanged17704408-byte extent. Five pure host
contract checks pass. This is sufficient for a bounded frozen component
comparison, not deployment or a claimed speed improvement.

The LLVM source explicitly implements XOR masks1..15 as DPP row_xmask on
GFX10+; its GFX11 tests corroborate emission. Modern LLVM's gfx1151 target has
`NoDataDepHazard`; older GCN3 mandatory DPP wait-state rules cannot simply be
transferred to this GPU. The patch preserves original waits and scheduling
hints. Changed VALU issue can change their performance effect.
[LLVM transformation](https://github.com/llvm/llvm-project/commit/cad0ef5a3fae7d37a1a00de822f14aa342596178),
[target definition](https://raw.githubusercontent.com/llvm/llvm-project/llvmorg-21.1.8/llvm/lib/Target/AMDGPU/AMDGPU.td),
[hazard recognizer](https://raw.githubusercontent.com/llvm/llvm-project/llvmorg-21.1.8/llvm/lib/Target/AMDGPU/GCNHazardRecognizer.cpp).

The finite screen reuses frozen original A/B normalized input words and raw Q8
weights. Four excluded warmup pairs precede sixteen measured pairs; both input
and arm order are balanced. GPU events bracket each arm without an added
per-arm wait. Readback and frozen-output byte comparison are outside timing.
The original server was restored normally and remains ready/open. The
[completed screen](halogen-gpu-compact-h-dpp-screen-20261006.json) measured
original mean **140.444 microseconds**, DPP mean **141.222 microseconds**
(0.554 percent candidate latency). Medians were 135.216 and
139.456 microseconds. 8 of16 pairs favored the candidate; all
outliers remain. The second arm won all16 measured pairs regardless of kernel.
This strong order effect precludes a claim of intrinsic DPP slowdown. All40
outputs across warmup and measured pairs matched the frozen originals
byte-for-byte. No demonstrated component advantage is established. This
variant stays disabled; no serving cohort or Prefill/Decode/native-acceptance
gain is inferred.

## Ordinary Prefill binding still needed

A second read-only audit found the conditional CacheOff host path
`1732750 -> 17e6050 -> 17dd020 -> 18c38f0 -> 18c2f70`. With the fused
normalization pointer populated and diagnostic flags off, it selects registered
`k_dn_fused16<0,false,false,true>` at identity18d8d48. This is a static branch
binding, not an observed current natural16K dispatch with shape/tensor bytes.
See [the retained norm-fold audit](halogen-dn-norm-fold-audit-20261004.md).

Existing HIP captures cover count1 MTP; the22 HGNTUNE3 records are validated
only as opaque envelopes. No retained bulk Prefill M/N/K, algorithm or shader
mapping establishes a WMMA/LDS optimization. The useful next source task is a
finite main-matmul/writer/consumer audit from chunk17dd020 to bind one actual
bulk target shape and tensor descriptor. The rejected norm-fold, trained-plan
and larger-arena cohorts are not repeated.

## Separate two-row input reuse lead

Another source-only option assigns two output rows to each sixteen-lane group,
with `o0=32*b+2*(t>>4)`, `o1=o0+1`, grid80/block256. Each chunk loads the same
eight X vectors once, then processes both Q8 rows sequentially using eight
independent sums. The original arithmetic boundaries would be retained.

| Derived recurring cost | Original Q8 | Proposed two-row Q8 |
|---|---:|---:|
| Waves |1280|640|
| X wave-load instructions |102400|51200|
| Weight plus X wave-load instructions |128000|76800|
| Issued X operand bytes |52428800|26214400|
| Issued weight operand bytes |8192000|8192000|
| Unique weight bytes |6963200|6963200|

These are instruction and operand counts, not DRAM traffic. Unique X is only
20480 bytes and may already be cached. Longer X liveness, extra sums and fewer
waves may worsen register pressure and latency hiding. No measured bottleneck
or hardware comparison is established for this separate candidate.

## Device and serving-metric assessment

| Development | GPU | CPU | NPU | Metrics affected |
|---|---|---|---|---|
| WMMA LDS padding for selected H | Retired: no matching staging | No applicability | No applicability | No measured Prefill/Decode/acceptance gain; broader Prefill unknown |
| Compact-Q8 DPP H exchange | New standalone candidate; no hot host crossing | Offload crossing lacks a benefit case | Earlier complete H routes slower; no repeat | Potential MTP Decode only; ordinary Prefill outside boundary; exact arithmetic intends unchanged acceptance |
| Two-row compact-Q8 H input reuse | Source-only; occupancy risk unresolved | No qualified substitute | No useful crossing established | Potential MTP Decode only; ordinary Prefill outside boundary; no acceptance increase intended |

The prior resident-BF16 sibling remains rejected: its measured mean was160.095
versus136.962 microseconds for the original in that earlier matched screen.
That comparison is not a controlled serving-rate delta. A claim about Prefill,
Decode or native acceptance requires an actual matched complete-engine cohort.
