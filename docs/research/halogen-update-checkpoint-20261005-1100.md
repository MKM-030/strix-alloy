# Halogen update check — 5 October 2026, 11:02 UTC

Halogen and the official GPU/NPU channels remain unchanged from the
[08:59 checkpoint](halogen-update-checkpoint-20261005-0859.md). No newly useful
candidate was established for the frozen Halogen native-HGN prose workload.
No benchmark, restart, installation or engine setting change was made.

Halogen `main` and `v0.16.2` still resolve to
[`7f31bbd4021f217a1be9776bdb7304bcf8eca62d`](https://github.com/peonist-ai/halogen-flash-server/commit/7f31bbd4021f217a1be9776bdb7304bcf8eca62d).
The annotated tag remains `71b5339a1dc74c26dc0952989e64aee4b06a6546`, and the
release collection and default-branch commit query since the prior check are
empty. The identical committed tree preserves the FLAGS/NPU documentation;
no deep audit of unchanged files was repeated.

The [395 driver channel](https://www.amd.com/en/support/downloads/drivers.html/processors/ryzen/ryzen-ai-max-series/amd-ryzen-ai-max-plus-395.html)
still lists 26.9.2 Optional and 26.8.1 Recommended.
[Ryzen AI](https://github.com/amd/RyzenAI-SW/releases) remains 1.8.0, with
[separate production NPU driver](https://ryzenai.docs.amd.com/en/latest/inst.html)
32.0.203.376. [Windows ML](https://github.com/microsoft/WindowsML/wiki/Windows-ML-Execution-Provider-Releases)
still lists VitisAI 1.8.75.0 / EP1605 and MIGraphX 1.8.64.0 as current;
1.8.80.0 and 1.8.65.0 remain upcoming. No new relevant precision/overlap fix or
supported Windows FP11/395 fabric hold/readback contract was established.

Two real upstream Rulith changes appeared after the prior check:

- [0.4.4](https://github.com/rulith-dev/rulith-inference/releases/tag/v0.4.4),
  published 09:18:09 UTC, fixes a residual-buffer dependency exposed by
  perplexity batches requesting hundreds of head output rows. The
  [primary fix](https://github.com/rulith-dev/rulith-inference/blob/cd52dd5e81a37309f1db0ad9c96f00f77772b2e8/patches/apply_xres_fix_044.py)
  retains the residual through later graph readers/output. The author reports
  ordinary chat/completion behavior and prefill speed unchanged. This is a
  correctness change in a different runtime, with no demonstrated gain for
  the current Halogen workload.
- [0.4.5](https://github.com/rulith-dev/rulith-inference/releases/tag/v0.4.5),
  published 10:26:41 UTC, changes API model naming. It supplies no throughput
  or NPU candidate.

New [Rulith profiling notes](https://github.com/rulith-dev/rulith-inference/blob/cd52dd5e81a37309f1db0ad9c96f00f77772b2e8/docs/results/prefill-gap-20261005.json)
describe untried LDS double buffering and an unexplained graph normalization
gap. These remain research hypotheses, without a reproduced portable cure.
The prior SSD wake/pregather portability audit was not repeated. The inspected
GSQHalo branch has no new commits and its release collection remains empty.

Reddit coverage remains incomplete because several public listings were
stale. A new harness leaderboard discussion supplied no reproducible Halogen
optimization. The user's own older post was excluded from independent
validation. This check does not establish the absence of every newer post.

Controller 29004 and backend 11988 preserve their original creation times,
run IDs and running container. Both health endpoints remained ready/idle
with completed8/cancelled0. The final runtime receipt at 11:09:38 UTC records
25.23 GiB physical reserve and 118.05 GiB commit headroom. No active measurement
handle was found; stale terminal IDs were verified absent. The engine remains
ready and open, with NPU off. Full hidden-projection accuracy and useful NPU
engine integration remain unqualified, so the existing blocked goal is kept.

The [completed natural-long results](../benchmarks/halogen0162-natural-long-20261005.md)
were not repeated. The numerical status remains due at 11:56:21 UTC. The next
official check is due at 13:02:46 UTC, two hours after this check began.

[Structured source receipts and runtime evidence](halogen-update-checkpoint-20261005-1100.json).
