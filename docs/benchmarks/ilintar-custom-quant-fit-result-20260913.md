# ilintar custom-quant attempt: result and the memory arithmetic (2026-09-13)

## Result

The **95.8 GiB ilintar IQ4_NL** set downloaded complete and size-verified (all 9 shards match the HF
manifest exactly). Launching it on the `strix-halo` fork at the **32 GB carve / 76 GB WSL** failed:

```
ggml_backend_cuda_buffer_type_alloc_buffer: allocating 3488.00 MiB on device 0: cudaMalloc failed: out of memory
graph_reserve: failed to allocate compute buffers
llama_init_from_model: failed to initialize the context: failed to allocate compute pp buffers
llama_server: exiting due to model loading error
```

Reproduced twice (large batch, then minimal `-b 512 -ub 512 -c 8192`, no MTP). The memory watchdog
killed the process at 1.4 GB host-free **before** it could wedge Windows — the guard worked.

## Why — the arithmetic

| | Total on disk | PLE (lazy) | Resident | vs 79.7 GiB pool (32 GB carve) |
| --- | ---: | ---: | ---: | --- |
| unsloth UD-IQ4_XS (worked, 300 t/s) | 87.25 GiB | ~26.8 | **~60 GiB** | fits, ~20 GiB spare ✅ |
| ilintar IQ4_NL (failed) | **95.8 GiB** | ~26.8 | **~69 GiB** | fits alone, but **+KV+compute+scales exceeds** ❌ |

The custom quant is **~8.5 GiB larger** than the stock one, and its `PROJFIX` arrangement appears to
keep more resident. With `GGML_HIP_ENABLE_UNIFIED_MEMORY=1` on a 76 GB WSL cap, device + host draw on
the same budget, so ~69 GiB of weights leaves too little for the compute buffers.

## What would make it fit

1. **Raise the carve to 64 GB** → device pool ~96 GiB, Windows sees 63.6 GB. The model needs ~69 GiB
   resident, so this fits the *pool*, but WSL then gets ≤ ~56 GB host — **likely too little** for the
   unified-memory accounting. This is the same pool-vs-host squeeze that blocks Halogen.
2. **Raise WSL memory** — not possible at 64 GB carve (Windows only has 63.6 GB to give).
3. **Use the stock UD-IQ4_XS instead** — it already runs here at **300.8 t/s prefill / 6.97 t/s
   decode** on the same fork, with the fork's kernels engaged. That is our verified Windows number.

**Verdict: on this 128 GB box with a Windows/WSL carve, the 95.8 GiB custom quant does not fit
alongside the OS.** If exact ilintar-class numbers matter, the clean route is a **native Linux boot**
(no carve split, full 124 GB), where Halogen 0.7.0's BYO-GGUF also becomes available.

## What we DO have working (verified on Windows/WSL)

| Config | Prefill | Decode | Status |
| --- | ---: | ---: | --- |
| strix-halo fork + **stock UD-IQ4_XS** | **300.8 t/s** @36k | 6.97 t/s | ✅ runs |
| strix-halo fork + ilintar IQ4_NL | — | — | ❌ OOM (model too large for the split) |
| Halogen `.hgn` (any mode) | — | — | ❌ WSL unsupported (confirmed by Peonist) |
