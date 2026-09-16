# Halogen 0.7.0 on Windows/WSL: BYO-GGUF results (2026-09-13)

Two founder questions, answered empirically:

1. *With `/mnt/c`, will Halogen also work?*
2. *Can we use Bring-Your-Own-GGUF for UD-IQ4_XS and Ornith?*

## 1. Does `/mnt/c` fix Halogen? No — the path was never the problem

The engine's own 0.7.0 log states the constraint directly, and it is not the filesystem:

```
checkpoint: refusing to pin 70.55 GiB, MemAvailable is 85.00 GiB and the floor is 16.00 GiB.
```

Halogen **pins the whole trunk in RAM** (its GGUF path explicitly: *"A GGUF trunk is held in pinned
memory in full"*). It needs `weights + 16 GiB floor`. The 70.55 GiB trunk needs **≥86.55 GiB free**, and
WSL did provide 85.00 — **short by 1.55 GiB**. Raising WSL to 92 GB pushed Windows to 2 GB free and had
to be killed.

This is the same **pool-vs-host squeeze** as before, now with exact numbers:

| Carve | Windows sees | WSL can have | Device pool | Engine pin needs |
| ---: | ---: | ---: | ---: | --- |
| 8 GB | 120 GB | ~112 GB | 68 GB | 86.55 host ✅ but pool 68 < 70.55 ❌ |
| **32 GB (now)** | **96 GB** | **88 GB** | **80 GB** | host 85 vs 86.55 — **1.55 short** ❌ |
| 64 GB | 64 GB | ~58 GB | 96 GB | host too small ❌ |

**`/mnt/c` does not change this.** The blocker is host-RAM capacity for pinning, not where the file
lives. (`/mnt/c` only affects *load speed* — the 10–13 min we saw.)

## 2. BYO-GGUF: the converter works; the formats decide what loads

### `--repack` WORKS on WSL (the real win)

Halogen 0.7.0 ships a **GGUF → `.hgn` converter** we did not have before:

```bash
flash_serve --repack IN.gguf --out OUT.hgn [--with-table] [--head HEAD.hgn|--no-head] [--threads N]
```

We ran it on the **stock unsloth UD-IQ4_XS on WSL, CPU-only, no GPU, in 83 seconds**:

```
checkpoint: repacking, 1166 of 1166 tensors, 70.6 GiB, 83 s
repack: wrote ffn-ud-iq4-xs.hgn: 1166 tensors, 70.55 GiB
```

So **we can now produce a real Halogen `.hgn` from any supported GGUF, on Windows/WSL, offline.** The
result is 70.55 GiB — *smaller* than the source, because the repack drops/reshapes the lookup table.

**Why this matters:** a `.hgn` loads through the **mmap+register** path (the one `hipshim` fixes), not
the "pin the whole trunk" GGUF path. It is the route that already worked for the 27B.

### Which quants BYO-GGUF accepts

| Model (arch) | Quant | Result |
| --- | --- | --- |
| **Qwen3.8-Flash-Next** (`qwen4exp`) | UD-IQ4_XS | ✅ **repacked** (1166 tensors, 70.55 GiB) |
| **Ornith 1.5 35B** (`qwen35moe`) | MTP-23G-ICE | ❌ **`architecture 'qwen35moe': this engine reads qwen4exp (Qwen3.8-Flash-Next) only`** |
| **Ornith 1.5 35B** | ROCmFP4 | ❌ `output.weight: unknown tensor type 101` |

**So BYO-GGUF is scoped to the Flash-Next architecture only.** Ornith is a *different* architecture
(`qwen35moe` = MoE variant) and is refused **by name at load**, before anything runs — exactly matching
Peonist's own caveat: *"the intent was for Qwen 3.8 flash / Qwen 4.0 architectures. Other models might
run, could just blow up."* (The ROCmFP4 file additionally uses a custom tensor type 101 that only
`LaurentZuijdwijk/llama.cpp` implements.)

## Summary table

| Question | Answer |
| --- | --- |
| Does `/mnt/c` make Halogen work? | **No.** The blocker is host-RAM for pinning (86.55 GiB needed, ~85 available), not the path. |
| Can BYO-GGUF convert **UD-IQ4_XS**? | **Yes — verified**, 70.55 GiB `.hgn` in 83 s, CPU-only, on WSL. |
| Can BYO-GGUF accept **Ornith**? | **No** — different architecture (`qwen35moe`), refused by name. |
| Does the repacked `.hgn` run? | **Not yet** — it pins 70.55 GiB and is refused by 1.55 GiB host RAM at 32 GB carve; the window is razor-thin. |

## The one number that would make it work

The engine needs `trunk + 16` GiB free host RAM, and the trunk must also fit the device pool. On this
128 GB box with Windows owning the OS:

- **32 GB carve**: host ~88, pool 80 → trunk 70.55 fits the pool, but host is 1.55 GiB short.
- **Smaller trunk**: a **Q3_K_XL / Q4_K_M-class Flash-Next GGUF (~55–70 GB)** would fit both comfortably.
- **Halogen's own native `.hgn` weights** are 5.53 bpw over a smaller resident set — the shipped file was
  designed for exactly this budget, which is why Peonist's own numbers work and our GGUF-derived repack
  is borderline.

**Practical next step:** repack a *smaller* Flash-Next quant (Q3_K_XL) and load its `.hgn` — that should
clear both budgets. We now have the converter and the shim to do it.

---

## 3. Can we RENAME the architecture to load Ornith? No — it is not the name

The founder asked whether patching `general.architecture` from `qwen35moe` to `qwen4exp` would let the
engine process Ornith. **No. The two architectures share neither tensor names nor structure.**

Measured tensor sets (dumped from the GGUF headers, `gguf-tensors.py`):

| | **Ornith 1.5 35B** (`qwen35moe`) | **Flash-Next** (`qwen4exp`, what the engine needs) |
| --- | --- | --- |
| embeddings | `token_embd.weight`, `output.weight` | `embed_tokens.weight` |
| attention | `blk.N.attn_qkv`, `attn_gate`, `attn_q/k/v/output` | `layers.N.attn.*`, `layers.N.linear_attn.*` (Gated DeltaNet) |
| state-space | `blk.N.ssm_a/alpha/beta/conv1d/dt/norm/out` (30 layers) | `layers.N.linear_attn.A_log`, `in_proj_*`, `out_proj` |
| experts | **256** (`ffn_gate_exps` [2048,512,256]) | **512** (`mlp.experts.gate_up_proj` [512,1280,2560]) |
| hyper-connections | **none** | `attn_hyper_connection.*`, `mlp_hyper_connection.*` |
| PLE / n-gram | **none** | `layers.N.ple.*`, `ngram_embedding.weight` (2.5M rows) |
| MTP head | `blk.N.nextn.*` (inline) | separate `mtp-…hgn` sidecar |

The engine parses by **exact name + shape**; on materialising a layer it would look for
`layers.N.linear_attn.*`, `attn_hyper_connection.*`, `ple.*` and a 512-expert `gate_up_proj` — **none of
which exist in Ornith's 753 tensors.** A rename changes one label and leaves every tensor unmatched.

**Conclusion:** the engine is the `qwen4exp` (Qwen3.8-Flash-Next / Qwen 4) family only. Ornith is a
different network (SSM hybrid, 256 experts, no PLE), so this is not a rename — a port would mean
reimplementing a different architecture, i.e. retraining. (Peonist's own caveat: *"Other models might
run, could just blow up."*)

**Ornith's speed is already measured** — `kernel-architecture-and-decode-concept-20260913.md`:
**46.3 t/s decode / 505.8 t/s prefill** (mainline) and 42.0 / 461.5 (fork) on `llama-bench`; 63–99 t/s
decode on Windows/Vulkan in the earlier Ornith evaluation. It is faster than Flash-Next because only
~3B of its 35B parameters are active per token.
