import asyncio,copy,json,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock,Mock,patch
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import controller

class StoppingStateTests(unittest.IsolatedAsyncioTestCase):
    async def exercise(self,fail_stopping_write):
        transitions=[]; cleanup_seen=[]
        gateway=SimpleNamespace(backend=SimpleNamespace(upstream='http://127.0.0.1:18880',
            identifier='fixture',checkpoint='fixture',context=4096),draining=False)
        engine=Mock();engine.process=None
        engine.start.side_effect=RuntimeError('fixture startup failure')
        async def cleanup(): cleanup_seen.append(True)
        engine.stop=AsyncMock(side_effect=cleanup)
        def record(path,state):
            transitions.append(copy.deepcopy(state))
            if fail_stopping_write and state['phase']=='stopping':raise PermissionError('fixture lock')
        with tempfile.TemporaryDirectory() as d, patch.object(controller,'LOCAL',Path(d)), \
             patch.object(controller,'load_config',return_value=gateway), \
             patch.object(controller,'Engine',return_value=engine), \
             patch.object(controller,'atomic',side_effect=record),patch('socket.socket') as socket:
            socket.return_value.__enter__.return_value.connect_ex.return_value=1
            fixture=Path(d)/'fixture.json'
            fixture.write_text(json.dumps({'engine':{},'minimum_reserve_gib':18}))
            code=await controller.run(fixture,18881)
        self.assertEqual(code,2)
        self.assertEqual([s['phase'] for s in transitions],['starting','stopping','failed'])
        self.assertTrue(all(len(s['profile_sha256'])==64 for s in transitions))
        self.assertEqual(cleanup_seen,[True]);engine.stop.assert_awaited_once()

    async def test_stopping_is_published_before_cleanup(self):
        await self.exercise(False)

    async def test_state_write_error_cannot_skip_cleanup(self):
        await self.exercise(True)

if __name__=='__main__':unittest.main()
