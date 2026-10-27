"""Real Windows delete-sharing contention against controller.atomic; no lifecycle."""
import ctypes
import asyncio
import json
import os
import socket
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import AsyncMock,Mock,patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from controller import atomic
import controller


@unittest.skipUnless(os.name=='nt','Requires Windows file-sharing semantics')
class AtomicWindowsSharingTests(unittest.TestCase):
    def open_reader_without_delete_share(self,path):
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.CreateFileW.argtypes=(ctypes.c_wchar_p,ctypes.c_uint32,ctypes.c_uint32,
                                    ctypes.c_void_p,ctypes.c_uint32,ctypes.c_uint32,ctypes.c_void_p)
        kernel.CreateFileW.restype=ctypes.c_void_p
        kernel.CloseHandle.argtypes=(ctypes.c_void_p,)
        kernel.CloseHandle.restype=ctypes.c_int
        handle=kernel.CreateFileW(str(path),0x80000000,1,None,3,0x80,None)
        if handle==ctypes.c_void_p(-1).value:raise ctypes.WinError(ctypes.get_last_error())
        return kernel,handle

    def test_reader_released_after_50ms_allows_real_atomic_replace(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'state.json';atomic(path,{'version':'old'})
            kernel,handle=self.open_reader_without_delete_share(path)
            blocked=threading.Event();released=threading.Event();errors=[]
            real_replace=Path.replace
            def observed_replace(source,target):
                try:return real_replace(source,target)
                except OSError as exc:
                    errors.append(exc.winerror);blocked.set();raise
            def release():
                try:
                    if blocked.wait(2):time.sleep(.05)
                finally:
                    kernel.CloseHandle(handle);released.set()
            reader=threading.Thread(target=release);reader.start()
            try:
                with patch.object(Path,'replace',observed_replace):
                    atomic(path,{'version':'new'})
            finally:
                reader.join(3)
                self.assertTrue(released.is_set(),'Test-owned reader must always close')
            self.assertTrue(errors,'At least one real Windows sharing denial must occur')
            self.assertTrue(set(errors)<={5,32,33},errors)
            self.assertEqual(json.loads(path.read_text()),{'version':'new'})
            self.assertEqual(list(Path(directory).glob('state.json.tmp-*')),[])

    def test_persistent_real_reader_raises_without_masking_or_replacing_old_data(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'state.json';atomic(path,{'version':'old'})
            kernel,handle=self.open_reader_without_delete_share(path)
            began=time.monotonic()
            try:
                with self.assertRaises(PermissionError) as caught:
                    atomic(path,{'version':'new'})
            finally:kernel.CloseHandle(handle)
            elapsed=time.monotonic()-began
            self.assertIn(caught.exception.winerror,(5,32,33))
            self.assertGreater(elapsed,.02)
            self.assertLess(elapsed,3.5,'Permanent contention must remain bounded')
            self.assertEqual(json.loads(path.read_text()),{'version':'old'})
            self.assertEqual(list(Path(directory).glob('state.json.tmp-*')),[])


@unittest.skipUnless(os.name=='nt','Requires Windows file-sharing semantics')
class HeartbeatWindowsTests(unittest.IsolatedAsyncioTestCase):
    open_reader_without_delete_share=AtomicWindowsSharingTests.open_reader_without_delete_share

    async def test_short_real_lock_does_not_block_independent_async_work(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'state.json';atomic(path,{'version':'old'})
            kernel,handle=self.open_reader_without_delete_share(path)
            ticks=[];blocked=threading.Event();real_replace=Path.replace
            def observed_replace(source,target):
                try:return real_replace(source,target)
                except PermissionError:blocked.set();raise
            async def release_after_ticks():
                try:
                    deadline=time.monotonic()+1
                    while not blocked.is_set() and time.monotonic()<deadline:await asyncio.sleep(.005)
                    for _ in range(10):
                        ticks.append(time.monotonic());await asyncio.sleep(.005)
                finally:kernel.CloseHandle(handle)
            release=asyncio.create_task(release_after_ticks())
            try:
                with patch.object(Path,'replace',observed_replace):
                    result=await controller.publish_heartbeat(path,{'version':'new'})
                    self.assertGreaterEqual(len(ticks),10)
            finally:await release
            self.assertTrue(blocked.is_set(),'A real Windows denial must occur')
            self.assertTrue(result)
            self.assertEqual(json.loads(path.read_text()),{'version':'new'})

    async def test_persistent_real_lock_skips_then_next_heartbeat_recovers(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'state.json';atomic(path,{'version':'old'})
            kernel,handle=self.open_reader_without_delete_share(path)
            began=time.monotonic()
            try:
                with self.assertLogs('alloy.controller',level='WARNING'):
                    self.assertFalse(await controller.publish_heartbeat(path,{'version':'blocked'}))
                self.assertGreaterEqual(time.monotonic()-began,2)
                self.assertEqual(json.loads(path.read_text()),{'version':'old'})
            finally:kernel.CloseHandle(handle)
            self.assertTrue(await controller.publish_heartbeat(path,{'version':'recovered'}))
            self.assertEqual(json.loads(path.read_text()),{'version':'recovered'})
            self.assertEqual(list(Path(directory).glob('state.json.tmp-*')),[])


class HeartbeatContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_unrelated_os_errors_propagate(self):
        other_windows_error=OSError('invalid parameter');other_windows_error.winerror=87
        for error in (OSError('disk failure'),PermissionError('unclassified denial'),other_windows_error):
            with self.subTest(error=error),patch.object(controller,'atomic',side_effect=error):
                with self.assertRaises(type(error)) as caught:
                    await controller.publish_heartbeat('unused',{})
                self.assertIs(caught.exception,error)

    async def test_windows_lock_code_on_other_os_still_propagates(self):
        error=PermissionError('fixture');error.winerror=32
        with patch.object(controller.os,'name','posix'),patch.object(controller,'atomic',side_effect=error):
            with self.assertRaises(PermissionError):await controller.publish_heartbeat('unused',{})

    async def test_worker_receives_frozen_nested_snapshot(self):
        started=threading.Event();release=threading.Event();captured=[]
        state={'memory':{'available_bytes':123},'requests':[{'count':1}]}
        def worker(path,value):
            started.set()
            if not release.wait(2):raise TimeoutError('test worker not released')
            captured.append(value)
        with patch.object(controller,'atomic',side_effect=worker):
            task=asyncio.create_task(controller.publish_heartbeat('unused',state))
            try:
                deadline=time.monotonic()+1
                while not started.is_set() and time.monotonic()<deadline:await asyncio.sleep(.005)
                self.assertTrue(started.is_set())
                state['memory']['available_bytes']=0;state['requests'][0]['count']=2
            finally:release.set()
            self.assertTrue(await task)
        self.assertEqual(captured,[{'memory':{'available_bytes':123},'requests':[{'count':1}]}])


@unittest.skipUnless(os.name=='nt','Requires Windows error handling')
class HeartbeatRunTests(unittest.IsolatedAsyncioTestCase):
    async def test_periodic_lock_in_startup_and_serving_does_not_stop_owner(self):
        gateway=SimpleNamespace(backend=SimpleNamespace(upstream='http://127.0.0.1:18880',
            identifier='fixture',checkpoint='fixture',context=4096),draining=False,
            active=0,probe=AsyncMock())
        engine=Mock();engine.config={'kind':'halogen'};engine.process=None
        engine.stopped_unexpectedly.return_value=False
        engine.state.return_value={'ready':True};engine.stop=AsyncMock()
        periodic=[];strict=[];owner_thread=threading.get_ident()
        class FixtureSocket(socket.socket):
            def connect_ex(self,address):return 1
        async def serve_fixture(gateway,port,stop):await stop.wait()
        def write_fixture(path,state):
            if threading.get_ident()==owner_thread:
                strict.append(state['phase']);return
            periodic.append(state['phase'])
            if state['phase']=='ready':
                (Path(path).parent/'stop.json').write_text(json.dumps({'run_id':state['run_id']}))
            error=PermissionError('held reader');error.winerror=32;raise error
        with tempfile.TemporaryDirectory() as directory,patch.object(controller,'LOCAL',Path(directory)), \
             patch.object(controller,'load_config',return_value=gateway), \
             patch.object(controller,'Engine',return_value=engine), \
             patch.object(controller,'serve',side_effect=serve_fixture), \
             patch.object(controller,'atomic',side_effect=write_fixture), \
             patch.object(controller,'available_gib',return_value=32), \
             patch('host_frames.frame',return_value={'available_bytes':32*1024**3,'commit_headroom_bytes':32*1024**3}), \
             patch('socket.socket',FixtureSocket):
            fixture=Path(directory)/'profile.json'
            fixture.write_text(json.dumps({'engine':{},'minimum_reserve_gib':18}))
            with self.assertLogs('alloy.controller',level='WARNING'):
                code=await controller.run(fixture,18881)
        self.assertEqual(code,0)
        self.assertEqual(periodic,['starting','ready'])
        self.assertEqual(strict,['starting','stopping','stopped'])
        engine.stop.assert_awaited_once()


if __name__=='__main__':unittest.main()
