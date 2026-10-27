/* Administrative mapping projection only. Global, server only, admin required.
 * No runtime writes, scope/preference switches, provider, TTS, STT or ACL changes.
 * Derived source/target identities and original persona backups are instance-private.
 */
var LocalLLMVoicePersonaRouteSync = Class.create();
LocalLLMVoicePersonaRouteSync.prototype = {
    initialize: function() {},
    ROUTE: 'local_llm_voice_execution_route_v2',
    BACKUP: 'local_llm_voice_original_persona_v2',
    BACKUP_META: 'local_llm_voice_original_persona_meta_v2',
    TABLE: 'sys_now_assist_deployment_config_attributes',
    PRIVATE_SET_PROPERTY: 'sn_voice_aia.local_llm.private_update_set',

    assertPrivateContext: function() { this._admin(); return this._privateContext(); },

    syncService: function(serviceId, previousProfile, removing, sourceConfigId) {
        this._admin(); this._guid(serviceId);
        previousProfile = previousProfile || '';
        if (previousProfile) this._guid(previousProfile);
        var capture = this._privateContext();
        var source;
        if (removing) {
            this._guid(sourceConfigId);
            source = {id:sourceConfigId,profile:'',active:false,removed:true};
        } else {
            source = this._source(serviceId);
            if (sourceConfigId && sourceConfigId !== source.id) this._fail();
        }
        var route = source.removed ? null : this._attribute(source.id, this.ROUTE);
        var oldRef = route && route.value ? this._decode(route.value) : null;
        if (oldRef && (oldRef.service_id !== serviceId || oldRef.source_config !== source.id)) this._fail();
        var mapped = source.active ? source.profile : '';
        var oldProfile = oldRef ? oldRef.context_profile : previousProfile;
        var restore = oldProfile && oldProfile !== mapped ? this._restorePlan(serviceId,source.id,oldProfile) : null;
        var project = mapped ? this._projectPlan(serviceId,source.id,mapped) : null;
        var desired = project ? project.reference : '';
        // Every old/new target and required attribute is preflighted before revocation.
        var attrs = [];
        if (route) attrs.push(route);
        if (restore) attrs.push(restore.persona,restore.backup,restore.metadata);
        if (project) attrs.push(project.persona,project.backup,project.metadata);
        for (var i = 0; i < attrs.length; i++) {
            if (!attrs[i].exists && attrs[i].scope !== capture.scope) this._fail();
            if (attrs[i].exists && attrs[i].scope !== 'global' && !/^[0-9a-f]{32}$/.test(attrs[i].scope)) this._fail();
        }
        var changed = 0;
        if (route && route.value && route.value !== desired) changed += this._write(route,'',capture);
        if (restore) changed += this._write(restore.persona,restore.original,capture);
        if (project) {
            changed += this._write(project.backup,project.original,capture);
            changed += this._write(project.metadata,project.backupMetadata,capture);
            changed += this._write(project.persona,project.reference,capture);
        }
        // This final private source attribute is the enablement commit. A partial
        // target write never authorizes use of stale or incomplete prompt settings.
        if (route) changed += this._write(route,desired,capture);
        return {version:2,changed:changed,mapped:!!mapped};
    },

    _projectPlan: function(serviceId, sourceId, profile) {
        var target = this._target(profile);
        this._owners(serviceId,profile,true);
        var ref = {version:2,source:'native_voice_assistant',service_id:serviceId,
            source_config:sourceId,target_config:target.id,context_profile:profile};
        var reference = this._reference(ref);
        this._bounded(reference);
        var persona = this._attribute(target.id,'agent_persona');
        var backup = this._attribute(target.id,this.BACKUP);
        var metadata = this._attribute(target.id,this.BACKUP_META);
        var original = persona.value;
        var prior = this._decode(persona.value);
        if (backup.exists || metadata.exists) {
            if (!backup.exists || !metadata.exists) this._fail();
            this._backup(ref,backup.value,metadata.value);
            if (prior) { if (this._reference(prior) !== reference) this._fail(); }
            else if (persona.value !== backup.value) this._fail();
            original = backup.value;
        } else if (prior) this._fail();
        this._original(original);
        var backupMetadata = JSON.stringify({version:2,service_id:serviceId,source_config:sourceId,
            target_config:target.id,context_profile:profile,sha256:this._hash(original)});
        this._bounded(backupMetadata);
        return {persona:persona,backup:backup,metadata:metadata,original:original,
            reference:reference,backupMetadata:backupMetadata};
    },

    _restorePlan: function(serviceId, sourceId, profile) {
        var target = this._target(profile);
        this._owners(serviceId,profile,false);
        var persona = this._attribute(target.id,'agent_persona');
        var backup = this._attribute(target.id,this.BACKUP);
        var metadata = this._attribute(target.id,this.BACKUP_META);
        if (!backup.exists || !metadata.exists) this._fail();
        var ref = {version:2,source:'native_voice_assistant',service_id:serviceId,
            source_config:sourceId,target_config:target.id,context_profile:profile};
        this._backup(ref,backup.value,metadata.value);
        var prior = this._decode(persona.value);
        if (prior) { if (this._reference(prior) !== this._reference(ref)) this._fail(); }
        else if (persona.value !== backup.value) this._fail();
        return {persona:persona,backup:backup,metadata:metadata,original:backup.value};
    },

    _reference: function(value) { return String(new sn_voice_aia.LocalLLMVoiceRuntimePolicy().referenceJSON(JSON.stringify(value))); },
    _decode: function(value) {
        var open = '<!-- LocalLLM native Voice Assistant reference v2 -->';
        var close = '<!-- /LocalLLM native Voice Assistant reference v2 -->';
        if (value.indexOf(open) < 0 && value.indexOf(close) < 0) return null;
        try { return JSON.parse(String(new sn_voice_aia.LocalLLMVoiceRuntimePolicy().decodeReferenceJSON(value))); } catch (invalid) { this._fail(); }
    },
    _backup: function(ref, original, metadata) {
        this._original(original); this._bounded(metadata);
        var data;
        try { data = JSON.parse(metadata); } catch (invalid) { this._fail(); }
        if (!data || typeof data !== 'object' || Array.isArray(data) ||
                Object.keys(data).sort().join(',') !== 'context_profile,service_id,sha256,source_config,target_config,version' ||
                data.version !== 2 || data.service_id !== ref.service_id || data.source_config !== ref.source_config ||
                data.target_config !== ref.target_config || data.context_profile !== ref.context_profile ||
                data.sha256 !== this._hash(original)) this._fail();
    },
    _original: function(value) {
        this._bounded(value);
        if (value.indexOf('<!-- LocalLLM native Voice Assistant reference v2 -->') >= 0 ||
                value.indexOf('<!-- /LocalLLM native Voice Assistant reference v2 -->') >= 0 ||
                value.indexOf('<!-- LocalLLM native Voice Assistant policy v1 -->') >= 0 ||
                value.indexOf('<!-- LocalLLM inherited Voice Assistant projection v1 -->') >= 0) this._fail();
    },

    _source: function(serviceId) {
        var deployment = this._record('sys_now_assist_deployment',serviceId,false);
        if (this._field(deployment,'assistant_type') !== 'voice') this._fail();
        var configs = new GlideRecordSecure('sys_now_assist_deployment_config');
        configs.addQuery('now_assist_deployment',serviceId); configs.setLimit(2); configs.query();
        if (!configs.next() || !configs.canRead() || !configs.canWrite()) this._fail();
        var id = this._field(configs,'sys_id');
        var profile = this._field(configs,'u_local_llm_execution_profile');
        if (profile) this._guid(profile);
        if (configs.next()) this._fail();
        return {id:id,profile:profile,active:this._active(this._field(deployment,'active'))};
    },
    _target: function(profile) {
        this._record('sys_cs_context_profile',profile,false);
        var configs = new GlideRecordSecure('sys_now_assist_deployment_config');
        configs.addQuery('context_profile',profile); configs.addQuery('now_assist_deployment.assistant_type','nava');
        configs.addQuery('now_assist_deployment.active','true'); configs.setLimit(2); configs.query();
        if (!configs.next() || !configs.canRead() || !configs.canWrite()) this._fail();
        var id = this._field(configs,'sys_id'), service = this._field(configs,'now_assist_deployment');
        if (this._field(configs,'context_profile') !== profile || configs.next()) this._fail();
        var deployment = this._record('sys_now_assist_deployment',service,false);
        if (this._field(deployment,'assistant_type') !== 'nava' || !this._active(this._field(deployment,'active'))) this._fail();
        return {id:id,service:service,profile:profile};
    },
    _owners: function(serviceId, profile, required) {
        var owners = new GlideRecordSecure('sys_now_assist_deployment_config');
        owners.addQuery('u_local_llm_execution_profile',profile);
        owners.addQuery('now_assist_deployment.assistant_type','voice'); owners.setLimit(2); owners.query();
        if (!owners.next()) { if (required) this._fail(); return; }
        if (!owners.canRead() || this._field(owners,'now_assist_deployment') !== serviceId || owners.next()) this._fail();
    },

    _privateContext: function() {
        var id = String(gs.getProperty(this.PRIVATE_SET_PROPERTY,'') || ''); this._guid(id);
        var target = this._record('sys_update_set',id,true);
        var selectedId = String(gs.getPreference('sys_update_set') || ''); this._guid(selectedId);
        if (selectedId !== id) this._fail();
        var selected = this._record('sys_update_set',selectedId,true);
        var scope = this._field(target,'application');
        if (this._field(target,'parent') || this._field(target,'base_update_set') ||
                this._field(target,'state') !== 'in progress' || this._field(target,'name').indexOf('LOCAL ONLY') !== 0 ||
                this._field(selected,'state') !== 'in progress' || this._field(selected,'application') !== scope ||
                String(gs.getCurrentApplicationId() || '') !== scope) this._fail();
        return {privateSet:id,selected:selectedId,scope:scope};
    },
    _attribute: function(configId, name) {
        this._guid(configId);
        if (['agent_persona',this.ROUTE,this.BACKUP,this.BACKUP_META].indexOf(name) < 0) this._fail();
        var record = new GlideRecordSecure(this.TABLE);
        record.addQuery('deployment_config',configId); record.addQuery('name',name); record.setLimit(2); record.query();
        if (record.next()) {
            if (!record.canRead() || !record.canWrite()) this._fail();
            var element = record.getElement('value');
            if (element === null || typeof element === 'undefined' || !element.canRead() || !element.canWrite()) this._fail();
            var value = this._field(record,'value'); this._bounded(value);
            var id = this._field(record,'sys_id'), scope = this._field(record,'sys_scope'), mod = this._field(record,'sys_mod_count');
            if (record.next()) this._fail();
            // Re-get keeps the record handle positioned on the exact captured row.
            record = this._record(this.TABLE,id,true);
            return {config:configId,name:name,id:id,exists:true,value:value,scope:scope,mod:mod,record:record};
        }
        record.initialize(); record.setValue('deployment_config',configId); record.setValue('name',name); record.setValue('value','');
        if (!record.canCreate()) this._fail();
        var names = ['deployment_config','name','value'];
        for (var i = 0; i < names.length; i++) { var field = record.getElement(names[i]); if (field === null || typeof field === 'undefined' || !field.canWrite()) this._fail(); }
        return {config:configId,name:name,id:'',exists:false,value:'',scope:String(gs.getCurrentApplicationId() || '')};
    },
    _write: function(attribute, value, capture) {
        this._admin(); this._guid(attribute.config);
        if (['agent_persona',this.ROUTE,this.BACKUP,this.BACKUP_META].indexOf(attribute.name) < 0) this._fail();
        var actual = this._privateContext();
        if (actual.privateSet !== capture.privateSet || actual.selected !== capture.selected || actual.scope !== capture.scope) this._fail();
        this._bounded(value);
        if (attribute.exists && attribute.value === value) return 0;
        var wrapper = global.NowAssistDeploymentConfig.getBySysId(attribute.config);
        if (!wrapper || String(wrapper.getSysId() || '') !== attribute.config) this._fail();
        wrapper.setAttributeValue(attribute.name,value);
        var current = this._attribute(attribute.config,attribute.name);
        if (!current.exists || current.value !== value || current.scope !== attribute.scope) this._fail();
        new GlideUpdateManager2().saveRecord(current.record);
        this._routeCapture(current,capture);
        attribute.id = current.id; attribute.exists = true; attribute.value = value; attribute.scope = current.scope;
        return 1;
    },
    _routeCapture: function(attribute, capture) {
        this._admin();
        var actual = this._privateContext();
        if (actual.privateSet !== capture.privateSet || actual.selected !== capture.selected || actual.scope !== capture.scope) this._fail();
        if (capture.selected !== capture.privateSet) this._fail();
        var name = this.TABLE + '_' + attribute.id;
        var cu = new GlideRecordSecure('sys_update_xml');
        cu.addQuery('name',name); cu.addQuery('update_set',capture.selected); cu.setLimit(2); cu.query();
        if (!cu.next() || !cu.canRead()) this._fail();
        var id = this._field(cu,'sys_id');
        if (this._field(cu,'application') !== attribute.scope || this._field(cu,'action') !== 'INSERT_OR_UPDATE') this._fail();
        var xml = new XMLDocument2();
        if (xml.parseXML(this._field(cu,'payload')) === false) this._fail();
        var base = '//' + this.TABLE + '/';
        if (String(xml.getNodeText(base+'sys_id') || '') !== attribute.id ||
                String(xml.getNodeText(base+'deployment_config') || '') !== attribute.config ||
                String(xml.getNodeText(base+'name') || '') !== attribute.name ||
                String(xml.getNodeText(base+'value') || '') !== attribute.value ||
                String(xml.getNodeText(base+'sys_scope') || '') !== attribute.scope ||
                String(xml.getNodeText(base+'sys_mod_count') || '') !== attribute.mod || cu.next()) this._fail();
        cu = this._record('sys_update_xml',id,false);
        cu = this._record('sys_update_xml',id,false);
        if (this._field(cu,'update_set') !== capture.privateSet || this._field(cu,'name') !== name) this._fail();
    },
    _record: function(table, id, write) {
        this._guid(id);
        var record = new GlideRecordSecure(table);
        if (!record.get(id) || !record.canRead() || write && !record.canWrite() || this._field(record,'sys_id') !== id) this._fail();
        return record;
    },
    _field: function(record, name) {
        if (!record.isValidField(name)) this._fail();
        var element = record.getElement(name);
        if (element === null || typeof element === 'undefined' || !element.canRead()) this._fail();
        return String(record.getValue(name) || '');
    },
    _hash: function(value) { return String(new GlideDigest().getSHA256Hex(value)).toLowerCase(); },
    _bounded: function(value) { if (typeof value !== 'string' || value.length > 1000) this._fail(); },
    _guid: function(value) { if (typeof value !== 'string' || !/^[0-9a-f]{32}$/.test(value)) this._fail(); },
    _active: function(value) { return value === true || value === 1 || value === 'true' || value === '1'; },
    _admin: function() { if (!gs.hasRole('admin')) this._fail(); },
    _fail: function() { throw new Error('VOICE_ASSISTANT_PERSONA_SYNC_UNAVAILABLE'); },
    type: 'LocalLLMVoicePersonaRouteSync'
};
