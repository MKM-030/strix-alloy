"""Private native caller identity and bounded owned conversation bootstrap.

No client identity assertion or JWT payload is an identity source. Each call
uses its original bearer only for its bounded owned bootstrap; nothing here
logs, caches or persists it.
"""
import asyncio
from dataclasses import dataclass, field
import json
import re
import time
import aiohttp

CALLER_HEADER = 'X-SCC-Voice-Authorization'
CALLER_INSTANCE_URL = 'https://soprasteriaassvsdemo14.service-now.com'
CALLER_CREATE_PATH = '/api/sn_voice_aia/local_voice_caller/create'
CALLER_SERVICE_ID = '8aa131d793f787105c8132d47aba1095'
CALLER_AGENT_ID = 'a6337ddf93f787105c8132d47aba1058'
CALLER_PROFILE_ID = 'c623e20f93374354e7f2b9fa6aba1081'
_ID = re.compile(r'[0-9a-f]{32}\Z')
_BEARER = re.compile(r'Bearer [A-Za-z0-9._~+/-]+=*\Z', re.I)
_FIELDS = {'version', 'service_id', 'context_profile', 'user_id', 'user_name',
           'email', 'email_mapping_unique'}


@dataclass(frozen=True)
class CallerBinding:
    user_id: str = field(repr=False)
    email: str = field(repr=False)


class CallerBootstrapCredential:
    """One own CREATE and one refresh; active erasure even without traffic."""
    __slots__ = ('_value', '_deadline', '_timer', '_on_expire', '_create_claimed')

    def __init__(self, authorization, *, seconds, on_expire=None):
        if not valid_authorization(authorization) or type(seconds) not in (int,float) or not 0 < seconds <= 45:
            raise ValueError('Native caller bootstrap unavailable')
        self._value = authorization
        self._create_claimed = False
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
            or type(request) is not dict or set(request) != {'version','requestId','clientSessionId','clientMessageId'}
            or type(request['version']) is not int or request['version'] != 1
            or any(type(request[k]) is not str or not _ID.fullmatch(request[k])
                   for k in ('requestId','clientSessionId','clientMessageId'))
            or type(timeout_seconds) not in (int,float) or not 0 < timeout_seconds <= 30):
        raise ValueError(error)
    factory = aiohttp.ClientSession if http_factory is None else http_factory
    headers = {'Authorization':authorization,'token':provider_token,'Accept':'application/json',
               'Content-Type':'application/json','Accept-Encoding':'identity'}
    try:
        async with asyncio.timeout(timeout_seconds):
            async with factory(cookie_jar=aiohttp.DummyCookieJar(),trust_env=False,
                    auto_decompress=False,skip_auto_headers={'Accept-Encoding'},
                    timeout=aiohttp.ClientTimeout(total=timeout_seconds)) as http:
                async with http.post(instance_url+api_path,json=request,headers=headers,
                                     allow_redirects=False) as response:
                    if (response.status != 200 or response.headers.get('Content-Encoding')
                            or not re.match(r'application/json(?:;|$)', response.headers.get('Content-Type',''),re.I)):
                        raise ValueError(error)
                    raw=bytearray()
                    async for chunk in response.content.iter_chunked(8192):
                        raw.extend(chunk)
                        if len(raw)>65536:raise ValueError(error)
                    data=json.loads(raw.decode('utf-8'),object_pairs_hook=_pairs,
                        parse_constant=lambda _: (_ for _ in ()).throw(ValueError(error)))
        return validated_created(data,request)
    except Exception:
        raise ValueError(error) from None
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


async def refresh_native_caller_session(instance_url, service_id, agent_id, profile_id, authorization,
                                        owned, caller, *, timeout_seconds=10, http_factory=None):
    """Request the native refresh once; an acknowledgement is not authentication."""
    error = 'Native caller session refresh unavailable'
    if (type(owned) is not dict or set(owned) != {'conversation_id','interaction_id','create_message_id'}
            or any(type(v) is not str or not _ID.fullmatch(v) for v in owned.values())
            or type(caller) is not CallerBinding):
        raise ValueError(error)
    data = await _native_projection(instance_url,service_id,agent_id,profile_id,authorization,
        {'conversationAuthenticationVersion':1,'conversationId':owned['conversation_id'],
         'interactionId':owned['interaction_id'],'createMessageId':owned['create_message_id']},
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
