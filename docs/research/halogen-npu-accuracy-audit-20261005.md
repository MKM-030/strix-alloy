# NPU accuracy evidence audit — 5 October 2026

The stable-high paired projection passes its original NPU component screen;
it still fails one value at the original stricter CPU screen. A later original
embedding RMS replay closes the frozen A/B RMS boundary. Native Q4C table
conversion/gather and actual early publication remain unqualified, so this
audit establishes neither a live NPU substitution nor an NPU token-rate delta.

This audit reads ordinary sources and retained JSON receipts only. It performs
no tensor/engine payload reads, provider initialization, model build or engine
operations. Root retains exclusive ownership of those operations. The early
preparer now binds the existing RMS qualification through JSON/source only;
its arithmetic and tolerances and the existing sealed plans are preserved.

## Unchanged numerical tests and the remaining CPU value

The original, one-pass and stable probes declare CPU
`rtol=.002, atol=.0002` and NPU `rtol=.03, atol=.003`. The stable probe checks
the pinned original helpers' tolerance dictionaries before session creation;
its comparison uses the original native-GPU Q8 FC outputs as the expected
values and also requires finite FLOAT shapes and BF16 output lattice. The
early-token preparer keeps those same two declarations and directly screens
its CPU projection with `.0002 + .002*abs(native_output)`. No tolerance was
widened and no oracle selected split operands or individual corrections.

The retained stable NPU receipt passes on both A/B projections throughout
four warmups and eight measured alternating calls. All 18 required dynamic
outputs satisfy strict hardware/STX placement and the execution profile proves
VitisAI execution with CPU fallback disabled. It is tolerance agreement:
A/B hidden outputs still differ from the native GPU in 3,648/3,614 BF16 words.

The stable CPU receipt fails B hidden projection `[0,1729]` (flat index 1729):

| Quantity | Value |
|---|---:|
| Stable CPU output | 0.0634765625 |
| Original native GPU output | 0.06298828125 |
| Absolute error | 0.00048828125 |
| Original `.0002 + .002*abs(expected)` allowance | 0.0003259765625 |
| Adjacent BF16 rounding midpoint | 0.063232421875 |
| Stable/native widened FP32 word | 1031929856 / 1031864320 |

The exact value and index come from comparing retained JSON output arrays of
the stable CPU receipt with the one-pass CPU receipt. The latter records zero
native BF16-word mismatches for the complete B hidden output, providing the
native value without opening a binary output. Both are independently sealed:

| Receipt below `server/.local/optimization9h-20261004/` | SHA256 |
|---|---|
| `native-stable-cpu-8ab32923ac844b5898afb471383b0df3/cpu.json` | `da8be1da0f7b10816f6a15cfd904f2e02fb219bf024b5812b6b2028d6973e823` |
| `native-split-cpu-7a7771ce41aa47bc9d394f2a2f12208b/cpu.json` | `97b1435dded58777d1a5b038ee6253b983eaca43faf45c227dfa4aada862647d` |

The source supplies a numerical reason for this failure: splitting changes one
native dot product into four independent FP32 MatMul reductions and the fixed
left-associated sum `((HH+HL)+LH)+LL`, before BF16 rounding. Exact numerical
reconstruction of operands does not make those floating-point reductions
equivalent to the original native BF16/DOT2 accumulation. The adjacent BF16
outputs show a final rounding-boundary crossing. The available receipts do
not retain pre-cast partial products, so attributing the crossing to one exact
partial or FMA would exceed the evidence. Stable weight residuals also contain
34/41 values that change under BF16 rounding; the fixed-point proof applies to
the high parts and is not a proof of exact provider residual arithmetic.

The minimal proof of closure is a generic arithmetic revision, applied to all
outputs, followed by a new same-candidate CPU receipt with zero values outside
the unchanged CPU tolerance and a new NPU receipt with the unchanged NPU and
placement/profile gates. Balanced or compensated recombination is a candidate
to investigate; it is not already proved to close the native mismatch. No
per-value correction, altered oracle, relaxed CPU gate or passing status is
justified. The existing failed CPU receipt is truthfully admitted only as
completed evidence for a standalone NPU diagnostic; integration admission
remains false.

## Original embedding RMS was already executed

The preparation report's assertion that native embedding RMS had no executed
receipt is stale. The later owned ROCr component stock run at
00:38:22..00:38:45 UTC on October 5 executed the original
`k_rmsnorm_grouped` shader. Its source verifies the original engine and
byte-identical embedded codeobject, uses width2560/groups1 with raw gamma and
aliased input/output, and retains mapped HIP/ROCr identities before and after.
Eight warmups and 64 measured calls per supplied A/B row repeat exactly.

| Stage | A SHA256 | B SHA256 |
|---|---|---|
| Supplied raw row | `af284c0101ac76b7562b3d9e19cfc6721266f282358d8f313a09b961435ee374` | `e14b7e6b5bd1a53d1e0c26d0eb9d2356728668a89a2e591707c463cc1e2b01b4` |
| Repeated original shader output and frozen NumPy/ORT RMS references | `97079c27ab56da44c2ab29780c856be79803d402caf754acfbf7d187fbe34892` | `8104e72375af48ab130c04b01fe68399e1d6c84951f9aa45c67a54b7d00db6ce` |

Raw gamma SHA256 is
`04c4a570850e06f2d8913da8220d54d4c7f87db6eb6d45480b938e8ba41d6a86`.
The supplied fixtures are sealed at
`cf7ae0ed36d323ae32b6664ed080bc2b3cdd44863878d51719b53ddef9f72246`.

| Receipt below `alloy-rocr-component-16a35be771404bd7a7ac3d1b43526528/` | SHA256 |
|---|---|
| `stock/result/probe.json` | `421b0f484f5364a3b71938729e78a4ef98f6eefa94ee4d8ba7d279ca42c41790` |
| `stock/owned-result.json` | `350fdbddc0faa56bdaa1a689d0617b18fd7bb48b7f7cb64ace81917a68925d34` |
| `result.json` | `7e1a0f5b1dcfd122d65f88db6d6dda43d0bbd2634adaf3cd7b4f21bb69e1e3b8` |

The stock probe passed and its process exited 0, job closed and container was
removed without errors. The outer controller records passed/uncontaminated,
colleague preserved, monitor stopped, controller handle closed and no pending
cleanup; minimum physical/commit headroom was 26.030510/118.802414 GiB. The
executed probe source SHA256 is
`9b2f6dd62162cbed8ea51f767e018c787a69ebf03fa6e4cc8b6ef153fdf83f52`.

This qualifies the original RMS boundary on those two supplied CPU raw rows.
It does not prove those raw rows equal the native checkpoint-table gather, nor
does it qualify other rows or a live head. Historical fixture/FC receipts remain
sealed; their then-current metadata does not negate the subsequent evidence.

## Early preparation source and remaining gate

The [early-token preparer](../../scripts/benchmarks/halogen_mtp_early_token_prepare.py)
and [raw capture](../../scripts/benchmarks/halogen0162_raw_embedding_capture.c)
preserve the intended sequence: host token14367; original native-table gather
oracle; exact comparison of all 2560 BF16 words; raw gamma and RMS; BF16-rounded
FC weights, CPU FP32 MatMul and the original output BF16 boundary. A single raw
word mismatch writes a failed gather receipt and stops before RMS/FC.

The capture checks the pinned full mapped head, gather identity/launch caller,
token/count/wire, launch geometry and native pointer slots. It forwards each
original head and launch once, then synchronizes and copies 5120 bytes before
the caller can enqueue in-place RMS. It introduces no device allocation or
tensor write. The captured pointer-span checks prove arithmetic bounds, not
allocation extents/lifetimes, active HIP context or loaded checkpoint identity;
the root-owned provenance contract remains necessary. Its synchronization makes
this an instrumented diagnostic and cannot serve as a live timing result.

The preparer binds sealed source and receipts and selected tile hashes before
and after publication. It performs no hidden computation, late hidden input,
NPU session or transport. Its metadata-only `embedding_rms_qualification`
checks the executed original kernel/engine/ABI, both raw/gamma/normalized row
hashes, all 64 exact repeats, mapped runtimes and stock/outer owned exit,
cleanup and reserve evidence. Both its plan and export receipt report
`frozen_input_native_embedding_rms_qualified=True`; the separate
`original_native_embedding_rms_observed_by_this_export=False` confirms the
current export executes no GPU. Qualification reads no payload bytes and
explicitly leaves native table/gather and general-table parity false.

The standard-library baseline qualification passes; 13 independent altered
metadata cases reject dispatch width, input/output alias, raw gamma, A raw row,
B normalized output, repeat parity/count, mapped HIP, owner job close/exit,
outer contamination/cleanup and fixture RMS lineage. No new fixture or provider
was executed. The exact raw-gather gate remains the next decisive numerical
proof. One token match still leaves broader table coverage and actual early
producer, batch publication and useful overlap unproved.

Revised preparer SHA256 is
`228657fea31f01c345978d125803b87f62df14f4450d83247f6f63afb791d114`;
the original `0a0223...ef76` source/plan receipts remain historical evidence.
Capture SHA256 remains
`a16afefb35db8affd5f4373b68a44341d830323acd928e7f153a29c8005c9cce`.

Root reviewed the final source and executed a fresh metadata-only plan in a
45-second owned CPU guard. The new plan below
`server/.local/optimization9h-20261004/early-token-metadata-refresh-0ac16816f0fd4c11a609d2d0632656e0/`
has SHA256
`77b41fcec8b5d9e9aef48f07e85ce4edb154083e4e78a465a196b49d3950492b`.
Its sibling `result.json` has SHA256
`5c65ce0d75b2d5efaee3e61c19e4fb6c0922d68a22d1da691d52eaf13fc0790b`
and records passed, exit 0, job closed and no errors, with minimum physical/
commit headroom of 27.664047/119.566479 GiB. It confirms zero payload bytes,
no GPU/NPU execution and the user's engine preserved. The plan declares the
frozen-input native RMS qualification, unchanged `.002/.0002` and `.03/.003`
tests, no runtime token producer and no batch publication. The older plan is
preserved. This refresh closes metadata admission of the existing RMS proof;
it does not execute the missing native raw-gather gate.

The retained paired-FC NPU timings remain component observations. The live
engine has no admitted NPU-on result, so no measured NPU tok/s delta exists.
No component latency was converted into synthetic token throughput.
