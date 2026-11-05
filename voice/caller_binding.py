"""Private native caller identity and bounded owned conversation bootstrap.

No client identity assertion or JWT payload is an identity source. Each call
uses its original bearer only for its bounded owned bootstrap; nothing here
logs, caches or persists it.
"""
import asyncio
from dataclasses import dataclass, field
import json
import logging
import re
import time
import aiohttp

CALLER_HEADER = 'X-SCC-Voice-Authorization'
CALLER_INSTANCE_URL = 'https://soprasteriaassvsdemo14.service-now.com'
CALLER_CREATE_PATH = '/api/sn_voice_aia/local_voice_caller/create'
PRESENTATION_GRANT_PATH = '/api/global/scc_voice_context/updates'
PRESENTATION_GRANT_OPERATION = 'attest_presentation_history_v1'
PRESENTATION_GRANT_PURPOSE = (CALLER_INSTANCE_URL + PRESENTATION_GRANT_PATH, PRESENTATION_GRANT_OPERATION)
CALLER_SERVICE_ID = '8aa131d793f787105c8132d47aba1095'
CALLER_AGENT_ID = 'a6337ddf93f787105c8132d47aba1058'
CALLER_PROFILE_ID = 'c623e20f93374354e7f2b9fa6aba1081'
CALLER_CREATE_FAILURE_CONTRACT = 'scc_local_caller_create_v1'
_ID = re.compile(r'[0-9a-f]{32}\Z')
_BEARER = re.compile(r'Bearer [A-Za-z0-9._~+/-]+=*\Z', re.I)
_FIELDS = {'version', 'service_id', 'context_profile', 'user_id', 'user_name',
           'email', 'email_mapping_unique'}


_CREATE_FAILURE_STAGES = frozenset({
    'pre_dispatch_validation', 'client_open', 'request_transport', 'http_status',
    'response_encoding', 'response_type', 'response_read', 'response_oversize',
    'response_json', 'transport_close', 'created_tuple_invalid', 'cancelled', 'unexpected'})
_CREATE_DISPATCH_STATES = frozenset({'not_dispatched', 'may_have_dispatched', 'response_received'})
_CREATE_LOG = logging.getLogger('voice-bridge')


def _create_request_ids(request):
    if (type(request) is not dict
            or set(request) != {'version','requestId','clientSessionId','clientMessageId'}
            or type(request['version']) is not int or request['version'] != 1):
        return ('', '', '')
    values = tuple(request[k] for k in ('requestId','clientSessionId','clientMessageId'))
    if (any(type(value) is not str or not _ID.fullmatch(value) for value in values)
            or len(set(values)) != 3):
        return ('', '', '')
    return values


@dataclass(frozen=True)
class CallerCreateFailureReceipt:
    """Bounded transport facts; an auth refusal alone never proves absence."""
    reason: str
    outcome: str
    stage: str
    http_status: int
    dispatch_state: str
    close_completed: bool
    contract: str
    request_id: str = field(repr=False)
    client_session_id: str = field(repr=False)
    client_message_id: str = field(repr=False)

    def __post_init__(self):
        ids = (self.request_id, self.client_session_id, self.client_message_id)
        correlated = (all(type(value) is str and _ID.fullmatch(value) for value in ids)
                      and len(set(ids)) == 3)
        empty = ids == ('', '', '')
        if (type(self.reason) is not str or self.reason not in {
                'caller_create_unauthorized','caller_create_access_denied','caller_create_unavailable'}
                or type(self.outcome) is not str or self.outcome not in {'unknown','not_created'}
                or type(self.stage) is not str or self.stage not in _CREATE_FAILURE_STAGES
                or type(self.http_status) is not int or not (self.http_status == 0 or 100 <= self.http_status <= 599)
                or type(self.dispatch_state) is not str or self.dispatch_state not in _CREATE_DISPATCH_STATES
                or type(self.close_completed) is not bool or not (correlated or empty)
                or type(self.contract) is not str):
            raise ValueError('Invalid caller CREATE failure receipt')
        expected_reason = ('caller_create_unauthorized' if self.http_status == 401 else
                           'caller_create_access_denied' if self.http_status == 403 else
                           'caller_create_unavailable')
        no_dispatch = self.dispatch_state == 'not_dispatched' and self.http_status == 0
        rejected = self.dispatch_state == 'response_received' and self.http_status == 403 and self.close_completed
        if (self.reason != expected_reason
                or self.outcome == 'unknown' and self.contract != ''
                or self.outcome == 'not_created' and (not correlated
                    or self.contract != CALLER_CREATE_FAILURE_CONTRACT or not (no_dispatch or rejected))):
            raise ValueError('Invalid caller CREATE failure receipt')


class CallerCreateFailure(ValueError):
    """Fixed public error plus an immutable, private structural receipt."""
    def __init__(self, receipt):
        if type(receipt) is not CallerCreateFailureReceipt:
            raise ValueError('Invalid caller CREATE failure receipt')
        self.receipt = receipt
        super().__init__('Native caller CREATE unavailable')


def _create_failure(request, stage, http_status, dispatch_state, close_completed=False,
                    *, negative_proof=False):
    ids = _create_request_ids(request)
    if type(http_status) is not int or not 100 <= http_status <= 599:
        http_status = 0
    reason = ('caller_create_unauthorized' if http_status == 401 else
              'caller_create_access_denied' if http_status == 403 else
              'caller_create_unavailable')
    no_dispatch = dispatch_state == 'not_dispatched' and http_status == 0
    rejected = (negative_proof and dispatch_state == 'response_received'
                and http_status == 403 and close_completed)
    not_created = bool(ids[0]) and (no_dispatch or rejected)
    receipt = CallerCreateFailureReceipt(reason, 'not_created' if not_created else 'unknown',
        stage, http_status, dispatch_state, close_completed,
        CALLER_CREATE_FAILURE_CONTRACT if not_created else '', *ids)
    _log_create_failure(stage, http_status, dispatch_state)
    return CallerCreateFailure(receipt)


def _validated_create_denial(data, request):
    """Only our exact pre-handler envelope can prove a received denial."""
    if (type(data) is not dict or set(data) != {'result'} or type(data['result']) is not dict
            or set(data['result']) != {'status','failure'} or data['result']['status'] != 'failure'):
        return False
    failure = data['result']['failure']
    required = {'contract','version','outcome','reason','requestId','clientSessionId',
                'clientMessageId','serviceId','contextProfile'}
    return (type(failure) is dict and set(failure) == required
        and failure['contract'] == CALLER_CREATE_FAILURE_CONTRACT
        and type(failure['version']) is int and failure['version'] == 1
        and failure['outcome'] == 'not_created' and failure['reason'] == 'access_denied'
        and failure['requestId'] == request['requestId']
        and failure['clientSessionId'] == request['clientSessionId']
        and failure['clientMessageId'] == request['clientMessageId']
        and failure['serviceId'] == CALLER_SERVICE_ID and failure['contextProfile'] == CALLER_PROFILE_ID)


def _log_create_failure(stage, http_status, dispatch_state):
    if type(stage) is not str or stage not in _CREATE_FAILURE_STAGES:
        stage = 'unexpected'
    if type(http_status) is not int or not 100 <= http_status <= 599:
        http_status = 0  # No valid HTTP status was observed.
    if type(dispatch_state) is not str or dispatch_state not in _CREATE_DISPATCH_STATES:
        dispatch_state = 'may_have_dispatched'
    _CREATE_LOG.warning('Caller CREATE failed stage=%s http_status=%d dispatch_state=%s',
                        stage, http_status, dispatch_state)


@dataclass(frozen=True)
class CallerBinding:
    user_id: str = field(repr=False)
    email: str = field(repr=False)


class PresentationAttestationLease:
    """Explicitly split authority for one owner's fixed metadata operation."""
    __slots__ = ('_value', '_deadline', '_owner', '_timer')

    def __init__(self, authorization, deadline, owner):
        self._value, self._deadline, self._owner = authorization, deadline, owner
        self._timer = asyncio.get_running_loop().call_later(
            max(0, deadline-time.monotonic()), self.clear)

    def __repr__(self):
        return 'PresentationAttestationLease(redacted)'

    @property
    def available(self):
        return bool(self._value) and time.monotonic() < self._deadline

    def take(self, owner, purpose):
        try:
            if (owner is not self._owner or type(purpose) is not tuple or purpose != PRESENTATION_GRANT_PURPOSE
                    or not self.available):
                raise ValueError('Presentation history unavailable')
            return self._value, self._deadline-time.monotonic(), self._deadline
        finally:
            self.clear()

    def clear(self):
        self._value, self._owner = '', None
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None


class CallerBootstrapCredential:
    """One CREATE/refresh; optional explicit split lease, with active erasure."""
    __slots__ = ('_value', '_deadline', '_timer', '_on_expire', '_create_claimed', '_presentation_delegated')

    def __init__(self, authorization, *, seconds, on_expire=None):
        if not valid_authorization(authorization) or type(seconds) not in (int,float) or not 0 < seconds <= 45:
            raise ValueError('Native caller bootstrap unavailable')
        self._value = authorization
        self._create_claimed = False
        self._presentation_delegated = False
        self._deadline = time.monotonic() + seconds
        self._on_expire = on_expire
        self._timer = asyncio.get_running_loop().call_later(seconds, self._expire)

    def __repr__(self):
        return 'CallerBootstrapCredential(redacted)'

    @property
    def available(self):
        return bool(self._value) and time.monotonic() < self._deadline

    def take(self):
        if not self.available:
            self.clear()
            raise ValueError('Native caller bootstrap unavailable')
        value, remaining, deadline = self._value, self._deadline - time.monotonic(), self._deadline
        self.clear()
        return value, remaining, deadline

    def claim_create(self):
        """One owned CREATE use; keep the distinct refresh ticket and timer."""
        if self._create_claimed or not self.available:
            raise ValueError('Native caller bootstrap unavailable')
        self._create_claimed = True
        return self._value, self._deadline-time.monotonic(), self._deadline

    def delegate_presentation(self, owner):
        """Split once before primary clear; never renew the original deadline."""
        if self._presentation_delegated or not self.available or owner is None:
            raise ValueError('Presentation history unavailable')
        self._presentation_delegated = True
        return PresentationAttestationLease(self._value, self._deadline, owner)

    def clear(self):
        self._value = ''
        self._on_expire = None
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

    def _expire(self):
        callback = self._on_expire
        self.clear()
        if callback is not None:
            callback()


def valid_authorization(value):
    return type(value) is str and len(value) <= 8192 and bool(_BEARER.fullmatch(value))


def validated_created(data, request):
    error = 'Native caller CREATE unavailable'
    if (type(data) is not dict or set(data) != {'result'} or type(data['result']) is not dict
            or set(data['result']) != {'status','created'} or data['result']['status'] != 'success'):
        raise ValueError(error)
    created = data['result']['created']
    required = {'requestId','clientSessionId','userId','body'}
    if (type(created) is not dict or not required <= set(created) <= required|{'nowSessionId'}
            or created['requestId'] != request['requestId']
            or created['clientSessionId'] != request['clientSessionId']
            or created['userId'] != 'voice-'+request['clientSessionId']
            or type(created['body']) is not list or len(created['body']) != 1):
        raise ValueError(error)
    control = created['body'][0]
    if (type(control) is not dict or set(control) != {'uiType','actionType','conversationId','interactionId','messageId'}
            or control['uiType'] != 'ActionMsg' or control['actionType'] != 'CreateConversation'
            or any(type(control[k]) is not str or not _ID.fullmatch(control[k])
                   for k in ('conversationId','interactionId','messageId'))):
        raise ValueError(error)
    if 'nowSessionId' in created:
        value = created['nowSessionId']
        if (type(value) is not str or not 0 < len(value) < 256 or value != value.strip()
                or any(not 32 <= ord(c) < 127 for c in value)):
            raise ValueError(error)
    return created


async def create_native_caller_conversation(instance_url, api_path, provider_token, authorization,
                                             request, *, timeout_seconds=10, http_factory=None):
    """Only the fixed own API can receive this bounded original-caller CREATE."""
    error = 'Native caller CREATE unavailable'
    if (api_path != CALLER_CREATE_PATH or not valid_authorization(authorization)
            or instance_url != CALLER_INSTANCE_URL
            or type(provider_token) is not str or not 0 < len(provider_token) <= 8192
            or any(ord(c) < 32 or ord(c) == 127 for c in provider_token)
            or not _create_request_ids(request)[0]
            or type(timeout_seconds) not in (int,float) or not 0 < timeout_seconds <= 30):
        raise _create_failure(request, 'pre_dispatch_validation', 0, 'not_dispatched')
    factory = aiohttp.ClientSession if http_factory is None else http_factory
    headers = {'Authorization':authorization,'token':provider_token,'Accept':'application/json',
               'Content-Type':'application/json','Accept-Encoding':'identity'}
    stage, http_status, dispatch_state = 'client_open', 0, 'not_dispatched'
    close_completed, negative_proof = False, False
    try:
        async with asyncio.timeout(timeout_seconds):
            async with factory(cookie_jar=aiohttp.DummyCookieJar(),trust_env=False,
                    auto_decompress=False,skip_auto_headers={'Accept-Encoding'},
                    timeout=aiohttp.ClientTimeout(total=timeout_seconds)) as http:
                stage, dispatch_state = 'request_transport', 'may_have_dispatched'
                async with http.post(instance_url+api_path,json=request,headers=headers,
                                     allow_redirects=False) as response:
                    http_status, dispatch_state = response.status, 'response_received'
                    stage = 'http_status'
                    if response.status in (200, 403):
                        stage = 'response_encoding'
                        if response.headers.get('Content-Encoding'):
                            raise ValueError(error)
                        stage = 'response_type'
                        if not re.match(r'application/json(?:;|$)', response.headers.get('Content-Type',''),re.I):
                            raise ValueError(error)
                        stage = 'response_read'
                        raw=bytearray()
                        limit = 4096 if response.status == 403 else 65536
                        async for chunk in response.content.iter_chunked(min(8192,limit)):
                            raw.extend(chunk)
                            if len(raw)>limit:
                                stage = 'response_oversize'
                                raise ValueError(error)
                        stage = 'response_json'
                        data=json.loads(raw.decode('utf-8'),object_pairs_hook=_pairs,
                            parse_constant=lambda _: (_ for _ in ()).throw(ValueError(error)))
                        if response.status == 403:
                            negative_proof = _validated_create_denial(data,request)
                    stage = 'transport_close'
        close_completed = True
        if http_status != 200:
            raise _create_failure(request, 'http_status', http_status, dispatch_state,
                                  close_completed, negative_proof=negative_proof)
        stage = 'created_tuple_invalid'
        return validated_created(data,request)
    except CallerCreateFailure:
        raise
    except asyncio.CancelledError:
        _log_create_failure('cancelled', http_status, dispatch_state)
        raise
    except Exception:
        raise _create_failure(request, stage, http_status, dispatch_state, close_completed) from None
    finally:
        headers.clear()
        authorization = None


def _pairs(pairs):
    value = {}
    for key, item in pairs:
        if key in value: raise ValueError('Native caller binding unavailable')
        value[key] = item
    return value


def validated_binding(data, service_id, agent_id, profile_id):
    error = 'Native caller binding unavailable'
    if type(data) is not dict or data.get('error') or type(data.get('result')) is not dict:
        raise ValueError(error)
    result = data['result']; agents = result.get('authorized_agents')
    settings = result.get('assistant_settings'); binding = result.get('caller_binding')
    if (type(agents) is not list or not 1 <= len(agents) <= 256 or agent_id not in agents
            or any(type(x) is not str or not _ID.fullmatch(x) for x in agents)
            or len(set(agents)) != len(agents) or type(settings) is not dict
            or type(settings.get('version')) is not int or settings['version'] != 1
            or settings.get('service_id') != service_id or settings.get('context_profile') != profile_id
            or type(binding) is not dict or set(binding) != _FIELDS
            or type(binding.get('version')) is not int or binding['version'] != 1
            or binding.get('service_id') != service_id or binding.get('context_profile') != profile_id
            or binding.get('email_mapping_unique') is not True):
        raise ValueError(error)
    uid, name, email = (binding.get(k) for k in ('user_id', 'user_name', 'email'))
    if (type(uid) is not str or not _ID.fullmatch(uid) or type(name) is not str
            or not name or name != name.strip() or len(name) > 256 or name.casefold() == 'guest'
            or type(email) is not str or not 3 <= len(email) <= 254 or email.count('@') != 1
            or any(c.isspace() or ord(c) < 32 or ord(c) == 127 or c == '^' for c in email)
            or any(ord(c) < 32 or ord(c) == 127 for c in name)):
        raise ValueError(error)
    return CallerBinding(uid, email)


async def _native_projection(instance_url, service_id, agent_id, profile_id, authorization,
                             extra=None, *, http_factory=None, timeout_seconds=10):
    error = 'Native caller binding unavailable'
    if (not valid_authorization(authorization) or any(type(x) is not str or not _ID.fullmatch(x)
            for x in (service_id, agent_id, profile_id))
            or type(instance_url) is not str or not re.fullmatch(r'https://[A-Za-z0-9.-]+(?::[1-9][0-9]{0,4})?', instance_url)):
        raise ValueError(error)
    if type(timeout_seconds) not in (int,float) or not 0 < timeout_seconds <= 10:
        raise ValueError(error)
    factory = aiohttp.ClientSession if http_factory is None else http_factory
    try:
        async with asyncio.timeout(timeout_seconds):
            async with factory(cookie_jar=aiohttp.DummyCookieJar(), trust_env=False,
                    auto_decompress=False, skip_auto_headers={'Accept-Encoding'},
                    timeout=aiohttp.ClientTimeout(total=timeout_seconds)) as http:
                async with http.post(instance_url + '/api/sn_voice_aia/ai_voice_agent/agents_authorized',
                        json={'serviceId':service_id, 'assistantSettingsVersion':1, 'callerBindingVersion':1, **(extra or {})},
                        headers={'Authorization':authorization, 'Content-Type':'application/json',
                                 'Accept':'application/json', 'Accept-Encoding':'identity'},
                        allow_redirects=False) as response:
                    if (response.status != 200 or response.headers.get('Content-Encoding')
                            or not re.match(r'application/json(?:;|$)', response.headers.get('Content-Type', ''), re.I)):
                        raise ValueError(error)
                    raw = bytearray()
                    async for chunk in response.content.iter_chunked(8192):
                        raw.extend(chunk)
                        if len(raw) > 131072: raise ValueError(error)
                    data = json.loads(raw.decode('utf-8'), object_pairs_hook=_pairs,
                                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError(error)))
                    return data
    except Exception:
        # Do not expose response, credential, identity or network details.
        raise ValueError(error) from None


async def resolve_native_caller(instance_url, service_id, agent_id, profile_id, authorization,
                                *, http_factory=None):
    data = await _native_projection(instance_url,service_id,agent_id,profile_id,authorization,
                                     http_factory=http_factory)
    return validated_binding(data,service_id,agent_id,profile_id)


@dataclass(frozen=True, repr=False)
class ProviderContextBinding:
    """Private optional metadata authority, separate from business identity."""
    service_id: str
    context_profile: str
    conversation_id: str
    interaction_id: str
    create_message_id: str
    caller_user_id: str
    provider_user_id: str


def validated_provider_context(value, service_id, profile_id, owned, caller):
    if (type(value) is not dict or set(value) != {'version','status','service_id','context_profile',
            'conversation_id','interaction_id','create_message_id','caller_user_id','provider_user_id'}
            or type(value.get('version')) is not int or value['version'] != 1
            or value.get('status') != 'available' or value.get('service_id') != service_id
            or value.get('context_profile') != profile_id or value.get('caller_user_id') != caller.user_id
            or any(value.get(k) != v for k,v in owned.items())
            or type(value.get('provider_user_id')) is not str
            or re.fullmatch(r'voice-[0-9a-f]{32}',value['provider_user_id']) is None):
        return None
    return ProviderContextBinding(**{k:value[k] for k in ('service_id','context_profile',
        'conversation_id','interaction_id','create_message_id','caller_user_id','provider_user_id')})


async def refresh_native_caller_session(instance_url, service_id, agent_id, profile_id, authorization,
                                        owned, caller, *, timeout_seconds=10, http_factory=None, provider_context=False):
    """Request the native refresh once; an acknowledgement is not authentication."""
    error = 'Native caller session refresh unavailable'
    if (type(owned) is not dict or set(owned) != {'conversation_id','interaction_id','create_message_id'}
            or any(type(v) is not str or not _ID.fullmatch(v) for v in owned.values())
            or type(caller) is not CallerBinding or type(provider_context) is not bool):
        raise ValueError(error)
    data = await _native_projection(instance_url,service_id,agent_id,profile_id,authorization,
        {'conversationAuthenticationVersion':1,'conversationId':owned['conversation_id'],
         'interactionId':owned['interaction_id'],'createMessageId':owned['create_message_id'],
         **({'providerContextVersion':1} if provider_context else {})},
        timeout_seconds=timeout_seconds,http_factory=http_factory)
    current = validated_binding(data,service_id,agent_id,profile_id)
    acknowledgement = data['result'].get('conversation_authentication')
    if (current != caller or type(acknowledgement) is not dict
            or set(acknowledgement) != {'version','refresh_requested','service_id','context_profile',
                                      'conversation_id','interaction_id','create_message_id'}
            or type(acknowledgement.get('version')) is not int or acknowledgement['version'] != 1
            or acknowledgement.get('refresh_requested') is not True
            or acknowledgement.get('service_id') != service_id or acknowledgement.get('context_profile') != profile_id
            or any(acknowledgement.get(k) != v for k,v in owned.items())):
        raise ValueError(error)
    if provider_context:
        return validated_provider_context(data['result'].get('provider_context_binding'),
            service_id,profile_id,owned,caller)
