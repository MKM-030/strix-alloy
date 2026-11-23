"""Exercise the ONNX acoustic sampler with the local CPU provider."""

import unittest

import numpy as np
import onnx
import onnxruntime as ort
from onnx import TensorProto, helper

from .export_first import _Graph
from .frame import sample_code
from .sampler import emit_sample


class SamplerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        graph = _Graph()
        code, valid = emit_sample(graph, 'logits', 'temperature', 'uniform', top_k=2)
        inputs = [helper.make_tensor_value_info(name, TensorProto.FLOAT, dims)
                  for name, dims in (('logits', [4]), ('temperature', []), ('uniform', []))]
        outputs = [helper.make_tensor_value_info(code, TensorProto.INT64, []),
                   helper.make_tensor_value_info(valid, TensorProto.BOOL, [])]
        model = helper.make_model(helper.make_graph(graph.nodes, 'sampler_test', inputs, outputs,
                                                    initializer=graph.initializers),
                                  opset_imports=[helper.make_opsetid('', 17)], ir_version=8)
        onnx.checker.check_model(model, full_check=True)
        config = ort.SessionOptions()
        config.intra_op_num_threads = 1
        config.inter_op_num_threads = 1
        cls.session = ort.InferenceSession(model.SerializeToString(), sess_options=config,
                                           providers=['CPUExecutionProvider'])

    def sample(self, logits, temperature, uniform):
        return tuple(value.item() for value in self.session.run(None, {
            'logits': np.asarray(logits, dtype=np.float32),
            'temperature': np.asarray(temperature, dtype=np.float32),
            'uniform': np.asarray(uniform, dtype=np.float32),
        }))

    def test_unique_logits_match_order_and_first_strict_crossing(self):
        for temperature, points in ((0.9, (0.0, 0.2, 0.6, 0.99)), (1.0, (0.0, 0.749, 0.75, 0.751))):
            logits = [-3.0, float(np.log(3.0)), 0.0, -1.0]
            for uniform in points:
                with self.subTest(temperature=temperature, uniform=uniform):
                    code = sample_code(logits, temperature, uniform, top_k=2)
                    self.assertEqual(self.sample(logits, temperature, uniform), (code, True))

    def test_equal_scores_within_top_k_or_at_cutoff_require_fallback(self):
        for logits in ([1, 1, 0, -1], [2, 1, 1, 0]):
            self.assertEqual(self.sample(logits, 1.0, 0), (0, False))
        self.assertEqual(self.sample([2, 1, 0, 0], 1.0, 0), (0, True))

    def test_invalid_input_is_contained_even_when_candidate_index_is_outside_top_k(self):
        for logits, temperature, uniform in (([2, 1, 0, -1], 0.0, 0.0),
                                               ([2, 1, 0, -1], 1.0, 1.0),
                                               ([2, 1, 0, -1], float('inf'), 0.0),
                                               ([2, 1, 0, float('-inf')], 1.0, 0.0),
                                               ([2, 1, 0, float('nan')], 1.0, 0.0)):
            self.assertEqual(self.sample(logits, temperature, uniform), (0, False))


if __name__ == '__main__':
    unittest.main()
