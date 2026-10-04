# Count1 D preparation: runnable graph and failed CPU screening

The receipt-bound D preparation graph is implemented and built from actual v2
weights. Its CPU screening **failed** the frozen `rtol=.002, atol=.0002` gate.
The NPU stage was consequently **not started**. No native numerical parity,
full-head integration, acceptance improvement or inference speed gain follows.

## Executable component

`scripts/benchmarks/halogen_npu_v2_d_prepare.py` accepts exactly BF16-widened
FLOAT inputs `e[1,2560]` and `h[1,10240]`, and returns FLOAT
`seed[1,4,2560]` on the BF16 lattice. It implements the statically proved D
norm order, raw BF16 gamma plus one, epsilon bits `0x358637bd`, projection
boundaries, four-stream embedding broadcast, and final BF16 rounding. Its
FP32 matrix and square-root/reciprocal operations remain an algebra reference,
not an emulation of native GPU accumulation or reciprocal-square-root bits.

The graph contains 31 nodes, including two fixed MatMuls and ten explicit
BF16/FP32 Cast nodes. Two q8g64 FC matrices and two raw BF16 norm vectors were
exported using the existing bounded, sealed reader. They occupy 52,480,000
decoded bytes and required 13,952,000 selected checkpoint payload bytes.
A single embedding row for retained token 14367 required another 1,504 source
bytes; its decoded values were rounded to BF16 for the input cut. The residual
is the retained count1 row at position 8192. This does not establish native
embedding-gather parity or observe the old run's wire mode.

The builder validates complete v2 lineage, tile/row/region coverage, hashes,
encodings and current reader/static evidence before transposing immutable FC
weights into graph external data. The strict replay runner uses bounded raw
BF16 fixture reads, alternating captured/synthetic input pairs, frozen
tolerances, a BF16 output-lattice check and explicit provider attribution.
NPU admission additionally requires CPU fallback disabled and compiler
hardware partitions covering every original dynamic output. Missing compiler
alias evidence leaves placement unqualified. A separate root-owned job guard
enforces 22-GiB admission and observes the 18-GiB physical/commit floor during
blocked native calls; sources and owned handles are retained.

## Actual CPU result

Four warmups and eight measured calls, balanced between captured A and
controlled synthetic B, produced stable differences in all repetitions.

| Feed | Final BF16 word mismatches / 10240 | Elements outside fixed tolerance | Maximum absolute error |
|---|---:|---:|---:|
| A, captured residual and selected embedding | 109 | 74 | 0.00390625 |
| B, deterministic BF16 synthetic pair | 76 | 55 | 0.0078125 |

All returned values were finite and on the BF16 lattice. The profile contains
348 CPU Node events for the 12 calls, including all ten Cast nodes per call.
Input-staleness checks, graph/source seals and owned cleanup passed. The
screening failure remains recorded; no timing is promoted and no tolerance
was loosened. The original planned NPU stage has zero session creations.

One subsequent bounded CPU diagnostic exposed intermediate outputs without
modifying the sealed candidate. Embedding RMS matched the NumPy reference
bit-for-bit in both feeds. Hidden RMS first diverged in **2 words for A and 4
for B**. After projection, hidden BF16 differences expanded to 238/148 words,
then 109/76 final seed words. Embedding projection differed in 2/0 BF16 words;
its underlying FP32 maximum differences were below 4.8e-7.
This localizes the first observed BF16 divergence to hidden RMS. FP32
reduction or reciprocal ordering near a rounding boundary is a plausible
explanation; the diagnostic does not identify which CPU implementation agrees
with native Halogen. It changes observable outputs and supplies no timing or
native-parity result.

The next precise qualification is one matched native D hidden-RMS output,
immediately before `fc_hidden`, with identical residual/gamma inputs and wire
D explicitly recorded. FC and final seed native parity are later gates.
No additional depth/PLD/performance sweep is justified by this failure.

## Verification and retained evidence

Two focused BF16/RMS fixtures and three offline placement/fixture guards
passed. Independent source review covered arithmetic, lineage, placement and
owned cleanup. The builder and CPU runner executed in separate owned windows;
the CPU diagnostic also completed and closed normally. The extraction
physical/commit minima were above 49/206 GiB; the build minima were above
47/202 GiB. The failed replay and subsequent diagnostic stayed above the
18-GiB floor. All owned jobs closed; no GPU engine or NPU provider remained.
Models, installed providers/drivers, BIOS and global WSL settings were not
modified.

[Sanitized measurements and hashes](halogen-npu-d-prepare-20261004.json).
Raw artifacts remain in
`server/.local/optimization9h-20261004/d-prepare-replay-20261004-1608`,
`d-prepare-diagnostic-20261004-1612`, and
`C:\AI\halogen-mtp-npu\v2-d-prepare-20261004`.

Builder SHA256:
`6334b32fc8a9a5cb792590d0422c0ee1fb532a7c475785f75979962ec80c2544`.
Runner SHA256:
`f5214bfc4c4a24ccfec7a708fcd90b919d05c1f0dfa8bf79eaa3bab6b5cf18a3`.
Graph SHA256:
`3dd6940b38d788643b709837959d36ab16d1b926e548121b6f6efcc554147518`.
The full optimization goal remains open.
