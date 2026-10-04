"""Build a small AMD 1.8 QMoEBf ONNX graph and official protobuf sidecar.

Only ONNX/protobuf construction is performed. No DynamicDispatch, ONNX Runtime,
provider, XRT, device, model decoder, or packer is imported or invoked. An owned
caller supplies a completed bank and its packing receipt. Bank payload bytes are
not read, copied, or hashed here. The graph is an unqualified runtime candidate.
"""

import argparse
import ast
import hashlib
import json
from pathlib import Path


PROTO_SOURCE_SHA256 = "11535c7348e169fd16fbda6da598281f8ee68b190f491b2e426358216f450d33"
DD_PACKER_SHA256 = "38814ad69d2233758b76bf82db922f2e674c0d01aace756ace066135cbf4aaab"
DD_WHEEL_SHA256 = "8988620998c23a0d1a71bf2ced9a5287bc6641133ad38b67900fa4c546e7a8e4"
ALIGNMENT = 65536
WIDTH = 2560
INTERMEDIATE = 640
DEFAULT_NODE_NAME = "/model/layers.48/moe/QMoE_0"
STANDARD_SWIGLU_LIMIT = float.fromhex("0x1.fffffep+127")
EXPECTED_FCS = {
    "FC1": ((2560, 1280), (2560, 2560), 4198400),
    "FC2": ((640, 2560), (768, 3072), 1597440),
}


def derive_geometry(pack_receipt):
    """Validate this exact two-FC pack geometry and derive 64KiB expert stride."""
    if pack_receipt.get("passed") is not True or pack_receipt.get("stage") != "complete":
        raise ValueError("requires a completed passing owned packing receipt")
    if pack_receipt.get("native_packer_sha256") != DD_PACKER_SHA256:
        raise ValueError("packing receipt does not identify the pinned AMD 1.8 packer")
    rows = pack_receipt.get("rows")
    if not isinstance(rows, list) or len(rows) != 2:
        raise ValueError("requires exactly FC1 gate/up and FC2 down packing rows")
    by_label = {row.get("label"): row for row in rows}
    if set(by_label) != set(EXPECTED_FCS):
        raise ValueError("packing rows must uniquely identify FC1 and FC2")
    for label, (logical, padded, byte_count) in EXPECTED_FCS.items():
        row = by_label[label]
        if tuple(row.get("logical_kn", ())) != logical or tuple(row.get("padded_kn", ())) != padded:
            raise ValueError(f"{label} logical/padded geometry differs from the admitted shape")
        if type(row.get("bytes")) is not int or row["bytes"] != byte_count:
            raise ValueError(f"{label} packed byte count differs from the admitted shape")
    fc1_bytes = by_label["FC1"]["bytes"]
    fc2_bytes = by_label["FC2"]["bytes"]
    tail = (-(fc1_bytes + fc2_bytes)) % ALIGNMENT
    stride = fc1_bytes + fc2_bytes + tail
    bank = pack_receipt.get("bank")
    if not isinstance(bank, dict):
        raise ValueError("requires a completed bank receipt, not only one expert")
    experts = bank.get("num_experts")
    if type(experts) is not int or not 1 <= experts <= 512:
        raise ValueError("bank must contain 1..512 explicitly counted experts")
    expected_bank = {
        "expert_stride": stride,
        "fc1_bytes": fc1_bytes,
        "fc2_raw_bytes": fc2_bytes,
        "fc2_tail_padding": tail,
        "fc2_padded_bytes": fc2_bytes + tail,
        "bytes": experts * stride,
    }
    for key, value in expected_bank.items():
        if type(bank.get(key)) is not int or bank[key] != value:
            raise ValueError(f"bank receipt {key} disagrees with converter alignment")
    if type(bank.get("synthetic")) is not bool:
        raise ValueError("bank receipt must explicitly distinguish synthetic and real weights")
    if not bank["synthetic"] and bank.get("packed_gate_up_layout") != "interleaved":
        raise ValueError("real candidate bank must declare interleaved packed gate/up rows")
    digest = bank.get("sha256", "")
    if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise ValueError("bank receipt must contain an owned lowercase SHA256")
    return {
        "num_experts": experts,
        "width": WIDTH,
        "intermediate": INTERMEDIATE,
        "block_size": 32,
        "mladf_version": "v2",
        "k_FC1": 2560,
        "n_FC1": 1280,
        "padded_kn_FC1": [2560, 2560],
        "k_FC2": 640,
        "n_FC2": 2560,
        "padded_kn_FC2": [768, 3072],
        "packed_expert_sz_FC1": fc1_bytes,
        "packed_expert_sz_FC2": fc2_bytes + tail,
        "fc2_raw_bytes": fc2_bytes,
        "fc2_tail_padding": tail,
        "expert_stride": stride,
        "bank_bytes": experts * stride,
        "alignment": ALIGNMENT,
    }


def node_attributes(geometry, top_k=10):
    """Source-exact geometry plus an explicitly unverified SwiGLU candidate."""
    if type(top_k) is not int or not 1 <= top_k <= geometry["num_experts"]:
        raise ValueError("top_k must be in 1..num_experts")
    attributes = {
        "activation_type": "swiglu",
        "activation_alpha": 1.0,
        "activation_beta": 0.0,
        "swiglu_limit": STANDARD_SWIGLU_LIMIT,
        "swiglu_fusion": 1,
        "expert_weight_bits": 4,
        "block_size": 32,
        "k": top_k,
        "normalize_routing_weights": 1,
        "use_sparse_mixer": 0,
        "num_experts": geometry["num_experts"],
        "num_fc": 2,
        "mladf_version": "v2",
    }
    for fc in ("FC1", "FC2"):
        for prefix in ("k", "n", "packed_expert_sz"):
            attributes[f"{prefix}_{fc}"] = geometry[f"{prefix}_{fc}"]
        attributes[f"block_size_{fc}"] = 32
    return attributes


def build_model(geometry, *, top_k=10, node_name=DEFAULT_NODE_NAME):
    """Construct exactly one custom op; initializer payloads are all empty."""
    import onnx

    if not isinstance(node_name, str) or not node_name or not node_name.strip("/"):
        raise ValueError("requires a stable nonempty custom-op node name")
    prefix = node_name.strip("/").replace("/", ".")
    inputs = ["x", "router"]
    initializers = []
    # Empty the same original inputs that AMD add_npu_weights empties.
    for suffix, dtype in (
        ("fc1.weight.empty", onnx.TensorProto.UINT8),
        ("fc1.scale.empty", onnx.TensorProto.FLOAT),
        ("fc1.bias.empty", onnx.TensorProto.FLOAT),
        ("fc2.weight.empty", onnx.TensorProto.UINT8),
        ("fc2.scale.empty", onnx.TensorProto.FLOAT),
        ("fc2.bias.empty", onnx.TensorProto.FLOAT),
    ):
        name = f"{prefix}.{suffix}"
        inputs.append(name)
        initializers.append(onnx.helper.make_tensor(name, dtype, [0], []))
    inputs.extend(["", "", ""])
    for suffix in ("fc1.qzeros.empty", "fc2.qzeros.empty"):
        name = f"{prefix}.{suffix}"
        inputs.append(name)
        initializers.append(onnx.helper.make_tensor(name, onnx.TensorProto.UINT8, [0], []))
    inputs.append("")
    packed_name = prefix + ".gate_up_down.packed.qexperts"
    inputs.append(packed_name)
    initializers.append(onnx.helper.make_tensor(packed_name, onnx.TensorProto.INT8, [0], []))
    attributes = node_attributes(geometry, top_k)
    node = onnx.helper.make_node(
        "QMoEBf", inputs, ["y"], name=node_name, domain="com.ryzenai", **attributes
    )
    graph = onnx.helper.make_graph(
        [node], "halogen_qmoe_resident_candidate",
        [onnx.helper.make_tensor_value_info("x", onnx.TensorProto.BFLOAT16, [1, WIDTH]),
         onnx.helper.make_tensor_value_info("router", onnx.TensorProto.FLOAT, [1, geometry["num_experts"]])],
        [onnx.helper.make_tensor_value_info("y", onnx.TensorProto.BFLOAT16, [1, WIDTH])],
        initializer=initializers,
    )
    model = onnx.helper.make_model(
        graph, producer_name="strix-alloy-qmoe-source-builder", producer_version="1",
        opset_imports=[onnx.helper.make_opsetid("", 19), onnx.helper.make_opsetid("com.ryzenai", 1)],
        ir_version=9,
    )
    model.doc_string = "Unqualified AMD1.8 QMoEBf candidate; SwiGLU semantics and Light compatibility require owned runtime measurement."
    onnx.helper.set_model_props(model, {
        "activation_profile": "proposed_standard_swiglu",
        "activation_semantics_verified": "false",
        "provider_inference": "false",
        "bank_payload_location": "AMD Header sidecar; packed initializer intentionally INT8[0]",
    })
    onnx.checker.check_model(model, check_custom_domain=False)
    return model, attributes


def header_class_from_source(proto_source):
    """Read the pinned official descriptor as data; never execute its module."""
    from google.protobuf import descriptor_pool, message_factory

    source = Path(proto_source).read_bytes()
    if hashlib.sha256(source).hexdigest() != PROTO_SOURCE_SHA256:
        raise ValueError("official external_data_pb2 source hash mismatch")
    tree = ast.parse(source)
    descriptors = [
        ast.literal_eval(node.args[0])
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        and node.func.attr == "AddSerializedFile" and len(node.args) == 1
    ]
    if len(descriptors) != 1 or not isinstance(descriptors[0], bytes):
        raise ValueError("expected exactly one official serialized protobuf descriptor")
    pool = descriptor_pool.DescriptorPool()
    pool.AddSerializedFile(descriptors[0])
    return message_factory.GetMessageClass(pool.FindMessageTypeByName("ryzenai.onnx_utils.proto.Header"))


def build_header(geometry, *, bank_filename, node_name, proto_source):
    """Match AMD jit.py with QMoE offload enabled and NPU/GPU JIT disabled."""
    if Path(bank_filename).name != bank_filename or not bank_filename:
        raise ValueError("sidecar requires a sibling bank filename")
    header = header_class_from_source(proto_source)()
    operator = header.operators[node_name]
    operator.op_type = "QMoEBf"
    operator.data.add(offset=0, size=geometry["bank_bytes"], shape=[geometry["bank_bytes"]], data_type=3)
    metadata = header.op_metadata["QMoEBf"]
    metadata.max_npu_buffer_size = 0
    metadata.first = metadata.last = node_name
    # save_qmoe does not add its payload size to the JIT Layer accounting.
    header.layers.add(offset=0, size=0, operators=[node_name])
    header.external_data.filename = bank_filename
    header.external_data.npu = False
    header.external_data.gpu = False
    header.external_data.embedding = False
    header.external_data.qmoe = True
    return header


def write_artifacts(pack_receipt_path, proto_source, output_path, *, top_k=10, node_name=DEFAULT_NODE_NAME):
    """Write only small ONNX/header/manifest files next to the existing bank."""
    receipt_path = Path(pack_receipt_path).resolve()
    receipt_bytes = receipt_path.read_bytes()
    receipt = json.loads(receipt_bytes)
    geometry = derive_geometry(receipt)
    bank = receipt["bank"]
    bank_path = Path(bank["path"]).resolve()
    output = Path(output_path).resolve()
    header_path = output.with_suffix(".pb.bin")
    manifest_path = output.with_suffix(".contract.json")
    if output.suffix.lower() != ".onnx":
        raise ValueError("output must end in .onnx")
    if bank_path.parent != output.parent:
        raise ValueError("ONNX, Header and bank must be siblings for relative metadata resolution")
    if not bank_path.is_file() or bank_path.stat().st_size != geometry["bank_bytes"]:
        raise ValueError("bank file size disagrees with the completed owned receipt")
    if any(path.exists() for path in (output, header_path, manifest_path)):
        raise ValueError("refusing to overwrite an existing graph/header/manifest")
    model, attributes = build_model(geometry, top_k=top_k, node_name=node_name)
    header = build_header(geometry, bank_filename=bank_path.name, node_name=node_name, proto_source=proto_source)
    graph_bytes = model.SerializeToString(deterministic=True)
    header_bytes = header.SerializeToString(deterministic=True)
    if len(graph_bytes) > 65536 or len(header_bytes) > 16384:
        raise ValueError("unexpected graph/metadata size; bank data must remain external")
    manifest = {
        "schema": "halogen_qmoe_graph_v1",
        "passed": True,
        "scope": "offline source-contract graph/header construction only",
        "graph_path": str(output), "graph_sha256": hashlib.sha256(graph_bytes).hexdigest(),
        "header_path": str(header_path), "header_sha256": hashlib.sha256(header_bytes).hexdigest(),
        "bank_path": str(bank_path), "bank_bytes": geometry["bank_bytes"], "bank_sha256": bank["sha256"],
        "bank_hash_verified_by_builder": False, "bank_hash_source": "completed owned pack receipt",
        "bank_synthetic": bank["synthetic"],
        "pack_receipt_path": str(receipt_path), "pack_receipt_sha256": hashlib.sha256(receipt_bytes).hexdigest(),
        "builder_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "protobuf_source_path": str(Path(proto_source).resolve()), "protobuf_source_sha256": PROTO_SOURCE_SHA256,
        "dd_packer_sha256": DD_PACKER_SHA256, "dd_wheel_sha256": DD_WHEEL_SHA256,
        "geometry": geometry,
        "node": {"name": node_name, "domain": "com.ryzenai", "op_type": "QMoEBf", "domain_opset": 1,
                 "inputs": list(model.graph.node[0].input), "outputs": ["y"], "attributes": attributes},
        "io": {"inputs": [{"name": "x", "dtype": "bfloat16", "shape": [1, WIDTH]},
                           {"name": "router", "dtype": "float32", "shape": [1, geometry["num_experts"]]}],
               "outputs": [{"name": "y", "dtype": "bfloat16", "shape": [1, WIDTH]}]},
        "provider_options": {"external_data_file": header_path.name, "hybrid_opt_token_backend": "npu",
                             "hybrid_opt_qmoe_dynamic_experts": "0", "hybrid_opt_qmoe_num_dynamic_layers": "0"},
        "activation_profile": "proposed_standard_swiglu", "packed_gate_up_layout": "interleaved",
        "activation_semantics_verified": False, "shape_padding_execution_verified": False,
        "sdk_light_abi_verified": False, "provider_inference": False, "full_mtp": False,
        "acceptance_qualified": False, "speed_gain": False,
    }
    for path, payload in ((output, graph_bytes), (header_path, header_bytes),
                          (manifest_path, (json.dumps(manifest, indent=2) + "\n").encode("utf-8"))):
        with path.open("xb") as stream:
            stream.write(payload)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack-receipt", type=Path, required=True)
    parser.add_argument("--proto-source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--node-name", default=DEFAULT_NODE_NAME)
    args = parser.parse_args()
    manifest = write_artifacts(args.pack_receipt, args.proto_source, args.output,
                               top_k=args.top_k, node_name=args.node_name)
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
