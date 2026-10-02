import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from article_metrics import validate_geometry

class GeometryTests(unittest.TestCase):
    def test_article_shapes_are_valid(self):
        for context,fill in [(65536,32768),(131072,65536),(131072,98304),(262144,131072)]:
            validate_geometry(context,fill,2,1536)
    def test_history_must_fit_without_automatic_truncation(self):
        with self.assertRaises(ValueError):validate_geometry(65536,64000,2,1536)
    def test_invalid_repetition_count_is_refused(self):
        with self.assertRaises(ValueError):validate_geometry(65536,32768,0,1536)
if __name__=='__main__':unittest.main()
