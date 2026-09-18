# strix-alloy user guide

For people who want to run Qwen3.8-Flash-Next locally on a Windows machine with an AMD Strix Halo
APU (Ryzen AI Max / Max+ 300 series, Radeon 8060S, `gfx1151`).

This is an **experimental prerelease**. It is tested on one machine and one model. Read the
limitations at the end before relying on it.

There is no strix-alloy application to install. What you get is a **llama.cpp runtime** and a short
launch script, and you run the model the same way you run your other GGUF models.

---

## 1. What you need

| | |
| --- | --- |
| Hardware | AMD Ryzen AI Max+ 395 (or another Strix Halo APU with Radeon 8060S) |
| Memory | 128 GB unified LPDDR5X recommended; a large dedicated-VRAM carve (see below) |
| OS | Windows 11, 64-bit |
| Drivers | Current AMD Adrenalin driver with the ROCm/HIP runtime |
| Model | Qwen3.8-Flash-Next GGUF shards - **not included**, you supply them |
| Disk | ~100 GB for the model, plus space for logs |

You do **not** need a compiler, the ROCm SDK, Git, Python or a development terminal to run the
runtime. Those are only needed to build it from source (`setup/README.md`).

## 2. Get the files

**The runtime.** Either take `strix-alloy-<version>-windows-x64.zip` from the release page and
extract it somewhere permanent (for example `%LOCALAPPDATA%\Programs\strix-alloy`; avoid running it
from inside the ZIP), or use a llama.cpp build you already have that supports this model and shared
MTP. See §5 for the support check.

Verify the download against `strix-alloy-<version>-SHA256SUMS.txt` if you want to:
`certutil -hashfile <zip> SHA256`

The extracted folder looks like this:

```
app/         launch-flash-next.ps1 and its .cmd entry point
runtime/     the inference engine and its AMD runtime DLLs
config/      model manifest example
docs/        this guide
licenses/    third-party notices
LICENSE
```

**The weights.** Nine shards from
[`ilintar/qwen3.8-flash-next-gguf-strix-halo`](https://huggingface.co/ilintar/qwen3.8-flash-next-gguf-strix-halo):

```powershell
hf download ilintar/qwen3.8-flash-next-gguf-strix-halo `
  --include "Qwen3.8-Flash-Next-IQ4_NL-PROJFIX-*.gguf" `
  --local-dir C:\AI\models\qwen38-flash\projfix
```

All nine must be present. The repository also carries the optional MTP sidecar
`mtp-Qwen3.8-Flash-Next-shared-Q8_0.gguf` (2.6 GiB), which is what the published MTP numbers use.

## 3. Set the GPU carve first

The iGPU can only use memory the firmware gives it. In your BIOS/UEFI, set the dedicated graphics
memory (UMA carve) to **96 GB**. This model needs roughly 72 GB of device memory at 32k context;
a small carve will load but run several times slower, and a 0.5 GB carve will not load at all.

> The carve is a portion of your system RAM reserved for the GPU. It is **not** a separate memory
> bank and it does **not** isolate the GPU from the rest of the system - the same physical memory
> serves both, so a larger carve means less for Windows.

## 4. Start it

From the extracted folder:

```powershell
.\app\launch-flash-next.ps1 -ModelDir C:\AI\models\qwen38-flash\projfix `
    -DraftPath C:\AI\models\qwen38-flash\projfix\mtp-Qwen3.8-Flash-Next-shared-Q8_0.gguf
```

or double-click **`app\Launch Flash Next.cmd`** and edit the paths into the command it shows.

The script:

1. checks that all nine shards are present (a partial set would otherwise burn a full load before
   failing);
2. refuses to start if the port is already held, and says by which process - it never kills
   something it did not start;
3. prints the exact `llama-server.exe` command it is about to run, so you can copy it into your own
   launcher and drop this script entirely.

Wait for the model to load - a couple of minutes is normal for ~100 GB of weights. When it is ready
the console prints the endpoint. **Leave the window open while you use the model**; closing it stops
the server.

Running the command again while it is already up reuses the running server instead of loading a
second copy.

## 5. Use it

Once ready, the server offers both of these on `127.0.0.1:8826`:

| | |
| --- | --- |
| Built-in chat page | `http://127.0.0.1:8826` |
| OpenAI-compatible API | `http://127.0.0.1:8826/v1`, model id `Qwen3.8-Flash-Next` |

Point any existing client at that endpoint. Nothing else is required - there is no proxy, no
gateway and no client to install.

```powershell
curl http://127.0.0.1:8826/v1/chat/completions -H 'Content-Type: application/json' -d '{
  "model": "Qwen3.8-Flash-Next",
  "messages": [{"role":"user","content":"Say hello in one short sentence."}],
  "max_tokens": 96
}'
```

**Using your own llama.cpp build instead.** The runtime in this package is not special because it
is ours - it is special because it is the build the numbers were measured on. A build supports this
model only if it was compiled with the Qwen3.8-Flash-Next architecture and the RDNA3.5 MoE path.
Check before you point it at 100 GB of weights:

```powershell
.\your-llama-server.exe --help | Select-String -Pattern 'spec-draft|draft-mtp|cache-type-k'
```

If `--spec-type draft-mtp` and `--spec-draft-model` are absent, that build cannot run the MTP
profile - it can still run the serial profile if it loads the architecture at all. **Importing these
weights into a different runtime does not bring these kernels with it**, and the numbers in the top
level README do not transfer to another engine.

## 6. Everyday commands

| I want to | Do this |
| --- | --- |
| Start | `app\launch-flash-next.ps1 -ModelDir <dir> [-DraftPath <gguf>]` |
| See the command without starting | add `-PrintOnly` |
| Stop | `app\launch-flash-next.ps1 -Stop` |
| Different port / context | `-Port 8826 -ContextSize 32768` |

There is no status file and no configuration store: the model folder, the draft head and the port
are arguments you pass. The script identifies a running server by the port it is listening on and
its command line, so it will not touch an unrelated process.

The one stateful thing worth knowing: **`-Stop` only stops a server whose command line is this
package's `llama-server.exe`.** If something else owns the port, it reports it and leaves it alone.
If you started the server by hand from your own runtime, stop it the same way.

## 7. Troubleshooting

**"Shard set is incomplete: N of 9 present"** - finish the download. A partial set will not load.

**"Port 8826 is already in use by PID ..."** - the script names the process and does nothing else.
Stop that program, or pass a different `-Port`.

**Server never becomes ready** - read the console output; it is the server's own stderr. The usual
cause is a carve that is too small, and the log shows the size it tried to allocate.

**Runs but very slow** - check the carve. If the pool is smaller than the model, it still loads but
reads weights over the slow path.

**HIP fails at device init** - make sure the `runtime\` folder still contains its DLLs. The engine
needs the AMD runtime DLLs *next to the executable*, not merely installed somewhere on the system.

**It does not use the MTP sidecar** - check the startup output for a `profile: mtp-2` line. If it
says `serial`, the `-DraftPath` was missing or the file was not found; the script never silently
falls back without saying so.

## 8. Limitations - read this

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
- **No network exposure.** The server binds to `127.0.0.1` and nothing opens a firewall rule. Do
  not expose it to a LAN without understanding the consequences.
- **Models are your responsibility.** This package bundles no weights and no downloader.

## 9. Uninstall

Stop the server, then delete the folder you extracted. Your model files are elsewhere and are not
touched. If you installed an earlier version under `%LOCALAPPDATA%\strix-alloy` and no longer want
it, that folder (a small `config.json` and logs) can be deleted too.

---

Numbers, comparisons and open items: `docs/benchmarks/engine-comparison.md` and
`docs/benchmarks/CLAIM-LEDGER.md` in the source repository.
