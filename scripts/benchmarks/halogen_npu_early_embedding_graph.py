"""Root-only count1 embedding projection sibling for a prospective early producer.

Reuse sealed stable embedding weights, quantizer and arithmetic exactly. No
hidden operand, RMS, gather, producer, publication or live substitution is
implemented. Graph eligibility does not admit overlap or establish speed.
Only root may build/verify assets in its coordinated server-idle guarded window.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path


HERE = Path(__file__).resolve().parent
STABLE_HELPER = HERE / "halogen_npu_v2_d_native_projection_stable_split_graph.py"
STABLE_HELPER_SHA256 = "94438473e7b1084818515b6c8308b86dc1f24a48cee05fa68e0b1f3c48636566"
STABLE_MODEL_SHA256 = "77e704f65f2d04a35379360e65cf13919cbb02747656bc7675991254d60a0c0f"
STABLE_RECEIPT_SHA256 = "7abfe3723b74fe3728644e0a727662b9903a9a68bb8906ac4967923d4d6d653b"
STABLE_DATA_SHA256 = "61ccb018d6855f1d189c39a22554bfaf82f1a31e95a7cd8b745042f7798b906f"
SCHEMA = "halogen_v2_count1_early_embedding_projection_graph.v1"
COMPONENT_MODE = "prospective-count1-early-embedding-projection"
INPUT_SHAPES = {"e_high": (1, 2560), "e_low": (1, 2560)}
OUTPUT_SHAPES = {"e_projection": (1, 2560)}
INITIALIZER_NAMES = ("W_embedding_high", "W_embedding_low")
REQUIRED_OUTPUTS = ("e_hh", "e_hl", "e_lh", "e_ll", "e_sum_h", "e_sum_h_lh",
                    "e_projection_fp32", "e_projection_bf16", "e_projection")
ARITHMETIC = ("unchanged stable embedding high/residual operands; four FLOAT MatMuls; "
              "((HH+HL)+LH)+LL; original BF16 RNE then FLOAT output; hidden/RMS/seed-add absent")
CLAIMS = dict(diagnostic_only=True, integration_admission=False, acceleration_claim=False,
              halogen_output_swap=False, hidden_input_used=False, hidden_computation=False,
              normalization_in_segment=False, seed_add_in_segment=False,
              producer_implemented=False, batch_publication_implemented=False, dynamic_batch_supported=False,
              full_d_claim=False, full_mtp_claim=False, acceptance_claim=False, overlap_admission=False,
              root_coordinated_server_idle_window_required=True, concurrent_gpu_inference_admitted=False,
              supported_safe_fabric_control_required_before_overlap=True,
              successful_strict_cpu_gate_required_before_npu=True)


def sha(value):
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError("independently supplied lowercase SHA256 required")
    return value


def digest(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            value.update(block)
    return value.hexdigest()


def sealed_stable():
    if digest(STABLE_HELPER) != STABLE_HELPER_SHA256:
        raise ValueError("sealed stable source differs")
    import halogen_npu_v2_d_native_projection_stable_split_graph as stable
    if Path(stable.__file__).resolve() != STABLE_HELPER:
        raise ValueError("sealed stable import origin differs")
    return stable


def prepare_input(e_norm, np):
    if e_norm.shape != (1, 2560) or e_norm.dtype != np.float32:
        raise ValueError("exact count1 normalized embedding FLOAT shape required")
    high, low, facts = sealed_stable().split_operand(e_norm, -1, np)
    return {"e_high": high, "e_low": low}, {"e": facts}


def embedding_members(graph):
    """Select the existing embedding branch and reject any hidden dependency."""
    nodes = [n for n in graph.node if set(n.output).issubset(REQUIRED_OUTPUTS) and n.output]
    inputs = [v for v in graph.input if v.name in INPUT_SHAPES]
    outputs = [v for v in graph.output if v.name in OUTPUT_SHAPES]
    weights = [v for v in graph.initializer if v.name in INITIALIZER_NAMES]
    allowed = set(INPUT_SHAPES) | set(INITIALIZER_NAMES) | set(REQUIRED_OUTPUTS)
    if (len(nodes) != 9 or {v for n in nodes for v in n.output} != set(REQUIRED_OUTPUTS) or
            [v.name for v in inputs] != list(INPUT_SHAPES) or [v.name for v in outputs] != list(OUTPUT_SHAPES) or
            [v.name for v in weights] != list(INITIALIZER_NAMES) or
            any(v not in allowed for n in nodes for v in n.input)):
        raise ValueError("unchanged embedding branch without hidden dependencies required")
    return nodes, inputs, outputs, weights


def create_graph(data_location, source_hash):
    from onnx import helper
    model = sealed_stable().create_graph(data_location, sha(source_hash))
    members = embedding_members(model.graph)
    for name, values in zip(("node", "input", "output", "initializer"), members, strict=True):
        target = getattr(model.graph, name)
        del target[:]
        target.extend(values)
    model.graph.name = "halogen_v2_count1_early_embedding_projection"
    model.producer_name = "strix-alloy-early-embedding-component-diagnostic"
    properties = {row.key: row.value for row in model.metadata_props}
    properties.update(stable_helper_sha256=STABLE_HELPER_SHA256, stable_model_sha256=STABLE_MODEL_SHA256,
                      stable_receipt_sha256=STABLE_RECEIPT_SHA256, arithmetic=ARITHMETIC,
                      scope=COMPONENT_MODE + "; no hidden input, producer, overlap, batch, live or speed admission")
    helper.set_model_props(model, properties)
    return model


def metadata(model):
    result = sealed_stable().metadata(model)
    result.update(input_shapes={k: list(v) for k, v in INPUT_SHAPES.items()},
                  output_shapes={k: list(v) for k, v in OUTPUT_SHAPES.items()}, output_names=list(OUTPUT_SHAPES),
                  hidden_input_used=False, hidden_computation=False, component_mode=COMPONENT_MODE)
    return result


def parent_binding(model, receipt, receipt_sha256):
    model, receipt = Path(model).resolve(strict=True), Path(receipt).resolve(strict=True)
    if digest(model) != STABLE_MODEL_SHA256 or sha(receipt_sha256) != STABLE_RECEIPT_SHA256:
        raise ValueError("exact retained stable model/receipt required")
    parent, original = sealed_stable().verify_split(model, receipt, receipt_sha256)
    if parent["data_sha256"] != STABLE_DATA_SHA256:
        raise ValueError("unchanged sealed stable data required")
    return parent, original


def candidate_receipt(parent, source_model, source_receipt, output, model_sha256):
    source_hash = digest(__file__)
    inventory = {row["path"]: row["sha256"] for row in parent["immutable_files"]}
    inventory.update({str(source_receipt): STABLE_RECEIPT_SHA256, str(Path(__file__).resolve()): source_hash,
                      str(output): sha(model_sha256)})
    lineage = {k: parent[k] for k in ("source_model", "source_model_sha256", "source_build_receipt",
              "source_build_receipt_sha256", "assets_receipt", "assets_receipt_sha256", "data", "data_sha256", "data_bytes",
              "weight_lineage", "split_diagnostics")}
    return dict(schema=SCHEMA, component_mode=COMPONENT_MODE, count=1, source_paired_wire_mode="D",
                transformer_sha256=source_hash, stable_helper_sha256=STABLE_HELPER_SHA256,
                source_stable_model=str(source_model), source_stable_model_sha256=STABLE_MODEL_SHA256,
                source_stable_receipt=str(source_receipt), source_stable_receipt_sha256=STABLE_RECEIPT_SHA256,
                model=str(output), model_sha256=model_sha256, reused_stable_embedding_weight_data=True,
                stable_embedding_operands_unchanged=True, arithmetic=ARITHMETIC,
                weight_diagnostics={"W_embedding": parent["weight_diagnostics"]["W_embedding"]},
                metadata=metadata(create_graph(Path(parent["data"]).name, source_hash)),
                immutable_files=[dict(path=p, sha256=s) for p, s in sorted(inventory.items())], **lineage, **CLAIMS)


def transform(source_model, source_receipt, receipt_sha256, output):
    import onnx
    source_model, source_receipt = Path(source_model).resolve(strict=True), Path(source_receipt).resolve(strict=True)
    output = Path(output).resolve()
    report, partial, lock = (Path(str(output) + suffix) for suffix in (".json", ".partial", ".lock"))
    if output.parent != source_model.parent or any(p.exists() for p in (output, report, partial, lock)):
        raise ValueError("fresh embedding sibling beside existing stable data required")
    source_hash = digest(__file__)
    with lock.open("x", encoding="utf-8"):
        parent, _ = parent_binding(source_model, source_receipt, receipt_sha256)
        model = create_graph(Path(parent["data"]).name, source_hash)
        with partial.open("xb") as stream:
            stream.write(model.SerializeToString()); stream.flush(); os.fsync(stream.fileno())
        onnx.checker.check_model(str(partial))
        parent_binding(source_model, source_receipt, receipt_sha256)
        if digest(__file__) != source_hash:
            raise ValueError("embedding transformer changed during build")
        os.rename(partial, output)
        result = candidate_receipt(parent, source_model, source_receipt, output, digest(output))
        sealed_stable().recheck_files(result["immutable_files"])
        with report.open("x", encoding="utf-8") as stream:
            json.dump(result, stream, indent=2, allow_nan=False); stream.flush(); os.fsync(stream.fileno())
        sealed_stable().recheck_files(result["immutable_files"])
    lock.unlink()
    return result


def verify_graph(model_path, receipt_path, receipt_sha256):
    import onnx
    model_path, receipt_path = Path(model_path).resolve(strict=True), Path(receipt_path).resolve(strict=True)
    if (receipt_path != Path(str(model_path) + ".json") or receipt_path.stat().st_size > 2 << 20 or
            digest(receipt_path) != sha(receipt_sha256) or
            any(Path(str(model_path) + s).exists() for s in (".partial", ".lock"))):
        raise ValueError("completed bounded embedding graph/receipt required")
    result = json.loads(receipt_path.read_text(encoding="utf-8"))
    source_model, source_receipt = Path(result["source_stable_model"]), Path(result["source_stable_receipt"])
    if source_model.parent != model_path.parent:
        raise ValueError("stable/embedding folders differ")
    parent, original = parent_binding(source_model, source_receipt, result["source_stable_receipt_sha256"])
    expected = candidate_receipt(parent, source_model, source_receipt, model_path, digest(model_path))
    actual = onnx.load(str(model_path), load_external_data=False)
    wanted = create_graph(Path(parent["data"]).name, digest(__file__))
    if result != expected or actual.SerializeToString() != wanted.SerializeToString():
        raise ValueError("exact unchanged embedding graph/data/source contract differs")
    sealed_stable().recheck_files(expected["immutable_files"])
    if digest(receipt_path) != receipt_sha256:
        raise ValueError("embedding receipt changed during verification")
    return result, original


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("source-stable-projection", "stable-projection-receipt", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--stable-projection-receipt-sha256", required=True)
    args = parser.parse_args(argv)
    print(json.dumps(transform(args.source_stable_projection, args.stable_projection_receipt,
                               sha(args.stable_projection_receipt_sha256), args.output), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
