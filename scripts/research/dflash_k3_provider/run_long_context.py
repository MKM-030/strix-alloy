"""Root-owned fixed16K component fixture, default off; no inference at import.

One16640-capacity cache, synthetic16384-row committed prefix projected in
bounded chunks, same actual resident weights/head, repeat versus grouped2D.
Repeated graph calls do not advance a request or fabricate target verification.
"""
import argparse
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import time

from abi import OwnerStamp, resource_plan
from provider import prepare_from_assets, reference_directory, reference_modules
from tensor_graphs import make_tensor_graphs


def run(args):
    contract, loader, compare = reference_modules()
    from owner_oracle import PinnedOwnerOracle, error_record, SOURCE_HASHES
    torch = loader.cpu_torch()
    torch.set_num_threads(args.threads)
    destination = Path(args.output).resolve()
    if destination.exists():
        raise FileExistsError("A new root-owned report path is required")
    stamp = OwnerStamp("00" * 16, 1, 1, 1, "SYNTHETIC_LONG_CONTEXT_NO_NATIVE_OWNER", 0, 1,
        request_birth="synthetic-16k-birth", holder_identity=2, model_address=3,
        request_address=4, total_prefill=16384)
    preparation_started = time.perf_counter_ns()
    worker = prepare_from_assets(checkpoint=args.checkpoint, config=args.config,
        bindings_receipt=args.bindings_receipt, capacity=16640, stamp=stamp,
        device=args.device, compute_dtype="bf16", attention_mode="repeat", head_mode="full_bf16")
    resident_weights = {name: (worker.graphs.context.weight(name) if name in worker.graphs.context._keys
        else worker.graphs.backbone.weight(name)) for name in worker.asset_owners[0].tensors}
    alternative = make_tensor_graphs(torch, weights=resident_weights,
        full_head=worker.graphs.head.full_head, capacity=16640,
        compute_dtype="bf16", attention_mode="grouped2d", head_mode="full_bf16")
    alternative.backbone.to(device=worker.device)
    for name in alternative.backbone._keys:
        if alternative.backbone.weight(name).data_ptr() != resident_weights[name].data_ptr():
            raise AssertionError("Paired alternative unexpectedly copied learned resident storage")
    if alternative.head.full_head.data_ptr() != worker.graphs.head.full_head.data_ptr():
        raise AssertionError("Paired alternative copied the original full head")
    preparation_ns = time.perf_counter_ns() - preparation_started
    chunks, retained_features = [], []
    prefill_started = time.perf_counter_ns()
    with torch.inference_mode():
        for start in range(0, 16384, args.prefill_chunk_rows):
            count = min(args.prefill_chunk_rows, 16384 - start)
            generated_at = time.perf_counter_ns()
            features = compare.synthetic_features(torch, count, offset=start * 12800, dtype=torch.bfloat16)
            projection_started = time.perf_counter_ns()
            worker.append_prefill(stamp=stamp, features=features, input_ids=(0,) * count,
                positions=tuple(range(start, start + count)), final=start + count == 16384)
            if args.compare_cpu_owner:
                retained_features.append(features)
            chunks.append({"start": start, "rows": count,
                "synthetic_CPU_feature_generation_ns": projection_started - generated_at,
                "owned_host_feature_to_projected_cache_append_ns": time.perf_counter_ns() - projection_started})
        if not bool(torch.isfinite(worker.cache).all().item()):
            raise ValueError("Nonfinite long committed cache")
        prefill_ns = time.perf_counter_ns() - prefill_started
        cache_version, cache_address = worker.cache._version, worker.cache.data_ptr()
        query_positions = (16384, 16385, 16386)
        owner_hidden = owner_logits = None
        owner_ns = None
        if args.compare_cpu_owner:
            cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
            oracle = PinnedOwnerOracle(SimpleNamespace(torch=torch, config=cfg,
                _weights=worker.asset_owners[0].tensors, _head=worker.asset_owners[2]._head,
                dtype=torch.bfloat16))
            complete = torch.cat(retained_features, dim=0)
            CPU_anchor, CPU_mask = worker.embedding_rows[1], worker.asset_owners[2]._mask
            started = time.perf_counter_ns()
            owner_hidden, owner_logits = oracle.forward(complete_context_features=complete,
                context_positions=tuple(range(16384)),
                query_embeddings=torch.stack((CPU_anchor, CPU_mask, CPU_mask), dim=0)[None],
                query_positions=query_positions)
            owner_ns = time.perf_counter_ns() - started
        backbones = {"repeat": worker.graphs.backbone, "grouped2d": alternative.backbone}

        def evaluate(label):
            started = time.perf_counter_ns()
            anchor = worker.embedding_rows[1].detach().to(device=worker.device, dtype=torch.bfloat16).clone()
            if not bool(torch.isfinite(anchor).all().item()):
                raise ValueError("Nonfinite actual anchor row")
            query = torch.stack((anchor, worker.mask, worker.mask), dim=0)
            cos, sin = worker._rope(query_positions)
            length = torch.tensor(16384, dtype=torch.long, device=worker.device)
            prepared_at = time.perf_counter_ns()
            hidden, valid = backbones[label](worker.cache, length, query, cos, sin)
            if not bool(valid.item()):
                raise ValueError("Nonfinite long-context backbone output")
            backbone_at = time.perf_counter_ns()
            ids, valid, logits = worker.graphs.head(hidden)
            if not bool(valid.item()):
                raise ValueError("Nonfinite original full-BF16 head output")
            raw_ids = tuple(int(value) for value in ids.tolist())
            finished_at = time.perf_counter_ns()
            CPU_hidden, CPU_logits = hidden.detach().cpu()[None], logits.detach().cpu()[None]
            record = {"attention_mode": label, "head_mode": "full_bf16", "raw_ids": list(raw_ids),
                "input_prepare_ns": prepared_at - started,
                "backbone_including_finite_sync_ns": backbone_at - prepared_at,
                "full_head_including_finite_sync_and_host_ID_copy_ns": finished_at - backbone_at,
                "component_draft_total_ns": finished_at - started,
                "all_hidden_and_logits_finite": bool(torch.isfinite(CPU_hidden).all() & torch.isfinite(CPU_logits).all())}
            if owner_hidden is not None:
                expected_ids = tuple(int(value) for value in owner_logits[0].argmax(-1).tolist())
                record.update(CPU_owner_hidden=error_record(CPU_hidden, owner_hidden),
                    CPU_owner_full_vocab_logits=error_record(CPU_logits, owner_logits),
                    CPU_owner_raw_ids=list(expected_ids), CPU_owner_raw_id_equality=raw_ids == expected_ids)
            return record, CPU_hidden, CPU_logits

        warmups = [evaluate(label)[0] for label in ("repeat", "grouped2d")]
        pairs = []
        for index, order in enumerate((("repeat", "grouped2d"), ("grouped2d", "repeat"), ("repeat", "grouped2d"))):
            results = {label: evaluate(label) for label in order}
            pairs.append({"pair_index": index, "execution_order": list(order),
                "variants": {label: result[0] for label, result in results.items()},
                "direct_raw_id_equality": results["repeat"][0]["raw_ids"] == results["grouped2d"][0]["raw_ids"],
                "direct_repeat_vs_grouped2d_hidden": error_record(results["repeat"][1], results["grouped2d"][1]),
                "direct_repeat_vs_grouped2d_full_vocab_logits": error_record(results["repeat"][2], results["grouped2d"][2])})
        cache_unchanged = worker.cache._version == cache_version and worker.cache.data_ptr() == cache_address
        if not cache_unchanged or len(worker.ids) != 16384 or not worker.prefill_complete:
            raise AssertionError("Paired component calls changed committed cache/frontier")
    sources = [Path(__file__).resolve()] + [Path(__file__).with_name(name) for name in
        ("abi.py", "provider.py", "tensor_graphs.py", "scalar_support.py")]
    sources += [reference_directory() / name for name in
        ("contract.py", "offline_loader.py", "reference.py", "owner_oracle.py", "compare.py")]
    report = {"schema": "dflash_fixed_16k_component_pair.v1", "enabled": False,
        "device": args.device, "device_name": torch.cuda.get_device_name(worker.device) if args.device == "cuda" else "CPU",
        "torch_version": str(torch.__version__), "torch_version_hip": getattr(torch.version, "hip", None),
        "compute_dtype": "BF16", "threads": args.threads, "capacity": 16640, "committed_prefix_rows": 16384,
        "query_positions": list(query_positions), "prefill_chunk_rows": args.prefill_chunk_rows,
        "checkpoint_sha256": contract.CHECKPOINT_SHA256, "original_head_sha256": worker.asset_owners[1].sha256,
        "pinned_owner_source_sha256": SOURCE_HASHES, "implementation_source_sha256": {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
        "resources": resource_plan(16640), "shared_learned_storage_asserted": True,
        "preparation_ns": preparation_ns, "prefill_total_including_CPU_generation_and_final_cache_finite_sync_ns": prefill_ns,
        "prefill_chunks": chunks, "excluded_warmups": warmups, "measured_pairs": pairs,
        "CPU_owner_compared": args.compare_cpu_owner, "independent_CPU_owner_forward_ns": owner_ns,
        "CPU_accuracy_qualified": False,
        "source_scope": "deterministic_synthetic_HCconcat_prefix_and_actual_anchor/mask/head;no_native_target_capture",
        "timing_scope": "synchronous_components_with_finite_syncs_and_host_ID_copy;no_native_tap_transport_verifier_commit_or_output;fixed_same_cache_and_same_inputs",
        "cache_unchanged_after_pairs": cache_unchanged, "native_transport_measured": False,
        "target_acceptance_measured": False, "serving_throughput_measured": False, "server_activation": False}
    destination.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"report": str(destination), "device": args.device,
        "committed_prefix_rows": 16384, "capacity": 16640, "measured_pairs": pairs}, indent=2))
    records = warmups + [r for pair in pairs for r in pair["variants"].values()]
    return 0 if all(r["all_hidden_and_logits_finite"] for r in records) and cache_unchanged else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute-root-owned", action="store_true", required=True)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--bindings-receipt", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument("--threads", type=int, choices=(1, 2, 3, 4), default=2)
    parser.add_argument("--prefill-chunk-rows", type=int, choices=(64, 128, 256, 512), default=128)
    parser.add_argument("--compare-cpu-owner", action="store_true", help="explicit long CPU oracle;retains400MiB synthetic features;no head/model reload")
    return run(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
