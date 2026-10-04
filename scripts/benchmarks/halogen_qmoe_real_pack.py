"""Stream the real v2 layer48 routed expert bank through AMD's offline packer.

Execution requires a root-owned Windows CPython3.12 child guard. Only one
expert/matrix is decoded at a time; no complete decoded bank is allocated.
The pinned v2 checkpoint is read through the qualified sparse q4c reader.
Weights are approximately requantized to affine INT4, with explicit
concatenated-to-interleaved gate/up ordering. No ORT, provider or inference
is invoked. A passing receipt qualifies construction, not live drafting.

Importing this module performs no file reads, NumPy/native imports or calls.
"""

import argparse
import ctypes
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import time
import types


ROOT = Path(r"C:\Projects\strix-alloy-clean")
SCRIPTS = ROOT / "scripts/benchmarks"
OWNED_ROOT = ROOT / "server/.local/optimization9h-20261004"
BACKEND_LOCAL = ROOT / "backends/halogen-wsl2-0.16.2/.local"
METADATA = Path(r"C:\AI\halogen-mtp-npu\v2-metadata-20261004\mtp-metadata.json")
INTEGRITY = BACKEND_LOCAL / "v2-integrity.json"
MACHINE = BACKEND_LOCAL / "machine.json"
STAGE = OWNED_ROOT / "qmoe-dd-stage-8bba3dba41e94053bb9196b918c2456f"
PAYLOAD = STAGE / "payload/ryzenai_dynamic_dispatch"
STATIC_REVIEW = STAGE / "static-review.json"
XRT = Path(r"C:\Windows\System32\DriverStore\FileRepository\kipudrv.inf_amd64_7b0051e064968f34")
PY_SHA256 = "4d6f5f81a4bca11191c4c7c6b43632694d0a4ce74e068619d8fdc161d469859a"
XRT_SHA256 = "04a26d37c6e0c713491ad0bfae74ce74ea94c74136d2aa056333616dac6c3a44"
CHECKPOINT_SHA256 = "71246c6ab3fc1de2cf06326f18e275fe9c2a18366d646ed3357d194c884fc687"
WHEEL_SHA256 = "8988620998c23a0d1a71bf2ced9a5287bc6641133ad38b67900fa4c546e7a8e4"
SOURCE_PINS = {
    SCRIPTS / "hgn_q4c_slice.py": "fe0dd1b9974f95bed02f37dddde1ee7c286f3f69d491548008d4a94ea703fdce",
    SCRIPTS / "halogen_npu_v2_sparse.py": "345f18778deeac5ade76c69f26f6bd2296741a55130d33a9caa0f6506f7e5c79",
    SCRIPTS / "halogen_npu_mtp_metadata.py": "25e25cf244e1da93d1fefa510ec0c95aefafb29d7fd8d0098237fb55adec0455",
    SCRIPTS / "halogen_qmoe_affine.py": "1346041e7d49bf2b8afdc2d080af83ea912c586df1b7a2cbd8c29007d04a1171",
    SCRIPTS / "halogen_qmoe_pack_probe.py": "081d91e32c6813c5b9a1c18d196c430d0b71efc48f5839e36b330cedd93934be",
    SCRIPTS / "halogen_qmoe_graph.py": "38d777a095f386c778b66ef90722bbaf36478e9cc919061ab945a2d96396cfbc",
    ROOT / "server/host_frames.py": "417e33060ce6bc5b8f336f9e90282012a4a0e12475a13ad1dba20eec2df8bdf8",
}
RECEIPT_PINS = {
    METADATA: "4159d1ddb9094907ba82b62940777317d9bc89e4c7a8cb881809ecb17912e3cb",
    INTEGRITY: "7b95c3181e036ffcba67602b1cbea0143d3389c2ff842888aef4d8c7f1e11ef2",
    MACHINE: "4afd3a90d13222c3f3460425c48f315c5959a29c2b7ade78a82791c8552fe527",
    STATIC_REVIEW: "b9e7b0e6d03608b92271b51f1526c0f568be8d4209443044dc149356581cf8c3",
}
PACKER_PINS = {
    "_DynamicDispatch.cp312-win_amd64.pyd": "38814ad69d2233758b76bf82db922f2e674c0d01aace756ace066135cbf4aaab",
    "dyn_bins.dll": "959bdb807646a5b7565fb3a68bbf4e2368aa6d200f1bdfd4fefeaba352b37175",
    "dyn_bins.zip": "9cc1cbe8d6939fcd6eb19c3647e3accd6a2921f918206d0bb5240c18d6093cac",
}
GIB = 1024**3
WORKING_BYTES = 128 * 1024**2
HASH_CHUNK_BYTES = 8 * 1024**2
EXPERTS, WIDTH, INTERMEDIATE = 512, 2560, 640
FC1_BYTES, FC2_BYTES, TAIL_BYTES = 4198400, 1597440, 36864
STRIDE = FC1_BYTES + FC2_BYTES + TAIL_BYTES
BANK_BYTES = EXPERTS * STRIDE
SOURCE_BYTES_PER_EXPERT = 2785408
DECODED_BYTES_PER_EXPERT = 19660800
FLUSH_EXPERTS = 8  # 46,661,632 output bytes, below64MiB dirty write interval.
MATRICES = (
    ("FC1", "mtp.layers.0.mlp.experts.gate_up_proj.weight", 1280, 2560, [2560, 2560], FC1_BYTES),
    ("FC2", "mtp.layers.0.mlp.experts.down_proj.weight", 2560, 640, [768, 3072], FC2_BYTES),
)


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify_pins(expected_self):
    pins = {**SOURCE_PINS, **RECEIPT_PINS, **{PAYLOAD / key: value for key, value in PACKER_PINS.items()},
            XRT / "xrt_coreutil.dll": XRT_SHA256, Path(sys.executable): PY_SHA256,
            Path(__file__).resolve(): expected_self}
    for path, expected in pins.items():
        if path.is_symlink() or not path.is_file() or sha(path) != expected:
            raise ValueError("Frozen input changed: " + str(path))
    review = json.loads(STATIC_REVIEW.read_text(encoding="utf-8"))
    retained = {Path(row["name"]).name: row["sha256"] for row in review["extracted"]}
    if review.get("passed") is not True or review.get("executed") is not False:
        raise ValueError("Passing source-only AMD acquisition receipt required")
    if review.get("wheel_sha256") != WHEEL_SHA256 or any(retained.get(key) != value for key, value in PACKER_PINS.items()):
        raise ValueError("AMD acquisition receipt differs from frozen packer pins")
    return {str(path): value for path, value in pins.items()}


def fresh_outputs(report, bank):
    report, bank = report.resolve(), bank.resolve()
    journal = report.parent / "expert-diagnostics.jsonl"
    partial = bank.with_name(bank.name + ".partial")
    paths = (report, bank, journal, partial)
    if report.parent != bank.parent or not report.parent.is_relative_to(OWNED_ROOT.resolve()):
        raise ValueError("Fresh sibling outputs in the root-owned task directory required")
    if report.parent == OWNED_ROOT.resolve() or not report.parent.is_dir():
        raise ValueError("Root guard must create a fresh owned child directory first")
    if len(set(paths)) != len(paths) or any(path.exists() or path.is_symlink() for path in paths):
        raise ValueError("Existing receipts, bank and partial evidence are never overwritten")
    if shutil.disk_usage(report.parent).free < BANK_BYTES + 64 * 1024**2:
        raise RuntimeError("Insufficient free output space for bank plus bounded diagnostics")
    return report, bank, journal, partial


def boundary(result, frame, started, maximum_seconds, additional_bytes=0):
    current = frame()
    memory = result.setdefault("memory", {"samples": 0, "reserve_bytes": 18 * GIB,
                                          "next_working_budget_bytes": WORKING_BYTES})
    memory["samples"] += 1
    for key in ("available_bytes", "commit_headroom_bytes"):
        minimum = "minimum_" + key
        memory[minimum] = min(memory.get(minimum, current[key]), current[key])
        if current[key] < 18 * GIB + additional_bytes:
            raise RuntimeError("18GiB physical/commit floor plus next allocation unavailable")
    if time.perf_counter() - started >= maximum_seconds:
        raise TimeoutError("Cooperative construction deadline reached; root guard owns hard termination")


def import_sources(result, started, maximum_seconds):
    sys.path.insert(0, str(SCRIPTS))
    sys.path.insert(0, str(ROOT / "server"))
    names = ("host_frames", "hgn_q4c_slice", "halogen_npu_mtp_metadata", "halogen_npu_v2_sparse",
             "halogen_qmoe_affine", "halogen_qmoe_graph")
    if any(name in sys.modules for name in names) or "ryzenai_dynamic_dispatch" in sys.modules:
        raise RuntimeError("Fresh child required; frozen helper modules must not be preloaded")
    modules = {}
    for name in names:
        expected = ROOT / "server/host_frames.py" if name == "host_frames" else SCRIPTS / (name + ".py")
        payload = expected.read_bytes()
        if hashlib.sha256(payload).hexdigest() != SOURCE_PINS[expected]:
            raise ValueError("Frozen source changed immediately before import: " + name)
        # Execute the reviewed source bytes, never an unpinned cached .pyc.
        module = types.ModuleType(name)
        module.__file__ = str(expected)
        sys.modules[name] = module
        exec(compile(payload, str(expected), "exec"), module.__dict__)
        modules[name] = module
        if name == "host_frames":
            boundary(result, module.frame, started, maximum_seconds, GIB)
    return modules


def source_binding(sparse):
    expected = json.loads(METADATA.read_text(encoding="utf-8"))["sources"]["v2"]
    integrity = json.loads(INTEGRITY.read_text(encoding="utf-8"))
    machine = json.loads(MACHINE.read_text(encoding="utf-8"))
    if integrity.get("sha256") != CHECKPOINT_SHA256 or integrity["identity"]["size"] != 66687678432:
        raise ValueError("Complete pinned v2 integrity receipt required")
    source = machine["models"] + "/qwen38-flash-next-v2.hgn"
    unc = Path("\\\\wsl.localhost\\" + machine["distro"] + source.replace("/", "\\"))
    if str(unc) != expected["path"]:
        raise ValueError("Machine path differs from pinned v2 metadata")
    before = sparse.native_identity(machine, source)
    if before != integrity["identity"]:
        raise ValueError("Native v2 identity differs from complete integrity receipt")
    actual = sparse.metadata(unc)
    keys = ("identity", "file_size", "version", "tensor_count", "header_sha256", "table_sha256", "entries")
    if any(actual[key] != expected[key] for key in keys):
        raise ValueError("v2 header/table/entries differ from qualified metadata")
    entries = {entry["name"]: entry for entry in actual["entries"]}
    for _, name, rows, width, _, _ in MATRICES:
        entry = entries[name]
        if entry["dims"] != [EXPERTS, rows, width] or (entry["store"], entry["variant"]) != (5, 2):
            raise ValueError("Requires exact v2 layer48 q4c-variant2 expert geometry")
    binding = dict(checkpoint_unc=str(unc), checkpoint_source=source, checkpoint_sha256=CHECKPOINT_SHA256,
                   checkpoint_hash_recomputed=False, checkpoint_hash_source="complete pinned integrity receipt plus unchanged native identity",
                   native_identity_before=before, metadata_bytes_read=actual["metadata_bytes_read"],
                   header_sha256=actual["header_sha256"], table_sha256=actual["table_sha256"],
                   source_gate_up_layout="concatenated", packed_gate_up_layout="interleaved",
                   complete_head_parity_assumed=False, standalone_payload_used=False)
    return unc, entries, machine, source, before, binding


def native_packer(handles, result):
    for directory in (PAYLOAD, XRT):
        handles.append(os.add_dll_directory(str(directory)))
    package = types.ModuleType("ryzenai_dynamic_dispatch")
    package.__path__ = [str(PAYLOAD)]
    sys.modules[package.__name__] = package
    path = PAYLOAD / "_DynamicDispatch.cp312-win_amd64.pyd"
    spec = importlib.util.spec_from_file_location(package.__name__ + "._DynamicDispatch", path)
    native = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = native
    spec.loader.exec_module(native)
    if Path(native.__file__).resolve() != path.resolve():
        raise RuntimeError("Unexpected loaded offline packer path")
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetModuleHandleW.argtypes = [ctypes.c_wchar_p]
    kernel.GetModuleHandleW.restype = ctypes.c_void_p
    kernel.GetModuleFileNameW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint]
    kernel.GetModuleFileNameW.restype = ctypes.c_uint
    loaded = ctypes.create_unicode_buffer(32768)
    handle = kernel.GetModuleHandleW("xrt_coreutil.dll")
    if not handle or not kernel.GetModuleFileNameW(handle, loaded, len(loaded)):
        raise RuntimeError("Loaded XRT path unavailable")
    if Path(loaded.value).resolve() != (XRT / "xrt_coreutil.dll").resolve():
        raise RuntimeError("Loaded XRT is not the reviewed DriverStore dependency")
    result["loaded_xrt_coreutil"] = loaded.value
    return native


def array_sha(array):
    return hashlib.sha256(memoryview(array).cast("B")).hexdigest()


def prepare_matrix(stream, entry, expert_id, spec, sparse, affine, native, np):
    label, _, rows, width, padded, byte_count = spec
    began = time.perf_counter()
    decoded, source_record = sparse.expert(stream, entry, expert_id, rows)
    decode_ms = (time.perf_counter() - began) * 1000
    if decoded.dtype != np.float32 or decoded.shape != (rows, width) or decoded.nbytes > 64 * 1024**2:
        raise RuntimeError("Bounded decoded single-expert matrix geometry differs")
    began = time.perf_counter()
    if label == "FC1":
        ordered = affine.reorder_gate_up_rows(decoded, source_layout="concatenated", target_layout="interleaved")
        layout = "gate_up_interleaved"
    else:
        ordered, layout = decoded, "linear"
    ordered_sha = array_sha(ordered)
    prepared = affine.quantize_rows(ordered, row_layout=layout)
    quantize_ms = (time.perf_counter() - began) * 1000
    del ordered, decoded
    quantized = {key: array_sha(getattr(prepared, key)) for key in ("weights", "bias", "scales", "zero_points")}
    attr = native.Attributes()
    attributes = {"K": width, "N": rows, "lora": False, "mladf_version": "v2",
                  "asymmetric_quant": True, "bias_en": False, "block_size": 32}
    for key, value in attributes.items():
        attr.set(key, value)
    began = time.perf_counter()
    data, size, padded_k, padded_n = native.matmulnbits.matmulnbits_pack_const_float32(
        prepared.weights, prepared.bias, prepared.scales, prepared.zero_points, attr)
    pack_ms = (time.perf_counter() - began) * 1000
    if not isinstance(data, np.ndarray) or data.dtype != np.uint8 or data.ndim != 1 or not data.flags.c_contiguous:
        raise RuntimeError("Official packer did not return contiguous UINT8 bytes")
    if data.nbytes != byte_count or size != byte_count or [padded_k, padded_n] != padded:
        raise RuntimeError("Official packer returned unqualified size or padding geometry")
    record = dict(label=label, logical_kn=[width, rows], padded_kn=padded, bytes=byte_count,
                  source=source_record, decoded_row_layout="concatenated" if label == "FC1" else "linear",
                  packed_row_layout=layout, reordered_decoded_sha256=ordered_sha,
                  affine_input_sha256=quantized, affine_diagnostics=prepared.diagnostics,
                  pack_attributes=attributes, packed_sha256=array_sha(data),
                  decode_host_ms=decode_ms, reorder_quantize_host_ms=quantize_ms, pack_host_ms=pack_ms,
                  synthetic_weights=False, no_npu_inference=True)
    return data, record


def write_exact(stream, data):
    if stream.write(data) != len(data):
        raise OSError("Short output write")


def flush_owned(bank_stream, journal_stream):
    for stream in (bank_stream, journal_stream):
        stream.flush()
        os.fsync(stream.fileno())


def run(args, report, bank, journal, partial):
    started = time.perf_counter()
    result = dict(schema="halogen_qmoe_real_pack_v1", passed=False, stage="frozen_inputs",
                  scope="streamed approximate real v2 layer48 routed-expert offline INT4 bank construction only",
                  source_sha256=args.expected_probe_sha256, native_packer_sha256=PACKER_PINS["_DynamicDispatch.cp312-win_amd64.pyd"],
                  dd_wheel_sha256=WHEEL_SHA256, xrt_coreutil_sha256=XRT_SHA256,
                  provider_inference=False, full_mtp=False, acceptance_qualified=False, speed_gain=False,
                  activation_semantics_verified=False, shape_padding_execution_verified=False,
                  approximate_quantization=True, maximum_seconds=args.maximum_seconds,
                  decoded_fp32_bytes_per_expert=DECODED_BYTES_PER_EXPERT,
                  full_decoded_bank_materialized=False, completed_experts=0, source_bytes_read=0,
                  journal_path=str(journal), partial_bank_path=str(partial), rows=[])
    handles = []
    try:
        result["frozen_inputs"] = verify_pins(args.expected_probe_sha256)
        modules = import_sources(result, started, args.maximum_seconds)
        sparse, affine, graph = (modules[name] for name in
                                 ("halogen_npu_v2_sparse", "halogen_qmoe_affine", "halogen_qmoe_graph"))
        frame = modules["host_frames"].frame
        boundary(result, frame, started, args.maximum_seconds, GIB)
        result["stage"] = "source_binding"
        unc, entries, machine, source, before, binding = source_binding(sparse)
        result["source_binding"] = binding
        result["stage"] = "native_import"
        native = native_packer(handles, result)
        import numpy as np
        result["numpy_version"] = np.__version__
        boundary(result, frame, started, args.maximum_seconds, WORKING_BYTES)
        totals = {label: dict(label=label, logical_kn=[width, rows], padded_kn=padded, bytes=byte_count,
                             experts_packed=0, pack_host_ms_total=0.0,
                             synthetic_weights=False, no_npu_inference=True)
                  for label, _, rows, width, padded, byte_count in MATRICES}
        bank_digest, journal_digest = hashlib.sha256(), hashlib.sha256()
        tail = bytes(TAIL_BYTES)
        result["stage"] = "packing"
        with unc.open("rb") as source_stream, partial.open("xb") as output_stream, journal.open("xb") as journal_stream:
            for expert_id in range(EXPERTS):
                expert_record = dict(expert=expert_id, bank_offset=expert_id * STRIDE, expert_stride=STRIDE,
                                     fc2_tail_padding=TAIL_BYTES, matrices=[])
                expert_digest = hashlib.sha256()
                source_bytes = 0
                for spec in MATRICES:
                    boundary(result, frame, started, args.maximum_seconds, WORKING_BYTES)
                    label, name, _, _, _, _ = spec
                    data, record = prepare_matrix(source_stream, entries[name], expert_id, spec, sparse, affine, native, np)
                    boundary(result, frame, started, args.maximum_seconds)
                    block = memoryview(data).cast("B")
                    write_exact(output_stream, block)
                    bank_digest.update(block)
                    expert_digest.update(block)
                    del block, data
                    expert_record["matrices"].append(record)
                    source_bytes += sum(row["bytes"] for row in record["source"]["ranges"])
                    totals[label]["experts_packed"] += 1
                    totals[label]["pack_host_ms_total"] += record["pack_host_ms"]
                if source_bytes != SOURCE_BYTES_PER_EXPERT:
                    raise RuntimeError("Unexpected source read extent for one expert")
                write_exact(output_stream, tail)
                bank_digest.update(tail)
                expert_digest.update(tail)
                expert_record["bank_expert_sha256"] = expert_digest.hexdigest()
                payload = (json.dumps(expert_record, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")
                if len(payload) > 65536:
                    raise RuntimeError("Per-expert diagnostics exceed bounded metadata budget")
                write_exact(journal_stream, payload)
                journal_digest.update(payload)
                result["completed_experts"] = expert_id + 1
                result["source_bytes_read"] += source_bytes
                if (expert_id + 1) % FLUSH_EXPERTS == 0:
                    flush_owned(output_stream, journal_stream)
                    print("REAL_BANK_WRITTEN_EXPERTS " + str(expert_id + 1), flush=True)
            flush_owned(output_stream, journal_stream)
            if output_stream.tell() != BANK_BYTES:
                raise RuntimeError("Streamed bank output extent differs")
        result["rows"] = list(totals.values())
        result["stage"] = "readback"
        readback = hashlib.sha256()
        with partial.open("rb") as stream:
            while True:
                boundary(result, frame, started, args.maximum_seconds, HASH_CHUNK_BYTES)
                chunk = stream.read(HASH_CHUNK_BYTES)
                if not chunk:
                    break
                readback.update(chunk)
        if partial.stat().st_size != BANK_BYTES or readback.hexdigest() != bank_digest.hexdigest():
            raise RuntimeError("Complete owned bank readback SHA256 differs from written stream")
        if sha(journal) != journal_digest.hexdigest():
            raise RuntimeError("Per-expert journal readback SHA256 differs")
        result["stage"] = "final_seals"
        if sparse.native_identity(machine, source) != before:
            raise ValueError("Native v2 checkpoint changed during construction")
        actual_after = sparse.metadata(unc)
        if actual_after["header_sha256"] != binding["header_sha256"] or actual_after["table_sha256"] != binding["table_sha256"]:
            raise ValueError("Native v2 header/table changed during construction")
        binding["native_identity_after"] = before
        binding["metadata_bytes_read"] += actual_after["metadata_bytes_read"]
        verify_pins(args.expected_probe_sha256)
        boundary(result, frame, started, args.maximum_seconds)
        candidate = dict(result, passed=True, stage="complete", bank=dict(
            path=str(bank), num_experts=EXPERTS, expert_stride=STRIDE, fc1_bytes=FC1_BYTES,
            fc2_raw_bytes=FC2_BYTES, fc2_tail_padding=TAIL_BYTES, fc2_padded_bytes=FC2_BYTES + TAIL_BYTES,
            bytes=BANK_BYTES, sha256=bank_digest.hexdigest(), synthetic=False,
            source_gate_up_layout="concatenated", packed_gate_up_layout="interleaved",
            approximate_quantization=True, readback_sha256=readback.hexdigest(), readback_verified=True,
            scope="real approximate routed-expert weights; live operator arithmetic and draft quality unqualified"))
        candidate["geometry"] = graph.derive_geometry(candidate)
        candidate["expert_diagnostics"] = dict(path=str(journal), experts=EXPERTS,
                                               sha256=journal_digest.hexdigest(), readback_verified=True)
        # Windows rename refuses an existing target. Partial bytes survive every
        # earlier failure, while the final name exists only after all seals pass.
        partial.rename(bank)
        result = candidate
    except BaseException as exc:
        result["passed"] = False
        result["failed_stage"] = result["stage"]
        result["stage"] = "failed"
        result["error"] = type(exc).__name__ + ": " + str(exc)
    finally:
        cleanup_errors = []
        for handle in reversed(handles):
            try:
                handle.close()
            except BaseException as exc:
                cleanup_errors.append(type(exc).__name__ + ": " + str(exc))
        result["dll_directory_handles_closed"] = not cleanup_errors
        if cleanup_errors:
            result.update(passed=False, stage="failed", cleanup_errors=cleanup_errors)
        result["construction_host_seconds"] = time.perf_counter() - started
        result["native_lifetime_owner"] = "root-owned child process/job; process exit releases native modules"
        with report.open("x", encoding="utf-8") as stream:
            json.dump(result, stream, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
    print(json.dumps({key: value for key, value in result.items() if key != "frozen_inputs"}, indent=2), flush=True)
    return 0 if result["passed"] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root-owned-admission", action="store_true")
    parser.add_argument("--expected-probe-sha256", required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--bank", type=Path, required=True)
    parser.add_argument("--maximum-seconds", type=int, default=1800)
    args = parser.parse_args()
    if not args.root_owned_admission or os.name != "nt" or sys.version_info[:2] != (3, 12):
        raise ValueError("Root-owned Windows CPython3.12 guarded child required")
    if not 60 <= args.maximum_seconds <= 3600:
        raise ValueError("Construction deadline must be60..3600 seconds; hard timeout remains guard-owned")
    if len(args.expected_probe_sha256) != 64 or any(c not in "0123456789abcdef" for c in args.expected_probe_sha256):
        raise ValueError("Reviewed lowercase source SHA256 required")
    if Path(__file__).resolve().parent != SCRIPTS.resolve():
        raise ValueError("Frozen source must execute from its reviewed workspace path")
    return run(args, *fresh_outputs(args.report, args.bank))


if __name__ == "__main__":
    raise SystemExit(main())
