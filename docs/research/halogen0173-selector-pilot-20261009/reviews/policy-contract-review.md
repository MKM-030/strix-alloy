# Independent frozen policy/provenance contract review

Source-only review on 2026-10-09. Root reports nine CPU tests passed. This worker
did not rerun them, fit a model, start a process, inspect hardware, or call an API.
The reviewed policy files match all four hashes in `source-freeze.json`; that
freeze's SHA-256 is
`f4e13429d422bbc63dc843832fea3ad5b74d5a1cc9192ece877958146c24167d`.
The policy source SHA-256 is
`8af81ce63a331163e6b98fe35dc7f59130232fd2bb39f3da6807ab02209a5d10`.

## Actionable finding corrected in this worker's checker

The original request-provenance checker required both native Begin depth_low
and depth_high to equal two. That was more restrictive than the qualified
fixed-depth rule. With adaptive disabled, the controller selects depth_low;
depth_high can be zero and still be a valid fixed-depth-two Begin. The policy's
`causal_width.py` correctly uses reviewed profile depth two, adaptive disabled,
causal depth_low two, native adaptive zero, and native allowance at least two.
Its existing test explicitly retains depth_high zero and verifies that changing
the later outcome attempted count cannot affect width projection.

`check_cohort.py` now requires Begin depth_low two/adaptive zero and retains
depth_high as evidence. The README now describes this same rule. No policy
source or tests were changed. The prior preparation seal remains the historical
pre-review seal; `policy-contract-review.json` records the corrected checker and
README hashes, and `refs-after-policy-review.json` seals the current preparation.
The frozen documents, payloads, and manifest bytes are unchanged.

## Reviewed behavior

No actionable target leakage, train/test contamination, or request-macro
calculation defect was found in the frozen policy source under its stated
root-reviewed manifest trust boundary.

* `selector_policy.py:69` derives features only from copied Begin history,
  current/opening IDs, position/history counts, and causal width. Outcome
  accepted/attempted counts, survival labels, costs, offer IDs, transport counts,
  request identity, and held-out labels do not enter the feature vector.
* `causal_width.py:10` does not read attempted/accepted outcomes. Raw native
  stock_width remains -1; the separate projected field is conditional on the
  root-reviewed fixed profile and actual causal Begin. PLD stays a separate
  source. Native allowance is checked independently of observed attempts.
* `selector_policy.py:115` uses observed complete neural attempts as supervision,
  excludes unattempted horizon two, unavailable history, and native-ineligible
  rows, and checks neural counters plus survival labels. It does not invent
  horizon labels for widths that were not attempted. The public/cost reader is
  responsible for excluding terminal, partial, and constrained wire pairs.
* `selector_policy.py:146` freezes whole requests/documents and catches duplicate
  request IDs and document/payload hashes that cross train/test. The native-owner
  triple cannot be reused by another request. The prepared 16 documents have
  unique IDs and are frozen 10 train/six test.
* `selector_policy.py:179` requires the recorded collected-manifest hash, rehashes
  payload/document/decoded/provenance and each mandatory evidence role, checks
  exact nonce/full wire/owner/request/document/split binding, rejects whole-journal
  loss, and bounds every selected row inside its Birth/Retire sequence interval.
  Stable checkpoint/N-gram/frontend-tokenizer role pins are enforced across the
  cohort. Caller-supplied decoder document metadata is not the admission proof.
* The policy reader intentionally relies on root's completed provenance review
  for actual native journal reconstruction, loaded-file identity/mount proof,
  private-client exclusivity, and output parity. Rehashing a receipt by itself is
  not independent native loading proof. Root must retain the offline review and
  actual source evidence before recording the manifest hash used for fitting.
* `selector_policy.py:441` fits mean/scale and class prior from train rows only,
  then trains fixed-epoch linear and MLP candidates on the same train mask.
  No held-out score selects epochs, normalization, threshold, or architecture.
  Train normalization is row-weighted; the training loss and prior are explicitly
  request-balanced. This is not leakage or a mislabeled request-macro metric.
* `selector_policy.py:302` assigns each request equal total sample weight.
  `metrics:360` uses those weights for request_macro metrics and separately names
  pooled row means and row confusion counts. Per-request values use each request's
  own round mean. Calibration bins are pooled by round and are not described as
  request-macro calibration.
* `paired_request_comparison:406` computes paired per-request MLP-minus-baseline
  differences and bootstraps entire requests with a shared deterministic set of
  resamples. It does not resample correlated rounds or alter model fitting.
* `observed_cost_summary:391` preserves actual stock intervals and states that
  they do not establish counterfactual savings. Diagnostic skip reports selected
  observed classes, not a changed acceptance ratio or speed gain. CPU/GPU/NPU
  placement remains separate root-owned work.
* `load_bundle:501` binds the actual weight bytes and source freeze and verifies
  shape, FP32 dtype, finite values, and positive scales. `export:518` constructs
  Gemm/Relu/Gemm with the same weights; normalization and decision arithmetic stay
  in the host contract. Source inspection establishes this construction, not
  executed ONNX/runtime equivalence or accelerator support.

## Limits retained

The nine existing tests exercise the feature invariance, label validation,
split, normalization, probability, request-weight and width-projection contracts.
They do not constitute a completed collected-manifest integration result. That
result must come from root's actual collected receipts and offline review.

Six held-out requests give limited uncertainty estimates. Training on complete
two-attempt stock rounds conditions the result on those observed rounds; it does
not establish behavior on censored or width-one rounds, PLD, a changed decode
trajectory, or arbitrary future workloads. Those limits are already retained in
the source/report contract and do not warrant another approval or test gate.
