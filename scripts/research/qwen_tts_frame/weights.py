"""Read the pinned Qwen3-TTS acoustic frame weights into CPU float32 arrays."""

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path

import numpy as np

from scripts.gufo_control.gguf import inspect_gguf


MODEL_PATH = Path('C:/AI/models/qwen3-tts-gguf/qwen-talker-0.6b-base-Q8_0.gguf')
MODEL_BYTES = 992_615_488
HEADER_BYTES = 5_954_368
HEADER_SHA256 = 'fc8b6f7c3cb6efef058dd59ce0a2be16bcda8dafaaf006f73816663eeb2a8e34'
FRAME_PAYLOAD_BYTES = 153_797_632
# Concatenation of selected tensor payloads in ascending GGUF file offset.
FRAME_PAYLOAD_SHA256 = '09cc2c184dd9af77116389a0aaca6aeb9d3639e0ddfa148890483ca79cfa97f4'
TALKER_CODEC_EMBEDDING = 'talker.codec_embd.weight'
Q8_0_BLOCK = np.dtype([('scale', '<f2'), ('quants', 'i1', (32,))])


@dataclass(frozen=True)
class FrameArchitecture:
    hidden_size: int
    intermediate_size: int
    num_hidden_layers: int
    num_attention_heads: int
    num_key_value_heads: int
    head_dim: int
    vocab_size: int
    num_acoustic_codebooks: int
    rope_theta: float
    rms_norm_eps: float
    talker_hidden_size: int
    talker_vocab_size: int
    context_length: int


@dataclass(frozen=True)
class FrameWeights:
    architecture: FrameArchitecture
    tensors: dict[str, np.ndarray]
    receipt: dict


def _architecture(metadata):
    prefix = 'qwen3-tts.code_pred.'
    return FrameArchitecture(
        hidden_size=metadata[prefix + 'embedding_length'],
        intermediate_size=metadata[prefix + 'feed_forward_length'],
        num_hidden_layers=metadata[prefix + 'block_count'],
        num_attention_heads=metadata[prefix + 'attention.head_count'],
        num_key_value_heads=metadata[prefix + 'attention.head_count_kv'],
        head_dim=metadata[prefix + 'attention.key_length'],
        vocab_size=metadata[prefix + 'vocab_size'],
        num_acoustic_codebooks=metadata['qwen3-tts.num_code_groups'] - 1,
        rope_theta=metadata[prefix + 'rope.freq_base'],
        rms_norm_eps=metadata[prefix + 'attention.layer_norm_rms_epsilon'],
        talker_hidden_size=metadata['qwen3-tts.talker.embedding_length'],
        talker_vocab_size=metadata['qwen3-tts.talker.vocab_size'],
        context_length=metadata[prefix + 'context_length'],
    )


def _tensor_dimensions(architecture):
    hidden = architecture.hidden_size
    intermediate = architecture.intermediate_size
    head = architecture.head_dim
    q_width = head * architecture.num_attention_heads
    kv_width = head * architecture.num_key_value_heads
    shapes = {
        TALKER_CODEC_EMBEDDING: (architecture.talker_hidden_size, architecture.talker_vocab_size),
        'code_pred.output_norm.weight': (hidden,),
    }
    for group in range(architecture.num_acoustic_codebooks):
        for projection in ('codec_embd', 'lm_head'):
            shapes[f'code_pred.{projection}.{group}.weight'] = (hidden, architecture.vocab_size)
    layer_shapes = {
        'attn_norm': (hidden,), 'ffn_norm': (hidden,),
        'attn_q': (hidden, q_width), 'attn_k': (hidden, kv_width),
        'attn_v': (hidden, kv_width), 'attn_output': (q_width, hidden),
        'attn_q_norm': (head,), 'attn_k_norm': (head,),
        'ffn_gate': (hidden, intermediate), 'ffn_up': (hidden, intermediate),
        'ffn_down': (intermediate, hidden),
    }
    for layer in range(architecture.num_hidden_layers):
        for name, shape in layer_shapes.items():
            shapes[f'code_pred.blk.{layer}.{name}.weight'] = shape
    return shapes


def _decode_tensor(raw, descriptor):
    kind = descriptor['ggml_type']
    if kind == 8:
        blocks = np.frombuffer(raw, dtype=Q8_0_BLOCK)
        scales = blocks['scale'].astype(np.float32)
        values = np.multiply(scales[:, None], blocks['quants'], dtype=np.float32)
    elif kind in (0, 1):
        values = np.frombuffer(raw, dtype='<f4' if kind == 0 else '<f2').astype(np.float32)
    elif kind == 30:
        bits = np.frombuffer(raw, dtype='<u2').astype(np.uint32) << 16
        values = bits.view(np.float32)
    else:
        raise ValueError(f'Unsupported frame tensor storage {kind}: {descriptor["name"]}')
    values = values.reshape(tuple(reversed(descriptor['dimensions'])))
    if not np.isfinite(values).all():
        raise ValueError(f'Non-finite frame tensor: {descriptor["name"]}')
    values.setflags(write=False)
    return values


def _identity(stat):
    return tuple(getattr(stat, key) for key in
                 ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns'))


def load_weights(path: str | Path = MODEL_PATH) -> FrameWeights:
    """Load only predictor weights and the Talker codec embedding for the frame.

    Matrices are in [output, input] order, suitable for ``x @ weight.T``.
    The receipt covers the GGUF header and selected tensor bytes only.
    """
    path = Path(path).resolve(strict=True)
    weights = {}
    payload_bytes = 0
    payload_sha = hashlib.sha256()
    with path.open('rb') as stream:
        before = os.fstat(stream.fileno())
        descriptor = inspect_gguf(path)
        if (before.st_size != MODEL_BYTES or descriptor['size_bytes'] != MODEL_BYTES
                or descriptor['mtime_ns'] != before.st_mtime_ns
                or descriptor['data_offset'] != HEADER_BYTES):
            raise ValueError('GGUF size or descriptor layout does not match the pinned frame model')
        if hashlib.sha256(stream.read(HEADER_BYTES)).hexdigest() != HEADER_SHA256:
            raise ValueError('GGUF header does not match the pinned frame model')

        architecture = _architecture(descriptor['metadata'])
        expected = _tensor_dimensions(architecture)
        selected = {
            tensor['name']: tensor for tensor in descriptor['tensors']
            if tensor['name'].startswith('code_pred.') or tensor['name'] == TALKER_CODEC_EMBEDDING
        }
        if selected.keys() != expected.keys():
            raise ValueError('GGUF frame tensor inventory does not match the pinned architecture')

        for name, tensor in sorted(selected.items(), key=lambda item: item[1]['offset']):
            if tuple(tensor['dimensions']) != expected[name]:
                raise ValueError(f'Unexpected dimensions for frame tensor {name}')
            stream.seek(HEADER_BYTES + tensor['offset'])
            raw = stream.read(tensor['size_bytes'])
            if len(raw) != tensor['size_bytes']:
                raise ValueError(f'Truncated frame tensor: {name}')
            payload_bytes += len(raw)
            payload_sha.update(raw)
            weights[name] = _decode_tensor(raw, tensor)

        after = os.fstat(stream.fileno())
        with path.open('rb') as current:
            resolved = os.fstat(current.fileno())
        if _identity(before) != _identity(after) or _identity(after) != _identity(resolved):
            raise ValueError('GGUF changed while reading frame weights')
    if payload_bytes != FRAME_PAYLOAD_BYTES or payload_sha.hexdigest() != FRAME_PAYLOAD_SHA256:
        raise ValueError('GGUF frame payload does not match the pinned frame model')

    receipt = {
        'path': str(path),
        'file_bytes': before.st_size,
        'file_mtime_ns': before.st_mtime_ns,
        'header_bytes': HEADER_BYTES,
        'header_sha256': HEADER_SHA256,
        'frame_payload_bytes': payload_bytes,
        'frame_payload_sha256': payload_sha.hexdigest(),
        'frame_tensor_count': len(weights),
    }
    return FrameWeights(architecture, weights, receipt)
