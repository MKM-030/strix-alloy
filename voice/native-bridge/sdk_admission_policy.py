"""Fixed SDK protocol identity and bounded admission resource limits.

Deployment allowlists live only in the validated SDKDeploymentPolicy supplied
at startup. Missing policy denies admission; there is no demo fallback.
"""
SDK_AGENT_ID = "agent_operator"
MAX_QUERY_BYTES = 4096
MAX_QUERY_FIELDS = 3
MAX_BODY_BYTES = 32768
MAX_RESPONSE_BYTES = 262144
MAX_AUTHORIZATION_BYTES = 8192
MAX_HEADER_BYTES = 16384
MAX_HEADER_COUNT = 64
AUTHORIZATION_TIMEOUT_SECONDS = 10
