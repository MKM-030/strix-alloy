# Laya/Jev and a Qwen NPU drafter — 4 October 2026

**Recommendation:** investigate a small drafter trained for the actual Qwen3.8-Flash-Next target and native verification. Use a decision model separately for narrow tasks that can avoid invoking Qwen. No Laya/Jev model has been installed, trained or benchmarked here; this is a feasibility assessment, not a measured speed gain.

## What the published models do

Laya uses a bidirectional encoder and a decision head to score supplied options. Its English checkpoint has 421M parameters and a 512-token question budget; multilingual has 322M parameters, normally 1024 tokens, with an encoder extension up to 8192. The reported 32.8/39.5 ms on a T4 are decision timings, not Qwen token-generation rates or AMD NPU results. [Official repository](https://github.com/NandhaKishorM/laya), [model card](https://huggingface.co/convaiinnovations/laya).

Jev is documented as a hosted typed-decision API. The reviewed official pages provide no local weight/export contract. TypeSafe explicitly warns that forcing generation through repeated choices performs poorly and slowly. Its private architecture should not be inferred from Laya. [Official model interface](https://docs.typesafe.ai/models), [generation limitation](https://docs.typesafe.ai/model-jaggedness/jev-1.13#generation).

Laya's current ONNX exporter uses opset18 and dynamic batch, sequence and option-marker dimensions. Its optional INT8 path is CPU-oriented dynamic MatMulInteger, and the author records substantial decision drift. This export is not a qualified Ryzen AI NPU artifact. [Exporter](https://github.com/NandhaKishorM/laya/blob/main/scripts/export_onnx.py).

AMD's separate Windows ML VitisAI transformer documentation supports FP32 with compilation to BF16 or QDQ A16W8. The RyzenAI Light/OGA LLM path uses prepared models and has a different deployment contract. Neither source establishes that arbitrary Laya or diffusion-drafter graphs execute on this machine. [Windows ML formats](https://ryzenai.docs.amd.com/projects/WinML/en/latest/model_support.html), [OGA flow](https://ryzenai.docs.amd.com/en/latest/hybrid_oga.html).

## A custom drafter is a different training task

The useful training signal is Qwen's behavior on contexts: target tokens, probabilities where available, and optionally internal features. Static weight fingerprints identify a checkpoint; they do not encode the evolving context needed to predict its next token. A very small model can learn an approximation, but size and quantization trade against accepted draft length.

EAGLE-3 uses target features to predict tokens. DFlash uses target features to condition parallel token-block predictions, trained against a frozen target. This is a concrete precedent for the proposed one-pass accelerator. [EAGLE-3 paper](https://arxiv.org/abs/2503.01840), [DFlash paper](https://arxiv.org/abs/2602.06036).

The current official DFlash support list includes Qwen3.8-27B; it does not explicitly list our Flash-Next target. That checkpoint is not an interchangeable head for Halogen v2. A supported tokenizer, proposal insertion, batched verification and state commit/discard are still needed. Feature-assisted designs such as EAGLE-3/DFlash additionally need a target-feature interface; a conventional token-only drafter does not. [DFlash implementation and supported targets](https://github.com/z-lab/dflash).

Use Qwen token IDs for a first implementation. Keep the drafter resident, transfer bounded features/proposals, and start with a small block. Preserve target greedy decisions or the appropriate sampling correction; confidence alone cannot replace target verification. Quantized drafting can preserve target output quality when verification is correct, while still losing speed through rejection. [Speculative-decoding algorithm](https://arxiv.org/abs/2211.17192).

## The local performance threshold

The retained matched stock control is 47.060 tok/s with native MTP, versus 35.942 serial tok/s. Thus the new path must beat existing MTP, not just serial generation. Stock MTP amortizes to 21.249 ms per generated token. Compare total drafting, IPC, synchronization, verification, rejection and rollback time divided by actual committed tokens. Four committed tokens per round permit less than 84.9979 ms total round time; this is arithmetic, not a predicted NPU result. Also compare complete request wall and first-token latency.

The observed native count1 head bracket was 3.32356 ms and its MLP bracket 0.404612 ms. These are instrumented call scopes, not exact uninstrumented per-output-token costs. Moving only the MLP provides limited room for overhead. [Timing receipt](halogen-mtp-full-head-event-timing-20261004.md), [matched control](../benchmarks/halogen9h-optimization-20261004.md).

| Mechanism | Useful role | Performance/quality boundary |
|---|---|---|
| NPU decision model | Route a narrow classification task away from Qwen | Reduces total work; does not increase Qwen's decode rate |
| Target-trained NPU block drafter | Propose several token IDs for GPU verification | Requires acceptance and complete wall-time evidence |
| Exact prefix hashes | Locate compatible saved prefix/model state | Validate tokens, model, positions and cache configuration |
| Vectors | Retrieve relevant text or propose a cached continuation | Similarity is not exact state/output equivalence |
| SSD | Cold loading, persisted caches, asynchronous exact expert-ID prefetch | Avoid synchronous weight loads on each drafting step |

Vectors can reduce prefill work by selecting a smaller context, but that changes the supplied information. An exact prefix cache can reuse previously computed state. Neither mechanism proves faster processing of the identical cold 128K/260K prompt. Hashes do not replace matrix computation.

The retained direct SSD placement experiment took 196.40 s versus warmed stock 180.124 s and was rejected. It supplies no positive streaming result. A predictive expert prefetcher is possible in principle, but its misses must fall back safely and the actual router coefficients still govern computation. [SSD comparison](../benchmarks/halogen0162-lookup-direct-results-20261004/README.md), [routing evidence](halogen-mtp-routing-live-20261004.md).

Before custom training, establish the supported target integration and measure a prepared drafter's full round cost. An unrelated prepared graph can establish runtime costs but cannot establish accepted tokens per round or a gain. No prepared Flash-Next-compatible NPU drafter is established here. For a semantic sidecar, establish NPU execution and held-out decision quality independently. This keeps a plausible research direction separate from the current unfinished native NPU MTP implementation.

## Confirmed Halogen integration boundary

The public Halogen 0.16.2 deployment sources at
`7f31bbd4021f217a1be9776bdb7304bcf8eca62d` already describe independent NPU
services: decisions, embeddings, reranking, moderation and Qwen3.5-2B
generation. The request's `model` selects a service. Custom sidecars are
restricted to the documented fine-tuned architectures; an arbitrary Laya
checkpoint is not covered by that contract. This Linux host/container
documentation does not establish admission of our separate Windows Light
experiment. [Pinned NPU contract](https://github.com/peonist-ai/halogen-flash-server/blob/7f31bbd4021f217a1be9776bdb7304bcf8eca62d/docs/NPU.md).

These services do not document feeding token proposals into Flash-Next MTP.
The published benchmark client accepts `serial` or `mtp` and explicitly
describes no separate draft checkpoint. `HALOGEN_MTP_HEAD` loads an HGN head
for GGUF trunks and is ignored for native HGN checkpoints. The checked public
sources expose no target-feature export, external candidate verification or
accepted-prefix commit/rejected-suffix discard contract. The engine is closed
source; this repository contains deployment code. A real NPU drafter therefore
needs an upstream integration contract or a target engine that exposes those
operations. [Drafter contract](https://github.com/peonist-ai/halogen-flash-server/blob/7f31bbd4021f217a1be9776bdb7304bcf8eca62d/tools/bench-serving.py#L89),
[head flag](https://github.com/peonist-ai/halogen-flash-server/blob/7f31bbd4021f217a1be9776bdb7304bcf8eca62d/docs/FLAGS.md#L33),
[engine scope](https://github.com/peonist-ai/halogen-flash-server/blob/7f31bbd4021f217a1be9776bdb7304bcf8eca62d/CONTRIBUTING.md#L25).

Halogen also states that Flash runs somewhat slower while its NPU services
work because the processors share the memory bus and chip power budget. A
separate drafter benchmark cannot quantify that penalty; measure the complete
concurrent target/drafter path. [Resource contention](https://github.com/peonist-ai/halogen-flash-server/blob/7f31bbd4021f217a1be9776bdb7304bcf8eca62d/docs/NPU.md).

For illustration only, a hypothetical 60 ms complete round yielding four,
three or two actually committed tokens averages 66.7, 50.0 or 33.3 tok/s,
respectively. Acceptance alone cannot establish acceleration. A block drafter
targets decode; it does not by itself speed processing of the original cold
128K/260K prompt. Feature-assisted drafting can avoid repeatedly encoding the
whole prompt, but that requires the missing target-feature interface. No new
model download, training, installation or runtime measurement was performed
for this source assessment.
