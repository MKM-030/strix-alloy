"""Root-owned CPU BF16 fixture from pinned owner AST; no head or accelerator.

No inference at import. Root may explicitly freeze a synthetic row or one actual
already-selected retained BF16 HCconcat row for the separate NPU process.
"""
import argparse
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import time

from provider import reference_modules


def prepare(args):
    contract, loader, compare = reference_modules()
    from owner_oracle import PinnedOwnerOracle, SOURCE_HASHES
    torch = loader.cpu_torch()
    torch.set_num_threads(2)
    owned_weights = loader.load_drafter(args.checkpoint)
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    contract.validate_config(config)
    oracle = PinnedOwnerOracle(SimpleNamespace(torch=torch, config=config,
        _weights=owned_weights.tensors, _head=None, dtype=torch.bfloat16))
    destination = Path(args.output_directory).resolve()
    destination.mkdir(parents=True, exist_ok=False)
    with torch.inference_mode():
        if args.features_raw:
            payload = Path(args.features_raw).read_bytes()
            if len(payload) != 25600:
                raise ValueError("Only the single already-selected actual BF16 row is accepted")
            features = torch.frombuffer(bytearray(payload), dtype=torch.bfloat16).reshape(1, 12800).clone()
        else:
            features = compare.synthetic_features(torch, 1, offset=args.synthetic_offset, dtype=torch.bfloat16)
        if not bool(torch.isfinite(features).all()):
            raise ValueError("Selected fixture row is nonfinite")
        model = oracle._model
        fused = model.hidden_norm(model.fc(features[None]))
        position = torch.tensor([[args.position]], dtype=torch.long, device="cpu")
        cos, sin = model.rotary_emb(fused, position)
        calls = []
        first_kv = None
        for call_index in range(4):
            started = time.perf_counter_ns()
            owned_features, owned_cos, owned_sin = features.clone(), cos.clone(), sin.clone()
            fused = model.hidden_norm(model.fc(owned_features[None]))
            projected = []
            for layer in model.layers:
                attention = layer.self_attn
                key = attention.k_norm(attention.k_proj(fused).view(1, 1, 2, 256)).transpose(1, 2)
                value = attention.v_proj(fused).view(1, 1, 2, 256).transpose(1, 2)
                # This is the actual pinned owner's RoPE function/global namespace.
                owner_rope = attention.forward.__func__.__globals__["apply_rotary_pos_emb"]
                _, key = owner_rope(key, key, owned_cos, owned_sin)
                projected.append(torch.stack((key[0], value[0]), dim=0))
            kv = torch.stack(projected, dim=0)
            healthy = bool(torch.isfinite(kv).all())
            returned = kv.clone()
            finished = time.perf_counter_ns()
            if not healthy:
                raise ValueError("Nonfinite source CPU context projection")
            if first_kv is None:
                first_kv = returned
            calls.append({"call_index": call_index, "excluded_warmup": call_index == 0,
                "source_CPU_host_input_to_owned_KV_return_ns": finished - started,
                "exact_equal_to_first_output": bool(torch.equal(returned, first_kv))})
        tensors = {"target_features": features, "cos": cos[0], "sin": sin[0], "context_kv": kv}
        rows = {}
        for name, value in tensors.items():
            if value.device.type != "cpu" or value.dtype != torch.bfloat16 or not bool(torch.isfinite(value).all()):
                raise ValueError("Invalid CPU source fixture tensor: " + name)
            payload = value.detach().contiguous().view(torch.int16).numpy().tobytes()
            path = destination / f"{name}.bf16.bin"
            path.write_bytes(payload)
            rows[name] = {"path": path.name, "shape": list(value.shape), "dtype": "BF16",
                "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}
    receipt = {"schema": "dflash_complete_context_R1_CPU_fixture.v1", "rows": 1,
        "retained_rows_only": True, "input_scope": "actual_committed_native_rows" if args.features_raw else "synthetic_component_only",
        "source_CPU_oracle": "pinned_owner_AST_fc_hidden_norm_k_proj_k_norm_v_proj_and_apply_rotary;CPU_BF16;no_full_head",
        "position": args.position, "checkpoint_sha256": contract.CHECKPOINT_SHA256,
        "pinned_owner_source_sha256": SOURCE_HASHES, "torch_version": str(torch.__version__),
        "preparer_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "source_CPU_calls": calls,
        "source_CPU_timing_scope": "owned_feature/cos/sin_clone;exact_owner_complete_context_projection;final_KV_finite_check;owned_KV_return_clone;source_rotary_preparation_excluded;does_not_include_provider_all_derived_finite_checks",
        "tensors": rows, "accelerator_executed": False, "serving_activation": False}
    path = destination / "fixture.json"
    path.write_text(json.dumps(receipt, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"fixture": str(path), "input_scope": receipt["input_scope"], "position": args.position}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute-root-owned", action="store_true", required=True)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--output-directory", required=True)
    parser.add_argument("--features-raw", help="already-selected actual raw BF16 row; exactly25600bytes")
    parser.add_argument("--synthetic-offset", type=int, default=90000)
    parser.add_argument("--position", type=int, default=16384)
    args = parser.parse_args()
    if not 0 <= args.position < 262144:
        parser.error("Position outside trained full NeoX range")
    prepare(args)


if __name__ == "__main__":
    main()
