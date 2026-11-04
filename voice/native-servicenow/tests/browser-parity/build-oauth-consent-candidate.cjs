'use strict';
// Source factory only. The vendor fixture and selector factory remain immutable.
const {derive: selectClient, ORIGINAL_SHA256}=require('./build-oauth-candidate.cjs');
const HELPERS=String.raw`
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
`;

function derive(original,ownClientId) {
    let source=selectClient(original,ownClientId);
    function replace(before,after){if(source.split(before).length!==2)throw new Error('Original OAuth source identity changed');source=source.replace(before,after);}
    replace('    const { state, codeChallenge, codeVerifier } = await fetchPKCEConfig();',
        `    const SCC_OWN_CLIENT_ID = '${ownClientId}';\n    const SCC_OWN_ENTITY_ID = '78e3391e93dc9354e7f2b9fa6aba1019';\n    const SCC_IS_OWN = APP_CLIENT_ID === SCC_OWN_CLIENT_ID;\n    let SCC_OWNER;\n    if (SCC_IS_OWN) {\n        if (api.state.callStarted === true) return;\n        const previous = window.__sccLocalVoiceAuthorizationOwner;\n        SCC_OWNER = {active: true, noticed: false, cancel: null};\n        window.__sccLocalVoiceAuthorizationOwner = SCC_OWNER;\n        if (previous) { previous.active = false; if (previous.cancel) previous.cancel(); }\n    }\n`+HELPERS+'\n    const { state, codeChallenge, codeVerifier } = await fetchPKCEConfig();');
    replace('    const redirectResponse = await window.fetch(authUrl);',
        '    const redirectResponse = SCC_IS_OWN ? await fetchOwnAuthorization(authUrl) : await window.fetch(authUrl);\n    if (SCC_IS_OWN && !redirectResponse) return;');
    replace('    if (!redirectResponse.ok) {',
        '    if (!redirectResponse.ok) {\n        if (SCC_IS_OWN) { await ownAuthorizationNotice(); return; }');
    replace('    const content = await redirectResponse.json();',
        '    const content = SCC_IS_OWN ? await readAuthorizationResponse(redirectResponse, authUrl) : await redirectResponse.json();\n    if (SCC_IS_OWN && !content) return;');
    replace('    const tokenData = await exchangeCodeForToken(code);',
        '    const tokenData = SCC_IS_OWN ? await exchangeOwnCode(code) : await exchangeCodeForToken(code);\n    if (SCC_IS_OWN && !tokenData) return;');
    replace('        if (!tokenResponse.ok) {',
        '        if (!tokenResponse.ok) {\n            if (SCC_IS_OWN) return null;');
    replace('        api.setState("auth_token", tokenData.access_token);',
        '        if (SCC_IS_OWN && !ownAuthorizationCurrent()) { releaseOwnAuthorization(); return; }\n        api.setState("auth_token", tokenData.access_token);');
    replace('            api.emit("START_NEW_CHAT");\n        }',
        '            api.emit("START_NEW_CHAT");\n        }\n        if (SCC_IS_OWN) releaseOwnAuthorization();');
    return source;
}
module.exports={derive,ORIGINAL_SHA256};
