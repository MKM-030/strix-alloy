/**
 * @param {params} params
 * @param {api} params.api
 * @param {any} params.event
 * @param {any} params.imports
 * @param {ApiHelpers} params.helpers
 */
async function handler({
    api,
    event,
    helpers,
    imports
}) {
    const uiUtils = imports["sn_nowassist_va.VoiceTestingUIUtils"](api, helpers);
    const window = uiUtils.getWindowObject();
    const APP_CLIENT_ID = (api.state?.isVoiceMode === true
        && api.context?.props?.voiceAssistantId === '8aa131d793f787105c8132d47aba1095'
        && api.data?.assistant_config_attributes?.output?.orchestratorUrl === 'https://strix-alloy.tail7f425a.ts.net/scc-native')
        ? '837d93812f004c9a9b1523d43969389f' : '78e47507c6744b9ca5806e2c7d1a12bb';
    const APP_REDIRECT_URI = '/api/sn_nowassist_va/voiceauth/oauth/authorize';
    const OAUTH_TOKEN_URI = `/oauth_token.do`;
    const OAUTH_AUTH_URI = `/oauth_auth.do`;
    const URI = 'uri';
    const GRANT_TYPE = 'grant_type';
    const CODE = 'code';
    const CLIENT_ID = 'client_id';
    const REDIRECT_URI = 'redirect_uri';
    const CODE_VERIFIER = 'code_verifier';
    const GRANT_TYPES = {
        AUTH_CODE: 'authorization_code',
        REFRESH_TOKEN: 'refresh_token',
    };
    const REQUESTED_CLAIMS = 'requested_claims';
    const PKCE_CODE_CHALLENGE_METHOD = 'S256';

    const base64UrlEncode = (arrayBuffer) => {
        const bytes = new window.Uint8Array(arrayBuffer);
        let binary = '';
        bytes.forEach((b) => (binary += String.fromCharCode(b)));
        return window.btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
    };
    
    const fetchPKCEConfig = async () => {
        const state = (window.crypto.randomUUID && window.crypto.randomUUID()) || generateRandomString(32);
        const codeVerifier = generateRandomString(64);
        const codeChallenge = await encodeWithVerifier(codeVerifier);
        return {
            state,
            codeChallenge,
            codeVerifier
        };
    }

    async function encodeWithVerifier(verifier) {
        const encoder = new window.TextEncoder();
        const data = encoder.encode(verifier);
        const digest = await window.crypto.subtle.digest('SHA-256', data);
        return base64UrlEncode(digest);
    }

    const generateRandomString = (length) => {
        const charset = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~';
        const randomValues = new window.Uint8Array(length);
        window.crypto.getRandomValues(randomValues);
        return Array.from(randomValues)
            .map((v) => charset[v % charset.length])
            .join('');
    };

    const SCC_OWN_CLIENT_ID = '837d93812f004c9a9b1523d43969389f';
    const SCC_OWN_ENTITY_ID = '78e3391e93dc9354e7f2b9fa6aba1019';
    const SCC_IS_OWN = APP_CLIENT_ID === SCC_OWN_CLIENT_ID;
    let SCC_OWNER;
    if (SCC_IS_OWN) {
        if (api.state.callStarted === true) return;
        const previous = window.__sccLocalVoiceAuthorizationOwner;
        SCC_OWNER = {active: true, noticed: false, cancel: null};
        window.__sccLocalVoiceAuthorizationOwner = SCC_OWNER;
        if (previous) { previous.active = false; if (previous.cancel) previous.cancel(); }
    }

    function ownAuthorizationContext() {
        return api.state && api.state.isVoiceMode === true
            && api.context && api.context.props && api.context.props.voiceAssistantId === '8aa131d793f787105c8132d47aba1095'
            && api.data && api.data.assistant_config_attributes && api.data.assistant_config_attributes.output
            && api.data.assistant_config_attributes.output.orchestratorUrl === 'https://strix-alloy.tail7f425a.ts.net/scc-native';
    }
    function ownAuthorizationOwner() {
        return SCC_OWNER && SCC_OWNER.active && window.__sccLocalVoiceAuthorizationOwner === SCC_OWNER;
    }
    function ownAuthorizationCurrent() {
        return ownAuthorizationOwner() && ownAuthorizationContext() && api.state.isConnectionInProgress !== false && api.state.callStarted !== true;
    }
    function releaseOwnAuthorization() {
        if (!SCC_OWNER) return;
        SCC_OWNER.active = false;
        if (window.__sccLocalVoiceAuthorizationOwner === SCC_OWNER) delete window.__sccLocalVoiceAuthorizationOwner;
    }
    async function ownAuthorizationNotice() {
        if (!ownAuthorizationOwner()) return;
        if (!ownAuthorizationContext()) { releaseOwnAuthorization(); return; }
        if (SCC_OWNER.noticed) return;
        SCC_OWNER.noticed = true;
        api.setState('isConnectionInProgress', false);
        let text = 'Die Anmeldung für den Sprachassistenten wurde nicht abgeschlossen. Bitte versuchen Sie es erneut.';
        try { const translated = await helpers.translate(text); if (typeof translated === 'string' && translated) text = translated; } catch (_) {}
        if (!ownAuthorizationOwner()) return;
        try {
            api.emit('NOW_UXF_PAGE#ADD_NOTIFICATIONS', {items: [{
                id: 'scc_local_voice_authentication', status: 'critical', icon: 'exclamation-triangle-outline',
                content: {type: 'html', value: text}, action: {type: 'dismiss'}
            }]});
        } finally { releaseOwnAuthorization(); }
    }
    function ownAuthorizationResult(value) {
        const result = value && value.result;
        if (!ownAuthorizationCurrent() || !result || result.state !== state || typeof result.code !== 'string'
                || !result.code.length || result.code.length > 8192 || result.error)
            throw new Error('Own authorization incomplete');
        return value;
    }
    function ownAuthorizationLocation(url, allowAuthorization) {
        const current = new window.URL(url, window.location.origin);
        if (current.origin !== window.location.origin || current.username || current.password || current.hash)
            throw new Error('Own authorization location refused');
        const names = [...current.searchParams.keys()];
        if (current.pathname === APP_REDIRECT_URI) {
            if (names.some(name => name !== 'code' && name !== 'state') || new Set(names).size !== names.length)
                throw new Error('Own callback parameters refused');
            return 'callback';
        }
        if (allowAuthorization && current.pathname === '/oauth_auth.do') return 'authorization';
        if (current.pathname === '/oauth_auth_check.do'
                && names.length === 1 && names[0] === 'sysparm_oauthapp_id'
                && current.searchParams.get('sysparm_oauthapp_id') === SCC_OWN_ENTITY_ID) return 'consent';
        throw new Error('Own authorization location refused');
    }
    async function fetchOwnAuthorization(authUrl) {
        try {
            if (!ownAuthorizationCurrent()) { releaseOwnAuthorization(); return null; }
            const response = await window.fetch(authUrl);
            if (!ownAuthorizationCurrent()) { releaseOwnAuthorization(); return null; }
            return response;
        }
        catch (_) { await ownAuthorizationNotice(); return null; }
    }
    function waitForNativeConsent(authUrl) {
        return new Promise((resolve, reject) => {
            const document = window.document, previousFocus = document && document.activeElement;
            let dialog, frame, cancel, timer, settled = false;
            const finish = (value) => {
                if (settled) return;
                settled = true;
                window.clearTimeout(timer);
                frame && frame.removeEventListener('load', loaded);
                frame && frame.removeEventListener('error', failed);
                dialog && dialog.removeEventListener('cancel', cancelled);
                dialog && dialog.removeEventListener('close', failed);
                cancel && cancel.removeEventListener('click', failed);
                if (SCC_OWNER.cancel === failed) SCC_OWNER.cancel = null;
                try { if (dialog && dialog.open) dialog.close(); } catch (_) {}
                if (dialog && dialog.parentNode) dialog.parentNode.removeChild(dialog);
                try { if (previousFocus && previousFocus.isConnected && previousFocus.focus) previousFocus.focus(); } catch (_) {}
                if (value) resolve(value); else reject(new Error('Own native consent incomplete'));
            };
            const failed = () => finish(null);
            const cancelled = (event) => { event.preventDefault(); finish(null); };
            const loaded = () => {
                try {
                    const href = frame.contentWindow.location.href;
                    if (href === 'about:blank') return;
                    if (ownAuthorizationLocation(href, true) !== 'callback') return;
                    const raw = frame.contentDocument && frame.contentDocument.body && frame.contentDocument.body.textContent;
                    if (typeof raw !== 'string' || raw.length > 16384) throw new Error('Own callback body refused');
                    finish(ownAuthorizationResult(JSON.parse(raw)));
                } catch (_) { finish(null); }
            };
            try {
                if (!document || !document.body) throw new Error('Own native consent unavailable');
                dialog = document.createElement('dialog');
                if (typeof dialog.showModal !== 'function') throw new Error('Own native consent unavailable');
                const heading = document.createElement('h2');
                heading.id = 'scc-native-voice-consent-title'; heading.textContent = 'Anmeldung bestätigen';
                dialog.setAttribute('aria-labelledby', heading.id);
                dialog.setAttribute('aria-modal', 'true');
                dialog.style.width = 'min(92vw, 720px)'; dialog.style.maxHeight = '92vh';
                frame = document.createElement('iframe');
                frame.title = 'ServiceNow: Zugriff für den Sprachassistenten bestätigen';
                frame.setAttribute('sandbox', 'allow-forms allow-scripts allow-same-origin');
                frame.style.width = '100%'; frame.style.height = '65vh'; frame.style.border = '0';
                cancel = document.createElement('button'); cancel.type = 'button'; cancel.textContent = 'Abbrechen';
                frame.addEventListener('load', loaded); frame.addEventListener('error', failed);
                dialog.addEventListener('cancel', cancelled); dialog.addEventListener('close', failed);
                cancel.addEventListener('click', failed);
                SCC_OWNER.cancel = failed;
                dialog.appendChild(heading); dialog.appendChild(frame); dialog.appendChild(cancel);
                frame.src = authUrl;
                document.body.appendChild(dialog); dialog.showModal();
                timer = window.setTimeout(failed, 120000);
            } catch (_) { finish(null); }
        });
    }
    async function readAuthorizationResponse(response, authUrl) {
        try {
            if (!response.ok) throw new Error('Own authorization unavailable');
            const type = response.headers && response.headers.get('content-type') || '';
            if (/^application\/json(?:;|$)/i.test(type)) {
                ownAuthorizationLocation(response.url || authUrl, true);
                return ownAuthorizationResult(await response.json());
            }
            if (!/^text\/html(?:;|$)/i.test(type)
                    || ownAuthorizationLocation(response.url || authUrl, true) !== 'consent')
                throw new Error('Own consent response refused');
            return await waitForNativeConsent(authUrl);
        } catch (_) { await ownAuthorizationNotice(); return null; }
    }
    async function exchangeOwnCode(code) {
        try {
            if (!ownAuthorizationCurrent()) { releaseOwnAuthorization(); return null; }
            const data = await exchangeCodeForToken(code);
            if (!ownAuthorizationCurrent()) { releaseOwnAuthorization(); return null; }
            if (!data || data.error || data.error_description || typeof data.access_token !== 'string'
                    || data.access_token.length < 16 || data.access_token.length > 8192
                    || !/^[A-Za-z0-9._~+\/-]+=*$/.test(data.access_token)) throw new Error('Own token unavailable');
            return data;
        } catch (_) { await ownAuthorizationNotice(); return null; }
    }

    const { state, codeChallenge, codeVerifier } = await fetchPKCEConfig();

    const authUrl =
        OAUTH_AUTH_URI +
        `?response_type=${CODE}&` +
        `client_id=${encodeURIComponent(APP_CLIENT_ID)}&` +
        `redirect_uri=${encodeURIComponent(APP_REDIRECT_URI)}&` +
        `code_challenge=${encodeURIComponent(codeChallenge)}&` +
        `code_challenge_method=${PKCE_CODE_CHALLENGE_METHOD}&` +
        `state=${encodeURIComponent(state)}`;
      
    const redirectResponse = SCC_IS_OWN ? await fetchOwnAuthorization(authUrl) : await window.fetch(authUrl);
    if (SCC_IS_OWN && !redirectResponse) return;
    if (!redirectResponse.ok) {
        if (SCC_IS_OWN) { await ownAuthorizationNotice(); return; }
        console.error('PKCE flow errored. Unable to fetch access token', {
            status: redirectResponse.status,
            auth_url: authUrl,
        });
        return;
    }

    const content = SCC_IS_OWN ? await readAuthorizationResponse(redirectResponse, authUrl) : await redirectResponse.json();
    if (SCC_IS_OWN && !content) return;
    const { result } = content;
    const { code, state: redirectState } = result;
    const tokenData = SCC_IS_OWN ? await exchangeOwnCode(code) : await exchangeCodeForToken(code);
    if (SCC_IS_OWN && !tokenData) return;
    
    if (code && redirectState === state && (tokenData.error_description !== "access_denied" || tokenData.error !== "server_error")) {
        if (SCC_IS_OWN && !ownAuthorizationCurrent()) { releaseOwnAuthorization(); return; }
        api.setState("auth_token", tokenData.access_token);
        if (api.state.isVoiceMode) {
            api.emit("START_VOICE_SESSION");
        } else {
            api.emit("START_NEW_CHAT");
        }
        if (SCC_IS_OWN) releaseOwnAuthorization();
    } // invalid state. Request and current client are not same.

    async function exchangeCodeForToken(code) {
        if (!code) throw new Error('Authorization code is required.');
        const claim = window.btoa(JSON.stringify({ "voice_service_id": api.context.props.voiceAssistantId }));
        const params = new window.URLSearchParams();
        params.append(GRANT_TYPE, GRANT_TYPES.AUTH_CODE);
        params.append(CODE, code);
        params.append(CLIENT_ID, APP_CLIENT_ID);
        params.append(REDIRECT_URI, APP_REDIRECT_URI);
        params.append(CODE_VERIFIER, codeVerifier || '');
        params.append(REQUESTED_CLAIMS, claim);

        const tokenResponse = await window.fetch(OAUTH_TOKEN_URI, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
            },
            body: params.toString(),
        });
        if (!tokenResponse.ok) {
            if (SCC_IS_OWN) return null;
            api.emit('NOW_UXF_PAGE#ADD_NOTIFICATIONS', {
                items: [{
                    id: 'auth_request_failure',
                    status: 'critical',
                    icon: 'exclamation-triangle-outline',
                    content: {
                        type: "html",
                        value: await helpers.translate("Authentication request failed.")
                    },
                    action: {
                        type: 'dismiss'
                    }
                }]
            });
        }
        const tokenData = await tokenResponse.json();
        return tokenData;
    }
}