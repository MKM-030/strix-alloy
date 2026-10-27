/* Native Voice policy mapping at the skill request boundary. No provider edits.
 * Native request metadata is accepted only for the three owned bindings below.
 * Installer verifies their scope, capability and validator binding before update.
 * No compressed conversation context, transcript or latest-record lookup.
 */
(function(payload) {
    var meta=payload&&payload._meta;
    var boundDefinitions={
        "8780c7e193f747d0e7f2b9fa6aba10ba":"2073a1aeff5fe2101657ffffffffff97",
        "8f80c7e193f747d0e7f2b9fa6aba109a":"1857ce78ff322210022dffffffffffa1",
        "4f80c7e193f747d0e7f2b9fa6aba1027":"f6f9e6e71bc38210f4200d81ec4bcb30"
    };
    function guid(v){return typeof v==='string'&&/^[0-9a-f]{32}$/.test(v);}
    function fail(){throw new Error('VOICE_ASSISTANT_POLICY_UNAVAILABLE');}
    function field(g,f){
        if(!g.isValidField(f))fail();
        var e=g.getElement(f);
        if(e===null||typeof e==='undefined'||!e.canRead())fail();
        return String(g.getValue(f)||'');
    }
    function record(t,id){var g=new GlideRecordSecure(t);if(!g.get(id)||!g.canRead())fail();return g;}
    function code(v){return typeof v==='string'&&/^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$/.test(v);}
    if(!meta||!guid(meta.conversationId)||!guid(meta.definition)||!guid(meta.capability))return payload;
    if(boundDefinitions[meta.definition]!==meta.capability)return payload;
    // The native NAVA parent already supplies this server-owned persona reference.
    // Resolving it through the native configuration API survives restricted AIA runtime ACLs.
    if(typeof payload.persona==='string'&&payload.persona.indexOf('<!-- LocalLLM native Voice Assistant reference v2 -->')>=0){
        try{
            var resolved=JSON.parse(String(new sn_voice_aia.LocalLLMVoiceRuntimePolicy().resolveReferenceJSON(payload.persona,meta.dtTargetLanguage)));
            if(!resolved||resolved.version!==2||typeof resolved.persona!=='string'||!code(resolved.language))fail();
            payload.persona=resolved.persona;
            meta.dtTargetLanguage=resolved.language;
            return payload;
        }catch(referencePolicyError){
            gs.error('VOICE_ASSISTANT_POLICY_UNAVAILABLE');
            fail();
        }
    }
    var profile;
    try{
        profile=field(record('sys_cs_conversation',meta.conversationId),'context_profile');
        if(!guid(profile))return payload;
    }catch(nonVoiceContext){return payload;}
    var configs=new GlideRecordSecure('sys_now_assist_deployment_config');
    var profileMatch=configs.addQuery('context_profile',profile);
    if(configs.isValidField('u_local_llm_execution_profile'))
        profileMatch.addOrCondition('u_local_llm_execution_profile',profile);
    configs.addQuery('now_assist_deployment.assistant_type','voice');
    configs.setLimit(2);configs.query();
    if(!configs.next())return payload;
    try{
        if(!configs.canRead())fail();
        var serviceId=field(configs,'now_assist_deployment');
        if(!guid(serviceId)||configs.next())fail();
        var deployment=record('sys_now_assist_deployment',serviceId);
        if(field(deployment,'assistant_type')!=='voice'||['1','true'].indexOf(field(deployment,'active'))<0)fail();
        var settings=new sn_voice_aia.LocalLLMVoiceAssistantSettings().getSettings(serviceId);
        if(!settings||settings.version!==1||settings.service_id!==serviceId||settings.context_profile!==profile||!code(settings.language))fail();
        var language=settings.language;
        var requested=typeof meta.dtTargetLanguage==='string'?meta.dtTargetLanguage.toLowerCase():'';
        var languages=[{code:settings.language}].concat(settings.language_selection&&settings.language_selection.languages||[]);
        for(var i=0;i<languages.length;i++)if(code(languages[i].code)&&languages[i].code.toLowerCase()===requested)language=languages[i].code;
        var instructions=settings.prompt&&settings.prompt.systemMessage;
        if(typeof instructions!=='string'||(payload.persona!==undefined&&payload.persona!==null&&typeof payload.persona!=='string'))fail();
        var marker='\n\n<!-- LocalLLM native Voice Assistant policy v1 -->\n';
        var persona=payload.persona||'';
        var previous=persona.indexOf(marker);
        if(previous>=0)persona=persona.substring(0,previous);
        var mapped=persona+marker+instructions+'\nRespond to the user in language code '+language+' for every user-facing message. Preserve the required JSON schema, action names and tool inputs.';
        payload.persona=mapped;
        meta.dtTargetLanguage=language;
        return payload;
    }catch(voicePolicyError){
        gs.error('VOICE_ASSISTANT_POLICY_UNAVAILABLE');
        fail();
    }
})(payload);
