/* Own Global SOURCE CANDIDATE: authenticated POST
 * /api/global/scc_voice_context/presentation-grants
 * Install separately with requires_authentication=1; no new role or ACL grant.
 * Provider token AND actual caller required. No CREATE or business operation.
 */
(function process(request, response) {
    var APP = '200af60f93fb4354e7f2b9fa6aba107d';
    function unavailable(status) {
        response.setStatus(status);
        response.setBody({status:'failure',state:'presentation_history_unavailable',attested:false,
            scope:'presentation_metadata_only',businessAuthority:false});
    }
    function nativeInteger(value) {
        return typeof value === 'number' && isFinite(value) && value % 1 === 0 && value >= 1 && value <= 9007199254740991;
    }
    try {
        var token = request.getHeader('token');
        if (typeof token !== 'string' || token.length < 1 || token.length > 8192 ||
            !new sn_cs.CustomAdapterAuthUtil().validateToken(APP, JSON.stringify({token:token}))) {
            unavailable(401); return;
        }
        var actor = String(gs.getUserID() || ''), name = String(gs.getUserName() || '');
        if (!/^[0-9a-f]{32}$/.test(actor) || name.length < 1 || name === 'guest') {
            unavailable(401); return;
        }
        var data = request.body.nextEntry();
        var receipt = JSON.parse(String(new global.SCCVoicePresentationHistoryV1().issueGrantJSON(JSON.stringify(data))));
        var keys = ['status','state','requestId','conversationId','nonceSha256','issuedAtMs','expiresAtMs','attested','scope','businessAuthority'];
        if (!receipt || typeof receipt !== 'object' || Array.isArray(receipt) || Object.keys(receipt).sort().join(',') !== keys.sort().join(',') ||
            receipt.requestId !== data.requestId || !data.conversationBinding || receipt.conversationId !== data.conversationBinding.conversationId ||
            receipt.nonceSha256 !== data.nonceSha256 || !nativeInteger(receipt.issuedAtMs) || !nativeInteger(receipt.expiresAtMs) ||
            receipt.expiresAtMs - receipt.issuedAtMs !== data.maxAgeSeconds * 1000 || receipt.status !== 'success' || receipt.state !== 'presentation_history_grant_attested' ||
            receipt.attested !== true || receipt.scope !== 'presentation_metadata_only' || receipt.businessAuthority !== false) {
            unavailable(503); return;
        }
        response.setStatus(200);
        // The native REST platform supplies the outer {result: receipt} wrapper.
        response.setBody(receipt);
    } catch (ignoredGrantFailure) {
        unavailable(503);
    }
})(request, response);
