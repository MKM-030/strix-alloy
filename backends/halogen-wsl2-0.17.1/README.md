# Halogen 0.17.1 for WSL2

This canonical package is installed from the pinned Halogen 0.17.1 image at
upstream revision `9196bc6e7b20`. The adapted entrypoint, engine, three compatibility
adapters, HIP probe, HIP headers and stock rocRoller identities are complete.
The local installation manifest records version `0.17.1` and `completed: true`.
See the [installation review](../../server/.local/optimization9h-20261004/halogen0171-backend-preparation-20261007/final-source-install-review.md)
and [release pins](profiles/release.json).

Runtime and performance qualification remain pending. Installation and source
checks do not establish model-load compatibility, throughput, acceptance or
memory stability. The preserved private preparation notes and seals describe
their earlier preparation state; they are historical evidence.

The current singleton comparison uses the v2 checkpoint, 262144 context/KV
positions, one slot, prefill chunk and arena 8192, MTP2, PLD `3,3`, Cache Off and
Thinking Off. Its managed profile disables console tracing. The mechanism under
evaluation is upstream single-stream learned n-gram row read-ahead. NPU text
offload and two-stream MTP remain disabled.

The human-authorized v2 startup floor is **35 GiB physical availability and
131 GiB commit headroom** at 262144 context. Runtime physical and commit floors
remain **18/18 GiB**. The [35 GiB binding receipt](../../server/.local/optimization9h-20261004/halogen0171-backend-preparation-20261007/authorized35-source-binding.json)
supersedes the historical 40 GiB comparison contract. Admission floors are
protection thresholds; they do not reserve memory or establish sufficiency at
exactly 35 GiB. The w4b budget remains separate in
[memory_budget.py](scripts/memory_budget.py).

Use the normal managed singleton lifecycle for runtime work. From the repository
root, the backend launcher accepts:

```powershell
.\backends\halogen-wsl2-0.17.1\Start.ps1 -Checkpoint v2 -ContextSize 262144
```

The frozen three-window comparison is recorded in
[the Current8K report](../../docs/benchmarks/halogen0171-current8k-20261007.md):
0.16.2 before, 0.17.1, then 0.16.2 after. Only the first baseline is complete in
the report skeleton. Candidate results and restoration of the original ready/open
server remain pending. No local 0.17.1 speed or acceptance gain is claimed yet.
