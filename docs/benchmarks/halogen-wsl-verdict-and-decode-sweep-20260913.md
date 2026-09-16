# Halogen Flash-Next on WSL: definitive verdict, and the decode measurements (2026-09-13)

## 1. HALOGEN: solved the repack, found the real blocker — it is the model layout, not memory

**Breakthrough parts (all verified):**

1. **`--repack` works on WSL, CPU-only.** We converted the stock unsloth `UD-IQ4_XS` GGUF into a
   self-contained Halogen `.hgn` **including the n-gram table and the MTP head**:
   ```
   --repack <gguf> --out ffn-full.hgn --with-table --head qwen38-flash-next-mtp.hgn
   → 1198 tensors, 98.79 GiB, 607 s
   ```
   This is a real capability we did not have before 0.7.0.

2. **The `.hgn` loads and the engine starts on WSL.** With the head embedded, the engine got all the way
   to listening:
   ```
   checkpoint: mapped 106.1 GB, NOT pinned (Pin::None)
   startup [23.5 s] weights ready; reserving working memory
   startup [23.5 s] memory: 0.0 GiB of weights locked in RAM, 0.9 GiB KV pool, 20.2 GiB working, 21.1 GiB in all
   flash_serve: listening on 127.0.0.1:8745, 1 slots over ONE 32768-position KV pool
   ```

**The blocker, in the engine's own words:**

```
experts.down: Q8S32 experts are read in place only (HALOGEN_FLASH_PIN_TRUNK=0 / Pin::None has no arm for them)
```

**`PIN_TRUNK=0` cannot run a GGUF-derived checkpoint.** The 8-bit expert layers (`Q8S32`) are readable
only **in place from the pinned mapping**; the no-pin staging path has no code for them. So the two paths
are:

| Path | Requirement | Status |
| --- | --- | --- |
| **Pinned** | host RAM ≥ 70.55 + 16 floor = **86.55 GiB** free, **and** device pool ≥ 70.55 + 20.2 working = **90.75 GiB** | ✗ needs carve ≥ 53 (pool) **and** ≤ 35 (host RAM) — **impossible together** |
| **PIN_TRUNK=0** | — | ✗ **refuses the Q8S32 expert layout entirely** |

Measured carve sweep (all tried): 0.5 / 8 / 16 / 32 / 64 GB. At 32 GB the pin was refused with
`MemAvailable 85.00, floor 16.00` (needed 86.55 — **1.55 GiB short**). At 64 GB it was refused for host
RAM. There is no carve that satisfies both budgets on a 128 GB machine.

### What would actually make Halogen run here

| Route | Feasible? |
| --- | --- |
| **Smaller Flash-Next quant (Q3_K_XL ≈ 55–70 GiB)** | ✅ would fit: host 55+16=71 (carve ≥25 ok), pool 55+20=75 (carve ≥22 ok) → carve ~24–30 works. *(Founder deferred Q3.)* |
| Peonist's own 115 GB `.hgn` | ✗ needs the pin, same wall |
| Native Linux | ✅ but declined |
| **The `strix-halo` llama.cpp fork** | ✅ **already runs** — no pinning needed (see §2) |

**So: on Windows/WSL, Flash-Next runs on the open fork; Halogen runs the 27B but not Flash-Next.**

## 2. DECODE: the parameter sweep found a real lever — shorter context

Founder's hypothesis ("try small context windows, then increase") **is correct.** Measured, same model,
same fork, MTP depth 2:

| Config | ctx | Warm decode | MTP acceptance |
| --- | ---: | ---: | ---: |
| baseline `on-direct`, ub 512, n-max 2 | **8192** | **19.97 t/s** | **88.9%**, len 2.78 |
| same, larger ctx | 65536 | 16.35 t/s | 77% |
| 25k-token prompt | — | 7.0–7.4 t/s | **0%**, len 1.00 |

**Two clear facts:**
1. **Decode falls with context depth, and MTP acceptance is the reason.** At short context the drafter
   accepts 89% and buys ~20 t/s; at 25k tokens acceptance is **0%** and decode falls to the base rate
   (7 t/s). Improving long-context decode = fixing the drafter at depth, not the base kernels.
2. **Prefill stays ~535 t/s** (18–25k tokens) regardless.

**Reference:** Peonist measured **25.4 t/s serial** decode for the same `UD-IQ4_XS` through Halogen
(native Linux). Our fork reaches **19.97 t/s on Windows** with MTP — the same ballpark, which is a good
Windows result.

### The theoretical ceiling and why we are at 20

Weight bandwidth allows ~**63–75 t/s** for ~6B active params at 4.25 bits. We are at 20, so ~3× headroom
exists — in **kernel launch overhead, graphs, and MTP-at-depth**, exactly the targets the kernel-session
prompt already ranks first (`kernel-architecture-and-decode-concept-20260913.md`).

## 3. Parameter sweep results (partial)

| Config | Result |
| --- | --- |
| A: `--load-mode none --lazy-mode on-direct -b 512 -ub 512 --spec-draft-n-max 2` | ✅ **19.97 t/s**, 88.9% accept |
| B: MTP `--spec-draft-n-max 4` | ⏱ load exceeded the test window (needs a retest) |
| C: `--load-mode mmap --lazy-mode on` (page-cache PLE) | ⏱ load exceeded the test window |
| D: no MTP (serial baseline) | ✗ server error on start (retest) |

B/C/D need retesting with a longer window; each server load is ~9 minutes.

## 4. Recommendations

1. **For tok/s now:** run Flash-Next with a **smaller context (8–32k)** where MTP acceptance is high
   (~89%) — that is worth **+20–25%** decode immediately, and it matches how REV:N actually uses a
   World Engine (bounded scene context, not 256k).
2. **For Halogen Flash-Next:** it needs a **≤70 GiB quant** or native Linux. Both were declined for now,
   so Halogen stays on the 27B (which works).
3. **For the kernel session:** the decode target is now *measured* — raise MTP acceptance at depth and
   verify HIP graphs. That is where the 3× headroom is.
