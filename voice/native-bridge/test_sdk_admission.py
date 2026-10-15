"""Offline admission tests. All tokens are synthetic fixtures; no real HTTP."""
import asyncio
import dataclasses
import importlib
import json
from pathlib import Path
import unittest

try:
    candidate = importlib.import_module("sdk_admission")
except ModuleNotFoundError as exc:
    if exc.name != "sdk_admission":
        raise
    candidate = None

FIXTURES = json.loads(Path(__file__).with_name("sdk226-fixtures.json").read_text())
INSTANCE = "https://soprasteriaassvsdemo14.service-now.com"
ASSISTANT = "8aa131d793f787105c8132d47aba1095"
VOICE_AGENT = "a6337ddf93f787105c8132d47aba1058"
AUTH_URL = INSTANCE + "/api/sn_voice_aia/ai_voice_agent/agents_authorized"


class FakeContent:
    def __init__(self, body, chunk_size=13):
        self.body = body
        self.chunk_size = chunk_size
        self.offset = 0

    async def read(self, size):
        end = min(self.offset + size, self.offset + self.chunk_size, len(self.body))
        part = self.body[self.offset:end]
        self.offset = end
        return part


class FakeResponse:
    def __init__(self, status=200, payload=None, raw=None, headers=None):
        self.status = status
        self.headers = headers or {}
        if raw is None:
            raw = json.dumps(FIXTURES["authorized"] if payload is None else payload).encode()
        self.content = FakeContent(raw)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


class FakeHttp:
    def __init__(self, response=None, error=None):
        self.response = response or FakeResponse()
        self.error = error
        self.calls = []
        self.factory_calls = []

    def factory(self, **kwargs):
        self.factory_calls.append(kwargs)
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if self.error:
            raise self.error
        return self.response


class AdmissionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.assertIsNotNone(candidate, "SDK admission candidate is not implemented")
        self.http = FakeHttp()
        self.token = FIXTURES["synthetic_tokens"]["opaque"]
        self.headers = [("Authorization", "Bearer " + self.token),
                        ("Content-Type", "application/json")]
        self.body = FIXTURES["sdk_226_create"]["body"].encode()
        self.query = FIXTURES["sdk_226_create"]["query_string"]

    async def admit(self, headers=None, body=None, query_string=None, http=None):
        return await candidate.admit_sdk_session(
            self.headers if headers is None else headers,
            self.body if body is None else body,
            query_string=self.query if query_string is None else query_string,
            http_factory=(self.http if http is None else http).factory)

    async def denied(self, status, headers=None, body=None, query_string=None, http=None):
        transport = self.http if http is None else http
        with self.assertRaises(candidate.AdmissionDenied) as caught:
            await self.admit(headers, body, query_string, transport)
        error = caught.exception
        self.assertEqual(error.status, status)
        expected = {400: "bad_request", 401: "unauthorized", 403: "forbidden"}[status]
        self.assertEqual(error.public_error, {"error": expected})
        self.assertEqual(str(error), expected)
        self.assertNotIn(self.token, repr(error))
        self.assertNotIn(ASSISTANT, repr(error))
        self.assertNotIn(VOICE_AGENT, repr(error))
        return error

    async def test_opaque_oauth_without_origin_returns_only_internal_context(self):
        context = await self.admit()
        self.assertIsInstance(context, candidate.VerifiedContext)
        self.assertEqual(context.instance_url, INSTANCE)
        self.assertEqual(context.assistant_id, ASSISTANT)
        self.assertEqual(context.voice_agent_id, VOICE_AGENT)
        self.assertEqual(context.sdk_agent_id, "agent_operator")
        self.assertIs(context.receive_data, True)
        self.assertNotIn(self.token, repr(context))
        self.assertEqual(set(dataclasses.asdict(context)), {
            "instance_url", "assistant_id", "voice_agent_id",
            "sdk_agent_id", "receive_data"})
        with self.assertRaises(dataclasses.FrozenInstanceError):
            context.assistant_id = "0" * 32

    async def test_jwt_is_forwarded_unchanged_and_never_accepted_without_platform(self):
        token = FIXTURES["synthetic_tokens"]["jwt"]
        headers = [("Authorization", "Bearer " + token), ("Content-Type", "application/json")]
        denied_http = FakeHttp(FakeResponse(status=401))
        await self.denied(401, headers=headers, http=denied_http)
        self.assertEqual(denied_http.calls[0][1]["headers"]["Authorization"], "Bearer " + token)

    async def test_actual_sdk_literal_requires_platform_authorization(self):
        try:
            await self.admit()
        except candidate.AdmissionDenied as error:
            self.fail("actual SDK 2.26 create fixture was rejected: " + error.code)
        self.assertEqual(self.http.calls[0][1]["json"], {"serviceId": ASSISTANT})
        await self.denied(403, http=FakeHttp(FakeResponse(payload={"result": []})))

    async def test_fixed_platform_post_excludes_testmode_clientapp_and_redirects(self):
        await self.admit()
        self.assertEqual(len(self.http.calls), 1)
        url, options = self.http.calls[0]
        self.assertEqual(url, AUTH_URL)
        self.assertEqual(options["json"], {"serviceId": ASSISTANT})
        self.assertEqual(options["headers"], {"Authorization": "Bearer " + self.token,
                                               "Content-Type": "application/json",
                                               "Accept": "application/json",
                                               "Accept-Encoding": "identity"})
        self.assertFalse(options["allow_redirects"])

    async def test_dedicated_client_disables_cookies_environment_and_decompression(self):
        await self.admit()
        options = self.http.factory_calls[0]
        self.assertFalse(options["trust_env"])
        self.assertFalse(options["auto_decompress"])
        self.assertEqual(options.get("skip_auto_headers"), {"Accept-Encoding"})
        self.assertEqual(type(options["cookie_jar"]).__name__, "DummyCookieJar")
        self.assertEqual(options["timeout"].total, 10)

    async def test_valid_matching_origin_is_optional(self):
        await self.admit(headers=self.headers + [("Origin", INSTANCE)])

    async def test_lowercase_header_and_scheme_preserve_original_bearer(self):
        headers = [("authorization", "bearer " + self.token), ("content-type", "application/json")]
        await self.admit(headers=headers)
        self.assertEqual(self.http.calls[0][1]["headers"]["Authorization"], "bearer " + self.token)

    async def test_missing_authorization(self):
        await self.denied(401, headers=[("Content-Type", "application/json")])
        self.assertFalse(self.http.calls)

    async def test_duplicate_authorization_case_insensitive(self):
        await self.denied(401, headers=self.headers + [("authorization", "Bearer " + self.token)])
        self.assertFalse(self.http.calls)

    async def test_malformed_or_ambiguous_bearer_headers(self):
        values = ["", "Basic fixture", "Bearer", "Bearer ", " Bearer " + self.token,
                  "Bearer  " + self.token, "Bearer " + self.token + " ",
                  "Bearer one,two", "Bearer one;two", "Bearer one\ttwo",
                  "Bearer one\r\ntwo", "Bearer fixture:token", "Bearer fïxture"]
        for value in values:
            with self.subTest(value=value):
                await self.denied(401, headers=[("Authorization", value), self.headers[1]])
        self.assertFalse(self.http.calls)

    async def test_oversized_bearer_is_rejected_before_http(self):
        await self.denied(401, headers=[("Authorization", "Bearer " + "x" * 8192), self.headers[1]])
        self.assertFalse(self.http.calls)

    async def test_cookies_are_not_an_authentication_source(self):
        for value in ("", "session=fixture"):
            with self.subTest(value=value):
                await self.denied(401, headers=self.headers + [("Cookie", value)])
        self.assertFalse(self.http.calls)

    async def test_conflicting_authentication_headers(self):
        names = ["Proxy-Authorization", "X-Authorization", "X-Access-Token", "X-Auth-Token",
                 "X-API-Key", "X-API-Token", "X-ServiceNow-Token", "X-SN-JWT",
                 "Sec-WebSocket-Protocol", "X-UserToken", "X-User-Token", "X-JWT",
                 "X-JWT-Token", "X-Bearer-Token", "Authentication", "X-Auth",
                 "X-Token", "X-Session-Token", "X-Forwarded-Authorization",
                 "X-Forwarded-Authentication"]
        for name in names:
            with self.subTest(name=name):
                await self.denied(401, headers=self.headers + [(name, "fixture")])
        self.assertFalse(self.http.calls)

    async def test_unrecognized_query_is_rejected(self):
        for query in ("jwt=fixture", "access_token=fixture", "agent_id=" + ASSISTANT, "unused=1"):
            with self.subTest(query=query):
                await self.denied(400, query_string=query)
        self.assertFalse(self.http.calls)

    async def test_sdk_optional_voice_service_uses_fixed_pinned_authorization(self):
        context = await self.admit(query_string=FIXTURES["sdk_226_create"]["query_string_with_voice_service"])
        self.assertEqual(context.assistant_id, ASSISTANT)
        self.assertEqual(self.http.calls[0][1]["json"], {"serviceId": ASSISTANT})

    async def test_missing_sdk_query_fields_are_bad_request(self):
        for query in ("", "instance_name=soprasteriaassvsdemo14", "receive_data=true"):
            with self.subTest(query=query):
                await self.denied(400, query_string=query)
        self.assertFalse(self.http.calls)

    async def test_duplicate_sdk_query_fields_are_rejected(self):
        queries = (self.query + "&instance_name=soprasteriaassvsdemo14",
                   self.query + "&receive_data=true",
                   self.query + "&voice_service_id=" + ASSISTANT + "&voice_service_id=" + ASSISTANT,
                   self.query + "&%72eceive_data=true")
        for query in queries:
            with self.subTest(query=query):
                await self.denied(400, query_string=query)
        self.assertFalse(self.http.calls)

    async def test_sdk_instance_value_is_exact_short_name(self):
        for value in ("", "other", INSTANCE, "soprasteriaassvsdemo14.service-now.com",
                      "SOPRASTERIAASSVSDEMO14", "soprasteriaassvsdemo14/", "soprasteriaassvsdemo14.evil.example"):
            with self.subTest(instance=value):
                await self.denied(403, query_string="instance_name=" + value + "&receive_data=true")
        self.assertFalse(self.http.calls)

    async def test_voice_service_query_cannot_select_unpinned_service(self):
        for value in ("", VOICE_AGENT, "0" * 32, ASSISTANT.upper(), "%20" + ASSISTANT):
            with self.subTest(service=value):
                await self.denied(403, query_string=self.query + "&voice_service_id=" + value)
        self.assertFalse(self.http.calls)

    async def test_sdk_receive_data_must_be_literal_true(self):
        for value in ("", "false", "True", "1", "true "):
            with self.subTest(receive_data=value):
                await self.denied(400, query_string="instance_name=soprasteriaassvsdemo14&receive_data=" + value)
        self.assertFalse(self.http.calls)

    async def test_query_cannot_add_auth_or_test_mode_inputs(self):
        for key in ("jwt", "access_token", "authorization", "clientApp", "admin_test", "agent_id", "instance_url"):
            with self.subTest(key=key):
                await self.denied(400, query_string=self.query + "&" + key + "=fixture")
        self.assertFalse(self.http.calls)

    async def test_raw_query_syntax_encoding_and_length_are_bounded(self):
        for query in (None, b"instance_name=fixture", 1, "?" + self.query,
                      self.query + "&", self.query + "&voice_service_id",
                      self.query + "&voice_service_id=%", self.query + "&voice_service_id=%GG",
                      self.query + "&voice_service_id=%C3%28", self.query + "\r\n",
                      self.query + "é", self.query + "&voice_service_id=" + "x" * 4096):
            with self.subTest(query=query):
                if query is None:
                    with self.assertRaises(candidate.AdmissionDenied) as caught:
                        await candidate.admit_sdk_session(self.headers, self.body, query_string=None, http_factory=self.http.factory)
                    self.assertEqual(caught.exception.status, 400)
                else:
                    await self.denied(400, query_string=query)
        self.assertFalse(self.http.calls)

    async def test_sdk_query_percent_encoding_is_decoded_once(self):
        await self.admit(query_string="instance_name=soprasteriaassvsdemo14&receive_data=%74rue&voice_service_id=" + ASSISTANT)
        await self.denied(403, query_string=self.query + "&voice_service_id=" + ASSISTANT + "%26jwt%3Dfixture")

    async def test_unapproved_or_malformed_origin_is_forbidden(self):
        origins = ["null", "https://evil.example", INSTANCE + "/", INSTANCE + ":443",
                   INSTANCE + " https://evil.example", "http://soprasteriaassvsdemo14.service-now.com",
                   "https://soprasteriaassvsdemo14.service-now.com.evil.example"]
        for origin in origins:
            with self.subTest(origin=origin):
                await self.denied(403, headers=self.headers + [("Origin", origin)])
        self.assertFalse(self.http.calls)

    async def test_duplicate_origin_is_bad_request(self):
        await self.denied(400, headers=self.headers + [("Origin", INSTANCE), ("origin", INSTANCE)])
        self.assertFalse(self.http.calls)

    async def test_exact_json_shape_and_duplicate_keys(self):
        for body in FIXTURES["invalid_request_bodies"]:
            with self.subTest(body=body):
                await self.denied(400, body=body.encode())
        self.assertFalse(self.http.calls)

    async def test_invalid_utf8_and_bom_are_bad_request(self):
        for body in (b"\xff", b"\xef\xbb\xbf" + self.body):
            with self.subTest(body=body):
                await self.denied(400, body=body)
        self.assertFalse(self.http.calls)

    async def test_body_limit_applies_to_wire_bytes(self):
        await self.denied(400, body=self.body + b" " * 32768)
        self.assertFalse(self.http.calls)

    async def test_body_exactly_at_limit_is_accepted(self):
        await self.admit(body=self.body + b" " * (32768 - len(self.body)))

    async def test_request_body_must_be_raw_bytes(self):
        await self.denied(400, body=self.body.decode())
        self.assertFalse(self.http.calls)

    async def test_wrong_agent_never_triggers_platform_request(self):
        for agent in (ASSISTANT, VOICE_AGENT, "0" * 32, "AGENT_OPERATOR",
                      " agent_operator", "agent_operator "):
            with self.subTest(agent=agent):
                await self.denied(403, body=json.dumps({"agent_id": agent}).encode())
        self.assertFalse(self.http.calls)

    async def test_content_type_is_required_json_with_optional_utf8(self):
        await self.admit(headers=[self.headers[0], ("Content-Type", "application/json; charset=utf-8")])
        for content_type in ("text/plain", "application/json; charset=latin-1",
                             "application/json; clientApp=admin_test", "application/json, text/plain"):
            with self.subTest(content_type=content_type):
                await self.denied(400, headers=[self.headers[0], ("Content-Type", content_type)])
        await self.denied(400, headers=[self.headers[0]])

    async def test_duplicate_content_type_is_bad_request(self):
        await self.denied(400, headers=self.headers + [("content-type", "application/json")])
        self.assertFalse(self.http.calls)

    async def test_request_encoding_is_rejected_even_identity(self):
        for value in ("gzip", "identity", ""):
            with self.subTest(value=value):
                await self.denied(400, headers=self.headers + [("Content-Encoding", value)])
        self.assertFalse(self.http.calls)

    async def test_content_length_must_match_and_cannot_be_duplicated(self):
        await self.admit(headers=self.headers + [("Content-Length", str(len(self.body)))])
        for value in ("-1", "0", str(len(self.body) + 1), "1,2", "000" + str(len(self.body))):
            with self.subTest(value=value):
                await self.denied(400, headers=self.headers + [("Content-Length", value)])
        await self.denied(400, headers=self.headers + [("Content-Length", str(len(self.body))),
                                                    ("content-length", str(len(self.body)))])

    async def test_transfer_encoding_is_rejected_for_bounded_json(self):
        await self.denied(400, headers=self.headers + [("Transfer-Encoding", "chunked")])
        self.assertFalse(self.http.calls)

    async def test_non_string_or_malformed_raw_headers_are_bad_request(self):
        for headers in (self.headers + [("X-Bad", 1)], self.headers + [("bad\rname", "fixture")],
                        self.headers + [("X-Bad", "fixture\n")], ["invalid-pair"], {"Authorization": "fixture"}):
            with self.subTest(headers=headers):
                await self.denied(400, headers=headers)
        self.assertFalse(self.http.calls)

    async def test_raw_header_count_and_total_bytes_are_bounded(self):
        await self.denied(400, headers=self.headers + [("X-Fixture", "x")] * 100)
        await self.denied(400, headers=self.headers + [("X-Fixture", "x" * 32768)])
        self.assertFalse(self.http.calls)

    async def test_upstream_401_is_generic_unauthorized(self):
        await self.denied(401, http=FakeHttp(FakeResponse(status=401, raw=b"fixture-private-detail")))

    async def test_upstream_403_is_generic_forbidden(self):
        await self.denied(403, http=FakeHttp(FakeResponse(status=403, raw=b"fixture-private-detail")))

    async def test_redirects_and_other_upstream_statuses_fail_closed(self):
        for status in (201, 204, 301, 302, 307, 308, 400, 404, 429, 500, 503):
            with self.subTest(status=status):
                await self.denied(403, http=FakeHttp(FakeResponse(status=status)))

    async def test_authorized_agents_requires_strict_core_schema_and_pinned_voice_agent(self):
        for payload in FIXTURES["malformed_authorization_responses"]:
            with self.subTest(payload=payload):
                await self.denied(403, http=FakeHttp(FakeResponse(payload=payload)))

    async def test_authorized_agents_may_include_other_valid_ids(self):
        await self.admit(http=FakeHttp(FakeResponse(payload={"result": ["0" * 32, VOICE_AGENT]})))

    async def test_malformed_duplicate_or_invalid_utf8_upstream_json_fails_closed(self):
        for raw in (b"not-json", b"\xff", b"\xef\xbb\xbf{}",
                    ('{"result":[],"result":["' + VOICE_AGENT + '"]}').encode()):
            with self.subTest(raw=raw):
                await self.denied(403, http=FakeHttp(FakeResponse(raw=raw)))

    async def test_oversized_upstream_body_fails_closed(self):
        await self.denied(403, http=FakeHttp(FakeResponse(raw=b" " * 32769)))

    async def test_compressed_upstream_body_fails_closed(self):
        await self.denied(403, http=FakeHttp(FakeResponse(headers={"Content-Encoding": "gzip"})))

    async def test_network_error_timeout_and_private_details_are_suppressed(self):
        for error in (OSError("fixture-private-token"), asyncio.TimeoutError("fixture-private-token")):
            with self.subTest(error=type(error).__name__):
                denied = await self.denied(403, http=FakeHttp(error=error))
                self.assertNotIn("fixture-private-token", repr(denied))
                self.assertTrue(denied.__suppress_context__)

    async def test_caller_cancellation_is_propagated(self):
        with self.assertRaises(asyncio.CancelledError):
            await self.admit(http=FakeHttp(error=asyncio.CancelledError()))


if __name__ == "__main__":
    unittest.main(verbosity=2)
