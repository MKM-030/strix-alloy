# Real v2 runtime expert replay — 4 October 2026

The guarded full-width original eight-operator graph passes CPU and NPU using
two sets of actual v2 q4c expert weights, IDs 0–9 and 10–19. All twelve calls per
provider pass their declared numerical gates, and all twelve NPU Node events
are attributed to VitisAI with CPU fallback disabled. The dynamic-weight path
is slower on NPU: mean host calls are 126.9444625 ms versus 114.6097125 ms on CPU;
`session.run` alone averages 19.09755 ms versus 6.207575 ms.

The x vectors and router coefficients remain synthetic. This qualifies these
two real-weight fixtures at the recorded tolerances, not live Halogen routing,
the complete v2 MTP head or end-to-end speed. The failed synthetic tiny fixture
does not establish a failure for these real weights.

A bounded constant-bank follow-up with twenty experts and runtime Gather passes
CPU but fails strict NPU session initialization because CPU placement is required.
Simple BF16 rounding of that bank also fails the unchanged strict CPU gate, so
no BF16-bank model was built. These are separate results from the passing
runtime-weight graph above.

## Source identity and bounded conversion

[Metadata receipt](C:/AI/halogen-mtp-npu/v2-metadata-20261004/mtp-metadata.json)
compares only HGN headers/tables: 191,784 bytes from w4b and 322,504 from v2.
All 31 MTP names and geometries agree. Eighteen tensors change from w4b
store 5 / variant 2 to v2 store 7 / variant 0, with different sizes and XOR32.
Ten BF16 tensors, the two routed expert tensors and the shared-expert gate have
matching metadata. XOR32 does not establish payload identity. The existing
standalone MTP manifest matches all 31 v2 geometry/encoding/size/XOR32 tuples.

[`halogen_npu_v2_sparse.py`](../../scripts/benchmarks/halogen_npu_v2_sparse.py)
binds the native v2 source to the current complete integrity receipt, pinned
checkpoint SHA-256
`71246c6ab3fc1de2cf06326f18e275fe9c2a18366d646ed3357d194c884fc687`.
Native device, inode, size, mtime and ctime match exactly before and after sparse
decoding. The header/table hashes match the metadata receipt. Every selected
codebook, code range, padded scale range and decoded expert has a retained hash.
The frozen q4c decoder consumes three bounded memory windows per expert; the
reader avoids thousands of small source reads. Neither checkpoint is edited.

The two sets read 55,708,160 source bytes and decode 393,216,000 FP32 weight
bytes (375 MiB), without expanding either complete expert tensor or the MTP
head. In the earlier offline CPU run, the one-time read/decode/binding cost was
5,010.3128 ms. Its source and CPU replay samples remained above 43.8488464 GiB
physical availability and 197.6894264 GiB commit headroom, preserving both
18 GiB floors. The later guarded CPU/NPU costs and external guard minima are
reported separately below.

The newly decoded v2 ID 0–9 arrays match the previous w4b fixed-top10 receipts
exactly: gate-up SHA-256 `a28726d352e7005a5be205e8fc0a4a0f0e9ebb684aad0d8262894b24afb1b8f4`,
down SHA-256 `d064c514db5e9a2a68a40933f661af6a8f8fe3be996ce49d58553b897d2e2e2e`.
This establishes decoded-weight equality for those ten experts only; it does
not establish complete-head equality or qualify a live v2 MTP path.

## Original eight operators and replay contract

[`halogen_npu_v2_dynamic_expert_probe.py`](../../scripts/benchmarks/halogen_npu_v2_dynamic_expert_probe.py)
copies the frozen original eight serialized nodes unchanged and changes only
their input geometry. All expert weights are runtime inputs:

| Input | Shape |
| --- | --- |
| x | `[1,2560]` |
| W_gate_up | `[10,2560,1280]` |
| W_down | `[10,640,2560]` |
| routing_weights | `[10,1,1]` |

One session per provider alternates changed x, both actual weight sets and routing
coefficients. Each fixture must detect substituting the other set's x, either
weight tensor or coefficients. Every returned array is retained before its gate.
The unchanged NPU branch disables CPU fallback and requires every profiled Node
to be VitisAI. The root-owned exclusive guard launched the completed run below.

## Guarded CPU/NPU result

The same-window [CPU receipt](C:/AI/halogen-mtp-npu/v2-dynamic-guarded-20261004/cpu.json)
and [NPU receipt](C:/AI/halogen-mtp-npu/v2-dynamic-guarded-20261004/npu.json)
each retain four warmups and eight measured calls. All calls pass, with zero
violations among the 2,560 output elements in each call. CPU uses
`rtol=3e-5, atol=3e-6`; NPU uses the existing prototype approximation criterion
`rtol=0.03, atol=0.003`. The maximum absolute errors are:

| Fixture | CPU | NPU |
| --- | ---: | ---: |
| A, experts 0–9 | `1.30385160446167e-08` | `0.00030145514756441116` |
| B, experts 10–19 | `3.632158041000366e-08` | `0.0010927822440862656` |

Every repeated A output has NPU SHA-256
`01d49b716a35640d9cd993010c0b7a5eb3151576a138836c41216fcaca63f13b`;
every repeated B output has
`f7610c6fe715b9eae2297babaf3af04b6310b6a1a7928844ec36c74105d27927`.
The CPU profile has 84 CPU Node events. The NPU profile has 12 Node events,
all `VitisAIExecutionProvider`; CPU EP and Python fallback are disabled. This
establishes strict ORT provider attribution, without measuring each internal
provider operation or hardware dispatch.

| Guarded replay metric | CPU | NPU |
| --- | ---: | ---: |
| Measured calls / excluded warmups | 8 / 4 | 8 / 4 |
| Mean host call | 114.6097125 ms | 126.9444625 ms |
| Mean preparation and input copies | 108.4021375 ms | 107.8469125 ms |
| Mean `session.run` | 6.207575 ms | 19.09755 ms |
| Host median / p95 | 114.68365 / 115.6385 ms | 126.6565 / 128.8184 ms |
| Session initialization | 4.2072 ms | 19,461.0303 ms |
| One-time sparse read/decode/binding | 1,769.7996 ms | 1,696.2344 ms |
| Independent FP32 reference preparation | 10.7624 ms | 10.4831 ms |

Each measured host call includes transpose/view preparation, fresh contiguous
copies of all runtime inputs, and `session.run` transfer/execution/output.
It copies 196,618,280 bytes, including 196,608,000 weight bytes (187.5 MiB).
Sparse decoding, reference preparation, initialization/compilation, validation,
array retention and hashing are excluded. `session.run` is a combined runtime
measurement; transfer, quantization and device execution are not separated.

The [guard result](C:/AI/halogen-mtp-npu/v2-dynamic-guarded-20261004/result.json)
is terminal `passed`. Build, CPU and NPU exit and terminal codes are all zero,
and every owned job closed. Provider unregister, DLL-directory close and
bootstrap shutdown succeeded. The external guard minimum was
43.709869384765625 GiB physical availability and 197.8492088317871 GiB commit
headroom, above both 18 GiB floors. Guard errors are empty and cleanup error
is null. These are standalone replay results; they do not qualify live MTP
acceptance or Halogen PP/TG performance.

## Earlier offline CPU baseline

[CPU receipt](C:/AI/halogen-mtp-npu/v2-dynamic-offline-20261004/cpu.json)
passes four warmups and eight measured calls at `rtol=3e-5`, `atol=3e-6`.
A maximum absolute error is `1.257285475730896e-8`; B is
`3.632158041000366e-8`. All 84 Node events are CPU. The mean host call is
127.744975 ms: transpose/view preparation and fresh contiguous input copies
take 121.1340625 ms, while `session.run` takes 6.6109125 ms. Every call copies
196,618,280 input bytes, including 187.5 MiB of weights. One-time sparse decoding,
9.8916 ms of FP32 reference preparation, compilation, validation, retention and
hashing are excluded and reported separately. This is an honest runtime-weight
transfer baseline, not an accelerator result or live Halogen speed claim.

## Bounded FP32 bank20 Gather placement failure

The frozen [bank20 source](../../scripts/benchmarks/halogen_npu_v2_bank20_expert_probe.py)
is also retained under `C:\AI\halogen-mtp-npu\v2-bank20-offline-20261004`.
It streams only the existing twenty decoded experts into 393,216,000 bytes
(375 MiB) of FP32 external data. Two axis-zero Gather nodes select gate/up and
down tensors from runtime `expert_ids: int64[10]`, followed by the unchanged
eight original node serializations. Runtime inputs are x `[1,2560]`, IDs `[10]`
and routing `[10,1,1]`, totaling 10,360 bytes; weights are constant initializers.
Reference weights are released before session creation. The explicit build
weight peak is 500 MiB, below the 1 GiB limit. No complete 512-expert tensor is
decoded or converted.

The root-owned [guarded CPU receipt](C:/AI/halogen-mtp-npu/v2-bank20-guarded-20261004/cpu.json)
passes all four warmups and eight measured calls against the exact saved
independent FP32 reference arrays at `rtol=3e-5, atol=3e-6`, with zero mismatches.
The A/B output hashes match the earlier dynamic-weight CPU outputs. Its mean
host call is 12.207125 ms, including 0.009975 ms of small input copies and
12.19715 ms of `session.run`; initialization is 4.6109 ms. The 108 CPU Node
events include 24 Gather events. This separately timed CPU replay does not
establish accelerator performance.

The [NPU receipt](C:/AI/halogen-mtp-npu/v2-bank20-guarded-20261004/npu.json)
fails during session initialization: ORT reports graph nodes assigned to the
default CPU EP while CPU fallback is disabled. There are no NPU inference calls,
numerical outputs or qualified timing. The retained compiler `context.json`
contains one VAIML partition with all eight original arithmetic output IDs and
inputs W_gate_up, W_down, x and routing_weights. Both Gather outputs are
partition inputs; the Gather nodes and bank initializers are outside that
partition. This records compiler selection, not executed Node attribution.

The [guard result](C:/AI/halogen-mtp-npu/v2-bank20-guarded-20261004/result.json)
is terminal `failed`: build and CPU exit zero; NPU exits one. All owned jobs
closed, provider unregister/DLL-directory close/bootstrap shutdown succeeded,
guard errors are empty and cleanup error is null. External minima are
43.70687484741211 GiB physical availability and 197.86988067626953 GiB commit
headroom, above both 18 GiB floors. The failure is provider placement, not a
memory-guard or numerical failure.

### BF16 type support and read-only precision qualification

AMD's [Ryzen AI 1.8 operator table](https://ryzenai.docs.amd.com/en/latest/ops_support.html)
marks Gather `Y` under BF16, with the other listed quantization columns blank;
it has no FP32 column and warns that specific configurations may be unsupported.
It specifies no required index width for this case. The local failure therefore
qualifies the tested FP32-bank configuration only. BF16 support motivates a
separate candidate; it does not prove the FP32 dtype is the sole cause of CPU
placement or guarantee support for rank-three banks and ten dynamic indices.

[`halogen_npu_v2_bf16_bank20_probe.py`](../../scripts/benchmarks/halogen_npu_v2_bf16_bank20_probe.py)
performs a read-only qualification of the hash-bound FP32 bank. It examines all
98,304,000 weights using BF16 nearest/even rounding, then widens each selected
expert to FP32 and evaluates the original independent per-expert expression.
The saved FP32 reference arrays, x/router hashes and CPU tolerance are unchanged.
OMP, OpenBLAS and MKL thread counts are one. The unconverted bank calculations
pass the saved CPU gate; their maximum A/B differences are
`9.66247171163559e-09` and `2.8870999813079834e-08`.

The [qualification receipt](C:/AI/halogen-mtp-npu/v2-bf16-bank20-offline-20261004/qualification.json)
records 95,746,308 changed weights and maximum weight difference
`0.0009014904499053955`. The weights are not exactly BF16-representable. With
only this weight rounding changed and all arithmetic kept FP32, both fixtures
fail the unchanged CPU gate:

| BF16-rounded weight calculation | A | B |
| --- | ---: | ---: |
| Maximum absolute output difference | `5.530659109354019e-05` | `0.00010124832624569535` |
| Violations / output elements | 1,832 / 2,560 | 2,274 / 2,560 |

Qualification minimum physical/commit availability is
45.807647705078125 / 200.51676177978516 GiB. Private/working-set peak increases
are 85,921,792 / 446,558,208 bytes, below 1 GiB. The original bank identity is
unchanged before/after the read. No BF16 external-data file, Gather/Cast model
or NPU launch was prepared: the prerequisite of exact conversion or passing
the unchanged strict CPU gate is false. This is a CPU precision result and
does not assert that a BF16 NPU model was executed or failed.

| Bank20 or BF16 qualification artifact | SHA-256 |
| --- | --- |
| Frozen FP32-bank source | `ae1372da176af3e473c78533d45906ae08c31380cdf15d0999b91da41b7b9210` |
| 1,346-byte bank20 ONNX | `38b3cfdb8280cc4d6b3419b35a0941e91150cc858daba512ceceae9d405b0d42` |
| FP32 external bank | `97ff0db7fdb2ef9375c08d4027dacf3aa553eccc958f6b470228677aa0992232` |
| Guarded bank20 CPU receipt | `53af2687a3d215350f06cae58a35f218780da5f13d05cb578699e9077ca1aab7` |
| Failed bank20 NPU receipt | `9ed51113624dfc4159cd5de887c38c6198641d696e2e9c204025ee9ba19359df` |
| Bank20 compiler context | `8e1b14bc50de42b84b25015db1ae37155e3b78743c642ac045e556ecf3bcc5ef` |
| Bank20 guard result | `ee70703e35151d905a826c594d0ebfdd33e596b528e59c1c242466b7e3ff4afa` |
| Read-only BF16 qualifier source | `73e76247c87362075c8852a43c64aa5a6a555379186320883508b02213f07f79` |
| BF16 qualification receipt | `b6bf95a430003bccbbc23634d2ca691a6da6dfab0044478ce0445adbfe81ca23` |

## Cache scope and source-only feasibility

Persistent contiguous runtime-layout buffers for fixed A/B would total 375 MiB,
below a 512 MiB host-weight cache limit. They could remove the measured strided
transpose/copy component, but the provider would still receive 187.5 MiB of
runtime weights per call. The guarded NPU `session.run` already takes longer
than CPU with this input contract. No runtime-buffer cache variant was launched;
the frozen baseline probe remains unchanged.

For arbitrary live top10 selections, a 512 MiB FP32 cache holds at most 27
experts at 18.75 MiB each. Cache transposed gate/up and down arrays by checkpoint
identity, tensor metadata, decoder version and expert ID. Persistent batched
staging buffers still need contiguous assembly when selected IDs change;
unchanged slots can be reused. Cache miss read/decode, assembly and transfer
must be timed. Predefined A/B buffer reuse alone does not measure live hit rates.

### Precompiled static expert-set graphs

A graph with selected experts as initializers removes per-call host weight
inputs. The [earlier fixed-top10 replay](halogen-npu-top10-20261004.md) supplies
local evidence for this geometry and the same eight operators: 100 calls average
1.504985 ms on NPU and 6.394102 ms on CPU, with synthetic x/router and fixed
experts 0–9. Those decoded weights match the selected v2 weights above. This
earlier run is separate from the guarded dynamic run and does not predict live
routing latency. Its NPU initialization took 32,704.2376 ms.

AMD documents compilation during initial session creation, persistent VitisAI
disk caches and ORT EP context models for later reuse; caches must be separated
by EP/driver version. It recommends EP context for final deployment. These
facilities make offline compilation and later loading of a bounded collection
of static-set graphs plausible. Their session-load latency, packed-cache size
and resident workspace still require measurement. See AMD's
[model compilation and cache documentation](https://ryzenai.docs.amd.com/en/latest/modelrun.html).

There are `C(512,10) = 312268282598377321216` unordered expert sets, so exhaustive
set precompilation is infeasible. A small cache requires actual routing traces
to establish set frequency, reuse distance and hit rate. Misses need an explicit
execution path, and graph load/compilation must be charged separately. Sorting
IDs for a cache key also requires permuting coefficients; changing the expert
sum order can change finite-precision results and needs the output gate.

### Constant-512-expert graph with dynamic Gather

Two constant tensors could hold gate/up `[512,2560,1280]` and down
`[512,640,2560]`; two Gather nodes driven by runtime expert IDs would select the
existing ten-expert MatMul shapes. The constants alone occupy 10,066,329,600
bytes (9.375 GiB) in FP32 or 5,033,164,800 bytes (4.6875 GiB) in BF16, before
compiled artifacts, selected tensors and runtime workspace. No full conversion
was prepared or authorized by this analysis.

AMD's current [operator table](https://ryzenai.docs.amd.com/en/latest/ops_support.html)
lists Gather with BF16 support, alongside the existing arithmetic operators,
but says individual configurations may remain unsupported. It does not qualify
rank-three expert constants, ten dynamic indices or Gather-to-MatMul fusion.
AMD's [constant-embedding Gather example](https://www.amd.com/en/developer/resources/technical-articles/2026/practical-technique-for-reducing-memory-usage-of-bce-models-on-r.html)
shows BF16 constant weights, runtime input IDs, an output Cast and external-data
export with compiled-cache reuse. That example permits fallback and does not
establish strict NPU attribution for Gather or this expert geometry. Its BF16
conversion is not a precision qualification for these weights.

The bounded FP32-bank case above fails strict placement, and simple BF16 weight
rounding fails the strict CPU gate. Operator-level documentation still leaves a
possible BF16 graph pattern, but supplies no qualified implementation or speed
result for these weights. A Gather output is a runtime MatMul operand; constant
storage alone does not prove that the compiler can prepack every selected slice
or eliminate the costly runtime-weight path. Only a qualified compiler partition
and measured run could establish that benefit.

The first candidate should be a small static-set cache if actual routing traces
show useful repetition. It has the strongest local initializer-backed evidence
and avoids expanding all 512 experts. The trace must first determine whether its
hit rate can justify graph/session loading and cache memory. No trace-driven
static-set cache or full-512 Gather graph has been launched; the bounded bank20
result above does not qualify that scale. No live-routing speedup is claimed.

| Frozen artifact | SHA-256 |
| --- | --- |
| Runtime probe source | `b8578423352d33bb8c9bebc0e591a2d599d388e401886d6afb654f53b10e045c` |
| Sparse reader source | `345f18778deeac5ade76c69f26f6bd2296741a55130d33a9caa0f6506f7e5c79` |
| Metadata comparison source | `25e25cf244e1da93d1fefa510ec0c95aefafb29d7fd8d0098237fb55adec0455` |
| 962-byte ONNX | `0d6bdb7d1108fa76d827e3375fef0639fee81f96b3beafd136cb0b23cb76750b` |
| Earlier offline CPU receipt | `a9863d763ea631efcaf595a28e7508ddf3fdf96e36327a1f83f69becbe43e0d8` |
| Metadata receipt | `4159d1ddb9094907ba82b62940777317d9bc89e4c7a8cb881809ecb17912e3cb` |

The guarded artifacts are retained under
`C:\AI\halogen-mtp-npu\v2-dynamic-guarded-20261004`; the model hash matches the
frozen 962-byte ONNX above. Exact executed commands are retained in `result.json`.

| Guarded artifact | SHA-256 |
| --- | --- |
| CPU receipt | `def9bc80ac3cf5f25542a8a110101ad11a91fa0116fe5fd00877c8676f323142` |
| NPU receipt | `6414893da17924b136c7012d1e8cfec7802fc0856202c8d05608cd469dd4809e` |
| CPU profile | `089fdccebba4b857bb343d99443484e2af2f8a9a1999ad4f7366d52cd4b39ade` |
| NPU profile | `99e7b52d998dfd2fd22a1e2e92ad2d2e018b3b3ce9e09f31a22c93d433a7e230` |
| Guard result | `64d3b94cd40bb7fcc9a714aa2d270d39b6391280ae605db99e874745430e738b` |
| Cleanup receipt | `6a453c78645656e88a406d7d317525c4c16ad29c5980afc160552175adfd06cb` |
| External memory samples | `ff4d36df38e2ca8ed83e36a91c8b0028df3c765e6634fd2f154786cf9761fb7d` |
| Stage receipt | `d1bcb332df4a57a0f87bb83ac7ebacd270c2d510bafafda48e73fa689a27c320` |
| Source/runner identity receipt | `164728a89416f26fcacd49df01ec2c4ec49dcf6981ff8e717fc0bdba0c83e539` |

Existing measured probes, builders, guards, checkpoint/provider files, completed
receipts and the precision note remain unchanged. Root-owned guarded replay and
placement attempts are reported separately from the new read-only CPU BF16
qualification source.
