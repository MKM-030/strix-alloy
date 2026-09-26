"""Windows owned-process output and native exit-status behavior."""

import ctypes as C
import msvcrt
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from gufo_control import winjob
from gufo_control.winjob import OwnedProcess


def _await_file(path):
    deadline = time.monotonic() + 5
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


@unittest.skipUnless(os.name == "nt", "Windows process ownership")
class OwnedOutputTests(unittest.TestCase):
    def launch(self, code, folder, out, err, *args):
        return OwnedProcess([sys.executable, "-c", code, *map(str, args)],
                            cwd=folder, env=dict(os.environ),
                            stdout_path=out, stderr_path=err)

    def test_separate_binary_logs_and_exit_code(self):
        with tempfile.TemporaryDirectory() as folder:
            out, err = Path(folder) / "output.bin", Path(folder) / "error.bin"
            child = self.launch("import os,sys; os.write(1,b'out\\x00\\xff'); "
                                "os.write(2,b'err'); sys.exit(7)", folder, out, err)
            try:
                self.assertIsNone(child.exit_code())
                self.assertEqual(out.read_bytes(), b"")
                child.resume()
                self.assertTrue(child.wait(5000))
                self.assertEqual(child.exit_code(), 7)
            finally:
                child.close(5000)
            self.assertEqual(child.exit_code(), 7)
            self.assertEqual(out.read_bytes(), b"out\x00\xff")
            self.assertEqual(err.read_bytes(), b"err")

    def test_stdin_is_eof_and_exit_259_is_final(self):
        with tempfile.TemporaryDirectory() as folder:
            out, err = Path(folder) / "out", Path(folder) / "err"
            child = self.launch("import sys; sys.stdout.buffer.write(sys.stdin.buffer.read()); "
                                "sys.exit(259)", folder, out, err)
            try:
                child.resume()
                self.assertTrue(child.wait(5000))
                self.assertEqual(child.exit_code(), 259)
            finally:
                child.close(5000)
            self.assertEqual(child.exit_code(), 259)
            self.assertEqual(out.read_bytes(), b"")

    def test_invalid_output_paths_never_execute_child(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            marker = root / "ran"
            out, err = root / "out", root / "err"
            code = "from pathlib import Path; import sys; Path(sys.argv[1]).touch()"
            argv = [sys.executable, "-c", code, str(marker)]
            cases = [(out, None), (out, root / "." / "out")]
            for stdout, stderr in cases:
                with self.subTest(stdout=stdout, stderr=stderr), self.assertRaises(ValueError):
                    OwnedProcess(argv, cwd=folder, env=dict(os.environ),
                                 stdout_path=stdout, stderr_path=stderr)
                self.assertFalse(marker.exists())
            out.write_bytes(b"old")
            with self.assertRaises(FileExistsError):
                OwnedProcess(argv, cwd=folder, env=dict(os.environ),
                             stdout_path=out, stderr_path=err)
            self.assertEqual(out.read_bytes(), b"old")
            self.assertFalse(marker.exists())

    def test_explicit_handle_list_excludes_inheritable_sentinel(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            sentinel = root / "sentinel"
            out, err = root / "out", root / "err"
            with open(sentinel, "wb", buffering=0) as file:
                handle = msvcrt.get_osfhandle(file.fileno())
                os.set_handle_inheritable(handle, True)
                code = ("import msvcrt,os,sys; h=int(sys.argv[1]); "
                        "\ntry: os.write(msvcrt.open_osfhandle(h,0),b'LEAK')"
                        "\nexcept OSError: pass")
                child = self.launch(code, folder, out, err, handle)
                try:
                    child.resume()
                    self.assertTrue(child.wait(5000))
                    self.assertEqual(child.exit_code(), 0)
                finally:
                    child.close(5000)
            self.assertEqual(sentinel.read_bytes(), b"")

    def test_job_handle_stays_noninheritable_with_logs(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            child = self.launch("pass", folder, root / "out", root / "err")
            try:
                flags = C.c_ulong()
                get_info = C.WinDLL("kernel32", use_last_error=True).GetHandleInformation
                get_info.argtypes = [C.c_void_p, C.POINTER(C.c_ulong)]
                get_info.restype = C.c_int
                self.assertTrue(get_info(child._job, C.byref(flags)))
                self.assertEqual(flags.value & 1, 0)
            finally:
                child.close(5000)

    def test_guardian_death_kills_redirected_child(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            marker = root / "pid"
            code = ("import os,sys,time; from pathlib import Path; "
                    "from gufo_control.winjob import OwnedProcess; "
                    "p=OwnedProcess([sys.executable,'-c','import time; time.sleep(60)'], "
                    "cwd=sys.argv[2],env=dict(os.environ),stdout_path=Path(sys.argv[2])/'out', "
                    "stderr_path=Path(sys.argv[2])/'err'); p.resume(); "
                    "m=Path(sys.argv[1]); t=m.with_suffix('.tmp'); "
                    "t.write_text(str(p.identity['pid'])); t.replace(m); time.sleep(60)")
            guardian = subprocess.Popen([sys.executable, "-c", code, str(marker), folder],
                                        cwd=folder, env=dict(os.environ),
                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            observer = None
            try:
                observer = _observer(int(_await_file(marker)))
                guardian.terminate()
                guardian.wait(timeout=5)
                self.assertEqual(observer[0].WaitForSingleObject(observer[1], 5000), 0)
            finally:
                if guardian.poll() is None:
                    guardian.terminate()
                    guardian.wait(timeout=5)
                if observer:
                    observer[0].CloseHandle(observer[1])

    def test_startup_failures_close_parent_log_handles_and_never_resume(self):
        real_api = winjob._api()
        for failure in ("UpdateProcThreadAttribute", "CreateProcessW"):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                out, err, marker = root / "out", root / "err", root / "ran"
                seen = []
                class Api:
                    def __getattr__(self, name):
                        return getattr(real_api, name)
                    def UpdateProcThreadAttribute(self, storage, flags, key, handles, size, prev, returned):
                        seen.extend(int(handle) for handle in C.cast(
                            handles, C.POINTER(winjob.W.HANDLE * 3)).contents)
                        if failure == "UpdateProcThreadAttribute":
                            C.set_last_error(5)
                            return 0
                        return real_api.UpdateProcThreadAttribute(
                            storage, flags, key, handles, size, prev, returned)
                    def CreateProcessW(self, *args):
                        if failure == "CreateProcessW":
                            C.set_last_error(5)
                            return 0
                        return real_api.CreateProcessW(*args)
                argv = [sys.executable, "-c", "from pathlib import Path; import sys; "
                        "Path(sys.argv[1]).touch()", str(marker)]
                with patch.object(winjob, "_api", return_value=Api()):
                    with self.assertRaises(OSError):
                        OwnedProcess(argv, cwd=folder, env=dict(os.environ),
                                     stdout_path=out, stderr_path=err)
                self.assertEqual(len(seen), 3)
                get_info = C.WinDLL("kernel32", use_last_error=True).GetHandleInformation
                get_info.argtypes = [C.c_void_p, C.POINTER(C.c_ulong)]
                get_info.restype = C.c_int
                for handle in seen:
                    flags = C.c_ulong()
                    self.assertFalse(get_info(handle, C.byref(flags)))
                    self.assertEqual(C.get_last_error(), 6)
                self.assertFalse(marker.exists())

    def test_exit_query_failure_retains_handle_for_close_retry(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            child = self.launch("pass", folder, root / "out", root / "err")
            real = child._api.GetExitCodeProcess
            try:
                child.resume()
                self.assertTrue(child.wait(5000))
                def fail(*args):
                    C.set_last_error(5)
                    return 0
                child._api.GetExitCodeProcess = fail
                with self.assertRaises(OSError):
                    child.close(5000)
                self.assertFalse(child._closed)
                self.assertIsNotNone(child._process)
            finally:
                child._api.GetExitCodeProcess = real
                child.close(5000)
            self.assertEqual(child.exit_code(), 0)


if __name__ == "__main__":
    unittest.main()
