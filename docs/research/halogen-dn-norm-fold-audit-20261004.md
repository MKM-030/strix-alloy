# HALOGEN_DN_NORM_FOLD static audit — 2026-10-04

Verdict: reject `HALOGEN_DN_NORM_FOLD=1` as a candidate for the pristine
v0.16.2 stock profile with prompt cache Off and PP8192. Stock already skips
the standalone gated RMS-normalization launch. Folding forces the general
DN implementation instead of stock fused16, without an additional kernel
or readback saving. No profile or hardware test was created for this flag.

Evidence is bounded CPU inspection of the pinned released executable,
`backends/halogen-wsl2-0.16.2/.local/flash_serve`, SHA256
`ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b`.
Addresses below are virtual addresses printed by llvm-objdump. Upstream
compute source is unavailable; this is static dispatch evidence, not a
measured performance or output-parity result.

## Actual folding mechanism

The fold getter at `0x1799e10` defaults to zero. Admission at
`0x1794825..0x179487a` requires norm-read mode 2, three intermediate buffers,
and the predicate at `0x18a8d40`. That predicate is a control-mode check:
`DN_SCAN=0`, `DN_S14=34`, and `DN_SCAN_UB=1`, all native defaults. It is not a
device-capability check. Norm-read global `0x18db578` is
`HALOGEN_DN_NORM_READ`, whose getter at `0x1799de0` defaults to 2; it is not
`DN_PREP_W`.

Fold1 populates the copied normalization arguments at
`0x17948d7..0x1794936` and marks normalization as produced. Its final general
read dispatch at `0x18ad488..0x18ad571` passes `DncNormFold` through helper
`0x18b4f10` to handle `0x18d8a88`, registered as
`k_dnc_scan3x<2,4,true,false,true,1,0,1,false>` (mangled-name string
`0x40f46`). This folds normalization into the final DN scan/read kernel.

The shared standalone-normalization skip is at `0x17952d2..0x17952e6`.
The skipped handles are `0x18d52d8` (`k_rmsnorm_gated_w`) and `0x18d52e0`
(`k_rmsnorm_gated`). Stock0 and fold1 both avoid the diagnostic readback:
the comparison kernel and 8-byte D2H copy at `0x17955be..0x1795664` belong
only to native fold mode 2.

## Why stock already saves that launch

`service.py:227` maps cache Off to `HALOGEN_PROMPT_CACHE=0`. Native startup
skips cache-object construction at `0x171a18d/0x171a215`. Engine initialization
zeroes checkpoint targets and active fields at `0x176b8af/0x176ba4f/56`.
The checkpoint setter is confined to cache-prefill; the cache-null serving
branch directly enters engine prefill via `0x1732750 -> 0x17e6050 ->
0x17dd020`. Active checkpoints are derived from the zero targets, so the
three `<=0` tests at `0x1794967/0x1794982/0x17949a0` pass.

Stock `DN_FUSED` defaults to 1. With fold disabled, its original norm output
pointer is zero and fused eligibility succeeds. `DN_FUSED_NORM` also defaults
to 1 (`0x179610d`, absent-value branch `0x1796485`). It populates normalization
arguments and marks normalization produced at `0x17949d9..0x1794a1d`, then
uses special fused16 helper `0x18c38f0` at `0x1794b26`.

Fold1 fills the norm output pointer before the eligibility test at
`0x179495c`. That test requires a null pointer, so fold1 routes instead to
general helper `0x18b6890`. Thus the change loses DN pipeline fusion while
retaining the normalization skip that stock already has.

## Numerical implication

This changes the DN implementation and its accumulation/reduction structure;
bitwise output parity cannot be inferred. Fold1 also passes an auxiliary
normalization buffer that stock fused norm sets to null. The native mode-2
word-comparison diagnostic reinforces the need to verify parity if this path
is ever tested for a workload where a distinct saving actually exists.

## Follow-up: actual Exact-cache p32768 article workload

This follow-up was requested after the Off PP8192 rejection. It separately
tests the hypothesis that Exact caching already forces general DN, making
fold1 useful without losing fused16. That hypothesis is disproved by the
retained configuration and static checkpoint setup; no fold1 execution is
being reported.

Executed stock evidence comes from
`server/.local/article0162-20261003/halogen-v2-c65536-p32768-lookup-stocka`
and `halogen-v2-c65536-p32768-lookup-stockb`. Both identities have profile
SHA256 `fbf9ef954f77fc491302dac4d3f45eff953925c9c31ae4016ac240212aa679c2`,
context 65536, Exact cache, depth 2, and no kernel overrides. Their retained
backend manifests (runs `1a7e40489cea4a38862da2d7f6b7bf45` and
`d13c01c17be648f59d5c1ff20aa49221`) set `HALOGEN_PROMPT_CACHE=1` and contain
no `HALOGEN_DN_*` overrides. Samples/logs report cold initial prompts of
32791/32792 tokens and warm follow-ups with `cache_n=32768`; native final
cache reports contain four hits, four misses, and two stores per run.

Exact policy 1 is stored on the cache object at offset `0x6c`
(`0x173bde6`). Cache-prefill loads that policy at `0x1750b52`. At
`0x1750b6d..0x1750b70`, it sets `R12B=(policy<2)`; for Exact, the branch at
`0x1750bbb` jumps directly to common prefill at `0x1750fb5`, bypassing the
checkpoint-target setter at `0x1750fad`. That is the setter's sole direct
call. Checkpoint setup is therefore a Flexible-policy operation, not an
Exact-policy operation.

The common Exact route calls engine prefill at `0x1750fc6`. Native chunk
entry explicitly clears active checkpoint fields and only repopulates them
from positive, in-chunk, 64-aligned targets (`0x17dd0ee..0x17dd17d`). Since
Exact never sets the initialized-zero targets, both cold and warm Exact
prefill keep these fields zero. The bounded cache-routine audit found no
direct writes of the target/active fields in cache restore paths. The warm
`cache_n` counter describes token/state reuse; it does not imply internal
DN checkpoint taps. Exact also skips the Flexible checkpoint reset and
stash handling after the common prefill.

With no DN overrides, stock's checkpoint eligibility thus still passes and
default fused norm already skips standalone normalization for the actual
32K workload. A controlled fold1 Exact32K trial is not justified by a
distinct launch saving. Folding would again force the general DN route.

This conclusion is scoped to the retained Exact policy and native defaults.
It does not assert that folding is universally useless. A workload already
using general DN with a standalone norm launch could have a real folding
opportunity; such a workload has not been demonstrated here. If one is
later established, validation should cover cold output parity and warm
restored DN state, since changing DN arithmetic can change cached recurrent
state, logits, greedy output, or speculative acceptance even when visible
answers look plausible.
