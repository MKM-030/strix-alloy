# Small carve-out: verified results and what it means (2026-09-12)

Founder changed the Adrenalin split to **Dedicated Graphics Memory = minimum, Remaining System Memory
= maximum**, then rebooted. This is the measured outcome and the revised plan.

## The split actually applied

| | before | **now** |
| --- | ---: | ---: |
| Physical (CIM) | 31.6 GB | **127.1 GB** |
| Windows visible | 31.6 GB | **127.1 GB** |
| iGPU carve-out | ~96 GB | **~0.5 GB** (AdapterRAM 0.5 GB) |
| WSL VM (`.wslconfig memory=100GB`) | 29 GB | **98 GB** |
| WSL GPU "total" (`mem_get_info`) | 119.89 GB | **68.61 GB** |

`.wslconfig` is now `memory=100GB swap=32GB` (backup: `.wslconfig.revn-100gb`).

## What improved (measured, same binaries)

**halogen-27B (real engine + `hipshim`):**
```
before: checkpoint registered 35.9 GB in 105 s · prompt cache OFF (1.3 GB free, floor 36.9 GB)
now:    checkpoint registered 35.9 GB in  76 s · prompt cache 59.1 GB AUTO — 3 x 262144-token entries
        (warm decode BITWISE identical to cold)
        prefill 482 ms -> 228 ms
        INFO cache_mb field: 0 -> 56317
```
The prompt cache coming alive is the headline win: returning agent turns now reuse a 262K history
for free, which is exactly the workload REV:N workers have.

**llama.cpp HIP 27B (WSL):** still works — pp512 ≈ 250 tok/s, tg64 ≈ 10.4 tok/s (same band as before;
the extra host RAM does not change compute).

## One real side-effect to understand: the GPU device ceiling shrinks

GTT scales with **visible system RAM**, so shrinking the carve-out from 96 GB to 0.5 GB also lowered
the GPU-visible pool:

```
mem_get_info total : 119.89 GB  ->  68.61 GB
largest device alloc (unfilled) : ~88 GB  ->  ~63 GB
rocminfo coarse pool : ~111 GB -> 67.0 GB   (fine pool 103 GB)
```

**This is the trade.** The carve-out was acting as a *reservation* that guaranteed the GPU a large
pool; with 0.5 GB, the GPU's ceiling is now bound by the 98 GB WSL VM and the DXG/GTT limits, landing
at ~63–68 GB usable. So:

| Resource | before (32/96) | now (min carve-out) |
| --- | ---: | ---: |
| Windows/WSL host RAM | 31.6 GB | **127 GB / 98 GB** |
| GPU device ceiling | ~88 GB | **~63–68 GB** |

For a 68 GiB-resident model like Flash-Next this lands right at the edge — which is the open question
for the next step.

## Revised decision for Halogen Flash-Next

The RAM blocker is **mostly** resolved: `flash_serve` needs ~68 GiB resident, and the GPU can now
allocate ~63–68 GB while the host holds 98 GB. That is borderline and depends on:
- whether `flash_serve` runs with **`HALOGEN_FLASH_PIN_TRUNK=0`** (no pinning — the engine's own
  "last resort"), which trades decode speed for not needing a pinned reservation, and
- how much of the 47.7 GiB n-gram table must sit in the page cache alongside the resident trunk.

The disk blocker stands until the cleanup finishes (~118 GiB needed; C: was at 108 GB free).

**Next experiment once disk allows:** download base + overlay, then run
`flash_serve --ck qwen38-flash-next-w4b.hgn --port 8731` with `HALOGEN_FLASH_PIN_TRUNK=0` and watch the
startup line, which reports what it leaves behind. If the ceiling is short by a few GB, the knobs are
`HALOGEN_KV_POOL_POSITIONS`, `HALOGEN_HOST_RESERVE_GIB`, `HALOGEN_QSA_STRIP_MB`.

## The ceiling rule (measured, important)

The GPU device ceiling tracks the **carve-out only**, not the WSL VM size:

| iGPU carve-out | WSL `memory=` | GPU `mem_get_info` total | largest device alloc |
| ---: | ---: | ---: | ---: |
| ~96 GB | 30 GB | 119.89 GB | ~88 GB |
| ~0.5 GB | 98 GB | **68.61 GB** | ~63 GB |
| ~0.5 GB | 62 GB | **68.61 GB** | — |

So lowering the carve-out *frees host RAM* but *caps the GPU pool at ~68.6 GB*. The carve-out is the
GPU's reservation; the WSL VM size is irrelevant to it. This is the central trade for this machine:

- **Want ≥69 GB per model (Flash-Next, Ciru 44 GiB KV):** need a larger carve-out.
- **Want the host to see ~127 GB (LM Studio + gemma + STT/TTS live stack, big page cache):** keep the
  carve-out minimal and accept a ~68 GB per-model ceiling.

### Measured effect on Ciru (vLLM)

- Full profile (21.17 GB model + **44 GiB** KV = 65.2 GiB) **fails** at the 63.9 GiB ceiling
  (`Tried to allocate 43.99 GiB; 63.90 GiB total, 37.12 GiB free`).
- With **`--cache-gib 36`** (21.17 + 36 = ~57 GiB) Ciru **starts and serves** on port 8000 with
  `ctx 262144`. So Ciru keeps working under the small carve-out at a reduced KV pool.

### Measured effect on halogen-27B

- **Large gain:** the prompt cache went from OFF to **59.1 GB AUTO (3 × 262K entries)** because the
  host now has the RAM to hold it; warm decode is bitwise-identical to cold. Prefill 482 → 228 ms.
- The model itself (35.9 GB mapped + ~17.8 GB resident pool) still fits under the 68.6 GB ceiling.

## Practical recommendation for a mixed REV:N day

| Workload | Carve-out | WSL `memory=` |
| --- | ---: | ---: |
| LM Studio / gemma / STT / TTS (live product, Windows side) | min (0.5 GB) | 100 GB |
| halogen-27B (with prompt cache) | min (0.5 GB) | 100 GB |
| Ciru (reduced KV, e.g. `--cache-gib 36`) | min (0.5 GB) | 100 GB |
| Ciru **full** 44 GiB KV, or Flash-Next 68 GiB | **~16–32 GB** | 100 GB |
| Qwen-27B-BF16 (51 GB) alone | min works | 100 GB |

If Flash-Next comes up a few GB short, raise the carve-out to ~16 GB (host still ~111 GB) rather than
reverting to 96 GB.
