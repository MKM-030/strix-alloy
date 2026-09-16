# New sources synthesis — drluoto fork, Froggeric template, vincentkelleher config (2026-09-14)

Founder supplied four sources. Assessment: **three are directly actionable for our box, and one of them
has a validated config that reaches ~2× our current decode.** This documents what each contains and
what we do with it.

## 1. `vincentkelleher/qwen3.8-flash-next-halo` — a **validated config for our exact machine**

This is the highest-value find: a Docker Compose deployment for **Ryzen AI MAX+ 395 / Radeon 8060S /
gfx1151 / 128 GB** — our box, exactly.

**Their measured numbers** (`llama-benchy`, 2048-token prompts, uncached prefill, MTP **on**, 3 runs):

| Context depth | Prefill (t/s) | **Decode (t/s)** | First response (s) |
| ---: | ---: | ---: | ---: |
| 0 | 570.8 ± 1.4 | **35.8 ± 1.1** | 3.72 |
| 8,192 | 506.1 ± 2.2 | **36.7 ± 2.3** | 20.36 |
| 32,768 | 405.4 ± 1.1 | **33.5 ± 1.8** | 86.02 |
| 128,000 | 230.9 ± 0.4 | **25.7 ± 1.0** | 563.42 |

**That is ~2× our pwilkin-fork numbers** (we measured 14–22 t/s decode, 270–330 prefill). And it holds
at depth — 25.7 t/s even at 128k.

**What their config uses (the differences that matter):**

| Element | Their setting | Ours (pwilkin fork) |
| --- | --- | --- |
| Engine | `drluoto/llama.cpp` **`strix-halo-vulkan`** @ `ba5354d46`, **Vulkan/RADV** | `pwilkin/strix-halo`, ROCm |
| Draft head | **`mtp-...-Q8_0-frspec-65k.gguf`** (FR-Spec, 3.64 GB) | shared-Q8_0 |
| Load mode | **`-lm dio`** (O_DIRECT) | `--load-mode none --lazy-mode on-direct` |
| Chat template | **Froggeric `chat_template.jinja`** (mandatory — server exits without it) | built-in |
| `--spec-draft-n-max` | 3 | 2–3 |
| `--spec-draft-p-min` | **0.0** (uncalibrated draft logits; any threshold wastes acceptance) | 0.75 |
| batching | `-b 2048 -ub 2048` | 4096 |
| KV | `-ctk f16 -ctv f16` | f16 |
| sampling | temp 1.0, top-k 20, top-p 0.95, min-p 0.0, presence 0.0 | default |
| `--ctx-checkpoints` | 8 | — |
| env | **`GGML_VK_DISABLE_GDN_CACHE_FUSION=1`** — *"this branch's fused GDN state-cache path is broken on the 8060S and corrupts output"* | n/a |
| kernel args | `amd_iommu=off amdgpu.gttsize=126976 ttm.pages_limit=32505856` | — |
| GPU access | `/dev/dri` only — **`/dev/kfd` not needed** | DXG/HIP |

**Critical detail they document:** *"it is the only build here that loads the FR-Spec MTP head"* — stock
llama.cpp rejects it (missing `t2d`/`d2t`). We already have that exact FR-Spec file
(`drluoto-frspec/mtp-Qwen3.8-Flash-Next-Q8_0-frspec-65k.gguf`, 3.64 GB) — **our pwilkin fork failed to
load it, which is consistent.**

**Why Vulkan matters for us:** their config needs **no `/dev/kfd`** (Vulkan goes through `/dev/dri`).
That is the same class of access WSL paravirtualization *can* provide — and it sidesteps the
HIP/DXG memory-model problems (no pinning, `dio` direct reads) that blocked Halogen.

## 2. `froggeric/Qwen-Fixed-Chat-Templates` — an actual reported llama.cpp bug

Downloaded to `/mnt/c/AI/models/qwen38-flash/froggeric/` (`chat_template.jinja`, 28 KB). Documented
fixes relevant to our decode work:

- **"AST: Flattened nesting to fix a reported 80% inference throughput drop on llama.cpp."** ← a
  template causing an 80% throughput loss is exactly the class of problem our numbers could hide.
- **KV cache: preserves past `<think>` blocks chronologically for a claimed "100% KV Cache hit rate."**
  ← relevant to the prompt-cache behaviour we saw.
- Thinking default **medium** (not `xhigh`), zero injected tokens — less wasted reasoning before answers.
- Non-thinking mode actually works (stock 3.8 template crashes on `enable_thinking=false`).
- Fixes blank `<think></think>` blocks and reasoning extraction across APIs.

Apply:
```
llama-server -m model.gguf --jinja --chat-template-file chat_template.jinja --reasoning-format deepseek
```
The vincentkelleher compose uses precisely this (with `--jinja` **before** `--chat-template-file`, and
`--reasoning-preserve`).

## 3. `drluoto/llama.cpp` — two Strix branches, both exist

| Branch | HEAD | Backend | Use |
| --- | --- | --- | --- |
| **`strix-halo-vulkan`** | `ba5354d46` | Vulkan/RADV | what vincentkelleher runs — **33–37 t/s** |
| **`strix-halo-flash-next`** | `590ac45` | ROCm/HIP | the variant our WSL/DXG path needs |

Both are forks of upstream carrying the qwen4exp MTP work; `strix-halo-vulkan` is the validated one.
We are **building `strix-halo-flash-next` (HIP) now** because our WSL path has no Vulkan.

## 4. The Dimaginar post (re-read with full comments)

The author runs **our exact box** (Bosgame M5, 128 GB) with UD-IQ4_XS + MTP Q8_0 on
`Nathanw1014/llama.cpp:strix-halo-vulkan` via distrobox. Reported **22–35 t/s at 0–15k KV, 27–31 at
15–60k, 23–29 at 60k+** — i.e. the same 25–37 t/s class as vincentkelleher. He also notes he has
**~40 GB free** and memory *does not grow* — because of the PLE architecture, so n-gram-offload-to-SSD
is unnecessary.

Two comments are directly relevant to us:
- `lcassellis`: *"Halogen Server with DSH. I'm getting around ~42 t/s on decode."*
- `Wise-Biscotti-3984`: *"Agree, the Kernel is way better. Got an M5 as well and was able to bring it
  into WSL on Windows. I got some Crazy Numbers, will share a few soon"* — **someone else is doing
  exactly our Windows/WSL project.**

## Bottom line

**Our 14–22 t/s is not the ceiling for this hardware — 25–37 t/s is, and a validated config exists.**
The gap is a specific stack: **drluoto's fork + the FR-Spec MTP head + `-lm dio` + Froggeric's template
+ p-min 0.0.** We are building the ROCm sibling of that fork now; the FR-Spec head we already have.

Action items, in order:
1. **Build `drluoto/strix-halo-flash-next` (HIP)** — in progress.
2. **Benchmark with their exact flags** (FR-Spec head, p-min 0.0, `-b 2048 -ub 2048`, Froggeric template).
3. If HIP underperforms: consider **Vulkan-on-Windows** (native, no WSL) since `/dev/kfd` is not needed
   and RADV is present on the host.
4. **Report the Froggeric 80%-throughput fix** to the kernel session — it may explain part of our gap.
