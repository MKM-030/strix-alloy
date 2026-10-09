# Frozen 0.17.3 BN64 comparison windows

`window.py` is source-only preparation for root's sequential stock-before, candidate and stock-after engine cohort. Root owns server upgrade, launcher wrappers, engine lifecycle and every API/hardware run. This source scope performed no imports, tests, builds or API calls.

Frozen client SHA256: `8f3c6285546eaf848d8e3986ce9b079b07cff485ea59f6eea3e534999c81649c`. The request body and prompt are copied unchanged from `../hc6-registration-route-v1/window.py`: 8192 actual input tokens, 128 actual output tokens, temperature0, seed1, cache/thinking off and MTP drafter. Profile and manifest checks require backend0.17.3, MTP depth2, PLD3,3, prefill/max8192 and host reserve18 GiB. The exact profile and prompt hashes are recorded in `frozen-source.json`.

Each window sends four sequential requests: one excluded warmup followed by three measurements. `before` establishes the output SHA256, accepted/drafted counters and finish reason from its first response; every other before response must match. Only a complete, passed before summary supplies the baseline to candidate and after. Those windows require all four signatures to match and require the same frozen profile, prompt, request and client hashes. No historical 0.17.2 output or acceptance counter is imposed.

Candidate requires `manifest.bulk_bn64_candidate.enabled=true` and `environment.ALLOY_BULK_BN64_ENABLE=1`. Both stock windows require the candidate manifest field and every `ALLOY_BULK_BN64_` environment key to be absent. `_hg_flash_serve` must also be absent from stock windows.

Before requests, each window records fresh read-only League/Riot process identities and Windows GPU Engine utilization in `load-before.json`. Only process ID, name, creation time and GPU counter fields are collected; command lines and tokens are excluded. The synchronous query completes before the request loop and memory watcher. Empty, invalid-status, nonfinite or negative GPU observations fail the window; League/Riot processes or observed GPU utilization above1 percent stop before any request so root can assess the observation. The snapshot establishes premeasurement conditions only.

Physical free memory and commit headroom must both be at least22 GiB on entry and again after the load snapshot. Both must remain at least18 GiB for each request; the request watcher records minima every0.2 seconds. Health must be idle before each request and after the window; exactly four additional completions and no additional cancellations are required.

Root-owned invocation, from the project directory with the corresponding already-ready engine:

```powershell
server\.local\venv\Scripts\python.exe -B server\.local\optimization9h-20261004\halogen0172-backend-preparation-20261008\bulk-bn64-engine-comparison-v1\window.py before
# Root then changes to the qualified candidate lifecycle.
server\.local\venv\Scripts\python.exe -B server\.local\optimization9h-20261004\halogen0172-backend-preparation-20261008\bulk-bn64-engine-comparison-v1\window.py candidate
# Root then returns to the stock lifecycle.
server\.local\venv\Scripts\python.exe -B server\.local\optimization9h-20261004\halogen0172-backend-preparation-20261008\bulk-bn64-engine-comparison-v1\window.py after
```

Each output directory must be new. Per-window identity, health, response, memory, clock, sample and summary receipts are written locally. Console output contains selected rates/accounting and token-free summaries. This source is frozen for root's use; real adapter activation, output equality and net engine rate remain runtime evidence to collect.
