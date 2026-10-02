# Halogen 0.15.1 on Windows / WSL2

Version-pinned experimental Strix Alloy adaptation for the 128 GiB Strix Halo
Windows host. Both w4b + overlay and the new checksum-verified v2 checkpoint have
completed 262144-capacity PP512/PP2048 and decode tests. This is not an upstream
claim of WSL support, a full model-quality evaluation, or certification of every
long-context workload. The complete 0.15.0 and 0.14.2 packages remain for rollback.

## Start and connect

From the repository root in PowerShell 7, after explicit installation:

```powershell
.\backends\halogen-wsl2-0.15.1\Start.ps1 -Checkpoint v2 -ContextSize 262144
.\backends\halogen-wsl2-0.15.1\Start.ps1 -Checkpoint w4b -ContextSize 262144
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
This adaptation currently needs the existing w4b checkpoint and matching overlay
for installation. Its v2 mode reuses the verified lookup-table payload inside the
w4b file. **Do not delete w4b after downloading v2.** A v2-only directory containing
the upstream standalone n-gram file is not yet a qualified installation path here.

Additional v2 core: `qwen38-flash-next-v2.hgn`, 66,687,678,432 bytes, SHA-256:
`71246c6ab3fc1de2cf06326f18e275fe9c2a18366d646ed3357d194c884fc687`.
Obtain it from the official `peonist-ai/halogen-qwen3.8-flash-next` repository,
revision `5a84e807efc2d987764a348530e5036d933e30e2`. For example, inside WSL
with Hugging Face CLI already installed and the directory changed to your model store:

```sh
hf download peonist-ai/halogen-qwen3.8-flash-next qwen38-flash-next-v2.hgn \
  --revision 5a84e807efc2d987764a348530e5036d933e30e2 --local-dir .
```

The launcher validates the full checksum on first use or changed file identity.
The verifier uses bounded reads and releases consumed file-cache ranges. It caches
only a receipt bound to size, device/inode and nanosecond modification/change times;
a same-size partial file is not accepted merely because its length looks correct.
No model download, quantization or conversion occurs automatically at server startup.

## Installation

Prerequisites: PowerShell 7, Windows Python 3.12+, reviewed 64 GiB graphics carve,
Ubuntu 24.04 WSL2 with a 56GB ceiling, working DXG, GCC 13.3, OpenSSL headers and
Docker Engine accessible to the selected Linux user. This installer does not change
BIOS, drivers, WSL settings or Windows memory policy. The legacy
[host guide](../halogen-wsl2/docs/setup.md) describes prerequisites, not this image version.

Pull the exact official image in WSL:

```sh
docker pull ghcr.io/peonist-ai/halogen-flash-server@sha256:414872efd58af104dd5619a4da1a1d428bb5920d342e556a233d79c7f435900c
```

Then install using your actual native model store and qualified DXG library:

```powershell
.\backends\halogen-wsl2-0.15.1\Install.ps1 -Install -Distribution Ubuntu-24.04 `
  -ModelDirectory /srv/models/flash-next -DxgLibrary /opt/rocm/lib/librocdxg.so.1
```

`-LinuxUser` chooses the WSL account; `-AmdWheel` can replace `-DxgLibrary` with
the reviewed AMD wheel. Setup extracts dependencies from a stopped temporary
container, builds the original compatibility adapters, and checks pinned hashes.
A running server is not required. Generated binaries, dependencies and machine
configuration stay under `.local/` and are not distributed in this repository.

## Memory policy and diagnostics

The reviewed Windows physical-memory admission floor is now 46 GiB for w4b and
36 GiB for v2. The 12 GiB physical/commit runtime reserve remains unchanged. Context
KV growth is not charged to the Windows physical pool a second time; total-commit
headroom remains separately checked (125 GiB at 262144 positions). These are launch
admission budgets, not claims about total model memory consumption or a guarantee
that arbitrary simultaneous games/inference loads are safe. RAM readings are measured
per run and retained with the independent guard's outcome.

```powershell
.\backends\halogen-wsl2-0.15.1\Start.ps1 -Status
.\backends\halogen-wsl2-0.15.1\Start.ps1 -Logs
.\backends\halogen-wsl2-0.15.1\Start.ps1 -Stop
```

Keep the serving terminal open. Logs are under `.local/services/<run-id>/`:
`service.log`, `engine.log`, `host-guard.jsonl`, and bootstrap diagnostics in
`guard-process.log`/`guard-failure.json` when relevant. Unresolved state is retained.
Legacy Trace4k/Single4k/Serve4k remain bounded diagnostics; do not expose them publicly.

[Measured checkpoint comparison](../../docs/benchmarks/halogen0151-v2-262k-20260930.md)
contains the actual PP/Decode and memory results, clock-calibration caveat, managed
lifecycle checks and limitations. [Benchmark scripts](../../scripts/benchmarks/README.md)
provide reproduction commands. [Research review](../../docs/integration/unified-review-20260930.md)
records investigated ideas without promoting untested kernel or driver changes.

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
controller. Directly starting the backend alone does not add this outer guard.
A polling guard cannot guarantee a floor against instantaneous outside allocations.
The client may still request serial decoding; this option only sets the greedy
MTP draft depth. It is not NPU offload or PROJFIX's tensor-placement selector.
See [measurements and scope](../../docs/research/halogen-gufo-mtp-20261001.md).

`draft_profiles.py --prefill-chunk 4096` and `8192` generate isolated v2
candidates; they forward the chunk through the launcher into the existing
Halogen container with a matching token arena. The earlier PP8192 output
hashes differ from the 2048 control. Neither candidate is qualified or a
replacement default. Run each 18 GiB managed profile sequentially through
the exact PP/TG and broad quality matrix in `server/.local/NEXT_STEPS.json`;
the quality gate treats output drift as failure and labels exposed top-N
logprob differences a proxy, not full-logit equivalence.
