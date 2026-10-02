# PROJFIX scheduler reservation candidate — 2 October 2026

The pinned `pwilkin` Windows source re-reserves the scheduler when a request
attaches or clears its backend sampler. Rulith's [reservation-reuse patch](https://github.com/rulith-dev/rulith-inference/tree/7f04d24185cb2438ea444ea3f9c0d88852dfb0db)
suggests retaining the reservation for a later chain of the same sampler names.
This is a source-only candidate, **not** a measured improvement on PROJFIX.

`backends/projfix-windows/patches/scheduler-reserve-optin.patch` applies to the
retained `pwilkin-release-20260929` source. Unlike the upstream patch, its
`LLAMA_SAMPLER_KEEP_RESERVE` switch is **off when unset** and accepts only `1`;
reuse is further restricted to one-sequence contexts. It leaves graph rebuilding
in place, retains signatures after a normal clear, and invalidates them on a
rejected backend sampler or a different chain. With the flag unset, the original
reservation decisions remain. The patch is reversible with `git apply --reverse`.
No profile sets this flag and no running binary was changed.

The patch has SHA-256 `7dd8c55ebfb85efa717b8edfedadc116781c8348b73639e2841c53f8aaa60c06`.
`test_scheduler_reserve_patch.py` applied/reversed both files byte-for-byte
against the pinned source. A separate patched copy under
`server/.local/projfix-scheduler-source-final-20261002/` passed the pinned
TheRock clang/PCH `llama-context.cpp` syntax command (`exit=0`); the compiler,
patch and patched-source hashes are retained in `syntax.log`. This did **not**
link an engine or test an inference graph.

Before use, build an isolated binary with this one patch, run sampler-chain and
multi-turn graph-reservation tests at `--parallel 1`, then compare output hashes,
top-N probabilities (or full logits if actually exposed), memory floor and wall
TTFT against a control. Test different sampler chains and a context with more
than one sequence to verify the fallback. Only after the broad quality and
Reddit workload gates may an explicit isolated profile set the environment flag;
the production executable hashes and registered defaults remain unchanged.
