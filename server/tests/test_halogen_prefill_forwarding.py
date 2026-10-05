import pathlib,sys,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from controller import halogen_draft_arguments, validate_engine

class PrefillForwardingTests(unittest.TestCase):
    def test_combined_options_reach_launcher(self):
        self.assertEqual(halogen_draft_arguments({'draft_tokens':1,'prefill_chunk':8192}),
                         ['-DraftTokens','1','-PrefillChunk','8192'])
    def test_prefill_without_draft_override(self):
        self.assertEqual(halogen_draft_arguments({'prefill_chunk':4096}),['-PrefillChunk','4096'])
    def test_bad_chunk_is_not_silently_ignored(self):
        for value in (None,True,0,'8192',65536):
            with self.subTest(value=value),self.assertRaises(ValueError):
                halogen_draft_arguments({'prefill_chunk':value})
    def test_explicit_token_arena_limit_reaches_launcher(self):
        self.assertEqual(halogen_draft_arguments({'context':262144,'prefill_chunk':8192,
                                                'max_prefill_tokens':8192}),
                         ['-PrefillChunk','8192','-MaxPrefillTokens','8192'])
    def test_token_arena_limit_requires_bounded_matching_chunk(self):
        cases=({'max_prefill_tokens':8192},
               {'prefill_chunk':16384,'max_prefill_tokens':8192},
               {'context':4096,'prefill_chunk':4096,'max_prefill_tokens':8192})
        cases+=tuple({'prefill_chunk':8192,'max_prefill_tokens':value}
                     for value in (None,True,0,'8192',65536))
        for engine in cases:
            with self.subTest(engine=engine),self.assertRaises(ValueError):
                halogen_draft_arguments(engine)
    def test_token_arena_limit_requires_launcher_support(self):
        repo=pathlib.Path(__file__).resolve().parents[2]
        engine={'kind':'halogen','checkpoint':'v2','context':262144,
                'prefill_chunk':8192,'max_prefill_tokens':8192}
        for version in ('0.15.1','0.16.1'):
            with self.subTest(version=version),self.assertRaisesRegex(ValueError,'launcher'):
                validate_engine(engine|{'directory':'backends/halogen-wsl2-'+version},repo)
        self.assertEqual(validate_engine(engine|{'directory':'backends/halogen-wsl2-0.16.2'},repo),
                         repo/'backends/halogen-wsl2-0.16.2')
