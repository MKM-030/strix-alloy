"""ROOT-only standalone fixed256 tiled D NPU diagnostic; never admission.

Original tiled probe/pass fields/tolerances remain unchanged. A separately
compiled pinned module is marked diagnostic at initial result creation, before
provider initialization. Only its CPU admission callback is replaced with strict
validation of the actual failed same-identity CPU run. No Halogen output swap,
native/full-head parity, acceptance or acceleration is claimed. Import runs none
of the providers, models, hardware or children. ROOT supplies retained22/18-GiB
ownership/deadline and must collect terminal cleanup independently.
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
PROBE = HERE / "halogen_npu_v2_d_tiled_probe.py"
PROBE_SHA256 = "08bbb8078ff1bda1ed0d06f2455b1844d1395831e05dc9333ef5ed13a1660bca"
NORMAL_SCHEMA = "halogen_v2_count1_D_tiled_probe.v1"
NESTED_SCHEMA = "halogen_mtp_tiled_standalone_npu_diagnostic_probe.v1"
SCHEMA = "halogen_mtp_tiled_standalone_npu_diagnostic.v1"
TOLERANCE = {"rtol": .002, "atol": .0002}
ERROR = "RuntimeError: frozen original ORT seed/tiled diagnostic screen failed; every returned output retained"
SHAPES = {"seed": (1, 4, 2560), "e_partial_sums": (1, 10, 1),
          "h_partial_sums": (1, 40, 1), "e_norm": (1, 2560), "h_norm": (1, 10240)}
IDENTITY_KEYS = ("source_sha256", "reference_mode", "model_sha256", "data_sha256", "tiled_receipt_sha256",
                 "transformer_sha256", "baseline_sha256", "runtime_input_sets", "fixture_binding", "rms_reference_proof",
                 "dependency_sha256", "probe_dependency_sha256", "graph_reference_sha256",
                 "required_hardware_partition_outputs", "fp32_reduction_order_changed")


def sha(value):
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError("independent lowercase SHA256 required")
    return value


def sealed(path, expected, limit):
    path = Path(path)
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or not 0 < before.st_size <= limit:
        raise ValueError("bounded unchanged regular tiled diagnostic input required")
    with path.open("rb") as stream:
        opened = os.fstat(stream.fileno())
        raw = stream.read(limit + 1)
        after = os.fstat(stream.fileno())
    fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns")
    fields += ("st_birthtime_ns",) if os.name == "nt" else ("st_ctime_ns",)
    identity = lambda row: tuple(getattr(row, field, None) for field in fields)
    path_after = path.lstat()
    if (not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1 or not stat.S_ISREG(path_after.st_mode)
            or path_after.st_nlink != 1 or not identity(before) == identity(opened) == identity(after) == identity(path_after)
            or before.st_ctime_ns != path_after.st_ctime_ns or opened.st_ctime_ns != after.st_ctime_ns
            or len(raw) != before.st_size or hashlib.sha256(raw).hexdigest() != sha(expected)):
        raise ValueError("tiled diagnostic input identity/hash differs")
    return raw


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def flatten(value, shape):
    if not shape:
        return [value]
    if type(value) is not list or len(value) != shape[0]:
        raise ValueError("complete observable tiled output extent required")
    return [item for child in value for item in flatten(child, shape[1:])]


def validate_cpu(gate, current=None):
    required = dict(schema=NORMAL_SCHEMA, source_sha256=PROBE_SHA256, reference_mode="original-ORT-seed-and-distinct-RMS-words",
                    provider="cpu", passed=False, graph_fidelity_screen_passed=False, diagnostics_passed=True,
                    output_replay_stability_passed=True, alternating_input_outputs_changed=True,
                    tolerance=TOLERANCE, tolerance_frozen_before_session=True, session_creations=1,
                    warmup_count=4, repetitions=8, error=ERROR, admission_gib=22, reserve_gib=18,
                    wire_mode="D", count=1, fp32_reduction_order_changed=True,
                    native_bit_parity_qualified=False, full_mtp_claim=False, acceptance_claim=False,
                    generic_speed_promotion=False, cpu_fallback_allowed=True, reference_weights_released_before_session=True,
                    ort_version="1.25.2", numpy_version="2.5.3", session_providers=["CPUExecutionProvider"])
    if (type(gate) is not dict or any(gate.get(key) != value for key, value in required.items())
            or gate.get("cleanup_errors") or gate.get("reserve_guard_error")):
        raise ValueError("complete numerical-only failed original tiled CPU receipt required")
    if current is not None and any(gate.get(key) != current.get(key) for key in IDENTITY_KEYS):
        raise ValueError("failed tiled CPU/current diagnostic identity differs")
    samples = gate.get("reserve_samples")
    if type(samples) is not list or len(samples) < 2:
        raise ValueError("CPU reserve/cleanup evidence absent")
    for index, sample in enumerate(samples):
        floor = (22 if index == 0 else 18) * 2**30
        if (type(sample) is not dict or any(type(sample.get(key)) is not int or sample[key] < floor
                                          for key in ("available_bytes", "commit_headroom_bytes"))):
            raise ValueError("CPU reserve evidence failed")
    events = json.loads(sealed(gate["profile"], gate["profile_sha256"], 32 << 20))
    if type(events) is not list or any(type(event) is not dict for event in events):
        raise ValueError("complete CPU profile required")
    nodes = [event for event in events if event.get("cat") == "Node"]
    proof = dict(passed=bool(nodes) and {event.get("args", {}).get("provider") for event in nodes} == {"CPUExecutionProvider"},
                 node_events=len(nodes), executed_node_providers=["CPUExecutionProvider"],
                 node_event_ops=sorted({event.get("args", {}).get("op_name", "<missing>") for event in nodes}))
    counts = Counter(event.get("name") for event in nodes)
    if proof != gate.get("profile_proof") or not proof["passed"] or len(nodes) != 444 or len(counts) != 37 or set(counts.values()) != {12}:
        raise ValueError("all444 original tiled CPU node executions required")
    calls = gate.get("calls")
    if type(calls) is not list or len(calls) != 12:
        raise ValueError("complete balanced12-call tiled CPU run required")
    stable, comparisons = {}, {}
    for index, call in enumerate(calls):
        label = "A" if index % 2 == 0 else "B"
        if (type(call) is not dict or call.get("call_index") != index or call.get("input_set") != label
                or call.get("warmup") is not (index < 4) or call.get("passed") is not False
                or call.get("output_stability_passed") is not True or set(call.get("outputs", {})) != set(SHAPES)):
            raise ValueError("tiled CPU call order/completeness/failure scope differs")
        graph = call.get("graph_comparison", {})
        if (graph.get("passed") is not False or graph.get("tolerance") != TOLERANCE
                or graph.get("elements") != 10240 or graph.get("non_bf16_lattice_elements") != 0
                or graph.get("mismatched_elements") != (73 if label == "A" else 55)
                or graph.get("max_abs_error") != (.00390625 if label == "A" else .0078125)):
            raise ValueError("CPU failure must retain the observed frozen seed comparison")
        comparisons.setdefault(label, graph)
        if comparisons[label] != graph:
            raise ValueError("CPU seed comparison changed across repeats")
        for name, shape in SHAPES.items():
            output = call["outputs"][name]
            bf16 = name in ("seed", "e_norm", "h_norm")
            if (type(output) is not dict or output.get("passed") is not True or output.get("shape") != list(shape)
                    or output.get("dtype") != "float32" or output.get("finite") is not True
                    or output.get("non_bf16_lattice_elements") != (0 if bf16 else None)):
                raise ValueError("all five finite tiled CPU diagnostics required")
            words = flatten(output.get("output_words_u32"), shape)
            values = flatten(output.get("output"), shape)
            for word, value in zip(words, values):
                if type(word) is not int or not 0 <= word <= 0xffffffff or bf16 and word & 0xffff:
                    raise ValueError("retained tiled CPU output word differs")
                number = struct.unpack("<f", struct.pack("<I", word))[0]
                if type(value) not in (int, float) or not math.isfinite(number) or number != value:
                    raise ValueError("retained tiled CPU numeric/word value differs")
            actual_hash = hashlib.sha256(b"".join(struct.pack("<I", word) for word in words)).hexdigest()
            if actual_hash != output.get("sha256"):
                raise ValueError("retained tiled CPU output hash differs")
            stable.setdefault((label, name), actual_hash)
            if stable[label, name] != actual_hash:
                raise ValueError("tiled CPU observable output is unstable")
        rms = call.get("hidden_rms_comparisons", {})
        if set(rms) != {"ort", "numpy", "native"}:
            raise ValueError("distinct original ORT/NumPy/native RMS comparisons required")
        for oracle in ("numpy", "native"):
            row = rms[oracle]
            if (row.get("passed") is not True or row.get("tolerance") != TOLERANCE or row.get("exact_word_mismatches") != 0
                    or row.get("mismatched_elements") != 0 or row.get("max_abs_error") != 0
                    or row.get("non_bf16_lattice_elements") != 0):
                raise ValueError("tiled CPU native/NumPy RMS identity was not retained")
    if any(stable["A", name] == stable["B", name] for name in SHAPES):
        raise ValueError("alternating inputs did not change every tiled output")
    return dict(cpu_passed=False, numerical_failure_only=True, complete_calls=12,
                profile_node_events=444, reserve_and_cleanup_validated=True,
                seed_comparisons=comparisons, all_five_outputs_stable_and_finite=True, integration_admission=False)


def write_json(path, value):
    with Path(path).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.flush()
        os.fsync(stream.fileno())


def run(args):
    report = args.report.absolute()
    nested_path = report.with_name(report.stem + ".probe-diagnostic.json")
    if not report.parent.is_dir() or any(path.exists() for path in (report, nested_path, Path(str(nested_path) + ".lock"))):
        raise FileExistsError("fresh tiled diagnostic report paths required")
    source_hash = digest(__file__)
    raw_probe = sealed(PROBE, PROBE_SHA256, 262144)
    cpu = json.loads(sealed(args.failed_cpu_gate, args.failed_cpu_gate_sha256, 32 << 20))
    validation = validate_cpu(cpu)
    envelope = dict(schema=SCHEMA, diagnostic_only=True, cpu_passed=False, integration_admission=False,
                    halogen_output_swap=False, acceleration_claim=False, native_word_parity_qualified=False,
                    phase="prepared", diagnostic_completed=False, adapter_sha256=source_hash,
                    original_probe_sha256=PROBE_SHA256, failed_cpu_receipt=dict(path=str(args.failed_cpu_gate.absolute()),
                    sha256=args.failed_cpu_gate_sha256, passed=False, validation=validation), nested_diagnostic_report=str(nested_path),
                    scope="standalone fixed256 tiled D NPU diagnosis after failed same-identity CPU fidelity; never integration admission",
                    timing_scope="actual standalone NPU host/copy/session-run calls, including arithmetic failures; no Halogen token-rate claim")
    write_json(report, envelope)
    module = types.ModuleType("halogen_mtp_tiled_npu_diagnostic_pinned_probe")
    module.__file__ = str(PROBE)
    exec(compile(raw_probe, str(PROBE), "exec"), module.__dict__)
    initial = []

    def diagnostic_dict(*positional, **keywords):
        result = dict(*positional, **keywords)
        if result.get("schema") == NORMAL_SCHEMA:
            if positional or initial or result.get("provider") != "npu" or result.get("passed") is not False:
                raise ValueError("unexpected original tiled result-construction site")
            result.update(schema=NESTED_SCHEMA, original_probe_schema=NORMAL_SCHEMA, diagnostic_only=True,
                          cpu_passed=False, integration_admission=False, halogen_output_swap=False,
                          acceleration_claim=False, diagnostic_adapter_sha256=source_hash,
                          failed_cpu_receipt_sha256=args.failed_cpu_gate_sha256, scope=envelope["scope"])
            initial.append(result)
        return result

    def failed_cpu_binding(probe_args, result, baseline_helpers):
        if result.get("schema") != NESTED_SCHEMA or result.get("integration_admission") is not False or result.get("cpu_passed") is not False:
            raise ValueError("initial diagnostic marking required before provider initialization")
        fresh = json.loads(sealed(args.failed_cpu_gate, args.failed_cpu_gate_sha256, 32 << 20))
        validated = validate_cpu(fresh, result)
        return dict(schema="halogen_mtp_tiled_failed_cpu_diagnostic_binding.v1", path=str(args.failed_cpu_gate.absolute()),
                    sha256=args.failed_cpu_gate_sha256, passed=False, integration_admission=False, diagnostic_only=True, validation=validated)

    module.dict = diagnostic_dict
    module.verify_cpu_gate = failed_cpu_binding
    probe_args = argparse.Namespace(**vars(args))
    probe_args.report, probe_args.provider = nested_path, "npu"
    probe_args.cpu_gate, probe_args.cpu_gate_sha256 = args.failed_cpu_gate, args.failed_cpu_gate_sha256
    try:
        nested = module.run(probe_args)
        if len(initial) != 1 or nested is not initial[0] or nested.get("schema") != NESTED_SCHEMA:
            raise ValueError("tiled probe escaped initial diagnostic marking")
        nested_hash = digest(nested_path)
        if json.loads(sealed(nested_path, nested_hash, 32 << 20)) != nested:
            raise ValueError("retained nested tiled diagnostic differs")
        if digest(__file__) != source_hash or digest(PROBE) != PROBE_SHA256 or digest(args.failed_cpu_gate) != args.failed_cpu_gate_sha256:
            raise ValueError("tiled diagnostic source/failed receipt changed")
        actual_calls = [{key: row.get(key) for key in ("call_index", "warmup", "input_set", "host_call_ms", "prepare_and_copy_ms", "session_run_ms",
                                                       "graph_comparison", "hidden_rms_comparisons", "passed")} for row in nested.get("calls", [])]
        measured = [row["host_call_ms"] for row in actual_calls if row["warmup"] is False]
        envelope.update(phase="completed", nested_probe=nested, nested_diagnostic_report_sha256=nested_hash,
                        actual_npu_calls=actual_calls, standalone_npu_graph_fidelity_screen_passed=nested.get("graph_fidelity_screen_passed") is True,
                        profile_placement=dict(profile_proof=nested.get("profile_proof"), context_proof=nested.get("context_proof")),
                        measured_host_mean_ms=sum(measured) / len(measured) if measured else None,
                        diagnostic_completed=(len(actual_calls) == 12 and not nested.get("cleanup_errors") and not nested.get("reserve_guard_error")
                                              and nested.get("provider_unregistered") is True and nested.get("dll_directory_closed") is True
                                              and nested.get("bootstrap_shutdown") is True and nested.get("profile_proof", {}).get("passed") is True))
    except BaseException as error:
        envelope.update(phase="failed", error=type(error).__name__ + ": " + str(error))
        raise
    finally:
        partial = report.with_name(report.name + ".update.partial")
        write_json(partial, envelope)
        os.replace(partial, report)
    return envelope


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("model", "tiled-receipt", "baseline", "e-u16", "h-u16", "rms-fixtures", "native-rms-replay", "ep-dir", "failed-cpu-gate", "report"):
        parser.add_argument("--" + name, type=Path, required=True)
    for name in ("tiled-receipt-sha256", "baseline-sha256", "e-sha256", "h-sha256", "rms-fixtures-sha256", "native-rms-replay-sha256", "failed-cpu-gate-sha256"):
        parser.add_argument("--" + name, type=sha, required=True)
    parser.add_argument("--reference-mode", choices=("original-ORT-seed-and-distinct-RMS-words",), default="original-ORT-seed-and-distinct-RMS-words")
    parser.add_argument("--wire-mode", choices=("D",), default="D")
    parser.add_argument("--provider", choices=("npu",), default="npu")
    result = run(parser.parse_args(argv))
    print(json.dumps({key: result.get(key) for key in ("schema", "phase", "diagnostic_completed", "cpu_passed", "integration_admission",
                                                     "standalone_npu_graph_fidelity_screen_passed", "measured_host_mean_ms")}, indent=2))
    return 0 if result["diagnostic_completed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
