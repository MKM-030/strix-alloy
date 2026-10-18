(function process(request, response) {
    'use strict';

    // ── Configuration ────────────────────────────────────────────────────────
    // Trusted parent domains for the orchestrator. The caller supplies the host,
    // but it must sit under one of these — this is the only thing standing
    // between this endpoint and forwarding the caller's session cookie to an
    // arbitrary destination.
    var TRUSTED_DOMAINS = ['sncapps.service-now.com', 'sncapps.servicenowlab.com'];

    // OAuth entity client_id registered on THIS instance for the gateway
    // (System OAuth > Application Registry > gateway registration > Client ID).
    var OAUTH_CLIENT_ID = '6b61ea618ba9469a9111665f42606073';

    var MAX_BODY_BYTES  = 2048;   // request body hard cap
    var MAX_FIELD_LEN   = 256;    // per-field length cap
    var HTTP_TIMEOUT_MS = 10000;  // outbound call timeout

    // Anchored shapes — no wildcards that could match a scheme, credentials,
    // port, path, or query.
    var RE_SYS_ID   = /^[0-9a-f]{32}$/;
    var RE_INSTANCE = /^[a-z0-9][a-z0-9-]{0,62}$/i;
    var RE_HOSTNAME = /^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)+$/i;

    function fail(code, message) {
        // Uniform responses only: 400 for any client-input problem, 502 for any
        // upstream/config problem. Distinguishable codes or messages would let an
        // unauthenticated caller probe which hosts are trusted or whether a given
        // session cookie is valid. Specific reasons go to the system log instead.
        response.setStatus(code);
        response.setBody({ error: message });
        return null;
    }

    // ── 1. Parse and bound the request body ──────────────────────────────────
    // request.body.dataString is a ONE-SHOT read — the underlying stream is
    // consumed on first access. Read it exactly once into a local; testing it
    // in a guard first (e.g. `request.body.dataString ? ... : ''`) drains the
    // stream and leaves the second read empty. Coerce to a JS string, since it
    // arrives as a Java string and .length would otherwise be undefined.
    var raw = '';
    try {
        var ds = request.body ? request.body.dataString : null;
        if (ds !== null && ds !== undefined) {
            raw = String(ds);
        }
    } catch (e) {
        return fail(400, 'Bad Request');
    }
    if (raw.length > MAX_BODY_BYTES) {
        return fail(400, 'Bad Request');
    }

    var payload;
    try {
        payload = raw ? JSON.parse(raw) : {};
    } catch (e) {
        return fail(400, 'Bad Request');
    }
    if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
        return fail(400, 'Bad Request');
    }

    // Coerce to a bounded JS string. Returns null — never a magic string — for
    // values that are the wrong type or over-long, so a rejected value can't be
    // confused with a legitimate one.
    function scalar(value) {
        if (value === null || value === undefined) return '';
        if (typeof value === 'object' || typeof value === 'function') return null;
        var s = String(value).trim();
        return s.length > MAX_FIELD_LEN ? null : s;
    }

    var instanceName    = scalar(payload.instance_name);
    var voiceServiceId  = scalar(payload.voice_service_id);
    var orchestratorRaw = scalar(payload.orchestrator_host);

    if (instanceName === null || voiceServiceId === null || orchestratorRaw === null) {
        return fail(400, 'Bad Request');
    }

    // ── 2. Validate each field against a strict shape ────────────────────────
    if (!RE_INSTANCE.test(instanceName)) {
        return fail(400, 'Bad Request');
    }
    if (!RE_SYS_ID.test(voiceServiceId)) {
        return fail(400, 'Bad Request');
    }

    // ── 3. Normalize and validate the orchestrator host ──────────────────────
    // Reduce a bare hostname or an https:// URL to a bare lowercase host, and
    // reject everything else: http://, embedded credentials, ports, paths,
    // queries, fragments, backslashes.
    function normalizeHost(value) {
        if (!value) return '';
        var v = value.trim();

        if (v.indexOf('://') !== -1) {
            if (v.toLowerCase().indexOf('https://') !== 0) return '';
            v = v.substring('https://'.length);
        }
        // A value carrying a path/query/credential is malformed input, not a
        // host — rejected outright rather than stripped down.
        if (/[\/?#@\\]/.test(v)) return '';
        if (v.indexOf(':') !== -1) return '';  // explicit ports not permitted

        v = v.toLowerCase();
        if (v.charAt(v.length - 1) === '.') v = v.substring(0, v.length - 1);
        return RE_HOSTNAME.test(v) ? v : '';
    }

    // Suffix match on a label boundary. A bare endsWith() would accept
    // "evil-sncapps.service-now.com"; requiring the leading dot (or an exact
    // match) forces the trusted domain to be a real parent, not a substring.
    function isTrustedHost(host) {
        for (var i = 0; i < TRUSTED_DOMAINS.length; i++) {
            var d = TRUSTED_DOMAINS[i];
            if (host === d) return true;
            if (host.length > d.length + 1 &&
                host.substring(host.length - d.length - 1) === '.' + d) {
                return true;
            }
        }
        return false;
    }

    var requestedHost = normalizeHost(orchestratorRaw);
    if (!requestedHost) {
        return fail(400, 'Bad Request');
    }
    if (!isTrustedHost(requestedHost)) {
        // Log for detection; do not reflect the value back to the caller.
        gs.warn('[webrtc cookie_auth] Rejected untrusted orchestrator host "' +
                requestedHost + '"');
        return fail(400, 'Bad Request');
    }

    // ── 4. Relay the session cookie to the validated host ────────────────────
    // Forward only the cookies the orchestrator needs, not the caller's whole
    // cookie jar. Never logged.
    var COOKIE_ALLOWLIST = ['JSESSIONID', 'BIGipServer', 'glide_user_route', 'glide_session_store'];
    function filterCookies(header) {
        if (!header) return '';
        var kept = [];
        String(header).split(';').forEach(function (part) {
            var t = part.trim();
            var eq = t.indexOf('=');
            if (eq <= 0) return;
            var name = t.substring(0, eq).trim();
            for (var i = 0; i < COOKIE_ALLOWLIST.length; i++) {
                if (name === COOKIE_ALLOWLIST[i] || name.indexOf(COOKIE_ALLOWLIST[i]) === 0) {
                    kept.push(t);
                    return;
                }
            }
        });
        return kept.join('; ');
    }

    var inboundCookie = filterCookies(request.getHeader('Cookie'));

    var wsTicket = null;
    var upstreamStatus = 0;

    try {
        var r1 = new sn_ws.RESTMessageV2();
        r1.setHttpMethod('POST');
        r1.setEndpoint('https://' + requestedHost + '/api/webrtc/auth/ticket');
        if (inboundCookie) {
            r1.setRequestHeader('Cookie', inboundCookie);
        }
        r1.setRequestHeader('Content-Type', 'application/json');
        r1.setHttpTimeout(HTTP_TIMEOUT_MS);
        // Do NOT set an Authorization header — the upstream endpoint rejects the
        // request if a bearer token is present.
        r1.setRequestBody(JSON.stringify({
            instance_name:    instanceName,
            oauth_client_id:  OAUTH_CLIENT_ID,
            voice_service_id: voiceServiceId
        }));

        var resp1 = r1.execute();
        upstreamStatus = parseInt(resp1.getStatusCode(), 10) || 0;

        if (upstreamStatus === 200) {
            var body1 = resp1.getBody();
            if (body1 && body1.length <= 8192) {
                try {
                    var parsed = JSON.parse(body1);
                    if (parsed && typeof parsed.ws_ticket === 'string') {
                        wsTicket = parsed.ws_ticket;
                    }
                } catch (e) { /* leave null — treated as failure below */ }
            }
        }
    } catch (e) {
        gs.error('[webrtc cookie_auth] Ticket mint failed for host ' +
                 requestedHost + ': ' + e.message);
        return fail(502, 'Bad Gateway');
    }

    if (!wsTicket) {
        // Log upstream status internally; return a generic error so upstream
        // behaviour is not probeable through this endpoint.
        gs.warn('[webrtc cookie_auth] No ws_ticket from ' + requestedHost +
                ' (upstream status ' + upstreamStatus + ')');
        return fail(502, 'Bad Gateway');
    }
    // ── 5. Respond with the ticket only ──────────────────────────────────────
    response.setStatus(200);
    response.setBody({ ws_ticket: wsTicket });
})(request, response);
