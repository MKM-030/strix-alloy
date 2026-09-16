# ChatGPT prompt — decode bottleneck + draft-head training, with all measured data

Paste everything below the line into ChatGPT (frontier model). It is self-contained.

---

You are a GPU-kernel and LLM-inference engineer reviewing a measurement-driven optimization effort. I will
give you **only measured facts** from one machine; where something is a claim from a third party I say so.
Your job is to (a) check our arithmetic and reasoning, (b) tell us the single highest-value next
experiment, and (c) call out anything we have concluded wrongly. Be blunt and concrete; do not repeat our
findings back to us as if they were yours.

## The machine and stack

- AMD Ryzen AI Max+ 395, Radeon 8060S iGPU (gfx1151, RDNA3.5, **wave32**, 40 CU), 128 GB LPDDR5X UMA
  (~200–240 GB/s), **96 GB dedicated carve**.
- Windows 11 + WSL2 over `/dev/dxg` (no `/dev/kfd`, no PM4 replay). Our fast path is **native Windows**,
  built with the TheRock 10.2 SDK, **clang 24.0.0git**, `GGML_HIP=ON`.
- Model: Qwen3.8-Flash-Next, a 177B MoE (~6B active): 48 layers, 512 routed experts top-k=10 + 1 shared,
  expert FFN 640, emb 2560, hyper-connections (4 streams, low-rank 320), hybrid GatedDeltaNet + full
  attention every 4th layer, QSA sparse lightning-indexer (top_k 2048), and a **non-resident 27 GiB PLE
  n-gram table** paged from disk.
- Quant: "PROJFIX" = IQ4_NL everywhere it holds quality (our target). Also UD-IQ4_XS as a reference.
- MTP draft head: a Q8_0 shared head (2.6 GB) that **borrows the trunk LM head** (no `output.weight` of
  its own).

## What we measured (ours, repeatable)

**Throughput**

| config | prefill @1k | @8k | @16k | decode @1k | @8k | @16k |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| PROJFIX, ub 16384 | 710 | 1021 | **1057** | 30.1 | 28.9 | 29.2 |
| PROJFIX, ub 2048 + MTP n-max 2 | 653 | 799 | 782 | **35.5** | 30.2 | 30.2 |
| PROJFIX, no MTP | 700 | 846 | — | 29.9 | 28.6 | — |

**Byte accounting.** Active weight payload per token = **4.254 GB** (dense/other 2.927 + routed experts
1.327). So the serial decode ceiling is **47–56 t/s**. Serial decode runs at 55–66% of that (bandwidth
bound); the MTP point runs at only **24–29%**.

**Draft cost model.** For n-max k, a speculative round costs `k·d + t` (d = draft-step time, t = target-step
time) and yields `1 + A_k` tokens. Fitting to measured decode rates gives **r = d/t ≈ 0.47** (0.45–0.54
across n-max and depth), i.e. **the draft step costs half a target step in time but only ~0.15 in bytes** —
so the draft step is ~70% fixed per-step overhead, not bandwidth.

**Decode levers, all measured, all ≤ noise except one:**
- n-max 1–2 optimal; 3→8 monotonically worse (acceptance 86%→32%).
- n-gram lookup ahead of MTP (cascade): worse (42% vs 62% acceptance).
- A device-resident spec-checkpoint PR: ~0% (branch already uses `rs_rollback`).
- `--spec-draft-p-min 0.75`: 0%. Standalone vs shared head: 0%.
- **FR-Spec trimmed-vocab head** (own 65,536-row LM head instead of borrowing the 248,320-row trunk head):
  **a wash** — +2% at n-max 2, −4% at n-max 1, because it costs ~4 points of acceptance.

**Public references (third-party, not ours):** ilintar's published config is **1204 t/s prefill @0 depth,
1086 @40k, 26.3 t/s decode** (ub 16384 as one batch, retained-PM4 runtime, *no* MTP). A Windows port of the
same branch reports 964–1045 prefill and ~35 t/s decode with device-checkpoint MTP. Halogen (closed engine)
is ~42 t/s decode. The Halogen author states publicly that **decode is at the hardware wall** and that
"the sparsity that makes decode cheap is what makes a wide verify expensive; that is the architectural
fact, not a tuning gap."

## What we are doing next (and want you to challenge)

1. **Rebased our fork onto ilintar's latest branch head** (`40a9f4d0`: extended MMB kernels, fused F32 PLE,
   and critically the commit that **removed all 53 `LLAMA_*` env gates and compiled the tuned defaults in**).
   A full rebuild is done; we are measuring now. Their own note: `ac1ebb4e0` measured **pp16384 = 1223 t/s
   with no env vars at all**. We currently sit at 1057.
2. **Building a draft-head training harness.** We read the head's exact input contract from the code:
   per position k it consumes `(h[k-1], embed(t_k))` and predicts `t_{k+1}`, where `h` is the trunk hidden
   at width `n_embd_out = hc_mult × n_embd = 10240` (4 hyper-connection streams). We built a read-only tool
   that dumps `h_nextn` for a corpus through the codebase's own nextn API (so it cannot diverge from what
   the head sees at inference) and verified a first dump: 8192 tokens × 10240 fp16, four distinct streams,
   finite. The next step is to **reproduce the existing head's ~75% acceptance through the harness** before
   training anything.
3. **Considering a weaker IOMMU/`amd_iommu=off` idea** from a community post (+1.8–31.6% prefill, model
   dependent, bare-metal Linux, decodes unaffected). We believe it is not reproducible on our path (Windows
   uses Device Guard, not `amd_iommu=off`; WSL is paravirtualized on Hyper-V with a *virtual* IOMMU), and it
   would disable the NPU we want to use.

## Questions

1. **Decode:** given `r ≈ 0.47` and only 24–29% of the byte ceiling at the MTP point, is there any decode
   lever we have *not* considered that is not the draft head? We have ruled out draft depth, n-gram cascade,
   p-min, checkpoints, and the cheaper FR-Spec head. Is the honest conclusion that decode is done?
2. **Prefill:** our 1057 vs their 1204. We believe the gap is (a) their ub-16384 one-batch path and (b) their
   retained-PM4 command lists. Rebuilding on their kernels should close some of it. Is there a *third* cause
   we are missing? Note their published caveat that HIP graphs never engage on prefill (each chunk shape
   occurs once per request).
3. **Draft head:** is training a head fitted to our trunk the right decode investment, or does the
   `r ≈ 0.47` overhead structure mean a *cheaper draft step* (fewer experts in the head) beats a
   *higher-acceptance* head? We estimate: acceptance 0.75→0.90 gives ~+21% decode; halving the draft
   step's fixed overhead (`r` 0.5→0.25) gives ~+33%. Which would you fund first, and why?
4. **Training design:** we plan a teacher-forced `(h, token) → next-token` fit at the **full 248,320 vocab**
   (the FR-Spec 65k trim is what cost us 4 points of acceptance). Starting from the existing shared head.
   What would you change — loss, data mix, whether to train the head's MoE FFN at all, or whether a
   *dense low-rank* head would be strictly better given `r ≈ 0.47`?
5. **Anything we are wrong about.** In particular: is our claim that "wide verify is fundamentally
   expensive on a sparse MoE" correct, or is there a verification scheme that avoids the sparsity cost?

Constraints: repository-only work, no paid APIs, no cloud, no product lifecycle changes. The machine is a
single shared box. Answer with concrete next experiments and expected effect sizes, and state your
uncertainty explicitly.
