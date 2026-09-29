# Setup and use

This is a narrow, experimental Windows + WSL2 package, tested on one machine—not upstream WSL support. Save your work before inference. Do not increase slot counts or lower reserves: a three-full-context research run froze Windows despite its guard. See [release qualification](release-qualification.md) and the [incident](benchmarks/parallel260k-20260925.md#three-full-contexts-host-freeze).

## 1. Prepare Windows and WSL

The tested host is a 128 GiB Ryzen AI Max+ 395 / Radeon 8060S (gfx1151), Windows 11 build 26200.7462, AMD driver 32.0.31041.1004 / Adrenalin 26.8.1. Its BIOS is AMI 3.10; that is identification, not a recommendation to flash another board.

- Set **64 GiB VGM** using only your device's supported BIOS or AMD Software control. Record the old setting and recovery procedure before changing it; a carve change needs a reboot. Do not write undocumented firmware variables.
- Install PowerShell 7, Python 3.12+ and Git on Windows, with `python` and `git` available in your shell.
- Prepare an **Ubuntu 24.04 WSL2** distribution with working `/dev/dxg` and Windows-provided `/usr/lib/wsl/lib/libdxcore.so`. Do not replace the installed Windows display driver with Linux packages.
- In Ubuntu, install **GCC 13.3**, `libssl-dev`, and **Docker Engine**. The selected Linux user must be able to use Docker without an interactive elevation prompt. Docker access is privileged; grant it only to a trusted user. The package checks these prerequisites but does not install them. Other compilers and Docker Desktop configurations have not been qualified.

Manually review `%USERPROFILE%\.wslconfig`, preserving unrelated settings:

```ini
[wsl2]
memory=56GB
processors=24
swap=32GB
localhostForwarding=true
[experimental]
autoMemoryReclaim=gradual
sparseVhd=true
```

Apply this only after stopping your WSL workloads, then restart WSL. WSL settings affect other distributions too. The native Windows sibling's **96 GiB carve** and Halogen's **native Linux minimal-carve advice** are different configurations: do not mix them into this profile.

## 2. Obtain the dependencies

Download the checkpoint, matching overlay and **complete tokenizer directory** from the [official Halogen model repository](https://huggingface.co/peonist-ai/halogen-qwen3.8-flash-next), accepting their terms yourself. Keep its chat template and other tokenizer assets; do not replace them with another model's tokenizer. Put them on **native WSL Ext4** (not `/mnt/c`, `/mnt/d` or another Windows-mounted filesystem). The example layout includes:

```text
/srv/models/flash-next/
  qwen38-flash-next-w4b.hgn
  qwen38-flash-next-w4b.overlay.hgn
  tokenizer/
    tokenizer.json
    tokenizer_config.json
    chat_template.jinja
    ... (retain the other supplied tokenizer assets)
```

The two HGN files total about 126.64 GB on disk; allow additional space for downloads, image layers and WSL growth. The installer verifies file sizes by default. Add `-VerifyModelHash` on first explicit installation for full SHA256 checks; this is substantial disk I/O. File sizes/hashes are pinned in `scripts/package.py`. A different model or overlay is not silently substituted.

Pull the pinned image **in the selected WSL distro**; this downloads the image but does not start inference:

```sh
docker pull ghcr.io/peonist-ai/halogen-flash-server@sha256:6e626c979d536ab1edb07898e278be6686afd353758ea268817457f801d687dd
```

Do not run upstream's native Linux launch command in WSL. Use this project's launcher below.

Download the [official AMD ROCm SDK core wheel](https://stable.repo.amd.com/rocm/core/whl-next/rocm-sdk-core/rocm_sdk_core-10.0.0-py3-none-linux_x86_64.whl) to Windows. Supply its path using `-AmdWheel`; the explicit installer extracts only the allowlisted DXG library locally. **Do not install the whole wheel or overwrite system libraries.** Alternatively use `-DxgLibrary` with an existing Linux library of exactly the [qualified hash](benchmarks/methodology.md#working-dependency-provenance). Both inputs are hash-gated; a changed upstream download is refused.

## 3. Check and install

In PowerShell 7, from your cloned repository, replace the example paths:

```powershell
# Checks only: no build, configuration write or model launch.
.\Install.ps1 -Distribution Ubuntu-24.04 -ModelDirectory /srv/models/flash-next `
  -AmdWheel C:\Downloads\rocm_sdk_core-10.0.0-py3-none-linux_x86_64.whl

# Builds adapters and writes only the package's local configuration.
.\Install.ps1 -Install -VerifyModelHash -Distribution Ubuntu-24.04 `
  -ModelDirectory /srv/models/flash-next `
  -AmdWheel C:\Downloads\rocm_sdk_core-10.0.0-py3-none-linux_x86_64.whl
```

Use `-LinuxUser` if you need a particular user rather than the distro default. The installer does not change BIOS, drivers, registry, services, WSL settings, pagefile or security settings. Do not weaken a refusal to get past a missing dependency or low-memory check.

## Use and remove

Run **one command at a time**, letting it stop before the next:

```powershell
.\Start.ps1 -Profile Single32k
.\Start.ps1 -Profile Serve32k -ServeSeconds 300
```

Once the API is ready, use another PowerShell window for a short request:

```powershell
$request = @{
  model = 'halogen-qwen3.8-flash-next'
  messages = @(@{ role = 'user'; content = 'Explain unified memory in two sentences.' })
  max_tokens = 128
  temperature = 0
  enable_thinking = $false
} | ConvertTo-Json -Depth 5
Invoke-RestMethod -Uri http://127.0.0.1:8731/v1/chat/completions `
  -Method Post -ContentType application/json -Body $request
```

`Serve32k` exposes one 32768-position slot for **30–300 seconds after readiness**, then stops, including outstanding requests. It is not an always-on service. Keep the supervising window open; Ctrl-C requests exact-container cleanup. The endpoint is loopback-only and unauthenticated. Do not bind it publicly.

`Single256k` is a bounded large-context qualification test; `Sessions32k` checks smaller parallel requests. They are not long-running serving profiles. The two-full-260k and three-full-260k research profiles are **not distributed**. The three-context failure demonstrated that asynchronous guards and container limits do not guarantee host safety.

Stop the launcher before running `Uninstall.ps1`. Uninstall removes only manifest-owned generated package files; models, Docker images, WSL, drivers and your manual settings remain. Local logs and machine configuration are excluded from Git. [Detailed rollback and test record](release-qualification.md).

## Native Windows alternative and 27B status

The separate [Strix Alloy v0.1.1 release](https://github.com/MKM-030/strix-alloy/releases/tag/v0.1.1) provides native Windows HIP / llama.cpp. Follow its [download/setup instructions](https://github.com/MKM-030/strix-alloy): obtain the PROJFIX GGUF shards and optional matching MTP GGUF sidecar, then use its helper:

```powershell
# In the native Strix Alloy package; replace paths.
.\app\launch-flash-next.ps1 -ModelDir C:\AI\models\projfix
# Optional speculation:
.\app\launch-flash-next.ps1 -ModelDir C:\AI\models\projfix -DraftPath C:\AI\models\mtp-Qwen3.8-Flash-Next-shared-Q8_0.gguf
```

These are alternatives, not commands to run simultaneously. Native API: `http://127.0.0.1:8826/v1`, model ID `Qwen3.8-Flash-Next`. Its published configuration uses a different carve; review its requirements independently. HGN overlays and GGUF MTP sidecars are not interchangeable.

The historical 27B Halogen experiment is a different model/server. This release does not provide a qualified 27B installation or a backend-switching flag; do not point the Flash Next launcher at 27B weights.
