# Flash-Next (strix-halo fork) verified numbers on Windows/WSL — 2026-09-13

Config: `pwilkin/llama.cpp@strix-halo` (commit `f5daaa3c`), stock **unsloth UD-IQ4_XS** + shared MTP
head, WSL 88 GB, iGPU carve 32 GB, `--load-mode none --lazy-mode on-direct`, MTP depth 2.
All numbers are server-reported timings (prompt/decode per second), single stream, temp 0.

## Measured

| Prompt | Prefill | Decode | MTP acceptance | Notes |
| --- | ---: | ---: | ---: | --- |
| 57 tok (cold) | 27.8–42 t/s | **13.7–16.4 t/s** | **77%**, len 2.55 | server warm-up inflates per-token cost |
| 18,699 tok | **543.8 t/s** | 7.0 t/s | 0% (see below) | cold cache, first long prompt |
| 20,113 tok | **530.2 t/s** | 7.4 t/s | 0% | |
| 25,291 tok | **538.3 t/s** | 7.2 t/s | 0% | |

**Reproducible:** prefill **~530–544 t/s at 18–25k tokens**, twice in a row, on two separate server
launches. That is the real Windows/WSL number for the fork on a stock quant.

## The two things this run clarified

1. **Prefill is genuinely fast and flat.** ~535 t/s holds from 18k to 25k tokens — the fork's fused
   Gated-DeltaNet and sparse-attention kernels are doing their job. This is the World-Engine-relevant
   axis and it is *better* than the 300 t/s measured earlier (that run's prompt was shorter/warmer).

2. **MTP collapses to 0% acceptance at long context, and that is why decode is 7 t/s there.**
   - short prompt: **77% acceptance, mean draft length 2.55** → 16 t/s decode
   - long prompt: **0% acceptance, mean draft length 1.00** → 7 t/s decode
   - `mean len 1.00` means the drafter proposes nothing usable; every token is verified serially.
   This is the concrete, measured answer to "why is decode slow": **speculation stops working at depth**,
   so long-context decode falls to the base rate. It matches the author's own note that draft
   acceptance varies by text type and drops with depth.

## Depth limit observed

Requests at ~16k+ *words* (my generator's ~35k+ tokens) returned HTTP 400 — the server caps
`prompt + max_tokens` against the KV pool, and `-c 32768`/`-c 65536` reserve the requested max_tokens.
This is a test-harness limit, not a model limit; a properly sized pool would accept it.

## What this means for REV:N

- **Prefill (~535 t/s) is production-grade** for a long-context World Engine.
- **Decode at long context (7 t/s) is the bottleneck**, and the cause is now *measured*: MTP acceptance
  → 0 at depth. The kernel-session follow-up should target exactly this (why does the drafter stop
  helping as context grows — drafter context handling, not the base kernels).

## Hardware/OS notes discovered this session

- **Load from `/mnt/c` is required for stability**, not just speed. Loading the same model from WSL
  **ext4** balloons the WSL VM to its cap and starves Windows (observed Windows at 86 MB free → the
  watchdog killed the load). `/mnt/c` lets the page cache live on the Windows side, which is
  reclaimable. (This reverses the earlier "stage to ext4" advice for models this large.)
- **`dxgkio_escape: Ioctl failed: -75`** appears in `dmesg` after repeated failed GPU allocations; a
  full `wsl --shutdown` clears it. A wedged server must be restarted, not retried.
- **The 16 GiB pin floor is hardcoded** in `flash_serve` (no env var) — this is what blocks Halogen
  from loading a 70 GiB trunk at 88 GB WSL.

## Crash-dump hygiene

Seven `flash_serve` dumps (293 GB) were written to `%LOCALAPPDATA%\Temp\wsl-crashes` during the failed
Halogen attempts. Deleted. A daily cleanup task (`REVN-WSL-CrashDump-Cleanup`, keeps newest dump) is now
registered, because a crash loop otherwise re-consumes hundreds of GB silently.
