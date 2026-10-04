"""Bounded real-v2 shared-expert/router preparation for live MTP replay.

CPU reference only. This loads the missing dense MLP weights, not attention,
hyperconnection state or the lm-head. No inference backend or NPU is launched.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from halogen_npu_mtp_metadata import metadata
from halogen_npu_v2_sparse import (
    CHECKPOINT_SHA256, METADATA_SHA256, DECODER_SHA256,
    native_identity, expert, reserve,
)

ROOT = Path(r"C:\Projects\strix-alloy-clean")
METADATA = Path(r"C:\AI\halogen-mtp-npu\v2-metadata-20261004\mtp-metadata.json")
BACKEND = ROOT / "backends/halogen-wsl2-0.16.2/.local"
PREFIX = "mtp.layers.0.mlp."
LIMIT = 64 * 1024**2


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def decode_q8g64(stream, entry):
    """Decode bounded affine u8 rows: FP16 scale/bias per 64 values."""
    width, rows = entry["dims"][-1], math.prod(entry["dims"][:-1])
    row_bytes = width + width // 16
    if ((entry["store"], entry["variant"]) != (7, 0) or width % 64 or
            rows * row_bytes != entry["size"] or rows * width * 4 > LIMIT):
        raise ValueError("Unsupported or unbounded q8g64 tensor")
    stream.seek(entry["offset"])
    payload = stream.read(entry["size"])
    if len(payload) != entry["size"]:
        raise ValueError("Truncated q8g64 tensor")
    raw = np.frombuffer(payload, dtype=np.uint8).reshape(rows, row_bytes)
    codes = raw[:, :width].reshape(rows, width // 64, 64).astype(np.float32)
    affine = raw[:, width:].copy().view("<f2").reshape(rows, width // 64, 2).astype(np.float32)
    value = (codes * affine[..., 0, None] + affine[..., 1, None]).reshape(rows, width)
    if not np.isfinite(value).all():
        raise ValueError("Nonfinite q8g64 weights")
    return value, dict(name=entry["name"], source_bytes=len(payload),
                       payload_sha256=hashlib.sha256(payload).hexdigest(),
                       decoded_sha256=hashlib.sha256(value.tobytes()).hexdigest())


def load_dense_mlp():
    samples = []
    reserve(samples, 4 * LIMIT)
    if digest(METADATA) != METADATA_SHA256 or digest(Path(__file__).with_name("hgn_q4c_slice.py")) != DECODER_SHA256:
        raise ValueError("Frozen metadata or decoder differs")
    expected = json.loads(METADATA.read_text())["sources"]["v2"]
    integrity = json.loads((BACKEND / "v2-integrity.json").read_text())
    machine = json.loads((BACKEND / "machine.json").read_text())
    if integrity["sha256"] != CHECKPOINT_SHA256:
        raise ValueError("Wrong v2 integrity receipt")
    source = machine["models"] + "/qwen38-flash-next-v2.hgn"
    unc = Path("\\\\wsl.localhost\\" + machine["distro"] + source.replace("/", "\\"))
    before = native_identity(machine, source)
    if str(unc) != expected["path"] or before != integrity["identity"]:
        raise ValueError("v2 checkpoint identity differs")
    actual = metadata(unc)
    if any(actual[key] != expected[key] for key in (
            "identity", "file_size", "version", "tensor_count", "header_sha256", "table_sha256", "entries")):
        raise ValueError("v2 metadata differs")
    entries = {item["name"]: item for item in actual["entries"]}
    weights, records = {}, []
    with unc.open("rb") as stream:
        entry = entries[PREFIX + "gate.weight"]
        if (entry["store"], entry["variant"], entry["dims"], entry["size"]) != (0, 0, [512, 2560], 2621440):
            raise ValueError("Wrong router geometry")
        stream.seek(entry["offset"])
        raw = stream.read(entry["size"])
        if len(raw) != entry["size"]:
            raise ValueError("Truncated router")
        weights["router"] = (np.frombuffer(raw, dtype="<u2").astype(np.uint32) << 16).view(np.float32).reshape(512, 2560)
        records.append(dict(name=entry["name"], source_bytes=len(raw), payload_sha256=hashlib.sha256(raw).hexdigest()))
        for key, shape in (("shared_gate", [640, 2560]), ("shared_up", [640, 2560]), ("shared_down", [2560, 640])):
            name = {"shared_gate": "gate_proj", "shared_up": "up_proj", "shared_down": "down_proj"}[key]
            entry = entries[PREFIX + "shared_expert." + name + ".weight"]
            if entry["dims"] != shape:
                raise ValueError("Wrong shared-expert geometry")
            reserve(samples, LIMIT)
            weights[key], record = decode_q8g64(stream, entry)
            records.append(record)
        entry = entries[PREFIX + "shared_expert_gate.weight"]
        if entry["dims"] != [1, 2560]:
            raise ValueError("Wrong shared routing gate")
        weights["shared_coefficient"], record = expert(stream, entry, 0, 1)
        records.append(record)
    if native_identity(machine, source) != before:
        raise ValueError("v2 checkpoint changed during dense decode")
    if any(not np.isfinite(value).all() for value in weights.values()):
        raise ValueError("Nonfinite dense MLP weights")
    reserve(samples)
    return weights, dict(scope=__doc__, checkpoint_sha256=CHECKPOINT_SHA256,
        native_identity=before, metadata_sha256=METADATA_SHA256, source_records=records,
        array_shapes={key: list(value.shape) for key, value in weights.items()},
        array_sha256={key: hashlib.sha256(value.tobytes()).hexdigest() for key, value in weights.items()},
        decoded_bytes=sum(value.nbytes for value in weights.values()), source_sha256=digest(__file__),
        minimum_available_gib=min(value["available_bytes"] for value in samples) / 2**30,
        minimum_commit_headroom_gib=min(value["commit_headroom_bytes"] for value in samples) / 2**30)


def sigmoid(value):
    e = np.exp(-np.abs(value))
    return np.where(value >= 0, 1 / (1 + e), e / (1 + e))


def shared_reference(x, weights):
    if x.dtype != np.float32 or x.shape != (1, 2560) or not np.isfinite(x).all():
        raise ValueError("Expected finite FP32[1,2560] live MLP input")
    gate = x @ weights["shared_gate"].T
    up = x @ weights["shared_up"].T
    activation = gate * sigmoid(gate) * up
    output = activation @ weights["shared_down"].T
    coefficient = sigmoid(x @ weights["shared_coefficient"].T)
    return output * coefficient


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists() or args.out.with_suffix(".json").exists():
        raise FileExistsError("Existing dense MLP artifacts refused")
    weights, receipt = load_dense_mlp()
    with args.out.open("xb") as stream:
        np.savez(stream, **weights)
    receipt.update(output=str(args.out), output_sha256=digest(args.out))
    with args.out.with_suffix(".json").open("x", encoding="utf-8") as stream:
        json.dump(receipt, stream, indent=2)
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
