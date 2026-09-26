"""Own a suspended Windows child through a kill-on-close job object."""

import ctypes as C
from ctypes import wintypes as W
import os
from pathlib import Path
import subprocess


class _BasicLimit(C.Structure):
    _fields_ = [("PerProcessUserTimeLimit", C.c_int64),
                ("PerJobUserTimeLimit", C.c_int64), ("LimitFlags", W.DWORD),
                ("MinimumWorkingSetSize", C.c_size_t), ("MaximumWorkingSetSize", C.c_size_t),
                ("ActiveProcessLimit", W.DWORD), ("Affinity", C.c_size_t),
                ("PriorityClass", W.DWORD), ("SchedulingClass", W.DWORD)]


class _Io(C.Structure):
    _fields_ = [(name, C.c_uint64) for name in
                ("ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                 "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]


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
                            W.DWORD, C.c_void_p, W.LPCWSTR, C.POINTER(_Startup),
                            C.POINTER(_ProcessInfo)], W.BOOL),
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
    def __init__(self, argv: list[str], *, cwd: str | Path, env: dict[str, str]):
        if os.name != "nt":
            raise OSError("Windows process ownership requires Windows")
        if not isinstance(argv, list) or not argv or any(
                not isinstance(v, str) or "\0" in v for v in argv):
            raise ValueError("argv must be a nonempty list of NUL-free strings")
        if not isinstance(env, dict) or any(
                not isinstance(k, str) or not k or "=" in k or "\0" in k
                or not isinstance(v, str) or "\0" in v for k, v in env.items()):
            raise ValueError("invalid child environment")
        executable = str(Path(argv[0]).resolve(strict=True))
        directory = str(Path(cwd).resolve(strict=True))
        if not Path(executable).is_file() or not Path(directory).is_dir():
            raise ValueError("invalid executable or working directory")
        self._api = api = _api()
        self._job = self._process = self._thread = None
        self._resumed = self._closed = False
        self.identity = None
        try:
            self._job = _check(api.CreateJobObjectW(None, None))
            limits = _ExtendedLimit()
            limits.BasicLimitInformation.LimitFlags = 0x2000  # KILL_ON_JOB_CLOSE
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
            self.identity = {"pid": int(info.dwProcessId),
                             "creation_time_100ns": (times[0].dwHighDateTime << 32) |
                             times[0].dwLowDateTime, "executable": image.value}
        except BaseException as original:
            try:
                self._abort_setup()
            except BaseException as cleanup:
                cleanup.owner = self  # Retain handles for an explicit retry.
                raise cleanup from original
            raise

    def _abort_setup(self):
        errors = []
        if self._process:
            # The process may not be assigned yet. Never resume it.
            if not self._api.TerminateProcess(self._process, 1):
                errors.append(C.WinError(C.get_last_error()))
        if self._job:
            try:
                _check(self._api.CloseHandle(self._job))
                self._job = None
            except OSError as error:
                errors.append(error)
        if self._process:
            result = self._api.WaitForSingleObject(self._process, 5000)
            if result != 0:
                errors.append(TimeoutError("setup cleanup did not confirm child exit") if result == 258
                              else C.WinError(C.get_last_error()))
        if errors:
            raise RuntimeError("setup cleanup unconfirmed: " + "; ".join(map(str, errors)))
        for name in ("_thread", "_process"):
            handle = getattr(self, name)
            if handle:
                _check(self._api.CloseHandle(handle))
                setattr(self, name, None)
        self._closed = True

    def resume(self) -> None:
        if self._closed or self._resumed:
            raise RuntimeError("process is closed or already resumed")
        count = self._api.ResumeThread(self._thread)
        if count != 1:
            try:
                self.close()
            except BaseException as cleanup:
                raise RuntimeError(f"unexpected suspend count {count}; cleanup unconfirmed") from cleanup
            raise OSError(f"unexpected primary-thread suspend count: {count}")
        self._resumed = True

    def wait(self, timeout_ms: int = 0) -> bool:
        timeout_ms = _timeout(timeout_ms)
        if self._closed:
            raise RuntimeError("process handle is closed")
        result = self._api.WaitForSingleObject(self._process, timeout_ms)
        if result == 0:
            return True
        if result == 258:
            return False
        raise C.WinError(C.get_last_error())

    def close(self, timeout_ms: int = 5000) -> None:
        timeout_ms = _timeout(timeout_ms)
        if self._closed:
            return
        if self._job:
            _check(self._api.CloseHandle(self._job))
            self._job = None
        if self._process and not self.wait(timeout_ms):
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
