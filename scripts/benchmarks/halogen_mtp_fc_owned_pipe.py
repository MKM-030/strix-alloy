"""Pinned Windows binary-pipe owner for a fresh root-owned resident FC relay.

Import launches nothing. Ownership, guards, cancellation and close are restricted
to the constructor's guardian thread. Non-daemon I/O workers have only pipe/thread
handles; they never resume, adopt, terminate or close a child/job. ROOT must supply
an external cancellation event and a bounded live guard, and call close in finally.

This subclass uses winjob private ctypes structures/API. Its exact source pin is
mandatory: changing server/winjob.py requires explicit review and a new pin here.
The pinned bytes are compiled directly, avoiding a verify-then-import reread.
Local job termination does not prove Docker daemon/container termination; ROOT
must independently stop/inspect/remove only its sealed full container identity.
"""
import ctypes as C
from ctypes import wintypes as W
import hashlib
import math
import os
from pathlib import Path
import queue
import re
import stat
import subprocess
import threading
import time
import types


WINJOB_SHA256 = "3d2db1c5c8ea3846152a0073dd4ed324a47ffd36ac63bf8f48cc52e39b0d4d4c"
WINJOB_PATH = Path(__file__).absolute().parents[2] / "server" / "winjob.py"
MAX_IO_BYTES = 65536
MAX_TOTAL_BYTES = 1048576


def _sealed_bytes(path, wanted):
    if not isinstance(wanted, str) or not re.fullmatch(r"[0-9a-f]{64}", wanted):
        raise ValueError("independent lowercase SHA256 required")
    path = Path(path)
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or not 1 <= before.st_size <= 262144:
        raise ValueError("bounded unchanged regular source required")
    with path.open("rb") as stream:
        opened = os.fstat(stream.fileno())
        raw = stream.read(262145)
        after = os.fstat(stream.fileno())
    identity = lambda value: (value.st_dev, value.st_ino, value.st_size,
                              value.st_mtime_ns, value.st_ctime_ns)
    if (identity(before) != identity(opened) or identity(before) != identity(after)
            or identity(before) != identity(path.lstat()) or len(raw) != before.st_size
            or hashlib.sha256(raw).hexdigest() != wanted):
        raise ValueError("source bytes/identity differ from independent pin")
    return raw


_base = types.ModuleType("halogen_mtp_fc_owned_pipe_pinned_winjob")
_base.__file__ = str(WINJOB_PATH)
exec(compile(_sealed_bytes(WINJOB_PATH, WINJOB_SHA256), str(WINJOB_PATH), "exec"), _base.__dict__)


class _SecurityAttributes(C.Structure):
    _fields_ = [("nLength", W.DWORD), ("lpSecurityDescriptor", C.c_void_p),
                ("bInheritHandle", W.BOOL)]


def _pipe_api(api):
    declarations = {
        "CreatePipe": ([C.POINTER(W.HANDLE), C.POINTER(W.HANDLE),
                        C.POINTER(_SecurityAttributes), W.DWORD], W.BOOL),
        "SetHandleInformation": ([W.HANDLE, W.DWORD, W.DWORD], W.BOOL),
        "ReadFile": ([W.HANDLE, C.c_void_p, W.DWORD, C.POINTER(W.DWORD), C.c_void_p], W.BOOL),
        "WriteFile": ([W.HANDLE, C.c_void_p, W.DWORD, C.POINTER(W.DWORD), C.c_void_p], W.BOOL),
        "GetCurrentThread": ([], W.HANDLE),
        "CancelSynchronousIo": ([W.HANDLE], W.BOOL),
    }
    for name, (args, result) in declarations.items():
        function = getattr(api, name)
        function.argtypes, function.restype = args, result
    return api


class _Operation:
    def __init__(self, value):
        self.value, self.result, self.error = value, None, None
        self.done = threading.Event()


class _Worker:
    """No child/job authority. Guardian owns duplicated real thread handle."""
    def __init__(self, api, handle, mode):
        self.api, self.handle, self.mode = api, handle, mode
        self.queue = queue.Queue(maxsize=1)
        self.stop = threading.Event()
        self.ready = threading.Event()
        self.thread_handle = None
        self.start_error = None
        self.started = False
        self.thread = threading.Thread(target=self._run, daemon=False,
                                       name="owned-fc-pipe-" + mode)

    def start(self):
        self.thread.start()
        self.started = True

    def _run(self):
        try:
            current = self.api.GetCurrentProcess()
            handle = W.HANDLE()
            _base._check(self.api.DuplicateHandle(current, self.api.GetCurrentThread(), current,
                                                  C.byref(handle), 0, False, 2))
            self.thread_handle = handle.value
        except BaseException as error:
            self.start_error = error
            return
        finally:
            self.ready.set()
        while not self.stop.is_set():
            try:
                operation = self.queue.get(timeout=.02)
            except queue.Empty:
                continue
            try:
                count = W.DWORD()
                if self.mode == "read":
                    buffer = C.create_string_buffer(operation.value)
                    good = self.api.ReadFile(self.handle, buffer, operation.value, C.byref(count), None)
                    if not good:
                        code = C.get_last_error()
                        if code in (109, 232):  # Broken pipe / pipe is being closed.
                            operation.result = b""
                        else:
                            raise C.WinError(code)
                    else:
                        if count.value > operation.value:
                            raise OSError("pipe read exceeded admitted extent")
                        operation.result = bytes(buffer.raw[:count.value])
                else:
                    buffer = C.create_string_buffer(operation.value, len(operation.value))
                    _base._check(self.api.WriteFile(self.handle, buffer, len(operation.value),
                                                   C.byref(count), None))
                    if not 0 < count.value <= len(operation.value):
                        raise OSError("pipe write made no bounded progress")
                    operation.result = int(count.value)
            except BaseException as error:
                operation.error = error
            finally:
                operation.done.set()


class _Reader:
    def __init__(self, owner):
        self.owner = owner

    def read(self, size):
        return self.owner._operate("read", size)


class _Writer:
    def __init__(self, owner):
        self.owner = owner

    def write(self, data):
        return self.owner._operate("write", data)

    def flush(self):
        # Win32 anonymous pipes have no user-space buffer to flush. A blocking
        # FlushFileBuffers would wait for the child and defeat guarded deadlines.
        self.owner._assert_guardian()
        self.owner._guard(allow_terminal=True)


class OwnedBinaryProcess(_base.OwnedProcess):
    """CREATE_SUSPENDED + retained job, raw transport reader/writer, bounded I/O.

    Required source_sha256 is the independent SHA256 of THIS adapter file.
    live_guard must return promptly; it runs only on the guardian. cancel_event
    may be set externally but only the guardian changes child/job ownership.
    lifetime_seconds and io_timeout_seconds are finite bounds <=45 seconds.
    set_io_deadline sets a tighter absolute time.monotonic deadline per phase.
    """
    def __init__(self, argv, *, cwd, env, stderr_path, source_sha256,
                 live_guard, cancel_event, lifetime_seconds=45,
                 io_timeout_seconds=45, max_io_bytes=MAX_IO_BYTES,
                 max_total_read_bytes=MAX_TOTAL_BYTES, max_total_write_bytes=MAX_TOTAL_BYTES):
        if os.name != "nt":
            raise OSError("owned FC binary pipes require Windows")
        _sealed_bytes(Path(__file__).absolute(), source_sha256)
        if not callable(live_guard) or not callable(getattr(cancel_event, "is_set", None)):
            raise ValueError("bounded live guard and external cancellation event required")
        for value in (lifetime_seconds, io_timeout_seconds):
            if type(value) not in (int, float) or not math.isfinite(value) or not 0 < value <= 45:
                raise ValueError("finite positive I/O/lifetime bound <=45 seconds required")
        if type(max_io_bytes) is not int or not 1 <= max_io_bytes <= MAX_IO_BYTES:
            raise ValueError("per-operation byte limit must be1..65536")
        if any(type(value) is not int or not 1 <= value <= MAX_TOTAL_BYTES
               for value in (max_total_read_bytes, max_total_write_bytes)):
            raise ValueError("finite total byte limits must be1..1048576")
        if not isinstance(argv, list) or not argv or any(
                not isinstance(value, str) or "\0" in value for value in argv):
            raise ValueError("argv must be a nonempty list of NUL-free strings")
        if not isinstance(env, dict) or any(
                not isinstance(key, str) or not key or "=" in key or "\0" in key
                or not isinstance(value, str) or "\0" in value for key, value in env.items()):
            raise ValueError("invalid child environment")
        executable = str(Path(argv[0]).resolve(strict=True))
        directory = str(Path(cwd).resolve(strict=True))
        if not Path(executable).is_file() or not Path(directory).is_dir():
            raise ValueError("invalid executable or working directory")
        # Thread objects remain distinct even if a numeric ident is later reused.
        self._guardian = threading.current_thread()
        self._live_guard, self._cancel = live_guard, cancel_event
        self.deadline = time.monotonic() + lifetime_seconds
        self.io_timeout_seconds, self.io_deadline = io_timeout_seconds, None
        self.max_io_bytes = max_io_bytes
        self._limits = {"read": max_total_read_bytes, "write": max_total_write_bytes}
        self._totals = {"read": 0, "write": 0}
        self._workers, self._pipe_handles, self._child_handles = {}, {}, []
        self._io_busy, self._pipes_closed, self._failure = False, False, None
        self.cleanup_evidence = {"child_terminal": False, "workers_joined": False,
                                 "pipes_closed": False, "remote_cleanup_proven": False}
        self._api = api = _pipe_api(_base._api())
        self._job = self._process = self._thread = None
        self._resumed = self._closed = False
        self._recovery_only = True
        self._exit_code = self.identity = None
        self.reader, self.writer = _Reader(self), _Writer(self)
        stderr = None
        try:
            self._job = _base._check(api.CreateJobObjectW(None, None))
            limits = _base._ExtendedLimit()
            limits.BasicLimitInformation.LimitFlags = 0x2000
            _base._check(api.SetInformationJobObject(self._job, 9, C.byref(limits), C.sizeof(limits)))
            attributes = _SecurityAttributes(C.sizeof(_SecurityAttributes), None, True)
            for mode in ("read", "write"):
                read_end, write_end = W.HANDLE(), W.HANDLE()
                _base._check(api.CreatePipe(C.byref(read_end), C.byref(write_end),
                                            C.byref(attributes), 0))
                parent, child = (read_end.value, write_end.value) if mode == "read" else (write_end.value, read_end.value)
                self._pipe_handles[mode] = parent
                self._child_handles.append(child)
                _base._check(api.SetHandleInformation(parent, 1, 0))
            import msvcrt
            stderr = open(Path(stderr_path).resolve(), "xb", buffering=0)
            stderr_handle = msvcrt.get_osfhandle(stderr.fileno())
            os.set_handle_inheritable(stderr_handle, True)
            handles = (W.HANDLE * 3)(self._child_handles[1], self._child_handles[0], stderr_handle)
            required = C.c_size_t()
            good = api.InitializeProcThreadAttributeList(None, 1, 0, C.byref(required))
            if good or C.get_last_error() != 122 or not 0 < required.value <= 65536:
                raise OSError("unexpected process attribute sizing result")
            storage = C.create_string_buffer(required.value)
            _base._check(api.InitializeProcThreadAttributeList(storage, 1, 0, C.byref(required)))
            try:
                _base._check(api.UpdateProcThreadAttribute(storage, 0, 0x20002, handles,
                                                          C.sizeof(handles), None, None))
                startup = _base._StartupEx()
                startup.StartupInfo.cb = C.sizeof(startup)
                startup.StartupInfo.dwFlags = 0x100
                startup.StartupInfo.hStdInput, startup.StartupInfo.hStdOutput, startup.StartupInfo.hStdError = handles
                startup.lpAttributeList = C.cast(storage, C.c_void_p)
                information = _base._ProcessInfo()
                command = C.create_unicode_buffer(subprocess.list2cmdline([executable, *argv[1:]]))
                entries = [key + "=" + env[key] for key in sorted(env, key=str.casefold)]
                environment = C.create_unicode_buffer("\0".join(entries) + "\0\0")
                _base._check(api.CreateProcessW(executable, command, None, None, True,
                                               0x4 | 0x400 | 0x08000000 | 0x80000,
                                               environment, directory, C.byref(startup.StartupInfo),
                                               C.byref(information)))
                self._process, self._thread = information.hProcess, information.hThread
            finally:
                api.DeleteProcThreadAttributeList(storage)
            _base._check(api.AssignProcessToJobObject(self._job, self._process))
            times = [W.FILETIME() for _ in range(4)]
            _base._check(api.GetProcessTimes(self._process, *(C.byref(value) for value in times)))
            image, length = C.create_unicode_buffer(32768), W.DWORD(32768)
            _base._check(api.QueryFullProcessImageNameW(self._process, 0, image, C.byref(length)))
            self.identity = {"pid": int(information.dwProcessId),
                             "creation_time_100ns": (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime,
                             "executable": image.value}
            self._recovery_only = False
            self._close_child_pipe_handles()
            stderr.close()
            stderr = None
            for mode in ("read", "write"):
                worker = _Worker(api, self._pipe_handles[mode], mode)
                self._workers[mode] = worker
                worker.start()
                if not worker.ready.wait(5) or worker.start_error is not None:
                    raise RuntimeError("owned pipe worker setup failed") from worker.start_error
            self._guard(require_resumed=False)
        except BaseException as original:
            try:
                self.close()
                if stderr is not None:
                    stderr.close()
            except BaseException as cleanup:
                cleanup.owner = self
                if stderr is not None:
                    self._retained_stderr = stderr
                raise cleanup from original
            raise

    def _assert_guardian(self):
        if threading.current_thread() is not self._guardian:
            raise RuntimeError("child/job ownership and I/O belong to the guardian thread")

    def _guard(self, require_resumed=True, allow_terminal=False):
        self._assert_guardian()
        if self._closed or self._pipes_closed or self._failure is not None:
            raise RuntimeError("owned binary pipe is closed or failed")
        if require_resumed and not self._resumed:
            raise RuntimeError("owned child has not resumed")
        now = time.monotonic()
        if (self._cancel.is_set() or now >= self.deadline
                or (self.io_deadline is not None and now >= self.io_deadline)):
            raise TimeoutError("owned binary pipe cancelled or lifetime expired")
        code = self.exit_code()
        if code is None:
            self.verify_live_identity()
        elif not allow_terminal or code != 0:
            raise RuntimeError("owned binary child is terminal: " + str(code))
        # A successfully exited retained child may have a complete final frame
        # buffered in OUR pipe. Read/drain and completed-operation checks accept
        # that state; a new write never does. Codec/container guards still apply.
        self._live_guard()
        now = time.monotonic()
        if (self._cancel.is_set() or now >= self.deadline
                or (self.io_deadline is not None and now >= self.io_deadline)):
            raise TimeoutError("owned binary guard returned after cancellation/deadline")

    def set_io_deadline(self, deadline):
        self._assert_guardian()
        if type(deadline) not in (int, float) or not math.isfinite(deadline) or not time.monotonic() < deadline <= self.deadline:
            raise ValueError("future monotonic phase deadline within owned lifetime required")
        self.io_deadline = deadline

    def clear_io_deadline(self):
        self._assert_guardian()
        self.io_deadline = None

    def resume(self):
        self._assert_guardian()
        self._guard(require_resumed=False)
        return super().resume()

    def verify_live_identity(self):
        self._assert_guardian()
        return super().verify_live_identity()

    def wait(self, timeout_ms=0):
        self._assert_guardian()
        return super().wait(timeout_ms)

    def exit_code(self):
        self._assert_guardian()
        return super().exit_code()

    def inspect_modules(self, **kwargs):
        # The base helper creates a daemon inspection worker outside this adapter's
        # cancellation contract; this relay owner deliberately does not expose it.
        raise RuntimeError("module inspection is outside the owned binary-pipe contract")

    def _operate(self, mode, value):
        self._assert_guardian()
        if self._io_busy:
            raise RuntimeError("concurrent or reentrant pipe operation refused")
        if mode == "read":
            if type(value) is not int or not 1 <= value <= self.max_io_bytes:
                raise ValueError("bounded positive binary read extent required")
            size = value
        else:
            if not isinstance(value, (bytes, bytearray, memoryview)):
                raise ValueError("binary write buffer required")
            extent = value.nbytes if isinstance(value, memoryview) else len(value)
            if not 1 <= extent <= self.max_io_bytes:
                raise ValueError("bounded nonempty binary write required")
            value = bytes(value)
            size = len(value)
            if not 1 <= size <= self.max_io_bytes:
                raise ValueError("bounded nonempty binary write required")
        if self._totals[mode] + size > self._limits[mode]:
            raise ValueError("owned pipe total byte budget exceeded")
        self._io_busy = True
        try:
            self._guard(allow_terminal=mode == "read")
            deadline = min(self.deadline, time.monotonic() + self.io_timeout_seconds,
                           self.io_deadline if self.io_deadline is not None else self.deadline)
            if time.monotonic() >= deadline:
                raise TimeoutError("owned binary I/O deadline already expired")
            operation = _Operation(value)
            worker = self._workers[mode]
            if not worker.thread.is_alive():
                raise RuntimeError("owned pipe worker is terminal")
            worker.queue.put_nowait(operation)
            while not operation.done.wait(.01):
                self._guard(allow_terminal=mode == "read")
                if time.monotonic() >= deadline:
                    raise TimeoutError("owned binary I/O deadline expired")
            self._guard(allow_terminal=True)
            if time.monotonic() >= deadline:
                raise TimeoutError("owned binary I/O completed after deadline")
            if operation.error is not None:
                raise operation.error
            self._totals[mode] += len(operation.result) if mode == "read" else operation.result
            return operation.result
        except BaseException as original:
            self._failure = type(original).__name__ + ": " + str(original)
            try:
                self.close()
            except BaseException as cleanup:
                cleanup.owner = self
                raise cleanup from original
            raise
        finally:
            self._io_busy = False

    def _close_child_pipe_handles(self):
        while self._child_handles:
            _base._check(self._api.CloseHandle(self._child_handles[-1]))
            self._child_handles.pop()

    def close(self, timeout_ms=5000):
        """Guardian kills/proves child terminal, cancels I/O, joins, closes pipes.

        Any unconfirmed step raises with owner retained for guardian-thread retry.
        cleanup_evidence never claims independent remote-container cleanup.
        """
        self._assert_guardian()
        timeout_ms = _base._timeout(timeout_ms)
        if self._pipes_closed:
            return
        try:
            # Base close uses retained handles, including direct termination if
            # assignment failed. It must prove local child exit before pipe close.
            super().close(timeout_ms)
            self.cleanup_evidence["child_terminal"] = True
            self.cleanup_evidence["exit_code"] = self._exit_code
            self.cleanup_evidence["identity"] = self.identity
            self._close_child_pipe_handles()
            for worker in self._workers.values():
                worker.stop.set()
                if worker.started and worker.thread.is_alive() and worker.thread_handle:
                    if not self._api.CancelSynchronousIo(worker.thread_handle):
                        code = C.get_last_error()
                        if code != 1168:  # No currently pending synchronous I/O.
                            raise C.WinError(code)
            deadline = time.monotonic() + timeout_ms / 1000
            for worker in self._workers.values():
                if worker.started:
                    # Retry cancellation during bounded joins: a worker may have
                    # moved from its queue wait into ReadFile/WriteFile after the
                    # first cancellation found no pending synchronous operation.
                    while worker.thread.is_alive() and time.monotonic() < deadline:
                        if worker.thread_handle:
                            if not self._api.CancelSynchronousIo(worker.thread_handle):
                                code = C.get_last_error()
                                if code != 1168:
                                    raise C.WinError(code)
                        worker.thread.join(min(.02, max(0, deadline - time.monotonic())))
                    if worker.thread.is_alive():
                        raise TimeoutError("pipe worker exit not confirmed; retain handles for retry")
            self.cleanup_evidence["workers_joined"] = True
            for worker in self._workers.values():
                if worker.thread_handle:
                    _base._check(self._api.CloseHandle(worker.thread_handle))
                    worker.thread_handle = None
            for mode in tuple(self._pipe_handles):
                _base._check(self._api.CloseHandle(self._pipe_handles[mode]))
                del self._pipe_handles[mode]
            stderr = getattr(self, "_retained_stderr", None)
            if stderr is not None:
                stderr.close()
                self._retained_stderr = None
            self._pipes_closed = True
            self.cleanup_evidence["pipes_closed"] = True
        except BaseException as error:
            self.cleanup_evidence["error"] = type(error).__name__ + ": " + str(error)
            self.cleanup_evidence["workers_alive"] = {
                mode: worker.thread.is_alive() for mode, worker in self._workers.items()}
            error.owner = self
            raise
