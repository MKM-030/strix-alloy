"""Root-owned explicit CPU/GPU component comparison. No inference at import.

Two synthetic K3 rounds plus cache-control rejection. No actual target capture,
native integration, target acceptance, transport qualification or tok/s claim.
"""
import argparse
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import time

from abi import OwnerStamp, resource_plan
from provider import prepare_from_assets, reference_modules, reference_directory


def run(args):
    contract, loader, compare = reference_modules()
    from owner_oracle import PinnedOwnerOracle, error_record, SOURCE_HASHES
    torch = loader.cpu_torch()
    torch.set_num_threads(args.threads)
    stamp = OwnerStamp("00" * 16, 1, 1, 1, "SYNTHETIC_ONLY_NO_NATIVE_OWNER", 0, 1,
                       request_birth="synthetic-birth", holder_identity=2,
                       model_address=3, request_address=4, total_prefill=4)
    preparation_started = time.perf_counter_ns()
    worker = prepare_from_assets(checkpoint=args.checkpoint, config=args.config,
        bindings_receipt=args.bindings_receipt, capacity=args.capacity,
        stamp=stamp, device=args.device, compute_dtype="bf16",
        attention_mode=args.attention_mode, head_mode=args.head_mode)
    worker.retain_diagnostics = True
    cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
    shim = SimpleNamespace(torch=torch, config=cfg, _weights=worker.asset_owners[0].tensors,
        _head=worker.asset_owners[2]._head, dtype=torch.bfloat16)
    oracle = PinnedOwnerOracle(shim)
    preparation_ns = time.perf_counter_ns() - preparation_started
    mask = worker.asset_owners[2]._mask
    embeddings = worker.embedding_rows
    rounds = []
    head_pairs = {"warmups": [], "measured_pairs": [],
        "scope": "same_already_computed_second_round_hidden_and_resident_BF16_head;one_excluded_warmup_per_head_then_three_alternating_order_pairs;no_serving_throughput_claim"}

    def compare_round(ready, complete, anchor):
        with torch.inference_mode():
            query = torch.stack((anchor, mask, mask), dim=0)[None]
            pos = (ready.position, ready.position + 1, ready.position + 2)
            reference_started = time.perf_counter_ns()
            hidden, logits = oracle.forward(complete_context_features=complete,
                context_positions=tuple(range(complete.shape[0])), query_embeddings=query,
                query_positions=pos)
            reference_ns = time.perf_counter_ns() - reference_started
            actual_hidden = worker.last_hidden.detach().cpu()[None]
            actual_logits = worker.last_logits.detach().cpu()[None]
            owner_ids = tuple(int(x) for x in logits[0].argmax(dim=-1).tolist())
            item = {
                "round_index": ready.round_index, "accepted_context_length": ready.position,
                "provider_raw_ids": list(ready.raw_ids), "owner_raw_ids": list(owner_ids),
                "raw_id_equality": ready.raw_ids == owner_ids,
                "hidden": error_record(actual_hidden, hidden),
                "full_vocab_logits": error_record(actual_logits, logits),
                "worker_host_phase_ns": dict(ready.host_phase_ns),
                "independent_CPU_owner_forward_ns": reference_ns,
                "measurement_scope": "synchronous_component_worker_including_explicit_finite_syncs_and_host_ID_copy;no_native_or_transport",
            }
            rounds.append(item)
            if args.pair_head and ready.round_index == 1:
                from tensor_graphs import make_full_head_bf16
                alternative = make_full_head_bf16(torch, worker.graphs.head.full_head)
                # Same already-computed hidden and same resident head; no extra
                # backbone, model load, learned matrix copy or transport call.
                heads = {"chunked": worker.graphs.head, "full_bf16": alternative}

                def evaluate_head(label):
                    started = time.perf_counter_ns()
                    ids, finite, values = heads[label](worker.last_hidden)
                    if not bool(finite.item()):
                        raise ValueError("Paired head produced nonfinite logits")
                    raw = tuple(int(x) for x in ids.tolist())
                    finished = time.perf_counter_ns()
                    cpu_values = values.detach().cpu()[None]
                    record = {"mode": label,
                        "host_wall_ns_including_finite_sync_and_host_ID_copy": finished - started,
                        "provider_raw_ids": list(raw), "owner_raw_ids": list(owner_ids),
                        "raw_id_equality": raw == owner_ids,
                        "CPU_owner_full_vocab_logits": error_record(cpu_values, logits)}
                    return record, cpu_values

                for label in ("chunked", "full_bf16"):
                    record, _ = evaluate_head(label)
                    head_pairs["warmups"].append(record)
                for pair_index, order in enumerate((("chunked", "full_bf16"),
                        ("full_bf16", "chunked"), ("chunked", "full_bf16"))):
                    results = {label: evaluate_head(label) for label in order}
                    head_pairs["measured_pairs"].append({"pair_index": pair_index,
                        "execution_order": list(order),
                        "heads": {label: result[0] for label, result in results.items()},
                        "direct_raw_id_equality": results["chunked"][0]["provider_raw_ids"] == results["full_bf16"][0]["provider_raw_ids"],
                        "direct_chunked_vs_full_BF16_logits": error_record(results["chunked"][1], results["full_bf16"][1])})

    with torch.inference_mode():
        prefill = compare.synthetic_features(torch, 4, offset=0, dtype=torch.bfloat16)
        prefill_started = time.perf_counter_ns()
        worker.append_prefill(stamp=stamp, features=prefill, input_ids=(0, 1, 1000, 0), positions=(0, 1, 2, 3), final=True)
        prefill_ns = time.perf_counter_ns() - prefill_started
        ready = worker.propose(stamp=stamp, round_index=0, current_id=1, anchor_embedding=embeddings[1])
        compare_round(ready, prefill, embeddings[1])
        if not ready.offerable:
            raise ValueError("Reserved raw full-head ID cannot enter control verifier fixture")
        verifier = compare.synthetic_features(torch, 4, offset=90000, dtype=torch.bfloat16)
        verifier[2:] = float("nan")
        update_started = time.perf_counter_ns()
        worker.apply_verification(stamp=stamp, round_index=0, verifier_features=verifier,
            verifier_ids=(1,) + ready.raw_ids, verifier_positions=(4, 5, 6, 7),
            accepted_prefix=1, authoritative_bonus_id=23)
        update_ns = time.perf_counter_ns() - update_started
        complete = torch.cat((prefill, verifier[:2]), dim=0)
        second = worker.propose(stamp=stamp, round_index=1, current_id=23, anchor_embedding=embeddings[23])
        compare_round(second, complete, embeddings[23])
        if not second.offerable:
            raise ValueError("Reserved second raw ID cannot enter accepted-row invalidity fixture")
        invalid = compare.synthetic_features(torch, 4, offset=180000, dtype=torch.bfloat16)
        invalid[0] = float("nan")
        try:
            worker.apply_verification(stamp=stamp, round_index=1, verifier_features=invalid,
                verifier_ids=(23,) + second.raw_ids, verifier_positions=(6, 7, 8, 9),
                accepted_prefix=0, authoritative_bonus_id=1)
        except ValueError as exc:
            if str(exc) != "Non-finite selected target features":
                raise
            if not worker.retired or worker.cache is not None or worker.ids or worker.positions:
                raise AssertionError("Non-finite selected row did not retire/clear provider state")
        else:
            raise AssertionError("Non-finite selected current row entered committed context")
    source_files = [Path(__file__), Path(__file__).with_name("abi.py"),
        Path(__file__).with_name("provider.py"), Path(__file__).with_name("tensor_graphs.py"),
        Path(__file__).with_name("scalar_support.py")]
    source_files += [reference_directory() / n for n in
        ("contract.py", "offline_loader.py", "reference.py", "owner_oracle.py", "compare.py")]
    report = {
        "schema": "dflash_fixed_capacity_component_comparison.v2",
        "device": args.device, "capacity": args.capacity, "torch_version": str(torch.__version__),
        "torch_version_hip": getattr(torch.version, "hip", None),
        "device_name": torch.cuda.get_device_name(worker.device) if args.device == "cuda" else "CPU",
        "attention_mode": args.attention_mode, "head_mode": args.head_mode,
        "compute_dtype": "BF16", "threads": args.threads,
        "feature_scope": "deterministic_synthetic_HCconcat;not_native_target_captured_features",
        "source_cpu_oracle": "pinned_owner_dynamic_accepted_context;exact_actual58_weights_and_full_original_head",
        "fixed_capacity_rounding": "masked_padded_context_may_change_kernel_reduction_order;report_every_error;no_invented_tolerance",
        "checkpoint_sha256": contract.CHECKPOINT_SHA256,
        "original_head_sha256": worker.asset_owners[1].sha256,
        "pinned_owner_source_sha256": SOURCE_HASHES,
        "implementation_source_sha256": {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in source_files},
        "resources": resource_plan(args.capacity),
        "preparation_ns": preparation_ns, "prefill_project_and_stage_ns": prefill_ns,
        "first_commit_context_update_ns": update_ns,
        "first_update_plus_second_propose_ns": update_ns + dict(second.host_phase_ns)["worker_propose_total"],
        "rounds": rounds,
        "head_pair": head_pairs,
        "control_fixture": {"selector1_discarded_two_NaN_rejected_rows": True,
            "selector0_NaN_selected_current_rejected_and_retired": True,
            "selectors_are_injected_test_controls_not_target_acceptance": True},
        "native_transport_measured": False, "target_acceptance_measured": False,
        "serving_throughput_measured": False, "server_activation": False,
    }
    destination = Path(args.output).resolve()
    destination.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"report": str(destination), "rounds": rounds,
                      "control_fixture": report["control_fixture"]}, indent=2, allow_nan=False))
    rounds_ok = all(r["raw_id_equality"] and r["hidden"]["all_values_finite"] and r["full_vocab_logits"]["all_values_finite"] for r in rounds)
    head_records = head_pairs["warmups"] + [r for pair in head_pairs["measured_pairs"] for r in pair["heads"].values()]
    pairs_ok = (all(r["raw_id_equality"] and r["CPU_owner_full_vocab_logits"]["all_values_finite"] for r in head_records)
        and all(pair["direct_raw_id_equality"] and pair["direct_chunked_vs_full_BF16_logits"]["all_values_finite"] for pair in head_pairs["measured_pairs"]))
    return 0 if rounds_ok and pairs_ok else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--bindings-receipt", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument("--capacity", type=int, choices=(8, 16), default=8)
    parser.add_argument("--threads", type=int, choices=(1, 2, 3, 4), default=2)
    parser.add_argument("--attention-mode", choices=("repeat", "grouped2d"), default="repeat")
    parser.add_argument("--head-mode", choices=("chunked", "full_bf16"), default="chunked")
    parser.add_argument("--pair-head", action="store_true")
    args = parser.parse_args()
    if args.pair_head and args.head_mode != "chunked":
        parser.error("Head pair requires baseline chunked head")
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
