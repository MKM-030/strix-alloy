"""Offline CPU K3 drafter. Importing this module does not import PyTorch.

The caller supplies the immutable target bindings and authoritative target rows.
No target verification, acceptance prediction, device selection, or serving hook
is implemented here.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from types import MappingProxyType

from contract import (HEAD_DIM, HIDDEN, K, KV_HEADS, LAYERS, MASK_ID,
                      Q_HEADS, RMS_EPS, ROPE_THETA, TAP_IDS, TOKENIZER_SHA256,
                      VOCAB, Frontier, valid_output_id, validate_config)
from offline_loader import cpu_torch, load_drafter


@dataclass(frozen=True)
class TargetIdentity:
    target_model_id: str
    target_revision: str
    tokenizer_sha256: str
    head_receipt: str
    embedding_receipt: str
    feature_provenance: str
    target_layer_ids: tuple[int, ...] = TAP_IDS

    def __post_init__(self):
        if not all(isinstance(x, str) and x for x in
                   (self.target_model_id, self.target_revision, self.head_receipt,
                    self.embedding_receipt, self.feature_provenance)):
            raise ValueError("Exact target and input provenance must be recorded")
        if self.tokenizer_sha256 != TOKENIZER_SHA256:
            raise ValueError("Target tokenizer is not the pinned tokenizer")
        if self.target_layer_ids != TAP_IDS:
            raise ValueError("HCconcat must use exactly target layers3,15,23,35,43")


@dataclass(frozen=True)
class TargetEmbedding:
    token_id: int
    values: object
    identity: TargetIdentity


@dataclass(frozen=True)
class TargetRows:
    # Each row is the five target tap outputs concatenated in TAP_IDS order.
    features: object
    input_ids: tuple[int, ...]
    positions: tuple[int, ...]
    identity: TargetIdentity


def _cpu_tensor(value, shape, torch):
    if not isinstance(value, torch.Tensor) or value.device.type != "cpu":
        raise ValueError("Only already-resident CPU tensors are accepted")
    if tuple(value.shape) != tuple(shape) or value.dtype not in (torch.bfloat16, torch.float32):
        raise ValueError(f"Expected BF16/F32 CPU tensor shaped {tuple(shape)}")
    return value


class NonFiniteTensorError(ValueError):
    def __init__(self, tensor_role):
        self.tensor_role = tensor_role
        super().__init__(f"Non-finite values in {tensor_role}")


def _require_finite(value, torch, tensor_role):
    if not bool(torch.isfinite(value).all().item()):
        raise NonFiniteTensorError(tensor_role)


class TargetBinding:
    """Private target snapshots: mutation of caller tensors cannot alter them.

    PyTorch has no read-only tensor flag; these snapshots are kept private and
    neither provider nor oracle writes them. A caller must supply the full head,
    including all248320 rows; masking/slicing the output vocabulary is forbidden.
    """
    def __init__(self, *, full_head, mask_embedding, identity: TargetIdentity):
        if not isinstance(identity, TargetIdentity):
            raise ValueError("A frozen target identity is required")
        torch = cpu_torch()
        head = _cpu_tensor(full_head, (VOCAB, HIDDEN), torch)
        mask = _cpu_tensor(mask_embedding, (HIDDEN,), torch)
        with torch.inference_mode():
            self._head = head.detach().clone().contiguous()
            self._mask = mask.detach().clone().contiguous()
            # Check immutable snapshots once. Chunk the large full head so the
            # finite-value scan also has bounded temporary memory.
            for start in range(0, VOCAB, 8192):
                _require_finite(self._head[start:start + 8192], torch, "target full vocabulary head")
            _require_finite(self._mask, torch, "target mask embedding")
        self._identity = identity

    @property
    def identity(self):
        return self._identity


@dataclass(frozen=True)
class Proposal:
    query: object
    raw_ids: tuple[int, int, int]
    offerable: bool
    hidden_states: object
    logits: object


class K3Reference:
    def __init__(self, *, checkpoint_path, config, binding: TargetBinding,
                 compute_dtype="bf16", request_nonce, epoch):
        validate_config(config)
        if not isinstance(binding, TargetBinding):
            raise ValueError("An immutable target binding is required")
        if compute_dtype not in {"bf16", "float32"}:
            raise ValueError("Choose explicit CPU BF16 or FP32 arithmetic")
        self.torch = torch = cpu_torch()
        self.dtype = {"bf16": torch.bfloat16, "float32": torch.float32}[compute_dtype]
        self.compute_dtype = compute_dtype
        self.identity = binding.identity
        self.config = MappingProxyType(copy.deepcopy(dict(config)))
        self._owner = load_drafter(checkpoint_path)
        # BF16 weights retain the private mapped storage; FP32 is an explicit
        # arithmetic reference conversion of the exact supplied BF16 tensors.
        with torch.inference_mode():
            self._weights = {n: t.detach().to(dtype=self.dtype) for n, t in self._owner.tensors.items()}
            self._head = binding._head
            self._mask = binding._mask.to(dtype=self.dtype)
            self._inv_freq = 1.0 / (ROPE_THETA **
                (torch.arange(0, HEAD_DIM, 2, dtype=torch.float32, device="cpu") / HEAD_DIM))
        self.frontier = Frontier(request_nonce, epoch)
        self._context_kv = None
        self._accepted_ids = ()
        self._accepted_positions = ()

    @property
    def accepted_ids(self):
        return self._accepted_ids

    @property
    def accepted_positions(self):
        return self._accepted_positions

    @property
    def context_length(self):
        return len(self._accepted_ids)

    def _rows_metadata(self, rows):
        if not isinstance(rows, TargetRows) or rows.identity != self.identity:
            raise ValueError("Features belong to a different target binding")
        ids, positions = tuple(rows.input_ids), tuple(rows.positions)
        if len(ids) != len(positions) or not ids or any(not valid_output_id(x) for x in ids):
            raise ValueError("Every target feature row needs an actual defined input ID/position")
        if any(type(p) is not int for p in positions):
            raise ValueError("Positions must be exact target integers")
        _cpu_tensor(rows.features, (len(ids), 5 * HIDDEN), self.torch)
        return ids, positions

    def _rms(self, x, name):
        torch = self.torch
        value = x.float()
        value = value * torch.rsqrt(value.pow(2).mean(-1, keepdim=True) + RMS_EPS)
        return self._weights[name] * value.to(dtype=x.dtype)

    def _linear(self, x, name):
        return self.torch.nn.functional.linear(x, self._weights[name])

    def _cos_sin(self, positions, dtype):
        torch = self.torch
        ids = torch.tensor([tuple(positions)], dtype=torch.long, device="cpu")
        inv = self._inv_freq[None, :, None].float().expand(1, -1, 1)
        freqs = (inv @ ids[:, None, :].float()).transpose(1, 2)
        emb = torch.cat((freqs, freqs), dim=-1)
        return emb.cos().to(dtype), emb.sin().to(dtype)

    def _rope(self, value, cos, sin):
        torch = self.torch
        half = value.shape[-1] // 2
        rotated = torch.cat((-value[..., half:], value[..., :half]), dim=-1)
        return value * cos.unsqueeze(1) + rotated * sin.unsqueeze(1)

    def _project_context(self, selected_features, positions):
        # The only path that constructs persistent KV. selected_features has
        # already been reduced to accepted processed TARGET input rows.
        _require_finite(selected_features, self.torch, "selected target features")
        fused = self._rms(self._linear(selected_features.unsqueeze(0), "fc.weight"),
                          "hidden_norm.weight")
        _require_finite(fused, self.torch, "fused target context")
        cos, sin = self._cos_sin(positions, fused.dtype)
        result = []
        n = len(positions)
        for layer in range(LAYERS):
            prefix = f"layers.{layer}.self_attn."
            key = self._linear(fused, prefix + "k_proj.weight").view(1, n, KV_HEADS, HEAD_DIM)
            key = self._rms(key, prefix + "k_norm.weight").transpose(1, 2)
            value = self._linear(fused, prefix + "v_proj.weight").view(1, n, KV_HEADS, HEAD_DIM).transpose(1, 2)
            key = self._rope(key, cos, sin)
            _require_finite(key, self.torch, f"layer {layer} target context key")
            _require_finite(value, self.torch, f"layer {layer} target context value")
            result.append((key, value))
        return tuple(result)

    def initialize(self, rows: TargetRows):
        ids, positions = self._rows_metadata(rows)
        if self._context_kv is not None or positions != tuple(range(len(ids))):
            raise ValueError("Initialize once using the complete contiguous target prefix")
        # Metadata validation precedes computation; frontier initialization is
        # committed only after every layer's target-context projection succeeds.
        if len(ids) >= 262144:
            raise ValueError("Initial context exceeds the pinned position range")
        try:
            with self.torch.inference_mode():
                owned = rows.features.detach().to(self.dtype).clone().contiguous()
                context = self._project_context(owned, positions)
            self.frontier.initialize(positions)
            self._context_kv = context
            self._accepted_ids, self._accepted_positions = ids, positions
        except Exception:
            self.retire()
            raise

    def _query_embeddings(self, anchor: TargetEmbedding):
        if not isinstance(anchor, TargetEmbedding) or anchor.identity != self.identity:
            raise ValueError("Anchor embedding belongs to another target")
        if not valid_output_id(anchor.token_id):
            raise ValueError("Anchor must be a defined target token")
        value = _cpu_tensor(anchor.values, (HIDDEN,), self.torch)
        owned = value.detach().to(dtype=self.dtype).clone().contiguous()
        _require_finite(owned, self.torch, "anchor embedding")
        query = self.torch.stack((owned, self._mask, self._mask), dim=0).unsqueeze(0)
        _require_finite(query, self.torch, "query embeddings")
        return query

    def _forward_query(self, hidden, query_positions):
        torch = self.torch
        cos, sin = self._cos_sin(query_positions, hidden.dtype)
        for layer in range(LAYERS):
            prefix = f"layers.{layer}."
            residual = hidden
            normalized = self._rms(hidden, prefix + "input_layernorm.weight")
            attn = prefix + "self_attn."
            q = self._linear(normalized, attn + "q_proj.weight").view(1, K, Q_HEADS, HEAD_DIM)
            q = self._rms(q, attn + "q_norm.weight").transpose(1, 2)
            key = self._linear(normalized, attn + "k_proj.weight").view(1, K, KV_HEADS, HEAD_DIM)
            key = self._rms(key, attn + "k_norm.weight").transpose(1, 2)
            value = self._linear(normalized, attn + "v_proj.weight").view(1, K, KV_HEADS, HEAD_DIM).transpose(1, 2)
            q, key = self._rope(q, cos, sin), self._rope(key, cos, sin)
            _require_finite(q, torch, f"layer {layer} query Q")
            _require_finite(key, torch, f"layer {layer} query K")
            _require_finite(value, torch, f"layer {layer} query V")
            # Temporary query KV is never stored in _context_kv, including after
            # acceptance. Only subsequent authoritative target rows persist.
            ctx_key, ctx_value = self._context_kv[layer]
            key = torch.cat((ctx_key, key), dim=2)
            value = torch.cat((ctx_value, value), dim=2)
            groups = Q_HEADS // KV_HEADS
            length = key.shape[2]
            key = key[:, :, None, :, :].expand(1, KV_HEADS, groups, length, HEAD_DIM).reshape(1, Q_HEADS, length, HEAD_DIM)
            value = value[:, :, None, :, :].expand(1, KV_HEADS, groups, length, HEAD_DIM).reshape(1, Q_HEADS, length, HEAD_DIM)
            score = torch.matmul(q, key.transpose(2, 3)) * (HEAD_DIM ** -0.5)
            probability = torch.nn.functional.softmax(score, dim=-1, dtype=torch.float32).to(q.dtype)
            output = torch.matmul(probability, value).transpose(1, 2).contiguous().reshape(1, K, Q_HEADS * HEAD_DIM)
            hidden = residual + self._linear(output, attn + "o_proj.weight")
            residual = hidden
            normalized = self._rms(hidden, prefix + "post_attention_layernorm.weight")
            gate = torch.nn.functional.silu(self._linear(normalized, prefix + "mlp.gate_proj.weight"))
            up = self._linear(normalized, prefix + "mlp.up_proj.weight")
            hidden = residual + self._linear(gate * up, prefix + "mlp.down_proj.weight")
            _require_finite(hidden, torch, f"layer {layer} query hidden states")
        hidden = self._rms(hidden, "norm.weight")
        _require_finite(hidden, torch, "final query hidden states")
        # Visit EVERY vocabulary row. Chunking bounds conversion workspace; it
        # neither ranks a shortlist nor changes the defined output domain.
        pieces = []
        for start in range(0, VOCAB, 8192):
            head = self._head[start:start + 8192].to(dtype=hidden.dtype)
            pieces.append(torch.nn.functional.linear(hidden, head))
        logits = torch.cat(pieces, dim=-1)
        return hidden, logits

    def propose(self, *, anchor: TargetEmbedding, round_index):
        if self._context_kv is None:
            raise ValueError("Initialize target context before proposing")
        with self.torch.inference_mode():
            try:
                hidden = self._query_embeddings(anchor)
                query = self.frontier.begin(round_index, anchor.token_id, self.context_length)
                hidden, logits = self._forward_query(hidden, query.query_positions)
                _require_finite(hidden, self.torch, "proposal hidden states")
                _require_finite(logits, self.torch, "full vocabulary logits")
                raw_ids = tuple(int(x) for x in logits[0].argmax(dim=-1).tolist())
                self.frontier.record_proposal(query, raw_ids)
            except Exception:
                self.retire()
                raise
        return Proposal(query, raw_ids, all(valid_output_id(x) for x in raw_ids), hidden, logits)

    def apply_verification(self, *, rows: TargetRows, round_index,
                           accepted_prefix, authoritative_bonus_id):
        ids, positions = self._rows_metadata(rows)
        plan = self.frontier.plan_commit(round_index, ids, positions,
                                         accepted_prefix, authoritative_bonus_id)
        try:
            with self.torch.inference_mode():
                # Slice FIRST. Rejected verifier rows are never fused/projected
                # and provisional query KV is never reused as target context.
                selected = rows.features[:len(plan.retained_indices)].detach().to(self.dtype).clone().contiguous()
                append = self._project_context(selected, plan.retained_positions)
                next_kv = tuple((self.torch.cat((old[0], new[0]), dim=2),
                                 self.torch.cat((old[1], new[1]), dim=2))
                                for old, new in zip(self._context_kv, append))
            self.frontier.finish_commit(plan)
            self._context_kv = next_kv
            self._accepted_ids += plan.retained_ids
            self._accepted_positions += plan.retained_positions
        except Exception:
            self.retire()
            raise
        return plan

    def retire(self):
        self.frontier.retire()
        self._context_kv = None
        self._accepted_ids = self._accepted_positions = ()
