# Ordinary QKV Prefill component screen, 6 October 2026

Neither tested GPU path justifies serving integration. The native packed path
failed the exact output contract. The selected 50 MiB original-weight cache
preserved every output but had higher measured mean latency. Both remain
disabled. The normal stock server is restored, ready and open on port 8840.

| Complete component | Original | Cached original weights |
|---|---:|---:|
| Mean wall time | 22.8911 ms | 23.2392 ms |

The cache mean is 1.5208% higher, or 0.3481 ms slower. It wins only three of eight
measured pairs. Both arms slow down in the final pairs; neither ordering gives
consistent savings. All outliers are retained. The separately excluded first
preparation took 0.706895 ms. Extra serving allocation, binding and first-miss
costs were not measured and cannot rescue a negative observed component return.
This result is specific to one layer-0 matrix; it does not measure wider caches.

The fixed ordinary DeltaNet QKV shape is M8192/N10240/K2560, descriptor mode4,
store16/variant4616. The timing measures CPU submission through full device
completion, including the original preparation in the stock arm. It is not pure
GPU busy time. Every completed output is checked against all 167,772,160 captured
bytes with unchanged raw 16-bit equality. Stock and cached-original match the
original hash exactly. Native HT has 26,787,285 mismatched words and was retired
at qualification, before any warmup or measured native cohort.

The finite schedule completed 23 pipeline calls: three excluded qualifications,
two excluded balanced warmup pairs and eight balanced measured pairs for the
cache. Seven device allocations were freed, with zero cleanup errors. No serving
request was submitted in the measurement engine. The inference gateway was
blocked before route construction. No Prefill tok/s, Decode tok/s or native
accepted/drafted delta was measured or inferred.

The coordinator's original result remains **failed**: its export destination
collided with the existing `replay` lifecycle directory after arithmetic had
completed. Root exported only the five small inventory-hashed result files from
the exact stopped container, without repeating arithmetic. All hashes and the
unchanged complete-output/schedule validator passed. This supplemental component
validation does not rewrite the coordinator failure. Normal restoration then
completed in that same coordinator; its final receipt proves the stock server
ready/open with context262144, zero active requests and no draining. The export
destination is now a separate exclusive `replay-results` directory. Actual
filesystem execution reproduced the old collision and verified the correction
and existing-destination rejection without hardware.

Physical reserve remained at least 30.9183 GiB and commit reserve at least
122.8638 GiB throughout this coordinator. Startup retained the unchanged 44/131
GiB admission with 60 stable seconds. These successful starts do not prove the
sufficiency of exactly 44 GiB.

GPU assessment: these exact candidates do not qualify a speed gain. CPU owns
submission and bounded metadata; no new CPU arithmetic advantage was measured.
No NPU producer was connected or executed. No supported API turns its small SRAM
into the selected 50 MiB GPU buffer; shared DDR adds no capacity. These results
justify no further unchanged cohort or NPU producer for this slower consumer.

The [raw evidence and calculations](halogen-prefill-ht-component-screen-20261006.json)
retain all pairs, output hashes, order groups, source receipts, the failed
coordinator result and the separate successful restoration. Independent
read-only audits released the arithmetic decision and the export-path fix.
