# Offline CPU K3 DFlash reference

This directory implements a custom mathematical K3 reference for the exact
supplied PixelML checkpoint, revision
`9cd660f9050c92fedc88cbe547bd53af0392abe1`, SHA256
`35a23c17c248ff2e3296e6b78882b6d955af3092498fb7b6c48be1af4bfa971a`,
996,219,904 bytes. All 58 supplied BF16 tensors are required, with no replacement
parameters. The exact inventory contains 498,106,880 parameters and is validated
before loading.

K3 is a custom reference use of the owner's dynamic query length. The pinned
`pixel_epoch7.py` serving adapter permits K4/K5/K7, requires TP2 and enforce_eager,
and does not qualify K3 as an authored serving configuration. This reference
does not establish K3 acceptance, target feature transport, native-controller
integration, serving throughput, or accelerator suitability.

## Computation

`reference.py` uses five target tap outputs in order `[3,15,23,35,43]` (HC
boundaries `[4,16,24,36,44]`). The fusion projection maps 12,800 features to 2,560,
followed by hidden RMSNorm. Each of five layers projects its context K/V from
this same fused context, without applying its query input-layernorm to context.
Queries use input RMSNorm, 24 Q heads, 2 KV heads, head dimension256, per-head Q/K
RMSNorm, full256-dimension default NeoX split-half RoPE with theta10,000,000, and
noncausal attention over all accepted context plus all three current queries.
The intermediate size is7,680, activation SiLU, and all projections are biasless.

With accepted context at positions0..p−1 and current authoritative anchor at p,
query IDs are `[anchor,248077,248077]` at `[p,p+1,p+2]`. These three outputs
predict target positions `[p+1,p+2,p+3]`, including query zero. The caller supplies
the actual target anchor embedding, mask row and full248,320×2,560 vocabulary
head. The reference evaluates every head row in8,192-row chunks. It never
suppresses mask/padding logits, creates a confidence gate, or limits candidates
to a sampled shortlist. Raw argmax IDs are returned unchanged; `offerable=False`
if an argmax falls outside the defined target-ID domain0..248076.

Use `compute_dtype="bf16"` for source-like BF16 arithmetic or `"float32"` for a
CPU mathematical reference using exact BF16-trained weights converted to FP32.
RMSNorm statistics, RoPE frequencies and attention softmax use FP32 in both.
PyTorch CPU kernel choices and incremental projection matrix sizes can change
rounding. FP32 is not a claim of source BF16 bit identity.

## Persistent state and immutable inputs

`TargetIdentity` records the target model/revision, pinned tokenizer SHA, head
and embedding receipts, feature provenance and exact tap IDs. `TargetBinding`
clones the caller's full head and mask row into private snapshots. Each anchor
and each selected feature append is also detached/cloned. Caller mutation
therefore cannot alter persistent state. PyTorch has no read-only tensor flag;
private tensors must remain private. Nothing in this code writes model weights,
binding snapshots or source files.

`TargetRows` binds each input feature row to its target input ID and absolute
position. The production caller is responsible for supplying actual target
features and an authoritative verifier decision; this provider cannot certify
their provenance from tensor values. The initial prefix must be complete and
contiguous from position0. One request birth nonce, epoch and round owns a
pending proposal. Stale round numbers, changed input IDs, wrong input positions,
foreign identity and foreign/stale commit plans are rejected.

For verifier inputs `[current,d0,d1,d2]` at `[p,p+1,p+2,p+3]`, authoritative
`accepted_prefix=a` retains exactly the first `a+1` processed target input rows.
For example, `a=1` retains `[current,d0]`, discards `d1,d2`, and sets the next
anchor position to `p+2`. The supplied authoritative bonus/correction ID is the
next anchor and is not appended until the target processes it. Selection happens
before fusion/projection. Temporary query K/V is never committed or reused;
accepted positions get replacement KV from their target-derived features.
All five cache appends are constructed before the frontier advances. The private
head and mask snapshots are checked for finite values once at binding, using
bounded head chunks. Anchor/query tensors, per-layer query Q/K/V and hidden
states, and complete logits must be finite before argmax can record a proposal.
Selected target features, fused context and each projected context K/V must be
finite before a cache append can commit. Selection precedes these checks;
rejected verifier feature values are neither checked nor projected. Numerical
failures during initialization, proposal or commit retire the request and clear
its context cache. Call `retire()` at stop or cancel.

Minimal integration (the caller owns verification):

```python
from reference import K3Reference, TargetBinding, TargetEmbedding, TargetRows

binding = TargetBinding(full_head=target_head, mask_embedding=target_mask_row,
                        identity=target_identity)
provider = K3Reference(checkpoint_path=checkpoint, config=config, binding=binding,
                       compute_dtype="bf16", request_nonce=request_nonce, epoch=0)
provider.initialize(TargetRows(prefill_taps, prefill_ids, prefill_positions,
                               target_identity))
proposal = provider.propose(anchor=TargetEmbedding(current_id, current_embedding,
                            target_identity), round_index=0)
# Offer only if proposal.offerable. The target supplies accepted_prefix and bonus.
plan = provider.apply_verification(rows=TargetRows(verifier_taps,
    (current_id,) + proposal.raw_ids, verifier_positions, target_identity),
    round_index=0, accepted_prefix=authoritative_accepted_prefix,
    authoritative_bonus_id=authoritative_bonus_id)
```

## Portable loading

`contract.py` reads only the bounded safetensors JSON header and checks duplicate
keys, positive shapes, exact byte sizes, complete nonoverlapping data coverage,
BF16/F32 storage and the pinned58-tensor manifest. `offline_loader.py` then
checks the full-file SHA256 and uses a private copy-on-write mapping plus
`torch.frombuffer`. No safetensors package, pickle, `torch.load`, package
installation, network fetch or accelerator API is required. The mapping lifetime
is retained with its tensors; no explicit unmap can invalidate borrowed storage.
Importing the provider, oracle or comparison module does not import PyTorch.

## Independent owner comparison

`owner_oracle.py` verifies saved source hashes, then AST-extracts the pinned
Pixel attention, decoder and `_forward_backbone` bodies plus exact
Transformers5.16.1 Qwen3 RMSNorm, MLP, default RoPE, rotate_half, repeat_kv and
eager attention definitions. It omits package imports and hub/dynamic decorators
while preserving `staticmethod`. Owner modules are constructed on meta, and all
58 actual supplied parameters replace meta parameters before CPU forward. The
oracle recomputes the complete accepted context each round; the provider uses
its incremental context KV. Both use the same immutable actual target head.
This provides an independent backbone path, not a second handwritten copy of
the provider arithmetic. The source files, receipts and MIT/Apache licenses are
in `sources/`.

`compare.py` is deliberately a synthetic numerical fixture. It uses actual
checkpoint weights, the original trained BF16 head and fetched actual embedding
rows, with deterministic synthetic HCconcat stimuli. It compares complete
hidden states, every vocabulary logit, and all three raw argmax IDs. A second
round injects a clearly labelled control selector1 and poisons rejected verifier
feature rows with NaN, testing row selection and target-KV replacement. This
is followed by one accepted-row control fixture using the pending second
proposal and the same loaded model: selector0 selects a NaN-poisoned current
row, which must raise `NonFiniteTensorError` before fusion/projection and leave
the request retired with its cache cleared. No third draft forward or extra
model load is performed. These control fixtures must execute for CLI exit0. This
selector is not measured target acceptance; synthetic features are not captured
target hidden states. No acceptance rate or tok/s is reported. The embedding
rows have exact fetched-row SHA receipts bound to pinned HTTPS206 ranges; the
complete embedding shard was not acquired or hashed, and that provenance limit
is preserved in the report.

Run from this directory using an existing CPU PyTorch runtime:

```powershell
& 'C:/Users/Marcel/AppData/Local/Programs/Python/Python312/python.exe' compare.py `
  --checkpoint 'C:/AI/halogen-dflash/pixelml-9cd660f9050c92fedc88cbe547bd53af0392abe1/model.safetensors' `
  --config 'C:/AI/halogen-dflash/pixelml-9cd660f9050c92fedc88cbe547bd53af0392abe1/config.json' `
  --bindings-receipt 'C:/Projects/strix-alloy-clean/server/.local/optimization9h-20261004/halogen0172-backend-preparation-20261008/dflash-checkpoint-20261009/binding-acquisition-outcome.json' `
  --dtype bf16 --threads 2 --output comparison-bf16.json
```

For FP32, change `--dtype float32 --output comparison-float32.json`. The full
head stays BF16 in its immutable snapshot; only one chunk is converted at a
time. Error reports include maximum absolute/relative error, exact element
counts and raw-ID equality. No error threshold is invented. `--atol X --rtol Y`
adds the caller's explicit allclose decision. Exit0 requires finite values and
raw-ID equality, plus allclose if tolerances were supplied; otherwise read the
reported numerical errors to assess arithmetic parity. This agent only ran
standard-library contract, syntax, import and AST checks. Numerical execution is
owned by the parent task.

The parent executed the BF16 fixture on2026-10-09 with two CPU threads and
PyTorch2.13.0+rocm10.0.0, using CPU tensors throughout. Both rounds matched exactly:
each round had7,680/7,680 identical hidden values and744,960/744,960 identical
full-head logits, with zero maximum absolute/relative error. Raw IDs were
`[256,364,364]` and `[21,198,198]` in both paths. After the injected selector1,
the context length was6; the two NaN-poisoned rejected rows were excluded. The
published qualification is recorded in
[`halogen0173-dflash-cpu-reference-20261009.json`](../../../docs/research/halogen0173-dflash-cpu-reference-20261009.json).
Final root-owned raw receipts remain in the local preparation directory as
`comparison-bf16-guarded.json` and `cpu-parity-guarded-outcome.json`.
This qualifies only these short synthetic CPU
fixtures, with the original trained head/embedding rows, and does not measure
target acceptance or K3 generalization.

Standard-library checks, requiring no tensor runtime:

```powershell
& 'C:/Users/Marcel/AppData/Local/Programs/Python/Python313/python.exe' -m unittest test_contract -v
```

## Source receipts

Pixel source revision: `54b35f57af721ffa8d55f1c0ae79f24952a82fd6`.
Transformers primitives: tag`v5.16.1`.
`sources/receipts.json` records each exact URL, length and SHA256;
`owner_oracle.py` independently pins the two executed source hashes.
`fetch_text_sources.py` is an optional source-text-only acquisition helper. The
provider and comparison never call it and remain fully offline.
