---
license: mit
library_name: vllm
pipeline_tag: text-generation
base_model:
  - ornith-ai/Ornith-1.5-35B-A3B
base_model_relation: quantized
model_name: Ornith1.5 Ciru Halo Agent (vllm strix halo)
tags:
  - ornith
  - ciru
  - amd
  - strix-halo
  - gfx1151
  - rocm
  - vllm
  - agentic
  - tool-use
  - quantized
  - speculative-decoding
  - dflash2
  - vision
  - image-text-to-text
---

# Ornith1.5 Ciru Halo Agent (vllm strix halo)

![Ornith1.5 Ciru Halo Agent — local agents on AMD Strix Halo](assets/ciru-halo-agent.png)

**A local AI team, built around AMD Strix Halo.** Ornith1.5 **Ciru Halo Agent** combines a custom quantization of Ornith's 35B-A3B mixture-of-experts model with a purpose-built vLLM/ROCm runtime for fast coding, tool use, and concurrent agents.

The design starts with the hardware: packed four-bit weights, four-bit activation paths, Strix Halo four-bit matrix instructions, specialized kernels, and adaptive DFlash2 speculative decoding. Prefix caching and a shared memory pool let agents return to long working histories.

**Measured on AMD Ryzen AI Max+ 395 / Radeon 8060S (gfx1151):**

- **178 tok/s single-request decode** on the ten-question coding speed screen, with **166 ms mean time to first token**.
- **295 tok/s aggregate at eight concurrent requests**, completing the ten-question batch in **5.52 seconds**.
- **1,287 tok/s cold prefill at 64K** and **668 tok/s near 256K**—**1.62× and 2.71×** the recorded Q4_K_XL prefill rates, respectively.
- **256K request context capacity**, eight active sequences, and a **44 GiB shared KV/state pool**.
- **123 tok/s cached C1 decode at 63K history**, with all ten return-task health checks passing.

These figures describe specific workloads, rather than a universal generation rate. The benchmark tables below include quality results and the workloads where other builds are faster.

**[Full benchmarks, runner builds, serving settings, and limitations](https://llm.ciru.ai/research/ornith-strix/)** · **[Source and build instructions](https://github.com/ciru-ai/ornith-ciru-halo-agent)** · **[Credits](CREDITS.md)**

## Running Ciru Halo Agent

**Use the accompanying Ciru runtime.** This is a custom packed checkpoint and serving stack; installing stock vLLM and pointing it at the weights does not reproduce this build.

The measured profile targets Linux on AMD Strix Halo, with enough unified memory for the model, drafter, and context pool. Peak whole-host memory during the recorded production campaign was **95.35 GB**. That includes other host processes and is not the model-file size or a minimum-memory guarantee. The hardware used for this work has 128 GB unified memory.

```bash
uvx --from huggingface_hub hf download \
  jcbtc/Ornith1.5-Ciru-Halo-Agent-vllm-strix-halo \
  --local-dir ./ciru-halo-agent
cd ciru-halo-agent
bash runtime/INSTALL-ORNITH-RUNTIME.sh "$PWD/installed-runtime"
bash bundle/serve.sh --host 127.0.0.1 --port 8000
```

Read **[Installation and build instructions](INSTALL.md)** first for Linux prerequisites, the runtime environment, source rebuild commands, and deployment details. The shipped stack was checked in an isolated installation on an existing Strix Halo test host; this is separate from validation on a fresh external machine. Source is available in **[ciru-ai/ornith-ciru-halo-agent](https://github.com/ciru-ai/ornith-ciru-halo-agent)**.

### Optional vision / image input

After the same download and runtime installation above, start the image-enabled profile:

```bash
bash bundle/serve-vision.sh --host 127.0.0.1 --port 8000
```

**The matching vision encoder and projector are already included.** This vLLM checkpoint uses native BF16 tensors, not a separate llama.cpp `mmproj` GGUF. All **333 `model.visual.*` tensors**, including the six `model.visual.merger.*` projector tensors, are in [protected-00.safetensors](bundle/models/target/protected-00.safetensors), indexed by [model.safetensors.index.json](bundle/models/target/model.safetensors.index.json). The image processor configuration is included alongside them. No additional projector download or `--mmproj` argument is needed; a GGUF projector cannot be substituted into this runtime.

The optional profile accepts **one image per request**, up to **eight active requests**, with a default **1,048,576-pixel preprocessing budget**. Video is disabled. It uses `TRITON_ATTN` for the BF16 image encoder and retains the text profile's 262,144-token request capacity, 44 GiB shared KV/state pool, A4/IU4 target paths, prefix caching, and adaptive DFlash2. Image tokens consume context capacity. `serve.sh` remains the text-only default.

Send an image through the OpenAI-compatible chat API; this example embeds a local file without exposing a local-file server:

```bash
python3 - ./image.png <<'PYIMAGE'
import base64, json, mimetypes, pathlib, sys, urllib.request
image = pathlib.Path(sys.argv[1])
mime = mimetypes.guess_type(image.name)[0] or "image/png"
data_url = f"data:{mime};base64," + base64.b64encode(image.read_bytes()).decode()
payload = {
    "model": "ciru-halo-agent",
    "messages": [{"role": "user", "content": [
        {"type": "text", "text": "Describe this image."},
        {"type": "image_url", "image_url": {"url": data_url}}
    ]}],
    "max_tokens": 512,
    "chat_template_kwargs": {"enable_thinking": False}
}
request = urllib.request.Request(
    "http://127.0.0.1:8000/v1/chat/completions",
    data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
with urllib.request.urlopen(request, timeout=180) as response:
    print(json.load(response)["choices"][0]["message"]["content"])
PYIMAGE
```

Earlier retained image-profile checks passed **8/8 API image requests**, **8/8 native Hermes image clients**, and **20/20 post-vision HumanEval base and extended checks**, with **96.91 GB peak whole-host memory**. A mixed batch scored **7/8**: all four images were correct, but one text-only request refused. These are narrow, partly image-cache-warm checks of the earlier packaged image profile, not a new evaluation of this publication or broad vision-quality evidence. The published weights and launcher settings were checked separately. See [vision checks and limits](VISION.md).

### Serving behavior

| Setting | Measured profile |
| --- | --- |
| Request context limit | 262,144 tokens, including prompt and output |
| Active requests | Up to 8; additional requests queue |
| Shared KV/recurrent-state pool | 44 GiB |
| Prefix caching | Enabled, including recurrent-state reuse |
| Speculative drafter | Trained Ornith DFlash2 by jzinno |
| Single-request speculation | Adaptive 15/7/off below 32,768 computed tokens; 15-token drafting on longer contexts |
| Concurrent speculation | 7-token drafting for 2–8 active requests |
| Agent integration | OpenAI-compatible API, tool calling, preserved Ornith chat/reasoning behavior |
| Default release evidence | Text profile |

The pool is shared. **Eight active requests does not mean eight unrelated, fully populated 256K histories fit at once.** Output must fit in the remaining request context; there is no separate promise of 256K output after a 256K input. Preserve the supplied chat template and use the client’s intended thinking setting.

## Coding speed and concurrency

HumanEval 0–9, thinking off, greedy sampling, natural end-of-sequence, cold prompt salts. Each row runs all ten questions. These are **speed and health checks**, not evidence of general coding quality.

| Concurrent requests | Ten-task completion | Mean request decode | Mean first-token latency | Aggregate throughput |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 10.65 s | **178.17 tok/s** | **0.166 s** | 148.69 tok/s |
| 2 | 8.47 s | 111.59 tok/s | 0.259 s | 187.07 tok/s |
| 4 | 7.12 s | 73.54 tok/s | 0.340 s | 222.74 tok/s |
| 6 | 5.99 s | 60.81 tok/s | 0.524 s | 264.84 tok/s |
| 8 | **5.52 s** | 55.84 tok/s | 0.709 s | **294.89 tok/s** |
| 10 offered / 8 active | 7.40 s | 55.38 tok/s | 1.297 s | 249.20 tok/s |

**60/60 base and extended health checks passed.** Mean request decode measures generation after the first token. Aggregate throughput divides all output tokens by complete batch wall time, including scheduling and prefill. They are different metrics, and output length varies between configurations.

For comparison, the fresh **Q4_K_XL + DFlash2 (7-token)** C1 run at 256K capacity completed the same ten-question batch in **17.32 s**, at **131.65 tok/s mean request decode** and **0.351 s mean first-token latency**, with 10/10 health. Ciru Halo Agent completed that batch **1.63× faster**. The measured ROCmFP4 C1 MTP4 mode took **19.56 s**, at **113.31 tok/s**. Complete concurrency sweeps, alternative modes, and their health outcomes are on the research page.

## Fast prompt ingestion

Cold input, without a prefix-cache hit. These are backend prefill-counter rates; each request then generated a natural 17-token acknowledgement. The short acknowledgement is not a sustained decode or reasoning benchmark.

| Input tokens | Ciru Halo Agent | Q4_K_XL | ROCmFP4 |
| ---: | ---: | ---: | ---: |
| 1,024 | **1,868 tok/s** | 1,056 tok/s | 1,058 tok/s |
| 8,192 | **1,715 tok/s** | 1,174 tok/s | 1,046 tok/s |
| 32,768 | **1,509 tok/s** | 998 tok/s | 842 tok/s |
| 65,536 | **1,287 tok/s** | 794 tok/s | 629 tok/s |
| 131,072 | **983 tok/s** | 552 tok/s | 414 tok/s |
| 253,952 | **668 tok/s** | 246 tok/s | 252 tok/s |

The complete near-256K cold request took **380.83 s**, versus **1,032.06 s for Q4_K_XL** and **1,007.04 s for ROCmFP4**. ROCmFP4’s lower-depth rows come from its retained author-profile sweep; the near-256K point is the fresh cold capture. The research page identifies each source run.

## Returning agents and large histories

All rows below use **all ten coding questions**, populated histories, and confirmed prefix-cache reuse. Timing includes queueing, suffix prefill, and generation; preparing the shared history is separate.

| Shared history | Concurrency | Ciru mean decode | Ciru mean first-token latency | Ciru ten-task completion |
| ---: | ---: | ---: | ---: | ---: |
| 63,000 tokens | 1 | **123.34 tok/s** | 0.848 s | 21.49 s |
| 63,000 tokens | 8 | **32.08 tok/s** | 3.968 s | 13.69 s |
| 253,952 tokens | 1 | **94.00 tok/s** | 4.619 s | 66.37 s |
| 253,952 tokens | 8 | **11.10 tok/s** | 18.033 s | 53.64 s |

**40/40 base and extended health checks passed.** At 63K/C1, Q4_K_XL and ROCmFP4 completed the ten returns in **52.24 s** and **33.45 s**. Near 256K/C1, they completed in **75.93 s** and **61.06 s**: ROCmFP4 finished that batch sooner despite Ciru’s higher generation rate. First-token latency and output length also matter.

The tested Q4_K_XL and ROCmFP4 configurations did not share the warmed prefix successfully across eight request slots. Their **cached C8 comparison remains unavailable**; this does not establish that the runners cannot support it.

## Quality and actual agent work

The release was evaluated separately from the short coding speed screen. Full EvalScope runs use the native **541 IFEval, 1,319 GSM8K, and 164 HumanEval** tasks. Tool and Hermes scores use their own native graders.

| Quality measure | Ciru Halo Agent | Q4_K_XL | ROCmFP4 |
| --- | ---: | ---: | ---: |
| Full GSM8K | **1,254/1,319 · 95.07%** | 1,252/1,319 · 94.92% | 1,228/1,319 · 93.10% |
| Full HumanEval | 144/164 · 87.80% | **151/164 · 92.07%** | 147/164 · 89.63% |
| Full IFEval, prompt strict | 390/541 · 72.09% | 413/541 · 76.34% | **421/541 · 77.82%** |
| Difficult HumanEval subset | **4/6** | 2/6 | 0/6 |
| Tool suite, 69 core + 15 hard | 140/168 points | 138/168 points | **143/168 points** |
| BF16 top-token agreement | 45/56 | **47/56** | 41/56 |

Full EvalScope used C8, thinking off, greedy sampling, and a 32,768-token response allowance. Ciru and ROCmFP4 used 256K capacity; Q4’s retained full-suite run used 65K capacity and its native chat protocol. Ciru had two IFEval length stops; ROCmFP4 had two GSM8K length stops. All other requests in those two runs completed naturally. Their complete evaluation wall times, including orchestration and grading, were **4,006 s** and **5,024 s**, respectively.

The difficult subset and tool suite are single blocks, not repeated confidence estimates. BF16 agreement uses seven held-out documents with eight adjacent prefix positions each: these 56 correlated anchors measure short-prefix fidelity, not task accuracy. The original BF16 source was fixed; the comparison quants’ exact source-weight ancestry is not established.

### Hermes: three complete passes per model and concurrency

Twenty native agent scenarios per pass, three seeds, 256K capacity, up to 64 turns, and output bounded by remaining context. Scores below are native scores, not percentages of tasks passed.

| Model | C1 mean score | C1 mean workflow time | C8 mean score | C8 mean workflow time |
| --- | ---: | ---: | ---: | ---: |
| **Ciru Halo Agent** | 90.33 | 820.00 s | 92.00 | 369.66 s |
| Q4_K_XL | 94.00 | 753.18 s | 94.00 | 358.95 s |
| ROCmFP4 | 93.67 | 681.84 s | 91.00 | 550.07 s |

Ciru’s C8 mean workflow time was **1.49× faster than ROCmFP4**, while Q4 was slightly faster than Ciru in this suite. One interrupted Q4 transport run was retained separately and replaced once; it is excluded from the three complete passes. The research page includes every pass, score range, token timing, and failure count.

## Where the speed advantage changes

Ciru Halo Agent’s strongest results are speculative coding, prompt ingestion, and shared-history workloads. **It is not the fastest model on every task.** Four ordinary prose tasks with automatic speculation measured **49.90–63.27 tok/s**, compared with approximately **59.5–59.8 tok/s for Q4** and **73.9–74.1 tok/s for ROCmFP4** in the retained no-speculation prose captures. Ciru’s target-only diagnostic measured approximately **56–58 tok/s**. The diagnostic skips draft work; its allocations still include the drafter.

256K capacity and the successful return tests do not establish uniformly strong reasoning across every long document. The main benchmark tables measure the text profile. The optional vision profile and its separate, earlier validation limits are described above. Hardware, software builds, memory pools, prompt mix, and speculation acceptance affect results.

## Credits and sponsorship

**Ciru Halo Agent is built by Ciru / Crown ([jcbtc](https://huggingface.co/jcbtc)). AMD provided me with a Ryzen AI Halo, and I am sponsored by AMD.**

- **[Ornith Team](https://huggingface.co/ornith-ai/Ornith-1.5-35B-A3B)** created the base Ornith model. Ciru’s work is its hardware-specific quantization, kernels, serving integration, and evaluation; we do not claim authorship of the base model’s training.
- **[jzinno](https://huggingface.co/jzinno/Ornith-1.5-35B-A3B-DFlash2)** trained the Ornith DFlash2 drafter, initialized from **[z-lab’s Qwen3.5 DFlash](https://huggingface.co/z-lab/Qwen3.5-35B-A3B-DFlash)**. Credit also goes to the **[DFlash](https://arxiv.org/abs/2602.06036)** and **[DFlash 2](https://inco.ai/blog/dflash2/)** authors and the NVIDIA Nemotron dataset contributors whose work supports that drafter.
- **[Qwen](https://github.com/QwenLM)** supplied the underlying Qwen model architecture used by this Ornith checkpoint.
- **[vLLM](https://github.com/vllm-project/vllm)**, **[AMD ROCm](https://github.com/ROCm)**, **[AITER](https://github.com/ROCm/aiter)**, **[Composable Kernel](https://github.com/ROCm/composable_kernel)**, **[PyTorch](https://github.com/pytorch/pytorch)**, and **[Triton](https://github.com/triton-lang/triton)** provide the runtime and compiler foundations.
- Thanks to **[peculiar-ragdoll](https://huggingface.co/peculiar-ragdoll/Unsloth-Ornith-1.5-35B-A3B)**, **[Daniel Han Chen](https://github.com/danielhanchen/llama.cpp)**, **[julianmb](https://huggingface.co/julianmb/Ornith-1.5-35B-A3B-ROCmFP4-GGUF)**, **[HaloFPX](https://github.com/julianmb/halofpx)**, and the llama.cpp/ROCmFP4 community for the comparison builds. Their artifacts are baselines, not components of Ciru’s target weights. The Q4 quant is a community Unsloth-style release, not an official Unsloth upload.

See **[CREDITS.md](CREDITS.md)** for pinned provenance and license details. The target model follows Ornith’s MIT declaration; the DFlash2 companion is Apache-2.0 and runtime components retain their own licenses.
