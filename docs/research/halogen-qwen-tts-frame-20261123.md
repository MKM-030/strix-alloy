# Qwen3-TTS acoustic frame replay for Halogen overlap

The CPU reference reproduces the first greedy audio frame from native
Vulkan. It changes two sampled decisions when it receives the same preceding
codes. This provides a concrete parity test for a future CodePredictor backend.
The [concurrent TTS benchmark](halogen0207-tts-gpu-contention-20261123.md)
sets the comparison budget at about 25.3 ms per frame including handoff costs.

## Input and results

The private `qwen-tts.exe` CLI captured the first frame with the installed
0.6B Base Q8_0 Talker, 12 Hz Q8_0 codec and synthetic German reference. The
CLI identifies as `a8a7716`. The comparison server identifies as `9c37f4c`.
The pinned source delta in the pipeline changes reporting at the output
token limit. The two binaries retain separate identities in the receipts.
The replay uses the last 1,024-value FP32 Talker row from prefill, native
`c0`, and the same host Philox draw sequence. It dequantizes the 87 required
tensors directly from the installed GGUF. Each frame starts with fresh KV.

| Native capture | Matching acoustic codes, free run | Matching decisions with reference history | First sampled divergence |
| --- | ---: | ---: | --- |
| Greedy, seed 42 | 15/15 | 15/15 | None |
| Sampling, seed 42 | 11/15 | 14/15 | c11, native 1331, replay 362 |
| Sampling, seed 91 | 7/15 | 14/15 | c3, native 310, replay 1596 |

The forced comparison feeds the original previous code into each subsequent
step. For seed 42, the CPU CDF ended the native code's interval at
0.9195200 and the shared draw was 0.9228392. For seed 91, those values
were 0.7570573 and 0.7574215. One changed decision in a free run can move
the rest of its trajectory. The Philox implementation also matched 75
draws from the pinned C++ implementation, including signed seeds.

The replay uses explicit FP32 attention and dequantized matmuls. The Vulkan
source can select Q8_1 activations for two-row matmuls and use narrower
operands inside the fused attention shader. A CPU approximation of two-row
Q8_1 activations did not reproduce both native decisions. The available
native dumps show the reference codes. They do not contain native acoustic
logits or prove which shader operation moved the probability boundary.

TTS remained on Vulkan. The captures neither changed the live Halogen
engine nor submitted inference requests to it. One attempt stopped when
the Native Bridge was temporarily unreachable. The three captures belong
to the subsequent attempt after the Bridge recovered. Greedy reached the
CLI's 96-frame cap. The first frame is available and this run supplies no
whole-utterance PCM equivalence claim. No NPU device ran the predictor.

## Replaying a native capture

Run from this repository with NumPy available. The dump directory must
contain native `talker-hidden-prefill-final.bin` and `codes-step0.bin` files.
Pass the actual resolved seed and acoustic temperature from the native
request. Use `0` for greedy. The command emits JSON and returns status 1
when any code differs. The JSON includes a separate teacher-forced
comparison and the reference code's probability interval when available.

```powershell
python -m scripts.research.qwen_tts_frame.replay `
  --gguf C:/AI/models/qwen3-tts-gguf/qwen-talker-0.6b-base-Q8_0.gguf `
  --dump-dir path/to/native-dump --name seeded-42 --seed 42 --temperature 0.9
```

The local receipts and snapshots are under
`server/.local/halogen-update-20261122/primary0207/tts-cpu-offload-prep-v1/codepredictor-native-capture-v2`.

## First-step ONNX and Windows provider

`export_first` builds a static opset-17 graph from the same frame weights.
It runs the two-token causal prefill and returns all 2,048 logits for `c1`.
Sampling stays on the host. The ONNX checker and a one-thread ONNX Runtime
CPU session passed with the three native inputs. All three selected the
native `c1` value `1666`. The largest absolute logit difference against
NumPy was `0.00002575`. This check covers the first acoustic decision.

## Measured first acoustic step on the NPU

The initial registration attempt used the legacy ORT adapter and failed
with Windows error 126 because its paired shared DLL was absent. The
existing standalone `onnxruntime_vitisai_ep.dll` matched the hash of a prior
working component probe and compiled the original graph. Its preliminary
partition left the dynamic `c0` embedding lookup on the host. That attempt
reached AIE scheduling and stopped at the three-minute compilation deadline.

`export_first --host-embedding` accepts two FP32 rows, the Talker hidden
row and the exact Q8_0 `c0` embedding decoded on the host. The rest of the
first-step graph stays the same. The default export reproduces its original
SHA-256. The two variants returned bit-identical CPU logits for six inputs
covering three native hidden rows and two semantic IDs per row.

The completed private run compiled the host-embedding graph in **179.7 s**.
The compiler assigned 363 optimized operators to one BF16 partition. Its
retained context reports `deviceName=stx` and `runnerType=hw`. All 12
ONNX Runtime inference node events were attributed to VitisAI, with CPU
fallback disabled. The optional EP-specific profiler reported no additional
events at shutdown. Per-node attribution and the hardware context are
the placement evidence.

| First-step backend | Warm calls | Mean host latency | Observed range |
| --- | ---: | ---: | ---: |
| VitisAI NPU | 9 | 8.247 ms | 8.201–8.384 ms |
| ORT CPU, one thread | 9 | 10.020 ms | 9.801–10.167 ms |

Each group used the same ONNX graph and three pinned input fixtures, with
one excluded warmup and three measured calls per fixture. Times include
host embedding lookup, the provider call, visible logits and the host
sampler. Every call selected native `c1=1666`. The three reference cases
share that expected code. The test covers the first acoustic step before
later codebooks and excludes live GPU hidden-state readback. The retained
Vulkan controls cover an entire acoustic frame with 15 dependent steps.
No result here establishes a gain in Halogen Prefill, Decode or MTP.

Public Halogen stayed online throughout the probe. The minimum sampled
physical or commit reserve was 25.06 GiB. The compiled context, raw
results and runner logs are retained locally in the sibling
`codepredictor-first-npu-run-v3-host-embedding` directory.
