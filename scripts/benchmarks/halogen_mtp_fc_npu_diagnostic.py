"""Standalone NPU numerical diagnostic after a sealed, numerical-only CPU miss.

ROOT alone executes this under retained ownership, bounded deadline and22/18-GiB
guards. This never supplies successful CPU/integration admission or a Halogen
output swap. The original probe is unchanged and its pass/tolerance fields remain
its actual standalone NPU results, nested within a unique diagnostic envelope.
Its initial result creation is marked diagnostic BEFORE it can write any report.
Import has no provider/model/child side effects. No per-value correction is made.
"""
import argparse
from collections import Counter
import hashlib
import json
import math
import os
from pathlib import Path
import stat
import struct
import types


HERE = Path(__file__).absolute().parent
PROBE = HERE / "halogen_npu_v2_d_native_projection_probe.py"
PROBE_SHA256 = "7d1f51fd254389906c66b3ce44117fbe889b38b73861d192e4965893f6b0d9b0"
NORMAL_SCHEMA = "halogen_v2_count1_D_native_projection_probe.v1"
NESTED_SCHEMA = "halogen_mtp_fc_standalone_npu_diagnostic_probe.v1"
SCHEMA = "halogen_mtp_fc_standalone_npu_diagnostic.v1"
CPU_TOLERANCE = {"rtol": .002, "atol": .0002}
EXPECTED_ERROR = "RuntimeError: frozen original GPU FC gate failed; both returned projections retained"
SHAPES = {"e_projection": (1, 2560), "h_projection": (4, 2560)}
IDENTITY_KEYS = ("source_sha256", "reference_mode", "model_sha256", "data_sha256",
                 "projection_receipt_sha256", "transformer_sha256", "weight_lineage",
                 "fc_fixtures_sha256", "native_fc_replay_sha256", "oracle_binding",
                 "runtime_input_sets", "dependency_sha256", "probe_dependency_sha256",
                 "required_hardware_partition_outputs")


def sha(value):
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError("independent lowercase SHA256 required")
    return value


def sealed(path, expected, limit):
    path = Path(path)
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or not 0 < before.st_size <= limit:
        raise ValueError("bounded unchanged regular diagnostic input required")
    with path.open("rb") as stream:
        opened = os.fstat(stream.fileno())
        raw = stream.read(limit + 1)
        after = os.fstat(stream.fileno())
    # Match the retained Windows capture contract: path-stat and handle-stat
    # ctime may use different Windows timestamp semantics. Compare their shared
    # birth time across APIs; require ctime stability within each API separately.
    fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns")
    fields += ("st_birthtime_ns",) if os.name == "nt" else ("st_ctime_ns",)
    identity = lambda row: tuple(getattr(row, field, None) for field in fields)
    path_after = path.lstat()
    if (not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1
            or not stat.S_ISREG(path_after.st_mode) or path_after.st_nlink != 1
            or identity(before) != identity(opened) or identity(before) != identity(after)
            or identity(before) != identity(path_after)
            or before.st_ctime_ns != path_after.st_ctime_ns or opened.st_ctime_ns != after.st_ctime_ns
            or len(raw) != before.st_size
            or hashlib.sha256(raw).hexdigest() != sha(expected)):
        raise ValueError("diagnostic input identity/hash differs")
    return raw


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def bf16_reference(record, shape):
    count = math.prod(shape)
    if record.get("shape") != list(shape) or record.get("bytes") != 2 * count:
        raise ValueError("bounded native BF16 projection extent differs")
    raw = sealed(record["path"], record["sha256"], 20480)
    if len(raw) != 2 * count:
        raise ValueError("native projection byte extent differs")
    words = [value << 16 for value in struct.unpack("<" + str(count) + "H", raw)]
    floats = [struct.unpack("<f", struct.pack("<I", value))[0] for value in words]
    if not all(math.isfinite(value) for value in floats):
        raise ValueError("nonfinite native BF16 projection")
    if hashlib.sha256(b"".join(struct.pack("<I", value) for value in words)).hexdigest() != record["float_array_sha256"]:
        raise ValueError("native projection widened-array hash differs")
    return words, floats


def actual_words(output, shape):
    rows = output.get("actual_output_words_u32")
    values = output.get("actual_output")
    if (output.get("actual_shape") != list(shape) or output.get("actual_dtype") != "float32"
            or type(rows) is not list or len(rows) != shape[0]
            or type(values) is not list or len(values) != shape[0]):
        raise ValueError("complete retained CPU output required")
    words, floats = [], []
    for row, numeric in zip(rows, values):
        if type(row) is not list or len(row) != shape[1] or type(numeric) is not list or len(numeric) != shape[1]:
            raise ValueError("complete CPU output row required")
        for word, value in zip(row, numeric):
            if type(word) is not int or not 0 <= word <= 0xffffffff or word & 0xffff:
                raise ValueError("finite BF16-lattice CPU word required")
            number = struct.unpack("<f", struct.pack("<I", word))[0]
            if type(value) not in (int, float) or not math.isfinite(number) or number != value:
                raise ValueError("CPU retained numeric/word output differs")
            words.append(word)
            floats.append(number)
    raw = b"".join(struct.pack("<I", word) for word in words)
    if hashlib.sha256(raw).hexdigest() != output.get("output_sha256"):
        raise ValueError("retained CPU output hash differs")
    return words, floats


def metrics(words, values, expected_words, expected_values):
    errors = [abs(actual - expected) for actual, expected in zip(values, expected_values)]
    outside = [index for index, (error, expected) in enumerate(zip(errors, expected_values))
               if error > CPU_TOLERANCE["atol"] + CPU_TOLERANCE["rtol"] * abs(expected)]
    result = dict(passed=not outside, tolerance=CPU_TOLERANCE,
                  exact_BF16_word_mismatches=sum(a != b for a, b in zip(words, expected_words)),
                  max_abs_error=max(errors), mismatched_elements=len(outside),
                  elements=len(words), non_BF16_lattice_elements=0)
    return result, outside


def validate_failed_cpu(gate, current=None):
    required = dict(schema=NORMAL_SCHEMA, source_sha256=PROBE_SHA256, provider="cpu", passed=False,
                    native_FC_screen_passed=False, output_replay_stability_passed=True,
                    alternating_inputs_changed=True, tolerance=CPU_TOLERANCE,
                    tolerance_frozen_before_session=True, session_creations=1, warmup_count=4,
                    repetitions=8, error=EXPECTED_ERROR, admission_gib=22, reserve_gib=18,
                    reference_weights_released_before_session=True, ort_version="1.25.2", numpy_version="2.5.3",
                    session_providers=["CPUExecutionProvider"], wire_mode="D", count=1,
                    native_bit_parity_qualified=False, seed_add_implemented=False,
                    embedding_rms_qualified=False, full_d_claim=False, full_mtp_claim=False,
                    acceptance_claim=False, generic_speed_promotion=False,
                    normalization_in_npu_segment=False, native_q8_affine_fma_decoder_proved=False)
    if (type(gate) is not dict or any(gate.get(key) != value for key, value in required.items())
            or gate.get("cleanup_errors") or gate.get("reserve_guard_error")):
        raise ValueError("complete same-source numerical-only failed CPU receipt required")
    if current is not None and any(gate.get(key) != current.get(key) for key in IDENTITY_KEYS):
        raise ValueError("failed CPU/current NPU source/model/data/receipt/oracle identity differs")
    samples = gate.get("reserve_samples")
    if type(samples) is not list or len(samples) < 2:
        raise ValueError("complete CPU reserve/cleanup evidence required")
    for index, sample in enumerate(samples):
        floor = (22 if index == 0 else 18) * 2**30
        if (type(sample) is not dict or type(sample.get("time")) not in (int, float)
                or not math.isfinite(sample["time"]) or sample["time"] <= 0
                or any(type(sample.get(name)) is not int or sample[name] < floor
                       for name in ("available_bytes", "commit_headroom_bytes"))):
            raise ValueError("CPU reserve evidence failed")
    profile = json.loads(sealed(gate["profile"], gate["profile_sha256"], 16 << 20))
    if type(profile) is not list or any(type(event) is not dict for event in profile):
        raise ValueError("bounded CPU profile event list required")
    nodes = [event for event in profile if event.get("cat") == "Node"]
    expected_names = {name + "_kernel_time" for name in
                      ("e_projection_fp32", "h_projection_fp32", "e_projection_bf16",
                       "h_projection_bf16", "e_projection", "h_projection", "h_streams")}
    proof = dict(passed=bool(nodes) and {event.get("args", {}).get("provider") for event in nodes} == {"CPUExecutionProvider"},
                 node_events=len(nodes), executed_node_providers=["CPUExecutionProvider"],
                 node_event_ops=sorted({event.get("args", {}).get("op_name", "<missing>") for event in nodes}))
    if (proof != gate.get("profile_proof") or not proof["passed"]
            or Counter(event.get("name") for event in nodes) != Counter({name: 12 for name in expected_names})):
        raise ValueError("all84 expected CPU node executions required")
    calls = gate.get("calls")
    if type(calls) is not list or len(calls) != 12:
        raise ValueError("complete balanced12-call CPU run required")
    references, stable = {}, {}
    for label in ("A", "B"):
        for name, shape in SHAPES.items():
            binding = gate["oracle_binding"]["normalized_inputs_and_projection_references"][label][name]
            native = bf16_reference(binding["native_GPU"], shape)
            numpy = bf16_reference(binding["informational"]["BF16_weight_numpy"], shape)
            if metrics(*native, *numpy)[1]:
                raise ValueError("native GPU/BF16-weight NumPy reference itself failed frozen tolerance")
            references[label, name] = native, numpy
    failure_indices = None
    for index, call in enumerate(calls):
        label = "A" if index % 2 == 0 else "B"
        if (type(call) is not dict or call.get("call_index") != index or call.get("input_set") != label
                or call.get("warmup") is not (index < 4) or call.get("output_stability_passed") is not True
                or call.get("passed") is not (label == "A") or set(call.get("outputs", {})) != set(SHAPES)):
            raise ValueError("CPU call order/completeness/failure scope differs")
        for name, shape in SHAPES.items():
            output = call["outputs"][name]
            words, values = actual_words(output, shape)
            native, numpy = references[label, name]
            comparison, outside = metrics(words, values, *native)
            independent, _ = metrics(words, values, *numpy)
            if (output.get("native_comparison") != comparison
                    or output.get("independent_numpy_comparisons", {}).get("BF16_weight_numpy") != independent):
                raise ValueError("CPU numerical comparison does not match retained words")
            key = label, name
            stable.setdefault(key, output["output_sha256"])
            if stable[key] != output["output_sha256"]:
                raise ValueError("CPU replay output changed")
            if label == "B" and name == "h_projection":
                if len(outside) != 2 or comparison["exact_BF16_word_mismatches"] != 2 or comparison["max_abs_error"] != .0009765625:
                    raise ValueError("only the observed two CPU BF16-ULP misses are diagnostic-authorized")
                if any((words[position] ^ native[0][position]) & 0x80000000
                       or abs((words[position] >> 16) - (native[0][position] >> 16)) != 1 for position in outside):
                    raise ValueError("CPU numerical failure must be exactly one BF16 ULP per missed element")
                if failure_indices is None:
                    failure_indices = tuple(outside)
                if tuple(outside) != failure_indices:
                    raise ValueError("CPU numerical failure indices changed across calls")
            elif outside:
                raise ValueError("CPU failure extends beyond authorized B hidden comparison")
    if any(stable["A", name] == stable["B", name] for name in SHAPES):
        raise ValueError("alternating CPU inputs did not change both outputs")
    return dict(cpu_passed=False, numerical_failure_only=True, complete_calls=12,
                failed_input_set="B", failed_output="h_projection", mismatched_elements=2,
                failure_indices=list(failure_indices), max_abs_error=.0009765625,
                frozen_tolerance=CPU_TOLERANCE, reserve_and_cleanup_validated=True,
                profile_validated=True, integration_admission=False)


def exclusive_json(path, value):
    with Path(path).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.flush()
        os.fsync(stream.fileno())


def run(args):
    report = args.report.absolute()
    nested_path = report.with_name(report.stem + ".probe-diagnostic.json")
    if not report.parent.is_dir() or any(path.exists() for path in (report, nested_path, Path(str(nested_path) + ".lock"))):
        raise FileExistsError("fresh diagnostic envelope/nested report paths required")
    adapter_hash = digest(__file__)
    probe_raw = sealed(PROBE, PROBE_SHA256, 262144)
    cpu_raw = sealed(args.failed_cpu_gate, args.failed_cpu_gate_sha256, 16 << 20)
    cpu = json.loads(cpu_raw)
    validated = validate_failed_cpu(cpu)
    envelope = dict(schema=SCHEMA, diagnostic_only=True, cpu_passed=False, integration_admission=False,
                    halogen_output_swap=False, acceleration_claim=False, performance_qualified=False,
                    native_word_parity_qualified=False, phase="prepared", diagnostic_completed=False,
                    adapter_sha256=adapter_hash, original_probe_sha256=PROBE_SHA256,
                    failed_cpu_receipt=dict(path=str(args.failed_cpu_gate.absolute()), sha256=args.failed_cpu_gate_sha256,
                                           passed=False, validation=validated),
                    nested_diagnostic_report=str(nested_path),
                    scope="standalone NPU comparison against actual native FC oracles after numerical-only CPU failure; never successful integration admission",
                    timing_scope="actual standalone NPU host-call/copy/session-run latencies; no Halogen token-rate or output-swap claim")
    exclusive_json(report, envelope)
    module = types.ModuleType("halogen_mtp_fc_npu_diagnostic_pinned_probe")
    module.__file__ = str(PROBE)
    exec(compile(probe_raw, str(PROBE), "exec"), module.__dict__)
    initial_creations = []

    def diagnostic_dict(*positional, **keywords):
        result = dict(*positional, **keywords)
        if result.get("schema") == NORMAL_SCHEMA:
            if positional or initial_creations or result.get("provider") != "npu" or result.get("passed") is not False:
                raise ValueError("unexpected original probe result-construction site")
            result.update(schema=NESTED_SCHEMA, original_probe_schema=NORMAL_SCHEMA,
                          diagnostic_only=True, integration_admission=False, cpu_passed=False,
                          halogen_output_swap=False, acceleration_claim=False,
                          diagnostic_adapter_sha256=adapter_hash,
                          failed_cpu_receipt_sha256=args.failed_cpu_gate_sha256,
                          scope=envelope["scope"])
            initial_creations.append(result)
        return result

    def diagnostic_cpu_gate(probe_args, result, bounded):
        if (result.get("schema") != NESTED_SCHEMA or result.get("integration_admission") is not False
                or result.get("cpu_passed") is not False or result.get("diagnostic_only") is not True):
            raise ValueError("initial diagnostic marking must precede CPU exception and provider initialization")
        fresh = json.loads(sealed(args.failed_cpu_gate, args.failed_cpu_gate_sha256, 16 << 20))
        validation = validate_failed_cpu(fresh, result)
        return dict(schema="halogen_mtp_fc_failed_cpu_diagnostic_binding.v1",
                    path=str(args.failed_cpu_gate.absolute()), sha256=args.failed_cpu_gate_sha256,
                    passed=False, integration_admission=False, diagnostic_only=True, validation=validation)

    # This callback exception and the narrow initial-result factory are confined
    # to a separately compiled pinned module. Normal probe imports remain intact.
    module.dict = diagnostic_dict
    module.cpu_gate = diagnostic_cpu_gate
    probe_args = argparse.Namespace(**vars(args))
    probe_args.report = nested_path
    probe_args.provider = "npu"
    probe_args.cpu_gate = args.failed_cpu_gate
    probe_args.cpu_gate_sha256 = args.failed_cpu_gate_sha256
    try:
        nested = module.run(probe_args)
        if len(initial_creations) != 1 or nested is not initial_creations[0] or nested.get("schema") != NESTED_SCHEMA:
            raise ValueError("original result escaped initial diagnostic marking")
        nested_hash = digest(nested_path)
        if json.loads(sealed(nested_path, nested_hash, 16 << 20)) != nested:
            raise ValueError("retained nested diagnostic report differs")
        if digest(__file__) != adapter_hash or digest(PROBE) != PROBE_SHA256 or digest(args.failed_cpu_gate) != args.failed_cpu_gate_sha256:
            raise ValueError("diagnostic source/failed receipt changed during comparison")
        envelope.update(phase="completed", nested_probe=nested, nested_diagnostic_report_sha256=nested_hash,
                        standalone_npu_native_screen_passed=nested.get("native_FC_screen_passed") is True,
                        profile_placement=dict(profile_proof=nested.get("profile_proof"), context_proof=nested.get("context_proof")),
                        actual_npu_calls=[dict(call_index=row.get("call_index"), warmup=row.get("warmup"), input_set=row.get("input_set"),
                                               host_call_ms=row.get("host_call_ms"), prepare_and_copy_ms=row.get("prepare_and_copy_ms"),
                                               session_run_ms=row.get("session_run_ms")) for row in nested.get("calls", [])],
                        diagnostic_completed=(len(nested.get("calls", [])) == 12 and not nested.get("cleanup_errors")
                                              and not nested.get("reserve_guard_error") and nested.get("provider_unregistered") is True
                                              and nested.get("dll_directory_closed") is True and nested.get("bootstrap_shutdown") is True))
    except BaseException as error:
        envelope.update(phase="failed", error=type(error).__name__ + ": " + str(error))
        raise
    finally:
        partial = report.with_name(report.name + ".update.partial")
        exclusive_json(partial, envelope)
        os.replace(partial, report)
    return envelope


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("model", "projection-receipt", "fc-fixtures", "native-fc-replay", "ep-dir", "failed-cpu-gate", "report"):
        parser.add_argument("--" + name, type=Path, required=True)
    for name in ("projection-receipt-sha256", "fc-fixtures-sha256", "native-fc-replay-sha256", "failed-cpu-gate-sha256"):
        parser.add_argument("--" + name, type=sha, required=True)
    parser.add_argument("--reference-mode", choices=("original-GPU-Q8-FC-before-seed-add",), default="original-GPU-Q8-FC-before-seed-add")
    parser.add_argument("--wire-mode", choices=("D",), default="D")
    parser.add_argument("--provider", choices=("npu",), default="npu")
    args = parser.parse_args(argv)
    result = run(args)
    print(json.dumps({key: result.get(key) for key in ("schema", "phase", "diagnostic_completed", "cpu_passed", "integration_admission",
                                                       "standalone_npu_native_screen_passed")}, indent=2))
    return 0 if result["diagnostic_completed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
