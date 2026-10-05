# Halogen 0.16.2 on Windows / WSL2

Version-pinned experimental Strix Alloy adaptation for the 128 GiB Strix Halo
Windows host. This upgrade uses the official 0.16.2 image and the existing,
checksum-verified v2 checkpoint through the reviewed WSL compatibility adapters.
The baseline is one slot, prompt cache Off and an 18 GiB Windows physical/commit
reserve. Source tests and readiness checks do not establish benchmark performance,
model quality or long-context equivalence. Record new live results in the
[0.16.2 upgrade report](../../docs/benchmarks/halogen0162-upgrade-20261003.md).
The 0.15.1 package is retained for separately verified rollback. The 0.16.1
package is an unqualified archive and is not a rollback backend.

## Start and connect

From the repository root in PowerShell 7, after explicit installation:

```powershell
.\backends\halogen-wsl2-0.16.2\Start.ps1 -Checkpoint v2 -ContextSize 262144
```

Run only one at a time. Direct-backend defaults remain w4b, 129024 context positions,
one slot, cache Off and continuous serving (`-ServeSeconds 0`). Use `-PromptCache Exact`
or `Flexible` only for a separately characterized warm-cache workload, never to inflate
cold-prefill results. Context accepts 4096..262144; prompt plus output must fit it.
`-StartupTimeoutSeconds` is separate from serving duration and defaults to 900 seconds.

Local API base: `http://127.0.0.1:8731/v1`. Model: `halogen-qwen3.8-flash-next`.
The persistent bearer token is in this package's ignored `.local/api-token.txt`.
Standalone launch prints the key after READY; managed launch suppresses that echo.

For a stable engine-independent endpoint and owned start/stop use
[server/Start.ps1](../../server/README.md), whose gateway listens on port 8840.
Do not start that controller while a standalone backend occupies port 8731.

## Model files and storage

Keep the model directory on native WSL Ext4, not a Windows-mounted filesystem.
Select the checkpoint explicitly during installation. The v2 core also needs a
matching n-gram table and tokenizer; the core alone is incomplete. The existing
w4b file can supply its embedded lookup-table payload through `-NgramSource`.
**Retain that file while it is the configured n-gram source.** The w4b serving path
additionally needs its matching overlay. Changing table sources requires separate
integrity and live validation; no table is downloaded or converted at startup.

Additional v2 core: `qwen38-flash-next-v2.hgn`, 66,687,678,432 bytes, SHA-256:
`71246c6ab3fc1de2cf06326f18e275fe9c2a18366d646ed3357d194c884fc687`.
Obtain it from the official `peonist-ai/halogen-qwen3.8-flash-next` repository,
revision `5a84e807efc2d987764a348530e5036d933e30e2`. For example, inside WSL
with Hugging Face CLI already installed and the directory changed to your model store:

```sh
hf download peonist-ai/halogen-qwen3.8-flash-next qwen38-flash-next-v2.hgn \
  --revision 5a84e807efc2d987764a348530e5036d933e30e2 --local-dir .
```

The v2 launcher verifies both the core and the selected n-gram source before GPU
allocation. It validates the full checksum on first use or changed file identity.
The verifier uses bounded reads and releases consumed file-cache ranges. It caches
only a receipt bound to size, device/inode and nanosecond modification/change times;
the n-gram receipt also binds the configured or default source path. A same-size
partial file is not accepted merely because its length looks correct.
No model download, quantization or conversion occurs automatically at server startup.

## Installation

Prerequisites: PowerShell 7, Windows Python 3.12+, reviewed 64 GiB graphics carve,
Ubuntu 24.04 WSL2 with a 56GB ceiling, working DXG, GCC 13.3, OpenSSL headers and
Docker Engine accessible to the selected Linux user. This installer does not change
BIOS, drivers, WSL settings or Windows memory policy. The legacy
[host guide](../halogen-wsl2/docs/setup.md) describes prerequisites, not this image version.

Pull the exact official image in WSL:

```sh
docker pull ghcr.io/peonist-ai/halogen-flash-server@sha256:0c61bf84ac22308a53f5d1ca6b86806702d7039e5ebc51cae4c66621b92fe04a
```

Then install using your actual native model store and qualified DXG library:

```powershell
.\backends\halogen-wsl2-0.16.2\Install.ps1 -Install -Distribution Ubuntu-24.04 `
  -Checkpoint v2 -ModelDirectory /srv/models/flash-next `
  -NgramSource /srv/models/flash-next/qwen38-flash-next-w4b.hgn `
  -DxgLibrary /opt/rocm/lib/librocdxg.so.1
```

`-LinuxUser` chooses the WSL account; `-AmdWheel` can replace `-DxgLibrary` with
the reviewed AMD wheel. Setup extracts dependencies from a stopped temporary
container, builds the compatibility adapters, and checks pinned hashes. The
0.16.2 package also pins a rocRoller compatibility library extracted from the
separate official image recorded in `profiles/release.json`; it is mounted only
for this adapted WSL runtime. These adapters make this an experimental Windows
baseline, rather than an unmodified native Linux run.
A running server is not required. Generated binaries, dependencies and machine
configuration stay under `.local/` and are not distributed in this repository.

## Memory policy and diagnostics

The service checks both Windows physical availability and commit headroom and
stops when either crosses its 18 GiB runtime threshold. Launch admission uses
the separate checkpoint/context budgets in `scripts/memory_budget.py`; the
controller reports the required and observed values when admission fails.
Context KV growth is not charged to the Windows physical pool a second time.
These are polled protection thresholds, not allocator reservations or guarantees
against instantaneous outside allocations. Each live run retains the observed
RAM readings and independent guard outcome.

```powershell
.\backends\halogen-wsl2-0.16.2\Start.ps1 -Status
.\backends\halogen-wsl2-0.16.2\Start.ps1 -Logs
.\backends\halogen-wsl2-0.16.2\Start.ps1 -Stop
```

Keep the serving terminal open. Logs are under `.local/services/<run-id>/`:
`service.log`, `engine.log`, `host-guard.jsonl`, and bootstrap diagnostics in
`guard-process.log`/`guard-failure.json` when relevant. Unresolved state is retained.
Legacy Trace4k/Single4k/Serve4k remain bounded diagnostics; do not expose them publicly.

[0.16.2 upgrade evidence](../../docs/benchmarks/halogen0162-upgrade-20261003.md)
records the new runtime identity, live lifecycle checks and measurements as they
are completed. The [0.15.1 checkpoint comparison](../../docs/benchmarks/halogen0151-v2-262k-20260930.md)
is historical evidence for that earlier engine. [Benchmark scripts](../../scripts/benchmarks/README.md)
provide reproduction commands; all cross-version performance claims require new
matched inputs and measurements.

## Opt-in shallow MTP through Strix Alloy

The managed controller can now forward a validated draft depth of 1, 2 or 3.
The backend's optional `-DraftTokens` becomes `--draft-tokens` in the service and
`HALOGEN_MTP_DEPTH` in the recorded container manifest. Without this option,
existing environment defaults remain unchanged. Legacy 4K qualification modes
refuse the option. No allocator, checkpoint or kernel is replaced.

Create a separate managed profile from an existing generated Halogen profile:

```powershell
$Py = '.\server\.local\venv\Scripts\python.exe'
& $Py .\server\draft_profiles.py `
  --source .\server\.local\halogen-v2-262144-Off.json --draft-tokens 1 `
  --output .\server\.local\halogen-mtp-shallow-262k.json
# After a normal managed stop and confirmed STOPPED:
& $Py .\server\controller.py run `
  --config .\server\.local\halogen-mtp-shallow-262k.json --port 8840
```

The candidate requests at least 18 GiB physical/commit headroom from the managed
controller, in addition to the backend's independent guard.
The client may still request serial decoding; this option only sets the greedy
MTP draft depth. It is not NPU offload or PROJFIX's tensor-placement selector.
See [measurements and scope](../../docs/research/halogen-gufo-mtp-20261001.md).

`draft_profiles.py --prefill-chunk` accepts 2048, 4096, 8192, 16384 or 32768,
bounded by the declared context. `--prefill-keep-trunk` is a v2-only opt-in;
`--admit-ticks` accepts 1..1024. These controls are recorded in the container
manifest and do not select a new default. Create separate managed profiles and
run them sequentially against the cache-Off baseline with matched PP/TG inputs
and quality checks. Earlier 0.15.1 PP8192 drift is historical evidence, not a
0.16.2 result. Exposed top-N logprob comparisons remain a proxy for full-logit
equivalence. Linux NPU support is unavailable through this WSL adaptation.

Explicit experimental chunk profiles retain the stock 32768-position token
arena, recorded as `HALOGEN_MAX_TOK=32768`, while changing the prefill chunk.
The stock profile leaves these controls at the image's compute defaults.
Holding the arena constant separates chunk-size effects from arena-size effects;
it does not change context capacity or the actual prompt length.

To opt into a smaller arena, set `engine.max_prefill_tokens` in a separate
managed profile. The 0.16.2 launcher exposes `-MaxPrefillTokens`, forwarded as
`--max-prefill-tokens` and recorded as `HALOGEN_MAX_TOK`. It accepts 2048, 4096,
8192, 16384 or 32768, requires an explicit prefill chunk no larger than that
limit, and cannot exceed the declared context. For example,
`engine.prefill_chunk=8192` with `engine.max_prefill_tokens=8192` records both
native limits as 8192 while retaining a 262144-position context and KV pool.
This startup setting sizes the per-token scratch arena, not the total input
capacity; changing it requires a normal managed stop and fresh launch.
Admission budgets and the 18 GiB runtime reserve remain in force. A lower arena
allocation or improved long-input rate must be qualified in a new measured
cohort before claiming a benefit.

## Internal numeric experiment controls

Managed profiles may include `engine.kernel_controls`, created with
`draft_profiles.py --kernel-controls-json`. The allowlist in
[`scripts/kernel_controls.py`](scripts/kernel_controls.py) covers selected
DeltaNet, attention, MoE and cache controls. Values are explicit integers;
unknown names and duplicate JSON keys are refused. Interface limits are local
experiment budgets, not upstream support or numerical-equivalence guarantees.
The launcher records the requested values in the container manifest. Compare
one variable at a time with the same weights, chunk/arena, cache policy and memory
reserve, then apply the output and functional gates in the
[upgrade report](../../docs/benchmarks/halogen0162-upgrade-20261003.md).
