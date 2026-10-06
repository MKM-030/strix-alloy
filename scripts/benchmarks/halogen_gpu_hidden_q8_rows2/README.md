# Compact Q8 H with two rows per lane group

This default-off source candidate processes two output rows sequentially per
16-lane group and reuses each chunk's eight X vector loads. It retains original
2720-byte Q8 rows; no expanded weights, host bridge or extra recurrent launch.
Launch is grid80/block256/wave32/LDS0/stream0, fixed K=N2560/M4. Every output row
is assigned once. Native packed BF16 DOT2 pair order, ten separate chunk ADDs,
XOR8/4/2/1 reduction and final BF16 RNE remain explicit.

FP16 scale/bias convert exactly to FP32. Explicit native FP32 FMA implements
the finite affine result; its equivalence argument is in
[the retained arithmetic audit](../../../docs/research/halogen-native-fc-accumulation-20261004.md).
Device float mode must match nearest-even/preserved denormals. Source semantics
are not a numerical qualification: emitted arithmetic and original GPU frozen
output parity still need checking at unchanged tolerances.

The source halves waves1280->640 and issued X load instructions102400->51200.
Unique X remains20480 bytes, so these are issue/operand counts, not saved DRAM
traffic. X liveness and eight running sums can raise register pressure, while
fewer waves can reduce latency hiding. Offline emission must verify vector loads,
no spills, native DOT2/ADD order, float mode and wave32 before a hardware screen.

This GPU candidate addresses MTP Decode H only, not ordinary Prefill. Exact
arithmetic intends unchanged proposals, not increased acceptance. CPU/NPU
offload would add crossings to this existing device-resident boundary; prior
complete NPU H calls were slower and remain disabled. Actual engine Prefill,
Decode and acceptance benefit is unmeasured and cannot be inferred from counts.
No compiler, hardware, model or lifecycle operation is triggered by these files.

Offline emission was checked against the source/build hashes: gfx1151 wave32,
40-byte W/X/Y/K/N arguments, 80 VGPR, no spills, private storage or LDS, float
mode0xf0. The loop contains eight X and two weight128-bit loads, two packed
affine32-bit loads, 64 native BF16 DOT2 instructions and 32 native affine FMAs.
This confirms the intended issue count, not a speed improvement. Independent
source review found no fixed-shape bounds or arithmetic-order defect; original
hardware output equality was subsequently verified for all40 timed outputs.

The finite paired screen uses one same-arm priming launch to a separate scratch
output immediately before each single timed launch. The timed output is poisoned
outside its event bracket. Four warmup pairs are excluded; sixteen measured pairs
balance both original/candidate order and frozen A/B inputs. Each timed output
must match its original frozen hash exactly. Report first/second-arm strata;
priming reduces the prior DPP screen's order confound but does not establish that
all hardware/cache/clock effects are eliminated.

The [completed screen](../../../docs/research/halogen-gpu-hidden-q8-rows2-screen-20261006.md)
measured original mean130.425 microseconds and candidate133.050 (+2.012%).
Only3/16 measured pairs favored the candidate; both arm-order means favored
the original. No component advantage is demonstrated. This candidate stays
disabled; do not repeat the unchanged screen or infer a serving tok/s gain.
The original server was restored and verified ready/open afterward.
