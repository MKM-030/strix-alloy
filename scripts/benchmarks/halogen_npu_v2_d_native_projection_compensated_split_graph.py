"""Root-only balanced TwoSum sibling of the sealed stable paired-FC graph.

The sealed stable graph/receipt/data and quantizer are never rewritten. This
sibling reuses its exact four weight matrices and input preparation, changes
only recombination of the same four FLOAT MatMul outputs, and retains final
BF16 RNE/FLOAT boundaries. No oracle, index or observed value selects an operand
or correction. CPU then NPU must separately pass their unchanged gates.

TwoSum recovers addition roundoff with ordinary IEEE round-to-nearest FLOAT
operations; that identity is not assumed for provider BFP arithmetic. It does
not recover error within a partial MatMul and is not native DOT2 emulation.
Only root runs build/verification, which read sealed model/data payloads.
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
SCHEMA = "halogen_v2_count1_D_native_projection_compensated_split_graph.v1"
ARITHMETIC = ("unchanged sealed stable-high/residual operands and four FLOAT MatMuls; "
              "balanced TwoSum(HH,HL), TwoSum(LH,LL), TwoSum(pair sums); "
              "sum recovered addition errors then add to merged sum; "
              "original final projection BF16 RNE then FLOAT; "
              "RMS and seed-add excluded; partial MatMul error and native DOT2 parity unqualified; "
              "provider IEEE FLOAT behavior is not assumed")
RECOMBINATION = dict(
    algorithm="balanced-three-TwoSum-with-recovered-addition-errors",
    pairs="TwoSum(HH,HL); TwoSum(LH,LL); TwoSum(first_sum,second_sum)",
    correction="(first_error+second_error)+merge_error",
    final="merge_sum+correction before original BF16 RNE boundary",
    uniform_all_elements=True, oracle_selected_arithmetic=False, per_value_correction=False,
    magnitude_order_required=False, ieee_round_to_nearest_required_for_TwoSum_identity=True,
    provider_ieee_float_assumed=False, partial_matmul_error_recovered=False,
    exact_native_accumulation_claim=False,
    reference="https://www.tuhh.de/ti3/paper/rump/OgRuOi05.pdf Algorithm 3.1")


def sha(value):
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError("independently supplied lowercase SHA256 required")
    return value


def digest(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            result.update(block)
    return result.hexdigest()


def sealed_stable():
    if digest(STABLE_HELPER) != STABLE_HELPER_SHA256:
        raise ValueError("sealed stable split source differs")
    import halogen_npu_v2_d_native_projection_stable_split_graph as stable
    if Path(stable.__file__).resolve() != STABLE_HELPER:
        raise ValueError("sealed stable split import origin differs")
    return stable


def prepare_inputs(e_norm, h_norm, np):
    return sealed_stable().prepare_inputs(e_norm, h_norm, np)


def recombination_nodes(branch, helper):
    """One fixed branch-free graph for every element; no magnitude sorting.

    TwoSum: s=a+b; z=s-a; error=(a-(s-z))+(b-z). Every elementary
    operation is a distinct FLOAT Add/Sub node, covered by placement proof.
    """
    nodes = []

    def operation(kind, first, second, name):
        output = branch + "_" + name
        nodes.append(helper.make_node(kind, [first, second], [output], name=output))
        return output

    def two_sum(first, second, name):
        total = operation("Add", first, second, name + "_sum")
        virtual_second = operation("Sub", total, first, name + "_virtual_second")
        virtual_first = operation("Sub", total, virtual_second, name + "_virtual_first")
        first_error = operation("Sub", first, virtual_first, name + "_first_error")
        second_error = operation("Sub", second, virtual_second, name + "_second_error")
        error = operation("Add", first_error, second_error, name + "_error")
        return total, error

    first_sum, first_error = two_sum(branch + "_hh", branch + "_hl", "pair_high")
    second_sum, second_error = two_sum(branch + "_lh", branch + "_ll", "pair_low")
    merged_sum, merged_error = two_sum(first_sum, second_sum, "merge")
    pair_errors = operation("Add", first_error, second_error, "pair_errors")
    correction = operation("Add", pair_errors, merged_error, "addition_correction")
    operation("Add", merged_sum, correction, "projection_fp32")
    return nodes


def create_graph(data_location, source_hash):
    """Reuse fixed stable descriptors; never materialize weights here."""
    import onnx
    from onnx import helper
    sha(source_hash)
    stable = sealed_stable()
    model = stable.create_graph(data_location, STABLE_HELPER_SHA256)
    nodes = []
    for branch, weight in (("e", "W_embedding"), ("h", "W_hidden")):
        for suffix, x_part, w_part in (("hh", "high", "high"), ("hl", "high", "low"),
                                      ("lh", "low", "high"), ("ll", "low", "low")):
            output = branch + "_" + suffix
            nodes.append(helper.make_node("MatMul", [branch + "_" + x_part, weight + "_" + w_part],
                                          [output], name=output))
        nodes.extend(recombination_nodes(branch, helper))
        nodes.append(helper.make_node("Cast", [branch + "_projection_fp32"], [branch + "_projection_bf16"],
                                      name=branch + "_projection_bf16", to=onnx.TensorProto.BFLOAT16))
        nodes.append(helper.make_node("Cast", [branch + "_projection_bf16"], [branch + "_projection"],
                                      name=branch + "_projection", to=onnx.TensorProto.FLOAT))
    del model.graph.node[:]
    model.graph.node.extend(nodes)
    model.graph.name = "halogen_v2_count1_D_native_projection_compensated_split"
    model.producer_name = "strix-alloy-native-projection-compensated-split-diagnostic"
    properties = {value.key: value.value for value in model.metadata_props}
    properties.update(transformer_sha256=source_hash, stable_helper_sha256=STABLE_HELPER_SHA256,
                      stable_model_sha256=STABLE_MODEL_SHA256, stable_receipt_sha256=STABLE_RECEIPT_SHA256,
                      arithmetic=ARITHMETIC, recombination=json.dumps(RECOMBINATION, sort_keys=True),
                      scope="standalone paired FC summation diagnostic; successful strict CPU gate required before NPU")
    helper.set_model_props(model, properties)
    return model


def metadata(model):
    result = sealed_stable().metadata(model)
    result.update(addition_order=RECOMBINATION["pairs"] + "; " + RECOMBINATION["correction"],
                  recombination=RECOMBINATION)
    return result


def parent_binding(model, receipt, receipt_sha256):
    model, receipt = Path(model).resolve(strict=True), Path(receipt).resolve(strict=True)
    if digest(model) != STABLE_MODEL_SHA256 or sha(receipt_sha256) != STABLE_RECEIPT_SHA256:
        raise ValueError("exact retained stable split model/receipt required")
    stable = sealed_stable()
    parent, build = stable.verify_split(model, receipt, receipt_sha256)
    if parent["data_sha256"] != STABLE_DATA_SHA256:
        raise ValueError("exact unchanged stable four-weight data required")
    return parent, build


def candidate_receipt(parent, source_model, source_receipt, output, model_sha256):
    source_hash = digest(__file__)
    result = dict(parent)
    inventory = {row["path"]: row["sha256"] for row in parent["immutable_files"]}
    inventory.update({str(STABLE_HELPER): STABLE_HELPER_SHA256,
                      str(Path(source_receipt).resolve(strict=True)): STABLE_RECEIPT_SHA256,
                      str(Path(__file__).resolve()): source_hash,
                      str(output): sha(model_sha256)})
    result.update(schema=SCHEMA, arithmetic=ARITHMETIC, transformer_sha256=source_hash,
                  stable_helper_sha256=STABLE_HELPER_SHA256,
                  source_stable_model=str(source_model), source_stable_model_sha256=STABLE_MODEL_SHA256,
                  source_stable_receipt=str(source_receipt), source_stable_receipt_sha256=STABLE_RECEIPT_SHA256,
                  model=str(output), model_sha256=model_sha256,
                  reused_stable_weight_data=True, derived_data_exclusive=False,
                  stable_operands_unchanged=True, recombination=RECOMBINATION,
                  successful_strict_cpu_gate_required_before_npu=True,
                  metadata=metadata(create_graph(Path(parent["data"]).name, source_hash)),
                  immutable_files=[dict(path=path, sha256=value) for path, value in sorted(inventory.items())])
    return result


def transform(source_model, source_receipt, receipt_sha256, output):
    import onnx
    source_model, source_receipt = Path(source_model).resolve(strict=True), Path(source_receipt).resolve(strict=True)
    output = Path(output).resolve()
    report, partial, lock = (Path(str(output) + suffix) for suffix in (".json", ".partial", ".lock"))
    if output.parent != source_model.parent:
        raise ValueError("compensated sibling must stay beside sealed stable data")
    if any(path.exists() for path in (output, report, partial, lock)):
        raise FileExistsError("existing compensated graph/receipt/partial/lock refused")
    stable = sealed_stable()
    source_hash = digest(__file__)
    with lock.open("x", encoding="utf-8"):
        parent, _ = parent_binding(source_model, source_receipt, receipt_sha256)
        model = create_graph(Path(parent["data"]).name, source_hash)
        with partial.open("xb") as stream:
            stream.write(model.SerializeToString())
            stream.flush()
            os.fsync(stream.fileno())
        onnx.checker.check_model(str(partial))
        parent_binding(source_model, source_receipt, receipt_sha256)
        if digest(__file__) != source_hash:
            raise ValueError("compensated source changed during build")
        os.rename(partial, output)
        result = candidate_receipt(parent, source_model, source_receipt, output, digest(output))
        stable.recheck_files(result["immutable_files"])
        with report.open("x", encoding="utf-8") as stream:
            json.dump(result, stream, indent=2, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        stable.recheck_files(result["immutable_files"])
    lock.unlink()
    return result


def verify_split(model_path, receipt_path, receipt_sha256):
    import onnx
    model_path, receipt_path = Path(model_path).resolve(strict=True), Path(receipt_path).resolve(strict=True)
    if (receipt_path != Path(str(model_path) + ".json") or receipt_path.stat().st_size > 2 << 20 or
            digest(receipt_path) != sha(receipt_sha256)):
        raise ValueError("bounded independently sealed compensated receipt required")
    result = json.loads(receipt_path.read_text(encoding="utf-8"))
    if any(Path(str(model_path) + suffix).exists() for suffix in (".partial", ".lock")):
        raise ValueError("compensated writer partial/lock present")
    source_model, source_receipt = Path(result["source_stable_model"]).resolve(strict=True), Path(result["source_stable_receipt"]).resolve(strict=True)
    if model_path.parent != source_model.parent:
        raise ValueError("compensated/stable folders differ")
    parent, build = parent_binding(source_model, source_receipt, result["source_stable_receipt_sha256"])
    model_sha256 = digest(model_path)
    expected = candidate_receipt(parent, source_model, source_receipt, model_path, model_sha256)
    wanted = create_graph(Path(parent["data"]).name, digest(__file__))
    actual = onnx.load(str(model_path), load_external_data=False)
    if result != expected or actual.SerializeToString() != wanted.SerializeToString():
        raise ValueError("fixed compensated graph/receipt/operand identity differs")
    sealed_stable().recheck_files(expected["immutable_files"])
    if digest(receipt_path) != receipt_sha256:
        raise ValueError("compensated receipt changed during verification")
    return result, build


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-stable-projection", type=Path, required=True)
    parser.add_argument("--stable-projection-receipt", type=Path, required=True)
    parser.add_argument("--stable-projection-receipt-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--wire-mode", choices=("D",), required=True)
    args = parser.parse_args(argv)
    result = transform(args.source_stable_projection, args.stable_projection_receipt,
                       sha(args.stable_projection_receipt_sha256), args.output)
    print(json.dumps(result, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
