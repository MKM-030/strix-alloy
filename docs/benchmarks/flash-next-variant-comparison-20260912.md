# Qwen3.8-Flash-Next variant comparison — measured on this box (2026-09-12)

> **UPDATE after the carve was raised to 64/64.** The device pool is now **95.8 GiB** and the GGUF
> path runs at full speed. Measured results in §2; the Halogen outcome is in §2b. Bottom line:
> **at 64/64 the GGUF (Windows/Vulkan) is the working World Engine; the Halogen `.hgn` pinned path
> needs a native-Linux host and cannot fit a split Windows/WSL machine at any carve.**

Founder goal: **make the Halo model load**, benchmark all Flash-Next variants with optimal parameters,
and get a table (prefill, tok/s, free space for other models) across Windows and WSL.

**Headline:** the Halo engine is not "broken" and does not need a better quant to load — it is blocked
by **one BIOS/Adrenalin setting: the iGPU carve-out.** Both Flash-Next models weigh ~87–115 GiB, but the
current minimum carve exposes only a **64 GiB device pool**. Raise the carve and both load. The numbers
below are what was actually measured today; the fast-path numbers are marked as *pending carve change*.

---

## 1. The single blocker, measured

| Where | Device pool at 0.5 GB carve | Command |
| --- | ---: | --- |
| Windows / Vulkan | **65,611 MiB = 64.07 GiB** | `llama-server.exe --list-devices` |
| WSL / HIP (DXG) | **63.9 GiB total, 63.4 GiB free** | `hipMemGetInfo` via `libamdhip64.so` |

The pool is *not* the physical RAM — it is set by the firmware carve (verified model from the Reddit
research: `pool ≈ 64 + carve/2`). Current carve = **512 MiB** (registry `qwMemorySize = 536870912`),
which I set earlier for the small Halogen **27B** engine. That was correct for a 36 GB model and
**wrong for Flash-Next** (87–115 GiB). The two engines want opposite carve settings.

| Carve (Adrenalin "Dedicated Graphics Memory") | Device pool | 87.25 GB GGUF full-offload | 115.5 GB `.hgn` pinned |
| ---: | ---: | --- | --- |
| 0.5 GB (now) | **64 GB** | ✗ OOM (needs ≈66) | ✗ dies at 48 GiB mapped |
| 16 GB | 72 GB | ✗ (too tight) | ✗ |
| **32 GB** | **80 GB** | ✅ fits (~14 GB headroom) | ✗ |
| **48 GB** | **88 GB** | ✅ | ✅ tight |
| **64 GB** | **96 GB** | ✅ comfortable | ✅ |
| 96 GB | 112 GB | ✅ | ✅ (host then sees only 32 GB) |

**Recommended: 32–64 GB for Flash-Next.** 32 GB is the minimum that fits the GGUF with real headroom;
64 GB is needed if you also want the Halogen `.hgn` (it additionally needs ~115 GB of host-RAM-style
residency that the unified pool provides at that size).

---

## 2b. MEASURED at 64/64 carve (device pool 95.8 GiB, Windows sees 63.6 GB)

The founder rebooted to **64 GB dedicated / 64 GB system**. New device pool: **98,123 MiB = 95.8 GiB**
(Vulkan). Windows visible RAM: **63.6 GB**.

### GGUF — UD-IQ4_XS + shared MTP (Windows/Vulkan, `myhacsint-2dff859`) ✅ WORKS

| Metric | Value |
| --- | ---: |
| Load time | **90 s** |
| Context | **262,144** (full native) |
| Prefill, 57 tok | 42.1 t/s |
| **Prefill, 54,802 tok** | **201.3 t/s** |
| **Prefill, 164,555 tok** | **104.8 t/s** |
| Decode, short prompt | **22.1 t/s** |
| Decode @55k depth | 20.4 t/s |
| Decode @164k depth | 13.6 t/s |
| **MTP draft acceptance** | **100%** (all runs), mean draft len 3.2–3.6 |
| Output | correct (answers "Paris") |

This is the working REV:N World-Engine shape **today**: full 262k context, ~100–200 t/s prefill across
the range, ~14–22 t/s decode, MTP fully effective.

### Halogen `.hgn` pinned (WSL/HIP, `flash_serve` + `hipshim2`) ✗ REFUSED

At 64/64 the HIP pool grew to **95.7 GiB**, but the engine **refuses to pin** before it ever calls the
shim:

```
checkpoint: refusing to pin 65.60 GiB, MemAvailable is 45.92 GiB and the floor is 16.00 GiB.
kv pool: host RAM 47 GiB, less 67.7 resident weights and 20.0 reserved … = 0.0 GiB for the device
```

The reason is structural, not a setting bug: **the pinned path needs ~65.6 GiB of *host* RAM**, but
raising the carve to 64 GB cut Windows-visible RAM to 63.6 GB, so the WSL VM (max ~60 GB) can never
supply it. Setting WSL `memory=110GB` is now impossible — Windows only has 63.6 GB to give.

### Why Halogen pinned cannot fit ANY carve on this machine

The pinned path (via mapped host memory) needs **both**:

| Requirement | Amount | Constraint |
| --- | ---: | --- |
| Host RAM to pin the trunk | ≥ 65.6 GiB + 16 floor ≈ 82 GiB | → carve ≤ ~36 GB (smaller carve = more Windows RAM) |
| Device pool for weights + KV + scratch | ≈ 65.6 + 15 + 18 ≈ 90 GiB | → carve ≥ ~52 GB (larger carve = more pool) |

These point in **opposite directions** and do not overlap:

| Carve | Windows RAM | WSL can have | Host enough to pin? | Device pool | Pool enough? |
| ---: | ---: | ---: | --- | ---: | --- |
| 8 GB | 120 GB | 114 GB | ✅ | 68 GB | ✗ |
| 16 GB | 112 GB | 106 GB | ✅ | 72 GB | ✗ |
| 32 GB | 96 GB | 90 GB | ✅ (tight) | 80 GB | ✗ |
| 48 GB | 80 GB | 74 GB | ✗ | 88 GB | ✗ (tight) |
| 64 GB | 63.6 GB | 58 GB | ✗ (45.9 avail) | 96 GB | ✅ |

**No carve satisfies both.** This confirms, with measurement, the engine's own note — *"it runs best on
a host of its own"* — and the independent review's verdict. **Halogen Flash-Next's fast path needs a
native Linux install** (no carve; host RAM = device memory = ~124 GiB), not this split Windows/WSL box.

The earlier `Pin::None` path (0.32 t/s) remains available but is unusable, and at 64/64 it is *worse*,
because WSL now has 47 GB of host RAM instead of 108 GB — the trunk can no longer be cached either.

---

## 2. What was actually measured before the carve change

All runs single-model, single-stream, temp 0, 32-token generation.

| # | Variant | Engine / OS | Device pool | Prefill | Decode | Outcome |
| --- | --- | --- | ---: | ---: | ---: | --- |
| A1 | Halogen `.hgn` 115.5 GB | `flash_serve`, WSL, `Pin::None` | pooled | **129.5 s / 57 tok = 0.44 t/s** (cold) | **0.32 t/s** | loads, **correct** ("Paris"), 25.5 GiB resident — but streaming, unusable |
| A2 | Halogen `.hgn` pinned | `flash_serve` + `hipshim2`, WSL | 64 GiB | — | — | **dies at 48 GiB mapped** (pool ceiling); safe kill at 1.1 GB free |
| B1 | UD-IQ4_XS 87.25 GB + MTP | `myhacsint` Vulkan, Windows | 64 GiB | — | — | **`ErrorOutOfDeviceMemory`** (needs ≈66 GiB) |
| B2 | UD-IQ4_XS, PLE→CPU + MTP | `myhacsint` Vulkan, Windows | 64 GiB | — | — | **OOM** (still wants ~64+ GiB) |
| B3 | UD-IQ4_XS, all-MoE→CPU | `myhacsint` Vulkan, Windows | 64 GiB | — | — | **OOM** |
| B4 | UD-IQ4_XS, `-ngl 12` (most on CPU) | `myhacsint` Vulkan, Windows | 64 GiB | **1.86 t/s** | **0.32 t/s** | loads, proves weights+template work; CPU-bound, unusable |

**Readings:**
- **The model and both engines are functional.** Halogen produced correct output; the GGUF loaded and
  answered once enough was on CPU. Nothing is corrupt or incompatible.
- **Every failure is the same cause: the device pool is ~23 GiB short of the model.**
- The B4 CPU-bound number (0.32 t/s) and the A1 streaming number (0.32 t/s) both look identical to the
  decode figure because both are memory-bandwidth-starved, not compute-fast. **The fast numbers require
  the weights on the GPU, which requires the carve.**

### Reference: the same engines' published numbers (for the table, once the carve is raised)

| Variant | Source | Prefill | Decode |
| --- | --- | ---: | ---: |
| Halogen Flash-Next | peonist model card | ~1,246 / 1,424 / 1,358 t/s @8k/32k/131k | 30–50 t/s |
| Halogen Flash-Next | Reddit (Strix Halo) | ~1,300 t/s @0 ctx | 30–50 t/s |
| UD-IQ4_XS + MTP | Reddit (same box class) | 300–430 t/s | 38 t/s (MTP), 22.5 (no MTP) |
| Halogen **27B** `.hgn` | **our own, WSL + shim** | 482→228 ms (5 tok) | **23.9 t/s** (MTP) |

---

## 3. Variants on disk vs available

Only **two** Flash-Next variants are local. The founder wanted "all of them"; the rest need downloading
(after the carve change, depending on disk).

| Variant | On disk? | Size | Notes |
| --- | --- | ---: | --- |
| **Halogen `.hgn` w4b** | ✅ | 115.5 GB + 2.4 + 2.3 overlays | downloaded + SHA256-verified today |
| **unsloth UD-IQ4_XS + MTP** | ✅ | 87.25 GB + 2.6 GB MTP | complete (3 shards + shared-Q8_0 head) |
| unsloth Q3_K_XL / Q4_K_XL | ✗ | ~70 / ~92 GB | "quality-max fallback"; no acceptance gain |
| jcbtc CIRU-STRIX-IU4 / Orca | ✗ | ~90 GB | Strix-specific, ~Q5 quality, needs custom fork |
| agentionai ROCmFP4-FAST | ✗ | ~90 GB | needs `LaurentZuijdwijk` Vulkan fork; crashes 200k+ on Vulkan |
| Ornith 1.5 35B A3B (MoE) | ✅ | 17.7–21.3 GB | already measured: 1,045–1,490 prefill, 63–99 t/s |

**Free space:** C: currently **593.7 GB free**. Full Flash-Next sets are ~90–118 GB each; three more
variants ≈ 300 GB — feasible but leaves ~290 GB. The `.hgn` set (115.5 GB) plus its WSL ext4 copy
duplicates ~250 GB if both are kept; the ext4 copy can be deleted (it is only a staging artifact).

---

## 4. Windows vs WSL — what each is good at

| | **Windows / Vulkan** | **WSL / HIP (DXG)** |
| --- | --- | --- |
| Flash-Next engine that works | `myhacsint` build (loads split GGUF, has MTP) | Halogen `flash_serve` (`.hgn` only) |
| Device pool seen | 64.07 GiB @0.5 carve | 63.9 GiB @0.5 carve (same!) |
| MTP | ✅ (`--spec-type draft-mtp`, depth 3 best) | ✅ engine-internal (`drafter 1`) |
| PLE/ngram host-mapping | ✅ `--load-mode none` | ✅ built-in (paged) |
| Vision | ✅ mmproj | ✅ `HALOGEN_VISION_TOWER=1` |
| Openness | ✅ open (PRs) | ✗ closed binary |
| Co-residence with brain/STT/TTS | easier (start/stop per process) | possible but heavier |

**Both see the same 64 GiB pool**, so the carve fix helps either path equally. Recommendation stands
from the earlier work: **Windows/Vulkan for the co-resident REV:N World Engine; Halogen only if the
machine is dedicated to it.**

---

## 5. Exact commands once the carve is raised (32–64 GB)

> ⚠️ Both engines must run **one at a time** and neither should be launched while a run is already
> resident. Change the carve in **AMD Software: Adrenalin Edition → Performance → Tuning** (or BIOS),
> set *Dedicated Graphics Memory* to 32–64 GB, then reboot the WSL VM (`wsl --shutdown`).

### Windows / Vulkan (GGUF) — the REV:N default candidate
```powershell
C:\AI\runtimes\myhacsint-2dff859\llama-server.exe `
  -m C:\AI\models\qwen38-flash\unsloth-UD-IQ4_XS\Qwen3.8-Flash-Next-UD-IQ4_XS-00001-of-00003.gguf `
  -md C:\AI\models\qwen38-flash\unsloth-UD-IQ4_XS\MTP\mtp-Qwen3.8-Flash-Next-shared-Q8_0.gguf `
  --alias qwen3.8-flash-next --host 127.0.0.1 --port 8080 `
  -fa on --parallel 1 --fit on --load-mode none `
  -ub 256 -b 512 -ctk f16 -ctv f16 `
  --spec-type draft-mtp --spec-draft-n-max 3 --spec-draft-p-min 0.75 `
  --jinja -np 1
```
Validation: look for an `n_ctx` near 262144 and a `draft acceptance` line; no draft line = MTP off.

### WSL / Halogen (`.hgn`) — the speed challenger
```bash
export HALOGEN_CTX=262144 HALOGEN_KV_POOL_POSITIONS=524288 HALOGEN_KV_SLOTS=2 HALOGEN_CACHE_ENTRIES=6
LD_PRELOAD=$HOME/hipshim2.so $HOME/halogen-flash/bins/flash_serve \
  --ck /home/revn/models/halogen-flashnext/qwen38-flash-next-w4b.hgn --port 8730 --bind 127.0.0.1
```
(No `HALOGEN_FLASH_PIN_TRUNK=0` → pinning, which `hipshim2.so` now supplies safely with a memory guard.)

---

## 6. What "the Halo kernel is extremely fast, the model just needs optimisation" means concretely

The founder's intuition is **half right, and the measurement split it precisely**:

- **The kernels are not the problem** — confirmed. The closed engine loads, reads the format, runs its
  MTP drafter, and produces correct output.
- **The model does not need optimisation either** — it needs **memory the split cannot provide.**
  Halogen's design assumes host RAM and GPU memory are *the same pages* (native Linux, no carve). On
  Windows/WSL they are decoupled by the carve, and the pinned path needs ~82 GiB of one *and* ~90 GiB
  of the other simultaneously. §2b shows no carve satisfies both.

So the honest conclusion: **on this machine the Halo fast path is a native-Linux project.** The GGUF
path (Windows/Vulkan) is the working World Engine at 64/64, and it is genuinely fast (100–200 t/s
prefill, 20 t/s decode, MTP at 100% acceptance).

### Recommendation for REV:N

1. **World Engine now: Flash-Next UD-IQ4_XS + MTP on Windows/Vulkan at 64/64.** Measured, working,
   full context. This replaces the earlier "Halogen challenger" plan for the shared box.
2. **Halogen: dedicate a native-Linux machine if the ~1,300 t/s prefill is worth it.** On that host
   (no carve) it is exactly the engine's intended configuration. Keep the `.hgn` on disk for that.
3. **The agent-split idea still stands and is independent of the engine** — see the build guide; small
   role models fit the split far more comfortably than one 125B monolith.

### One open decision for the founder

The 64/64 carve is right for the GGUF and wrong for Halogen. If you want to *test* Halogen seriously,
set the carve to **8–16 GB** (Windows gets ~112–120 GB, WSL can pin), accept that the GGUF then won't
fit its pool, and we retest. That is a one-time experiment to confirm the arithmetic above; it cannot
be a shared production setting on this box.

**Bottom line:** everything on disk works; the choice is which engine the machine is configured for.
At 64/64 that is **Flash-Next GGUF + MTP**, benchmarked above.
