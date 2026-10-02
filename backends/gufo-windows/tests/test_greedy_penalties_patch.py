import pathlib
import tempfile
import unittest
from importlib.util import module_from_spec, spec_from_file_location


ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = spec_from_file_location('optin_attention', ROOT / 'optin_attention.py')
optin = module_from_spec(spec)
spec.loader.exec_module(optin)


class GreedyPenaltiesPatchTests(unittest.TestCase):
    def test_opt_in_patch_walks_sparse_sorted_penalties_once(self):
        patch = (ROOT / 'patches/greedy-penalties-optin.patch').read_text()
        self.assertIn('auto penalty = penalty_counts_.begin()', patch)
        self.assertIn('penalty->token < index', patch)
        self.assertIn('Penalize(logits[index], config_, *penalty)', patch)
        self.assertNotIn('CanSelectArgmax', patch)

    def test_greedy_guard_refuses_unqualified_source(self):
        with tempfile.TemporaryDirectory() as directory:
            target = pathlib.Path(directory) / optin.GREEDY_RELATIVE
            target.parent.mkdir(parents=True)
            target.write_text('different source')
            with self.assertRaisesRegex(ValueError, 'pinned GUFO source'):
                optin.verify(directory, 'greedy')


if __name__ == '__main__':
    unittest.main()
