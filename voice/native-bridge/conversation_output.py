"""Bounded serial speech with real playback-generation fencing.

publish enqueues; it never waits for synthesis. Suppressed business text remains
in the task journal. Counters describe generated/sent audio, never heard audio.
"""

import asyncio
import inspect
from contextlib import aclosing


FIELDS = frozenset({'kind', 'task_id', 'operation_id', 'utterance_id', 'context_version', 'text', 'priority'})
KINDS = frozenset({'local_reply', 'backend_reply', 'task_state', 'error'})


def validate_event(event):
    if not isinstance(event, dict) or set(event) != FIELDS:
        raise ValueError('invalid output event')
    if event['kind'] not in KINDS or not isinstance(event['text'], str) or len(event['text']) > 4000:
        raise ValueError('invalid output text')
    if any(not isinstance(event[k], str) or len(event[k]) > 128 for k in ('task_id', 'operation_id', 'utterance_id')):
        raise ValueError('invalid output identity')
    if type(event['context_version']) is not int or event['context_version'] < 0 or type(event['priority']) is not int:
        raise ValueError('invalid output version')


class OutputArbiter:
    def __init__(self, speech, playback, emit_transcript, is_live):
        self.speech, self.playback = speech, playback
        self.emit_transcript, self.is_live = emit_transcript, is_live
        self._pending = []
        self._wake = asyncio.Event()
        self._idle = asyncio.Event()
        self._idle.set()
        self._closed = False
        self._versions = {}
        self._audio_failed = False
        self._overflow_reported = False
        self.suppressed_count = self.generated_bytes = self.sent_bytes = 0
        self._active = None
        self._worker = asyncio.create_task(self._run())

    @property
    def pending_count(self):
        return len(self._pending)

    def interrupt(self):
        self.playback.interrupt()
        if self._active is not None and not self._active.done():
            self._active.cancel()
        self.suppressed_count += len(self._pending)
        self._pending.clear()
        if self._active is None:
            self._idle.set()

    async def wait_idle(self):
        """Wait for queued/active synthesis to stop; this is not a playback ACK."""
        await self._idle.wait()

    async def publish(self, event):
        validate_event(event)
        if self._closed or not self.is_live():
            return False
        task = event['task_id']
        version = event['context_version']
        if task and version < self._versions.get(task, 0):
            self.suppressed_count += 1
            return False
        if task:
            self._versions[task] = version
        entry = (dict(event), self.playback.generation)
        if len(self._pending) >= 8:
            self.suppressed_count += 1
            worst = max(range(len(self._pending)), key=lambda i: self._pending[i][0]['priority'])
            if event['priority'] < self._pending[worst][0]['priority']:
                self._pending.pop(worst)
            else:
                self._overflow_reported = True
                self._wake.set()
                return False
            self._overflow_reported = True
        self._pending.append(entry)
        self._idle.clear()
        self._pending.sort(key=lambda item: item[0]['priority'])
        self._wake.set()
        return True

    async def _transcript(self, event):
        if self.is_live() and not self._closed:
            result = self.emit_transcript(dict(event))
            if inspect.isawaitable(result):
                await result

    def _current(self, event, generation):
        return (not self._closed and self.is_live() and generation == self.playback.generation
                and event['context_version'] >= self._versions.get(event['task_id'], 0))

    async def _speak(self, event, generation):
        await self._transcript(event)
        async with aclosing(self.speech.synthesize(event['text'])) as chunks:
            async for chunk in chunks:
                self.generated_bytes += len(chunk)
                if not self._current(event, generation):
                    break
                while len(self.playback.data) > 48000 and self._current(event, generation):
                    await asyncio.sleep(.01)
                if self._current(event, generation) and self.playback.put(chunk, generation):
                    self.sent_bytes += len(chunk)

    async def _run(self):
        while not self._closed:
            await self._wake.wait()
            self._wake.clear()
            while self._pending and not self._closed:
                event, generation = self._pending.pop(0)
                if not self._current(event, generation):
                    self.suppressed_count += 1
                    continue
                try:
                    self._active = asyncio.create_task(self._speak(event, generation))
                    await self._active
                except asyncio.CancelledError:
                    if self._closed:
                        raise
                except Exception:
                    if not self._audio_failed:
                        self._audio_failed = True
                        try:
                            await self._transcript(dict(event, kind='error', priority=0,
                                text='Die Audioausgabe ist fehlgeschlagen. Der Auftrag wird weiter beobachtet.'))
                        except Exception:
                            pass
                finally:
                    self._active = None
            if self._overflow_reported:
                self._overflow_reported = False
                try:
                    await self._transcript(dict(kind='error', task_id='', operation_id='', utterance_id='',
                        context_version=0, priority=0, text='Nicht alle Antworten konnten gesprochen werden. Bitte frage nach dem Status.'))
                except Exception:
                    pass
            if not self._pending and self._active is None:
                self._idle.set()

    async def close(self):
        if self._closed:
            return
        self._closed = True
        self.interrupt()
        self._worker.cancel()
        await asyncio.gather(self._worker, return_exceptions=True)
        self._idle.set()
