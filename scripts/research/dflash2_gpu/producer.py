"""Explicit full81-tensor + external dense-head composition; import is passive."""
from .graph import QueryBackbone, LAYER_SHAPES
from .partitions import ContextGraph, ProposalGraph, CONTEXT_EXTRA_SHAPES, SELECTOR_KEYS


class DFlashGraph:
    """Private proposer; no model file loader, stream/fence or native ownership."""
    @classmethod
    def from_cpu(cls, model_weights, target_head_cpu, *, device, org_vocab_size, batched_attention=False):
        body_names = {f'layers.{i}.{name}' for i in range(5) for name in LAYER_SHAPES} | {'norm.weight'}
        expected = body_names | set(CONTEXT_EXTRA_SHAPES) | set(SELECTOR_KEYS)
        if type(model_weights) is not dict or set(model_weights) != expected or len(expected) != 81:
            raise ValueError('Exactly the81 trained DFlash2 tensors required')
        # Each partition performs its CPU finite/shape scan once at startup.
        # Context reuses already transferred body K/V and k_norm weights.
        body = QueryBackbone.from_cpu({name: model_weights[name] for name in body_names}, device=device, batched_attention=batched_attention)
        context = ContextGraph.from_owned_body(body, {name: model_weights[name] for name in CONTEXT_EXTRA_SHAPES})
        selector = ProposalGraph.from_cpu({name: model_weights[name] for name in SELECTOR_KEYS}, target_head_cpu,
                                         device=device, org_vocab_size=org_vocab_size)
        return cls.from_owned_parts(body, context, selector)

    @classmethod
    def from_owned_parts(cls, body, context, selector):
        """Compose already-owned staged parts without copying or transferring.

        Root can release CPU body tensors before acquiring the separate target
        head. This changes startup retention only, never arithmetic/precision.
        """
        if type(body) is not QueryBackbone or type(context) is not ContextGraph or type(selector) is not ProposalGraph:
            raise TypeError('Owned QueryBackbone, ContextGraph and ProposalGraph required')
        if context._body is not body:
            raise ValueError('Context must share this exact owned query body')
        if context.dtype != body.dtype or selector.dtype != body.dtype or context.device != body.device or selector.device != body.device:
            raise ValueError('Owned component dtype/device differs')
        obj = cls()
        obj.body, obj.context, obj.selector = body, context, selector
        return obj

    def propose(self, input_embeds, context, anchor_token_ids, *, prefix_tokens):
        hidden = self.body.forward(input_embeds, context, prefix_tokens=prefix_tokens)
        return self.selector.propose(hidden, anchor_token_ids)
