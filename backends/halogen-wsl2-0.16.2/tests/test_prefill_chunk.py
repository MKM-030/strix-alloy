import pathlib, sys, tempfile, unittest
from types import SimpleNamespace
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'scripts'))
import service as s

class PrefillChunkTests(unittest.TestCase):
    def env(self,value):
        try: return s.environment(262144,'v2','Off',draft_tokens=1,prefill_chunk=value)
        except TypeError as exc: self.fail('Prefill option missing: '+str(exc))
    def test_matching_chunk_and_scratch_limit(self):
        for value in (2048,4096,8192,16384,32768):
            env=self.env(value)
            self.assertEqual(env['HALOGEN_PREFILL_CHUNK'],str(value))
            self.assertGreaterEqual(int(env['HALOGEN_MAX_TOK']),value)
            self.assertEqual(env['HALOGEN_MTP_DEPTH'],'1')
            self.assertEqual(env['HALOGEN_PROMPT_CACHE'],'0')
    def test_default_environment_preserved(self):
        self.assertEqual(self.env(None),s.environment(262144,'v2','Off',draft_tokens=1))
    def test_chunk_ablation_retains_stock_32k_token_arena(self):
        for value in (8192,16384,32768):
            with self.subTest(chunk=value):
                env=s.environment(262144,'v2','Off',prefill_chunk=value)
                self.assertEqual(env['HALOGEN_PREFILL_CHUNK'],str(value))
                self.assertEqual(env['HALOGEN_MAX_TOK'],'32768')
    def test_bad_chunk_refused(self):
        for value in (0,True,'4096',1.5,65536):
            with self.subTest(value=value),self.assertRaises(ValueError): self.env(value)
    def test_cli_rejects_chunk_larger_than_context(self):
        with self.assertRaises((ValueError,SystemExit)):
            s.options(['--context-size','4096','--prefill-chunk','8192'])
    def test_explicit_token_arena_limit_preserves_full_context_and_reserve(self):
        try:
            env=s.environment(262144,'v2','Off',draft_tokens=2,prefill_chunk=8192,
                              max_prefill_tokens=8192)
        except TypeError as exc: self.fail('Token arena option missing: '+str(exc))
        self.assertEqual(env['HALOGEN_MAX_TOK'],'8192')
        self.assertEqual(env['HALOGEN_PREFILL_CHUNK'],'8192')
        self.assertEqual(env['HALOGEN_CTX'],'262144')
        self.assertEqual(env['HALOGEN_KV_POOL_POSITIONS'],'262144')
        self.assertEqual(env['HALOGEN_HOST_RESERVE_GIB'],'18')
    def test_token_arena_rejects_missing_chunk_and_out_of_bounds_limits(self):
        cases=({'max_prefill_tokens':8192},
               {'prefill_chunk':16384,'max_prefill_tokens':8192},
               {'prefill_chunk':4096,'max_prefill_tokens':8192,'context':4096})
        cases+=tuple({'prefill_chunk':8192,'max_prefill_tokens':value}
                     for value in (True,0,'8192',65536))
        for case in cases:
            context=case.get('context',262144)
            controls={key:value for key,value in case.items() if key!='context'}
            with self.subTest(case=case):
                try:
                    with self.assertRaises(ValueError): s.environment(context,'v2','Off',**controls)
                except TypeError as exc: self.fail('Token arena validation missing: '+str(exc))
    def test_cli_accepts_explicit_token_arena_and_refuses_invalid_pairs(self):
        try:
            o=s.options(['--context-size','262144','--prefill-chunk','8192',
                         '--max-prefill-tokens','8192'])
        except SystemExit as exc: self.fail('Token arena CLI missing: '+str(exc))
        self.assertEqual(o.max_prefill_tokens,8192)
        for flags in (['--max-prefill-tokens','8192'],
                      ['--prefill-chunk','16384','--max-prefill-tokens','8192'],
                      ['--context-size','4096','--prefill-chunk','4096','--max-prefill-tokens','8192']):
            with self.subTest(flags=flags),self.assertRaises(ValueError): s.options(flags)
    def test_explicit_token_arena_reaches_recorded_container_environment(self):
        options=SimpleNamespace(context_size=262144,checkpoint='v2',serve_seconds=0,
                                startup_timeout=900,prefill_chunk=8192,max_prefill_tokens=8192)
        with tempfile.TemporaryDirectory() as directory:
            attempt=pathlib.Path(directory)
            (attempt/'entrypoint-service.sh').write_text('# test entrypoint',encoding='utf-8')
            manifest=s.build_manifest(options,attempt,'a'*32)
        self.assertEqual(manifest['environment']['HALOGEN_MAX_TOK'],'8192')
