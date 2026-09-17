# strix-alloy user guide

For people who want to run Qwen3.8-Flash-Next locally on a Windows machine with an AMD Strix Halo
APU (Ryzen AI Max / Max+ 300 series, Radeon 8060S, `gfx1151`).

This is an **experimental prerelease**. It is tested on one machine and one model. Read the
limitations at the end before relying on it.

---

## 1. What you need

| | |
| --- | --- |
| Hardware | AMD Ryzen AI Max+ 395 (or another Strix Halo APU with Radeon 8060S) |
| Memory | 128 GB unified LPDDR5X recommended; a large dedicated-VRAM carve (see below) |
| OS | Windows 11, 64-bit |
| Drivers | Current AMD Adrenalin driver with the ROCm/HIP runtime |
| Model | Qwen3.8-Flash-Next GGUF shards — **not included**, you supply them |
| Disk | ~100 GB for the model, plus space for logs |

You do **not** need a compiler, the ROCm SDK, Git, Python or a development terminal to run this.
Those are only needed to build the engine from source (`setup/README.md`).

## 2. Install

1. Download `strix-alloy-<version>-windows-x64.zip` from the release page.
2. Extract it somewhere permanent, for example
   `%LOCALAPPDATA%\Programs\strix-alloy`. Avoid running it from inside the ZIP.
3. Verify the download against `strix-alloy-<version>-SHA256SUMS.txt` if you want to:
   `certutil -hashfile <zip> SHA256`

The extracted folder looks like this:

```
app/         launcher (Start Strix Alloy.cmd, Stop..., start-strix-alloy.ps1)
runtime/     the inference engine and its AMD runtime DLLs
config/      example configuration
docs/        this guide
licenses/    third-party notices
LICENSE
```

## 3. Set the GPU carve first

The iGPU can only use memory the firmware gives it. In your BIOS/UEFI, set the dedicated graphics
memory (UMA carve) to **96 GB**. This model needs roughly 72 GB of device memory at 32k context;
a small carve will load but run several times slower, and a 0.5 GB carve will not load at all.

> The carve is a portion of your system RAM reserved for the GPU. It is **not** a separate memory
> bank and it does **not** isolate the GPU from the rest of the system — the same physical memory
> serves both, so a larger carve means less for Windows.

## 4. First run

Double-click **`app\Start Strix Alloy.cmd`**.

On first run it asks for your model folder, because it cannot guess where you keep 100 GB of
weights:

1. Point it at the folder containing the target GGUF shards.
2. Optionally point it at the draft head `.gguf` for speculative decoding. Leave blank to run
   without speculation.
3. It saves your choices to `%LOCALAPPDATA%\strix-alloy\config.json` and starts the server.

Wait for the model to load — a couple of minutes is normal. When it is ready the local chat page
opens at `http://127.0.0.1:8899`. **After this, starting is a single double-click.**

Run it again later and it reuses the saved configuration. If a server from this installation is
already running, a second double-click reopens the existing page instead of loading the model a
second time.

## 5. Everyday commands

| I want to | Do this |
| --- | --- |
| Start | double-click `app\Start Strix Alloy.cmd` |
| Stop | double-click `app\Stop Strix Alloy.cmd` |
| Check status | `app\start-strix-alloy.ps1 -Action status` |
| Change model or port | `app\start-strix-alloy.ps1 -Action configure` |
| Find the logs | `%LOCALAPPDATA%\strix-alloy\logs` |

The launcher only ever stops the server **it** started, identified by PID *and* start time. It will
not kill another llama.cpp instance you are running for a different purpose, and it will not touch
anything else on your machine.

## 6. Configuration

`%LOCALAPPDATA%\strix-alloy\config.json`:

| key | meaning |
| --- | --- |
| `modelDir` | folder holding the target GGUF shards |
| `draftPath` | optional shared MTP sidecar; empty = serial profile |
| `port` | local port, bound to `127.0.0.1` only |
| `contextSize` | context window (32768 is a safe default; 251904 is the tested maximum) |
| `ubatch` | prefill micro-batch; 2048 is conservative, 16384 is used for the published prefill numbers |

The launcher **never silently changes inference mode**. It writes which profile it used
(`serial` or `mtp-2`) to the log, and the status command shows it.

## 7. Troubleshooting

**"no .gguf target model in ..."** — the folder you chose has no target shards. Point it at the
folder with the `...-00001-of-000NN.gguf` files.

**"expected N shards, found M"** — your shard set is incomplete. Download the missing pieces; a
partial set will not load.

**Server never becomes ready** — read `%LOCALAPPDATA%\strix-alloy\logs\server.stderr.log`. The
usual cause is a carve that is too small; the log shows the size it tried to allocate.

**Port already in use** — the launcher reports which process owns the port and does not touch it.
Change `port` in your config, or stop that other program.

**Runs but very slow** — check the carve. If the pool is smaller than the model, it still loads but
reads weights over the slow path.

**HIP fails at device init** — make sure the `runtime\` folder still contains its DLLs. The engine
needs the AMD runtime DLLs *next to the executable*, not merely installed somewhere on the system.

## 8. Limitations — read this

- **One model, one machine.** Everything was measured on a single Ryzen AI Max+ 395 box. Other
  Strix Halo variants are untested.
- **Experimental.** There are known open correctness items: state handling after a speculative
  draft is partially accepted, and full multi-turn / long-context quality validation. Completing a
  251k-token request proves capacity, not accuracy.
- **Speculative decoding is not guaranteed to be bit-identical to serial decoding** in the first
  ~2050 tokens of a conversation. The difference is small (sub-0.2-nat ties) and deterministic, but
  it exists.
- **The RTX 2070 SUPER / eGPU plan is not part of this release.** Nothing here uses a second GPU,
  and running games at the same time has not been validated.
- **No network exposure.** The server binds to `127.0.0.1` and the launcher does not open a firewall
  rule. Do not expose it to a LAN without understanding the consequences.
- **Models are your responsibility.** This package bundles no weights and no downloader.

## 9. Uninstall

Stop the server, delete the folder you extracted, and delete `%LOCALAPPDATA%\strix-alloy`. Your
model files are elsewhere and are not touched.

---

Numbers, comparisons and open items: `docs/benchmarks/engine-comparison.md` and
`docs/benchmarks/CLAIM-LEDGER.md` in the source repository.
