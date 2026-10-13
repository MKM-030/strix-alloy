import asyncio
import io
import json
import tempfile
import unittest
from pathlib import Path

from aiohttp import FormData, web
from aiohttp.test_utils import TestClient, TestServer

from voice.mobile_gateway import GatewayConfig, create_app, load_password


ORIGIN = "https://strix-alloy.tail7f425a.ts.net"
HOST = "strix-alloy.tail7f425a.ts.net"
PASSWORD = "test-only-password-32-characters-long"


class GatewayTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.now = 100.0
        self.calls = []
        self.backend_csrf = "backend-csrf-1"
        self.backend_cookie = "private-bridge-cookie"
        self.reset_count = 0
        self.event_gate = asyncio.Event()
        self.slow_events = False
        self.slow_reset = False
        self.reset_headers_sent = asyncio.Event()
        self.reset_gate = asyncio.Event()
        self.reject_messages = False

        async def backend(request):
            self.calls.append((request.method, request.path, dict(request.headers)))
            if request.path == "/api/session":
                response = web.json_response({"csrf": self.backend_csrf,
                                              "serviceNowEnabled": True, "started": False})
                response.set_cookie("scc_voice", self.backend_cookie)
                return response
            if request.cookies.get("scc_voice") != self.backend_cookie:
                return web.json_response({"error": "backend cookie missing"}, status=401)
            if request.method == "POST":
                if request.headers.get("Origin") != str(self.backend_server.make_url("")).rstrip("/"):
                    return web.json_response({"error": "backend origin missing"}, status=403)
                if request.headers.get("X-CSRF-Token") != self.backend_csrf:
                    return web.json_response({"error": "backend csrf missing"}, status=403)
            if request.path == "/api/reset":
                self.reset_count += 1
                self.backend_csrf = "backend-csrf-" + str(self.reset_count + 1)
                self.backend_cookie = "private-bridge-cookie-" + str(self.reset_count + 1)
                if self.slow_reset:
                    response = web.StreamResponse(headers={"Content-Type": "application/json"})
                    response.set_cookie("scc_voice", self.backend_cookie)
                    await response.prepare(request)
                    self.reset_headers_sent.set()
                    await self.reset_gate.wait()
                    await response.write(json.dumps({"csrf": self.backend_csrf, "started": False}).encode())
                    await response.write_eof()
                    return response
                response = web.json_response({"csrf": self.backend_csrf, "started": False})
                response.set_cookie("scc_voice", self.backend_cookie)
                return response
            if request.path == "/api/events":
                if self.slow_events:
                    await self.event_gate.wait()
                return web.json_response({"events": [{"id": 1, "kind": "bot", "text": "Hallo"}],
                                          "cursor": 1, "choices": [{"label": "Ja", "value": "opaque"}]})
            if request.path in ("/api/speak", "/api/audio-test"):
                return web.Response(body=b"RIFF\x00\x00\x00\x00WAVE", content_type="audio/wav")
            if request.path == "/api/transcribe":
                part = await (await request.multipart()).next()
                self.upload = await part.read()
                return web.json_response({"text": "Mein Drucker funktioniert nicht."})
            self.payload = await request.json()
            if self.reject_messages and request.path == "/api/message":
                return web.json_response({"error": "Expired session"}, status=401)
            return web.json_response({"accepted": True}, status=202)

        mock = web.Application(client_max_size=25 * 1024 * 1024)
        mock.router.add_route("*", "/{tail:.*}", backend)
        self.backend_server = TestServer(mock)
        await self.backend_server.start_server()
        self.config = GatewayConfig(public_origin=ORIGIN, base_path="/scc-demo",
                                    backend_origin=str(self.backend_server.make_url("")).rstrip("/"),
                                    password=PASSWORD, session_ttl=100, idle_ttl=30,
                                    login_attempt_limit=3, clock=lambda: self.now)
        self.client = TestClient(TestServer(create_app(self.config)))
        await self.client.start_server()
        self.headers = {"Host": HOST, "Origin": ORIGIN}
        self.cookie = None
        self.csrf = None

    async def asyncTearDown(self):
        self.event_gate.set()
        self.reset_gate.set()
        await self.client.close()
        await self.backend_server.close()

    async def request(self, method, path, *, authenticated=True, **kwargs):
        headers = dict(self.headers)
        headers.update(kwargs.pop("headers", {}))
        if authenticated and self.cookie:
            headers["Cookie"] = self.cookie
            headers.setdefault("X-CSRF-Token", self.csrf)
        return await self.client.request(method, path, headers=headers, **kwargs)

    async def login(self):
        response = await self.request("POST", "/auth/login", json={"password": PASSWORD})
        self.assertEqual(response.status, 200, await response.text())
        self.cookie = "scc_mobile=" + response.cookies["scc_mobile"].value
        self.csrf = (await response.json())["csrf"]
        return response

    async def test_login_cookie_and_api_authentication(self):
        response = await self.request("GET", "/api/session")
        self.assertEqual(response.status, 401)
        self.assertEqual(self.calls, [])
        response = await self.login()
        cookie = response.cookies["scc_mobile"]
        self.assertTrue(cookie["httponly"])
        self.assertTrue(cookie["secure"])
        self.assertEqual(cookie["samesite"], "Strict")
        self.assertEqual(cookie["path"], "/scc-demo")
        response = await self.request("GET", "/api/session")
        payload = await response.json()
        self.assertEqual(payload["csrf"], self.csrf)
        self.assertNotIn("backend", str(payload))
        self.assertNotIn("scc_voice", response.headers.get("Set-Cookie", ""))
        self.assertEqual(response.headers["Cache-Control"], "no-store")

    async def test_exact_origin_host_csrf_and_whitelisted_paths(self):
        await self.login()
        for headers in ({"Origin": "https://evil.test"}, {"Origin": ORIGIN + "/"},
                        {"Host": "evil.test"}, {"X-CSRF-Token": "wrong"}, {"Origin": ""}):
            response = await self.request("POST", "/api/start", json={}, headers=headers)
            self.assertEqual(response.status, 403)
        for path in ("/api/other", "/api/session?url=http://evil.test", "/api/events?after=1&url=x",
                     "/api/events?after=-1", "/api/events?wait=999", "/api/events?after=1&after=2"):
            response = await self.request("GET", path)
            self.assertIn(response.status, (400, 404))
        response = await self.request("POST", "/api/session", json={})
        self.assertEqual(response.status, 405)
        self.assertEqual(self.calls, [])

    async def test_backend_cookie_csrf_reset_and_logout_reuse(self):
        await self.login()
        for path in ("/api/start", "/api/reset", "/api/message"):
            response = await self.request("POST", path, json={"text": "Drucker"} if "message" in path else {})
            self.assertIn(response.status, (200, 202), await response.text())
        self.assertEqual(self.payload, {"text": "Drucker"})
        self.assertEqual(len([c for c in self.calls if c[1] == "/api/session"]), 1)
        response = await self.request("POST", "/auth/logout", json={})
        self.assertEqual(response.status, 200)
        response = await self.request("POST", "/api/start", json={})
        self.assertEqual(response.status, 401)
        self.cookie = self.csrf = None
        await self.login()
        response = await self.request("POST", "/api/message", json={"choice": "opaque"})
        self.assertEqual(response.status, 202)
        self.assertEqual(len([c for c in self.calls if c[1] == "/api/session"]), 1)

    async def test_audio_upload_and_response(self):
        await self.login()
        form = FormData()
        form.add_field("file", io.BytesIO(b"RIFF-test-WAVE"), filename="speech.wav", content_type="audio/wav")
        response = await self.request("POST", "/api/transcribe", data=form)
        self.assertEqual(response.status, 200, await response.text())
        self.assertEqual(self.upload, b"RIFF-test-WAVE")
        response = await self.request("POST", "/api/speak", json={"eventId": 1})
        self.assertEqual(response.status, 200)
        self.assertEqual(response.headers["Content-Type"], "audio/wav")
        self.assertEqual(await response.read(), b"RIFF\x00\x00\x00\x00WAVE")

    async def test_login_limits_session_cap_and_expiry(self):
        for _ in range(3):
            response = await self.request("POST", "/auth/login", json={"password": "wrong"})
            self.assertEqual(response.status, 401)
        response = await self.request("POST", "/auth/login", json={"password": PASSWORD})
        self.assertEqual(response.status, 429)
        self.now += 61
        await self.login()
        response = await self.request("POST", "/auth/login", json={"password": PASSWORD}, authenticated=False)
        self.assertEqual(response.status, 409)
        self.now += 31
        response = await self.request("GET", "/api/session")
        self.assertEqual(response.status, 401)
        self.cookie = self.csrf = None
        await self.login()
        for _ in range(4):
            self.now += 25
            response = await self.request("GET", "/auth/session")
        self.assertFalse((await response.json())["authenticated"])

    async def test_content_limits_and_json_shape(self):
        await self.login()
        response = await self.request("POST", "/api/message", data=b"x" * (65536 + 1),
                                      headers={"Content-Type": "application/json"})
        self.assertEqual(response.status, 413)
        response = await self.request("POST", "/auth/login", json=[PASSWORD])
        self.assertEqual(response.status, 400)
        response = await self.request("POST", "/api/message", data="text=x")
        self.assertEqual(response.status, 415)
        response = await self.request("POST", "/api/transcribe", data=b"x" * 16,
                                      headers={"Content-Type": "text/plain"})
        self.assertEqual(response.status, 415)

    async def test_long_poll_does_not_block_send(self):
        await self.login()
        self.slow_events = True
        poll = asyncio.create_task(self.request("GET", "/api/events?after=0&wait=20"))
        await asyncio.sleep(0.03)
        response = await asyncio.wait_for(self.request("POST", "/api/message", json={"text": "Test"}), 1)
        self.assertEqual(response.status, 202)
        self.event_gate.set()
        self.assertEqual((await poll).status, 200)

    async def test_long_poll_concurrency_is_bounded(self):
        await self.login()
        self.slow_events = True
        polls = [asyncio.create_task(self.request("GET", "/api/events?after=0&wait=20")) for _ in range(2)]
        await asyncio.sleep(0.03)
        response = await self.request("GET", "/api/events?after=0&wait=20")
        self.assertEqual(response.status, 429)
        self.event_gate.set()
        for poll in polls:
            self.assertEqual((await poll).status, 200)

    async def test_chunked_oversize_body_is_bounded(self):
        await self.login()
        async def chunks():
            yield b"x" * 32768
            yield b"x" * 32769
        response = await self.request("POST", "/api/message", data=chunks(),
                                      headers={"Content-Type": "application/json"})
        self.assertEqual(response.status, 413)
        self.assertEqual(self.calls, [])

    async def test_public_assets_have_base_path_and_csp(self):
        with tempfile.TemporaryDirectory() as folder:
            self.config.static_dir = Path(folder)
            (self.config.static_dir / "index.html").write_text(
                '<html data-base-path="__SCC_BASE_PATH__"></html>', encoding="utf-8")
            response = await self.request("GET", "/", authenticated=False)
            self.assertEqual(response.status, 200)
            self.assertIn('data-base-path="/scc-demo"', await response.text())
            self.assertIn("frame-ancestors 'none'", response.headers["Content-Security-Policy"])
            self.assertNotIn(PASSWORD, await response.text())
        self.assertEqual(self.calls, [])

    async def test_reset_cookie_and_csrf_rotate_atomically_for_audio(self):
        await self.login()
        self.slow_reset = True
        reset = asyncio.create_task(self.request("POST", "/api/reset", json={}))
        await asyncio.wait_for(self.reset_headers_sent.wait(), 1)
        speak = asyncio.create_task(self.request("POST", "/api/speak", json={"eventId": 1}))
        await asyncio.sleep(0.03)
        self.assertFalse(speak.done())
        self.assertFalse(any(call[1] == "/api/speak" for call in self.calls))
        self.reset_gate.set()
        self.assertEqual((await reset).status, 200)
        self.assertEqual((await speak).status, 200)

    async def test_expired_backend_get_refreshes_once_without_replaying_mutations(self):
        await self.login()
        response = await self.request("GET", "/api/session")
        self.assertEqual(response.status, 200)
        self.backend_cookie = "expired-replaced-cookie"
        self.backend_csrf = "expired-replaced-csrf"
        response = await self.request("GET", "/api/events?after=0")
        self.assertEqual(response.status, 200)
        self.assertEqual(len([call for call in self.calls if call[1] == "/api/events"]), 2)
        self.reject_messages = True
        response = await self.request("POST", "/api/message", json={"text": "Create once"})
        self.assertEqual(response.status, 502)
        self.assertEqual(len([call for call in self.calls if call[1] == "/api/message"]), 1)

    def test_password_config_fails_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder) / "secret.txt"
            file.write_text("too-short", encoding="utf-8")
            with self.assertRaises(ValueError):
                load_password(file)
            file.write_text(PASSWORD + "\n", encoding="utf-8")
            self.assertEqual(load_password(file), PASSWORD)
        with self.assertRaises(ValueError):
            GatewayConfig(public_origin="http://example.test", password=PASSWORD)
        with self.assertRaises(ValueError):
            GatewayConfig(public_origin=ORIGIN, backend_origin="http://example.test", password=PASSWORD)


if __name__ == "__main__":
    unittest.main()
