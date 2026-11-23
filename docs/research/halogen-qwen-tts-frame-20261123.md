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

## Full 15-step frame and native logit comparison

The static `export_frame` graph keeps K/V state and all 15 sampler decisions
inside one ONNX invocation. A single-thread ORT CPU run used the first two
frames of each of the three captures. Each frame used one excluded warmup
and three timed calls. ORT matched the NumPy free run on all 90 acoustic
codes. Every tested frame reported a valid sampler result.

| Native capture | Frame 0 exact codes | Frame 1 exact codes |
| --- | ---: | ---: |
| Greedy, seed 42 | 15/15 | 7/15 |
| Sampling, seed 42 | 11/15 | 6/15 |
| Sampling, seed 91 | 7/15 | 15/15 |

The free run matched native Vulkan on **61/90** codes and **2/6** complete
frames. With native history held at every step, NumPy matched **86/90**
decisions. The CPU frame means ranged from **135.28 to 142.94 ms**.
The earlier NPU measurement covers the first decision. The full graph
remains experimental and has no NPU frame latency result.

A private build at the same `a8a7716` source commit reads all 15 projection
outputs after the Vulkan graph completes. For all three captures, both
Talker inputs, the first code row, the complete code matrix and the WAV
file were byte-identical to the prior capture. Minimum sampled physical or
commit reserve was **24.47 GiB**. The added readbacks affect timing.

The host sampler reproduced **90/90** native decisions using the captured
Vulkan logits and native Philox draws. Each of the four NumPy comparisons
with held history flipped when Vulkan logits replaced the CPU logits.
Three sampled draws crossed different CDF boundaries. In the greedy
second frame, codebook 5 ranked native code 819 ahead by 0.00141 in Vulkan
and behind by 0.01875 in NumPy. Across the six frames the largest
single-logit absolute delta was 0.40991. These discrepancies arise before
token selection on the tested fixtures. The capture leaves the individual
arithmetic operations responsible for the differences unresolved.

The [private Vulkan tap](../../scripts/research/qwen_tts_frame/native-logits-a8a7716.patch)
captures the first two frames with `--dump`. For a captured directory,
pass `--frame-index 0` or `1` and `--native-logits` to the replay command.
The reader verifies the associated acoustic code row.

## Acoustic prefix speculation

An offline screen compared previous-frame copies, recent same-semantic-ID
copies and held-out same-semantic-ID candidates against 162 saved native
frames. On the 66 frames at temperature 0.9, no candidate reproduced all
15 codes. The held-out prompt candidate matched 11 leading codes in total,
or 0.167 per frame. At a hypothetical linear cost of 25.3 ms per 15 codes,
that represents about 0.28 ms per frame before verification and repair.
The native runtime already evaluates a whole frame in one Vulkan graph.
The greedy run yielded 56 full previous-frame hits in 96 frames, including
22 hits from one sequence of 23 identical frames.

The private full-frame, native-logit and speculation receipts are in
`codepredictor-full-frame-onnx-v1`, `codepredictor-native-logits-capture-v1`
and `codepredictor-acoustic-speculation-offline-v1.json` in the same local
evidence directory. Halogen and the voice services continued serving.

## Packed Vulkan gate and up projections

The [private Vulkan patch](../../scripts/research/qwen_tts_frame/native-packed-ffn-a8a7716.patch)
stores the two Q8_0 matrices as consecutive output rows and uses one
projection followed by packed SwiGLU. On the ordinary Vulkan matvec path
this removes one dispatch per layer and codebook, or 75 per frame. The
model still reads the same weight values. The option defaults to off.
`QWENTTS_CODEPRED_PACKED_FFN=1` enables it on compatible Vulkan weights.

The private CLI confirmed packing on all five layers. All six captured
logit matrices and all three file-level code matrices and WAV files
matched the split implementation byte for byte.

The same private `a8a7716` HTTP server binary ran split, packed, then split
again under Halogen 0.20.7 decode overlap. The Windows client sent the
same 8,192-token non-repetitive novel prefix with cache off, thinking off
and 128 generated tokens. Speech started at the first visible text.
Each arm included a separate speech prime and one excluded warmup pair.
The table averages three measured pairs per arm.

| Vulkan TTS | TTS predictor ms/frame | TTS complete HTTP, s | Halogen API prefill tok/s | Halogen API decode tok/s | Native MTP | Halogen first text to EOF, s | Halogen complete HTTP, s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Split before | 25.345 | 1.324 | 2,052.81 | 49.645 | 192/291 (65.98%) | 2.578 | 6.628 |
| Packed | 25.229 | 1.303 | 2,064.96 | 49.864 | 192/291 (65.98%) | 2.567 | 6.602 |
| Split after | 25.154 | 1.312 | 2,013.92 | 49.449 | 192/291 (65.98%) | 2.590 | 6.731 |

Halogen text matched byte for byte across all twelve pairs. Speech PCM
matched by trial index across the three arms, and all pairs overlapped
from first PCM through part of text decode. The packed stage mean falls
between both controls. Windows measured 0.45% and 0.89% shorter Halogen
text delivery than the two control means, with overlapping trial ranges.
The benchmark starts speech after prefill and the phase-clock rates are
descriptive. The observed differences leave the option experimental.

The first attempt stopped on a live-request guard during the packed
warmup. The completed run verified gateway completion and cancellation
counters around each owned request. The minimum sampled physical or
commit reserve was 23.78 GiB. The private server was closed and the public
Halogen, TTS, ASR and Native endpoints reported ready afterward.

Raw evidence is under `tts-decode-overlap-packed-ffn-v2`. The paired
analysis SHA-256 is
`5f3d4ae9fce958c7c96a401f82f2763b840d9050c18de559588c1ff344a13570`.
