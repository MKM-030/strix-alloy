# Flash-Next on Halogen: definitive root cause and the working alternative (2026-09-13)

Founder goal: run Halogen Flash-Next at speed. Outcome after testing carves 0.5 / 8 / 16 / 32 GB:
**the blocker is not the carve — it is WSL's memory model.** The fix is a different runtime, and the
community has just published one that reaches the same speed. Details below, both measured here and
from the new external config.

## 1. What now works for certain

At the 32 GB carve the engine gets **through the weight pinning** — the thing that blocked every
earlier attempt:

```
checkpoint: pinned 67.86 GiB in 2 range(s)   ← trunk + overlay, full quality
startup [269 s] weights pinned: 186 contiguous 2 MiB blocks free (372 MiB)
```

Then it fails on the engine's own startup allocation:

```
halogen: WARNING the host has only 186 contiguous 2 MiB blocks of free memory (372 MiB)
         before this server has allocated anything. There may be plenty of free memory, but it is
         in the wrong shape: large allocations each stop to compact it, most of those attempts fail.
pid:… [CreateContext] fail c000000d
```

## 2. The root cause: physical-memory fragmentation under WSL, not capacity

Measured buddy-allocator state (order-9 = 2 MiB blocks, the unit the engine needs):

| Moment | order-9 blocks |
| --- | ---: |
| WSL fresh boot, before anything | **1** |
| after `echo 1 > compact_memory` | 121 |
| after pinning 67.86 GiB | 154–224 (≈ 0.4 GiB) |

The engine wants **thousands** of contiguous 2 MiB blocks; WSL's dynamic-memory ballooning hands out
RAM as non-contiguous 4 KiB pages, so even with ~20 GiB "free" the large blocks do not exist. Two
proofs this is not capacity:
1. **At 16 GB the same `CreateContext` failure appeared with 36 GB host-free.**
2. **`compact_memory` raised order-9 blocks from 1 to only 121** — the free memory is real but the
   *shape* is wrong, and compaction cannot fix balloon-backed VMs.

**This is why the carve sweep never succeeded:** 8 GB (overlay 0.3 GiB short), 16 GB (weights pin, no
working blocks), 32 GB (weights pin at 67.86 GiB, no working blocks), 64 GB (pin refused, host RAM too
small). There is no carve that gives both a large enough pool *and* contiguous host memory, because the
constraint that fails is orthogonal to the carve.

**What would fix it (for a future attempt):** a **native Linux install** where memory is not
balloon-managed (this is exactly the configuration the engine and its author describe — "a host of its
own"), or a WSL memory mode that pre-allocates contiguous backing. Neither is available on this box today.

## 3. The 27B Halogen works — production, live

Because 35.9 GiB is well inside the pool and needs far fewer contiguous blocks, the **27B Halogen runs
reliably** at 8–32 GB carve:

```
checkpoint: registered 35.9 GB in 62.9 s (Mapped|ReadOnly)
serve: prompt cache 48.5 GB AUTO, 3 × 262144-token entries
serve: drafters — mtp, dflash2 available
listening on 127.0.0.1:8730 — 64 layers, ctx 262144
```

OpenAI service: engine 8730 + `serve_api.py` 8731, `id: halogen-qwen3.8-27b`, answers correctly.
Decode: serial 9.4 / MTP 10.3 / **DFlash2 17.1 t/s**.

## 4. The new community config — the same speed, open source, no pinning

The founder supplied two brand-new sources, and they are the answer for Flash-Next:

- Reddit: *"Qwen3.8 Flash Next, the optimized config (1.2k t/s prefill!)"* (`u/ilintar`)
- Site + repo: `https://pwilkin.github.io/strix-halo/`, `github.com/pwilkin/llama.cpp` branch
  **`strix-halo`**, and `github.com/pwilkin/rocm-systems` branch `ilintar-experiments`

**Why this is the solution rather than another attempt at Halogen:**

| | Halogen Flash-Next | pwilkin/llama.cpp `strix-halo` |
| --- | --- | --- |
| Loading | pins 67.86 GiB host → **fails on WSL fragmentation** | **mmap GGUF, page cache** — no giant pin |
| Prefill @0 | target ~1.2k t/s | **1,204 t/s measured** |
| Prefill @40k | — | **1,086 t/s** (~90% retained) |
| Prefill @150k | ~850 t/s target | ~850 t/s reported |
| Decode | ~30 t/s target | **26.3 t/s** |
| Open source | ✗ closed | ✅ MIT fork + custom quant |
| Key trick | pinned host memory | `--load-mode none --lazy-mode on-direct` + 16384 batch/ubatch keeps the 27.5 GiB PLE table **out of the resident set**; PM4-replay HIP build for decode |

**This is the crucial technical difference:** the community config solves the *same* PLE/embedding-table
memory problem the Halogen pin was created for — but by **lazy-loading from disk into the page cache**
instead of pinning host memory. That sidesteps WSL fragmentation entirely. It is also open source, so
the founder's wish to "optimize the model ourselves" is achievable here, not through a closed binary.

Install (their scripts):
```bash
bash <(curl -fsSL https://raw.githubusercontent.com/pwilkin/strix-halo/main/install.sh)             # 27B, ~30 GiB
bash <(curl -fsSL https://raw.githubusercontent.com/pwilkin/strix-halo/main/install-flash-next.sh)   # Flash-Next, ~110 GiB, 128 GB RAM
```
Launchers land in `~/.local/bin`; models default to `~/.models`. Their claim: 16384-token prefill path,
retained-PM4 ROCr/HIP runtime, IQ4_NL custom quant + DFlash2 2.8 GB draft.

## 5. Recommendation

1. **Stop pursuing Halogen Flash-Next on this Windows/WSL box.** It is blocked by WSL memory
   fragmentation, not tuning. Keep it for a native-Linux machine.
2. **Use the pwilkin `strix-halo` llama.cpp build for Flash-Next here** — same measured prefill class
   as Halogen, open source, mmap-based (no fragmentation trap), and it also has a **Qwen3.8-27B config
   at 256.8 prefill / 26.3 decode**.
3. **Keep the Halogen 27B OpenAI service running** (it works today at 17.1 t/s) as the Halogen option.
4. **To actually run Halogen Flash-Next at speed:** a native Linux install (bare metal), where host
   memory is contiguous and not ballooned. That is the engine's intended environment.

## 6. Caveats on the community sources

- Reddit 403s to the fetch tool; the numbers above are from the post text and the site. The Reddit
  comment thread shows `mfarmemo` reproducing ~1,100–1,467 t/s locally, so the result is corroborated
  by a second party.
- Their Next-Flash path is newer than their 27B path; decode is "~8% below target" per their own notes.
- The halogen author (`peonist-ai`) commented on the thread asking ilintar to help maintain Halogen
  once open — so the closed/open gap is expected to narrow.
