"""Pinned-source TP1 dense full-head/top16 learned-selector CPU reference.

Adapted from SGLang@3c560089e1818a5217a73f2168273485a5350341,
Apache-2.0 (sources/SGLANG_LICENSE). Caller owns all tensors. Import is passive.
Only greedy whole query blocks4/8 are supported. The worker's anchor hidden row
is discarded. Numerical scope is the source CPU topk fallback and sequential
selector, not FlashInfer tie behavior, GPU/NPU equivalence, speed or quality.
The explicit org-vocab prefix does not establish the defined-token domain or
native publication readiness. No loader, native allocation or attachment exists.
"""
from dataclasses import dataclass
import hashlib
from pathlib import Path

SOURCE = Path(__file__).with_name('sources') / 'sglang_dflash.py'
SOURCE_SHA256 = 'b7b541368cbbb072a679d08ba5bf0f952f4a43f02b6c078562b2ea7a9ddfd01b'
WORKER_SOURCE = SOURCE.with_name('sglang_dflash_worker_v2.py')
WORKER_SHA256 = '8f82de8d666f81f3c1aa43dc651006f4182ff58593fdfe4eea28c5ee2a14bfc0'
SELECTOR_KEYS = (
    'candidate_selector.hidden_projection.weight',
    'candidate_selector.predecessor_codebook',
    'candidate_selector.successor_codebook',
)


def verify_sources():
    """Explicit saved-source hashing, with no tensor payload access."""
    for path, expected in ((SOURCE, SOURCE_SHA256), (WORKER_SOURCE, WORKER_SHA256)):
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError('Pinned proposal source differs: ' + path.name)
    return dict(width=2560, rank=256, top_k=16, model_payload_opened=False,
                revision='3c560089e1818a5217a73f2168273485a5350341')


@dataclass(frozen=True)
class Proposal:
    tokens: object
    candidate_ids: object
    unary_logits: object
    edge_scores: object
    q_rows: object
    path_indices: object


def _finite(value, torch):
    # Bounded validation temporary even for the full caller-owned dense head.
    return all(bool(torch.isfinite(value[start:start + 64]).all())
               for start in range(0, value.shape[0], 64))


def propose_greedy(hidden_states, anchor_token_ids, head_weight, selector_weights,
                   *, block_size, org_vocab_size):
    """Return owned top16 lattice and greedy predecessor-dependent path.

    hidden:[B*block,2560], anchors:[B], head:[vocab,2560]; learned weights
    are projection[256,2560] and two codebooks[vocab,256]. Synthetic vocab is
    allowed for explicit CPU tests; checkpoint vocab ceiling is248320. B<=8.
    Source head matmul casts hidden to head dtype before topk; projection uses
    hidden dtype. Unary values are transformed to FP32 after topk, as upstream.
    Caller explicitly configures intra/inter-op CPU threads to one.
    """
    import torch
    if __package__:
        from . import math_ops
    else:
        import math_ops
    if torch.get_num_threads() != 1 or torch.get_num_interop_threads() != 1:
        raise ValueError('Explicit one-thread CPU execution required')
    if type(block_size) is not int or block_size not in (4, 8):
        raise ValueError('Only whole query blocks4/8 supported')
    if type(org_vocab_size) is not int or not 16 <= org_vocab_size <= 248320:
        raise ValueError('Explicit original vocabulary prefix16..248320 required')
    for name, value in (('hidden', hidden_states), ('head', head_weight)):
        if not isinstance(value, torch.Tensor) or value.device.type != 'cpu' or value.dtype not in (torch.float32, torch.bfloat16):
            raise TypeError('CPU FP32/BF16 ' + name + ' required')
    if hidden_states.ndim != 2 or hidden_states.shape[1] != 2560 or hidden_states.shape[0] % block_size:
        raise ValueError('hidden must contain whole flat query blocks of width2560')
    batch = hidden_states.shape[0] // block_size
    if not 1 <= batch <= 8:
        raise ValueError('CPU reference requires batch1..8')
    if head_weight.ndim != 2 or head_weight.shape[1] != 2560 or not org_vocab_size <= head_weight.shape[0] <= 248320:
        raise ValueError('Dense head shape/domain differs')
    if not isinstance(anchor_token_ids, torch.Tensor) or anchor_token_ids.dtype != torch.int64 or anchor_token_ids.device.type != 'cpu':
        raise TypeError('CPU int64 anchors required')
    if anchor_token_ids.shape != (batch,) or bool((anchor_token_ids < 0).any()) or bool((anchor_token_ids >= org_vocab_size).any()):
        raise ValueError('One in-prefix anchor per query block required')
    if type(selector_weights) is not dict or set(selector_weights) != set(SELECTOR_KEYS):
        raise ValueError('Exactly the three learned selector tensors required')
    shapes = ((256, 2560), (head_weight.shape[0], 256), (head_weight.shape[0], 256))
    for key, shape in zip(SELECTOR_KEYS, shapes):
        value = selector_weights[key]
        if not isinstance(value, torch.Tensor) or value.device.type != 'cpu' or value.dtype != hidden_states.dtype or tuple(value.shape) != shape:
            raise ValueError('Learned selector CPU tensor shape/dtype differs: ' + key)
        if not _finite(value, torch):
            raise ValueError('Nonfinite learned selector weight')
    if not _finite(hidden_states, torch) or not _finite(head_weight, torch):
        raise ValueError('Nonfinite hidden/head')
    with torch.inference_mode():
        predicted = hidden_states.view(batch, block_size, 2560)[:, 1:]
        # Actual worker flattens all predicted positions before compute_candidates.
        flat = predicted.reshape(-1, 2560)
        logits = torch.matmul(flat.to(head_weight.dtype), head_weight[:org_vocab_size].T)
        values, ids = torch.topk(logits, 16, dim=-1)
        ids = ids.long().view(batch, block_size - 1, 16)
        unary = values.float().view(batch, block_size - 1, 16)
        projected = torch.nn.functional.linear(predicted, selector_weights[SELECTOR_KEYS[0]])
        scores = math_ops.score_edges(
            predecessor_table=selector_weights[SELECTOR_KEYS[1]],
            successor_table=selector_weights[SELECTOR_KEYS[2]], candidate_ids=ids,
            unary_logits=unary, hidden=projected, anchor_token_ids=anchor_token_ids, top_k=16)
        if not _finite(scores, torch):
            raise ValueError('Nonfinite proposal lattice')
        initial = scores[:, 0, 0].argmax(-1)
        maps = scores[:, 1:].argmax(-1)
        path = math_ops.follow_maps(maps, initial, block_size - 2)
        tokens = ids.gather(-1, path.unsqueeze(-1))[:, :, 0]
        q = torch.nn.functional.one_hot(path, 16).float()
        return Proposal(tokens, ids, unary, scores, q, path)
