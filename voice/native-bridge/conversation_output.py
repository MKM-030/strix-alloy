"""Bounded serial speech with real playback-generation fencing.

publish enqueues; it never waits for synthesis. Suppressed business text remains
in the task journal. Counters describe generated/sent audio, never heard audio.
"""

import asyncio
import inspect
from contextlib import aclosing
from dataclasses import dataclass
from types import MappingProxyType


FIELDS = frozenset({'kind', 'task_id', 'operation_id', 'utterance_id', 'context_version', 'text', 'priority'})
KINDS = frozenset({'local_reply', 'backend_reply', 'task_state', 'error'})


@dataclass(eq=False)
class _QueuedOutput:
    event: object
    generation: object
    validity: object = None
    disposition: str = "transient"
    completion: object = None
    started: bool = False
    grounded_id: str | None = None
    invalidated: bool = False


class OutputSink:
    """Callable legacy emitter with an additive guarded-publication seam."""
    def __init__(self, arbiter):
        self.arbiter = arbiter

    def interrupt(self):
        self.arbiter.interrupt()

    def interrupt_for_input(self):
        self.arbiter.interrupt_for_input()

    async def publish_deferred(self, event, validity):
        return await self.arbiter.publish_deferred(event, validity)

    async def __call__(self, event):
        return await self.arbiter.publish(event)

    async def publish_guarded(self, event, validity, *, grounded_id=None):
        if grounded_id is None:
            return await self.arbiter.publish_guarded(event, validity)
        return await self.arbiter.publish_guarded(event, validity, grounded_id=grounded_id)

    @property
    def playback_generation(self):
        return self.arbiter.playback.generation

    def invalidate_grounded(self, grounded_id):
        self.arbiter.invalidate_grounded(grounded_id)


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
    def __init__(self, speech, playback, emit_transcript, is_live, *, input_ready=None, control_ready=None):
        self.speech, self.playback = speech, playback
        self.emit_transcript, self.is_live = emit_transcript, is_live
        self.input_ready = input_ready or (lambda: True)
        self.control_ready = control_ready or (lambda: True)
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
        self._active_entry = None
        self._grounded_owner = None
        self._worker = asyncio.create_task(self._run())

    @property
    def pending_count(self):
        return len(self._pending)

    @staticmethod
    def _complete(entry):
        if entry.completion is not None and not entry.completion.done():
            entry.completion.set_result(None)

    def notify_input_changed(self):
        self._wake.set()

    def interrupt_for_input(self):
        self._interrupt(preserve_deferred=True)

    def interrupt(self):
        self._interrupt()

    def _interrupt(self, *, preserve_deferred=False):
        self.playback.interrupt()
        self._grounded_owner = None
        if self._active is not None and not self._active.done():
            self._active.cancel()
        retained = []
        for entry in self._pending:
            if preserve_deferred and entry.disposition == 'deferred' and not entry.started:
                retained.append(entry)
            else:
                self.suppressed_count += 1
                self._complete(entry)
        self._pending[:] = retained
        self._wake.set()
        if not self._pending and self._active is None:
            self._idle.set()

    async def wait_idle(self):
        """Wait for queued/active synthesis to stop; this is not a playback ACK."""
        await self._idle.wait()

    async def publish(self, event):
        return await self._publish(event, None)

    async def publish_guarded(self, event, validity, *, grounded_id=None):
        if not callable(validity):
            raise ValueError('invalid output validity')
        if grounded_id is not None and (not isinstance(grounded_id, str) or not grounded_id or len(grounded_id) > 128):
            raise ValueError('invalid grounded ownership')
        return await self._publish(event, validity, grounded_id=grounded_id)

    def invalidate_grounded(self, grounded_id):
        # This entire compare-and-clear executes without an await. An old ID
        # cannot clear newer/backend PCM, even if a playback generation recurs.
        for entry in tuple(self._pending):
            if entry.grounded_id == grounded_id:
                entry.invalidated = True
                self._pending.remove(entry)
                self._complete(entry)
        active = self._active_entry
        if active is not None and active.grounded_id == grounded_id:
            active.invalidated = True
            if self._grounded_owner == (grounded_id, self.playback.generation):
                self.playback.interrupt()
                self._grounded_owner = None
            if self._active is not None and not self._active.done():
                self._active.cancel()
        self._wake.set()

    async def publish_deferred(self, event, validity):
        if not callable(validity):
            raise ValueError('invalid output validity')
        return await self._publish(event, validity, disposition='deferred')

    async def publish_control(self, event, validity=None, *, wait=False):
        completion = asyncio.get_running_loop().create_future() if wait else None
        accepted = await self._publish(event, validity, disposition='control', completion=completion)
        if accepted and completion is not None:
            await asyncio.shield(completion)
        return accepted

    async def _publish(self, event, validity, *, disposition='transient', completion=None, grounded_id=None):
        validate_event(event)
        entry = _QueuedOutput(MappingProxyType(dict(event)),
            None if disposition == 'deferred' else self.playback.generation, validity, disposition, completion,
            grounded_id=grounded_id)
        if self._closed or not self.is_live() or not self._valid(validity):
            self._complete(entry)
            return False
        task = event['task_id']
        version = event['context_version']
        if task and version < self._versions.get(task, 0):
            self.suppressed_count += 1
            self._complete(entry)
            return False
        if task:
            self._versions[task] = version
        if len(self._pending) >= 8:
            self.suppressed_count += 1
            worst = max(range(len(self._pending)), key=lambda i: self._pending[i].event['priority'])
            if event['priority'] < self._pending[worst].event['priority']:
                self._complete(self._pending.pop(worst))
            else:
                self._overflow_reported = True
                self._wake.set()
                self._complete(entry)
                return False
            self._overflow_reported = True
        self._pending.append(entry)
        self._idle.clear()
        self._pending.sort(key=lambda item: item.event['priority'])
        self._wake.set()
        return True

    async def _transcript(self, event):
        if self.is_live() and not self._closed:
            result = self.emit_transcript(dict(event))
            if inspect.isawaitable(result):
                await result

    @staticmethod
    def _valid(validity):
        try:
            return validity is None or bool(validity())
        except Exception:
            return False

    def _current(self, event, generation, validity=None):
        return (not self._closed and self.is_live() and generation == self.playback.generation
                and event['context_version'] >= self._versions.get(event['task_id'], 0)
                and self._valid(validity))

    def _eligible(self, entry):
        return (not entry.invalidated and not self._closed and self.is_live() and self._valid(entry.validity)
                and (entry.generation is None or entry.generation == self.playback.generation)
                and entry.event['context_version'] >= self._versions.get(entry.event['task_id'], 0))

    def _ready(self, entry):
        return self._valid(self.control_ready if entry.disposition == 'control' else self.input_ready)

    async def _speak(self, entry):
        # Reservation remains inside the bounded queue until this atomic claim.
        # Input interruption before this coroutine runs retains deferred work.
        if entry not in self._pending:
            return
        if not self._eligible(entry):
            self._pending.remove(entry)
            self.suppressed_count += 1
            self._complete(entry)
            return
        if not self._ready(entry):
            return
        if entry.grounded_id is not None:
            # Existing backend/lifecycle PCM is allowed to finish before this
            # answer acquires exclusive ownership of the one physical buffer.
            while self.playback.data and self._eligible(entry) and self._ready(entry):
                await asyncio.sleep(.01)
                if any(other is not entry and other.event['priority'] < entry.event['priority']
                       and self._eligible(other) and self._ready(other) for other in self._pending):
                    return
            if entry not in self._pending or not self._eligible(entry) or not self._ready(entry):
                return
            self._grounded_owner = (entry.grounded_id, entry.generation)
        self._pending.remove(entry)
        entry.started = True
        if entry.generation is None:
            entry.generation = self.playback.generation
        event, generation, validity = entry.event, entry.generation, entry.validity
        def current():
            return not entry.invalidated and self._current(event, generation, validity) and self._ready(entry)
        if not current():
            return
        await self._transcript(event)
        if not current():
            self.suppressed_count += 1
            return
        async with aclosing(self.speech.synthesize(event['text'])) as chunks:
            async for chunk in chunks:
                self.generated_bytes += len(chunk)
                if not current():
                    break
                while len(self.playback.data) > 48000 and current():
                    await asyncio.sleep(.01)
                if current() and self.playback.put(chunk, generation):
                    self.sent_bytes += len(chunk)
        if entry.grounded_id is not None:
            while self.playback.data and current():
                await asyncio.sleep(.01)
            if not current():
                self.invalidate_grounded(entry.grounded_id)

    async def _run(self):
        while not self._closed:
            await self._wake.wait()
            self._wake.clear()
            while self._pending and not self._closed:
                for entry in tuple(self._pending):
                    if not self._eligible(entry):
                        self._pending.remove(entry)
                        self.suppressed_count += 1
                        self._complete(entry)
                entry = next((item for item in self._pending if self._ready(item)), None)
                if entry is None:
                    break
                try:
                    self._active_entry = entry
                    self._active = asyncio.create_task(self._speak(entry))
                    await self._active
                except asyncio.CancelledError:
                    if self._closed:
                        raise
                except Exception:
                    if not self._audio_failed and self._eligible(entry) and self._ready(entry):
                        self._audio_failed = True
                        try:
                            await self._transcript(dict(entry.event, kind='error', priority=0,
                                text='Die Audioausgabe ist fehlgeschlagen. Der Auftrag wird weiter beobachtet.'))
                        except Exception:
                            pass
                finally:
                    if entry.grounded_id is not None and self._grounded_owner == (entry.grounded_id, entry.generation):
                        # Exceptions/cancellation must not orphan guarded PCM.
                        if self.playback.data and self.playback.generation == entry.generation:
                            self.playback.interrupt()
                        self._grounded_owner = None
                    if entry.started or entry not in self._pending:
                        self._complete(entry)
                    self._active = None
                    self._active_entry = None
            if self._overflow_reported and self._valid(self.input_ready):
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
