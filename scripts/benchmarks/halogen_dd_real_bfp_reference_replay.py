"""CPU-only documented BFP candidates for retained real-DD expert0 outputs.

Reads only sealed preparation receipts, ~5.8 MB of existing packed FC fixtures,
small saved input/reference arrays, SDK text, and retained raw outputs. No
checkpoint, native library, engine, provider, or hardware is loaded. The
accepted arithmetic contract and tolerance are not changed by this diagnostic.
"""
import argparse
import hashlib
import json
from pathlib import Path
import time

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / "server/.local/optimization9h-20261004"
PREPARATION = WORK / "dd-real-expert-prepare-a88d6de92c2f4308870143a93be367e3/preparation.json"
ADMISSION = WORK / "dd-owned-fc-admission-9726b06bafab4ba69e4ac85356fec744/admission.json"
SDK = WORK / "qmoe-dd-owned-client-sdk/include/ryzenai/dynamic_dispatch"
PINS = {
    PREPARATION: "444bda8703820cf0f5c688705e08265bb4b7b9af7a48d814f0974f4206068d98",
    ADMISSION: "7a7261fcdca7b1ff9f0846e5f51a9896b918610e5e490a1727bfe87d49a05c1d",
    SDK / "ops/llm_ops/mladfmatmulbias/matmulbias_weights/matmulbias_weights_bfp16/mamtulbias_weights_params.hpp": "0337a125879a365b7644dcb8f9bd3055e1fa08ae7e35a8124d8e522b4689c7b9",
    SDK / "ops/llm_ops/mladfmatmulbias/matmulbias_weights/matmulbias_weights_bfp16/matmulbias_weights_bfp16.cpp": "6c592e4eba09dda87b14fe7bfbaa70188d0951b25c7cb73d7455caadafda9553",
    SDK / "ops/llm_ops/wts_devkit/xtensor/utils/compress_utils/compress_utils.hpp": "dd11369e03a359e5ed3840d94cbad3887dad5f6af9d8b35342920fd4e6e8b36f",
}
PUBLIC_CAST_REFERENCE = {
    "url": "https://github.com/amd/DynamicDispatch/blob/b3051f03e20aab237cda3bbe4cd2081f76b72b06/tests/cpp/unit_tests/test_cast.cpp#L152-L253",
    "commit": "b3051f03e20aab237cda3bbe4cd2081f76b72b06",
    "git_blob": "133100a0c1efcd7fd29e32a5d4ab750ffaf87f3c",
    "sha256": "e08299fa574f7fb65a98a1f7ff930964aa2892304d67031f1373804cd1940e76",
    "limitation": "The non-golden branch compares cpu_out with itself at line 377; it does not validate hardware. The MLADF BFP GEMM golden fixture directory is external and absent from the public tree.",
}


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def require(value, message):
    if not value:
        raise ValueError(message)


def bf16(values, np, half_away=False):
    values = np.asarray(values, dtype=np.float32)
    require(np.isfinite(values).all(), "Finite BF16 candidate required")
    bits = values.view(np.uint32)
    rounded = bits + np.uint32(0x8000) if half_away else bits + np.uint32(0x7fff) + ((bits >> 16) & 1)
    return (rounded & np.uint32(0xffff0000)).view(np.float32)


def unpack_nibbles(values, np):
    result = np.empty((*values.shape[:-1], values.shape[-1] * 2), dtype=np.int16)
    result[..., 0::2] = values & 15
    result[..., 1::2] = values >> 4
    return result


def decode_packed(payload, k, n, np):
    """Invert the pinned SDK's group32/ni2/32-column BFP weight formatter."""
    padded_k, padded_n = (2560, 2560) if (k, n) == (2560, 1280) else (768, 3072)
    blocks = padded_k // 32
    # g32 stores two bias/padding entries, followed by 640-byte tiles.
    tiles = payload.reshape(padded_n // 64, blocks + 2, 2, 640)
    require(not tiles[:, :2].any(), "Expected zero bias/padding entries")
    tiles = tiles[:, 2:]
    quantized = unpack_nibbles(tiles[..., :512], np)
    quantized = quantized.reshape(padded_n // 64, blocks, 2, 4, 32, 8)
    quantized = quantized.transpose(1, 4, 0, 2, 3, 5).reshape(padded_k, padded_n)
    zero_padded = unpack_nibbles(tiles[..., 512:576], np)
    require(not zero_padded[..., 32:].any(), "Expected zero nibble alignment padding")
    zeros = zero_padded[..., :32].transpose(1, 0, 2, 3).reshape(blocks, padded_n)
    scale_words = np.ascontiguousarray(tiles[..., 576:640]).view("<u2")
    scales = (scale_words.astype(np.uint32) << 16).view(np.float32)
    scales = scales.transpose(1, 0, 2, 3).reshape(blocks, padded_n)
    rows = ((quantized.reshape(blocks, 32, padded_n) - zeros[:, None, :]) * scales[:, None, :]).reshape(padded_k, padded_n).T[:n, :k]
    return np.ascontiguousarray(bf16(rows, np))


def bfp_half_away(values, axis, carry, np):
    """Public cast clamp or installed f2bfp signed-overflow carry, ebs8."""
    moved = np.moveaxis(np.asarray(values, dtype=np.float32), axis, -1)
    shape = moved.shape
    require(shape[-1] % 8 == 0 and np.isfinite(moved).all(), "Finite ebs8 blocks required")
    blocks = np.ascontiguousarray(moved).reshape(*shape[:-1], shape[-1] // 8, 8)
    exponent = ((blocks.view(np.uint32) >> 23) & 255).max(axis=-1, keepdims=True)
    step = np.exp2(exponent.astype(np.int32) - 127 - 6).astype(np.float32)

    def rounded(step_value):
        scaled = blocks / step_value
        return np.sign(scaled) * np.floor(np.abs(scaled) + np.float32(.5))

    mantissa = rounded(step)
    if carry:
        # f2bfp defaults m2_0_rnd=true: test signed mantissa >127.
        step = step * np.where(np.any(mantissa > 127, axis=-1, keepdims=True), np.float32(2), np.float32(1))
        result = rounded(step) * step
    else:
        result = np.clip(mantissa, -128, 127) * step
    return np.ascontiguousarray(np.moveaxis(result.reshape(shape), -1, axis))


def dot(rows, x, np):
    return np.asarray([np.dot(row.astype(np.float64), x.astype(np.float64)) for row in rows], dtype=np.float32)


def comparison(actual, expected, np):
    a, b = actual.astype(np.float64), expected.astype(np.float64)
    error = a - b
    permitted = .003 + .03 * np.abs(b)
    return dict(exact_elements=int(np.count_nonzero(actual == expected)), elements=int(a.size),
                relative_l2_error=float(np.linalg.norm(error) / np.linalg.norm(b)),
                max_abs_error=float(np.abs(error).max()),
                violating_elements=int(np.count_nonzero(np.abs(error) > permitted)),
                passed=bool(np.isfinite(a).all() and np.all(np.abs(error) <= permitted)))


def run(args):
    require(not args.report.exists() and args.report.parent == WORK, "Fresh bounded diagnostic report required")
    require(sha(Path(__file__)) == args.expected_source_sha256, "Reviewed diagnostic source changed")
    started = time.perf_counter()
    for path, expected in PINS.items():
        require(sha(path) == expected, "Pinned receipt/SDK source changed: " + str(path))
    prep = json.loads(PREPARATION.read_text(encoding="utf-8"))
    admission = json.loads(ADMISSION.read_text(encoding="utf-8"))
    require(prep["passed"] and prep["reference_contract_version"] == "affine_bf16_scale_and_dequant_rne_v2", "Corrected preparation required")
    require(prep["tolerance"] == {"rtol": .03, "atol": .003}, "Frozen gate changed")
    import numpy as np
    result = dict(schema="halogen_dd_real_bfp_reference_diagnosis_v1", source_sha256=args.expected_source_sha256,
                  scope=__doc__, public_cast_reference=PUBLIC_CAST_REFERENCE,
                  input_file_pins={str(p): v for p, v in PINS.items()}, rows=[],
                  accepted_reference_contract_changed=False, tolerance=prep["tolerance"],
                  full_mtp_proven=False, acceptance_qualified=False, speed_gain_established=False)
    for fc in prep["fixtures"]:
        packed = Path(fc["path"])
        require(sha(packed) == prep["file_pins"][str(packed)], "Packed fixture changed")
        result["input_file_pins"][str(packed)] = sha(packed)
        payload = np.fromfile(packed, dtype=np.uint8)
        require(payload.nbytes == fc["bytes"], "Packed extent changed")
        weights = decode_packed(payload, fc["k"], fc["n"], np)
        for case in fc["cases"]:
            for key in ("input_path", "affine_reference_path"):
                path = Path(case[key])
                require(sha(path) == prep["file_pins"][str(path)], "Saved fixture changed")
                result["input_file_pins"][str(path)] = sha(path)
            x = (np.load(case["input_path"], allow_pickle=False).astype(np.uint32) << 16).view(np.float32)
            existing = np.load(case["affine_reference_path"], allow_pickle=False)
            decoded = dot(weights, x, np)
            require(np.array_equal(decoded, existing), "Independent packed decoder differs from corrected CPU reference")
            native = next(row for row in admission["calls"] if row["fc_index"] == fc["index"] and row["call"] == case["call"])
            output = Path(native["output_path"])
            require(sha(output) == native["output_sha256"], "Retained native output changed")
            result["input_file_pins"][str(output)] = sha(output)
            words = np.fromfile(output, dtype="<u2")
            actual = (words.astype(np.uint32) << 16).view(np.float32)
            row = dict(fc_index=fc["index"], call=case["call"], packed_decoder_exact_reference=True,
                       corrected_affine_comparison=comparison(actual, existing, np), candidates=[])
            for carry in (False, True):
                qx = bfp_half_away(x, -1, carry, np)
                for axis, rationale in ((-1, "K reduction axis, matching the previous separate BF16-GEMM numerical diagnosis"),
                                        (0, "N groups match consecutive ebs8 values in the pinned packed INT4 tile layout")):
                    qw = bfp_half_away(weights, axis, carry, np)
                    value = dot(qw, qx, np)
                    for output_ties_away in (False, True):
                        reference = bf16(value, np, output_ties_away)
                        candidate_words = (reference.view(np.uint32) >> 16).astype("<u2")
                        row["candidates"].append(dict(cast="installed_f2bfp_signed_overflow_carry" if carry else "public_cast_signed_clamp",
                            exponent_group=8, weight_axis="K" if axis == -1 else "N", layout_rationale=rationale,
                            output_rounding="BF16 nearest ties away (prior separate observed formula)" if output_ties_away else "BF16 nearest even (documented CPU golden)",
                            accumulation="FP64 dot then FP32; installed accumulation remains unproven",
                            output_sha256=hashlib.sha256(candidate_words.tobytes()).hexdigest(),
                            comparison=comparison(actual, reference, np)))
            result["rows"].append(row)
        del payload, weights
    result["exact_candidate_keys"] = []
    for index in range(8):
        if all(row["candidates"][index]["comparison"]["exact_elements"] == row["candidates"][index]["comparison"]["elements"] for row in result["rows"]):
            result["exact_candidate_keys"].append({key: result["rows"][0]["candidates"][index][key] for key in ("cast", "weight_axis", "output_rounding")})
    result["exact_executed_formula_established"] = bool(result["exact_candidate_keys"])
    result["host_seconds"] = time.perf_counter() - started
    with args.report.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({key: result[key] for key in ("exact_candidate_keys", "exact_executed_formula_established", "host_seconds")}, indent=2))
    for row in result["rows"]:
        best = max(row["candidates"], key=lambda value: value["comparison"]["exact_elements"])
        print(row["fc_index"], row["call"], best["cast"], best["weight_axis"], best["output_rounding"], best["comparison"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-source-sha256", required=True)
    parser.add_argument("--report", type=Path, required=True)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
