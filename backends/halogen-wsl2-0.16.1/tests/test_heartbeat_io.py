"""Regression tests for the Windows heartbeat replacement failure. No model starts."""
import ctypes
import errno
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch, Mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"scripts"))
import service as s

def denied(code=5):
    exc=PermissionError(errno.EACCES, "simulated Windows sharing conflict")
    exc.winerror=code
    return exc

class AtomicHeartbeatTests(unittest.TestCase):
    def test_transient_windows_conflict_retries_same_complete_payload(self):
        for code in (5,32,33):
            with self.subTest(winerror=code), tempfile.TemporaryDirectory() as td:
                path=Path(td)/"lease.json"
                old={"run_id":"r","time":100}; new={"run_id":"r","time":101}
                s.atomic(path,old); real_replace=os.replace; seen=[]
                def replace(src,dst):
                    seen.append(json.loads(Path(src).read_text()))
                    self.assertEqual(s.read(path),old)
                    if len(seen)<3: raise denied(code)
                    return real_replace(src,dst)
                with patch.object(s.os,"replace",side_effect=replace):
                    s.atomic(path,new)
                self.assertEqual(seen,[new,new,new])
                self.assertEqual(s.read(path),new)
                self.assertEqual(list(Path(td).iterdir()),[path])

    def test_permanent_windows_conflict_is_bounded_and_preserves_old_lease(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/"lease.json"; s.atomic(path,{"time":100})
            clock=[0.0]
            def advance(seconds): clock[0]+=seconds
            with patch.object(s.os,"replace",side_effect=denied()), patch.object(s.time,"monotonic",side_effect=lambda:clock[0]), patch.object(s.time,"sleep",side_effect=advance):
                with self.assertRaises(PermissionError): s.atomic(path,{"time":200})
            self.assertGreaterEqual(clock[0],1.5)
            self.assertLessEqual(clock[0],2.01)
            self.assertEqual(s.read(path),{"time":100})
            self.assertEqual(list(Path(td).iterdir()),[path])

    def test_other_io_errors_are_not_retried(self):
        for exc in (OSError(errno.ENOSPC,"disk full"), denied(87), PermissionError(errno.EACCES,"not a Windows sharing code")):
            with self.subTest(error=str(exc)), tempfile.TemporaryDirectory() as td:
                path=Path(td)/"lease.json"; s.atomic(path,{"time":100})
                with patch.object(s.os,"replace",side_effect=exc) as replace, patch.object(s.time,"sleep") as sleep:
                    with self.assertRaises(OSError): s.atomic(path,{"time":200})
                    self.assertEqual(replace.call_count,1); sleep.assert_not_called()
                self.assertEqual(s.read(path),{"time":100})
                self.assertEqual(list(Path(td).iterdir()),[path])

    def test_serialization_failure_does_not_damage_previous_lease(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/"lease.json"; s.atomic(path,{"time":100})
            with self.assertRaises(TypeError): s.atomic(path,{"invalid":object()})
            self.assertEqual(s.read(path),{"time":100})
            self.assertEqual(list(Path(td).iterdir()),[path])

    @unittest.skipUnless(os.name=="nt","Real Windows sharing semantics")
    def test_real_open_reader_blocks_rename_then_recovers(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/"lease.json"; s.atomic(path,{"time":100})
            candidate=Path(td)/"probe.tmp"; candidate.write_text("probe")
            reader=path.open("rb")
            try:
                with self.assertRaises(OSError) as found: os.replace(candidate,path)
                self.assertIn(found.exception.winerror,(5,32,33))
                timer=threading.Timer(.15,reader.close); timer.start()
                try: s.atomic(path,{"time":101})
                finally: timer.join(timeout=2)
                self.assertEqual(s.read(path),{"time":101})
            finally:
                reader.close(); candidate.unlink(missing_ok=True)

class GuardDiagnosticTests(unittest.TestCase):
    def test_root_guard_failure_reaches_controller_error(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td); s.atomic(path/"guard-failure.json",{"error":"WinError 5 replacing lease.json"})
            with patch.object(s.r,"guard_alive",side_effect=RuntimeError("independent guard missing/stale/dead")):
                with self.assertRaisesRegex(RuntimeError,"WinError 5 replacing lease.json"):
                    s.guard_alive(Mock(),path)

    def test_guard_report_failure_cannot_skip_owned_shutdown(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td); s.atomic(path/"manifest.json",{"sources":{},"run_id":"r"}); s.atomic(path/"container.json",{"id":"a"*64})
            with patch.object(s,"logger",return_value=Mock()), patch.object(s.r,"configure"), patch.object(s,"source_hashes",return_value={}), patch.object(s.r,"inspect",return_value={}), patch.object(s,"owned",side_effect=ValueError("invalid guard target")), patch.object(s,"atomic",side_effect=OSError("cannot write diagnostics")), patch.object(s,"stop_owned") as stop:
                with patch("builtins.print"):
                    self.assertEqual(s.guard(path),2)
                stop.assert_called_once_with("a"*64,{"sources":{},"run_id":"r"})

if __name__=="__main__": unittest.main()
