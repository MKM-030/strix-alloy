"""Unqualified REV:N-compatible WebSocket text protocol, isolated from Native.

The caller supplies a socket with async send_json/receive_json/close methods.
This module never opens sockets, starts models, submits business actions, or
claims durable resume, authentication, audio qualification or spoken delivery.
"""
import asyncio
import math
import struct


class ProtocolError(Exception):
    pass


def require(condition):
    if not condition:
        raise ProtocolError('Optional Omni protocol state or message is invalid.')


def text(value, limit=4000):
    require(type(value) is str and 0 < len(value) <= limit)
    return value


def identifier(value):
    require(type(value) is int and value > 0)
    return value


def pcm16_input(payload):
    """Wire representation only: raw mono PCM16 LE at 16 kHz, without header."""
    require(type(payload) is bytes and 0 < len(payload) <= 64000 and len(payload) % 2 == 0)
    return payload


def decode_audio_frame(frame, *, generation_id):
    """Parse optional mono 24 kHz PCM16; no playback/delivery acknowledgment."""
    require(type(frame) is bytes and 16 <= len(frame) <= 1048592 and frame[:4] == b'OMNI')
    generation, sequence, length = struct.unpack('<III', frame[4:16])
    require(generation > 0 and length == len(frame) - 16 and length % 2 == 0)
    if generation != generation_id:
        return None
    return sequence, frame[16:]


class TextSession:
    def __init__(self, socket, *, handshake_seconds=10, turn_seconds=30,
                 control_seconds=1, cleanup_seconds=.25):
        for value, maximum in ((handshake_seconds, 10), (turn_seconds, 30),
                               (control_seconds, 1), (cleanup_seconds, 1)):
            require(type(value) in (int, float) and math.isfinite(value) and 0 < value <= maximum)
        self.socket = socket
        self.handshake_seconds, self.turn_seconds = handshake_seconds, turn_seconds
        self.control_seconds, self.cleanup_seconds = control_seconds, cleanup_seconds
        self.lock = asyncio.Lock()
        self.ready = False
        self.closed = False
        self.active = False
        self.cancel_requested = False
        self.last_turn = 0
        self.last_generation = 0

    @staticmethod
    async def _until(operation, deadline):
        # wait_for/timeout can themselves wait indefinitely for a transport that
        # suppresses cancellation. Stop awaiting it at the absolute deadline.
        task = asyncio.create_task(operation)
        def consume(done):
            if not done.cancelled():
                done.exception()
        try:
            done, _ = await asyncio.wait({task}, timeout=max(0, deadline - asyncio.get_running_loop().time()))
            if not done:
                raise TimeoutError()
            return task.result()
        finally:
            if not task.done():
                task.cancel()
                task.add_done_callback(consume)

    async def _receive(self, deadline):
        event = await self._until(self.socket.receive_json(), deadline)
        require(type(event) is dict and type(event.get('type')) is str)
        require(event['type'] != 'error')
        return event

    async def _failed(self):
        self.ready = False
        self.closed = True
        try:
            await self._until(self.socket.close(), asyncio.get_running_loop().time() + self.cleanup_seconds)
        except Exception:
            pass

    async def start(self, system_prompt):
        require(not self.ready and not self.closed)
        text(system_prompt, 12000)
        deadline = asyncio.get_running_loop().time() + self.handshake_seconds
        try:
            async with asyncio.timeout_at(deadline):
                await self._until(self.socket.send_json({'type': 'session.start', 'mode': 'text',
                                             'system_prompt': system_prompt, 'language': 'de'}), deadline)
                event = await self._receive(deadline)
                require(event['type'] == 'session.ready' and event.get('mode') == 'text')
                self.session_id = text(event.get('session_id'), 128)
                self.ready = True
        except BaseException as error:
            await self._failed()
            if isinstance(error, asyncio.CancelledError):
                raise
            raise ProtocolError('Optional Omni handshake failed.') from None

    async def turn(self, request_id, user_text, *, on_delta=None):
        text(request_id, 128)
        text(user_text)
        require(on_delta is None or callable(on_delta))
        async with self.lock:
            require(self.ready and not self.closed)
            self.active = True
            self.cancel_requested = False
            turn_id = generation_id = None
            done = None
            cancelled = False
            streamed = ''
            deadline = asyncio.get_running_loop().time() + self.turn_seconds
            try:
                async with asyncio.timeout_at(deadline):
                    await self._until(self.socket.send_json({'type': 'input.text', 'text': user_text}), deadline)
                    while True:
                        event = await self._receive(deadline)
                        kind = event['type']
                        incoming_generation = event.get('generation_id')
                        if incoming_generation is not None:
                            identifier(incoming_generation)
                            if incoming_generation <= self.last_generation:
                                continue
                        if kind == 'input.committed':
                            require(turn_id is None and event.get('text') is True)
                            turn_id = identifier(event.get('turn_id'))
                            require(turn_id > self.last_turn)
                        elif kind == 'response.created':
                            require(turn_id is not None and event.get('turn_id') == turn_id and generation_id is None)
                            generation_id = identifier(incoming_generation)
                            require(generation_id > self.last_generation)
                        else:
                            require(generation_id is not None and incoming_generation == generation_id)
                            if kind == 'response.text.delta':
                                delta = text(event.get('delta'), 16384)
                                if on_delta is not None:
                                    require(done is None and len(streamed) + len(delta) <= 16384)
                                    streamed += delta
                                    if not cancelled and not self.cancel_requested:
                                        await on_delta(delta)
                            elif kind == 'response.text.done':
                                require(done is None and type(event.get('text')) is str and len(event['text']) <= 16384)
                                done = event['text']
                            elif kind == 'response.cancelled':
                                require(event.get('turn_id') == turn_id)
                                cancelled = True
                            elif kind == 'metrics':
                                require(event.get('turn_id') == turn_id and type(event.get('cancelled')) is bool)
                                cancelled = cancelled or event['cancelled'] or self.cancel_requested
                                require(cancelled or done is not None)
                                if on_delta is not None and not cancelled:
                                    require(streamed.strip() == done.strip())
                                self.last_turn, self.last_generation = turn_id, generation_id
                                return {'request_id': request_id, 'turn_id': turn_id, 'generation_id': generation_id,
                                        'text': '' if cancelled else done, 'cancelled': cancelled}
                            else:
                                require(False)
            except BaseException as error:
                await self._failed()
                if isinstance(error, asyncio.CancelledError):
                    raise
                raise ProtocolError('Optional Omni turn failed; no reply accepted.') from None
            finally:
                self.active = False

    async def cancel(self):
        require(self.ready and not self.closed)
        if self.active:
            self.cancel_requested = True
            try:
                await self._until(self.socket.send_json({'type': 'response.cancel'}),
                                  asyncio.get_running_loop().time() + self.control_seconds)
            except BaseException as error:
                await self._failed()
                if isinstance(error, asyncio.CancelledError):
                    raise
                raise ProtocolError('Optional Omni cancellation transport failed.') from None

    async def update_context(self, patch):
        text(patch, 12000)
        deadline = asyncio.get_running_loop().time() + self.control_seconds
        try:
            async with asyncio.timeout_at(deadline), self.lock:
                require(self.ready and not self.closed)
                # Appends a system message; no server acknowledgment and no
                # implicit reply. A new turn is always a separate caller action.
                await self._until(self.socket.send_json({'type': 'session.update', 'system_prompt_patch': patch}), deadline)
        except BaseException as error:
            await self._failed()
            if isinstance(error, asyncio.CancelledError):
                raise
            raise ProtocolError('Optional Omni context transport failed.') from None

    async def playback_state(self, generation_id, played_ms):
        require(self.ready and not self.closed)
        identifier(generation_id)
        require(type(played_ms) is int and 0 <= played_ms <= 3600000)
        if generation_id != self.last_generation or self.active:
            return False
        try:
            await self._until(self.socket.send_json({'type': 'playback.state', 'generation_id': generation_id, 'played_ms': played_ms}),
                              asyncio.get_running_loop().time() + self.control_seconds)
        except BaseException as error:
            await self._failed()
            if isinstance(error, asyncio.CancelledError):
                raise
            raise ProtocolError('Optional Omni playback transport failed.') from None
        return True

    async def close(self):
        if not self.closed:
            try:
                await self._until(self.socket.send_json({'type': 'session.close'}),
                                  asyncio.get_running_loop().time() + self.control_seconds)
            except BaseException as error:
                if isinstance(error, asyncio.CancelledError):
                    raise
                raise ProtocolError('Optional Omni close transport failed.') from None
            finally:
                await self._failed()
