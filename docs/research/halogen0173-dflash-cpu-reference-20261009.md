# DFlash CPU reference and acquired bindings — 9 October 2026

The supplied DFlash backbone now has an executable, offline CPU reference in
[`scripts/research/dflash_k3_reference`](../../scripts/research/dflash_k3_reference/README.md).
Its final BF16 comparison matches the pinned owner's backbone exactly on two
short, explicitly synthetic feature inputs. This establishes that reference
calculation and accepted-context cache handling for these inputs. It does not
establish target acceptance, a serving speed improvement, or GPU/NPU execution.
The existing Halogen 0.17.3 service remained ready and open throughout.

## Acquired assets

- [PixelML checkpoint](https://huggingface.co/PixelML/Qwen3.8-Flash-Next-NVFP4-DFlash/tree/9cd660f9050c92fedc88cbe547bd53af0392abe1):
  996,219,904 bytes, 58 BF16 tensors and 498,106,880 parameters. Full-file SHA256:
  `35a23c17c248ff2e3296e6b78882b6d955af3092498fb7b6c48be1af4bfa971a`.
- [Original shared head](https://huggingface.co/Qwen/Qwen3.8-Flash-Next/tree/f5d08274bafd880402bd16f5e3e6c514136ec06c):
  only shard `model-00131-of-00131.safetensors`, 1,271,398,528 bytes,
  BF16 `[248320,2560]`. Full-shard SHA256:
  `50be0ccd11e4da0c92114600aca321d2c18f795e9e923fd587469587ecfd9df4`.
- Five original embedding rows: IDs 0, 1, 23, 1000 and the internal mask 248077.
  Each is 5,120 bytes. Pinned HTTPS requests were checked for exact `206`
  byte ranges and source length; fetched row hashes are recorded. The complete
  embedding shard was not downloaded or hashed. These bindings do not establish
  equality to Halogen's quantized HGN weights.

No complete 360 GB teacher checkpoint, driver, package, firmware or model
replacement was acquired. Both managed download children terminated normally.

## Implemented calculation

The reference strictly loads the supplied tensors, concatenates five target
tap outputs, and implements the five-layer backbone, per-head RMSNorm, full
NeoX RoPE and noncausal query attention. It evaluates all 248,320 vocabulary
rows, using 8,192-row head chunks to bound temporary memory. The current anchor
and two mask queries predict three successive positions, including query zero.

Persistent KV contains only processed target input rows accepted by the
authoritative verifier. Rejected rows are sliced out before projection; query
KV is temporary. The next bonus/correction becomes an anchor and is added only
after the target processes it. Request nonce, epoch, round and committed input
positions are checked. Caller tensors are copied into owned snapshots.

K3 is this custom mathematical reference. The pinned author's vLLM attachment
allows K4/K5/K7 and requires TP2/eager execution. Its supported configuration
does not qualify K3 acceptance or this Halogen integration.

## Numerical evidence

Root executed the final published implementation with two CPU threads,
PyTorch `2.13.0+rocm10.0.0`, explicit CPU tensors and BF16 arithmetic. No
accelerator path was initialized by the fixture. The independent oracle uses
hash-checked source AST from the owner backbone and Transformers 5.16.1 math;
it recomputes the full context, while the reference retains incremental KV.

| Fixture | Context rows | Exact hidden values | Exact full-head logits | Draft IDs agree |
| --- | ---: | ---: | ---: | --- |
| Initial proposal | 4 | 7,680 / 7,680 | 744,960 / 744,960 | Yes |
| After partial commit | 6 | 7,680 / 7,680 | 744,960 / 744,960 | Yes |

Maximum absolute and relative errors are zero in both rounds. No tolerance was
widened. The second round injects a cache-control selector of one and poisons
the two rejected feature rows with NaN. All output values remain finite and
the committed cache contains exactly six rows. This injected selector is not
measured target acceptance. The feature inputs are deterministic synthetic
stimuli; weights, head and embedding rows are real acquired assets.

An additional control poisons the selected current row of the pending second
proposal. The provider rejects it before projection and retires the request,
clearing KV, IDs and positions. Finite binding/context/query/logit checks reject
numerical failure before cache publication or argmax. The independent source
review's finite-value finding is closed.

The final fixture's sampled minimum physical reserve was 24.41 GiB; sampled
commit reserve was 118.05 GiB. Its owned child exited normally. Seven
contract checks cover layout, stale/foreign transactions, mask rejection and
loader validation. No full-repository suite was run.

## Remaining integration

The owned native feature exporter and full replacement of native drafting are
not integrated. Initial prefill precedes the existing Request owner registry;
it requires a pending-prefill generation bridged to the completed Request,
with cancellation, chunk and buffer-lifetime handling. A source candidate is
the common attention-HC boundary before its output buffer is reused. Halogen
and the original teacher have different gate-rounding arithmetic; approximate
draft conditioning can be evaluated, while native target verification remains
authoritative.

The native Request-backed K3 verify/commit/output join is identified. A complete
adapter must also avoid native replay costs and restore state safely after
external drafting. The serial request mode has a different ownership ABI, and
cache restore can skip the full model reset. These obligations are unfinished;
there is no executable live bridge claim and no default-on hook.

The new passive controller receipt checks 24 instruction spans and 1,771
instruction-byte matches against the pinned ELF. That validates the cited
source locations. It does not validate a runtime replacement. In particular,
an already selected slot needs retained scalar enforcement even if the optional
collector is disabled or loses ownership; Request retirement alone cannot
release that slot before a completed full model reset.

Only after these interfaces work will a GPU/NPU provider receive actual target
features and be compared against the preserved native engine on frozen natural
inputs, including all provider/transport costs. Existing slow NPU and ready64
paths remain disabled. There are no new NPU Prefill/Decode or acceptance values.

The latest serving measurement remains the separate
[natural 16K RAW cohort](../benchmarks/halogen0173-natural16k-raw-20261009.md):
1,833.70 Prefill tok/s, 43.05 Decode tok/s, and 180/399 = 45.11% combined API
MTP+PLD draft acceptance. This source/reference work adds no serving gain claim.
