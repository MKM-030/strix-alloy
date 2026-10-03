import copy, pathlib, sys, unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import draft_profiles as p

class PrefillLookupTests(unittest.TestCase):
    def profile(self, kind='halogen'):
        if kind=='halogen':
            return {'backend':{'identifier':'halogen-v2','context':262144},
                    'engine':{'kind':'halogen','checkpoint':'v2'}}
        return {'backend':{'identifier':'gufo-flash-next','context':262144},
                'engine':{'kind':'native','qualified':True,'executable_sha256':'pinned',
                 'command':['gufo.exe','serve','llm','--mtp-model','head.gguf',
                            '--speculative','mtp','--prefill-chunk','2048']}}
    def tune(self, source, **options):
        try: return p.tune(source,draft_tokens=1,**options)
        except TypeError as e: self.fail('Tuning parameters missing: '+str(e))
    def test_halogen_chunk_is_explicit_and_source_unchanged(self):
        source=self.profile(); before=copy.deepcopy(source)
        result=self.tune(source,prefill_chunk=8192)
        self.assertEqual(source,before)
        self.assertEqual(result['engine']['prefill_chunk'],8192)
        self.assertEqual(result['minimum_reserve_gib'],18)
    def test_gufo_lookup_and_prefill_use_supported_switches(self):
        result=self.tune(self.profile('gufo'),prefill_chunk=4096,prompt_lookup=True)
        args=result['engine']['command']
        self.assertEqual(args[args.index('--prefill-chunk')+1],'4096')
        self.assertEqual(args.count('--prompt-lookup'),1)
        self.assertEqual(result['engine']['executable_sha256'],'pinned')
    def test_gufo_disk_cache_is_isolated_and_bounded(self):
        root=pathlib.Path(__file__).resolve().parents[2]
        cache=root/'server/.local/gufo-candidate-cache'
        result=self.tune(self.profile('gufo'),cache_disk=cache)
        args=result['engine']['command']
        self.assertEqual(args[args.index('--cache-disk')+1],str(cache))
        self.assertEqual(args[args.index('--cache-disk-staging-bytes')+1],'4294967296')
        self.assertEqual(result['minimum_reserve_gib'],18)
        with self.assertRaises(ValueError):self.tune(self.profile(),cache_disk=cache)
        with self.assertRaises(ValueError):self.tune(self.profile('gufo'),cache_disk=root/'docs')
    def test_lookup_absent_preserved_and_explicit_disable(self):
        source=self.profile('gufo'); source['engine']['command']+=['--prompt-lookup']
        self.assertIn('--prompt-lookup',self.tune(source)['engine']['command'])
        self.assertNotIn('--prompt-lookup',self.tune(source,prompt_lookup=False)['engine']['command'])
    def test_bad_values_and_backend_confusion_rejected(self):
        for value in (0, True, 1.5, '8192', 65536):
            with self.subTest(value=value),self.assertRaises(ValueError):
                self.tune(self.profile(),prefill_chunk=value)
        source=self.profile(); source['backend']['context']=4096
        with self.assertRaises(ValueError): self.tune(source,prefill_chunk=8192)
        with self.assertRaises(ValueError): self.tune(self.profile(),prompt_lookup=True)
        with self.assertRaises(ValueError): self.tune(self.profile('gufo'),prompt_lookup=1)
    def test_default_does_not_invent_prefill_override(self):
        self.assertNotIn('prefill_chunk',self.tune(self.profile())['engine'])
