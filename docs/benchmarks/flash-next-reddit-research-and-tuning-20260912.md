# Qwen3.8-Flash-Next on Strix Halo — Reddit research synthesis and REV:N optimization plan (2026-09-12)

Source: 13 Reddit threads supplied by the founder (r/LocalLLM, r/LocalLLaMA, r/StrixHalo ×7,
r/Qwen_AI, r/unsloth, r/Dimaginar), plus the key repositories their posts and comments point to.
Purpose: find every lever that can raise Flash-Next speed and quality **on this exact box**, so the
World Engine is fast and REV:N has one coherent best local setup. Everything is cited; nothing here
is a claim about our own host until measured.

Our box: BOSGAME BeyondMax, Ryzen AI Max+ 395 / Radeon 8060S (gfx1151), 128 GiB LPDDR5X, Windows 11
+ WSL2. Our own prior findings (carve-out rule `pool = 64 GiB + ½·carve`, hipshim for the 27B
`halogen` engine, Ciru under WSL, WSL `memory=110GB`) are folded in below.

---

## 1. The single biggest finding: there are TWO completely different engines, and they win different things

> **MEASURED, later the same day (see `halogen-flash-next-measured-verdict-20260912.md`).** Halogen
> Flash-Next was downloaded, SHA256-verified, and run here. On this **shared** 128 GB box it is **not
> viable at speed**: its safe `Pin::None` path is stable and fits (262k context in 25.5 GiB) but
> decodes at **0.32 t/s**; its pinned fast path needs ~115 GB of non-swappable host RAM the machine
> does not have, and the shim that reaches it bypasses the engine's own pin guard (reached 1.1 GB
> free before being killed). **The findings below (published 1,300 t/s prefill etc.) are real but
> assume a host of the engine's own.** The llama.cpp/Vulkan shape is therefore the REV:N default.

| | **Halogen** (`peonist-ai/halogen-flash-server`) | **llama.cpp forks** (Vulkan/ROCm) |
| --- | --- | --- |
| Weights | `.hgn` 115.55 GiB + 2.396 GiB quality overlay (speed overlay 2.308 GiB) | `unsloth` GGUF UD-IQ4_XS ~87 GiB (3 shards) + MTP Q8_0 sidecar |
| Openness | **closed source** | open (forks, PRs) |
| Cold prefill | **~1,287 t/s @64K** (published); community: **~1,300 t/s @0 ctx** | ~200–430 t/s (Vulkan; a patched build hit 2,000+ in a sweep) |
| Decode | 30–50 t/s; "only 1 stream, one extra drafted token" | **38 t/s** with MTP (22.5 without) |
| Context ceiling | 262,144 native; 1M with `HALOGEN_ROPE_YARN=4` | 262,144 native (fits at 96 GB carve) |
| Vision | yes (0.6.x, off by default) | yes via `mmproj` |
| Quirk | **does not emit thinking traces** → harnesses time out | emits everything |

**Decisive quotes.** Thread 4 (`r/StrixHalo` "Halogen vs Llama.cpp Vulcan benchmarks"): *"at 0
context Halogen can get up to 1300 t/s prefill"*; *"Halogen consistently is 1k+ on prefill and 30-50
tps on decode."* Thread 13 (alchi-flac's writeup): the llama.cpp branch is *"probably the fastest,
most reliable, and most usable implementation… especially with long context"* — but *"halogen… claims
even crazier numbers, but it is not llama.cpp and it does not have vision"* (since corrected: vision
is live).

**Implication for REV:N:** the World Engine's real load is **cold prefill over long world/scene
context**. Halogen is ~3–5× faster there. That is exactly why we are downloading the `.hgn`. But
Halogen is closed, single-stream-oriented, and holds the machine; llama.cpp is the flexible,
co-resident, open option. The two are not competitors so much as **different deployment shapes**.

---

## 2. MTP (speculative decoding) is the leverage — and it needs a specific build

The whole decode story turns on MTP (multi-token prediction / NextN draft head):

| Config | Decode | Source |
| --- | ---: | --- |
| No MTP | 22.5 t/s | thread 12 (obsidience) |
| **MTP depth 3, `-ub 256`** | **38.6 t/s** | thread 12 |
| MTP shipped depth 4 | 34.0 t/s | thread 12 |
| Halogen MTP (engine-internal) | 30–50 t/s | thread 4 |

Community-verified points:
- **MTP lives in no mainline llama.cpp.** You must apply **PR #28243 (qwen4exp MTP)** onto master
  (thread 12). On Windows the **checkpoint mechanism (PR #28118)** is also required — without it MTP
  *drops* decode from 21.4 → 5.1 t/s (ggml discussion #27950).
- **`-md` must be passed explicitly.** The MTP head sits in an `MTP/` subfolder that sidecar
  auto-discovery does not search; `--spec-type draft-mtp` alone finds nothing and *silently* runs the
  base model. Check for a `draft acceptance = …` line — no line, no MTP (thread 12).
- **Depth 3, not 4.** Depth 4 wins on prose but collapses on RAG-shaped input (25.3 vs 37.8 t/s);
  on a 512-expert MoE every extra drafted token widens the expert set the verify step reads (thread 12).
- **MTP can corrupt sampling at temp>0** — one report of CJK characters leaking into Rust identifiers
  and undefined types at temp 0.2; **temp 0 clean** (thread 13, netvandal). Halogen's 8k default
  output cap is too low for a thinking model — set 32k (thread 4).
- **MTP costs nothing in quality at temp 0**: the target verifies every drafted token (thread 12).

---

## 3. Quant landscape — what actually exists and what to run

| Quant | Size | Notes | Verdict |
| --- | ---: | --- | --- |
| **unsloth UD-IQ4_XS** | ~87 GiB | the quant of record; fits 262k with ~22 GiB headroom at 96 GB carve | **primary choice** |
| unsloth Q4_K_XL | ~92 GiB | fits but **no acceptance gain, ~5% slower**, ~6 GiB headroom | fallback only |
| unsloth Q3_K_XL / Q3 | ~70 GiB | used by several, lower quality | only if space-bound |
| **jcbtc CIRU-STRIX-IU4 / Orca / UL4** | ~? | Strix-Halo-specific, ~Q5 quality, "decent prefill, decent TG with MTP"; **"best quant+runtime combo for q38f on Strix Halo right now"** | strong alt (needs custom llama-server) |
| agentionai ROCmFP4-FAST-imatrix | ~90 GiB | needs `LaurentZuijdwijk/llama.cpp` branch `vulkan/qwen4exp-rocmfpx` built with Vulkan; **crashes at 200k+ ctx on Vulkan** | niche |
| Jab1718 Moe-slices | 85 GB BF16 (91% Pass@1), 44 GB INT8 (83%, 2×24 GB), 26 GB Q4 (24 GB GPU) | expert-pruned by activation profiling | research branch |
| AtomicChat GGUF | — | community distrust: *"misleading about the actual per-weight quantizations"* | avoid |
| REAP-288 4-bit prune | ~40 GB | claimed 98%, but pruned models often *"completely lobotomise the model"* (loops) | avoid |

Halogen's own precision: **5.53 bpw** across 179.55B params (4.55 bpw trunk/experts excluding the FP8
n-gram table). The 4-bit floor is deliberate: 125B + 51B-param n-gram = 335 GiB BF16 / 173 GiB FP8 vs
124 GB memory.

---

## 4. The llama.cpp launch playbook (worst-to-know flags)

From `olliehm/qwen-flash-next-windows` (our box, 96 GB carve) and threads 11/12/13:

```bash
llama-server.exe \
  -m Qwen3.8-Flash-Next-UD-IQ4_XS-00001-of-00003.gguf \
  -md mtp-Qwen3.8-Flash-Next-Q8_0.gguf \
  -c 262144 --host 127.0.0.1 --port 13399 --jinja \
  -fa on --parallel 1 -ctk f16 -ctv f16 \
  --load-mode none -b 512 -ub 512 \
  --spec-type draft-mtp --spec-draft-n-max 4 --spec-draft-p-min 0.75 \
  --temp 1.0 --top-p 0.95 --top-k 20 --min-p 0.0 \
  --presence-penalty 0.0 --repeat-penalty 1.0 \
  --n-predict 16384 --reasoning-budget 6144 \
  --ctx-checkpoints 8 --cache-ram 3072 \
  --chat-template-kwargs '{"enable_thinking":true,"reasoning_effort":"medium","preserve_thinking":false}'
```

Non-obvious flags that matter (each cost someone hours):
1. **`--load-mode none` keeps the ~26.8 GiB PLE (`per_layer_token_embd`) table in host mmap**, out of
   the GPU carve. On Linux the equivalent memory-trick set is
   `--load-mode mmap --tensor-read-lazy auto --no-repack --no-host` (threads 12/13).
2. **`--fit on` with NO explicit `-ngl` or `-c`.** `--fit` only adjusts arguments you did not set, so
   a hard-coded `-ngl`/`-c` silently defeats the GPU/CPU split. Left alone it picks n_ctx 262144 and
   puts ~83.9% on GPU (~62 GB), the correct answer (thread 12).
3. **`-ub 256`, not the 512 default** — +6.5% decode *and* higher draft acceptance (thread 12).
4. **Force the PLE table host-side** with `-ot "per_layer_token_embd=CPU"` if it still thrashes. Do
   **not** use `ple_key`/`ple_value` — those tensors total ~17 MB and the pattern pins nothing
   (thread 12).
5. **`reasoning_effort` = `medium`, not `xhigh`, for agents** — medium scored 2/3 vs xhigh 1/3 on
   PowerShell repair at **2.7× less wall time** (thread 12). Valid values are only xhigh/medium/low.
6. **Multi-session:** `-np 3 --ctx-checkpoints 8` fixes cache eviction (ggml discussion #27950).
7. **`llama-bench` cannot see draft flags** and has an `-ub 2048` trap — don't trust it for MTP.
8. **ROCm < 7.13:** set `GGML_CUDA_DISABLE_GRAPHS=1`.

**Measured (thread 13, alchi-flac / Ninja2777, our hardware class, depth ≥8192):**
- pp128 @ d8192 = 421 t/s; tg64 = 32 t/s; pp1024 @0 = 410–415; tg512 = 31–37 t/s
- pp128 @ d65536 = 335 t/s; tg512 = 28–29 t/s
- 200k+ deep context: ~22.7 t/s, MTP accept 84.9%, GPU busy 84–87%, GPU-bound
- **Prefill ~208 t/s with their local UMA patch, ~117 without it** (thread 12) — a kernel patch worth
  ~1.8× that is *not* upstream.

---

## 5. Halogen configuration playbook (from the 0.6.x repo + thread 4)

Container (Docker: swap `keep-groups` for `--group-add video --group-add render`):

```bash
podman run --rm -p 8731:8731 \
  --device /dev/kfd --device /dev/dri --group-add keep-groups \
  --ipc=host --ulimit memlock=-1:-1 \
  -v ~/halogen-models:/models:ro \
  ghcr.io/peonist-ai/halogen-flash-server:0.6.2
```

Thread 4's production systemd unit adds the group ids and pins the KV shape:
`--group-add 44 --group-add 993`, `-e HALOGEN_API_PORT=8030`, `-e HALOGEN_CACHE_ENTRIES=6`,
`-e HALOGEN_KV_SLOTS=2`, `-e HALOGEN_KV_POOL_POSITIONS=524288`.

Memory knobs (128 GB machine):

| `HALOGEN_KV_POOL_POSITIONS` | Holds | Device |
| ---: | --- | ---: |
| 262,144 | one full conversation / four @65k | 27.8 GB |
| **524,288 (default)** | two full / four @131k | 35.0 GB |
| 786,432 | three full / four @196k | 42.2 GB |
| 1,048,576 | four full / eight @131k | ~41 GB only with `HALOGEN_MAX_TOK=16384` |

- `HALOGEN_MAX_TOK` (default 32768) sizes the prefill arena; **cap the context halving rule**: past
  262,144 the arena is forced to 16384.
- `HALOGEN_FLASH_PIN_TRUNK=0` = no-pin mode: returns ~68 GiB of host RAM, costs *several×* decode.
- `HALOGEN_HOST_RESERVE_GIB` (20) reserves RAM for the n-gram file cache.
- Quality↔speed: `-e HALOGEN_CK_OVERLAY=/models/qwen38-flash-next-w4b.overlay-speed.hgn`.
- Sampling defaults: temp 1.0 / top_p 0.95 / top_k 20 (thinking); 0.7/0.80/20 + presence 1.5 (non-thinking).
- `-e HALOGEN_VISION_TOWER=1` enables images.

**Harness integration gotcha (thread 4):** Halogen does **not** stream thinking traces. Opencode/agent
harnesses that wait for output will time out mid-workflow. Fix:
`"chunkTimeout": 1800000` (30 min) and `"limit": { "context": 262144, "output": 32768 }`. Halogen
defaults output to 8k, too low for a thinking model — raise to 32k.

---

## 6. Kernel / OS / system-level tuning (the "own kernel" question)

The founder asked whether we can build our own quant/kernel. The research says yes, and here is the
actual landscape:

| Lever | Effect | Cost | Source |
| --- | --- | --- | --- |
| **`amd_iommu=off` vs `iommu=pt`** | **+26.2–31.6% prefill** dense, +2.6–8% MoE, decode unaffected | disables NPU + DMA translation | thread 3 |
| `amdgpu.gttsize=126976 ttm.pages_limit=32505856` | GTT sizing (held constant in thread 3) | — | thread 3 |
| **UMA/VRAM carve split** | Windows VRAM = dedicated + ½ system RAM; 96+16=112 GB in one report; "over 110 GB with KV" | see below | threads 11/12 |
| **Local UMA buffer kernel patch** (thread 12's) | **prefill ~117 → ~208 t/s** | not upstream | thread 12 |
| `stew675/llama-cpp-rdna-boosts` patch set | carries unmerged qwen4exp MTP PRs + gfx1151 fixes | build effort | thread 11 |
| **`--load-mode`/`-lzm` lazy n-gram** | pages the model's large lookup table from SSD, saves RAM (47.7 GiB is Halogen's n-gram table; the GGUF PLE table is 26.8 GiB — do not mix them) | slower cold reads | threads 7/10 |
| Swap/pagefile for page cache | reclaims ~8–10 GB for the n-gram cache | — | thread 10 |
| Windows pagefile 163840 MB | raises commit ceiling to ~127.6 GB so full 262k profile fits | elevated shell | our `developer-world-model-profiles.md` |

**Important hardware truths from these threads:**
- **ROCm's HIP pool on gfx1151 can sit below the weight size** — *"the HIP pool on this chip sits
  below the weight size, so ROCm can't hold this model at a useful quant regardless of flags. Vulkan
  can"* (thread 12). This is why our WSL/HIP path needed the carve-out tricks and why several Strix
  users run **Vulkan on Windows** for Flash-Next.
- **WSL has no Vulkan** (only `lavapipe`) — our own finding. So on Windows/WSL we have two real paths:
  **HIP in WSL** (what we built) or **native Windows Vulkan** (Lemonade + the fork).
- **IOMMU is a Linux kernel param** — it does not apply inside WSL. The +26–32% is a native-Linux
  (Fedora) result; the WSL equivalent would be tested on the Windows side or not at all.
- **NPU (FastFlowLM)** can run Qwen3.6-35B-A3B *alongside* a GPU model at ¼ the power (20 vs 80 W),
  no MTP yet — but it needs IOMMU on, conflicting with the `amd_iommu=off` prefill win (thread 3).

---

## 7. Community tooling index (all cited repos)

- `peonist-ai/halogen-flash-server` — the closed engine; OpenAI API, vision, KV pool tuning.
- `olliehm/qwen-flash-next-windows` (MIT) — Windows 11 recipe, MTP coherence gates, fit measurement,
  admission proxy to avoid WDDM oversubscription freeze.
- `stew675/llama-cpp-rdna-boosts` — Windows HIP patch set (carries MTP PRs).
- `myhacsint/llama.cpp` branch `production/strix-halo-qwen4exp-b10685` — Vulkan build snapshot.
- `drluoto/llama.cpp` `strix-halo-flash-next` + `drluoto/Qwen3.8-Flash-Next-MTP-GGUF` — ROCm path.
- `LaurentZuijdwijk/llama.cpp` `vulkan/qwen4exp-rocmfpx` — ROCmFP4 support.
- `halo-box/strix-llama.cpp` — active community Strix Halo fork (hip+vulkan); Nate's lineage.
- `kyuz0` / `Nathanw1014/llama.cpp:strix-halo-vulkan` — kyuz0 toolbox builds.
- `Jab1718/Moe-slices` — activation-profiled expert pruning.
- `mritzco/strixhalo-recipes` — versioned recipe/result registry (tools: `analyze.py`, `test`).
- `baldlawyer/strix-halo-iommu-benchmark` — the IOMMU harness + JSON + power/clock traces.
- `jcbtc/Qwen3.8-Flash-CIRU-STRIX-IU4`, `…-Orca`, `jcbtc/Ornith1.5-Ciru-Halo-Agent-vllm-strix-halo`.
- `lemonade-server.ai` — plug-and-play Windows over the fork; `FastFlowLM` (ROCm) for the NPU.
- ggregml discussion **#27950** — the canonical "Flash-Next on Strix Halo" build/flag thread.

---

## 8. Recommended REV:N configuration (proposal, not yet measured on our box)

Two shapes, because REV:N's World Engine must run **permanently** beside brain + STT + TTS:

**Shape 1 — World Engine = Halogen (best speed, dedicated).** Run `flash_serve` in WSL under the
`hipshim` with `PIN_TRUNK=0` on the **minimum carve-out** (host ~127 GB, which we already set),
`HALOGEN_KV_POOL_POSITIONS=524288`, `HALOGEN_CACHE_ENTRIES=6`, `HALOGEN_KV_SLOTS=2`. This is what the
running download is for. Expect ~1,300 prefill @0 / 250–380 @60k, 30–50 t/s decode. **Co-residence is
the open question** — the engine "runs best on a host of its own"; gemma4+STT+TTS may not fit beside
it on 128 GB. If the World Engine must coexist with a live brain, this shape likely wants a second box.

**Shape 2 — World Engine = llama.cpp Vulkan UD-IQ4_XS + MTP (co-resident).** Native Windows Vulkan
(not WSL), `--fit on`, `--load-mode none`, `-ub 256`, MTP depth 3. ~200–430 prefill, 38 t/s decode,
~74 GB footprint at 96 GB carve. Leaves room for gemma4 (~14 GB) + STT + TTS in the headroom. This is
the better "one machine runs everything" shape and the recommended default for REV:N today.

**Brain:** keep gemma4 (unchanged; per the combination matrix it is the only candidate meeting the
few-hundred-ms bar). **STT/TTS:** unchanged.

**System tuning to apply:** BIOS UMA = Auto/min for Flash-Next's engine; Performance mode; IOMMU
decision only if we boot native Linux (off = +26–32% prefill, on = NPU available); pagefile 163840 MB;
persistent swap; lazy n-gram loading so the large lookup table pages from SSD (Halogen n-gram 47.7 GiB;
GGUF PLE 26.8 GiB).

**Own-quant / own-kernel options, ranked by payoff vs risk:**
1. **Build the fork with PR #28243 + #28118** (MTP) — highest payoff, lowest risk, well-documented.
2. **Apply the local UMA buffer kernel patch** (thread 12's; ~1.8× prefill) once its source is located.
3. **Run the IOMMU A/B on a native-Linux boot** to see if +26–32% holds for our MoE.
4. `Jab1718/Moe-slices`-style expert pruning if we ever need Flash-Next on a smaller carve.
5. A custom quant is **not** worth it — the shipped 4-bit is the deliberate precision floor and halogen
   takes only its own `.hgn` layout.

## 9. What is still unknown / to test on our box

- Flash-Next **actual** prefill/decode here (the download is at ~77%; the harness is armed).
- Whether Halogen Flash-Next at 115 GB **coexists** with gemma4+STT+TTS on 128 GB, or needs a second box.
- Whether our WSL/HIP llama.cpp build can take the MTP PRs and reach the ~38 t/s figures, or whether
  native Windows Vulkan is the only route to them.
- The UMA-buffer patch source and whether it ports to WSL.
- gemma4 cold-turn first-token on the retest protocol (authored, not run).
