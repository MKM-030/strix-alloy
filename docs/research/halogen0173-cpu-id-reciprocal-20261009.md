# CPU PLE-ID reciprocal screen: closed

9 October 2026. Replacing sixteen dynamic signed 64-bit divisions per token with compiler-lowered exact constant signed remainder saved **0.1194500 ms median elapsed time per full 8,192-token / 131,072-ID window**. Keep the normal engine stock; the absolute saving does not justify binary attachment or another engine cohort.

| Full scalar CPU ID component | Median ms/window | P10–P90 ms/window |
|---|---:|---:|
| Dynamic signed division | 0.1974250 | 0.1964250–0.1987375 |
| Exact literal remainder, including divisor admission | 0.0780625 | 0.0761625–0.0787500 |
| Paired elapsed time saved | 0.1194500 | 0.1186125–0.1208375 |

The single timed screen used 31 alternating paired samples, eight full windows per sample and two untimed warmup windows per path, with the normal server idle. The paired mean saving was 0.119585887 ms/window. Candidate timing includes an actual 16-word model-divisor admission per window; no runtime descriptor generation is needed. `std::chrono::steady_clock` measures component elapsed time. Native row-copy work, GPU overlap, serving critical-path effect and sixteen potential binary thunk round trips remain unmeasured. No serving throughput conversion or acceptance claim is supported.

Both implementations preserve unsigned modulo-2^64 hash/offset wrap, int32 sign extension, two carry words, preceding-EOS replacement and head order. They reproduce all archived ID bytes with SHA-256 `b309f270a5af14d60b895507b8d9964303e7190a81d0c3e475f38d7083cea704`. Verification also passes 65,840 signed remainder cases, 50,960 full scalar adversarial IDs and 64 unsupported-divisor rejections before output mutation. Emitted token loops contain sixteen baseline IDIVs and zero candidate IDIVs. Independent read-only review found no material concern.

Sources, original build/run scripts, the portable fixture-location runner, sanitized historical receipts and review are archived in [halogen0173_cpu_id_reciprocal](../../scripts/benchmarks/experimental/halogen0173_cpu_id_reciprocal/README.md). [The JSON record](halogen0173-cpu-id-reciprocal-20261009.json) retains source hashes and all 31 measured pairs. Large fixtures, binaries, raw state and generated ID buffers are omitted; offline fixture requirements and reproduction commands are documented in the archive README. Saving this archive involved no further compilation, test, benchmark, hardware, integration, state or Git commit action.
