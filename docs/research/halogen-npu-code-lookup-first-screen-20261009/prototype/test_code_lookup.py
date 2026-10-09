"""Few filesystem correctness probes; only Git inventory is replaced for fixtures."""
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import code_lookup


ALPHA = (
    "# public source fixture\n"
    "def resolve_profile(route):\n"
    "    return route['backend']\n"
    "\n"
    "def normalize_request(body):\n"
    "    return dict(body)\n"
)
BETA = "def resolve_profile(name):\n    return {'name': name}\n"


class LookupCorrectness(unittest.TestCase):
    def setUp(self):
        self.area = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.addCleanup(self.area.cleanup)
        self.repo = Path(self.area.name)
        (self.repo / 'server').mkdir()
        (self.repo / 'server/alpha.py').write_bytes(ALPHA.encode('utf-8'))
        (self.repo / 'server/beta.py').write_bytes(BETA.encode('utf-8'))
        (self.repo / 'server/.local').mkdir()
        (self.repo / 'server/.local/hidden.py').write_text('SECRET = 123\n')
        self.root_patch = patch.object(code_lookup, 'APPROVED_REPOSITORY', self.repo)
        self.inventory_patch = patch.object(
            code_lookup, '_tracked_inventory',
            return_value=['server/alpha.py', 'server/beta.py', 'server/.local/hidden.py'],
        )
        self.root_patch.start()
        self.inventory_patch.start()
        self.addCleanup(self.root_patch.stop)
        self.addCleanup(self.inventory_patch.stop)
        self.index_path = self.repo / 'index.json'

    def test_exact_identifier_returns_real_six_line_span_and_excludes_local(self):
        # Break caught: wrong line slicing/hash, or reading .local as source.
        index = code_lookup.build_index(self.repo, self.index_path)
        result = code_lookup.lookup(code_lookup.load_index(self.index_path),
                                    'normalize_request', repo=self.repo)
        self.assertEqual(result['status'], 'ok')
        self.assertEqual([s['path'] for s in index['sources']],
                         ['server/alpha.py', 'server/beta.py'])
        item = result['results'][0]
        self.assertEqual((item['path'], item['start_line'], item['end_line']),
                         ('server/alpha.py', 1, 6))
        self.assertEqual(item['excerpt'], ALPHA)
        self.assertEqual(item['source_sha256'], hashlib.sha256(ALPHA.encode()).hexdigest())
        self.assertEqual(item['index_generation'], index['generation'])
        self.assertEqual(item['identifier_match_lines'], [5])
        self.assertLessEqual(result['shortlist_count'], 12)
        self.assertLessEqual(len(result['results']), 3)

    def test_changed_file_returns_stale_without_cached_excerpt(self):
        # Break caught: using indexed text after source bytes change.
        index = code_lookup.build_index(self.repo, self.index_path)
        (self.repo / 'server/alpha.py').write_bytes((ALPHA + '# changed\n').encode('utf-8'))
        result = code_lookup.lookup(index, 'normalize_request', repo=self.repo)
        self.assertEqual(result['status'], 'stale_index')
        self.assertEqual(result['results'], [])
        self.assertTrue(result['rebuild_required'])
        self.assertIn('server/alpha.py', result['stale_paths'])

    def test_ambiguous_identifier_and_no_match_are_explicit(self):
        # Break caught: presenting one shared identifier as a definitive answer.
        index = code_lookup.build_index(self.repo, self.index_path)
        result = code_lookup.lookup(index, 'resolve_profile', repo=self.repo)
        self.assertEqual(result['status'], 'ambiguous')
        self.assertEqual({r['path'] for r in result['results']},
                         {'server/alpha.py', 'server/beta.py'})
        missing = code_lookup.lookup(index, 'zzqv987654321', repo=self.repo)
        self.assertEqual(missing['status'], 'no_match')
        self.assertEqual(missing['results'], [])
        self.assertFalse(missing['main_model_called'])

    def test_provider_is_not_invoked_without_explicit_opt_in(self):
        # Break caught: semantic/provider work automatically starting on a lookup.
        class TrapProvider:
            def rerank(self, query, candidates):
                raise AssertionError('disabled provider invoked')
        index = code_lookup.build_index(self.repo, self.index_path)
        result = code_lookup.lookup(index, 'normalize_request', repo=self.repo,
                                    reranker=TrapProvider())
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['provider']['status'], 'disabled')
        self.assertFalse(result['main_model_called'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
