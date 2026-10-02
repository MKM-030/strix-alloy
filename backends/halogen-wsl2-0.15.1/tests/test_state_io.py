import errno
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from state_io import read_json

class StateReadTests(unittest.TestCase):
    def test_transient_permission_read_preserves_original_timestamp(self):
        calls=[]
        def load():
            calls.append(1)
            if len(calls)==1: raise PermissionError(errno.EACCES, 'busy')
            return '{"run_id":"old","time":123}'
        result=read_json('unused',load=load,windows=True,sleep=lambda _:None)
        self.assertEqual(result, {'run_id':'old','time':123})
        self.assertEqual(len(calls),2)

    def test_permanent_denial_is_bounded(self):
        now=[0.0]
        def load(): raise PermissionError(errno.EACCES,'busy')
        def sleep(seconds): now[0]+=seconds
        with self.assertRaises(PermissionError):
            read_json('unused',budget=.1,windows=True,load=load,
                      clock=lambda:now[0],sleep=sleep)
        self.assertAlmostEqual(now[0],.1)
    def test_missing_or_malformed_state_is_not_retried(self):
        for error in [FileNotFoundError(), OSError(errno.EIO,'disk failure')]:
            calls=[]
            def load(): calls.append(1); raise error
            with self.assertRaises(type(error)):
                read_json('unused',load=load,windows=True)
            self.assertEqual(len(calls),1)
        with self.assertRaises(json.JSONDecodeError):
            read_json('unused',load=lambda:'{',windows=True)

    def test_nonwindows_permission_failure_is_immediate(self):
        def load(): raise PermissionError(errno.EACCES,'denied')
        def never(_): self.fail('Unexpected retry')
        with self.assertRaises(PermissionError):
            read_json('unused',load=load,windows=False,sleep=never)

    def test_excessive_budget_refused(self):
        with self.assertRaises(ValueError): read_json('unused',budget=45)

if __name__=='__main__': unittest.main()
