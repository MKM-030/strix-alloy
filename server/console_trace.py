"""Opt-in, bounded console observation; never a response transform or file log.

Decoding/display work is capped, but synchronous stdout can add transport
latency when the console is slow. Keep tracing disabled for benchmarks.
"""
from datetime import datetime, timezone
import json
import logging
import sys
import time
import unicodedata
from uuid import uuid4

MAX_EVENT_BYTES = 256 * 1024
MAX_JSON_BYTES = 256 * 1024
MAX_DISPLAY_CHARS = 64 * 1024
_CREDENTIAL_FIELDS = {'authorization', 'apikey', 'xapikey', 'accesstoken',
                      'clientsecret', 'password', 'backendtoken'}


class _StdoutHandler(logging.StreamHandler):
    def handleError(self, record):
        # A closed/broken console must never change an API response.
        pass


class ConsoleTrace:
    """One console-only logger per gateway session; no root logger propagation."""
    def __init__(self, *, secrets=(), stream=None):
        self.session = uuid4().hex
        self.secrets = tuple(secret for secret in secrets if secret)
        self.logger = logging.Logger('alloy.console_trace', logging.INFO)
        self.logger.propagate = False
        self.handler = _StdoutHandler(sys.stdout if stream is None else stream)
        self.handler.setFormatter(logging.Formatter('%(message)s'))
        self.logger.addHandler(self.handler)

    def start(self, method, path, backend):
        request = RequestTrace(self)
        request.emit('request', method=method, path=path, backend=backend)
        return request

    def _safe(self, value, budget, depth=0):
        if depth >= 32 or budget[0] <= 0:
            return '[TRUNCATED]'
        budget[0] -= 1
        if isinstance(value, str):
            for secret in self.secrets:
                value = value.replace(secret, '[REDACTED]')
            kept = value[:budget[0]]
            budget[0] -= len(kept)
            return kept + ('[TRUNCATED]' if len(kept) < len(value) else '')
        if isinstance(value, dict):
            result = {}
            for key, child in value.items():
                if budget[0] <= 0:
                    result['[TRUNCATED]'] = True
                    break
                safe_key = self._safe(str(key), budget, depth + 1)
                normalized = ''.join(char for char in str(key).lower() if char.isalnum())
                result[safe_key] = ('[REDACTED]' if normalized in _CREDENTIAL_FIELDS
                                    else self._safe(child, budget, depth + 1))
            return result
        if isinstance(value, (list, tuple)):
            result = []
            for child in value:
                if budget[0] <= 0:
                    result.append('[TRUNCATED]')
                    break
                result.append(self._safe(child, budget, depth + 1))
            return result
        return value

    def write(self, request_id, event, fields):
        try:
            row = {'timestamp': datetime.now(timezone.utc).isoformat(timespec='milliseconds')
                   .replace('+00:00', 'Z'), 'session': self.session,
                   'request_id': request_id, 'event': event}
            row.update(self._safe(fields, [MAX_DISPLAY_CHARS]))
            text = json.dumps(row, ensure_ascii=False, separators=(',', ':'))
            # JSON already escapes C0 characters; also escape C1, bidi/format
            # controls and lone surrogates without hiding ordinary Unicode.
            text = ''.join('\\u%04x' % ord(char)
                           if unicodedata.category(char) in ('Cc', 'Cf', 'Cs') else char
                           for char in text)
            encoding = getattr(self.handler.stream, 'encoding', None)
            if encoding:
                try:
                    text.encode(encoding)
                except UnicodeError:
                    text = json.dumps(row, ensure_ascii=True, separators=(',', ':'))
            self.logger.info('[api] %s', text)
        except Exception:
            # Observation is best effort, including unusual payloads/stdio.
            pass


class RequestTrace:
    def __init__(self, console):
        self.console = console
        self.request_id = uuid4().hex
        self.began = time.perf_counter()
        self.status = None
        self.outcome = 'complete'
        self.decoder = None

    def emit(self, event, **fields):
        self.console.write(self.request_id, event, fields)

    def payload(self, value):
        self.emit('payload', payload=value)

    def response(self, status, content_type, content_encoding=''):
        self.status = status
        self.emit('upstream', status=status, content_type=content_type)
        if content_encoding and content_encoding.lower() != 'identity':
            self.emit('trace_skipped', reason='encoded_response')
        elif content_type.split(';', 1)[0].strip().lower() == 'text/event-stream':
            self.decoder = _SSEDecoder(self)
        else:
            self.decoder = _JSONDecoder(self)

    def feed(self, chunk):
        if self.decoder is not None:
            try:
                self.decoder.feed(chunk)
            except Exception:
                self.decoder = None
                self.emit('trace_skipped', reason='decode_error')

    def finish(self, status, outcome=None):
        if self.decoder is not None:
            try:
                self.decoder.finish()
            except Exception:
                self.emit('trace_skipped', reason='decode_error')
        self.emit('end', status=status, outcome=outcome or self.outcome,
                  seconds=round(time.perf_counter() - self.began, 4))

    def value(self, value, event_type=''):
        """Show model-supplied fields only; never infer hidden model reasoning."""
        if not isinstance(value, dict):
            self.emit('response', payload=value)
            return
        kind = value.get('type', event_type)
        self._content(value.get('content'))
        output = value.get('output')
        if isinstance(output, list):
            for item in output:
                if not isinstance(item, dict):
                    continue
                if item.get('type') in ('function_call', 'tool_call'):
                    self.emit('tool_call', payload=item)
                elif item.get('type') == 'reasoning':
                    self._content(item.get('summary'), reasoning=True)
                else:
                    self._content(item.get('content'))
        if value.get('steps') is not None:
            self.emit('stage', stage='returned_steps', payload=value['steps'])
        if value.get('usage') is not None:
            self.emit('usage', usage=value['usage'])
        for choice in value.get('choices', []) if isinstance(value.get('choices'), list) else []:
            if not isinstance(choice, dict):
                continue
            index = choice.get('index', 0)
            delta = choice.get('delta', choice.get('message', {}))
            if isinstance(delta, dict):
                for key in ('content', 'reasoning_content', 'reasoning', 'thinking'):
                    if delta.get(key) is not None:
                        self.emit('answer' if key == 'content' else 'reasoning',
                                  choice=index, field=key, text=delta[key])
                for key in ('tool_calls', 'function_call'):
                    if delta.get(key) is not None:
                        self.emit('tool_call', choice=index, field=key, payload=delta[key])
            if choice.get('text') is not None:
                self.emit('answer', choice=index, text=choice['text'])
            if choice.get('finish_reason') is not None:
                self.emit('finish', choice=index, reason=choice['finish_reason'])
        if kind in ('response.output_text.delta', 'response.reasoning_text.delta',
                    'response.reasoning_summary_text.delta'):
            self.emit('answer' if kind == 'response.output_text.delta' else 'reasoning',
                      field=kind, text=value.get('delta', ''),
                      item_id=value.get('item_id'), output_index=value.get('output_index'))
        elif kind == 'response.function_call_arguments.delta':
            self.emit('tool_call', field=kind, payload=value)
        elif kind in ('response.output_item.added', 'response.output_item.done'):
            item = value.get('item', {})
            if isinstance(item, dict) and item.get('type') in ('function_call', 'tool_call'):
                self.emit('tool_call', field=kind, payload=item)
            else:
                self.emit('stage', stage=kind)
        elif kind == 'content_block_delta':
            delta = value.get('delta', {})
            if isinstance(delta, dict):
                if delta.get('type') == 'text_delta':
                    self.emit('answer', text=delta.get('text', ''), block=value.get('index'))
                elif delta.get('type') == 'thinking_delta':
                    self.emit('reasoning', field='thinking', text=delta.get('thinking', ''),
                              block=value.get('index'))
                elif delta.get('type') == 'input_json_delta':
                    self.emit('tool_call', field='arguments', payload=delta.get('partial_json', ''),
                              block=value.get('index'))
        elif kind == 'content_block_start':
            block = value.get('content_block', {})
            if isinstance(block, dict) and block.get('type') == 'tool_use':
                self.emit('tool_call', payload=block, block=value.get('index'))
            else:
                self.emit('stage', stage=kind, block=value.get('index'))
        elif kind:
            self.emit('stage', stage=kind)
        response = value.get('response', value.get('message'))
        if isinstance(response, dict):
            if response.get('usage') is not None:
                self.emit('usage', usage=response['usage'])
        delta = value.get('delta')
        if isinstance(delta, dict) and delta.get('stop_reason'):
            self.emit('finish', reason=delta['stop_reason'])
        if value.get('error') is not None:
            self.emit('error', payload=value['error'])
        if not kind and not isinstance(value.get('choices'), list):
            self.emit('response', payload=value)

    def _content(self, blocks, reasoning=False):
        if not isinstance(blocks, list):
            return
        for block in blocks:
            if not isinstance(block, dict):
                continue
            kind = block.get('type')
            if kind in ('text', 'output_text', 'summary_text', 'reasoning_text'):
                self.emit('reasoning' if reasoning or kind == 'reasoning_text' else 'answer',
                          field=kind, text=block.get('text', ''))
            elif kind == 'thinking':
                self.emit('reasoning', field=kind, text=block.get('thinking', ''))
            elif kind in ('tool_use', 'function_call', 'tool_call'):
                self.emit('tool_call', payload=block)


class _JSONDecoder:
    def __init__(self, trace):
        self.trace = trace
        self.buffer = bytearray()
        self.dropped = False

    def feed(self, chunk):
        if self.dropped:
            return
        if len(self.buffer) + len(chunk) > MAX_JSON_BYTES:
            self.buffer.clear()
            self.dropped = True
            self.trace.emit('trace_skipped', reason='json_limit', limit_bytes=MAX_JSON_BYTES)
        else:
            self.buffer.extend(chunk)

    def finish(self):
        if self.dropped or not self.buffer:
            return
        try:
            self.trace.value(json.loads(self.buffer))
        except (ValueError, UnicodeError, RecursionError):
            self.trace.emit('trace_skipped', reason='invalid_json')
        self.buffer.clear()


class _SSEDecoder:
    """Incremental bounded SSE parser; recognizes LF, CRLF and CR boundaries."""
    def __init__(self, trace):
        self.trace = trace
        self.line = bytearray()
        self.data = []
        self.event = ''
        self.event_bytes = 0
        self.dropped = False
        self.line_dropped = False
        self.skip_lf = False
        self.first_line = True

    def feed(self, chunk):
        offset = 0
        if self.skip_lf and chunk:
            offset = int(chunk[0] == 10)
            self.skip_lf = False
        while offset < len(chunk):
            cr, lf = chunk.find(b'\r', offset), chunk.find(b'\n', offset)
            ends = [index for index in (cr, lf) if index >= 0]
            end = min(ends) if ends else len(chunk)
            length = end - offset
            if not self.dropped and self.event_bytes + len(self.line) + length > MAX_EVENT_BYTES:
                self.dropped = self.line_dropped = True
                self.line.clear()
                self.data.clear()
                self.trace.emit('trace_skipped', reason='sse_event_limit', limit_bytes=MAX_EVENT_BYTES)
            elif not self.dropped:
                self.line.extend(chunk[offset:end])
            elif length:
                self.line_dropped = True
            if end == len(chunk):
                return
            self._line()
            offset = end + 1
            if chunk[end] == 13:
                if offset < len(chunk) and chunk[offset] == 10:
                    offset += 1
                elif offset == len(chunk):
                    self.skip_lf = True

    def _line(self):
        if self.first_line:
            self.first_line = False
            if self.line.startswith(b'\xef\xbb\xbf'):
                del self.line[:3]
        if not self.line and not self.line_dropped:
            if not self.dropped:
                self._dispatch()
            self.data.clear()
            self.event = ''
            self.event_bytes = 0
            self.dropped = False
        elif not self.dropped:
            self.event_bytes += len(self.line) + 1
            field, separator, value = bytes(self.line).partition(b':')
            if separator and value.startswith(b' '):
                value = value[1:]
            if field == b'data':
                self.data.append(value)
            elif field == b'event':
                self.event = value.decode('utf-8', errors='replace')
        self.line.clear()
        self.line_dropped = False

    def _dispatch(self):
        if not self.data:
            return
        raw = b'\n'.join(self.data)
        if raw.strip() == b'[DONE]':
            self.trace.emit('finish', reason='done')
            return
        try:
            self.trace.value(json.loads(raw), self.event)
        except (ValueError, UnicodeError, RecursionError):
            self.trace.emit('trace_skipped', reason='invalid_sse_json', stage=self.event)

    def finish(self):
        # EOF does not complete an SSE event. Report partial trace data without
        # treating a truncated model stream as a complete message.
        if self.line or self.data or self.line_dropped:
            self.trace.emit('trace_skipped', reason='incomplete_sse_event')
