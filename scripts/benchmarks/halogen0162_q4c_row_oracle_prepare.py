"""Prepare a bounded original-Q4C-shader row oracle without loading a server.

Prepare-only reads ordinary sealed JSON and source text. Root-only Linux export
reads exactly the three selected checkpoint ranges (1504 bytes), verifies their
independent hashes plus native inode/timestamps, and copies the pinned CPU BF16
reference. It performs no CPU decoding, provider import, build, or device work.
The original-kernel harness then determines exact numerical parity. This gate
never proves original full-table allocation, the live server, or a speed gain.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat


HERE = Path(__file__).resolve().parent
ASSETS = Path(r"C:\AI\halogen-mtp-npu\v2-d-prepare-20261004")
EMBEDDING_SHA = "408d29273a4d737b7a0d7596f07f0f5c122d8298bcc497ffc86dd22a67def1e3"
EMBEDDING_PLAN_SHA = "0fd6aab5f14f3f69735ecdca2e7e88270130366a137661949ed952b20fdf9c1b"
SCAFFOLD_SHA = "7ea99028014f590a0938d5a06790f51ce571948706d851c16bfcb72f694f4fa8"
ENGINE_SHA = "ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b"
CODE_SHA = "45941c0579dc3487d07978a50c85cbaa141bbb674b225e708e82d81397334a83"
CHECKPOINT_SHA = "71246c6ab3fc1de2cf06326f18e275fe9c2a18366d646ed3357d194c884fc687"
REFERENCE_SHA = "af284c0101ac76b7562b3d9e19cfc6721266f282358d8f313a09b961435ee374"
DECODED_SHA = "e9e662c644efff444dc1af8c17ac4c43986d088a6983821cf0409c8d8fd93cb5"
SOURCE = "/home/revn/halogen-models-native/qwen38-flash-next-v2.hgn"
SOURCE_UNC = r"\\wsl.localhost\Ubuntu-24.04\home\revn\halogen-models-native\qwen38-flash-next-v2.hgn"
TOKEN, WIDTH, PACK_BYTES, ROW_BYTES = 14367, 2560, 1504, 5120
NATIVE_IDENTITY = dict(size=66687678432, device=2096, inode=616828,
    mtime_ns=1790979071648131939, ctime_ns=1790979072020131920)
ENTRY = dict(name="embed_tokens.weight", store=5, rank=2, dims=[248320, WIDTH],
    offset=322560, size=357580864, xor32=462038655, variant=2)
RANGES = [
    dict(name=ENTRY["name"], offset=322560, bytes=64,
         sha256="1f2755c994ae6ea3d4a24a5cc2b8066de0971b07eacd76a05c5e111cba8d3679", destination_offset=0),
    dict(name=ENTRY["name"], offset=18712384, bytes=1280,
         sha256="47b6702d51297b13cc90632f2f746d42b0c5fc97d06fcf778dbad225aac8cbcb", destination_offset=64),
    dict(name=ENTRY["name"], offset=320470944, bytes=160,
         sha256="79cc173820638d74f37a9340782a92e4d620b8a53cff138d17c7ebebeaafeabb", destination_offset=1344)]
VECTOR = "_ZN7halogen12_GLOBAL__N_114k_deq_q4cp_v8uILi2ELb0EEEvPKhPtjjllllNS0_5DeqCbE"
SCALAR = "_ZN7halogen12_GLOBAL__N_110k_deq_q4cpEPKhPtlllll"
GATHER = "_ZN7halogen12_GLOBAL__N_114k_embed_gatherEPKtPKiPt"
MAX_METADATA_BYTES = 2 << 20


def sha(value):
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError("independently supplied lowercase SHA256 required")
    return value


def identity(value):
    return dict(size=value.st_size, device=value.st_dev, inode=value.st_ino,
                mtime_ns=value.st_mtime_ns, ctime_ns=value.st_ctime_ns)


def captured(path, expected_sha, expected_bytes=None, maximum=MAX_METADATA_BYTES):
    """Read a bounded regular input and bind both pathname and handle identity."""
    path = Path(path)
    if not path.is_absolute():
        raise ValueError("absolute input path required")
    before = path.lstat()
    if (not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= maximum or
            (expected_bytes is not None and before.st_size != expected_bytes)):
        raise ValueError("bounded regular input extent differs: " + str(path))
    with path.open("rb") as stream:
        opened = os.fstat(stream.fileno())
        raw = stream.read(before.st_size + 1)
        after = os.fstat(stream.fileno())
    end = path.lstat()
    fields = ("st_size", "st_dev", "st_ino", "st_mtime_ns")
    fields += ("st_birthtime_ns",) if os.name == "nt" else ("st_ctime_ns",)
    shared_identity = lambda value: tuple(getattr(value, field, None) for field in fields)
    # Windows pathname/handle ctime have different documented API meanings;
    # compare their stability separately, while binding common birth time.
    # Native checkpoint identity() remains the strict Linux size/dev/ino/mtime/ctime gate.
    if (not shared_identity(before) == shared_identity(opened) == shared_identity(after) == shared_identity(end) or
            before.st_ctime_ns != end.st_ctime_ns or opened.st_ctime_ns != after.st_ctime_ns or
            len(raw) != before.st_size or
            hashlib.sha256(raw).hexdigest() != sha(expected_sha)):
        raise ValueError("input hash or file identity differs: " + str(path))
    return raw


def source_pin(path, expected_sha):
    captured(path, expected_sha)
    return sha(expected_sha)


def read_json(path, expected_sha):
    return json.loads(captured(path, expected_sha))


def contract(args):
    """No checkpoint, tensor, engine, codeobject or provider is opened here."""
    preparer_sha = source_pin(__file__, args.source_sha256)
    harness_sha = source_pin(HERE / "halogen0162_q4c_row_oracle.c", args.harness_sha256)
    source_pin(HERE / "halogen0162_embedding_rms_replay.c", SCAFFOLD_SHA)
    receipt = read_json(args.embedding_receipt, EMBEDDING_SHA)
    parent_plan = read_json(args.embedding_plan, EMBEDDING_PLAN_SHA)
    source = receipt["source"]
    if (receipt.get("schema") != 1 or parent_plan.get("schema") != 1 or
            receipt["prepared_plan_sha256"] != EMBEDDING_PLAN_SHA or
            source != parent_plan["source"] or source["checkpoint_sha256"] != CHECKPOINT_SHA or
            source["checkpoint_source"] != SOURCE or source["checkpoint_unc"] != SOURCE_UNC or
            source["native_identity"] != NATIVE_IDENTITY or receipt["source_identity_after"] != NATIVE_IDENTITY or
            receipt["source_bytes_read"] != PACK_BYTES or receipt["data_bytes"] != 10240 or
            receipt["data_sha256"] != DECODED_SHA):
        raise ValueError("sealed embedding source/selected-byte lineage differs")
    if len(receipt["tensors"]) != 1 or len(receipt["tiles"]) != 1 or len(parent_plan["tensors"]) != 1:
        raise ValueError("exactly one sealed selected row required")
    tensor, tile, parent_tensor = receipt["tensors"][0], receipt["tiles"][0], parent_plan["tensors"][0]
    if (tensor["source_entry"] != ENTRY or tensor["row_start"] != TOKEN or tensor["rows"] != 1 or
            tensor["shape"] != [1, WIDTH] or tensor["sideplanes"] is not None or
            parent_tensor["entry"] != ENTRY or parent_tensor["row_start"] != TOKEN or
            parent_tensor["rows"] != 1 or parent_tensor["output_shape"] != [1, WIDTH] or
            tile["tensor"] != ENTRY["name"] or tile["row_start"] != TOKEN or tile["rows"] != 1 or
            tile["output_bytes"] != 10240 or tile["decoded_sha256"] != DECODED_SHA):
        raise ValueError("sealed selected tensor shape/store/variant differs")
    expected_ranges = [{key: row[key] for key in ("name", "offset", "bytes", "sha256")} for row in RANGES]
    if tile["source_ranges"] != expected_ranges:
        raise ValueError("sealed selected raw windows differ")
    parent_ranges = [{key: row[key] for key in ("name", "offset", "bytes")} for row in RANGES]
    if (len(parent_tensor["tiles"]) != 1 or
            parent_tensor["tiles"][0]["source_ranges"] != parent_ranges):
        raise ValueError("sealed original plan raw windows differ")
    # Recompute original native full-table offsets and exact selected windows.
    rows, width = ENTRY["dims"]
    code_bytes = rows * (width // 2)
    code_extent = (code_bytes + 63) // 64 * 64
    scale_stride = ((width // 32 * 2) + 15) // 16 * 16
    if (ENTRY["size"] != 64 + code_extent + rows * scale_stride or
            RANGES[1]["offset"] != ENTRY["offset"] + 64 + TOKEN * width // 2 or
            RANGES[2]["offset"] != ENTRY["offset"] + 64 + code_extent + TOKEN * scale_stride or
            scale_stride != 160):
        raise ValueError("original store5/variant2 extent/address arithmetic differs")
    return dict(schema="halogen0162.q4c-row-oracle-plan.v1", scope=__doc__,
        preparer_sha256=preparer_sha, harness_sha256=harness_sha, included_scaffold_sha256=SCAFFOLD_SHA,
        engine_sha256=ENGINE_SHA, codeobject_sha256=CODE_SHA, codeobject_engine_offset=331776,
        codeobject_bytes=17704408, embedding_receipt_sha256=EMBEDDING_SHA,
        embedding_plan_sha256=EMBEDDING_PLAN_SHA, checkpoint_sha256_lineage=CHECKPOINT_SHA,
        checkpoint_source=SOURCE, checkpoint_native_identity=NATIVE_IDENTITY,
        source_entry=ENTRY, token=TOKEN, source_ranges=RANGES,
        native_pack=dict(bytes=PACK_BYTES, selected_rows=1, width=WIDTH, code_offset=64,
                         scale_offset=1344, scale_stride=160, no_CPU_decoding=True),
        reference=dict(bytes=ROW_BYTES, sha256=REFERENCE_SHA, origin="unchanged pinned CPU raw BF16 row"),
        conversion=dict(default_aligned_absent_overrides_symbol=VECTOR, scalar_sibling_symbol=SCALAR,
            grid=[1, 1, 1], block=[256, 1, 1], blocks_per_row=320, total_blocks=320,
            vector_public_offsets=[0, 8, 16, 20, 24, 32, 40, 48, 56],
            vector_public_sizes=[8, 8, 4, 4, 8, 8, 8, 8, 64], optional_codebook_all_zero=True,
            vector_static_LDS_bytes=64, vector_kernarg_bytes=376, kernarg_alignment=8,
            hidden_ABI_supplied_by_HIP=True),
        gather=dict(symbol=GATHER, actual_token=TOKEN, private_table_rows=TOKEN + 1,
                    private_table_bytes=(TOKEN + 1) * ROW_BYTES, grid=[1, 1, 1], block=[256, 1, 1]),
        retained_text_evidence=[
            dict(file="mtp-route-static-20261004/host-text-disassembly.txt",
                 sha256="523467ac08e576e770a9fcffdb59ffa9542f82d58958bd03d74743f8caccb8f9",
                 references=["0x17ee50d..0x17ee5d9", "0x17d2e50..0x17d3ebc", "0x182c300..0x182c3e1"]),
            dict(file="mtp-route-static-20261004/kernel-registrations.json",
                 sha256="c38287607691b58e618fb5e1b9f31cb5150daa85d82ecc0d22ecd46171732c2f"),
            dict(file="gather-copy-codeobject-notes.txt",
                 sha256="64641c462a5856843ebac4f3c72779a83a27f97fad6f87ee6635a75f032c2ff3")],
        retained_text_rehashed_by_preparer=False, original_shader_relocation_review_required_before_execution=True,
        payload_bytes_read_by_prepare=0, device_executed_by_prepare=False,
        numerical_parity_qualified=False, original_full_table_loader_qualified=False,
        live_allocation_qualified=False, general_table_parity_qualified=False, speed_claim=False)


def write_new(path, raw):
    with Path(path).open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def json_bytes(value):
    return (json.dumps(value, indent=2, allow_nan=False) + "\n").encode("utf-8")


def export(args):
    if os.name != "posix":
        raise ValueError("root-only Linux export required for exact native fstat identity")
    plan = read_json(args.plan, args.plan_sha256)
    if plan != contract(args):
        raise ValueError("independently sealed current plan differs")
    checkpoint = Path(args.checkpoint)
    if not checkpoint.is_absolute():
        raise ValueError("absolute checkpoint path required")
    before = checkpoint.lstat()
    if not stat.S_ISREG(before.st_mode) or identity(before) != NATIVE_IDENTITY:
        raise ValueError("native checkpoint pathname identity differs")
    packed = bytearray(PACK_BYTES)
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW
    descriptor = os.open(checkpoint, flags)
    try:
        if identity(os.fstat(descriptor)) != NATIVE_IDENTITY:
            raise ValueError("native checkpoint open-handle identity differs")
        for row in RANGES:
            raw = os.pread(descriptor, row["bytes"], row["offset"])
            if len(raw) != row["bytes"] or hashlib.sha256(raw).hexdigest() != row["sha256"]:
                raise ValueError("original selected checkpoint window differs")
            start = row["destination_offset"]
            packed[start:start + row["bytes"]] = raw
        if identity(os.fstat(descriptor)) != NATIVE_IDENTITY or identity(checkpoint.lstat()) != NATIVE_IDENTITY:
            raise ValueError("native checkpoint identity changed during selected export")
    finally:
        os.close(descriptor)
    reference = captured(args.reference, REFERENCE_SHA, ROW_BYTES, ROW_BYTES)
    # Revalidate all sealed source/JSON after reading the selected payloads.
    if read_json(args.plan, args.plan_sha256) != contract(args):
        raise ValueError("source/JSON changed during selected export")
    if identity(checkpoint.lstat()) != NATIVE_IDENTITY:
        raise ValueError("native checkpoint identity changed before publication")
    output = Path(args.output)
    if not output.is_absolute():
        raise ValueError("absolute exclusive output directory required")
    output.mkdir(mode=0o700, parents=False, exist_ok=False)
    write_new(output / "native-row.q4c", packed)
    write_new(output / "cpu-reference.u16", reference)
    result = dict(schema="halogen0162.q4c-row-oracle-export.v1", passed=True,
        scope="unchanged selected checkpoint bytes and CPU reference exported; original GPU oracle not yet executed",
        plan_sha256=sha(args.plan_sha256), preparer_sha256=plan["preparer_sha256"],
        harness_sha256=plan["harness_sha256"], included_scaffold_sha256=SCAFFOLD_SHA,
        checkpoint_sha256_lineage=CHECKPOINT_SHA, checkpoint_whole_file_rehashed=False,
        checkpoint_path=str(checkpoint), native_identity_before=NATIVE_IDENTITY, native_identity_after=NATIVE_IDENTITY,
        checkpoint_payload_bytes_read=PACK_BYTES, reference_payload_bytes_read=ROW_BYTES,
        source_ranges=RANGES, native_pack=dict(file="native-row.q4c", bytes=PACK_BYTES,
            sha256=hashlib.sha256(packed).hexdigest()),
        cpu_reference=dict(file="cpu-reference.u16", bytes=ROW_BYTES, sha256=REFERENCE_SHA),
        CPU_decoding_executed=False, GPU_executed=False, numerical_parity_qualified=False,
        original_full_table_loader_qualified=False, live_allocation_qualified=False, speed_claim=False)
    captured(output / "native-row.q4c", result["native_pack"]["sha256"], PACK_BYTES, PACK_BYTES)
    captured(output / "cpu-reference.u16", REFERENCE_SHA, ROW_BYTES, ROW_BYTES)
    if (identity(checkpoint.lstat()) != NATIVE_IDENTITY or
            read_json(args.plan, args.plan_sha256) != contract(args)):
        raise ValueError("source/JSON/native identity changed before export receipt")
    write_new(output / "export.json", json_bytes(result))
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare-only", action="store_true")
    mode.add_argument("--export-root-only", action="store_true")
    parser.add_argument("--source-sha256", required=True)
    parser.add_argument("--harness-sha256", required=True)
    parser.add_argument("--embedding-receipt", type=Path, default=ASSETS / "embedding-row.json")
    parser.add_argument("--embedding-plan", type=Path, default=ASSETS / "embedding-row.plan.json")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--plan-sha256")
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument("--reference", type=Path)
    args = parser.parse_args(argv)
    if args.prepare_only:
        result = contract(args)
        if not args.output.is_absolute():
            parser.error("absolute exclusive output plan path required")
        write_new(args.output, json_bytes(result))
    else:
        if not all((args.plan, args.plan_sha256, args.checkpoint, args.reference)):
            parser.error("export requires independently sealed plan, checkpoint and pinned CPU reference")
        result = export(args)
    print(json.dumps(result, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
