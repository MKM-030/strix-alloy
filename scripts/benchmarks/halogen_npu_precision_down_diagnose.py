"""CPU-only suffix diagnosis from complete retained tiny expert outputs.

Never initializes ORT, Windows ML or hardware. The first projection is checked
against its measured exact formula. SiLU, multiplication and reduction below
are explicit arithmetic hypotheses, not observed intermediate device outputs.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from halogen_npu_parameter_probe import fixtures, reference
from halogen_npu_precision_split_probe import bfp16_high, prepare


TOLERANCE = {"rtol": .03, "atol": .003}
DEPENDENCIES = {
    "halogen_npu_parameter_probe.py": "ddd476b25f6e434b03390fb0974d54f157fcd26492417641a5ed9cc38fa15a1c",
    "halogen_npu_precision_split_probe.py": "012f496c94e52f06ed2b530a58fbc35781ef7795f44715b16f13d75285a68412",
    "halogen_npu_precision_expert_split_probe.py": "68bd9da3f0ad90971c84fed2706b306631767d001ef4b16be9326dafd8a2428f",
}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def array_digest(value):
    return hashlib.sha256(np.ascontiguousarray(value, dtype=np.float32).tobytes()).hexdigest()


def bf16(value, ties_away=False):
    bits = np.array(value, dtype=np.float32, copy=True).view(np.uint32)
    correction = np.uint32(0x8000) if ties_away else np.uint32(0x7fff) + ((bits >> 16) & 1)
    return ((bits + correction) & np.uint32(0xffff0000)).view(np.float32)


def gemm(left, right):
    return bf16(bfp16_high(left, -1) @ bfp16_high(right, -2), True)


def projection(feed):
    split = prepare(feed)
    products = [gemm(split[x], split[w]) for x, w in
                [("x_high", "W_high"), ("x_high", "W_low"),
                 ("x_low", "W_high"), ("x_low", "W_low")]]
    return bf16(bf16(bf16(products[0] + products[1], True) + products[2], True) + products[3], True)


def retained(receipt, label, expected):
    rows = [row for row in receipt["calls"] if row["input_set"] == label]
    arrays = [np.array(row["actual_output"], dtype=np.float32) for row in rows]
    if len(rows) != 6:
        raise ValueError("expected six retained calls per fixture")
    for row, array in zip(rows, arrays):
        if array.shape != expected.shape or not np.isfinite(array).all():
            raise ValueError("retained output geometry or finite values differ")
        if array_digest(array) != row["output_sha256"]:
            raise ValueError("retained output hash differs")
        failures = int((~np.isclose(array, expected, **receipt["tolerance"])).sum())
        if failures != row["mismatched_elements"] or bool(failures == 0) != row["passed"]:
            raise ValueError("retained numerical gate differs")
        if float(np.abs(array - expected).max()) != row["max_abs_error"]:
            raise ValueError("retained maximum error differs")
        if not np.array_equal(array, arrays[0]):
            raise ValueError("retained repetitions differ")
    return arrays[0]


def compare(value, expected, actual):
    failed = ~np.isclose(value, expected, **TOLERANCE)
    return {"mismatched_elements": int(failed.sum()),
            "mismatched_indices": np.argwhere(failed).tolist(),
            "max_abs_error": float(np.abs(value - expected).max()),
            "l2_error": float(np.linalg.norm(value - expected)),
            "exact_values_matching_npu": int((value == actual).sum()),
            "max_abs_distance_to_npu": float(np.abs(value - actual).max()),
            "l2_distance_to_npu": float(np.linalg.norm(value - actual)),
            "output_sha256": array_digest(value), "output": value.tolist()}


def diagnose(full_directory, first_directory):
    root = Path(__file__).resolve().parent
    hashes = {name: digest(root / name) for name in DEPENDENCIES}
    if hashes != DEPENDENCIES:
        raise ValueError("frozen source dependency differs")
    full = json.loads((full_directory / "npu.json").read_text())
    first = json.loads((first_directory / "npu.json").read_text())
    cpu = json.loads((full_directory / "cpu.json").read_text())
    if full["tolerance"] != TOLERANCE or first["tolerance"] != TOLERANCE:
        raise ValueError("unchanged tolerance differs")
    for directory, receipt, model in [(full_directory, full, "tiny-expert-first-split.onnx"),
                                       (first_directory, first, "first-gemm-split.onnx")]:
        if digest(directory / model) != receipt["model_sha256"]:
            raise ValueError("model hash differs")
    rows = []
    for label, feed in fixtures().items():
        expected = reference(feed)
        if {name: array_digest(value) for name, value in feed.items()} != full["input_sets"][label]:
            raise ValueError("original fixture hash differs")
        if array_digest(expected) != full["reference_sha256"][label]:
            raise ValueError("original full FP32 reference hash differs")
        actual = retained(full, label, expected)
        retained(cpu, label, expected)
        gu_reference = np.stack([feed["x"] @ weight for weight in feed["W_gate_up"]])
        gu = retained(first, label, gu_reference)
        predicted_gu = projection(feed)
        if not np.array_equal(gu, predicted_gu):
            raise ValueError("observed first-projection formula differs")
        gate, up = np.split(gu, 2, axis=-1)
        hidden_exact = (gate / (1 + np.exp(-gate))) * up
        # Fused SiLU and both multiplications are modeled with BF16 RNE.
        # These outputs were not retained by the hardware graph.
        hidden = bf16(bf16(gate / (1 + np.exp(-gate))) * up)
        down, routing = feed["W_down"], bf16(feed["routing_weights"])
        hidden_q, down_q = bfp16_high(hidden, -1), bfp16_high(down, -2)

        def finish(expert_output):
            weighted = bf16(expert_output * routing)
            return bf16(weighted.sum(axis=0, dtype=np.float32), True)

        low = down - down_q
        predictions = {
            "retained_npu": actual,
            "observed_projection_fp32_suffix": ((hidden_exact @ down) * feed["routing_weights"]).sum(axis=0, dtype=np.float32),
            "bf16_activation_fp32_down_and_routing": ((hidden @ down) * feed["routing_weights"]).sum(axis=0, dtype=np.float32),
            "bf16_down_no_bfp": finish(bf16(hidden @ bf16(down), True)),
            "bfp_down_weights_only": finish(bf16(hidden @ down_q, True)),
            "bfp_down_activation_only": finish(bf16(hidden_q @ bf16(down), True)),
            "bfp_down_both_operands": finish(gemm(hidden, down)),
            "two_term_down_weight_split_forecast": finish(bf16(gemm(hidden, down_q) + gemm(hidden, low), True)),
        }
        rows.append({"fixture": label, "reference_sha256": array_digest(expected),
                     "reference_output": expected.tolist(), "observed_projection_formula_exact": True,
                     "projection_output_sha256": array_digest(gu),
                     "hypothetical_hidden_sha256": array_digest(hidden),
                     "hypothetical_hidden": hidden.tolist(),
                     "comparisons": {name: compare(value, expected, actual) for name, value in predictions.items()}})
    return {"schema": 1, "scope": "CPU-only fixed arithmetic ablations; no hardware or provider launch",
            "tolerance": TOLERANCE, "script_sha256": digest(__file__), "dependency_sha256": hashes,
            "evidence_sha256": {str(path): digest(path) for path in
                                [full_directory / "npu.json", full_directory / "cpu.json",
                                 first_directory / "npu.json"]},
            "all_retained_calls_hash_and_gate_verified": True,
            "observed_activation_outputs_available": False, "full_graph_formula_exact": False,
            "down_weight_precision_dominates": False,
            "two_term_down_weight_split_passes_forecast": False, "hardware_candidate_prepared": False,
            "limitations": ["The first projection is exact in a separately measured graph; its internal output in the full graph was not retained",
                            "SiLU approximation, Mul rounding and ReduceSum accumulation remain unobserved",
                            "Counterfactual ablations identify errors in this arithmetic model, not an independently measured device root cause",
                            "Weight-only and activation-only down BFP ablations have similar errors; a weight split still fails the original gate"],
            "fixtures": rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full-dir", type=Path, required=True)
    parser.add_argument("--first-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.report.exists():
        raise FileExistsError("completed diagnosis receipt exists; overwrite refused")
    result = diagnose(args.full_dir, args.first_dir)
    with args.report.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2)
    print(json.dumps({"report": str(args.report), "report_sha256": digest(args.report),
                      "retained_calls_verified": result["all_retained_calls_hash_and_gate_verified"],
                      "full_graph_formula_exact": False, "down_weight_precision_dominates": False,
                      "weight_only_split_forecast_passed": False}, indent=2))


if __name__ == "__main__":
    main()
