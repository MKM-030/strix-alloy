"""Optional host-emission history. No business authority, retries or logging."""
import asyncio
import hashlib
import json
import re

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
        from .caller_binding import CALLER_INSTANCE_URL, PRESENTATION_GRANT_PATH, valid_authorization, _pairs
    else:
        from caller_binding import CALLER_INSTANCE_URL, PRESENTATION_GRANT_PATH, valid_authorization, _pairs
    error='Presentation history unavailable'
    headers={}
    try:
        if (instance_url != CALLER_INSTANCE_URL or not valid_authorization(authorization)
                or type(provider_token) is not str or not 0 < len(provider_token) <= 8192
                or any(ord(c) < 32 or ord(c) == 127 for c in provider_token)
                or not valid_grant_request(request)
                or type(timeout_seconds) not in (int,float) or not 0 < timeout_seconds <= 2):
            raise ValueError(error)
        headers.update(Authorization=authorization, token=provider_token,
            Accept='application/json', **{'Content-Type':'application/json','Accept-Encoding':'identity'})
        factory=aiohttp.ClientSession if http_factory is None else http_factory
        async with asyncio.timeout(timeout_seconds):
            async with factory(cookie_jar=aiohttp.DummyCookieJar(), trust_env=False,
                    auto_decompress=False, skip_auto_headers={'Accept-Encoding'},
                    timeout=aiohttp.ClientTimeout(total=timeout_seconds)) as http:
                async with http.post(instance_url+PRESENTATION_GRANT_PATH, json=request,
                        headers=headers, allow_redirects=False, ssl=True) as response:
                    if (response.status != 200 or response.headers.get('Content-Encoding')
                            or not re.match(r'application/json(?:;|$)',response.headers.get('Content-Type',''),re.I)):
                        raise ValueError(error)
                    raw=bytearray()
                    async for chunk in response.content.iter_chunked(4096):
                        raw.extend(chunk)
                        if len(raw) > 4096:raise ValueError(error)
                    data=json.loads(raw.decode('utf-8'), object_pairs_hook=_pairs,
                        parse_constant=lambda _: (_ for _ in ()).throw(ValueError(error)))
                    if (type(data) is not dict or set(data) != {'result'}
                            or not valid_grant_receipt(data['result'],request)):
                        raise ValueError(error)
                    result=data['result']
        return result
    except asyncio.CancelledError:
        raise
    except Exception:
        raise ValueError(error) from None
    finally:
        headers.clear()
        authorization=provider_token=None

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

    async def run(self, publisher):
        try:
            while not self.disabled:
                event = await self._queue.get()
                try:
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
