"""Session-scoped ServiceNow TURN discovery; never forwards SDP, media or prompts."""
from dataclasses import dataclass, field
import asyncio
import json
import logging
from pathlib import Path
import re
from urllib.parse import urlsplit

import aiohttp
from aiortc import RTCIceServer

LOG = logging.getLogger(__name__)

MAX_CONFIG_BYTES = 16384
MAX_RESPONSE_BYTES = 65536
CREATE_SECONDS = 6
DELETE_SECONDS = 3
_HOST = re.compile(r'aivoiceservice-[a-z0-9](?:[a-z0-9-]{0,100}[a-z0-9])?\.sncapps\.service-now\.com')
_SESSION = re.compile(r'[A-Za-z0-9][A-Za-z0-9_-]{0,127}')
_INSTANCE = re.compile(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?')
_SERVICE = re.compile(r'[0-9a-f]{32}')
_TURNS = re.compile(r'turns:([^:/?#]+):443\?transport=tcp')


class ManagedTurnUnavailable(Exception):
    def __init__(self):
        super().__init__('Managed ServiceNow TURN is unavailable')


def _host(value):
    if not isinstance(value,str) or _HOST.fullmatch(value) is None:
        raise ValueError('Invalid ServiceNow voice destination')
    return value


def _origin(value, allowed, *, bare=False):
    if not isinstance(value,str) or len(value)>512:
        raise ValueError('Invalid ServiceNow voice origin')
    if bare and _HOST.fullmatch(value):
        value = 'https://' + value
    parsed = urlsplit(value)
    if (parsed.scheme!='https' or parsed.hostname not in allowed
            or parsed.netloc not in (parsed.hostname,parsed.hostname+':443')
            or parsed.path not in ('','/') or parsed.query or parsed.fragment):
        raise ValueError('Unapproved ServiceNow voice origin')
    return 'https://' + parsed.hostname


def _origin_diagnostics(value, allowed, *, bare=False):
    """Fixed boolean fields only; rejected endpoints and parse errors stay private."""
    flags = dict.fromkeys(('type_valid','length_ok','parsed_ok','canonical_origin',
        'bare_host','scheme_ok','supported_hostname','allowlisted','netloc_safe',
        'path_empty_or_root','has_query','has_fragment'),False)
    flags['type_valid'] = isinstance(value,str)
    flags['length_ok'] = flags['type_valid'] and len(value)<=512
    if not flags['length_ok']:
        return flags
    flags['bare_host'] = bare and _HOST.fullmatch(value) is not None
    try:
        parsed = urlsplit('https://'+value if flags['bare_host'] else value)
        hostname = parsed.hostname
    except ValueError:
        return flags
    flags.update(parsed_ok=True,
        canonical_origin=bool(hostname and value=='https://'+hostname),
        scheme_ok=parsed.scheme=='https',
        supported_hostname=_HOST.fullmatch(hostname or '') is not None,
        allowlisted=hostname in allowed,
        netloc_safe=bool(hostname and parsed.netloc in (hostname,hostname+':443')),
        path_empty_or_root=parsed.path in ('','/'),
        has_query=bool(parsed.query),has_fragment=bool(parsed.fragment))
    return flags


def _unique(pairs):
    value = {}
    for key,item in pairs:
        if key in value:
            raise ValueError('Duplicate configuration field')
        value[key] = item
    return value


def _json(data):
    def invalid(value):
        raise ValueError('Nonfinite JSON value')
    result = json.loads(data.decode('utf-8-sig'),object_pairs_hook=_unique,
                        parse_constant=invalid)
    if not isinstance(result,dict):
        raise ValueError('Expected an object')
    return result


@dataclass(frozen=True,repr=False)
class ManagedTurnConfiguration:
    base_origin: str | None = field(default=None,repr=False)
    signaling_hosts: tuple = field(default=(),repr=False)
    turn_hosts: tuple = field(default=(),repr=False)

    def __post_init__(self):
        if self.base_origin is None:
            if self.signaling_hosts or self.turn_hosts:
                raise ValueError('Disabled managed TURN cannot contain destinations')
            return
        for hosts in (self.signaling_hosts,self.turn_hosts):
            if type(hosts) is not tuple or not 1<=len(hosts)<=16:
                raise ValueError('Managed TURN requires bounded explicit destination lists')
            for host in hosts:
                _host(host)
            if len(set(hosts))!=len(hosts):
                raise ValueError('Duplicate managed TURN destination')
        if _origin(self.base_origin,self.signaling_hosts)!=self.base_origin:
            raise ValueError('Managed TURN base origin must be canonical HTTPS')

    @property
    def enabled(self):
        return self.base_origin is not None


def load_managed_turn_file(filename):
    try:
        with Path(filename).open('rb') as handle:
            data = handle.read(MAX_CONFIG_BYTES+1)
        if len(data)>MAX_CONFIG_BYTES:
            raise ValueError()
        raw = _json(data)
        if set(raw)!={'base_origin','signaling_hosts','turn_hosts'}:
            raise ValueError()
        if type(raw['signaling_hosts']) is not list or type(raw['turn_hosts']) is not list:
            raise ValueError()
        return ManagedTurnConfiguration(raw['base_origin'],tuple(raw['signaling_hosts']),
                                        tuple(raw['turn_hosts']))
    except (OSError,TypeError,UnicodeError,ValueError,RecursionError):
        raise ValueError('Managed TURN configuration cannot be read or is invalid') from None


class ManagedTurnBootstrap:
    """No token, cloud-session handle, or response credential survives this call."""
    def __init__(self, config, *, session_factory=None):
        if not isinstance(config,ManagedTurnConfiguration) or not config.enabled:
            raise ValueError('Resolved managed TURN configuration is required')
        self.config = config
        self._session_factory = session_factory or aiohttp.ClientSession

    @staticmethod
    def _servers(payload,allowed):
        rows = payload.get('iceServers')
        if not isinstance(rows,list) or not 1<=len(rows)<=4:
            raise ValueError('Invalid managed ICE servers')
        urls = []
        for row in rows:
            if not isinstance(row,dict) or not isinstance(row.get('urls'),list):
                raise ValueError('Invalid managed ICE server')
            if not 1<=len(row['urls'])<=4:
                raise ValueError('Invalid managed ICE URL count')
            for url in row['urls']:
                match = _TURNS.fullmatch(url) if isinstance(url,str) and len(url)<=512 else None
                if match is None or match.group(1) not in allowed:
                    raise ValueError('Unapproved managed TURN destination')
                if url not in urls:
                    urls.append(url)
        # The SDK derives instance:service:OAuth / oauth itself. Never return
        # remote credentials, nor accidentally direct signaling to the cloud.
        return [{'urls':[url]} for url in urls]

    async def _delete(self,http,origin,session_id,headers):
        try:
            async with asyncio.timeout(DELETE_SECONDS):
                async with http.delete(origin+'/api/webrtc/sessions/'+session_id,
                        headers=headers,allow_redirects=False,
                        timeout=aiohttp.ClientTimeout(total=DELETE_SECONDS,connect=2)) as response:
                    LOG.info('Managed TURN stage=delete_response status=%d',response.status)
                    if response.status not in (200,204,404):
                        raise ManagedTurnUnavailable()
        except asyncio.CancelledError:
            raise
        except Exception as error:
            LOG.warning('Managed TURN stage=delete_failed type=%s',type(error).__name__)
            raise ManagedTurnUnavailable() from None

    async def ice_servers(self,token,instance,service):
        if (not isinstance(token,str) or not 1<=len(token)<=8192
                or any(ord(c)<33 or ord(c)>126 for c in token)
                or not isinstance(instance,str) or _INSTANCE.fullmatch(instance) is None
                or not isinstance(service,str) or _SERVICE.fullmatch(service) is None):
            raise ManagedTurnUnavailable()
        headers = {'Authorization':'Bearer '+token,'Accept':'application/json',
                   'Accept-Encoding':'identity'}
        session_id = None
        cleanup_origin = self.config.base_origin
        stage = 'client_setup'
        try:
            async with self._session_factory(trust_env=False,auto_decompress=False,
                    timeout=aiohttp.ClientTimeout(total=CREATE_SECONDS,connect=2),
                    cookie_jar=aiohttp.DummyCookieJar()) as http:
                try:
                    stage = 'create_request'
                    async with asyncio.timeout(CREATE_SECONDS):
                        async with http.post(self.config.base_origin+'/api/webrtc/sessions',
                                params={'instance_name':instance,'voice_service_id':service,
                                        'receive_data':'true'},
                                json={'agent_id':'agent_operator'},headers=headers,
                                allow_redirects=False) as response:
                            stage = 'create_response'
                            LOG.info('Managed TURN stage=create_response status=%d',response.status)
                            if response.status!=200:
                                raise ManagedTurnUnavailable()
                            if response.headers.get('Content-Type','').split(';',1)[0].strip().lower()!='application/json':
                                raise ManagedTurnUnavailable()
                            data = bytearray()
                            while len(data)<=MAX_RESPONSE_BYTES:
                                chunk = await response.content.read(min(16384,MAX_RESPONSE_BYTES+1-len(data)))
                                if not chunk:
                                    break
                                data.extend(chunk)
                            if len(data)>MAX_RESPONSE_BYTES:
                                raise ManagedTurnUnavailable()
                            stage = 'response_json'
                            payload = _json(bytes(data))
                    stage = 'session_id'
                    sid = payload.get('session_id')
                    if not isinstance(sid,str) or _SESSION.fullmatch(sid) is None:
                        raise ManagedTurnUnavailable()
                    session_id = sid
                    stage = 'endpoint_origin'
                    try:
                        cleanup_origin = _origin(payload.get('endpoint_url'),
                                                 self.config.signaling_hosts,bare=True)
                    except ValueError:
                        LOG.warning('Managed TURN stage=endpoint_rejected %s',
                            _origin_diagnostics(payload.get('endpoint_url'),
                                                self.config.signaling_hosts,bare=True))
                        raise
                    stage = 'ice_servers'
                    servers = self._servers(payload,self.config.turn_hosts)
                    stage = 'cleanup'
                    return servers
                finally:
                    if session_id is not None:
                        cleanup = asyncio.create_task(self._delete(http,cleanup_origin,session_id,headers))
                        try:
                            await asyncio.shield(cleanup)
                        except asyncio.CancelledError:
                            # Cancellation does not orphan a successfully-created
                            # metadata session; only its exact validated ID is deleted.
                            try:
                                await asyncio.wait_for(asyncio.shield(cleanup),DELETE_SECONDS+1)
                            except BaseException:
                                cleanup.cancel()
                                await asyncio.gather(cleanup,return_exceptions=True)
                            raise
        except asyncio.CancelledError:
            raise
        except Exception as error:
            LOG.warning('Managed TURN stage=failed checkpoint=%s type=%s',stage,type(error).__name__)
            raise ManagedTurnUnavailable() from None


class SessionIceServer(RTCIceServer):
    """aiortc consumes OAuth in RAM; its default dataclass repr exposes credentials."""
    def __repr__(self):
        return 'SessionIceServer()'


def session_host_ice(servers,token,instance,service):
    """Fresh per-call ICE snapshot; SDK and backend use the same OAuth identity."""
    username = instance+':'+service+':'+token
    # Host candidates are gathered without STUN. Managed TURN supplies the relay;
    # unrelated per-interface public STUN queries must not delay its ready answer.
    return ([] if servers else [SessionIceServer(urls=['stun:stun.l.google.com:19302'])]) + [
        SessionIceServer(urls=list(row['urls']),username=username,credential='oauth',
                         credentialType='password') for row in servers]


def clear_session_ice(servers,peer=None):
    """Best-effort removal of our credential references after transport shutdown.

    Python strings cannot be securely zeroed. aiortc also copies the credential
    into aioice; clear those version-dependent references after peer.close().
    """
    if not servers:
        return
    for server in servers:
        server.username = server.credential = None
    servers.clear()
    if peer is None:
        return
    try:
        transports = []
        for transceiver in peer.getTransceivers():
            transports.extend([transceiver.sender.transport,transceiver.receiver.transport])
        if peer.sctp is not None:
            transports.append(peer.sctp.transport)
        for dtls in transports:
            gatherer = dtls.transport.iceGatherer if dtls is not None else None
            connection = getattr(gatherer,'_connection',None)
            if connection is not None:
                connection.turn_username = connection.turn_password = None
                # aioice.close() drops _protocols but keeps CandidatePairs;
                # those retain TurnTransport and its copied OAuth username.
                for name in ('_check_list','_early_checks'):
                    retained = getattr(connection,name,None)
                    if isinstance(retained,list):
                        retained.clear()
    except (AttributeError,TypeError):
        # Credential removal must never interrupt the owned call cleanup.
        pass
