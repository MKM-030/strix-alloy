"""Root-owned strict Light QMoEBf admission of one frozen synthetic bank.

The single BF16 QMoEBf node has 512 experts/top10 and zero packed weights.
At most two calls share one session. This admits only the frozen synthetic
contract; it proves no Halogen quality, full MTP, internal kernel placement,
weight residency or speed gain. Root must enforce its exclusive owned job,
22-GiB initial/18-GiB continuous reserve and 90-second deadline, and hash the
complete bank before launch. This child does not rehash the 3-GB bank.
"""
import argparse
import ctypes
import faulthandler
import gc
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time

SELF = Path(__file__).resolve()
ROOT = SELF.parents[2]
LIGHT = "RyzenAILightExecutionProvider"
PACKAGE = Path(r"C:\Program Files\WindowsApps\MicrosoftCorporationII.WinML.AMD.NPU.EP.1.8_1.8.75.0_x64__8wekyb3d8bbwe")
LIBRARY = PACKAGE / "ExecutionProvider/onnxruntime_providers_ryzenai.dll"
LIBRARY_SHA256 = "ccc3bd0c2a8f519f9cd5fb112491785918810819f80c804302f717d2a93456ec"
PACKAGE_MANIFEST_SHA256 = "0a1e15844043769d095bc70a808bbdff9d30c389182b61ddb7d61a7b6a8809a3"
EP_COPY = Path(r"C:\AI\halogen-mtp-npu\npu-ep-1.8.75-20261004")
RUNTIME = Path(r"C:\AI\runtimes\winml-npu")
RUNTIME_EXE = RUNTIME / "Scripts/python.exe"
ORT_STAGE = ROOT / "server/.local/optimization9h-20261004/qmoe-ort129-stage-f1e210f85e8e4f609aa66df0b80e5495"
ORT_STAGE_MANIFEST = ORT_STAGE / "stage-manifest.json"
ORT_STAGE_MANIFEST_SHA256 = "3760ee417baa2ecea0d5c8921f3a80568483a28cd1b24479f9ef4f8b8583216f"
ORT_STAGE_TREES = ("onnxruntime", "onnxruntime-1.29.0.dist-info")
ORT_DONOR = Path(r"C:\AI\runtimes\qwen3-tts\.venv\Lib\site-packages")
FAULT_LIBRARY = ROOT / "server/.local/optimization9h-20261004/qmoe-fault-capture-build/halogen_qmoe_fault_capture.dll"
FAULT_LIBRARY_SHA256 = "c75b93bb3a13a357df545f0e5261f2a54eead53ca26d3e540c9ae7d70017064d"
BANK_BYTES = 2_986_344_448
BANK_SHA256 = "05283a60ce7858fdfa93d46ce84e86a5a38d5bbe46631e8571d2ff632890365f"
BF16 = 16
FLOAT = 1
OUTPUT_BYTES = 5120
MAX_CALLS = 2
MANIFEST_SHA256 = "9f694e76125cef522e90df002bd010a28efb6fbf78ccd117e0cc0dcae83d5b54"
BUILDER_SOURCE_SHA256 = "38d777a095f386c778b66ef90722bbaf36478e9cc919061ab945a2d96396cfbc"
PROTOBUF_SOURCE = ROOT / "server/.local/optimization9h-20261004/qmoe-source-only/ryzenai_onnx_utils__proto__external_data_pb2.py"
PROTOBUF_SOURCE_SHA256 = "11535c7348e169fd16fbda6da598281f8ee68b190f491b2e426358216f450d33"
OPTION_SOURCE = "https://huggingface.co/amd/gpt-oss-20B_eager_rai_1.8.0_npu_16K/resolve/bcbb238a3e7e1c11fcac9850bde957e34eb51ebd/genai_config.json"
DEPENDENCIES = {
    "scripts/benchmarks/halogen_qmoe_fault_capture.c": "ebe093f7b7efc652f0accea8bf8c07be56284911acc7b6ae9a4f5ca738b8dc6d",
    "scripts/benchmarks/halogen_npu_light_ep_admission_probe.py": "401ea8c9c83758568f19b7e07e3bf128b2d194d79fc01861355b53ca0ad89100",
    "scripts/benchmarks/halogen_npu_expert_onnx.py": "900a4deb32b86a48c6c132bf1326a3174bc5ef11482fd88b98005d0c40a4b722",
    "scripts/benchmarks/hgn_q4c_slice.py": "fe0dd1b9974f95bed02f37dddde1ee7c286f3f69d491548008d4a94ea703fdce",
    "server/host_frames.py": "417e33060ce6bc5b8f336f9e90282012a4a0e12475a13ad1dba20eec2df8bdf8",
}
RUNTIME_FILES = {
    "Scripts/python.exe": "0b471133e110cfb53a061cad528ce8e517d7b9ac41a0a396c39ad795a487fc14",
    "pyvenv.cfg": "bfcf9bd909509a16852041f05e5578c4d242f5b48811e8a8eaa4fea5065031e0",
    "Lib/site-packages/numpy/__init__.py": "a6958cb364663b7acce81ccfd58eeb65a2b34d5376157f924777b97211a73be4",
    "Lib/site-packages/onnx/__init__.py": "02bc0a45980ba519e8b322a50f1b9fc6e95b482d868cc0a13e869d0493b50f2c",
    "Lib/site-packages/onnxruntime/__init__.py": "53250ff546a968aea22e671744d5616304a87a861f17195e443b4546ed9eab53",
    "Lib/site-packages/onnxruntime/capi/onnxruntime_inference_collection.py": "91b4233708e960df90e069ae03fea58b83e313c90ad4afd79ad05ae84ccf91a7",
    "Lib/site-packages/onnxruntime/capi/onnxruntime_pybind11_state.pyd": "f7f09ee4fcb8a24094ccc4cdd1e13b548d72e82594b3c1972030720848d4dc3a",
    "Lib/site-packages/winui3/microsoft/windows/applicationmodel/dynamicdependency/bootstrap/__init__.py": "4d8cd8426c72c42c55273d25fdffffc4d30404d6a7bfa5dce2e92200bf85d8cd",
    "Lib/site-packages/winui3/_winui3_microsoft_windows_applicationmodel_dynamicdependency_bootstrap.cp312-win_amd64.pyd": "b5aa00e3a64a288d168f0569f1a7b20d04431463f786b6afa039110e42c27b8a",
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            value.update(chunk)
    return value.hexdigest()


def plain_path(path):
    path = Path(path).absolute()
    for entry in (path, *path.parents):
        info = entry.lstat()
        require(not entry.is_symlink() and not getattr(info, "st_file_attributes", 0) & 0x400,
                "Reparse path is not admitted: " + str(entry))
    return path.resolve(strict=True)


def json_safe(value):
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    return value


def verify_ort_stage(args):
    require(not any(name == "onnxruntime" or name.startswith("onnxruntime.") for name in sys.modules),
            "ORT must not be imported before sealed package selection")
    require(sys.implementation.name == "cpython" and sys.version_info[:2] == (3, 12)
            and sys.maxsize > 2**32, "Staged binding requires 64-bit CPython 3.12")
    manifest_path = plain_path(args.ort_stage_manifest)
    require(manifest_path == plain_path(ORT_STAGE_MANIFEST)
            and args.expected_ort_stage_manifest_sha256.lower() == ORT_STAGE_MANIFEST_SHA256
            and manifest_path.stat().st_size < 1 << 20
            and digest(manifest_path) == ORT_STAGE_MANIFEST_SHA256,
            "Root-reviewed ORT stage manifest changed")
    sealed = json.loads(manifest_path.read_text(encoding="utf-8"))
    site = plain_path(ORT_STAGE / "site-packages")
    require(sealed["schema"] == "halogen_qmoe_ort_stage_v1" and sealed["completed"] is True
            and sealed["package_name"] == "onnxruntime" and sealed["package_version"] == "1.29.0"
            and sealed["wheel_tag"] == "cp312-cp312-win_amd64" and sealed["c_api_max_version"] == 29
            and sealed["trees"] == list(ORT_STAGE_TREES)
            and plain_path(sealed["stage_root"]) == plain_path(ORT_STAGE)
            and plain_path(sealed["site_packages"]) == site
            and Path(sealed["donor_site_packages"]) == ORT_DONOR,
            "Unexpected complete ORT stage identity")
    require(sealed["donor_preserved"] is True and sealed["old_winml_environment_modified"] is False
            and sealed["staged_files_read_only"] is True
            and sealed["file_count"] == len(sealed["files"]) == 630,
            "ORT stage copy is incomplete")
    expected, total_bytes = set(), 0
    for row in sealed["files"]:
        relative = Path(row["relative_path"])
        require(not relative.is_absolute() and relative.parts and relative.parts[0] in ORT_STAGE_TREES
                and all(part not in (".", "..") for part in relative.parts)
                and relative.as_posix() not in expected, "Invalid or duplicate staged path")
        target = plain_path(site / relative)
        require(target.is_relative_to(site) and Path(row["staged_path"]) == target
                and Path(row["donor_path"]) == ORT_DONOR / relative,
                "Stage inventory path differs")
        require(target.stat().st_size == row["bytes"]
                and digest(target) == row["staged_sha256"] == row["donor_sha256"]
                and getattr(target.stat(), "st_file_attributes", 0) & 1,
                "Sealed ORT package file changed: " + relative.as_posix())
        expected.add(relative.as_posix())
        total_bytes += row["bytes"]
    actual = set()
    for entry in site.rglob("*"):
        plain_path(entry)
        if entry.is_file():
            actual.add(entry.relative_to(site).as_posix())
    require(actual == expected and total_bytes == sealed["total_bytes"] == 45_280_440,
            "Sealed ORT file set or total size changed")
    require({entry.name for entry in ORT_STAGE.iterdir()} == {"site-packages", "stage-manifest.json"},
            "Unexpected entry in sealed ORT stage")
    return dict(manifest_path=str(manifest_path), manifest_sha256=ORT_STAGE_MANIFEST_SHA256,
                site_packages=str(site), package_version="1.29.0", c_api_max_version=29,
                file_count=len(expected), total_bytes=total_bytes,
                complete_package_verified_before_import=True)


def verify_sources(args):
    require(digest(SELF) == args.expected_source_sha256.lower(), "Root-reviewed probe source changed")
    require(plain_path(sys.executable) == plain_path(RUNTIME_EXE), "Use the pinned WinML runtime")
    require(sys.byteorder == "little", "Bounded BF16 decoding requires little endian host")
    actual = {name: digest(ROOT / name) for name in DEPENDENCIES}
    require(actual == DEPENDENCIES, "Pinned helper source changed")
    runtime_hashes = {name: digest(RUNTIME / name) for name in RUNTIME_FILES}
    require(runtime_hashes == RUNTIME_FILES, "Pinned runtime dependency changed")
    ort_stage_pins = verify_ort_stage(args)
    require(plain_path(FAULT_LIBRARY).stat().st_size == 31744
            and digest(FAULT_LIBRARY) == FAULT_LIBRARY_SHA256,
            "Root-reviewed native fault collector changed")
    require(digest(PACKAGE / "AppxManifest.xml") == PACKAGE_MANIFEST_SHA256,
            "Installed provider package manifest changed")
    require(digest(LIBRARY) == LIBRARY_SHA256 and LIBRARY.stat().st_size == 4368688,
            "Installed Light provider changed")
    model_path, manifest_path = plain_path(args.model), plain_path(args.manifest)
    require(manifest_path.stat().st_size < 1 << 20, "Builder manifest is unbounded")
    require(digest(manifest_path) == MANIFEST_SHA256, "Frozen builder manifest changed")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    require(manifest["schema"] == "halogen_qmoe_graph_v1", "Unknown QMoEBf builder manifest")
    require(manifest["builder_source_sha256"] == BUILDER_SOURCE_SHA256
            and digest(ROOT / "scripts/benchmarks/halogen_qmoe_graph.py") == BUILDER_SOURCE_SHA256,
            "Frozen graph builder source changed")
    require(manifest["protobuf_source_sha256"] == PROTOBUF_SOURCE_SHA256
            and digest(PROTOBUF_SOURCE) == PROTOBUF_SOURCE_SHA256,
            "Frozen official header schema source changed")
    require(model_path == plain_path(manifest["graph_path"]), "Model is not the frozen builder artifact")
    require(model_path.stat().st_size < 1 << 20 and digest(model_path) == manifest["graph_sha256"],
            "Frozen graph changed")
    header_path = plain_path(manifest["header_path"])
    require(header_path.stat().st_size < 1 << 20 and digest(header_path) == manifest["header_sha256"],
            "Frozen external header changed")
    bank_path = plain_path(manifest["bank_path"])
    require(bank_path.parent == header_path.parent == model_path.parent and bank_path.stat().st_size == BANK_BYTES
            and manifest["bank_bytes"] == BANK_BYTES and manifest["bank_sha256"] == BANK_SHA256,
            "Frozen synthetic bank identity/size changed")
    require(manifest["passed"] is True and manifest["bank_synthetic"] is True,
            "Only the completed frozen synthetic bank is admitted")
    pack_receipt = plain_path(manifest["pack_receipt_path"])
    require(pack_receipt.stat().st_size < 1 << 20
            and digest(pack_receipt) == manifest["pack_receipt_sha256"],
            "Frozen owned packing receipt changed")
    require(manifest["bank_hash_verified_by_builder"] is False,
            "Bank hash scope changed; root guard must verify the complete bank")
    return manifest, model_path, header_path, dict(
        dependencies=actual, runtime=runtime_hashes, ort_stage=ort_stage_pins,
        fault_collector_library=str(FAULT_LIBRARY), fault_collector_sha256=FAULT_LIBRARY_SHA256,
        builder_manifest_sha256=MANIFEST_SHA256,
        builder_source_sha256=BUILDER_SOURCE_SHA256, protobuf_source_sha256=PROTOBUF_SOURCE_SHA256,
        graph_sha256=manifest["graph_sha256"], header_sha256=manifest["header_sha256"],
        pack_receipt_sha256=manifest["pack_receipt_sha256"],
        bank_path=str(bank_path), bank_bytes=BANK_BYTES, bank_sha256_expected=BANK_SHA256,
        bank_hash_verified_by_child=False, bank_hash_scope="whole-bank hash belongs to root guard")


def graph_contract(model, manifest, onnx):
    require(len(model.graph.node) == 1, "Frozen graph must contain exactly one node")
    node = model.graph.node[0]
    require(node.domain == "com.ryzenai" and node.op_type == "QMoEBf"
            and len(node.input) == 15 and len(node.output) == 1,
            "Expected exactly one 15-slot com.ryzenai::QMoEBf")
    require([v.version for v in model.opset_import if v.domain == "com.ryzenai"] == [1],
            "Custom domain opset changed")
    attributes = {v.name: onnx.helper.get_attribute_value(v) for v in node.attribute}
    attributes = {k: v.decode("utf-8") if isinstance(v, bytes) else v for k, v in attributes.items()}
    require(attributes.get("num_experts") == 512 and attributes.get("k") == 10,
            "Only the frozen 512-expert/top10 bank is admitted")
    expected = manifest["node"]
    require(node.name == expected["name"] and list(node.input) == expected["inputs"]
            and list(node.output) == expected["outputs"] and attributes == expected["attributes"],
            "Graph node differs from frozen manifest")

    def entries(values):
        answer = []
        for value in values:
            tensor = value.type.tensor_type
            shape = []
            for dimension in tensor.shape.dim:
                require(dimension.HasField("dim_value") and dimension.dim_value > 0,
                        "Only exact positive static I/O shapes are admitted")
                shape.append(dimension.dim_value)
            answer.append(dict(name=value.name, element_type=tensor.elem_type, shape=shape))
        return answer

    inputs, outputs = entries(model.graph.input), entries(model.graph.output)
    require(len(inputs) == 2 and len(outputs) == 1, "Frozen graph I/O count changed")
    activation = [v for v in inputs if v["element_type"] == BF16 and v["shape"] == [1, 2560]]
    router = [v for v in inputs if v["element_type"] in (FLOAT, BF16) and v["shape"] == [1, 512]]
    require(len(activation) == len(router) == 1 and outputs[0]["element_type"] == BF16
            and outputs[0]["shape"] == [1, 2560], "Frozen BF16 activation/router/output contract changed")
    names = {FLOAT: "float32", BF16: "bfloat16"}
    declared = dict(inputs=[dict(name=v["name"], dtype=names[v["element_type"]], shape=v["shape"]) for v in inputs],
                    outputs=[dict(name=v["name"], dtype=names[v["element_type"]], shape=v["shape"]) for v in outputs])
    require(declared == manifest["io"], "Static graph I/O differs from manifest")
    return activation[0], router[0], outputs[0], attributes


def run(args):
    require(not args.report.exists() and args.report.parent.is_dir(),
            "Report must be a fresh file in an existing root-owned directory")
    plain_path(args.report.parent)
    require(not list(args.report.parent.glob(args.report.name + ".ort-profile*")),
            "Profiling output prefix must also be fresh")
    result = dict(schema=1, passed=False, scope="frozen synthetic zero-bank 512-expert/top10 QMoEBf strict admission only",
                  source_sha256=digest(SELF), provider_requested=LIGHT, provider_options={},
                  cpu_fallback_allowed=False, automatic_acquisition_allowed=False,
                  call_count=0, completed_calls=0, calls=[], session_creations=0, stages=[],
                  full_mtp_support_proven=False, internal_placement_proven=False,
                  weight_residency_proven=False, quality_proven=False, speed_gain_established=False,
                  timing_scope="synthetic admission host calls only; no inference throughput or speed gain")
    runtime = session = options = devices = all_devices = dll_directory = ort_dll_directory = ort = None
    feed = outputs = output = x_storage = router_storage = actual = model = None
    registered = profile_finished = False
    fault_library, fault_armed = None, False
    memory_samples, cleanup_errors = [], []

    def stage(name):
        result["stage"] = name
        result["stages"].append(dict(stage=name, epoch_ns=time.time_ns(), qpc=time.perf_counter()))
        print("QMOE_STAGE " + name, flush=True)

    try:
        stage("source_and_artifact_validation")
        require(all(os.environ.get(name) == "1" for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")),
                "Set all three BLAS/OpenMP thread variables to 1 before Python starts")
        manifest, model_path, header_path, pins = verify_sources(args)
        result["pins"] = pins
        # Select the complete sealed package while retaining the pinned old
        # interpreter, NumPy, ONNX and WinUI dependencies in site-packages.
        sys.path.insert(0, pins["ort_stage"]["site_packages"])
        sys.path.insert(0, str(ROOT / "server"))
        from host_frames import frame

        def reserve(phase, minimum_gib=18):
            current = frame()
            memory_samples.append(dict(phase=phase, **current))
            require(min(current["available_bytes"], current["commit_headroom_bytes"]) >= minimum_gib * 1024**3,
                    "Physical/commit reserve below " + str(minimum_gib) + " GiB")

        reserve("admission", 22)
        stage("static_graph_validation")
        import numpy as np
        import onnx
        from halogen_npu_expert_onnx import verified_provider_copy
        require(Path(np.__file__).resolve() == (RUNTIME / "Lib/site-packages/numpy/__init__.py").resolve()
                and Path(onnx.__file__).resolve() == (RUNTIME / "Lib/site-packages/onnx/__init__.py").resolve(),
                "Imported graph/tensor modules differ from pinned runtime")
        model = onnx.load(str(model_path), load_external_data=False)
        activation, router, output_contract, attributes = graph_contract(model, manifest, onnx)
        result.update(input_contract=[activation, router], output_contract=output_contract,
                      custom_node_attributes=attributes)
        stage("provider_copy_validation")
        chosen_library, verified_files = verified_provider_copy(LIBRARY, EP_COPY)
        require(digest(chosen_library) == LIBRARY_SHA256, "Verified copy is not the pinned Light library")
        result.update(provider_library=str(chosen_library), provider_library_sha256=LIBRARY_SHA256,
                      provider_copy_files=verified_files)
        expected_options = {"external_data_file": header_path.name,
                            "hybrid_opt_token_backend": "npu",
                            "hybrid_opt_qmoe_dynamic_experts": "0",
                            "hybrid_opt_qmoe_num_dynamic_layers": "0"}
        require(manifest["provider_options"] == expected_options,
                "Source-confirmed frozen provider options changed")
        provider_options = dict(expected_options, external_data_file=str(header_path))
        result["provider_options"] = provider_options
        result["provider_option_source"] = OPTION_SOURCE
        reserve("before_registration")
        stage("winml_bootstrap")
        from winui3.microsoft.windows.applicationmodel.dynamicdependency.bootstrap import initialize
        runtime = initialize()
        dll_directory = os.add_dll_directory(str(chosen_library.parent))
        stage("sealed_ort_validation_before_import")
        result["ort_stage"] = verify_ort_stage(args)
        ort_dll_directory = os.add_dll_directory(str(ORT_STAGE / "site-packages/onnxruntime/capi"))
        stage("provider_registration")
        import onnxruntime as ort
        require(ort.__version__ == ort.get_version_string() == "1.29.0" and Path(ort.__file__).resolve()
                == (ORT_STAGE / "site-packages/onnxruntime/__init__.py").resolve(),
                "Expected sealed complete ORT 1.29.0 package")
        binding = sys.modules["onnxruntime.capi.onnxruntime_pybind11_state"]
        require(Path(binding.__file__).resolve()
                == (ORT_STAGE / "site-packages/onnxruntime/capi/onnxruntime_pybind11_state.pyd").resolve(),
                "Imported ORT binding is not the sealed API29 candidate")
        result["ort_binding_path"] = str(Path(binding.__file__).resolve())
        binding = None
        result["ort_version"] = ort.__version__
        ort.register_execution_provider_library(LIGHT, str(chosen_library))
        registered = True
        stage("npu_device_selection")
        all_devices = ort.get_ep_devices()
        result["advertised_ep_devices"] = [dict(ep_name=d.ep_name, device_type=str(d.device.type)) for d in all_devices]
        devices = [d for d in all_devices if d.ep_name == LIGHT and d.device.type == ort.OrtHardwareDeviceType.NPU]
        all_devices = None
        require(len(devices) == 1, "Expected exactly one pinned Light NPU device")
        options = ort.SessionOptions()
        # Official OGA v0.14.0 adds this session key before SetupProvider;
        # the frozen Header binds its bank by a sibling relative basename.
        # This is one initialization candidate, not a proven crash remedy.
        model_root = str(model_path.parent)
        options.add_session_config_entry("model_root", model_root)
        result["session_model_root"] = model_root
        print("QMOE_MODEL_ROOT " + model_root, flush=True)
        options.intra_op_num_threads = options.inter_op_num_threads = 1
        options.enable_profiling = True
        options.profile_file_prefix = str(args.report.parent / (args.report.name + ".ort-profile"))
        options.add_provider_for_devices(devices, provider_options)
        options.add_session_config_entry("session.disable_cpu_ep_fallback", "1")
        # EP factory registration and custom-operator schema registration are
        # separate APIs. This same pinned DLL exports standard RegisterCustomOps.
        stage("custom_operator_registration")
        options.register_custom_ops_library(str(chosen_library))
        result["custom_ops_library"] = str(chosen_library)
        result["custom_ops_library_sha256"] = LIBRARY_SHA256
        reserve("before_session")
        stage("strict_session_admission")
        result["session_creations"] += 1
        started = time.perf_counter_ns()
        try:
            session = ort.InferenceSession(str(model_path), sess_options=options, enable_fallback=False)
            session.disable_fallback()
        finally:
            result["initialization_ms"] = (time.perf_counter_ns() - started) / 1e6
        result["session_providers"] = session.get_providers()
        reserve("after_session")
        stage("native_fault_capture_arm")
        fault_path = args.report.parent / "native-fault.jsonl"
        require(not fault_path.exists(), "Native fault metadata must be fresh")
        fault_library = ctypes.CDLL(str(FAULT_LIBRARY))
        fault_library.start_capture.argtypes = [ctypes.c_wchar_p]
        fault_library.start_capture.restype = ctypes.c_uint32
        fault_library.stop_capture.argtypes = []
        fault_library.stop_capture.restype = ctypes.c_uint32
        require(fault_library.start_capture(str(fault_path.resolve())) == 0,
                "Native fault metadata collector did not arm")
        fault_armed = True
        result["native_fault_metadata"] = dict(path=str(fault_path),
            collector_sha256=FAULT_LIBRARY_SHA256, record_limit=8, record_byte_limit=8192,
            scope="exception metadata and arm-time module snapshot; no payload or performance evidence")
        print("QMOE_SESSION_PROVIDERS " + json.dumps(result["session_providers"]), flush=True)
        stage("synthetic_admission_calls")
        for index in range(MAX_CALLS):
            reserve("before_call_" + str(index))
            stage("synthetic_call_" + str(index) + "_prepare")
            prepare_started = time.perf_counter_ns()
            x_storage = np.full(activation["shape"], 0x3F80 if index == 0 else 0x4000, dtype=np.uint16)
            scores = np.zeros(router["shape"], dtype=np.float32)
            first_expert = 0 if index == 0 else 502
            scores[0, first_expert:first_expert + 10] = np.arange(10, 0, -1, dtype=np.float32) / 10
            router_storage = scores if router["element_type"] == FLOAT else (scores.view(np.uint32) >> 16).astype(np.uint16)
            feed = {activation["name"]: ort.OrtValue.ortvalue_from_numpy_with_onnx_type(x_storage, BF16)}
            feed[router["name"]] = (ort.OrtValue.ortvalue_from_numpy(router_storage)
                                    if router["element_type"] == FLOAT else
                                    ort.OrtValue.ortvalue_from_numpy_with_onnx_type(router_storage, BF16))
            started = time.perf_counter_ns()
            row = dict(call_index=index, scope="synthetic zero-bank admission; no speed gain",
                       routed_fixture_experts=list(range(first_expert, first_expert + 10)),
                       prepare_ms=(started - prepare_started) / 1e6, passed=False)
            result["calls"].append(row)
            result["call_count"] += 1
            stage("synthetic_call_" + str(index) + "_invoke")
            try:
                outputs = session.run_with_ort_values([output_contract["name"]], feed)
            finally:
                row["host_session_call_ms"] = (time.perf_counter_ns() - started) / 1e6
            result["completed_calls"] += 1
            stage("synthetic_call_" + str(index) + "_returned")
            require(len(outputs) == 1, "Expected one bounded BF16 output")
            output = outputs[0]
            require(output.device_name() == "cpu" and output.element_type() == BF16
                    and list(output.shape()) == output_contract["shape"],
                    "Returned output is not the expected CPU BF16 geometry")
            require(math.prod(output.shape()) * 2 == OUTPUT_BYTES and output.data_ptr() > 0,
                    "Returned BF16 buffer exceeds exact 5120-byte bound")
            # Keep both the output OrtValue and its returned list alive during this copy.
            raw = ctypes.string_at(output.data_ptr(), OUTPUT_BYTES)
            actual = (np.frombuffer(raw, dtype="<u2").astype(np.uint32) << 16).view(np.float32)
            row.update(output_bytes=OUTPUT_BYTES, output_shape=list(output.shape()), output_element_type=BF16,
                       output_device=output.device_name(), output_sha256=hashlib.sha256(raw).hexdigest(),
                       finite=bool(np.isfinite(actual).all()), zero_output=bool((actual == 0).all()))
            row["passed"] = row["finite"] and row["zero_output"]
            require(row["passed"], "Frozen zero-bank output is not finite zeros")
            stage("synthetic_call_" + str(index) + "_validated")
            feed = outputs = output = x_storage = router_storage = actual = None
            reserve("after_call_" + str(index))
        stage("profile_attribution")
        profile = Path(session.end_profiling())
        profile_finished = True
        events = json.loads(profile.read_text(encoding="utf-8"))
        nodes = [v for v in events if v.get("cat") == "Node"]
        kernels = [v for v in nodes if str(v.get("name", "")).endswith("_kernel_time")]
        executed = sorted({v.get("args", {}).get("provider", "<missing>") for v in kernels})
        other = [v for v in nodes if v.get("args", {}).get("provider") not in (None, LIGHT)]
        result.update(profile=str(profile), profile_sha256=digest(profile), node_events=len(nodes),
                      kernel_events=len(kernels), executed_kernel_providers=executed)
        require(kernels and executed == [LIGHT] and not other,
                "Profile does not prove exclusive Light ORT kernel attribution")
        require(result["completed_calls"] == MAX_CALLS and all(v["passed"] for v in result["calls"]),
                "Frozen synthetic admission gate failed")
        result["passed"] = True
    except Exception as exc:
        result.update(error=type(exc).__name__ + ": " + str(exc), failed_at_stage=result.get("stage"))
    finally:
        stage("cleanup")
        if fault_armed:
            try:
                require(fault_library.stop_capture() == 0, "Native fault collector stop failed")
                result["native_fault_collector_stopped"] = True
            except Exception as exc:
                cleanup_errors.append("native fault collector stop: " + str(exc))
        if session is not None and not profile_finished:
            try:
                result["partial_profile"] = str(session.end_profiling())
            except Exception as exc:
                result["partial_profile_error"] = type(exc).__name__ + ": " + str(exc)
        session = options = devices = all_devices = feed = outputs = output = None
        x_storage = router_storage = actual = model = None
        gc.collect()
        result["session_device_options_released_before_unregister"] = True
        if registered:
            try:
                ort.unregister_execution_provider_library(LIGHT)
                result["provider_unregistered"] = True
            except Exception as exc:
                cleanup_errors.append("provider unregister: " + str(exc))
        if dll_directory is not None:
            try:
                dll_directory.close()
                result["dll_directory_closed"] = True
            except Exception as exc:
                cleanup_errors.append("DLL directory close: " + str(exc))
        if ort_dll_directory is not None:
            try:
                ort_dll_directory.close()
                result["ort_dll_directory_closed"] = True
            except Exception as exc:
                cleanup_errors.append("ORT DLL directory close: " + str(exc))
        if runtime is not None:
            try:
                runtime()
                result["bootstrap_shutdown"] = True
            except Exception as exc:
                cleanup_errors.append("bootstrap shutdown: " + str(exc))
        result["reserve_samples"] = memory_samples
        if memory_samples:
            result.update(minimum_available_gib=min(v["available_bytes"] for v in memory_samples) / 1024**3,
                          minimum_commit_headroom_gib=min(v["commit_headroom_bytes"] for v in memory_samples) / 1024**3)
        if cleanup_errors:
            result.update(passed=False, cleanup_errors=cleanup_errors)
        stage("synthetic_admission_passed" if result["passed"] else "failed")
        with args.report.open("x", encoding="utf-8") as output_file:
            json.dump(json_safe(result), output_file, indent=2, allow_nan=False)
            output_file.write("\n")
    return result


def main():
    # Native access violations bypass Python finally/report serialization.
    # Persist stage markers and a Python stack in the owned child logs.
    faulthandler.enable(all_threads=True)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--expected-source-sha256", required=True)
    parser.add_argument("--ort-stage-manifest", type=Path, required=True)
    parser.add_argument("--expected-ort-stage-manifest-sha256", required=True)
    parser.add_argument("--root-owned-admission", action="store_true", required=True)
    args = parser.parse_args()
    result = run(args)
    print(json.dumps(json_safe({key: value for key, value in result.items()
                               if key not in ("provider_copy_files", "reserve_samples", "pins")}),
                     indent=2, allow_nan=False))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
