"""Explicit GPU-capable context and learned proposal graphs; no eager imports.

SGLang3c560089e1818a5217a73f2168273485a5350341, Apache-2.0; see
../dflash2_reference/sources/SGLANG_LICENSE. Synthetic CPU source parity is
separate from actual GPU numerics/performance, native readiness and ownership.
"""
from dataclasses import dataclass
from .graph import QueryBackbone, PrivateContext, _check_cpu_weights, _explicit_device, _metadata, _norm, _rotary

SELECTOR_KEYS = (
    'candidate_selector.hidden_projection.weight',
    'candidate_selector.predecessor_codebook',
    'candidate_selector.successor_codebook',
)
CONTEXT_EXTRA_SHAPES = {'fc.weight': (2560, 12800), 'hidden_norm.weight': (2560,)}


class ContextGraph:
    """Own FC/norm; share the body's already-owned K/V/norm rows persistently."""
    @classmethod
    def from_owned_body(cls, body, context_weights_cpu):
        if type(body) is not QueryBackbone:
            raise TypeError('Already-owned QueryBackbone required')
        t = body._t
        dtype = _check_cpu_weights(context_weights_cpu, CONTEXT_EXTRA_SHAPES, t)
        if dtype != body.dtype:
            raise ValueError('Context partition dtype differs from query body')
        obj = cls()
        obj._body, obj._t, obj.dtype, obj.device = body, t, dtype, body.device
        with t.inference_mode():
            obj._fc = context_weights_cpu['fc.weight'].to(device=body.device, copy=True)
            obj._norm = context_weights_cpu['hidden_norm.weight'].to(device=body.device, copy=True)
        return obj

    def prepare(self, features, *, start_position):
        """Private KV for actual target INPUT feature rows, never bonus guesses.

        Metadata checks use Python integers/shapes. Input feature integrity and
        completion belong to Root's owner boundary; no device scalar is read.
        """
        t = self._t
        if not isinstance(features, t.Tensor) or features.ndim != 2 or not 1 <= features.shape[0] <= 2048:
            raise ValueError('Features[1..2048,12800] required')
        rows = features.shape[0]
        _metadata(features, (rows, 12800), self.dtype, self.device, t, 'target HC means')
        if type(start_position) is not int or not 0 <= start_position <= 262144 - rows:
            raise ValueError('Contiguous absolute target-input positions required')
        with t.inference_mode():
            hidden, _ = _norm(t.nn.functional.linear(features, self._fc), self._norm, None, t)
            positions = t.arange(start_position, start_position + rows, device=self.device, dtype=t.int64)
            angles = t.einsum('i,j -> ij', positions.float(), self._body._layers[0]._frequency)
            cos = angles.cos().to(self.dtype)[:, None, :]
            sin = angles.sin().to(self.dtype)[:, None, :]
            keys, values = [], []
            for layer in self._body._layers:
                weights = layer._weights
                kv = t.nn.functional.linear(hidden, weights['qkv'][4096:]).view(rows, 2, 8, 128)
                key, _ = _norm(kv[:, 0], weights['self_attn.k_norm.weight'], None, t)
                keys.append(_rotary(key, cos, sin, t))
                values.append(kv[:, 1])
            return PrivateContext(t.stack(keys, dim=0), t.stack(values, dim=0), start_position)


@dataclass(frozen=True)
class PrivateProposal:
    tokens: object
    candidate_ids: object
    unary_logits: object
    edge_scores: object
    q_rows: object
    path_indices: object


class ProposalGraph:
    """Persistent dense head/top16 and trained rank256 selector, greedy only."""
    @classmethod
    def from_cpu(cls, weights, target_head_cpu, *, device, org_vocab_size):
        import torch
        if not isinstance(target_head_cpu, torch.Tensor) or target_head_cpu.device.type != 'cpu' or target_head_cpu.ndim != 2:
            raise TypeError('Explicit caller-owned dense CPU target head required')
        vocab = target_head_cpu.shape[0]
        if type(org_vocab_size) is not int or not 16 <= org_vocab_size <= vocab <= 248320:
            raise ValueError('Explicit original vocabulary prefix16..248320 required')
        shapes = dict(zip(SELECTOR_KEYS, ((256, 2560), (vocab, 256), (vocab, 256))))
        dtype = _check_cpu_weights(weights, shapes, torch)
        _check_cpu_weights({'head': target_head_cpu}, {'head': (vocab, 2560)}, torch)
        chosen = _explicit_device(device, torch)
        obj = cls()
        obj._t, obj.dtype, obj.device, obj.org_vocab_size = torch, dtype, chosen, org_vocab_size
        with torch.inference_mode():
            obj._head = target_head_cpu.to(device=chosen, copy=True)
            obj._projection, obj._predecessors, obj._successors = tuple(weights[key].to(device=chosen, copy=True) for key in SELECTOR_KEYS)
        return obj

    def propose(self, hidden, anchor_token_ids):
        t = self._t
        if not isinstance(hidden, t.Tensor) or hidden.ndim != 2 or hidden.shape[0] not in (4, 8):
            raise ValueError('Whole hidden block4/8 required')
        block = hidden.shape[0]
        _metadata(hidden, (block, 2560), self.dtype, self.device, t, 'query hidden')
        _metadata(anchor_token_ids, (1,), t.int64, self.device, t, 'actual anchor')
        # Defined-token and authoritative anchor checks remain at publication.
        # No .all/.item/CPU copy is inserted into this private tensor graph.
        with t.inference_mode():
            predicted = hidden.view(1, block, 2560)[:, 1:]
            flat = predicted.reshape(-1, 2560)
            logits = t.matmul(flat.to(self._head.dtype), self._head[:self.org_vocab_size].T)
            unary, ids = t.topk(logits, 16, dim=-1)
            ids = ids.long().view(1, block - 1, 16)
            unary = unary.float().view(1, block - 1, 16)
            projected = t.nn.functional.linear(predicted, self._projection)
            predecessors = t.cat((anchor_token_ids[:, None, None].expand(-1, 1, 16), ids[:, :-1]), dim=1)
            scores = unary[:, :, None] + t.einsum(
                'blpr,blcr->blpc', self._predecessors[predecessors] * projected[:, :, None], self._successors[ids])
            index = scores[:, 0, 0].argmax(-1)
            maps = scores[:, 1:].argmax(-1)
            path = [index]
            for edge in range(block - 2):
                index = maps[:, edge].gather(-1, index[:, None])[:, 0]
                path.append(index)
            path = t.stack(path, dim=1)
            tokens = ids.gather(-1, path.unsqueeze(-1))[:, :, 0]
            return PrivateProposal(tokens, ids, unary, scores, t.nn.functional.one_hot(path, 16).float(), path)
