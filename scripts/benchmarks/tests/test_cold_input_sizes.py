import pathlib,sys,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import article_metrics
class InputSizesTests(unittest.TestCase):
    def test_reviewed_sizes_fit_with_output_room(self):
        fn=getattr(article_metrics,'benchmark_input_sizes',None)
        self.assertIsNotNone(fn)
        self.assertEqual(fn([512,2048,8192],262144),(512,2048,8192))
    def test_invalid_sizes_refused(self):
        fn=getattr(article_metrics,'benchmark_input_sizes',None)
        self.assertIsNotNone(fn)
        for values in ([],[True],[512,512],[262144],[0],[-1],[4097]):
            with self.subTest(values=values),self.assertRaises(ValueError):fn(values,262144)
if __name__=='__main__':unittest.main()
