"""Independent numerical oracle from unedited pinned owner/HF definitions.

Only selected definitions are compiled. Third-party package imports, hub/kernel
decorators, and dynamic-RoPE decorators are excluded. Default RoPE, RMSNorm,
MLP, attention and the owner's complete backbone body remain exact source AST.
This module imports no tensor runtime until PinnedOwnerOracle is constructed.
"""
from __future__ import annotations

import ast
import copy
import hashlib
from pathlib import Path
from types import SimpleNamespace

from contract import HEAD_DIM, HIDDEN, K, LAYERS, VOCAB

SOURCE_HASHES = {
    "pixel_modeling.py": "9ad90bcb926b32b5144e8a27816ef18b51e9e5ee083108c5fbd8f63bc92b3953",
    "hf_modeling_qwen3.py": "cbb7f2dc274c2f5592746c0dc6985ca50353efa07376f92cc922b77680a74f69",
}


class _LocalDecorators(ast.NodeTransformer):
    def _strip(self, node):
        # Preserve staticmethod; every discarded decorator is package/hub/
        # no-grad dispatch metadata. Outer inference_mode supplies no-grad.
        node.decorator_list = [d for d in node.decorator_list
                               if isinstance(d, ast.Name) and d.id == "staticmethod"]
        return self.generic_visit(node)

    visit_ClassDef = _strip
    visit_FunctionDef = _strip


def extracted_owner_ast():
    sources = Path(__file__).resolve().parent / "sources"
    trees = {}
    for name, expected in SOURCE_HASHES.items():
        data = (sources / name).read_bytes()
        if hashlib.sha256(data).hexdigest() != expected:
            raise ValueError(f"Pinned source receipt differs: {name}")
        trees[name] = ast.parse(data.decode("utf-8"), filename=name)

    def definitions(filename, names):
        nodes = {node.name: node for node in trees[filename].body
                 if isinstance(node, (ast.ClassDef, ast.FunctionDef))}
        return [copy.deepcopy(nodes[name]) for name in names]

    hf = definitions("hf_modeling_qwen3.py", ["Qwen3RMSNorm", "Qwen3MLP",
        "Qwen3RotaryEmbedding", "rotate_half", "repeat_kv", "eager_attention_forward"])
    pixel = definitions("pixel_modeling.py", ["apply_rotary_pos_emb",
        "Qwen3DSparkAttention", "Qwen3DSparkDecoderLayer"])
    model = next(n for n in trees["pixel_modeling.py"].body
                 if isinstance(n, ast.ClassDef) and n.name == "Qwen3DSparkModel")
    backbone = copy.deepcopy(next(n for n in model.body
                                 if isinstance(n, ast.FunctionDef) and n.name == "_forward_backbone"))
    skeleton = ast.ClassDef(name="_PinnedOwnerBackbone",
        bases=[ast.Attribute(value=ast.Name(id="nn", ctx=ast.Load()), attr="Module", ctx=ast.Load())],
        keywords=[], body=[backbone], decorator_list=[])
    tree = ast.Module(body=[ast.ImportFrom(module="__future__",
        names=[ast.alias(name="annotations")], level=0)] + hf + pixel + [skeleton], type_ignores=[])
    tree = _LocalDecorators().visit(tree)
    return ast.fix_missing_locations(tree)


class PinnedOwnerOracle:
    def __init__(self, provider):
        self.torch = torch = provider.torch
        namespace = {"torch": torch, "nn": torch.nn,
            "ACT2FN": {"silu": torch.nn.functional.silu},
            "GradientCheckpointingLayer": torch.nn.Module,
            "ALL_ATTENTION_FUNCTIONS": {}, "maybe_autocast": torch.autocast}
        exec(compile(extracted_owner_ast(), "<pinned-owner-extracted>", "exec"), namespace)
        config = SimpleNamespace(**dict(provider.config))
        config._attn_implementation = "eager"
        config.attention_dropout = 0.0
        config.sliding_window = None
        # Constructors execute ONLY on meta. Every registered parameter is
        # replaced with the real supplied tensor before any CPU forward call.
        with torch.device("meta"):
            model = namespace["_PinnedOwnerBackbone"]()
            model.fc = torch.nn.Linear(5 * HIDDEN, HIDDEN, bias=False)
            model.hidden_norm = namespace["Qwen3RMSNorm"](HIDDEN, eps=config.rms_norm_eps)
            model.norm = namespace["Qwen3RMSNorm"](HIDDEN, eps=config.rms_norm_eps)
            model.layers = torch.nn.ModuleList(namespace["Qwen3DSparkDecoderLayer"](config, i)
                                               for i in range(LAYERS))
        expected = set(provider._weights)
        if set(dict(model.named_parameters())) != expected:
            raise ValueError("Owner oracle parameter inventory is not exactly the supplied58")
        for name, tensor in provider._weights.items():
            parent, leaf = name.rsplit(".", 1)
            module = model.get_submodule(parent)
            module._parameters[leaf] = torch.nn.Parameter(tensor, requires_grad=False)
        # This exact HF default-RoPE construction is an independent source path.
        model.rotary_emb = namespace["Qwen3RotaryEmbedding"](config, device="cpu")
        if any(p.device.type != "cpu" for p in model.parameters()):
            raise ValueError("Unbound meta/non-CPU owner parameter")
        model.eval()
        self._model = model
        self._head = provider._head
        self.dtype = provider.dtype

    def forward(self, *, complete_context_features, context_positions,
                query_embeddings, query_positions):
        torch = self.torch
        features = complete_context_features.detach().to(dtype=self.dtype).unsqueeze(0)
        noise = query_embeddings.detach().to(dtype=self.dtype)
        positions = torch.tensor([tuple(context_positions) + tuple(query_positions)],
                                 dtype=torch.long, device="cpu")
        with torch.inference_mode():
            hidden = self._model._forward_backbone(position_ids=positions,
                attention_mask=None, noise_embedding=noise, target_hidden_states=features,
                past_key_values=None, use_cache=False, is_causal=False)
            logits = torch.cat([torch.nn.functional.linear(hidden,
                self._head[start:start + 8192].to(dtype=self.dtype))
                for start in range(0, VOCAB, 8192)], dim=-1)
        return hidden, logits


def error_record(actual, expected, *, atol=None, rtol=None):
    # No guessed cosine/error threshold. Allclose is reported only if the caller
    # explicitly supplied BOTH tolerances; zero reference values are separate.
    import torch
    with torch.inference_mode():
        a, b = actual.double(), expected.double()
        absolute = (a - b).abs()
        nonzero = b != 0
        record = {
            "max_absolute_error": float(absolute.max().item()),
            "max_relative_error_nonzero_reference": float((absolute[nonzero] / b[nonzero].abs()).max().item())
                if bool(nonzero.any()) else None,
            "zero_reference_nonzero_actual_count": int(((b == 0) & (a != 0)).sum().item()),
            "exact_element_count": int((actual == expected).sum().item()),
            "element_count": actual.numel(),
            "all_values_finite": bool(torch.isfinite(actual).all() & torch.isfinite(expected).all()),
        }
        if (atol is None) != (rtol is None):
            raise ValueError("Supply both atol and rtol, or neither")
        if atol is not None:
            if atol < 0 or rtol < 0:
                raise ValueError("Allclose tolerances must be nonnegative")
            record.update(atol=atol, rtol=rtol,
                          allclose=bool(torch.allclose(actual, expected, atol=atol, rtol=rtol)))
    return record


def compare_proposal(provider, oracle, *, proposal, complete_context_features,
                     anchor, atol=None, rtol=None):
    with provider.torch.inference_mode():
        query = provider.torch.stack((anchor.values.to(provider.dtype),
                                     provider._mask, provider._mask), dim=0).unsqueeze(0)
        hidden, logits = oracle.forward(complete_context_features=complete_context_features,
            context_positions=provider.accepted_positions, query_embeddings=query,
            query_positions=proposal.query.query_positions)
        owner_ids = tuple(int(x) for x in logits[0].argmax(dim=-1).tolist())
    return {
        "round_index": proposal.query.round_index,
        "context_length": provider.context_length,
        "query_positions": list(proposal.query.query_positions),
        "provider_raw_ids": list(proposal.raw_ids), "owner_raw_ids": list(owner_ids),
        "raw_id_equality": proposal.raw_ids == owner_ids,
        "offerable": proposal.offerable,
        "hidden": error_record(proposal.hidden_states, hidden, atol=atol, rtol=rtol),
        "logits": error_record(proposal.logits, logits, atol=atol, rtol=rtol),
    }
