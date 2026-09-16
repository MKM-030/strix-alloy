# Follow-on session prompt: faster decode kernel for Flash-Next on Bosgame M5

Paste this into a **fresh session**. It is self-contained; it points at the context files in this repo.

---

You are a GPU-kernel + LLM-inference engineer. Your job: design and prototype a **faster DECODE** kernel
for **Qwen3.8-Flash-Next** (`qwen4exp` MoE, ~6B active, 512 experts) on a **Bosgame M5** mini-PC
(AMD Ryzen AI Max+ 395, Radeon 8060S, **gfx1151 / RDNA3.5 wave32**, 128 GB LPDDR5X ~200–240 GB/s),
running on **Windows 11 + WSL2 over `/dev/dxg`** (no `/dev/kfd`, so no PM4/replay runtime).

**Read first (in this workspace `C:\Projects\REV-N-ornith-eval-20260911`):**
- `docs/benchmarks/KERNEL-CONCEPT-CONTEXT-BRIEF-20260913.md` — full hardware/model/engine context and measured data.
- `docs/benchmarks/kernel-architecture-and-decode-concept-20260913.md` — the consolidated concept and ranking.
- `docs/benchmarks/codex-astra-kernel-review-raw-20260913.txt` — a prior expert review to build on (don't repeat it).
- `docs/benchmarks/flash-next-variant-comparison-20260912.md`, `halogen-production-windows-20260913.md`,
  `strix-halo-fork-windows-sharing-draft-20260913.md` — the measurements and the Windows fork adaptation.

## Established context (do not re-derive)
- Prefill is already good: `pwilkin/llama.cpp@strix-halo` (already built at `/home/revn/strix-llama`,
  commit `f5daaa3c`) hits ~300 t/s on a stock quant and ~1200 t/s published on its custom quant.
  **Decode is the weak point** (we measure ~7 t/s on Flash-Next stock; author ~26 t/s native Linux).
- Weight-bandwidth ceiling is ~63–75 t/s for ~6B active at 4.25 bits/weight. We see 143 ms/token, so
  **~130 ms/token is non-bandwidth**. That is your target.
- The `strix-halo` fork is **Flash-Next-targeted**; off-architecture it is neutral/worse. Build ON it.
- Codex "Astra" ranked strategies: **A(graphs) > E(spec decode) > F(PLE cache) > G(Q8 KV) > D(fused MoE)
  > C(fp4) > H(own fork) > B(PM4)**, first experiment = **A**.

## Your task
1. **Run experiment A first:** graph-enabled vs graph-disabled, non-speculative decode A/B on the same
   Flash-Next binary + quant + context + warm PLE state. Prove graph capture/instantiate/replay works and
   is numerically correct over this DXG runtime; prove execution *reuses* graphs across changing expert
   IDs/positions; record ms/token, graph rebuild count, GPU gaps, PLE wait. This separates submission
   overhead from kernel execution and host stalls — do it before proposing any new kernel.
2. **Instrument the unknowns** the review flagged: selected-experts-per-token, per-layer time split,
   exact quantized tensor sizes. A precise bandwidth model needs these.
3. Then **design the decode kernel concept**: pick from A/E/F/G/D plus the three techniques in §4 of the
   concept doc (selected-expert×output-tile scheduling; decode-specific weight packing; register/occupancy
   aware GEMV tiling). Give expected gain, effort, risk, and the next experiment for each.
4. **Also produce a kernel-architecture comparison** (pros/cons for THIS hardware, Windows/WSL vs native
   Linux) across: llama.cpp mainline HIP, `strix-halo` fork, Halogen, Ciru/vLLM, chlorine-server,
   Vulkan forks, ROCmFPX/agentionai fp4, EngramHalo.

## Method / constraints
- Work under `/home/revn` in WSL; source `~/ciru-runtime/sources/vllm-glm53-strix/runtime-env.sh`, export
  `HSA_ENABLE_DXG_DETECTION=1`. GPU is a ROCm0 device (`llama-bench --list-devices`).
- **WSL memory cap ≤72 GB; run ONE heavy job at a time** — parallel heavy jobs hard-restarted the host.
- **Stage models onto WSL ext4** (`~/models/…`) before benchmarking; `/mnt/c` (9p) makes loads 10–13 min.
- Never start the REV:N product Cloud/FiveM; no paid API/overage; **no pushes**. Do not run `flash_serve`
  under `hipshim*.so`.
- You may **build your own fork** — branch from `pwilkin/llama.cpp@strix-halo` (it already builds over DXG
  with `-DGGML_HIP=ON -DGPU_TARGETS=gfx1151 -DGGML_HIP_GRAPHS=ON -DGGML_HIP_MMQ_MFMA=ON`).

## Collaborate (optional, if available)
- **Codex** (installed, `gpt-6-astra`): `codex exec -s read-only -C <dir> --skip-git-repo-check "<prompt>"`
  for an independent review of each kernel proposal.
- **GLM 5.3** via `zai` is blocked until `ZAI_API_KEY` is set; use it if the key appears
  (`zai -p "<prompt>" -m <glm-model>`).

## Deliverable
A decode-kernel design doc with: the graph A/B result, the instrumented stage breakdown, a ranked
kernel-strategy table with expected gains, a concrete first kernel to build, and the reproduction steps.
Be explicit about what is measured vs estimated, and flag anything the prior review got wrong.
