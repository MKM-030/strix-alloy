"""Check the fixed caller API's access before allocating a Voice session.

Literal {} is rejected before the own resource can invoke a lifecycle handler.
This is an admission check, never a receipt for a later real CREATE outcome.
"""
import asyncio
from contextlib import asynccontextmanager
import json
import math
import re

import aiohttp


_INSTANCE = 'https://soprasteriaassvsdemo14.service-now.com'
_SERVICE = '8aa131d793f787105c8132d47aba1095'
_PROFILE = 'c623e20f93374354e7f2b9fa6aba1081'
_AGENT = 'a6337ddf93f787105c8132d47aba1058'
_URL = _INSTANCE + '/api/sn_voice_aia/local_voice_caller/create'
_BEARER = re.compile(r'(?i:Bearer) [A-Za-z0-9._~+/-]+=*\Z')
_JSON_TYPE = re.compile(r'application/json(?:\s*;\s*charset=utf-8)?\Z', re.I)
_DENIAL = {'result': {'status': 'failure', 'detail': 'Local caller create unavailable'}}
MAX_RESPONSE_BYTES = 4096
REQUEST_TIMEOUT_SECONDS = 10


class CallerCreatePreflightDenied(Exception):
    """Only a fixed public denial crosses this boundary; no upstream detail."""
    def __init__(self, status):
        self.status = 401 if status == 401 else 403
        super().__init__('unauthorized' if self.status == 401 else 'forbidden')


def requires_caller_create_preflight(instance_url, service_id, context_profile, required_agent_id):
    """Only fresh trusted settings for this own deployment need its own API."""
    return (instance_url, service_id, context_profile, required_agent_id) == (
        _INSTANCE, _SERVICE, _PROFILE, _AGENT)


@asynccontextmanager
async def deadline_bound_context(manager, deadline):
    """Keep enter and unwind in the caller task under one absolute deadline.

    A timer that interrupted the body cannot interrupt a later awaiting exit
    again. Each exit therefore gets a fresh timer for the same deadline. On
    external cancellation, attempt exit immediately and preserve cancellation
    even if that aborting exit cannot finish. No cleanup task is detached.
    """
    async with asyncio.timeout_at(deadline):
        value = await manager.__aenter__()
    try:
        yield value
    except BaseException as error:
        cancelled = isinstance(error, asyncio.CancelledError)
        exit_deadline = deadline
        if cancelled:
            exit_deadline = min(deadline, asyncio.get_running_loop().time())
        try:
            async with asyncio.timeout_at(exit_deadline):
                await manager.__aexit__(type(error), error, error.__traceback__)
        except BaseException:
            if cancelled:
                raise error
            raise
        raise
    else:
        async with asyncio.timeout_at(deadline):
            await manager.__aexit__(None, None, None)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Invalid access response')
        result[key] = value
    return result


def _reject_constant(_):
    raise ValueError('Invalid access response')


async def _read_denial(response):
    content_type = response.headers.get('Content-Type', '')
    encoding = response.headers.get('Content-Encoding')
    if (not isinstance(content_type, str) or not _JSON_TYPE.fullmatch(content_type)
            or encoding is not None and (
                not isinstance(encoding, str) or encoding.lower() != 'identity')):
        raise ValueError('Invalid access response')
    raw = bytearray()
    while len(raw) <= MAX_RESPONSE_BYTES:
        part = await response.content.read(MAX_RESPONSE_BYTES + 1 - len(raw))
        if not part:
            value = json.loads(bytes(raw).decode('utf-8'), object_pairs_hook=_unique_object,
                               parse_constant=_reject_constant)
            if value != _DENIAL:
                raise ValueError('Invalid access response')
            return
        raw.extend(part)
    raise ValueError('Invalid access response')


async def require_caller_create_access(authorization, *, http_factory=None, deadline=None):
    """One caller-only malformed request; accept after both contexts close.

    The entrypoint supplies the fixed deployment predicate and absolute combined
    admission deadline. The own cap also bounds standalone callers. Every phase
    and unwind uses that same deadline; no positive result or credential is cached.
    """
    if (not isinstance(authorization, str) or len(authorization) > 8192
            or not _BEARER.fullmatch(authorization)):
        raise CallerCreatePreflightDenied(401)
    now = asyncio.get_running_loop().time()
    if deadline is not None and (type(deadline) not in (int, float) or not math.isfinite(deadline)):
        raise CallerCreatePreflightDenied(403)
    own_deadline = now + REQUEST_TIMEOUT_SECONDS
    deadline = own_deadline if deadline is None else min(deadline, own_deadline)
    if deadline <= now:
        raise CallerCreatePreflightDenied(403)
    factory = aiohttp.ClientSession if http_factory is None else http_factory
    headers = {'Authorization': authorization, 'Content-Type': 'application/json',
               'Accept': 'application/json', 'Accept-Encoding': 'identity'}
    status = 0
    try:
        client = factory(cookie_jar=aiohttp.DummyCookieJar(), trust_env=False,
            auto_decompress=False, skip_auto_headers={'Accept-Encoding'},
            timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS))
        async with deadline_bound_context(client, deadline) as http:
            request = http.post(_URL, data=b'{}', headers=headers, allow_redirects=False)
            async with deadline_bound_context(request, deadline) as response:
                status = response.status
                if status == 400:
                    async with asyncio.timeout_at(deadline):
                        await _read_denial(response)
        if asyncio.get_running_loop().time() >= deadline:
            raise CallerCreatePreflightDenied(403)
        if status != 400:
            raise CallerCreatePreflightDenied(401 if status == 401 else 403)
    except CallerCreatePreflightDenied:
        raise
    except Exception:
        raise CallerCreatePreflightDenied(403) from None
    finally:
        headers.clear()
        authorization = None
