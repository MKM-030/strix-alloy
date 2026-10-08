# Halogen 0.17.2: actual host-call census

A default-off native observer captured 112,040 valid fixed-size records from the actual 0.17.2 engine. The live export survived normal shutdown. This is diagnostic attribution, not a new throughput benchmark or a qualified speedup. The normal Thinking server was restored, authenticated, ready and open in its visible console.

The frozen request used exactly 8,192 natural prose input tokens and 128 output tokens, temperature 0 / seed 1, Thinking Off, Cache Off, MTP2 / PLD3,3, arena and chunk8192, at capacity262144. One warmup and one diagnostic request were kept separate. Both outputs matched; combined API MTP+PLD accounting remained70/113=61.9469%.

The last qualified stock cohort remains **1,226.62 Prefill tok/s,42.61 Decode tok/s,61.95% combined acceptance**. The historical48.42 Decode tok/s belongs to0.16.2. No instrumented rate is added to the post table.

## Observed diagnostic request

| Selected host API | Observed calls | Host interval union ms | Request share |
| --- | ---: | ---: | ---: |
| hipMemcpy | 244 | 6369.802 | 66.664% |
| hipDeviceSynchronize | 171 | 2637.161 | 27.599% |
| hipLaunchKernel | 49725 | 118.835 | 1.244% |
| hipMemcpyAsync | 1349 | 23.742 | 0.248% |

The calibrated request window was9,555.118ms. The selected host interval union was9,149.539ms(95.755%). Host intervals can include queued GPU computation, transfer work, driver work or scheduling. Their sum/union is not GPU busy time, and the uncovered interval is unclassified.

Thirteen4-byte H2D calls at returnRVA0x17b91be accounted for6,204.254ms(64.931% of the request). The observed source and destination were stable within the run. This establishes an expensive synchronization boundary, not six seconds of removable four-byte transfer overhead. The source is a dynamic32-bit scalar, so byte-wise memset equivalence was not established.

The four previously proposed H2D sites0x17bd966/0x17bd98a/0x17bd9b3/0x17bd9dc were not observed anywhere in the exported trace. No batching adapter was built for that inactive path. The next bounded hypothesis is an exact32-bit asynchronous scalar publication, conditional on verified legacy-stream ordering and measured end-to-end benefit.

## Scope and durability

The installed ROCProfiler SDK1.3.2 produced no export from the earlier real engine run after normal stop; both valid requests and the missing-export receipt are retained. No exact cause is inferred from exit143. The replacement observer writes each record during execution and was exported while the engine was idle, before normal stop.

The six selected HIP wrappers forward unchanged arguments, results and errno. API timestamps and request boundaries share LinuxCLOCK_BOOTTIME, with guest/host calibration and RTT uncertainty retained. Main-image return addresses are checked against executable ranges. There were no invalid records, partial tails or sequence gaps; the64MiB cap was not reached. Without a footer or loss counters, complete capture is not independently claimed. Existing preload-internal RTLD_NEXT calls can bypass this prepended observer.

No drivers, firmware, voltages, global WSL settings, startup thresholds or model weights changed. The NPU was not used in this diagnostic.

The JSON pins raw evidence, source identity, request boundaries, memory samples and restored server identity. The reusable observer and CPU analyzers are in [scripts/benchmarks/experimental/halogen0172_host_census](../../scripts/benchmarks/experimental/halogen0172_host_census/README.md).
