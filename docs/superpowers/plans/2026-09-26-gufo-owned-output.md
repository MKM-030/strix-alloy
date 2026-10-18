# GUFO Owned Process Output Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement and review this task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Capture native test/server stdout, stderr and the actual process exit code without weakening the existing suspended-child/job ownership.

**Architecture:** Extend the existing Windows process primitive with optional exclusive log files and an explicit STARTUPINFOEX inherited-handle allowlist. Keep the job handle non-inheritable. This supports the bounded probe runner and later server guardian; it does not itself launch GUFO or qualify a runtime.

**Tech Stack:** Python3.12 standard library, ctypes Win32 APIs, unittest, harmless Python child processes.

## Global Constraints

- Work only in `C:\Projects\strix-alloy-research\integration`, commit only owned paths.
- No GPU/model/WSL execution or persistent system changes. Tests launch only harmless bounded Python children.
- Create children suspended, assign the non-inherited kill-on-close job before resume, and preserve the exact-handle cleanup retry behavior.
- Never inherit the job or arbitrary parent handles. Only the explicitly opened stdin/stdout/stderr handles may be inherited in the redirected path.
- Retain failed-run logs; never overwrite an existing log. No recursive deletion or public push.
- Existing callers without log arguments retain their behavior. No model admission, monitor, readiness or memory-reclamation claim in this task.

### Task 1: Exclusive output capture and native exit status

**Files:**
- Modify `scripts/gufo_control/winjob.py`: optional log setup and exit-code API.
- Create `tests/gufo/test_winjob_output.py`: real harmless-child and injected-failure tests.

**Interfaces:**
- Extend `OwnedProcess(argv, *, cwd, env, stdout_path=None, stderr_path=None)`. Both optional paths must be supplied together. Files are separate, newly created binary files in existing directories; relative paths resolve in the caller, not the child. stdin is the Windows null device when redirected.
- Add `exit_code() -> int | None`. Return None only while the process is running; after confirmed exit return the native unsigned DWORD code, including259. Preserve the captured code after successful close. A Win32 query failure raises and retains handles for retry.
- Original wait/close/resume/identity semantics remain unchanged. Job closure still terminates descendants even when the root has exited.

- [ ] **Step 1: Add real-child RED tests.** Use this skeleton and extend it with the enumerated cases below before implementing each feature.

```python
import os
from pathlib import Path
import sys
import tempfile
import unittest
from gufo_control.winjob import OwnedProcess

@unittest.skipUnless(os.name == 'nt', 'Windows process ownership')
class OwnedOutputTests(unittest.TestCase):
    def test_separate_binary_logs_and_exit_code(self):
        with tempfile.TemporaryDirectory() as directory:
            stdout = Path(directory) / 'output.bin'
            stderr = Path(directory) / 'error.bin'
            argv = [sys.executable, '-c',
                    "import os,sys; os.write(1,b'out\\x00\\xff'); os.write(2,b'err'); sys.exit(7)"]
            child = OwnedProcess(argv, cwd=directory, env=dict(os.environ),
                                 stdout_path=stdout, stderr_path=stderr)
            try:
                self.assertIsNone(child.exit_code())
                self.assertEqual(stdout.read_bytes(), b'')
                child.resume()
                self.assertTrue(child.wait(5000))
                self.assertEqual(child.exit_code(), 7)
            finally:
                child.close(5000)
            self.assertEqual(child.exit_code(), 7)
            self.assertEqual(stdout.read_bytes(), b'out\x00\xff')
            self.assertEqual(stderr.read_bytes(), b'err')
```

Other required real tests: stdin reads EOF; exit259 is not mistaken for running; one path missing/same resolved path/existing output is rejected without executing child; a parent inheritable sentinel-file handle cannot be written by the child; the job remains non-inheritable with logging enabled; killing a guardian with redirected child still kills that child. Use existing test_winjob.py handle-observer and atomic file-handshake patterns without copying whole tests. Add a focused injected failure at UpdateProcThreadAttribute and CreateProcessW to prove opened parent log handles are closed and no child is resumed. Use bounded waits and finally cleanup in all tests. After injected GetExitCodeProcess failure during close, restore the real API and retry close successfully.

Run focused RED:

```powershell
$env:PYTHONPATH = Join-Path $PWD 'scripts'
& 'C:\Users\Marcel\AppData\Local\Programs\Python\Python312\python.exe' -m unittest discover -s tests/gufo -p test_winjob_output.py -v
```

Expected: missing optional argument/exit_code failures, followed by behavioral RED before corresponding checks.

- [ ] **Step 2: Add explicit-handle startup support.** Implement this helper in winjob.py, using the existing aliases C, W, _Startup and _check. Add `contextlib` imports. Keep initialization/cleanup bounded and propagate errors; logs remain on failure.

```python
class _StartupEx(C.Structure):
    _fields_ = [('StartupInfo', _Startup), ('lpAttributeList', C.c_void_p)]

@contextlib.contextmanager
def _startup_info(api, stdout_path, stderr_path):
    if stdout_path is None and stderr_path is None:
        startup = _Startup()
        startup.cb = C.sizeof(startup)
        yield C.byref(startup), False, 0
        return
    if stdout_path is None or stderr_path is None:
        raise ValueError('both stdout_path and stderr_path are required')
    out = Path(stdout_path).resolve()
    err = Path(stderr_path).resolve()
    if os.path.normcase(str(out)) == os.path.normcase(str(err)):
        raise ValueError('stdout and stderr must be distinct files')
    import msvcrt
    with contextlib.ExitStack() as stack:
        files = [stack.enter_context(open(os.devnull, 'rb', buffering=0)),
                 stack.enter_context(open(out, 'xb', buffering=0)),
                 stack.enter_context(open(err, 'xb', buffering=0))]
        handles = (W.HANDLE * 3)(*(msvcrt.get_osfhandle(f.fileno()) for f in files))
        for handle in handles:
            os.set_handle_inheritable(handle, True)
        required = C.c_size_t()
        ok = api.InitializeProcThreadAttributeList(None, 1, 0, C.byref(required))
        if ok or C.get_last_error() != 122 or not 0 < required.value <= 65536:
            raise OSError('unexpected process attribute sizing result')
        storage = C.create_string_buffer(required.value)
        _check(api.InitializeProcThreadAttributeList(storage, 1, 0, C.byref(required)))
        try:
            _check(api.UpdateProcThreadAttribute(storage, 0, 0x20002, handles,
                                                C.sizeof(handles), None, None))
            startup = _StartupEx()
            startup.StartupInfo.cb = C.sizeof(startup)
            startup.StartupInfo.dwFlags = 0x100  # STARTF_USESTDHANDLES
            startup.StartupInfo.hStdInput = handles[0]
            startup.StartupInfo.hStdOutput = handles[1]
            startup.StartupInfo.hStdError = handles[2]
            startup.lpAttributeList = C.cast(storage, C.c_void_p)
            yield C.byref(startup.StartupInfo), True, 0x80000
        finally:
            api.DeleteProcThreadAttributeList(storage)
```

Add these API declarations to the existing table:

```python
'InitializeProcThreadAttributeList': ([C.c_void_p, W.DWORD, W.DWORD,
                                      C.POINTER(C.c_size_t)], W.BOOL),
'UpdateProcThreadAttribute': ([C.c_void_p, W.DWORD, C.c_size_t, C.c_void_p,
                               C.c_size_t, C.c_void_p, C.c_void_p], W.BOOL),
'DeleteProcThreadAttributeList': ([C.c_void_p], None),
'GetExitCodeProcess': ([W.HANDLE, C.POINTER(W.DWORD)], W.BOOL),
```

Inside the constructor's existing try block replace only the startup/CreateProcess section. Initialize `_exit_code = None` with other fields. Ensure self owns returned process/thread handles **before leaving** the context manager, so any cleanup error is handled by the original constructor abort path:

```python
with _startup_info(api, stdout_path, stderr_path) as (startup, inherit, extra_flags):
    _check(api.CreateProcessW(executable, command, None, None, inherit,
                             0x4 | 0x400 | 0x08000000 | extra_flags,
                             environment, directory, startup, C.byref(info)))
    self._process, self._thread = info.hProcess, info.hThread
```

The existing command/environment creation remains before this block. Job assignment and identity collection remain after it, before any resume. Keep CreateProcessW's existing POINTER(_Startup) signature: the pointer addresses the first embedded StartupInfo member. No additional inherited handles or shell invocation.

- [ ] **Step 3: Add native exit status and close retention.**

```python
def exit_code(self):
    if self._closed:
        return self._exit_code
    if not self.wait(0):
        return None
    code = W.DWORD()
    _check(self._api.GetExitCodeProcess(self._process, C.byref(code)))
    self._exit_code = int(code.value)
    return self._exit_code
```

In close(), after confirmed process exit and before closing its handle, call exit_code(). Do not set _closed or discard the process handle when exit-code retrieval fails. Keep the recovery-only termination branch and job-close order unchanged. Construction failures retain their original error chaining and cleanup semantics. The discarded object on successful constructor-abort needs no public exit result.

- [ ] **Step 4: GREEN and self-review.** Run both Windows test files with pattern `test_winjob*.py`, then all tests once. Every Windows case must execute, not skip. Check binary logs, guardian death, explicit allowlist and failure cleanup from behavior, not merely structure. Do not run GUFO to test logging.

```powershell
$env:PYTHONPATH = Join-Path $PWD 'scripts'
& 'C:\Users\Marcel\AppData\Local\Programs\Python\Python312\python.exe' -m unittest discover -s tests/gufo -p 'test_winjob*.py' -v
& 'C:\Users\Marcel\AppData\Local\Programs\Python\Python312\python.exe' -m unittest discover -s tests/gufo -p 'test_*.py' -v
git diff --check
git add -- scripts/gufo_control/winjob.py tests/gufo/test_winjob_output.py
git commit -m 'feat: capture owned Windows process logs and exit status'
```

Record commands and RED/GREEN evidence, changed files, handle cleanup findings, and any concerns in the task report. Full-guardian/model integration is outside this task.

## API evidence

- Microsoft UpdateProcThreadAttribute: explicit HANDLE_LIST requires inheritable handles, bInheritHandles TRUE, and values alive until the attribute list is destroyed: https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-updateprocthreadattribute
- GetExitCodeProcess reports259 for an active process, but an exited application can also return259; consult the owned process wait state first: https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-getexitcodeprocess

This plan fills one reusable prerequisite. Remaining spec work is the guarded runner/guardian, model profiles, setup/CLI, HTTP correctness and benchmark tooling, numerical qualification, matched measurements and documentation.
