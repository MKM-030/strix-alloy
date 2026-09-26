import ctypes as C
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from gufo_control.winjob import OwnedProcess


def _await_file(path, seconds=5):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if path.exists():
            return path.read_text()
        time.sleep(0.02)
    raise AssertionError(f"child did not write {path}")


def _observer(pid):
    kernel = C.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [C.c_ulong, C.c_int, C.c_ulong]
    kernel.OpenProcess.restype = C.c_void_p
    kernel.WaitForSingleObject.argtypes = [C.c_void_p, C.c_ulong]
    kernel.WaitForSingleObject.restype = C.c_ulong
    kernel.CloseHandle.argtypes = [C.c_void_p]
    kernel.CloseHandle.restype = C.c_int
    handle = kernel.OpenProcess(0x100000, False, pid)
    if not handle:
        raise C.WinError(C.get_last_error())
    return kernel, handle


@unittest.skipUnless(os.name == "nt", "Windows lifecycle qualification")
class WinJobTests(unittest.TestCase):
    def launch(self, code, *args, cwd):
        return OwnedProcess([sys.executable, "-c", code, *map(str, args)],
                            cwd=cwd, env=dict(os.environ))

    def test_suspended_until_resume_then_clean_exit(self):
        with tempfile.TemporaryDirectory() as folder:
            marker = Path(folder) / "ran.txt"
            with self.launch("from pathlib import Path; import sys; Path(sys.argv[1]).write_text('ok')",
                             marker, cwd=folder) as child:
                self.assertFalse(child.wait(100))
                self.assertFalse(marker.exists())
                self.assertGreater(child.identity["pid"], 0)
                self.assertGreater(child.identity["creation_time_100ns"], 0)
                self.assertEqual(Path(child.identity["executable"]).resolve(), Path(sys.executable).resolve())
                json.dumps(child.identity)
                child.resume()
                self.assertTrue(child.wait(5000))
                self.assertEqual(marker.read_text(), "ok")

    def test_close_kills_running_child_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as folder:
            child = self.launch("import time; time.sleep(60)", cwd=folder)
            try:
                child.resume()
                self.assertFalse(child.wait(50))
                child.close(5000)
                child.close()
                with self.assertRaises(RuntimeError):
                    child.wait()
                with self.assertRaises(RuntimeError):
                    child.resume()
            finally:
                child.close(5000)

    def test_unresumed_close(self):
        with tempfile.TemporaryDirectory() as folder:
            marker = Path(folder) / "ran.txt"
            child = self.launch("from pathlib import Path; import sys; Path(sys.argv[1]).touch()",
                                marker, cwd=folder)
            try:
                child.close()
                self.assertFalse(marker.exists())
            finally:
                child.close(5000)

    def test_quoting_and_environment(self):
        with tempfile.TemporaryDirectory() as folder:
            marker = Path(folder) / "quoted output.json"
            code = ("import json,os,sys; from pathlib import Path; "
                    "Path(sys.argv[1]).write_text(json.dumps([sys.argv[2],os.environ['GUFO_TEST_VALUE']]))")
            env = dict(os.environ, GUFO_TEST_VALUE='a b "c"')
            with OwnedProcess([sys.executable, "-c", code, str(marker), 'space "quote" \\ tail'],
                              cwd=folder, env=env) as child:
                child.resume()
                self.assertTrue(child.wait(5000))
            self.assertEqual(json.loads(marker.read_text()), ['space "quote" \\ tail', 'a b "c"'])

    def test_bad_inputs_and_resume_twice(self):
        with tempfile.TemporaryDirectory() as folder:
            for argv in ([], ["bad\0path"], "not a list"):
                with self.subTest(argv=argv), self.assertRaises(ValueError):
                    OwnedProcess(argv, cwd=folder, env={})
            for env in ({"BAD=KEY": "x"}, {"X": "bad\0value"}):
                with self.subTest(env=env), self.assertRaises(ValueError):
                    OwnedProcess([sys.executable], cwd=folder, env=env)
            with self.launch("pass", cwd=folder) as child:
                for value in (-1, 60001, 1.2, True):
                    with self.subTest(value=value), self.assertRaises(ValueError):
                        child.wait(value)
                    with self.subTest(close_value=value), self.assertRaises(ValueError):
                        child.close(value)
                child.resume()
                with self.assertRaises(RuntimeError):
                    child.resume()

    def test_job_handle_not_inheritable(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.launch("pass", cwd=folder) as child:
                flags = C.c_ulong()
                get_info = C.WinDLL("kernel32", use_last_error=True).GetHandleInformation
                get_info.argtypes = [C.c_void_p, C.POINTER(C.c_ulong)]
                get_info.restype = C.c_int
                self.assertTrue(get_info(child._job, C.byref(flags)))
                self.assertEqual(flags.value & 1, 0)

    def test_assignment_failure_never_executes_child(self):
        from gufo_control import winjob
        with tempfile.TemporaryDirectory() as folder:
            marker = Path(folder) / "ran.txt"
            real_api = winjob._api()
            observer = []
            class Api:
                def __getattr__(self, name):
                    return getattr(real_api, name)
                def AssignProcessToJobObject(self, job, process):
                    get_pid = C.WinDLL("kernel32", use_last_error=True).GetProcessId
                    get_pid.argtypes = [C.c_void_p]
                    get_pid.restype = C.c_ulong
                    observer.append(_observer(get_pid(process)))
                    C.set_last_error(5)
                    return 0
            try:
                with patch.object(winjob, "_api", return_value=Api()):
                    with self.assertRaises(OSError):
                        self.launch("from pathlib import Path; import sys; Path(sys.argv[1]).touch()",
                                    marker, cwd=folder)
                self.assertEqual(observer[0][0].WaitForSingleObject(observer[0][1], 5000), 0)
            finally:
                if observer:
                    observer[0][0].CloseHandle(observer[0][1])
            self.assertFalse(marker.exists())

    def test_failed_exit_confirmation_retains_handle_for_retry(self):
        with tempfile.TemporaryDirectory() as folder:
            child = self.launch("import time; time.sleep(60)", cwd=folder)
            try:
                child.resume()
                real_wait = child._api.WaitForSingleObject
                child._api.WaitForSingleObject = lambda handle, timeout: 258
                try:
                    with self.assertRaises(TimeoutError):
                        child.close(100)
                    self.assertIsNotNone(child._process)
                    self.assertFalse(child._closed)
                finally:
                    child._api.WaitForSingleObject = real_wait
            finally:
                child.close(5000)

    def test_setup_cleanup_uncertainty_chains_error_and_retains_retry_owner(self):
        from gufo_control import winjob
        with tempfile.TemporaryDirectory() as folder:
            real_api = winjob._api()
            class Api:
                def __getattr__(self, name):
                    return getattr(real_api, name)
                def AssignProcessToJobObject(self, job, process):
                    C.set_last_error(5)
                    return 0
                def WaitForSingleObject(self, process, timeout):
                    return 258
            owner = None
            try:
                with patch.object(winjob, "_api", return_value=Api()):
                    with self.assertRaisesRegex(RuntimeError, "cleanup unconfirmed") as caught:
                        self.launch("import time; time.sleep(60)", cwd=folder)
                owner = caught.exception.owner
                self.assertIsInstance(caught.exception.__cause__, OSError)
                self.assertIsNotNone(owner._process)
            finally:
                if owner is not None:
                    owner._api = real_api
                    owner.close(5000)

    def test_failed_assignment_and_transient_termination_retries_on_close(self):
        from gufo_control import winjob
        with tempfile.TemporaryDirectory() as folder:
            marker = Path(folder) / "ran.txt"
            real_api = winjob._api()
            observer = None
            class Api:
                termination_attempts = 0
                def __getattr__(self, name):
                    return getattr(real_api, name)
                def AssignProcessToJobObject(self, job, process):
                    nonlocal observer
                    get_pid = C.WinDLL("kernel32", use_last_error=True).GetProcessId
                    get_pid.argtypes = [C.c_void_p]
                    get_pid.restype = C.c_ulong
                    observer = _observer(get_pid(process))
                    C.set_last_error(5)
                    return 0
                def TerminateProcess(self, process, exit_code):
                    self.termination_attempts += 1
                    if self.termination_attempts == 1:
                        C.set_last_error(5)
                        return 0
                    return real_api.TerminateProcess(process, exit_code)
                def WaitForSingleObject(self, process, timeout):
                    if self.termination_attempts == 1:
                        return 258
                    return real_api.WaitForSingleObject(process, timeout)
            injected = Api()
            owner = None
            try:
                with patch.object(winjob, "_api", return_value=injected):
                    with self.assertRaisesRegex(RuntimeError, "cleanup unconfirmed") as caught:
                        self.launch("from pathlib import Path; import sys; Path(sys.argv[1]).touch()",
                                    marker, cwd=folder)
                owner = caught.exception.owner
                with self.assertRaises(RuntimeError):
                    owner.resume()
                owner.close(5000)
                self.assertEqual(injected.termination_attempts, 2)
                self.assertTrue(owner._closed)
                self.assertEqual(observer[0].WaitForSingleObject(observer[1], 0), 0)
                self.assertFalse(marker.exists())
            finally:
                try:
                    if owner is not None and not owner._closed:
                        real_api.TerminateProcess(owner._process, 1)
                        owner._api = real_api
                        owner.close(5000)
                finally:
                    if observer:
                        observer[0].CloseHandle(observer[1])

    def test_guardian_death_kills_its_child(self):
        with tempfile.TemporaryDirectory() as folder:
            marker = Path(folder) / "identity.json"
            code = ("import json,os,sys,time; from pathlib import Path; "
                    "from gufo_control.winjob import OwnedProcess; "
                    "p=OwnedProcess([sys.executable,'-c','import time; time.sleep(60)'],"
                    "cwd=sys.argv[2],env=dict(os.environ)); p.resume(); "
                    "m=Path(sys.argv[1]); t=m.with_suffix('.tmp'); "
                    "t.write_text(json.dumps(p.identity)); t.replace(m); time.sleep(60)")
            guardian = subprocess.Popen([sys.executable, "-c", code, str(marker), folder],
                                        cwd=folder, env=dict(os.environ),
                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            observer = None
            try:
                identity = json.loads(_await_file(marker))
                self.assertGreater(identity["creation_time_100ns"], 0)
                observer = _observer(identity["pid"])
                guardian.terminate()
                guardian.wait(timeout=5)
                self.assertEqual(observer[0].WaitForSingleObject(observer[1], 5000), 0)
            finally:
                try:
                    if guardian.poll() is None:
                        guardian.terminate()
                        guardian.wait(timeout=5)
                finally:
                    if observer:
                        observer[0].CloseHandle(observer[1])

    def test_close_kills_descendant_in_same_job(self):
        with tempfile.TemporaryDirectory() as folder:
            marker = Path(folder) / "descendant.txt"
            code = ("import subprocess,sys,time; from pathlib import Path; "
                    "p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']); "
                    "m=Path(sys.argv[1]); t=m.with_suffix('.tmp'); "
                    "t.write_text(str(p.pid)); t.replace(m); time.sleep(60)")
            child = self.launch(code, marker, cwd=folder)
            observer = None
            try:
                child.resume()
                observer = _observer(int(_await_file(marker)))
                child.close(5000)
                self.assertEqual(observer[0].WaitForSingleObject(observer[1], 5000), 0)
            finally:
                try:
                    if not child._closed:
                        child.close(5000)
                finally:
                    if observer:
                        observer[0].CloseHandle(observer[1])

    def test_identity_matches_owned_handle(self):
        from gufo_control import winjob
        self.assertEqual(C.sizeof(winjob._BasicLimit), 64)
        self.assertEqual(C.sizeof(winjob._ExtendedLimit), 144)
        self.assertEqual(C.sizeof(winjob._Startup), 104)
        self.assertEqual(C.sizeof(winjob._ProcessInfo), 24)
        with tempfile.TemporaryDirectory() as folder:
            with self.launch("pass", cwd=folder) as child:
                times = [winjob.W.FILETIME() for _ in range(4)]
                self.assertTrue(child._api.GetProcessTimes(
                    child._process, *(C.byref(t) for t in times)))
                created = (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime
                self.assertEqual(child.identity["creation_time_100ns"], created)


if __name__ == "__main__":
    unittest.main()
