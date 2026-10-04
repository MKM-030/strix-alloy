# Resident NPU expert path: source-only feasibility — 4 October 2026

No additional static-bank prototype is justified for an end-to-end optimization
at this point. A Gather-free, initializer-backed NPU expert graph is already
locally qualified, but its retained mean is **1.504985 ms** (minimum 1.426900 ms).
The live native complete MTP MLP event bracket averages **0.404611973 ms**.
These fixtures and timing scopes differ; the comparison establishes no speed
advantage for the proposed offload. Merely admitting a different graph would
not establish an optimization.

## One supported resident design, already measured

The defensible Gather-free implementation is a persistent fixed-top10 graph
with `W_gate_up` and `W_down` as constant initializers, runtime
`x: FP32[1,2560]` and `routing_weights: FP32[10,1,1]`, and output
`y: FP32[1,2560]`. The local builder
[`halogen_npu_expert_onnx.py`](../../scripts/benchmarks/halogen_npu_expert_onnx.py)
implements this at `build_graph` (lines 41–85). Its retained
`top10-routing-20261004` compiler context claims both weight constants and all
eight operators in one `VAIML` / `stx` / `runnerType=hw` partition. Strict NPU
replay passed 100 measured calls with only `VitisAIExecutionProvider` Node
events; session initialization, including compilation, took 32.704238 s.
See the [fixed-top10 report](halogen-npu-top10-20261004.md).

This graph already removes per-call weight inputs. Its graph constants occupy
196,608,000 bytes (187.5 MiB FP32). Input/output payloads total only 20,520 bytes
per call: 10,240-byte input, 40-byte coefficients and 10,240-byte output. Packed
provider weights and workspace are additional, unmeasured resident memory.
The measured 1.505-ms call cannot be explained by a 187.5-MiB runtime weight feed:
there is no such feed in this graph.

To use fixed graphs with live routing, a persistent cache would bind checkpoint,
provider, graph/data/context identities and exact expert sets, permute
coefficients into each graph's order, and send misses to the original GPU path.
Graph loading/compilation belongs outside the steady-state call but must be
charged on misses. The live trace provides poor support for a small cache:
64 trained resident experts covered zero complete held-out calls; 128 covered
2/37. Ten per-expert sessions would avoid set combinations but add dispatch and
reduction boundaries with no local latency qualification. Neither design has
evidence of a benefit over retaining the GPU MLP.

## Why a masked bank or different node is insufficient

A Gather-free 16-expert bank could compute all experts and accept a bank-ordered
coefficient vector with zeros for unselected experts. Its constants would be
150 MiB BF16 or 300 MiB FP32, before Cast folding, packed artifacts and workspace.
It would perform 16 expert projections instead of ten; zero output coefficients
do not establish conditional execution. Extending this to 512 experts needs
4.6875 GiB BF16 or 9.375 GiB FP32 constants and computes 51.2 times the selected
expert work. These are graph-storage/work counts, not measured provider memory
or runtime forecasts. Replacing Gather with runtime Slice also leaves changing
MatMul operands; no retained strict Slice placement or fusion evidence supports
that substitution. Static slices can instead be exported as fixed initializers,
which returns to the already measured fixed-graph path.

The successful fixed-top10 mean is about 3.72 times the native bracket. It would
need over 73% less call time merely to equal that bracket, before Windows/WSL
handoff, GPU synchronization, BF16 conversion, remaining MLP work and output
injection. The native bracket includes routing/shared work absent from the NPU
expert graph, and includes waits/enqueue gaps/observer overhead; it is not exact
uninstrumented latency. The retained NPU input/router fixture is synthetic and
fixed, rather than the captured live routes. No accepted-token or complete-MLP
quality gain follows from either measurement.

## Exact installed capability evidence

The installed package manifest at
`C:/Program Files/WindowsApps/MicrosoftCorporationII.WinML.AMD.NPU.EP.1.8_1.8.75.0_x64__8wekyb3d8bbwe/AppxManifest.xml`
identifies version 1.8.75.0 and registers `VitisAIExecutionProvider` plus
`RyzenAILightExecutionProvider`. The package's `readme.txt` contains license
terms, not an operator, residency or latency contract. Alternate provider
presence alone does not qualify this expert graph or a faster execution path.

Installed ORT Python source
`C:/AI/runtimes/winml-npu/Lib/site-packages/onnxruntime/capi/onnxruntime_inference_collection.py`
documents `run_with_iobinding` (line 425), `bind_ortvalue_input` (925),
`bind_ortvalue_output` (983), and `OrtValue` creation with generic NPU device
types (1040–1113). Those are binding/allocation APIs. They do not document
VAIML importing Halogen's Linux HIP allocation, retaining mutable runtime expert
weights on device, bypassing provider conversion, or a direct cross-WSL state
handoff. No session/provider call was made to infer such support.

| Local evidence | SHA-256 |
|---|---|
| Fixed-top10 NPU receipt | `dd97e2594369a920d3bec1e2fe68e632255384dde3e47bc50494d30b133a3ec0` |
| Fixed-top10 compiler context | `4885438623b92260c7c9af7365b8ff4bfa847a7b01b93c374293e280bd64e078` |
| Installed provider manifest | `0a1e15844043769d095bc70a808bbdff9d30c389182b61ddb7d61a7b6a8809a3` |
| Installed ORT binding source | `91b4233708e960df90e069ae03fea58b83e313c90ad4afd79ad05ae84ccf91a7` |

This task read local sources, manifests and retained receipts only. It created
this report, with no new prototype, graph compilation, provider session,
checkpoint decode, large allocation, hardware/storage job or commit. Existing
probes and reports remain frozen. Promoting the synchronous MLP replacement
examined here requires evidence of a different execution mechanism with a
credible sub-0.4-ms total replacement budget. A full draft-head offload with
GPU/NPU overlap is a different scope; it has not been implemented or timed.
