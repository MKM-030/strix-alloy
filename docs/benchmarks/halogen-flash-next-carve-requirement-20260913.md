# Flash-Next on Halogen: the exact carve requirement (measured 2026-09-13)

Founder goal: run **Halogen Flash-Next** (the fast kernel) on Windows. Progress: the engine now gets
through **pinning the full 65.6 GiB trunk + 2.4 GiB overlay**, and fails only on working memory — which
is a precise, solvable carve number. The 27B Halogen runs in production today; Flash-Next needs one
more carve step.

All measurements at the carve the founder set, WSL `memory` as noted.

## 1. What each carve produced (measured)

| Carve | Device pool | Windows RAM | Result |
| ---: | ---: | ---: | --- |
| 0.5 GB | 64.0 GiB | 127 GB | trunk pins 65.6 GiB only on the very first post-boot attempt; overlay refused |
| **8 GB** | **67.8 GiB** | 119.6 GB | trunk pinned 65.60 GiB ✅, overlay 2.40 GiB **refused** (pool 0.3 GiB short) |
| **16 GB** | **71.7 GiB** | 111.6 GB | **trunk 65.60 GiB ✅ + overlay 2.40 GiB ✅ both pinned**, then `CreateContext fail c000000d` |
| 64 GB | 95.8 GiB | 63.6 GB | pin **refused** — host RAM "MemAvailable 45.92 GiB" insufficient |

So the progression is exact:
1. **Too small a carve** → the pool cannot hold trunk + overlay (8 GB: 0.3 GiB short).
2. **16 GB** → weights pin, but after 68.0 GiB of the 71.7 GiB pool is consumed only **3.7 GiB** remains,
   and the engine's *working memory* (KV pool + prefill arena + scratch) needs more → `c000000d`.
3. **Too large a carve** → Windows/WSL host RAM shrinks below the ~82 GiB the pin guard requires.

## 2. The engine's own memory doc (from `flash_serve` strings)

```
HALOGEN_KV_POOL_POSITIONS  resident attention positions (~29.5 KiB each: 262144 ≈ 7.2 GiB)
HALOGEN_MAX_TOK            the single-call PREFILL ARENA (32768 ≈ 16.7 GiB, 16384 ≈ 8.4, 4096 ≈ 2)
HALOGEN_HOST_RESERVE_GIB   RAM left for the 47.7 GiB n-gram page cache
```

Measured working-memory figure from an earlier unpinned run: **~18.5 GiB of working memory** at the
default arena. That is the budget that must fit *beside* the pinned weights.

## 3. The carve window for Flash-Next

Requirement: **pool ≥ 68.0 (weights) + working (~10–12 GiB with a reduced arena) ≈ 78–80 GiB**, while
host RAM stays ≥ ~85 GiB for the pin.

`pool = 64 + carve/2`:

| Carve | Pool | Weights+working (≈80) | Windows RAM (pin budget) |
| ---: | ---: | --- | ---: |
| 16 GB | 71.7 | ✗ 8 GiB short | 111.6 GB ✅ |
| 24 GB | 76.0 | ✗ 4 GiB short | 104 GB ✅ |
| **32 GB** | **80.0** | ✅ **fits** | **96 GB ✅** |
| 40 GB | 84.0 | ✅ 4 GiB headroom | 88 GB ✅ |
| 48 GB | 88.0 | ✅ 8 GiB headroom | 80 GB ⚠️ pin margin thin |

**Recommended: 32 GB** — the smallest carve whose pool clears weights + working memory while host RAM
(~96 GB) stays comfortably above the pin guard. 40 GB gives more margin if the reduced arena proves
too slow.

## 4. Why the pieces that already work, work

| Model | Weights | At 8 GB (pool 67.8) | At 16 GB (pool 71.7) |
| --- | ---: | --- | --- |
| **Halogen 27B** | 35.9 GiB | ✅ **runs** (32 GiB left for working) | ✅ runs |
| Halogen Flash-Next | 68.0 GiB | overlay refused | weights pin, working memory short |

The 27B leaves ~32 GiB of pool for working memory — that is why it is stable at 8 GB. Flash-Next leaves
3.7 GiB at 16 GB. At **32 GB** Flash-Next would leave ~12 GiB, matching the 27B's healthy margin.

## 5. Additional levers confirmed present in the engine

- `HALOGEN_CK_OVERLAY_SKIP=<regex>` — skip overlay tensors (quality cost) to reclaim pool.
- `HALOGEN_MAX_TOK=4096` — smallest prefill arena (~2 GiB vs 16.7 at 32768); costs prefill speed.
- `HALOGEN_KV_POOL_POSITIONS` — pool ≥ ctx, minimum 32768.
- `HALOGEN_QSA_STRIP_MB`, `HALOGEN_QSA_DENSE`, `HALOGEN_QSA_NOSKIP` — QSA sparse-attention tuning.
- `HALOGEN_FLASH_PIN_TRUNK=0` — the unpinned fallback (0.32 t/s, not usable).

## 6. Status summary

| | Engine | Carve | State |
| --- | --- | --- | --- |
| **Halogen 27B** | `halogen` + `serve_api.py` (8730/8731) | **8 GB** | ✅ **production, live** |
| Halogen Flash-Next | `flash_serve` + `hipshim2.so` | **32 GB** | weights verified pinnable; needs the working-memory margin |
| Flash-Next GGUF | `myhacsint` Vulkan (8090) | 64 GB | measured 201 t/s prefill, 22 t/s decode, MTP 100% |

**Next action:** set *Dedicated Graphics Memory* to **32 GB** and reboot, then run
`halo-fe-16gb.sh` (change `HALOGEN_KV_POOL_POSITIONS`/`MAX_TOK` to the reduced values from §3). That is
the last step to a working Halogen Flash-Next on Windows.

**Shim note:** the pin works via `hipshim2.so` (single-residency mapped-pin with a memory guard). On
SIGKILL the pinned pages are released only on WSL restart, so always `wsl --shutdown` between engine
swaps.
