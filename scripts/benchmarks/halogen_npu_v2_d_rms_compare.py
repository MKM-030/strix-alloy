"""Compare one matched native D hidden RMS capture with two frozen CPU references.

Root alone runs this CPU-only tool and reads real assets/capture payloads. No
NPU/engine is initialized, no graph is modified, no parameters are fitted and
no tolerance is used. The existing diagnostic graph must reproduce retained
ORT and NumPy h_norm hashes for both fixed A/B feeds before comparison.

Installed ORT CPU kernel source was not found locally. A deterministic CPU
sum/reciprocal recipe cannot be claimed as native arithmetic from that absence.
This tool compares the existing implementations rather than inventing one.
"""
import argparse
import gc
import hashlib
import json
import os
from pathlib import Path
import stat
import sys


ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
FOLDER = Path(r"C:\AI\halogen-mtp-npu\v2-d-prepare-20261004")
MODEL = FOLDER / "d-prepare.onnx"
BUILD = FOLDER / "d-prepare.onnx.json"
BUILD_SHA256 = "06bba1a8bb9658047ce12292becf7bbee9d639498a345aaf3019af4540bcfd99"
MODEL_SHA256 = "3dd6940b38d788643b709837959d36ab16d1b926e548121b6f6efcc554147518"
DIAGNOSTIC = FOLDER / "d-prepare-diagnostic.onnx"
DIAGNOSTIC_SHA256 = "6e0e12647c38644f1c66e6a55002e0d22c862c07f143cfefa393fbcd5fff64ec"
FIXTURE = FOLDER / "input-fixture.json"
FIXTURE_SHA256 = "0dcd96bca2c858709a053356a85bbf4fe850c2959a5a913a7f7b26537292daa2"
BOUNDARY = ROOT / "server/.local/optimization9h-20261004/d-prepare-boundary-diagnostic.json"
BOUNDARY_SHA256 = "68ab8fe6124a01e63ef970df9804b2eb90333b3606742b03ade294db46d4802b"
BUILDER_SHA256 = "6334b32fc8a9a5cb792590d0422c0ee1fb532a7c475785f75979962ec80c2544"
PROBE_SHA256 = "f5214bfc4c4a24ccfec7a708fcd90b919d05c1f0dfa8bf79eaa3bab6b5cf18a3"
DIAGNOSTIC_SOURCE = ROOT / "server/.local/optimization9h-20261004/d-prepare-cpu-boundary-diagnostic.py"
DIAGNOSTIC_SOURCE_SHA256 = "e7829b3621c2434d4c724ad5a005225e822d62aa266d2832b62486180d632fa1"
ENGINE_SHA256 = "ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b"
FUNCTION_SHA256 = "132f2da76d86694ffe5f120d61e304e57c685f3db72935c6d5e61bf7b0d5cc20"
MAX_JSON_BYTES, NORM_BYTES = 2 << 20, 20_480
OUTPUTS = ["seed", "e_norm", "h_norm", "e_projection_fp32", "h_projection_fp32", "e_projection", "h_projection"]


def require_sha(value):
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError("independently supplied lowercase SHA256 required")
    return value


def digest(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for payload in iter(lambda: stream.read(1 << 20), b""):
            value.update(payload)
    return value.hexdigest()


def read_exact(path, size, expected):
    require_sha(expected)
    path = Path(path).resolve(strict=True)
    before = path.stat()
    if not stat.S_ISREG(before.st_mode) or before.st_size != size:
        raise ValueError("raw capture/fixture must be a regular file of the exact extent")
    with path.open("rb") as stream:
        payload = stream.read(size + 1)
    after = path.stat()
    attrs = ("st_size", "st_dev", "st_ino", "st_mtime_ns", "st_ctime_ns")
    if (len(payload) != size or hashlib.sha256(payload).hexdigest() != expected or
            any(getattr(before, key) != getattr(after, key) for key in attrs)):
        raise ValueError("raw capture/fixture hash or file identity differs")
    return payload


def read_json(path, expected):
    path = Path(path).resolve(strict=True)
    size = path.stat().st_size
    if not 0 < size <= MAX_JSON_BYTES:
        raise ValueError("bounded comparison JSON limit exceeded")
    return json.loads(read_exact(path, size, expected))


def array_hash(value):
    return hashlib.sha256(value.tobytes(order="C")).hexdigest()


def words(value, np):
    if value.dtype != np.dtype("float32") or value.shape != (1, 10240) or not np.isfinite(value).all():
        raise ValueError("RMS reference must be finite FLOAT[1,10240]")
    bits = np.ascontiguousarray(value).view(np.uint32)
    if np.any(bits & 0xffff):
        raise ValueError("RMS reference is not exactly on the BF16 lattice")
    return (bits >> 16).astype("<u2")


def compare(left, right, np):
    lwords, rwords = words(left, np), words(right, np)
    different = lwords != rwords
    indices = np.flatnonzero(different)[:16]
    return dict(elements=10240, exact_bf16_word_mismatches=int(different.sum()),
                exact_match=not bool(different.any()), max_abs_error=float(np.max(np.abs(left - right))),
                left_fp32_sha256=array_hash(left), right_fp32_sha256=array_hash(right),
                left_u16_sha256=array_hash(lwords), right_u16_sha256=array_hash(rwords),
                examples=[dict(index=int(index), stream=int(index // 2560), feature=int(index % 2560),
                left_word=f"0x{int(lwords.flat[index]):04x}", right_word=f"0x{int(rwords.flat[index]):04x}",
                left=float(left.flat[index]), right=float(right.flat[index])) for index in indices])


def capture(directory, records_sha256, complete_sha256, fixture, raw_gamma, np, builder):
    directory = Path(directory).resolve(strict=True)
    records_path, complete_path = directory / "records.json", directory / "complete.json"
    records = read_json(records_path, records_sha256)
    complete = read_json(complete_path, complete_sha256)
    if (records.get("schema") != 1 or records.get("mode") != "rms1-v1" or
            records.get("engine_sha256") != ENGINE_SHA256 or records.get("function_sha256") != FUNCTION_SHA256 or
            records.get("tensor_bytes") != NORM_BYTES or records.get("word_format") != "little-endian-bf16-u16" or
            complete.get("schema") != 1 or complete.get("mode") != "rms1-v1" or
            complete.get("passed") is not True or complete.get("captured") is not True or
            complete.get("calls") != 1 or complete.get("error") is not None or
            complete.get("observer_hip_syncs") != 2 or complete.get("observer_hip_copies") != 3 or
            len(records.get("samples", [])) != 1):
        raise ValueError("capture requires passed complete receipt and exactly one rms1-v1 sample")
    sample = records["samples"][0]
    expected = dict(count=1, wire_mode="D", wire_byte_before=68, wire_byte_after=68,
                    kernel_identity_rva="0x18d5160", launch_return_rva="0x17db632", width=10240, groups=1,
                    grid=[1, 1, 1], block=[256, 1, 1], shared_bytes=0, stream="0x0", launch_result=0,
                    captured=True, completed=True, reserved=True, entry_valid=True, launch_result_valid=True,
                    exact_launches=1, nested_forwards=0, observer_hip_syncs=2, observer_hip_copies=3, error=None)
    if any(sample.get(key) != value for key, value in expected.items()):
        raise ValueError("native capture mode/kernel/launch/completion metadata differs")
    if (sample.get("wire_initialized_before") is not True or sample.get("wire_initialized_after") is not True or
            type(sample.get("head_result")) is not int or sample["head_result"] < 0 or
            type(sample.get("position")) is not int or sample["position"] < 0 or
            type(sample.get("token_i32")) is not int or not 0 <= sample["token_i32"] < 248320):
        raise ValueError("native capture explicit D count1 metadata is invalid")
    gamma_words = words(raw_gamma.reshape(1, 10240), np)
    if sample.get("raw_gamma_sha256") != array_hash(gamma_words):
        raise ValueError("native raw gamma differs from sealed asset words")
    payloads = {}
    for name, field in (("000-input-residual-u16.bin", "input_residual_sha256"),
                        ("000-raw-gamma-u16.bin", "raw_gamma_sha256"),
                        ("000-output-hidden-rms-u16.bin", "output_hidden_rms_sha256")):
        payloads[field] = read_exact(directory / name, NORM_BYTES, sample[field])
    input_words = np.frombuffer(payloads["input_residual_sha256"], dtype="<u2")
    output = builder.widen_bf16(np.frombuffer(payloads["output_hidden_rms_sha256"], dtype="<u2")).reshape(1, 10240)
    if payloads["raw_gamma_sha256"] != gamma_words.tobytes():
        raise ValueError("native raw gamma word payload differs")
    return sample, builder.widen_bf16(input_words).reshape(1, 10240), output


def run(args):
    report_path = args.report.resolve()
    if report_path.exists() or not report_path.parent.is_dir():
        raise FileExistsError("comparison report must be exclusive in an existing directory")
    result = dict(schema="halogen_v2_D_hidden_rms_comparison.v1", comparison_completed=False,
                  source_sha256=digest(__file__), arithmetic_fitting=False, tolerance_used=False,
                  wire_mode="D", scope="one matched captured count1 native D hidden RMS row; no whole-D/full-head/acceptance claim",
                  native_general_parity_qualified=False, npu_provider_initialized=False, session_creations=0)
    session = None
    try:
        if any(os.environ.get(name) != "1" for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")):
            raise ValueError("BLAS/OpenMP thread variables must all be1 before Python starts")
        for path, expected in ((HERE / "halogen_npu_v2_d_prepare.py", BUILDER_SHA256),
                               (HERE / "halogen_npu_v2_d_prepare_probe.py", PROBE_SHA256),
                               (DIAGNOSTIC_SOURCE, DIAGNOSTIC_SOURCE_SHA256),
                               (MODEL, MODEL_SHA256), (DIAGNOSTIC, DIAGNOSTIC_SHA256)):
            if digest(path) != expected:
                raise ValueError("frozen source/model identity differs: " + str(path))
        fixture = read_json(FIXTURE, FIXTURE_SHA256)
        boundary = read_json(BOUNDARY, BOUNDARY_SHA256)
        if boundary["original_model_sha256"] != MODEL_SHA256 or boundary["diagnostic_sha256"] != DIAGNOSTIC_SHA256:
            raise ValueError("retained CPU boundary receipt model identity differs")
        sys.path.insert(0, str(HERE))
        import numpy as np
        import onnx
        import onnxruntime as ort
        import halogen_npu_v2_d_prepare as builder
        build, weights = builder.verify_model(MODEL, BUILD, BUILD_SHA256, "D")
        if ort.__version__ != "1.25.2" or np.__version__ != "2.5.3":
            raise ValueError("installed CPU reference runtime versions differ")
        e = builder.widen_bf16(np.frombuffer(read_exact(fixture["embedding_bf16"], 5120, fixture["embedding_bf16_sha256"]), dtype="<u2")).reshape(1, 2560)
        h = builder.widen_bf16(np.frombuffer(read_exact(fixture["residual_bf16"], NORM_BYTES, fixture["residual_bf16_sha256"]), dtype="<u2")).reshape(1, 10240)
        rng = np.random.default_rng(20261004)
        feeds = {"A": dict(e=e, h=h), "B": {name: builder.bf16_rne(rng.normal(0, .5, value.shape).astype(np.float32))
                                             for name, value in dict(e=e, h=h).items()}}
        model = onnx.load(str(DIAGNOSTIC), load_external_data=False)
        if [value.name for value in model.graph.output] != OUTPUTS:
            raise ValueError("diagnostic observable outputs differ")
        sample, native_input, native_output = capture(args.capture, args.records_sha256, args.complete_sha256,
                                                       fixture, weights["gamma_hidden"], np, builder)
        matched_old_input = sample["input_residual_sha256"] == fixture["residual_bf16_sha256"]
        if matched_old_input and not np.array_equal(native_input.view(np.uint32), h.view(np.uint32)):
            raise ValueError("equal native/fixture input hashes have different word payloads")
        options = ort.SessionOptions()
        options.intra_op_num_threads = 1
        options.enable_profiling = True
        options.profile_file_prefix = str(report_path.with_suffix(""))
        session = ort.InferenceSession(str(DIAGNOSTIC), sess_options=options,
                                       providers=["CPUExecutionProvider"], enable_fallback=False)
        result["session_creations"] = 1
        session.disable_fallback()
        retained = {row["label"]: row["differences"]["h_norm"] for row in boundary["rows"]}
        references, baseline_rows = {}, []
        for label, feed in feeds.items():
            actual = dict(zip(OUTPUTS, session.run(OUTPUTS, feed)))["h_norm"]
            expected = builder.rms_bf16(feed["h"], weights["gamma_hidden"])
            words(actual, np)
            words(expected, np)
            if (array_hash(actual) != retained[label]["actual_hash"] or
                    array_hash(expected) != retained[label]["reference_hash"]):
                raise ValueError("retained CPU h_norm hashes were not exactly reproduced: " + label)
            references[label] = dict(ort=actual, numpy=expected)
            baseline_rows.append(dict(label=label, retained_ort_fp32_sha256=array_hash(actual),
                                      retained_numpy_fp32_sha256=array_hash(expected), comparison=compare(actual, expected, np)))
        # A fresh legitimate native row is authoritative. Preserve baseline A/B
        # as integrity checks, then use at most one additional fixed-session call.
        if matched_old_input:
            native_references = references["A"]
            reference_calls = 2
        else:
            current_ort = session.run(["h_norm"], {"e": e, "h": native_input})[0]
            current_numpy = builder.rms_bf16(native_input, weights["gamma_hidden"])
            words(current_ort, np)
            words(current_numpy, np)
            native_references = dict(ort=current_ort, numpy=current_numpy)
            reference_calls = 3
        profile = Path(session.end_profiling())
        events = json.loads(profile.read_text(encoding="utf-8"))
        nodes = [row for row in events if row.get("cat") == "Node"]
        providers = sorted({row.get("args", {}).get("provider", "<missing>") for row in nodes})
        if not nodes or providers != ["CPUExecutionProvider"]:
            raise ValueError("comparison profile did not prove CPU-only reference execution")
        result.update(comparison_completed=True, capture_sample=sample,
                      capture_records_sha256=args.records_sha256, capture_complete_sha256=args.complete_sha256,
                      build_receipt_sha256=BUILD_SHA256, assets_receipt_sha256=build["assets_receipt_sha256"],
                      fixture_sha256=FIXTURE_SHA256, boundary_receipt_sha256=BOUNDARY_SHA256,
                      baseline_reproduction=baseline_rows,
                      captured_input_matches_retained_A=matched_old_input, cpu_reference_calls=reference_calls,
                      native_input_u16_sha256=sample["input_residual_sha256"],
                      current_ort_vs_numpy=compare(native_references["ort"], native_references["numpy"], np),
                      native_vs_numpy=compare(native_output, native_references["numpy"], np),
                      native_vs_retained_ort=compare(native_output, native_references["ort"], np),
                      ort_version=ort.__version__, numpy_version=np.__version__, profile=str(profile),
                      profile_sha256=digest(profile), executed_node_providers=providers)
    except Exception as exc:
        result["error"] = type(exc).__name__ + ": " + str(exc)
    finally:
        session = None
        gc.collect()
        with report_path.open("x", encoding="utf-8") as stream:
            json.dump(result, stream, indent=2, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", type=Path, required=True, help="root-owned records.json/complete.json and exact three u16 files")
    parser.add_argument("--records-sha256", required=True)
    parser.add_argument("--complete-sha256", required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--wire-mode", choices=("D",), required=True)
    args = parser.parse_args(argv)
    require_sha(args.records_sha256)
    require_sha(args.complete_sha256)
    result = run(args)
    print(json.dumps(result, indent=2))
    return 0 if result["comparison_completed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
