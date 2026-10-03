import pathlib,sys,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from controller import halogen_draft_arguments, validate_engine
from draft_profiles import tune

class Halogen0161ControlsTests(unittest.TestCase):
    def test_prefill_keep_trunk_and_admit_ticks_forward(self):
        args=halogen_draft_arguments({'checkpoint':'v2','context':262144,'draft_tokens':2,'prefill_chunk':16384,
                                      'prefill_keep_trunk':True,'admit_ticks':8})
        self.assertEqual(args,['-DraftTokens','2','-PrefillChunk','16384','-AdmitTicks','8','-PrefillKeepTrunk'])
    def test_larger_upstream_prefill_chunk_is_bounded_by_context(self):
        self.assertIn('32768',halogen_draft_arguments({'context':262144,'prefill_chunk':32768}))
        with self.assertRaises(ValueError):
            halogen_draft_arguments({'context':16384,'prefill_chunk':32768})
    def test_invalid_boolean_or_ticks_fail_closed(self):
        for engine in ({'prefill_keep_trunk':False},{'admit_ticks':0},{'admit_ticks':True}):
            with self.subTest(engine=engine),self.assertRaises(ValueError):
                halogen_draft_arguments(engine)

class ManagedHalogenControlValidationTests(unittest.TestCase):
    repo=pathlib.Path(__file__).resolve().parents[2]

    def engine(self,version='0.16.2',checkpoint='v2'):
        return {'kind':'halogen','directory':'backends/halogen-wsl2-'+version,
                'checkpoint':checkpoint,'context':262144}

    def profile(self,version='0.16.2',checkpoint='v2'):
        return {'backend':{'identifier':'halogen-'+checkpoint,'context':262144},
                'engine':self.engine(version,checkpoint)}

    def test_w4b_keep_trunk_is_rejected_before_launch(self):
        engine=self.engine(checkpoint='w4b'); engine['prefill_keep_trunk']=True
        with self.assertRaisesRegex(ValueError,'v2'):
            validate_engine(engine,self.repo)

    def test_w4b_keep_trunk_profile_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'v2'):
            tune(self.profile(checkpoint='w4b'),draft_tokens=1,prefill_keep_trunk=True)

    def test_legacy_launcher_rejects_new_controls_before_launch(self):
        for option in ({'prefill_chunk':16384},{'prefill_chunk':32768},
                       {'prefill_keep_trunk':True},{'admit_ticks':8}):
            with self.subTest(option=option),self.assertRaisesRegex(ValueError,'launcher'):
                validate_engine(self.engine('0.15.1')|option,self.repo)

    def test_legacy_profile_rejects_new_controls(self):
        for option in ({'prefill_chunk':16384},{'prefill_chunk':32768},
                       {'prefill_keep_trunk':True},{'admit_ticks':8}):
            with self.subTest(option=option),self.assertRaisesRegex(ValueError,'launcher'):
                tune(self.profile('0.15.1'),draft_tokens=1,**option)

    def test_supported_launchers_keep_new_controls(self):
        for version in ('0.16.1','0.16.2'):
            with self.subTest(version=version):
                result=tune(self.profile(version),draft_tokens=2,prefill_chunk=32768,
                            prefill_keep_trunk=True,admit_ticks=8)
                self.assertEqual(result['engine']['prefill_chunk'],32768)
                self.assertIs(result['engine']['prefill_keep_trunk'],True)
                self.assertEqual(result['engine']['admit_ticks'],8)
                self.assertEqual(validate_engine(result['engine'],self.repo),
                                 self.repo/('backends/halogen-wsl2-'+version))

    def test_legacy_supported_controls_remain_usable(self):
        result=tune(self.profile('0.15.1'),draft_tokens=1,prefill_chunk=8192)
        self.assertEqual(validate_engine(result['engine'],self.repo),
                         self.repo/'backends/halogen-wsl2-0.15.1')
