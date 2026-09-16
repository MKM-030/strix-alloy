# Flash-Next on Strix Halo: the plan and strategy for best prefill + decode (2026-09-14)

Synthesized from: this session's measurements; ilintar's r/StrixHalo announcement + comments; olliehm's
Windows port and issue #24; the shisa-ai hipEngine RDNA3 tuning guide; ggml-org PRs #28118/#28123;
and a Codex Astra review of all of the above. Written for the founder to decide the one reboot action.

---

## 0. The decisive intelligence (this reframes the whole effort)

**The fork author (ilintar/pwilkin) published the reachable target and how he got it** (r/StrixHalo,
2 days ago, "Qwen3.8 Flash Next, the optimized config (1.2k t/s prefill!)"):

- **1204 t/s prefill @0 depth · ~1100 @40k · ~850 @150k · ~30 t/s raw decode** on his `strix-halo`
  branch + custom IQ4_NL "PROJFIX" quant + custom HIP build with retained PM4.
- His own words: retained PM4 gives "faster generation speeds (and some small prefill benefits...for
  mysterious reasons)" — **PM4 does not engage during prefill measurement**; prefill wins are kernel
  work. He also states his next goal is **QSA for decode** (decode is the unfinished half).
- He published the full journey + reproduction data at https://pwilkin.github.io/strix-halo.

**And it is already reproduced on WINDOWS, without any custom runtime**, by olliehm's group
(issue #24 + `github.com/olliehm/qwen-flash-next-windows`):

- Same branch, TheRock ROCm 10.1 SDK, Clang 23, stock runtime, no retained PM4, no lazy-direct,
  **stock unsloth UD-IQ4_XS (not even PROJFIX)**.
- **964–1045 t/s prefill** at 262144 ctx, `-b/-ub 8192`, `--load-mode none`, with **all 35 launcher
  env gates ON except one: `LLAMA_MMB_HC16=0`**. All gates OFF = only ~418 t/s.
- The single corrupting gate is `LLAMA_MMB_HC16` (bf16 HC streams end-to-end), worth only 1.08× per
  the author's own ablation. Bisected precisely: corruption needs MMB+HC together; HC16=0 is fully
  clean (verified at 2k/8k/16k + exact 24k needle).
- **`-b 512 → 2048` alone was +20–40% prefill** with no ill effects at 262k ctx.

**So the 964–1045 t/s class is reachable on Windows with our exact model and no custom runtime. My
session measured 300–525 t/s because the gates were never enabled** (they are all default-OFF, and
the author's installer sets them in a launcher I had not located).

## 0b. Round-2 intelligence (later 2026-09-14): ready-made engines + new levers

### Ready-made binaries that already support OUR model

**Heretek-AI/ROCmFPX-BUILDER** ships automated builds of four engines with **bundled ROCm 7 runtime
libraries and portable `$ORIGIN` RPATHs — no ROCm SDK or driver install needed, Windows and Linux**:

| Engine | Relevance to us |
| --- | --- |
| **kingjones30/ROCmFPX** | **Natively supports `qwen4exp` = Qwen3.8-Flash-Next**, published at **345 t/s prefill / 22.6 t/s decode** in their own table. Also ROCmFP4/ROCmFP8 native tensor types across 7 architectures. Ubuntu binaries for gfx1151; b1038 has a **windows** artifact. |
| **charlie12345/ROCmFPX** (upstream) | Multi-arch HIP (RDNA2/3/3.5/4 + CDNA), standard MMQ/MMVQ dispatch. Ubuntu + Windows builds. |
| **ciru-ai/ROCmFPX** | Low-bit layouts (ROCmFP2/3/4/FAST/6/7-DualView/8), **ActiveFPX PromptForge with fused projections on gfx1151**, DualView Q7+Q8 shadow. |
| **julianmb/q38rocm** | 27B-focused Strix Halo stack: **30.56–36.04 t/s via MTP K=4–6**, and **Asymmetric TurboQuant KV (`-ctk q8_0 -ctv turbo4`) compressing 262K context from 61.4 GB → 20.08 GB**. |

**Three transferable techniques from these engines:**

1. **Vulkan/RADV beats ROCm/HIP for MTP decode.** q38rocm: "Vulkan0 (Mesa RADV Wave64 cooperative
   matrix KHR_coopmat) unlocks 34–36 tok/s with MTP; **ROCm HIP caps MTP at ~28 tok/s**." This matches
   our own data (Vulkan+FR-Spec 30 t/s vs HIP ~20). → **Decode should be Vulkan; prefill/ingest can be
   HIP.** (Reinforces the two-engine strategy.)
2. **Asymmetric TurboQuant KV (`-ctk q8_0 -ctv turbo4`)** — K in 8-bit (precise attention routing), V
   in 4-bit: 262K context RAM from **61.4 GB → 20.08 GB**. This is the single biggest *capacity* lever
   for a 128 GB box and directly enables PROJFIX + FR-Spec + long ctx to coexist. Needs a TurboQuant
   KV kernel (present in these forks) — check if the pwilkin fork has `-ctv turbo*`.
3. **Hybrid-recurrent checkpoint discipline:** "Qwen3.8 (qwen35) combines SSM layers with attention,
   meaning KV cells cannot be arbitrarily shifted. Context reuse relies strictly on RAM checkpoints:
   `--ctx-checkpoints 128 --checkpoint-every-n-tokens 2048 --cache-ram 32768` for ~5 s rollbacks."
   Directly applicable to qwen4exp (GDN + attention hybrid) and to our MTP decode.

### Halogen 0.8.1 (still the performance reference; native-Linux only)

Latest is **0.8.1** (0.8.0 added structured output + `/metrics`; 0.8.1 grammar/cache/vision fixes —
no new speed claims; the published prefill/decode rows are **unchanged** since 0.7.0). Its BYO-GGUF
facts, now confirmed in the changelog: repacks our **UD-IQ4_XS** losslessly into its kernel layouts,
94 GB on disk vs 118 GiB native, **18 s cold / 9 s warm startup**, optional repack cache (1.4 s warm);
**prefill within 1% at 8k/32k, serial decode 25.4 t/s (vs 35.4 on its native 8-bit trunk), 42–45 on
coding turns with both drafters**; and **against llama.cpp on the same file: prefill 1.9× @8k, 2.7×
@32k, decode 1.1–1.3×, 1.9× on coding turns.** It also documents the PLE/n-gram cold-start fix
(64-row batched reads: 32k first prompt 46–52 s → 1.3 s) — **directly relevant to our PLE stalls**;
`HALOGEN_NGRAM_GATHER_THREADS` semantics map to our lazy reader.

## 0c. BREAKTHROUGH (late 2026-09-14): the author's real gate values + 839 t/s measured

The author's actual launcher was found on disk at **`/home/revn/pwilkin/install.sh`** (lines 493–540) —
it had been there all along. It sets gates with **specific numeric values** and includes gates my
source-grep missed. Reproducing it exactly gave the session's biggest jump.

| Gate | Author's value | My earlier guess | Effect |
| --- | --- | --- | --- |
| `LLAMA_MMB_TALL` | **2** | 1 | wide 384×64 WMMA tile |
| `LLAMA_MMB_F32SPLIT` | **2** | 1 | two-way F32 split |
| `LLAMA_MMB_HC16` | **2** (Linux) — 0 only on Windows | 0 | bf16 HC streams |
| `LLAMA_MMB_SHADOW` | **2** | 1 | bf16 shadow copies |
| `LLAMA_QSA_QUERY_STRIP` | **512** (a tile size, not a flag) | 1 | QSA query strip width |
| `LLAMA_QSA_SCORE_BOUNDS` | 1 | **missing from my list** | sparse score bounds |
| `LLAMA_QSA_COMPACT_METADATA`, `LLAMA_QSA_NO_DENSE_MASK`, `LLAMA_QSA_FA_V3`, `LLAMA_HC_PACK_DI` | 1 | **missing** | |
| `LLAMA_MTP_QSA_MIN_T` | 128 | **missing** | |

Also from the launcher: **`MTP_N_MAX` default is 2** (not 3/4), and the canonical flags are
`-dev ROCm0 -ngl 999 -fa on -fit off --load-mode none --lazy-mode on-direct -ctk f16 -ctv f16
--spec-type draft-mtp --spec-draft-device ROCm0 --spec-draft-ngl 99`.

### Measured result of the exact gate set (PROJFIX, ub 8192, ctx 49152, WSL/DXG)

| | @1k | @8k | @16k | @32k |
| --- | ---: | ---: | ---: | ---: |
| prefill t/s | 565–585 | **646–839** | **747–827** | **714–778** |
| decode t/s | 19.4–21.0 | 15.8–16.8 | 14.8–15.2 | 10.9–12.7 |

**`839 t/s @8k` vs `366 t/s` at session start = +129%**, and `778 @32k` vs `316` = +146%.

**The MMB kernels are confirmed firing** — the logs now show `MMB_GLU fused gate/up+swiglu`,
`MMB_BLK16 dense BF16 in place`, `MMB_DOWN16 routed down BF16 in place`,
`MMB_TALL(wide 384x64) dense M=324 K=10240 T=8188`, and `QSA_SCORE_BOUNDS active ... mean=1135 (55% of full)`.
My earlier "MMB never fires" conclusion was a **logging artifact**, exactly as Codex Astra suspected:
the gates were present but set to values that put the kernels on different paths.

### The remaining gap to 1,204

**ub 16384 runs fine** — PROJFIX + author gates at `-b 16384 -ub 16384` loaded and produced
**870 t/s @16k, 834 @32k** (median ~770–870). So the earlier "ub 16384 does not fit" conclusion was
wrong: it fits *with PROJFIX + gates* at 49k ctx on this carve. That removes "carve is required for
batches" from the critical path (the carve remains useful for 262k ctx and for adding the draft head).

**Final measured table (author-exact gates, PROJFIX):**

| Config | @8k | @16k | @32k |
| --- | ---: | ---: | ---: |
| ub 8192 | 646–839 | 747–827 | 714–778 |
| **ub 16384** | 604–818 | **705–870** | **731–834** |

**Stock UD-IQ4_XS + same author gates (olliehm parity check):**

| Size | prefill median | decode |
| --- | ---: | ---: |
| 1k | ~513 | ~13 |
| 8k | ~661 | ~13–15 |
| 16k | ~680 | ~13 |
| 32k | ~693 | ~11 |

So UD reaches **~660–698 t/s** — good, but **PROJFIX is ~15–20% faster and more stable at every depth**.
olliehm measured 964–1045 on *native Windows* with UD; our WSL/DXG numbers (660–698) are ~70% of that,
consistent with the WSL-vs-native gap identified earlier.

### Decode / MTP head compatibility (measured)

- **FR-Spec head (`...frspec-65k.gguf`) does NOT load on the pwilkin fork**: it uses drluoto's MTP
  tensor naming (`fc_embd`/`fc_hidden`/`hc_down`/`hc_up`/`hc_norm`) instead of `eh_proj`/`hc_head_*`,
  so `blk.48.nextn.eh_proj.weight` is missing. My `d2t` port handles the vocab trim, but the *tensor
  naming* is a second, separate port. Treat FR-Spec as Vulkan-side for now.
- **Plain head (`mtp-Qwen3.8-Flash-Next-Q8_0.gguf`, 3.85 GB) loads** (has `eh_proj`, full 248k vocab)
  and is the correct head for HIP-side speculation.
- The shared head (2.6 GB) also has `eh_proj` but no `output.weight` (borrows the target's).

### Decode + gates interaction (measured, important)

| Config | Prefill @1k | Decode @1k | Acceptance |
| --- | ---: | ---: | ---: |
| UD + **no gates** + plain MTP head | 243–289 | **18.0–19.3 t/s** | 48–58% |
| PROJFIX + **author-exact gates**, no MTP | 565–585 | 19.4–21.0 | — |
| PROJFIX + **author-exact gates + MTP** | — | **load path HANGS** (CPU spin, RSS frozen) | — |
| Vulkan + UD + FR-Spec MTP d3 | 288–314 | **29.3–30.6** | 73%@1k |

**Finding: the author-exact gate set and the MTP draft path are mutually exclusive on this fork as
built.** With all gates on, `common_speculative_init_result: loading draft model` never returns — the
process spins at 100% CPU with RSS frozen. Disabling `LLAMA_MTP_QSA` alone does not fix it, so the
conflict is in the MMB/HC/QSA gates, not just the MTP-specific one.

This matches the ecosystem evidence: **the author's own decode numbers (~30 t/s) come from his
retained-PM4 runtime, and olliehm measured only ~24 t/s decode without device checkpoints** — i.e.
decode is *not* delivered by the gates. Decode is delivered by (a) spec decode with on-device
checkpoints (PR #28118/#28123) and (b) the runtime.

**Practical decode conclusion:** run **Vulkan + FR-Spec for interactive decode (30 t/s measured)**
and **HIP + author-exact gates for prefill/ingest (839 t/s measured)** — two engines, one model,
one at a time. The HIP-side MTP path needs either the checkpoint PR fully wired (with gate/MTP
conflict resolved) or the retained runtime; it is not a quick win.

## 1b. Full measurement history this session (all token-exact)

| Config | Prefill @1k / @8k / @16k / @32k | Decode @1k / @8k / @32k |
| --- | --- | --- |
| pwilkin HIP + UD, **no gates** | 324 / 325–364 / — / 316 | 20.6 / 13–19 / 11.5 |
| pwilkin HIP + UD, `LLAMA_MMB=1` | 364 / 460–525 / — / 381 | 21.7 / 17–19 / 10.0 |
| pwilkin HIP + PROJFIX + partial (guessed) gates | 503 / 578–618 / 568 / 466–479 | 21.4 / 19–21 / 13–18 |
| **pwilkin HIP + PROJFIX + AUTHOR gates, ub 8192** | 565–585 / 646–839 / 747–827 / 714–778 | 19.4–21.0 / 15.8–16.8 / 10.9–12.7 |
| **pwilkin HIP + PROJFIX + AUTHOR gates, ub 16384** | — / 604–818 / **705–870** / **731–834** | — / 15.5–17.0 / 10.7–13.0 |
| pwilkin HIP + **UD stock** + AUTHOR gates, ub 8192 | ~513 / ~661 / ~680 / ~693 | ~13 / 13–15 / ~11 |
| Vulkan + UD + FR-Spec MTP d3 | 288–314 / 360–366 / — / 271 | **29.3–30.6** / 17.8 / 20.0 |
| UD + no gates + plain MTP head (spec working) | 243–289 | **18.0–19.3** (48–58% accept) | — |
| drluoto HIP + UD + plain MTP | 161 / (failed) | **6.8** (host-checkpoint pathology) |
| ⚠️ my all-35 guessed gate set | — | **`GGML_ASSERT(obj_new)` crash** |

**Progress: 366 → 870 t/s @16k (+138%)**, then 778–834 @32k. The two levers were (a) the PROJFIX
quant and (b) the author's real gate values. Decode best remains **Vulkan+FR-Spec at 30 t/s**.



## 2. Measurement corrections (Codex Astra + harness review)

Several of my earlier conclusions were wrong and must be discarded:

| My earlier claim | Correction |
| --- | --- |
| "MMB=1 gives +45% prefill" | Not established. MMB's markers never appeared in my logs, so the +45% is likely run-to-run variance, not MMB. **Codex: absent markers are inconclusive** — need `LLAMA_MMB_CVT_LOG=1` + dispatch counters. The real prefill lever is the **full gate set**, which I never enabled. |
| "6.8 t/s decode ⇒ PR #28118 absent" | Symptom matches, not proof. Verified separately: the fork's spec calls lack `ON_DEVICE` (true), but the PR's 41.5/56.6 t/s numbers were **Vulkan+RADV with Q4_K_M and q8_0 KV**, not our HIP/PROJFIX config. Also **PR #28123 (merged) may supersede it**: correct GDN/PLE-conv rollback can eliminate checkpoints entirely (44 t/s rollback vs 41 t/s device ckpt). |
| "carve 48 GB is the prefill lever" | Partly wrong. Carve is **capacity, not bandwidth**. olliehm hit 964–1045 t/s at the *same* ub 8192 with a 96 GB carve; ub 8192→16384 is only **est. 0–15%** and only for prompts >8k. The carve matters for *fitting* the working set (and 262k ctx), not for raw prefill rate. |
| "PROJFIX is the better quant" | Not proven for decode: PROJFIX carries **14.2% more routed-expert bytes** (1.327 GB vs UD 1.162 GB per forward). It is the *prefill-layout* quant; decode may prefer UD. Select quant by total request time. |
| Vulkan 8k decode "17.8 t/s" | My harness only generated **7 tokens** at 8k — not a valid throughput sample. Harness fixed: 256 output tokens, warmup discarded, 3 reps. |

## 2b. The strategy (four layers, priority order) — revised after round-2 intelligence

### Layer 0 — Eliminate build risk first (new; cheapest, highest expected value)

**Try the ready-made engines before building anything more.** `Heretek-AI/ROCmFPX-BUILDER` publishes
Windows+Linux binaries with bundled ROCm 7 (no SDK install):

- **kingjones30/ROCmFPX (b1043)** — **natively supports `qwen4exp` = our model**; their own table
  claims **345 t/s prefill / 22.6 t/s decode**. A ~30-minute download-and-run test.
- **charlie12345/ROCmFPX** — upstream multi-arch HIP, Windows+Ubuntu artifacts.
- **ciru-ai/ROCmFPX** — ROCmFP2/3/4/6/7-DualView/8 low-bit + PromptForge fused projections on gfx1151.
- Cross-check against our verified `strix-vulkan-ba5354d` (30 t/s decode).

If any of these hits its published numbers here, the baseline jumps and the plan shifts up.

### Layer 1 — Prefill: PROJFIX + the real gate set (measured 618; target 900–1,100)

**Best measured today: PROJFIX + gate families = 618 t/s @8k / 568 @16k** (up from 366 baseline).

1. **Get the author's authoritative 35-gate launcher** — the single highest-value missing input. It is
   not in the public installer, the olliehm repo, or the repro JSON; ask the founder to paste the
   launcher block from his install (`~/.local/bin/qwen*.sh` or the installer's generated launcher).
2. **Native Windows build** (olliehm's route: 964–1045 t/s, `LLAMA_MMB_HC16=0`, stock quant) — ~45 min.
3. **Carve → 96 GB + reboot** for ub 16384 (est. 0–15% for >8k prompts) and long-context capacity.
4. Do NOT: port retained PM4 (no prefill effect), rewrite kernels, or reshape MoE grids (59% slower).

### Layer 2 — Decode: Vulkan + MTP (measured winner), and fix the HIP state path

**Round-2 decision: decode on Vulkan/RADV**, where MTP works — q38rocm measured Vulkan 34–36 t/s vs
ROCm ~28 for identical MTP, matching our own 30 vs ~20. Best measured here: **30 t/s (Vulkan+FR-Spec)**.

- Tune toward 34–36: `--spec-draft-n-max 4 --spec-draft-p-min 0.0`, `-b/-ub 2048`, f16 KV, froggeric.
- HIP fork: I ported PR #28118 (on-device checkpoints); **audit merged PR #28123** — correct
  GDN/PLE-conv rollback can remove checkpoints entirely (44 vs 41 t/s). Add hybrid-recurrent
  checkpoint discipline: `--ctx-checkpoints 128 --cache-ram 32768`.
- Depth: default 4; promote 6 only for ≥5% more emitted tokens/s. Union reuse is weak
  (d=4 → 0.971, d=6 → 0.952 per accepted token) so the limiter is **cycle time** (GDN serialization,
  draft cost, acceptance-by-position), not expert bytes.

### Layer 3 — Capacity: TurboQuant KV + carve (new; biggest capacity lever)

- **`-ctk q8_0 -ctv turbo4`** (q38rocm): 262K KV from **61.4 GB → 20.08 GB**. Verify our forks expose
  a turbo KV type; if so this is what lets PROJFIX + FR-Spec + 262K coexist on 128 GB.
- Then the 96 GB carve. Codex caveat: a larger carve does **not** guarantee WSL more usable RAM (the
  `memory=86GB` cap is not a post-reservation guarantee). Measure the real device budget after reboot;
  require ≥3 GiB device / ≥4 GiB host free. Codex arithmetic at 96 GiB: PROJFIX 66.34 + FR-Spec 3.39 +
  KV 1.13 (49k) + GDN 0.11 + ub16384 14.05 = **85.0 GiB at 49k** → **49k is the safe first combined
  config; 262k + ub16384 is too tight to select by arithmetic alone.**

### Layer 4 — Only if still short: kernel work

Bounded by Amdahl (a 42%-faster kernel that is 30% of runtime = 9.7% end-to-end). Profile first, on
the real shapes (640/2560/6144).



## 7. The founder's four architecture questions — answered

### Q1. Can we build ONE combined engine (prefill from the fast side + decode from the other)?

**Short answer: no for a true per-request handoff, yes for "one engine does both" — and the right target
is the pwilkin HIP fork itself, not a hybrid.**

Measured/derived facts that decide it:

| Consideration | Number |
|---|---|
| KV f16, our model (12 full-attn layers of 48) | **24 KiB/token** → 1.12 GiB @49k, 3.0 @131k, 6.0 @262k |
| GDN recurrent state | ~0.106 GiB (fixed) |
| Cost to move KV+state between backends @200 GB/s | **4.3 ms @32k**, 15.5 ms @131k |
| Two engines resident simultaneously (same UD file) | **120.8 GiB** (PROJFIX: 132.7) |
| Total RAM / pool at 96 GB carve | 128 GiB / ~112 GiB |

So a handoff would be *cheap in bandwidth* (4–15 ms) but is impossible in practice for two reasons:
**(a) two engines cannot both be resident** — 120–133 GiB of weights exceeds even a 96 GB-carve pool, so
only one model can be loaded at a time; and **(b) KV + GDN state are backend-private**, so a handoff would
need full state serialization between two different runtime stacks, which llama.cpp has no mechanism for.

What IS achievable:
1. **One engine that does both well = the HIP fork with its decode path completed.** That is exactly what
   upstream is doing: `d67d5883` (Sep 14) already adds *sparse QSA decode + incremental indexer state* —
   i.e. the author's own "next goal". Our decode problem (<30 t/s) is the missing spec-state optimisation,
   not an architectural split.
2. **Two engines, swapped per workload, not concurrent** (what we already do): HIP for ingest/prefill,
   Vulkan for interactive decode, one at a time.

**Recommendation: do not build a hybrid.** Finish the decode path on the HIP fork (upstream's own plan):
add PR #28118/#28123 spec-state handling, take `d67d5883`'s sparse QSA decode, and HIP becomes the single
engine. That is strictly less work than a cross-backend state-transfer layer and it is where upstream is
heading anyway.

### Q2. Why are we using WSL at all, if native Windows is faster?

**It is a toolchain convenience we should now drop for inference.** Measured comparison:

| | WSL/DXG (ours) | Native Windows (olliehm) |
|---|---|---|
| prefill, same quant + gates | **660–698 t/s** (UD) | **964–1045 t/s** (UD) |
| ratio | **~70%** | 100% |
| Vulkan decode | **impossible — no `/dev/dri`, verified** | works; our best decode (30 t/s) |

So WSL costs ~30% of prefill, and it is also where the **VM hard-restarted 6 times** today. The only reason
to be in WSL is that our fork, patches, and model staging live there.

**Recommendation:** build the pwilkin fork natively on Windows with TheRock ROCm (exactly what olliehm did;
~45 min, plus the one-line `prefetch()` no-op stub from issue #24) and use that for inference. Keep WSL only
for building/testing. Expected: prefill 900–1,050 t/s and Vulkan decode at 30 t/s from the same workstation.

### Q3. Should we make our own fork with our own quants (like Halogen's BYO-GGUF)?

**No — and the reason is that Halogen's BYO-GGUF is not really a quant feature.** Their changelog states it
repacks the GGUF's tensors into their kernel layouts *"losslessly (the file's own quantized values, moved,
never requantized)"*. The value is **layout**, and we already have that benefit through PROJFIX (ilintar's
all-IQ4_NL layout), which we measured 15–20% faster than unsloth UD-IQ4_XS on the same engine.

Would a genuinely different quant help? Bits-per-weight is the ceiling:
- IQ4_XS 4.25 bpw / IQ4_NL 4.5 / PROJFIX 4.52
- NVFP4-codebook (halogen's `q4c`) ≈ 4.0 bpw → **only ~6% fewer bytes**
- fp8 (`fp8r`) 8.25 bpw → *worse*
- Hadamard-rotated int4 (`i4l`) 4.25 bpw → **no byte saving**; its value is cheaper integer decode

So the only real remaining prize is *decode cost* (integer/DP4A instead of float dequant), worth maybe
5–15% on decode, at high effort (WMMA-fragment-aware layouts + new kernels for every tensor type).
**Verdict: not worth it now.** Contribute to pwilkin's MIT fork (which is *already* doing layout work and
just compiled its tuned defaults in) instead of forking; a private fork would duplicate maintained work.

### Q4. Is TurboQuant like BYO-GGUF? Would it speed us up, and can we do it?

**Different thing entirely: TurboQuant is a *KV-cache* format, not a weight format.**
q38rocm uses it asymmetrically — `-ctk q8_0` (keys, precise for attention routing) `-ctv turbo4` (values,
4-bit). It touches **KV bytes only**, so it cannot affect weight traffic, which is what dominates both our
prefill and decode. Its whole value is **capacity**.

And for *our* model the capacity win is small, because only 12 of 48 layers use full attention:
- q38rocm's headline "61.4 GB → 20.08 GB" is for a **dense 27B with full attention on every layer** — it
  cannot establish our model's capacity, as Codex Astra pointed out.
- Our model: KV f16 @262k = **6.0 GiB**. Ideal f16→(q8_0 K + 4-bit V) is **39.06%** of f16 (not 32.7%), so
  ≈2.34 GiB — and **ordinary Q8/Q8 KV already gets to 3.19 GiB**, so the *extra* TurboQuant saving over
  plain Q8 is **at most ~0.84 GiB** before V metadata.
- Also: q38rocm's own README says **v1.7.0 dropped `turbo4`**, so it is not a current plug-and-play setting.
- Decisively: **our new sparse QSA decode path consumes F16 K/V** — quantizing KV would lose the very
  decode path we want (see §7b). Codex: "do not sacrifice the new sparse path merely to save memory."

**Verdict: defer TurboQuant.** Our fork has no turbo KV types (verified: zero matches in `ggml.h` /
`ggml-common.h` / `llama-kv-cache.cpp`), our KV is only 6 GiB at full 262k, and QSA already cuts the actual
KV read to ~47 MiB/token at any depth. There is no bandwidth or capacity problem to solve here.

## 7d. Carve recommendation (final)

| Carve | Pool (est.) | Windows RAM | Fits | Verdict |
|---|---|---|---|---|
| **32 GB (now)** | 79.8 GiB | 95.6 GB | everything at ≤49k ctx; **measured 870 t/s prefill at ub 16384** | works today, no reboot |
| 64 GB | ~96 GiB | ~64 GB | + 131k ctx + draft head | safest middle |
| **96 GB** | ~112 GiB | ~32 GB | + 262k ctx (author's and olliehm's config) | **recommended if 262k is needed** |

**Recommendation: raise to 96 GB — but after taking a native-Windows baseline at 32 GB first** (Codex's
sequencing), so the carve change is isolated from the runtime migration. 96 GB is what both the author and
olliehm use and what lets ub 16384 + a draft head + deep context coexist. Codex's caveats: a carve is
**capacity, not bandwidth** (expect 0–5% direct speed change if residency was already healthy); a larger
carve **shrinks host RAM** and our PLE table pages through host RAM; and it does **not** guarantee Vulkan
fits — requalify Vulkan after the change. Keep an admission margin of **≥8 GiB below the measured usable
device budget**.



## 7b. THE AUTHORITATIVE UPSTREAM NUMBERS (found after round 2 — this is the target)

The newest fork commit **`d67d5883` "hip: enable sparse QSA decode and incremental indexer state"**
(Sep 14, the author's stated goal) ships a qualification document at
`docs/development/qwen4exp-decode-indexer.md`. Its own measured numbers, on **our exact model and quant**:

| Workload | Result |
|---|---|
| 40,680-token request, prefill | **1164.30 / 1174.60 t/s** |
| 40,680-token request, generation (MTP width 3) | **35.83 / 39.01 t/s** |
| Warm short generation | **50.28 t/s** |
| Incremental vs recompute, depth 40000 | 25.85 → **28.82 t/s** |
| MTP repeated request, incremental | 32.69 → **39.10 t/s** |

Config: IQ4_NL-PROJFIX, F16 K/V, full GPU offload, **retained PM4 graph replay**, 16 threads,
`-b/-ub 16384`, MTP width 3, gfx1151. Correctness: 512 paired tokens matched; SIMT 18/18 and WMMA 49/49
kernel tests at NMSE ≤ 1e-5; ~2M bit-identical logits across lifecycle ops; WikiText-2 ppl 2.0244 unchanged.

**This is the decisive fact: the decode problem I was chasing (<30 t/s) is solved upstream in code we
can build — it is sparse QSA decode + incremental indexer state, and it consumes the existing F16 K/V.**
Caution: those numbers include retained PM4 and were measured on native Linux. The sparse-decode kernels
themselves are HIP/gfx1151 and should engage over DXG, but the PM4 part will not.

Also from the doc: the indexer state costs **~104 MiB at 64k ctx, ~416 MiB at 262k** for this model.

## 7c. Codex Astra's audit of my plan (corrections I accept)

| My claim | Codex correction | Status |
|---|---|---|
| "WSL costs 32% of prefill" | **Not established** — my comparison changed carve + machine config + OS simultaneously; attribution is unmeasured | **Accept.** Report the *gap* (660–698 vs 964–1045) but not a causal "WSL cost". |
| gfx1151 is wave32-only | **Wrong** — gfx1151 supports wave32 **and** wave64; wave32 is a kernel choice | **Accept.** |
| DXG errors explain the VM restarts | It does not prove OOM/deadlock: `-512`=ERESTARTSYS, `-75`=EOVERFLOW. Correlate timestamps with Windows GPU-reset/WER events | **Accept** — investigate properly. |
| Native Windows removes memory failures | **Wrong** — my own Vulkan log ends in `ErrorOutOfDeviceMemory` at a 64k request (~59k tokens processed, 0.94 GiB request, 2.91 GiB graph reserve) | **Accept.** Memory budget is a real constraint on every path. |
| TurboQuant saves 61→20 GB for us | q38rocm's **v1.7.0 dropped `turbo4`**; and ideal 8/4-bit KV is 39.06% of F16 (not 32.7%), so our 6 GiB KV → ~2.34 GiB, saving **at most ~0.84 GiB over ordinary Q8/Q8**. Also: **our new sparse QSA decode consumes F16 K/V** — quantizing KV would lose that path | **Accept. Defer TurboQuant.** |
| Build our own quant format | Layout is not the whole story: Halogen's own data shows decode 35.4 → 25.4 t/s when swapping its checkpoint for UD-IQ4_XS (extra bytes from UD's higher-precision dense layers). But a *new* FP4/codebook/Hadamard format has no defensible positive forecast and costs 4–8+ weeks | **Accept: keep a small integration branch; no new weight format.** |
| Vulkan = RADV coopmat advantage | On **Windows** Vulkan is not RADV; q38rocm's Vulkan>HIP result is a Linux/Mesa finding | **Accept** — retitle that claim. |

Codex's single most valuable experiment: **one controlled native-Windows HIP qualification matrix**
(UD first, exact 8k/32k, serial vs plain MTP with verified rollback, 1 warmup + ≥5 reps, ≥256 generated
tokens), which answers whether two engines are needed at all. Prefer **recurrent rollback (PR #28123,
handles GDN *and* PLE conv histories)** over on-device checkpoints.

Codex routing math [ESTIMATE]: at our measured rates, Vulkan overtakes HIP on *total* time only beyond
~2,367 generated tokens (short prompts: ~100 output tokens) — i.e. **route whole sessions, never hand off
mid-request**, and keep one model resident.



| Carve | Pool (est.) | Windows RAM | Fits |
|---|---|---|---|
| 32 GB (now) | 79.8 GiB | 95.6 GB | **everything at ≤49k ctx** (measured 870 t/s prefill, ub 16384) |
| **64 GB** | ~96 GiB | ~64 GB | + 131k ctx, + draft head — **safest middle** |
| 96 GB | ~112 GiB | ~32 GB | + 262k ctx (author's and olliehm's config) |

**Recommendation: 96 GB if the World Engine needs 262k context; 64 GB if 131k suffices; stay at 32 GB if
≤50k is the target** (it already delivers 870 t/s prefill with no reboot). Note WSL's host RAM shrinks with
the carve, and the PLE table is paged through host RAM — so a large carve trades paging headroom for
capacity.



Technically plausible; **not automatically additive**. The pwilkin HIP fork is the only place all
four can live (Vulkan accepts FR-Spec but has no MMB and OOMs on PROJFIX at this carve). Verify:

| Boundary | Check |
| --- | --- |
| FR-Spec vocab | Target logits 248320-wide; draft 65536-wide; `d2t` IDs valid/unique; inverse map for out-of-draft tokens |
| Shared embd/head | Do **not** blindly add `--mtp-shared-embd` — the author's sharing mode includes the LM head, but FR-Spec needs its trimmed head |
| Quant pairing | Target quant change alters acceptance — re-measure |
| HC/MMB | Keep `LLAMA_MMB_HC16=0`; verify output under the full gate combo |
| Spec state | Target+draft save/restore, rejected suffixes, repeated requests, cached prefixes, truncation |
| Allocations | Measure warmed peak incl. MMB shadows + draft buffers |

**Status of my ports (built clean, untested together):**
- FR-Spec `d2t`/`t2d` → `src/models/qwen4exp.cpp` (loader + MTP graph builder). ✅ builds
- PR #28118 (6 spec checkpoint sites → `ON_DEVICE`) → `tools/server/server-context.cpp`. ✅ builds
- ⚠️ To audit: PR #28123 rollback (may supersede #28118); GDN/PLE conv rollback snapshots.

## 4. Six-hour execution order (Codex's checklist, adopted verbatim)

| Time | Experiment | Expected | Abort/keep |
| --- | --- | --- | --- |
| 0:00–0:25 | Fix harness (256 tok, warmup, 3 reps, save outputs); run WSL HIP UD + **full gates**, no draft, c49152/b8192/ub8192 | est. 600–950 pp | corruption/OOM ⇒ stop; <600 pp ⇒ dispatch investigation, not bigger batch |
| 0:25–1:10 | Prepare **native TheRock** build from patched fork (+ Windows `prefetch()` no-op stub) | builds, correctness probes | time-box 45 min; keep WSL fallback |
| 1:10–1:30 | **Founder: carve → 96 GB, reboot**; measure device + host budget | more headroom | require ≥3 GiB device / ≥4 GiB host free |
| 1:30–2:05 | Native UD + full gates, 1K/8K/32K | **900–1050 pp, 24–30 tg** | <800 pp ⇒ investigate build/GDN/MMB before adding features |
| 2:05–2:40 | Ordinary MTP head depth 3, corrected state path | 30–38 tg | stop on state-restore/correctness failure |
| 2:40–3:25 | FR-Spec depth 3 (p-min 0.75 vs 0.0), then depth 4 | 33–40 tg | reject on mapping/state errors |
| 3:25–4:00 | Depth 6 vs winner, code + prose, 256 tok, 3 reps | 33–40 general, 45–56 code | keep 6 only for ≥5% |
| 4:00–4:45 | PROJFIX with winner head/depth; then b16384/ub16384 @49k | 900–1100 pp | reject if memory margin fails; keep ub16384 only for ≥5% |
| 4:45–5:25 | Winner at c131072 then c262144; 64K/120K retrieval | capacity/quality | stop on paging collapse |
| 5:25–6:00 | HIP vs Vulkan bracket, 1K/8K/32K, same sampling | defensible winners | publish medians + spread + failures |

**Winner rule:** HIP earns "better decode" only if it beats Vulkan by ≥10% on the same suite
(≥33 t/s vs a verified 30 t/s). Otherwise Vulkan stays the decode winner; HIP still wins total
request latency because prefill is much faster. No cross-engine state transfer.

## 5. Expected outcome

| Workload | Estimate (qualified HIP + gates + FR-Spec) |
| --- | ---: |
| Warm 8–16K prefill | **900–1100 t/s** |
| Fresh 32K prefill | **800–1050 t/s** |
| Short-context decode | **33–40 t/s** |
| Decode @32–40K | 20–30 t/s (lower confidence) |
| High-acceptance code | 45–56 t/s (stretch) |

All layer-1 numbers are externally measured on Windows by olliehm; layer-2 are PR/author data
transposed to our config and must be validated here. Explicitly **not** promised: full-context
decode scaling (author's controlled table: 26.28 @0k → 16.63 @40k), and anything relying on PROJFIX +
ub16384 fitting at 262k.

## 6. Sources

- ilintar's announcement + comments: https://www.reddit.com/r/StrixHalo/comments/1weo5s3/
- Author's site/journey/repro data: https://pwilkin.github.io/strix-halo (~1204/1100/850 t/s, 30 t/s; journey.html has the ablation ladder incl. GDN 499→1182)
- olliehm Windows port: https://github.com/olliehm/qwen-flash-next-windows (38 t/s decode, 85–100% accept, 74 GB footprint)
- Issue #24 (gate bisection, HC16 culprit, 964–1045 t/s): https://github.com/pwilkin/llama.cpp/issues/24
- hipEngine RDNA3 tuning guide: https://github.com/shisa-ai/hipEngine/blob/main/docs/RDNA3-TUNING-GUIDE.md
- PR #28118 (on-device spec checkpoints): https://github.com/ggml-org/llama.cpp/pull/28118
- PR #28123 (RS rollback; merged — supersedes checkpointing): https://github.com/ggml-org/llama.cpp/pull/28123
- Codex Astra review (this session): `kernel-work/codex-plan-20260914.txt`
