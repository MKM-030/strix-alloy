"""Root-guarded expert0-only real q4c-v2 packing and independent CPU references.

Import has no payload reads or native/NumPy imports. Execution reads only the
two selected expert matrices and loads AMD's pinned offline formatter. It does
not create an NPU context or run inference. Root owns the 8GiB job and22/18GiB
host reserves. Outputs qualify these FCs, not an MTP route or draft quality.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import types

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts/benchmarks"
WORK = ROOT / "server/.local/optimization9h-20261004"
PACK_SOURCE = SCRIPTS / "halogen_qmoe_real_pack.py"
PACK_SHA = "b74d76c4082d447285f55a1af41e8f28ec85a4bd35b5ce1535553eed6fe004d1"
TOLERANCE = {"rtol": .03, "atol": .003}


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def bf16_words(values, np):
    bits = np.asarray(values, dtype=np.float32).view(np.uint32)
    if not np.isfinite(values).all():
        raise ValueError("Finite BF16 values required")
    return ((bits + np.uint32(0x7fff) + ((bits >> 16) & 1)) >> 16).astype("<u2")


def widen(words, np):
    return (np.asarray(words, dtype=np.uint32) << 16).view(np.float32)


def metrics(actual, expected, np):
    a, b = actual.astype(np.float64), expected.astype(np.float64)
    error = a - b
    denominator = float(np.square(b).sum())
    return dict(max_abs_error=float(np.abs(error).max()), rmse=float(np.sqrt(np.square(error).mean())),
                relative_l2_error=float(np.sqrt(np.square(error).sum() / denominator)) if denominator else 0.0)


def independent_affine(prepared, np, rounded_scales):
    """Decode nibbles directly; never call affine.reconstruct_rows or DD."""
    n, k = prepared.N, prepared.K
    codes = np.empty((n, k), dtype=np.int16)
    codes[:, 0::2] = prepared.weights & 15
    codes[:, 1::2] = prepared.weights >> 4
    blocks = k // 32
    zeros = np.empty((n, blocks), dtype=np.int16)
    zeros[:, 0::2] = prepared.zero_points & 15
    zeros[:, 1::2] = prepared.zero_points[:, :blocks // 2] >> 4
    scales = widen(bf16_words(prepared.scales, np), np) if rounded_scales else prepared.scales
    return ((codes.reshape(n, blocks, 32) - zeros[:, :, None]) * scales[:, :, None]).reshape(n, k).astype(np.float32)


def cpu_dot(rows, x, np):
    # FP64 reference accumulation is independent of native/BF16 kernel arithmetic.
    return np.asarray([np.dot(row.astype(np.float64), x.astype(np.float64)) for row in rows], dtype="<f4")


def save(path, array, np):
    with path.open("xb") as stream:
        np.save(stream, array, allow_pickle=False)
        stream.flush()
        os.fsync(stream.fileno())
    return str(path)


def run(args):
    out = args.report.resolve().parent
    if args.report.exists() or out == WORK.resolve() or not out.is_relative_to(WORK.resolve()) or not out.is_dir():
        raise ValueError("Fresh root-created task output directory required")
    result = dict(schema="halogen_real_expert_fc_preparation_v1", passed=False, expert=0,
                  scope="selected real v2 layer48 expert0 FC arithmetic only", stage="validate",
                  full_mtp_proven=False, acceptance_qualified=False, speed_gain_established=False,
                  router_semantics_verified=False, activation_semantics_verified=False,
                  approximate_quantization=True, source_sha256=args.expected_probe_sha256,
                  tolerance=TOLERANCE, fixtures=[], rows=[], completed_experts=0)
    started, handles = time.perf_counter(), []
    try:
        if sha(__file__) != args.expected_probe_sha256 or sha(PACK_SOURCE) != PACK_SHA:
            raise ValueError("Reviewed preparation/helper source changed")
        payload = PACK_SOURCE.read_bytes()
        helper = types.ModuleType("halogen_qmoe_real_pack")
        helper.__file__ = str(PACK_SOURCE)
        exec(compile(payload, str(PACK_SOURCE), "exec"), helper.__dict__)
        result["frozen_inputs"] = helper.verify_pins(PACK_SHA)
        result["frozen_inputs"][str(Path(__file__).resolve())] = args.expected_probe_sha256
        modules = helper.import_sources(result, started, args.maximum_seconds)
        sparse, affine = modules["halogen_npu_v2_sparse"], modules["halogen_qmoe_affine"]
        frame = modules["host_frames"].frame
        helper.boundary(result, frame, started, args.maximum_seconds, helper.WORKING_BYTES)
        result["stage"] = "source_binding"
        unc, entries, machine, source, before, binding = helper.source_binding(sparse)
        result["source_binding"] = binding
        result["stage"] = "offline_packer_import"
        native = helper.native_packer(handles, result)
        import numpy as np
        result["numpy_version"] = np.__version__
        pins, source_bytes = {}, 0
        with unc.open("rb") as stream:
            for index, spec in enumerate(helper.MATRICES):
                label, name, rows, k, padded, packed_bytes = spec
                result["stage"] = label + "_prepare"
                print("REAL_EXPERT_STAGE " + result["stage"], flush=True)
                helper.boundary(result, frame, started, args.maximum_seconds, helper.WORKING_BYTES)
                decoded, record = sparse.expert(stream, entries[name], 0, rows)
                if decoded.dtype != np.float32 or decoded.shape != (rows, k) or not np.isfinite(decoded).all():
                    raise ValueError("Selected decoded expert geometry/values differ")
                ordered = affine.reorder_gate_up_rows(decoded, source_layout="concatenated", target_layout="interleaved") if index == 0 else decoded
                if index == 0 and (not np.array_equal(ordered[0::2], decoded[:rows // 2]) or
                                   not np.array_equal(ordered[1::2], decoded[rows // 2:])):
                    raise ValueError("FC1 g0,u0 row interleave failed")
                prepared = affine.quantize_rows(ordered, row_layout="gate_up_interleaved" if index == 0 else "linear")
                reconstructed = independent_affine(prepared, np, False)
                quantization = metrics(reconstructed, ordered, np)
                del reconstructed
                reconstructed = independent_affine(prepared, np, True)
                rounded_quantization = metrics(reconstructed, ordered, np)
                attributes = {"K": k, "N": rows, "lora": False, "mladf_version": "v2",
                              "asymmetric_quant": True, "bias_en": False, "block_size": 32}
                attr = native.Attributes()
                for key, value in attributes.items():
                    attr.set(key, value)
                data, size, pk, pn = native.matmulnbits.matmulnbits_pack_const_float32(
                    prepared.weights, prepared.bias, prepared.scales, prepared.zero_points, attr)
                if data.dtype != np.uint8 or data.ndim != 1 or data.nbytes != packed_bytes or size != packed_bytes or [pk, pn] != padded:
                    raise ValueError("Official packed FC extent/geometry differs")
                packed_path = out / (label + ".packed.bin")
                with packed_path.open("xb") as packed_stream:
                    helper.write_exact(packed_stream, memoryview(data).cast("B"))
                    packed_stream.flush()
                    os.fsync(packed_stream.fileno())
                paths, cases = [packed_path], []
                for call in range(2):
                    axis = np.arange(k, dtype=np.float32)
                    values = (.25 * np.sin(axis * (.17 if call == 0 else .071)) +
                              .125 * np.cos(axis * (.037 if call == 0 else .113))).astype(np.float32)
                    words = bf16_words(values, np)
                    x = widen(words, np)
                    affine_ref = cpu_dot(reconstructed, x, np)
                    original = cpu_dot(decoded, x, np)
                    decoded_ref = np.empty_like(original)
                    if index == 0:
                        decoded_ref[0::2], decoded_ref[1::2] = original[:rows // 2], original[rows // 2:]
                    else:
                        decoded_ref[:] = original
                    case_paths = [out / f"{label}.call{call}.{suffix}.npy" for suffix in ("input-bf16", "affine-reference", "decoded-reference")]
                    for path, array in zip(case_paths, (words, affine_ref, decoded_ref)):
                        save(path, array, np)
                    paths.extend(case_paths)
                    cases.append(dict(call=call, input_path=str(case_paths[0]), affine_reference_path=str(case_paths[1]),
                                      decoded_reference_path=str(case_paths[2]), input_dtype="BF16 words",
                                      reference_accumulation="FP64 then FP32", approximation_output_error=metrics(affine_ref, decoded_ref, np)))
                for path in paths:
                    pins[str(path)] = sha(path)
                source_bytes += sum(row["bytes"] for row in record["ranges"])
                result["fixtures"].append(dict(index=index, expert=0, label=label, k=k, n=rows, bytes=packed_bytes,
                                               path=str(packed_path), cases=cases, synthetic=False,
                                               row_layout="g0,u0,g1,u1,..." if index == 0 else "linear"))
                result["rows"].append(dict(label=label, source=record, packed_sha256=pins[str(packed_path)],
                                           affine_input_sha256={key: helper.array_sha(getattr(prepared, key)) for key in ("weights", "bias", "scales", "zero_points")},
                                           independent_affine_fp32_weight_error=quantization,
                                           independent_affine_bf16_scale_weight_error=rounded_quantization,
                                           scale_semantics="BF16 nearest-even; SDK AIEMode(16,16,6,1)",
                                           source_row_layout="concatenated" if index == 0 else "linear"))
                del decoded, ordered, prepared, reconstructed, data
        if source_bytes != helper.SOURCE_BYTES_PER_EXPERT:
            raise ValueError("Source reads exceed one selected expert")
        result["source_bytes_read"] = source_bytes
        result["file_pins"] = pins
        if sparse.native_identity(machine, source) != before:
            raise ValueError("Native checkpoint identity changed during preparation")
        after = sparse.metadata(unc)
        if after["header_sha256"] != binding["header_sha256"] or after["table_sha256"] != binding["table_sha256"]:
            raise ValueError("Native checkpoint metadata changed during preparation")
        binding["native_identity_after"] = before
        helper.verify_pins(PACK_SHA)
        if sha(__file__) != args.expected_probe_sha256:
            raise ValueError("Preparation source changed during execution")
        helper.boundary(result, frame, started, args.maximum_seconds)
        result.update(passed=True, stage="complete", completed_experts=1)
    except BaseException as exc:
        result.update(passed=False, failed_stage=result["stage"], stage="failed", error=type(exc).__name__ + ": " + str(exc))
    finally:
        cleanup_errors = []
        for handle in reversed(handles):
            try:
                handle.close()
            except BaseException as exc:
                cleanup_errors.append(type(exc).__name__ + ": " + str(exc))
        if cleanup_errors:
            result.update(passed=False, cleanup_errors=cleanup_errors)
        result["host_seconds"] = time.perf_counter() - started
        with args.report.open("x", encoding="utf-8") as stream:
            json.dump(result, stream, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
    print(json.dumps({key: value for key, value in result.items() if key not in ("frozen_inputs", "file_pins")}, indent=2), flush=True)
    return 0 if result["passed"] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root-owned-admission", action="store_true")
    parser.add_argument("--expected-probe-sha256", required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--maximum-seconds", type=int, default=180)
    args = parser.parse_args()
    if not args.root_owned_admission or os.name != "nt" or sys.version_info[:2] != (3, 12) or not 60 <= args.maximum_seconds <= 300:
        raise ValueError("Root-guarded Windows CPython3.12 expert0 preparation required")
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
