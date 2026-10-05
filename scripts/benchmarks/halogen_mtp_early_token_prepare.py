"""Root-only token14367 lineage gate and offline embedding preparation.

Prepare-only reads sealed JSON/source files, never tensor payloads. Export first
requires the separate original-table gather capture and root's independently
sealed owned-process/checkpoint provenance. One raw-word mismatch stops before
RMS/FC. Existing BF16/RMS helpers and retained e-FC assets are reused. Hidden
assets, engine, provider, compiler and inference are never opened or executed.
The materialized CPU algebra is a fixture, not a live early producer or timing.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import stat


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
WORK = ROOT / "server/.local/optimization9h-20261004"
ASSETS = Path(r"C:\AI\halogen-mtp-npu\v2-d-prepare-20261004")
BUILDER_SHA = "6334b32fc8a9a5cb792590d0422c0ee1fb532a7c475785f75979962ec80c2544"
EMBEDDING_SHA = "408d29273a4d737b7a0d7596f07f0f5c122d8298bcc497ffc86dd22a67def1e3"
WEIGHTS_SHA = "dbf679c94c75439638b01058c2c6915d43dd211c69b27918f7caa77d826e8fb7"
FC_RECEIPT = WORK / "alloy-fc-original-06875d9ccbb548b3affac7128cb0788a/native/replay.json"
FC_RECEIPT_SHA = "2fb0f6a198581156e430301064acef3e41d10a99e0a0cd06ab5ae9a16b8ed5fb"
ENGINE_SHA = "ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b"
HEAD_SHA = "132f2da76d86694ffe5f120d61e304e57c685f3db72935c6d5e61bf7b0d5cc20"
CHECKPOINT_SHA = "71246c6ab3fc1de2cf06326f18e275fe9c2a18366d646ed3357d194c884fc687"
GATHER_SOURCE = HERE / "halogen0162_raw_embedding_capture.c"
TOKEN, WIDTH, ROW_BYTES = 14367, 2560, 5120
RAW_SHA = "af284c0101ac76b7562b3d9e19cfc6721266f282358d8f313a09b961435ee374"
NORM_SHA = "97079c27ab56da44c2ab29780c856be79803d402caf754acfbf7d187fbe34892"
GAMMA_SHA = "04c4a570850e06f2d8913da8220d54d4c7f87db6eb6d45480b938e8ba41d6a86"
RMS_WINDOW = WORK / "alloy-rocr-component-16a35be771404bd7a7ac3d1b43526528"
RMS_PROBE = RMS_WINDOW / "stock/result/probe.json"
RMS_PROBE_SHA = "421b0f484f5364a3b71938729e78a4ef98f6eefa94ee4d8ba7d279ca42c41790"
RMS_OWNED = RMS_WINDOW / "stock/owned-result.json"
RMS_OWNED_SHA = "350fdbddc0faa56bdaa1a689d0617b18fd7bb48b7f7cb64ace81917a68925d34"
RMS_OUTER = RMS_WINDOW / "result.json"
RMS_OUTER_SHA = "7e1a0f5b1dcfd122d65f88db6d6dda43d0bbd2634adaf3cd7b4f21bb69e1e3b8"
RMS_FIXTURES = WORK / "embedding-rms-fixtures-78c49b8e265c4de9adb9c0cf3cc8254e/fixtures.json"
RMS_FIXTURES_SHA = "cf7ae0ed36d323ae32b6664ed080bc2b3cdd44863878d51719b53ddef9f72246"
RMS_SOURCE = HERE / "halogen_rocr_poll_backoff_probe.py"
RMS_SOURCE_SHA = "9b2f6dd62162cbed8ea51f767e018c787a69ebf03fa6e4cc8b6ef153fdf83f52"
RMS_CODE_SHA = "45941c0579dc3487d07978a50c85cbaa141bbb674b225e708e82d81397334a83"
RMS_ROW_HASHES = {
    "A": dict(raw=RAW_SHA, normalized=NORM_SHA),
    "B": dict(raw="e14b7e6b5bd1a53d1e0c26d0eb9d2356728668a89a2e591707c463cc1e2b01b4",
              normalized="8104e72375af48ab130c04b01fe68399e1d6c84951f9aa45c67a54b7d00db6ce"),
}
CPU_TOLERANCE = dict(rtol=.002, atol=.0002)
NPU_TOLERANCE = dict(rtol=.03, atol=.003)
MAX_JSON, MAX_TILE = 2 << 20, 8 << 20


def sha(value):
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError("independent lowercase SHA256 required")
    return value


def captured(path, size, expected, offset=0, total=None):
    """Bind selected bytes, path/handle identity and each API's ctime stability."""
    path = Path(path)
    before = path.lstat()
    extent = size if total is None else total
    if (not stat.S_ISREG(before.st_mode) or before.st_size != extent or
            not 0 < size <= MAX_TILE or not 0 <= offset <= extent - size):
        raise ValueError("bounded regular file/selected extent differs: " + str(path))
    fields = ("st_size", "st_dev", "st_ino", "st_mtime_ns")
    fields += ("st_birthtime_ns",) if os.name == "nt" else ("st_ctime_ns",)
    identity = lambda value: tuple(getattr(value, field, None) for field in fields)
    with path.open("rb") as stream:
        opened = os.fstat(stream.fileno())
        stream.seek(offset)
        raw = stream.read(size)
        after = os.fstat(stream.fileno())
    end = path.lstat()
    if (not identity(before) == identity(opened) == identity(after) == identity(end) or
            before.st_ctime_ns != end.st_ctime_ns or opened.st_ctime_ns != after.st_ctime_ns or
            len(raw) != size or hashlib.sha256(raw).hexdigest() != sha(expected)):
        raise ValueError("selected bytes/hash/file identity differ: " + str(path))
    return raw


def source_hash(path):
    path = Path(path)
    size = path.lstat().st_size
    if not 0 < size <= MAX_JSON:
        raise ValueError("bounded source/JSON required")
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    captured(path, size, digest)
    return digest


def read_json(path, expected):
    path = Path(path)
    size = path.lstat().st_size
    if not 0 < size <= MAX_JSON:
        raise ValueError("bounded JSON required")
    return json.loads(captured(path, size, expected))


def helper():
    if source_hash(HERE / "halogen_npu_v2_d_prepare.py") != BUILDER_SHA:
        raise ValueError("frozen BF16/RMS helper differs")
    import halogen_npu_v2_d_prepare as builder
    if Path(builder.__file__).resolve() != HERE / "halogen_npu_v2_d_prepare.py":
        raise ValueError("frozen helper import origin differs")
    return builder


def embedding_rms_qualification():
    """Bind previously executed frozen-row RMS using JSON/source only.

    No output, input, gamma, shader or engine payload is opened here. This
    proves the supplied A/B RMS boundary, never the native table/gather.
    """
    probe = read_json(RMS_PROBE, RMS_PROBE_SHA)
    owned = read_json(RMS_OWNED, RMS_OWNED_SHA)
    outer = read_json(RMS_OUTER, RMS_OUTER_SHA)
    fixtures = read_json(RMS_FIXTURES, RMS_FIXTURES_SHA)
    if source_hash(RMS_SOURCE) != RMS_SOURCE_SHA:
        raise ValueError("executed original embedding RMS source differs")
    required_probe = dict(schema="halogen.rocr-poll-backoff-component.v1", variant="stock", passed=True,
        warmup_per_fixture=8, repeats_per_fixture=64, tensor_bytes=ROW_BYTES, width=WIDTH, groups=1,
        grid=[1, 1, 1], block=[256, 1, 1], shared_bytes=0, input_output_alias=True,
        kernel_symbol="_ZN7halogen12_GLOBAL__N_117k_rmsnorm_groupedEPKtS2_Ptii", cleanup_errors=[],
        registered_callback_drain_confirmed=True, unsafe_object_teardown_skipped=False,
        process_exit_without_python_finalization=False)
    if any(probe.get(key) != value for key, value in required_probe.items()):
        raise ValueError("executed original embedding RMS dispatch/repeat/cleanup contract differs")
    bindings = probe["bindings"]
    for name, expected, extent in (("source", RMS_SOURCE_SHA, None), ("engine", ENGINE_SHA, 26052768),
            ("codeobject", RMS_CODE_SHA, 17704408), ("fixtures", RMS_FIXTURES_SHA, None),
            ("gamma", GAMMA_SHA, ROW_BYTES)):
        if bindings[name]["sha256"] != expected or (extent is not None and bindings[name]["bytes"] != extent):
            raise ValueError("executed original embedding RMS source/engine/shader/fixture/gamma binding differs")
    for name, expected in (("hip", "6f3c9fe6b655a611e04a9a5a157cb46c425717e2873973f11a67bb6bbf6587b5"),
            ("hsa", "1961df7d395b62d9b7c0086e0a247a02d0e97129eb9d8b28acb0e0a597e819f5"),
            ("bridge", "0de8e26350933754d3d9ead9446c39e04792a2bef68d1b6df97950d07312b9d6")):
        if (bindings[name]["sha256"] != expected or probe["mapped_before"][name] != bindings[name] or
                probe["mapped_after"][name] != bindings[name]):
            raise ValueError("executed original embedding RMS mapped runtime binding differs")
    if (fixtures.get("schema") != 1 or fixtures["gamma"] !=
            dict(file="raw-gamma.u16", bytes=ROW_BYTES, sha256=GAMMA_SHA) or
            [row["label"] for row in fixtures["rows"]] != ["A", "B"] or
            [row["label"] for row in probe["timings"]] != ["A", "B"]):
        raise ValueError("executed original embedding RMS frozen row/gamma identity differs")
    for fixture, observed in zip(fixtures["rows"], probe["timings"], strict=True):
        label = fixture["label"]
        expected = RMS_ROW_HASHES[label]
        for suffix, digest in (("input", expected["raw"]), ("numpy-rms", expected["normalized"]),
                               ("ort-rms", expected["normalized"])):
            name = label + "-" + suffix + ".u16"
            if fixture["files"][name] != dict(file=name, bytes=ROW_BYTES, sha256=digest):
                raise ValueError("frozen raw/NumPy/ORT embedding RMS hash differs")
        if (bindings[label + "_input"]["sha256"] != expected["raw"] or
                bindings[label + "_input"]["bytes"] != ROW_BYTES or
                fixture["fc_normalized_input_sha256"] != expected["normalized"] or
                observed["output_file"] != label + "-embedding-rms-u16.bin" or
                observed["output_sha256"] != expected["normalized"] or observed["exact_repeat_parity"] is not True):
            raise ValueError("executed raw-to-normalized embedding RMS hash/repeat parity differs")
        elapsed = observed["wall_launch_synchronize_us"]
        if len(elapsed) != 64 or any(type(value) not in (int, float) or not math.isfinite(value) or value < 0 for value in elapsed):
            raise ValueError("completed original embedding RMS repeat extent differs")
    required_owned = dict(variant="stock", passed=True, container_removed=True, job_closed=True,
        cleanup_pending=False, errors=[], exit_code=0, probe_receipt_sha256=RMS_PROBE_SHA,
        hsa_sha256=bindings["hsa"]["sha256"])
    required_outer = dict(schema="halogen.rocr-component-owned.v1", passed=True, contaminated=False,
        errors=[], probe_sha256=RMS_SOURCE_SHA, root_runtime_reviewed=True, colleague_preserved=True,
        monitor_stopped=True, controller_handle_closed=True, cleanup_pending=False)
    if (any(owned.get(key) != value for key, value in required_owned.items()) or
            any(outer.get(key) != value for key, value in required_outer.items()) or
            probe["image"] != outer["image"] or [row for row in outer["windows"] if row["variant"] == "stock"] != [owned] or
            owned["terminal_container_state"]["Running"] is not False or
            owned["terminal_container_state"]["ExitCode"] != 0 or
            owned["terminal_container_state"]["OOMKilled"] is not False or
            outer["minimum_physical_gib"] < 18 or outer["minimum_commit_gib"] < 18):
        raise ValueError("owned original embedding RMS exit/cleanup/reserve provenance differs")
    return dict(scope="original embedding RMS on two supplied frozen CPU raw rows; native table/gather unqualified",
        frozen_input_native_embedding_rms_qualified=True, original_kernel_output_repeat_parity=True,
        raw_gamma_sha256=GAMMA_SHA, frozen_rows=RMS_ROW_HASHES, source_sha256=RMS_SOURCE_SHA,
        receipt_bindings=[dict(path=str(path), sha256=digest) for path, digest in (
            (RMS_PROBE, RMS_PROBE_SHA), (RMS_OWNED, RMS_OWNED_SHA), (RMS_OUTER, RMS_OUTER_SHA),
            (RMS_FIXTURES, RMS_FIXTURES_SHA))],
        qualification_payload_bytes_read=0, gpu_executed_by_this_preparation=False,
        native_table_or_gather_qualified=False, general_table_parity_qualified=False)


def metadata_plan(source_sha, gather_source_sha):
    if source_hash(__file__) != sha(source_sha) or source_hash(GATHER_SOURCE) != sha(gather_source_sha):
        raise ValueError("reviewed preparer/capture source differs")
    builder = helper()
    embedding = read_json(ASSETS / "embedding-row.json", EMBEDDING_SHA)
    weights = read_json(ASSETS / "weights.json", WEIGHTS_SHA)
    selected = {}
    for receipt in (embedding, weights):
        plan = read_json(receipt["prepared_plan"], receipt["prepared_plan_sha256"])
        if (receipt.get("schema") != 1 or receipt["source"] != plan["source"] or
                receipt["source"]["checkpoint_sha256"] != CHECKPOINT_SHA or
                receipt["source_identity_after"] != receipt["source"]["native_identity"] or
                receipt["reader_sources"] != builder.READER_SHA256 or plan["reader_sources"] != builder.READER_SHA256):
            raise ValueError("sealed asset lineage differs")
        for name, expected in builder.READER_SHA256.items():
            if source_hash(HERE / name) != expected:
                raise ValueError("sealed decoder source differs: " + name)
        if Path(receipt["data"]).parent != ASSETS or Path(receipt["prepared_plan"]).parent != ASSETS:
            raise ValueError("asset files must stay beside frozen receipts")
        for item in receipt["tensors"]:
            if item["name"] in ("embed_tokens.weight", "mtp.fc_embedding.weight", "mtp.pre_fc_norm_embedding.weight"):
                tiles = [tile for tile in receipt["tiles"] if tile["tensor"] == item["name"]]
                selected[item["name"]] = dict(tensor=item, tiles=tiles, data=receipt["data"], total=receipt["data_bytes"])
    if embedding["source"] != weights["source"] or set(selected) != {
            "embed_tokens.weight", "mtp.fc_embedding.weight", "mtp.pre_fc_norm_embedding.weight"}:
        raise ValueError("one checkpoint generation and three token-only tensors required")
    # Exact independently sealed receipts bind all tile/source extents; assert
    # the narrow row/weight/gamma cut before any exported payload may be read.
    for name, dims, encoding, row_start, rows, length in (
            ("embed_tokens.weight", [248320, WIDTH], (5, 2), TOKEN, 1, 10240),
            ("mtp.fc_embedding.weight", [WIDTH, WIDTH], (7, 0), 0, WIDTH, 26214400),
            ("mtp.pre_fc_norm_embedding.weight", [WIDTH], (0, 0), 0, 1, 10240)):
        item = selected[name]["tensor"]
        entry, region = item["source_entry"], item["external_data"]
        if (entry["dims"] != dims or (entry["store"], entry["variant"]) != encoding or
                item["row_start"] != row_start or item["rows"] != rows or region["length"] != length or
                region["location"] != Path(selected[name]["data"]).name):
            raise ValueError("token-only tensor cut differs")
    return dict(schema="halogen0162.early-token-preparation-plan.v1", token=TOKEN,
                preparer_sha256=source_sha, gather_source_sha256=gather_source_sha, builder_sha256=BUILDER_SHA,
                embedding_receipt_sha256=EMBEDDING_SHA, weights_receipt_sha256=WEIGHTS_SHA,
                checkpoint_source=embedding["source"], selected=selected,
                input_cut="host token14367; no hidden residual or late normalized row input",
                raw_gather_oracle_required=True, payload_bytes_read=0,
                embedding_rms_qualification=embedding_rms_qualification(),
                frozen_input_native_embedding_rms_qualified=True,
                runtime_token_producer_implemented=False, batch_publication_implemented=False,
                cpu_tolerance=CPU_TOLERANCE, npu_tolerance=NPU_TOLERANCE,
                full_hidden_path="GPU", npu_executed=False, useful_overlap_qualified=False)


def write(path, raw):
    with Path(path).open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    return dict(file=Path(path).name, bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


def json_write(path, value):
    return write(path, json.dumps(value, indent=2, allow_nan=False).encode("utf-8"))


def capture_row(args, plan):
    directory = args.capture.resolve(strict=True)
    activation = read_json(directory / "activation.json", args.activation_sha256)
    records = read_json(directory / "records.json", args.records_sha256)
    complete = read_json(directory / "complete.json", args.complete_sha256)
    provenance = read_json(args.provenance, args.provenance_sha256)
    expected = dict(schema=1, mode="gather14367-v1", engine_sha256=ENGINE_SHA, function_sha256=HEAD_SHA)
    if any(activation.get(k) != v or records.get(k) != v for k, v in expected.items()):
        raise ValueError("raw gather activation/records differ")
    if (complete.get("schema") != 1 or complete.get("mode") != "gather14367-v1" or
            complete.get("passed") is not True or complete.get("calls") != 1 or complete.get("captured") is not True or
            complete.get("error") is not None or complete.get("observer_hip_syncs") != 1 or
            complete.get("observer_hip_copies") != 1 or len(records.get("samples", [])) != 1):
        raise ValueError("one completed original gather with one sync/copy required")
    row = records["samples"][0]
    required = dict(index=0, count=1, token_i32=TOKEN, entry_valid=True, reserved=True, completed=True,
                    captured=True, exact_launches=1, nested_forwards=0, wire_mode="D", wire_byte_before=68,
                    wire_byte_after=68, wire_initialized_before=True, wire_initialized_after=True,
                    kernel_identity_rva="0x18d5b40", launch_return_rva="0x17db44e", grid=[1, 1, 1],
                    block=[256, 1, 1], shared_bytes=0, stream="0x0", launch_result_valid=True, launch_result=0,
                    observer_hip_syncs=1, observer_hip_copies=1, capture_before_in_place_rms=True,
                    raw_embedding_file="000-raw-embedding-u16.bin", error=None)
    if any(row.get(k) != v for k, v in required.items()) or type(row.get("head_result")) is not int or row["head_result"] < 0:
        raise ValueError("original gather seam/token/completion contract differs")
    # This receipt is made independently by root's owned controller. Captured
    # pointers and engine hash alone cannot prove which checkpoint was loaded.
    required_provenance = dict(schema="halogen0162.raw-embedding-owned-provenance.v1",
        engine_sha256=ENGINE_SHA, checkpoint_sha256=CHECKPOINT_SHA,
        checkpoint_native_identity=plan["checkpoint_source"]["native_identity"],
        capture_source_sha256=plan["gather_source_sha256"], capture_directory=str(directory),
        activation_sha256=args.activation_sha256, records_sha256=args.records_sha256,
        complete_sha256=args.complete_sha256, model_pointer=row["model"],
        exclusive_owned_process=True, checkpoint_generation_immutable=True,
        no_other_head_interposer=True, original_allocation_lifetimes_qualified=True,
        process_exit=0, cleanup_proven=True, admission_gib=22, reserve_gib=18)
    if any(provenance.get(k) != v for k, v in required_provenance.items()):
        raise ValueError("independent owned-process/checkpoint provenance differs")
    sha(provenance["capture_binary_sha256"])
    sha(provenance["runtime_sha256"])
    return captured(directory / row["raw_embedding_file"], ROW_BYTES, row["raw_embedding_sha256"]), row


def words(value, builder, np):
    value = builder.bf16_input(value, value.shape, "stage output")
    return (value.view(np.uint32) >> 16).astype("<u2").tobytes()


def export(args):
    plan = read_json(args.plan, args.plan_sha256)
    if plan != metadata_plan(plan["preparer_sha256"], plan["gather_source_sha256"]):
        raise ValueError("sealed metadata/source plan changed")
    if any(os.environ.get(name) != "1" for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")):
        raise ValueError("all three BLAS/OpenMP thread variables must be1 before Python starts")
    builder = helper()
    import numpy as np
    if np.__version__ != "2.5.3":
        raise ValueError("retained NumPy2.5.3 reference required")
    native_raw, sample = capture_row(args, plan)
    selected = plan["selected"]
    def tile_bytes(item, tile):
        return captured(item["data"], tile["output_bytes"], tile["decoded_sha256"],
                        offset=tile["output_offset"], total=item["total"])
    embedding = selected["embed_tokens.weight"]
    raw = builder.bf16_rne(np.frombuffer(tile_bytes(embedding, embedding["tiles"][0]), dtype="<f4").reshape(1, WIDTH))
    raw_words = words(raw, builder, np)
    if hashlib.sha256(raw_words).hexdigest() != RAW_SHA:
        raise ValueError("token row no longer reproduces retained BF16 fixture")
    if raw_words != native_raw:
        different = np.frombuffer(raw_words, dtype="<u2") != np.frombuffer(native_raw, dtype="<u2")
        args.out.mkdir(exist_ok=False)
        json_write(args.out / "raw-gather-gate.json", dict(
            schema="halogen0162.token14367-raw-gather-gate.v1", passed=False, token=TOKEN,
            candidate_sha256=hashlib.sha256(raw_words).hexdigest(),
            native_gather_sha256=hashlib.sha256(native_raw).hexdigest(),
            exact_bf16_word_mismatches=int(different.sum()),
            first_indices=np.flatnonzero(different)[:16].tolist(),
            rms_or_fc_executed=False, speed_claim=False))
        raise ValueError("token14367 Q4C->BF16 native gather mismatch; raw-gather-gate.json retained; RMS/FC not run")
    gamma_item = selected["mtp.pre_fc_norm_embedding.weight"]
    gamma = np.frombuffer(tile_bytes(gamma_item, gamma_item["tiles"][0]), dtype="<f4").copy()
    gamma_words = words(gamma, builder, np)
    if hashlib.sha256(gamma_words).hexdigest() != GAMMA_SHA:
        raise ValueError("raw embedding gamma differs from checkpoint words")
    normalized = builder.rms_bf16(raw, gamma)
    norm_words = words(normalized, builder, np)
    if hashlib.sha256(norm_words).hexdigest() != NORM_SHA:
        raise ValueError("token-only RMS no longer reproduces frozen e-FC input")
    projection = np.empty((1, WIDTH), dtype=np.float32)
    weight_item = selected["mtp.fc_embedding.weight"]
    cursor = 0
    for tile in weight_item["tiles"]:
        start, rows = tile["row_start"], tile["rows"]
        if start != cursor or not 0 < rows <= WIDTH - cursor:
            raise ValueError("embedding FC output-row tile coverage differs")
        decoded = np.frombuffer(tile_bytes(weight_item, tile), dtype="<f4").reshape(rows, WIDTH)
        projection[:, start:start + rows] = builder.bf16_rne(normalized @ builder.bf16_rne(decoded).T)
        cursor += rows
    if cursor != WIDTH:
        raise ValueError("embedding FC output-row coverage incomplete")
    native_fc = read_json(FC_RECEIPT, FC_RECEIPT_SHA)
    oracle = native_fc["fixtures"][0]
    if (native_fc.get("passed") is not True or native_fc.get("engine_sha256") != ENGINE_SHA or
            native_fc.get("cleanup_errors") != 0 or oracle["id"] != "A-embedding" or
            oracle["input_sha256"] != NORM_SHA or native_fc["raw_weight_sha256"]["embedding"] !=
            "ec6ac9d2e6111b3cf9df7cc408afd555cd33ac291e5613d4000d58cd8a51107d"):
        raise ValueError("retained original GPU FC oracle differs")
    oracle_raw = captured(FC_RECEIPT.parent / oracle["output_file"], ROW_BYTES, oracle["output_sha256"])
    oracle_value = builder.widen_bf16(np.frombuffer(oracle_raw, dtype="<u2")).reshape(1, WIDTH)
    outside = int(np.count_nonzero(np.abs(projection - oracle_value) > .0002 + .002 * np.abs(oracle_value)))
    if outside:
        raise ValueError("embedding FC CPU reference fails unchanged .002/.0002 native-output screen")
    # Recheck selected regions and all receipts before publication; no hidden
    # tensor, original checkpoint, engine payload or provider is read here.
    for item in selected.values():
        for tile in item["tiles"]:
            tile_bytes(item, tile)
    capture_row(args, plan)
    if plan != metadata_plan(plan["preparer_sha256"], plan["gather_source_sha256"]):
        raise ValueError("source/metadata changed during materialization")
    args.out.mkdir(exist_ok=False)
    projection_words = words(projection, builder, np)
    files = [write(args.out / name, payload) for name, payload in (
        ("tokens.i32", np.array([TOKEN], dtype="<i4").tobytes()), ("embedding.u16", raw_words),
        ("raw-gamma.u16", gamma_words), ("embedding-norm.u16", norm_words), ("embedding-fc-reference.u16", projection_words))]
    result = dict(schema="halogen0162.early-token-offline-preparation.v1", token=TOKEN,
        plan=str(args.plan.resolve()), plan_sha256=args.plan_sha256, files=files,
        capture_provenance=str(args.provenance.resolve()), capture_provenance_sha256=args.provenance_sha256,
        token14367_q4c_to_native_gather_equal=True, frozen_e_fc_input_reproduced=True,
        native_fc_receipt_sha256=FC_RECEIPT_SHA, native_fc_output_sha256=oracle["output_sha256"],
        fc_exact_word_mismatches=int(sum(a != b for a, b in zip(np.frombuffer(projection_words, dtype="<u2"),
                                                             np.frombuffer(oracle_raw, dtype="<u2")))),
        fc_outside_frozen_cpu_tolerance=outside, cpu_tolerance=CPU_TOLERANCE, npu_tolerance=NPU_TOLERANCE,
        arithmetic="retained BF16 RNE/RMS; raw gamma+1; weight BF16 RNE; CPU FP32 MatMul; output BF16 RNE",
        embedding_rms_qualification=plan["embedding_rms_qualification"],
        frozen_input_native_embedding_rms_qualified=True,
        original_native_embedding_rms_observed_by_this_export=False, general_table_parity_qualified=False,
        native_rsq_dot2_emulated=False, runtime_token_producer_implemented=False,
        batch_publication_implemented=False, npu_executed=False, full_hidden_path="GPU",
        useful_overlap_qualified=False, speed_claim=False, whole_checkpoint_read=False,
        hidden_tensor_read=False, full_external_data_rehashed=False, selected_region_hashes_verified=True)
    receipt = json_write(args.out / "complete.json", result)
    return dict(receipt=str(args.out / "complete.json"), receipt_sha256=receipt["sha256"], **result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare-only", action="store_true")
    mode.add_argument("--export", action="store_true")
    parser.add_argument("--source-sha256")
    parser.add_argument("--gather-source-sha256")
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--plan-sha256")
    parser.add_argument("--capture", type=Path)
    parser.add_argument("--activation-sha256")
    parser.add_argument("--records-sha256")
    parser.add_argument("--complete-sha256")
    parser.add_argument("--provenance", type=Path)
    parser.add_argument("--provenance-sha256")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    if args.prepare_only:
        if not args.source_sha256 or not args.gather_source_sha256:
            parser.error("prepare-only requires independently reviewed preparer/capture SHA256")
        plan = metadata_plan(args.source_sha256, args.gather_source_sha256)
        sealed = json_write(args.plan, plan)
        print(json.dumps(dict(plan=str(args.plan.resolve()), plan_sha256=sealed["sha256"],
                              raw_gather_oracle_required=True, payload_bytes_read=0), indent=2))
    else:
        if not all((args.plan_sha256, args.capture, args.activation_sha256, args.records_sha256,
                    args.complete_sha256, args.provenance, args.provenance_sha256, args.out)):
            parser.error("export requires sealed plan, three capture hashes, owned provenance and fresh output directory")
        print(json.dumps(export(args), indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
