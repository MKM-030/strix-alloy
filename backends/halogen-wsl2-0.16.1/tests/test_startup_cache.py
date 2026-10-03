"""No model/GPU tests for startup reclamation and precise safety diagnostics."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import service
import startup_cache as cache
from startup_monitor import StartupMonitor

RUN = 'a'*32

class StartupTests(unittest.TestCase):
    def test_low_memory_diagnostic_distinguishes_pressure_and_keeps_floor(self):
        f = {'available_bytes':11*2**30, 'commit_headroom_bytes':120*2**30}
        with self.assertRaisesRegex(ValueError, '11.000/120.000'):
            service.check_runtime_frame(f, .001)
        service.check_runtime_frame({**f,'available_bytes':12*2**30}, .1)

    def test_slow_sample_diagnostic_is_distinct(self):
        with self.assertRaisesRegex(ValueError,'too slow/stale'):
            service.check_runtime_frame({'available_bytes':40*2**30,'commit_headroom_bytes':120*2**30},2.1)

    def test_malformed_memory_is_not_silently_safe(self):
        for f in [{}, {'available_bytes':True,'commit_headroom_bytes':120*2**30}]:
            with self.assertRaises(ValueError): service.check_runtime_frame(f,.01)

    def test_engine_exit_exposes_guard_cause(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)
            (p/'guard-failure.json').write_text(json.dumps({'error':'physical 11.7 GiB'}))
            self.assertIn('physical 11.7 GiB',str(service.startup_exit_error(p)))

    def test_matching_stop_precedes_any_file_advice(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td); model=p/'model'; model.write_bytes(b'preserve')
            stop=p/'stop.json'; stop.write_text(json.dumps({'run_id':RUN}))
            rows=[]
            with patch.object(cache,'advise') as advice:
                self.assertEqual(cache.run(RUN,stop,10,paths=[model],emit=rows.append),0)
                advice.assert_not_called()
            self.assertEqual(rows[-1]['event'],'stopped')
            self.assertEqual(model.read_bytes(),b'preserve')

    def test_wrong_stop_does_not_accept_some_other_run(self):
        with tempfile.TemporaryDirectory() as td:
            stop=Path(td)/'stop'; stop.write_text(json.dumps({'run_id':'b'*32}))
            with self.assertRaises(ValueError): cache.run(RUN,stop,10,paths=[],emit=lambda _:None)

    def test_independent_worker_measures_every_interval_then_acknowledges(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td); model=p/'model'; model.write_bytes(b'no writes')
            stop=p/'stop'; clock=[0.0]; rows=[]
            def sleep(dt):
                clock[0]+=dt
                if clock[0]>=3: stop.write_text(json.dumps({'run_id':RUN}))
            with patch.object(cache,'advise') as advice:
                self.assertEqual(cache.run(RUN,stop,20,paths=[model],clock=lambda:clock[0],
                    sleep=sleep,emit=rows.append,snapshot=lambda:{'Cached':100}),0)
                self.assertEqual(advice.call_count,3)
            self.assertEqual([r['event'] for r in rows],['advice']*3+['stopped'])
            self.assertEqual(model.read_bytes(),b'no writes')

    def test_worker_deadline_does_not_leave_running_loop(self):
        clock=[0.0]
        def advance(dt): clock[0]+=dt
        with tempfile.TemporaryDirectory() as td, patch.object(cache,'advise'):
            with self.assertRaises(TimeoutError):
                cache.run(RUN,Path(td)/'absent',3,paths=[],clock=lambda:clock[0],
                    sleep=advance,emit=lambda _:None,snapshot=lambda:{})
        self.assertEqual(clock[0],3)

    def test_client_inference_requires_worker_exit_and_ack(self):
        m=StartupMonitor.__new__(StartupMonitor)
        m.attempt=Path('.'); m.run_id=RUN; m.publish=Mock(); m.failure=None
        m.process=Mock(); m.process.wait.return_value=0
        m.thread=Mock(); m.thread.is_alive.return_value=False
        m.last_record={'event':'advice'}
        with self.assertRaisesRegex(RuntimeError,'acknowledgement'): m.stop()
        m.last_record={'event':'stopped'}; m.stop()
        m.process.wait.assert_called_with(timeout=12)

    @unittest.skipUnless(os.name=='posix','Linux file-cache API')
    def test_actual_fadvise_retains_file_bytes(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'file'; data=b'x'*65536; p.write_bytes(data)
            fd=os.open(p,os.O_RDONLY)
            try: cache.advise([fd])
            finally: os.close(fd)
            self.assertEqual(p.read_bytes(),data)

if __name__=='__main__': unittest.main()
