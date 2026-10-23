/* Prospective OWNED separate resource in sn_voice_aia, NOT Global.
 * Source-backed same-scope native checks; resource accessibility/security metadata
 * must be read and reviewed before a native update set can be produced.
 * This file never replaces Authorized Agents v1 or its array response.
 */
(function process(request,response) {
    function deny(status) {response.setStatus(status);response.setBody({error:'registry_unavailable'});}
    try {
        var payload=request.body.data;
        if(!payload || Object.keys(payload).sort().join('|')!=='registryVersion|serviceId' || payload.registryVersion!==2 ||
            typeof payload.serviceId!=='string'||!/^[0-9a-f]{32}$/.test(payload.serviceId)) {deny(400);return;}
        var nativeUtils=new VoiceRestUtils();
        if(!nativeUtils.validateServiceId(request,response)||!nativeUtils.validateServiceAuthorization(request,response)) return;
        if(nativeUtils.isTestMode(request)) {deny(403);return;}
        var header=String(request.getHeader('Authorization')||'');
        if(header.length>8192||!/^Bearer [A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$/i.test(header)||!gs.getUserID()||gs.getUserName()==='guest') {deny(403);return;}
        var bound=JSON.parse(new sn_auth.VoiceServiceInfoRequestor().getVoiceServiceInfo()||'{}');
        if(bound.voice_service_id!==payload.serviceId) {deny(403);return;}
        var ids=new VoiceAgentUtils().getAuthorizedAgentIds(payload.serviceId,false);
        if(!Array.isArray(ids)||!ids.length||ids.length>16) {deny(503);return;}
        var unique={};
        for(var i=0;i<ids.length;i++) {
            if(typeof ids[i]!=='string'||!/^[0-9a-f]{32}$/.test(ids[i])||unique[ids[i]]) {deny(503);return;}
            unique[ids[i]]=true;
        }
        ids=ids.slice().sort();
        var principal=String(gs.getUserID()), now=new GlideDateTime().getNumericValue()*1;
        var revision=new GlideDigest().getSHA256Hex(JSON.stringify({version:2,principal:principal,service:payload.serviceId,agents:ids}));
        response.setStatus(200);
        response.setBody({protocol_version:2,source_revision:'native-registry-v2-candidate-1',registry_revision:String(revision),
            principal:{id:principal,kind:'platform_actor',human_caller_verified:false},service_id:payload.serviceId,
            authorized_agent_ids:ids,snapshot_expires_at:now+60000,
            capabilities:{safe_write:false,independent_context:false,tool_permissions_verified:false,cross_call_resume:false},
            evidence:{basis:'native_service_authorization_and_agent_ids',wire_qualified:false}});
    } catch(ignored) {deny(503);}
})(request,response);
