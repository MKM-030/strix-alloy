"""Fresh policy and retained generic helper closure without runtime operations."""
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / 'cohort'))
spec = importlib.util.spec_from_file_location('fresh0202_framework_tested', HERE / 'cohort/cohort_campaign.py')
c = importlib.util.module_from_spec(spec); spec.loader.exec_module(c)


class FrameworkBindingTests(unittest.TestCase):
    def test_retained_cost_helper_reads_only_current_normal_policy(self):
        def forbidden(): raise AssertionError('Old normal profile must not be read')
        framework = NS(policy=NS(normal=forbidden))
        reference = NS()
        trace = NS(qualify_trace=lambda *args: {})
        modules = {'real_npu_existing_lifecycle': framework,
                   'real_npu_original_lookup_trace': trace,
                   'real_npu_existing_cleanup': reference}
        with patch.object(c, 'load', side_effect=lambda name, path: modules[name]):
            selected, _ = c.support(HERE / 'unused-CPU-output', {'native_environment': {}})
        self.assertIs(selected, framework)
        self.assertEqual(framework.PACKAGE, c.PACKAGE)
        self.assertEqual(framework.policy.normal(), json.loads(c.NORMAL.read_bytes()))
        self.assertEqual(reference.NORMAL, c.NORMAL)

    def test_prepared_bindings_remain_unsealed_and_include_transitive_reader(self):
        path = HERE / 'bindings-prepared-v3.json'
        value = json.loads(path.read_bytes())
        self.assertFalse(value['root_sealed'])
        paths = {Path(row['path']).name for row in value['retained_generic_framework']}
        self.assertIn('oracle_evidence.py', paths)
        self.assertEqual(value['normal_source_manifest']['sha256'], c.BASE_SOURCE_SHA)


if __name__ == '__main__': unittest.main()
