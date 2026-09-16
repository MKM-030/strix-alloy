# PLE host-side staging measured: the hypothesis is refuted (2026-09-15)

## Result

**PLE host-side staging costs ~0.05% of the decode wall. It is not a material part of the target
verify time.**

Measured directly by instrumenting `llm_graph_input_ple::set_input()`, split into its three phases:

| prompt | calls | tokens | prev | hash | gather | upload | host-total | per token |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| MTP n-max 2, 8k | 224 | 17,039 | 3.1 ms | 1.0 ms | 0.0 ms | 0.2 ms | **4.3 ms** | 0.252 µs |
| no MTP, 8k | 512 | 16,894 | 3.2 ms | 1.1 ms | 0.0 ms | 0.3 ms | **4.6 ms** | 0.272 µs |

Against the measured decode wall of 7,989 ms / 8,706 ms:

**host-total / decode wall = 0.054 %** (both configurations).

## Why this mattered and how it was tested

Codex's review made a specific, falsifiable claim that my phase analysis had missed:

> "the inspected `40a9f4d0` implementation, the lazy PLE path performs a host-side gather into staging
> memory and then supplies that input tensor. A wall-clock interval around `llama_decode` can include
> this preparation."

**I verified the claim in source before accepting or rejecting it.** It is real — `set_input()` runs
host-side inside `llama_decode` and does four non-GPU things (source comments confirm the design):

1. `mctx->get_prev_tokens()` — predecessors from the KV cells
2. a **host-side n-gram hash** — *"The hash runs host-side because ggml has no int64 and no xor"*
3. `ple_reader->gather()` — *"257k-393k scattered 90-byte reads, ~300 ms with the GPU idle"*
4. `ggml_backend_tensor_set()` — host→device staging upload

So the premise was right: my "~80% is GPU work" framing was **too strong**, and I retracted it in favour of
"the remaining target-call latency is uncomposed."

**Then I measured it, and the magnitude is negligible for warm decode.** ~4.3 ms of host work against
~8,000 ms of decode wall.

## The interesting detail: `gather` measured 0.0 ms

The scatter-gather — the one the source comment describes as the expensive part at *"~300 ms"* — showed
**0.0 ms across all calls**. Two compatible readings, and I cannot distinguish them from this experiment:

- the lazy reader's gather branch is **inactive** in this configuration, so rows are fetched by the
  on-GPU `get_rows` path instead (the code has both branches: `if (pmodel.ple_reader) { … } else { … }`);
- or it is genuinely cheap here.

Note the source comment's ~300 ms figure is about a **chunk boundary with the GPU idle** during prefill —
a different regime from steady-state warm decode. The absolute numbers are not directly comparable.

**This means the PLE storage hypothesis is not closed for prefill.** The decode result (0.05%) is solid;
the prefill case remains untested, and that is exactly where the source says the stall lives.

## What this changes

| prior belief | status |
| --- | --- |
| "~80% of decode wall is GPU work" | **corrected** to "uncomposed" — host-side staging is real but only 0.05% |
| "PLE table access is a candidate for warm decode" | **refuted** — 0.054% of wall. Do not optimize this for decode. |
| "PLE access might explain the prefill gap" | **still open** — the ~300 ms chunk-boundary comment is a prefill phenomenon; needs its own measurement |

Per Codex's decision gate (deprioritize when the upper confidence bound on benefit is below ~2%), **PLE
row-access optimisation for warm decode is now closed** at 0.054%.

## Method note

This was the cheapest useful experiment of the whole session: one instrumentation point, one rebuild, one
benchmark run, and it converted a plausible-sounding hypothesis into a hard number. Contrast with the
per-op profiling attempts — three methods, many rebuilds, zero usable numbers. **Measuring the thing
directly, even narrowly, beat trying to profile everything.**

## State

- Both instrumented files reverted; `win-native` clean; `llama.dll` and `ggml-hip.dll` rebuilt and
  **verified free of `PLE_TIMING` / `OP_TIMING` strings**, 0 compile errors.
- Production throughput unaffected by the instrumentation (8k: 992 t/s prefill, 29.3 t/s decode).
