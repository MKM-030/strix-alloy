"""Tiny runtime-weight graph fixtures; CPU EP only, never register VitisAI."""
import importlib.util
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
DEPENDENCIES = all(importlib.util.find_spec(name) for name in ('onnx', 'onnxruntime'))


@unittest.skipUnless(DEPENDENCIES, 'use the existing winml-npu Python environment')
class ParameterProbeTests(unittest.TestCase):
    def test_runtime_matrices_are_graph_inputs_and_alternating_calls_match_independent_reference(self):
        import onnxruntime as ort
        from halogen_npu_parameter_probe import build_graph, fixtures, reference
        model = build_graph()
        inputs = {value.name for value in model.graph.input}
        initializers = {value.name for value in model.graph.initializer}
        self.assertTrue({'W_gate_up', 'W_down', 'x', 'routing_weights'} <= inputs)
        self.assertFalse({'W_gate_up', 'W_down'} & initializers)
        options = ort.SessionOptions()
        options.intra_op_num_threads = 1
        session = ort.InferenceSession(model.SerializeToString(), sess_options=options,
                                       providers=['CPUExecutionProvider'])
        feeds = fixtures()
        for label in ('A', 'B', 'A', 'B'):
            expected = reference(feeds[label])
            actual = session.run(None, feeds[label])[0]
            np.testing.assert_allclose(actual, expected, rtol=3e-5, atol=3e-6)
        self.assertFalse(np.allclose(reference(feeds['A']), reference(feeds['B']), rtol=.03, atol=.003))
        self.assertLess(sum(value.nbytes for feed in feeds.values() for value in feed.values()), 1 << 20)

    def test_literal_one_expert_reference_and_individual_runtime_input_changes(self):
        import onnxruntime as ort
        from halogen_npu_parameter_probe import build_graph, fixtures, reference
        feeds = fixtures()
        seed = {name: np.zeros_like(value) for name, value in feeds['A'].items()}
        seed['x'][0, 0] = 2
        seed['W_gate_up'][0, 0, 0] = .5
        seed['W_gate_up'][0, 0, 32] = 1
        seed['W_down'][0, 0, 0] = 3
        seed['routing_weights'][0, 0, 0] = 1
        expected = np.zeros_like(seed['x'])
        expected[0, 0] = 4.3863514718  # SiLU(1) * 2 * 3.
        np.testing.assert_allclose(reference(seed), expected, rtol=1e-6, atol=1e-7)
        session = ort.InferenceSession(build_graph().SerializeToString(), providers=['CPUExecutionProvider'])
        baseline = session.run(None, feeds['A'])[0]
        for name in ('W_gate_up', 'W_down', 'x', 'routing_weights'):
            changed = dict(feeds['A'], **{name: feeds['B'][name]})
            actual = session.run(None, changed)[0]
            np.testing.assert_allclose(actual, reference(changed), rtol=3e-5, atol=3e-6)
            self.assertFalse(np.allclose(actual, baseline, rtol=3e-5, atol=3e-6), name)


if __name__ == '__main__':
    unittest.main()
