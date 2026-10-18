"""Own a suspended Windows child through a kill-on-close job object."""

import ctypes as C
from ctypes import wintypes as W
import contextlib
import ntpath
import os
from pathlib import Path
import subprocess
import threading
import time


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


class _StartupEx(C.Structure):
    _fields_ = [("StartupInfo", _Startup), ("lpAttributeList", C.c_void_p)]


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
        "InitializeProcThreadAttributeList": ([C.c_void_p, W.DWORD, W.DWORD,
                                                C.POINTER(C.c_size_t)], W.BOOL),
        "UpdateProcThreadAttribute": ([C.c_void_p, W.DWORD, C.c_size_t, C.c_void_p,
                                       C.c_size_t, C.c_void_p, C.c_void_p], W.BOOL),
        "DeleteProcThreadAttributeList": ([C.c_void_p], None),
        "GetExitCodeProcess": ([W.HANDLE, C.POINTER(W.DWORD)], W.BOOL),
        "ResumeThread": ([W.HANDLE], W.DWORD),
        "TerminateProcess": ([W.HANDLE, W.UINT], W.BOOL),
        "WaitForSingleObject": ([W.HANDLE, W.DWORD], W.DWORD),
        "CloseHandle": ([W.HANDLE], W.BOOL),
        "GetCurrentProcess": ([], W.HANDLE),
        "GetProcessId": ([W.HANDLE], W.DWORD),
        "DuplicateHandle": ([W.HANDLE, W.HANDLE, W.HANDLE, C.POINTER(W.HANDLE),
                              W.DWORD, W.BOOL, W.DWORD], W.BOOL),
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


def _normalized_path(value):
    return ntpath.normcase(ntpath.normpath(value))


def _module_api():
    api = C.WinDLL('psapi', use_last_error=True)
    api.EnumProcessModulesEx.argtypes = [W.HANDLE, C.POINTER(W.HMODULE), W.DWORD,
                                       C.POINTER(W.DWORD), W.DWORD]
    api.EnumProcessModulesEx.restype = W.BOOL
    api.GetModuleFileNameExW.argtypes = [W.HANDLE, W.HMODULE, W.LPWSTR, W.DWORD]
    api.GetModuleFileNameExW.restype = W.DWORD
    return api


def _module_paths(api, process, deadline) -> dict[str, str]:
    """Bounded best-effort snapshot using only the independent process handle."""
    psapi = _module_api()
    handles = (W.HMODULE * 4096)()
    needed = W.DWORD()
    if time.monotonic() > deadline:
        raise TimeoutError('inspection_timeout')
    _check(psapi.EnumProcessModulesEx(process, handles, C.sizeof(handles), C.byref(needed), 3))
    if not 0 < needed.value <= C.sizeof(handles) or needed.value % C.sizeof(W.HMODULE):
        raise ValueError('module_count_unknown')
    paths = {}
    try:
        for index in range(needed.value // C.sizeof(W.HMODULE)):
            if time.monotonic() > deadline:
                raise TimeoutError('inspection_timeout')
            path = C.create_unicode_buffer(32768)
            length = _check(psapi.GetModuleFileNameExW(process, handles[index], path, len(path)))
            if length >= len(path)-1 or not ntpath.isabs(path.value):
                raise ValueError('module_path_unknown')
            name = ntpath.basename(path.value).lower()
            if name in paths and _normalized_path(paths[name]) != _normalized_path(path.value):
                # Preserve BOTH paths as evidence before failing inconclusive.
                # The classifier must still fail any observed external HIP DLL.
                paths[name + '#duplicate'] = path.value
                raise ValueError('ambiguous_module_name')
            paths[name] = path.value
    except BaseException as error:
        error.modules = paths
        raise
    return paths


def _external_hip(paths, app_local_dir):
    return any(ntpath.basename(path).lower() == 'amdhip64_7.dll'
               and _normalized_path(ntpath.dirname(path)) != app_local_dir
               for path in paths.values())


class ModuleInspectionTask:
    """Daemon result plus independent terminal and duplicate-close evidence.

    done does not imply duplicate_closed: CloseHandle itself can fail. Native API
    calls cannot be forcibly interrupted; the guardian must enforce deadline,
    stop its job immediately, and keep its latch if this task remains unfinished.
    """
    def __init__(self):
        self.done = threading.Event()
        self.duplicate_closed = threading.Event()
        self.duplicate_closed.set()  # No handle exists before duplication.
        self.deadline = time.monotonic() + 2.0
        self.result = None

    def snapshot(self, *, now=None) -> dict:
        terminal = self.done.is_set()
        if terminal:
            result = dict(self.result)
            result['modules'] = dict(result['modules'])
        else:
            expired = (time.monotonic() if now is None else now) > self.deadline
            result = dict(status='unknown' if expired else 'pending',
                reason='inspection_timeout' if expired else 'inspection_pending', modules={})
        return dict(result, terminal=terminal,
                    duplicate_handle_closed=self.duplicate_closed.is_set())


def _inspect_modules(task, api, duplicate, app_local_dir):
    # This worker has no OwnedProcess reference and never touches the original
    # process handle or job. Its duplicate is non-inheritable and read-only.
    result = dict(status='unknown', reason='inspection_unavailable', modules={})
    try:
        paths = _module_paths(api, duplicate, task.deadline)
        result['modules'] = paths
        hip = paths.get('amdhip64_7.dll')
        if _external_hip(paths, app_local_dir):
            result.update(status='failed', reason='hip_module_outside_app_local')
        elif time.monotonic() > task.deadline:
            result.update(reason='inspection_timeout')
        elif api.WaitForSingleObject(duplicate, 0) != 258:
            result.update(reason='process_not_live')
        elif hip is None:
            result.update(reason='hip_module_not_observed')
        else:
            result.update(status='verified', reason='app_local_hip_observed')
    except BaseException as error:
        result['modules'] = dict(getattr(error, 'modules', {}))
        result.update(reason='inspection_timeout' if isinstance(error, TimeoutError)
                      else 'inspection_unavailable', error=type(error).__name__)
        if _external_hip(result['modules'], app_local_dir):
            result.update(status='failed', reason='hip_module_outside_app_local')
    finally:
        try:
            _check(api.CloseHandle(duplicate))
            task.duplicate_closed.set()
        except BaseException as error:
            result['duplicate_close_error'] = type(error).__name__
            if result['status'] != 'failed':
                result.update(status='unknown', reason='duplicate_close_unconfirmed')
        task.result = result
        task.done.set()


@contextlib.contextmanager
def _startup_info(api, stdout_path, stderr_path):
    if stdout_path is None and stderr_path is None:
        startup = _Startup()
        startup.cb = C.sizeof(startup)
        yield C.byref(startup), False, 0
        return
    if stdout_path is None or stderr_path is None:
        raise ValueError("both stdout_path and stderr_path are required")
    out = Path(stdout_path).resolve()
    err = Path(stderr_path).resolve()
    if os.path.normcase(str(out)) == os.path.normcase(str(err)):
        raise ValueError("stdout and stderr must be distinct files")
    import msvcrt
    with contextlib.ExitStack() as stack:
        files = [stack.enter_context(open(os.devnull, "rb", buffering=0)),
                 stack.enter_context(open(out, "xb", buffering=0)),
                 stack.enter_context(open(err, "xb", buffering=0))]
        handles = (W.HANDLE * 3)(*(msvcrt.get_osfhandle(f.fileno()) for f in files))
        for handle in handles:
            os.set_handle_inheritable(handle, True)
        required = C.c_size_t()
        ok = api.InitializeProcThreadAttributeList(None, 1, 0, C.byref(required))
        if ok or C.get_last_error() != 122 or not 0 < required.value <= 65536:
            raise OSError("unexpected process attribute sizing result")
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


class OwnedProcess:
    def __init__(self, argv: list[str], *, cwd: str | Path, env: dict[str, str],
                 stdout_path: str | Path | None = None, stderr_path: str | Path | None = None):
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
        self._recovery_only = True
        self._exit_code = None
        self.identity = None
        try:
            self._job = _check(api.CreateJobObjectW(None, None))
            limits = _ExtendedLimit()
            limits.BasicLimitInformation.LimitFlags = 0x2000  # KILL_ON_JOB_CLOSE
            _check(api.SetInformationJobObject(self._job, 9, C.byref(limits), C.sizeof(limits)))
            info = _ProcessInfo()
            command = C.create_unicode_buffer(subprocess.list2cmdline([executable, *argv[1:]]))
            entries = [k + "=" + env[k] for k in sorted(env, key=str.casefold)]
            environment = C.create_unicode_buffer("\0".join(entries) + "\0\0")
            with _startup_info(api, stdout_path, stderr_path) as (startup, inherit, extra_flags):
                _check(api.CreateProcessW(executable, command, None, None, inherit,
                                         0x4 | 0x400 | 0x08000000 | extra_flags,
                                         environment, directory, startup, C.byref(info)))
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
            self._recovery_only = False
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
        if self._closed or self._resumed or self._recovery_only:
            raise RuntimeError("process is closed, already resumed, or setup did not complete")
        count = self._api.ResumeThread(self._thread)
        if count != 1:
            try:
                self.close()
            except BaseException as cleanup:
                raise RuntimeError(f"unexpected suspend count {count}; cleanup unconfirmed") from cleanup
            raise OSError(f"unexpected primary-thread suspend count: {count}")
        self._resumed = True

    def verify_live_identity(self) -> dict:
        """Prove recorded identity against the retained handle, never a PID open."""
        if self._closed or not self._process or self._recovery_only:
            raise RuntimeError('owned process handle unavailable')
        api, process = self._api, self._process
        if api.WaitForSingleObject(process, 0) != 258:
            raise ValueError('owned_process_not_live')
        pid = int(_check(api.GetProcessId(process)))
        times = [W.FILETIME() for _ in range(4)]
        _check(api.GetProcessTimes(process, *(C.byref(t) for t in times)))
        image = C.create_unicode_buffer(32768)
        length = W.DWORD(len(image))
        _check(api.QueryFullProcessImageNameW(process, 0, image, C.byref(length)))
        live = dict(pid=pid, creation_time_100ns=(times[0].dwHighDateTime << 32) |
                    times[0].dwLowDateTime, executable=image.value)
        recorded = self.identity
        if (not isinstance(recorded, dict)
                or any(type(recorded.get(k)) is not int or recorded[k] != live[k]
                       for k in ('pid', 'creation_time_100ns'))
                or not isinstance(recorded.get('executable'), str)
                or _normalized_path(recorded['executable']) != _normalized_path(live['executable'])
                or api.WaitForSingleObject(process, 0) != 258):
            raise ValueError('owned_identity_mismatch')
        return live

    def inspect_modules(self, *, app_local_dir: str | Path) -> ModuleInspectionTask:
        """Duplicate only the process handle synchronously, then inspect off-thread.

        Call from the guardian thread after its first accepted live frame. All
        owner methods (including close) remain guardian-thread operations.
        """
        self.verify_live_identity()
        directory = _normalized_path(str(app_local_dir))
        if not ntpath.isabs(directory):
            raise ValueError('app-local directory must be absolute')
        task = ModuleInspectionTask()
        api = self._api
        duplicate = W.HANDLE()
        try:
            current = api.GetCurrentProcess()
            # SYNCHRONIZE | PROCESS_QUERY_INFORMATION | PROCESS_VM_READ.
            # No Job duplicate, inheritance, terminate access or CLOSE_SOURCE.
            _check(api.DuplicateHandle(current, self._process, current,
                                       C.byref(duplicate), 0x100410, False, 0))
            task.duplicate_closed.clear()
            worker = threading.Thread(target=_inspect_modules,
                args=(task, api, duplicate.value, directory), daemon=True,
                name='owned-module-inspection')
            worker.start()
        except BaseException as error:
            result = dict(status='unknown', reason='inspection_start_failed',
                          modules={}, error=type(error).__name__)
            if duplicate.value:
                try:
                    _check(api.CloseHandle(duplicate))
                    task.duplicate_closed.set()
                except BaseException:
                    result['reason'] = 'duplicate_close_unconfirmed'
            task.result = result
            task.done.set()
        return task

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

    def exit_code(self) -> int | None:
        if self._closed:
            return self._exit_code
        if not self.wait(0):
            return None
        code = W.DWORD()
        _check(self._api.GetExitCodeProcess(self._process, C.byref(code)))
        self._exit_code = int(code.value)
        return self._exit_code

    def close(self, timeout_ms: int = 5000) -> None:
        timeout_ms = _timeout(timeout_ms)
        if self._closed:
            return
        if self._recovery_only and self._process:
            # Assignment may have failed, so closing the job alone cannot kill it.
            if not self._api.TerminateProcess(self._process, 1):
                error = C.WinError(C.get_last_error())
                if not self.wait(timeout_ms):
                    raise error
        if self._job:
            _check(self._api.CloseHandle(self._job))
            self._job = None
        if self._process and not self.wait(timeout_ms):
            raise TimeoutError("owned-process exit not confirmed; retain handles for retry")
        if self._process:
            self.exit_code()
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
