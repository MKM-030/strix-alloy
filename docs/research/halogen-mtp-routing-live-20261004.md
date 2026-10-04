# Live Halogen MTP routing capture — 4 October 2026

The exact Halogen 0.16.2 MLP tap captured 73 complete speculative
layer-48/count-one calls from one v2, 8192-input / 128-output greedy story
request. Their ten-way routes used 215 of 512 experts; consecutive calls
shared a mean of 1.2083 experts. A small fixed resident set therefore covered
few complete ten-expert calls in this trace. The engine's original MLP,
verifier and rollback remained authoritative. This is routing evidence,
without an NPU substitution, accepted-token count or speedup claim.

## Bounded live receipt

The root-owned run was
`1971a648ad05409486f2636dcadef8f4`, with retained controller PID 8476. It used
the direct service on port 8731, v2 checkpoint, context 262144, prompt cache
Off, MTP depth 2 and one slot. The tap armed after readiness and calibration,
called the original MLP exactly once per invocation, and retained only
layer 48/count 1. Its independent bounds were 128 calls, 514 files and 2 MiB.
The run exported 294 regular files totaling 814,314 bytes; the call limit was
not reached. Each call includes an entry input row and exit expert IDs,
coefficients and complete MLP output row.

The final result passed, source pins were unchanged, controller exit was 0,
and terminal state was stopped with cleanup and RAM recovery proven. The
minimum available physical memory was 24,290,902,016 bytes (22.62 GiB), above
the 18-GiB reserve. The output SHA-256
`0fbe27247d33d2829aa90b66964ff3bb946679be7ce79b379e2555f60ec74fa6`
matches the corresponding stock output. The prompt SHA-256 was
`0fb44189491024eb0c3f1715828303dd6ba6073641d08ce7a8261f9a3a22c3a1`.

Artifacts are retained under
`server/.local/optimization9h-20261004/mtp-route-capture-353f04fbb6cf42cb8a4f9030aa4eafc9`.
The immutable receipts identify this observation:

| Artifact | SHA-256 |
| --- | --- |
| Successful result | `f471ff109a158fb5a06b858edebdc67fa1e6ef80c2baffadf872086febd1812c` |
| Entry/exit pairs | `e902cb16b5f0867698c3f32ac79451aea23d70de86d65672056a424c8feaf9c1` |
| Routing statistics | `ef8a03669cdf9e42c82ac63e00f9dfc7b2d5cfd6b85a4cf6beb4c12e4507160c` |
| Terminal recovery | `87299df5514df3fee80cbbccdf91731be55d71522cb626de7bea26e0e8dc3365` |

## Resident-set coverage

There were 730 selected expert slots. The first 36 calls trained each
resident set by observed expert frequency; ties use expert ID. The remaining
37 calls (370 slots) were held out. A complete-call hit requires all ten
selected experts to be resident.

| Capacity | Actual trained experts | Holdout slot hits | Holdout complete-call hits |
| ---: | ---: | ---: | ---: |
| 10 | 10 | 50/370 (13.51%) | 0/37 (0%) |
| 20 | 20 | 85/370 (22.97%) | 0/37 (0%) |
| 32 | 32 | 114/370 (30.81%) | 0/37 (0%) |
| 64 | 64 | 169/370 (45.68%) | 0/37 (0%) |
| 128 | 128 | 258/370 (69.73%) | 2/37 (5.41%) |
| 256 | 153 | 276/370 (74.59%) | 6/37 (16.22%) |

Only 153 experts appeared during training, so the capacity-256 candidate did
not fill its unobserved slots. Its result does not measure an independently
chosen, fully populated 256-expert cache. Retrospective sets ranked on the
entire trace perform better, but reuse the evaluation data; they are not
predictions. All 215 observed experts trivially fit within capacity 256.

This single prompt provides weak support for a tiny fixed cache that must
satisfy the whole route: even capacity 64 missed part of every held-out
ten-expert call. Partial expert residency, dynamic loading or split execution
would need separate cost measurements. These counts describe speculative
MLP invocations, which may include rejected work; they do not establish
verifier acceptance or generalize to other prompts.

## Exact seam and BF16 decoding

The [tap](../../scripts/benchmarks/halogen0162_mtp_route_tap.c) pins image
`ghcr.io/peonist-ai/halogen-flash-server@sha256:0c61bf84ac22308a53f5d1ca6b86806702d7039e5ebc51cae4c66621b92fe04a`
and engine SHA-256
`ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b`.
The MLP is RVA `0x17bd410..0x17ca056`, function SHA-256
`e318b4639c8bd2e57d66b12b823fcafc1f5c5a5136e3651c06e2bac54e46c717`,
with ABI `void mlp(model*, int32_t layer, int32_t count)`.

The input anchor is `*(model+0x6e8)` and complete output is
`*(model+0x6d8)`, each raw little-endian u16[2560] (5,120 bytes). Exit IDs
are int32[10] at pointer global RVA `0x18db400`; corresponding coefficients
are FP32[10] at `0x18db3e0`. The routed-only scratch is branch dependent and
was omitted.

Subsequent source-only GPU disassembly establishes **BF16**, supplementing
the frozen receipt's deliberately unqualified raw-u16 label. The retained
gfx1151 ELF payload begins at engine file offset `0x51000`, has 17,704,408
bytes, and SHA-256
`45941c0579dc3487d07978a50c85cbaa141bbb674b225e708e82d81397334a83`.
Its evidence is in
`server/.local/optimization9h-20261004/mtp-route-static-20261004`:

- `k_hc_mixed` (GPU RVA `0x232000`, host identity `0x18d51b8`)
  writes the third argument, identified by the host as `model+0x6e8`.
  At `0x232260/0x23226c/0x232278`, it extracts FP32 bit 16, adds that
  bit and `0x7fff`, and stores the high 16 bits. `k_hc_mixed_sig` has
  the same rounding/store sequence at `0x232798/0x2327a4`.
- Non-fused `k_moe_sum` expands u16 values with shifts by 16 at
  `0x24b090/0x24b098`, then rounds and stores high 16 bits to the
  complete output at `0x24b0d4/0x24b0e0`.
- The subsequent `k_hc_scatter` consumes `model+0x6d8` as its second
  argument. Its u16 loads at `0x237894/0x237900` are shifted by 16 at
  `0x237934/0x23793c` before FP32 arithmetic. This establishes the
  complete output's consumer contract across the producer branches.

Decode a saved element by reinterpreting `uint32_t(u16) << 16` as FP32.
Do not apply an FP16 conversion. The saved bytes and original receipts are
unchanged. Entry/exit synchronization and D2H copies make the live trace
intrusive; its response timings cannot establish original GPU MLP latency.
