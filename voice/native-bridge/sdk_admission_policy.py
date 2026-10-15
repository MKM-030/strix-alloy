"""Pinned admission policy. No runtime configuration or test-mode override."""
from types import MappingProxyType

INSTANCE_URL = "https://soprasteriaassvsdemo14.service-now.com"
INSTANCE_NAME = "soprasteriaassvsdemo14"
SDK_AGENT_ID = "agent_operator"
ASSISTANT_ID = "8aa131d793f787105c8132d47aba1095"
VOICE_AGENT_ID = "a6337ddf93f787105c8132d47aba1058"
VOICE_AGENT_BY_ASSISTANT = MappingProxyType({ASSISTANT_ID: VOICE_AGENT_ID})
AUTHORIZATION_URL = INSTANCE_URL + "/api/sn_voice_aia/ai_voice_agent/agents_authorized"
MAX_QUERY_BYTES = 4096
MAX_QUERY_FIELDS = 3
MAX_BODY_BYTES = 32768
MAX_RESPONSE_BYTES = 32768
MAX_AUTHORIZATION_BYTES = 8192
MAX_HEADER_BYTES = 16384
MAX_HEADER_COUNT = 64
AUTHORIZATION_TIMEOUT_SECONDS = 10
