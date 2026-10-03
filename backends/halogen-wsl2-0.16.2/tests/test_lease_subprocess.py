"""Linux CPU-only supervisor lifecycle fixtures; no Docker, GPU or model."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest

SCRIPTS=Path(__file__).resolve().parents[1]/"scripts"
RUN="d"*32

@unittest.skipUnless(sys.platform=="linux", "Linux process-group fixture; run explicitly in WSL")
class SupervisorProcessTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix="strix-lease-cpu-")
        self.path=Path(self.tmp.name); self.process=None; self.seq=0
        self.write(9000000000)

    def tearDown(self):
        if self.process is not None and self.process.poll() is None:
            self.process.send_signal(signal.SIGTERM)
            self.process.wait(timeout=15)
        if self.process is not None:
            self.process.stdout.close()
        self.tmp.cleanup()

    def write(self,stamp):
        self.seq+=1
        stage=self.path/"stage"
        stage.write_text(json.dumps({"schema":2,"run_id":RUN,"sequence":self.seq,"time":stamp}))
        os.replace(stage,self.path/"lease.json")

    def launch(self):
        # Shorten time only inside this CPU fixture process, never in production.
        bootstrap="import sys; sys.path.insert(0,sys.argv.pop(1)); import lease_supervisor as m; m.LEASE_AGE=2; raise SystemExit(m.main())"
        child="import os,time; from pathlib import Path; Path("+repr(str(self.path/"child.pid"))+").write_text(str(os.getpid())); time.sleep(60)"
        self.process=subprocess.Popen([sys.executable,"-u","-c",bootstrap,str(SCRIPTS),
            "--lease",str(self.path/"lease.json"),"--run-id",RUN,sys.executable,"-c",child],
            stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)

    def wait_child(self):
        end=time.monotonic()+5
        while not (self.path/"child.pid").exists():
            if self.process.poll() is not None or time.monotonic()>end:
                self.fail("supervisor did not start fixture child")
            self.write(-9000000000 if self.seq%2 else 9000000000)
            time.sleep(.1)
        return int((self.path/"child.pid").read_text())

    def assert_child_gone(self,pid):
        with self.assertRaises(ProcessLookupError): os.kill(pid,0)

    def test_stale_static_file_never_launches_child(self):
        self.launch()
        output,_=self.process.communicate(timeout=8)
        self.assertEqual(self.process.returncode,2,output)
        self.assertFalse((self.path/"child.pid").exists())

    def test_clock_skew_progress_runs_then_missing_writer_stops_owned_child(self):
        self.launch(); pid=self.wait_child()
        end=time.monotonic()+3
        while time.monotonic()<end:
            self.write(-9000000000 if self.seq%2 else 9000000000)
            self.assertIsNone(self.process.poll()); time.sleep(.1)
        output,_=self.process.communicate(timeout=8)
        self.assertEqual(self.process.returncode,2,output)
        self.assertIn("Guard progress confirmed",output)
        self.assertIn("stopping owned engine",output)
        self.assert_child_gone(pid)

    def test_brief_unreadable_file_does_not_renew_but_can_recover(self):
        self.launch(); pid=self.wait_child()
        (self.path/"lease.json").unlink(); time.sleep(.4)
        end=time.monotonic()+3
        while time.monotonic()<end:
            self.write(0); time.sleep(.1); self.assertIsNone(self.process.poll())
        self.process.send_signal(signal.SIGTERM)
        self.process.communicate(timeout=15)
        self.assert_child_gone(pid)

if __name__=="__main__": unittest.main()
