"""Bounded, offline Q8 hidden-FC arithmetic diagnosis.

Scalar operations use exact integer dyadics and IEEE round-to-nearest-even.
The recovered M4 shader schedule is 16 lanes, eight dot2 instructions per
16-value block, ten block additions per lane, then XOR 8/4/2/1 reduction.
The three explicit dot2 rounding models are hypotheses: documentation's
pseudocode alone does not prove the instruction's internal rounding.

The optional NumPy path converts a <=49-bit affine numerator exactly to FP64
and then casts once to FP32. BF16 products are exact in FP64 (<=16 significant
bits, exponents within binary64 normal range). Error-free TwoSum detects any
inexact FP64 addition; those dot2 operations use scalar integer fallback.
No runtime provider, checkpoint, engine, GPU, or NPU code is imported.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import time


MODELS = ("fused", "sequential", "pair_then_acc")
CPU_TOLERANCE = {"rtol": 0.002, "atol": 0.0002}
NPU_TOLERANCE = {"rtol": 0.03, "atol": 0.003}
WIDTH = ROWS = 2560
STREAMS = 4
RAW_BYTES = ROWS * (WIDTH + WIDTH // 16)


def _check_word(word, bits):
    if type(word) is not int or not 0 <= word < (1 << bits):
        raise ValueError(f"requires unsigned {bits}-bit word")


def _dyadic(word, fraction_bits, exponent_bits, bias):
    _check_word(word, fraction_bits + exponent_bits + 1)
    fraction = word & ((1 << fraction_bits) - 1)
    exponent = (word >> fraction_bits) & ((1 << exponent_bits) - 1)
    if exponent == (1 << exponent_bits) - 1:
        raise ValueError("nonfinite arithmetic input")
    coefficient = fraction if exponent == 0 else (1 << fraction_bits) | fraction
    power = (1 - bias if exponent == 0 else exponent - bias) - fraction_bits
    if word >> (fraction_bits + exponent_bits):
        coefficient = -coefficient
    return coefficient, power


def _sum_dyadics(terms):
    terms = [(n, p) for n, p in terms if n]
    if not terms:
        return 0, 0
    power = min(p for _, p in terms)
    return sum(n << (p - power) for n, p in terms), power


def _round_terms_f32(terms, negative_signs):
    n, power = _sum_dyadics(terms)
    if not n and all(not coefficient for coefficient, _ in terms) and all(negative_signs):
        return 0x80000000
    return round_dyadic_to_f32(n, power)


def _rne_shift(n, shift):
    if shift <= 0:
        return n << -shift
    quotient, remainder = divmod(n, 1 << shift)
    half = 1 << (shift - 1)
    return quotient + (remainder > half or (remainder == half and quotient & 1))


def round_dyadic_to_f32(n, power):
    """Correctly round n*2**power, including gradual FP32 underflow."""
    if type(n) is not int or type(power) is not int:
        raise ValueError("dyadic coefficient and power must be integers")
    if not n:
        return 0
    sign = 0x80000000 if n < 0 else 0
    n = abs(n)
    top_power = n.bit_length() - 1 + power
    if top_power < -126:
        mantissa = _rne_shift(n, -149 - power)
        return sign | mantissa  # carry naturally reaches minimum normal.
    shift = n.bit_length() - 24
    mantissa = _rne_shift(n, shift)
    if mantissa >= (1 << 24):
        mantissa >>= 1
        shift += 1
    exponent = power + shift + 23 + 127
    if exponent >= 255:
        raise ValueError("nonfinite FP32 arithmetic result")
    return sign | (exponent << 23) | (mantissa - (1 << 23))


def fp16_to_f32_bits(word):
    n, power = _dyadic(word, 10, 5, 15)
    return round_dyadic_to_f32(n, power) if n else ((word & 0x8000) << 16)


def f32_to_bf16_rne(word):
    _dyadic(word, 23, 8, 127)  # Reject nonfinite input, do not canonicalize it.
    return ((word + 0x7FFF + ((word >> 16) & 1)) >> 16) & 0xFFFF


def bits_to_float(word):
    return struct.unpack("<f", struct.pack("<I", word))[0]


def add_f32_bits(a, b):
    terms = [_dyadic(a, 23, 8, 127), _dyadic(b, 23, 8, 127)]
    n, power = _sum_dyadics(terms)
    if not n and a == b == 0x80000000:
        return 0x80000000
    return round_dyadic_to_f32(n, power)


def fma_f32_bits(a, b, c):
    an, ap = _dyadic(a, 23, 8, 127)
    bn, bp = _dyadic(b, 23, 8, 127)
    cn, cp = _dyadic(c, 23, 8, 127)
    n, power = _sum_dyadics([(an * bn, ap + bp), (cn, cp)])
    if not n and not an * bn and not cn and ((a ^ b) & c & 0x80000000):
        return 0x80000000
    return round_dyadic_to_f32(n, power)


def affine_f32_bits(code, scale_fp16, bias_fp16):
    """FP32 affine FMA from unsigned code and original finite FP16 pair."""
    _check_word(code, 8)
    scale, sp = _dyadic(scale_fp16, 10, 5, 15)
    bias, bp = _dyadic(bias_fp16, 10, 5, 15)
    n, power = _sum_dyadics([(code * scale, sp), (bias, bp)])
    if not n and not code * scale and not bias and scale_fp16 & bias_fp16 & 0x8000:
        return 0x80000000
    return round_dyadic_to_f32(n, power)


def decode_q8_row(payload, width=WIDTH):
    if type(width) is not int or width <= 0 or width % 64:
        raise ValueError("Q8 row width must be positive and divisible by 64")
    if len(payload) != width + width // 16:
        raise ValueError("Q8 row byte extent mismatch")
    affine = struct.unpack("<" + "H" * (width // 32), payload[width:])
    result = []
    for group in range(width // 64):
        scale, bias = affine[group * 2:group * 2 + 2]
        result.extend(f32_to_bf16_rne(affine_f32_bits(code, scale, bias))
                      for code in payload[group * 64:(group + 1) * 64])
    return result


def dot2_f32_bits(a0, b0, a1, b1, accumulator, model="fused"):
    if model not in MODELS:
        raise ValueError("unknown dot2 rounding model")
    a0n, a0p = _dyadic(a0, 7, 8, 127)
    b0n, b0p = _dyadic(b0, 7, 8, 127)
    a1n, a1p = _dyadic(a1, 7, 8, 127)
    b1n, b1p = _dyadic(b1, 7, 8, 127)
    an, ap = _dyadic(accumulator, 23, 8, 127)
    products = [(a0n * b0n, a0p + b0p), (a1n * b1n, a1p + b1p)]
    signs = [bool((a0 ^ b0) & 0x8000), bool((a1 ^ b1) & 0x8000)]
    if model == "fused":
        return _round_terms_f32(products + [(an, ap)], signs + [bool(accumulator & 0x80000000)])
    if model == "sequential":
        first = _round_terms_f32([products[0], (an, ap)], [signs[0], bool(accumulator & 0x80000000)])
        return _round_terms_f32([products[1], _dyadic(first, 23, 8, 127)],
                                [signs[1], bool(first & 0x80000000)])
    pair = _round_terms_f32(products, signs)
    return add_f32_bits(accumulator, pair)


def xor_reduce_f32(lanes):
    if len(lanes) != 16:
        raise ValueError("original shader requires 16 reduction lanes")
    lanes = list(lanes)
    for distance in (8, 4, 2, 1):
        previous = lanes
        lanes = [add_f32_bits(previous[lane], previous[lane ^ distance])
                 for lane in range(16)]
    return lanes[0]


def project_row_fp32(weights, inputs, model="fused"):
    """Original shader's block/lane order; return the final FP32 word."""
    if len(weights) != len(inputs) or not weights or len(weights) % 256:
        raise ValueError("original schedule width must be divisible by 256")
    for word in list(weights) + list(inputs):
        _dyadic(word, 7, 8, 127)
    lanes = [0] * 16
    for iteration in range(len(weights) // 256):
        for lane in range(16):
            start = iteration * 256 + lane * 16
            block = 0
            for pair in range(8):
                k = start + pair * 2
                block = dot2_f32_bits(weights[k], inputs[k], weights[k + 1],
                                       inputs[k + 1], block, model=model)
            lanes[lane] = add_f32_bits(lanes[lane], block)
    return xor_reduce_f32(lanes)


def decode_q8_numpy(payload, width=WIDTH, rows=ROWS):
    """Exact vectorized finite u8/FP16 affine, then FP32 and BF16 RNE."""
    import numpy as np
    if type(width) is not int or width <= 0 or width % 64 or type(rows) is not int or rows <= 0:
        raise ValueError("invalid Q8 matrix geometry")
    if len(payload) != rows * (width + width // 16) or len(payload) > RAW_BYTES:
        raise ValueError("Q8 matrix extent mismatch or exceeds hidden-matrix bound")
    raw = np.frombuffer(payload, dtype=np.uint8).reshape(rows, width + width // 16)
    codes = raw[:, :width].reshape(rows, width // 64, 64).astype(np.int64)
    pairs = raw[:, width:].copy().view("<u2").reshape(rows, width // 64, 2)
    if np.any(((pairs >> 10) & 31) == 31):
        raise ValueError("nonfinite FP16 affine input")
    exponent = ((pairs >> 10) & 31).astype(np.int64)
    mantissa = (pairs & 1023).astype(np.int64) + np.where(exponent != 0, 1024, 0)
    # Every FP16 is an integer multiple of 2^-24; maximum numerator is <2^40.
    fixed = mantissa << np.maximum(exponent - 1, 0)
    fixed = np.where(pairs & 0x8000, -fixed, fixed)
    numerator = codes * fixed[..., 0, None] + fixed[..., 1, None]
    # |numerator| <= 256*65504*2^24 < 2^49, exactly representable in binary64.
    rounded = (numerator.astype(np.float64) * (2.0 ** -24)).astype(np.float32)
    bits = rounded.view(np.uint32)
    words = ((bits + np.uint32(0x7FFF) + ((bits >> 16) & 1)) >> 16).astype(np.uint16)
    # Preserve the affine -0 case, which an integer coefficient cannot encode.
    negative_zero = (numerator == 0) & ((codes == 0) | (fixed[..., 0, None] == 0))
    negative_zero &= ((pairs[..., 0, None] & pairs[..., 1, None] & 0x8000) != 0)
    words[negative_zero] = 0x8000
    return words.reshape(rows, width)


def _two_sum_numpy(a, b):
    """Return rounded FP64 sum and its exact residual (no under/overflow)."""
    total = a + b
    virtual_b = total - a
    residual = (a - (total - virtual_b)) + (b - virtual_b)
    return total, residual


def _dot2_numpy(a0, b0, a1, b1, accumulator, model):
    import numpy as np
    arrays = np.broadcast_arrays(a0, b0, a1, b1)
    floats = [(word.astype(np.uint32) << 16).view(np.float32).astype(np.float64)
              for word in arrays]
    p0, p1 = floats[0] * floats[1], floats[2] * floats[3]
    acc64 = accumulator.astype(np.float64)
    if model == "fused":
        pair, error0 = _two_sum_numpy(p0, p1)
        total, error1 = _two_sum_numpy(pair, acc64)
    elif model == "sequential":
        first, error0 = _two_sum_numpy(p0, acc64)
        first = first.astype(np.float32)
        total, error1 = _two_sum_numpy(first.astype(np.float64), p1)
    else:
        pair, error0 = _two_sum_numpy(p0, p1)
        pair = pair.astype(np.float32)
        total, error1 = _two_sum_numpy(pair.astype(np.float64), acc64)
    fallback = np.flatnonzero((error0 != 0) | (error1 != 0))
    rounded = total.astype(np.float32)
    bits = rounded.view(np.uint32)
    acc_bits = accumulator.view(np.uint32)
    for index in fallback:
        bits.flat[index] = dot2_f32_bits(*(int(word.flat[index]) for word in arrays),
                                        int(acc_bits.flat[index]), model=model)
    if not np.isfinite(rounded).all():
        raise ValueError("nonfinite FP32 dot2 arithmetic result")
    return rounded, int(fallback.size)


def project_numpy(weights, inputs, model="fused"):
    """Exact TwoSum-checked implementation of the scalar original schedule."""
    import numpy as np
    if model not in MODELS:
        raise ValueError("unknown dot2 rounding model")
    if (weights.ndim != 2 or inputs.ndim != 2 or weights.shape[1] != inputs.shape[1]
            or not weights.shape[0] or not inputs.shape[0] or not weights.shape[1]
            or weights.shape[1] % 256 or weights.size > ROWS * WIDTH or inputs.size > STREAMS * WIDTH):
        raise ValueError("bounded projection requires 2D BF16 matrices and K divisible by 256")
    rows, width = weights.shape
    streams = inputs.shape[0]
    if weights.dtype != np.uint16 or inputs.dtype != np.uint16:
        raise ValueError("requires unsigned BF16 storage words")
    if np.any((weights & 0x7F80) == 0x7F80) or np.any((inputs & 0x7F80) == 0x7F80):
        raise ValueError("nonfinite BF16 input")
    lanes = np.zeros((streams, rows, 16), dtype=np.float32)
    fallback_count = 0
    for iteration in range(width // 256):
        block = np.zeros_like(lanes)
        for pair in range(8):
            k0 = iteration * 256 + np.arange(16) * 16 + pair * 2
            block, count = _dot2_numpy(weights[None, :, k0], inputs[:, None, k0],
                                       weights[None, :, k0 + 1], inputs[:, None, k0 + 1], block, model)
            fallback_count += count
        lanes = np.add(lanes, block, dtype=np.float32)
    for distance in (8, 4, 2, 1):
        lanes = np.add(lanes, lanes[..., np.arange(16) ^ distance], dtype=np.float32)
    if not np.isfinite(lanes).all():
        raise ValueError("nonfinite FP32 lane/reduction result")
    bits = lanes[..., 0].copy().view(np.uint32)
    words = ((bits + np.uint32(0x7FFF) + ((bits >> 16) & 1)) >> 16).astype(np.uint16)
    return bits, words, {"exact_integer_fallback_dot2_count": fallback_count,
                         "dot2_count": streams * rows * width // 2,
                         "nonzero_input_subnormals": int(np.count_nonzero(((inputs & 0x7F80) == 0) & ((inputs & 0x007F) != 0))),
                         "nonzero_weight_subnormals": int(np.count_nonzero(((weights & 0x7F80) == 0) & ((weights & 0x007F) != 0)))}


def comparison(actual, oracle):
    import numpy as np
    a = (actual.astype(np.uint32) << 16).view(np.float32)
    b = (oracle.astype(np.uint32) << 16).view(np.float32)
    difference = np.abs(a.astype(np.float64) - b.astype(np.float64))
    mismatch = np.flatnonzero(actual.ravel() != oracle.ravel())
    result = {"elements": int(actual.size), "exact_BF16_word_mismatches": int(mismatch.size),
              "max_abs_error": float(difference.max())}
    for name, tolerance in (("cpu", CPU_TOLERANCE), ("npu", NPU_TOLERANCE)):
        failed = difference > tolerance["atol"] + tolerance["rtol"] * np.abs(b.astype(np.float64))
        result[name + "_frozen_screen"] = {"tolerance": tolerance, "passed": not bool(failed.any()),
                                          "out_of_tolerance_elements": int(failed.sum())}
    result["mismatches"] = [{"index": int(i), "stream": int(i // ROWS), "output": int(i % ROWS),
                              "actual_word": f"0x{int(actual.flat[i]):04x}",
                              "oracle_word": f"0x{int(oracle.flat[i]):04x}"}
                             for i in mismatch[:32]]
    return result


def _read_exact(path, size):
    if path.stat().st_size != size:
        raise ValueError(f"unexpected bounded fixture extent: {path}")
    payload = path.read_bytes()
    return payload, hashlib.sha256(payload).hexdigest()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixtures", type=Path, required=True)
    parser.add_argument("--oracle-dir", type=Path, required=True)
    parser.add_argument("--cpu-report", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--models", nargs="+", choices=MODELS, default=list(MODELS))
    args = parser.parse_args(argv)
    if args.out.exists():
        raise FileExistsError("existing report refused")
    import numpy as np
    manifest_path = args.fixtures / "fixtures.json"
    if manifest_path.stat().st_size > 1024 * 1024:
        raise ValueError("fixture manifest exceeds 1 MiB bound")
    manifest_payload, manifest_hash = _read_exact(manifest_path, manifest_path.stat().st_size)
    manifest = json.loads(manifest_payload)
    payload, weight_hash = _read_exact(args.fixtures / "h-weight.q8g64", RAW_BYTES)
    weight_entry = manifest["raw_weights"]["h"]
    if (weight_entry["sha256"] != weight_hash or weight_entry["bytes"] != RAW_BYTES
            or weight_entry["entry"]["dims"] != [ROWS, WIDTH]
            or (weight_entry["entry"]["store"], weight_entry["entry"]["variant"]) != (7, 0)):
        raise ValueError("extracted hidden weights do not match fixture manifest")
    weights = decode_q8_numpy(payload)
    replay_path = args.oracle_dir / "replay.json"
    if replay_path.stat().st_size > 1024 * 1024:
        raise ValueError("native replay manifest exceeds 1 MiB bound")
    _, replay_hash = _read_exact(replay_path, replay_path.stat().st_size)
    report = {"schema": "halogen_native_q8_hidden_offline_numeric.v1",
              "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "scope": "bounded offline hidden-FC arithmetic diagnosis; no hardware or engine changes",
              "schedule": {"lanes": 16, "values_per_block": 16, "dot2_per_block": 8,
                           "iterations": 10, "block_accumulator_reset": True,
                           "lane_add_is_separate_fp32": True, "xor_reduction": [8, 4, 2, 1]},
              "dot2_instruction_rounding_proved": False,
              "native_bit_parity_qualified": False,
              "gpu_or_npu_executed": False,
              "npu_hardware_screen_run": False,
              "dot2_models": {"fused": "RN32(exact p0+p1+acc)",
                              "sequential": "RN32(RN32(exact acc+p0)+p1)",
                              "pair_then_acc": "RN32(acc+RN32(exact p0+p1))"},
              "scalar_arithmetic": "exact integer dyadics; FP32/BF16 RNE, gradual underflow, finite operands",
              "vector_arithmetic_proof": "BF16 products have <=16 significant bits and exponents within FP64 normal range; TwoSum identifies every inexact FP64 addition and falls back to scalar integer dot2; standalone FP32 additions preserve recovered lane/reduction rounding",
              "shader_schedule_source": {"symbol": "_ZN7halogen12_GLOBAL__N_16k_lq8wILi4ELi16ELi1EEEvPKhPKtPtll",
                                         "retained_code_object_sha256": "45941c0579dc3487d07978a50c85cbaa141bbb674b225e708e82d81397334a83",
                                         "recovered_by": "CPU-only llvm-objdump disassembly of existing engine-gfx1151.hsaco"},
              "frozen_tolerances": {"cpu": CPU_TOLERANCE, "npu": NPU_TOLERANCE},
              "fixture_manifest_sha256": manifest_hash,
              "native_replay_manifest_sha256": replay_hash,
              "weight_sha256": weight_hash,
              "decoder": "exact u8*FP16+FP16 affine; one FP32 RNE then BF16 RNE",
              "affine_multiply_exact_reason": "u8 <=8 and FP16 <=11 significant bits; product <=19 bits fits FP32",
              "input_contract": "unchanged original whole-row RMS10240 BF16 reshaped [4,2560]",
              "cases": {}}
    cpu = None
    if args.cpu_report:
        if args.cpu_report.stat().st_size > 12 * 1024 * 1024:
            raise ValueError("CPU report exceeds bounded 12 MiB extent")
        cpu_payload, cpu_hash = _read_exact(args.cpu_report, args.cpu_report.stat().st_size)
        cpu = json.loads(cpu_payload)
        if cpu["tolerance"] != CPU_TOLERANCE:
            raise ValueError("retained CPU report does not use frozen strict CPU tolerance")
        report["cpu_report_sha256"] = cpu_hash
    for case in ("A", "B"):
        inp, input_hash = _read_exact(args.fixtures / f"{case}-h-norm.u16", STREAMS * WIDTH * 2)
        oracle_payload, oracle_hash = _read_exact(args.oracle_dir / f"{case}-hidden-fc-u16.bin", STREAMS * ROWS * 2)
        inputs = np.frombuffer(inp, dtype="<u2").reshape(STREAMS, WIDTH)
        if manifest["inputs"][case]["h"]["sha256"] != input_hash:
            raise ValueError("hidden input does not match fixture manifest")
        oracle = np.frombuffer(oracle_payload, dtype="<u2").reshape(STREAMS, ROWS)
        case_report = {"input_sha256": input_hash, "oracle_sha256": oracle_hash, "models": {}}
        for model in args.models:
            started = time.perf_counter()
            bits, words, bounds = project_numpy(weights, inputs, model=model)
            for index in (1729, 7029):
                stream, row = divmod(index, ROWS)
                stride = WIDTH + WIDTH // 16
                scalar_weights = decode_q8_row(payload[row * stride:(row + 1) * stride])
                if scalar_weights != weights[row].tolist():
                    raise AssertionError("vector affine decoder differs from exact integer scalar")
                scalar_bits = project_row_fp32(scalar_weights, inputs[stream].tolist(), model=model)
                if scalar_bits != int(bits.flat[index]):
                    raise AssertionError("vector schedule differs from exact integer scalar")
            case_report["models"][model] = {"comparison": comparison(words, oracle), "arithmetic_checks": bounds,
                                            "elapsed_seconds": round(time.perf_counter() - started, 3),
                                            "focused_scalar_integer_checks_passed": True,
                                            "output_fp32_sha256": hashlib.sha256(bits.astype("<u4").tobytes()).hexdigest(),
                                            "output_bf16_sha256": hashlib.sha256(words.astype("<u2").tobytes()).hexdigest(),
                                            "focused_values": [{"index": i, "fp32_word": f"0x{int(bits.flat[i]):08x}",
                                                                "fp32": bits_to_float(int(bits.flat[i])),
                                                                "bf16_word": f"0x{int(words.flat[i]):04x}",
                                                                "oracle_word": f"0x{int(oracle.flat[i]):04x}"}
                                                               for i in (1729, 7029)]}
        if cpu:
            call = next(c for c in cpu["calls"] if c["input_set"] == case)
            actual = np.asarray(call["outputs"]["h_projection"]["actual_output"], dtype=np.float32)
            cpu_words = (actual.view(np.uint32) >> 16).astype(np.uint16)
            case_report["retained_cpu_comparison"] = comparison(cpu_words, oracle)
            case_report["retained_cpu_focused_values"] = [{"index": i, "value": float(actual.flat[i]),
                                                          "bf16_word": f"0x{int(cpu_words.flat[i]):04x}"}
                                                         for i in (1729, 7029)]
        report["cases"][case] = case_report
        print(f"{case}: " + ", ".join(f"{m}={r['comparison']['exact_BF16_word_mismatches']} BF16 mismatches"
                                      for m, r in case_report["models"].items()), flush=True)
    report["diagnosis"] = {
        "all_evaluated_models_match_all_retained_oracle_BF16_words": all(
            model["comparison"]["exact_BF16_word_mismatches"] == 0
            for case in report["cases"].values() for model in case["models"].values()),
        "retained_oracle_cannot_distinguish_dot2_internal_rounding": len(args.models) > 1 and all(
            model["comparison"]["exact_BF16_word_mismatches"] == 0
            for case in report["cases"].values() for model in case["models"].values()),
        "limitation": "Agreement is limited to retained A/B BF16 outputs; instruction semantics and NPU execution remain unqualified"}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")
    print(str(args.out), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
