# Next native NPU real component: original hidden FC with a replacement consumer

5 October 2026. Source/text review only; no payload reads, imports, execution,
builds, hardware queries, installs or lifecycle actions. ROOT supplied the new
native result: control complete mean 82.2625 us/p95 83.07 us, static 32-KiB integer
GEMV mean 77.183333 us/p95 89.785 us, each 8 warmups + 48 measured calls and all 3,584
output values exact. Both clear the chosen 150-us small-call continuation gate.
Those fixtures do not measure the original real projection, floating-point
arithmetic, streamed weights or the Windows/WSL consumer.

**Next concrete source package: one native launch for the complete original
hidden FC, connected to a new before-original-H replacement hook.** Keep the
embedding FC on GPU. Stream the unchanged hidden matrix's packed Q8 information
from a persistent Windows DDR BO, decode/round on the AIE cores, and return all
four 2560-element BF16 outputs. Do not schedule another hardware-only diagnostic:
the arithmetic implementation, finite dataflow, input-only live wire and actual
replacement/fallback consumer must form one reviewable package first.

## Why this cut, rather than a paired launch or small invented projector

The retained native order is gather -> E RMS -> E FC -> whole-row H RMS -> H FC
-> seed add. Both normalized inputs first exist at H FC entry, after E FC has
already executed. A one-launch paired replacement therefore requires deferring
E and proving that its output/input is not consumed or reused between those
stages; that proof and branch do not exist. H-only replaces useful work without
inventing a stage reorder. Its matrix is reused across four input streams in one
dispatch, as in the original M4 shader.

The two stored matrices are each 2560x2560, 6,963,200 raw bytes; the packed pair is
13,926,400 B. Their BF16 form is 25 MiB, and the earlier corrected high/low FP32
form 100 MiB. Even one packed matrix exceeds all 6 MiB of raw distributed NPU SRAM,
before stacks/FIFOs. Full static residency is rejected. A compact low-rank
projector changes the operation; a lossless codebook needs a measured encoding
and exact reconstruction proof. Retained source establishes neither. A small
real shard that leaves the complete original GPU FC running is also rejected as
an optimization: it does not remove the component's work.

Sources: [native order/storage](C:/Projects/strix-alloy-clean/docs/research/halogen-native-d-fc-dispatch-20261004.md:66),
[original replay contract](C:/Projects/strix-alloy-clean/scripts/benchmarks/halogen0162_fc_replay.c:9).

## Preserve the real numeric boundary

Original store7/variant0 uses unsigned u8 codes, not signed i8. Every 2720-byte row
contains 2560 codes followed by 40 little-endian FP16 scale/bias pairs, one pair
per 64 input columns. For each weight use one FP32 affine FMA from the original
FP16 scale/bias and converted u8 code, then BF16 RNE. Multiply those rounded
weights by the unchanged normalized BF16 input with FP32 accumulation/reduction,
and round each completed projection to BF16 RNE. Do not replace this with an
integer dot followed by one scale: intermediate weight rounding changes that
operation. Do not substitute the separate-multiply/add Python decoder or the
QMoE/BF16-scale contract.

H input is 20,480 B: the original whole 10240-element RMS result, subsequently
viewed as four 2560-element FC streams. H output is 20,480 B before seed add. The
NPU must not independently renormalize the four streams or move the BF16 output
boundary. E RMS/FC, seed add and all remaining head operations stay original.

The frozen oracle remains the actual original Q8 GPU FC on identical normalized
A/B BF16 inputs. Preserve CPU rtol=0.002/atol=0.0002 and NPU rtol=0.03/atol=0.003,
using abs(error) <= atol + rtol*abs(reference), finite BF16 lattice outputs and
separate exact-word mismatch counts. Any remaining strict CPU failure is a
blocker; the retained stable CPU sibling has two one-BF16-ULP hidden-B misses.
Changing hardware does not erase them or permit wider tolerances. Different AIE
dot/reduction order can be screened at the frozen NPU tolerance; bit-exact native
accumulation must not be asserted without proof. Require complete-head/output
and acceptance qualification separately before a speed A/B.

Sources: [native FMA/BF16/dot boundary](C:/Projects/strix-alloy-clean/docs/research/halogen-native-d-fc-dispatch-20261004.md:154),
[frozen comparison gates](C:/Projects/strix-alloy-clean/scripts/benchmarks/halogen_npu_v2_d_native_projection_stable_split_probe.py:38),
[remaining CPU failure](C:/Projects/strix-alloy-clean/scripts/benchmarks/halogen_mtp_fc_npu_diagnostic.py:200).

## One-launch streamed implementation to review

Use the installed MLIR-AIE 1.3.4/XRT mechanism already admitted, expanded to the
full NPU2 target's eight columns/four compute rows. Proposed tile geometry is
16 output rows x 256 K values, with ten K chunks and 160 output-row tiles. Across
32 workers, each worker computes five output-row tiles and consumes 50 packed
weight chunks per invocation. Every output tile computes all four streams; keep
FP32 partial sums across the ten K chunks and perform BF16 RNE only at the final
output store. Use one persistent run/argument set and a finite64-invocation
worker budget, with 8+48 initial cohort calls. There is no per-chunk XRT launch.

Each packed chunk contains 4096 code bytes plus 256 scale/bias bytes = 4352 B.
An initialization packer changes storage order only, preserving every original
u8/FP16 bit, and binds its receipt to the original row-range hashes. It must
prove inverse reconstruction equals the original matrix. A persistent DDR BO
holds all 6,963,200 packed bytes; every invocation streams the full matrix through
shim/memory-tile DMA. This is DDR retention, not full SRAM residency.

A proposed per-worker budget is 20,480 B for one complete H input, 8,704 B for
two packed chunks, 8,192 B decoded BF16 scratch, 256 B FP32 partial outputs, 256 B
double output FIFO, and 4096 B stack = 41,984 B before compiler bookkeeping and
spills. Broadcast one input DMA per column to its four workers; this reads
163,840 input bytes from DDR per invocation. Output DMA is20,480 B; weight DMA
is 6,963,200 B. Minimum specified DDR-to-array/array-to-DDR traffic is therefore
7,147,520 B per call, in addition to Windows/WSL transport. Generated bank maps,
BD transfer units, exact 50-chunk schedules, input lifetime, output ordering and
aggregate call-stack extent must replace these proposed budgets before admission.

AIE BF16 MAC implementation/reduction is a candidate, not an assumed match to
gfx1151. Its affine decoder must retain one FP32 FMA and explicit weight RNE;
review the compiler output for contraction/conversion boundaries. If it cannot
pass the frozen gates without value-specific fitting or a large high/low rewrite,
reject this implementation rather than carrying the 100-MiB corrected ORT form
into another native latency probe.

## The actual Windows/WSL consumer is part of the component

The retained paired consumer is **shadow only**: it always runs both original
FCs, captures norms and native outputs, then optionally publishes a candidate
before seed add. Its request is 51,424 B and reply 25,856 B, plus 56 B transport
framing each way. It also uses fsync/rename packet files, 1-ms relay polling and
10-ms C reply sleeps, with a 200-ms wait. That path cannot establish a gain from
an approximately 80-us native launch and must not be reused as the speed consumer.

Create a separate H-only input/request version. At the validated count1-D H
dispatcher entry, before original_fc, fence the exact owned default-stream input,
copy its 20,480 B to CPU, and send an input-only packet over already established
resident binary Windows/WSL/docker pipes. The Windows C++ endpoint validates the
same process/model/descriptor/nonce/epoch/sequence bindings, feeds the persistent
NPU run, and returns 20,480 B BF16 output. The C hook validates the complete reply
before writing anything, copies the result to the original H output, establishes
its visibility to subsequent seed-add work, and skips exactly this original H
call. E remains original. There is no Windows XRT BO/WSL HIP zero-copy claim.

With the existing 224-B identity header and 32-B response digest retained, the
input-only packet is 20,704 B and reply 20,736 B; including both 56-B frames, total
pipe traffic is 41,552 B. Use direct resident descriptors/events in the hot path:
no /tmp polling, fsync, new process, Python file relay or per-call artifact load.
Existing pure codecs/identity checks can inform the new contract, but their
original-output-containing packet and original-launch prerequisites must change.

Before publication, timeout/stale identity/incomplete response returns through
exactly one original H invocation with the original inputs untouched. After a
candidate is committed, never invoke original H as an apparent success fallback;
consumer/epoch failure fail-stops the owned window. Preserve the outer head
lifetime/overlap checks: paired rollback is insufficient after seed add. This is
a new private-hook replacement implementation, not an existing supported external
token-verifier API. If an owned direct-pipe H entry/return cannot be implemented
and reviewed, stop before another hardware cohort.

Sources: [original H always executes](C:/Projects/strix-alloy-clean/scripts/benchmarks/halogen0162_mtp_fc_quality_publish.c:633),
[shadow capture/publication](C:/Projects/strix-alloy-clean/scripts/benchmarks/halogen0162_mtp_fc_quality_publish.c:562),
[pipe contract](C:/Projects/strix-alloy-clean/scripts/benchmarks/halogen_mtp_fc_transport.py:13),
[resident relay scope](C:/Projects/strix-alloy-clean/scripts/benchmarks/halogen_mtp_fc_relay.py:1),
[response polling](C:/Projects/strix-alloy-clean/scripts/benchmarks/halogen0162_mtp_fc_quality_publish.c:523).

## Timing and reject rules

Start the useful timer before the H input readiness fence; stop only when the
original GPU consumer can read the replacement output. Include GPU-to-CPU copy,
framing/digests, pipe transit in both directions, Windows preparation and BO
copy/sync, all streamed-weight DMA/decode/compute, submit/wait, NPU output
sync/readback, CPU-to-GPU copy and output visibility. Report initialization
separately, including original-weight read/hash, lossless repack/inverse check,
weight BO copy/sync and configuration. Also report first-call cost and whole
cohort cost including preparation; any amortized result states the actual number
of uses. Retaining immutable weight BOs cannot exclude their per-call SRAM
streaming cost. Output/reference checks cannot hide required consumer work.

The retained original H device bracket is 0.158707124 ms; E is 0.152995063 ms.
The 0.487170-ms paired host bracket is not the H-only replacement budget. Even
using the H device bracket as a provisional conservative target, 77.183333 us
leaves only 81.523791 us for real arithmetic, traffic and transport. The specified
7,147,520 B would require about 87.67 GB/s in that entire remainder before any
compute/pipe cost. This is a required-rate calculation, not measured NPU bandwidth
or a proof of infeasibility. It makes full-matrix traffic and consumer latency
the decisive early source/measurement gates; the 150-us tiny-fixture gate is not
a real-component acceptance threshold.

Reject before new hardware if there is no reviewed skipped-original-H branch,
if the protocol still polls files/ms intervals, if emitted memory/finite schedule
does not fit, or if the original numeric gates fail. For execution, reject any
lost/stale/duplicate result, partial publication, fallback counted as NPU success,
original-H execution in a committed candidate call, hidden preparation/weight
traffic, or missing terminal cleanup. Require the complete H replacement to beat
a newly matched original H readiness-to-consumer bracket with the same input,
stream and visibility scope; if it does not, stop without a regular engine A/B.
If it does, only a bookended regular 8K engine comparison with unchanged output,
acceptance and head correctness can admit an optimization. No conversion from
component microseconds into token rates is permitted.

GPU reference: [retained component summary](C:/Projects/strix-alloy-clean/server/.local/optimization9h-20261004/alloy-fc-timing-f7c3c720f88f4edfaa0a1adcee68a56d/gpu-timing-summary.json).
ROOT remains the sole execution/lifecycle owner. The rejected ready-row consumer
and any external-token-proposer/verifier path are outside this design.
