"""Offline token-only neural-prefix predictor; no engine or accelerator imports.

Root must verify collected provenance before passing its frozen manifest SHA.
The caller's frozen SHA binds that review; no `qualified` boolean admits data.
Outcomes cover the first two actually attempted neural drafts. Observed costs
remain stock-trajectory observations and never become counterfactual savings.
"""
import argparse
from collections import Counter
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys

import numpy as np
from causal_width import project as project_fixed_width

HERE = Path(__file__).resolve().parent
RUNTIME_SHA = "af4f07bbe3759206013eb6f1328095ca2105cfda5127c5b9a2ab93e1aea987b7"
FEATURE_VERSION = "halogen0173.token-history64.v1"
SEED, WIDTH, HIDDEN, CLASSES = 20261009, 64, 16, 3
MAX_ROWS, MAX_REQUESTS = 32768, 128
EPOCHS, RATE, L2 = 300, .01, .01
SKIP_THRESHOLD = .65  # Preregistered diagnostic; not a cost-optimal policy.
KEY_FIELDS = ("session_nonce", "owner_birth", "slot_cookie", "slot_epoch",
              "round", "begin_seq", "outcome_seq")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read_json(path):
    require(Path(path).stat().st_size <= 64 << 20, "JSON exceeds bounded input size")
    with Path(path).open(encoding="utf-8-sig") as stream:
        return json.load(stream)


def write_json(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")


def integer(value, low=0, high=(1 << 31)-1):
    return type(value) is int and low <= value <= high


def mix32(value):
    value = int(value) & 0xffffffff
    value = ((value ^ (value >> 16)) * 0x7feb352d) & 0xffffffff
    value = ((value ^ (value >> 15)) * 0x846ca68b) & 0xffffffff
    return (value ^ (value >> 16)) & 0xffffffff


def hash_scalar(token):
    return ((mix32(token) & 0xffffff) / float(1 << 23)) - 1.


def features(row):
    """Read only copied predecision history and native eligibility fields.

    Bins0..31: signed unigram sketch;32..47: signed ordered bigrams;
    48..55: newest-to-oldest last8 token hashes (zero missing slots);
    56,57: current/opening hashes;58..61: log1p(position,total,count,width);
    62: current==opening;63: adjacent repetition fraction.
    Token integer magnitude is not interpreted as semantic distance.
    """
    require(row.get("context_available") is True, "Copied token history unavailable")
    ids = row.get("context_suffix")
    require(isinstance(ids, list) and 0 < len(ids) <= 64 and
            all(integer(token) for token in ids), "Invalid bounded copied token suffix")
    for name in ("model_position", "context_total", "current_id"):
        require(integer(row.get(name)), "Invalid causal input: " + name)
    width = effective_width(row)
    require(integer(width, 2, 16), "Missing causal eligible stock width")
    require(integer(row.get("opening_id"), -1), "Invalid opening ID")
    require(len(ids) == min(row["context_total"], 64), "Incomplete copied suffix")
    result = np.zeros(WIDTH, dtype=np.float32)
    for token in ids:
        hashed = mix32(token ^ 0x9e3779b9)
        result[hashed & 31] += (-1. if hashed & 0x80000000 else 1.) / len(ids)
    for left, right in zip(ids, ids[1:]):
        hashed = mix32(mix32(left) ^ ((mix32(right) << 1) & 0xffffffff) ^ 0x85ebca6b)
        result[32 + (hashed & 15)] += (-1. if hashed & 0x80000000 else 1.) / max(1, len(ids)-1)
    for index, token in enumerate(reversed(ids[-8:])):
        result[48 + index] = hash_scalar(token)
    result[56:58] = [hash_scalar(row["current_id"]), hash_scalar(row["opening_id"])]
    result[58:62] = [math.log1p(value) for value in
                     (row["model_position"], row["context_total"], len(ids), width)]
    result[62] = float(row["current_id"] == row["opening_id"])
    result[63] = sum(left == right for left, right in zip(ids, ids[1:])) / max(1, len(ids)-1)
    require(np.isfinite(result).all(), "Nonfinite feature")
    return result


def effective_width(row):
    if row.get("width_source") == "qualified_fixed_engine_profile_depth2":
        require(row.get("stock_width") == -1 and row.get("causal_stock_width") == 2 and
                row.get("causal_depth_low") == 2 and row.get("adaptive") == 0,
                "Invalid fixed-profile causal width projection")
        return 2
    return row.get("stock_width")


def exclusion(row):
    """Invalid supervised labels fail; valid but ineligible rows are counted."""
    if row.get("source") != "neural":
        return "source"
    if any(row.get(key) is True for key in ("censored", "terminal", "partial_output", "constrained")):
        return "censored"
    attempted, accepted = row.get("attempted"), row.get("accepted_prefix")
    require(integer(attempted, 0, 16) and integer(accepted, 0, attempted), "Invalid observed prefix")
    if attempted < 2:
        return "unattempted_horizon"
    width = effective_width(row)
    if not integer(width, 2, 16) or not integer(row.get("native_allowance"), 2):
        return "native_ineligible"
    require(attempted <= min(width, row["native_allowance"]), "Attempt exceeds native bounds")
    if row.get("context_available") is not True:
        return "history_unavailable"
    deltas = row.get("native_counter_deltas", {})
    require((deltas.get("neural_rounds"), deltas.get("neural_drafted"), deltas.get("neural_accepted")) ==
            (1, attempted, accepted), "Neural outcome/counter mismatch")
    require(all(deltas.get(key) == 0 for key in ("pld_rounds", "pld_drafted", "pld_accepted")),
            "Cross-source prefix aggregation")
    require(row.get("survival_labels") == [int(accepted >= horizon) for horizon in range(1, attempted+1)],
            "Attempted survival label mismatch")
    features(row)  # Reject malformed causal fields before training.
    return None


def label(row):
    return min(row["accepted_prefix"], 2)


def validate_split(requests):
    request_ids, groups = set(), {}
    for request in requests:
        ident, split, documents = request.get("request_id"), request.get("split"), request.get("document_ids")
        require(isinstance(ident, str) and ident and ident not in request_ids, "Missing or duplicate request ID")
        require(split in ("train", "test"), "Use frozen train/test request split")
        require(isinstance(documents, list) and documents and len(documents) == len(set(documents)) and
                all(isinstance(value, str) and value for value in documents), "Missing document grouping")
        request_ids.add(ident)
        group_keys = ["document:" + value for value in documents]
        for field in ("document", "payload"):
            if isinstance(request.get(field), dict) and request[field].get("sha256"):
                group_keys.append(field + "-bytes:" + request[field]["sha256"])
        for key in group_keys:
            require(key not in groups or groups[key] == split, "Request/document bytes cross train/test: " + key)
            groups[key] = split


def resolve_ref(base, ref):
    require(isinstance(ref, dict) and isinstance(ref.get("path"), str) and
            re.fullmatch("[0-9a-f]{64}", str(ref.get("sha256"))), "Missing frozen artifact reference")
    path = (base / ref["path"]).resolve(strict=True)
    require(path.is_file() and digest(path) == ref["sha256"], "Artifact hash mismatch: " + str(path))
    return path


def verify_freeze():
    freeze = read_json(HERE / "source-freeze.json")
    for name, expected in freeze["sources"].items():
        require(digest(HERE / name) == expected, "Prepared source differs from frozen hash: " + name)
    return freeze


def load_cohort(manifest_path, reviewed_sha):
    require(re.fullmatch("[0-9a-f]{64}", reviewed_sha) and digest(manifest_path) == reviewed_sha,
            "Collected manifest differs from root's recorded provenance review")
    manifest = read_json(manifest_path)
    require(manifest.get("schema") == "halogen0173.selector-request-cohort.v1", "Unknown cohort schema")
    requests = manifest.get("requests", [])
    require(isinstance(requests, list) and 4 <= len(requests) <= MAX_REQUESTS,
            "At least four independent collected requests needed; maximum128")
    validate_split(requests)
    counts = Counter(request["split"] for request in requests)
    require(min(counts["train"], counts["test"]) >= 2, "At least two independent requests in each split")
    records, exclusions, joined_keys, native_owners, cohort_asset_pins = [], Counter(), set(), set(), set()
    base = manifest_path.resolve().parent
    for request in requests:
        nonce, wire, owner = (request.get(key) for key in ("session_nonce", "wire_request_id", "owner_birth"))
        require(isinstance(nonce, str) and re.fullmatch("[0-9a-f]{32}", nonce) and
                integer(wire, 1, (1 << 64)-1) and integer(owner, 1, (1 << 64)-1),
                "Preparation manifest has no collected native owner")
        owned_key = (nonce, wire, owner)
        require(owned_key not in native_owners, "Native request owner duplicated in cohort")
        native_owners.add(owned_key)
        for field in ("payload", "document"):
            resolve_ref(base, request[field])
        decoded_path = resolve_ref(base, request.get("decoded"))
        provenance_path = resolve_ref(base, request.get("provenance"))
        provenance = read_json(provenance_path)
        require(provenance.get("schema") == "halogen0173.selector-request-provenance.v1",
                "Missing owned request provenance receipt")
        # Root's provenance verifier establishes the receipt's native loading,
        # exclusive request mapping and parity proof. This reader checks exact
        # identity and artifact binding again, rather than trusting a bool.
        for name in ("request_id", "session_nonce", "wire_request_id", "owner_birth"):
            require(provenance.get(name) == request[name], "Provenance mapping mismatch: " + name)
        require(provenance.get("document_ids") == request["document_ids"] and
                provenance.get("split") == request["split"], "Provenance split/document mismatch")
        for field in ("payload", "document", "decoded"):
            bound_path = resolve_ref(provenance_path.parent, provenance.get(field))
            require(digest(bound_path) == request[field]["sha256"], "Provenance artifact differs: " + field)
        evidence = provenance.get("evidence", {})
        evidence_paths = {}
        for field in ("journal", "startup", "close", "loaded_assets", "profile", "engine_log",
                      "response", "health_before", "health_after"):
            evidence_paths[field] = resolve_ref(provenance_path.parent, evidence.get(field))
        for field in ("normal_response", "cost_sidecar"):
            if evidence.get(field) is not None:
                resolve_ref(provenance_path.parent, evidence[field])
        assets = read_json(evidence_paths["loaded_assets"])
        require(assets.get("schema") == "halogen0173.selector-loaded-assets.v1" and
                assets.get("runtime", {}).get("sha256") == RUNTIME_SHA,
                "Loaded-asset role receipt contract differs")
        role_pins = tuple(assets.get(role, {}).get(pin) for role, pin in
                          (("checkpoint", "complete_file_sha256"), ("ngram", "complete_file_sha256"),
                           ("frontend_tokenizer", "asset_set_sha256")))
        require(all(isinstance(pin, str) and re.fullmatch("[0-9a-f]{64}", pin) for pin in role_pins),
                "Loaded main/draft/tokenizer role pins incomplete")
        cohort_asset_pins.add(role_pins)
        require(len(cohort_asset_pins) == 1, "Loaded target/draft/tokenizer roles differ across requests")
        interval = provenance.get("interval", {})
        require(interval.get("native_log_wire_ids") == [wire] and
                interval.get("gateway_completed_delta") == 1 and interval.get("gateway_cancelled_delta") == 0 and
                integer(interval.get("birth_seq"), 1, (1 << 64)-1) and
                integer(interval.get("retire_seq"), interval["birth_seq"]+1, (1 << 64)-1),
                "Exclusive native request interval proof incomplete")
        fixed = provenance.get("fixed_engine_policy", {})
        width_profile = dict(mtp_depth=fixed.get("neural_depth"),
                             spec_adapt=False if type(fixed.get("adaptive")) is int and fixed["adaptive"] == 0 else None)
        decoded = read_json(decoded_path)
        require(decoded.get("dataset_complete") is True and
                decoded.get("header", {}).get("session_nonce") == nonce and
                decoded.get("header", {}).get("runtime_sha256") == RUNTIME_SHA,
                "Decoded journal is incomplete or from another owned runtime")
        for name in ("gaps", "dropped_cumulative", "unmatched_begins", "unmatched_outcomes",
                     "invalidated_pairs", "unretired_owners"):
            require(decoded.get("summary", {}).get(name) == 0, "Whole-journal loss: " + name)
        eligible = 0
        for raw_row in decoded.get("rows", []):
            row = project_fixed_width(raw_row, width_profile)
            require(len(records) < MAX_ROWS, "Training row budget exceeded")
            if (row.get("session_nonce"), row.get("wire_request_id"), row.get("owner_birth")) != owned_key:
                continue
            key = tuple(row.get(name) for name in KEY_FIELDS)
            require(key not in joined_keys and all(integer(value, 1, (1 << 64)-1) for value in key[1:]) and
                    key[-1] > key[-2] and interval["birth_seq"] < key[-2] < key[-1] < interval["retire_seq"],
                    "Duplicate/malformed round key or row outside owned request interval")
            joined_keys.add(key)
            reason = exclusion(row)
            if reason:
                exclusions[reason] += 1
                continue
            records.append(dict(row=row, request_id=request["request_id"],
                                split=request["split"], document_ids=request["document_ids"]))
            eligible += 1
        require(eligible > 0, "No eligible complete attempted neural prefix for request " + request["request_id"])
    require(records, "Empty neural-prefix training set")
    return records, dict(request_counts=dict(counts), row_exclusions=dict(exclusions),
                         manifest_sha256=reviewed_sha, requests=requests,
                         loaded_role_pins=[dict(checkpoint=value[0], ngram=value[1], frontend_tokenizer_set=value[2])
                                           for value in sorted(cohort_asset_pins)],
                         sufficiency_scope="Counts are structural minima; root judges cohort breadth and precision")


def fit_normalizer(train):
    require(train.ndim == 2 and np.isfinite(train).all() and len(train), "Invalid train-only features")
    mean = train.mean(axis=0, dtype=np.float64).astype(np.float32)
    scale = train.std(axis=0, dtype=np.float64).astype(np.float32)
    scale[scale < 1e-6] = 1.
    return mean, scale


def normalize(value, mean, scale):
    return np.ascontiguousarray((value - mean) / scale, dtype=np.float32)


def softmax(logits):
    shifted = logits - np.max(logits, axis=1, keepdims=True)
    exp = np.exp(shifted)
    return exp / exp.sum(axis=1, keepdims=True)


def survival(probabilities):
    return np.column_stack((probabilities[:, 1] + probabilities[:, 2], probabilities[:, 2]))


def request_weights(ids):
    counts = Counter(ids)
    return np.array([1. / (len(counts) * counts[ident]) for ident in ids], dtype=np.float32)


def logits(x, weights):
    if "w1" in weights:
        return np.maximum(x @ weights["w1"] + weights["b1"], 0.) @ weights["w2"] + weights["b2"]
    return x @ weights["w"] + weights["b"]


def train(x, y, ids, *, hidden):
    """Fixed full-batch Adam; every request has equal total training weight."""
    rng = np.random.default_rng(SEED)
    if hidden:
        weights = dict(w1=rng.normal(0., math.sqrt(2./WIDTH), (WIDTH, HIDDEN)).astype(np.float32),
                       b1=np.zeros(HIDDEN, np.float32),
                       w2=rng.normal(0., math.sqrt(1./HIDDEN), (HIDDEN, CLASSES)).astype(np.float32),
                       b2=np.zeros(CLASSES, np.float32))
    else:
        weights = dict(w=np.zeros((WIDTH, CLASSES), np.float32), b=np.zeros(CLASSES, np.float32))
    onehot = np.eye(CLASSES, dtype=np.float32)[y]
    sample_weights = request_weights(ids)
    first = {name: np.zeros_like(value) for name, value in weights.items()}
    second = {name: np.zeros_like(value) for name, value in weights.items()}
    for step in range(1, EPOCHS+1):
        if hidden:
            pre = x @ weights["w1"] + weights["b1"]
            activation = np.maximum(pre, 0.)
            probability = softmax(activation @ weights["w2"] + weights["b2"])
        else:
            probability = softmax(logits(x, weights))
        delta = (probability - onehot) * sample_weights[:, None]
        if hidden:
            back = (delta @ weights["w2"].T) * (pre > 0.)
            gradients = dict(w1=x.T @ back + L2*weights["w1"], b1=back.sum(axis=0),
                             w2=activation.T @ delta + L2*weights["w2"], b2=delta.sum(axis=0))
        else:
            gradients = dict(w=x.T @ delta + L2*weights["w"], b=delta.sum(axis=0))
        for name in weights:
            first[name] = .9*first[name] + .1*gradients[name]
            second[name] = .999*second[name] + .001*gradients[name]**2
            weights[name] -= RATE*(first[name]/(1.-.9**step))/(np.sqrt(second[name]/(1.-.999**step))+1e-8)
    require(all(np.isfinite(value).all() for value in weights.values()), "Nonfinite trained weights")
    return weights


def metric_values(y, probability):
    observed = np.eye(CLASSES, dtype=np.float32)[y]
    q = survival(probability)
    target = np.column_stack((y >= 1, y >= 2)).astype(np.float32)
    return dict(log_loss=-np.log(np.maximum(probability[np.arange(len(y)), y], 1e-9)),
                multiclass_brier=np.sum((probability-observed)**2, axis=1),
                accuracy=(probability.argmax(axis=1) == y).astype(np.float32),
                prefix1_brier=(q[:, 0]-target[:, 0])**2,
                prefix2_brier=(q[:, 1]-target[:, 1])**2)


def metrics(y, probability, ids):
    require(probability.shape == (len(y), CLASSES) and np.isfinite(probability).all(), "Invalid probabilities")
    values = metric_values(y, probability)
    weights = request_weights(ids)
    per_request = {}
    for ident in sorted(set(ids)):
        mask = np.array([value == ident for value in ids])
        per_request[ident] = dict(rows=int(mask.sum()), **{name: float(value[mask].mean()) for name, value in values.items()})
    confusion = np.zeros((CLASSES, CLASSES), dtype=np.int64)
    for truth, predicted in zip(y, probability.argmax(axis=1)):
        confusion[truth, predicted] += 1
    calibration = {}
    for horizon in (1, 2):
        q = survival(probability)[:, horizon-1]
        bins = []
        for index in range(10):
            mask = np.minimum((q*10).astype(int), 9) == index
            if mask.any():
                bins.append(dict(bin=index, rows=int(mask.sum()), predicted=float(q[mask].mean()),
                                 observed=float((y[mask] >= horizon).mean())))
        calibration[str(horizon)] = bins
    skip = probability[:, 0] >= SKIP_THRESHOLD
    return dict(rows=len(y), requests=len(set(ids)),
                row_mean={name: float(value.mean()) for name, value in values.items()},
                request_macro={name: float(np.sum(value*weights)) for name, value in values.items()},
                confusion_true_rows_predicted_columns=confusion.tolist(), calibration=calibration,
                per_request=per_request, diagnostic_skip=dict(threshold=SKIP_THRESHOLD,
                    skipped_rows=int(skip.sum()), skipped_observed_class_counts=np.bincount(y[skip], minlength=3).tolist(),
                    scope="Observed label selection only; no throughput/counterfactual claim"))


def observed_cost_summary(records):
    status, samples = Counter(), []
    for record in records:
        row = record["row"]
        status[row.get("cost_status", "unavailable")] += 1
        elapsed = row.get("observed_begin_to_outcome_ns")
        if row.get("cost_status") == "observed":
            require(integer(elapsed, 0, (1 << 64)-1), "Invalid observed round cost")
            samples.append(elapsed)
    return dict(status_counts=dict(status), observed_rows=len(samples),
                observed_total_ns=sum(samples), observed_median_ns=float(np.median(samples)) if samples else None,
                scope="Actual stock begin-to-outcome including observer; neither committed-token wall time nor alternate width savings",
                speed_gain_established=False)


def paired_request_comparison(evaluation):
    """Resample whole test requests, never correlated individual decode rounds."""
    result = {}
    mlp = evaluation["mlp"]["per_request"]
    ids = sorted(mlp)
    rng = np.random.default_rng(SEED + 1)
    resamples = rng.integers(0, len(ids), size=(2000, len(ids)))
    for baseline in ("prior", "linear"):
        result[baseline] = {}
        for metric in ("log_loss", "multiclass_brier", "prefix1_brier", "prefix2_brier"):
            differences = np.array([mlp[ident][metric] - evaluation[baseline]["per_request"][ident][metric]
                                    for ident in ids], dtype=np.float64)
            draws = differences[resamples].mean(axis=1)
            result[baseline][metric] = dict(mlp_minus_baseline_mean=float(differences.mean()),
                request_bootstrap95_percentile=np.percentile(draws, [2.5, 97.5]).tolist(),
                requests_improved=int((differences < 0).sum()), requests=len(ids),
                per_request=dict(zip(ids, differences.tolist())))
    return dict(comparisons=result, resamples=2000, seed=SEED+1,
        scope="Paired whole-request prediction uncertainty; few requests give limited precision, no speed evidence")


def prepare_feed(row, values):
    """Same host feature packing/normalization input for every placement."""
    return {"features": normalize(features(row)[None, :], values["mean"], values["scale"])}


def decode_logits(value):
    """Same host postprocessing for every placement; ordinary/width2 diagnostic."""
    require(value.shape == (1, CLASSES) and value.dtype == np.float32 and np.isfinite(value).all(),
            "Placement returned invalid FP32 logits")
    probability = softmax(value)
    return dict(probabilities=probability[0].tolist(), survival=survival(probability)[0].tolist(),
                action="ordinary" if probability[0, 0] >= SKIP_THRESHOLD else "neural_width2")


def fit(args):
    require(all(os.environ.get(name) == "1" for name in
                ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")),
            "Set all three BLAS/OpenMP thread variables to1 before Python starts")
    freeze = verify_freeze()
    records, receipt = load_cohort(args.manifest, args.reviewed_manifest_sha256)
    require(not args.output.exists(), "Existing fit output refused")
    x = np.stack([features(record["row"]) for record in records])
    y = np.array([label(record["row"]) for record in records], dtype=np.int64)
    ids = [record["request_id"] for record in records]
    train_mask = np.array([record["split"] == "train" for record in records])
    require(set(y[train_mask]) == {0, 1, 2}, "Training requests do not cover all three observed prefix classes")
    mean, scale = fit_normalizer(x[train_mask])
    normalized = normalize(x, mean, scale)
    train_ids = [ident for ident, selected in zip(ids, train_mask) if selected]
    prior = (np.bincount(y[train_mask], weights=request_weights(train_ids), minlength=3) + .01)
    prior = (prior/prior.sum()).astype(np.float32)
    linear = train(normalized[train_mask], y[train_mask], train_ids, hidden=False)
    mlp = train(normalized[train_mask], y[train_mask], train_ids, hidden=True)
    predictions = dict(prior=np.tile(prior, (len(y), 1)), linear=softmax(logits(normalized, linear)),
                       mlp=softmax(logits(normalized, mlp)))
    results = {}
    for split, mask in (("train", train_mask), ("test", ~train_mask)):
        split_ids = [ident for ident, selected in zip(ids, mask) if selected]
        results[split] = {name: metrics(y[mask], probability[mask], split_ids) for name, probability in predictions.items()}
    args.output.mkdir(parents=True)
    arrays = dict(mean=mean, scale=scale, prior=prior,
                  **{"linear_"+name: value for name, value in linear.items()},
                  **{"mlp_"+name: value for name, value in mlp.items()})
    weights_path = args.output / "weights.npz"
    with weights_path.open("xb") as stream:
        np.savez(stream, **arrays)
    row_predictions = []
    for index, record in enumerate(records):
        row_predictions.append(dict(key={name: record["row"][name] for name in KEY_FIELDS},
            request_id=record["request_id"], split=record["split"], observed_class=int(y[index]),
            probabilities={name: value[index].tolist() for name, value in predictions.items()}))
    write_json(args.output / "predictions.json", row_predictions)
    report = dict(schema="halogen0173.token-prefix-predictor.v1", feature_version=FEATURE_VERSION,
        root_reviewed_manifest_sha256=args.reviewed_manifest_sha256, cohort=receipt,
        source_freeze_sha256=digest(HERE / "source-freeze.json"), sources=freeze["sources"],
        environment=dict(python=sys.version, numpy=np.__version__,
                         blas_threads={name: os.environ.get(name) for name in
                                       ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")}),
        weights_sha256=digest(weights_path), seed=SEED, feature_count=WIDTH,
        train_normalizer_sha256=hashlib.sha256(mean.tobytes()+scale.tobytes()).hexdigest(),
        training=dict(epochs=EPOCHS, learning_rate=RATE, l2=L2, optimizer="full-batch Adam",
                      weighting="equal total weight per train request", test_used_for_fitting=False),
        predictor=dict(shape=[WIDTH, HIDDEN, CLASSES], parameter_count=sum(value.size for value in mlp.values()),
                       fp32_parameter_bytes=sum(value.nbytes for value in mlp.values()),
                       normalizer_bytes=mean.nbytes+scale.nbytes, input_bytes=WIDTH*4, logit_output_bytes=CLASSES*4),
        evaluation=results, paired_test_prediction=paired_request_comparison(results["test"]),
        observed_cost=observed_cost_summary(records),
        trained_policy_speed_gain_established=False, placement_measured=False,
        diagnostic_skip_threshold=SKIP_THRESHOLD,
        limitation="Heldout prediction on stock trajectories; changed-policy end-to-end trials required for speed")
    write_json(args.output / "report.json", report)
    print(json.dumps({key: report[key] for key in ("schema", "predictor", "evaluation", "placement_measured")}))


def load_bundle(path):
    verify_freeze()
    report = read_json(path / "report.json")
    require(report.get("schema") == "halogen0173.token-prefix-predictor.v1" and
            report.get("feature_version") == FEATURE_VERSION and
            report.get("source_freeze_sha256") == digest(HERE / "source-freeze.json"), "Bundle/source contract differs")
    require(digest(path / "weights.npz") == report["weights_sha256"], "Trained weights differ")
    with np.load(path / "weights.npz", allow_pickle=False) as archive:
        values = {name: archive[name].copy() for name in archive.files}
    expected = dict(mean=(64,), scale=(64,), prior=(3,), linear_w=(64, 3), linear_b=(3,),
                    mlp_w1=(64, 16), mlp_b1=(16,), mlp_w2=(16, 3), mlp_b2=(3,))
    require(values.keys() == expected.keys() and all(values[name].shape == shape and
            values[name].dtype == np.float32 and np.isfinite(values[name]).all()
            for name, shape in expected.items()) and np.all(values["scale"] > 0), "Frozen bundle tensor contract differs")
    return values, report


def export(args):
    """Serialize identical normalized-feature FP32 Gemm/Relu/Gemm; no runtime."""
    values, report = load_bundle(args.bundle)
    import onnx
    from onnx import TensorProto, helper, numpy_helper
    require(not args.output.exists() and not args.output.with_suffix(".json").exists(), "Existing ONNX export refused")
    tensors = [numpy_helper.from_array(values["mlp_"+name], name) for name in ("w1", "b1", "w2", "b2")]
    nodes = [helper.make_node("Gemm", ["features", "w1", "b1"], ["hidden_pre"]),
             helper.make_node("Relu", ["hidden_pre"], ["hidden"]),
             helper.make_node("Gemm", ["hidden", "w2", "b2"], ["logits"])]
    graph = helper.make_graph(nodes, "token_only_prefix2", [helper.make_tensor_value_info("features", TensorProto.FLOAT, [1, 64])],
                              [helper.make_tensor_value_info("logits", TensorProto.FLOAT, [1, 3])], tensors)
    model = helper.make_model(graph, producer_name="strix-alloy-token-selector", opset_imports=[helper.make_opsetid("", 17)])
    model.ir_version = 8
    helper.set_model_props(model, dict(feature_version=FEATURE_VERSION, source_freeze_sha256=report["source_freeze_sha256"],
        weights_sha256=report["weights_sha256"], preprocessing="host; frozen train mean/scale; FP32",
        decision="host stable softmax; diagnostic skip if P(class0)>=0.65; no live policy"))
    onnx.checker.check_model(model)
    with args.output.open("xb") as stream:
        stream.write(model.SerializeToString())
    write_json(args.output.with_suffix(".json"), dict(schema="halogen0173.selector-onnx.v1", model_sha256=digest(args.output),
        model_bytes=args.output.stat().st_size, report_sha256=digest(args.bundle / "report.json"),
        weights_sha256=report["weights_sha256"], operators=[node.op_type for node in nodes],
        opset=17, ir_version=8, same_computation_required=True, placement_measured=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    fit_parser = commands.add_parser("fit")
    fit_parser.add_argument("--manifest", type=Path, required=True)
    fit_parser.add_argument("--reviewed-manifest-sha256", required=True)
    fit_parser.add_argument("--output", type=Path, required=True)
    fit_parser.set_defaults(run=fit)
    export_parser = commands.add_parser("export")
    export_parser.add_argument("--bundle", type=Path, required=True)
    export_parser.add_argument("--output", type=Path, required=True)
    export_parser.set_defaults(run=export)
    args = parser.parse_args()
    args.run(args)


if __name__ == "__main__":
    main()
