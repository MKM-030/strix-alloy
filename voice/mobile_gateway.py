"""Bounded HTTPS-facing adapter for the private, single-operator voice bridge.

Run only on 127.0.0.1 behind the configured HTTPS reverse proxy. The proxy must
strip /scc-demo and preserve the public Host header. No forwarded headers are
trusted, no arbitrary upstream paths are accepted, and bridge credentials never
leave the server. The callback password file is read once at startup.

Restart this gateway and the bridge together: the bridge's single-session slot
is intentionally retained in memory across mobile logouts, not written to disk.
ASR/TTS workers do not need to be restarted when these two HTTP services restart.
"""

from __future__ import annotations

import argparse
import asyncio
import hmac
import json
import re
import secrets
import time
from collections import deque
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit

from aiohttp import ClientError, ClientSession, ClientTimeout, CookieJar, web


COOKIE = "scc_mobile"
JSON_LIMIT = 64 * 1024
UPLOAD_LIMIT = 21 * 1024 * 1024
AUDIO_LIMIT = 20 * 1024 * 1024
ROUTES = {
    "/api/session": "GET", "/api/events": "GET", "/api/start": "POST",
    "/api/message": "POST", "/api/reset": "POST", "/api/transcribe": "POST",
    "/api/audio-test": "POST", "/api/speak": "POST",
}


def load_password(path: Path) -> str:
    password = path.read_text(encoding="utf-8-sig").strip()
    if not 24 <= len(password) <= 512:
        raise ValueError("Mobile access requires a callback password of 24 to 512 characters")
    return password


@dataclass
class GatewayConfig:
    public_origin: str
    password: str = field(repr=False)
    base_path: str = "/scc-demo"
    backend_origin: str = "http://127.0.0.1:8850"
    static_dir: Path = field(default_factory=lambda: Path(__file__).with_name("mobile_static"))
    session_ttl: int = 3600
    idle_ttl: int = 900
    login_attempt_limit: int = 5
    login_window: int = 60
    clock: Callable[[], float] = field(default=time.monotonic, repr=False)

    def __post_init__(self):
        public = urlsplit(self.public_origin)
        if (public.scheme != "https" or not public.hostname or public.username or public.password
                or public.path or public.query or public.fragment or public.port not in (None, 443)):
            raise ValueError("public_origin must be an exact HTTPS origin")
        if not re.fullmatch(r"/[A-Za-z0-9_-]+", self.base_path):
            raise ValueError("base_path must be one absolute path segment")
        backend = urlsplit(self.backend_origin)
        if (backend.scheme != "http" or backend.hostname != "127.0.0.1" or not backend.port
                or backend.username or backend.password or backend.path or backend.query or backend.fragment):
            raise ValueError("backend_origin must be an exact 127.0.0.1 HTTP origin with port")
        if not 24 <= len(self.password) <= 512:
            raise ValueError("Mobile access requires a password of 24 to 512 characters")
        if not (0 < self.idle_ttl <= self.session_ttl <= 3600):
            raise ValueError("Session lifetime must be bounded by one hour")
        if not (1 <= self.login_attempt_limit <= 10 and 30 <= self.login_window <= 3600):
            raise ValueError("Login rate limit is outside safe bounds")


@dataclass
class AuthSession:
    token: str
    csrf: str
    created: float
    touched: float


def failure(status: int, message: str) -> web.Response:
    return web.json_response({"error": message}, status=status)


class MobileGateway:
    def __init__(self, config: GatewayConfig):
        self.config = config
        self.auth: AuthSession | None = None  # Single fixed operator; never unbounded.
        self.attempts: deque[float] = deque(maxlen=config.login_attempt_limit)
        self.backend: ClientSession | None = None
        self.backend_csrf: str | None = None
        self.backend_needs_refresh = False
        self.bootstrap_lock = asyncio.Lock()
        self.mutation_lock = asyncio.Lock()
        self.credential_condition = asyncio.Condition()
        self.active_posts = 0
        self.rotation_waiters = 0
        self.rotating = False
        self.inflight = 0
        self.audio_inflight = 0
        self.polls_inflight = 0

    async def lifecycle(self, app):
        # unsafe=True is required solely for cookies from the pinned loopback IP.
        self.backend = ClientSession(cookie_jar=CookieJar(unsafe=True),
                                     timeout=ClientTimeout(total=200, connect=5),
                                     trust_env=False)
        yield
        await self.backend.close()
        self.auth = None

    def session(self, request, *, touch=True):
        now = self.config.clock()
        current = self.auth
        if current and (now - current.created >= self.config.session_ttl
                        or now - current.touched >= self.config.idle_ttl):
            self.auth = current = None
        supplied = request.cookies.get(COOKIE, "")
        if not current or not hmac.compare_digest(supplied.encode("utf-8"), current.token.encode("utf-8")):
            return None
        if touch:
            current.touched = now
        return current

    @web.middleware
    async def protect(self, request, handler):
        origins = request.headers.getall("Origin", [])
        origin = origins[0] if len(origins) == 1 else None
        expected_host = urlsplit(self.config.public_origin).netloc
        if request.headers.getall("Host", []) != [expected_host]:
            response = failure(403, "Unzulässiger Host.")
        elif (len(origins) > 1 or (origin is not None and origin != self.config.public_origin)
              or (request.method not in ("GET", "HEAD") and origin != self.config.public_origin)):
            response = failure(403, "Unzulässiger Ursprung.")
        elif (request.headers.get("Sec-Fetch-Site") == "cross-site"
              and not (request.method in ("GET", "HEAD") and request.path == "/"
                       and request.headers.get("Sec-Fetch-Mode") == "navigate"
                       and request.headers.get("Sec-Fetch-Dest") == "document")):
            # Links from chat/Now Mobile may open the public login document.
            # Cross-site APIs, mutations, subresources and frames remain denied.
            response = failure(403, "Unzulässige Anfrage.")
        else:
            try:
                response = await handler(request)
            except web.HTTPException as exc:
                response = failure(exc.status, "Anfrage nicht zulässig.")
            except (ClientError, asyncio.TimeoutError):
                response = failure(502, "Die Sprachverbindung ist gerade nicht erreichbar.")
        response.headers.update({
            "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer", "X-Frame-Options": "DENY",
            "Permissions-Policy": "microphone=(self), camera=(), geolocation=()",
            "Content-Security-Policy": "default-src 'none'; script-src 'self'; style-src 'self'; "
                "connect-src 'self'; media-src 'self' blob:; img-src 'self' data:; "
                "frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
            "Strict-Transport-Security": "max-age=31536000",
        })
        return response

    async def read_bounded(self, request, maximum):
        if request.content_length is not None and request.content_length > maximum:
            raise web.HTTPRequestEntityTooLarge(max_size=maximum, actual_size=request.content_length)
        result = bytearray()
        try:
            async with asyncio.timeout(30):
                async for chunk in request.content.iter_chunked(65536):
                    result.extend(chunk)
                    if len(result) > maximum:
                        raise web.HTTPRequestEntityTooLarge(max_size=maximum, actual_size=len(result))
        except TimeoutError:
            raise web.HTTPRequestTimeout() from None
        return bytes(result)

    async def read_json(self, request, maximum=JSON_LIMIT):
        if request.content_type != "application/json":
            raise web.HTTPUnsupportedMediaType()
        try:
            value = json.loads(await self.read_bounded(request, maximum))
        except (ValueError, UnicodeError):
            raise web.HTTPBadRequest() from None
        if not isinstance(value, dict):
            raise web.HTTPBadRequest()
        return value

    def check_csrf(self, request, session):
        supplied = request.headers.get("X-CSRF-Token", "")
        return bool(supplied and hmac.compare_digest(supplied.encode("utf-8"), session.csrf.encode("utf-8")))

    async def auth_session(self, request):
        if request.query:
            raise web.HTTPBadRequest()
        current = self.session(request)
        if not current:
            return web.json_response({"authenticated": False})
        return web.json_response({"authenticated": True, "csrf": current.csrf,
                                  "expiresIn": max(0, int(self.config.session_ttl -
                                      (self.config.clock() - current.created)))})

    async def login(self, request):
        if request.query:
            raise web.HTTPBadRequest()
        now = self.config.clock()
        while self.attempts and now - self.attempts[0] >= self.config.login_window:
            self.attempts.popleft()
        if len(self.attempts) >= self.config.login_attempt_limit:
            response = failure(429, "Zu viele Anmeldeversuche. Bitte später erneut versuchen.")
            response.headers["Retry-After"] = str(self.config.login_window)
            return response
        self.attempts.append(now)
        payload = await self.read_json(request, 2048)
        password = payload.get("password")
        if (set(payload) != {"password"} or not isinstance(password, str) or len(password) > 512
                or not hmac.compare_digest(password.encode("utf-8"), self.config.password.encode("utf-8"))):
            return failure(401, "Anmeldung fehlgeschlagen.")
        current = self.session(request, touch=False)  # Purges expiry even without a cookie.
        if self.auth and not current:
            return failure(409, "Die Demo ist bereits geöffnet. Bitte dort abmelden oder später erneut versuchen.")
        self.auth = AuthSession(secrets.token_urlsafe(32), secrets.token_urlsafe(32), now, now)
        response = web.json_response({"authenticated": True, "csrf": self.auth.csrf})
        response.set_cookie(COOKIE, self.auth.token, path=self.config.base_path,
                            max_age=self.config.session_ttl, secure=True, httponly=True, samesite="Strict")
        return response

    async def logout(self, request):
        current = self.session(request)
        if not current:
            return failure(401, "Bitte anmelden.")
        if not self.check_csrf(request, current):
            return failure(403, "Ungültiger Sitzungsschutz.")
        if request.query:
            raise web.HTTPBadRequest()
        await self.read_json(request, 2048)
        if self.session(request, touch=False) is not current:
            return failure(401, "Bitte anmelden.")
        self.auth = None
        # Preserve the single bridge cookie jar across mobile logins. Discarding
        # it would allocate another backend slot on the next /api/session call.
        response = web.json_response({"authenticated": False})
        response.set_cookie(COOKIE, "", path=self.config.base_path, max_age=0,
                            secure=True, httponly=True, samesite="Strict")
        return response

    async def backend_response(self, method, path, *, data=None, headers=None, limit=1024 * 1024):
        assert self.backend is not None
        async with self.backend.request(method, self.config.backend_origin + path,
                                        data=data, headers=headers, allow_redirects=False) as response:
            body = bytearray()
            async for chunk in response.content.iter_chunked(65536):
                body.extend(chunk)
                if len(body) > limit:
                    raise web.HTTPBadGateway()
            return response.status, response.content_type, bytes(body)

    @asynccontextmanager
    async def credential_guard(self, *, exclusive=False, shared=False):
        """Keep a reset's cookie+CSRF rotation atomic relative to POSTs.

        Audio and message POSTs may overlap, while events never hold this gate.
        Waiting rotation takes priority so a stream of audio cannot starve reset.
        """
        if not exclusive and not shared:
            yield
            return
        condition = self.credential_condition
        async with condition:
            if exclusive:
                self.rotation_waiters += 1
                try:
                    await condition.wait_for(lambda: not self.rotating and self.active_posts == 0)
                    self.rotating = True
                finally:
                    self.rotation_waiters -= 1
                    condition.notify_all()
            else:
                await condition.wait_for(lambda: not self.rotating and self.rotation_waiters == 0)
                self.active_posts += 1
        try:
            yield
        finally:
            async with condition:
                if exclusive:
                    self.rotating = False
                else:
                    self.active_posts -= 1
                condition.notify_all()

    async def ensure_backend(self, *, force=False):
        if self.backend_csrf and not self.backend_needs_refresh and not force:
            return
        async with self.bootstrap_lock:
            if self.backend_csrf and not self.backend_needs_refresh and not force:
                return
            async with self.credential_guard(exclusive=True):
                status, mime, body = await self.backend_response("GET", "/api/session",
                    headers={"Origin": self.config.backend_origin})
                if status != 200 or mime != "application/json":
                    raise web.HTTPBadGateway()
                try:
                    token = json.loads(body)["csrf"]
                    if not isinstance(token, str) or not 1 <= len(token) <= 512:
                        raise ValueError()
                except (KeyError, ValueError, TypeError, UnicodeError):
                    raise web.HTTPBadGateway() from None
                self.backend_csrf = token
                self.backend_needs_refresh = False

    def proxy_path(self, request):
        if request.path != "/api/events":
            if request.query:
                raise web.HTTPBadRequest()
            return request.path
        if set(request.query) - {"after", "wait"}:
            raise web.HTTPBadRequest()
        for key, value in request.query.items():
            if len(request.query.getall(key)) != 1 or not re.fullmatch(r"[0-9]{1,10}", value):
                raise web.HTTPBadRequest()
            if int(value) > (20 if key == "wait" else 2147483647):
                raise web.HTTPBadRequest()
        return request.path + ("?" + str(request.query_string) if request.query else "")

    async def proxy(self, request):
        current = self.session(request)
        if not current:
            return failure(401, "Bitte anmelden.")
        path = self.proxy_path(request)
        if request.method == "POST" and not self.check_csrf(request, current):
            return failure(403, "Ungültiger Sitzungsschutz.")
        audio = request.path in ("/api/transcribe", "/api/speak", "/api/audio-test")
        poll = request.path == "/api/events"
        if self.inflight >= 6 or (audio and self.audio_inflight >= 2) or (poll and self.polls_inflight >= 2):
            return failure(429, "Bitte die laufende Anfrage abwarten.")
        self.inflight += 1
        self.audio_inflight += int(audio)
        self.polls_inflight += int(poll)
        try:
            data = None
            headers = {"Origin": self.config.backend_origin}
            if request.method == "POST":
                if request.path == "/api/transcribe":
                    if request.content_type != "multipart/form-data" or not request.headers.get("Content-Type"):
                        raise web.HTTPUnsupportedMediaType()
                    data = await self.read_bounded(request, UPLOAD_LIMIT)
                    headers["Content-Type"] = request.headers["Content-Type"]
                else:
                    payload = await self.read_json(request)
                    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                    headers["Content-Type"] = "application/json"
            await self.ensure_backend()
            async def forward():
                async with self.credential_guard(exclusive=request.path in ("/api/reset", "/api/session"),
                                                 shared=request.method == "POST"):
                    return await self.perform_proxy(request, current, path, data, headers, audio)
            async def attempt():
                if request.path in ("/api/start", "/api/message", "/api/reset", "/api/session"):
                    async with self.mutation_lock:
                        return await forward()
                return await forward()
            response = await attempt()
            if response.status in (401, 403) and self.session(request, touch=False) is current:
                if request.method == "GET":
                    # One safe refresh/retry for a bridge session that expired.
                    # Never replay start, message, reset or audio operations.
                    await self.ensure_backend(force=True)
                    response = await attempt()
                else:
                    self.backend_needs_refresh = True
                if response.status in (401, 403):
                    return failure(502, "Die Sprachsitzung ist abgelaufen. Bitte den Status erneut laden.")
            return response
        finally:
            self.inflight -= 1
            self.audio_inflight -= int(audio)
            self.polls_inflight -= int(poll)

    async def perform_proxy(self, request, current, path, data, headers, audio):
        # Queued requests may not proceed after logout or session expiry.
        if self.session(request, touch=False) is not current:
            return failure(401, "Bitte anmelden.")
        if request.method == "POST":
            headers["X-CSRF-Token"] = self.backend_csrf
        status, mime, body = await self.backend_response(request.method, path, data=data, headers=headers,
                                                       limit=AUDIO_LIMIT if audio else 1024 * 1024)
        if mime == "application/json":
            try:
                payload = json.loads(body)
            except (ValueError, UnicodeError):
                raise web.HTTPBadGateway() from None
            if not isinstance(payload, dict):
                raise web.HTTPBadGateway()
            if "csrf" in payload:
                token = payload["csrf"]
                if not isinstance(token, str) or not 1 <= len(token) <= 512:
                    raise web.HTTPBadGateway()
                self.backend_csrf = token
                payload["csrf"] = current.csrf
            return web.json_response(payload, status=status)
        if audio and status == 200 and mime in ("audio/wav", "audio/x-wav", "audio/wave"):
            return web.Response(body=body, content_type="audio/wav")
        # Never forward redirects, arbitrary headers, upstream HTML or cookies.
        return failure(502, "Ungültige Antwort der Sprachverbindung.")

    async def static(self, request):
        if request.query:
            raise web.HTTPBadRequest()
        names = {"/": ("index.html", "text/html"), "/app.js": ("app.js", "application/javascript"),
                 "/style.css": ("style.css", "text/css")}
        filename, mime = names[request.path]
        try:
            text = (self.config.static_dir / filename).read_text(encoding="utf-8")
        except OSError:
            raise web.HTTPNotFound() from None
        if filename == "index.html":
            text = text.replace("__SCC_BASE_PATH__", self.config.base_path)
        return web.Response(text=text, content_type=mime)


def create_app(config: GatewayConfig) -> web.Application:
    gateway = MobileGateway(config)
    app = web.Application(middlewares=[gateway.protect], client_max_size=UPLOAD_LIMIT)
    app.cleanup_ctx.append(gateway.lifecycle)
    app.router.add_get("/auth/session", gateway.auth_session)
    app.router.add_post("/auth/login", gateway.login)
    app.router.add_post("/auth/logout", gateway.logout)
    for path, method in ROUTES.items():
        app.router.add_route(method, path, gateway.proxy)
    for path in ("/", "/app.js", "/style.css"):
        app.router.add_get(path, gateway.static)
    return app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--password-file", type=Path, required=True)
    parser.add_argument("--public-origin", required=True)
    parser.add_argument("--base-path", default="/scc-demo")
    parser.add_argument("--port", type=int, default=8854)
    parser.add_argument("--backend-origin", default="http://127.0.0.1:8850")
    args = parser.parse_args()
    config = GatewayConfig(public_origin=args.public_origin, password=load_password(args.password_file),
                           base_path=args.base_path, backend_origin=args.backend_origin)
    # No public bind option and no access logs containing user requests.
    web.run_app(create_app(config), host="127.0.0.1", port=args.port, access_log=None)


if __name__ == "__main__":
    main()
