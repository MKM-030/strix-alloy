"""Explicit offline CPU original-tree RMS adapter for the sealed token producer.

Consumes an existing original producer plan; original producer/receipts remain
unchanged. Reuses its bounded checkpoint windows, decoder, BF16 and fresh split
helpers. New CPU normalization applies one uniform portable tree to1..64 rows.
No FC/hidden input, provider, device, live publication or speed admission.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import struct


HERE = Path(__file__).resolve().parent
ORIGINAL_SHA = "56ebe190cdbdc47a50b6c6930172cb6cf274f04995276100c4c8537325ee1da5"
PORTABLE_SHA = "4ed6f25305c0ef714a85af2977a094b936b433d0912b781dbc46fab7e2e8f02a"


def load(name, expected_sha):
    with (HERE / name).open("rb") as stream:
        source = stream.read((2 << 20) + 1)
    if not 0 < len(source) <= 2 << 20 or hashlib.sha256(source).hexdigest() != expected_sha:
        raise ValueError("bounded sealed adapter helper source differs")
    spec = importlib.util.spec_from_file_location("_native_rms_" + Path(name).stem, HERE / name)
    module = importlib.util.module_from_spec(spec)
    exec(compile(source, str(HERE / name), "exec"), module.__dict__)
    if Path(module.__file__).resolve() != HERE / name:
        raise ValueError("sealed adapter helper import origin differs")
    return module


def produce(args):
    original_path = HERE / "halogen_mtp_early_token_producer.py"
    # Loading this stdlib-only source performs no tensor/numerical import.
    original = load(original_path.name, ORIGINAL_SHA)
    original.captured(original_path, ORIGINAL_SHA)
    original.captured(Path(__file__).resolve(), args.source_sha256)
    portable_path = HERE / "halogen0162_embedding_rms_cpu_tree_portable.py"
    original.captured(portable_path, PORTABLE_SHA)
    plan = original.read_json(args.plan, args.plan_sha256)
    def recheck():
        original.captured(original_path, ORIGINAL_SHA)
        original.captured(Path(__file__).resolve(), args.source_sha256)
        original.captured(portable_path, PORTABLE_SHA)
        if original.read_json(args.plan, args.plan_sha256) != plan or plan != original.metadata_plan(plan["schedule"], ORIGINAL_SHA, args.assets):
            raise ValueError("original source/metadata plan changed")
    recheck()
    scheduled = original.decode_schedule(plan["schedule"])
    if args.generation_hex != scheduled.generation.hex() or args.sequence != scheduled.sequence:
        raise ValueError("current generation/sequence differs; discard stale request")
    tokens = plan["producer_tokens"]
    if not 1 <= len(tokens) <= 64:
        raise ValueError("explicit nonempty bounded1..64 original token rows required")
    if any(os.environ.get(name) != "1" for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")):
        raise ValueError("all three BLAS/OpenMP thread variables must be1 before Python starts")
    import numpy as np
    if np.__version__ != "2.5.3":
        raise ValueError("retained NumPy2.5.3 required")
    decoder = original.load_source("hgn_q4c_slice.py")
    builder = original.load_source("halogen_npu_v2_d_prepare.py")
    split = original.load_source("halogen_npu_v2_d_native_projection_stable_split_graph.py")
    portable = load(portable_path.name, PORTABLE_SHA)
    windows, observed = original.checkpoint_windows(plan, args.checkpoint)
    gamma_raw = windows[(original.GAMMA_ENTRY["offset"], 5120)]
    gamma_words = struct.unpack("<2560H", gamma_raw)
    stream = original.SelectedWindowStream({key: raw for key, raw in windows.items() if key[0] != original.GAMMA_ENTRY["offset"]})
    payloads, rows, codes, scales = [], [], [], []
    for index, token in enumerate(tokens):
        decoded = decoder.decode_rows(stream, original.EMBEDDING_ENTRY, token, 1)
        raw = builder.bf16_input(builder.bf16_rne(decoded), [1, 2560], "raw token embedding")
        raw_bytes = (raw.view(np.uint32) >> 16).astype("<u2").tobytes(order="C")
        normalized_words, diagnostics = portable.rms_bf16_words(struct.unpack("<2560H", raw_bytes), gamma_words,
                                                               accumulation="portable_exact_square")
        norm_bytes = struct.pack("<2560H", *normalized_words)
        normalized = builder.bf16_input(builder.widen_bf16(np.frombuffer(norm_bytes, dtype="<u2")).reshape(1, 2560),
                                       [1, 2560], "portable original-tree normalized embedding")
        high, low, split_diagnostics = split.split_operand(normalized, -1, np)
        raw_sha, norm_sha = hashlib.sha256(raw_bytes).hexdigest(), hashlib.sha256(norm_bytes).hexdigest()
        if token == original.FROZEN_TOKEN:
            decoded_sha = hashlib.sha256(decoded.astype("<f4", copy=False).tobytes(order="C")).hexdigest()
            if (decoded_sha != original.FROZEN_HASHES["decoded"] or raw_sha != original.FROZEN_HASHES["raw"]
                    or norm_sha != original.FROZEN_HASHES["normalized"]):
                raise ValueError("frozen token14367 decoded/raw/normalized hashes differ")
        prefix = f"{index:03d}-token{token}-"
        for suffix, value in (("raw.u16", raw_bytes), ("norm.u16", norm_bytes), ("e_norm.f32", normalized),
                              ("e_high.f32", high), ("e_low.f32", low)):
            data = value if isinstance(value, bytes) else value.astype("<f4", copy=False).tobytes(order="C")
            payloads.append((prefix + suffix, data))
        source_rows = [row for row in observed if row["token"] == token]
        codes.append(windows[(next(row["offset"] for row in source_rows if row["kind"] == "codes"), 1280)])
        scales.append(windows[(next(row["offset"] for row in source_rows if row["kind"] == "scales"), 160)])
        rows.append(dict(index=index, token=token, shape=[1, 2560], raw_BF16_sha256=raw_sha,
                         norm_BF16_sha256=norm_sha, RMS_diagnostics=diagnostics, split_diagnostics=split_diagnostics))
    packed = windows[(original.EMBEDDING_ENTRY["offset"], 64)] + b"".join(codes) + b"".join(scales)
    payloads.extend((("selected-rows.q4c", packed), ("raw-gamma.u16", gamma_raw),
                     ("tokens.i32", struct.pack("<" + "i" * len(tokens), *tokens))))
    if sum(len(raw) for _, raw in payloads) != plan["candidate_payload_bytes"]:
        raise ValueError("bounded original candidate payload extent differs")
    recheck()
    if original.native_identity(args.checkpoint.lstat()) != original.NATIVE_IDENTITY:
        raise ValueError("original checkpoint identity changed")
    if not args.out.is_absolute():
        raise ValueError("absolute exclusive output directory required")
    args.out.mkdir(mode=0o700, parents=False, exist_ok=False)
    files = [original.write_new(args.out, name, raw) for name, raw in payloads]
    recheck()
    if original.native_identity(args.checkpoint.lstat()) != original.NATIVE_IDENTITY:
        raise ValueError("original checkpoint identity changed before completion")
    receipt = dict(schema="halogen0162.early-token-native-rms-candidates.v1", completed=True,
        adapter_sha256=original.sha(args.source_sha256), original_producer_sha256=ORIGINAL_SHA,
        portable_RMS_sha256=PORTABLE_SHA, original_plan_sha256=original.sha(args.plan_sha256),
        generation_hex=scheduled.generation.hex(), sequence=scheduled.sequence, schedule=plan["schedule"],
        candidate_tokens=tokens, deferred_known_tokens=plan["deferred_known_tokens"],
        unknown_tail_requires_original_fallback=plan["unknown_tail_requires_original_fallback"], rows=rows, files=files,
        observed_source_ranges=observed, checkpoint_payload_bytes_read=2 * plan["checkpoint_bytes_per_pass"],
        normalization="uniform portable256-lane original reduction tree; CPU one-round rsqrt; arbitrary native v_rsq parity unqualified",
        cpu_tolerance=plan["cpu_tolerance"], npu_tolerance=plan["npu_tolerance"], gate_status=plan["gate_status"],
        checkpoint_whole_file_rehashed=False, FC_weight_payload_read=False, hidden_payload_read=False, CPU_FC_executed=False,
        original_full_table_loader_qualified=False, live_allocation_qualified=False, live_generation_binding_proved=False,
        native_FC_skip_admitted=False, live_publication_implemented=False, device_upload_completed=False,
        npu_executed=False, concurrent_GPU_NPU_inference_allowed=False, speed_claim=False, arithmetic_fitting=False)
    completed = original.write_new(args.out, "complete.json", original.json_bytes(receipt))
    return dict(receipt=str(args.out / "complete.json"), receipt_sha256=completed["sha256"],
                candidate_tokens=tokens, native_FC_skip_admitted=False, speed_claim=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native-rms", action="store_true", required=True)
    for name in ("source-sha256", "plan-sha256", "generation-hex"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--sequence", type=int, required=True)
    for name in ("plan", "assets", "checkpoint", "out"):
        parser.add_argument("--" + name, type=Path, required=True)
    print(json.dumps(produce(parser.parse_args()), indent=2, allow_nan=False))
