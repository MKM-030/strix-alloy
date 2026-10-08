# Native MTP query and original HT weight layout

2026-10-08. Sealed source and metadata finding; the observer is a design, with no implementation or live run.

The final native MTP vocabulary query is **BF16[2560], 5,120 bytes**. Original HT4 weights mix across **128 output lanes**, so independently gathering arbitrary packed token rows is invalid. A faithful whole-block variant preserves original lane order and selects outputs afterward. English requires **242,483,200 packed bytes**, versus **69,238,080 bytes** for the current selected Q4 codes and scales: **3.502×** by byte geometry. This defeats the proposed packed-byte saving for that variant; it does not establish measured traffic or runtime.

This finding combines `mtp-lowrank-assets-20261008` and the final `mtp-native-query-design-20261008` seal. All 7 asset-receipt entries, 13 native-delivery entries, and 8 reused source inputs match their recorded lengths and SHA256 hashes. The native seal includes six byte-checked host excerpts and three byte-checked device symbols. The [machine-readable receipt](halogen0172-mtp-query-weight-layout-20261008.json) records the pins, verification, geometry and archival files.

## Query and publication contract

The native call `0x17f1c68 → 0x17f2080` receives the final query at `model[+0xd50] + (count-1)*5120`. Q4 launch return `0x17f6f03`, descriptor `0x18f5d78`, binds `k_lq4w<1,16,1,true,0,0>`. Its arg1 query pointer is `s[6:7]`; direct loads `0x73b864..0x73b8a8` feed `v_dot2_f32_bf16` from `0x73b94c`. Preserve the raw u16 BF16 bits. FP16 conversions elsewhere concern scales.

Core and optional tail produce contiguous FLOAT logits from the same query. Scatter return `0x17f24b7`, descriptor `0x18f3be8`, binds `k_dv_scatter(const float*, const int*, float*, int)` with full count **248,320**. Its signed reverse map is **full token ID → reduced row index**. Negative entries write FLOAT negative infinity (`0xff800000`); nonnegative entries read the corresponding logit. This scatter fills the full output, so no separate full-buffer fill is required. Runtime map capture is needed to establish actual reduced row order.

## Corrected original HT ABI and closure

The original caller `0x17e48f0` invokes helper `0x1814dc0` at `0x17e4925`: descriptor in RDI, query in RSI, FLOAT output in RDX, CL=1, R8D=O, R9D=N, and stack K=2560.

| Descriptor offset | Typed meaning |
| --- | --- |
| `+0x30` | Packed weights pointer |
| `+0x38` | suH pointer |
| `+0x40` | svH pointer |
| `+0x48` | Source bits |
| **`+0x4c`** | **int32 O: output rows** |
| **`+0x50`** | **uint64 K: width** |

O and K must each be multiples of 128 and equal the supplied dimensions. This corrects the earlier reversed O/K interpretation. N=1 routes through `0x18266f0`; the default source4 path selects descriptor `0x18f4e30` and launch return `0x1828616`. Native scratch and split/grid bookkeeping also belong to this helper, so using this path requires explicit buffer ownership.

The retained decoder describes packed order `[O/128, K/16, 8 output tiles, 32 little-endian uint32]`, cyclic 256-value trellises, input/output H128, shared suH and per-output svH. Current native `k_ht_lin<4,1,true,true,false,false>` at `0x524600..0x5267d8` independently confirms cross-output butterflies. It does not establish every rounding detail of the older decoder.

| Selection | List entries / distinct IDs | Source blocks / 1,940 | Closure lanes | Packed HT bytes | Selected Q4 codes + scales | Ratio |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| English | 48,082 / 48,082 | 1,480 | 189,440 | 242,483,200 | 69,238,080 | 3.502× |
| Shared pool | 198,759 / 165,292 | 1,939 | 248,192 | 317,685,760 | 286,212,960 | 1.110× |

The pooled list includes 33,467 duplicate occurrences; each named selection is unique. Each packed block is `128*2560/2 = 163,840` bytes; each selected Q4 row has 1,280 code bytes and 160 scale bytes. Ratios exclude scales on the HT side, caches, actual DRAM traffic and timings. English whole-block svH adds 378,880 bytes and shared suH adds 5,120 bytes. A custom masked-output kernel may use 96,164 selected svH bytes, while still requiring the complete packed blocks.

For sorted copied source blocks and selected token `t`, the closure index is:

```text
128 * index(sorted_source_blocks, t // 128) + t % 128
```

A whole-block design would use `O'=128*block_count` and an owned closure FLOAT buffer. Publication can gather closure logits into the existing reduced order, or use an owned reverse map that preserves negative entries and remaps only selected entries to closure indices. Both retain the native scatter and exact selected coverage. Extra closure lanes must not become additional selected candidates. Numerical preservation remains to be checked against a native reference after an actual export.

## Bounded observer design and remaining evidence

The archived [capture contract](../../scripts/benchmarks/experimental/halogen0172_mtp_query_weight_layout/capture-contract.json) specifies ordinary `RTLD_NEXT` HIP API interception, legacy null stream0, and native pass-through. It brackets Q4 and retained scatter separately, queues query/logit/map snapshots after scatter's end event, obtains the chosen ID from the successful native four-byte D2H copy, and harvests after the response. Preparation occurs before arming; errors or overflow stop observation while native execution continues. No extra per-head synchronization is specified.

Capacity is 128 candidate slots, 254,935,040 GPU snapshot bytes, at most 769 timing events, and 4 MiB preallocated host staging. Post-response harvest uses one final stream event synchronization on the captured device. A complete corpus requires matching native counts, completed harvest, and no dropped, ambiguous or erroneous heads. Event results would be **instrumented stream elapsed brackets**, including observation and scheduling effects; they would not establish exclusive kernel time or uninstrumented serving throughput.

Exact final native query values, selected Q4 weight payloads, fitted factors and a reduced-head GPU duration corpus remain unavailable in the inspected retained evidence. The observer is **unimplemented and unrun**. No low-rank accuracy, NPU benefit, acceptance benefit or serving gain is established. A future factor design must bind actual rows and runtime order, pay both factor stages and conversion/publication costs, and undergo native verification. NPU integration additionally needs query readback, transport and output upload; positive final-query lead has not been established.

The [archival directory](../../scripts/benchmarks/experimental/halogen0172_mtp_query_weight_layout/README.md) preserves the unchanged metadata planner, source-capture script, contract and bounded excerpts. This publication performed only local source/metadata reads and archival writes; no model payload, hardware, WSL/container, engine/server, build or serving operation occurred.
