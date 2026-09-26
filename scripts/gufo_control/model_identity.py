"""Bounded identity check for the first GUFO Flash Next AR4k model profile."""

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path

from .gguf import GgufError, MAX_HEADER, SCALARS, _Reader, inspect_gguf


class ModelIdentityError(ValueError):
    """The selected files do not match the pinned first AR4k profile."""


@dataclass(frozen=True)
class ShardPin:
    filename: str
    size_bytes: int
    descriptor_end: int
    descriptor_sha256: str
    tensor_count: int
    split_no: int


@dataclass(frozen=True)
class ProfilePins:
    revision: str
    shards: tuple[ShardPin, ShardPin, ShardPin]
    first_scalars: dict
    arrays: dict


@dataclass(frozen=True)
class ValidatedModel:
    first_shard: Path
    revision: str
    context_capacity: int = 4096
    sessions: int = 1
    mtp_enabled: bool = False


AR4K_PINS = ProfilePins(
    revision='38bb39ee97821de2c9009abb7e93950eec396e66',
    shards=(
        ShardPin('Qwen3.8-Flash-Next-UD-IQ4_XS-00001-of-00003.gguf',
                 10946624, 10946618,
                 '9cd7aa82ad189b54ea3c97d1c89463b4473f9f6bd9472b8381c42236e5915de8', 0, 0),
        ShardPin('Qwen3.8-Flash-Next-UD-IQ4_XS-00002-of-00003.gguf',
                 49835229856, 23584,
                 '65aed4c0d6ffeda13b7188179f3c4d9764076012eedacf7cc5e4df52f46d7f70', 373, 1),
        ShardPin('Qwen3.8-Flash-Next-UD-IQ4_XS-00003-of-00003.gguf',
                 43836407744, 54317,
                 'f23293bb029821907bf79414b2a88d698ce66e87b274602d120bbcb3fe08c4a9', 851, 2),
    ),
    first_scalars={
        'general.architecture': 'qwen4exp',
        'qwen4exp.block_count': 48,
        'qwen4exp.context_length': 262144,
        'qwen4exp.embedding_length': 2560,
        'qwen4exp.attention.head_count': 24,
        'qwen4exp.attention.head_count_kv': 2,
        'qwen4exp.attention.key_length': 256,
        'qwen4exp.attention.value_length': 256,
        'qwen4exp.attention.layer_norm_rms_epsilon': 9.999999974752427e-7,
        'qwen4exp.full_attention_interval': 4,
        'qwen4exp.expert_count': 512,
        'qwen4exp.expert_used_count': 10,
        'qwen4exp.expert_feed_forward_length': 640,
        'qwen4exp.expert_shared_feed_forward_length': 640,
        'qwen4exp.ssm.conv_kernel': 4,
        'qwen4exp.ssm.state_size': 128,
        'qwen4exp.ssm.group_count': 16,
        'qwen4exp.ssm.time_step_rank': 48,
        'qwen4exp.ssm.inner_size': 6144,
        'qwen4exp.hyper_connection.count': 4,
        'qwen4exp.hyper_connection.low_rank': 320,
        'qwen4exp.attention.indexer.head_count': 4,
        'qwen4exp.attention.indexer.key_length': 128,
        'qwen4exp.attention.indexer.top_k': 2048,
        'qwen4exp.rope.dimension_count': 64,
        'qwen4exp.rope.freq_base': 10000000.0,
        'qwen4exp.ple.ngram_size': 3,
        'qwen4exp.ple.heads_per_ngram': 8,
        'qwen4exp.ple.conv_kernel': 4,
        'qwen4exp.ple.eos_token_id': 248044,
        'qwen4exp.ple.image_token_id': 248056,
        'qwen4exp.embedding_length_per_layer_input': 160,
    },
    arrays={
        'qwen4exp.attention.compress_ratios': (0, 0, 0, 4) * 12,
        'qwen4exp.rope.dimension_sections': (11, 11, 10, 0),
        'qwen4exp.ple.layers': (1,),
        'qwen4exp.ple.head_offsets': (
            0, 20000003, 40000026, 60000059, 80000106, 100000165,
            120000228, 140000297, 160000374, 180000455, 200000548,
            220000655, 240000802, 260000955, 280001114, 300001275),
        'qwen4exp.ple.head_vocab_sizes': (
            20000003, 20000023, 20000033, 20000047, 20000059, 20000063,
            20000069, 20000077, 20000081, 20000093, 20000107, 20000147,
            20000153, 20000159, 20000161, 20000171),
        'qwen4exp.ple.layer_multipliers': (
            23703573157769, 20109073645365, 8052911324071),
    },
)


def _numeric_arrays(path: Path, wanted: dict) -> dict:
    """Retain only requested short numeric arrays from the bounded header."""
    found = {}
    with path.open('rb', buffering=0) as stream:
        reader = _Reader(stream, os.fstat(stream.fileno()).st_size)
        if reader.advance(4) != b'GGUF' or reader.number('I') != 3:
            raise GgufError('expected GGUF v3')
        reader.number('Q')  # tensor count; inspect_gguf validates the directory
        count = reader.number('Q')
        if count > 100000:
            raise GgufError('metadata count exceeds limit')
        for _ in range(count):
            key = reader.string(limit=64 << 10)
            kind = reader.number('I')
            if key not in wanted:
                reader.value(kind)
                continue
            if kind != 9 or key in found:
                raise ModelIdentityError(f'invalid profile array: {key}')
            subtype, length = reader.number('I'), reader.number('Q')
            if subtype not in SCALARS or length > 256:
                raise ModelIdentityError(f'invalid profile array type/count: {key}')
            found[key] = tuple(reader.number(SCALARS[subtype]) for _ in range(length))
        if stream.tell() > MAX_HEADER:
            raise GgufError('descriptor exceeds limit')
    return found


def _descriptor_digest(path: Path, end: int, expected_size: int, expected_mtime: int) -> str:
    if not 0 <= end <= MAX_HEADER:
        raise ModelIdentityError('descriptor length outside bound')
    digest = hashlib.sha256()
    with path.open('rb', buffering=0) as stream:
        before = os.fstat(stream.fileno())
        if (before.st_size, before.st_mtime_ns) != (expected_size, expected_mtime):
            raise ModelIdentityError('file changed before descriptor hashing')
        remaining = end
        while remaining:
            block = stream.read(min(1 << 20, remaining))
            if not block:
                raise ModelIdentityError('truncated descriptor')
            digest.update(block)
            remaining -= len(block)
        after = os.fstat(stream.fileno())
        if (after.st_size, after.st_mtime_ns) != (expected_size, expected_mtime):
            raise ModelIdentityError('file changed during descriptor hashing')
    return digest.hexdigest()


def _reject_projector(model_dir: Path) -> None:
    for directory in (model_dir, model_dir.parent):
        try:
            if any(entry.name.casefold() == 'mmproj-bf16.gguf' for entry in directory.iterdir()):
                raise ModelIdentityError(f'GUFO projector auto-discovery candidate: {directory}')
        except OSError as error:
            raise ModelIdentityError(f'cannot inspect projector directory: {directory}') from error


def validate_ar4k_model(first_shard: str | Path, *, pins: ProfilePins = AR4K_PINS) -> ValidatedModel:
    """Validate the pinned three-shard target without reading tensor payloads."""
    try:
        first = Path(first_shard).resolve(strict=True)
        if first.name != pins.shards[0].filename:
            raise ModelIdentityError('first shard path/name mismatch')
        _reject_projector(first.parent)
        total = 0
        for pin in pins.shards:
            candidate = first.parent / pin.filename
            path = candidate.resolve(strict=True)
            if path != candidate or path.parent != first.parent:
                raise ModelIdentityError(f'shard escapes model directory: {pin.filename}')
            report = inspect_gguf(path)
            if (report['size_bytes'], report['descriptor_end'], len(report['tensors'])) != (
                    pin.size_bytes, pin.descriptor_end, pin.tensor_count):
                raise ModelIdentityError(f'shard size/directory mismatch: {pin.filename}')
            if _descriptor_digest(path, pin.descriptor_end,
                                  report['size_bytes'], report['mtime_ns']) != pin.descriptor_sha256:
                raise ModelIdentityError(f'shard descriptor mismatch: {pin.filename}')
            metadata = report['metadata']
            for key, value in {'split.no': pin.split_no, 'split.count': 3,
                               'split.tensors.count': sum(
                                   item.tensor_count for item in pins.shards)}.items():
                if type(metadata.get(key)) is not int or metadata[key] != value:
                    raise ModelIdentityError(f'shard split metadata mismatch: {pin.filename}: {key}')
            if pin.split_no == 0:
                for key, value in pins.first_scalars.items():
                    if type(metadata.get(key)) is not type(value) or metadata[key] != value:
                        raise ModelIdentityError(f'first shard scalar mismatch: {key}')
                if any(key.startswith('qwen4exp.nextn_') for key in metadata):
                    raise ModelIdentityError('MTP metadata in AR first shard')
                if _numeric_arrays(path, pins.arrays) != pins.arrays:
                    raise ModelIdentityError('first shard geometry arrays mismatch')
            elif set(metadata) != {'split.no', 'split.count', 'split.tensors.count'}:
                raise ModelIdentityError(f'unexpected metadata in split shard: {pin.filename}')
            total += len(report['tensors'])
        if total != sum(pin.tensor_count for pin in pins.shards):
            raise ModelIdentityError('total tensor count mismatch')
        _reject_projector(first.parent)
        return ValidatedModel(first, pins.revision)
    except (GgufError, OSError) as error:
        raise ModelIdentityError(f'model identity inspection failed: {error}') from error
