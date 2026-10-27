/* Native Voice instructions at the owned skill boundary. Server only; client_callable=false.
 * A compact reference is inherited from the dedicated native NAVA agent_persona.
 * Read only the native public configuration APIs used by the Voice implementation.
 * No direct runtime table access, credentials, role changes, cached prompts or writes.
 */
var LocalLLMVoiceRuntimePolicy = Class.create();
LocalLLMVoiceRuntimePolicy.prototype = {
    initialize: function() {},
    OPEN: '<!-- LocalLLM native Voice Assistant reference v2 -->\n',
    CLOSE: '\n<!-- /LocalLLM native Voice Assistant reference v2 -->',
    ROUTE: 'local_llm_voice_execution_route_v2',
    BACKUP: 'local_llm_voice_original_persona_v2',
    BACKUP_META: 'local_llm_voice_original_persona_meta_v2',
    POLICY: '\n\n<!-- LocalLLM native Voice Assistant policy v1 -->\n',

    // Native cross-scope calls can wrap objects as Java Maps. Only primitive
    // JSON text crosses our scope boundary; strict validation occurs after parse.
    referenceJSON: function(text) {
        if (typeof text !== 'string' || text.length > 1000) this._fail();
        var value;
        try { value = JSON.parse(text); } catch (invalid) { this._fail(); }
        return this.reference(value);
    },
    decodeReferenceJSON: function(persona) { return JSON.stringify(this._decode(persona)); },
    resolveReferenceJSON: function(persona, requestedLanguage) {
        return JSON.stringify(this.resolveReference(persona,requestedLanguage));
    },

    reference: function(value) {
        this._validateReference(value);
        return this.OPEN + JSON.stringify({version:2,source:'native_voice_assistant',
            service_id:value.service_id,source_config:value.source_config,
            target_config:value.target_config,context_profile:value.context_profile}) + this.CLOSE;
    },

    // Called only after native Voice authorization and the Secure mapping preflight.
    // A failed administrative mapping update must not allocate an unconfigured SDK session.
    validateSettingsRoute: function(serviceId, profileId) {
        this._guid(serviceId); this._guid(profileId);
        var configs = global.NowAssistDeploymentConfig.getByDeploymentSysId(serviceId);
        if (!configs || configs.length !== 1) this._fail();
        var persona = String(configs[0].getAttributeValue(this.ROUTE) || '');
        var ref = this._decode(persona);
        if (!ref || ref.service_id !== serviceId || ref.context_profile !== profileId ||
                ref.source_config !== String(configs[0].getSysId() || '')) this._fail();
        this._route(ref, persona);
        return true;
    },

    resolveReference: function(persona, requestedLanguage) {
        var ref = this._decode(persona);
        if (!ref) return null;
        var route = this._route(ref, persona);
        var source = route.source, sourceDeployment = route.deployment;
        // This is the exact native Voice systemMessage source, read fresh per call.
        var instructions = String(sourceDeployment.getDescription() || '');
        if (instructions.length > 32768 || instructions.indexOf(this.OPEN) >= 0 ||
                instructions.indexOf(this.CLOSE) >= 0 || instructions.indexOf(this.POLICY) >= 0)
            this._fail();
        var attrs = source.getAttributeNameValueMap();
        var defaults = VoiceAgentConstants.CONFIG_DEFAULTS || {};
        var native = new sn_voice_aia.VoiceServiceConfiguration();
        var primary = this._value(attrs.language, '');
        if (!primary) primary = this._value(native._getTTSConfig(attrs.tts_config_sys_id).language, defaults.LANGUAGE);
        if (!this._code(primary)) this._fail();
        var configured = native._loadLanguageData(ref.service_id).configs || [];
        if (!Array.isArray(configured) || configured.length > 16) this._fail();
        var languages = [primary], secondary = {}, seen = {};
        seen[primary.toLowerCase()] = true;
        for (var i = 0; i < configured.length; i++) {
            var lc = configured[i], code = lc && lc.code;
            if (!this._code(code)) this._fail();
            var key = code.toLowerCase();
            var prompt = lc.secondary_language_prompt;
            if (prompt === undefined || prompt === null) prompt = '';
            if (typeof prompt !== 'string' || prompt.length > 32768 || prompt.indexOf(this.OPEN) >= 0 || prompt.indexOf(this.CLOSE) >= 0 || prompt.indexOf(this.POLICY) >= 0) this._fail();
            if (secondary[key] !== undefined && secondary[key] !== prompt) this._fail();
            secondary[key] = prompt;
            if (!seen[key]) { seen[key] = true; languages.push(code); }
        }
        if (languages.length > 16) this._fail();
        var selection = this._boolean(this._value(attrs.enable_language_selection, defaults.ENABLE_LANGUAGE_SELECTION));
        var language = primary, wanted = typeof requestedLanguage === 'string' ? requestedLanguage.toLowerCase() : '';
        if (selection) for (var j = 0; j < languages.length; j++) if (languages[j].toLowerCase() === wanted) language = languages[j];
        var pacing = {};
        var number = this._value(attrs.number_delivery, defaults.NUMBER_DELIVERY);
        var identifier = this._value(attrs.identifier_delivery, defaults.IDENTIFIER_DELIVERY);
        if (number !== undefined && number !== null) pacing.number_delivery = this._scalar(number);
        if (identifier !== undefined && identifier !== null) pacing.identifier_delivery = this._scalar(identifier);
        var mapped = route.original + this.POLICY + instructions;
        mapped += '\nRespond to the user in language code ' + language + ' for every user-facing message. Preserve the required JSON schema, action names and tool inputs.';
        if (Object.keys(pacing).length) mapped += '\nNative Voice speaking preferences: ' + JSON.stringify(pacing) + '. Apply these configured delivery preferences to user-facing speech. Preserve exact identifiers and numbers in tool inputs.';
        return {version:2,source:'native_voice_assistant',service_id:ref.service_id,
            context_profile:ref.context_profile,language:language,allowed_languages:languages,
            persona:mapped};
    },

    _decode: function(persona) {
        if (typeof persona !== 'string') return null;
        var start = persona.indexOf(this.OPEN), end = persona.indexOf(this.CLOSE);
        if (start < 0 && end < 0) return null;
        if (persona.length > 1000 || start !== 0 || end < 0 ||
                start !== persona.lastIndexOf(this.OPEN) || end !== persona.lastIndexOf(this.CLOSE) ||
                end + this.CLOSE.length !== persona.length) this._fail();
        var ref;
        try { ref = JSON.parse(persona.substring(this.OPEN.length, end)); } catch (invalid) { this._fail(); }
        if (this.reference(ref) !== persona) this._fail();
        return ref;
    },

    _validateReference: function(value) {
        if (!value || typeof value !== 'object' || Array.isArray(value) ||
                Object.keys(value).sort().join(',') !== 'context_profile,service_id,source,source_config,target_config,version' ||
                value.version !== 2 || value.source !== 'native_voice_assistant') this._fail();
        this._guid(value.service_id); this._guid(value.source_config);
        this._guid(value.target_config); this._guid(value.context_profile);
        if (value.source_config === value.target_config) this._fail();
    },
    _route: function(ref, persona) {
        var source = this._config(ref.source_config, ref.service_id, null);
        var target = this._config(ref.target_config, null, ref.context_profile);
        var targetService = String(target.getDeploymentSysId() || '');
        this._guid(targetService);
        var deployment = this._deployment(ref.service_id, 'voice');
        this._deployment(targetService, 'nava');
        if (String(source.getAttributeValue(this.ROUTE) || '') !== persona ||
                String(target.getAttributeValue('agent_persona') || '') !== persona) this._fail();
        return {source:source,deployment:deployment,original:this._original(target,ref)};
    },
    _original: function(target, ref) {
        var original = String(target.getAttributeValue(this.BACKUP) || '');
        var metadata = String(target.getAttributeValue(this.BACKUP_META) || '');
        if (original.length > 1000 || metadata.length > 1000 || original.indexOf(this.OPEN) >= 0 ||
                original.indexOf(this.CLOSE) >= 0 || original.indexOf(this.POLICY) >= 0) this._fail();
        var value;
        try { value = JSON.parse(metadata); } catch (invalid) { this._fail(); }
        if (!value || typeof value !== 'object' || Array.isArray(value) ||
                Object.keys(value).sort().join(',') !== 'context_profile,service_id,sha256,source_config,target_config,version' ||
                value.version !== 2 || value.service_id !== ref.service_id || value.source_config !== ref.source_config ||
                value.target_config !== ref.target_config || value.context_profile !== ref.context_profile ||
                typeof value.sha256 !== 'string' || !/^[0-9a-f]{64}$/.test(value.sha256) ||
                String(new GlideDigest().getSHA256Hex(original)).toLowerCase() !== value.sha256) this._fail();
        return original;
    },
    _config: function(id, deploymentId, profileId) {
        var wrapper = global.NowAssistDeploymentConfig.getBySysId(id);
        if (!wrapper || String(wrapper.getSysId() || '') !== id) this._fail();
        var deployment = String(wrapper.getDeploymentSysId() || '');
        this._guid(deployment);
        if (deploymentId && deployment !== deploymentId) this._fail();
        var configs = global.NowAssistDeploymentConfig.getByDeploymentSysId(deployment);
        if (!configs || configs.length !== 1 || String(configs[0].getSysId() || '') !== id) this._fail();
        if (profileId) {
            var profile = wrapper.getContextProfile();
            if (!profile || String(profile.getSysId() || '') !== profileId) this._fail();
        }
        return wrapper;
    },
    _deployment: function(id, type) {
        var wrapper = global.NowAssistDeployment.getBySysId(id);
        if (!wrapper || String(wrapper.getSysId() || '') !== id ||
                String(wrapper.getAssistantType() || '') !== type || !this._active(wrapper.getActive())) this._fail();
        return wrapper;
    },
    _boolean: function(value) { if (this._active(value)) return true; if (value === false || value === 0 || value === 'false' || value === '0') return false; this._fail(); },
    _active: function(value) { return value === true || value === 1 || value === 'true' || value === '1'; },
    _value: function(value, fallback) { return value === undefined || value === null || value === '' ? fallback : value; },
    _scalar: function(value) { if ((typeof value !== 'string' && typeof value !== 'boolean' && typeof value !== 'number') || typeof value === 'number' && !isFinite(value)) this._fail(); value = String(value); if (value.length > 1000) this._fail(); return value; },
    _guid: function(value) { if (typeof value !== 'string' || !/^[0-9a-f]{32}$/.test(value)) this._fail(); },
    _code: function(value) { return typeof value === 'string' && /^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$/.test(value); },
    _fail: function() { throw new Error('VOICE_ASSISTANT_POLICY_UNAVAILABLE'); },
    type: 'LocalLLMVoiceRuntimePolicy'
};
