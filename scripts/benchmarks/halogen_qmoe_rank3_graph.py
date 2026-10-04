"""Adapt only x/y rank in the frozen synthetic QMoEBf graph; no provider load."""
import hashlib
import json
from pathlib import Path
import onnx


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_rank3(original_manifest):
    original_manifest = Path(original_manifest).resolve(strict=True)
    if sha(original_manifest) != "9f694e76125cef522e90df002bd010a28efb6fbf78ccd117e0cc0dcae83d5b54":
        raise ValueError("Frozen original graph contract changed")
    contract = json.loads(original_manifest.read_text())
    original_graph = Path(contract["graph_path"]).resolve(strict=True)
    if sha(original_graph) != contract["graph_sha256"]:
        raise ValueError("Frozen original graph changed")
    model = onnx.load(str(original_graph), load_external_data=False)
    if len(model.graph.node) != 1 or model.graph.node[0].op_type != "QMoEBf":
        raise ValueError("Expected single frozen QMoEBf graph")
    activation = model.graph.input[0].type.tensor_type
    output = model.graph.output[0].type.tensor_type
    router = model.graph.input[1].type.tensor_type
    if ([d.dim_value for d in activation.shape.dim] != [1, 2560]
            or [d.dim_value for d in output.shape.dim] != [1, 2560]
            or [d.dim_value for d in router.shape.dim] != [1, 512]):
        raise ValueError("Original I/O contract changed")
    original_node = model.graph.node[0].SerializeToString()
    original_initializers = [value.SerializeToString() for value in model.graph.initializer]
    for tensor in (activation, output):
        tensor.shape.ClearField("dim")
        for dimension in (1, 1, 2560):
            tensor.shape.dim.add().dim_value = dimension
    if model.graph.node[0].SerializeToString() != original_node:
        raise ValueError("Rank adaptation changed kernel attributes or inputs")
    if [value.SerializeToString() for value in model.graph.initializer] != original_initializers:
        raise ValueError("Rank adaptation changed packed initializer declarations")
    graph_path = original_graph.with_name("halogen-qmoe-512-top10-rank3.onnx")
    manifest_path = original_manifest.with_name("halogen-qmoe-512-top10-rank3.contract.json")
    if graph_path.exists() or manifest_path.exists():
        raise ValueError("Rank3 graph/manifest must be new files")
    onnx.save(model, str(graph_path))
    contract.update(
        scope="offline rank3-only adaptation of frozen synthetic QMoEBf graph; execution unproved",
        original_manifest_path=str(original_manifest), original_manifest_sha256=sha(original_manifest),
        original_graph_path=str(original_graph), original_graph_sha256=sha(original_graph),
        original_builder_source_sha256=contract["builder_source_sha256"],
        builder_source_sha256=sha(Path(__file__)), graph_path=str(graph_path), graph_sha256=sha(graph_path),
        sole_graph_change="x/y shape [1,2560] -> [1,1,2560]; router remains [1,512]",
        packed_bank_and_header_unchanged=True,
        rank_support_source="pinned Light AMDQMoEKernel reads third activation dimension at RVA0x14da8c",
        provider_inference=False, full_mtp=False, acceptance_qualified=False, speed_gain=False)
    contract["io"]["inputs"][0]["shape"] = [1, 1, 2560]
    contract["io"]["outputs"][0]["shape"] = [1, 1, 2560]
    manifest_path.write_text(json.dumps(contract, indent=2) + "\n", encoding="utf-8")
    return dict(graph_path=str(graph_path), graph_sha256=sha(graph_path),
                manifest_path=str(manifest_path), manifest_sha256=sha(manifest_path),
                builder_source_sha256=sha(Path(__file__)), bank_read=False, provider_loaded=False)


if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        raise SystemExit("Pass the frozen original graph manifest")
    print(json.dumps(build_rank3(sys.argv[1]), indent=2))
