# strix-alloy

**A 125B-parameter MoE (~6B active) running on a consumer Windows PC — natively.**

Qwen3.8-Flash-Next on an AMD Ryzen AI Max+ 395 mini-PC: **1,031 t/s prefill**, **34 t/s decode with
speculative decoding**, and a working **251k-token context** — with no Linux, no CUDA, and no
datacenter GPU. Just the Windows box on your desk.

> **On the parameter count:** the transformer is **~125B** (121B in routed experts + ~4B attention,
> embeddings and norms), which is what the model card and other ports cite. The checkpoint also carries
> a separate **51B-parameter PLE n-gram embedding table** that lives in host memory and is not part of
> the transformer. Model + table ≈ 176B; some places (including earlier drafts of this README) quote
> that figure as "177B". We verified 125B against our own byte census: 120.8B expert params × 4.5 bpw =
> **67.9 GB**, which is exactly the routed-expert total we measure on disk. Use **125B** for the model;
> the table is a table.

```
prefill   1,031 t/s @ 16k      ──►   812 t/s @ 251k
decode       34 t/s @ 16k      (MTP n-max 2, 56–73% acceptance)
serial       28.3 t/s          (no drafter)
context      251,904 tokens    works end to end, no OOM
```

---

## Why "Windows-native" is the whole point

The Strix Halo local-inference scene is Linux-first. The fastest published stacks — **Halogen** and
**Chlorine** — require a native Linux host, and the reference HIP fork is built for Linux. Windows users
have been told, correctly, that they give up throughput. While I was able to build a bridge and make the halogen engine usable under WSL, 
only the qwen 3.8 27b model was fitting into the 96 gb. I will continue this development in a different project and eventually release with a different flash-next quant.

Two stacks now run this model natively on Windows: **olliehm's** (published first) and `strix-alloy`.
Neither is a fork of the other — we share an upstream ancestor and diverge after that. Our case is
**prefill** (we do not know of a faster Windows-native prefill on this hardware) plus a complete
measurement trail, retractions included. No WSL, no dual-boot, no VM: the GPU is driven directly
through HIP on Windows over `/dev/dxg`, with **HIP graphs** keeping the decode path dispatch-free
(worth ~65 ms/token here — 35 t/s with graphs vs 10.7 without).

### Head-to-head, both Windows-native

| | **olliehm** | **strix-alloy** |
| --- | --- | --- |
| **engine** | upstream `ggml-org/llama.cpp` + **`stew675/llama-cpp-rdna-boosts`** patches, served via **Lemonade** | **`pwilkin/llama.cpp` `strix-halo`** (ilintar) fork, TheRock clang 24, `llama-server` directly |
| prefill | ~660 t/s @8k–17k | **1031 @16k · 993 @65k · 925 @131k · 812 @251k** |
| decode, no MTP | 21.7 @500 · 21.6 @2000 · **20.3 @8k** | **28.8 @8k** · 28.3 @16k |
| decode, MTP | **38 t/s** *(depth not published)* | 34 @16k · 32.6 @65k · 32.8 @131k |
| draft acceptance | **85–100%** (`n-max 4`, `p-min 0.75`) | 56–73% (`n-max 2`, `p-min 0.0`) |
| context | 262,144 | 251,904 verified |
| quant | UD-IQ4_XS — chosen for **fit margin** (~22 GiB spare at 262k) | IQ4_NL PROJFIX — chosen for **speed** on this fork's kernels |
| drafter | full Q8_0 head (~3.2 GB) | **shared** Q8_0 head (2.6 GB, borrows the trunk LM head) |
| carve footprint | 74.0 GB (weights 61.2 + drafter 3.2 + KV 8.75 + compute ~2) | ~74 GB |
| deployment | Lemonade + an **admission shim** sharing one carve across instances | direct `llama-server` |

**Different kernels, different lineage — not a fork of each other.** We share an upstream ancestor and
diverge: our tree carries the fork's own backend work (MMB large-batch kernels, fused F32 PLE, sparse
QSA decode, hyper-connection kernels, top-k tuning); his carries `rdna-boosts` RDNA tuning and the
`qwen4exp`/MTP work as mailbox patches on plain upstream. That is why prefill differs by ~1.5× — MMB
is a large-batch path his engine does not have — while his patch set is the one thing we lack.

Read the decode rows honestly: **his published MTP number has no depth attached, and his acceptance
comes from a different operating point.** We tested his exact flags on our engine at 65k:

| MTP config | decode @65k | acceptance |
| --- | ---: | ---: |
| ours: `n-max 2, p-min 0.0` | **33.1 t/s** | 65% |
| his: `n-max 4, p-min 0.75` | 26.4 t/s | **96%** |

His acceptance reproduces here; **his throughput does not** — the higher `n-max` costs a 5-row verify
every round for drafts the `p-min` gate usually discards. Full audit and the
what-we-should-learn section: `docs/benchmarks/engine-comparison-vs-olliehm-20260916.md`.

Negatives on our side (see the investigation section): our **177B claim was wrong** (it is ~125B plus a
51B table) and our **"only Windows-native stack" claim was wrong** (his came first on decode).

Two things in his repo matter more than any single number, and we say so plainly:

- **His correctness gates.** He gates on *sequence-level* validation — single-turn, multi-turn, depth
  bands, needle retrieval — and warns that **MTP on HIP can show 2× tok/s while emitting collapsed
  text**. We hit variants of exactly this from the other direction. Speed-only benchmarking on this
  stack is not trustworthy, in either repo.
- **His deployment work.** A Lemonade recipe and an admission shim letting several instances share one
  carve — infrastructure we do not have.

---

## Hardware

| | |
| --- | --- |
| SoC | AMD **Ryzen AI Max+ 395** |
| GPU | Radeon **8060S** — gfx1151, RDNA3.5, wave32, 40 CU |
| Memory | 128 GB LPDDR5X **unified**, ~235 GB/s measured sequential-read ceiling |
| Carve | **96 GB** dedicated (device pool ~108 GiB) |
| Box | Bosgame M5 mini-PC (a consumer mini-PC, not a workstation) |
| OS | **Windows 11 native** |

Two facts about this box drive every number below: the memory is **unified** (the "VRAM" is host RAM, so
the carve trades host RAM for device pool), and the ceiling is **~236 GB/s**, which is what makes a
bandwidth-bound engine like this viable at all.

---

## Model & quantization — decided by measurement, not by default

**Model:** Qwen3.8-Flash-Next — **~125B transformer parameters** (~6B active), plus a separate
**51B-parameter PLE n-gram table**. 48 layers, 512 routed experts (top-10) + 1
shared expert, expert FFN width 640, `n_embd` 2560, **4 hyper-connection streams**, a hybrid
**GatedDeltaNet + full-attention** stack, a **QSA lightning indexer** (top_k 2048), and the **~27 GiB PLE
n-gram table**, which is mmap'd from disk rather than resident.

**Quantization chosen: `IQ4_NL` "PROJFIX"** — every tensor IQ4_NL, uniformly.

This was the single largest performance decision in the project, and it is counter-intuitive: PROJFIX is
**larger** (4.52 bpw) than the popular UD-IQ4_XS (4.24 bpw), yet it is dramatically faster.

| depth | UD-IQ4_XS (prefill / decode) | **PROJFIX (prefill / decode)** | gain |
| ---: | ---: | ---: | ---: |
| 1,024 | 260 / 6.8 | **469 / 30.4** | +82% / **+347%** |
| 8,192 | 474 / 14.4 | **593 / 28.0** | +25% / **+94%** |
| 16,384 | 473 / 14.5 | **590 / 29.0** | +25% / **+100%** |
| 32,768 | 459 / 14.5 | **582 / 28.7** | +27% / **+98%** |

**Decode roughly doubled and prefill gained a quarter — from layout, not bit-width.** The reason is that
this fork's fast paths are built around **resident IQ4_NL**; a stock quant mixes IQ3_S/Q8_0 and only
partially qualifies, so it falls back to slower paths, while a uniform IQ4_NL build qualifies
everywhere.

Two corrections to how we first described this (see
`docs/benchmarks/engine-comparison-vs-olliehm-20260916.md` for the audit):

- The **prefill** gain is the fork's **MMB large-batch kernels** (`mmb.cu`), which are gated at
  `T ≥ 512` (`mmb_min_t()`) — so MMB is **off during decode**. The decode gain is real but comes from
  the decode-path kernels (QSA/top-k/hyper-connection/`mmvq`), not MMB.
- Similarly, a mixed-layout quant's penalty is not one thing: it falls back on the prefill path *and*
  on the decode path, independently.

**We also tried and rejected:** UD-IQ4_XS (mixed layout, fell back), Q4_K_M, and an FR-Spec 65k-vocab
draft head (works, but net-neutral at n-max 2 — the MTP operating point is not bandwidth-bound). The
full comparison trail is in `docs/benchmarks/`.

---

## Benchmarks

All numbers: native Windows, WSL shut down, page cache warm (**rep ≥ 3** — see the methodology note),
single instance, `-c 262144`.

### Prefill (max-prefill shape, `-ub 16384`, no drafter)

| context | prefill t/s |
| ---: | ---: |
| 16,384 | **1,031** |
| 65,536 | 993 |
| 131,072 | 925 |
| 196,608 | 859 |
| **251,904** | **812** |

Prefill is a **shallow arc, not a cliff**: ~985 t/s through the 32k–65k band, declining gently to 812.
A 251k prompt ingests in ~5 minutes.

### Decode

| context | serial (no drafter) | **MTP n-max 2** | acceptance |
| ---: | ---: | ---: | ---: |
| 16,384 | 28.3 | **31.2** | 56% |
| 65,536 | 27.8 | **32.6** | 65% |
| 131,072 | 26.9 | **32.8** | 70% |
| 251,904 | 25.1 | **31.0** | 73% |

**Decode is essentially depth-independent** (31.0–32.8 t/s across a 15× context span) and **acceptance
*rises* with depth**. That is not what you would expect, and it is a real, reproduced shape.

### The `-ub` finding

A large ubatch is usable **with** the MTP draft head attached — which earlier work had ruled out. Lifting
that restriction recovered **18–25% prefill** at depth (778 → 970 t/s @16k in that test).

---

## Quickstart

```bat
:: 1. SDK  (TheRock Windows HIP for gfx1151, clang 24)
::    latest nightly: https://nightly.repo.amd.com/rocm/core/tarball/
::    -> extract to C:\AI\sdk\therock1151

:: 2. Build the fork (see setup/ for the full script)
setup\build-windows.cmd

:: 3. IMPORTANT: the exe must find the SDK's HIP runtime beside it, not System32's.
setup\pin-hip-dlls.cmd

:: 4. Run
llama-server.exe ^
  -m  models\Qwen3.8-Flash-Next-IQ4_NL-PROJFIX-00001-of-00009.gguf ^
  -md models\mtp-Qwen3.8-Flash-Next-shared-Q8_0.gguf ^
  --spec-type draft-mtp --spec-draft-n-max 2 --spec-draft-p-min 0.0 ^
  -dev ROCm0 -ngl 999 --n-gpu-layers-draft 999 -fa on ^
  -fit off --load-mode none -ctk f16 -ctv f16 ^
  -c 262144 -b 8192 -ub 8192 --parallel 1
```

Two things will bite you if you skip them:

- **The HIP DLL pin (#3).** `ggml-hip.dll` imports `amdhip64_7.dll` by *name*; Windows resolves it from
  the exe's directory first, then System32. With no local copy the driver's older copy shadows the SDK's
  and HIP fails at device init with a misleading `cudaMemGetInfo failed (invalid argument)`. Copying the
  SDK runtime beside the exe fixes it. `fix-hip-dll.ps1` does this.
- **WSL must be shut down** (`wsl --shutdown`) for every measurement. `vmmemWSL` holds host RAM and, on a
  UMA box, corrupts prefill numbers — it silently produced a fake "cliff" twice before we caught it.

---

## What we learned investigating performance

The honest version, because most of it is negative results and they matter more than the positives:

**Where the time goes.** A decode token reads **4.219 GB** of weights (exact GGUF census): routed experts
32%, attention 30%, output head 12%, hyper-connections 9%, GDN 8%, norms 6%, shared expert 3%. Ideal at
235.7 GB/s is 17.9 ms; we run ~33 ms serial.

**We measured the real kernel, in-graph.** A standalone harness driving the actual production `MUL_MAT`
gives **≈5.4 µs fixed + ~133 GB/s marginal per op**. That means efficiency is set by *output rows*:
`lm_head` (R=248k) hits **100% of bandwidth**, `attn_q` 85%, but the router (R=512) only **41%**.

**What did NOT work** (each measured, with an interleaved A/B harness for ~1–2% effects):

| candidate | result |
| --- | --- |
| small-K MMVQ rows-per-block (RDNA3.5) | inert — gfx1151's RDNA2 table can never trigger it |
| borrowing the RDNA3.0 MMVQ parameter table | **−21%** |
| MMVF prefetch for the F32 router | −0.9% (noise) |
| `rpb` 1→2 for verify widths | covered, +0.3% (noise) |
| K-splitting the small-R ops | **wrong lever** — the cost is per-op, not per-block |
| q8_0 KV cache | hard-blocked: the sparse path asserts f16 |
| lowering `mmb_min_t` for short prompts | ~0% at every size |
| PLE host-side staging | 0.054% of decode wall |

**A correction we published and then retracted:** we initially reported a "uniform 37% bandwidth
shortfall" as ALU-bound. It wasn't — the *benchmark's own* contended `atomicAdd` epilogue was the
bottleneck. With a fair epilogue the same integer kernel reaches **~100% of bandwidth**. The lesson is
now a rule here: every in-vitro number gets an epilogue-fairness and code-path-coverage check before it
is allowed to explain anything.

**Also refuted along the way, by better measurement:** a "configured-context penalty" (it was a warm-up
ramp — prefill needs 3–4 reps to reach steady state at any `-c`) and a "deep-context prefill cliff"
(same artifact).

Full trail: **`docs/benchmarks/`** — 110+ dated reports, including the retractions and the raw evidence.

---

## Future plan

**1. Fine-tune the MTP draft head** (the main remaining lever). Acceptance is 56–73% and the head is a
single trained MTP block. We have a working hidden-state dump harness (`llama_set_embeddings_nextn`)
that produces `(h_nextn, next-token)` training pairs from real traffic. Plan: adapt the head's
input/fusion projections and normalisation against the actual quantized target, freezing the target and
the shared output projection; screen a small adapter rank (8 vs 16) before touching the expert FFN.
Success metric is **held-out emitted tokens/second after export**, not training loss.

**2. Adopt sequence-level correctness gates before believing any speed number.** olliehm's gate set
(single-turn, multi-turn, depth bands, ~24k needle retrieval) is the model; his warning that MTP on HIP
can show 2× tok/s with collapsed output matches what we found from the numerical side. A minimal
version of this belongs in every future benchmark run, not just at release.

**3. Audit `stew675/rdna-boosts` against our tree.** The one component our engine lacks. Bounded task:
diff it, keep what is backend-portable on gfx1151, A/B each piece in the interleaved harness.

**4. Grouped GEMV for the small-R projections.** The measured per-op cost means batching independent
same-K projections (router, shared expert, HC down/up) into fewer, larger `MUL_MAT`s is the correct
lever — bounded at **~6%** of decode. Must be validated in the real operator before shipping.

**5. Remove dead epilogue work.** At `nwarps == 1` (our case) the MMVQ epilogue still emits an
unconditional `__syncthreads()` and shared-memory machinery. Needs a compiled-resource check first, then
a measured A/B.

**6. Re-test recurrent-state checkpoint counts.** olliehm documents `--ctx-checkpoints` as *mandatory*
for MTP (21.4 → 5.1 t/s without it). Our fork carries the equivalent and we have never swept the count.

**7. Longer context.** 262k is the trained limit; the machinery already works at 251k with no memory
failure.

**Out of scope for now:** general split-K, whole-model persistent execution, a q8 QSA kernel, and
anything requiring retained-PM4 (a bare-metal Linux ROCm change we cannot use on Windows).

**Scope note:** this repository is deliberately **Flash-Next only** — the engine work, its measurement
trail, and the setup recipe. Halogen/Chlorine material and the REV:N product live elsewhere; the
Halogen `LD_PRELOAD` shim we built belongs in its own repository rather than here.

---

## Built on the work of others

This project is a compilation, and it would not exist without these people. Sincere thanks:

**The fork and kernels we build on**
- **[pwilkin](https://github.com/pwilkin/llama.cpp)** (`ilintar`) — the `strix-halo` branch: the extended
  MMB quant kernels, fused F32 PLE, sparse QSA decode and incremental indexer state that make these
  numbers possible. Also the IQ4_NL "PROJFIX" quantization, which is the single biggest performance
  decision documented here.
- **[ggml-org/llama.cpp](https://github.com/ggml-org/llama.cpp)** — upstream, and the MTP/NextN work
  (PRs #27742, #27836, #27941).
- **[myhacsint](https://github.com/myhacsint/llama.cpp)** — the shared-MTP fit fixes (measuring shared
  sidecars with target metadata) that explained our `--fit on` load failure.
- **[SixVolts](https://github.com/SixVolts/llama-halo-hybrid)** — Strix Halo + R9700 patch set: grouped
  `mul_mat_vec_q`, hyper-connection fusions, IQ4_NL `get_rows`.
- **[halo-box](https://github.com/halo-box/strix-llama.cpp)** — PR18's RDNA3.5 kernel work and **PR26**
  (give MTP targets their recurrent rollback slots back), a fix worth more than any single kernel tweak.
- **[drluoto](https://github.com/drluoto/llama.cpp)** — tensor naming and reference work.

**The Linux reference stacks** (the bar we were chasing, and the naming family we joined)
- **[peonist-ai](https://github.com/peonist-ai/halogen-flash-server)** — **Halogen** and
  **halogen-flash-server**: *"the fastest way to run Qwen3.8-Flash-Next on Strix Halo"*. The benchmark to
  beat, and a model of how to document this hardware.
- **[Heretek-AI/chlorine-server](https://github.com/Heretek-AI/chlorine-server)** — Chlorine.
- **[olliehm/qwen-flash-next-windows](https://github.com/olliehm/qwen-flash-next-windows)** — the first
  Windows-native stack for this model, and the one to read alongside ours: 38 t/s decode at 85–100%
  draft acceptance, a Lemonade deployment recipe, an admission shim for sharing one carve, and — most
  valuable of all — sequence-gated correctness validation, including the warning that MTP on HIP can
  produce doubled tok/s with collapsed output. Build recipe, no weights or binaries.

**Measurements, tooling and community**
- **[baldlawyer/strix-halo-iommu-benchmark](https://github.com/baldlawyer/strix-halo-iommu-benchmark)** —
  the IOMMU prefill study.
- **[adelj88/rocm_wmma_gemm](https://github.com/adelj88/rocm_wmma_gemm)**,
  **[shisa-ai/hipEngine](https://github.com/shisa-ai/hipEngine)**,
  **[mighty-studios/StrixHaloCluster](https://github.com/mighty-studios/StrixHaloCluster)**,
  **[vincentkelleher/qwen3.8-flash-next-halo](https://github.com/vincentkelleher/qwen3.8-flash-next-halo)**,
  **[MirkoCovizzi/ninfer-rtx5090-mobile](https://github.com/MirkoCovizzi/ninfer-rtx5090-mobile)**.
- **AMD** — the [TheRock](https://github.com/ROCm/TheRock) build of ROCm/HIP that we compile against.
- **r/StrixHalo** — the community whose shared carve arithmetic, quant layouts and gfx1151 findings
  saved us weeks.

If we have used your work and not credited you, that is an omission on our part — please open an issue.

---

## Methodology notes (so you can reproduce, and so we don't fool ourselves again)

1. **`wsl --shutdown` before every measurement.** WSL holds host RAM; on a UMA box this distorts prefill.
2. **Prefill needs 3–4 warm reps.** rep 0 is cold (mmap paging). A single rep understated deep prefill by
   20–55% and we published that error before catching it.
3. **Report `(throughput @ depth)`.** Prefill varies 2.5× across the context range; a bare "t/s" is
   meaningless.
4. **~1–2% effects need an interleaved A/B** (alternating arms). A single 5-rep run has the same ±1%
   spread as the effect you are chasing.
5. **Log which kernel specialisations actually ran** before trusting any A/B. One of our negatives was
   invalid because the patch could not execute in the configuration we measured.
6. **Check the benchmark's own epilogue.** A contended write in the harness made a 100%-bandwidth kernel
   look like a 46% one.

---

## Repository layout

```
README.md            this document
setup/               SDK + build + DLL-pinning + run instructions
docs/benchmarks/     108 dated findings, benchmarks and retractions
  measured-baseline.json          machine-readable numbers
  acceptance-width-report.md      the W=1/2/3 verify-consistency test
  real-kernel-measured-20260916.md the production-kernel measurement
  acceptance-metric-frozen-*.md   what "acceptance" actually counts
  CODEX-PROMPT-*.md               the review prompts we sent out
kernel-work/         every script and harness behind the numbers
  mmvqbench.cpp       standalone harness driving the REAL ggml MUL_MAT
  shapebench.hip      memory-access vs kernel-shape microbenchmarks
  fnbench.py          token-exact prefill/decode measurement
  interleaved-ab.ps1  high-confidence A/B for 1-2% effects
  build-target.bat    incremental rebuild of one ggml target
  results/            small JSON evidence (raw logs are gitignored)
scripts/flashnext-*  the lane/client launchers used for these runs
```

Nothing here is a vendored engine: this repo is **the measurement work, the harnesses and the setup
recipe**. The engine itself is the upstream fork named in *Built on the work of others*, and the model
weights are fetched separately (see `setup/README.md`).

---

## License & status

Measurement work and harnesses published so the Windows-native path is reproducible instead of
folklore. Code under the repo is licensed as its upstream sources are; the write-ups are free to reuse
with attribution. **Everything here is measured on one physical machine** — treat it as reproducible
evidence, not a vendor benchmark, and re-run the harnesses before trusting any single figure.

*strix-alloy — one consumer Windows PC. A 125B MoE. 34 t/s.*
