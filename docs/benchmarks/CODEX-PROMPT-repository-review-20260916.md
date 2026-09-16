# Codex prompt — adversarial review of `strix-alloy`

Copy everything below the line into Codex. It is self-contained: repository URL, what the project
claims, the specific numbers to attack, and the sources to cross-check against.

---

You are reviewing a performance-engineering repository as a skeptical peer reviewer. Your job is to find
problems, not to praise. Assume the author is competent but possibly wrong, over-claiming, or measuring the
wrong thing — that is the pattern this repo's own history shows (it has published and then retracted two
headline claims).

**Repository:** https://github.com/MKM-030/strix-alloy

Please read the repository directly (README, `docs/benchmarks/*.md`, `kernel-work/`, `setup/`).

## What the project is

A fork of the `pwilkin/llama.cpp` `strix-halo` branch, built natively for **Windows** with the TheRock ROCm 10
HIP SDK (clang 24), targeting **gfx1151** (AMD Ryzen AI Max+ 395, Radeon 8060S, RDNA3.5, wave32, 40 CU,
128 GB unified LPDDR5X, 96 GB firmware carve). It runs Qwen3.8-Flash-Next (`qwen4exp`): a ~125B-parameter MoE
(~6B active), 48 layers, 512 routed experts top-10 + 1 shared, FFN width 640, `n_embd` 2560, 4
hyper-connection streams, hybrid GatedDeltaNet + full attention, QSA lightning indexer (top_k 2048), plus a
separate ~27 GiB PLE n-gram table that is mmap'd rather than resident. Quant is `IQ4_NL` "PROJFIX" (every
tensor IQ4_NL, ~4.52 bpw).

## The claims to attack

1. **Headline benchmark (the most important thing to check).** The README now leads with `llama-bench`:
   `pp512 761.30 ± 38.24 t/s`, `tg128 31.49 ± 0.17 t/s`, and `pp16384 892.59 ± 22.50 t/s` with `-b/-ub 16384`.
   The author chose `llama-bench` specifically because it **cannot drive a drafter**, making `tg128` plain
   serial decode and therefore comparable to other people's numbers.
   - Is that reasoning sound, or is it a way to quote a lower, more defensible number while the served engine
     is actually faster?
   - The repo states that `llama-server` reports **926–1043 t/s for the same 16k prefill shape** where
     `llama-bench` reports **893**, and calls this an unexplained ~15% harness gap, ruling out warm-up
     (`-r 8` does not climb). **Investigate this gap.** Which number is more honest to publish? Is there a
     benign explanation (context size `n_prompt+n_gen` vs `-c 32768`, graph capture differences, timing
     boundaries, batch-size defaults)?

2. **The cross-engine comparison.** Against ilintar's (`pwilkin/strix-halo`, Linux) published figures on the
   same tool, the README claims **26% behind on prefill** (893 vs 1204) and **15% ahead on serial decode**
   (30.2 vs 26.3). The author attributes the prefill gap to ilintar's retained-PM4 command-list runtime.
   - Is that attribution justified, or is there a cheaper explanation (kernel set, env flags, `-ub` choice,
     graph engagement on prefill)?
   - Are the two measurements actually comparable at all?

3. **The MTP acceptance claim (recently rewritten — check the reasoning).** The README now asserts that draft
   acceptance is **deterministic per content class**, not run-to-run unstable: three consecutive repeats of one
   prompt give identical ratios (53/134), while different text gives 40% (doc-continuation) vs 92% (instructed
   answers). This **retracts** an earlier published claim that acceptance was irreproducible (47% vs 65%).
   - Is three repeats enough to establish determinism?
   - Is there a confound the author has not controlled for (seed handling, prompt caching, KV state, sampler
     state, `n_predict` interplay, batch-size ramp)?
   - The follow-on recommendation is to pick `n-max` per content class (`n-max 4` is +10% at 92% acceptance;
     `n-max 2` wins at 40–53%). Is that a legitimate optimization or curve-fitting to two hand-written
     prompts?

4. **Two ported kernels measured as negatives.** The author ported `MMID_512` (512-expert/10-active MoE
   routing in one block instead of 512 warp blocks) from `halo-box/strix-llama.cpp` and measured **−0.2%
   decode**, arguing it cannot help because **HIP graphs already remove the launch overhead** it targets
   (48 calls × 512 launches would be ~123 ms/token if exposed; zero was measured). They also claim the rest of
   halo-box's HIP set **cannot apply** because `MMV_GROUP` and the fused matvec prologues are gated to
   **Q8_0/Q6_K** while this model is IQ4_NL throughout, verified by a GGUF census.
   - Is the "HIP graphs absorb it" explanation actually sound, or did the port simply measure the wrong thing
     (e.g. coverage unproven, wrong shape, kernel objectively worse in ways that mask a real dispatch win)?
   - Is the Q8_0 gate a hard blocker or merely the default (the author notes `MMVQ_FQ_IQ_TYPES` defaults to
     false — i.e. it might be a **compile flag away**)? If so, is the "cannot apply" claim too strong?
   - `WEIGHTED_DOWN` **is** IQ4_NL-compatible; the author declined it citing a ~0.2% ceiling from their byte
     census. Check that arithmetic and the dismissal.

5. **The memory/carve claims.** The repo asserts, from a measured allocation ceiling and a 16 GB-carve
   experiment, that: (a) `hipMalloc`, `hipMallocManaged` and `hipHostMalloc` all cap at the same value
   (~113% of the reported pool) on this stack; (b) a carve below the resident set does not fail but runs
   **5× slower** (prefill 1031 → 85 t/s, decode 34 → 6.25 t/s) because the whole weight buffer is served from
   the system-memory path; and (c) `GGML_HIP_ENABLE_UNIFIED_MEMORY` was inert in their scripts because the
   build only reads `GGML_CUDA_ENABLE_UNIFIED_MEMORY`.
   - Are (a) and (b) correctly measured and correctly interpreted? The 5×-slower inference is drawn from
     ~127 ms/token of extra cost, inferred not directly observed — is that inference safe?
   - Is "the whole buffer is demoted, not just the 4.3% overflow" supported?

6. **Methodology gaps generally.** The repo publishes its own rules (`Reproducing measurements`): prefill needs
   3–4 warm reps, 1–2% effects need an interleaved A/B, log which kernel specialisations actually ran, average
   ≥3 MTP runs, quote `llama-bench` for cross-engine claims.
   - Point out anywhere the published data **violates the repo's own rules**.
   - The negative results are single-configuration in several cases. Flag every claim that rests on n=1 or on
     a measurement without coverage proof.

7. **Windows-specific risk.** The repo claims to be "the only Windows-native stack that sustains these
   numbers" in places (and elsewhere corrects that olliehm's came first). It pins the SDK's `amdhip64_7.dll`
   next to the exe because Windows searches the exe directory before System32, without which HIP fails at
   device init with a misleading `cudaMemGetInfo failed (invalid argument)`.
   - Are there additional Windows/HIP correctness or stability risks this skips?
   - Any `BLOCKED`-class gaps that should be stated rather than implied?

## Sources to cross-check against (the author's inputs)

Use these to judge whether the fork picked the right levers and whether any were dropped without reason:

- **https://github.com/halo-box/strix-llama.cpp** — sibling fork, same `pwilkin/strix-halo` lineage. Its
  commit `6130b7262` "hip: optimize RDNA3.5 MoE inference paths" (+3141/−214) holds the HIP set discussed in
  claim 4. Its README documents `MMV_GROUP`, `MMID_512`, `WEIGHTED_DOWN`, `GDN_GATE`, ROCmFPx quants, Q8_0 KV
  kernels, device-resident spec checkpoints, and `--ngram-on-disk`. **Assess which of these the author should
  have taken and did not, and whether any dismissal is wrong.**
- **https://github.com/myhacsint/llama.cpp/tree/production/strix-halo-qwen4exp-b10685** — curated b10685
  snapshot. Source of the shared-MTP fit fix (`common_fit_extra_model::path_model_shared`) and the adaptive
  acceptance-EMA draft controller (`--spec-draft-adaptive`) which the author ported and measured at −4.7% to
  −9.6%. **Attack the port and the measurement, and say whether the controller's design or the author's test
  is at fault.**
- **https://github.com/pwilkin/llama.cpp** (`strix-halo` branch) — the fork this project is built on, and the
  origin of the IQ4_NL PROJFIX quant and the MMB/QSA/PLE kernels.
- **https://github.com/olliehm/qwen-flash-next-windows** — the other Windows-native stack for this model,
  credited as first. Its correctness gates (sequence-level validation: single-turn, multi-turn, depth bands,
  needle retrieval) and its warning that MTP on HIP can show 2× t/s while emitting collapsed text are the most
  important correctness claims to test against this project.
- **https://github.com/stew675/llama-cpp-rdna-boosts** — RDNA patch set the author lists as "to audit" and has
  not completed. Worth reviewing for portable pieces.
- **https://github.com/SixVolts/llama-halo-hybrid** — Strix Halo + R9700 kernel patch set.
- **https://github.com/peonist-ai/halogen-flash-server** — "Halogen", the Linux reference stack for this model.
- **https://github.com/HereTek-AI/chlorine-server** — "Chlorine", Linux reference stack.
- **https://github.com/ROCm/TheRock** — the Windows HIP SDK build used here.
- **Reddit context** (the author could not fetch these programmatically; if you can, the comments carry the
  dissenting measurements): `r/StrixHalo` — search for Qwen3.8 Flash-Next, QSA, gfx1151, and the ilintar and
  strix-halo tuning threads. Also `r/LocalLLM`.
- **https://pwilkin.github.io/strix-halo** — ilintar's published reference figures (`pp16384 = 1204.31`,
  `tg128 = 26.28`), the numbers used in the comparison above.

## What I want back

1. **A list of concrete issues**, each with: severity, the file/line or document it refers to, the evidence,
   and a proposed correction. Prioritise anything that makes a **published number wrong or misleading**.
2. **Optimisation potential not yet tried**, ranked by expected effect on decode tokens/second, with the
   reasoning made explicit. The repo's own analysis says decode is bound by 4.219 GB/token of actual weight
   traffic (~33 ms at ~133 GB/s marginal), not by dispatch — so favour ideas that reduce *bytes moved* or
   improve *effective bandwidth*, and say why a suggested kernel fusion would beat that bound.
3. **Where the repo's reasoning is wrong even if its numbers are right** — bad inferences, unstated
   assumptions, conclusions that outrun the evidence.
4. **Anything you could not verify from the repository alone**, stated as such rather than guessed.

Be specific and cite what you are looking at. If a claim is sound, say so briefly and move on — I want the
problems, the missing levers, and the broken inferences.
