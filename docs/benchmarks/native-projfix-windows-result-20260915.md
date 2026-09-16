# Native Windows PROJFIX: 593 t/s prefill + 28–29 t/s decode (2026-09-15)

## The result

Same binary (`C:\AI\build\strix-llama-win`, ROCm 7.2 / clang 21, commit `d67d5883` + prefetch stub),
same flags (`-ngl 999 -fa on -fit off --load-mode none -ctk f16 -ctv f16 -c 49152 -b 8192 -ub 8192`),
native Windows, WSL shut down. **Only the quant differs.**

| depth | UD-IQ4_XS prefill / decode | **IQ4_NL PROJFIX** prefill / decode | gain |
| ---: | ---: | ---: | ---: |
| 1024 | 260 / 6.8 | 469–474 / **30.4** | +82% / +347% |
| 8192 | 474 / 14.4 | **593–594 / 28.0** | +25% / **+94%** |
| 16384 | 473 / 14.5 | **590 / 29.0** | +25% / **+100%** |
| 32768 | 459 / 14.5 | **582 / 28.7** | +27% / **+98%** |

**Decode roughly doubled, and prefill gained 25–27%.** This is the first time we have cleared 28 t/s
sustained at 32k depth on this box, and it is 60% above the 14.5 t/s serial figure that everything
before today topped out at.

### Why PROJFIX is so much faster

Recall the quants differ in layout, not bits-per-weight (4.24 vs 4.52 bpw, PROJFIX is *bigger*):
- **UD-IQ4_XS**: experts are IQ3_S (gate/up) + IQ4_NL/Q8_0 (down); attention/GDN projections are Q8_0.
- **PROJFIX**: **every tensor is IQ4_NL**, uniform 1350 MiB/layer experts.

The fork's MMB fast paths are built around **resident IQ4_NL** (`mmb_is_resident_iq4`,
`mmb_dq_iq4nl_bf16_kernel`, the fused `MMB_GLU`/`MMB_DOWN16` kernels). A stock UD quant only partially
qualifies, so it falls back; PROJFIX qualifies everywhere. That is consistent with the author
recommending PROJFIX and with our earlier WSL measurement (839 vs 671 t/s, +25% — the same ratio).

## The carve correction (my earlier advice was wrong)

The device pool grows with the carve, but **the model is UMA — its resident weights come from host RAM**,
and the carve takes host RAM away. Measured on this machine:

| carve | device pool | Windows total RAM | outcome |
| ---: | ---: | ---: | --- |
| 32 GB | 79.8 GiB | 95.6 GB | WSL ran PROJFIX at 839 t/s |
| 48 GB | ~87.8 GiB | ~79.6 GB | **both paths viable — recommended** |
| 64 GB | ~95.8 GiB | ~63.6 GB | marginal: UD needs 60.4 GiB resident + KV/compute |
| **96 GB** | **111.8 GiB** | **31.6 GB** | **model cannot load natively or in WSL** |

At 96 GB we hit the failure directly: `vmmemWSL` was holding **20.5 GB** of Windows' 31.6 GB, leaving
0.7 GB free, and the HIP loader died at model load. Shutting WSL down recovered 25.2 GB, which was
*just* enough for PROJFIX (66.3 GiB resident) to load and run — i.e. 96 GB works only if WSL is kept
completely off, and even then with almost no margin: no draft head, no second model, no deep context.

**Revised recommendation: 48 GB**, not 96. It leaves ~79.6 GB of host RAM (enough for PROJFIX + the 2.6 GB
draft head + KV + compute with real margin) and an 87.8 GiB pool (enough for ub 16384 and deep context).
96 GB is a net loss on a UMA box because the pool it buys cannot be used without the RAM it costs.

## PROJFIX + MTP: 33–35 t/s decode, no override needed

Adding the shared MTP head (`-b/-ub 2048`, which Bug A requires) on top of PROJFIX:

| depth | prefill t/s | decode t/s | acceptance |
| ---: | ---: | ---: | ---: |
| 1024 | 450–457 | **34.9–35.4** | 61% (140/229) |
| 8192 | 506 | 29.8–29.9 | 49% (126/257) |
| 16384 | 500 | **33.4–33.5** | 61% (140/229) |
| 32768 | 491 | **32.6–32.9** | 60% (139/231) |

Two things worth noting: acceptance held at **49–61% across every depth**, so the `indexer.top_k` cliff
that plagued UD did **not** appear here — and **no `--override-kv` was needed**. Decode is now
**33 t/s sustained at 32k**, against 14.5 serial and against the best Vulkan figure of 30 (measured at
short context only).

`-b/-ub 2048` is required (Bug A: the draft load fails at 8192), which costs some prefill — 491 vs 582
at 32k. That is the current trade to be aware of: **prefill-only runs use ub 8192 (582 t/s);
decode-oriented runs use ub 2048 (491 t/s prefill, 33 t/s decode).**

## What this changes

| | before today | now |
| --- | ---: | ---: |
| best prefill (native Windows) | 474 | **593** |
| best decode (native Windows, serial) | 14.5 | **28.7** |
| best decode anywhere | 30 (Vulkan+FR-Spec) | **30.4 native** (and now at depth) |

Native Windows with PROJFIX now matches or beats the Vulkan path on decode *and* is 60% faster on
prefill — so the two-engine split is no longer necessary for these workloads. The remaining gap to
the author's 1204 t/s prefill is then attributable to the **compiler** (clang 21 vs his clang 23) and
his retained-PM4 runtime, not the quant.
