"""Inactive, independently testable SDK session admission candidate.

This module registers no routes and produces no SDK session response, SDP or
WebSocket DTO. The caller must supply duplicate-preserving raw header pairs and
the complete, still-encoded request body, bounded while reading to 32 KiB. A
successful result is internal authorization context only. Bearer credentials
are never parsed as JWTs, logged, retained in context, or accepted locally.
"""
import asyncio
from dataclasses import dataclass
import json
import re

import aiohttp

from core import authorized_agents
from sdk_admission_policy import (
    ASSISTANT_ID, AUTHORIZATION_TIMEOUT_SECONDS, AUTHORIZATION_URL, INSTANCE_URL,
    MAX_AUTHORIZATION_BYTES, MAX_BODY_BYTES, MAX_HEADER_BYTES, MAX_HEADER_COUNT,
    MAX_RESPONSE_BYTES, VOICE_AGENT_BY_ASSISTANT, VOICE_AGENT_ID,
)

_HEADER_NAME = re.compile(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+\Z")
_BEARER = re.compile(r"(?i:Bearer) ([A-Za-z0-9._~+/-]+=*)\Z")
_CONTENT_TYPE = re.compile(r"application/json(?:\s*;\s*charset=utf-8)?\Z", re.I)
_CONFLICTING_AUTH_HEADERS = frozenset({
    "cookie", "proxy-authorization", "x-authorization", "x-access-token",
    "x-auth-token", "x-api-key", "x-api-token", "x-servicenow-token", "x-sn-jwt",
    "sec-websocket-protocol",
    "x-usertoken", "x-user-token", "x-jwt", "x-jwt-token", "x-bearer-token",
    "authentication", "x-auth", "x-token", "x-session-token",
    "x-forwarded-authorization", "x-forwarded-authentication",
})
_PUBLIC_ERRORS = {400: "bad_request", 401: "unauthorized", 403: "forbidden"}


class AdmissionDenied(Exception):
    """Only these fixed public error values may reach an eventual HTTP adapter."""
    def __init__(self, status):
        self.status = status
        self.code = _PUBLIC_ERRORS[status]
        super().__init__(self.code)

    @property
    def public_error(self):
        return {"error": self.code}


@dataclass(frozen=True)
class VerifiedContext:
    """Internal context; deliberately has no credential or SDK wire fields."""
    instance_url: str
    assistant_id: str
    voice_agent_id: str
    requested_assistant: bool
    requested_voice_agent: bool


def _validated_headers(raw_headers):
    if not isinstance(raw_headers, (list, tuple)) or len(raw_headers) > MAX_HEADER_COUNT:
        raise AdmissionDenied(400)
    headers = {}
    total_bytes = 0
    for pair in raw_headers:
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            raise AdmissionDenied(400)
        name, value = pair
        if not isinstance(name, str) or not _HEADER_NAME.fullmatch(name):
            raise AdmissionDenied(400)
        key = name.lower()
        error_status = 401 if key == "authorization" else 400
        if not isinstance(value, str) or any(ord(c) < 32 or ord(c) > 126 for c in value):
            raise AdmissionDenied(error_status)
        if key == "authorization" and len(value) > MAX_AUTHORIZATION_BYTES:
            raise AdmissionDenied(401)
        total_bytes += len(name) + len(value) + 4
        if total_bytes > MAX_HEADER_BYTES:
            raise AdmissionDenied(400)
        headers.setdefault(key, []).append(value)
    return headers


def _single_header(headers, name, *, required=False, status=400):
    values = headers.get(name, [])
    if len(values) > 1 or (required and not values):
        raise AdmissionDenied(status)
    return values[0] if values else None


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError("non-JSON constant")


def _strict_json(body):
    return json.loads(body.decode("utf-8"), object_pairs_hook=_unique_object,
                      parse_constant=_reject_constant)


def _validate_request(raw_headers, body, query_string):
    headers = _validated_headers(raw_headers)
    authorization = _single_header(headers, "authorization", required=True, status=401)
    if not _BEARER.fullmatch(authorization):
        raise AdmissionDenied(401)
    if any(name in headers for name in _CONFLICTING_AUTH_HEADERS):
        raise AdmissionDenied(401)
    if not isinstance(query_string, str) or query_string:
        raise AdmissionDenied(400)
    origin = _single_header(headers, "origin")
    if origin is not None and origin != INSTANCE_URL:
        raise AdmissionDenied(403)
    if "content-encoding" in headers or "transfer-encoding" in headers:
        raise AdmissionDenied(400)
    content_type = _single_header(headers, "content-type", required=True)
    if not _CONTENT_TYPE.fullmatch(content_type):
        raise AdmissionDenied(400)
    if not isinstance(body, bytes) or len(body) > MAX_BODY_BYTES:
        raise AdmissionDenied(400)
    content_length = _single_header(headers, "content-length")
    if content_length is not None:
        if not re.fullmatch(r"0|[1-9][0-9]*", content_length) or content_length != str(len(body)):
            raise AdmissionDenied(400)
    try:
        data = _strict_json(body)
    except (UnicodeError, ValueError, RecursionError):
        raise AdmissionDenied(400) from None
    if (not isinstance(data, dict) or set(data) != {"agent_id"} or
            not isinstance(data["agent_id"], str) or not data["agent_id"]):
        raise AdmissionDenied(400)
    requested_assistant = data["agent_id"] == ASSISTANT_ID
    requested_voice_agent = data["agent_id"] == VOICE_AGENT_BY_ASSISTANT[ASSISTANT_ID]
    if not (requested_assistant or requested_voice_agent):
        raise AdmissionDenied(403)
    return authorization, requested_assistant, requested_voice_agent


async def _bounded_response(response):
    if any(name.lower() == "content-encoding" for name in response.headers):
        raise AdmissionDenied(403)
    body = bytearray()
    while len(body) <= MAX_RESPONSE_BYTES:
        part = await response.content.read(MAX_RESPONSE_BYTES + 1 - len(body))
        if not part:
            return _strict_json(bytes(body))
        body.extend(part)
    raise AdmissionDenied(403)


async def admit_sdk_session(raw_headers, body, *, query_string="", http_factory=None):
    """Verify a POST /api/webrtc/sessions request without activating that API.

    ``http_factory`` is an offline test seam. Integration uses the default new
    ClientSession with an empty cookie jar and environment credentials disabled.
    Body ``agent_id`` may be the pinned assistant OR its pinned voice agent; both
    always authorize the same serviceId and require the same authorized agent.
    No platform test-mode field is sent, so active-service policy is preserved.
    """
    authorization, requested_assistant, requested_voice_agent = _validate_request(
        raw_headers, body, query_string)
    factory = aiohttp.ClientSession if http_factory is None else http_factory
    try:
        async with asyncio.timeout(AUTHORIZATION_TIMEOUT_SECONDS):
            async with factory(
                cookie_jar=aiohttp.DummyCookieJar(), trust_env=False,
                auto_decompress=False,
                skip_auto_headers={"Accept-Encoding"},
                timeout=aiohttp.ClientTimeout(total=AUTHORIZATION_TIMEOUT_SECONDS),
            ) as http:
                async with http.post(
                    AUTHORIZATION_URL, json={"serviceId": ASSISTANT_ID},
                    headers={"Authorization": authorization, "Content-Type": "application/json",
                             "Accept-Encoding": "identity"},
                    allow_redirects=False,
                ) as response:
                    if response.status != 200:
                        raise AdmissionDenied(401 if response.status == 401 else 403)
                    data = await _bounded_response(response)
                    if not authorized_agents(data, VOICE_AGENT_ID):
                        raise AdmissionDenied(403)
    except AdmissionDenied:
        raise
    except Exception:
        # Suppress platform/network/parser details; caller cancellation still
        # propagates because CancelledError is a BaseException, not Exception.
        raise AdmissionDenied(403) from None
    return VerifiedContext(INSTANCE_URL, ASSISTANT_ID, VOICE_AGENT_ID,
                           requested_assistant, requested_voice_agent)
