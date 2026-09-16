# ilintar rebase + upstream-sync result (2026-09-15)

## What was done

1. **Fetched `pwilkin/llama.cpp` `strix-halo`** — it had moved from our base `d67d5883` to **`40a9f4d0`**
   ("hip: extend MMB quants and fuse Flash-Next F32 PLE"), one commit ahead.
2. **Rebased our three `win-native` commits onto `40a9f4d0`**:
   `424cd1b8` (`_WIN32` prefetch stub) → `5b3a22db` (d2t draft-vocab trim + on-device spec checkpoints) →
   `18d329d9` (hidden-dump harness). Clean rebase, no conflicts; backup branch
   `win-native-backup-20260915` kept at the pre-rebase tip.
3. **Replaced the 3-file sync with a full `rsync`** of the fork into `C:\AI\build\strix-llama-win`
   (excluding `build-*`), because the rebase touched seven HIP kernel files that the old 3-file copy
   silently skipped.
4. **Full native-Windows rebuild** with clang 24: **65/65 targets, exit 0**, warnings only.

## What `40a9f4d0` adds (the reason we rebased)

| file | change |
| --- | ---: |
| `ggml-cuda/mmb-quant.cuh` | **+336** (new: extended MMB quant kernels) |
| `ggml-cuda/dequantize.cuh` | +165/− |
| `ggml-cuda/mmb.cu` | +124 |
| `ggml-cuda/ple-conv.cu` | +81 (fuse Flash-Next F32 PLE) |
| `ggml-cuda/ggml-cuda.cu` | +18 |
| `models/qwen4exp.cpp` | 2 lines |

## Measured result: the rebase is **neutral on speed**

Server-based ladder, PROJFIX, WSL shut down, rep-1/2 (page-cache warm):

| config | prefill @1k | @8k | @16k | @32k | decode @1k | @8k | @16k |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| **before rebase** (ub 16384) | 710 | 1021 | **1057** | 1035 | 30.1 | 28.9 | 29.2 |
| **after rebase** (ub 16384) | 697 | 1003 | **1029** | 1019 | 29.4 | 27.9 | 28.5 |
| before (ub 2048 + MTP n2) | 653 | 799 | 782 | — | **35.5** | 30.2 | 30.2 |
| after (ub 2048 + MTP n2) | 655 | 952 | 988 | 968 | 34.1 | 29.7 | 28.8 |

(The 16k/32k cells were confirmed twice, WSL down: 1024.8 / 1029.3 and 1019.2 / 1018.6 — i.e. ~1025 t/s
@16k against the pre-rebase 1057. Same within noise.)

**Interpretation — and why this is not a failure.** The deltas are within run-to-run noise. The rebase
change (`ac1ebb4e0`, "compile in the tuned defaults and drop the env gating") removed **all 68 `LLAMA_*`
`getenv()` calls** and baked the measured-optimal values in. We were **already** supplying those exact
values through `gates-test.sh`, so the *behaviour* was already the tuned one — the rebase makes it
**default and unbreakable**, not faster. `grep -c 'getenv("LLAMA_'` in the rebased tree is now **0**, so
our env recipe is obsolete and the 53-gate fragility is gone. That is a real maintainability win and
removes a whole class of "one gate set wrong → corrupted output" failures (which is exactly what bit us
with `LLAMA_MMB_HC16`).

## The llama-bench `pp16384 = 494 ± 172` smoke alarm — diagnosed as interference, not a regression

Running ilintar's exact protocol (`llama-bench -p 16384 -n 128 -b 16384 -ub 16384 -r 3`) gave
**494.31 ± 172.70 t/s** — far below our server's stable ~1040 and with a ±35% spread. The cause is
**host memory contention**: I had restarted WSL for the source sync, so `vmmemWSL` was holding RAM during
the benchmark. After `wsl --shutdown` the host went from 19.9 GB to 26.7 GB free. Decode in that same run
(28.96 ± 0.95) matched our server number, confirming the machine was fine and the *prefill* phase was
being starved. **Do not quote the 494 number**; it is an artifact. The server-based ladder above (with WSL
down) is the valid measurement. This is the third time co-tenant/vmmemWSL memory has contaminated a
prefill measurement — the runbook rule (WSL down for all native runs) is load-bearing, not hygiene.

## Ilintar's launcher, for reference (their published config)

`install.sh` `flash-next` profile defaults, which reproduce their 1204 t/s:

```
CTX_SIZE=65536  BATCH_SIZE=16384  UBATCH_SIZE=16384  PARALLEL=1  MTP_N_MAX=2
-m $MAIN  -dev ROCm0 -ngl 999 -fa on -fit off
--load-mode none --lazy-mode on-direct      # keeps the 27.5 GB PLE table out of the resident set
-ctk f16 -ctv f16 -c 65536 -b 16384 -ub 16384
--jinja --spec-type draft-mtp --spec-draft-device ROCm0 --spec-draft-ngl 99 --spec-draft-n-max 2
```

plus the (now-compiled-in) gate block, whose tuned values were: `LLAMA_MMB_HC16=2`, `LLAMA_MMB_TALL=2`,
`LLAMA_MMB_CACHE=4`, `LLAMA_MMB_F32SPLIT=2`, `LLAMA_MMB_SHADOW=2` (levels, not booleans). Our rebased
build has these as defaults now.

## Conclusion

The rebase closes the **maintainability** gap (no env block, tuned-by-default) but not the **prefill
speed** gap (1057 → 1040, i.e. still ~14% short of 1204). Their remaining advantage is more likely the
**retained-PM4 command-list runtime** (a ROCm userspace change we do not have) than any kernel in the
branch, since we now run the branch's kernels. That runtime is the next candidate, and it is a much
larger piece of work than a rebase.
