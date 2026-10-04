"""Read-only BF16-RNE qualification of the frozen real-v2 FP32 20-expert bank.

Every weight is inspected; no checkpoint decode, ONNX session, model write,
provider registration or hardware launch occurs. Converted FP32 calculations
are compared with exact saved independent references at the unchanged CPU gate.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

import numpy as np

BANK_HELPER = Path(r"C:\AI\halogen-mtp-npu\v2-bank20-offline-20261004\halogen_npu_v2_bank20_expert_probe.py")
BANK_HELPER_SHA256 = "ae1372da176af3e473c78533d45906ae08c31380cdf15d0999b91da41b7b9210"
BANK_DATA = BANK_HELPER.with_name("v2-bank20-top10.onnx.data")
BANK_DATA_SHA256 = "97ff0db7fdb2ef9375c08d4027dacf3aa553eccc958f6b470228677aa0992232"
if hashlib.sha256(BANK_HELPER.read_bytes()).hexdigest() != BANK_HELPER_SHA256:
    raise ValueError("frozen bank20 helper source differs")
sys.path.insert(0, str(BANK_HELPER.parent))
import halogen_npu_v2_bank20_expert_probe as bank


def bf16_rne(value):
    """FP32 to BF16 nearest/even, widened back to FP32; finite input required."""
    bits = np.array(value, dtype=np.float32, order="C", copy=True).view(np.uint32)
    bits += np.uint32(0x7fff) + ((bits >> 16) & np.uint32(1))
    bits &= np.uint32(0xffff0000)
    return bits.view(np.float32)


def identity(path):
    status = path.stat()
    return dict(size=status.st_size, mtime_ns=status.st_mtime_ns, ctime_ns=status.st_ctime_ns)


def contribution(x, gate_up, down):
    projected = x @ gate_up
    gate, up = projected[:, :bank.INTERMEDIATE], projected[:, bank.INTERMEDIATE:]
    activated = gate / (1 + np.exp(-gate))
    return (activated * up) @ down


def qualify(report_path):
    if report_path.exists():
        raise FileExistsError("qualification receipt exists; overwrite refused")
    samples, baseline = [], bank.process_memory()
    started = time.perf_counter_ns()
    bank.reserve(samples, bank.WEIGHT_LIMIT)
    before = identity(BANK_DATA)
    if before["size"] != bank.BANK_BYTES or bank.dynamic.digest(BANK_DATA) != BANK_DATA_SHA256:
        raise ValueError("frozen FP32 bank differs")
    if bank.dynamic.digest(bank.REFERENCE_RECEIPT) != bank.REFERENCE_RECEIPT_SHA256:
        raise ValueError("frozen reference receipt differs")
    frozen = json.loads(bank.REFERENCE_RECEIPT.read_text(encoding="utf-8"))
    expected = {label: np.asarray(frozen["reference_outputs"][label], dtype=np.float32) for label in ("A", "B")}
    gate_bank = np.memmap(BANK_DATA, mode="r", dtype="<f4", shape=(bank.BANK_COUNT, bank.WIDTH, 2 * bank.INTERMEDIATE))
    down_bank = np.memmap(BANK_DATA, mode="r", dtype="<f4", offset=bank.GATE_BANK_BYTES,
                          shape=(bank.BANK_COUNT, bank.INTERMEDIATE, bank.WIDTH))
    rng = np.random.default_rng(2026100402)
    fixtures = {}
    for label, scale in (("A", .2), ("B", .35)):
        coefficients = np.arange(1, bank.TOP_K + 1, dtype=np.float32)
        if label == "B":
            coefficients = coefficients[::-1].copy()
        fixtures[label] = {"x": rng.normal(0, scale, (1, bank.WIDTH)).astype(np.float32),
                           "routing_weights": (coefficients / 55).reshape(bank.TOP_K, 1, 1)}
        if any(bank.dynamic.array_digest(value) != frozen["decoded_input_sets"][label][name]
               for name, value in fixtures[label].items()):
            raise ValueError("synthetic x/router fixture differs from frozen receipt")
        if bank.dynamic.array_digest(expected[label]) != frozen["reference_sha256"][label]:
            raise ValueError("saved FP32 reference array differs")
    records, outputs = [], {}
    for label, first in (("A", 0), ("B", 10)):
        original_output = np.zeros((1, bank.WIDTH), dtype=np.float32)
        converted_output = np.zeros_like(original_output)
        for position, expert_id in enumerate(range(first, first + bank.TOP_K)):
            bank.reserve(samples, 8 * (gate_bank[expert_id].nbytes + down_bank[expert_id].nbytes))
            rounded_gate, rounded_down = bf16_rne(gate_bank[expert_id]), bf16_rne(down_bank[expert_id])
            for name, original, rounded in (("gate_up", gate_bank[expert_id], rounded_gate),
                                             ("down", down_bank[expert_id], rounded_down)):
                if not np.isfinite(original).all() or not np.isfinite(rounded).all():
                    raise ValueError("nonfinite decoded or converted weight")
                exact = original.view(np.uint32) == rounded.view(np.uint32)
                difference = np.abs(original - rounded)
                records.append({"expert_id": expert_id, "tensor": name, "elements": int(original.size),
                                "exact_elements": int(np.sum(exact)), "changed_elements": int(np.sum(~exact)),
                                "max_abs_difference": float(difference.max()),
                                "original_sha256": hashlib.sha256(memoryview(original)).hexdigest(),
                                "bf16_widened_sha256": hashlib.sha256(memoryview(rounded)).hexdigest()})
            coefficient = float(fixtures[label]["routing_weights"][position, 0, 0])
            original_output += coefficient * contribution(fixtures[label]["x"], gate_bank[expert_id], down_bank[expert_id])
            converted_output += coefficient * contribution(fixtures[label]["x"], rounded_gate, rounded_down)
            rounded_gate = rounded_down = original = rounded = exact = difference = None
            bank.reserve(samples)
        original_matches = np.isclose(original_output, expected[label], **bank.dynamic.CPU_TOLERANCE)
        converted_matches = np.isclose(converted_output, expected[label], **bank.dynamic.CPU_TOLERANCE)
        outputs[label] = {"original_fp32_output": original_output.tolist(), "converted_weight_fp32_output": converted_output.tolist(),
                          "original_fp32_sha256": bank.dynamic.array_digest(original_output),
                          "frozen_reference_sha256": frozen["reference_sha256"][label],
                          "converted_weight_fp32_sha256": bank.dynamic.array_digest(converted_output),
                          "original_matches_frozen_cpu_gate": bool(original_matches.all()),
                          "original_max_abs_difference": float(np.max(np.abs(original_output - expected[label]))),
                          "converted_weights_pass_frozen_cpu_gate": bool(converted_matches.all()),
                          "converted_max_abs_difference": float(np.max(np.abs(converted_output - expected[label]))),
                          "converted_mismatched_elements": int(np.sum(~converted_matches)), "output_elements": int(converted_output.size)}
        if not original_matches.all():
            raise ValueError("unconverted bank expression fails unchanged frozen CPU gate")
    after = identity(BANK_DATA)
    if after != before:
        raise ValueError("frozen FP32 bank identity changed during read-only qualification")
    changed = sum(row["changed_elements"] for row in records)
    gate_passed = all(row["converted_weights_pass_frozen_cpu_gate"] for row in outputs.values())
    result = {"schema": 1, "completed": True, "scope": __doc__, "source_sha256": bank.dynamic.digest(__file__),
              "bank_helper_sha256": BANK_HELPER_SHA256, "dependency_sha256": bank.dependencies(),
              "bank_data": str(BANK_DATA), "bank_data_sha256": BANK_DATA_SHA256, "bank_identity_before": before,
              "bank_identity_after": after, "reference_receipt_sha256": bank.REFERENCE_RECEIPT_SHA256,
              "rounding": "BF16 nearest/even: bits += 0x7fff + ((bits >> 16) & 1); bits &= 0xffff0000; widen to FP32",
              "blas_thread_environment": {name: bank.os.environ.get(name) for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")},
              "tolerance": bank.dynamic.CPU_TOLERANCE, "total_weight_elements": sum(row["elements"] for row in records),
              "changed_weight_elements": changed, "all_weights_exactly_bf16_representable": changed == 0,
              "max_weight_abs_difference": max(row["max_abs_difference"] for row in records),
              "weight_records": records, "outputs": outputs, "strict_cpu_gate_passed": gate_passed,
              "eligible_for_bf16_graph": changed == 0 or gate_passed, "model_built": False,
              "weight_tensor_limit_bytes": bank.WEIGHT_LIMIT, "qualification_ms": (time.perf_counter_ns() - started) / 1e6}
    result.update(bank.memory_summary(samples, baseline))
    if result["peak_private_increase_bytes"] >= bank.WEIGHT_LIMIT:
        result.update(eligible_for_bf16_graph=False, error="read-only qualification exceeded conservative 1 GiB private-memory cap")
    with report_path.open("x", encoding="utf-8") as output:
        json.dump(result, output, indent=2)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    result = qualify(args.report)
    print(json.dumps({key: value for key, value in result.items() if key not in ("weight_records", "outputs", "reserve_samples")}, indent=2))
    print(json.dumps({label: {key: value for key, value in row.items() if not key.endswith("_output")} for label, row in result["outputs"].items()}, indent=2))
