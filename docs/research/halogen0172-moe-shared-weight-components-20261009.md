# Halogen 0.17.2 shared expert weights — component results

Four GPU prototypes implement sharing packed int4 loads and decoding between two or three same-expert routed tasks. All are rejected for serving: every screened pattern is slower than the authentic native projection. The normal server and its visible request-log console stayed ready and open; these components sent no inference request and changed no engine lifecycle.

| Component | Shared tasks | Native ms | Candidate ms | Candidate time change |
| --- | ---: | ---: | ---: | ---: |
| down-pair-scalar | 0/31 | 0.173543 | 0.260673 | +50.21% |
| down-pair-scalar | 20/31 | 0.167355 | 0.214618 | +28.24% |
| down-pair-scalar | 30/31 | 0.167164 | 0.191813 | +14.75% |
| down-pair-vector | 0/31 | 0.173079 | 0.259948 | +50.19% |
| down-pair-vector | 20/31 | 0.170527 | 0.218732 | +28.27% |
| down-pair-vector | 30/31 | 0.175702 | 0.186464 | +6.12% |
| gu-pair-vector | 0/31 | 0.385817 | 0.669736 | +73.59% |
| gu-pair-vector | 20/31 | 0.315551 | 0.414211 | +31.27% |
| gu-pair-vector | 30/31 | 0.272888 | 0.279550 | +2.44% |
| gu-triple-fixed | 30/30 | 0.270677 | 0.324921 | +20.04% |

Each pattern has one excluded warmup and nine measured alternating AB/BA pairs. Each arm brackets eight complete projection launches with HIP events; timings above are per launch. Every final FP32 output and both 64-byte tail guards were checked on every pair. Across 100 pairs (90 measured), 1,600 projection launches and 6,336,000 compared output rows, there were zero bit mismatches, nonfinite failures or guard errors. All owned helpers and HIP allocations/events/modules were closed.

These are constructed finite synthetic inputs, not captured model weights, activations or actual expert-overlap statistics. Down uses width640/output2560; GU uses width2560/output1280. The authentic reference is native `k_i4r_rows<640>` or `<2560>` from the retained gfx1151 module, with32 allocated synthetic experts. Pair patterns contain31 tasks and0/20/30 paired tasks. The30/31 pattern is an optimistic stress case: at N=3 with10 unique experts per token at most20/30 tasks can be paired. The triple pattern uses30 independent input rows with three tasks for each of10 experts. Its expert multiplicities are feasible under perfect top-10 overlap at N=3 after task permutation, but it does not replay the native token-major/shared-three-input layout. Even this optimistic multiplicity stress loses20.04%. Maps are precomputed and their construction costs are excluded.

The scalar pair has many dependent scalar LDS reads. The vector pair emits b128 query loads ahead of the dots and shares native low/high nibble masks and permutations, but retains repeated pairing branches. The fixed triple removes the inner pairing branches and uses the installed `__ockl_fdot2` primitive; emitted code still has separate `v_dot2_f32_f16` instructions with clamp encoding, not native dual-dot instructions. The finite fixture establishes equality for its checked values, not universal numerical parity for other values or the complete fused GL/FL epilogue.

The generated queries contain finite normal values and one input sign: sampling the LCG low bit every second draw repeats its parity. Quantized weights contain both signs. Mixed-sign queries, exceptional values and native fused epilogue behavior were not qualified. No additional diagnostics are warranted merely to broaden correctness coverage after the performance rejection.

Requested packed reads/decode work can be shared, but that does not imply proportional DDR traffic savings: the native route order and caches can already serve repeated weights. The extra query work, residency and scheduling can outweigh shared decoding. Lower VGPR counts alone did not qualify a benefit. No route capture, fused completion adapter or full-engine cohort is justified by these results. Both the existing GL activation/counters and FL fold remain untouched.

No Prefill/Decode tok/s or MTP acceptance was measured by these components; component milliseconds are not converted into token rates. The latest retained stock0.17.2 reference remains8192 actual synthetic pseudoprose input tokens,1225.98 prefill tok/s,43.00 decode tok/s and210/339=61.95% combined API MTP+PLD acceptance, with Thinking/Cache Off. It is historical evidence for that frozen workload, not a new measurement and not non-repetitive natural prose.

Two independent source decisions were also completed: another hipBLASLt setup cache duplicates the native cache, while a DPara-style independent NPU predictor needs a genuinely trained token-only asset and delayed correction head. The existing0.8B/projection experiments are not renamed or repeated. No current NPU throughput gain is qualified.

[Machine-readable evidence](halogen0172-moe-shared-weight-components-20261009.json). Exact executed candidate/host sources are archived in `scripts/benchmarks/experimental/halogen0172_moe_shared_weights/`; native binaries and all model payloads are excluded.
