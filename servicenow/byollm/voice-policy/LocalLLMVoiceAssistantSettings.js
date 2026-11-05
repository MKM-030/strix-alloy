/* Read-only projection of the selected native Voice assistant. Install in sn_voice_aia.
 * Optional conversation selection reads only native registration metadata.
 * Provider code, connections, credentials, caches and protected source stay outside this projection.
 */
var LocalLLMVoiceAssistantSettings = Class.create();
LocalLLMVoiceAssistantSettings.prototype = {
    initialize: function() {},

    // Primitive JSON interface for administrative/native cross-scope callers.
    getSettingsJSON: function(serviceId) { return JSON.stringify(this.getSettings(serviceId)); },

    getConversationModel: function(serviceId) {
        try {
            if (typeof serviceId !== 'string' || !/^[0-9a-f]{32}$/.test(serviceId))
                throw new Error('Conversation model unavailable');
            return this._conversationModel();
        } catch (ignoredSelectionError) {
            return {version:1, status:'unavailable'};
        }
    },

    _conversationModel: function() {
        var capabilityId = 'aca5634f4312121038520464dbb8f236';
        var capability = this._selectionOne('sys_one_extend_capability', [['sys_id', capabilityId]], ['active']);
        var selection = this._selectionOne('sys_one_extend_definition_config',
            [['capability', capabilityId], ['active', true], ['default', true]],
            ['capability', 'definition', 'active', 'default']);
        var definition = this._selectionOne('sys_one_extend_capability_definition',
            [['sys_id', selection.definition]], ['capability', 'api', 'api_type', 'filter_properties']);
        if (!this._selectionEnabled(capability.active) || selection.capability !== capabilityId ||
                !this._selectionEnabled(selection.active) || !this._selectionEnabled(selection.default) ||
                definition.capability !== capabilityId || definition.api_type !== 'sys_hub_flow')
            throw new Error('Conversation model unavailable');
        this._selectionFilter(definition.filter_properties, true);
        var bindings = this._selectionRows('sys_generative_ai_prompt_config', [['definition', definition.sys_id]],
            ['definition', 'ai_config', 'is_default', 'filter_type', 'filter_properties'], 33);
        var defaults = [], i;
        for (i = 0; i < bindings.length; i++) {
            if (bindings[i].definition !== definition.sys_id || bindings[i].filter_type !== 'default')
                throw new Error('Conversation model unavailable');
            this._selectionFilter(bindings[i].filter_properties, false);
            if (this._selectionEnabled(bindings[i].is_default)) defaults.push(bindings[i]);
        }
        if (defaults.length !== 1) throw new Error('Conversation model unavailable');
        var binding = defaults[0];
        var prompt = this._selectionOne('sys_generative_ai_config', [['sys_id', binding.ai_config]],
            ['definition', 'definition_table', 'active', 'state', 'model']);
        if (prompt.definition !== definition.sys_id || prompt.definition_table !== 'sys_one_extend_capability_definition' ||
                !this._selectionEnabled(prompt.active) || prompt.state !== 'published' ||
                !/^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$/.test(prompt.model))
            throw new Error('Conversation model unavailable');
        var registrations = this._selectionRows('sys_generative_ai_model_config',
            [['model', prompt.model], ['active', true], ['lifecycle_state', 'active'], ['usage_mode', 'none']],
            ['model', 'provider', 'active', 'lifecycle_state', 'usage_mode'], 33);
        var matches = [];
        for (i = 0; i < registrations.length; i++) {
            var candidate = registrations[i];
            var candidateMapping = this._selectionOne('sys_generative_ai_provider_mapping',
                [['sys_id', candidate.provider]], ['active', 'provider', 'provider_api', 'provider_implementation',
                    'provider_implementation_document', 'gen_ai_provider']);
            if (candidateMapping.provider_implementation === definition.api && this._selectionEnabled(candidateMapping.active))
                matches.push({model:candidate, mapping:candidateMapping});
        }
        if (matches.length !== 1) throw new Error('Conversation model unavailable');
        var model = matches[0].model, mapping = matches[0].mapping;
        if (model.model !== prompt.model || !this._selectionEnabled(model.active) || model.lifecycle_state !== 'active' ||
                model.usage_mode !== 'none' || !this._selectionEnabled(mapping.active) ||
                mapping.provider !== 'Custom LLM' || mapping.provider_api !== 'custom_api' ||
                mapping.provider_implementation_document !== definition.api_type)
            throw new Error('Conversation model unavailable');
        var provider = this._selectionOne('sys_gen_ai_provider', [['sys_id', mapping.gen_ai_provider]], ['gen_ai_provider']);
        if (provider.gen_ai_provider !== 'Custom LLM Provider') throw new Error('Conversation model unavailable');
        // The installed callable implementation has a draft authoring status.
        // Its existence and mapping establish this join; prompt publication is checked above.
        var implementation = this._selectionOne('sys_hub_flow', [['sys_id', definition.api]], []);
        var rows = [capability, selection, definition, binding, prompt, model, mapping, provider, implementation];
        var revisions = [];
        for (i = 0; i < rows.length; i++) revisions.push([rows[i].sys_id, rows[i].sys_mod_count]);
        revisions.push(prompt.model);
        var digest = String(new GlideDigest().getSHA256Hex(JSON.stringify(revisions))).toLowerCase();
        if (!/^[0-9a-f]{64}$/.test(digest)) throw new Error('Conversation model unavailable');
        return {version:1, status:'selected', capability_id:capabilityId,
            definition_config_id:selection.sys_id, definition_id:definition.sys_id,
            prompt_binding_id:binding.sys_id, prompt_id:prompt.sys_id, model_config_id:model.sys_id,
            provider_mapping_id:mapping.sys_id, provider_id:provider.sys_id,
            implementation_id:implementation.sys_id, model_identifier:prompt.model, binding_sha256:digest};
    },

    _selectionEnabled: function(value) { return value === '1' || value === 'true'; },

    _selectionFilter: function(text, requireProvider) {
        var value = JSON.parse(text || '{}');
        if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('Conversation model unavailable');
        var keys = Object.keys(value);
        for (var i = 0; i < keys.length; i++) {
            if (keys[i] === 'provider' && value[keys[i]] === 'Custom LLMcustom_api') continue;
            if (keys[i] === 'provider_api' && value[keys[i]] === 'custom_api') continue;
            throw new Error('Conversation model unavailable');
        }
        if (requireProvider && value.provider !== 'Custom LLMcustom_api') throw new Error('Conversation model unavailable');
    },

    _selectionOne: function(table, filters, fields) {
        var rows = this._selectionRows(table, filters, fields, 2);
        if (rows.length !== 1) throw new Error('Conversation model unavailable');
        return rows[0];
    },

    _selectionRows: function(table, filters, fields, limit) {
        var record = new GlideRecord(table), rows = [], i, field, element;
        fields = ['sys_id', 'sys_mod_count'].concat(fields);
        if (record.isValid() !== true) throw new Error('Conversation model unavailable');
        for (i = 0; i < fields.length; i++)
            if (record.isValidField(fields[i]) !== true) throw new Error('Conversation model unavailable');
        for (i = 0; i < filters.length; i++) record.addQuery(filters[i][0], filters[i][1]);
        record.setLimit(limit);
        record.query();
        while (record.next()) {
            if (record.canRead() !== true) throw new Error('Conversation model unavailable');
            // Check all required rights before reading any value. Ordinary queries
            // retain conflicting rows that a secure query might silently hide.
            for (i = 0; i < fields.length; i++) {
                element = record.getElement(fields[i]);
                if (element === null || typeof element === 'undefined' || element.canRead() !== true)
                    throw new Error('Conversation model unavailable');
            }
            var row = {};
            for (i = 0; i < fields.length; i++) {
                field = fields[i];
                var raw = record.getValue(field);
                var value = raw === null || typeof raw === 'undefined' ? '' : String(raw);
                if (value.length > (field === 'filter_properties' ? 4096 : 128))
                    throw new Error('Conversation model unavailable');
                row[field] = value;
            }
            if (!/^[0-9a-f]{32}$/.test(row.sys_id) || !/^(0|[1-9][0-9]{0,9})$/.test(row.sys_mod_count))
                throw new Error('Conversation model unavailable');
            rows.push(row);
        }
        if (rows.length >= 33) throw new Error('Conversation model unavailable');
        return rows;
    },

    getSettings: function(serviceId) {
        if (typeof serviceId !== 'string' || !/^[0-9a-f]{32}$/.test(serviceId))
            throw new Error('Invalid assistant');
        var service = new sn_voice_aia.VoiceServiceConfiguration();
        var config = service._getDeploymentConfig(serviceId);
        if (!config) throw new Error('Assistant configuration unavailable');
        var attrs = config.getAttributeNameValueMap();
        var defaults = VoiceAgentConstants.CONFIG_DEFAULTS || {};
        var profile = config.getContextProfile();
        var profileId = profile ? String(profile.getSysId() || '') : '';
        if (!/^[0-9a-f]{32}$/.test(profileId)) throw new Error('Assistant profile unavailable');
        var nativeProfileId = profileId;
        profileId = this._executionProfile(serviceId, profileId);
        if (profileId !== nativeProfileId)
            new sn_voice_aia.LocalLLMVoiceRuntimePolicy().validateSettingsRoute(serviceId, profileId);
        var primaryVoice = service._getTTSConfig(attrs.tts_config_sys_id);
        var languageSource = attrs.language !== undefined && attrs.language !== null && attrs.language !== '' ? 'configured' :
            (primaryVoice.language ? 'tts' : 'native_default');
        var language = this._value(attrs.language, primaryVoice.language);
        language = this._value(language, defaults.LANGUAGE);
        if (typeof language !== 'string' || !/^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$/.test(language))
            throw new Error('Assistant language unavailable');

        var languageData = service._loadLanguageData(serviceId);
        var languages = [];
        var voices = {};
        var keyTerms = {};
        var configs = languageData.configs || [];
        for (var i = 0; i < configs.length; i++) {
            var lc = configs[i];
            languages.push({
                code: lc.code,
                display_name: lc.display_name || lc.code,
                language_selection_prompt: lc.language_selection_prompt || '',
                dtmf_language_selection_prompt: lc.dtmf_language_selection_prompt || '',
                trigger_phrases: lc.trigger_phrases || [],
                secondary_language_prompt: lc.secondary_language_prompt === undefined ? null : lc.secondary_language_prompt
            });
        }
        var nativeVoices = languageData.voices || {};
        var nativeTerms = languageData.keyterms || {};
        for (var j = 0; j < languages.length; j++) {
            var code = languages[j].code;
            if (nativeVoices[code]) voices[code] = {
                voice_id: nativeVoices[code].voice_id || '',
                voice_gender: nativeVoices[code].voice_gender || ''
            };
            if (nativeTerms[code]) keyTerms[code] = nativeTerms[code];
        }
        if (!languages.length && primaryVoice.language) {
            languages.push({code:primaryVoice.language,display_name:primaryVoice.language_display_name || primaryVoice.language,
                language_selection_prompt:'',dtmf_language_selection_prompt:'',trigger_phrases:[],secondary_language_prompt:''});
            voices[primaryVoice.language] = {voice_id:primaryVoice.voice_id || '',voice_gender:primaryVoice.voice_gender || ''};
        }
        var selection = this._boolean(this._value(attrs.enable_language_selection, defaults.ENABLE_LANGUAGE_SELECTION));
        var dtmf = this._boolean(this._value(attrs.enable_dtmf, defaults.ENABLE_DTMF));
        var nativePrompt = service._getVoiceSystemPrompt(serviceId, config);
        var behavior = {};
        var behaviorSources = {};
        // Explicit non-secret native configuration. Telephony metadata is projected,
        // not a claim that the local WebRTC transport implements those features.
        var keys = ['language','voice_profile','tts_config_sys_id','enable_language_selection','enable_dtmf','language_input_selection',
            'max_call_duration_in_minutes','user_inactivity_threshold_in_seconds','filler_message_delay_in_seconds',
            'noise_suppression_level','persist_context_data','orchestration_mode','gateway_mode','number_delivery','identifier_delivery',
            'retry_prefix','goodbye_message','voice_max_retries','start_time_in_ms','stop_time_in_ms','communication_channel',
            'caller_identification_fields','capture_pre_transfer_details','enable_phone_number_based_identification',
            'enable_multifactor_authentication','auto_authenticate','disable_auth_v2','primary_authentication_type',
            'secondary_authentication_type','step_up_authentication_type','primary_identification_type','secondary_identification_type',
            'require_auth_for_fallback_record_creation','fallback_option','create_ticket_fallback_record_producer_sys_id',
            'mobile_fallback_record_producer','push_notification_max_polling_retries','voice_minutes_account_is_locked','sip_context_header'];
        // Names below are proven by the installed native _buildVoiceSystemConfig source.
        var fallbackNames = {max_call_duration_in_minutes:'MAX_CALL_DURATION_IN_MINUTES',
            user_inactivity_threshold_in_seconds:'USER_INACTIVITY_THRESHOLD_IN_SECONDS',
            filler_message_delay_in_seconds:'FILLER_MESSAGE_DELAY_IN_SECONDS',noise_suppression_level:'NOISE_SUPPRESSION_LEVEL',
            persist_context_data:'PERSIST_CONTEXT_DATA',orchestration_mode:'ORCHESTRATION_MODE',gateway_mode:'GATEWAY_MODE',
            number_delivery:'NUMBER_DELIVERY',identifier_delivery:'IDENTIFIER_DELIVERY',retry_prefix:'RETRY_PREFIX',goodbye_message:'GOODBYE_MESSAGE',
            enable_language_selection:'ENABLE_LANGUAGE_SELECTION',enable_dtmf:'ENABLE_DTMF'};
        for (var k = 0; k < keys.length; k++) {
            var key = keys[k];
            var value = this._value(attrs[key], defaults[fallbackNames[key]]);
            if (value !== undefined && value !== null) {
                behavior[key] = this._scalar(value);
                behaviorSources[key] = attrs[key] !== undefined && attrs[key] !== null && attrs[key] !== '' ? 'configured' : 'native_default';
            }
        }
        if (behavior.retry_prefix !== undefined && defaults.RETRY_PREFIX !== undefined &&
                behavior.retry_prefix === String(defaults.RETRY_PREFIX)) behaviorSources.retry_prefix = 'native_default';
        var result = {
            version: 1,
            service_id: serviceId,
            context_profile: profileId,
            language: language,
            language_source: languageSource,
            language_selection: {enabled:selection,dtmf_enabled:dtmf,
                mode:this._scalar(this._value(attrs.language_input_selection, '')),languages:languages},
            tts: {voice_profile:this._scalar(this._value(attrs.voice_profile, '')),voices:voices},
            key_terms: keyTerms,
            phonemes: this._phonemes(service, serviceId, language, languages),
            notice_messages: this._notices(language, languages),
            prompt: {systemMessage:nativePrompt.systemMessage || '',introduction:nativePrompt.introduction || ''},
            vad: service._getVADConfig(attrs),
            behavior: behavior,
            behavior_sources: behaviorSources
        };
        if (this._utf8Length(JSON.stringify(result)) > 120000) throw new Error('Assistant settings exceed transport capacity');
        return result;
    },


    // Pronunciation data is metadata. The local TTS engine must advertise support
    // before interpreting native phoneme syntax; no engine configuration is changed.
    _phonemes: function(service, serviceId, primary, languages) {
        var out = {}, allowed = {}, entries = {}, i, code;
        allowed[primary] = true;
        for (i = 0; i < languages.length; i++) allowed[languages[i].code] = true;
        if (typeof service._getPhonemesGroupedByLanguage !== 'function') return out;
        entries = service._getPhonemesGroupedByLanguage(serviceId) || {};
        var codes = Object.keys(entries);
        for (i = 0; i < codes.length; i++) {
            code = codes[i];
            if (!allowed[code]) continue;
            var values = entries[code];
            if (!Array.isArray(values) || values.length > 256) throw new Error('Invalid assistant pronunciation');
            var mapped = [];
            for (var j = 0; j < values.length; j++) {
                var value = values[j];
                if (!value || typeof value.word !== 'string' || typeof value.phoneme !== 'string' ||
                        !value.word.length || value.word.length > 128 || !value.phoneme.length || value.phoneme.length > 256)
                    throw new Error('Invalid assistant pronunciation');
                mapped.push({word:value.word,phoneme:value.phoneme});
            }
            out[code] = mapped;
        }
        return out;
    },

    _notices: function(primary, languages) {
        var out = {}, codes = [primary], seen = {}, keys = ['INPUT_LOST','BUSY_AUDIO','BUSY_TEXT','ASR_EMPTY','ASR_FAILED','TURN_FAILED','LANGUAGE_RETRY'];
        if (typeof gs.getMessageLang !== 'function') return out;
        seen[primary.toLowerCase()] = true;
        for (var i = 0; i < languages.length; i++) {
            var language = languages[i].code;
            if (!seen[language.toLowerCase()]) { seen[language.toLowerCase()] = true; codes.push(language); }
        }
        if (codes.length > 16) throw new Error('Invalid assistant notices');
        for (var c = 0; c < codes.length; c++) {
            var code = codes[c], translated = {};
            for (var k = 0; k < keys.length; k++) {
                var key = 'local_llm.voice.notice.' + keys[k].toLowerCase();
                var english = String(gs.getMessageLang(key, 'en') || '');
                var message = String(gs.getMessageLang(key, code) || '');
                if (message === key || !message || (code.toLowerCase().split('-')[0] !== 'en' && message === english)) continue;
                if (message.length > 2000) throw new Error('Invalid assistant notices');
                translated[keys[k]] = message;
            }
            if (Object.keys(translated).length) out[code] = translated;
        }
        return out;
    },

    _utf8Length: function(text) {
        var bytes = 0;
        for (var i = 0; i < text.length; i++) {
            var n = text.charCodeAt(i);
            if (n < 128) bytes++;
            else if (n < 2048) bytes += 2;
            else if (n >= 55296 && n <= 56319 && i + 1 < text.length && text.charCodeAt(i + 1) >= 56320 && text.charCodeAt(i + 1) <= 57343) { bytes += 4; i++; }
            else bytes += 3;
        }
        return bytes;
    },

    // An explicit native Voice configuration field selects a dedicated nava route.
    // The Voice deployment remains the policy source; empty mapping retains its profile.
    _executionProfile: function(serviceId, nativeProfileId) {
        var source = new GlideRecordSecure('sys_now_assist_deployment_config');
        source.addQuery('now_assist_deployment', serviceId);
        source.setLimit(2);
        source.query();
        if (!source.next() || !source.canRead())
            throw new Error('Assistant execution profile unavailable');
        if (this._readField(source, 'now_assist_deployment') !== serviceId ||
                this._readField(source, 'context_profile') !== nativeProfileId)
            throw new Error('Assistant execution profile unavailable');
        var mapped = this._readField(source, 'u_local_llm_execution_profile');
        if (source.next()) throw new Error('Assistant execution profile unavailable');
        if (!mapped) return nativeProfileId;
        if (!/^[0-9a-f]{32}$/.test(mapped))
            throw new Error('Assistant execution profile unavailable');
        this._secureRecord('sys_cs_context_profile', mapped);
        var voice = this._secureRecord('sys_now_assist_deployment', serviceId);
        if (this._readField(voice, 'assistant_type') !== 'voice')
            throw new Error('Assistant execution profile unavailable');

        // A mapped profile belongs to one Voice assistant, including text test calls.
        var owners = new GlideRecordSecure('sys_now_assist_deployment_config');
        owners.addQuery('u_local_llm_execution_profile', mapped);
        owners.addQuery('now_assist_deployment.assistant_type', 'voice');
        owners.setLimit(2);
        owners.query();
        if (!owners.next() || !owners.canRead() ||
                this._readField(owners, 'now_assist_deployment') !== serviceId ||
                this._readField(owners, 'u_local_llm_execution_profile') !== mapped ||
                owners.next())
            throw new Error('Assistant execution profile unavailable');

        var targets = new GlideRecordSecure('sys_now_assist_deployment_config');
        targets.addQuery('context_profile', mapped);
        targets.addQuery('now_assist_deployment.assistant_type', 'nava');
        targets.addQuery('now_assist_deployment.active', 'true');
        targets.setLimit(2);
        targets.query();
        if (!targets.next() || !targets.canRead() ||
                this._readField(targets, 'context_profile') !== mapped)
            throw new Error('Assistant execution profile unavailable');
        var deploymentId = this._readField(targets, 'now_assist_deployment');
        if (!/^[0-9a-f]{32}$/.test(deploymentId) || targets.next())
            throw new Error('Assistant execution profile unavailable');
        var deployment = this._secureRecord('sys_now_assist_deployment', deploymentId);
        if (this._readField(deployment, 'assistant_type') !== 'nava' ||
                ['1', 'true'].indexOf(this._readField(deployment, 'active')) < 0)
            throw new Error('Assistant execution profile unavailable');
        return mapped;
    },

    _secureRecord: function(table, id) {
        var record = new GlideRecordSecure(table);
        if (!record.get(id) || !record.canRead() || this._readField(record, 'sys_id') !== id)
            throw new Error('Assistant execution profile unavailable');
        return record;
    },

    _readField: function(record, field) {
        if (!record.isValidField(field))
            throw new Error('Assistant execution profile unavailable');
        var element = record.getElement(field);
        if (element === null || typeof element === 'undefined' || !element.canRead())
            throw new Error('Assistant execution profile unavailable');
        return String(record.getValue(field) || '');
    },

    _value: function(value, fallback) {
        return value === undefined || value === null || value === '' ? fallback : value;
    },

    _scalar: function(value) {
        if (typeof value !== 'string' && typeof value !== 'boolean' && typeof value !== 'number')
            throw new Error('Invalid assistant setting');
        if (typeof value === 'number' && !isFinite(value)) throw new Error('Invalid assistant setting');
        return String(value);
    },

    _boolean: function(value) {
        if (value === true || value === 'true' || value === '1' || value === 1) return true;
        if (value === false || value === 'false' || value === '0' || value === 0) return false;
        throw new Error('Assistant language selection unavailable');
    },

    type: 'LocalLLMVoiceAssistantSettings'
};
