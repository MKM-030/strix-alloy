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
    const APP_CLIENT_ID = '78e47507c6744b9ca5806e2c7d1a12bb';
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

    const { state, codeChallenge, codeVerifier } = await fetchPKCEConfig();

    const authUrl =
        OAUTH_AUTH_URI +
        `?response_type=${CODE}&` +
        `client_id=${encodeURIComponent(APP_CLIENT_ID)}&` +
        `redirect_uri=${encodeURIComponent(APP_REDIRECT_URI)}&` +
        `code_challenge=${encodeURIComponent(codeChallenge)}&` +
        `code_challenge_method=${PKCE_CODE_CHALLENGE_METHOD}&` +
        `state=${encodeURIComponent(state)}`;
      
    const redirectResponse = await window.fetch(authUrl);
    if (!redirectResponse.ok) {
        console.error('PKCE flow errored. Unable to fetch access token', {
            status: redirectResponse.status,
            auth_url: authUrl,
        });
        return;
    }

    const content = await redirectResponse.json();
    const { result } = content;
    const { code, state: redirectState } = result;
    const tokenData = await exchangeCodeForToken(code);
    
    if (code && redirectState === state && (tokenData.error_description !== "access_denied" || tokenData.error !== "server_error")) {
        api.setState("auth_token", tokenData.access_token);
        if (api.state.isVoiceMode) {
            api.emit("START_VOICE_SESSION");
        } else {
            api.emit("START_NEW_CHAT");
        }
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