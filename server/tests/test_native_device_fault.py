"""No engine/network: known native fault must retire generation readiness."""
import asyncio
from collections import deque
import json
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import AsyncMock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from controller import Engine
from gateway import Gateway

class NativeDeviceFaultTest(unittest.IsolatedAsyncioTestCase):
    async def test_owned_device_fault_latches_unavailability_without_replaying_work(self):
        engine = Engine.__new__(Engine)
        engine.config = {'kind': 'native'}
        engine.native_device_lost = threading.Event()
        gateway = Gateway.__new__(Gateway)
        gateway._draining = False
        gateway.waiters = deque()
        gateway.active = 1
        gateway.completed = 0
        gateway.cancelled = 0
        gateway.backend = type('Backend', (), {'identifier': 'fixture', 'checkpoint': 'fixture', 'context': 32768})()
        gateway.probe = AsyncMock(return_value={'status': 'ok'})
        engine.gateway = gateway
        state = {'phase': 'ready'}
        # Ordinary failures and quoted/user-like text do not establish device loss.
        engine.observe_output('HTTP500')
        engine.observe_output('user says vk::Queue::submit: ErrorDeviceLost')
        engine.publish_unavailability(state)
        self.assertEqual(state['phase'], 'ready')
        self.assertFalse(gateway.draining)
        waiter = asyncio.get_running_loop().create_future()
        gateway.waiters.append(waiter)
        engine.observe_output('2357.41.848.122 E srv  update_slots: decode() failed: vk::Queue::submit: ErrorDeviceLost\n')
        engine.publish_unavailability(state)
        self.assertEqual(state, {'phase': 'unavailable', 'backend_failure': 'device_lost'})
        self.assertTrue(gateway.draining)
        self.assertFalse(waiter.result())
        self.assertFalse(await gateway.acquire_slot())
        self.assertEqual(gateway.active, 1)  # Already-running work is not declared failed/cancelled.
        self.assertEqual(gateway.cancelled, 0)
        # Even a misleading successful backend health cannot clear the generation latch.
        response = await gateway.health(None)
        self.assertEqual(response.status, 503)
        self.assertEqual(json.loads(response.body)['status'], 'unavailable')
        engine.publish_unavailability(state)
        self.assertTrue(gateway.draining)

if __name__ == '__main__':
    unittest.main()
