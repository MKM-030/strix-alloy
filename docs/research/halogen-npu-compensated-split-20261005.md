# Uniform compensated paired-FC candidate — 5 October 2026

The stable CPU projection's B hidden value `[0,1729]` is one BF16 step above
the original native result and fails the unchanged `.002/.0002` gate. The
[accuracy audit](halogen-npu-accuracy-audit-20261005.md) records the precise
values and source-supported rounding-topology difference: four independent
rounded FP32 dot products
and a left-associated addition chain need not round like the native DOT2 path.
The partial products before the final BF16 cast are not retained in those JSON
receipts, so their individual errors cannot be identified from current evidence.

The new source-only sibling changes recombination uniformly:

```text
(s0,e0) = TwoSum(HH,HL)
(s1,e1) = TwoSum(LH,LL)
(s2,e2) = TwoSum(s0,s1)
correction = (e0+e1)+e2
projection_fp32 = s2+correction
projection = FLOAT(BF16_RNE(projection_fp32))

TwoSum(a,b):
    s = FLOAT(a+b)
    z = FLOAT(s-a)
    error = FLOAT(FLOAT(a-FLOAT(s-z)) + FLOAT(b-z))
```

Under ordinary finite IEEE round-to-nearest arithmetic, TwoSum retains the
addition error as a second floating-point value without requiring magnitude
ordering. Adding the recovered errors reduces the loss from recombining the
already rounded partial products. This rationale follows Algorithm 3.1 and
Theorem 3.4 in [Ogita, Rump and Oishi, Accurate Sum and Dot Product](https://www.tuhh.de/ti3/paper/rump/OgRuOi05.pdf).
The final correction sum still rounds. This algorithm does not recover error
inside MatMul, emulate the native DOT2 reduction or guarantee crossing back
to the native side of this particular BF16 midpoint. Its IEEE identity is not
assumed for the provider's BFP operations; independent CPU/NPU gates remain
decisive.

The [new transformer](../../scripts/benchmarks/halogen_npu_v2_d_native_projection_compensated_split_graph.py)
reuses the sealed stable graph's exact external weight descriptors and data,
with SHA256
`61ccb018d6855f1d189c39a22554bfaf82f1a31e95a7cd8b745042f7798b906f`.
The existing quantizer and per-call input preparation are imported from the
pinned stable source without changes. No operand, observed index, native value
or tolerance selects the compensation. The original four MatMul operations,
output shapes and final BF16/FLOAT boundaries remain intact. The source writes
only a fresh graph and receipt beside the existing data; existing stable files
and failed CPU receipts are never rewritten.

Each branch has four MatMuls, nine Adds, twelve Subs and two Casts. All 54
dynamic outputs from both branches remain required by the unchanged strict
hardware/STX context proof. `ORT_DISABLE_ALL` is retained. The
[new probe](../../scripts/benchmarks/halogen_npu_v2_d_native_projection_compensated_split_probe.py)
requires a same-candidate successful CPU receipt before NPU initialization.
A failed CPU receipt is preserved but cannot admit this sibling to an NPU
diagnostic. Both provider gates still use the original native GPU oracle:
CPU `.002/.0002`, NPU `.03/.003`, with finite shapes and BF16 output lattice.

Source identities are:

| Source | SHA256 |
|---|---|
| New compensated transformer | `a279b16e4159420fc8235efe126483d6e0158d130f1aaa3e265dae19af4a472d` |
| New compensated probe | `1a5a03ee0abfd76a1997f2b7a378d04c4f0e0832c52d162fc44872f026ace639` |
| Unchanged stable transformer | `94438473e7b1084818515b6c8308b86dc1f24a48cee05fa68e0b1f3c48636566` |
| Unchanged stable probe | `2ba71370edddd8d772111a16a985a90e02396066e6d88d04686acccbfa6b2558` |

The source-only author parsed both files, checked the fixed 21-operation
recombination branch and confirmed a generic scalar cancellation sanity case
recovers a lost unit. A mocked failed CPU receipt rejects before any provider
work. An independent source review found no actionable formula or lineage
issue. These checks import only the standard library; they read no tensor,
model or engine payload, build no ONNX model and execute no provider or
accelerator. The later root-owned CPU execution below failed the unchanged
screen. No corrected CPU or NPU output or tok/s result is established.

Root's builder CLI uses the retained stable model
`C:\AI\halogen-mtp-npu\v2-d-prepare-20261004\d-native-stable-7d51948d0cdb454aa4e15079bc19aee6.onnx`
and its `.onnx.json` receipt, SHA256
`7abfe3723b74fe3728644e0a727662b9903a9a68bb8906ac4967923d4d6d653b`:
`--source-stable-projection`, `--stable-projection-receipt`,
`--stable-projection-receipt-sha256`, `--output` to a fresh same-folder file,
and `--wire-mode D`. The probe retains the preceding diagnostic's CLI argument
names and frozen FC fixtures/oracle identities. Only root executes those
commands inside its owned reserve/deadline guard. The original user's server
stays open, and the sibling supplies no live output swap or full-path admission.

## Executed CPU result: unchanged failure plus one new failure

Root built the fresh model and completed one CPU session with four warmups and
eight measured alternating A/B calls. Every repeated output was stable and
both branches changed between A/B. The retained profile has 648 CPU-only node
events (54 nodes times 12 calls), covering `MatMul`, `Add`, `Sub` and `Cast`
with `ORT_DISABLE_ALL`. Numerical execution completed, but the strict native
GPU screen failed at the unchanged `rtol=.002, atol=.0002`. The failed CPU
receipt cannot admit this candidate to the NPU; root executed no NPU run.

| Retained output | Native BF16-word mismatches | Values outside original CPU tolerance | Maximum absolute error |
|---|---:|---:|---:|
| A embedding `[1,2560]` | 0 | 0 | 0 |
| A hidden `[4,2560]` | 0 | 0 | 0 |
| B embedding `[1,2560]` | 1 | 0 | 0.0000019073486328125 |
| B hidden `[4,2560]` | 2 | 2 | 0.00390625 |

Comparing all retained final output words with the pinned stable CPU receipt
shows exactly one changed word across both A/B projections: B hidden
`[0,2095]`. The original B hidden `[0,1729]` mismatch persists unchanged.
The native hidden values below come from the independently pinned one-pass
CPU receipt, whose complete B hidden output has zero native BF16-word
mismatches. This audit opened only the retained JSON arrays, and rehashed
their word representations against their recorded output hashes.

| B hidden index | Compensated CPU | Original native GPU | Absolute error | Original allowance | Adjacent BF16 midpoint |
|---|---:|---:|---:|---:|---:|
| `[0,1729]` | 0.0634765625 | 0.06298828125 | 0.00048828125 | 0.0003259765625 | 0.063232421875 |
| `[0,2095]` | 0.984375 | 0.98828125 | 0.00390625 | 0.0021765625 | 0.986328125 |

The corresponding widened FP32 words are `0x3d820000` versus `0x3d810000`
at 1729 and `0x3f7c0000` versus `0x3f7d0000` at 2095. Stable CPU already
returned the native `0.98828125` at 2095. Compensation therefore changes a
previously passing value to the other side of its BF16 midpoint while failing
to change 1729. It does not repair the strict CPU gate. The evidence shows
that recombination topology changes a final rounding decision; it cannot
identify whether the surviving 1729 error originates inside a partial MatMul,
the split representation, recombination, or the native reduction topology.
No pre-cast values or partial products were retained by this execution.

| Artifact | SHA256 |
|---|---|
| Fresh compensated model, as bound by root's receipts | `275bdf2714675e622386e711a1f20db0b3b16a308ddc6d9f4a19e6acd84f4305` |
| Fresh model receipt | `f94054dcdcd7f506de994abca217f4360bcc7f88a95863ebfe074397e6073d19` |
| [CPU receipt](../../server/.local/optimization9h-20261004/native-compensated-cpu-46bbc9308f8a4b1f816feeb1817da80e/cpu.json) | `197c525f0b01e624b8c24fb76a3e137adc67c1c443732bcdc7c8c54f47c41f29` |
| [Owned guard result](../../server/.local/optimization9h-20261004/native-compensated-cpu-46bbc9308f8a4b1f816feeb1817da80e/result.json) | `c783322617820026b45c720af84566ad71ee431a8dbd25fe343dc50371181e6e` |
| Retained CPU profile | `d050db65ae77cdec4fe8222c676bf8130d3ed0961d00d0247edc9b21963eacbf` |

The outer guard records exit 1 for numerical failure, all owned jobs closed,
monitor stopped and no pending cleanup. Minimum physical/commit headroom
was 27.328735/119.930031 GiB; the CPU probe reports no reserve-guard error.
Root reports that the original live GPU server was preserved. The recorded
8.7114375 ms mean preparation/copy/session call is an unqualified CPU component
observation. It supplies no NPU benefit, integration admission or token rate.

## Next diagnostic: observe reductions before changing arithmetic

An instrumentation-only CPU replay should retain all four MatMul outputs,
the existing intermediate sums, recovered errors and the value immediately
before the original BF16 cast, for every A/B output. It must preserve the
sealed stable operands, weight bytes, arithmetic nodes, disabled ORT graph
optimization and failed native-gate status. Adding diagnostic graph outputs
must be verified to leave the existing final-output words unchanged. This
would expose the hidden values required to attribute the error; it is not a
new arithmetic candidate or an NPU admission.

An independent exact dyadic sum of products can then compare the original
BF16 operands with the same high/residual operands across all outputs.
Checking exact reconstruction first avoids treating FP32 reconstruction
agreement as exact real-number identity. Comparing each observed partial
MatMul with its exact dot isolates errors inside that reduction. Summing the
four observed partials exactly, then comparing the existing pre-cast sums,
isolates recombination error. Applying the unchanged BF16 RNE boundary to
each exact and observed total makes its position relative to the native
rounding midpoint explicit. No observed index chooses operands or arithmetic.

The final native BF16 outputs alone do not expose the native pre-cast
accumulators. Assigning a remaining discrepancy to a particular native DOT2,
FMA or reduction order requires a separately source-supported native replay
of the dispatched shader and its decoder/rounding boundaries. Current
receipts do not establish that attribution. Retain the failed candidates;
perform the original Q4C/native raw-row lineage proof and reduction
instrumentation before proposing another arithmetic revision. The original
tolerances and native oracle remain unchanged.
