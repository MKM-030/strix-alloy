"""DeepSpec c92c068 Qwen3DSparkModel, DFlash-only vLLM serving attachment.

The existing DFlash Qwen3 implementation has the same five-layer backbone:
context hidden_norm(fc(taps)), unnormalised-by-layer context K/V, query
pre-norm, per-head Q/K norms, full NeoX RoPE and non-causal block attention.
Only registration, strict checkpoint loading and anchor scheduling differ.
"""
from vllm.model_executor.models.qwen3_dflash import DFlashQwen3ForCausalLM


TAPS = [3, 15, 23, 35, 43]


def checkpoint_shapes():
    shapes = {"fc.weight": (2560, 12800), "hidden_norm.weight": (2560,),
              "norm.weight": (2560,)}
    for layer in range(5):
        prefix = f"layers.{layer}."
        for name, shape in {
            "input_layernorm.weight": (2560,),
            "post_attention_layernorm.weight": (2560,),
            "self_attn.q_proj.weight": (6144, 2560),
            "self_attn.k_proj.weight": (512, 2560),
            "self_attn.v_proj.weight": (512, 2560),
            "self_attn.o_proj.weight": (2560, 6144),
            "self_attn.q_norm.weight": (256,),
            "self_attn.k_norm.weight": (256,),
            "mlp.gate_proj.weight": (7680, 2560),
            "mlp.up_proj.weight": (7680, 2560),
            "mlp.down_proj.weight": (2560, 7680),
        }.items():
            shapes[prefix + name] = shape
    return shapes


class DFlashQwen3DSparkModel(DFlashQwen3ForCausalLM):
    """Native DeepSpec DFlash weights on vLLM's TP-parallel Qwen3 kernels."""

    has_own_embed_tokens = False
    has_own_lm_head = False

    def __init__(self, *, vllm_config, prefix=""):
        spec = vllm_config.speculative_config
        config = spec.draft_model_config.hf_config
        expected = {
            "hidden_size": 2560, "intermediate_size": 7680,
            "num_hidden_layers": 5, "num_attention_heads": 24,
            "num_key_value_heads": 2, "head_dim": 256, "vocab_size": 248320,
            "block_size": 7, "mask_token_id": 248077, "markov_rank": 0,
            "enable_confidence_head": False, "attention_bias": False,
            "tie_word_embeddings": False, "hidden_act": "silu",
            "rms_norm_eps": 1e-6,
        }
        for field, value in expected.items():
            if getattr(config, field, None) != value:
                raise ValueError(f"Epoch7 {field} must be {value!r}")
        if list(config.target_layer_ids) != TAPS:
            raise ValueError("Epoch7 requires HC taps [3,15,23,35,43]")
        rope = config.rope_parameters
        if (rope.get("rope_type") != "default"
                or rope.get("rope_theta") != 10000000.0
                or rope.get("partial_rotary_factor", 1.0) != 1.0
                or not getattr(config, "is_neox_style", True)):
            raise ValueError("Epoch7 requires full-head default NeoX RoPE theta=1e7")
        if config.layer_types != ["full_attention"] * 5:
            raise ValueError("Epoch7 requires five non-causal full-attention layers")
        if spec.method != "dflash" or spec.num_speculative_tokens not in (4, 5, 7):
            raise ValueError("Epoch7 serving supports DFlash K=4,5,7, never native MTP")
        if not config.dflash_config.get("query_zero_predicts_next"):
            raise ValueError("DeepSpec requires the query-zero proposer patch")
        if spec.target_model_config.architectures != ["Qwen4ExpForConditionalGeneration"]:
            raise ValueError("Epoch7 attachment requires the native Qwen4Exp VLM wrapper")
        if str(spec.draft_model_config.dtype) != "torch.bfloat16":
            raise ValueError("Epoch7 draft compute must remain BF16")
        if vllm_config.parallel_config.tensor_parallel_size != 2:
            raise ValueError("This attachment is contracted for TP2")
        if vllm_config.parallel_config.pipeline_parallel_size != 1:
            raise ValueError("HC auxiliary transport is not implemented for PP")
        if not vllm_config.model_config.enforce_eager:
            raise ValueError("HC attachment requires enforce_eager")
        if spec.draft_model_config.quantization is not None:
            raise ValueError("Epoch7 draft is BF16, not target ModelOpt NVFP4")
        super().__init__(vllm_config=vllm_config, prefix=prefix)

    def load_weights(self, weights):
        expected = checkpoint_shapes()
        seen = set()

        def checked():
            for name, tensor in weights:
                if name not in expected or name in seen:
                    raise ValueError(f"Unexpected/duplicate epoch7 tensor: {name}")
                if tuple(tensor.shape) != expected[name] or str(tensor.dtype) != "torch.bfloat16":
                    raise ValueError(f"Wrong epoch7 tensor shape/dtype: {name}")
                seen.add(name)
                yield name, tensor
            if seen != expected.keys():
                raise ValueError(f"Missing epoch7 tensors: {sorted(expected.keys() - seen)}")

        # Parent loader maps q/k/v and gate/up through vLLM's TP weight loaders,
        # builds per-rank fused context K/V, and leaves stripped head/embed for
        # SpecDecodeBaseProposer.load_model's target-module sharing protocol.
        return super().load_weights(checked())
