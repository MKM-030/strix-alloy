# Per-op composition: what I tried, what is real, and why the numbers are not usable (2026-09-15)

## Bottom line

I could **not** produce a trustworthy per-op composition for the production (graphs-on) decode path.
Three distinct methods were tried; all three are blocked, for three *different* reasons. Separately, **the
one run I previously labelled "RUN VALID" was not valid**, and I am retracting it.

## The three blockers — each verified, each different

| method | what it measures | why it fails here |
| --- | --- | --- |
| **in-graph events** (`LLAMA_OP_TIMING=2`) | per-op GPU time during capture | `hipEventElapsedTime()` returns **400 / `hipErrorInvalidResourceHandle`** for captured events, even when the events are created *outside* the capture region. Proven with pooled pre-capture events. |
| **capture-time CPU wall-clock** (my proposed fix) | enqueue cost only | during stream capture the GPU does **not execute**; `cudaStreamBeginCapture` records work. So wall-clock there measures how long it takes to *record* the graph, not to run it. |
| **eager warmup evals** (aggregate path with graphs on) | real per-op GPU time, valid region | graphs are **warmed up at model load**, so by inference time every eval is a pure replay and the eager path never executes again. Confirmed from the warmup logic (`warmup_complete` is set on the 2nd no-change call at load). |

Also checked and unavailable: **there is no vendor profiler in the TheRock SDK** — no `rocprof`, `rocprofv2`,
`rocprofv3`, or `rocprofiler-sdk` under `C:\AI\sdk\therock1151`. So the standard escape hatch is closed too.

## Retraction of the earlier "valid" composition run

I reported a run as passing its gate (32 summaries, 0 zero-rows, 0 errors) with:
MUL_MAT 56.1%, SCALE 11.5%, RMS_NORM 10.2%, GET_ROWS 8.8%, CONT 6.1%, CPY 4.4%.

**That gate was too weak and the run is not usable**, for two reasons the numbers themselves reveal:

1. **`graphs reused = 255`** — graphs were never actually disabled, despite `GGML_CUDA_DISABLE_GRAPHS=1`
   being set in the process environment. (The variable *is* consulted: `common.cuh:1292`.) So this was not
   the documented graphs-off configuration the path requires.
2. **The decode rate was 10.72 t/s.** Our production decode is 35 t/s, and graphs-off measures ~10 t/s.
   So the run was in a graphs-disabled-like state in *some* sense, yet still reporting replay — the
   configuration is inconsistent with either clean mode, which is itself disqualifying.
3. **The strongest check I should have run from the start:** sum of per-op GPU time vs measured decode
   wall. In the later run that ratio was **0.06×** — the timer accounted for **6% of wall time**. A timer
   that captures 6% of the time cannot be reporting the composition of decode.

**My gate checked "did rows appear and were there errors" — not "does this describe the thing I claim".**
That is the same class of mistake as the earlier `r = 0.47` fit and the mis-transcribed 16k figure: a
plausible number accepted without a sanity check against an independent measurement. The correct gate for a
composition claim is the **wall-clock budget check**, and it fails decisively.

## What IS solid, unchanged

- **The target forward pass is ~80% of the decode wall** (and all of prefill). This came from the direct
  phase timer (`phase: tgt_decode`) comparing against measured decode wall — an independent ratio check
  that *does* close. It does not depend on any of the broken instrumentation above.
- **Graphs are worth ~65 ms/token**: 35 t/s with graphs ON vs ~10 t/s with them off/absent. Clean A/B,
  reproduced three times today.
- Those two together: the production path is dispatch-free, and ~80% of its time is real GPU work in the
  target forward pass. **What is inside that 80% remains unmeasured on this stack.**

## Can it be measured at all?

Not with the means available here. The realistic options, in order:

1. **`rocprofv3` / `rocprofiler-sdk`** on a Linux ROCm install — the standard answer. The TheRock Windows
   SDK ships none of it, and our WSL path is clang-23/HIP-over-DXG where the same capture limitations
   apply. Would need a bare-metal Linux host.
2. **A debug build with per-op host timing around real (non-captured) execution** — i.e. measure in a
   graphs-off run and accept that it describes a different execution mode.
3. **Structured ablation instead of profiling**: disable/shrink one component at a time (PLE gathers,
   indexer, MTP block, attention) and observe the throughput delta. This attributes *cost* without needing
   per-op timers, and it works on the production build. **This is what I would do next** — it is the only
   route that measures the shipped configuration.

## State

- Production binary restored and **verified clean** (no `OP_TIMING` strings in the DLL), rebuilt from the
  pre-instrumentation source, 0 compile errors.
- `win-native` source is clean again.
- The full instrumentation + diagnosis is preserved as `results/op-timing-igtimer-diagnosed.patch`.

## Process notes worth keeping

Two build-hygiene failures cost most of the time here, both masked by my own checks:
- A build that **failed** (`error: expected unqualified-id`, from a brace slip in my restored patch) was
  reported as `rc=0` because I piped it through a redirect. The *stale artifact* then looked like a
  logic bug. Lesson: verify the artifact (string in the DLL, mtime), not the exit code of a redirected
  command.
- `cudaEventCreate` / `cudaEventElapsedTime` have **no `hip*` alias** in `vendors/hip.h` (unlike
  `cudaEventRecord` etc.), so code copied from the CUDA-symbol world fails to compile on the HIP build.
