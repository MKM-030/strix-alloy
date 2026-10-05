"""Bounded offline early token-only embedding-input producer.

Planning uses only ordinary JSON/source and the sealed host-token scheduler.
Root-only Linux production reads selected original v2 Q4C windows and raw BF16
embedding gamma under strict native checkpoint identity. It applies unchanged
decoder/BF16/RMS and fresh stable input splitting, without FC weights, hidden
inputs, providers, device calls, threads, live hooks or a persistent cache.
Outputs are request-scoped candidate inputs, never native FC skip admission.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat


HERE = Path(__file__).resolve().parent
ASSETS = Path(r"C:\AI\halogen-mtp-npu\v2-d-prepare-20261004")
SOURCE_PINS = {
    "halogen_mtp_early_token_schedule.py": "3ed44fabf21f4c7e62637da79da89b3d619627d322179d9d604297fa1a1e9afb",
    "hgn_q4c_slice.py": "fe0dd1b9974f95bed02f37dddde1ee7c286f3f69d491548008d4a94ea703fdce",
    "halogen_npu_v2_d_prepare.py": "6334b32fc8a9a5cb792590d0422c0ee1fb532a7c475785f75979962ec80c2544",
    "halogen_npu_v2_d_native_projection_stable_split_graph.py": "94438473e7b1084818515b6c8308b86dc1f24a48cee05fa68e0b1f3c48636566",
}
RECEIPT_PINS = {
    "embedding-row.json": "408d29273a4d737b7a0d7596f07f0f5c122d8298bcc497ffc86dd22a67def1e3",
    "embedding-row.plan.json": "0fd6aab5f14f3f69735ecdca2e7e88270130366a137661949ed952b20fdf9c1b",
    "weights.json": "dbf679c94c75439638b01058c2c6915d43dd211c69b27918f7caa77d826e8fb7",
    "weights.plan.json": "850341ce237de0d48e995af5b0c3f913ad23369b2ddd99c25231b10ff156fe36",
}
CHECKPOINT_SHA = "71246c6ab3fc1de2cf06326f18e275fe9c2a18366d646ed3357d194c884fc687"
CHECKPOINT_SOURCE = "/home/revn/halogen-models-native/qwen38-flash-next-v2.hgn"
NATIVE_IDENTITY = dict(size=66687678432, device=2096, inode=616828,
    mtime_ns=1790979071648131939, ctime_ns=1790979072020131920)
WIDTH, VOCABULARY, MAX_TOKENS = 2560, 248320, 64
MAX_METADATA_BYTES, MAX_OUTPUT_BYTES = 2 << 20, 3 << 20
EMBEDDING_ENTRY = dict(name="embed_tokens.weight", store=5, rank=2, dims=[VOCABULARY, WIDTH],
    offset=322560, size=357580864, xor32=462038655, variant=2)
GAMMA_ENTRY = dict(name="mtp.pre_fc_norm_embedding.weight", store=0, rank=1, dims=[WIDTH],
    offset=65185026944, size=5120, xor32=7733293, variant=0)
CODEBOOK_SHA = "1f2755c994ae6ea3d4a24a5cc2b8066de0971b07eacd76a05c5e111cba8d3679"
GAMMA_SHA = "04c4a570850e06f2d8913da8220d54d4c7f87db6eb6d45480b938e8ba41d6a86"
FROZEN_TOKEN = 14367
FROZEN_HASHES = dict(
    codes="47b6702d51297b13cc90632f2f746d42b0c5fc97d06fcf778dbad225aac8cbcb",
    scales="79cc173820638d74f37a9340782a92e4d620b8a53cff138d17c7ebebeaafeabb",
    decoded="e9e662c644efff444dc1af8c17ac4c43986d088a6983821cf0409c8d8fd93cb5",
    raw="af284c0101ac76b7562b3d9e19cfc6721266f282358d8f313a09b961435ee374",
    normalized="97079c27ab56da44c2ab29780c856be79803d402caf754acfbf7d187fbe34892")
REQUIRED_GATES = (
    "original_native_Q4C_to_raw_BF16_multirow_parity",
    "original_native_embedding_RMS_on_each_new_raw_row",
    "original_full_table_or_live_allocation_provenance_for_the_integration",
    "embedding_only_FC_CPU_vs_original_native_output_rtol_.002_atol_.0002",
    "embedding_only_NPU_all_outputs_rtol_.03_atol_.003_and_actual_STX_hardware_no_CPU_fallback",
    "same_generation_sequence_token_position_upload_event_and_correction_fallback_publication",
    "batch_FC_skip_qualification_when_native_head_count_exceeds_one",
    "supported_Windows_fabric_clock_control_and_observed_held_state_for_GPU_NPU_overlap",
    "full_engine_tok_per_second_AB_with_unchanged_acceptance_and_all_helper_costs",
)


def sha(value):
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError("independently supplied lowercase SHA256 required")
    return value


def native_identity(value):
    return dict(size=value.st_size, device=value.st_dev, inode=value.st_ino,
                mtime_ns=value.st_mtime_ns, ctime_ns=value.st_ctime_ns)


def captured(path, expected_sha):
    path = Path(path)
    if not path.is_absolute():
        raise ValueError("absolute source/JSON path required")
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= MAX_METADATA_BYTES:
        raise ValueError("bounded regular source/JSON required")
    with path.open("rb") as stream:
        opened = os.fstat(stream.fileno())
        raw = stream.read(before.st_size + 1)
        after = os.fstat(stream.fileno())
    end = path.lstat()
    fields = ("st_size", "st_dev", "st_ino", "st_mtime_ns")
    fields += ("st_birthtime_ns",) if os.name == "nt" else ("st_ctime_ns",)
    shared = lambda value: tuple(getattr(value, field, None) for field in fields)
    if (not shared(before) == shared(opened) == shared(after) == shared(end) or
            before.st_ctime_ns != end.st_ctime_ns or opened.st_ctime_ns != after.st_ctime_ns or
            len(raw) != before.st_size or hashlib.sha256(raw).hexdigest() != sha(expected_sha)):
        raise ValueError("source/JSON hash or stable file identity differs: " + path.name)
    return raw


def read_json(path, expected_sha):
    return json.loads(captured(path, expected_sha))


def load_source(name):
    """Only the pure scheduler is loaded in metadata planning."""
    captured(HERE / name, SOURCE_PINS[name])
    spec = importlib.util.spec_from_file_location("_early_token_" + Path(name).stem, HERE / name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if Path(module.__file__).resolve() != HERE / name:
        raise ValueError("sealed helper import origin differs")
    return module


def schedule_document(plan):
    return dict(schema="halogen0162.early-token-schedule.v1", generation_hex=plan.generation.hex(),
                sequence=plan.sequence, path=plan.path, start_position=plan.start_position,
                input_tokens=list(plan.input_tokens), next_token=plan.next_token)


def decode_schedule(value):
    scheduler = load_source("halogen_mtp_early_token_schedule.py")
    if not isinstance(value, dict):
        raise ValueError("sealed scheduler JSON object required")
    generation_hex = value.get("generation_hex")
    if (not isinstance(generation_hex, str) or len(generation_hex) != 32 or
            any(c not in "0123456789abcdef" for c in generation_hex)):
        raise ValueError("lowercase nonzero 16-byte generation_hex required")
    tokens = value.get("input_tokens")
    if type(tokens) is not list or not 1 <= len(tokens) <= scheduler.MAX_ROWS:
        raise ValueError("bounded copied scheduler token list required")
    plan = scheduler.EarlyTokenPlan(bytes.fromhex(generation_hex), value.get("sequence"), value.get("path"),
                                    value.get("start_position"), tuple(tokens),
                                    value.get("next_token"))
    if value != schedule_document(plan):
        raise ValueError("exact sealed scheduler fields required")
    return plan


def metadata_plan(schedule_value, source_sha, assets):
    captured(Path(__file__).resolve(), source_sha)
    for name, expected in SOURCE_PINS.items():
        captured(HERE / name, expected)
    scheduled = decode_schedule(schedule_value)
    receipts = {name: read_json(Path(assets) / name, expected) for name, expected in RECEIPT_PINS.items()}
    embedding, weights = receipts["embedding-row.json"], receipts["weights.json"]
    for receipt, plan_name in ((embedding, "embedding-row.plan.json"), (weights, "weights.plan.json")):
        parent = receipts[plan_name]
        source = receipt["source"]
        if (receipt.get("schema") != 1 or parent.get("schema") != 1 or source != parent["source"] or
                source["checkpoint_sha256"] != CHECKPOINT_SHA or source["checkpoint_source"] != CHECKPOINT_SOURCE or
                source["native_identity"] != NATIVE_IDENTITY or receipt["source_identity_after"] != NATIVE_IDENTITY or
                receipt["prepared_plan_sha256"] != RECEIPT_PINS[plan_name]):
            raise ValueError("sealed original checkpoint lineage differs")
    if embedding["source"] != weights["source"]:
        raise ValueError("embedding and gamma must belong to one sealed checkpoint")
    entry = [item["source_entry"] for item in embedding["tensors"] if item["name"] == EMBEDDING_ENTRY["name"]]
    gamma = [item["source_entry"] for item in weights["tensors"] if item["name"] == GAMMA_ENTRY["name"]]
    if entry != [EMBEDDING_ENTRY] or gamma != [GAMMA_ENTRY]:
        raise ValueError("original Q4C embedding/BF16 gamma entries differ")
    known = scheduled.producer_tokens
    tokens = known[:MAX_TOKENS]
    code_bytes = WIDTH // 2
    code_extent = (VOCABULARY * code_bytes + 63) // 64 * 64
    scale_stride = (WIDTH // 16 + 15) // 16 * 16
    if EMBEDDING_ENTRY["size"] != 64 + code_extent + VOCABULARY * scale_stride or scale_stride != 160:
        raise ValueError("original Q4C extent differs")
    ranges = []
    if tokens:
        ranges.append(dict(kind="codebook", token=None, offset=EMBEDDING_ENTRY["offset"], bytes=64,
                           independent_sha256=CODEBOOK_SHA))
        for token in tokens:
            for kind, offset, length in (
                    ("codes", EMBEDDING_ENTRY["offset"] + 64 + token * code_bytes, code_bytes),
                    ("scales", EMBEDDING_ENTRY["offset"] + 64 + code_extent + token * scale_stride, scale_stride)):
                ranges.append(dict(kind=kind, token=token, offset=offset, bytes=length,
                                   independent_sha256=FROZEN_HASHES[kind] if token == FROZEN_TOKEN else None))
        ranges.append(dict(kind="raw_gamma", token=None, offset=GAMMA_ENTRY["offset"], bytes=GAMMA_ENTRY["size"],
                           independent_sha256=GAMMA_SHA))
    source_bytes = sum(row["bytes"] for row in ranges)
    output_bytes = len(tokens) * (4 * WIDTH * 4 + 4) + (64 + len(tokens) * (code_bytes + scale_stride) + WIDTH * 2 if tokens else 0)
    if source_bytes > 64 + MAX_TOKENS * 1440 + 5120 or output_bytes > MAX_OUTPUT_BYTES:
        raise ValueError("bounded token producer budget exceeded")
    return dict(schema="halogen0162.early-token-producer-plan.v1", producer_sha256=sha(source_sha),
        schedule=schedule_document(scheduled), source_pins=SOURCE_PINS, receipt_pins=RECEIPT_PINS,
        checkpoint_sha256_lineage=CHECKPOINT_SHA, checkpoint_source=CHECKPOINT_SOURCE,
        checkpoint_native_identity=NATIVE_IDENTITY, embedding_entry=EMBEDDING_ENTRY, gamma_entry=GAMMA_ENTRY,
        producer_tokens=list(tokens), deferred_known_tokens=list(known[MAX_TOKENS:]),
        known_shifted_tokens=list(scheduled.known_shifted_tokens), unknown_tail_requires_original_fallback=scheduled.sampled_tail_unknown,
        source_ranges=ranges, checkpoint_bytes_per_pass=source_bytes, checkpoint_read_passes=2,
        candidate_payload_bytes=output_bytes, max_producer_tokens=MAX_TOKENS, max_candidate_payload_bytes=MAX_OUTPUT_BYTES,
        candidate_ABI=dict(e_norm=dict(dtype="little-endian FLOAT, finite exact BF16 lattice", shape=[1, WIDTH]),
                           e_high=dict(dtype="little-endian FLOAT", shape=[1, WIDTH]),
                           e_low=dict(dtype="little-endian FLOAT", shape=[1, WIDTH]),
                           split="fresh pinned stable.split_operand(e_norm, -1, np)"),
        lifetime="one exact sealed generation/sequence request; no persistent cache or published device output",
        mathematical_early_input_eligibility=True, schedule_entry_live_observed=False,
        required_gates=list(REQUIRED_GATES), gate_status={gate: False for gate in REQUIRED_GATES},
        cpu_tolerance=dict(rtol=.002, atol=.0002), npu_tolerance=dict(rtol=.03, atol=.003),
        native_arbitrary_row_RMS_qualified=False, live_publication_implemented=False, native_FC_skip_admitted=False,
        supported_fabric_clock_overlap_qualified=False, concurrent_GPU_NPU_inference_allowed=False,
        unsupported_HALOGEN_NPU_WITH_GPU_override_allowed=False, full_engine_AB_qualified=False,
        hidden_path="GPU", payload_bytes_read_by_planning=0, npu_executed=False, speed_claim=False)


class SelectedWindowStream:
    """Expose only captured selected windows at their original checkpoint offsets."""
    def __init__(self, windows):
        self.windows = windows
        self.position = 0

    def seek(self, position, whence=0):
        if type(position) is not int or position < 0 or whence != 0:
            raise ValueError("absolute bounded selected-window seek required")
        self.position = position
        return position

    def read(self, length):
        if type(length) is not int or not 0 < length <= WIDTH // 2:
            raise ValueError("bounded selected-window read required")
        for (offset, extent), raw in self.windows.items():
            if offset <= self.position and self.position + length <= offset + extent:
                start = self.position - offset
                self.position += length
                return raw[start:start + length]
        raise ValueError("decoder attempted a read outside selected original Q4C windows")


def checkpoint_windows(plan, checkpoint):
    if os.name != "posix":
        raise ValueError("root-only Linux production required for strict original native fstat identity")
    checkpoint = Path(checkpoint)
    if not checkpoint.is_absolute():
        raise ValueError("absolute original checkpoint path required")
    before = checkpoint.lstat()
    if not stat.S_ISREG(before.st_mode) or native_identity(before) != NATIVE_IDENTITY:
        raise ValueError("original checkpoint pathname identity differs")
    descriptor = os.open(checkpoint, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    windows, observed = {}, []
    try:
        if native_identity(os.fstat(descriptor)) != NATIVE_IDENTITY:
            raise ValueError("original checkpoint handle identity differs")
        for row in plan["source_ranges"]:
            raw = os.pread(descriptor, row["bytes"], row["offset"])
            digest = hashlib.sha256(raw).hexdigest()
            if len(raw) != row["bytes"] or (row["independent_sha256"] is not None and digest != row["independent_sha256"]):
                raise ValueError("selected original checkpoint window differs")
            windows[(row["offset"], row["bytes"])] = raw
            observed.append(dict(**row, observed_sha256=digest))
        for row in plan["source_ranges"]:
            if os.pread(descriptor, row["bytes"], row["offset"]) != windows[(row["offset"], row["bytes"])]:
                raise ValueError("selected original checkpoint window changed during recheck")
        if native_identity(os.fstat(descriptor)) != NATIVE_IDENTITY or native_identity(checkpoint.lstat()) != NATIVE_IDENTITY:
            raise ValueError("original checkpoint identity changed during bounded production reads")
    finally:
        os.close(descriptor)
    return windows, observed


def write_new(directory, name, raw):
    with (directory / name).open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    return dict(file=name, bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


def json_bytes(value):
    return (json.dumps(value, indent=2, allow_nan=False) + "\n").encode("utf-8")


def produce(args):
    plan = read_json(args.plan, args.plan_sha256)
    if plan != metadata_plan(plan["schedule"], args.source_sha256, args.assets):
        raise ValueError("independently sealed current source/metadata plan differs")
    scheduled = decode_schedule(plan["schedule"])
    if args.generation_hex != scheduled.generation.hex() or args.sequence != scheduled.sequence:
        raise ValueError("current generation/sequence differs; discard the entire stale request")
    payloads, rows, observed = [], [], []
    if plan["producer_tokens"]:
        if any(os.environ.get(name) != "1" for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")):
            raise ValueError("all three BLAS/OpenMP thread variables must be 1 before Python starts")
        import numpy as np
        if np.__version__ != "2.5.3":
            raise ValueError("retained NumPy 2.5.3 reference required")
        decoder = load_source("hgn_q4c_slice.py")
        builder = load_source("halogen_npu_v2_d_prepare.py")
        split = load_source("halogen_npu_v2_d_native_projection_stable_split_graph.py")
        windows, observed = checkpoint_windows(plan, args.checkpoint)
        gamma_raw = windows[(GAMMA_ENTRY["offset"], GAMMA_ENTRY["size"])]
        gamma = builder.widen_bf16(np.frombuffer(gamma_raw, dtype="<u2"))
        q4_windows = {key: raw for key, raw in windows.items() if key[0] != GAMMA_ENTRY["offset"]}
        stream = SelectedWindowStream(q4_windows)
        packed_codes, packed_scales = [], []
        for index, token in enumerate(plan["producer_tokens"]):
            decoded = decoder.decode_rows(stream, EMBEDDING_ENTRY, token, 1)
            raw = builder.bf16_input(builder.bf16_rne(decoded), [1, WIDTH], "raw token embedding")
            normalized = builder.bf16_input(builder.rms_bf16(raw, gamma), [1, WIDTH], "normalized token embedding")
            high, low, diagnostics = split.split_operand(normalized, -1, np)
            bf16_words = lambda value: (value.view(np.uint32) >> 16).astype("<u2").tobytes(order="C")
            raw_words, norm_words = bf16_words(raw), bf16_words(normalized)
            decoded_hash = hashlib.sha256(decoded.astype("<f4", copy=False).tobytes(order="C")).hexdigest()
            raw_hash, normalized_hash = hashlib.sha256(raw_words).hexdigest(), hashlib.sha256(norm_words).hexdigest()
            if token == FROZEN_TOKEN and (decoded_hash != FROZEN_HASHES["decoded"] or raw_hash != FROZEN_HASHES["raw"] or
                                         normalized_hash != FROZEN_HASHES["normalized"]):
                raise ValueError("unchanged token14367 decoded/raw/normalized fixture differs")
            prefix = f"{index:03d}-token{token}-"
            row_files = []
            for suffix, value in (("raw.u16", raw_words), ("norm.u16", norm_words),
                                  ("e_norm.f32", normalized.astype("<f4", copy=False).tobytes(order="C")),
                                  ("e_high.f32", high.astype("<f4", copy=False).tobytes(order="C")),
                                  ("e_low.f32", low.astype("<f4", copy=False).tobytes(order="C"))):
                payloads.append((prefix + suffix, value))
                row_files.append(prefix + suffix)
            selected = [row for row in observed if row["token"] == token]
            packed_codes.append(windows[(next(row["offset"] for row in selected if row["kind"] == "codes"), WIDTH // 2)])
            packed_scales.append(windows[(next(row["offset"] for row in selected if row["kind"] == "scales"), 160)])
            rows.append(dict(index=index, token=token, shape=[1, WIDTH], files=row_files,
                             decoded_sha256=decoded_hash, raw_BF16_sha256=raw_hash, norm_BF16_sha256=normalized_hash,
                             split_diagnostics=diagnostics, arbitrary_row_native_parity_admitted=False,
                             candidate_input_only=True, native_FC_skip_admitted=False))
        packed = windows[(EMBEDDING_ENTRY["offset"], 64)] + b"".join(packed_codes) + b"".join(packed_scales)
        payloads.extend((("selected-rows.q4c", packed), ("raw-gamma.u16", gamma_raw),
                         ("tokens.i32", np.array(plan["producer_tokens"], dtype="<i4").tobytes(order="C"))))
        if native_identity(Path(args.checkpoint).lstat()) != NATIVE_IDENTITY:
            raise ValueError("original checkpoint identity changed during candidate arithmetic")
    if sum(len(raw) for _, raw in payloads) != plan["candidate_payload_bytes"]:
        raise ValueError("candidate output extent differs from sealed bounded plan")
    if read_json(args.plan, args.plan_sha256) != metadata_plan(plan["schedule"], args.source_sha256, args.assets):
        raise ValueError("source/metadata changed before candidate file completion")
    output = Path(args.out)
    if not output.is_absolute():
        raise ValueError("absolute exclusive output directory required")
    output.mkdir(mode=0o700, parents=False, exist_ok=False)
    files = [write_new(output, name, raw) for name, raw in payloads]
    result = dict(schema="halogen0162.early-token-producer-candidates.v1", completed=True,
        plan_sha256=sha(args.plan_sha256), producer_sha256=plan["producer_sha256"],
        generation_hex=scheduled.generation.hex(), sequence=scheduled.sequence, schedule=plan["schedule"],
        candidate_tokens=plan["producer_tokens"], deferred_known_tokens=plan["deferred_known_tokens"],
        unknown_tail_requires_original_fallback=plan["unknown_tail_requires_original_fallback"], rows=rows, files=files,
        observed_source_ranges=observed, checkpoint_payload_bytes_read=2 * plan["checkpoint_bytes_per_pass"],
        checkpoint_whole_file_rehashed=False, FC_weight_payload_read=False, hidden_payload_read=False,
        CPU_FC_executed=False, normalized_candidate_RMS="unchanged canonical NumPy whole-row RMS; arbitrary native rsq/reduction parity unqualified",
        selected_native_pack=dict(rows=len(rows), width=WIDTH, code_offset=64, scale_offset=64 + len(rows) * (WIDTH // 2),
                                  scale_stride=160, rebased_private_fixture_only=True, original_full_table_qualified=False),
        cpu_tolerance=plan["cpu_tolerance"], npu_tolerance=plan["npu_tolerance"],
        required_gates=plan["required_gates"], gate_status=plan["gate_status"],
        generation_checkpoint_live_binding_proved=False, live_publication_implemented=False,
        native_FC_skip_admitted=False, device_upload_completed=False, npu_executed=False,
        supported_fabric_clock_overlap_qualified=False, concurrent_GPU_NPU_inference_allowed=False,
        full_engine_AB_qualified=False, speed_claim=False)
    if read_json(args.plan, args.plan_sha256) != metadata_plan(plan["schedule"], args.source_sha256, args.assets):
        raise ValueError("source/metadata changed before completion receipt")
    if rows and native_identity(Path(args.checkpoint).lstat()) != NATIVE_IDENTITY:
        raise ValueError("original checkpoint identity changed before completion receipt")
    receipt = write_new(output, "complete.json", json_bytes(result))
    return dict(receipt=str(output / "complete.json"), receipt_sha256=receipt["sha256"],
                candidate_tokens=plan["producer_tokens"], native_FC_skip_admitted=False, speed_claim=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare-only", action="store_true")
    mode.add_argument("--produce", action="store_true")
    parser.add_argument("--source-sha256", required=True)
    parser.add_argument("--assets", type=Path, default=ASSETS)
    parser.add_argument("--schedule", type=Path)
    parser.add_argument("--schedule-sha256")
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--plan-sha256")
    parser.add_argument("--generation-hex")
    parser.add_argument("--sequence", type=int)
    parser.add_argument("--checkpoint", type=Path, default=Path(CHECKPOINT_SOURCE))
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    if args.prepare_only:
        if not args.schedule or not args.schedule_sha256 or not args.plan.is_absolute():
            parser.error("prepare-only requires absolute sealed schedule/plan paths and schedule SHA256")
        plan = metadata_plan(read_json(args.schedule, args.schedule_sha256), args.source_sha256, args.assets)
        receipt = write_new(args.plan.parent, args.plan.name, json_bytes(plan))
        print(json.dumps(dict(plan=str(args.plan), plan_sha256=receipt["sha256"],
                              producer_tokens=plan["producer_tokens"], payload_bytes_read=0), indent=2))
    else:
        if not args.plan_sha256 or not args.generation_hex or args.sequence is None or not args.out:
            parser.error("produce requires sealed plan hash, current generation/sequence and exclusive output directory")
        print(json.dumps(produce(args), indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
