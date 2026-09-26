# GUFO Owned Windows Process Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to execute and independently review this task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish tested Windows process ownership before wiring a real model launcher.

**Architecture:** A small ctypes binding creates one suspended child, assigns it to an unnamed non-inherited kill-on-close job, and exposes explicit resume, wait, identity and bounded close. Tests use only the current Python executable and tiny temporary-file markers. This is the OS lifecycle primitive, not the long-lived guardian, telemetry or GUFO launcher itself; redirected engine logs and startup protocol remain controller work.

**Tech Stack:** Python 3.12 standard library, Windows kernel32, unittest.

## Global Constraints

- Work only in `C:\Projects\strix-alloy-research\integration` and commit only the task-owned files.
- No model, GPU, WSL, driver, service, security, BIOS, disk-layout or persistent environment changes.
- Do not kill by image name or trust a stale PID file.
- Create the child suspended, assign it to the job before any weight loading, then resume it. Failed job assignment aborts before resume.
- The guardian owns a non-inherited Windows Job Object with kill-on-close behavior.
- This is lifecycle cleanup, not a GPU-memory cap or proof against a driver hang.
- Source snapshots and existing installations remain unchanged. No public push.

### Task 1: Owned suspended process and real Windows lifecycle tests

**Files:**
- Create `scripts/gufo_control/winjob.py`: platform structures, typed API boundary and lifecycle object.
- Create `tests/gufo/test_winjob.py`: real Windows child-process tests and focused failure injection.

**Interfaces:**
- `OwnedProcess(argv: list[str], *, cwd: str | Path, env: dict[str, str])` creates a suspended assigned child; constructor returns only after assignment and identity capture.
- `.identity` is a JSON-safe dictionary with `pid`, `creation_time_100ns`, `executable` from the process handle, not inferred from a PID file.
- `.resume() -> None`: exactly once, requires the primary thread's previous suspend count to equal one.
- `.wait(timeout_ms: int = 0) -> bool`: true only if the exact owned process handle is signaled; bounded integer timeout 0..60000, no infinite waits.
- `.close(timeout_ms: int = 5000) -> None`: close the sole job handle first, verify root-process exit within the bound, release remaining handles; idempotent after successful cleanup. Raise on unconfirmed exit, do not call that successful reclamation.
- Context-manager support delegates to close. No destructor pretending to verify successful shutdown.
- Import on non-Windows is allowed; construction raises `OSError`. Windows tests skip elsewhere, never call a skipped suite a Windows qualification.

- [ ] **Step 1: Write failing real-process tests.** The complete starter tests below establish the normal and kill-on-close path; extend them with the exact cases in Step 4.

```python
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from gufo_control.winjob import OwnedProcess


@unittest.skipUnless(os.name == "nt", "Windows lifecycle qualification")
class WinJobTests(unittest.TestCase):
    def test_suspended_until_resume_then_clean_exit(self):
        with tempfile.TemporaryDirectory() as folder:
            marker = Path(folder) / "ran.txt"
            code = "from pathlib import Path; import sys; Path(sys.argv[1]).write_text('ok')"
            with OwnedProcess([sys.executable, "-c", code, str(marker)],
                              cwd=folder, env=dict(os.environ)) as child:
                self.assertFalse(child.wait(100))
                self.assertFalse(marker.exists())
                self.assertGreater(child.identity["pid"], 0)
                self.assertGreater(child.identity["creation_time_100ns"], 0)
                self.assertEqual(Path(child.identity["executable"]).resolve(), Path(sys.executable).resolve())
                child.resume()
                self.assertTrue(child.wait(5000))
                self.assertEqual(marker.read_text(), "ok")

    def test_close_kills_running_child(self):
        with tempfile.TemporaryDirectory() as folder:
            child = OwnedProcess([sys.executable, "-c", "import time; time.sleep(60)"],
                                 cwd=folder, env=dict(os.environ))
            child.resume()
            self.assertFalse(child.wait(50))
            child.close(5000)
            child.close()
```

- [ ] **Step 2: Run RED.**

```powershell
$env:PYTHONPATH = Join-Path $PWD 'scripts'
& 'C:\Users\Marcel\AppData\Local\Programs\Python\Python312\python.exe' -m unittest discover -s tests/gufo -p test_winjob.py -v
```

Record the expected missing-module failure. Then add a minimal nonfunctional object and confirm the suspended/execution assertions fail before implementing the actual lifecycle.

- [ ] **Step 3: Implement the lifecycle.** Use the following complete core as a starting point. Verify structure sizes and prototypes against the local Windows SDK or Microsoft definitions; correct concrete discrepancies. Preserve exception-safe cleanup if setup fails at any point.

```python
"""Owned Windows child handles. No admission or GPU reservation is implied."""
import ctypes as C
from ctypes import wintypes as W
import os
from pathlib import Path
import subprocess


class _BasicLimit(C.Structure):
    _fields_ = [("PerProcessUserTimeLimit", C.c_int64), ("PerJobUserTimeLimit", C.c_int64),
                ("LimitFlags", W.DWORD), ("MinimumWorkingSetSize", C.c_size_t),
                ("MaximumWorkingSetSize", C.c_size_t), ("ActiveProcessLimit", W.DWORD),
                ("Affinity", C.c_size_t), ("PriorityClass", W.DWORD), ("SchedulingClass", W.DWORD)]


class _Io(C.Structure):
    _fields_ = [(name, C.c_uint64) for name in ("ReadOperationCount", "WriteOperationCount",
                "OtherOperationCount", "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]


class _ExtendedLimit(C.Structure):
    _fields_ = [("BasicLimitInformation", _BasicLimit), ("IoInfo", _Io),
                ("ProcessMemoryLimit", C.c_size_t), ("JobMemoryLimit", C.c_size_t),
                ("PeakProcessMemoryUsed", C.c_size_t), ("PeakJobMemoryUsed", C.c_size_t)]


class _Startup(C.Structure):
    _fields_ = [("cb", W.DWORD), ("lpReserved", W.LPWSTR), ("lpDesktop", W.LPWSTR),
                ("lpTitle", W.LPWSTR), ("dwX", W.DWORD), ("dwY", W.DWORD),
                ("dwXSize", W.DWORD), ("dwYSize", W.DWORD), ("dwXCountChars", W.DWORD),
                ("dwYCountChars", W.DWORD), ("dwFillAttribute", W.DWORD),
                ("dwFlags", W.DWORD), ("wShowWindow", W.WORD), ("cbReserved2", W.WORD),
                ("lpReserved2", C.POINTER(W.BYTE)), ("hStdInput", W.HANDLE),
                ("hStdOutput", W.HANDLE), ("hStdError", W.HANDLE)]


class _ProcessInfo(C.Structure):
    _fields_ = [("hProcess", W.HANDLE), ("hThread", W.HANDLE),
                ("dwProcessId", W.DWORD), ("dwThreadId", W.DWORD)]


def _api():
    if os.name != "nt":
        raise OSError("Windows process ownership requires Windows")
    api = C.WinDLL("kernel32", use_last_error=True)
    declarations = {
        "CreateJobObjectW": ([C.c_void_p, W.LPCWSTR], W.HANDLE),
        "SetInformationJobObject": ([W.HANDLE, C.c_int, C.c_void_p, W.DWORD], W.BOOL),
        "AssignProcessToJobObject": ([W.HANDLE, W.HANDLE], W.BOOL),
        "CreateProcessW": ([W.LPCWSTR, W.LPWSTR, C.c_void_p, C.c_void_p, W.BOOL,
                            W.DWORD, C.c_void_p, W.LPCWSTR, C.POINTER(_Startup), C.POINTER(_ProcessInfo)], W.BOOL),
        "ResumeThread": ([W.HANDLE], W.DWORD),
        "TerminateProcess": ([W.HANDLE, W.UINT], W.BOOL),
        "WaitForSingleObject": ([W.HANDLE, W.DWORD], W.DWORD),
        "CloseHandle": ([W.HANDLE], W.BOOL),
        "GetProcessTimes": ([W.HANDLE] + [C.POINTER(W.FILETIME)] * 4, W.BOOL),
        "QueryFullProcessImageNameW": ([W.HANDLE, W.DWORD, W.LPWSTR, C.POINTER(W.DWORD)], W.BOOL),
    }
    for name, (args, result) in declarations.items():
        fn = getattr(api, name)
        fn.argtypes, fn.restype = args, result
    return api


def _check(result):
    if not result:
        raise C.WinError(C.get_last_error())
    return result


def _timeout(value):
    if type(value) is not int or not 0 <= value <= 60000:
        raise ValueError("timeout must be an integer from 0 through 60000 ms")
    return value


class OwnedProcess:
    def __init__(self, argv, *, cwd, env):
        if not isinstance(argv, list) or not argv or any(not isinstance(v, str) or "\0" in v for v in argv):
            raise ValueError("argv must be a nonempty list of NUL-free strings")
        if not isinstance(env, dict) or any(not isinstance(k, str) or not k or "=" in k or "\0" in k
                or not isinstance(v, str) or "\0" in v for k, v in env.items()):
            raise ValueError("invalid child environment")
        executable = str(Path(argv[0]).resolve(strict=True))
        directory = str(Path(cwd).resolve(strict=True))
        if not Path(executable).is_file() or not Path(directory).is_dir():
            raise ValueError("invalid executable or working directory")
        self._api = api = _api()
        self._job = self._process = self._thread = None
        self._resumed = False
        self._closed = False
        try:
            self._job = _check(api.CreateJobObjectW(None, None))
            limits = _ExtendedLimit()
            limits.BasicLimitInformation.LimitFlags = 0x2000  # KILL_ON_JOB_CLOSE; no breakaway
            _check(api.SetInformationJobObject(self._job, 9, C.byref(limits), C.sizeof(limits)))
            startup = _Startup()
            startup.cb = C.sizeof(startup)
            info = _ProcessInfo()
            command = C.create_unicode_buffer(subprocess.list2cmdline([executable, *argv[1:]]))
            entries = [k + "=" + env[k] for k in sorted(env, key=str.casefold)]
            environment = C.create_unicode_buffer("\0".join(entries) + "\0\0")
            _check(api.CreateProcessW(executable, command, None, None, False,
                                     0x4 | 0x400 | 0x08000000, environment, directory,
                                     C.byref(startup), C.byref(info)))
            self._process, self._thread = info.hProcess, info.hThread
            _check(api.AssignProcessToJobObject(self._job, self._process))
            times = [W.FILETIME() for _ in range(4)]
            _check(api.GetProcessTimes(self._process, *(C.byref(t) for t in times)))
            image = C.create_unicode_buffer(32768)
            length = W.DWORD(len(image))
            _check(api.QueryFullProcessImageNameW(self._process, 0, image, C.byref(length)))
            self.identity = {"pid": int(info.dwProcessId), "creation_time_100ns":
                             (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime,
                             "executable": image.value}
        except BaseException:
            # The child may exist but not yet be assigned. Never resume that child.
            if self._process:
                api.TerminateProcess(self._process, 1)
                api.WaitForSingleObject(self._process, 5000)
            for handle in (self._job, self._thread, self._process):
                if handle:
                    api.CloseHandle(handle)
            self._job = self._thread = self._process = None
            self._closed = True
            raise

    def resume(self):
        if self._closed or self._resumed:
            raise RuntimeError("process is closed or already resumed")
        count = self._api.ResumeThread(self._thread)
        if count != 1:
            self.close()
            raise OSError("unexpected primary-thread suspend count: " + str(count))
        self._resumed = True

    def wait(self, timeout_ms=0):
        timeout_ms = _timeout(timeout_ms)
        if self._closed:
            raise RuntimeError("process handle is closed")
        result = self._api.WaitForSingleObject(self._process, timeout_ms)
        if result == 0:
            return True
        if result == 258:
            return False
        raise C.WinError(C.get_last_error())

    def close(self, timeout_ms=5000):
        timeout_ms = _timeout(timeout_ms)
        if self._closed:
            return
        if self._job:
            _check(self._api.CloseHandle(self._job))
            self._job = None
        exited = self.wait(timeout_ms)
        if not exited:
            raise TimeoutError("owned-process exit not confirmed; retain handles for retry")
        for name in ("_thread", "_process"):
            handle = getattr(self, name)
            if handle:
                _check(self._api.CloseHandle(handle))
                setattr(self, name, None)
        self._closed = True

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
```

The constructor failure branch above is a starting point: strengthen it so failed termination/wait/close is surfaced with the original setup error chained, rather than silently discarding cleanup uncertainty. No false verified-cleanup claim on any path. Preserve handles as appropriate for a retry if a live object exists. The public controller will later journal such failures; no journal, lock, endpoint or model/profile logic belongs in this primitive.

- [ ] **Step 4: Add focused RED/GREEN coverage.** Use actual harmless children for guardian death, unresumed close, quoting/environment propagation, normal exit, a child spawning a descendant, and identity from the handle. For guardian death, launch a small Python guardian subprocess which constructs and resumes this primitive, writes the child PID and creation time to a temp file, then sleeps; terminate only that guardian handle and verify the exact child handle signals within five seconds. The test observer may open a handle to its known child before killing the guardian; never kill an arbitrary PID. Ensure test cleanup in `finally`. For descendant termination hold an observer handle to the child's announced descendant before close and assert both handles signal. This tests the real last-handle behavior, not a mock.

Inject just the relevant API call to exercise assignment failure before resume and failure to confirm exit. Patch a fresh `_api()` instance or facade, preserve real process creation, record created process handles, set an explicit last-error on injected failure and verify child never executes its marker and exits. Test bad argv/env/timeouts, second resume, closed wait and repeated close. Verify the job has no inheritable flag using GetHandleInformation in a focused test. Do not assert no global Windows process exists by image name. Tests must release every observer handle. No sleep longer than bounded polling required for temporary-file handshakes; the process lifetime60seconds is only a backstop, not a test delay.

- [ ] **Step 5: Run focused and full offline suites, then commit.**

```powershell
$env:PYTHONPATH = Join-Path $PWD 'scripts'
& 'C:\Users\Marcel\AppData\Local\Programs\Python\Python312\python.exe' -m unittest discover -s tests/gufo -p test_winjob.py -v
& 'C:\Users\Marcel\AppData\Local\Programs\Python\Python312\python.exe' -m unittest discover -s tests/gufo -p 'test_*.py' -v
git diff --check
git add -- scripts/gufo_control/winjob.py tests/gufo/test_winjob.py
git commit -m 'feat: own suspended Windows child with kill-on-close job'
```

Report exact RED/GREEN commands/counts, actual Windows execution (not skipped), cleanup failure behavior, API/structure validation, files and limitations. No memory reclamation or real-model readiness claim follows from this OS-only test.

## Scope review

This task delivers the lifecycle primitive. Remaining specification components (model/profile binding, telemetry, long-lived guardian protocol, single-instance lock, engine log redirection, readiness, memory reclamation, installer and benchmarks) remain explicit separate work, not silently considered satisfied by these tests.

## Primary API references

- https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects
- https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-createprocessw
- https://learn.microsoft.com/en-us/windows/win32/api/jobapi2/nf-jobapi2-setinformationjobobject
- https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_extended_limit_information
