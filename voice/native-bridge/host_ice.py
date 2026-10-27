"""Private host-only ICE configuration. Never send these credentials to mobile DTOs."""
from dataclasses import dataclass, field
import ipaddress
import json
import os
from pathlib import Path
import re

from aiortc import RTCIceServer
from aiortc.rtcicetransport import parse_stun_turn_uri

STUN_URL = 'stun:stun.l.google.com:19302'
MAX_PRIVATE_FILE_BYTES = 16384
_ENV_NAME = re.compile(r'[A-Za-z_][A-Za-z0-9_]{0,127}')
_TURN_URL = re.compile(r'(turn|turns):([A-Za-z0-9][A-Za-z0-9.-]*)(?::([0-9]+))?(?:\?transport=(udp|tcp))?')
_HOST_LABEL = re.compile(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?')


def _validated_url(value):
    if not isinstance(value,str) or len(value)>1024:
        raise ValueError('Invalid private host TURN URL')
    match = _TURN_URL.fullmatch(value)
    if match is None:
        raise ValueError('Invalid private host TURN URL')
    scheme,host,port,transport = match.groups()
    labels = host.removesuffix('.').split('.')
    if len(host)>253 or any(_HOST_LABEL.fullmatch(label) is None for label in labels):
        raise ValueError('Invalid private host TURN hostname')
    if re.fullmatch(r'[0-9.]+',host):
        try:
            ipaddress.IPv4Address(host)
        except ValueError:
            raise ValueError('Invalid private host TURN hostname') from None
    if port is not None and (len(port)>5 or not 1<=int(port)<=65535):
        raise ValueError('Invalid private host TURN port')
    if scheme=='turns' and transport=='udp':
        raise ValueError('Private host TURNS requires TCP')
    # Keep validation aligned with the installed aiortc parser, without echoing a URL.
    try:
        parse_stun_turn_uri(value)
    except ValueError:
        raise ValueError('Unsupported private host TURN URL') from None
    return value


def _validated_secret(value,limit):
    if (not isinstance(value,str) or not value.strip() or len(value)>limit
            or any(ord(character)<32 or ord(character)==127 for character in value)):
        raise ValueError('Private host TURN environment value is missing or invalid')
    return value


@dataclass(frozen=True,repr=False)
class HostIceConfiguration:
    """Resolved startup snapshot; not a relay health/readiness result."""
    _turn_url: str | None = field(default=None,repr=False)
    _username: str | None = field(default=None,repr=False)
    _credential: str | None = field(default=None,repr=False)

    def __post_init__(self):
        if self._turn_url is None:
            if self._username is not None or self._credential is not None:
                raise ValueError('Private host TURN credentials require a TURN URL')
            return
        _validated_url(self._turn_url)
        _validated_secret(self._username,256)
        _validated_secret(self._credential,4096)

    def servers(self):
        """Return fresh aiortc server objects. Mobile signaling uses its own fixed STUN."""
        servers = [RTCIceServer(urls=[STUN_URL])]
        if self._turn_url is not None:
            servers.append(RTCIceServer(urls=[self._turn_url],username=self._username,
                                        credential=self._credential,credentialType='password'))
        return servers


def _unique_object(pairs):
    result = {}
    for key,value in pairs:
        if key in result:
            raise ValueError('Duplicate private host ICE configuration key')
        result[key] = value
    return result


def load_host_ice_file(filename):
    """Read an operator-owned JSON file containing one TURN URL and env references."""
    if not isinstance(filename,(str,Path)) or not str(filename):
        raise ValueError('Invalid private host ICE configuration path')
    try:
        with Path(filename).open('rb') as handle:
            data = handle.read(MAX_PRIVATE_FILE_BYTES+1)
        if len(data)>MAX_PRIVATE_FILE_BYTES:
            raise ValueError('oversized')
        payload = json.loads(data.decode('utf-8-sig'),object_pairs_hook=_unique_object)
    except (OSError,UnicodeError,ValueError):
        raise ValueError('Private host ICE configuration cannot be read or is invalid') from None
    if not isinstance(payload,dict) or set(payload)!={'turn_servers'}:
        raise ValueError('Private host ICE configuration requires only turn_servers')
    servers = payload['turn_servers']
    if not isinstance(servers,list) or len(servers)!=1:
        raise ValueError('Exactly one private host TURN server is supported; aiortc ignores additional servers')
    server = servers[0]
    if not isinstance(server,dict) or set(server)!={'url','username_env','credential_env'}:
        raise ValueError('Private host TURN requires url and environment references only')
    url = _validated_url(server['url'])
    names = (server['username_env'],server['credential_env'])
    if any(not isinstance(name,str) or _ENV_NAME.fullmatch(name) is None for name in names):
        raise ValueError('Invalid private host TURN environment reference')
    username = _validated_secret(os.environ.get(names[0]),256)
    credential = _validated_secret(os.environ.get(names[1]),4096)
    return HostIceConfiguration(url,username,credential)
