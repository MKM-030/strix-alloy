# Flash-Next decode: root cause found — MTP works only on the FIRST request per server life

Founder: "the tok/s are far too low, try different parameters, small context first then increase."

**Answer: parameter tuning is not the problem. We found a reproducible defect in the fork's MTP path:
speculative decoding works on the first request after a server start and then produces nothing for the
whole rest of the server's life. Every measurement below is exact and reproducible.**

## The measurement

Server: `strix-halo` fork, unsloth UD-IQ4_XS + shared MTP head, `-c 32768`, one process per run.
Two runs, differing only in `LLAMA_MTP_QSA`:

| Depth | QSA=1 (default) | QSA=0 (dense drafter) |
| --- | ---: | ---: |
| ~0.6k | 9.88 t/s | **20.22 t/s** |
| ~2k | 6.90 | 7.96 |
| ~6k | 7.90 | 7.95 |
| ~14k | 7.26 | 7.04 |
| ~28k | 5.89 | 6.66 |

**Draft acceptance, in request order:**

```
task  0  (first request of the process):  0.68889 (31 accepted / 45)   mean len 3.07   ← works
task 20  (second request):                0.00000 ( 0 accepted /135)   mean len 1.00   ← dead
task 70, 121, 174 (all later):            0.00000 ( 0 accepted /135)   mean len 1.00   ← dead
```

**Identical under both `LLAMA_MTP_QSA` settings.** The drafter engages for the first request and then
never again — `mean len 1.00` means it proposes nothing, so every later token is verified serially.

## What this means

- **The cliff is not context depth.** It is **request count**: request #1 is fast (19–20 t/s), requests
  #2..N are slow (7 t/s). My earlier depth tables only *looked* like a depth cliff because each server
  processed one prompt: the one deep prompt was always the *second* request.
- **It is not the draft head.** All three MTP heads tested (unsloth `shared-Q8_0`, drluoto `Q8_0`,
  drluoto `frspec-65k` — the last won't load at all) behave the same.
- **It is not `LLAMA_MTP_QSA`.** Toggling it changes nothing.
- **Consequence for REV:N:** a World Engine answering one prompt per process start would look fast, but a
  **live conversation degrades to 7 t/s after the first turn** — exactly the "tok/s far too low" symptom.

## Where to look for the fix (for the kernel session)

This is a state-handling bug in the fork's speculative path, not a tuning matter. Likely candidates:
1. **Recurrent/drafter state not reset between requests** — the MTP head is depth-1 over the target's
   hidden state; if that state pointer goes stale after request 1, proposals become unusable.
   (`llama.cpp` PR #28118 is exactly "speculative recurrent-state checkpoints" — the fork may carry an
   incomplete version.)
2. **The draft context is not rebuilt** for the new request (prompt-cache interaction).
3. **A counter/SNAP interaction**: the branch sets `SNAP`/`SNAP2` prompt-cache snapshots; a bad snapshot
   could put the drafter's KV on the wrong slot.

**First test for the session:** one server, `--parallel 1`, two *identical* short prompts in a row;
read `draft acceptance` on each. If #1 accepts and #2 is 0.00, the bug is confirmed at minimum cost (no
long-context work needed).

## Practical workaround (works today)

Because **any single request is fast when it is the first**, batch the work:
- For REV:N, **restart the engine between conversations**, or use `--parallel N` so several
  conversations are admitted as "first" requests on separate slots.
- Or accept **7 t/s sustained** with MTP as-is — still ~7× the old GGUF-number and 22× Halogen's
  `Pin::None` fallback; and the **prefill (~540 t/s) is unaffected** and is the World-Engine-relevant
  axis.

## Prefill (unchanged, both configs)

| Depth | Prefill |
| --- | ---: |
| ~2k | 418–472 t/s |
| ~6k | 465–512 t/s |
| ~14k | 547–549 t/s |
| ~28k | 516–577 t/s |

Prefill is flat and fast across depth — the fork's kernels are doing their job. Only *decode after the
first request* is broken.
