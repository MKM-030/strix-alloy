"""Metadata-only sealing for the bounded original Q4C/count1 RMS oracle.

Reads only pinned source text and ordinary producer plan/completion JSON.
Never opens a candidate tensor, checkpoint, engine, codeobject or provider.
Root supplies exact original tokens, hashes the binary manifest independently,
and binds reviewed source/binary/runtime in its existing owned GPU envelope.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import struct


HERE = Path(__file__).resolve().parent
SCAFFOLD_SHA = "7ea99028014f590a0938d5a06790f51ce571948706d851c16bfcb72f694f4fa8"
MAGIC, HEADER_BYTES, RECORD_BYTES = b"HGMROW1\0", 200, 132


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(value):
    require(isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value),
            "independently supplied lowercase SHA256 required")
    return value


def captured(path, expected):
    path = Path(path)
    require(path.is_absolute(), "absolute source/JSON path required")
    before = path.lstat()
    require(stat.S_ISREG(before.st_mode) and 0 < before.st_size <= 2 << 20, "bounded regular source/JSON required")
    with path.open("rb") as stream:
        opened = os.fstat(stream.fileno())
        raw = stream.read(before.st_size + 1)
        after = os.fstat(stream.fileno())
    end = path.lstat()
    fields = ("st_size", "st_dev", "st_ino", "st_mtime_ns")
    fields += ("st_birthtime_ns",) if os.name == "nt" else ("st_ctime_ns",)
    shared = lambda value: tuple(getattr(value, field, None) for field in fields)
    require(shared(before) == shared(opened) == shared(after) == shared(end)
            and before.st_ctime_ns == end.st_ctime_ns and opened.st_ctime_ns == after.st_ctime_ns
            and len(raw) == before.st_size and hashlib.sha256(raw).hexdigest() == sha(expected),
            "source/JSON hash or stable file identity differs: " + path.name)
    return raw


def seal(args):
    captured(Path(__file__).resolve(), args.source_sha256)
    captured(HERE / "halogen0162_q4c_multirow_oracle.c", args.harness_sha256)
    captured(HERE / "halogen0162_embedding_rms_replay.c", SCAFFOLD_SHA)
    producer_path = HERE / "halogen_mtp_early_token_producer.py"
    captured(producer_path, args.producer_sha256)
    spec = importlib.util.spec_from_file_location("_sealed_multirow_producer", producer_path)
    producer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(producer)
    require(Path(producer.__file__).resolve() == producer_path, "sealed producer import origin differs")
    plan = json.loads(captured(args.producer_plan, args.producer_plan_sha256))
    require(plan == producer.metadata_plan(plan["schedule"], args.producer_sha256, args.assets),
            "current independently sealed producer source/metadata plan differs")
    complete = json.loads(captured(args.complete, args.complete_sha256))
    tokens = args.tokens
    require(type(tokens) is list and 1 <= len(tokens) <= 64 and len(set(tokens)) == len(tokens)
            and all(type(token) is int and 0 <= token < 248320 for token in tokens),
            "1..64 unique explicit original tokens required")
    require(complete["schema"] == "halogen0162.early-token-producer-candidates.v1" and complete["completed"] is True
            and complete["plan_sha256"] == args.producer_plan_sha256 and complete["producer_sha256"] == args.producer_sha256
            and complete["schedule"] == plan["schedule"] and complete["generation_hex"] == plan["schedule"]["generation_hex"]
            and complete["sequence"] == plan["schedule"]["sequence"]
            and complete["candidate_tokens"] == plan["producer_tokens"] == tokens
            and complete["deferred_known_tokens"] == plan["deferred_known_tokens"]
            and complete["unknown_tail_requires_original_fallback"] == plan["unknown_tail_requires_original_fallback"],
            "completed producer request/token lineage differs")
    require(complete["required_gates"] == list(producer.REQUIRED_GATES)
            and complete["gate_status"] == {gate: False for gate in producer.REQUIRED_GATES}
            and complete["cpu_tolerance"] == plan["cpu_tolerance"] and complete["npu_tolerance"] == plan["npu_tolerance"],
            "candidate qualification/tolerance contract differs")
    for key in ("checkpoint_whole_file_rehashed", "FC_weight_payload_read", "hidden_payload_read", "CPU_FC_executed",
                "generation_checkpoint_live_binding_proved", "live_publication_implemented", "native_FC_skip_admitted",
                "device_upload_completed", "npu_executed", "supported_fabric_clock_overlap_qualified",
                "concurrent_GPU_NPU_inference_allowed", "full_engine_AB_qualified", "speed_claim"):
        require(complete[key] is False, "broader candidate gate was admitted: " + key)
    rows = len(tokens)
    require(complete["selected_native_pack"] == dict(rows=rows, width=2560, code_offset=64,
            scale_offset=64 + rows * 1280, scale_stride=160, rebased_private_fixture_only=True,
            original_full_table_qualified=False)
            and complete["checkpoint_payload_bytes_read"] == 2 * plan["checkpoint_bytes_per_pass"],
            "bounded candidate native pack/source read contract differs")
    files = complete["files"]
    require(type(files) is list and len(files) == 5 * rows + 3, "exact candidate file list required")
    by_name = {}
    for item in files:
        require(type(item) is dict and set(item) == {"file", "bytes", "sha256"}
                and type(item["file"]) is str and item["file"] not in by_name, "unique exact candidate file records required")
        sha(item["sha256"])
        by_name[item["file"]] = item
    expected_files = {"selected-rows.q4c": 64 + rows * 1440, "tokens.i32": rows * 4, "raw-gamma.u16": 5120}
    for index, token in enumerate(tokens):
        prefix = f"{index:03d}-token{token}-"
        expected_files.update({prefix + suffix: size for suffix, size in
                              (("raw.u16", 5120), ("norm.u16", 5120), ("e_norm.f32", 10240),
                               ("e_high.f32", 10240), ("e_low.f32", 10240))})
    require(set(by_name) == set(expected_files)
            and all(type(by_name[name]["bytes"]) is int and by_name[name]["bytes"] == size for name, size in expected_files.items())
            and sum(item["bytes"] for item in files) == plan["candidate_payload_bytes"]
            and by_name["raw-gamma.u16"]["sha256"] == producer.GAMMA_SHA, "exact bounded candidate file ABI differs")
    observed = complete["observed_source_ranges"]
    require(type(observed) is list and len(observed) == len(plan["source_ranges"]), "bounded observed source windows required")
    windows = {}
    for actual, planned in zip(observed, plan["source_ranges"]):
        require(type(actual) is dict and set(actual) == set(planned) | {"observed_sha256"}
                and {key: actual[key] for key in planned} == planned, "original checkpoint window identity/order differs")
        digest = sha(actual["observed_sha256"])
        require(planned["independent_sha256"] is None or digest == planned["independent_sha256"], "frozen original window SHA differs")
        windows[(actual["kind"], actual["token"])] = digest
    require(windows[("codebook", None)] == producer.CODEBOOK_SHA
            and windows[("raw_gamma", None)] == producer.GAMMA_SHA, "frozen original codebook/gamma differs")
    require(type(complete["rows"]) is list and len(complete["rows"]) == rows, "exact producer row records required")
    manifest = bytearray(struct.pack("<8sII16sQ", MAGIC, rows, 2560,
                                    bytes.fromhex(complete["generation_hex"]), complete["sequence"]))
    for digest in (args.complete_sha256, args.producer_plan_sha256, args.producer_sha256,
                   by_name["selected-rows.q4c"]["sha256"], by_name["tokens.i32"]["sha256"]):
        manifest.extend(bytes.fromhex(sha(digest)))
    for index, (token, row) in enumerate(zip(tokens, complete["rows"])):
        prefix = f"{index:03d}-token{token}-"
        names = [prefix + suffix for suffix in ("raw.u16", "norm.u16", "e_norm.f32", "e_high.f32", "e_low.f32")]
        require(row["index"] == index and row["token"] == token and row["shape"] == [1, 2560] and row["files"] == names
                and row["raw_BF16_sha256"] == by_name[names[0]]["sha256"]
                and row["norm_BF16_sha256"] == by_name[names[1]]["sha256"]
                and row["arbitrary_row_native_parity_admitted"] is False and row["candidate_input_only"] is True
                and row["native_FC_skip_admitted"] is False, "exact candidate row/reference contract differs")
        if token == producer.FROZEN_TOKEN:
            require(row["raw_BF16_sha256"] == producer.FROZEN_HASHES["raw"]
                    and row["norm_BF16_sha256"] == producer.FROZEN_HASHES["normalized"], "frozen token14367 BF16 reference differs")
        manifest.extend(struct.pack("<I", token))
        for digest in (row["raw_BF16_sha256"], row["norm_BF16_sha256"], windows[("codes", token)], windows[("scales", token)]):
            manifest.extend(bytes.fromhex(sha(digest)))
    require(len(manifest) == HEADER_BYTES + rows * RECORD_BYTES, "binary manifest ABI extent differs")
    # Rebind metadata/source after constructing the manifest; still no payload read.
    require(json.loads(captured(args.complete, args.complete_sha256)) == complete
            and json.loads(captured(args.producer_plan, args.producer_plan_sha256)) == plan
            and plan == producer.metadata_plan(plan["schedule"], args.producer_sha256, args.assets), "source/JSON changed before sealing")
    captured(Path(__file__).resolve(), args.source_sha256)
    captured(HERE / "halogen0162_q4c_multirow_oracle.c", args.harness_sha256)
    captured(HERE / "halogen0162_embedding_rms_replay.c", SCAFFOLD_SHA)
    return bytes(manifest), dict(schema="halogen0162.q4c-multirow-oracle-plan.v1",
        preparer_sha256=sha(args.source_sha256), harness_sha256=sha(args.harness_sha256), included_scaffold_sha256=SCAFFOLD_SHA,
        producer_sha256=sha(args.producer_sha256), producer_plan_sha256=sha(args.producer_plan_sha256), complete_sha256=sha(args.complete_sha256),
        generation_hex=complete["generation_hex"], sequence=complete["sequence"], original_tokens=tokens,
        manifest=dict(file="oracle-manifest.bin", bytes=len(manifest), sha256=hashlib.sha256(manifest).hexdigest(),
                      byte_order="little", header_bytes=HEADER_BYTES, row_record_bytes=RECORD_BYTES),
        selected_rows=rows, width=2560, pack_bytes=64 + rows * 1440, scale_offset=64 + rows * 1280,
        vector_grid=[(320 * rows + 511) // 512, 1, 1], scalar_grid=[rows, 1, 1], rms_grid=[1, 1, 1], block=[256, 1, 1],
        native_kernel_calls=2 + rows, expected_copies=6 + rows, device_allocation_bytes=64 + rows * 1440 + rows * 5120 + 5120,
        raw_gate="all BF16 words of both original converters exactly match each sealed CPU raw row",
        rms_gate="original count1 in-place RMS on each native vector row exactly matches sealed CPU normalized row",
        payload_bytes_read=0, GPU_executed=False, numerical_parity_qualified=False,
        original_full_table_loader_qualified=False, live_allocation_qualified=False, general_table_parity_qualified=False,
        gather_replayed=False, live_generation_binding_proved=False, native_FC_skip_admitted=False,
        full_D_parity_qualified=False, full_head_qualified=False, FC_executed=False, npu_executed=False, speed_claim=False,
        tolerance_adjustment=False, arithmetic_fitting=False)


def write_new(path, raw):
    with path.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("source", "harness", "producer", "producer-plan", "complete"):
        parser.add_argument("--" + name + "-sha256", required=True)
    parser.add_argument("--producer-plan", type=Path, required=True)
    parser.add_argument("--complete", type=Path, required=True)
    parser.add_argument("--assets", type=Path, required=True)
    parser.add_argument("--tokens", type=int, nargs="+", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    manifest, plan = seal(args)
    require(args.out.is_absolute(), "absolute exclusive output directory required")
    args.out.mkdir(mode=0o700, parents=False, exist_ok=False)
    write_new(args.out / "oracle-manifest.bin", manifest)
    write_new(args.out / "oracle-plan.json", (json.dumps(plan, indent=2, allow_nan=False) + "\n").encode())
    print(json.dumps(plan, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
