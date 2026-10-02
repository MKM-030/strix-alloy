import copy,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from prepare_native_profile import resized_profile
class NativeProfileTests(unittest.TestCase):
    def fixture(self):
        return {'schema':1,'backend':{'identifier':'gufo-flash-next','context':262144},
                'engine':{'kind':'native','qualified':True,'command':['gufo.exe','serve','--context','262144'],
                          'executable_sha256':'retained','runtime_hashes':{'HIP':'same'}},
                'token_file':'existing-token-path'}
    def test_resizes_only_the_selected_profile_copy(self):
        original=self.fixture();before=copy.deepcopy(original)
        result=resized_profile(original,65536)
        self.assertEqual(original,before)
        self.assertEqual(result['backend']['context'],65536)
        self.assertEqual(result['engine']['command'][-1],'65536')
        self.assertEqual(result['engine']['runtime_hashes'],before['engine']['runtime_hashes'])
    def test_unqualified_native_is_not_promoted(self):
        value=self.fixture();value['engine']['qualified']=False
        with self.assertRaises(ValueError):resized_profile(value,65536)
    def test_ambiguous_or_mismatched_context_is_rejected(self):
        for command in (['gufo.exe','--context','32768'],['gufo.exe','--context','262144','-c','262144']):
            value=self.fixture();value['engine']['command']=command
            with self.assertRaises(ValueError):resized_profile(value,65536)
    def test_unavailable_capacity_is_rejected(self):
        with self.assertRaises(ValueError):resized_profile(self.fixture(),1048576)
if __name__=='__main__':unittest.main()
