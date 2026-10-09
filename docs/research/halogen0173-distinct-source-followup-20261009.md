# Halogen 0.17.3: distinct source follow-up after recovery

The server stays available on port 8840. This follow-up adds no inference,
accelerator execution, serving change or speed claim. The qualified
[natural 16K measurement](../benchmarks/halogen0173-natural16k-raw-20261009.md)
remains 1,833.70 Prefill tok/s, 43.05 Decode tok/s and 180/399 = 45.11%
combined API MTP+PLD acceptance. The broader acceleration goal remains active.

## A trained Flash-Next drafter exists

[PixelML's checkpoint](https://huggingface.co/PixelML/Qwen3.8-Flash-Next-NVFP4-DFlash/tree/9cd660f9050c92fedc88cbe547bd53af0392abe1)
removes the earlier assumption that a Flash-Next trial first needs training.
It contains five draft layers and a fusion projection, but omits embedding
and vocabulary-head weights. Its conditioning uses five layer-local HC
contractions, not token IDs alone. The author reports its strongest gains on
mathematics and regressions on chat on a different NVIDIA serving stack.
Those results do not predict Halogen or NPU performance. HGN/NVFP4 feature
differences may affect draft quality; target verification remains the output
authority. This is a possible new producer, not a ready NPU integration.
[Model card](https://huggingface.co/PixelML/Qwen3.8-Flash-Next-NVFP4-DFlash/blob/9cd660f9050c92fedc88cbe547bd53af0392abe1/README.md).

The teacher tokenizer SHA256 matches the mounted frontend's
[retained receipt](halogen0173-selector-pilot-20261009/loaded-assets-receipt.json).
The trained tap IDs are 3,15,23,35,43, with next-layer boundaries
4,16,24,36,44. Each contraction has width2560, making the fusion input12800.
A K3 query uses the bonus anchor and two internal mask rows; its three
outputs predict the next three positions. Dropping query zero shifts this
checkpoint's convention. Mask ID248077 stays internal and must never be
published as a target proposal or output ID. Only committed verifier inputs may update draft
context KV. Rejected rows and provisional query KV need invalidation or
replacement. [Pinned adapter config](https://raw.githubusercontent.com/PixelML/deepspec-qwen38-flash-next/54b35f57af721ffa8d55f1c0ae79f24952a82fd6/serving/adapter/draft-config.json),
[V2 cache handling](https://github.com/vllm-project/vllm/blob/e962733e08d10f7ca65dac4df99e116460b8b174/vllm/v1/worker/gpu/spec_decode/dflash/speculator.py).

## Storage geometry, not a memory measurement

The pinned configuration describes five full-attention layers, two KV heads
of width256 and no sliding window. Assuming BF16 and uncompressed full
context, draft KV is `T * 5 * 2 * 256 * 2(K,V) * 2` bytes. Retaining all five
input contractions simultaneously is `T * 5 * 2560 * 2` bytes. Streaming
the contractions could avoid retaining the entire contraction buffer; no such
implementation is established here.
[Configuration](https://huggingface.co/PixelML/Qwen3.8-Flash-Next-NVFP4-DFlash/blob/9cd660f9050c92fedc88cbe547bd53af0392abe1/config.json).

| Actual input tokens | All contractions, GiB | Uncompressed draft KV, GiB |
| --- | ---: | ---: |
| 8,192 | 0.1953 | 0.0781 |
| 16,384 | 0.3906 | 0.1563 |
| 131,072 | 3.1250 | 1.2500 |
| 260,000 | 6.1989 | 2.4796 |

The 498,106,880 BF16 draft parameters alone represent 0.9278 GiB.
A full BF16 vocabulary projection represents another1.1841 GiB. These
numbers exclude runtime workspace, transfer buffers and compilation.
A full duplicate embedding table is unnecessary for drafting: the internal
mask vector and gathered anchor row can suffice. These full-table footprints
do not establish SRAM residency; tiled SRAM/DDR execution remains unmeasured.
These calculations establish no actual allocation or latency.

## A replacement must remove native drafting work

The pinned current host disassembly identifies controller `0x1751770`.
Its proposal loop precedes `0x1751803`, which builds the current anchor plus
candidate IDs. `0x1751834` calls the existing linear verifier; `0x17518a3`
commits the accepted target state. This supplies a source-supported bounded
linear route, without claiming an installed K3 bridge.

Overwriting IDs after native generation leaves that generation cost paid.
Continuing native draft replay at `0x1751d89` and the PLD missing-opening
call at `0x17403bb` also need explicit handling. Replacing only the existing
PLD tails cannot be credited as replacing the native MTP head. A future
trial must include all feature capture, transport, provider, vocabulary
projection, replay and fallback costs, preserve capacity and stop handling,
and compare exact authoritative output plus end-to-end rates.

The feature seam, state lifecycle and serialized provider remain unqualified.
No arbitrary cosine threshold or new training is required as a prerequisite;
an executable provider with correctly owned inputs is required. GPU and NPU
placements must be assessed against the same complete operation.

A current typed output candidate is `k_hc_mixed_sig`, reached through
`0x17f22bc -> 0x179abe0` with selector0, and HIP launch `0x179f8a9`.
Its third argument is the chunk-adjusted `*(model+0x948)` BF16 row of
width2560. That establishes an output pointer and shape, not the five trained
layer identities, checkpoint-equivalent contraction, fused/carry coverage,
completed-copy lifetime or request/epoch ownership. No tap exporter is installed.

## Other closed leads

Current target recurrence already chains distinct input/output states and
commits accepted versions by pointer swaps. The suggested preparatory
full-state clone was not found. Its substantial stored state is not proof of
removable traffic. Exact host pin and locations are preserved in the JSON.

The current official Strata v0.1.40 ref resolves to
`1cbcacbcae2953f3be9edc46369f0c875bc6ab8b`; the earlier acquired snapshot
retains its historical `1735d647` identity. The cause of that discrepancy
is not established. Sixteen reviewed mechanism files were unchanged;
ten explicit hashes were independently checked against the retained tree.
Its separate fused-head-GR opt-in exists on HIP, while multi-block head
argmax and `HEAD_MIX_MULTI` are HIP-disabled. Source presence establishes
no matching HGN arithmetic seam or local serving gain.
[Current ref](https://api.github.com/repos/Niko1221/Strata/git/ref/tags/v0.1.40),
[historical assessment](strata0140-halogen-source-assessment-20261006.md).

The separate Strata scorer-grid lead also closes: current Halogen's default
index-WMMA path dynamically bounds its grid to visible compressed keys and
query rows, and already returns uniformly before query/global loads for
out-of-range work. This source result is not a new live dispatch capture,
and it does not establish coverage of every optional scorer mode.

The repeated maps scans discussed in the historical checked-copy work
belong to its disabled consumer. The current private registration adapter
does not intercept Decode lookups. The
[scope correction](halogen-serving-copy-frontier-20261007.md) prevents treating
that older consumer overhead as a current serving fix.

STEEL supplies a distinct fused-attention dataflow reference for XDNA.
Its reported comparison uses other attention dimensions and hardware,
including a head width64 and a gfx1150 GPU; its energy results do not qualify
head256 K3 drafting, Halogen indexed attention or a local Decode gain.
[Primary paper](https://arxiv.org/html/2607.09385v1).

## Execution boundary

Root and three agents performed bounded source review. Root acquired text
metadata, not checkpoint payloads, and calculated geometry offline. Existing
serving and phase-measurement settings were preserved. No benchmark was
repeated, no additional engine started, and no NPU-on/off tok/s result was
invented. Automation stays paused. Source identities, pending seams and
the final live-server receipt are recorded in the companion JSON.
