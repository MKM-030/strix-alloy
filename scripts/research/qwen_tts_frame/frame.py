"""CPU reference for one Qwen3-TTS Base acoustic predictor frame.

The reference reads dequantized Q8_0 weights and uses explicit FP32
attention. Vulkan accumulation and equal-logit sort order may differ.
Compare sampled code IDs against a native fixture before using the result.
"""

from dataclasses import dataclass
import math

import numpy as np


def _softmax(scores):
    weights = np.exp(scores - np.max(scores, axis=-1, keepdims=True))
    return weights / weights.sum(axis=-1, keepdims=True, dtype=np.float32)


def ranked_cdf(logits, temperature, top_k):
    """Return the candidate IDs and cumulative probabilities in replay order."""
    logits = np.asarray(logits, dtype=np.float32)
    if logits.ndim != 1 or not 1 <= top_k <= logits.size:
        raise ValueError('Invalid sampler vocabulary or top-k')
    if not np.isfinite(logits).all() or not math.isfinite(temperature) or temperature <= 0:
        raise ValueError('Sampler requires finite logits and positive effective temperature')
    scaled = logits / np.float32(temperature)
    if not np.isfinite(scaled).all():
        raise ValueError('Non-finite temperature-scaled logits')
    ranked = np.argsort(-scaled, kind='stable')[:top_k]
    cdf = np.cumsum(_softmax(scaled[ranked]), dtype=np.float32)
    return ranked, cdf


def sample_code(logits, temperature, uniform, top_k):
    """Select the first top-k token whose cumulative mass exceeds the draw."""
    if not 0 <= uniform < 1:
        raise ValueError('Sampler draw must be in [0, 1)')
    ranked, cdf = ranked_cdf(logits, temperature, top_k)
    crossings = np.flatnonzero(cdf > np.float32(uniform))
    if not crossings.size:
        raise ValueError('Sampler cumulative mass did not cross the draw')
    return int(ranked[crossings[0]])


def _rms(values, weight, eps):
    square_mean = np.mean(values * values, axis=-1, keepdims=True, dtype=np.float32)
    return (values / np.sqrt(square_mean + eps)) * weight


def _rope_neox(values, cos, sin):
    left, right = np.split(values, 2, axis=-1)
    return np.concatenate((left * cos - right * sin, left * sin + right * cos), axis=-1)


@dataclass(frozen=True)
class FrameResult:
    codes: np.ndarray
    logits: np.ndarray


class FramePredictor:
    """Replay one causal 15-code chain with a new KV cache each time."""

    def __init__(self, weights):
        self.arch = weights.architecture
        self.tensors = weights.tensors
        if (self.arch.hidden_size != self.arch.talker_hidden_size
                or 'code_pred.mtp_proj.weight' in self.tensors):
            raise ValueError('Frame replay requires the Base identity projection')
        if self.arch.head_dim % 2 or self.arch.num_attention_heads % self.arch.num_key_value_heads:
            raise ValueError('Invalid attention geometry')
        self.eps = np.float32(self.arch.rms_norm_eps)
        self.scale = np.float32(1 / math.sqrt(self.arch.head_dim))
        groups = self.arch.num_attention_heads // self.arch.num_key_value_heads
        self.kv_head_ids = np.repeat(np.arange(self.arch.num_key_value_heads), groups)
        self.positions = np.arange(self.arch.num_acoustic_codebooks + 1)
        dims = np.arange(0, self.arch.head_dim, 2, dtype=np.float32)
        frequencies = np.float32(self.arch.rope_theta)**(-dims / self.arch.head_dim)
        angles = self.positions.astype(np.float32)[:, None] * frequencies[None, :]
        self.cos = np.cos(angles)[None, :, :]
        self.sin = np.sin(angles)[None, :, :]

    def _layer(self, layer, values, start, keys, history):
        arch = self.arch
        prefix = f'code_pred.blk.{layer}.'

        def weight(name):
            return self.tensors[prefix + name + '.weight']

        tokens = len(values)
        end = start + tokens
        norm = _rms(values, weight('attn_norm'), self.eps)
        q = (norm @ weight('attn_q').T).reshape(tokens, arch.num_attention_heads, arch.head_dim)
        k = (norm @ weight('attn_k').T).reshape(tokens, arch.num_key_value_heads, arch.head_dim)
        v = (norm @ weight('attn_v').T).reshape(tokens, arch.num_key_value_heads, arch.head_dim)
        cos, sin = self.cos[:, start:end], self.sin[:, start:end]
        q = _rope_neox(_rms(q, weight('attn_q_norm'), self.eps).transpose(1, 0, 2), cos, sin)
        k = _rope_neox(_rms(k, weight('attn_k_norm'), self.eps).transpose(1, 0, 2), cos, sin)
        keys[:, start:end] = k
        history[:, start:end] = v.transpose(1, 0, 2)
        logits = (q @ keys[self.kv_head_ids].transpose(0, 2, 1)) * self.scale
        causal = self.positions[None, :] <= self.positions[start:end, None]
        logits = np.where(causal, logits, np.float32(-np.inf))
        attended = _softmax(logits) @ history[self.kv_head_ids]
        attended = attended.transpose(1, 0, 2).reshape(tokens, -1)
        values = values + attended @ weight('attn_output').T

        norm = _rms(values, weight('ffn_norm'), self.eps)
        gate = norm @ weight('ffn_gate').T
        up = norm @ weight('ffn_up').T
        silu = gate / (np.float32(1) + np.exp(-np.clip(gate, -80, 80)))
        return values + (silu * up) @ weight('ffn_down').T

    def predict(self, hidden, c0, temperature, uniforms, top_k=50, forced_codes=None):
        """Return model decisions and logits, optionally consuming held reference IDs."""
        arch = self.arch
        steps = arch.num_acoustic_codebooks
        hidden = np.asarray(hidden, dtype=np.float32)
        uniforms = np.asarray(uniforms, dtype=np.float32)
        if hidden.shape != (arch.talker_hidden_size,) or not np.isfinite(hidden).all():
            raise ValueError('Invalid Talker hidden state')
        if (uniforms.shape != (steps,) or not np.isfinite(uniforms).all()
                or np.any((uniforms < 0) | (uniforms >= 1))):
            raise ValueError('Invalid acoustic sampler state')
        if not isinstance(c0, (int, np.integer)) or not 0 <= c0 < arch.talker_vocab_size:
            raise ValueError('Invalid semantic code')
        if forced_codes is not None:
            forced_codes = np.asarray(forced_codes)
            if (forced_codes.shape != (steps,) or forced_codes.dtype.kind not in 'iu'
                    or np.any((forced_codes < 0) | (forced_codes >= arch.vocab_size))):
                raise ValueError('Invalid teacher-forced acoustic codes')

        shape = (arch.num_hidden_layers, arch.num_key_value_heads, steps + 1, arch.head_dim)
        keys = np.zeros(shape, dtype=np.float32)
        history = np.zeros_like(keys)
        codes = np.empty(steps + 1, dtype=np.int32)
        logits = np.empty((steps, arch.vocab_size), dtype=np.float32)
        codes[0] = c0
        embed = self.tensors['talker.codec_embd.weight'][c0]
        values = np.stack((hidden, embed))
        for step in range(steps):
            start = 0 if step == 0 else step + 1
            for layer in range(arch.num_hidden_layers):
                values = self._layer(layer, values, start, keys[layer], history[layer])
            out = _rms(values[-1], self.tensors['code_pred.output_norm.weight'], self.eps)
            logits[step] = self.tensors[f'code_pred.lm_head.{step}.weight'] @ out
            code = sample_code(logits[step], temperature, uniforms[step], top_k)
            codes[step + 1] = code
            if step + 1 < steps:
                code = code if forced_codes is None else forced_codes[step]
                values = self.tensors[f'code_pred.codec_embd.{step}.weight'][code][None, :]
        return FrameResult(codes, logits)
