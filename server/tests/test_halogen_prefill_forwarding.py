import pathlib,sys,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from controller import halogen_draft_arguments

class PrefillForwardingTests(unittest.TestCase):
    def test_combined_options_reach_launcher(self):
        self.assertEqual(halogen_draft_arguments({'draft_tokens':1,'prefill_chunk':8192}),
                         ['-DraftTokens','1','-PrefillChunk','8192'])
    def test_prefill_without_draft_override(self):
        self.assertEqual(halogen_draft_arguments({'prefill_chunk':4096}),['-PrefillChunk','4096'])
    def test_bad_chunk_is_not_silently_ignored(self):
        for value in (None,True,0,'8192',16384):
            with self.subTest(value=value),self.assertRaises(ValueError):
                halogen_draft_arguments({'prefill_chunk':value})
