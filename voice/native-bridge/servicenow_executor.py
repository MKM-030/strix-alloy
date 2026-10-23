"""Owned legacy VA adapter. Reply text is not authoritative business completion."""

from dataclasses import dataclass
import asyncio
import json
import re
from urllib.parse import urlsplit

from business_tasks import StoreInvalid


@dataclass(frozen=True)
class ExecutorCapabilities:
    independent_context: bool = False
    checkpoints: bool = False
    status_lookup: bool = False
    durable_execution: bool = False
    authoritative_idempotency: bool = False
    version_fence: bool = False
    cancel_before_commit: bool = False
    compensate_after_commit: bool = False


class LegacyVAExecutor:
    capabilities = ExecutorCapabilities()

    def __init__(self, dialog, *, ready=None):
        self.dialog = dialog
        self.ready = ready

    async def wait_ready(self):
        if self.ready is not None:
            await self.ready.wait()

    async def turn(self, operation, on_reply):
        return await self.dialog.turn(operation['text'], on_reply=on_reply,
                                      voice_context=operation['voice_context'])

    async def close(self):
        await self.dialog.close()
        # Dialog.close intentionally catches failed END; ownership lasts until ACK.
        if getattr(self.dialog, 'must_reset', False):
            await self.dialog.wait_owned_cleanup()
        if getattr(self.dialog, 'must_reset', False):
            raise RuntimeError('owned cleanup not acknowledged')


class OwnedTaskExecutor:
    """Explicit candidate protocol for owned resources, not native VA authority.

    No automatic retry, redirect, model-facing surface, or local qualification
    switch. Only prepare is a candidate mutation; live business commit remains
    unavailable until an actual platform principal/transaction route is qualified.
    The injected transport is a private test/integration seam with the same shape
    as _http; it never grants capabilities.
    """
    capabilities = ExecutorCapabilities()
    route = '/api/global/scc_voice_tasks/v2'

    def __init__(self, store, *, origin, authorization, transport=None):
        parsed = urlsplit(origin)
        if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
                or parsed.path not in ('', '/') or parsed.query or parsed.fragment
                or parsed.port not in (None, 443)):
            raise ValueError('invalid owned origin')
        if not callable(authorization):
            raise ValueError('private authorization provider required')
        self.store, self.origin = store, origin.rstrip('/')
        self._authorization = authorization
        self._transport = transport or self._http

    @staticmethod
    def _identifier(value):
        if type(value) is not str or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}', value):
            raise StoreInvalid('invalid owned identifier')
        return value

    def qualify(self, evidence):
        # A JSON claim, local hash or server Boolean cannot close the wire gaps.
        raise PermissionError('live principal and durable authority qualification unavailable')

    async def commit(self, operation_id, task_ref, command):
        raise PermissionError('owned business commit is not live qualified')

    async def _http(self, method, url, *, headers, body, allow_redirects):
        import aiohttp
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout, trust_env=False) as session:
            async with session.request(method, url, headers=headers, data=body, allow_redirects=False) as response:
                if response.status != 200:
                    raise RuntimeError('owned response unavailable')
                raw = await response.content.read(65537)
                if len(raw) > 65536:
                    raise ValueError('owned response too large')
                def pairs(items):
                    result = {}
                    for key, value in items:
                        if key in result:
                            raise ValueError('duplicate owned field')
                        result[key] = value
                    return result
                return json.loads(raw, object_pairs_hook=pairs,
                                  parse_constant=lambda _: (_ for _ in ()).throw(ValueError('invalid owned JSON')))

    async def _request(self, method, path, body=None):
        authorization = self._authorization()
        if type(authorization) is not str or not authorization or len(authorization) > 8192 or '\r' in authorization or '\n' in authorization:
            raise ValueError('invalid private authorization')
        encoded = json.dumps(body, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8') if body is not None else None
        return await self._transport(method, self.origin + self.route + path,
                                     headers={'Authorization': authorization, 'Content-Type': 'application/json'},
                                     body=encoded, allow_redirects=False)

    async def registry(self):
        return await self._request('GET', '/registry')

    async def status(self, task_ref):
        return await self._request('GET', '/tasks/' + self._identifier(task_ref))

    async def operation_status(self, operation_ref):
        return await self._request('GET', '/operations/' + self._identifier(operation_ref))

    async def prepare(self, operation_id, task_ref, command):
        self._identifier(operation_id)
        self._identifier(task_ref)
        if (type(command) is not dict or set(command) != {'command_id', 'expected_revision', 'kind', 'proposal', 'context_version'}
                or command['command_id'] != operation_id or command['kind'] != 'prepare'):
            raise StoreInvalid('invalid owned preparation')
        if type(command['context_version']) is not int or command['context_version'] != self.store.executor_binding(operation_id)['operation']['context_version']:
            raise StoreInvalid('invalid owned context version')
        self._identifier(command['expected_revision'])
        proposal = command['proposal']
        fields = {'employee_name', 'start_date', 'delivery_location', 'manager_name'}
        if type(proposal) is not dict or set(proposal) != fields or any(type(v) is not str or not v or len(v) > 100 for v in proposal.values()):
            raise StoreInvalid('invalid bounded proposal')
        bound = self.store.record_owned_dispatch(operation_id, task_ref, command)
        if bound['operation']['dispatch_state'] != 'unsubmitted':
            return bound['operation']
        self.store.dispatch(operation_id)
        try:
            result = await self._request('POST', '/tasks/' + task_ref + '/commands', command)
            if (type(result) is not dict or result.get('task_id') != task_ref
                    or result.get('command_id') != operation_id or result.get('kind') != 'prepare'
                    or type(result.get('revision')) is not str):
                raise ValueError('owned response correlation mismatch')
            self._identifier(result['revision'])
            self.store.record_receipt(operation_id, receipt={'task_ref': task_ref, 'operation_ref': result['revision'], 'status': 'accepted'})
            # Preparation is not business completion. Record ACK only.
            self.store.settle(operation_id, replies=[], outcome='awaiting_input', evidence={'source': 'owned_prepare'})
        except BaseException as error:
            self.store.mark_unknown(operation_id, 'owned_transport_uncertain')
            if isinstance(error, (asyncio.CancelledError, KeyboardInterrupt, SystemExit)):
                raise
        return self.store.executor_binding(operation_id)['operation']

    def observe(self, operation_id, event):
        # Caller must obtain this from an authenticated configured-origin poll;
        # no unauthenticated callback endpoint is installed by this package.
        return self.store.observe_owned(operation_id, event)
