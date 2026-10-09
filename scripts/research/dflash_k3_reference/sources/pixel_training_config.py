import os

from deepspec.trainer import Qwen4ExpDSparkTrainer
from deepspec.utils.constant import BASE_CKPT_DIR, BASE_TB_DIR, QWEN_3_8_FLASH_NEXT

project_name = "deepspec"
exp_name = "dflash_block7_qwen38_flash_next"
seed = 42

model = dict(
    target_model_name_or_path=QWEN_3_8_FLASH_NEXT,
    # Pin the target revision: Qwen/Qwen3.8-Flash-Next is a moving repo on
    # HF main. Recorded in docs/dflash-training-log.md; falls back to latest
    # main if this SHA stops resolving (also recorded there).
    target_model_revision="f5d08274bafd880402bd16f5e3e6c514136ec06c",
    block_size=7,
    num_draft_layers=5,
    # Qwen3.8-Flash-Next (qwen4_exp): 48 decoder layers, full-attention/QSA
    # at every 4th layer starting from index 3 (0-indexed):
    #   [3, 7, 11, 15, 19, 23, 27, 31, 35, 39, 43, 47]  (12 layers total)
    # DeepSpec's rule: uniform spacing from the second layer through the
    # third-to-last (the Qwen3-8B/36-layer protocol's [1,9,17,25,33] is
    # exactly this rule applied to its own full-attention layout). Applied
    # here per coordinator correction 2026-09-06:
    #   [3, 15, 23, 35, 43]
    # (An earlier pick, [7,15,23,27,35], was rejected: 27 and 35 are
    # adjacent full-attention ordinals -- not uniform -- and nothing was
    # tapped after 35. See docs/dflash-training-log.md for the full note.)
    target_layer_ids=[3, 15, 23, 35, 43],
    # First embedding row after all defined vocab.json (0..248043) +
    # added special tokens (248044..248076) for Qwen/Qwen3.8-Flash-Next,
    # i.e. the first row in the padded embedding table's reserved slack --
    # exact structural analog of the original Qwen3-8B mask_token_id=151669
    # (151643 defined + 26 added special tokens = 151669). See
    # docs/dflash-training-log.md for the numeric derivation.
    mask_token_id=248077,
    num_anchors=512,

    # Disable markov head.
    markov_rank=0,

    # Disable confidence head.
    confidence_head_alpha=0.0,

    # CE-only loss.
    loss_decay_gamma=4.0,
    ce_loss_alpha=1.0,
    l1_loss_alpha=0.0,
)

train = dict(
    trainer_cls=Qwen4ExpDSparkTrainer,
    lr=6.0e-4,
    warmup_ratio=0.04,
    weight_decay=0.0,
    precision="bf16",
    local_batch_size=1,
    global_batch_size=512,
    num_train_epochs=10,
    max_train_steps=None,
    max_grad_norm=1.0,
    sharding_strategy="no_shard",
    torch_compile=True,
)

logging = dict(
    logging_steps=10,
    checkpointing_steps=3000,
)

data = dict(
    target_cache_path=None,
    chat_template="qwen38_flash_next",
    max_length=4096,
    num_workers=4,
)


def finalize_cfg(cfg):
    logging_cfg = dict(cfg["logging"])
    project_name=str(cfg['project_name'])
    exp_name = str(cfg["exp_name"])
    logging_cfg["checkpoint_dir"] = os.path.join(BASE_CKPT_DIR, project_name, exp_name)
    logging_cfg["tensorboard_dir"] = os.path.join(BASE_TB_DIR, project_name, exp_name)
    cfg["logging"] = logging_cfg

    return cfg
