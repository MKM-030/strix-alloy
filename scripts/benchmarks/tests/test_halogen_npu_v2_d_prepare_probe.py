"""Offline placement-proof guards; never import ORT or initialize a provider."""
import importlib.util
from pathlib import Path
import sys
import unittest


SOURCE = Path(__file__).resolve().parents[1] / "halogen_npu_v2_d_prepare_probe.py"


class PlacementProofTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.probe = None
        if SOURCE.exists():
            spec = importlib.util.spec_from_file_location("d_probe_offline", SOURCE)
            cls.probe = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = cls.probe
            spec.loader.exec_module(cls.probe)

    def require_probe(self):
        self.assertIsNotNone(self.probe, "strict D placement guards are not implemented")
        return self.probe

    def context(self):
        return {
            "metaDef": [{"device": "VAIML", "nodes": ["e_square", "h_inverse_rms", "e_norm_bf16", "h_streams", "e_projected", "h_projected", "seed"],
                         "vaimlParam": {"deviceName": "stx", "runnerType": "hw"}}],
            "config": {"cacheKey": "cache", "ort_session_config": {"session.disable_cpu_ep_fallback": "1"},
                       "sessionOptions": {"library_path": "provider.dll", "cache_key": "cache"},
                       "passes": [{"name": "vaiml_partition", "vaimlConfig": {"device": "stx"}}]},
        }

    def test_any_cpu_or_missing_node_attribution_fails(self):
        probe = self.require_probe()
        node = {"cat": "Node", "args": {"provider": "VitisAIExecutionProvider"}}
        self.assertTrue(probe.profile_proof([node], "npu")["passed"])
        self.assertFalse(probe.profile_proof([], "npu")["passed"])
        self.assertFalse(probe.profile_proof([node, {"cat": "Node", "args": {}}], "npu")["passed"])
        self.assertFalse(probe.profile_proof([node, {"cat": "Node", "args": {"provider": "CPUExecutionProvider"}}], "npu")["passed"])

    def test_context_must_cover_dynamic_norm_casts_and_projections_in_hardware(self):
        probe = self.require_probe()
        required = {"e_square", "h_inverse_rms", "e_norm_bf16", "h_streams", "e_projected", "h_projected", "seed"}
        self.assertTrue(probe.context_proof(self.context(), required, "cache", "provider.dll")["passed"])
        context = self.context()
        context["metaDef"][0]["nodes"].remove("h_projected")
        self.assertFalse(probe.context_proof(context, required, "cache", "provider.dll")["passed"])
        context = self.context()
        context["metaDef"][0]["nodes"].remove("e_norm_bf16")
        self.assertFalse(probe.context_proof(context, required, "cache", "provider.dll")["passed"])
        context = self.context()
        context["metaDef"][0]["vaimlParam"]["runnerType"] = "cpu"
        self.assertFalse(probe.context_proof(context, required, "cache", "provider.dll")["passed"])

    def test_context_rejects_fallback_and_wrong_compilation_identity(self):
        probe = self.require_probe()
        required = {"e_projected", "h_projected", "seed"}
        context = self.context()
        context["config"]["ort_session_config"]["session.disable_cpu_ep_fallback"] = "0"
        self.assertFalse(probe.context_proof(context, required, "cache", "provider.dll")["passed"])
        self.assertFalse(probe.context_proof(self.context(), required, "other-cache", "provider.dll")["passed"])
        self.assertFalse(probe.context_proof(self.context(), required, "cache", "other-provider.dll")["passed"])


if __name__ == "__main__":
    unittest.main()
