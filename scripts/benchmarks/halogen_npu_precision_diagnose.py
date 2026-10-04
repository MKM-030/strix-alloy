"""CPU-only precision approximations for the frozen tiny runtime-matrix probe.

Never initializes ORT, Windows ML, an execution provider, or hardware. The
approximations are not a model of the closed WinML compiler's exact kernels.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

import numpy as np

from halogen_npu_parameter_probe import fixtures, reference


TOLERANCE = {"rtol": .03, "atol": .003}
QUARK_SOURCE = ("https://github.com/amd/Quark/blob/"
                "1b229f781a1974cc742884e42d8eefc1eebb4f0a/"
                "quark/onnx/operators/custom_ops/src/bfp/cpu/bfp_kernel.cc")


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def bf16(value, half_away=False):
    """Finite FP32 -> BF16, represented as FP32; default ties-to-even.

    half_away=True implements nearest with exact ties away from zero. This is
    an observed device-output formula, not a claimed provider option.
    """
    value = np.array(value, dtype=np.float32, copy=True)
    if not np.isfinite(value).all():
        raise ValueError("this bounded approximation requires finite input")
    bits = value.view(np.uint32)
    rounded = (bits + np.uint32(0x8000) if half_away else
               bits + np.uint32(0x7fff) + ((bits >> 16) & 1))
    return (rounded & np.uint32(0xffff0000)).view(np.float32)


def bfp16(value, axis, compiler_style=False, group_size=8, rounding_mode=2):
    """Quark v0.12 BFP CPU algorithm; default eb8 and rounding_mode=2.

    Input already has BF16 precision. Block axis is the GEMM reduction axis.
    BFPCPUKernel uses symmetric saturation; BFPCPUKernelCompiler increases
    the shared exponent if rounded positive mantissa is >=128 (negative <-128).
    Neither algorithm establishes the behavior of a WinML device conversion.
    """
    value = np.asarray(value, dtype=np.float32)
    moved = np.moveaxis(value, axis, -1).copy()
    shape = moved.shape
    if group_size not in (8, 16) or shape[-1] % group_size:
        raise ValueError("approximation permits primary-defined eb8/eb16 blocks only")
    if rounding_mode not in (0, 1, 2):
        raise ValueError("rounding mode must be one of the documented Quark modes")
    def round_mantissa(value):
        if rounding_mode == 0:
            return np.sign(value) * np.floor(np.abs(value) + np.float32(.5))
        if rounding_mode == 1:
            return np.floor(value + np.float32(.5))
        return np.rint(value)
    blocks = moved.reshape(*shape[:-1], shape[-1] // group_size, group_size)
    exponent = ((blocks.view(np.uint32) & 0x7f800000) >> 23).max(-1, keepdims=True)
    step = np.exp2(exponent.astype(np.int32) - 127 - 6).astype(np.float32)
    rounded = round_mantissa(blocks / step)
    if compiler_style:
        carry = np.any((rounded >= 128) | (rounded < -128), axis=-1, keepdims=True)
        step = step * np.where(carry, np.float32(2), np.float32(1))
        quantized = round_mantissa(blocks / step) * step
    else:
        quantized = np.clip(rounded, -127, 127) * step
    return np.moveaxis(quantized.reshape(shape), -1, axis)


def approximation(feed, bfp_weights=False, bfp_activations=False, compiler_style=False):
    x, gate_up, down, routing = (bf16(feed[name]) for name in
                               ("x", "W_gate_up", "W_down", "routing_weights"))
    if bfp_weights:
        gate_up = bfp16(gate_up, -2, compiler_style)
        down = bfp16(down, -2, compiler_style)
    if bfp_activations:
        x = bfp16(x, -1, compiler_style)
    projected = bf16(x @ gate_up)
    gate, up = np.split(projected, 2, axis=-1)
    # The compiler logs a fused SiLU kernel. Its approximation is not public;
    # here exact FP32 SiLU is rounded once to BF16, then multiplication is rounded.
    hidden = bf16(bf16(gate / (1 + np.exp(-gate))) * up)
    if bfp_activations:
        hidden = bfp16(hidden, -1, compiler_style)
    expert_output = bf16(hidden @ down)
    return bf16(np.sum(bf16(expert_output * routing), axis=0, dtype=np.float32))


def evidence(directory):
    report = directory / "npu.json"
    receipt = json.loads(report.read_text(encoding="utf-8"))
    stderr = directory / "npu-stderr.txt"
    stdout = directory / "npu-stdout.txt"
    context_path = next((directory / "vitisai-cache").rglob("context.json"))
    context = json.loads(context_path.read_text(encoding="utf-8"))
    error = receipt.get("error", "")
    observed = [{"index": int(index), "actual": float(actual), "expected": float(expected)}
                for index, actual, expected in re.findall(
                    r"\[0, (\d+)\]: ([\d.eE+-]+) \(ACTUAL\), ([\d.eE+-]+) \(DESIRED\)", error)]
    return receipt, {
        "directory": str(directory.resolve()), "passed": receipt["passed"],
        "model_sha256": receipt["model_sha256"],
        "provider_library_sha256": receipt["provider_library_sha256"],
        "files_sha256": {path.name: sha256(path) for path in (report, stderr, stdout, context_path)},
        "passes": context["config"]["passes"],
        "bfp16_weight_enable_occurrences": stderr.read_text().count("config.enable_bfp16_wts val=1"),
        "bfp16_emulation_compile_define": "-DAIE_API_EMULATE_BFLOAT16_MMUL_WITH_BFP16=1" in stdout.read_text(),
        "observed_exact_mismatch_values": observed,
    }


def diagnose(failed_dir, working_dir):
    receipt, failed = evidence(failed_dir)
    _, working = evidence(working_dir)
    if receipt["tolerance"] != TOLERANCE:
        raise ValueError("receipt differs from the unchanged frozen NPU tolerance")
    feeds = fixtures()
    for label, feed in feeds.items():
        for name, value in feed.items():
            actual_hash = hashlib.sha256(value.tobytes()).hexdigest()
            if actual_hash != receipt["input_sets"][label][name]:
                raise ValueError("fixture identity differs: " + label + "/" + name)
        if hashlib.sha256(reference(feed).tobytes()).hexdigest() != receipt["reference_sha256"][label]:
            raise ValueError("reference identity differs: " + label)
    labels = [label for label, feed in feeds.items() if all(
        float(reference(feed)[0, row["index"]]) == row["expected"]
        for row in failed["observed_exact_mismatch_values"])]
    if len(labels) != 1 or not failed["observed_exact_mismatch_values"]:
        raise ValueError("cannot uniquely identify failing fixture from retained assertion")
    variants = {
        "bf16_only": {},
        "quark_bfp16_weights": {"bfp_weights": True},
        "quark_bfp16_both_operands": {"bfp_weights": True, "bfp_activations": True},
        "quark_compiler_bfp16_weights": {"bfp_weights": True, "compiler_style": True},
        "quark_compiler_bfp16_both_operands": {"bfp_weights": True, "bfp_activations": True,
                                                "compiler_style": True},
    }
    results = []
    for label, feed in feeds.items():
        expected = reference(feed)
        for name, kwargs in variants.items():
            simulated = approximation(feed, **kwargs)
            error = np.abs(simulated - expected)
            row = {"fixture": label, "approximation": name,
                   "mismatched_elements": int(np.sum(error > .003 + .03 * np.abs(expected))),
                   "max_abs_error": float(error.max()), "output": simulated.tolist()}
            if label == labels[0]:
                row["retained_actual_comparison"] = [dict(point,
                    approximation=float(simulated[0, point["index"]]),
                    abs_distance_to_actual=abs(float(simulated[0, point["index"]]) - point["actual"]))
                    for point in failed["observed_exact_mismatch_values"]]
            results.append(row)
    return {"schema": 1, "scope": "CPU-only bounded approximation; no EP or hardware launch",
            "seed": receipt["seed"], "tolerance": TOLERANCE,
            "fixture_and_reference_hashes_verified": True, "failed_fixture": labels[0],
            "root_cause_proved": False, "supported_precision_disable_found": False,
            "limitations": ["Full failed NPU output was not retained; only five exact values are available",
                            "WinML GEMM packing, reduction tree and SiLU approximation are not reproduced",
                            "Quark CPU BFP quantizers do not prove closed compiler device arithmetic"],
            "quark_source": QUARK_SOURCE, "script_sha256": sha256(__file__),
            "failed_evidence": failed, "working_evidence": working, "approximations": results}


def diagnose_first_gemm(directory):
    """Compare complete retained hardware outputs; never opens an ORT session."""
    npu_path, cpu_path = directory / "npu.json", directory / "cpu.json"
    npu = json.loads(npu_path.read_text(encoding="utf-8"))
    cpu = json.loads(cpu_path.read_text(encoding="utf-8"))
    guarded = json.loads((directory / "result.json").read_text(encoding="utf-8"))
    cleanup = json.loads((directory / "cleanup.json").read_text(encoding="utf-8"))
    identity = json.loads((directory / "identity.json").read_text(encoding="utf-8"))
    model_path = directory / "first-gemm.onnx"
    if npu["tolerance"] != TOLERANCE or npu["model_sha256"] != sha256(model_path):
        raise ValueError("first-GEMM model or unchanged tolerance differs")
    for name, expected_hash in guarded["artifacts_sha256"].items():
        if name in ("npu.json", "cpu.json", "first-gemm.onnx", "cleanup.json", "identity.json"):
            if sha256(directory / name) != expected_hash:
                raise ValueError("guarded artifact identity differs: " + name)
    variants = {
        "bf16_only": (False, False, False, -2),
        "quark_bfp16_weights_K": (True, False, False, -2),
        "quark_bfp16_both_K": (True, True, False, -2),
        "quark_compiler_bfp16_weights_K": (True, False, True, -2),
        "quark_compiler_bfp16_both_K": (True, True, True, -2),
        # Quark permits a block axis; N is a layout sensitivity comparison,
        # not a claim that the compiled provider's weights use this grouping.
        "layout_sensitivity_compiler_bfp16_weights_N": (True, False, True, -1),
        "layout_sensitivity_compiler_bfp16_both_N": (True, True, True, -1),
    }
    results = []
    fixture_rows = []
    exact_formula_results = []
    for label, feed in fixtures().items():
        for name in ("x", "W_gate_up"):
            if hashlib.sha256(feed[name].tobytes()).hexdigest() != npu["input_sets"][label][name]:
                raise ValueError("first-GEMM fixture differs: " + label + "/" + name)
        expected = np.stack([feed["x"] @ weight for weight in feed["W_gate_up"]])
        expected_hash = hashlib.sha256(expected.tobytes()).hexdigest()
        if expected_hash != npu["reference_sha256"][label] or expected_hash != cpu["reference_sha256"][label]:
            raise ValueError("first-GEMM independent reference differs: " + label)
        calls = [row for row in npu["calls"] if row["input_set"] == label]
        actual_arrays = [np.asarray(row["actual_output"], dtype=np.float32) for row in calls]
        for row, array in zip(calls, actual_arrays):
            if array.shape != expected.shape or not np.isfinite(array).all():
                raise ValueError("first-GEMM output shape or finite-value contract differs")
            if hashlib.sha256(array.tobytes()).hexdigest() != row["output_sha256"]:
                raise ValueError("first-GEMM retained array hash differs")
        actual = actual_arrays[0]
        same_output = all(np.array_equal(actual, array) for array in actual_arrays)
        matches = np.isclose(actual, expected, **TOLERANCE)
        fixture_rows.append({"fixture": label, "calls": len(calls), "all_calls_identical": same_output,
                             "output_sha256": calls[0]["output_sha256"],
                             "output_is_exact_bf16_grid": bool(np.array_equal(actual, bf16(actual))),
                             "mismatched_elements": int(np.sum(~matches)), "output_elements": int(actual.size),
                             "max_abs_error": float(np.max(np.abs(actual - expected)))})
        x, weights = bf16(feed["x"]), bf16(feed["W_gate_up"])
        for name, (quant_weights, quant_x, compiler_style, axis) in variants.items():
            sim_x = bfp16(x, -1, compiler_style) if quant_x else x
            sim_weights = bfp16(weights, axis, compiler_style) if quant_weights else weights
            simulated = bf16(sim_x @ sim_weights)
            distance = np.abs(simulated - actual)
            results.append({"fixture": label, "approximation": name, "weight_block_axis": axis,
                            "group_size": 8 if quant_weights else None,
                            "exact_elements_matching_actual": int(np.sum(simulated == actual)),
                            "mismatches_against_fp32": int(np.sum(~np.isclose(simulated, expected, **TOLERANCE))),
                            "max_abs_distance_to_actual": float(distance.max()),
                            "mean_abs_distance_to_actual": float(distance.mean()),
                            "simulated_sha256": hashlib.sha256(simulated.tobytes()).hexdigest()})
        # Fixed primary-defined group widths and Quark rounding modes, no
        # continuously fitted scales or tolerances. Public AIE BF16 emulation
        # explicitly selects eb8. eb16 is a documented type sensitivity check.
        for group_size in (8, 16):
            for rounding_mode in (0, 1, 2):
                sim_x = bfp16(x, -1, True, group_size, rounding_mode)
                sim_weights = bfp16(weights, -2, True, group_size, rounding_mode)
                raw = sim_x @ sim_weights
                simulated = bf16(raw)
                output_away = bf16(raw, half_away=True)
                residual_indices = np.argwhere(simulated != actual)
                exact_formula_results.append({
                    "fixture": label, "input_bf16_rounding": "half_even", "weight_block_axis": -2,
                    "activation_block_axis": -1, "group_size": group_size,
                    "mantissa_rounding_mode": rounding_mode, "compiler_style_exponent_carry": True,
                    "output_half_even_exact_elements": int(np.sum(simulated == actual)),
                    "output_half_away_exact_elements": int(np.sum(output_away == actual)),
                    "output_half_away_max_abs_distance": float(np.max(np.abs(output_away - actual))),
                    "output_half_away_sha256": hashlib.sha256(output_away.tobytes()).hexdigest(),
                    "half_even_residual_details": [
                        {"index": index.tolist(), "raw_fp32": float(raw[tuple(index)]),
                         "raw_fp32_bits": hex(int(raw.view(np.uint32)[tuple(index)])),
                         "half_even": float(simulated[tuple(index)]),
                         "half_away": float(output_away[tuple(index)]), "actual": float(actual[tuple(index)])}
                        for index in residual_indices] if group_size == 8 and rounding_mode == 0 else []})
    monitored = [json.loads(line) for line in (directory / "memory.jsonl").read_text().splitlines()]
    return {"scope": "offline comparison of complete guarded first-GEMM outputs; no hardware initialization",
            "directory": str(directory.resolve()), "guard_status": guarded["status"],
            "guard_errors": guarded["guard_errors"], "source_pins": identity["sources_sha256"],
            "receipt_sha256": {name: sha256(directory / name) for name in
                               ("npu.json", "cpu.json", "first-gemm.onnx", "result.json", "cleanup.json", "memory.jsonl")},
            "cpu_passed": cpu["passed"], "npu_passed": npu["passed"],
            "npu_timing_qualified": npu["timing_qualified"], "npu_initialization_ms": npu["initialization_ms"],
            "node_events": npu["node_events"], "executed_node_providers": npu["executed_node_providers"],
            "all_owned_jobs_closed": all(stage["owned_job_closed"] for stage in guarded["stages"]),
            "minimum_available_gib": min(row["available_bytes"] for row in monitored) / (1 << 30),
            "minimum_commit_headroom_gib": min(row["commit_headroom_bytes"] for row in monitored) / (1 << 30),
            "cleanup_error": cleanup["cleanup_error"],
            "fixture_and_reference_hashes_verified": True, "first_projection_failure_localized": True,
            "first_gemm_output_formula_proved_for_retained_calls": all(
                row["output_half_away_exact_elements"] == 640 for row in exact_formula_results
                if row["group_size"] == 8 and row["mantissa_rounding_mode"] == 0),
            "root_cause_proved": False, "supported_precision_disable_found": False,
            "limitations": ["Public AIE API supports K-axis eb8 conversions; provider packing remains closed",
                            "N-axis variants measure grouping sensitivity and do not establish the provider layout",
                            "Exact eb8 half-away formula reproduces retained projections, not the full MoE graph",
                            "Stable per-fixture results do not establish every possible runtime-input update case"],
            "fixtures": fixture_rows, "approximations": results, "exact_formula_comparisons": exact_formula_results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--failed-dir", required=True, type=Path)
    parser.add_argument("--working-dir", required=True, type=Path)
    parser.add_argument("--first-gemm-dir", type=Path,
                        help="optional completed guarded first-GEMM receipts; offline reads only")
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    if args.report.exists():
        raise FileExistsError("report exists; overwrite refused")
    result = diagnose(args.failed_dir, args.working_dir)
    if args.first_gemm_dir:
        result["first_gemm"] = diagnose_first_gemm(args.first_gemm_dir)
    with args.report.open("x", encoding="utf-8") as output:
        json.dump(result, output, indent=2)
    print(json.dumps({"report": str(args.report.resolve()), "failed_fixture": result["failed_fixture"],
                      "root_cause_proved": result["root_cause_proved"],
                      "first_gemm": ({key: value for key, value in result["first_gemm"].items()
                                      if key not in ("source_pins", "receipt_sha256", "approximations", "exact_formula_comparisons")}
                                     if args.first_gemm_dir else None),
                      "approximations": [{k: row[k] for k in
                        ("fixture", "approximation", "mismatched_elements", "max_abs_error")}
                        for row in result["approximations"]]}, indent=2))


if __name__ == "__main__":
    main()
