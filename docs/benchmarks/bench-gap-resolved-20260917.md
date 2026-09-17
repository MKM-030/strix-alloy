# The llama-bench / server gap is harness-side, not the token stream (2026-09-17)

Review item 3 asked whether the ~15% difference between `llama-bench` and the served engine is real,
and item 2 proposed a specific cause: `llama-bench` feeds pseudorandom tokens via `std::rand() % n_vocab`,
which on the Windows CRT reaches only 13.2% of the vocabulary. **That cause is now tested and excluded.**
The gap is real, ~13%, and lives in the harness.

## Experiment

llama-bench offers no way to inject a token array, so the test was inverted: if the *server*, fed
llama-bench's own token distribution, reproduces llama-bench's number, the gap is the workload; if it does
not, the gap is the harness. One server session, `-b/-ub 16384`, 16,384-token prompts, 3 reps, warm medians
(`bench-gap-ab.ps1` + `bench-gap-tokens.py`):

| arm | median | min | max |
| --- | ---: | ---: | ---: |
| prose (real IDs — the workload our served numbers use) | **1021.1** | 1020.2 | 1021.9 |
| random-a (uniform pseudorandom, full vocab) | 1010.5 | 1001.0 | 1020.0 |
| random-b | 994.7 | 990.7 | 998.7 |
| random-c | 1013.8 | 1010.8 | 1016.9 |

**Random vs prose = −1.0%**, and the three independent random draws span only **1.9%**, so draw-to-draw
variance is small. Meanwhile:

| measurement | t/s | vs llama-bench |
| --- | ---: | ---: |
| `llama-bench` `pp16384` | 892.59 | — |
| server + random tokens | 1010.5 | **+13.2%** |
| server + prose tokens | 1021.1 | **+14.4%** |

**Conclusion: the token distribution does not explain the gap.** Feeding the server llama-bench's own
distribution still runs ~13% faster. What the `rand()` defect *does* mean stands separately and is narrower —
the two platforms are not measuring an identical workload, so a cross-platform comparison needs the token
workload published even though it does not change throughput by much here.

**Where the ~13% actually lives is not yet localized.** llama-bench's `test_prompt()` decodes in `n_batch`
chunks and calls `llama_synchronize()` after each, then reports the mean of `-r` timed runs with warmup runs
ahead of them; the server reports llama.cpp's internal `prompt_per_second`. Candidate explanations still
untested: what each timer includes (graph capture, first-call allocation, synchronisation boundaries), and
whether llama-bench's per-chunk synchronise costs more than the server's single-batch shape. Cheaper to
resolve by instrumenting than by arguing, and it is the next experiment rather than a claim.

## Practical consequence

Quote each harness with its own name and never mix them:

- **`llama-bench`** — synthetic token evaluation, the community-standard tool, ~892 t/s `pp16384`. Use it for
  cross-machine comparisons *with the caveat that the token stream differs by platform*.
- **`llama-server`** — served throughput, ~1021 t/s for the same shape. Use it for what users experience.
- The ~13% between them is **a harness difference, not evidence that either stack is faster.**

## Also verified in this pass: the patch series reconstructs the engine

`verify-patch-series.sh` applies `engine-patches/` to a clean worktree at the declared base
(`40a9f4d01b69314d0f75c9120abe8e199e49111d`) and compares the result with the built source tree:
**all 8 touched files match byte-for-byte** (`src/llama-lazy-reader.h`, `src/models/qwen4exp.cpp`,
`tools/server/server-context.cpp`, `ggml/src/ggml-cuda/mmid.cu`, `common/speculative.cpp`, `common/common.h`,
`common/arg.cpp`, `tools/hidden-dump/hidden-dump.cpp`), with a total delta of 581 insertions / 17 deletions
across 10 files.

**One trap worth recording:** `git apply --check` on the whole directory **fails** on
`tools/server/server-context.cpp`, because the patches are *stacked* — patch 0005 expects the file as patch
0004 leaves it. They apply correctly in order via `git am engine-patches/*.patch`, and that is the documented
method in `engine-provenance-20260916.md`. Do not "fix" this by reordering; apply with `git am`.
