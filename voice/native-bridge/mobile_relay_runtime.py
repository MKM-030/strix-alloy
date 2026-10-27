"""Owned, hash-pinned loopback relay process; never detached from Native lifetime."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import subprocess
import uuid

from aiohttp import ClientSession,ClientTimeout
from mobile_relay import MobileRelayUnavailable


class MobileRelayRuntime:
    def __init__(self,config):
        self.config=config
        self.process=None
        self.startup_id=uuid.uuid4().hex

    def __repr__(self):
        return '<MobileRelayRuntime owned='+str(self.process is not None)+'>'

    def ensure_running(self):
        if self.process is None or self.process.poll() is not None:
            raise MobileRelayUnavailable()

    async def start(self):
        if self.process is not None:
            raise MobileRelayUnavailable()
        try:
            # Hash the actual executable immediately before launching that same path.
            path=Path(self.config.relay_executable)
            with path.open('rb') as handle:
                actual=hashlib.file_digest(handle,'sha256').hexdigest()
            if actual!=self.config.relay_executable_sha256:
                raise MobileRelayUnavailable()
            self.process=subprocess.Popen([str(path),'--listen',self.config.listen_address,
                '--health',self.config.status_address,'--relay-ip',self.config.relay_address,
                '--registry',self.config.registry_file,'--realm',self.config.realm,
                '--startup-id',self.startup_id,'--exit-on-stdin-eof'],
                stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            async with asyncio.timeout(3):
                async with ClientSession(trust_env=False,timeout=ClientTimeout(total=.3)) as http:
                    while True:
                        self.ensure_running()
                        try:
                            async with http.get('http://'+self.config.status_address+'/health',
                                                allow_redirects=False) as response:
                                if response.status==200:
                                    raw=await response.content.read(4097)
                                    if len(raw)>4096:
                                        raise MobileRelayUnavailable()
                                    value=json.loads(raw)
                                    if (isinstance(value,dict) and value.get('status')=='ready'
                                            and value.get('startup_id')==self.startup_id):
                                        self.ensure_running()
                                        return
                                    # A foreign listener cannot satisfy this invocation.
                                    raise MobileRelayUnavailable()
                        except MobileRelayUnavailable:
                            raise
                        except (OSError,ValueError,TimeoutError):
                            pass
                        except Exception:
                            # Connection refused while the owned child starts.
                            self.ensure_running()
                        await asyncio.sleep(.05)
        except BaseException as error:
            await self.close()
            if isinstance(error,asyncio.CancelledError):
                raise
            raise MobileRelayUnavailable() from None

    def abort(self):
        """Synchronously withdraw the owned relay when registry revocation fails."""
        process=self.process
        if process is None:
            return
        if process.stdin is not None:
            try:process.stdin.close()
            except OSError:pass
        if process.poll() is None:
            try:process.terminate()
            except OSError:pass

    async def close(self):
        process=self.process
        if process is None:
            return
        if process.stdin is not None:
            try:process.stdin.close()
            except OSError:pass
        for _ in range(20):
            if process.poll() is not None:
                self.process=None
                return
            await asyncio.sleep(.05)
        try:process.terminate()
        except OSError:pass
        for _ in range(10):
            if process.poll() is not None:
                self.process=None
                return
            await asyncio.sleep(.05)
        try:process.kill()
        except OSError:pass
        for _ in range(10):
            if process.poll() is not None:
                self.process=None
                return
            await asyncio.sleep(.05)
        # Keep the owned handle if termination unexpectedly remains unresolved.
        raise MobileRelayUnavailable()
        # Only this Popen-owned process is addressed; no process-name matching.
