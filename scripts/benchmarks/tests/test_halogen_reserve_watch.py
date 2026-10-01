import math,pathlib,sys,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from halogen_reserve_watch import below_reserve
class ReserveWatchTests(unittest.TestCase):
    def test_two_gib_stop_margin(self):
        self.assertFalse(below_reserve(18))
        self.assertTrue(below_reserve(17.99))
        self.assertTrue(below_reserve(16))
    def test_invalid_telemetry_is_not_a_healthy_sample(self):
        for value in (None,True,'40',-1,math.nan,math.inf):
            with self.subTest(value=value),self.assertRaises(ValueError):below_reserve(value)
if __name__=='__main__':unittest.main()
