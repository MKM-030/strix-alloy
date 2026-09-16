You are reviewing a performance program and must produce the PLAN + STRATEGY that gets the best prefill and decode on ONE machine. Be concrete, numeric, and decisive. Where my reasoning is weak, say so and correct it.

## Machine (fixed)
Bosgame/Corsair Strix Halo: Ryzen AI Max+ 395, Radeon 8060S gfx1151 (RDNA3.5, wave32, 40 CU, 2 MiB L2, 32 MiB MALL), 128 GB LPDDR5X (256 GB/s theoretical, ~221-234 GB/s practical), Windows 11 + WSL2 (HIP over /dev/dxg only; no /dev/kfd; UMA so weights live in host RAM). Current carve 32 GB -> device pool 79.82 GiB. WSL cap 86 GB.

## Model
Qwen3.8-Flash-Next (qwen4exp MoE, 177B total / ~6B active, 512 experts top-k 10 + shared, 48 layers, 36 GatedDeltaNet + 12 full-attn, hyper-connections, 26.82 GiB n-gram PLE table paged from disk, vocab 248320).

## THE AUTHORITATIVE RESULT (this changes everything)
The fork author (ilintar/pwilkin) just published on r/StrixHalo: **1204 t/s prefill @0 depth, ~1100 @40k, ~850 @150k; ~30 t/s decode**, on his strix-halo llama.cpp branch + custom IQ4_NL "PROJFIX" quant + custom MIT/HIP build using retained PM4 replay. Separately, olliehm ported the SAME branch to Windows/TheRock ROCm 10.1/Clang 23 and measured **964-1045 t/s prefill with the STOCK unsloth UD-IQ4_XS quant** (not even PROJFIX), 262144 ctx, `-b/-ub 8192`, `--load-mode none`, NO custom runtime, NO lazy-direct -- with ALL 35 launcher env gates ON except ONE: `LLAMA_MMB_HC16=0` (that gate alone corrupts output on Windows; its ablation value is only 1.08x). All gates OFF gives only ~418 t/s. So the gates are what buy ~2.3x, and they work on Windows.

Also from issue #24 + PR #28118: MTP without on-device speculative recurrent-state checkpoints is a net LOSS (77-79% acceptance but only ~24 t/s decode, vs ~34-38 t/s with device checkpoints, vs 6.2 t/s when host checkpoints dominate an ~825 ms round). PR #28118 is 8 lines: OR LLAMA_STATE_SEQ_FLAGS_ON_DEVICE into the speculative ckpt update/load for target+draft.

Reference: hipEngine RDNA3 tuning guide (shisa-ai) says llama.cpp HIP leaves most threads idle in its GEMV loops (e.g. Q4_K ncols=512 uses 32 of 256 threads), recommends wave32 coalesced packed loads + multiple accumulators, K-dependent workgroup sizing (K=512->64 threads, K=2048->128), vec4->vec8 unroll (+42%/+8%), LDS only when it earns barriers, and notes MoE grid reshape to (packs, experts) measured 59% SLOWER; also grid.sync ~1us, and speculative decode on a 35B-A3B measured eta=0.736 running 0.7-0.85x its own AR baseline.

## What I measured on this box (32 GB carve, token-exact prompts)
- pwilkin HIP + PROJFIX, ub 8192, ctx 49152, MMB=1: prefill 364@1k / 460-525@8k / 381@32k; decode 21.7@1k / 17-19@8k / 10.0@32k
- same, MMB off: 324 / 325-364 / 316; decode 20.6 / 13-19 / 11.5
- pwilkin HIP + UD-IQ4_XS + MMB=1: prefill 155-380 (unstable), 206@32k
- Vulkan (drluoto ba5354d) + UD + FR-Spec MTP d3: prefill 288-314@1k/360-366@8k/271@32k; decode 29.3-30.6@1k/17.8@8k/20.0@32k. No-spec decode 18.5-19.2. So MTP=1.6x there.
- drluoto HIP + UD + plain MTP: decode 6.8 t/s (this matches the "host checkpoint" 6.2 t/s case exactly -> the fork lacks PR#28118)
- Memory: pool 79.82 - PROJFIX resident 66.34 = 13.48 GiB for KV+compute; ub16384 needs 14.05 -> fails. So at 32 GB carve the author's ub 16384 cannot run; ub 8192 fits.
- Also: the fork's 35 gates are real and I now have the complete list from the source. MMB kernels exist but I could not confirm from logs that they fire (their markers never appeared) -- possibly they only print under LLAMA_MMB_CVT_LOG, or the gate combination matters.

## What I have already built this session
- Ported FR-Spec `d2t`/`t2d` draft-vocab trim into the pwilkin fork's `src/models/qwen4exp.cpp` (loader + MTP graph builder), so the HIP fork can load the 65k-vocab FR-Spec head that previously only Vulkan accepted. Builds clean.
- Ported PR #28118 (speculative checkpoints -> ON_DEVICE) into the same fork's server (`tools/server/server-context.cpp`), 6 call sites. Builds clean.
- Full token-exact benchmark harness (fnbench.py) and a gate-launcher script.

## QUESTIONS -- answer each with numbers and a decision

1. **Prefill strategy.** Given the 964-1045 t/s Windows result with stock quant + gates, what is the highest-probability path to the best prefill on THIS box: (a) run the 35 gates at the 32 GB carve and accept ub 8192, (b) raise the carve to 96 GB (like the author and olliehm both did) so ub 16384 fits, or (c) something else? Quantify the expected gain from each. Note the carve is a founder/BIOS action.

2. **Decode strategy.** The best decode I have is 30 t/s (Vulkan+FR-Spec). The author gets ~30 t/s, and with device-checkpoint MTP ~35-41, and 56 t/s on code at n-max 6. Given I have BOTH the FR-Spec port and the PR#28118 port in the HIP fork (but they are untested together, and PROJFIX+FR-Spec may not fit memory at 32 GB carve), what decode plan do you recommend and in what order? Is Vulkan+FR-Spec the better decode, or HIP + FR-Spec + MMB + PR#28118 once the carve is raised?

3. **Can all three coexist?** PROJFIX (best prefill layout) + FR-Spec (best decode draft) + the 35 gates/MMB (best prefill kernels) + PR#28118 (best decode checkpoints) on the pwilkin HIP fork. What will break, what must be verified, and what is the memory arithmetic at 96 GB carve? Give the expected combined numbers.

4. **The 512-expert MoE + speculation.** With top-k=10 of 512 and depth-d drafting, E[union] = 512(1-(1-10/512)^d): d=1 ->10, d=2 ->19.8, d=4 ->38.8, d=6 ->57.7. Per accepted token, expert bytes scale as union/d: 1.00, 0.99, 0.97, 0.96. Is there a strong reason to prefer depth 4 (author's default) vs 6 (56.6 t/s on code in PR#28118) here? What is the real limiter for decode -- expert-union bytes, GDN recurrence serialization, or acceptance rate?

5. **What am I still missing?** In particular: (i) is my "MMB kernels never fired" observation a real failure or a logging artifact, and how do I check definitively? (ii) The QSA-lightning-indexer for decode is the author's stated next goal ("Next goal: QSA for decode") -- what does that imply for us? (iii) Any high-value kernel work (per hipEngine: GEMV workgroup sizing, vec8 unroll, L2/MALL policy, avoiding the 59%-slower MoE grid reshape) that beats just using the gates?

6. **The cheapest 80/20 plan.** If you had 6 more hours on this box and one founder action available (a carve reboot), write the exact ordered checklist: what to run, in what order, with which gates/flags/quant/head, and the expected t/s at each step, plus the abort condition for each step.

Be specific about env vars, flags, and file paths. Prefer measured numbers over speculation, and flag clearly which of your numbers are estimates.
