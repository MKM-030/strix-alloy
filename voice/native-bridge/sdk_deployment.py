"""Validated operator startup policy for one SDK assistant on one instance.

No destination is inferred from request headers, query strings or credentials.
The SDK identity remains the 2.26 literal agent_operator. This policy does not
map an OAuth caller to the separate Bot backend's conversation identity.
"""
from dataclasses import dataclass
import math
import re
from urllib.parse import urlsplit

from sdk_admission_policy import SDK_AGENT_ID

_LABEL = re.compile(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z')
_SYS_ID = re.compile(r'[0-9a-f]{32}\Z')
_AUTHORIZATION_PATH = '/api/sn_voice_aia/ai_voice_agent/agents_authorized'


def _public_origin(value):
    """Require a canonical HTTPS DNS origin; no URL credentials or routing data.

    This is syntax validation, not DNS/TLS reachability verification. Operators
    must control the configured TLS proxy and its DNS. SDK 2.26 retains only
    scheme and host, so explicit ports are forbidden, as are local hostnames.
    """
    if (not isinstance(value,str) or not 1 <= len(value) <= 512
            or any(ord(c) < 33 or ord(c) > 126 for c in value)):
        raise ValueError('sdk_public_origin must be a canonical public HTTPS origin')
    try:
        parsed = urlsplit(value)
        host, port = parsed.hostname, parsed.port
    except ValueError:
        raise ValueError('sdk_public_origin must be a canonical public HTTPS origin') from None
    if (parsed.scheme != 'https' or not host or len(host) > 253
            or parsed.path or parsed.query or parsed.fragment
            or parsed.username is not None or parsed.password is not None
            or '.' not in host or not re.fullmatch(r'[a-z][a-z0-9-]*',host.rsplit('.',1)[-1])
            or any(not _LABEL.fullmatch(label) for label in host.split('.'))
            or host.endswith(('.local','.internal','.localhost'))
            or port is not None):
        raise ValueError('sdk_public_origin must be a canonical public HTTPS origin')
    expected = 'https://' + host
    if value != expected:
        raise ValueError('sdk_public_origin must be a canonical public HTTPS origin')


def valid_call_duration(value):
    return type(value) in (int,float) and 0 < value <= 3600 and math.isfinite(value)


@dataclass(frozen=True)
class SDKDeploymentPolicy:
    instance_name: str
    assistant_id: str
    voice_agent_id: str
    public_origin: str

    def __post_init__(self):
        if not isinstance(self.instance_name,str) or not _LABEL.fullmatch(self.instance_name):
            raise ValueError('SDK instance_name must be a canonical ServiceNow instance label')
        for name, value in (('assistant_id',self.assistant_id),('voice_agent_id',self.voice_agent_id)):
            if not isinstance(value,str) or not _SYS_ID.fullmatch(value):
                raise ValueError('SDK '+name+' must be an explicit lowercase 32-character sys_id')
        _public_origin(self.public_origin)

    @property
    def instance_url(self):
        return 'https://' + self.instance_name + '.service-now.com'

    @property
    def authorization_url(self):
        return self.instance_url + _AUTHORIZATION_PATH

    @property
    def sdk_agent_id(self):
        return SDK_AGENT_ID

    def matches_config(self, config):
        """Reject contradictory or changed config after startup; never rebind."""
        return (getattr(config,'sdk_policy',None) is self
            and getattr(config,'auth_mode',None) == 'servicenow'
            and not getattr(config,'development_token',None)
            and getattr(config,'instance_name',None) == self.instance_name
            and getattr(config,'instance_url',None) == self.instance_url
            and getattr(config,'voice_service_id',None) == self.assistant_id
            and getattr(config,'required_agent_id',None) == self.voice_agent_id
            and getattr(config,'sdk_public_origin',self.public_origin) == self.public_origin
            and valid_call_duration(getattr(config,'max_call_seconds',None)))
