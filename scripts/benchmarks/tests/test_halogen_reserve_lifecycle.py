import json,pathlib,sys,tempfile,types,unittest
from unittest.mock import patch
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import halogen_reserve_watch as watch
class MonitorLifecycleTests(unittest.TestCase):
    def exercise(self, failure=False):
        with tempfile.TemporaryDirectory() as folder:
            root=pathlib.Path(folder);statefile=root/'server/.local/current.json'
            statefile.parent.mkdir(parents=True);statefile.write_text('{}')
            state={'backend':'halogen-v2','phase':'starting','run_id':'owned-run','heartbeat':0}
            calls=[];values=iter([25,17.5,30])
            def available():
                if failure and calls:raise OSError('telemetry unavailable')
                value=next(values);calls.append(('sample',value));return value
            def atomic(path,value):calls.append(('stop',str(path),value));state['phase']='stopped'
            fake=types.SimpleNamespace(available_gib=available,read=lambda _:dict(state),atomic=atomic)
            args=['watch','--repo',str(root),'--out',str(root/'out')]
            with patch.dict(sys.modules,{'controller':fake}),patch.object(sys,'argv',args),patch.object(watch.time,'sleep'):
                if failure:
                    with self.assertRaises(OSError):watch.main()
                else:self.assertEqual(watch.main(),0)
            if not failure:self.assertEqual(calls[:2],[('sample',25),('sample',17.5)])
            stops=[c for c in calls if c[0]=='stop']
            self.assertEqual(len(stops),1)
            self.assertEqual(stops[0][2],{'run_id':'owned-run'})
    def test_stop_uses_owned_run_and_memory_not_stale_startup_clock(self):self.exercise()
    def test_telemetry_failure_requests_owned_cleanup(self):self.exercise(True)
if __name__=='__main__':unittest.main()
