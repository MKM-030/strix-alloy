# Halogen update check — 5 October 2026, 13:02 UTC

The checked official channels remain unchanged from the
[11:02 checkpoint](halogen-update-checkpoint-20261005-1100.md). No concrete
new Halogen throughput or NPU candidate was established. No benchmark,
restart, installation or engine setting change was made.

Halogen `main` and `v0.16.2` remain
[`7f31bbd4021f217a1be9776bdb7304bcf8eca62d`](https://github.com/peonist-ai/halogen-flash-server/commit/7f31bbd4021f217a1be9776bdb7304bcf8eca62d),
with the same annotated tag. The release collection and commit query since
11:02:46 UTC are empty. The identical committed tree preserves FLAGS/NPU
documentation; unchanged deep audits were not repeated.

The [395 graphics channel](https://www.amd.com/en/support/downloads/drivers.html/processors/ryzen/ryzen-ai-max-series/amd-ryzen-ai-max-plus-395.html)
still lists 26.9.2 Optional and 26.8.1 Recommended.
[Ryzen AI releases](https://github.com/amd/RyzenAI-SW/releases) remain at 1.8.0;
the [separate production NPU driver](https://ryzenai.docs.amd.com/en/latest/inst.html)
is 32.0.203.376. [Windows ML](https://github.com/microsoft/WindowsML/wiki/Windows-ML-Execution-Provider-Releases)
retains current VitisAI 1.8.75.0 / EP1605 and MIGraphX 1.8.64.0, with
1.8.80.0 / 1.8.65.0 upcoming. A `1.8.1` wheel-index path in
[older July 23 OGA documentation](https://ryzenai.docs.amd.com/projects/WinML/en/stable/hybrid_oga.html)
does not establish a new full-stack release or supported fabric contract;
the package index was not inspected.

The inspected Rulith and GSQHalo repositories/branches have no commits after
11:02:46 UTC. [Rulith 0.4.5](https://github.com/rulith-dev/rulith-inference/releases/tag/v0.4.5)
remains its latest release; GSQHalo's release collection is empty.
A fresh [StrixHalo discussion](https://www.reddit.com/r/StrixHalo/comments/1wy7ffo/doom_for_unified_memory_pc/)
at 12:36 UTC supplied no implementation or reproduced Halogen result. Public
Reddit listing freshness remains incomplete. Older SSD and profiling
hypotheses were not re-audited or counted as new improvements.

The same controller 29004, backend 11988, run IDs and running container were
verified. Both health endpoints remained ready/idle, with completed9/cancelled0.
The final runtime receipt at 13:06:47 UTC records 23.26 GiB physical reserve
and 115.74 GiB commit headroom. The engine stays ready and open; no measurement
handle is active and NPU integration remains off. The full goal stays blocked
because hidden-projection accuracy and useful NPU engine integration remain
unqualified.

The [qualified natural-long cohorts](../benchmarks/halogen0162-natural-long-20261005.md)
were not repeated. Numerical status is next due at 13:56:21 UTC. The next
official check is due at 15:02:58 UTC, two hours after this check began.

[Structured observations and raw-receipt hashes](halogen-update-checkpoint-20261005-1300.json).
