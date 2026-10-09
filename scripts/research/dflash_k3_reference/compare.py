"""Explicitly synthetic CPU parity fixture using real drafter/head/embedding data.

This command performs numerical inference ONLY when explicitly executed by the
caller. It is offline: no downloads, accelerator APIs, or dependency installs.
The injected prefix selector is a cache-control stimulus, NOT measured target
acceptance. Synthetic target features are labelled in every output report.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from contract import (CHECKPOINT_REVISION, CHECKPOINT_SHA256, HIDDEN, MASK_ID,
                      OWNER_REVISION, TOKENIZER_SHA256, VOCAB)
from offline_loader import OwnedTensorFile, cpu_torch
from owner_oracle import PinnedOwnerOracle, compare_proposal
from reference import (K3Reference, NonFiniteTensorError, TargetBinding,
                       TargetEmbedding, TargetIdentity, TargetRows)

ORIGINAL_REPO = "Qwen/Qwen3.8-Flash-Next"
ORIGINAL_REVISION = "f5d08274bafd880402bd16f5e3e6c514136ec06c"
ORIGINAL_HEAD_SHA = "50be0ccd11e4da0c92114600aca321d2c18f795e9e923fd587469587ecfd9df4"


def load_binding_receipt(path, torch):
    receipt = json.loads(Path(path).read_text(encoding="utf-8"))
    if receipt["repo"] != ORIGINAL_REPO or receipt["revision"] != ORIGINAL_REVISION:
        raise ValueError("Numerical fixture requires the exact trained original bindings")
    head_receipt = receipt["head"]
    if head_receipt["sha256"] != ORIGINAL_HEAD_SHA or not head_receipt["whole_shard_hash_verified"]:
        raise ValueError("Original full-head shard receipt is not the checked pinned shard")
    head_file = OwnedTensorFile(head_receipt["path"], expected_sha256=ORIGINAL_HEAD_SHA)
    if set(head_file.tensors) != {"lm_head.weight"}:
        raise ValueError("Fixture requires the full original head-only shard")
    rows, row_receipts = {}, {}
    for item in receipt["embedding_rows"]:
        token_id = item["token_id"]
        if token_id in rows:
            raise ValueError("Duplicate embedding row receipt")
        body = Path(item["path"]).read_bytes()
        if len(body) != 2 * HIDDEN or hashlib.sha256(body).hexdigest() != item["sha256"]:
            raise ValueError(f"Embedding row{token_id} differs from its exact range receipt")
        rows[token_id] = torch.frombuffer(bytearray(body), dtype=torch.bfloat16).clone()
        row_receipts[token_id] = item
    if not {0, 1, 23, 1000, MASK_ID} <= rows.keys():
        raise ValueError("Synthetic fixture requires real rows0,1,23,1000,248077")
    identity = TargetIdentity(ORIGINAL_REPO, ORIGINAL_REVISION, TOKENIZER_SHA256,
        "whole_head_shard_sha256:" + ORIGINAL_HEAD_SHA,
        "pinned_HTTPS_206_rows;row_SHA256_checked;whole_embedding_shard_SHA256_not_checked",
        "synthetic_deterministic_HCconcat_stimuli;not_captured_target_hidden_states")
    binding = TargetBinding(full_head=head_file.tensors["lm_head.weight"],
                            mask_embedding=rows[MASK_ID], identity=identity)
    return binding, rows, row_receipts, head_file


def synthetic_features(torch, count, *, offset, dtype):
    # These are input stimuli, never substitute model parameters or embeddings.
    index = torch.arange(count * 5 * HIDDEN, dtype=torch.float32, device="cpu") + offset
    return (index.mul(0.017).sin() + index.mul(0.007).cos().mul(0.25)).reshape(count, 5 * HIDDEN).to(dtype)


def run(args):
    torch = cpu_torch()
    torch.set_num_threads(args.threads)
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    binding, embeddings, row_receipts, head_owner = load_binding_receipt(args.bindings_receipt, torch)
    provider = K3Reference(checkpoint_path=args.checkpoint, config=config, binding=binding,
        compute_dtype=args.dtype, request_nonce="offline-synthetic-parity", epoch=0)
    oracle = PinnedOwnerOracle(provider)
    with torch.inference_mode():
        prefill = synthetic_features(torch, 4, offset=0, dtype=provider.dtype)
        provider.initialize(TargetRows(prefill, (0, 1, 1000, 0), (0, 1, 2, 3), binding.identity))
        anchor = TargetEmbedding(1, embeddings[1], binding.identity)
        proposal = provider.propose(anchor=anchor, round_index=0)
        rounds = [compare_proposal(provider, oracle, proposal=proposal,
            complete_context_features=prefill, anchor=anchor, atol=args.atol, rtol=args.rtol)]
        cache_control = {"source": "injected_synthetic_control_fixture;NOT_target_acceptance",
                         "accepted_prefix_selector": 1,
                         "rejected_feature_rows_poisoned_with_NaN": 2}
        accepted_nonfinite = {
            "source": "injected_synthetic_control_fixture;NOT_target_acceptance",
            "accepted_prefix_selector": 0,
            "selected_current_row_poisoned_with_NaN": True,
            "executed": False,
        }
        if proposal.offerable:
            verifier = synthetic_features(torch, 4, offset=90000, dtype=provider.dtype)
            verifier[2:] = float("nan")
            provider.apply_verification(rows=TargetRows(verifier, (1,) + proposal.raw_ids,
                (4, 5, 6, 7), binding.identity), round_index=0,
                accepted_prefix=1, authoritative_bonus_id=23)
            complete = torch.cat((prefill, verifier[:2]), dim=0)
            next_anchor = TargetEmbedding(23, embeddings[23], binding.identity)
            next_proposal = provider.propose(anchor=next_anchor, round_index=1)
            rounds.append(compare_proposal(provider, oracle, proposal=next_proposal,
                complete_context_features=complete, anchor=next_anchor,
                atol=args.atol, rtol=args.rtol))
            cache_control.update(executed=True, context_length=provider.context_length,
                retained_ids=list(provider.accepted_ids), retained_positions=list(provider.accepted_positions),
                expected_context_length=6)
            if next_proposal.offerable:
                # Reuse the pending second proposal and the same loaded model.
                # Selector0 selects only current input row0; that selected row
                # must fail before fusion/projection and retire/clear the cache.
                invalid = synthetic_features(torch, 4, offset=180000, dtype=provider.dtype)
                invalid[0] = float("nan")
                try:
                    provider.apply_verification(rows=TargetRows(invalid,
                        (23,) + next_proposal.raw_ids, (6, 7, 8, 9), binding.identity),
                        round_index=1, accepted_prefix=0, authoritative_bonus_id=1)
                except NonFiniteTensorError as exc:
                    if exc.tensor_role != "selected target features":
                        raise
                    retired = provider.frontier._retired
                    cleared = (provider._context_kv is None and provider.context_length == 0
                               and provider.accepted_ids == () and provider.accepted_positions == ())
                    if not retired or not cleared:
                        raise AssertionError("Non-finite selected row did not retire and clear the request")
                    accepted_nonfinite.update(executed=True, rejected=True,
                        request_retired=retired, cache_cleared=cleared,
                        rejection_role=exc.tensor_role)
                else:
                    raise AssertionError("Non-finite selected row was accepted into target-context KV")
            else:
                accepted_nonfinite["reason"] = "Second proposal contains a reserved ID; cannot offer it"
        else:
            cache_control.update(executed=False, reason="Raw full-head argmax includes a reserved ID; cannot offer it")
            accepted_nonfinite["reason"] = "No offerable second proposal was produced"
        provider.retire()
    report = {
        "scope": "offline_CPU_numerical_parity_on_explicitly_synthetic_feature_stimuli",
        "target_acceptance_measured": False, "serving_performance_measured": False,
        "checkpoint_revision": CHECKPOINT_REVISION, "checkpoint_sha256": CHECKPOINT_SHA256,
        "owner_revision": OWNER_REVISION, "hf_primitives_version": "5.16.1",
        "k3_scope": "custom_mathematical_reference_q_len3;NOT_authored_vLLM_serving_configuration",
        "authored_epoch7_serving_scope": "K4/K5/K7;TP2;enforce_eager;K3_acceptance_generalization_unqualified",
        "torch_version": str(torch.__version__), "device": "cpu", "threads": args.threads,
        "compute_dtype": args.dtype, "head_rows_evaluated_per_query": VOCAB,
        "head_projection_chunk_rows": 8192,
        "target_identity": vars(binding.identity),
        "head_shard_sha256": head_owner.sha256,
        "embedding_row_receipts": list(row_receipts.values()),
        "embedding_provenance_limit": "Row hashes match fetched pinned HTTPS206 ranges; whole embedding shard not fetched/hashed",
        "oracle": "exact_AST_extracted_owner_backbone_and_HF_math;all58_real_parameters_bound_before_CPU_forward",
        "rounds": rounds, "cache_control_fixture": cache_control,
        "accepted_nonfinite_control_fixture": accepted_nonfinite,
    }
    if args.atol is not None:
        report["caller_tolerance_pass"] = all(r["hidden"]["allclose"] and r["logits"]["allclose"] for r in rounds)
    output = Path(args.output).resolve()
    output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"report": str(output), "rounds": rounds,
                      "cache_control_fixture": cache_control,
                      "accepted_nonfinite_control_fixture": accepted_nonfinite}, indent=2, allow_nan=False))
    return 0 if (accepted_nonfinite["executed"]
        and all(r["raw_id_equality"] and r["hidden"]["all_values_finite"] and r["logits"]["all_values_finite"] for r in rounds)
        and report.get("caller_tolerance_pass", True)) else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--bindings-receipt", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--dtype", choices=("bf16", "float32"), default="bf16")
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--atol", type=float)
    parser.add_argument("--rtol", type=float)
    args = parser.parse_args()
    if not 1 <= args.threads <= 4 or (args.atol is None) != (args.rtol is None):
        parser.error("Use1..4 CPU threads and supply both tolerances or neither")
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
