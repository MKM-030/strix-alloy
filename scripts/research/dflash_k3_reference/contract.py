"""Standard-library-only contract for the pinned PixelML K3 reference.

This module never imports a tensor runtime or accesses an accelerator.
"""
from __future__ import annotations

import hashlib
import json
import math
import struct
from dataclasses import dataclass, replace
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

CHECKPOINT_REVISION = "9cd660f9050c92fedc88cbe547bd53af0392abe1"
CHECKPOINT_SHA256 = "35a23c17c248ff2e3296e6b78882b6d955af3092498fb7b6c48be1af4bfa971a"
CHECKPOINT_BYTES = 996219904
OWNER_REVISION = "54b35f57af721ffa8d55f1c0ae79f24952a82fd6"
TOKENIZER_SHA256 = "0997f410c57a1f4e53b09e4be8f4a172d90edd9564368fb0847030937229b9f3"
HIDDEN = 2560
INTERMEDIATE = 7680
LAYERS = 5
Q_HEADS = 24
KV_HEADS = 2
HEAD_DIM = 256
VOCAB = 248320
MASK_ID = 248077
TAP_IDS = (3, 15, 23, 35, 43)
TAP_BOUNDARIES = (4, 16, 24, 36, 44)
MAX_POSITION = 262144
ROPE_THETA = 10000000.0
RMS_EPS = 1e-6
K = 3


def numel(shape):
    return math.prod(shape)


def checkpoint_shapes() -> dict[str, tuple[int, ...]]:
    # Exact inventory in the pinned author's serving/plugin/dflash_epoch7.py.
    result = {"fc.weight": (HIDDEN, 5 * HIDDEN),
              "hidden_norm.weight": (HIDDEN,), "norm.weight": (HIDDEN,)}
    layer_shapes = {
        "input_layernorm.weight": (HIDDEN,),
        "post_attention_layernorm.weight": (HIDDEN,),
        "self_attn.q_proj.weight": (6144, HIDDEN),
        "self_attn.k_proj.weight": (512, HIDDEN),
        "self_attn.v_proj.weight": (512, HIDDEN),
        "self_attn.o_proj.weight": (HIDDEN, 6144),
        "self_attn.q_norm.weight": (HEAD_DIM,),
        "self_attn.k_norm.weight": (HEAD_DIM,),
        "mlp.gate_proj.weight": (INTERMEDIATE, HIDDEN),
        "mlp.up_proj.weight": (INTERMEDIATE, HIDDEN),
        "mlp.down_proj.weight": (HIDDEN, INTERMEDIATE),
    }
    for layer in range(LAYERS):
        result.update({f"layers.{layer}.{name}": shape for name, shape in layer_shapes.items()})
    return result


def validate_config(config: Mapping):
    fields = {
        "architectures": ["Qwen3DSparkModel"], "hidden_size": HIDDEN,
        "intermediate_size": INTERMEDIATE, "num_hidden_layers": LAYERS,
        "num_attention_heads": Q_HEADS, "num_key_value_heads": KV_HEADS,
        "head_dim": HEAD_DIM, "vocab_size": VOCAB, "mask_token_id": MASK_ID,
        "block_size": 7, "markov_rank": 0, "enable_confidence_head": False,
        "attention_bias": False, "hidden_act": "silu", "rms_norm_eps": RMS_EPS,
        "tie_word_embeddings": False, "use_sliding_window": False,
        "layer_types": ["full_attention"] * LAYERS,
        "target_layer_ids": list(TAP_IDS), "num_target_layers": 48,
        "max_position_embeddings": MAX_POSITION,
    }
    for field, expected in fields.items():
        if config.get(field) != expected:
            raise ValueError(f"Wrong pinned config field {field}: {config.get(field)!r}")
    rope = config.get("rope_parameters", {})
    if (rope.get("rope_type") != "default" or rope.get("rope_theta") != ROPE_THETA
            or rope.get("partial_rotary_factor", 1.0) != 1.0):
        raise ValueError("Reference requires full-head default NeoX RoPE theta=1e7")
    if config.get("is_neox_style", True) is not True:
        raise ValueError("Interleaved RoPE is not this checkpoint's convention")


def valid_output_id(token_id):
    # Defined tokenizer IDs include ordinary and special/stop tokens through248076.
    return type(token_id) is int and 0 <= token_id < MASK_ID


@dataclass(frozen=True)
class QueryLayout:
    input_ids: tuple[int, int, int]
    query_positions: tuple[int, int, int]
    output_positions: tuple[int, int, int]
    request_nonce: str = ""
    epoch: int = 0
    round_index: int = 0


def query_layout(*, anchor_id, anchor_position):
    if not valid_output_id(anchor_id):
        raise ValueError("Anchor must be a defined target ID; mask248077 is internal")
    if type(anchor_position) is not int or not 0 <= anchor_position < MAX_POSITION - K:
        raise ValueError("Insufficient target position capacity for current plus K3")
    p = anchor_position
    return QueryLayout((anchor_id, MASK_ID, MASK_ID), (p, p + 1, p + 2), (p + 1, p + 2, p + 3))


@dataclass(frozen=True)
class CommitPlan:
    query: QueryLayout
    retained_indices: tuple[int, ...]
    retained_ids: tuple[int, ...]
    retained_positions: tuple[int, ...]
    next_anchor_position: int
    next_anchor_id: int


class Frontier:
    """One continuing request, one pending round, authoritative commit only.

    `accepted_prefix` comes from the target verifier. This class does not infer it
    from target features, offline labels, or draft logits.
    """
    def __init__(self, request_nonce: str, epoch: int):
        if not request_nonce or type(epoch) is not int or epoch < 0:
            raise ValueError("Request birth nonce and nonnegative epoch are required")
        self.request_nonce, self.epoch = request_nonce, epoch
        self.position = None
        self.round_index = 0
        self.expected_anchor_id = None
        self._query = None
        self._proposal_ids = None
        self._planned = None
        self._retired = False

    def _active(self):
        if self._retired:
            raise ValueError("Request has been retired")

    def initialize(self, positions):
        self._active()
        positions = tuple(positions)
        if (self.position is not None or not positions
                or any(type(p) is not int for p in positions)
                or positions != tuple(range(len(positions)))):
            raise ValueError("Initial context must be the complete contiguous prefix from position0")
        if len(positions) >= MAX_POSITION:
            raise ValueError("Initial context exceeds the trained position range")
        self.position = len(positions)

    def begin(self, round_index, anchor_id, anchor_position):
        self._active()
        if self.position is None or self._query is not None:
            raise ValueError("Initialize context and finish the previous round first")
        if type(round_index) is not int or round_index != self.round_index or anchor_position != self.position:
            raise ValueError("Stale round or wrong accepted context frontier")
        if self.expected_anchor_id is not None and anchor_id != self.expected_anchor_id:
            raise ValueError("Anchor is not the authoritative previous bonus/correction")
        q = replace(query_layout(anchor_id=anchor_id, anchor_position=anchor_position),
                    request_nonce=self.request_nonce, epoch=self.epoch, round_index=round_index)
        self._query = q
        return q

    def record_proposal(self, query, proposal_ids):
        self._active()
        ids = tuple(proposal_ids)
        if query is not self._query or self._proposal_ids is not None:
            raise ValueError("Proposal does not belong to the pending round")
        if len(ids) != K or any(type(x) is not int or not 0 <= x < VOCAB for x in ids):
            raise ValueError("The reference must return all three full-head argmax IDs")
        self._proposal_ids = ids

    def plan_commit(self, round_index, verifier_input_ids, verifier_positions,
                    accepted_prefix, authoritative_bonus_id):
        self._active()
        if (self._query is None or self._proposal_ids is None
                or type(round_index) is not int or round_index != self.round_index):
            raise ValueError("Missing proposal or stale verifier transaction")
        inputs, positions = tuple(verifier_input_ids), tuple(verifier_positions)
        p = self.position
        if inputs != (self._query.input_ids[0],) + self._proposal_ids:
            raise ValueError("Verifier inputs differ from current plus this round's proposals")
        if positions != tuple(range(p, p + K + 1)):
            raise ValueError("Verifier input positions must cover current plus K3")
        if not all(valid_output_id(x) for x in inputs):
            raise ValueError("Reserved mask/padding IDs cannot be offered to the target")
        if type(accepted_prefix) is not int or not 0 <= accepted_prefix <= K:
            raise ValueError("Accepted prefix must come from the target and be in0..3")
        if not valid_output_id(authoritative_bonus_id):
            raise ValueError("Authoritative bonus/correction must be a defined target ID")
        count = accepted_prefix + 1  # processed current input plus accepted draft inputs
        plan = CommitPlan(self._query, tuple(range(count)), inputs[:count], positions[:count],
                          p + count, authoritative_bonus_id)
        self._planned = plan
        return plan

    def finish_commit(self, plan):
        self._active()
        if plan is None or self._query is None or plan is not self._planned or plan.query is not self._query:
            raise ValueError("Commit plan is stale or foreign")
        self.position, self.expected_anchor_id = plan.next_anchor_position, plan.next_anchor_id
        self.round_index += 1
        self._query = self._proposal_ids = self._planned = None

    def retire(self):
        self._retired = True
        self._query = self._proposal_ids = self._planned = None


@dataclass(frozen=True)
class TensorInfo:
    dtype: str
    shape: tuple[int, ...]
    start: int
    end: int


@dataclass(frozen=True)
class TensorManifest:
    path: Path
    data_offset: int
    data_bytes: int
    tensors: Mapping[str, TensorInfo]
    metadata: Mapping[str, str]


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key {key!r}")
        result[key] = value
    return result


def inspect_safetensors(path) -> TensorManifest:
    """Read only a bounded JSON header; never read or execute tensor values."""
    path = Path(path).resolve(strict=True)
    total = path.stat().st_size
    with path.open("rb") as f:
        prefix = f.read(8)
        if len(prefix) != 8:
            raise ValueError("Missing safetensors header length")
        header_bytes = struct.unpack("<Q", prefix)[0]
        if not 2 <= header_bytes <= 8 * 1024 * 1024 or 8 + header_bytes > total:
            raise ValueError("Invalid safetensors header length")
        header = json.loads(f.read(header_bytes).decode("utf-8"), object_pairs_hook=_unique_pairs)
    if not isinstance(header, dict):
        raise ValueError("Safetensors header must be a dictionary")
    metadata = header.pop("__metadata__", {})
    if not isinstance(metadata, dict) or not all(isinstance(k, str) and isinstance(v, str)
                                                for k, v in metadata.items()):
        raise ValueError("Invalid safetensors metadata")
    tensors = {}
    data_bytes = total - 8 - header_bytes
    for name, row in header.items():
        if not isinstance(name, str) or not isinstance(row, dict) or set(row) != {"dtype", "shape", "data_offsets"}:
            raise ValueError("Invalid tensor descriptor")
        dtype, shape, offsets = row["dtype"], row["shape"], row["data_offsets"]
        if dtype not in {"BF16", "F32"}:
            raise ValueError(f"Unsupported reference storage dtype {dtype!r}")
        if not isinstance(shape, list) or any(type(x) is not int or x <= 0 for x in shape):
            raise ValueError(f"Invalid shape for {name}")
        if (not isinstance(offsets, list) or len(offsets) != 2
                or any(type(x) is not int for x in offsets)):
            raise ValueError(f"Invalid offsets for {name}")
        start, end = offsets
        if not 0 <= start <= end <= data_bytes or end - start != numel(shape) * ({"BF16": 2, "F32": 4}[dtype]):
            raise ValueError(f"Tensor size/offset mismatch for {name}")
        tensors[name] = TensorInfo(dtype, tuple(shape), start, end)
    frontier = 0
    for info in sorted(tensors.values(), key=lambda x: x.start):
        if info.start != frontier:
            raise ValueError("Safetensors data has an overlap or uncovered span")
        frontier = info.end
    if not tensors or frontier != data_bytes:
        raise ValueError("Safetensors data is not completely described")
    return TensorManifest(path, 8 + header_bytes, data_bytes,
                          MappingProxyType(tensors), MappingProxyType(metadata))


def sha256_file(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def validate_checkpoint_manifest(manifest):
    shapes = checkpoint_shapes()
    if set(manifest.tensors) != set(shapes):
        raise ValueError("Pinned checkpoint must contain exactly the supplied58 tensors")
    for name, shape in shapes.items():
        info = manifest.tensors[name]
        if info.dtype != "BF16" or info.shape != shape:
            raise ValueError(f"Wrong pinned shape/dtype for {name}")
    if manifest.path.stat().st_size != CHECKPOINT_BYTES:
        raise ValueError("Pinned checkpoint file length differs")
