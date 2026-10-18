# Offline NPU table/compute decision — 15 October 2026

**No new justified NPU mechanism was found for the current exact PLE table consumer.** The specific first blocker is an exact, compact, independently addressable row producer. No such learned decoder, decoder-plus-residual representation, or qualified native byte decoder is present. A learned index does not supply that producer: the current keys are dense row IDs with an existing exact constant-time address calculation. Do not run another NPU dispatch, replay the closed codecs/reciprocal screen, or attach a cache to settle this question.

This is a narrow disposition of the table-to-compute idea, not a claim that the general Flash optimization goal is blocked or that future learned compression is impossible. This review used retained local source and reports only. It did not inspect active processes, WSL, Docker, devices, drivers, inference, lifecycle or model payloads. It did not build or execute a candidate. No live or shared production file was changed.

## What the native consumer actually needs

The populated tensor `layers.1.ple.ngram_embedding.weight` has dimensions `[128,2500012,160]`: 320,001,536 dense rows of 160 FP8 bytes, plus its four-byte global scale. Payload is 51,200,245,764 bytes (47.684 GiB), starting at file offset 1,882,122,624. These are trained input features, not next-token proposals. The retained header receipt is `server/.local/halogen-lookup-header-audit-20261004.json`; no payload read was repeated.

The native path computes exact hash-derived row IDs, copies each selected row from a readonly mapped file into the original raw output, and then retains the normal H2D, FP8 unpack, RMS and projection consumer. It is not a per-row `pread` call. The OS page cache already backs the mapping.

The source-concrete copy-mode insertion class is **after all 16 IDs for a token have been produced, before its 16 mapped-memory row copies**, with the original raw output layout and native worker completion retained. The detailed retained 0.17.2 map is `scripts/benchmarks/experimental/native-worker-interception-scope.md`: final ID store `0x1865aa4`, copy entry `0x1865ab4`, token continuation `0x1865791`, completion convergence `0x1865d72`, and consumer before H2D `0x17eecc1`. Those are old-image evidence only. This review did not derive or imply a 0.18.5 RVA binding. The ordinary seam is bypassed by native prefetch and cannot be reused merely by removing its flag check.

Any future replacement must fill every original-order raw row exactly and keep the native mapping/output ping-pong, generation, cancellation, joins and H2D lifetime. A pending-countdown of zero proves worker termination, not successful row production. These contracts matter independently of decoder speed.

Evidence: `docs/research/halogen-cpu-ssd-opportunities-20261004.md`, the interception scope above, and `scripts/benchmarks/experimental/ple0172-native-ordinary-first-lookup-v1/ordinary_first_lookup_0172.cpp`.

## Why index/hash learning does not remove the payload

Native addressing is already `table_base + row_id * 160`. A learned index or minimal perfect hash is useful when locating sparse or ordered keys is costly. Here it would add an evaluation or indirection to dense addressing, while the same 160 trained bytes still have to arrive. Moving the byte sequence into pixels likewise supplies a layout, not a compact generator. Hashed row order gives no established spatial relation for image reconstruction.

Turning storage into compute is possible in principle with a decoder `D(row_id)` and a representation that produces the exact original row. A fitted low-rank model, codebook, or neural decoder can instead approximate the row; then it changes ordinary target prompt state. Draft-token verification does not correct that changed target state. An exact residual can restore equality, but the residual, index, decoder weights and scale are all part of storage and complete decode cost. No evidence here establishes that those assets are sufficiently small or fast.

The already completed actual-weight screen must not be presented as a new opportunity:

| Existing exact screen | Retained result | Limitation |
| --- | --- | --- |
| Indexed byte-aligned canonical Huffman | 13.240926% net sample saving; 13.25% held-out evaluation | Below selected 20% screen; no whole-table ratio or native decoder latency |
| zlib, 256-row blocks | 17.62% sample saving | One row can require reconstructing 40,960 bytes; below 20% screen |
| Dynamic signed division replaced by exact constant remainder | 0.1194500 ms median saving per complete 8,192-token / 131,072-ID window | Closed; no native row I/O or serving improvement established |

The codec sample covered 8,192 distinct, nonzero rows across 32 windows and 16 physical regions; train/evaluation bytes were disjoint. A marginal entropy of 6.48306 bits/byte is a property of that measured model, not a proof of whole-table incompressibility. The Huffman sample used uint32 offsets; a complete table would require a sharded or wider index. This review ran no codec again.

Evidence: `docs/research/halogen-npu-native-route-20261005.md`, its JSON, and `docs/research/halogen0173-cpu-id-reciprocal-20261009.md`.

## Full cost and the CPU/GPU comparison

For an exact compressed raw-row replacement, compare complete consumer costs:

`max(0, compressed_fetch + decode + preparation - actual_ready_lead) + packing + transport + validation + synchronization + concurrent_target_slowdown < native_row_work_actually_exposed_on_the_critical_path`.

The unchanged H2D/unpack/RMS/projections are not savings of this raw-row producer. Startup, compilation, index construction and cache population must be amortized over real use rather than omitted. Native lookup already overlaps prior transformer work: the retained next-chunk observation had about 14.709 s from token publication to the second key but only about 200.944 ms native wait-to-join. The lead is not 14.709 s of removable work.

An 8,192-token chunk needs 131,072 selected rows, or 20,971,520 raw bytes (20 MiB). Compression can reduce stored bytes without reducing random page-fault bytes proportionally. A 160-byte native row faults one or two 4-KiB pages; the tensor starts at page offset 2432. Four of 128 possible row-start offsets straddle a page. A compressed random row still needs its index and one or more source pages. A benefit requires less actual miss work, more useful cache coverage, or a faster complete producer; none follows directly from the sample compression ratio.

| Placement | Actual consumer implication |
| --- | --- |
| CPU exact decoder or packed cache | Closest placement to the existing mapped gather and raw host output. It avoids NPU dispatch/return, but still must beat native page-cache hits/misses and include indexing, decoder and duplicate-memory cost. No qualified new artifact was found. |
| GPU decoder | Could retain the normal downstream consumer, but needs a qualified complete compressed-table residency/streaming and decode route. Original FP8 bytes are already compact per element. No existing exact fast representation or measured advantage is established. |
| NPU decoder/cache | Adds dispatch, DDR input/output, completion and Windows-to-WSL publication. Private distributed SRAM is not GPU-addressable capacity. No direct allocation/import/fence/lifetime contract is qualified for Windows XRT BOs and WSL HIP/DXG. |
| Independently trained token proposer | May be approximate because the unchanged target verifies its proposed IDs. It needs genuinely trained causal proposal weights, tokenizer/state transactions and timely useful native ingress. PLE bytes do not supply those weights. The tested 0.8B alternatives and same-history/pending-MTP lookup are already closed negative screens. |

The retained small native NPU GEMV's 77.183 microseconds included only 512 input and 256 output bytes in a different finite kernel. It is not a row-decoder latency or a universal launch floor. The retained staged Windows-to-WSL row exchange took 2.211–2.423 ms, complete diagnostic 6.134–6.348 ms. Those scopes are not directly additive or forecasts for 20 MiB. They do establish that a zero-cost bridge cannot be assumed. Bulk regular NPU math or a new fence cannot repair absent exact bytes.

The alternative of replacing PLE projections rather than raw rows has its own closed first blocker: the executed M8192 NPU producer changed 88,572,989 of 104,857,600 native BF16 words. Ready64 whole-embedding consumer substitution was 21.8% slower. Neither is repaired by compressing table inputs or moving the producer earlier.

Evidence: `docs/research/npu-independent-roi-20261010.md`, `docs/research/halogen-npu-memory-fabric-20261005.md`, `docs/research/halogen-npu-native-route-20261005.md`, and `server/.local/halogen0185-update-20261015/adapter-prep/npu-decision.md`.

## Bounded next action

**No new hardware or native hook is recommended.** The first missing deliverable for this exact mechanism is a self-contained, row-addressable, exact decoder package for the actual table, with all index/residual/model/scale bytes counted and a CPU complete-cost result. Such an artifact would provide a real changed premise and the CPU control before selecting NPU/GPU placement. No such artifact was found, and the retained codecs do not justify producing one by rerunning the same sample. Training a separate drafter would be a different model project, not compression of this table or a presently available accelerator.

Retain the normal 0.18.5 server and its original exact consumer. This report adds no serving cohort, no generic driver inquiry, and no claim of Prefill, Decode or native-acceptance improvement.
