"""Numerical checks for the selected-expert prototype; no NPU initialization."""
import importlib.util
import io
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
DEPENDENCIES = all(importlib.util.find_spec(name) for name in ('numpy', 'onnx', 'onnxruntime'))


@unittest.skipUnless(DEPENDENCIES, 'optional ONNX/NumPy runtime is unavailable')
class SelectedExpertTests(unittest.TestCase):
    def test_provider_copy_requires_complete_identical_file_bytes(self):
        from halogen_npu_expert_onnx import verified_provider_copy
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original, copied = root / 'installed', root / 'copied'
            original.mkdir()
            copied.mkdir()
            for folder in (original, copied):
                (folder / 'provider.dll').write_bytes(b'provider-bytes')
                (folder / 'dependency.dll').write_bytes(b'dependency-bytes')
            chosen, receipt = verified_provider_copy(original / 'provider.dll', copied)
            self.assertEqual(chosen, copied / 'provider.dll')
            self.assertEqual(len(receipt), 2)
            self.assertTrue(all(row['catalog_sha256'] == row['copied_sha256'] for row in receipt))
            with self.assertRaisesRegex(ValueError, 'separate directory'):
                verified_provider_copy(original / 'provider.dll', original)
            (copied / 'dependency.dll').write_bytes(b'dependency-tamper')
            with self.assertRaisesRegex(ValueError, 'differs from installed bytes'):
                verified_provider_copy(original / 'provider.dll', copied)
            (copied / 'dependency.dll').unlink()
            with self.assertRaisesRegex(ValueError, 'file set differs'):
                verified_provider_copy(original / 'provider.dll', copied)
            (copied / 'dependency.dll').write_bytes(b'dependency-bytes')
            (copied / 'unexpected.dll').write_bytes(b'extra')
            with self.assertRaisesRegex(ValueError, 'file set differs'):
                verified_provider_copy(original / 'provider.dll', copied)

    def test_top10_graph_matches_separate_weighted_experts(self):
        import numpy as np
        import onnxruntime as ort
        from halogen_npu_expert_onnx import build_graph
        rng = np.random.default_rng(72)
        gu = rng.normal(0, .2, (10, 8, 32)).astype(np.float32)
        down = rng.normal(0, .2, (10, 32, 4)).astype(np.float32)
        x = rng.normal(0, 1, (1, 32)).astype(np.float32)
        coefficients = np.arange(1, 11, dtype=np.float32) / 55
        expected = np.zeros((1, 32), dtype=np.float32)
        for index in range(10):
            projected = x @ gu[index].T
            gate, up = projected[:, :4], projected[:, 4:]
            expected += coefficients[index] * ((gate / (1 + np.exp(-gate)) * up) @ down[index].T)
        options = ort.SessionOptions()
        options.intra_op_num_threads = 1
        session = ort.InferenceSession(build_graph(gu, down, tuple(range(10))).SerializeToString(),
                                       sess_options=options, providers=['CPUExecutionProvider'])
        actual = session.run(None, {'x': x, 'routing_weights': coefficients.reshape(10, 1, 1)})[0]
        np.testing.assert_allclose(actual, expected, rtol=2e-5, atol=2e-6)
        # Changing router coefficients must change the weighted sum, not the weights.
        selected = np.zeros(10, dtype=np.float32)
        selected[7] = 1
        actual = session.run(None, {'x': x, 'routing_weights': selected.reshape(10, 1, 1)})[0]
        projected = x @ gu[7].T
        gate, up = projected[:, :4], projected[:, 4:]
        expected = (gate / (1 + np.exp(-gate)) * up) @ down[7].T
        np.testing.assert_allclose(actual, expected, rtol=2e-5, atol=2e-6)

    def test_replay_preserves_legacy_vector_and_host_shaped_router_parity(self):
        import numpy as np
        import onnx
        from onnx import helper, TensorProto, numpy_helper
        from halogen_npu_expert_onnx import build_graph, replay, save_graph
        rng = np.random.default_rng(103)
        gu = rng.normal(0, .2, (10, 8, 32)).astype(np.float32)
        down = rng.normal(0, .2, (10, 32, 4)).astype(np.float32)
        selected = tuple(range(10))
        current = build_graph(gu, down, selected)
        # Historical [10] router ABI: the graph itself inserts the shape operation.
        legacy = onnx.ModelProto()
        legacy.CopyFrom(current)
        legacy.graph.input[1].CopyFrom(helper.make_tensor_value_info('routing_weights', TensorProto.FLOAT, [10]))
        legacy.graph.initializer.append(numpy_helper.from_array(np.array([1, 2], dtype=np.int64), 'routing_axes'))
        routing_mul_index = next(index for index, node in enumerate(legacy.graph.node)
                                 if 'routing_weights' in node.input)
        legacy.graph.node[routing_mul_index].input[1] = 'routing_column'
        legacy.graph.node.insert(routing_mul_index,
                                 helper.make_node('Unsqueeze', ['routing_weights', 'routing_axes'], ['routing_column']))
        onnx.checker.check_model(legacy)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            results = []
            for name, graph in (('current', current), ('legacy', legacy)):
                model_path = root / (name + '.onnx')
                save_graph(graph, model_path, gu, down, selected)
                result = replay(model_path, 'cpu', 3, root / (name + '.json'))
                self.assertTrue(result['passed'], result.get('error'))
                results.append(result)
            self.assertEqual(results[0]['routing_input_shape'], [10, 1, 1])
            self.assertEqual(results[1]['routing_input_shape'], [10])
            self.assertEqual(results[0]['input_sha256'], results[1]['input_sha256'])
            self.assertEqual(results[0]['routing_sha256'], results[1]['routing_sha256'])
            self.assertAlmostEqual(results[0]['max_abs_error'], results[1]['max_abs_error'], places=7)

    def test_single_expert_keeps_one_input_contract(self):
        import numpy as np
        from halogen_npu_expert_onnx import build_graph
        graph = build_graph(np.zeros((8, 32), dtype=np.float32), np.zeros((32, 4), dtype=np.float32))
        self.assertEqual([value.name for value in graph.graph.input], ['x'])
        self.assertEqual([value.name for value in graph.graph.output], ['y'])

    def test_ambiguous_geometry_duplicate_ids_and_nonfinite_weights_are_refused(self):
        import numpy as np
        from halogen_npu_expert_onnx import build_graph, expert_ids
        with self.assertRaises(ValueError):
            expert_ids('0,0,1,2,3,4,5,6,7,8')
        with self.assertRaises(ValueError):
            expert_ids(','.join(str(i) for i in range(9)))
        with self.assertRaises(ValueError):
            build_graph(np.zeros((10, 8, 32)), np.zeros((10, 33, 4)), tuple(range(10)))
        gu = np.zeros((10, 8, 32), dtype=np.float32)
        gu[4, 3, 2] = np.nan
        with self.assertRaises(ValueError):
            build_graph(gu, np.zeros((10, 32, 4)), tuple(range(10)))

    def test_q4c_nonzero_rows_and_truncated_scale_plane(self):
        import numpy as np
        from hgn_q4c_slice import decode_rows
        # Four 32-wide rows, one scale per row plus padding to a 16-byte stride.
        codebook = np.arange(16, dtype='<f4').tobytes()
        codes = b''.join(bytes([index | ((index + 1) << 4)]) * 16 for index in range(4))
        scales = b''.join(np.array([index + .5], dtype='<f2').tobytes() + b'\0' * 14
                          for index in range(4))
        payload = codebook + codes + scales
        entry = {'store': 5, 'variant': 2, 'dims': [2, 2, 32], 'offset': 0, 'size': len(payload)}
        actual = decode_rows(io.BytesIO(payload), entry, 1, 2)
        expected = np.array([[1, 2] * 16, [2, 3] * 16], dtype=np.float32)
        expected *= np.array([1.5, 2.5], dtype=np.float32)[:, None]
        np.testing.assert_array_equal(actual, expected)
        with self.assertRaises(ValueError):
            decode_rows(io.BytesIO(payload[:-20]), entry, 3, 1)

    def test_saved_graph_data_and_receipt_are_never_overwritten(self):
        import numpy as np
        from halogen_npu_expert_onnx import build_graph, digest, save_graph
        gu, down = np.zeros((10, 8, 32), dtype=np.float32), np.zeros((10, 32, 4), dtype=np.float32)
        selected = tuple(range(10))
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'top10.onnx'
            receipt = save_graph(build_graph(gu, down, selected), path, gu, down, selected)
            identities = {file.name: digest(file) for file in Path(temporary).iterdir()}
            self.assertEqual(receipt['model_sha256'], digest(path))
            self.assertEqual(receipt['data_sha256'], digest(path.with_name(path.name + '.data')))
            with self.assertRaises(FileExistsError):
                save_graph(build_graph(gu, down, selected), path, gu, down, selected)
            self.assertEqual(identities, {file.name: digest(file) for file in Path(temporary).iterdir()})

    def test_imported_top10_reader_refuses_unbounded_selection_before_io(self):
        from halogen_npu_expert_onnx import read_top10

        class NoIO:
            def read_text(self, **kwargs):
                raise AssertionError('manifest read before selected-ID admission')

            def stat(self):
                raise AssertionError('HGN accessed before selected-ID admission')

        for selected in (range(512), (0,) * 10, (True,) + tuple(range(1, 10)), tuple(range(1, 10)) + (512,)):
            with self.subTest(selected=str(selected)):
                with self.assertRaises(ValueError):
                    read_top10(NoIO(), NoIO(), selected)


if __name__ == '__main__':
    unittest.main()
