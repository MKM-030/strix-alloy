# strix-alloy

Windows-native Qwen inference on AMD Strix Halo, built on [pwilkin's `llama.cpp` fork](https://github.com/pwilkin/llama.cpp/tree/strix-halo).

## What this is

An experimental Windows package for running **Qwen3.8-Flash-Next** locally on an AMD Strix Halo APU — the Ryzen AI Max / Max+ 300 series with a Radeon 8060S (`gfx1151`, RDNA 3.5). No Linux, no WSL, no CUDA, no datacenter GPU. It runs the model on the machine under your desk while you use Windows for everything else.

Scope is deliberately narrow: one model family, one GPU architecture, one operating system, measured on one box — stated plainly rather than generalised.

## Why I built it

My old desktop stopped working. It was still on DDR3, and rather than rebuild around it I bought a **BOSGAME M5 with 128 GB of unified memory**. I still have an **RTX 2070 SUPER** I want to put back to use.

The M5 is also my everyday Windows PC. I want to work on it, develop on it and play games — not turn it into a dedicated Linux inference server. That is the whole reason for this project.

I am also building **REV:N**, an AI-driven GTA V / FiveM project, and it needs local models. `strix-alloy` is the local-inference side of that work, not the game itself.

**The plan I am working toward** is the M5's 8060S handling inference and the RTX 2070 SUPER acting as an eGPU for games, with Windows available throughout. **That is a goal, not a validated result.** Nothing in this release uses a second GPU, and simultaneous gaming plus inference has not been tested. The numbers below are inference-only.

## Download and run

strix-alloy documents and distributes the tested llama.cpp configuration and Windows HIP changes used to run Qwen3.8-Flash-Next on Strix Halo. Download the external GGUF files, optionally add the matching MTP sidecar, and load them with a compatible llama-server using your normal model-launch workflow. Use the server's existing web UI or your preferred client. **No separate strix-alloy application is required** - the package is a llama.cpp runtime plus one launch script.

| Item | Required? | Source | Use |
| --- | --- | --- | --- |
| Qwen3.8-Flash-Next PROJFIX GGUF shards (9 files, ~100 GB) | Yes | [ilintar/qwen3.8-flash-next-gguf-strix-halo](https://huggingface.co/ilintar/qwen3.8-flash-next-gguf-strix-halo) - `Qwen3.8-Flash-Next-IQ4_NL-PROJFIX-00001-of-00009.gguf` … `-00009-of-00009.gguf` | Start shard 1 with the compatible server |
| Matching shared MTP sidecar (2.6 GiB) | Optional | Same repo: [`mtp-Qwen3.8-Flash-Next-shared-Q8_0.gguf`](https://huggingface.co/ilintar/qwen3.8-flash-next-gguf-strix-halo/resolve/main/mtp-Qwen3.8-Flash-Next-shared-Q8_0.gguf) | Enables the tested MTP flags. The gain is **workload-dependent** - it is largest on short-context instructed decoding and shrinks as context grows; the measured figures are in [Current numbers](#current-numbers) below |
| Windows llama.cpp runtime (HIP/ROCm) | Only if your existing runtime lacks the model or shared-MTP support | The [v0.1.1 release](../../releases/tag/v0.1.1) archive (v0.1.0 is superseded), or build from source with [`setup/`](setup/) | The same normal `llama-server` workflow |

Weights stay on your disk and are never bundled or auto-downloaded; the upstream repo is Apache-2.0 and the files are unchanged from the publisher (verified by size and SHA-256, see [`config/model-manifest.example.json`](config/model-manifest.example.json)). No separate tokenizer or PLE file is needed.

```powershell
# 1. fetch the weights (native -hf loading is not used; download first, then point -m at shard 1)
hf download ilintar/qwen3.8-flash-next-gguf-strix-halo `
  --include "Qwen3.8-Flash-Next-IQ4_NL-PROJFIX-*.gguf" `
  --local-dir C:\AI\models\qwen38-flash\projfix

# 2. start the server - this is the whole command, no wrapper and no config file
& .\runtime\llama-server.exe `
  -m C:\AI\models\qwen38-flash\projfix\Qwen3.8-Flash-Next-IQ4_NL-PROJFIX-00001-of-00009.gguf `
  --alias Qwen3.8-Flash-Next -dev ROCm0 -ngl 99 -fa on -fit off --load-mode none `
  -ctk f16 -ctv f16 -c 32768 -b 2048 -ub 2048 --parallel 1 `
  --host 127.0.0.1 --port 8826 --seed 1234 --jinja
#    append for the MTP profile:
#      -md <path>\mtp-Qwen3.8-Flash-Next-shared-Q8_0.gguf
#      --spec-type draft-mtp --spec-draft-device ROCm0 --spec-draft-ngl 99 --spec-draft-n-max 2
```

`app/launch-flash-next.ps1` is a thin template around that command - it checks the shard set is complete, refuses to start a second copy on an occupied port, and prints the command it runs. Use it or ignore it; it is an ordinary server window that stops when closed.

```powershell
.\app\launch-flash-next.ps1 -ModelDir <dir> [-DraftPath <sidecar.gguf>]
.\app\launch-flash-next.ps1 -PrintOnly -ModelDir <same>   # show the command, start nothing
.\app\launch-flash-next.ps1 -Stop                         # stop it again
```

Once ready, the server's own chat page is at `http://127.0.0.1:8826` and the OpenAI-compatible API is `http://127.0.0.1:8826/v1`, model id `Qwen3.8-Flash-Next` - point LM Studio, Z Code or a `curl` at it. Note that importing the GGUF into another runtime (LM Studio, Ollama, a stock llama.cpp build) does **not** bring these kernels or this flag set with it; the same weights on a different runtime are a different measurement.

**Set your GPU carve first.** In BIOS/UEFI, reserve **96 GB** as dedicated graphics memory. The model needs about 72 GB of device memory. A small carve loads but runs several times slower; a 0.5 GB carve will not load. The carve is a reservation of system RAM, **not** a separate memory bank and **not** isolation.

Full details, troubleshooting and uninstall: **[docs/user/README.md](docs/user/README.md)**. You do **not** need a compiler, the ROCm SDK, Git or Python to run the runtime - those are only needed to build it from source.

## Current numbers

Published measurements, 17 September 2026. Native Windows HIP, TheRock SDK, IQ4_NL "PROJFIX", 96 GB carve. MTP runs use a shared Q8_0 draft head.

| Measurement | Result | Conditions |
|---|---:|---|
| Synthetic serial, `llama-bench tg128` | **31.49 ± 0.17 t/s** | No drafter; pseudorandom token inputs |
| Synthetic prefill, `pp16384` | **892.59 ± 22.50 t/s** | Batch and microbatch 16384 |
| Served serial decode | **28.3 t/s** | 16,384-token context; no drafter |
| Served MTP decode | **45.31 t/s** | Warm median, one 259-token instructed prompt; draft depth two |
| Served MTP, long-context ladder | **31.0–32.8 t/s** | Separate tests at 16,384–251,904 occupied tokens |
| Maximum-prefill serving setup | **1,031 t/s at 16k; 812 at 251,904** | Warm, no drafter, microbatch 16384 |

`±` is sample standard deviation. These are **different workloads and configurations**, not one combined performance promise — 31.49 without speculation and 45.31 with MTP do not measure the same thing.

For context, on speculative serving Halogen publishes 45.3 t/s (mean over ten prompt shapes) and CIRU 44.53 t/s on a 12,960-token replay. Our 45.31 is one prompt's median, so a tie is not established. The [full comparison](docs/benchmarks/engine-comparison.md) separates synthetic, served-serial, MTP and prefill results with pinned sources; the [claim ledger](docs/benchmarks/CLAIM-LEDGER.md) records every correction, including figures I had to withdraw.

## Requirements and honest limitations

- **Tested configuration:** one Ryzen AI Max+ 395 / Radeon 8060S box, Windows 11, 128 GB unified memory, 96 GB carve. Other Strix Halo variants are untested.
- **Models are external.** Nothing is bundled and nothing is downloaded automatically.
- **The 96 GB carve is not isolation.** It reserves part of the same physical RAM Windows uses.
- **The eGPU / simultaneous gaming setup is unvalidated** and is not part of this release.
- **Open correctness items remain:** state handling after partial draft acceptance, and full multi-turn / long-context quality validation. Completing a 251k request shows capacity, not accuracy. Speculative decoding is not guaranteed bit-identical to serial decoding in the first ~2050 tokens.

## Credits and collaboration

Built on [pwilkin / ilintar](https://github.com/pwilkin/llama.cpp)'s `strix-halo` engine and its Qwen kernels and PROJFIX quantization; on [llama.cpp](https://github.com/ggml-org/llama.cpp); on [Qwen](https://github.com/QwenLM)'s model; and on [AMD's TheRock](https://github.com/ROCm/TheRock) HIP SDK. I learned from [Halogen / peonist-ai](https://github.com/peonist-ai/halogen-flash-server), [CIRU](https://github.com/ciru-ai/Qwen3.8-Flash-CIRU-STRIX-IU4), [olliehm](https://github.com/olliehm/qwen-flash-next-windows), [myhacsint](https://github.com/myhacsint/llama.cpp), [stew675](https://github.com/stew675/llama-cpp-rdna-boosts), [SixVolts](https://github.com/SixVolts/llama-halo-hybrid), [halo-box](https://github.com/halo-box/strix-llama.cpp), [drluoto](https://github.com/drluoto/llama.cpp) and the r/StrixHalo community. [Full credits](docs/CREDITS.md).

Most of the kernel work is theirs. My contribution is the Windows integration, local patches, tested configurations and the measurement trail. I am not trying to beat these projects — I would rather share findings and patches with them.

## Developers and researchers

- **Build from source:** [`setup/README.md`](setup/README.md) creates a fresh engine checkout at the pinned base revision, applies the ordered [patch series](engine-patches/) and builds with checked exit codes.
- **Benchmark evidence and kernel experiments:** [`docs/benchmarks/`](docs/benchmarks/) - including negative results and retractions.
- **Reproduce the runtime archive:** [`packaging/build-release.ps1`](packaging/build-release.ps1).

**Maintenance status:** release and packaging complete. New performance research is paused — this is a stabilisation release, not an ongoing optimisation programme.
