# Native NPU route and exact PLE representation — 5 October 2026

Native Windows XRT is a functioning new path on this machine. The finite synthetic
control and vector GEMV both passed exact verification with reusable host objects,
small tile-local weights and sub-0.1-ms steady-state mean complete latency. This
qualifies further real-component design; it does **not** qualify a Halogen speedup.
The original GPU server was normally restored and verified ready/open on port8840.
The full acceleration goal remains unfulfilled.

## Actual new hardware measurements

| Native fixture | Complete mean | Complete p50 | Complete p95 | Submit/wait mean |
| --- | ---: | ---: | ---: | ---: |
| Same-I/O widening control |82.263 µs|78.400 µs|83.070 µs|81.548 µs|
| Static32-KiB i16 GEMV64×256 |77.183 µs|75.000 µs|89.785 µs|76.431 µs|

Each fixture has8 excluded warmups and48 measured calls in one persistent context,
with a uniquely marked changing input and exact CPU verification on all56 calls:
3,584 output values per fixture,7,168 total. Every dispatch transfers512B input
and256B output. Complete time includes input copy, output poison, required buffer
syncs, start/wait, output sync and readback. CPU reference construction and value
comparison are outside that interval; their scope is explicit in the raw report.
There is one retained device/context/kernel/run and three retained BOs per process.
No batching, scalar fallback, ONNX provider or token-generation path was used.

The control mean includes one293.3-µs outlier. GEMV being slightly faster than the
control is not negative arithmetic cost; these are sequential, separately loaded
fixtures with host jitter. Do not subtract their times to claim device-only compute.
The chosen control-p95≤150-µs small-call design gate passed.

The old1.850-ms NPU result and0.487-ms GPU host result concern the **large real
paired projection**, with different arithmetic, weights and timing scopes. They
are not matched baselines for this32-KiB integer fixture. No multiple-of-speedup,
prefill/decode rate, MTP acceptance or whole-engine NPU-on/off delta follows from
these new timings. The previous rejected ready-cache consumers remain disabled.

## What changed in the implementation

[Native probe source](../../scripts/benchmarks/halogen_npu_native_dispatch/README.md)
uses the existing native Windows XRT SDK2.21.0, installed MLIR-AIE1.3.4/Peano and
NPU driver32.0.20102.3930. It neither changes nor replaces the driver. Root compiled
and ran the explicit vector entry point on the installed stack. The compiler flags
were corrected against the installed binary/helper, including MSVC
`/Zc:__cplusplus` and `--aie-generate-xclbin/--aie-generate-npu-insts`.

Emitted ABI matches `MLIR_AIE`: opcode3, instruction BO, uint32 **word count**,
then the two runtime BOs. Compiler padding slots are validated and unbound.
Both DMA completion tokens are consumed. Core execution is finite64 calls,
with56 used; no forever worker or inferred auto-restart contract is introduced.

The sequential allocation fallback placed32,768B weights at local0x1000–0x8fff,
input FIFO at0x9000–0x93ff, output FIFO at0x9400–0x95ff, indices at0x9600–0x9607,
and reserved4-KiB stack below0x1000. There is no overlapping allocation. The final
AIE2p ELF has no `.data/.bss`; disassembly and stack records show64-byte main/init
frames and a zero-byte GEMV frame, within the4-KiB reservation. Exact complete
weight bytes were found in the initial CDO at offset464 and in the PDI at2380.
The per-call instruction sequence programs shim BDs and completion syncs; it does
not reset the core or reload the weights. This establishes residency within this
finite active design, not persistence across context eviction or driver events.

Both root-owned hardware jobs exited normally and were closed. A relative plan
path initially prevented server restoration; a canonical-path fix allowed the
ordinary restart. A second receipt-name collision happened after the server was
ready; a read-only identity/health seal completed the bookkeeping. The original
failed supervisor result is preserved alongside the successful restoration seal.
No measurement was repeated to hide these failures. Final controller19920/backend
15024 were verified ready, idle and open, with31.48GiB physical/124.00GiB commit
headroom in the final seal. Runtime18-GiB and startup44/131-GiB policies were retained.

## Tested answer to the pixel/compression idea

The47.684-GiB object is `layers.1.ple.ngram_embedding.weight`, a learned FP8
feature table with320,001,536 rows of160bytes. It is separate from native
prompt-copy lookup and MTP token embeddings. Its hashed row order does not supply
the spatial relationship that image reconstruction normally exploits.

Packing bytes into pixels changes their layout. Lossless compression can exploit
actual redundancy; lossy image reconstruction, low-rank fitting or a learned
decoder changes the values unless exact residual information is retained.
Image sharpening cannot recover arbitrary discarded trained-weight information
with an exactness guarantee. This does not rule out a trained approximate drafter;
it rules out calling that reconstruction an exact target-weight replacement.

Root sampled32 disjoint256-row windows across16 physical regions,1,310,720B
total. A disjoint491,520B train split built the all-symbol Huffman code;819,200B
remained evaluation data. Every encoded row was decoded exactly and checked.

| Exact representation | Net saving on the sample | Isolated row reconstruction |
| --- | ---: | --- |
| Byte-aligned indexed Huffman |13.24% aggregate;13.25% eval|one160B row|
| zlib,256-row blocks |17.62%|up to40,960B /256 rows|

Huffman net bytes include a uint32 offset directory/sentinel, per-row CRC32,
256code lengths and the exact global scale. All8,192 sampled vectors were
distinct; none was zero. Byte entropy under the measured marginal model was
6.48306bits. The direct full Huffman table would be1MiB at19-bit maximum code
length; native decoder placement and speed were not tested.

Neither tested representation meets the selected20% exact net-saving screen.
Block output amplification is not a measured page-fault/I/O cost. No whole-table
compression ratio, resident capacity, CPU latency, NPU decoder benefit or token
rate is inferred from the sample. The lossless probe source and focused synthetic
tests are retained; a live compressed consumer was not implemented.

## Selected direction and remaining work

Use native NPU compute for a compact, regular operation whose weights or working
tiles stay local, with one dispatch and reused buffers. Driver reverse engineering
is not needed to reach the demonstrated small-call floor. WSL compilation with a
Windows host is documented; it does not establish Linux NPU passthrough or a
Windows-XRT-to-WSL-HIP import/fence contract. Native Linux HSA is a separate runtime
and OS qualification project, not an admitted switch for this server.

The NPU has4MiB raw distributed L2 and2MiB distributed L1 data SRAM. These are
working memories, not a contiguous free6MiB allocation or additional GPU RAM.
Shared buffers refer to existing DDR and do not increase memory capacity.

The next real candidate is a **single original hidden FC**, leaving embedding FC
on GPU. Its four2560-word streams share one6,963,200B packed-Q8 matrix. The full
pair requires13,926,400B packed storage or25MiB BF16, so complete SRAM residency
is unavailable. Native decode must preserve affine-FP32-FMA→BF16-rounding and the
original dot/reduction/output boundaries, with unchanged numerical tolerances.
Streaming/preparation/readback must be inside the component measurement.

The current E→H stage order does not expose both normalized inputs before E FC.
The retained quality bridge executes both GPU FCs first and then publishes a
shadow replacement, with copied pipes/files and10-ms reply polling. It cannot
inherit an80-µs kernel floor or establish avoided GPU work. A new guarded H-only
replacement and event-driven transport must first have a measurable cost budget;
do not attach this producer to the rejected ready consumer. Only a real-component
pass, useful consumer and acceptance-matched full-engine A/B can qualify deployment.

The [H-only next design](halogen-npu-native-hidden-next-design-20261005.md) gives
an explicit finite32-worker schedule and full transport budget. Its proposed
per-call array traffic is7,147,520B. Against the retained158.707-µs H device bracket,
the small77.183-µs fixture leaves81.524µs; fitting that traffic alone into this
remainder would require87.7GB/s before useful arithmetic or pipe copies. This is
a required-rate calculation, not measured NPU bandwidth or a matched H host
baseline. The real design has a tight budget; build the complete consumer contract
and numeric implementation before another hardware window, and reject it if the
complete matched component cannot beat original H.

A separate compact drafting model remains a larger option: learn conditional
token proposals and verify them with the original target. The inspected Halogen
GEN API exposes builtin drafters but no external draft-block/accepted-prefix/
rollback transaction. A proposer alone is therefore insufficient. No such model
was trained or inserted into the engine in this work.

## Evidence and primary references

[Machine-readable results](halogen-npu-native-route-20261005.json) preserve native
samples, CPU split/accounting, artifact hashes, failures and the restoration seal.
Raw owned evidence remains in ignored `.local` directories; no model copy or
driver package is committed.

- [AMD native Windows MLIR-AIE guide](https://xilinx.github.io/mlir-aie/dev/buildHostWinNative/)
- [MLIR-AIE device support](https://xilinx.github.io/mlir-aie/dev/Devices/)
- [XRT buffer and kernel APIs](https://xilinx.github.io/XRT/master/html/xrt_native_apis.html)
- [MLIR-AIE core memory guide](https://xilinx.github.io/mlir-aie/dev/programming_guide/core_data_memory/)
- [Triton-XDNA runtime/platform contract](https://github.com/amd/Triton-XDNA/blob/694d60d4f336952b9a8e7210ebd352086f8b6f44/README.md)
- [HGN storage contract](https://raw.githubusercontent.com/jtsylve/hgn-spec/main/STORAGE.md)
- [Official Qwen reference config](https://huggingface.co/Qwen/Qwen3.8-Flash-Next/raw/main/config.json)
