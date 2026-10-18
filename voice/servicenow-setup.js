/* ServiceNow Scripts - Background, Global.
 * Run only after creating the two credentials through the standard UI.
 * Reuses existing standard tables. No protected/OOB scripts are changed.
 * New connection/outbound/channel records are inactive; existing active states are preserved.
 */
(function () {
    var NAME = 'SCC Local Voice';
    var PROVIDER = 'd6eadc7a53301010ad77ddeeff7b124a';
    var ASSISTANT = 'c623a20f93374354e7f2b9fa6aba10fd';
    var CALLBACK = 'https://strix-alloy.tail7f425a.ts.net/scc-voice/callback';
    var changed = [];

    function newest(table, field, value) {
        var record = new GlideRecord(table);
        record.addQuery(field, value);
        record.orderByDesc('sys_created_on');
        record.setLimit(1);
        record.query();
        return record.next() ? record : null;
    }
    function save(table, field, value, values) {
        var record = newest(table, field, value);
        var creating = !record;
        if (creating) { record = new GlideRecord(table); record.initialize(); }
        var dirty = creating;
        record.setValue(field, value);
        for (var key in values) {
            if (!record.isValidField(key)) throw new Error('Unknown field: ' + table + '.' + key);
            if (key === 'active' && !creating) continue;
            if (String(record.getValue(key) || '') !== String(values[key])) {
                record.setValue(key, values[key]);
                dirty = true;
            }
        }
        if (dirty) {
            record.setWorkflow(false);
            var id = creating ? record.insert() : record.update();
            if (!id) throw new Error('Could not save ' + table + ': ' + record.getLastErrorMessage());
            changed.push({table: table, id: String(id)});
        }
        return record.getUniqueValue();
    }
    try {
        var token = newest('token_verification', 'name', NAME + ' Inbound Token');
        var credential = newest('basic_auth_credentials', 'name', NAME + ' Callback');
        if (!token || !credential) throw new Error('Create SCC Local Voice Inbound Token and SCC Local Voice Callback credentials first.');
        var assistant = new GlideRecord('sys_now_assist_deployment');
        if (!assistant.get(ASSISTANT) || assistant.getValue('assistant_type') !== 'nava') throw new Error('Expected NAVA assistant is missing.');
        var provider = new GlideRecord('sys_cs_provider');
        if (!provider.get(PROVIDER) || provider.getValue('automatic_link_enabled') !== '1' || provider.getValue('link_account_enabled') !== '1') throw new Error('Standard bot account linking is not enabled.');

        var auth = save('message_auth', 'name', NAME + ' Message Auth', {
            provider_name: 'VA Bot to Bot Provider',
            inbound_message_verification: token.getUniqueValue(),
            outbound_message_creation: token.getUniqueValue()
        });
        var identity = save('sys_cs_provider_application', 'inbound_id', 'scc-local-voice', {
            name: NAME, provider: PROVIDER, message_auth: auth,
            short_description: 'SCC demo: local speech adapter with existing ServiceNow skills'
        });
        var alias = save('sys_alias', 'id', 'global.SCC_Local_Voice_Callback', {
            name: 'SCC_Local_Voice_Callback', type: 'connection', connection_type: 'http_connection',
            multiple_connections: '0', description: 'Authenticated callback for SCC Local Voice'
        });
        var connection = save('http_connection', 'name', NAME + ' Callback', {
            connection_alias: alias, credential: credential.getUniqueValue(),
            connection_url: CALLBACK, active: '0', use_mid: '0', connection_timeout: '5000'
        });
        var outbound = save('sn_va_as_service_outbound_configuration', 'provider_channel_identity', identity, {
            outbound_handler_type: 'rest_connection', rest_connection: alias, active: '0'
        });
        var channel = save('sys_now_assist_deployment_channel', 'document_id', identity, {
            document_table: 'sys_cs_provider_application', now_assist_deployment: ASSISTANT,
            config_type: 'Simple', active: '0'
        });
        gs.print('[SCC Setup] ' + JSON.stringify({ok:true, newRecordsInactive:true, existingActivePreserved:true, identity:identity, auth:auth, alias:alias, connection:connection, outbound:outbound, channel:channel, changed:changed}));
    } catch (error) {
        gs.print('[SCC Setup] ' + JSON.stringify({ok:false, error:String(error), changed:changed}));
    }
})();
