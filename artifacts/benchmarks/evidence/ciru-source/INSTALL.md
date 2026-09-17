# Install and run Ornith1.5 Ciru Halo Agent

This release includes the target model, trained DFlash2 drafter, native kernels, custom vLLM plugin, and exact vLLM/AITER runtime wheels and source archives. **Use this runtime; stock `pip install vllm` does not provide the custom quantization or serving path.**

## Hardware and platform

- AMD Ryzen AI Max+ Strix Halo, gfx1151, with 128 GB unified memory.
- Linux x86-64 with a working AMD GPU driver, readable/writable `/dev/kfd` and render nodes.
- Budget roughly 100 GB available system memory for the loaded production profile. The recorded whole-host peak was 95.35 GB; other applications also use that memory.
- Allow at least 60 GB free disk for the 24.3 GB model assets, runtime installation and caches; source rebuilds need additional space.
- Validated platform: NixOS, Linux 7.2.2, glibc 2.42. A clean isolated runtime installation was tested on Strix Halo. The Ubuntu recipe below is provided for deployment and has not been independently validated on Ubuntu. Do not replace your system glibc to run this model.

## Download

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) and Git, then:

```bash
uvx --from huggingface_hub hf download \
  jcbtc/Ornith1.5-Ciru-Halo-Agent-vllm-strix-halo \
  --local-dir ./ciru-halo-agent
cd ciru-halo-agent
```

## Ubuntu 26.04 LTS prerequisites

Ubuntu 26.04 supplies [glibc 2.43](https://packages.ubuntu.com/resolute/libc6). This is the mainstream distro recipe; the validated host remains NixOS.

```bash
sudo apt-get update
sudo apt-get install -y build-essential git cmake ninja-build pkg-config xxd \
  curl ca-certificates tar libnuma-dev libdrm-dev libelf-dev libssl-dev \
  zlib1g-dev libvulkan-dev
```

Ensure your user can access `/dev/kfd` and `/dev/dri/renderD*`; GPU access must work before launching. The installer obtains the pinned ROCm SDK and Python packages; a stock distro vLLM package is not needed.

```bash
bash runtime/INSTALL-ORNITH-RUNTIME.sh "$PWD/installed-runtime"
bash bundle/serve.sh --dry-run
bash bundle/serve.sh --host 127.0.0.1 --port 8000
```

The runtime installer refuses to overwrite an existing installation. `uv` must be on PATH. Installation downloads pinned dependencies from the AMD wheel index and Python package index.

## NixOS

Enable the standard dynamic loader with `programs.nix-ld.enable = true;` and working AMD GPU device access. The provided shell supplies the compiler and host libraries:

```bash
nix-shell runtime/shell.nix --run \
  'bash runtime/INSTALL-ORNITH-RUNTIME.sh "$PWD/installed-runtime"'
nix-shell runtime/shell.nix --run \
  'bash bundle/serve.sh --host 127.0.0.1 --port 8000'
```

## API and agent clients

The server exposes an OpenAI-compatible API at `http://127.0.0.1:8000/v1`, model ID **`ciru-halo-agent`**. Point Hermes or another compatible agent client to that URL. Use `--host 0.0.0.0` only when you intend to expose it on your network; the launcher provides no authentication by default.

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"ciru-halo-agent","messages":[{"role":"user","content":"Write a Python function that merges overlapping intervals."}],"temperature":0.6,"top_p":0.95,"max_tokens":4096,"chat_template_kwargs":{"enable_thinking":false}}'
```

The default profile supplies **262,144 tokens of per-request context capacity**, **eight active sequences**, **44 GiB shared KV/state pool**, prefix caching and adaptive speculation. Input and output share the context window; your agent client must reserve output space and compact history before filling it. Eight independent, fully populated 256K histories are not promised. The default server profile is text-only. For optional image input, run `bash bundle/serve-vision.sh --host 127.0.0.1 --port 8000` after installation. The matching native BF16 vision encoder and projector are already included in `bundle/models/target/protected-00.safetensors`; no separate GGUF mmproj is required. This enables one image per request at a 1,048,576-pixel budget with up to eight active requests. See [the model card](README.md#optional-vision--image-input) and [vision validation limits](VISION.md).

First startup compiles/loads GPU kernels and creates caches. Wait for `/health` before sending work. Keep `bundle/cache` writable. Change runtime/model locations with `ORNITH_RUNTIME_ROOT`, `ORNITH_MODEL`, and `ORNITH_DRAFT`. Ordinary users do not need to change quantization or draft-policy settings.

## Build from source

The [Ciru source repository](https://github.com/ciru-ai/ornith-ciru-halo-agent) contains the model plugin, all eight native kernel sources, and the corresponding build script. See its `BUILD.md` for the native rebuild command. Runtime source archives are provided in this Hugging Face repository under `runtime/`; they include the matching vLLM/AITER source, licenses and release overlay notes. The binary installation above is the tested way to assemble the pinned engine; native source rebuilding is separate from retraining or requantizing the model.

Pinned runtime: vLLM `0.1.0rc2.dev9+g9255fd9fb9.rocm100` (base `9255fd9fb9fedf4b29d574a8d8bb21d93892cc98` plus supplied cache overlay), AITER `0.1.0rc1`, Python 3.14.3, PyTorch `2.13.0+rocm10.0.0`, ROCm SDK 10.0.0 and Transformers 5.16.1. Preserve included third-party licenses when redistributing.
