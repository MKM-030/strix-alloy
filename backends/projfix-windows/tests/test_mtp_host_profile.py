import hashlib, pathlib, sys, tempfile, unittest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from profile import make_profile

class MtpHostProfileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)
        self.runtime = self.root / 'runtime'
        self.runtime.mkdir()
        (self.runtime / 'llama-server.exe').write_bytes(b'fixture')
        (self.root / 'target.gguf').write_bytes(b'GGUF')
        (self.root / 'draft.gguf').write_bytes(b'GGUF')
        self.token = self.root / 'test-token.txt'
        self.token.write_text('fixture-not-an-api-key')
        self.pins = {'runtime_files': {'llama-server.exe':
                     hashlib.sha256(b'fixture').hexdigest()}, 'sdk_runtime': 'fixture',
                     'target': 'target.gguf', 'draft': 'draft.gguf',
                     'model_files': {'target.gguf': 4, 'draft.gguf': 4}}

    def make(self):
        return make_profile(self.runtime, self.root, self.token,
                            32768, self.pins, 'mtp-host')

    def test_mtp_host_requires_the_draft_file(self):
        (self.root / 'draft.gguf').unlink()
        with self.assertRaises(ValueError):
            self.make()

    def test_mtp_host_metadata_is_not_legacy_or_silently_qualified_for_speed(self):
        value = self.make()
        self.assertEqual(value['qualification']['placement'], 'pinned-host-experts-0-17')
        self.assertEqual(value['qualification']['decoding_mode'], 'mtp-host')
        self.assertTrue(value['qualification'].get('experimental'))
        self.assertNotIn('fixture-not-an-api-key', str(value))
        self.assertIn('--tensor-split', value['engine']['command'])

    def test_candidate_points_to_its_own_evidence(self):
        value = self.make()
        self.assertEqual(value['qualification']['source'],
                         'docs/research/mtp-host-implementation-20261001.md')

    def test_candidate_requests_stricter_memory_reserve(self):
        self.assertEqual(self.make().get('minimum_reserve_gib'), 18)
