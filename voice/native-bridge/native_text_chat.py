"""Native Text Chat wire adapter for the existing caller-owned Dialog."""
import asyncio
import json
import logging
import re
import uuid
from aiohttp import WSMsgType, web
from assistant_settings import CallSettings

LOG = logging.getLogger(__name__)
PATH = '/text/chat/agent_operator'
ERROR = 'Die Verbindung zu ServiceNow ist derzeit nicht verfügbar.'
MAX_PENDING = 8
MAX_TEXT = 8192


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate key')
        result[key] = value
    return result


class _Session:
    def __init__(self, manager):
        self.manager = manager
        self.ws = self.dialog = self.worker = self.close_task = None
        self.settings = None
        self.closed = False
        self.close_complete = asyncio.Event()
        self.pending = asyncio.Queue(maxsize=MAX_PENDING)
        self.call_id = uuid.uuid4().hex

    async def emit(self, value):
        if not self.closed:
            await self.ws.send_json(value)

    async def reply(self, text):
        if isinstance(text, str) and text.strip():
            await self.emit({'type': 'static', 'content': text, 'message_id': uuid.uuid4().hex})

    async def run(self):
        try:
            await self.emit({'type': 'connected', 'call_sid': self.call_id})
            await self.reply(self.settings.introduction)
            replies = await self.dialog.open()
            metadata = getattr(self.dialog, 'metadata', {})
            keys = ('interaction_id', 'conversation_id')
            if all(isinstance(metadata.get(key), str)
                   and re.fullmatch(r'[0-9a-f]{32}', metadata[key]) for key in keys):
                await self.emit({'type': 'metadata', 'metadata': {key: metadata[key] for key in keys}})
            for reply in replies or []:
                await self.reply(reply)
            while not self.closed:
                text = await self.pending.get()
                # Callback owns delivery; turn's returned list may repeat its replies.
                await self.dialog.turn(text, on_reply=self.reply)
                if getattr(self.dialog, "conversation_ended", False):
                    await self.emit({"type": "end_call"})
                    self.begin_close()
                    return
        except asyncio.CancelledError:
            raise
        except Exception as error:
            LOG.warning('Native Chat worker failed type=%s', type(error).__name__)
            await self.emit({'type': 'error', 'message': ERROR})
            self.begin_close()

    def begin_close(self):
        if self.close_task is None:
            self.closed = True
            self.close_task = asyncio.create_task(self._finish_close())
            self.close_task.add_done_callback(self._observe_close)
        return self.close_task

    @staticmethod
    def _observe_close(task):
        if not task.cancelled() and task.exception() is not None:
            LOG.error('Native Chat owned cleanup unresolved type=%s', type(task.exception()).__name__)

    async def close(self):
        await asyncio.shield(self.begin_close())

    async def _finish_close(self):
        if self.ws is not None:
            await self.ws.close()
        if self.worker is not None:
            self.worker.cancel()
            await asyncio.gather(self.worker, return_exceptions=True)
        if self.dialog is not None:
            await self.dialog.close()
            if self.dialog.must_reset:
                await self.dialog.wait_owned_cleanup()
            await self.dialog.shutdown()
        self.manager.active.discard(self)
        self.manager.sessions.discard(self)
        self.close_complete.set()


class NativeTextChat:
    def __init__(self, config, http, active, authorize, dialog_factory, *,
                 before_create, websocket_factory=web.WebSocketResponse,
                 creating=None, is_stopping=lambda: False):
        self.config, self.http, self.active = config, http, active
        self.authorize, self.dialog_factory = authorize, dialog_factory
        self.before_create, self.websocket_factory = before_create, websocket_factory
        self.creating = creating if creating is not None else set()
        self.is_stopping, self.sessions, self.stopping = is_stopping, set(), False

    async def handle(self, request):
        if self.stopping or self.is_stopping() or self.active:
            raise web.HTTPServiceUnavailable(text=ERROR)
        operation = asyncio.current_task()
        session = _Session(self)
        self.active.add(session)
        self.sessions.add(session)
        self.creating.add(operation)
        try:
            settings = await self.authorize(request, self.config, self.http, with_settings=True)
            if not isinstance(settings, CallSettings):
                raise web.HTTPUnauthorized(text='Chat authorization rejected')
            await self.before_create()
            if self.stopping or self.is_stopping() or session.closed:
                raise web.HTTPServiceUnavailable(text=ERROR)
            session.ws = self.websocket_factory(heartbeat=20, max_msg_size=MAX_TEXT * 6)
            await session.ws.prepare(request)
            session.settings = settings
            session.dialog = self.dialog_factory(self.config, settings)
            session.dialog._call_owned = True
            session.dialog.bind_caller_authorization('Bearer ' + request.query.get('auth_token', ''))
            session.worker = asyncio.create_task(session.run())
            self.creating.discard(operation)
            async for message in session.ws:
                if message.type != WSMsgType.TEXT:
                    break
                try:
                    value = json.loads(message.data, object_pairs_hook=_unique_object)
                    if (type(value) is not dict or set(value) != {'type', 'content'}
                            or value['type'] != 'user_query' or type(value['content']) is not str
                            or not value['content'].strip() or len(value['content']) > MAX_TEXT):
                        raise ValueError('Invalid message')
                    session.pending.put_nowait(value['content'])
                except (ValueError, TypeError, asyncio.QueueFull):
                    await session.emit({'type': 'error', 'message': 'Die Chatnachricht konnte nicht angenommen werden.'})
                    break
            return session.ws
        except web.HTTPException:
            raise
        except asyncio.CancelledError:
            raise
        except Exception as error:
            LOG.warning('Native Chat admission failed type=%s', type(error).__name__)
            if session.ws is None:
                raise web.HTTPServiceUnavailable(text=ERROR) from None
            await session.emit({'type': 'error', 'message': ERROR})
            return session.ws
        finally:
            self.creating.discard(operation)
            if operation.cancelling():
                session.begin_close()
            else:
                await session.close()

    async def shutdown(self):
        self.stopping = True
        await asyncio.gather(*(session.close() for session in tuple(self.sessions)))


def register_native_text_route(app, *, config, active, authorize, before_create,
                               http_key, dialog_factory, creating=None,
                               is_stopping=lambda: False):
    """Resolve the shared HTTP session after application startup."""
    manager = NativeTextChat(config, None, active, authorize, dialog_factory,
                             before_create=before_create, creating=creating,
                             is_stopping=is_stopping)
    async def handle(request):
        manager.http = request.app[http_key]
        return await manager.handle(request)
    app.router.add_get(PATH, handle)
    return manager

