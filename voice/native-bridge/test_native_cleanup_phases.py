"""Call-owned shutdown diagnostics with held fake stages; no services or media IO."""
import asyncio
import logging
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from native_bridge import Config, LOG, NativeCall
from sdk_sessions import SDKSessionManager
from test_input_lifecycle import Peer


class CleanupPeer(Peer):
    def __init__(self, configuration):
        super().__init__(configuration)
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.release.set()
        self.failure = False

    async def close(self):
        self.entered.set()
        await self.release.wait()
        if self.failure:
            raise RuntimeError('private-transport-address-and-token')
        await super().close()


class OwnedDialog:
    metadata = {}
    _call_owned = True
    must_reset = False

    def __init__(self):
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.release.set()
        self.shutdown_called = False

    async def close(self):
        self.entered.set()
        await self.release.wait()

    async def shutdown(self):
        self.shutdown_called = True


class CleanupPhaseTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.dialog = OwnedDialog()
        with patch('native_bridge.RTCPeerConnection', CleanupPeer):
            self.call = NativeCall(Config(), object(), self.dialog)
        self.messages = []
        messages = self.messages
        class Capture(logging.Handler):
            def emit(self, record):
                messages.append(record.getMessage())
        self.capture = Capture()
        self.old_level = LOG.level
        LOG.setLevel(logging.INFO)
        LOG.addHandler(self.capture)

    async def asyncTearDown(self):
        self.call.peer.release.set()
        self.dialog.release.set()
        if self.call.close_task is not None:
            await asyncio.wait_for(asyncio.gather(self.call.close_task, return_exceptions=True), 1)
        else:
            await self.call.close()
        LOG.removeHandler(self.capture)
        LOG.setLevel(self.old_level)

    def stages(self):
        return [message.split('stage=', 1)[1].split()[0] for message in self.messages
                if message.startswith('Voice cleanup call=') and 'stage=' in message]

    async def test_held_worker_cancel_is_distinguishable_from_peer_close(self):
        entered, cancelled, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
        async def worker():
            entered.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancelled.set()
                await release.wait()
                raise
        self.call.spawn(worker())
        await entered.wait()
        closing = asyncio.create_task(self.call.close())
        try:
            await asyncio.wait_for(cancelled.wait(), 1)
            self.assertIn('workers_begin', self.stages())
            self.assertNotIn('peer_close_begin', self.stages())
        finally:
            release.set()
            await asyncio.wait_for(closing, 1)
        self.assertEqual(self.stages(), ['begin', 'workers_begin', 'workers_end',
            'peer_close_begin', 'peer_close_end', 'dialog_close_begin', 'dialog_close_end',
            'dialog_shutdown_begin', 'dialog_shutdown_end', 'complete'])
        self.assertTrue(self.call.close_complete.is_set())

    async def test_held_peer_and_owned_dialog_keep_capacity_and_identify_await(self):
        self.call.peer.release.clear()
        self.dialog.release.clear()
        closing = asyncio.create_task(self.call.close())
        try:
            await asyncio.wait_for(self.call.peer.entered.wait(), 1)
            self.assertIn('peer_close_begin', self.stages())
            self.assertNotIn('peer_close_end', self.stages())
            self.assertFalse(self.call.close_complete.is_set())
            self.call.peer.release.set()
            await asyncio.wait_for(self.dialog.entered.wait(), 1)
            self.assertIn('peer_close_end', self.stages())
            self.assertIn('dialog_close_begin', self.stages())
            self.assertNotIn('dialog_close_end', self.stages())
            self.assertFalse(self.call.close_complete.is_set())
        finally:
            self.call.peer.release.set()
            self.dialog.release.set()
            await asyncio.wait_for(closing, 1)
        self.assertTrue(self.dialog.shutdown_called)
        self.assertTrue(self.call.close_complete.is_set())

    async def test_failed_peer_keeps_owned_capacity_and_logs_only_phase_and_type(self):
        self.call.peer.failure = True
        active = {self.call}
        manager = SDKSessionManager(Config(), active, lambda: self.call, None)
        session = SimpleNamespace(operation=None, watchers=set(), call=self.call,
                                  pending=[], closed_at=None)
        with self.assertRaises(RuntimeError):
            await manager._finish_close(session)
        self.assertIn('peer_close_failed', self.stages())
        self.assertIn('unresolved', self.stages())
        self.assertNotIn('complete', self.stages())
        self.assertFalse(self.call.close_complete.is_set())
        self.assertIn(self.call, active, 'Peer failure cannot release the SDK capacity reservation')
        self.assertIsNone(session.closed_at)
        self.assertTrue(self.dialog.shutdown_called)
        messages = '\n'.join(self.messages)
        self.assertIn('type=RuntimeError', messages)
        self.assertNotIn('private-transport-address-and-token', messages)

    async def test_failed_unowned_dialog_also_cannot_claim_complete_cleanup(self):
        self.dialog._call_owned = False
        async def failed_close():
            raise RuntimeError('private-dialog-cookie')
        self.dialog.close = failed_close
        with self.assertRaises(RuntimeError):
            await self.call.close()
        self.assertIn('peer_close_end', self.stages())
        self.assertIn('dialog_close_failed', self.stages())
        self.assertIn('unresolved', self.stages())
        self.assertFalse(self.call.close_complete.is_set())
        self.assertNotIn('private-dialog-cookie', '\n'.join(self.messages))


if __name__ == '__main__':
    unittest.main()
