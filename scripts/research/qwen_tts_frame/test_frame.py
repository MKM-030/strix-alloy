"""Check the CPU replay's sampling and dependent acoustic decisions."""

from pathlib import Path
import struct
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

import numpy as np

from .frame import FramePredictor, sample_code
from .fixtures import acoustic_sampler_inputs, load_first_frame, philox_uniform


def toy_weights():
    architecture = SimpleNamespace(hidden_size=4, intermediate_size=4,
                                   num_hidden_layers=1, num_attention_heads=2,
                                   num_key_value_heads=1, head_dim=2, vocab_size=3,
                                   num_acoustic_codebooks=2, rope_theta=10000.0,
                                   rms_norm_eps=1e-6, talker_hidden_size=4,
                                   talker_vocab_size=3)
    table = np.eye(4, dtype=np.float32)[:3]
    prefix = 'code_pred.blk.0.'
    tensors = {
        'talker.codec_embd.weight': table,
        'code_pred.codec_embd.0.weight': table,
        'code_pred.lm_head.0.weight': table[[0, 2, 1]],
        'code_pred.lm_head.1.weight': table[[2, 0, 1]],
        'code_pred.output_norm.weight': np.ones(4, dtype=np.float32),
    }
    for name in ('attn_norm', 'ffn_norm', 'attn_q_norm', 'attn_k_norm'):
        size = 2 if name in ('attn_q_norm', 'attn_k_norm') else 4
        tensors[prefix + name + '.weight'] = np.ones(size, dtype=np.float32)
    for name in ('attn_q', 'attn_k', 'attn_v', 'attn_output', 'ffn_gate', 'ffn_up', 'ffn_down'):
        size = 2 if name in ('attn_k', 'attn_v') else 4
        tensors[prefix + name + '.weight'] = np.zeros((size, 4), dtype=np.float32)
    return SimpleNamespace(architecture=architecture, tensors=tensors)


class FrameTests(unittest.TestCase):
    def test_sampler_uses_strict_crossing_and_ranked_original_ids(self):
        logits = np.array([-3.0, 4.0, 0.0], dtype=np.float32)
        self.assertEqual(sample_code(logits, 1.0, 0.0, 2), 1)
        self.assertEqual(sample_code(logits, 1.0, 0.999, 2), 2)
        tied = np.zeros(4, dtype=np.float32)
        self.assertEqual(sample_code(tied, 1.0, 0.25, 4), 1)

    def test_previous_acoustic_code_selects_next_embedding(self):
        predictor = FramePredictor(toy_weights())
        hidden = np.ones(4, dtype=np.float32)
        uniform = np.zeros(2, dtype=np.float32)
        first = predictor.predict(hidden, 1, 1.0, uniform, top_k=3)
        forced = predictor.predict(hidden, 1, 1.0, uniform, top_k=3, forced_codes=[1, 0])
        second = predictor.predict(hidden, 1, 1.0, uniform, top_k=3)
        np.testing.assert_array_equal(first.codes, np.array([1, 2, 0]))
        np.testing.assert_array_equal(forced.codes, np.array([1, 2, 2]))
        np.testing.assert_array_equal(second.codes, first.codes)
        np.testing.assert_array_equal(second.logits, first.logits)
        self.assertEqual(first.logits.shape, (2, 3))

    def test_loads_last_visible_hidden_row_and_rejects_short_native_dump(self):
        with TemporaryDirectory() as path:
            folder = Path(path)
            hidden = np.arange(2048, dtype='<f4').reshape(2, 1024)
            codes = np.arange(16, dtype='<f4')
            (folder / 'talker-hidden-prefill-final.bin').write_bytes(
                struct.pack('<iii', 2, 2, 1024) + hidden.tobytes())
            code_path = folder / 'codes-step0.bin'
            data = struct.pack('<ii', 1, 16) + codes.tobytes()
            code_path.write_bytes(data)
            last, sampled = load_first_frame(folder)
            np.testing.assert_array_equal(last, hidden[-1])
            np.testing.assert_array_equal(sampled, codes.astype(np.int32))
            code_path.write_bytes(data[:-1])
            with self.assertRaisesRegex(ValueError, 'file length'):
                load_first_frame(folder)

    def test_sampler_inputs_match_native_logged_draws_and_greedy_mode(self):
        for seed, subsequence, native in ((42, 0, 0.6129598618), (42, 16, 0.7741796374),
                                         (91, 0, 0.6379817128), (91, 16, 0.3106479347)):
            self.assertEqual(philox_uniform(seed, subsequence), np.float32(native))
        temperature, draws = acoustic_sampler_inputs(42, 0, 0.0)
        self.assertEqual(temperature, np.float32(1.0))
        np.testing.assert_array_equal(draws, np.zeros(15, dtype=np.float32))


if __name__ == '__main__':
    unittest.main()
