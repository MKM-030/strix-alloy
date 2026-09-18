# Building and quantizing your own Qwen-based Halo (`.hgn`) models — a working guide (2026-09-12)

Founder request: document how to **build/train our own Qwen-based model with weights for the Halo
kernel**, and how to **split the important agents** to reduce model size and improve performance.

This is written from what we verified on this machine (the real `halogen`/`flash_serve` binaries, the
`chlorine-server` clean-room sources, and the `.hgn` format). It separates the two halves that the
word "Halo model" conflates, because only one of them we can actually build.

---

## 0. The two halves — and which one you can build

| Half | What it is | Open? | Can we build/modify it? |
| --- | --- | --- | --- |
| **The `.hgn` checkpoint** | A container format (header + tensor table + blobs). Holds the weights. | ✅ format documented; a writer exists | **Yes** — we can quantize any model into it |
| **The halogen kernel/engine** | The closed C++/HIP binary (`halogen`, `flash_serve`) that runs `.hgn` | ❌ closed source | No — we use it as-is |

**Consequence:** "train my own model for the Halo kernel" means **train a normal Qwen model
(safetensors), then repack it into `.hgn` so the closed engine can load it** — *provided the engine
recognizes your model's architecture*. The engine is **model-family-specific** (`qwen4exp` for
Flash-Next, a `qwen3.8` config for the 27B); it is not a generic loader. That is the one hard gate.

---

## 1. The `.hgn` format (verified against the real files)

```
header  (0x68 = 104 bytes):
  magic      uint32   "HGN1" = 0x314E4748
  version    uint32   1 | 2
  n_tensors  uint32
  table_off  uint32   0x68
  data_off   uint32   0x68 + 0xA0 * n_tensors
  file_size  uint64
  name[64]   char

entry (0xA0 = 160 bytes each):
  name[96]   char
  ndim|dtype uint64   (ndim<<32) | dtype
  dims[4]    uint32
  offset     uint64
  size       uint64
  qparam     uint64   (qparam<<32)

data: blobs in entry order, each 64-byte aligned
```

**Dtypes** (the `dtype` field):

| code | name | meaning | writer support |
| ---: | --- | --- | --- |
| 0 | `bf16` | bfloat16 | ✅ (as-is) |
| 1 | `f32` | float32 | ✅ |
| 2 | `f16` | float16 | ✅ |
| 3 | `i32` | int32 | ✅ |
| 4 | `i64` | int64 | ✅ |
| 5 | `q4c` | 4-bit, per-column groups + 1B/16 scales | ✅ *simple* form only |
| 6 | `fp8r` | FP8 rowwise (absmax→448) | ✅ *simple* form only |
| 7 | `q8g64` | 8-bit, group 64 | engine reads it; converter does not emit it |
| 8 | `i4l` | 4-bit "int4-load" (the NVFP4-imported layout) | ❌ **not emittable by the open converter** |
| 10 | (n-gram FP8) | the big `ple.ngram_embedding` table (`fp8`, paged) | engine-only |

### The actual Flash-Next tensor spec (from `hgn-inspect.py`, real file)

`model_name = qwen3.8-flash-next`, **1198 tensors**, version 2. Per layer the engine expects
(`layers.N.*`):

```
attn_hyper_connection.block_inject_weight.weight   q4c  [4, 10240]
attn_hyper_connection.hc_norm.weight               bf16 [10240]
attn_hyper_connection.input_mix_weight_{down,up}   q4c  [320,10240] / [10240,320]
linear_attn.{A_log,dt_bias}                        bf16          # Gated DeltaNet
linear_attn.conv1d.weight                          bf16 [10240,1,4]
linear_attn.in_proj_{a,b,qkv,z}, out_proj, norm    q4c / bf16
mlp_hyper_connection.*                              q4c (as attn)
mlp.experts.down_proj.weight                       q4c  [512, 2560, 640]     # 512-expert MoE
mlp.experts.gate_up_proj.weight                    q4c  [512, 1280, 2560]
mlp.gate.weight                                    bf16 [512, 2560]
mlp.shared_expert.* / shared_expert_gate.weight     q4c
ple.{key_proj,norm_*,conv1d}                        bf16
ple.ngram_embedding.weight                          fp8 [128, 2500012, 160]   # 47.7 GiB, paged
embed_tokens.weight                                 q4c  [248320, 2560]
```

So the architecture is **`qwen4exp`**: hybrid attention (Gated DeltaNet `linear_attn` **+** full
`attn`), a **512-expert** MoE with a shared expert, hyper-connection adapters, and a per-layer
embedding with a 2.5M-row n-gram table. Any self-built model must reproduce this tensor set exactly.

**The gap that matters:** the *quality* of Peonist's checkpoints comes from `i4l` and the
NVFP4-derived `q4c` layout (activation-aware), which the open `hgn-convert.py` **cannot reproduce**.
So a self-built `.hgn` will be a *correct container the engine can read*, but at a lower-precision
scheme than the shipped files — unless you implement the missing dtypes (see §4).

---

## 2. The toolchain we have (WSL)

`~/chlorine-server/` (AGPL clean-room reimplementation of the engine + converter):

```
converter/hgn-convert.py     safetensors -> .hgn writer (bf16/f32/f16/i32/i64 + simple fp8r/q4c)
converter/hgn-inspect.py     .hgn inspector (names, dtypes, sizes)
engine/src/generator.hip     HIP reference kernels for gfx1151 (attention, gemv, dequant)
docs/halogen/CHECKPOINT-FORMAT.md   the format spec (source of truth)
docs/halogen/KERNELS-DEQUANT.md     how each dtype dequantizes
docs/halogen/ARCHITECTURE.md, TRUNK-NOTES.md, REBUILD-PLAN.md
```

The **closed** engine binaries we run are separate and stay untouched:
`~/halogen-re/halogen` (27B) and `~/halogen-flash/bins/flash_serve` (Flash-Next), both extracted from
`ghcr.io/peonist-ai/*`.

---

## 3. Recipe A — repack an existing Qwen model into `.hgn` (no training)

This is the practical path today. It produces a loadable `.hgn` from any safetensors model whose
architecture the engine supports.

```bash
# 1. get the base model as safetensors (Hugging Face)
hf download Qwen/<your-model> --local-dir ~/models/<your-model>

# 2. inspect the tensor names/shapes you must map (must match the engine's expected names)
python converter/hgn-inspect.py ~/some/existing.hgn   # to see the target naming, shapes, dtypes

# 3. repack: declare each tensor and its target dtype
python converter/hgn-convert.py out.hgn <MODEL_NAME> \
  model.embed_tokens.weight=bf16 \
  model.layers.0.self_attn.q_proj.weight=q4c:... \
  ...

# 4. smoke-test with the engine (loads, generates) — see the run harnesses
```

**Reference tensor sets to match:** the shipped files are the ground truth —
`qwen3.8-27b-p1w4d-d2.hgn` (1352 tensors, `bf16 493 / fp8r 233 / q4c 222 / i4l 400`) and
`qwen38-flash-next-w4b.hgn` (1198 tensors). Always `hgn-inspect.py` the shipped file first and mirror
its names/dims exactly; a single mismatched name fails the load with a `tensor ... not found`-style error.

**Honest caveat:** step 3 with the current converter gives `bf16`/`fp8r`/simple-`q4c`. That is bigger
and lower-quality than the shipped `i4l` mix. Repacking alone does not reproduce Peonist quality.

---

## 4. Recipe B — extend the writer to reach Peonist-quality quants

To build genuinely competitive `.hgn` files you implement the two missing pieces, following
`docs/halogen/KERNELS-DEQUANT.md`:

1. **`i4l` (dtype 8)** — the 4-bit NVFP4-imported layout. Implement the packer in
   `hgn-convert.py` (and the matching dequant in the chlorine engine to validate it).
2. **Full `q4c`** — the activation-aware/purpose-built per-column layout, not the "simple" form.

Because the format is documented and the dequant rules are in the repo, this is **software work, not
reverse-engineering of the closed binary** — you validate against the chlorine engine's own kernels,
then the closed engine reads your file the same way it reads its own.

This is the path if REV:N needs a *custom-quant* Halo model (e.g. a German-dialogue-tuned 27B in the
exact layout the fast kernel wants).

---

## 5. Recipe C — train/fine-tune a Qwen base, then pack it

```text
1. Base:    pick a Qwen base whose arch the engine supports (qwen4exp / qwen3.8 families).
2. Tune:    LoRA / full fine-tune on your data (dialogue, world-state, German) — standard HF/PEFT
            tooling. Output: a normal safetensors checkpoint.
3. Fuse:    merge LoRA into the base weights (safetensors).
4. Quantize: apply the chosen scheme (IQ4_XS via llama.cpp's quantize, or your §4 `i4l`/`q4c` packer).
5. Pack:    hgn-convert.py -> .hgn with the engine's tensor names.
6. Validate: hgn-inspect.py, then load in flash_serve and run the smoke prompt; compare quality vs base.
```

Steps 2–3 are ordinary ML work and need a GPU with enough memory (or an offloaded/multi-pass setup).
Steps 4–5 are the Halo-specific part and can run on this box.

---

## 6. The big lever he asked about: **split the monolithic model into role-specialised agents**

The single most effective "optimisation of the model itself" is **not** a smaller quant — it is
**architectural decomposition**. Flash-Next is ~125B precisely because it does everything. REV:N does
not need one model to do everything; it needs several small ones, each fast, each fitting a small
carve. The Reddit research supports this directly (MoE-active-parameter economics; the Jcbtc/CIRU
and Moe-slices projects are exactly this instinct).

### Proposed REV:N agent split

| Role | Workload | Suggested size | Why separate |
| --- | --- | --- | --- |
| **World-State Engine** | long-context world/scene memory, event deltas | 27B–35B MoE (3B active) | needs context + prefill, not speed |
| **Dialogue Brain** | live NPC speech, German, few-hundred-ms TTFT | 7B–26B (gemma-class) | latency-critical, small |
| **Action/Tool Planner** | structured JSON, tool calls, validation | 3B–8B | deterministic, cheap |
| **Perception/Summary** | transcript → structured facts | 1B–3B | high frequency, tiny |
| **STT / TTS** | speech in / speech out | 1B / 0.6–1.7B | already separate today |

**Why this beats one big model here:**
- Each model fits a **smaller device pool**, so the carve can stay moderate and models **co-reside**.
- Decode is memory-bandwidth-bound on Strix Halo; a 3B-active MoE decodes far faster than a dense 27B
  (measured: Ornith 35B-A3B **63–99 t/s** vs dense 27B **11–15 t/s**).
- The World Engine only needs **prefill**; the Brain only needs **low-latency decode**. Splitting lets
  each be tuned for its axis instead of compromising.

### How to actually build the split
1. **Define the roles and their schemas** (what each agent is allowed to output). This is the real
   design work and belongs in the backlog, not here.
2. **Distill, don't retrain from scratch.** Use the big Flash-Next (or a cloud model once, off-box) as
   a teacher to generate role-specific data; fine-tune a small base per role.
3. **Quantize each to its own budget** (§4/§5) — the Brain to a fast low-bit quant, the World Engine to
   a quality-favouring one.
4. **Route by role in the orchestrator**, not by one mega-prompt.

### Expert pruning as a middle path
If a single model is still wanted, `Jab1718/Moe-slices` shows activation-profiled **expert pruning**
(keep the experts that actually fire for your domain; align to multiples of 16 for GEMM). That is
*model surgery* — it shrinks a 125B MoE toward 26–44 GB — but evaluation must be domain-specific
(coding retention ≠ world consistency or German quality). Treat it as a research arm.

---

## 7. Practical limits and honest cautions

- **Architecture gate:** the closed engine only loads the model families it was built for. A custom
  *arch* (different layer mix) will not load no matter how well packed. Start from a supported family.
- **`i4l` gap:** without §4, self-built files are lower-quality than the shipped ones.
- **Carve is shared:** every resident model draws on the same device pool (`pool ≈ 64 + carve/2`).
  Splitting helps only if the pieces are individually small — which is the point.
- **Quality must be re-measured:** a custom quant is a new model; run the German-quality bake-off
  under the project's own quality protocol before it replaces anything.

---

## 8. What to do first (concrete)

1. **Raise the carve to 32–64 GB** so a full Flash-Next runs at speed and we finally get the fast
   benchmark numbers (`flash-next-variant-comparison-20260912.md`).
2. **Run `hgn-inspect.py`** on both shipped `.hgn` files to capture the exact tensor set (names, dims,
   dtypes) the engine expects — this is the spec any self-built file must match.
3. **Prototype Recipe A** on a small supported Qwen to prove the round-trip (pack → engine load →
   generate), then scale to the 27B.
4. **Draft the role split** as a backlog concept (roles, schemas, sizes), then distill models per role.
