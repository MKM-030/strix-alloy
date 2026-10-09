# Offline token-only neural-prefix selector preparation

Source preparation only. No training, test execution, ONNX export, placement,
engine launch, GPU/NPU call, or live policy mutation was performed by this worker.
Root owns those executions and the collected provenance review. The old56 rows
from one synthetic request are deliberately insufficient for this pipeline.

The fixed feature vector has64 FP32 entries:32 signed unigram bins,16 signed
ordered-bigram bins,8 newest token hashes, current/opening token hashes,
log1p(position/history total/copied count/causal stock width), current-opening
equality and adjacent repetition fraction. Hashing uses fixed uint32 arithmetic;
raw token-number distance has no semantic interpretation. Inputs come only from
the copied native Begin. Offered/future neural IDs, accepted counts, costs,
transport counts, request identity and heldout labels cannot enter the features.

The native v1 neural observer runs before width selection and intentionally
records `stock_width=-1`. The qualified private cost reader adds
`causal_depth_low/high` from that exact Begin. `causal_width.py` projects width2
only from a reviewed fixed-depth2 profile (`mtp_depth=2`, `spec_adapt=false`),
Begin depth_low2/adaptive0 and native allowance>=2. It adds
`causal_stock_width=2` and
`width_source=qualified_fixed_engine_profile_depth2`; the raw stock_width stays
-1. A later attempted count never supplies a causal width. If those independent
conditions cannot be proved, the row is excluded.

Only complete neural rows with two actually attempted horizons are supervised.
The classes are `min(accepted_prefix,2)`; wider complete attempts can label only
their first2 horizons. PLD, unattempted, censored, terminal/partial/constrained,
native-ineligible and unavailable-history rows are excluded. Native counter
deltas and survival labels must agree exactly. Whole-journal loss rejects the
request rather than silently producing a convenient subset.

The frozen collected manifest uses
`halogen0173.selector-request-cohort.v1` from the request-provenance worker.
Every request needs request/document IDs, explicit train/test split, full
session nonce/uint64 wire request ID/owner birth, and hash-bound payload,
document, decoded ledger and provenance receipt. The uncollected preparation
manifest has null native bindings and cannot fit. Root's recorded reviewed
manifest SHA is an immutable input binding after reviewing the actual loaded
model/draft/tokenizer roles, exclusive request/native-owner mapping and receipts;
a caller-provided `qualified` boolean is insufficient. All input artifact bytes
are rehashed. Repeated request IDs, native owner identities, document IDs or
document/payload bytes cannot leak across the split. The structural minimum is
two independent requests per split; it does not certify statistical adequacy.

The mean and scale are fitted on train rows only. A train-only class prior,
regularized64->3 linear softmax and64->16->3 ReLU MLP use the same features.
Full-batch Adam uses fixed seed20261009,300 epochs, learning rate0.01 and L2 0.01;
each train request gets equal total loss weight. Hyperparameters and the
diagnostic skip threshold0.65 are frozen before evaluation. No test input chooses
an epoch, architecture, normalization, threshold or hyperparameter. Root should
retain the first holdout result even if the predictor is unhelpful.

The output classes imply consistent survival probabilities `q1=p1+p2`, `q2=p2`.
Reports include log loss, multiclass/prefix Brier, accuracy, confusion matrix,
prefix calibration bins and request-macro/per-request metrics for every baseline
on train and test. Paired whole-request bootstrap intervals resample requests,
not correlated decode rounds. A6-request test split can still have considerable
uncertainty. The skip diagnostic counts the observed classes among selected
rows; it computes neither an altered acceptance ratio nor throughput. The cost
summary retains actual stock Begin-to-Outcome time including observer overhead.
`transported_delta` remains a transport count, not authoritative committed-token
wall time. Observed stock costs cannot price an untried width or skip trajectory.

The MLP has1,091 parameters:4,364 bytes in FP32. Frozen normalization adds512
bytes; a normalized input is256 bytes and logits are12 bytes. The exported graph
has fixed shape[1,64]->[1,3], constant FP32 weights and exactly
`Gemm -> Relu -> Gemm`, ONNX opset17/IR8. Export records the actual serialized
graph size, weight hash, source freeze and report hash. No latency result exists
in this preparation. No quantization or target-model weight modification occurs.

## Root-owned run recipe

Use the already installed NumPy/ONNX Python environment. Do not install packages,
download models or modify target weights. Set all BLAS/OpenMP thread variables
before starting Python. Under root's existing owned-process/reserve/deadline
guard, first execute the prepared CPU checks:

```powershell
$env:OMP_NUM_THREADS = '1'
$env:OPENBLAS_NUM_THREADS = '1'
$env:MKL_NUM_THREADS = '1'
$policyDir = 'C:/Projects/strix-alloy-clean/server/.local/optimization9h-20261004/halogen0172-backend-preparation-20261008/npu-selector-policy-20261009'
& $existingPython -B "$policyDir/test_selector_policy.py"
```

After root has qualified and frozen the collected manifest and receipts, use its
actual recorded hash, not the uncollected preparation manifest hash:

```powershell
& $existingPython -B "$policyDir/selector_policy.py" fit --manifest $collectedManifest --reviewed-manifest-sha256 $reviewedCollectedHash --output $freshFitDirectory
```

Inspect paired heldout MLP prediction against both cheap baselines, request
coverage, calibration and uncertainty. Prediction improvement is a necessary
screen, not speed evidence. Only then serialize a fresh graph:

```powershell
& $existingPython -B "$policyDir/selector_policy.py" export --bundle $freshFitDirectory --output "$freshFitDirectory/selector.onnx"
```

`load_bundle`, `prepare_feed`, `logits` and `decode_logits` are reusable pure
host functions for later placement runners. `prepare_feed` includes the exact
feature preparation and train normalization; `decode_logits` applies the same
stable softmax and decision threshold everywhere. For direct CPU reference use
`logits(feed['features'], mlp_weights)` with the four `mlp_` arrays from the
bundle. For ORT send that identical feed to the same frozen ONNX bytes. Validate
logit/probability agreement and action parity over changing actual input rows,
including threshold-adjacent rows. Do not use a constant synthetic input to
claim a ready selector.

## Placement preparation and complete cost contract

Inspected local source: `scripts/benchmarks/halogen_npu_expert_onnx.py` uses the
installed Windows ML provider catalog, external provider registration,
`ort.get_ep_devices`, `SessionOptions.add_provider_for_devices`, disabled CPU
fallback, provider-library pins and exclusive node-profile attribution.
`halogen_npu_light_ep_admission_probe.py` does the analogous pinned
RyzenAILight path with verified copied provider bytes and explicit readiness
limits. Their existing tensor-specific replay routines are unsuitable for this
selector without a dedicated input/reference adapter. Reuse their installed
runtime admission/cleanup pattern, not their expert tensor shapes or tolerances.

CPU placement must include the minimal direct host implementation, since forcing
a tiny CPU model through ORT alone could inflate the reference cost. GPU placement
can attempt `DmlExecutionProvider` only if the existing runtime advertises it;
configure sequential execution and disabled memory pattern as required by the
installed provider, disable fallback and require actual node attribution.
Availability and compatibility have not been executed here. NPU can attempt the
existing pinned RyzenAILight/VitisAI provider without acquisition or downloads.
Provider attribution alone does not establish internal AIE-only placement; keep
that limitation until compiler/device evidence qualifies it. There is no
current evidence that either accelerator accepts or accelerates this tiny graph.

Hold model bytes, normalized input bytes, decision arithmetic, allowed native
actions, workload and generation settings constant for each placement. Measure
fresh changing rows with separate initialization and warmup receipts. The
per-decision exposed interval starts before history-feature preparation and
ends when the owned native decision is usable. It includes feature hashing,
normalization, contiguous packing, submission, scheduling, host/device transfer,
synchronization, logits return, softmax, publication/ownership validation and
any discarded/fallback job. Report mean/p50/p95 plus unamortized initialization
and actual request-amortized cost. Separately time all WSL/Windows serialization,
outbound transport, responder queue, graph call and return/consume steps. A
host `session.run` clock includes ORT synchronization but does not include a
missing cross-process/native transport interval. Component timings may be
nested; use a single exposed end-to-end clock to avoid double counting.

No guessed time-saving budget is supplied by prefix labels. A root-declared
overhead ceiling can screen placements, but adoption requires repeated actual
stock-versus-policy end-to-end requests with delivered Prefill/Decode, output
parity, complete accepted/attempted counts and total selector/target slowdown.
Raising acceptance by skipping hard rounds does not establish useful speed.

No live policy is wired. A future ordinary skip uses the native handler path
after eligibility/clamps at CMP ESI>=2 (`0x174088b`) and its ordinary continuation
(`0x1740894`). Never pass0/1 directly into the neural controller. Preserve its
original Request RDI/width ESI and24-byte by-memory output at entry RSP+8,
ownership/reset/cancellation/slot lifetimes, and every native capacity gate.
