# In-graph op timer: root-caused, fixed where fixable, and declared unusable here (2026-09-15)

## Outcome

**The in-graph (`_IG`) per-op timer cannot work on this ROCm-over-DXG build.** That is now *proven*, not
assumed, and the timer has been changed to say so loudly instead of silently reporting zero.

## The three findings, in the order I proved them

### 1. The op filter was case-sensitive (a real bug — fixed)

First diagnostic, after the case-fix attempt, showed the recording hook was **never called**:

```
OP_TIMING_IG DIAG: record_calls=0 collect_calls=3 segs=0
```

Cause: `op_selected()` compared `ggml_op_name(node->op)` — which returns **UPPERCASE** (`"MUL_MAT_ID"`)
— against lowercase filter tokens (`"mul_mat_id"`) using a case-sensitive `std::string::find`. Nothing
ever matched. Fixed by lowercasing both sides.

**Result:** `record_calls=96, cap_nodes=3490, matches=96` — recording now works. This fix is correct and
should be kept for anyone using the timer on a platform where the query works.

### 2. Not an event-lifetime problem (hypothesis tested and falsified)

With recording fixed, the query still failed:

```
seg: op=MUL_MAT_ID  a=… b=…  err=400 (invalid resource handle)  ms=0.0000
```

`hipErrorInvalidResourceHandle` on events recorded inside a capture. My hypothesis was that events created
*while capture is active* never become valid queryable handles, so I moved them to a **pool created outside
the capture region** (`begin_capture_hook()` runs before `cudaStreamBeginCapture`).

**Result: identical `err=400`.** The event-lifetime hypothesis is **falsified**. Pooled, pre-capture events
fail exactly the same way.

### 3. Conclusion: captured events have no queryable timing state after replay

Across both event strategies, `hipEventElapsedTime()` returns 400 for every captured event. Combined with
finding 1 (recording demonstrably happens — 96 records across 3490 nodes), the only consistent explanation
is that **event records which become graph nodes do not maintain timing state that can be queried after a
replay on this ROCm/DXG stack.**

This is a genuine platform limitation, not a bug in the patch. It should be treated like
"no PM4 replay on Windows": a capability this stack does not expose.

## What was changed

- `op_selected()` now matches case-insensitively (**keep** — correct regardless of platform).
- Events are allocated from a pre-capture pool (**keep** — correct, even though it did not fix the query).
- `collect()` now prints **one loud line** when every query fails:
  > `OP_TIMING_IG: hipEventElapsedTime() failed for all N captured events (hipErrorInvalidResourceHandle). In-graph event timing is NOT supported on this ROCm/DXG build. For per-op shares use LLAMA_OP_TIMING=1 with GGML_CUDA_DISABLE_GRAPHS=1.`
  
  and suppresses the misleading `tracked total 0.0 ms/replay` spam that previously read like a valid
  measurement. **This is the most important change** — the failure mode I actually hit was a silent zero
  that I almost reported.

## State of the tree

- `win-native` is **clean** (0 op-timing refs); the production binary is rebuilt from it.
- The whole diagnosed patch is preserved as
  `kernel-work/results/op-timing-igtimer-diagnosed.patch` (13 204 bytes) and in
  `git stash@{0}` ("op-timing in-graph (broken on DXG; diagnosed)").
- Nothing about the failure is lost, and nothing broken is on the main branch.

## Where this leaves per-op composition

The **only** working path on this box is the aggregate timer in its documented configuration:

```powershell
LLAMA_OP_TIMING=1  GGML_CUDA_DISABLE_GRAPHS=1     # graphs OFF is REQUIRED by that path
```

Validated earlier (32 summaries, 0 zero-rows, 0 errors) and it gave MUL_MAT 56.1% / SCALE 11.5% /
RMS_NORM 10.2% / GET_ROWS 8.8% / CONT 6.1% / CPY 4.4%.

**But that runs with graphs disabled, and graphs are worth ~65 ms/token** (35 t/s with them, 10.7 t/s
without). So those shares describe a mode we do not ship, and I will not present them as decode
composition. The honest position stands: **the target forward pass is ~80% of decode and all of prefill
(solid, from the phase timer), but what is inside that 80% is not reliably measured.**

## Lesson

The failure I hit was not "the tool didn't work" — it was **a tool that reported a plausible number while
measuring nothing**. Three of my attempts produced output I would have believed. The guard that catches
this class: *validate the instrument before reading it* — non-zero totals, no error returns, and the
correct configuration for the code path. That is now written into the script (`op-timing-correct.ps1`
prints `RUN VALID` / `RUN INVALID`).
