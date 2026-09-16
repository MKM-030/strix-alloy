# strix-alloy

**A 125B-parameter MoE (~6B active) running on a consumer Windows PC — natively.**

Qwen3.8-Flash-Next on an AMD Ryzen AI Max+ 395 mini-PC. No Linux, no WSL, no CUDA, no datacenter GPU.

| | |
| --- | --- |
| **`llama-bench`** | **pp512 761.3 t/s** · **tg128 31.5 t/s** — the standard tool, comparable to every other Strix Halo number |
| `llama-bench`, 16k prompt | pp16384 892.6 t/s · tg128 30.2 t/s |
| prefill, served | 1,031 @16k · 993 @65k · 925 @131k · **812 @251k** |
| decode, served | **31–47 t/s** with MTP (depends how predictable the output is) · 28.3 serial |
| **context** | **251,904 tokens**, works end to end, no OOM |

**Why `llama-bench` is the headline.** It defaults to `-p 512 -n 128` and is the tool upstream, ilintar,
olliehm and the Strix Halo threads all report, so it needs no translation. It also **cannot drive a drafter**,
which makes `tg128` plain serial decode — the engine's own speed, free of the content-dependent acceptance
rate that makes bare MTP figures hard to compare. Against ilintar's published Linux numbers on the same tool:
**26% behind on prefill** (893 vs 1204) and **15% ahead on serial decode** (30.2 vs 26.3).

> The served figures below run ~15% higher than `llama-bench` for the same shape, and we do not have a full
> explanation — it is not warm-up (`-r 8` does not climb). We quote the `llama-bench` number as the headline
> because a third party can reproduce it in one command. Details in
> [`docs/benchmarks/canonical-llama-bench-20260916.md`](docs/benchmarks/canonical-llama-bench-20260916.md).

The transformer is ~125B (121B routed experts + ~4B attention/embeddings). The checkpoint also carries a
separate 51B PLE n-gram table living in host memory — model + table ≈ 176B, sometimes quoted as "177B".
Use 125B for the model.

## Hardware

| | |
| --- | --- |
| SoC | AMD **Ryzen AI Max+ 395** |
| GPU | Radeon **8060S** — gfx1151, RDNA3.5, wave32, 40 CU |
| Memory | 128 GB LPDDR5X **unified**, ~236 GB/s measured ceiling |
| Carve | **96 GB** dedicated (device pool ~108 GiB) |
| Box | Bosgame M5 mini-PC |
| OS | **Windows 11 native** |

The unified memory drives everything: the carve trades host RAM for device pool, and the ~236 GB/s
ceiling is what makes a bandwidth-bound engine like this viable at all.

## Model & quantization

**Qwen3.8-Flash-Next** (`qwen4exp`): 48 layers, 512 routed experts (top-10) + 1 shared, FFN width 640,
`n_embd` 2560, 4 hyper-connection streams, hybrid GatedDeltaNet + full attention, QSA lightning indexer
(top_k 2048), ~27 GiB mmap'd PLE table.

**Chosen quant: `IQ4_NL` "PROJFIX"** — every tensor IQ4_NL, uniformly. Counter-intuitively it is
*larger* than the popular UD-IQ4_XS (4.52 vs 4.24 bpw) and dramatically faster:

| depth | UD-IQ4_XS prefill / decode | **PROJFIX prefill / decode** | gain |
| ---: | ---: | ---: | ---: |
| 1,024 | 260 / 6.8 | **469 / 30.4** | +82% / **+347%** |
| 8,192 | 474 / 14.4 | **593 / 28.0** | +25% / **+94%** |
| 16,384 | 473 / 14.5 | **590 / 29.0** | +25% / **+100%** |
| 32,768 | 459 / 14.5 | **582 / 28.7** | +27% / **+98%** |

The reason is layout, not bit-width: this fork's fast paths are built around **resident IQ4_NL**, and a
mixed-layout quant only partially qualifies, falling back to slower kernels. The prefill part of that gain
comes from the fork's MMB large-batch kernels — gated at `T ≥ 512`, so decode never uses them.

Also tried and rejected: UD-IQ4_XS, Q4_K_M, and an FR-Spec 65k-vocab draft head (net-neutral at n-max 2).

## Benchmarks

Everything below is **served** (`llama-server`), not `llama-bench` — that is why it sits ~15% above the
headline. Native Windows, WSL shut down, page cache warm (rep ≥ 3), single instance, `-c 262144`.

**Prefill** — max-prefill shape (`-ub 16384`, no drafter):

| context | 16,384 | 65,536 | 131,072 | 196,608 | 251,904 |
| --- | ---: | ---: | ---: | ---: | ---: |
| t/s | **1,031** | 993 | 925 | 859 | **812** |

A shallow arc, not a cliff: ~985 t/s through the 32k–65k band, declining gently. 251k ingests in ~5 min.

**Decode** — MTP n-max 2, shared draft head:

| context | serial | **MTP** | acceptance |
| ---: | ---: | ---: | ---: |
| 16,384 | 28.3 | **31.2** | 56% |
| 65,536 | 27.8 | **32.6** | 65% |
| 131,072 | 26.9 | **32.8** | 70% |
| 251,904 | 25.1 | **31.0** | 73% |

Decode is essentially depth-independent across a 15× context span, and acceptance *rises* with depth.

**Acceptance tracks the *content*, not the engine.** We previously reported it as run-to-run instability
(47% vs 65% on the same config); that was most likely content mix between runs, because warm repeats of a
*fixed* workload were repeatable within the sample (three consecutive doc-continuation runs: 42.3%, 39.6%,
39.6% at `n-max 2`), while different text gives very different ratios at identical settings — 40% on
doc-continuation, 92% on an instructed answer. That is a small sample, so treat it as the working
explanation rather than a proof. The practical rule holds either way: **always state the workload with an
acceptance figure**, because a bare "MTP acceptance" is not comparable to anything.

That also sets the right draft depth, which is content-dependent:

| content | acceptance @n-max 2 | best depth | gain vs `n-max 2` |
| --- | ---: | --- | ---: |
| instructed answers (structured, predictable) | 92% | `n-max 4` | **+10%** |
| doc-continuation, 1k | 53% | `n-max 2` | — |
| doc-continuation, 8k | 40% | `n-max 2` | — (n-max 4 is −6%) |

We publish `n-max 2` because it is near-optimal on both and never collapses; a chat-heavy deployment should
use 4, and a low-acceptance one should use 1. An adaptive controller that sized drafts from a measured
acceptance EMA was ported and tested — it works, but loses to the better fixed value on every content class
(−4.7% to −9.6%), because its "full accept → draft deeper" rule assumes depth always pays, which is not true
here. Kept behind `--spec-draft-adaptive`, off by default.

## Quickstart

```bat
:: 1. TheRock Windows HIP SDK for gfx1151 (clang 24)
::    nightly: https://nightly.repo.amd.com/rocm/core/tarball/  ->  C:\AI\sdk\therock1151
::    (plain `sort` puts 10.2.0a before 7.9.0rc — use `sort -V`)

:: 2. Build
setup\build-windows.ps1 -Src <fork> -Sdk C:\AI\sdk\therock1151

:: 3. Pin the SDK HIP runtime beside the exe — NOT optional, see setup/README.md
setup\pin-hip-dlls.ps1 -Sdk C:\AI\sdk\therock1151 -BinDir <build>\bin

:: 4. Run
llama-server.exe ^
  -m  Qwen3.8-Flash-Next-IQ4_NL-PROJFIX-00001-of-00009.gguf ^
  -md mtp-Qwen3.8-Flash-Next-shared-Q8_0.gguf ^
  --spec-type draft-mtp --spec-draft-n-max 2 --spec-draft-p-min 0.0 ^
  -dev ROCm0 -ngl 999 --n-gpu-layers-draft 999 -fa on ^
  -fit off --load-mode none -ctk f16 -ctv f16 ^
  -c 262144 -b 8192 -ub 8192 --parallel 1
```

Three things that will bite you:

- **The HIP DLL pin.** `ggml-hip.dll` imports `amdhip64_7.dll` by name, and Windows checks the exe's
  directory before System32. Without a local copy the driver's older DLL shadows the SDK's and HIP dies
  at device init with a misleading `cudaMemGetInfo failed (invalid argument)`.
- **`-fit off --load-mode none`** is required with the shared MTP head. `--fit on` measures the sidecar
  standalone (which fails — it borrows the trunk's embeddings), then silently fits without it.
- **`wsl --shutdown` before any measurement.** WSL holds host RAM and, on a UMA box, distorts prefill.

Full flag notes, SDK setup and hygiene: **[`setup/README.md`](setup/README.md)**.

## Why Windows-native

The Strix Halo scene is Linux-first — the fastest published stacks (**Halogen**, **Chlorine**) need a
native Linux host, and the reference HIP fork targets Linux. While I was able to build a bridge and make
the Halogen engine usable under WSL, only the Qwen3.8-27B model fit into the 96 GB carve. I will continue
that development in a different project and eventually release it with a different Flash-Next quant.

Two stacks now run this model natively on Windows: **olliehm's** (published first) and `strix-alloy`.
Neither is a fork of the other — we share an upstream ancestor and diverge after that.

| | **olliehm** | **strix-alloy** |
| --- | --- | --- |
| engine | upstream llama.cpp + **`stew675/llama-cpp-rdna-boosts`** patches, via **Lemonade** | **`pwilkin` `strix-halo`** fork, `llama-server` directly |
| prefill | ~660 t/s @8k–17k | **1,031 @16k · 993 @65k** |
| decode, no MTP | 20.3 @8k | **28.8 @8k · 31.5 `llama-bench tg128`** |
| decode, MTP | **38 t/s** *(no depth published)* | 31–47 t/s *(content-dependent)* |
| acceptance | **85–100%** (`n-max 4`, `p-min 0.75`) | 40–92% (`n-max 2`, `p-min 0.0`) — content-dependent |
| context | 262,144 | 251,904 verified |
| quant | UD-IQ4_XS — for **fit margin** | IQ4_NL PROJFIX — for **speed** |
| drafter | full Q8_0 head (~3.2 GB) | **shared** Q8_0 head (2.6 GB) |
| footprint | 74.0 GB in carve | ~74 GB |

Read the decode/acceptance rows with care: acceptance is content-dependent on **both** engines, so two single
figures taken on different prompts do not rank them. His `n-max 4` at 85–100% is a better operating point than
our published `n-max 2` for chat-like text — which is why we now report the depth table above instead of one
number.

Different kernels, different lineage: our tree carries the fork's backend work (MMB large-batch kernels,
fused F32 PLE, sparse QSA decode, hyper-connection kernels) while his carries RDNA tuning — which is why
prefill differs by ~1.5×. We tested his exact MTP flags on our engine at 65k: his **acceptance reproduces
(96%)** but his **throughput does not** (26.4 vs our 33.1 t/s), because the higher `n-max` costs a 5-row
verify per round for drafts the `p-min` gate usually discards.

Two things in his repo matter beyond any single number:

- **olliehm correctness gates.** He gates on *sequence-level* validation — single-turn, multi-turn, depth
  bands, needle retrieval — and warns that MTP on HIP can show 2× t/s while emitting collapsed text. We
  hit variants of this from the numerical side. Speed-only benchmarking on this stack is not trustworthy,
  in either repo.
- **olliehm deployment work.** A Lemonade recipe and an admission shim letting several instances share
  one carve — infrastructure we do not have.

Full audit: [`docs/benchmarks/engine-comparison-vs-olliehm-20260916.md`](docs/benchmarks/engine-comparison-vs-olliehm-20260916.md).

## What we found investigating performance

A decode token reads a **nominal ~4.2 GB** of active weights in our census model: routed experts 32%,
attention 30%, output head 12%, hyper-connections 9%, GDN 8%, norms 6%, shared expert 3%. Ideal at
236 GB/s is ~17.9 ms; we run ~33 ms.

> **Provenance caveat.** This is a *model* (tensor types × sizes × a selected-expert fraction from
> `kernel-work/byte-accounting.py`), not a bus measurement, and older reports in this repo used a different
> dtype mix (a Q6_K head, F32 routers) and total ~4.25 GB. Treat it as **nominal active weight payload**,
> not as DRAM traffic. Activation quantisation, state traffic, attention reads, repeated weight reads and
> cache reuse are accounted separately, if at all.

A standalone harness driving the **real** production `MUL_MAT` fits **≈5.4 µs + bytes/133 GB/s** across the
operator family it tested, so efficiency is set by *output rows*: `lm_head` (R=248k) reaches **100% of
bandwidth**, `attn_q` 85%, the router (R=512) only **41%**. Those are fitted parameters of that operator
family — the intercept is not proven to be host launch overhead, nor the slope proven to be DRAM bandwidth.

Measured negatives (each via an interleaved A/B): small-K MMVQ rows-per-block (inert on RDNA3.5), the
RDNA3.0 parameter table (**−21%**), MMVF prefetch (−0.9%), `rpb` 1→2 (+0.3%), K-splitting the small-R ops
(wrong lever — the cost is per-op, not per-block), q8_0 KV (the sparse path asserts f16), lowering
`mmb_min_t`, PLE host staging (0.054% of decode wall).

Two more from the sibling forks, ported and measured rather than assumed:

- **`halo-box`'s `MMID_512`** (MoE expert routing placed by a block-wide histogram instead of one warp per
  expert): ported and built, but **it cannot affect decode on this engine**. A probe counting calls by token
  width, run against a 200-token decode, recorded **one call total — prefill, zero at `n_tokens==1`**. The
  helper is reached only from the large-batch paths (`mmb.cu` at `T ≥ 512`, `mmq.cu`, `mmf.cu`); serial decode
  takes MMVF/MMVQ. So "−0.2% decode" measured a path decode never executes; the honest status is *neutral and
  unexercised in decode*, and the earlier "HIP graphs absorb the launch overhead" explanation was wrong too
  (a 512-block grid is one launch, not 512).
- **The rest of `halo-box`'s HIP set is deprioritised, not disproved**: `MMV_GROUP` is Q8_0-only as implemented,
  and a GGUF census shows this model is IQ4_NL for every expert and attention tensor (only two HC projections and
  `ple_key` are Q8_0) — but the fused matvec prologues **do** contain an IQ4_NL path behind a default-off gate
  (`MMVQ_FQ_IQ_TYPES`), so that is an untested candidate rather than a closed door. `WEIGHTED_DOWN` is IQ4_NL and
  applicable, with a likely-small but **unmeasured** effect.

One published claim we retracted: a "uniform 37% bandwidth shortfall" attributed to ALU limits was the
*benchmark's own* contended `atomicAdd` epilogue. With a fair epilogue the same kernel reaches ~100% of
bandwidth.

Full trail — 110+ dated reports including the retractions — in **[`docs/benchmarks/`](docs/benchmarks/)**.

## Future plan

1. **Fine-tune the MTP draft head** — the main lever. Acceptance is 56–73% and the head is one trained MTP
   block. We have a hidden-state dump harness producing `(h_nextn, next-token)` pairs from real traffic.
   Adapt the input/fusion projections against the quantized target, freeze the target and shared output
   projection, screen adapter rank 8 vs 16. Success metric is held-out emitted tokens/second, not loss.
2. **~~Find the MTP acceptance instability~~** — working explanation: acceptance tracks the workload, and warm
   repeats of a fixed workload were repeatable within the sample. Report the workload alongside the figure and
   prefer per-position acceptance over the single aggregate ratio.
3. **Audit `stew675/rdna-boosts`** against our tree and A/B each portable piece.
4. **Grouped GEMV** for the small-R projections (bounded at ~6% of decode).
5. **Remove dead epilogue work** at `nwarps == 1` (unconditional `__syncthreads` + shared machinery).
6. **A depth controller that measures whether depth pays.** The ported EMA controller assumes depth always
   helps and loses to the better fixed value on every content class (−4.7% to −9.6%). The missing signal is
   the *marginal* cost of another draft token on this engine, not the acceptance EMA.

Out of scope: general split-K, whole-model persistent execution, a q8 QSA kernel, retained-PM4.

## Built on the work of others

**The fork and kernels we build on**
- **[pwilkin / ilintar](https://github.com/pwilkin/llama.cpp)** — the `strix-halo` branch: extended MMB
  quant kernels, fused F32 PLE, sparse QSA decode, incremental indexer state; and the IQ4_NL "PROJFIX"
  quantization.
- **[ggml-org/llama.cpp](https://github.com/ggml-org/llama.cpp)** — upstream, and the MTP/NextN work.
- **[myhacsint](https://github.com/myhacsint/llama.cpp)** — shared-MTP fit fixes.
- **[stew675](https://github.com/stew675/llama-cpp-rdna-boosts)** — the RDNA boosts patch set.
- **[SixVolts](https://github.com/SixVolts/llama-halo-hybrid)** — Strix Halo + R9700 kernel patch set.
- **[halo-box](https://github.com/halo-box/strix-llama.cpp)** — RDNA3.5 kernel work; PR26 (MTP recurrent
  rollback slots) is worth more than any single kernel tweak.
- **[drluoto](https://github.com/drluoto/llama.cpp)** — tensor naming and reference work.

**Linux reference stacks** (the bar, and the naming family we joined)
- **[peonist-ai](https://github.com/peonist-ai/halogen-flash-server)** — **Halogen** and
  `halogen-flash-server`, *"the fastest way to run Qwen3.8-Flash-Next on Strix Halo."*
- **[Heretek-AI/chlorine-server](https://github.com/Heretek-AI/chlorine-server)** — Chlorine.
- **[olliehm/qwen-flash-next-windows](https://github.com/olliehm/qwen-flash-next-windows)** — the first
  Windows-native stack for this model, and the one to read alongside ours.

**Measurements, tooling, community**
- **[baldlawyer/strix-halo-iommu-benchmark](https://github.com/baldlawyer/strix-halo-iommu-benchmark)**,
  **[adelj88/rocm_wmma_gemm](https://github.com/adelj88/rocm_wmma_gemm)**,
  **[shisa-ai/hipEngine](https://github.com/shisa-ai/hipEngine)**,
  **[mighty-studios/StrixHaloCluster](https://github.com/mighty-studios/StrixHaloCluster)**,
  **[vincentkelleher/qwen3.8-flash-next-halo](https://github.com/vincentkelleher/qwen3.8-flash-next-halo)**,
  **[MirkoCovizzi/ninfer-rtx5090-mobile](https://github.com/MirkoCovizzi/ninfer-rtx5090-mobile)**.
- **AMD** — the [TheRock](https://github.com/ROCm/TheRock) build of ROCm/HIP.
- **r/StrixHalo** — shared carve arithmetic, quant layouts and gfx1151 findings that saved us weeks.

If we have used your work and not credited it, that is our omission — please open an issue.

## Reproducing measurements

1. `wsl --shutdown` before every run — WSL holds host RAM and, on UMA, distorts prefill.
2. **Prefill needs 3–4 warm reps.** rep 0 is cold; a single rep understated deep prefill by 20–55% in our
   own early reports.
3. **Report `(t/s @ depth)`** — prefill varies 2.5× across the context range.
4. **~1–2% effects need an interleaved A/B** — a single 5-rep run has the same spread as the effect.
5. **Log which kernel specialisations actually ran** before trusting an A/B.
6. **Check the harness's own epilogue** — see the retracted claim above.
7. **Average ≥3 MTP runs**, and always report acceptance alongside the t/s figure.
8. **Quote `llama-bench` for any cross-engine claim** — `pp512` / `tg128`, one command, no drafter in the
   harness. Served numbers are higher and not directly comparable to published figures.

## Scope, and what is NOT verified

This repository is a **measurement and Windows-integration repository around a locally modified engine**, not
a fully published engine fork. The engine source (`src/`, `ggml/`, the patch series) is **not** in this tree:
`setup/build-windows.ps1` takes a separate `$Src` checkout and builds that. That is the single biggest limit on
what a reader can check, and it is stated here rather than buried.

Consequently these are **UNVERIFIED from this repository alone**:

| Item | Status |
| --- | --- |
| The exact engine source behind the headline binary | **BLOCKED** — not published; no engine hash here lets you rebuild it |
| Whether `MMID_512` executes in the timed decode phase | **RESOLVED — it does not.** Probe: 1 call total in a 200-token decode, all prefill; decode takes MMVF/MMVQ |
| Whether the allocation probe reflects *resident* GPU capacity | **UNVERIFIED** — it shows an allocation-acceptance boundary for one process state, not residency or usable bandwidth |
| The token stream `llama-bench` feeds on Windows | **CONFIRMED** — with UCRT `RAND_MAX = 32767`, `rand() % n_vocab` reaches only 13.2% of a 248k vocab (`rand-check.c`). Workload-identity defect; throughput impact measured at 0–1.4% |
| Why `llama-bench` and the server differ (~4–17%) | **UNRESOLVED, not separable from server spread** — the same construction measured 876 and 952 t/s in two sessions; needs the same stored token array through both entry points |
| Cause of the prefill gap vs ilintar | **UNRESOLVED** — and **not** retained-PM4, which their own page says does not engage on prefill |
| Whole-buffer demotion in the small-carve experiment | **UNRESOLVED** — the slowdown is real and reproduced; the mechanism is inferred, not observed |
| Multi-turn / depth-band / retrieval correctness | **NOT DONE** — see the future plan; drive-level validation is olliehm's, not ours |
| Weight byte-accounting as *DRAM traffic* | **MODEL ONLY** — nominal active payload from tensor metadata, not a bus measurement |

Corrections from external review are welcome and have been applied before — including several where the
first published explanation was wrong (see `docs/benchmarks/`). If you find a number that does not replicate,
please open an issue with the harness, the engine revision and the settings.

## License & status

Measurement work and harnesses, published so the Windows-native path is reproducible instead of folklore.
Free to reuse with attribution. Everything here was measured on one physical machine — treat it as
reproducible evidence, not a vendor benchmark, and re-run the harnesses before trusting any figure.

---

*strix-alloy — one consumer Windows PC. A 125B MoE. 31.5 t/s (`llama-bench tg128`).*
