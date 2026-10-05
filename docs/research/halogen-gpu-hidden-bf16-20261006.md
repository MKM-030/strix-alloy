# Resident BF16 GPU hidden projection — 6 October 2026

**The GPU sibling is bit-exact on the two retained inputs, but this single comparison does not qualify a speed improvement. It remains disabled.** The mean original projection was 136.962 µs; the resident-BF16 candidate was 160.095 µs, a 16.89% higher component latency. Their medians were 138.371 and 139.877 µs. Only eight of sixteen measured pairs favored the candidate. The candidate's 486.932-µs outlier remains in the mean; no samples were removed or replacement series started.

| Same-window GPU event bracket | Original | Resident BF16 candidate |
|---|---:|---:|
| Mean, µs | 136.962 | 160.095 |
| Median, µs | 138.371 | 139.877 |
| Range, µs | 101.069–158.631 | 121.633–486.932 |
| Measured pairs | 16 | 16 |

The paired mean `original - candidate` is −23.133 µs. This result is insufficient to justify a live engine comparison. It does not establish a 16.89% whole-engine slowdown, a tok/s change, or universal kernel performance. The earlier original-H mean of 158.707 µs belongs to a different retained window; the decision here uses the simultaneously compared 136.962-µs arm.

## Mechanism and qualification

The candidate removes recurrent Q8 affine weight decoding and BF16 rounding by retaining the original decoded BF16 matrix on the GPU. It preserves the original four-stream M4 mapping, native BF16 dot2 accumulation, ten chunk additions, XOR8/4/2/1 reduction and final BF16 RNE. The [source audit](halogen-gpu-vector-h-candidate-20261005.md) explains the mechanism and bandwidth tradeoff; the [emission audit](halogen-gpu-hidden-bf16-emission-20261005.md) covers the compiled schedule and matching descriptor modes. Compilation uses gfx1151/code-object V6; its actual ELF ABI byte is4. The candidate has10 SGPRs/54 VGPRs and zero spills versus21/88 in the original. That register reduction did not qualify a speed gain.

One finite root-owned comparison used four excluded warmup pairs and sixteen measured pairs, A,B,B,A inputs with alternating arm order. All40 launches completed, every output matched its frozen native SHA, and original/candidate bytes agreed. The two distinct10,240-word BF16 output rows had zero word differences or nonfinite values. No tolerance was relaxed. This proves those frozen inputs, not arbitrary whole-head predictions or target acceptance.

Both arms kept weights and inputs resident. Default-stream HIP events bracket input-ready to output-ready, including host enqueue gaps/event instrumentation. Poison/input copies, output readback, hashing, comparisons, I/O and setup are outside the event bracket. Pair-end waits serve both arms; there is no added stock H-to-seed wait. Setup took1,382.328 ms, including file verification, module loading, allocation/upload and event creation; offline weight preparation is separate. The original raw matrix is6,963,200 bytes and the decoded matrix13,107,200 bytes. A live candidate would add12.5 MiB while retaining the original weights; issued weight bytes grow1.6×. Shared DDR pressure can outweigh removed arithmetic, although this screen alone does not isolate the cause of its timings.

## Effect on the optimization goal

This H boundary belongs to MTP decode. Ordinary target prefill does not use it, and exact projection replacement does not intentionally change proposed tokens. **No new Prefill tok/s, Decode tok/s or acceptance measurement was performed.** Their measured deltas are unavailable, rather than zero or an inverse of these microseconds. No engine hook or NPU producer was installed. No full-head or live cohort follows this screen.

After every development, evaluate its GPU and CPU realization alongside the NPU version, then judge complete-engine elapsed time and native accepted/attempted draft counts. Prefer the device that improves the actual critical path. The next independent NPU mechanism is bounded token proposals, with native target verification; the slower direct-H and ready-row paths remain disabled.

## Ownership and evidence

Root normally stopped the exact original controller28392/run5623a5421a8442488c20b21cbb816fd6 and backend23824/run50f336f9ba9f483e86346738c745a579. A fresh pretrial inventory showed no League process and GPU maximum utilization1%. Riot clients were retained. The finite comparison mounted no model, installed no driver, and used the pinned original image/runtime. The owned container48cf137d878ad0455b247515f8bd25199075af82a76773987b2106718401c844 and Windows job were removed/closed; the memory monitor ended. Minimum component reserves were44.610 GiB physical and199.078 GiB commit, above the unchanged22/18-GiB gates. Original restoration uses the unchanged44/131-GiB admission with60 seconds stability and remains separate from the measurement.

Raw evidence: `server/.local/optimization9h-20261004/alloy-gpu-hidden-bf16-44a6c7e26e82495ea8cb4d138498b18d/`. The [portable JSON](halogen-gpu-hidden-bf16-20261006.json) retains all twenty timing pairs, complete counters, output hashes, cleanup and preparation/lifecycle bindings. The initial helper invocation failed to import `aiohttp` in the global Python before any stop or hardware action; the successful lifecycle used the existing project virtual environment. Neither failure nor observation timeout caused a second measurement.

The normal restoration completed at22:41:21 UTC. Original controller4980/run093f67ccd22f4a5f8c865b6da3572d53 and backend20352/runa450aad327854e0bbbe33780e4f58770 are ready, with container3429bcc95ca2dbcfb4c7054549d2c020d3df3461fbf2b66d12d514f2971bc84f. Authenticated gateway health reports262144 context, zero active/completed/cancelled requests, and no draining. The original profile is unchanged; NPU integration and the candidate remain off. The owned WSL hold job is closed and no restoration recovery is pending. The successful higher-reserve start does not prove that exactly44 GiB would suffice.
