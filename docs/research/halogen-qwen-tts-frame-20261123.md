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

The NPU attempt stopped at VitisAI provider registration with Windows error
126. The available VitisAI DLL depends on `onnxruntime_providers_shared.dll`,
which is absent from the pinned runtime configuration. The Windows ML
catalog reported VitisAI as `NOT_PRESENT` and returned no library path.
The separate ONNX Runtime 1.29 installation contains a differently versioned
shared DLL. The probe used the pinned local components and produced no NPU
inference samples. The private runner exited and Halogen stayed online.
