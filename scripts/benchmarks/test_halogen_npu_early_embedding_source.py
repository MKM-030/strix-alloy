"""Standard-library source-contract checks; no assets, providers or ONNX imports."""
import unittest
from types import SimpleNamespace as NS


class EarlyEmbeddingContractTests(unittest.TestCase):
    def test_embedding_selection_rejects_hidden_dependency(self):
        import halogen_npu_early_embedding_graph as graph
        nodes = [NS(input=["e_high", "W_embedding_high"], output=[name])
                 for name in graph.REQUIRED_OUTPUTS]
        original = NS(node=nodes, input=[NS(name=n) for n in graph.INPUT_SHAPES],
                      output=[NS(name="e_projection")],
                      initializer=[NS(name=n) for n in graph.INITIALIZER_NAMES])
        selected = graph.embedding_members(original)
        self.assertEqual(len(selected[0]), 9)
        nodes[0].input.append("W_hidden_high")
        with self.assertRaises(ValueError):
            graph.embedding_members(original)

    def test_failed_or_paired_cpu_receipt_cannot_admit_npu(self):
        import halogen_npu_early_embedding_probe as probe
        current = {key: "same" for key in probe.IDENTITY_KEYS}
        gate = {**current, **probe.CPU_REQUIRED, "error": None}
        probe.cpu_receipt_header(gate, current)
        for mutation in ({"passed": False}, {"cpu_passed": False},
                         {"schema": "halogen_v2_count1_D_native_projection_stable_split_diagnostic.v1"},
                         {"hidden_input_used": True}, {"tolerance": {"rtol": .03, "atol": .003}}):
            with self.subTest(mutation=mutation):
                with self.assertRaises(ValueError):
                    probe.cpu_receipt_header({**gate, **mutation}, current)


if __name__ == "__main__":
    unittest.main()
