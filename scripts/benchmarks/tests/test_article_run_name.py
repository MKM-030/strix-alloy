import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import article_metrics as m
class RunNameTests(unittest.TestCase):
    def test_retry_uses_a_new_evidence_directory(self):
        self.assertEqual(m.cell_name('halogen-v2',65536,32768,'ready-confirmed'),'halogen-v2-c65536-p32768-ready-confirmed')
    def test_default_keeps_existing_names(self):
        self.assertEqual(m.cell_name('gufo',65536,32768,''),'gufo-c65536-p32768')
    def test_path_traversal_tag_is_rejected(self):
        with self.assertRaises(ValueError):m.cell_name('gufo',65536,32768,'../overwrite')
if __name__=='__main__':unittest.main()
