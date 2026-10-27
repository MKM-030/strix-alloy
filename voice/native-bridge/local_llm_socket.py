"""Local text SSE mapped onto the existing scoped conversation protocol.

This transport has no ServiceNow tools or business authority. OmniConversation
continues to validate input snapshots, epochs, response identities and deltas.
"""
import asyncio
import json
from pathlib import Path
import re
import uuid

CONTROLLER_CHAT_URL = 'http://127.0.0.1:8840/v1/chat/completions'
CONTROLLER_MODELS_URL = 'http://127.0.0.1:8840/v1/models'


def validate_local_conversation(url, token_file):
    if url == '' and token_file == '':
        return
    if (url != CONTROLLER_CHAT_URL or not isinstance(token_file, (str, Path))
            or not str(token_file) or str(token_file).startswith(('\\\\', '//'))
            or any(ord(char) < 32 for char in str(token_file))
            or not Path(token_file).is_absolute()):
        raise ValueError('Conversation requires the authenticated local controller and token file')


def _token(path):
    try:
        with Path(path).open('rb') as stream:
            raw = stream.read(8196)
        value = raw.decode('utf-8-sig').strip()
        if len(raw) > 8195 or not 16 <= len(value) <= 8192 or any(not 33 <= ord(c) <= 126 for c in value):
            raise ValueError()
        return value
    except (OSError, UnicodeError, ValueError):
        raise ValueError('Local controller credential file is unavailable or invalid') from None


class LocalTextSocket:
    def __init__(self, url, token_file, *, http=None):
        validate_local_conversation(url, token_file)
        if not url:
            raise ValueError('Local conversation endpoint missing')
        self.url, self.token_file, self.http = url, token_file, http
        self.transient_busy = False
        self.events = asyncio.Queue(maxsize=4096)
        self.closed = False
        self.session_id = uuid.uuid4().hex
        self.turn = self.generation = 0
        self._seed = self._snapshot = ''
        self._task = self._record = None

    def _emit(self, kind, **fields):
        if not self.closed:
            self.events.put_nowait(dict(type=kind, session_id=self.session_id, **fields))

    async def send_json(self, event):
        if self.closed:
            raise RuntimeError('Local conversation closed')
        kind = event['type']
        if kind == 'session.start':
            if self._seed or event.get('mode') != 'text':
                raise ValueError('Invalid local conversation start')
            self._seed = event['system_prompt']
            self._emit('session.ready', mode='text')
        elif kind == 'session.update':
            self._snapshot = event['system_prompt_patch']
        elif kind == 'input.text':
            if not self._seed or not self._snapshot or self._task and not self._task.done():
                raise RuntimeError('Local conversation busy or unbound')
            self.turn += 1
            self.generation += 1
            self.transient_busy = False
            record = dict(turn_id=self.turn, generation_id=self.generation, terminal=False)
            self._record = record
            self._emit('input.committed', turn_id=self.turn, text=True)
            self._emit('response.created', turn_id=self.turn, generation_id=self.generation)
            self._task = asyncio.create_task(self._generate(event['text'], record))
        elif kind == 'response.cancel':
            await self._cancel()
        elif kind == 'session.close':
            await self.close()
        elif kind != 'playback.state':
            raise ValueError('Unsupported local conversation operation')

    async def receive_json(self):
        if self.closed:
            raise RuntimeError('Local conversation closed')
        return await self.events.get()

    def _finish(self, record, text='', *, cancelled=False):
        if record['terminal']:
            return
        record['terminal'] = True
        binding = {k:record[k] for k in ('turn_id','generation_id')}
        if cancelled:
            self._emit('response.cancelled', **binding)
        else:
            self._emit('response.text.done', text=text, **binding)
        self._emit('metrics', cancelled=cancelled, **binding)

    async def _generate(self, raw, record):
        parts, total = [], 0
        binding = {k:record[k] for k in ('turn_id','generation_id')}
        try:
            if self.http is None:
                from aiohttp import ClientSession, ClientTimeout
                self.http = ClientSession(trust_env=False, timeout=ClientTimeout(total=25))
            from aiohttp import ClientTimeout
            headers = {'Authorization': 'Bearer ' + _token(self.token_file)}
            # Resolve the central selection for each caller operation. A model
            # switch never causes a retry or a second inference for that input.
            async with self.http.get(CONTROLLER_MODELS_URL, headers=headers,
                    allow_redirects=False, timeout=ClientTimeout(total=3)) as response:
                if response.status == 429:
                    self.transient_busy = True
                payload = await response.content.read(65537)
                models = json.loads(payload)
                if (response.status != 200 or len(payload) > 65536 or type(models) is not dict
                        or type(models.get('data')) is not list or len(models['data']) != 1
                        or type(models['data'][0]) is not dict):
                    raise ValueError('Local controller selection unavailable')
                model = models['data'][0].get('id')
                if type(model) is not str or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}', model):
                    raise ValueError('Invalid local controller selection')
            body = dict(model=model, messages=[
                dict(role='system', content=self._seed),
                dict(role='system', content=self._snapshot),
                dict(role='user', content=raw)], stream=True, max_tokens=192,
                temperature=.3, reasoning_effort='none', enable_thinking=False)
            async with self.http.post(self.url, json=body, headers=headers,
                    allow_redirects=False) as response:
                if response.status == 429:
                    self.transient_busy = True
                if response.status != 200 or 'text/event-stream' not in response.headers.get('Content-Type',''):
                    raise ValueError('Local model unavailable')
                data, event_count, saw_finish, saw_done = [], 0, False, False
                async for line in response.content:
                    if len(line) > 65536:
                        raise ValueError('Oversized local model event')
                    decoded = line.decode('utf-8').rstrip('\r\n')
                    if decoded.startswith('data:'):
                        data.append(decoded[5:].lstrip(' '))
                        if sum(map(len,data)) > 65536:
                            raise ValueError('Oversized local model event')
                        continue
                    if decoded or not data:
                        continue
                    payload, data = '\n'.join(data), []
                    event_count += 1
                    if event_count > 4096:
                        raise ValueError('Too many local model events')
                    if payload == '[DONE]':
                        saw_done = True
                        break
                    item = json.loads(payload)
                    if type(item) is not dict or item.get('error'):
                        raise ValueError('Invalid local model event')
                    choices = item.get('choices')
                    if choices == [] and 'usage' in item:
                        continue
                    if type(choices) is not list or len(choices) != 1:
                        raise ValueError('Invalid local model choice')
                    choice = choices[0]
                    delta = choice.get('delta')
                    if type(delta) is not dict or delta.get('tool_calls') or delta.get('function_call'):
                        raise ValueError('Unexpected tool operation')
                    if delta.get('reasoning_content') or delta.get('reasoning'):
                        raise ValueError('Unexpected hidden reasoning')
                    content = delta.get('content')
                    if content is not None:
                        if type(content) is not str or saw_finish:
                            raise ValueError('Invalid local model text')
                        if content:
                            total += len(content)
                            if total > 16384:
                                raise ValueError('Local model text too long')
                            parts.append(content)
                            self._emit('response.text.delta', delta=content, **binding)
                    reason = choice.get('finish_reason')
                    if reason is not None:
                        if reason not in ('stop','length') or saw_finish:
                            raise ValueError('Invalid local model completion')
                        saw_finish = True
                if not saw_finish or not saw_done or not parts:
                    raise ValueError('Incomplete local model response')
            self._finish(record, ''.join(parts))
        except asyncio.CancelledError:
            self._finish(record, cancelled=True)
            raise
        except Exception:
            record['terminal'] = True
            self._emit('error', code='controller_busy' if self.transient_busy else 'local_model_unavailable')

    async def _cancel(self):
        if self._task is not None and not self._task.done():
            self._task.cancel()
            try:
                await asyncio.wait_for(asyncio.gather(self._task, return_exceptions=True), .5)
            except TimeoutError:
                pass
        if self._record is not None:
            self._finish(self._record, cancelled=True)

    async def close(self):
        if self.closed:
            return
        await self._cancel()
        self.closed = True
        if self.http is not None:
            await self.http.close()
