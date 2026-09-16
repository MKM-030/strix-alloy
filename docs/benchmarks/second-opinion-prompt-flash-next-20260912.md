# Second-opinion prompt — Qwen3.8-Flash-Next optimization for REV:N on Strix Halo

Paste everything between the `=====` markers into the other model. It is self-contained.

=====

You are a senior local-inference engineer. I want an independent, skeptical review of an optimization
plan for running **Qwen3.8-Flash-Next** on one specific machine, plus concrete improvements. Do not be
agreeable — if something below is wrong, unmeasured, or a bad trade, say so and give the corrected
number or the missing measurement.

## The machine (fixed, cannot change)

- BOSGAME BeyondMax mini-PC. AMD Ryzen AI Max+ 395, Radeon 8060S iGPU (**gfx1151**, RDNA3.5).
- 128 GiB LPDDR5X unified memory (single pool; no separate VRAM — the "VRAM" is a firmware carve-out).
- Windows 11 host + WSL2 (Ubuntu-24.04). WSL sees `/dev/dxg` (NOT `/dev/kfd`); there is no Vulkan in
  WSL (only `lavapipe`), so GPU work in WSL goes through **ROCm/HIP over the DXG bridge**
  (`HSA_ENABLE_DXG_DETECTION=1` + ROCm 10 SDK libs from a vLLM/ROCm venv).
- Measured carve-out rule on this box: GPU device pool ≈ `64 GiB + ½ × carve-out`. With the firmware
  carve set to minimum (~512 MiB) Windows sees ~127 GB.

## The application (REV:N — a persistent AI-NPC layer for a GTA/FiveM server)

Load profile, all local, no cloud:
- **World Engine** — must run **permanently**, holds large world/scene context, so its real cost is
  **cold prefill over long context**, not decode.
- **Brain** — live NPC dialogue; hard requirement: **first token in a few hundred ms**. Currently
  `gemma-4-26B QAT q4_0` (~14 GiB, 31–56 tok/s). Quality already validated (16/16 German grounded test).
- **STT** (whisper/canary, ~1–2 GiB) and **TTS** (Qwen3-TTS ~4 GiB) always resident.
- A "Voice Studio" loads on demand.

So the World Engine must ideally share the 128 GiB with brain + STT + TTS.

## What we have already measured ourselves

- The **Halogen 27B** engine (`peonist-ai` closed `.hgn` engine, a different smaller model) runs in WSL
  via a custom `LD_PRELOAD` shim that supplies the engine's missing `hipHostRegister` fallback (the
  engine mmaps+registers the checkpoint; file-backed registration fails on DXG). With the shim: 23.9 t/s
  decode (MTP), prefill 482→228 ms.
- **llama.cpp HIP** builds and runs in WSL (a Qwen3.8-27B dense quant does 10.9–14.7 tok/s decode,
  300–400 prefill @4K).
- **MoE vs dense is the whole story here:** Ornith 35B-A3B (MoE, ~3B active) does 63–99 tok/s decode
  1,045–1,490 prefill; dense 27B does ~11–15 tok/s.
- 2 concurrent streams is the sweet spot; 4–8 saturate the GPU at ~120–128 tok/s aggregate.
- Windows VRAM formula observed: usable ≈ dedicated carve + ½ × system RAM.

## The plan under review (proposed)

**World Engine, two candidate shapes:**
1. **Halogen Flash-Next** — `.hgn` 115.55 GiB + 2.31 GiB quality overlay, run via `flash_serve` in WSL
   under the shim, `HALOGEN_FLASH_PIN_TRUNK=0` (no host pinning), minimum carve-out,
   `HALOGEN_KV_POOL_POSITIONS=524288`, `HALOGEN_KV_SLOTS=2`, `HALOGEN_CACHE_ENTRIES=6`. Claimed:
   ~1,300 t/s prefill @0 ctx, 250–380 @60k, 30–50 t/s decode. **Closed source. Single-stream-oriented.
   Does not stream thinking traces. Claimed to "run best on a host of its own."**
2. **llama.cpp Vulkan UD-IQ4_XS + MTP** (native Windows, not WSL) — `unsloth` UD-IQ4_XS ~87 GiB
   (3 shards) + Q8_0 MTP sidecar, `--fit on` (no explicit `-ngl`/`-c`), `--load-mode none` (keeps the
   26.8 GiB PLE table host-side), `-ub 256`, `--spec-type draft-mtp --spec-draft-n-max 3
   --spec-draft-p-min 0.75`. Claimed: ~200–430 prefill, ~38 t/s decode, ~74 GB footprint at 96 GB carve.
   Requires PR **#28243** (qwen4exp MTP) + **#28118** (Windows checkpoint) since MTP is not in mainline.

**Claimed tactics we plan to use:**
- MTP always (≈1.71× decode: 22.5 → 38.6 t/s).
- `reasoning_effort: medium` (not xhigh) — reported 2/3 vs 1/3 task success at 2.7× less wall time.
- Lazy/mmap n-gram loading so the 47.7 GiB lookup table pages from SSD.
- `-ot "per_layer_token_embd=CPU"` to force the PLE table off the GPU.
- Windows pagefile 163840 MB to raise the commit ceiling so the 262k-context profile fits.
- Keep brain = gemma4 (unchanged), STT/TTS unchanged.

## Hardware/OS levers reported by the community (to sanity-check)

- `amd_iommu=off` vs `iommu=pt`: **+26–32% prefill** on dense models, +2–8% on MoE, decode unaffected;
  but disables the NPU and DMA translation. (Native-Linux result; IOMMU is a kernel param, not a WSL one.)
- A local "UMA buffer" llama.cpp kernel patch reportedly took prefill from ~117 to ~208 t/s.
- NPU (FastFlowLM) can run a 35B-A3B *alongside* the GPU model at ~20 W, but needs IOMMU on and has no MTP.
- BIOS: UMA = Auto/minimum for the Halogen engine; Performance mode; one report recommends IOMMU disabled.

## Questions I want answered

1. **Which World-Engine shape is actually better for a permanently-resident long-context World Engine
   that must share the box with brain+STT+TTS?** Is the Halogen single-stream prefill advantage worth
   giving up co-residence and open source, or is the llama.cpp/MTP shape the right default?
2. **Will Halogen Flash-Next at 115 GiB + KV pool realistically coexist with gemma4 (~14 GiB) + STT
   (~2 GiB) + TTS (~4 GiB) in 128 GiB, or does it need a second machine?** Show the arithmetic.
3. **Is the MTP plan sound?** Any known correctness risk beyond the "temp>0 leaks CJK chars" report?
   Should depth be 3 or 4 for our mixed prose/world-context load?
4. **Is there a faster path we are missing** — a different quant (jcbtc CIRU-STRIX-IU4/Orca, agentionai
   ROCmFP4, Jab1718 Moe-slices), a different runtime, or the local UMA kernel patch? Rank by payoff/risk.
5. **For a long-context World Engine, what prefill/decode numbers should we actually require**, and how
   should we benchmark it (cold prefill at 8k/32k/64k, warm-cache reuse, TTFT) so the comparison is fair
   between the two engines?
6. **Anything in the plan that is a known trap** given `exactOptionalPropertyTypes`-style strictness is
   irrelevant here but correctness-of-output is not — e.g. does MTP at temp 0 truly preserve output, and
   does the closed Halogen engine's lack of thinking traces break agent harnesses badly enough to matter?
7. **What would you test first, in order, on this one box, to decide?**

Give: (a) a blunt verdict on each of the two shapes, (b) the corrected arithmetic for question 2,
(c) a prioritized improvement list with expected speedups and confidence, (d) anything you think is
outright wrong in the plan above.

=====
