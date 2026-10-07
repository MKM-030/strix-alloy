"""Small offline refusal guards; no Linux/native/runtime work."""
import copy
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).with_name("halogen_serving_kernel_qualification.py")
spec = importlib.util.spec_from_file_location("cpu_qualification", SOURCE)
qualification = importlib.util.module_from_spec(spec); spec.loader.exec_module(qualification)


class RefusalTest(unittest.TestCase):
    def setUp(self):
        self.api = qualification.bridge()
        self.plan = dict(nonce="1" * 32, container_id="2" * 64, source_sha256={"pin": "3" * 64},
                         native_helper_sha256="4" * 64, native_helper_bytes=1024,
                         baseline_receipt_path="/candidate/baseline.json", baseline_receipt_sha256="5" * 64)
        masks = dict(effective=1 << 8, permitted=1 << 8, inheritable=0, bounding=1 << 8, ambient=0)
        self.receipt = dict(schema=qualification.BASELINE_SCHEMA, nonce="6" * 32, container_id="7" * 64,
                            native_probe_performed=False, source_sha256=self.plan["source_sha256"],
                            native_helper_sha256=self.plan["native_helper_sha256"], native_helper_bytes=1024,
                            snapshot=dict(capabilities=masks, task_count=1, cgroup="0::/docker/" + "7" * 64))

    def test_independent_no_bpf_receipt_is_required(self):
        bad = dict(self.plan, baseline_receipt_path=None)
        with self.assertRaises(ValueError): qualification.expected_masks(self.api, bad)
        for mutation in (dict(nonce=self.plan["nonce"]), dict(container_id=self.plan["container_id"]),
                         dict(native_probe_performed=True)):
            bad = dict(self.receipt, **mutation)
            with patch.object(qualification, "read_private", return_value=bad), self.assertRaises(ValueError):
                qualification.expected_masks(self.api, self.plan)

    def test_baseline_with_bpf_or_fake_private_cgroup_is_rejected(self):
        bad = copy.deepcopy(self.receipt); bad["snapshot"]["capabilities"]["bounding"] |= self.api.BPF_MASK
        with patch.object(qualification, "read_private", return_value=bad), self.assertRaises(ValueError):
            qualification.expected_masks(self.api, self.plan)
        bad = copy.deepcopy(self.receipt); bad["snapshot"]["cgroup"] = "0::/"
        bad["snapshot"]["container_id"] = bad["container_id"]
        with patch.object(qualification, "read_private", return_value=bad), self.assertRaises(ValueError):
            qualification.expected_masks(self.api, self.plan)

    def test_qualify_refuses_extra_capability_before_native_work(self):
        baseline = self.receipt["snapshot"]["capabilities"]
        policy = dict(baseline_masks=baseline, expected_before_masks=dict(baseline))
        before = dict(capabilities=dict(baseline)); before["capabilities"]["effective"] |= 1 << 21
        with (patch.object(qualification, "expected_masks", return_value=(self.receipt, policy)),
              patch.object(qualification, "check_pins"), patch.object(qualification, "owned_snapshot", return_value=before),
              patch.object(self.api, "_require_fresh_receipt"), patch.object(self.api, "_observe_native") as observe):
            with self.assertRaises(ValueError): qualification.qualify(self.api, self.plan, Path("unused"), "8" * 64)
        observe.assert_not_called()


if __name__ == "__main__": unittest.main()
