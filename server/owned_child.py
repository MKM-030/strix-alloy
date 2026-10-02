"""Small process interface backed by a suspended, kill-on-close Windows job."""
import subprocess
import time
from winjob import OwnedProcess

class JobChild:
    def __init__(self, command, *, cwd, env, stdout_path, stderr_path):
        self.command=command
        self.stdout=None
        self.owner=OwnedProcess(command,cwd=cwd,env=env,
            stdout_path=stdout_path,stderr_path=stderr_path)
        self.pid=self.owner.identity['pid']
        try: self.owner.resume()
        except BaseException:
            self.owner.close()
            raise

    def poll(self):
        return self.owner.exit_code()

    def wait(self, timeout=None):
        deadline=None if timeout is None else time.monotonic()+timeout
        while self.poll() is None:
            remaining=1 if deadline is None else deadline-time.monotonic()
            if remaining<=0: raise subprocess.TimeoutExpired(self.command,timeout)
            self.owner.wait(max(1,min(1000,int(remaining*1000))))
        return self.poll()

    def close(self): self.owner.close()
    def kill(self): self.close()

    def contains(self, pid):
        """Check job membership, not merely a matching PID in a state file."""
        import ctypes as C
        from ctypes import wintypes as W
        if type(pid) is not int or pid<=0 or self.owner._job is None:
            return False
        api=C.WinDLL('kernel32',use_last_error=True)
        api.OpenProcess.argtypes=[W.DWORD,W.BOOL,W.DWORD]
        api.OpenProcess.restype=W.HANDLE
        api.IsProcessInJob.argtypes=[W.HANDLE,W.HANDLE,C.POINTER(W.BOOL)]
        api.IsProcessInJob.restype=W.BOOL
        api.CloseHandle.argtypes=[W.HANDLE]; api.CloseHandle.restype=W.BOOL
        handle=api.OpenProcess(0x1000,False,pid)
        if not handle: return False
        try:
            result=W.BOOL()
            return bool(api.IsProcessInJob(handle,self.owner._job,C.byref(result)) and result.value)
        finally: api.CloseHandle(handle)
