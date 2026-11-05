"""Optional host-emission history. No business authority or retries."""
import asyncio
from decimal import Decimal
import hashlib
import json
import logging
import re
import time


def _grant_diagnostic(stage, conversation_id='', *, http_status=0, elapsed_ms=0,
                      budget_ms=0, response_bytes=0):
    """Fixed metadata only; diagnostics cannot affect the optional grant."""
    if stage not in {'delegated','queued','lease_take','dispatch','http_status','encoding',
            'response_read','response_json','envelope','receipt','transport_accepted','accepted',
            'validation','timeout','cancelled','retired'}:
        return
    conversation_id = (conversation_id if type(conversation_id) is str
        and re.fullmatch('[0-9a-f]{32}',conversation_id) else 'unavailable')
    def bounded(value, limit):
        return min(limit,max(0,value)) if type(value) is int else 0
    try:
        logging.getLogger('voice-bridge').info('Voice presentation grant conversation=%s stage=%s '
            'http_status=%d elapsed_ms=%d budget_ms=%d response_bytes=%d',conversation_id,stage,
            bounded(http_status,599),bounded(elapsed_ms,2147483647),bounded(budget_ms,2000),
            bounded(response_bytes,4097))
    except Exception:
        pass


def _receipt_diagnostic(kind, stage, conversation_id, receipt=None, forms=None, *,
                        http_status=0, transport='unavailable'):
    """Fixed classes/counts only; never receipt values, lexemes or exception text."""
    if kind not in ('grant', 'store') or stage not in (
            'dispatch', 'http_status', 'response_read', 'response_json', 'decoded', 'envelope', 'receipt'):
        return
    try:
        conversation = conversation_id if type(conversation_id) is str and re.fullmatch(
            '[0-9a-f]{32}', conversation_id) else 'unavailable'
        types = []
        for field in ('issuedAtMs', 'expiresAtMs', 'sequence'):
            types.append({int:'integer', float:'float', str:'string', bool:'boolean',
                type(None):'null', dict:'object', list:'array'}.get(type(receipt[field]), 'other')
                if type(receipt) is dict and field in receipt else 'missing')
        counts = [min(32, max(0, forms[name])) if type(forms) is dict
            and type(forms.get(name)) is int else -1 for name in ('plain', 'decimal', 'exponent')]
        status = http_status if type(http_status) is int and 100 <= http_status <= 599 else 0
        transport = transport if type(transport) is str and transport in (
            'before_response', 'response_received') else 'unavailable'
        logging.getLogger('voice-bridge').info('Voice presentation receipt kind=%s stage=%s '
            'conversation=%s issued_type=%s expires_type=%s sequence_type=%s '
            'plain=%d decimal=%d exponent=%d http_status=%d transport=%s',
            kind, stage, conversation, *types, *counts, status, transport)
    except Exception:
        pass


def _decode_native_integer_receipt(raw, kind, conversation_id):
    """Decode only native grant/store responses into exact integer DTO values."""
    if __package__:
        from .caller_binding import _pairs
    else:
        from caller_binding import _pairs
    forms = dict(plain=0, decimal=0, exponent=0)
    def integer(token):
        if len(token) > 64:
            raise ValueError('Invalid native receipt number')
        _, marker, exponent = token.lower().partition('e')
        if marker and not -64 <= int(exponent) <= 64:
            raise ValueError('Invalid native receipt number')
        value = Decimal(token)
        if (not value.is_finite() or abs(value.as_tuple().exponent) > 64
                or not -9007199254740991 <= value <= 9007199254740991
                or value != value.to_integral_value()):
            raise ValueError('Invalid native receipt number')
        form = 'exponent' if 'e' in token.lower() else 'decimal' if '.' in token else 'plain'
        forms[form] = min(32, forms[form] + 1)
        return int(value)
    stage, value = 'response_json', None
    try:
        value = json.loads(raw, object_pairs_hook=_pairs, parse_int=integer,
                           parse_float=integer, parse_constant=integer)
        stage = 'decoded'
        return value
    finally:
        receipt = value.get('result', value) if type(value) is dict else None
        _receipt_diagnostic(kind, stage, conversation_id, receipt, forms)

GRANT_FIELDS = frozenset(('operation', 'requestId', 'appInboundId', 'clientSessionId',
    'userId', 'callerUserId', 'conversationBinding', 'nonceSha256', 'maxAgeSeconds'))
GRANT_RECEIPT_FIELDS = frozenset(('status', 'state', 'requestId', 'conversationId',
    'nonceSha256', 'issuedAtMs', 'expiresAtMs', 'attested', 'scope', 'businessAuthority'))


def valid_grant_request(value):
    def digest(item, size=32):
        return type(item) is str and re.fullmatch('[0-9a-f]{'+str(size)+'}',item) is not None
    if type(value) is not dict or set(value) != GRANT_FIELDS:
        return False
    binding=value['conversationBinding']
    return (value['operation'] == 'attest_presentation_history_v1'
        and value['appInboundId'] == 'scc-local-voice'
        and all(digest(value[key]) for key in ('requestId','clientSessionId','callerUserId'))
        and value['userId'] == 'voice-'+value['clientSessionId']
        and digest(value['nonceSha256'],64)
        and type(value['maxAgeSeconds']) is int and 60 <= value['maxAgeSeconds'] <= 3600
        and type(binding) is dict and set(binding) == {'source','conversationId',
            'creationMessageId','createRequestId','interactionId'}
        and binding['source'] == 'servicenow_create_conversation'
        and all(digest(binding[key]) for key in ('conversationId','creationMessageId','createRequestId','interactionId')))


def valid_grant_receipt(value, request):
    """Native interval only: host wall-clock skew is irrelevant to attestation."""
    return (valid_grant_request(request) and type(value) is dict and set(value) == GRANT_RECEIPT_FIELDS
        and value['status'] == 'success' and value['state'] == 'presentation_history_grant_attested'
        and value['requestId'] == request['requestId']
        and value['conversationId'] == request['conversationBinding']['conversationId']
        and value['nonceSha256'] == request['nonceSha256']
        and type(value['issuedAtMs']) is int and 0 < value['issuedAtMs'] <= 9007199254740991
        and type(value['expiresAtMs']) is int and 0 < value['expiresAtMs'] <= 9007199254740991
        and value['expiresAtMs']-value['issuedAtMs'] == request['maxAgeSeconds']*1000
        and value['attested'] is True and value['scope'] == 'presentation_metadata_only'
        and value['businessAuthority'] is False)


async def issue_presentation_grant(instance_url, provider_token, authorization, request,
                                   *, timeout_seconds=2, http_factory=None):
    """One fixed TLS metadata POST with bounded input/output and no ambient auth."""
    import aiohttp
    # The Native audio process loads only the DTO/outbox via a file import.
    # Caller bootstrap dependencies belong exclusively to this Bridge transport.
    if __package__:
        from .caller_binding import CALLER_INSTANCE_URL, PRESENTATION_GRANT_PATH, valid_authorization
    else:
        from caller_binding import CALLER_INSTANCE_URL, PRESENTATION_GRANT_PATH, valid_authorization
    error='Presentation history unavailable'
    headers={}
    stage, status, size, budget, conversation = 'validation', 0, 0, 0, ''
    receipt = None
    started=time.monotonic()
    try:
        if (instance_url != CALLER_INSTANCE_URL or not valid_authorization(authorization)
                or type(provider_token) is not str or not 0 < len(provider_token) <= 8192
                or any(ord(c) < 32 or ord(c) == 127 for c in provider_token)
                or not valid_grant_request(request)
                or type(timeout_seconds) not in (int,float) or not 0 < timeout_seconds <= 2):
            raise ValueError(error)
        conversation=request['conversationBinding']['conversationId']
        budget=int(timeout_seconds*1000)
        headers.update(Authorization=authorization, token=provider_token,
            Accept='application/json', **{'Content-Type':'application/json','Accept-Encoding':'identity'})
        factory=aiohttp.ClientSession if http_factory is None else http_factory
        stage='dispatch'
        async with asyncio.timeout(timeout_seconds):
            async with factory(cookie_jar=aiohttp.DummyCookieJar(), trust_env=False,
                    auto_decompress=False, skip_auto_headers={'Accept-Encoding'},
                    timeout=aiohttp.ClientTimeout(total=timeout_seconds)) as http:
                async with http.post(instance_url+PRESENTATION_GRANT_PATH, json=request,
                        headers=headers, allow_redirects=False, ssl=True) as response:
                    status=response.status
                    stage='http_status'
                    if status != 200:
                        raise ValueError(error)
                    stage='encoding'
                    if (response.headers.get('Content-Encoding') or not re.match(
                            r'application/json(?:;|$)',response.headers.get('Content-Type',''),re.I)):
                        raise ValueError(error)
                    raw=bytearray()
                    stage='response_read'
                    async for chunk in response.content.iter_chunked(4096):
                        raw.extend(chunk)
                        size=min(len(raw),4097)
                        if len(raw) > 4096:raise ValueError(error)
                    stage='response_json'
                    data=_decode_native_integer_receipt(raw.decode('utf-8'), 'grant', conversation)
                    stage='envelope'
                    if type(data) is not dict or set(data) != {'result'}:
                        raise ValueError(error)
                    receipt=data['result']
                    stage='receipt'
                    if not valid_grant_receipt(receipt,request):
                        raise ValueError(error)
                    result=data['result']
        stage='transport_accepted'
        return result
    except asyncio.CancelledError:
        stage='cancelled'
        raise
    except TimeoutError:
        stage='timeout'
        raise ValueError(error) from None
    except Exception:
        raise ValueError(error) from None
    finally:
        headers.clear()
        authorization=provider_token=None
        if stage in ('envelope', 'receipt'):
            _receipt_diagnostic('grant', stage, conversation, receipt)
        _grant_diagnostic(stage,conversation,http_status=status,
            elapsed_ms=int((time.monotonic()-started)*1000),budget_ms=budget,response_bytes=size)

MAX_EVENTS = 16
FIELDS = frozenset(('version', 'kind', 'local_output_state', 'native_request_binding',
    'owner_id', 'event_id', 'sequence', 'caller_turn_id', 'original_asr_sha256',
    'output_epoch', 'task_revision', 'playback_generation', 'text', 'text_sha256',
    'accepted_samples', 'emitted_samples'))
RECEIPT_FIELDS = frozenset(('status', 'state', 'requestId', 'conversationId', 'sequence',
    'eventId', 'textSha256', 'stored', 'hostEmitted', 'heard', 'promptIncluded'))


def valid_receipt(value, event, conversation_id, request_id=None):
    return (type(value) is dict and set(value) == RECEIPT_FIELDS
        and value['status'] == 'success' and value['state'] == 'presentation_history_stored'
        and type(value['requestId']) is str and re.fullmatch('[0-9a-f]{32}', value['requestId']) is not None
        and (request_id is None or value['requestId'] == request_id)
        and value['conversationId'] == conversation_id
        and type(value['sequence']) is int and value['sequence'] == event['sequence']
        and value['eventId'] == event['event_id'] and value['textSha256'] == event['text_sha256']
        and value['stored'] is True and value['hostEmitted'] is True
        and value['heard'] is False and value['promptIncluded'] is False)


def validate_event(value):
    def integer(name, low, high):
        return type(value.get(name)) is int and low <= value[name] <= high
    def digest(item, size):
        return type(item) is str and re.fullmatch('[0-9a-f]{' + str(size) + '}', item) is not None
    if (type(value) is not dict or set(value) != FIELDS
            or not integer('version', 1, 1) or value['kind'] != 'local_conversation_history'
            or value['local_output_state'] != 'host_emitted'
            or value['native_request_binding'] != 'unavailable'
            or not digest(value['owner_id'], 32) or not digest(value['event_id'], 32)
            or not integer('sequence', 1, MAX_EVENTS)
            or not integer('output_epoch', 1, 2147483647)
            or not integer('task_revision', 1, 2147483647)
            or not integer('playback_generation', 0, 2147483647)
            or not integer('accepted_samples', 1, 43200000)
            or not integer('emitted_samples', 1, 43200000)
            or value['accepted_samples'] != value['emitted_samples']
            or type(value['text']) is not str or not value['text'].strip()
            or len(value['text']) > 2000 or not digest(value['text_sha256'], 64)):
        raise ValueError('Invalid bounded host-emission history')
    caller, raw = value['caller_turn_id'], value['original_asr_sha256']
    if not (caller is None and raw is None or digest(caller, 32) and digest(raw, 64)):
        raise ValueError('Invalid optional caller provenance')
    try:
        encoded = value['text'].encode('utf-8')
        utf16_units = len(value['text'].encode('utf-16-le')) // 2
    except UnicodeError:
        raise ValueError('Invalid history text encoding') from None
    if utf16_units > 2000 or len(encoded) > 8000 or hashlib.sha256(encoded).hexdigest() != value['text_sha256']:
        raise ValueError('Invalid history text digest or size')
    return dict(value)


class PresentationOutbox:
    """Finite single writer; an uncertain attempt disables only this lane."""
    def __init__(self, owner_id):
        if type(owner_id) is not str or not re.fullmatch('[0-9a-f]{32}', owner_id):
            raise ValueError('Invalid history producer')
        self.owner_id, self.sequence, self.disabled = owner_id, 0, False
        self._queue = asyncio.Queue(maxsize=MAX_EVENTS)

    def offer(self, value):
        if self.disabled or self.sequence >= MAX_EVENTS:
            return False
        try:
            event = validate_event(value)
            if event['owner_id'] != self.owner_id or event['sequence'] != self.sequence + 1:
                return False
            self._queue.put_nowait(event)
        except (ValueError, asyncio.QueueFull):
            return False
        self.sequence = event['sequence']
        return True

    async def run(self, publisher, *, wait_ready=None):
        try:
            while not self.disabled:
                # Binding readiness never consumes an event or its publication budget.
                if wait_ready is not None and await wait_ready() is not True:
                    break
                event = await self._queue.get()
                try:
                    # Reset/end can invalidate the captured generation during queue wait.
                    if self.disabled or wait_ready is not None and await wait_ready() is not True:
                        break
                    if await asyncio.wait_for(publisher(event), 2) is not True:
                        self.close()
                except Exception:
                    self.close()
                finally:
                    self._queue.task_done()
        finally:
            self.close()

    def close(self):
        self.disabled = True
        while not self._queue.empty():
            self._queue.get_nowait()
            self._queue.task_done()
