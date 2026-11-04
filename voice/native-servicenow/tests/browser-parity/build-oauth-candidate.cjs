'use strict';
// Inert source factory. Original record656f3a82b726321081fee3fdde11a9a9, revision7.
// Root supplies the actual own client ID only after its insert/readback; no default candidate is written.
const {createHash} = require('node:crypto');
const ORIGINAL_SHA256 = '9673f9b61867a007d14114976f7a9e11e78b8b8d1dcbd0758816a5c56357bef1';
const NATIVE_CLIENT_ID = '78e47507c6744b9ca5806e2c7d1a12bb';

function derive(originalSource, ownClientId) {
    if (typeof ownClientId !== 'string' || !/^[0-9a-f]{32}$/.test(ownClientId)
            || ownClientId === NATIVE_CLIENT_ID) throw new Error('Own OAuth client identity invalid');
    if (!Buffer.isBuffer(originalSource) && typeof originalSource !== 'string')
        throw new Error('Original OAuth source identity changed');
    const raw = Buffer.isBuffer(originalSource) ? originalSource : Buffer.from(originalSource, 'utf8');
    if (createHash('sha256').update(raw).digest('hex') !== ORIGINAL_SHA256)
        throw new Error('Original OAuth source identity changed');
    const source = raw.toString('utf8');
    const anchor = "    const APP_CLIENT_ID = '78e47507c6744b9ca5806e2c7d1a12bb';";
    if (source.split(anchor).length !== 2) throw new Error('Original OAuth source identity changed');
    return source.replace(anchor, `    const APP_CLIENT_ID = (api.state?.isVoiceMode === true
        && api.context?.props?.voiceAssistantId === '8aa131d793f787105c8132d47aba1095'
        && api.data?.assistant_config_attributes?.output?.orchestratorUrl === 'https://strix-alloy.tail7f425a.ts.net/scc-native')
        ? '${ownClientId}' : '78e47507c6744b9ca5806e2c7d1a12bb';`);
}

module.exports = {derive, ORIGINAL_SHA256};
