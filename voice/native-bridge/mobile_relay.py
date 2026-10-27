"""Optional SDK mobile relay admission registry. Contains token hashes, never OAuth tokens."""
from dataclasses import dataclass, field
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import tempfile
import time

_MAX_FILE_BYTES = 16384
_LABEL = re.compile(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?')
_ID = re.compile(r'[0-9a-f]{32}')
_HASH = re.compile(r'[0-9a-f]{64}')
_URL = re.compile(r'turns:([a-z0-9.-]+):([0-9]{1,5})\?transport=tcp')


class MobileRelayUnavailable(RuntimeError):
    def __init__(self):
        super().__init__('Private mobile relay registry unavailable')


def _valid_ipv4(value):
    try:
        ip = ipaddress.ip_address(value)
        return (isinstance(ip,ipaddress.IPv4Address) and str(ip)==value
                and not (ip.is_unspecified or ip.is_loopback or ip.is_multicast
                         or ip.is_link_local or ip.is_reserved))
    except (ValueError,TypeError):
        return False


@dataclass(frozen=True,repr=False)
class MobileRelayConfiguration:
    url: str | None = field(default=None,repr=False)
    registry_file: str | None = field(default=None,repr=False)
    relay_address: str | None = field(default=None,repr=False)
    relay_executable: str | None = field(default=None,repr=False)
    relay_executable_sha256: str | None = field(default=None,repr=False)
    listen_address: str = field(default='127.0.0.1:8872',repr=False)
    status_address: str = field(default='127.0.0.1:8873',repr=False)
    realm: str = field(default='voice.local',repr=False)

    def __post_init__(self):
        if self.url is None:
            if (self.registry_file is not None or self.relay_address is not None
                    or self.relay_executable is not None or self.relay_executable_sha256 is not None):
                raise ValueError('Private mobile relay configuration is incomplete')
            return
        match = _URL.fullmatch(self.url) if isinstance(self.url,str) else None
        if match is None:
            raise ValueError('Private mobile relay requires a TURNS TCP URL with explicit port')
        host=match.group(1)
        if not 1<=int(match.group(2))<=65535:
            raise ValueError('Invalid private mobile relay public port')
        if (len(host)>253 or '.' not in host
                or any(_LABEL.fullmatch(label) is None for label in host.split('.'))
                or not re.fullmatch(r'[a-z][a-z0-9-]*',host.rsplit('.',1)[-1])
                or host.endswith(('.localhost','.local','.internal'))):
            raise ValueError('Invalid private mobile relay hostname')
        if (not isinstance(self.registry_file,str) or not self.registry_file
                or not Path(self.registry_file).is_absolute()
                or any(ord(c)<32 for c in self.registry_file)):
            raise ValueError('Private mobile relay registry path must be absolute')
        if not _valid_ipv4(self.relay_address):
            raise ValueError('Private mobile relay address must be a unicast non-loopback IPv4 address')
        if (not isinstance(self.relay_executable,str) or not self.relay_executable
                or not Path(self.relay_executable).is_absolute()
                or any(ord(c)<32 for c in self.relay_executable)
                or not isinstance(self.relay_executable_sha256,str)
                or _HASH.fullmatch(self.relay_executable_sha256) is None):
            raise ValueError('Private mobile relay executable requires an absolute path and SHA256')
        target=Path(self.registry_file).resolve()
        executable=Path(self.relay_executable).resolve()
        if target==executable or Path(str(target)+'.lock')==executable:
            raise ValueError('Private mobile relay registry must not overwrite its executable')
        ports=[]
        for address in (self.listen_address,self.status_address):
            try:
                host,port=address.split(':')
                parsed=ipaddress.IPv4Address(host)
                if (not parsed.is_loopback or str(parsed)!=host or not port.isascii()
                        or not port.isdecimal() or not 1024<=int(port)<=65535):
                    raise ValueError()
                ports.append(int(port))
            except (ValueError,TypeError,AttributeError):
                raise ValueError('Private mobile relay listeners require loopback IPv4 and ports 1024..65535') from None
        if ports[0]==ports[1]:
            raise ValueError('Private mobile relay listener and status ports must differ')
        if not isinstance(self.realm,str) or not re.fullmatch(r'[A-Za-z0-9._-]{1,128}',self.realm):
            raise ValueError('Private mobile relay realm must be a bounded ASCII label')

    @property
    def enabled(self):
        return self.url is not None

    def ice_servers(self):
        return [{'urls':[self.url]}] if self.enabled else []


def _unique(pairs):
    result={}
    for key,value in pairs:
        if key in result:
            raise ValueError('Duplicate private mobile relay key')
        result[key]=value
    return result


def load_mobile_relay_file(filename):
    try:
        with Path(filename).open('rb') as handle:
            raw=handle.read(_MAX_FILE_BYTES+1)
        if len(raw)>_MAX_FILE_BYTES:
            raise ValueError()
        value=json.loads(raw.decode('utf-8-sig'),object_pairs_hook=_unique)
    except (OSError,TypeError,UnicodeError,ValueError):
        raise ValueError('Private mobile relay configuration cannot be read or is invalid') from None
    fields={'url','registry_file','relay_address','relay_executable','relay_executable_sha256',
            'listen_address','status_address','realm'}
    if not isinstance(value,dict) or set(value)!=fields:
        raise ValueError('Private mobile relay configuration requires the exact startup fields')
    config=MobileRelayConfiguration(**value)
    if Path(config.registry_file).resolve()==Path(filename).resolve():
        raise ValueError('Private mobile relay registry must not overwrite its configuration')
    return config


def local_udp_peers(peer,relay_address):
    """Collect only real gathered host sockets via public aiortc transport APIs."""
    transports=[]
    for transceiver in peer.getTransceivers():
        for endpoint in (transceiver.sender,transceiver.receiver):
            dtls=getattr(endpoint,'transport',None)
            ice=getattr(dtls,'transport',None)
            if ice is not None:
                transports.append(ice)
    sctp=getattr(peer,'sctp',None)
    ice=getattr(getattr(sctp,'transport',None),'transport',None)
    if ice is not None:
        transports.append(ice)
    seen_transports=set()
    endpoints=set()
    for transport in transports:
        if id(transport) in seen_transports:
            continue
        seen_transports.add(id(transport))
        gatherer=transport.iceGatherer
        if gatherer.state!='completed':
            raise MobileRelayUnavailable()
        for candidate in gatherer.getLocalCandidates():
            if (candidate.type!='host' or candidate.protocol.lower()!='udp'
                    or candidate.component!=1 or not _valid_ipv4(candidate.ip)
                    or type(candidate.port) is not int or not 1024<=candidate.port<=65535):
                continue
            endpoints.add((candidate.ip,candidate.port))
    if not endpoints or len(endpoints)>32 or relay_address not in {ip for ip,port in endpoints}:
        raise MobileRelayUnavailable()
    return [{'ip':ip,'port':port} for ip,port in sorted(endpoints)]


class MobileRelayRegistry:
    """One process owns the registry; the relay reads complete atomic snapshots."""
    def __init__(self,config):
        if not isinstance(config,MobileRelayConfiguration) or not config.enabled:
            raise ValueError('Enabled private mobile relay configuration required')
        self.config=config
        self.path=Path(config.registry_file)
        self._lock=None
        self._sessions={}
        self._poisoned=False
        try:
            # Never truncate before lock acquisition: another owner may be live.
            self._lock=open(str(self.path)+'.lock','a+b')
            self._lock.seek(0,os.SEEK_END)
            if self._lock.tell()==0:
                self._lock.write(b'0');self._lock.flush()
            self._lock.seek(0)
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(self._lock.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(self._lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except (OSError,ValueError):
            if self._lock is not None:
                self._lock.close();self._lock=None
            raise MobileRelayUnavailable() from None
        try:
            self._publish({})
        except BaseException:
            self._release()
            raise

    def __repr__(self):
        return '<MobileRelayRegistry owned='+str(self._lock is not None)+'>'

    def _require_owned(self):
        if self._lock is None or self._poisoned:
            raise MobileRelayUnavailable()

    def _publish(self,sessions):
        self._require_owned()
        temp=None
        try:
            encoded=json.dumps({'version':1,'sessions':list(sessions.values())},
                               separators=(',',':'),allow_nan=False).encode('utf8')
            fd,temp=tempfile.mkstemp(prefix=self.path.name+'.',suffix='.tmp',dir=self.path.parent)
            with os.fdopen(fd,'wb') as handle:
                handle.write(encoded);handle.flush();os.fsync(handle.fileno())
            os.replace(temp,self.path)
            temp=None
            self._sessions=sessions
        except (OSError,ValueError,TypeError):
            self._poisoned=True
            self._sessions={}
            # A stale allowlist must not survive a failed atomic update.
            try:
                self.path.unlink(missing_ok=True)
            except OSError:
                raise MobileRelayUnavailable() from None
            raise MobileRelayUnavailable() from None
        finally:
            if temp is not None:
                try:Path(temp).unlink(missing_ok=True)
                except OSError:pass

    def _current(self):
        self._require_owned()
        now=time.time()
        return {key:value for key,value in self._sessions.items() if value['expires_at']>now}

    def register(self,session_id,instance,service_id,token_sha256,remaining_seconds):
        if (not isinstance(session_id,str) or _ID.fullmatch(session_id) is None
                or not isinstance(instance,str) or _LABEL.fullmatch(instance) is None
                or not isinstance(service_id,str) or _ID.fullmatch(service_id) is None
                or not isinstance(token_sha256,str) or _HASH.fullmatch(token_sha256) is None
                or type(remaining_seconds) not in (int,float)
                or not math.isfinite(remaining_seconds) or not 0<remaining_seconds<=3600):
            raise MobileRelayUnavailable()
        sessions=self._current()
        if session_id in sessions or len(sessions)>=128:
            raise MobileRelayUnavailable()
        sessions[session_id]={'id':session_id,'instance':instance,'service_id':service_id,
            'token_sha256':token_sha256,'expires_at':time.time()+remaining_seconds,'peers':[]}
        self._publish(sessions)

    def set_peers(self,session_id,peer):
        peers=local_udp_peers(peer,self.config.relay_address)
        sessions=self._current()
        if session_id not in sessions:
            raise MobileRelayUnavailable()
        sessions[session_id]={**sessions[session_id],'peers':peers}
        self._publish(sessions)

    def prune(self):
        self._publish(self._current())

    def revoke(self,session_id):
        sessions=self._current()
        sessions.pop(session_id,None)
        self._publish(sessions)

    def _release(self):
        if self._lock is not None:
            self._lock.close();self._lock=None

    def close(self):
        if self._lock is None:
            return
        try:
            if not self._poisoned:
                self._publish({})
        finally:
            self._release()
