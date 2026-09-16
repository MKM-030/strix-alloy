# Halogen Flash-Next on this box: measured verdict (2026-09-12)

The engine is real, loads, and answers correctly on this WSL/DXG host — but **it cannot reach its
fast path here, and its safe path is ~1000× too slow.** This is a measured result, not the earlier
planning estimate. It changes the World-Engine recommendation.

## What was actually measured

All four `.hgn` files were downloaded and **SHA256-verified** against HuggingFace's LFS hashes
(base 124,068,083,904 B; quality overlay 2,572,466,560 B; speed overlay 2,478,095,488 B; vision
897,916,416 B). The checkpoint was staged on WSL ext4 (to avoid 9p page faults on the 47.7 GiB
n-gram table). `flash_serve` 0.6.1 (from `ghcr.io/peonist-ai/halogen-flash-server:0.6.1`) ran under
the Ciru ROCm-10 runtime with `HSA_ENABLE_DXG_DETECTION=1`.

### Run A — `HALOGEN_FLASH_PIN_TRUNK=0` (the engine's own no-pin mode)

Startup, verbatim:

```
checkpoint: mapped 124.1 GB, NOT pinned (Pin::None)
checkpoint: mapped 2.6 GB, NOT pinned (Pin::None)
overlay: 30 tensors upgraded to q8g64 in place of Q4C-P
overlay: 741 tensors, 2.40 GiB from …/qwen38-flash-next-w4b.overlay.hgn
startup [25.9 s] memory: 0.0 GiB of weights locked in RAM, 7.2 GiB of KV pool, 18.3 GiB of working memory, 25.5 GiB in all
startup [25.9 s] the model's 47.7 GiB lookup table is NOT held in RAM; read from disk through the file cache
startup [25.9 s] host memory left for everything else: 106.4 GiB total
flash_serve: listening on 127.0.0.1:8730, 2 slots over ONE 262144-position KV pool
```

The **full 262,144-position KV pool fits**, the engine starts in **25.9 s**, and its **total resident
memory is only 25.5 GiB** — because **0.0 GiB of weights are locked: every weight is streamed from
disk on demand.** Output was correct (`"Paris"`). Performance:

| | Measured |
| --- | ---: |
| Cold prefill, 57 tokens (first request, cold page cache) | **129.5 s** |
| Warm prefill, same 57 tokens | **61.5 s** |
| Decode (MTP, 24 tokens) | **0.32 t/s** |
| Total, first request | 205 s |

This is **~1000× below the published ~1,300 t/s prefill / 30–50 t/s decode.** It is not a config
error: it is the documented consequence of `Pin::None` ("costs several times the decode speed"). The
engine's own host-memory line is the tell — *0.0 GiB of weights locked*.

### Run B — pinning ON, with `hipshim.so` preloaded

Without `LD_PRELOAD`, the engine refuses to pin (its guard: *"refusing to pin … MemAvailable … and the
floor is …"*) and falls back to `Pin::None`. With the shim (the same shim that made the 27B engine
work), `hipHostRegister` on the file-backed mmap "succeeds" via the hipMalloc+hipMemcpy fallback, so
**the engine proceeds down its pinned path** — and the shim then **bypasses the engine's own pin
guard**:

| Observation | Value |
| --- | ---: |
| Shim registrations before the kill | 212 chunks (`hipHostRegister fallback`) |
| Engine host RSS | 12 GB → 32 GB → **57 GB**, still climbing |
| Windows free physical memory | 127 GB → **1.1 GB** |

The run was **killed at 1.1 GB free** (no freeze occurred; memory recovered to 57 GB free). It was
3.5 minutes into pinning and nowhere near done.

**Interpretation:** pinning materialises the whole ~115 GB checkpoint in host memory and copies the
registered regions to the device. On a 127 GB machine — with Windows plus a WSL VM at 108 GB — the
host simply cannot hold a pinned 115 GB checkpoint. The engine's own guard knows this and refuses;
**the shim defeats that guard and drives the box toward exhaustion.** The earlier fit-analysis claim
that "the `hipshim` is not even needed for flash_serve" was wrong in the opposite direction: the shim
is *the only way to reach the pinned path*, and using it here is **unsafe**.

## Verdict

**On this machine, Halogen Flash-Next is not viable at speed.**

- **Safe path (`Pin::None`):** stable, correct, full 262k context in 25.5 GiB — but **0.32 t/s**
  decode, which is unusable for a World Engine (or anything interactive).
- **Fast path (pinned):** requires ~115 GB of non-swappable host RAM the machine does not have; the
  shim that enables it also removes the engine's safety guard. **Do not run `flash_serve` under
  `hipshim.so` on this host.**

The engine's own documentation says it "runs best on a host of its own." Our measurement confirms
that literally: it wants **≥128 GB free to itself**, which a shared 128 GB box cannot give.

**Do not retry the shimmed pin.** It is a known, dangerous over-allocation here.

## What this means for REV:N

1. **World Engine: use the llama.cpp/Vulkan shape (untested here yet).** The independent review already
   recommended it as the default; this measurement now supplies the *reason*: llama.cpp mmaps the GGUF
   and places weights in unified memory through Vulkan (no 115 GB host pin, no shim), with
   `--load-mode none` keeping the 26.8 GiB PLE table out of the carve. The community numbers
   (200–430 prefill, ~38 t/s decode with MTP) came from exactly this shape on this hardware class.
2. **Halogen is retained only as a dedicated-host / future arm** — its published ~1,300 t/s prefill is
   real *given a host of its own*, which this box is not. It matches the existing
   `WORLD-MODEL-HALOGEN-HYBRID-20260909` parked arm; the Reddit research's "challenger, not default"
   conclusion stands and is now measured.
3. **The `.hgn` download was not wasted** — it proves the ceiling and settles the question with data
   rather than arithmetic. It stays on disk (ext4 + `C:\AI\models\halogen-flashnext`, ~252 GB) for a
   future dedicated host or a pinned-capable configuration.
4. **The co-load test the review demanded is now moot for Halogen** (it can't even load fast enough
   alone). It remains the right test for the llama.cpp shape.

## Open items

- Measure the **llama.cpp/Vulkan UD-IQ4_XS + MTP** shape on this box (the actual candidate).
- Decide whether to reclaim the ~252 GB of `.hgn` files (C: had 723 GB free before; the ext4 copy is
  in the sparse VHDX).

## Safety note for the log

Two machine-safety events now on record: the earlier memory-capability probe that froze the desktop,
and this shimmed-pin run that reached 1.1 GB free before being killed. The common factor is
**unbounded host-memory allocation**. All future Flash-Next runs must either stay in `Pin::None`
(bounded, safe) or use the llama.cpp path; the shim must not be used with `flash_serve`.
