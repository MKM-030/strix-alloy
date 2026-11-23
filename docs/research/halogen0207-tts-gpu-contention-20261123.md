# Halogen 0.20.7 and native TTS GPU contention

Moving native speech synthesis from Vulkan to CPU slowed down both Halogen
text delivery and speech synthesis in a paired 8K test. Production TTS
continues to use Vulkan.

Five Windows admission observations report 52–96% Compute activity
for the process that serves Qwen3-TTS on port 8862. Its verified birth
precedes those saved samples. All five occurred around measuring
requests, during admission or settling. They identify a competing
compute workload. An effect on Halogen request time needs a paired
overlap measurement.

Across 571 retained Halogen 0.20.7 admission receipts, 1,153 of 1,187
GPU observations contain no nonzero engine counter. The 34 remaining
observations include 18 Copy counter rows attributed to Windows System
PID 4 by the counter. The largest observed Copy value is 3%. The
archived ETW trace has 180 Copy spans and lacks a complete Linux owner
join. Current Windows driver image hashes still match the pinned
namespace proof. That proof identifies field meanings. The Copy spans
still require actual ownership evidence.
[Earlier Copy attribution implementation](halogen-copy-attribution-implementation-20261007.md)

## CPU and Vulkan speech synthesis

Three new private TTS instances used native Qwen3-TTS Base 0.6B Q8_0,
the same 12 Hz Q8_0 codec, the same synthetic German reference and
one fixed sentence with seed 42. Vulkan preceded and followed the
CPU arm. Each arm excluded one warmup and measured three requests.
The Windows client timed the first complete PCM16 sample and the
response EOF. The native log confirmed the selected backend.

| Backend | Mean first PCM | Mean complete HTTP | Mean real-time factor |
| --- | ---: | ---: | ---: |
| Vulkan before | 44.38 ms | 0.626 s | 0.230 |
| CPU | 255.78 ms | 1.814 s | 0.687 |
| Vulkan after | 44.24 ms | 0.613 s | 0.225 |

All three warm CPU requests completed faster than playback duration.
CPU synthesis took about 2.9 times as long as Vulkan and delayed first
audio by about 0.21 s on this fixture. The matching Vulkan requests
produced identical PCM across both control arms. The CPU requests
produced a different PCM hash. Audio quality and speech recognizer
agreement were outside this component comparison.

The regular Halogen, TTS, ASR and Native services remained available
during collection. The three private TTS processes closed afterward.
The lowest sampled physical or commit reserve was 23.92 GiB.
The native CPU mode is selected with process-local
`GGML_BACKEND=CPU`; the test changed only the private server environment.

The local evidence is retained under
`server/.local/halogen-update-20261122/primary0207/tts-cpu-offload-prep-v1`.
The component summary SHA-256 is
`e6fa717bb309424e9c87e228d79755a3a67abce4c7922b3756bafc5c4d668162`.

## Halogen decode with concurrent speech synthesis

The same speech fixture started when a Windows client received the first
visible text from Halogen. Each arm ran one excluded warmup pair and three
measured pairs. The same Halogen 0.20.7 process served all twelve pairs on
port 8840. Each request contained 8,192 actual novel-prefix input tokens and
returned 128 tokens with greedy MTP, cache off and thinking off. The client
used Windows QPC for both streams. The TTS request used the fixed German
phrase throughout, so its content and length budget were held constant
across arms.

| TTS backend | Halogen API prefill (tok/s) | Halogen API decode (tok/s) | Native MTP acceptance | First visible text to Halogen EOF | Halogen HTTP total | TTS first PCM | TTS HTTP total | Both streams complete |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Vulkan before | 2,067.06 | 49.83 | 65.98% | 2.569 s | 6.596 s | 107.44 ms | 1.329 s | 6.596 s |
| CPU | 2,047.16 | 48.34 | 65.98% | 2.651 s | 6.719 s | 403.85 ms | 2.827 s | 6.895 s |
| Vulkan after | 2,071.91 | 50.14 | 65.98% | 2.553 s | 6.570 s | 103.05 ms | 1.307 s | 6.570 s |

These are means of three measured pairs per arm. Native MTP accepted 64 of
97 proposals in every trial, or 192 of 291 per arm. All twelve Halogen
outputs were byte-identical. Windows measured 3.20% and 3.82% longer text
delivery on CPU relative to the preceding and following Vulkan arms. Both
streams took 4.54% and 4.96% longer to finish. First PCM arrived during
Halogen decode in all twelve pairs. Vulkan speech completed before Halogen
in all pairs and CPU speech finished afterward. The mean speech real-time
factor was 0.503, 1.071 and 0.495, respectively. The lowest sampled physical
or commit reserve was 23.50 GiB.

The native TTS log reports flash attention on for Vulkan and off for CPU.
The paired results describe the complete backend paths under overlap.
The benchmark begins speech synthesis after prefill, includes no no-speech
control, and produces no per-engine GPU Copy attribution. API rates are
descriptive because the native WSL phase clocks can diverge from Windows
elapsed time. The paired Vulkan controls matched PCM hashes by trial, while
CPU produced different PCM. Speech quality was outside the comparison.
[Native phase clocks](halogen0207-phase-clock-audit-20261123.md)

The overlap run retained the per-trial SSE events, PCM, QPC timestamps,
backend logs and summary in `tts-decode-overlap-run-v1` below the evidence
directory above. The overlap summary SHA-256 is
`c7f221456cee43707ab4f338ba8279d8241e7a95e4c7921b84e189f2e7e0a6f7`.

## Halogen with the speech process idle or synthesizing

In a separate paired run, one private Vulkan TTS process stayed loaded
throughout. Starting its synthesis on the first visible Halogen token
extended the interval from first text through response EOF by **342 ms**
on average. The difference was 329–351 ms in each measured pair.

| TTS state | Halogen input / output | API Prefill tok/s | API Decode tok/s | Native MTP | First text through EOF | Full HTTP |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Loaded and idle | 8,192 / 128 | 2,042.39 | 56.68 | 192/291 (65.98%) | 2.252 s | 6.312 s |
| Synthesizing during text delivery | 8,192 / 128 | 2,016.82 | 49.20 | 192/291 (65.98%) | 2.594 s | 6.687 s |

Both arms used the same Halogen 0.20.7 serving process, frozen novel
request, greedy MTP, cache off and thinking off. One warmup pair was
excluded. Three measured pairs alternated order. All eight Halogen
responses matched the exact reference. Every synthesized PCM matched
the corresponding ordinal in both earlier Vulkan runs. Those ordinals
contain 37, 34, 31 and 34 frames. The separate speech warmup is outside
the pairs. An initial attempt ended before sending a Halogen request
because it applied a measured ordinal's audio hash to that warmup.

Windows QPC measured both HTTP intervals. API rates retain the native
phase clock's scope. Removing all synthesis work from this particular
overlap window corresponded to **13.18% less delivery time**. The idle
arm provides a reference for partial offload, whose actual effect still
requires a paired measurement. The minimum sampled reserve was 26.99 GiB.
The private TTS process closed and the normal services remained ready.

Raw SSE, PCM, window timestamps and the terminal record are under
`server/.local/halogen-update-20261122/primary0207/tts-cpu-offload-prep-v1/tts-idle-overlap-paired-v2`.
The summary SHA-256 is
`f337f1ed72c5e03bc1df8ebdb7a4697590080cc8983b56848030d88dbd2d0a8b`.

## Packed Q/K/V under the same overlap

An isolated `a8a7716` build packs the three Q8_0 projections in each of
the five CodePredictor layers into one matrix. Q, K and V are views
with the packed row stride. The original runtime DLLs and weight bytes
are preserved. The private option is `QWENTTS_CODEPRED_PACKED_QKV=1`.
The CPU layout test covered three input shapes. Both Vulkan modes
reproduced six native logit matrices, complete acoustic codes and WAV
files byte for byte across three synthetic voice fixtures.

| Q/K/V projection | Predictor per frame | TTS HTTP | Halogen API Prefill tok/s | Halogen API Decode tok/s | Halogen first text through EOF | Halogen HTTP |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Split before | 25.28 ms | 1.324 s | 2,065.28 | 49.44 | 2.581 s | 6.599 s |
| Packed | 23.47 ms | 1.257 s | 2,069.68 | 49.50 | 2.577 s | 6.585 s |
| Split after | 25.39 ms | 1.319 s | 2,042.63 | 49.43 | 2.581 s | 6.641 s |

Each arm excluded a warmup pair and measured three pairs on the same
8,192-input, 128-output Halogen workload. All 12 Halogen streams had
identical outputs and MTP counts. Each measured arm accepted
192/291 head drafts (65.98%). PCM matched byte for byte at each ordinal.
Verification checked private Vulkan startup, exact speech frames, raw
response bytes and timestamps. The minimum sampled reserve was 27.07 GiB.

Packing cut predictor time by **7.15–7.56%** and TTS HTTP time by
**4.71–5.03%** against the two controls. The first-text delivery interval
improved by **3.6–4.0 ms**, about 0.15%, and the average of API Decode
changed by about 0.07 tok/s. This establishes a speech-stage speedup
with a small measured change in Halogen delivery. Production uses its
existing Vulkan build. Halogen, ServiceNow, Native, TTS and ASR passed
readiness after the private processes closed.

Local evidence is under
`server/.local/halogen-update-20261122/primary0207/tts-cpu-offload-prep-v1`.

| Artifact | SHA-256 |
| --- | --- |
| Packed Q/K/V patch for the private build | `11994f16dc5f828b1429045dee8afff93826c1d0b06723c955e1dc77bc4041f9` |
| Split Vulkan parity | `1b00cc08cf4cc04b596eb6d98843bc6dd405031d8d394a5b73d46be81220c52e` |
| Packed Vulkan parity | `92e2c465e85d3ba8443ec3fbf052979299cd9be0ec64b382454c326dcaf879bb` |
| Packed overlap raw summary | `d8c68e594750ab67ac1882b6eaa15741feb4a1a061d48be11f70439d5954ca1f` |
| Packed overlap paired analysis | `972032857a931ae488781ee149ab4ac8bd6c2205994afa4a37367f8c02551e1f` |

## Candidate stage for NPU evaluation

The matching native TTS logs identify the acoustic CodePredictor as the
largest measured stage during Vulkan and Halogen overlap. The logged frame
counts match the PCM lengths. The means below use the three measured pairs
per backend and exclude both warmups. Stage times include native waits.

| TTS backend | CodePredictor per frame | Audio codec per frame |
| --- | ---: | ---: |
| Vulkan before | 25.29 ms | 3.85 ms |
| CPU | 34.27 ms | 21.82 ms |
| Vulkan after | 25.28 ms | 3.37 ms |

The pinned TTS build `9c37f4c` keeps the batch-one Talker output as 1,024
FP32 values on the GPU. An independent predictor would receive those 4 KiB,
the first token and existing sampler inputs, then return 15 acoustic IDs.
The predictor would keep its own short KV state. The existing Vulkan
readback also submits a queue operation and waits on a fence, even for
host-visible memory. A candidate must include that cost, preserve all 15
seeded decisions and beat approximately 25.3 ms per frame during overlap.
The measured audio codec has a much smaller latency budget.

The installed TTS path has no compiled NPU graph for this Q8_0 predictor and
sampler. AMD documents specific ONNX formats for its Windows NPU provider.
Compiling a new graph and checking its exact codes and PCM would be necessary
before a paired throughput test. [AMD Windows ML model support](https://ryzenai.docs.amd.com/projects/WinML/en/stable/model_support.html)

## Native output codec as a separate NPU candidate

The output codec consumes the acoustic IDs that the Windows TTS process
already owns, after the CodePredictor has finished. Moving this stage
would use the existing host-owned IDs and return PCM to the same process.
The candidate's end-to-end budget is the **3.37–3.85 ms per acoustic
frame** measured for Vulkan during Halogen overlap.

An offline exporter built static ONNX versions of the first causal DAC
transpose convolution for one, two, four and eight acoustic frames. It
uses the installed tokenizer GGUF's 1,536-to-768 weights and a kernel
width of 16, stride 8, with the original causal carry. CPU ONNX Runtime
matched the pinned GGML formula within **9.54 × 10⁻⁷** on synthetic
activations with nonzero carry. One-, two- and four-frame blocks matched
serial ONNX calls bit for bit. The eight-frame block had rounding
differences. This experiment evaluates one operation with FP32 operands.

The complete streaming codec retains **8,954,496 bytes** of FP32 state
per stream across 16 K/V buffers and 21 convolution or carry buffers.
Reading state back and sending it again would move about 17.9 MB per
call. If the provider can keep state device-resident, the interface needs
588 bytes of IDs and control inputs per acoustic frame and returns 7,680
bytes of FP32 PCM. Generating the RoPE sine and cosine tables on the host
adds 256 bytes per frame and avoids the provider's BF16 Cos gap.
[AMD supported operators](https://ryzenai.docs.amd.com/en/latest/ops_support.html)

The retained 141-frame acoustic-ID fixture crosses the 128-row K/V ring
boundary. The archived WAVs used buffered output. A full comparison
requires a PCM reference from the streaming path for the same IDs,
including the ring transition. WinML may convert a provided FP32 graph
to BF16, so full PCM parity and the provider's state placement require
their own measured proof. The component run used CPU, and the full NPU
codec and its effect on Halogen throughput remain unmeasured.
[AMD Windows ML model support](https://ryzenai.docs.amd.com/projects/WinML/en/stable/model_support.html)

The local receipt `npu-tts-codec-carried-convtranspose-offline-v1/codec-carried-conv-receipt.json`
has SHA-256 `cc895ea3fd0b53186dbd6f613ae5a8c97cab09389add420d27125a570b4767a5`.
The full state and operator inventory in the same directory has SHA-256
`79742edfa1475cbbbfa33ab5b85c6bff6bc68a686ed6560dd03bc7b808333d7d`.
The separately prepared `npu-tts-codec-frozen-stream-reference-v1` runner
links the retained native codec and covers both the production chunk
schedule and one frame per step. Its preparation verified the fixture
and runtime identities and passed 14 offline lifecycle and output checks.

## DAC with finite input history

The native GPU front can retain the codec transformer and its K/V ring
while the NPU runs only the waveform decoder (DAC). An offline dependency
check across all 480 output phases found that the DAC needs the last
**20 actual rows** of its 1,024-wide input. The host can keep those rows in
80 KiB per stream. Each invocation prepends them to the new rows and crops
the first 9,600 samples. Six offline tests covered the tight history bound,
the native start of stream, mixed widths and exact output on a synthetic
causal graph.

The one-frame call exchanges 105,984 bytes with the NPU provider. The
eight-frame call exchanges 274,432 bytes and processes 1.625 times the
number of new DAC input rows. The GPU front would also download 16 KiB
per new frame. Preserve the 1/2/4/8 streaming schedule to avoid waiting
for seven extra frames before the first audio chunk. The Vulkan budget
for the whole eight-frame codec call during overlap was about 27–31 ms.

The proposed capture reads the native FP32 tensor between the streaming
upsampler and the DAC after graph completion. The captured rows can test
explicit-state and cropped-history ONNX against the native streaming PCM.
The dependency proof covers input history. Precision, VitisAI placement,
transfer time and any effect on Halogen Decode still need measurement.
The offline preparation receipt `npu-tts-codec-dac-overlap-prep-v1/preparation.json`
has SHA-256 `456c13e9ee25ea0f6fba7c39db903905b7670aa5f92d8c91fc1b06ac9a204733`.

### Vulkan reference for the two chunk schedules

A private Vulkan run decoded the same 141 reference frames and 33
generated frames in each arm. Both arms produced 63,360 samples at 24 kHz
and finished at cursor 174. Reconstructing PCM16 from the saved FP32 in
each arm reproduced its native PCM bytes exactly. Comparing the two
schedules gave different values in 41,111 PCM16 samples, with a maximum
absolute difference of 525 and RMS difference of 27.62 sample units.
All FP32 samples differed, with a maximum difference of 0.0160262.

Use the stock chunk schedule as the production reference. The width-one
stream supplies its own reference for a width-one graph. The first render
attempt ended during a health check and produced no terminal audio. The
completed run used the same native executable and fixtures with a
three-second overall health deadline and stage-specific timing. The
lowest physical reserve in either completed arm was 29.71 GiB. Halogen
and the Voice services passed readiness after both renderer processes
closed. NPU placement and throughput remain unmeasured.

The local `vulkan-seeded-42-v2-bdicvgwv/comparison.json` receipt has
SHA-256 `389c1790f4c7d64851dd5688ad0cfc188e15a6c5a174d4f8544bf6e9ae2e9e42`.

A private build captured the FP32 inputs immediately before the DAC on
the normal chunk schedule. It produced **26 chunks and 2,850,816 bytes**,
covering staging and generated audio. The final FP32 and PCM16 arrays
matched the uninstrumented stock reference byte for byte. The captured
rows provide the native input for the CPU exporter and its parity checks.
The additional tensor readback alters the capture's timing, so the run
qualifies the fixture for correctness.

The captured feature data has SHA-256
`a04c3a29d5306c1fb290d79db7695bb12e36428764566dbccf6021c1e8e4faf7`.

### CPU execution of the first native frame

The first width-one ONNX export used 20 retained staging rows and four
new rows from the production trace. The full graph passed the ONNX checker
and ran on one CPU thread with graph optimizations disabled. After the
9,600-sample crop, 376 of the 1,920 PCM16 samples differed by one integer
unit. The first difference was at zero-based index 5. The maximum FP32
error was 2.74646 × 10⁻⁵ and the RMS error was 7.63838 × 10⁻⁶.

The same FP32-to-PCM conversion reproduced the native PCM bytes from the
recorded native FP32 samples. The exported computation failed exact PCM
parity. The first-frame CPU result is retained as `width1-native-k463hna9/cpu-check.json`,
SHA-256 `1ffd19bd661e3e8f7734b4d8ecbd6f237b5f6158e812bdbf384649096129e8bd`.

## Talker timing and a resident NPU state

The 28-layer Talker is a separate stage from CodePredictor and the DAC.
In the three measured 8K Halogen overlap pairs it took 310.9, 283.3 and
308.6 ms for 34, 31 and 34 audio frames. That is **301 ms per utterance**
and **9.12 ms per frame**. The separate excluded Vulkan prime had 33
frames at 4.45 ms each. The native stage times include waits. The
342-ms difference in Halogen delivery time belongs to the comparison
between idle speech and full synthesis.

The pinned speech implementation loads the Talker and CodePredictor
on the same backend and keeps their 4 KiB FP32 hidden row on the device.
Its public interface exposes whole synthesis. The current 4,096-position
FP32 Talker KV allocation is 896 MiB. Copying the active KV state out
and back at each frame would move an estimated 66–81 MiB per frame on
the observed trajectory. A resident external state would instead need
the Talker's MRoPE, sampler, code feedback and a consumer for its hidden
row. [Pinned speech API](https://github.com/ServeurpersoCom/qwentts.cpp/blob/9c37f4ce84c779930e1c1117ce6d8f71fca37433/src/qwen.h)

AMD's documented WinML NPU transformer formats cover BF16 conversion
and A16W8 QDQ. Exact execution of the native Q8_0 Talker and FP32
state remains unqualified. Vision is disabled in the regular Halogen
profile, ASR runs on CPU, and the NPU add-on model IDs handle separate
requests. The assessment used retained Vulkan data and source files.
[AMD model formats](https://ryzenai.docs.amd.com/projects/WinML/en/stable/model_support.html)
· [Halogen NPU interfaces](https://github.com/peonist-ai/halogen-flash-server/blob/dea807d22a638c67553abea876344a8192054a94/docs/NPU.md)

The local receipt `sources-20261123/talker-npu-overlap-bounds-v1.json`
binds the original overlap logs, timing arithmetic and source files.
SHA-256 `41088cc8ee3a8e28d45ae035cd515663d54a53f4fe37c8867c6e552f0681f95d`.

### Exact Q8_0 representation on CPU

A CPU ONNX Runtime probe reconstructed **122,880** real FP32 weight
values from the Talker file exactly, using either blocked dequantization
or an explicit cast and multiply. The 84 sampled output rows required
per-block scales for exact reconstruction. A BF16 conversion changed
118,956 of those weight values.

Encoding each signed Q8 value as two W4 components reconstructed the
393,216 sampled weights exactly. Applying two separate matrix products
changed 21,747 of 22,656 FP32 outputs on synthetic dense samples, with
a maximum absolute difference of 6.44 × 10⁻⁶. Dense limb products also
changed outputs, which isolates a difference in the order of
accumulation. The sampled 64-way argmax values matched. The pinned
batch-one Vulkan path uses FP32 input, groups products before scaling
each Q8 block contribution and then reduces the lane partials.
Exact reproduction of that order and native projection parity on the
NPU remain open. [ONNX blocked dequantization](https://onnx.ai/onnx/operators/onnx__DequantizeLinear.html)
· [AMD operator support](https://ryzenai.docs.amd.com/en/latest/ops_support.html)

The local `sources-20261123/talker-q8-format-proof-v1.json` receipt
binds the CPU reproduction, pinned original weights and test arithmetic.
SHA-256 `0d167fcb13c148e3b2787c83303b623722a1fd9502db2cb281be38d54c825f74`.

## Warm cloned-voice reference cache

An opt-in qwentts.cpp cache reduced mean time to first PCM from
**44.36 ms to 39.98 ms** and mean time to audio EOF from **610.95 ms to
602.21 ms**. The cache reuses the original FP32 projection of a cloned
voice's reference codes. The broader `PromptBuild` stage fell from a
mean of 6.75 ms to 2.47 ms.

| Mean latency | Off before | On | Off after | Change vs. mean Off |
| --- | ---: | ---: | ---: | ---: |
| Request to first PCM | 44.11 ms | 39.98 ms | 44.60 ms | −4.38 ms (−9.88%) |
| Request to audio EOF | 615.03 ms | 602.21 ms | 606.86 ms | −8.74 ms (−1.43%) |
| `PromptBuild` | 6.70 ms | 2.47 ms | 6.80 ms | −4.28 ms (−63.46%) |

All three windows used the same rebuilt qwentts.cpp executable at
`9c37f4c` and the Vulkan DLLs from the running TTS service. Each window
registered the same 141-frame synthetic reference, excluded one warmup
and measured three requests with identical text, seed 42 and a 96-token
cap. All 12 PCM responses matched the corresponding historical Vulkan
responses byte for byte. The lowest reported physical or commit
reserve was 24.93 GiB. Halogen generation was idle throughout, and the
regular Halogen, Voice, ASR and TTS listeners stayed online.

The result measures speech latency for this fixture. In the earlier
overlap test, the sample standard deviation for Halogen delivery was
9.28 ms over three stock overlap runs. A Halogen Prefill, Decode or MTP
effect from this cache remains unmeasured.

The patch, build, protocol and raw evidence are retained under
`server/.local/halogen-update-20261122/primary0207/tts-reference-projection-cache-prep-v1`.

| Evidence | SHA-256 |
| --- | --- |
| Source patch | `b5500c27fee8e6e7e06674fe52231136d1bfaa5fbb305c7464e3756e86341ed7` |
| Component measurement | `9884da2a14d119fede5cffec3093cb46cd3d133187dac090d54b83768ae7787e` |
| Independent PCM and timing replay | `6bab2a27cf575eba0caceb5b370e01a6650f28508671f1fa5192f6ecfa32e46c` |
| Post-test service readiness | `0d622033afeeb0d8353a94520d696eba31642aed427c21534468a32fc6e83b13` |

## Native CPU codec parity

An isolated qwentts.cpp render selected the native CPU codec and fed it
the same 141 reference frames and 33 generated acoustic frames as the
retained Vulkan control. It skipped the Talker and used the same packet
schedule. The two renders both produced 63,360 samples at 24 kHz.

The CPU backend changed **41,351 of 63,360 PCM16 samples** (65.26%).
The first difference occurred at sample index 5, and the maximum
absolute difference was 878 PCM16 units. The FP32 output also differed.
An independent read of the two PCM files reproduced the difference
count, first index, and maximum. This candidate fails exact PCM parity.
The 3.375 s CPU observation includes process startup, model load,
reference priming, rendering, and writing. Halogen serving rates were
outside this component measurement.

The regular Halogen and Voice listeners remained available. Raw
evidence is in `tts-reference-projection-cache-prep-v1/native-cpu-codec-stock-v1`
under the local evidence directory above. The comparison SHA-256 is
`dc298708a8372eff77253d46f3497964d2719f6e2ce3a9865be6ffc5b0449dc1`.
