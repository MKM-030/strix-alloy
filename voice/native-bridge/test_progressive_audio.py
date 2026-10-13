import asyncio
import unittest
from native_bridge import Config, Dialog, NativeCall


class ProgressiveAudioTests(unittest.IsolatedAsyncioTestCase):
    async def test_speech_failure_does_not_abandon_inflight_backend_turn(self):
        released, failed = asyncio.Event(), asyncio.Event()
        class DelayedDialog(Dialog):
            def __init__(self):
                super().__init__(Config())
                self.reads = 0
                self.final_read = False
            async def open(self):
                return []
            async def close(self):
                pass
            async def request(self, method, path, **kwargs):
                if path == '/api/message':
                    return {'accepted':True}
                self.reads += 1
                if self.reads == 1:
                    return {'cursor':1,'busy':True,'events':[{'id':1,'kind':'bot','text':'Ankündigung'}]}
                await released.wait()
                self.final_read = True
                return {'cursor':2,'busy':False,'events':[]}
        class FailedSpeech:
            async def transcribe(self, pcm):
                return 'Bitte helfen'
            async def synthesize(self, text):
                failed.set()
                raise RuntimeError('Speech service unavailable')
                yield b''
        dialog = DelayedDialog()
        call = NativeCall(Config(), FailedSpeech(), dialog)
        with self.assertLogs('native-voice', level='WARNING'):
            task = call.spawn(call.process_turns())
            await call.turns.put((0, bytes(16000)))
            try:
                await asyncio.wait_for(failed.wait(), .3)
                self.assertFalse(task.done())
                self.assertFalse(dialog.final_read)
                released.set()
                await asyncio.wait_for(task, .3)
                self.assertTrue(dialog.final_read)
            finally:
                released.set()
                await call.close()

    async def test_complete_announcement_is_spoken_before_backend_is_input_ready(self):
        released = asyncio.Event()
        announced = asyncio.Event()
        questioned = asyncio.Event()
        class DelayedDialog(Dialog):
            def __init__(self):
                super().__init__(Config())
                self.reads = 0
            async def open(self):
                return []
            async def close(self):
                pass
            async def request(self, method, path, **kwargs):
                if path == '/api/message':
                    return {'accepted':True}
                self.reads += 1
                if self.reads == 1:
                    return {'cursor':1,'busy':True,'events':[{'id':1,'kind':'bot','text':'Ankündigung'}]}
                await released.wait()
                return {'cursor':2,'busy':False,'events':[{'id':2,'kind':'bot','text':'Frage'}]}
        class Speech:
            async def transcribe(self, pcm):
                return 'Bitte helfen'
            async def synthesize(self, text):
                (announced if text == 'Ankündigung' else questioned).set()
                yield bytes(960)
        call = NativeCall(Config(), Speech(), DelayedDialog())
        call.spawn(call.process_turns())
        await call.turns.put((0, bytes(16000)))
        try:
            await asyncio.wait_for(announced.wait(), .3)
            self.assertFalse(released.is_set())
            self.assertFalse(questioned.is_set())
            released.set()
            await asyncio.wait_for(questioned.wait(), .3)
        finally:
            released.set()
            await call.close()

    async def test_configured_greeting_is_spoken_once_when_backend_has_none(self):
        self.assertIn('greeting', Config.__dataclass_fields__, 'configured native greeting missing')
        spoken = []
        recorded = []
        class EmptyDialog:
            metadata = {}
            async def open(self):
                return []
            def record_greeting(self, text):
                recorded.append(text)
            async def close(self):
                pass
        class Speech:
            async def synthesize(self, text):
                spoken.append(text)
                yield bytes(960)
        call = NativeCall(Config(greeting='Hallo, ich helfe Ihnen bei der Laptopdemo.'), Speech(), EmptyDialog())
        call.spawn(call.process_turns())
        try:
            await asyncio.sleep(.03)
            self.assertEqual(spoken, ['Hallo, ich helfe Ihnen bei der Laptopdemo.'])
            self.assertEqual(recorded, spoken)
        finally:
            await call.close()

    async def test_greeting_is_skipped_if_user_already_started_speaking(self):
        self.assertIn('greeting', Config.__dataclass_fields__)
        spoken = []
        recorded = []
        class EmptyDialog:
            metadata = {}
            async def open(self):
                return []
            def record_greeting(self, text):
                recorded.append(text)
            async def close(self):
                pass
        class Speech:
            async def synthesize(self, text):
                spoken.append(text)
                yield bytes(960)
        call = NativeCall(Config(greeting='Hallo'), Speech(), EmptyDialog())
        call.playback.interrupt()
        call.spawn(call.process_turns())
        try:
            await asyncio.sleep(.03)
            self.assertEqual(spoken, [])
            self.assertEqual(recorded, [])
        finally:
            await call.close()

    async def test_genuine_backend_greeting_is_not_added_to_first_message_history(self):
        spoken, recorded = [], []
        class BackendDialog:
            metadata = {}
            async def open(self):
                return ['Begrüßung aus ServiceNow']
            def record_greeting(self, text):
                recorded.append(text)
            async def close(self):
                pass
        class Speech:
            async def synthesize(self, text):
                spoken.append(text)
                yield bytes(960)
        call = NativeCall(Config(greeting='Fallback'), Speech(), BackendDialog())
        call.spawn(call.process_turns())
        try:
            await asyncio.sleep(.03)
            self.assertEqual(spoken, ['Begrüßung aus ServiceNow'])
            self.assertEqual(recorded, [])
        finally:
            await call.close()


if __name__ == '__main__':
    unittest.main()
