import pathlib
import sys
import unittest

sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from prepare_gateway_prompts import build_prompt


class Tokenizer:
    def encode(self,text,add_special_tokens=False):
        return type('Encoding',(),{'ids':text.split()})()
    def decode(self,ids,skip_special_tokens=False):
        return ' '.join(ids)


class PromptTests(unittest.TestCase):
    def test_deterministic_prose_under_chat_headroom(self):
        tokenizer=Tokenizer()
        for size in (512,2048,8192,16384):
            first=build_prompt(size,tokenizer)
            self.assertEqual(first,build_prompt(size,tokenizer))
            self.assertLessEqual(len(tokenizer.encode(first).ids),size-128)
            self.assertIn('story',first)

    def test_unreviewed_size_rejected(self):
        with self.assertRaises(ValueError):build_prompt(1024,Tokenizer())

if __name__=='__main__':unittest.main()
