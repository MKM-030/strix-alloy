You are a senior performance engineer reviewing an ongoing program. I need you to (a) audit my findings
and reasoning, (b) answer four specific architecture questions below, and (c) give a decision-grade plan.

Be numeric, decisive, and correct me where I am wrong. Clearly label [MEASURED] vs [ESTIMATE].

## MACHINE (fixed)
Bosgame/Corsair Strix Halo: Ryzen AI Max+ 395, Radeon 8060S iGPU gfx1151 (RDNA3.5, wave32, 40 CU,
2 MiB L2, 32 MiB MALL), 128 GB LPDDR5X (256 GB/s theoretical, ~221-234 practical).
Windows 11 + WSL2: HIP over /dev/dxg ONLY (no /dev/kfd, no PM4 replay, no Vulkan in WSL).
UMA: weights live in host RAM. Firmware carve currently 32 GB -> device pool 79.82 GiB. WSL cap 86 GB.
IMPORTANT: the WSL VM has hard-restarted ~6 times during heavy PROJFIX runs; dmesg shows
`dxgkio_wait_sync_object_cpu: Ioctl failed: -512` and `dxgkio_escape: Ioctl failed: -75`.

## MODEL
Qwen3.8-Flash-Next (qwen4exp MoE): 177B total / ~6B active, 512 experts top-k 10 + 1 shared, 48 layers
(36 GatedDeltaNet + 12 full-attn), hyper-connections (4 streams), 26.82 GiB n-gram PLE table paged from
disk, vocab 248320, native ctx 262144.

## TARGETS (official published, same hardware class)
- ilintar/pwilkin (fork author), native Linux + custom quant IQ4_NL "PROJFIX" + custom HIP/ROCr build with
  RETAINED PM4: **1204 t/s prefill @0 depth, ~1100 @40k, ~850 @150k; ~30 t/s raw decode; "MTP may vary".**
  His stated next goal was "QSA for decode".
- olliehm (Windows port of the same branch, stock unsloth UD-IQ4_XS, TheRock ROCm 10.1, Clang 23, no custom
  runtime, 96 GB carve): **964-1045 t/s prefill** with all 35 launcher env gates ON except
  LLAMA_MMB_HC16=0 (that one gate corrupts output on Windows; worth only 1.08x). All gates OFF = ~418 t/s.
  MTP: 77-79% acceptance but only ~24 t/s decode without on-device spec checkpoints.
- Halogen 0.8.1 (closed, native Linux, BYO-GGUF): prefill within 1% at 8k/32k; decode 25.4 t/s serial,
  42-45 with both drafters; vs llama.cpp same file: prefill 1.9x @8k / 2.7x @32k.
- kingjones30/ROCmFPX (Heretek-AI/ROCmFPX-BUILDER, prebuilt Windows+Linux binaries w/ bundled ROCm 7,
  natively supports qwen4exp): claims **345 t/s prefill / 22.6 t/s decode**.
- q38rocm (same builder, 27B): 30.56-36.04 t/s via MTP K=4-6; states **Vulkan0/RADV coopmat unlocks
  34-36 t/s while ROCm HIP caps MTP at ~28**; and **Asymmetric TurboQuant KV (-ctk q8_0 -ctv turbo4)
  compresses 262K context KV from 61.4 GB to 20.08 GB**.

## MY MEASURED RESULTS THIS SESSION (all token-exact: prompts sized via /tokenize, cache_prompt=false)
Machine: WSL/DXG, pwilkin HIP fork. Quant: unsloth UD-IQ4_XS (60.4 GiB resident) or ilintar IQ4_NL
PROJFIX (66.34 GiB resident). All at 32 GB carve.

| Config | prefill @1k / @8k / @16k / @32k | decode @1k / @8k / @32k |
|---|---|---|
| pwilkin HIP + UD, no gates | 324 / 325-364 / - / 316 | 20.6 / 13-19 / 11.5 |
| + LLAMA_MMB=1 only | 364 / 460-525 / - / 381 | 21.7 / 17-19 / 10.0 |
| PROJFIX + partially-guessed gates | 503 / 578-618 / 568 / 466-479 | 21.4 / 19-21 / 13-18 |
| **PROJFIX + AUTHOR-EXACT gates, ub 8192** | 565-585 / **646-839** / 747-827 / 714-778 | 19.4-21.0 / 15.8-16.8 / 10.9-12.7 |
| **PROJFIX + AUTHOR-EXACT gates, ub 16384** | - / 604-818 / **705-870** / **731-834** | - / 15.5-17.0 / 10.7-13.0 |
| UD stock + author gates, ub 8192 | ~513 / ~661 / ~680 / ~693 | ~13 / 13-15 / ~11 |
| **Vulkan (Windows, native) + UD + FR-Spec MTP d3** | 288-314 / 360-366 / - / 271 | **29.3-30.6** / 17.8 / 20.0 |
| same, NO MTP | 323-334 / - / - / - | 18.5-19.2 |
| UD + no gates + plain MTP head (spec WORKS) | 243-289 | **18.0-19.3** (48-58% accept) |
| drluoto HIP + UD + plain MTP | 161 / - | **6.8** (host-checkpoint pathology) |

Other measured facts:
- I found the author's REAL gate launcher on disk (/home/revn/pwilkin/install.sh): the gates use specific
  NUMERIC values I had guessed wrong -- LLAMA_MMB_TALL=2 (I guessed 1), LLAMA_MMB_F32SPLIT=2, LLAMA_MMB_HC16=2,
  LLAMA_MMB_SHADOW=2, LLAMA_QSA_QUERY_STRIP=512 (a tile WIDTH, not a flag), plus 6 gates my grep missed
  (LLAMA_QSA_SCORE_BOUNDS, LLAMA_QSA_COMPACT_METADATA, LLAMA_QSA_NO_DENSE_MASK, LLAMA_QSA_FA_V3,
  LLAMA_HC_PACK_DI, LLAMA_MTP_QSA_MIN_T=128). Reproducing them gave the +138% prefill jump.
- With author gates the MMB kernels CONFIRM to fire: `MMB_GLU fused gate/up+swiglu`,
  `MMB_BLK16 dense BF16 in place`, `MMB_DOWN16 routed down BF16 in place`,
  `MMB_TALL(wide 384x64) dense M=324 K=10240 T=8188`, `QSA_SCORE_BOUNDS active ... mean=1135 (55% of full)`.
  My earlier "MMB never fires" claim was a logging/gate-value artifact.
- ub 16384 DOES fit at 32 GB carve with PROJFIX + gates at ctx 49152 (contradicting my earlier arithmetic).
- FR-Spec head does NOT load on the pwilkin HIP fork: it uses drluoto's MTP tensor naming
  (fc_embd/fc_hidden/hc_down/hc_up/hc_norm) instead of eh_proj/hc_head_*; blk.48.nextn.eh_proj.weight missing.
  I ported the d2t/t2d vocab-trim logic into the fork's src/models/qwen4exp.cpp (builds clean) but the tensor
  NAMING is a separate port.
- I ported ggml-org PR #28118 (speculative recurrent-state checkpoints -> LLAMA_STATE_SEQ_FLAGS_ON_DEVICE)
  into tools/server/server-context.cpp (6 sites; builds clean). Untested together with the gates.
- GATE + MTP ARE MUTUALLY EXCLUSIVE on the f5daaa3c fork: with author gates AND -md (any MTP head) the
  draft-load path SPINS at 100% CPU with RSS frozen forever. Gate-family bisect [MEASURED]:
  MMB family + MTP = LOADS AND WORKS (20 t/s, 63% acceptance); HC family + MTP = FAIL; QSA family + MTP = FAIL;
  NORM family + MTP = FAIL. (NOTE: each "FAIL" may also have been the VM restarting; 12 dxg errors seen.)
- The author's strix-halo branch is 7 commits AHEAD of our f5daaa3c. New commits:
  d67d5883 "hip: enable sparse QSA decode and incremental indexer state" (his stated decode goal, DONE),
  0f295019 "qwen4exp: skip unused HIP decode indexer work",
  ac1ebb4e "strix: compile in the tuned defaults and drop the env gating" -- THIS REMOVES ALL 53 GATES and
  bakes in the measured-optimal values (his words: the 30-line export block was "something anybody could get
  subtly wrong"; e.g. `bool mmb_enabled() { return true; }`). So the gate exercise is now obsolete.
  I built d67d5883 successfully but have not yet obtained numbers from it (the VM restarted during the run).
- pwilkin/rocm-systems@ilintar-experiments contains the retained-PM4 runtime work:
  "hip: add retained PM4 graph command lists", "ROCr: fix gfx1201 retained PM4 register programming",
  "hip: fix quadratic case, optimize memory usage". This is ROCr/HIP runtime code -> needs /dev/kfd -> native
  Linux only, NOT usable on WSL/DXG.

## MY PLAN (audit this)
Layer 0: try ready-made binaries (kingjones30/ROCmFPX natively supports qwen4exp; charlie12345/ROCmFPX).
Layer 1 (prefill): author-exact gates + PROJFIX at ub 16384 (measured 870 @16k); then native Windows build;
  then carve 96 GB for 262k ctx. Do NOT port retained PM4 or rewrite kernels.
Layer 2 (decode): use VULKAN/RADV + FR-Spec MTP (measured 30 t/s) since Vulkan>HIP for MTP; on HIP wire the
  spec checkpoints properly; QSA decode now exists upstream (d67d5883) - measure it.
Layer 3 (capacity): TurboQuant KV to shrink 262k KV 61->20 GB (but the fork has NO turbo KV types - verified).
Layer 4: kernel work last (Amdahl-bounded).

## THE FOUR QUESTIONS THE FOUNDER ASKED ME -- answer each concretely

**Q1. Combined engine.** Can we build ONE engine that takes prefill from the fast side and decode from the
other? Concretely: HIP gives 870 t/s prefill, Vulkan gives 30 t/s decode. Options: (a) one binary with both
backends selectable per-phase, (b) actual mid-request handoff (prefill on HIP then decode on Vulkan),
(c) run two engines and route by request type. What is achievable and what is the cost? Note the KV cache and
recurrent/GDN state are device-resident and backend-specific - quantify what a handoff would have to move
(kv bytes at 32k/128k ctx, GDN state size) and whether it is worth it. Give a recommendation.

**Q2. Why WSL at all?** We measured HIP-in-WSL at ~70-75% of olliehm's native-Windows HIP (660-698 vs 964-1045
with the same quant/gates). Vulkan runs natively on Windows and already gives our best decode (30 t/s).
What exactly does WSL cost us, and is there any remaining reason to use WSL for this workload? What would a
pure-native-Windows HIP build (TheRock/Clang, as olliehm did) require from us, and what is the realistic gain?

**Q3. Own fork + own quants (like Halogen's BYO-GGUF).** Is creating our own fork/quant worthwhile?
Consider: (i) Halogen's BYO-GGUF value is that its kernels read the GGUF's quantized values "moved, not
requantized" into its own layouts + a repack cache - i.e. the win is LAYOUT, not a new quant; (ii) we already
have PROJFIX (all-IQ4_NL) which beat UD-IQ4_XS by 15-20% here; (iii) is a genuinely different quant (fp8,
NVFP4-codebook like halogen's q4c, Hadamard-rotated int4 like its i4l) a realistic prefill/decode win, or is
layout the whole game? Give expected gains and effort, and say plainly whether we should do it.

**Q4. Is TurboQuant something like BYO-GGUF?** Explain what TurboQuant KV actually is (asymmetric q8_0 K /
turbo4 V), how it differs from a weight-quant format, what it would buy us (I measured our fork has NO turbo
types - it would need kernels), and whether it improves prefill, decode, or just capacity. Should we chase it?

## ALSO
- Audit every claim above. Which of my conclusions are solid, which are likely wrong, and what single
  measurement or experiment would most improve the final answer?
- Given the VM restarts (6 of them), is my "two-engine, native-Windows" recommendation the right risk posture?
- If you had the next 6 hours and one founder action (a BIOS carve change + reboot), what is the ordered
  checklist with expected t/s at each step?
