You are reviewing a performance-engineering effort on ONE machine and must find the real bottlenecks
and the way forward. Be concrete and numeric. Challenge my reasoning where it is weak.

## The goal
Qwen3.8-Flash-Next (qwen4exp MoE, 177B total / ~6B active, 512 experts top-k=10 + shared, 48 layers,
hybrid 36 GatedDeltaNet + 12 full-attn, hyper-connections, 160-dim per-layer embedding with a
26.82 GiB n-gram PLE table, vocab 248,320). Target: beat the published figures on this hardware class:
  - Halogen (closed, native Linux, own 4-bit .hgn + own quant): prefill 1246/1423/1358 t/s @8k/32k/131k; decode 25.4 t/s serial, 42-45 t/s with both drafters
  - pwilkin strix-halo fork (native Linux, IQ4_NL 93 GiB, ub 16384): prefill 1204 t/s @0k, 1086 @40k; decode 26.28 @0k, 16.63 @40k
  - vincentkelleher / drluoto Vulkan + FR-Spec MTP (Windows): 35.8/36.7/33.5/25.7 t/s decode @0/8k/32k/128k; prefill 570/506/405/231

## The hardware / runtime constraints (fixed)
- Bosgame M5: Ryzen AI Max+ 395, Radeon 8060S iGPU gfx1151 (RDNA3.5 wave32, 40 CUs), 128 GB LPDDR5X (~200-240 GB/s usable), 128 GB unified.
- Windows 11 + WSL2. In WSL: HIP over /dev/dxg ONLY (no /dev/kfd, no PM4 replay). Weights are UMA (host RAM).
- **Current firmware carve = 32 GB dedicated.** Observed device/GPU pool = **79.82 GiB** (Vulkan sees 81739 MiB; rule of thumb pool ~= 64 GiB + carve/2).
- WSL memory cap 86 GB. One heavy engine at a time.

## Engines available (all built/staged locally)
1. **Way 1**: C:\AI\runtimes\strix-vulkan-ba5354d\llama-server.exe = drluoto strix-halo-vulkan @ba5354d46 (Vulkan/RADV). Supports FR-Spec vocabulary-trimmed MTP head (output.weight 2560x65536 + d2t map). Runs native Windows.
2. **Way 2**: /home/revn/strix-llama = pwilkin strix-halo HIP @f5daaa3c (has tiled GDN, QSA sparse attn, HC fusions, bf16-WMMA "MMB" prefill path [LLAMA_MMB=1, default OFF], lazy PLE reader).
3. **Way 3**: /home/revn/drluoto-llama = drluoto HIP branch @590ac45b.

## Quants / heads
- unsloth UD-IQ4_XS: 87.24 GiB total, 4.235 bpw; attention/GDN projections are Q8_0; experts IQ3_S gate/up + IQ4_NL/Q8_0 down; PLE table IQ4_NL 26.82 GiB paged. Resident ~60.4 GiB.
- ilintar IQ4_NL "PROJFIX": 93.16 GiB total, 4.523 bpw; ALL tensors IQ4_NL incl. attention/GDN. All 48 layers uniform 1350 MiB experts. Resident ~66.34 GiB. This is exactly what the pwilkin author used for 1204 t/s.
- FR-Spec MTP head: 3.39 GiB, 65k-vocab draft + d2t; plain MTP head 4.14 GiB (full 248k vocab).

## MEASURED results (token-exact prompts sized by /tokenize, cache_prompt=false, gen 64-128, this box, 32 GB carve)

Way 2 (pwilkin HIP) + PROJFIX, ub 8192, ctx 49152, -fit off, f16 KV, --lazy-mode on-direct:
  + LLAMA_MMB=1 : prefill 364 @1k / 460-525 @8k / 381 @32k ; decode 21.7 @1k / 17-19 @8k / 10.0 @32k
  MMB off       : prefill 324 @1k / 325-364 @8k / 316 @32k ; decode 20.6 / 13-19 / 11.5
Way 2 + unsloth UD-IQ4_XS + MMB=1, ub 8192: prefill 155-380 (unstable) @8k, 206 @32k; decode 12-14. WORSE and unstable.
Way 2 + UD-IQ4_XS, ub 16384 (fits: UD is smaller): prefill 379 @8k; decode 12.9.
Way 1 (Vulkan) + UD-IQ4_XS + FR-Spec MTP depth3: prefill 288-314 @1k / 360-366 @8k / 271 @32k; decode **29.3-30.6 @1k / 17.8 @8k / 20.0 @32k**
Way 1 no-spec: decode 18.5-19.2 @1k  => MTP = 1.6x decode.
Way 3 (drluoto HIP) + UD + plain MTP: (still running)
Draft acceptance is content-dependent: 73% @1k, 33% @8k, 54% @32k (same model). First bench rep is always low (cold), reps 1-2 steady.

## The memory arithmetic I derived (verify it)
Pool 79.82 GiB - PROJFIX resident 66.34 = 13.48 GiB for KV+compute. KV f16 @49k + GDN state ~1.23 GiB
=> compute budget ~12.25 GiB. Measured: `-ub 16384` needs 14.05 GiB -> ALLOCATION FAILS.
`-ub 8192` needs ~7.03 GiB -> OK. The author's config is `-b 16384 -ub 16384`. So at 32 GB carve we
CANNOT run his ubatch; raising carve to 48 GB (pool ~= 88 GiB) would make it fit.

## My open questions — answer each with numbers and a recommended experiment

1. **The prefill gap.** We get 525 t/s @8k with ub 8192; the author gets 1204 t/s with ub 16384 on the
   same quant + same branch (native Linux, ~120 GiB pool, custom ROCr/PM4 retained runtime). Is going
   8192 -> 16384 ubatch plausibly worth 2.3x, or is most of the gap something else (WSL/DXG overhead,
   graph capture, kernel saturation, GTT mapping)? Estimate the ubatch scaling curve for a compute-bound
   WMMA GEMM on 40 CUs and tell me what fraction of 2.3x it can explain. What is the single best
   diagnostic and the realistic WSL ceiling?

2. **Would the 48 GB carve actually get us near 1204?** Give a prediction with reasoning. If not, what
   else must change?

3. **Can PROJFIX + FR-Spec + LLAMA_MMB=1 coexist on ONE engine?** Today: pwilkin fork has MMB+PROJFIX
   but REJECTS FR-Spec (`output.weight` expected 2560x248320, got 2560x65536); Vulkan accepts FR-Spec
   but has no MMB and OOMs on PROJFIX at this carve. Sketch the exact code port needed (d2t/t2d vocab
   mapping in the draft path — where does it live in the Vulkan fork?). Is it a small patch?

4. **Multiple drafters.** The pwilkin fork's spec types are a vector (draft-mtp, draft-dflash,
   draft-eagle3, draft-dspark) plus an n-gram lookup cache. Would chaining e.g. draft-mtp + lookup help
   decode here? Quantify: with acceptance a at depth d, expected accepted tokens per target pass, and
   what the target-pass cost is. Is the 512-expert MoE expert-union the limiter (E[union of d tokens of
   top-10 of 512])? Recommend a concrete depth/chain.

5. **Decode headroom.** We see 30 t/s @1k (Way 1, MTP) and 20-22 (Way 2). Active weight bytes/token (k=10)
   = 5.84 GB (UD) / 4.61 GB (PROJFIX). At 200-240 GB/s that is a floor of ~20-29 ms => ~34-49 t/s.
   Where are the missing ~20 ms at @1k? What gets us from 30 to 40+?

6. **Anything I am getting wrong** in the above model, the measurements, or the plan.

Answer concisely, organized by question, with numbers. Cite specific kernel/format facts where relevant.
