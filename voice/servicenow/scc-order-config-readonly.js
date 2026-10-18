/* READ ONLY — SCC configuration diagnosis. No order, model or tool execution.
 * Prepared and statically checked only; NOT executed or verified on the instance.
 * Run manually in ServiceNow Scripts - Background, Global, as an administrator.
 * This file NEVER applies the prepared item-response patch.
 *
 * Exactly five get(sys_id) reads; no table/dictionary search or reference traversal.
 * Known fields only: check isValidField before reading each primitive string.
 * Unproven script/postprocessor/output-selection field names remain UNKNOWN.
 * Bounded field metadata (name + internal type only) identifies them for review;
 * values of unknown fields are NEVER read or printed. No Glide objects serialized.
 *
 * Provenance:
 * - SOURCE-MANIFEST.json and scc-laptop-order-tool.js: owned order tool identity.
 * - evidence/scc-german-dialogue-fresh-readback-20261013.json: agent fields/IDs.
 * - ../native-servicenow/counterpart-evidence.json: exact Voice and Chat bindings.
 * - ../native-servicenow/VoiceAgentUtilsSNC.js: tool/M2M fields below.
 * - scc-batch-capture.js: getElements/getName/getED/getInternalType metadata API.
 *
 * Review printed metadata to establish exact script/postprocessor field names.
 * A second, explicitly reviewed allowlist is needed to read those values.
 * Do not infer missing fields, apply a patch, or paste credentials into this file.
 */
(function () {
    var MAX_FIELDS = 128;
    var MAX_FIELD_CHARS = 12000;
    var MAX_TOTAL_VALUE_CHARS = 32000;
    var valueChars = 0;
    var ORDER_TOOL = '8b5c4f0393b38354e7f2b9fa6aba10f7';
    var CHAT = 'a4a9438393738354e7f2b9fa6aba101d';
    var VOICE = 'a6337ddf93f787105c8132d47aba1058';
    var specs = [
        {table:'sn_aia_tool', id:ORDER_TOOL, purpose:'SCC order tool',
            fields:['name','description','type','input_schema'],
            unknown:['tool script field technical name','tool output schema field technical name']},
        {table:'sn_aia_agent', id:CHAT, purpose:'SCC Chat agent',
            fields:['name','role','instructions'], unknown:[]},
        {table:'sn_aia_agent', id:VOICE, purpose:'SCC Voice agent',
            fields:['name','role','instructions'], unknown:[]},
        {table:'sn_aia_agent_tool_m2m', id:'835c4f0393b38354e7f2b9fa6aba10f9', purpose:'SCC Chat order binding',
            fields:['name','agent','tool','description','inputs'], expectedAgent:CHAT,
            unknown:['binding postprocessor field technical name','binding output-field-selection technical name']},
        {table:'sn_aia_agent_tool_m2m', id:'0ed4b19b933b87105c8132d47aba1030', purpose:'SCC Voice order binding',
            fields:['name','agent','tool','description','inputs'], expectedAgent:VOICE,
            unknown:['binding postprocessor field technical name','binding output-field-selection technical name']}
    ];
    var report = {read_only:true, writes:0, record_limit:5,
        field_metadata_limit_per_record:MAX_FIELDS,
        max_field_value_chars:MAX_FIELD_CHARS, max_total_value_chars:MAX_TOTAL_VALUE_CHARS,
        ready_for_patch:false,
        reason:'Script and postprocessor technical field names require metadata review; no unknown values read.',
        records:[]};

    function sensitiveLiteral(value) {
        return /-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----/.test(value) ||
            /\bBearer\s+[A-Za-z0-9._~+\/-]{12,}/i.test(value) ||
            /["'](?:password|client_secret|api_key|access_token|refresh_token|auth_token|private_key|shared_secret)["']\s*:\s*["'][^"'\s][^"']*["']/i.test(value);
    }
    function readField(gr, field) {
        if (!gr.isValidField(field)) return {status:'missing'};
        var raw = gr.getValue(field);
        var value = raw === null ? '' : String(raw);
        if (value.length > MAX_FIELD_CHARS || valueChars + value.length > MAX_TOTAL_VALUE_CHARS)
            return {status:'omitted_limit', length:value.length};
        if (sensitiveLiteral(value)) return {status:'omitted_sensitive_literal', length:value.length};
        valueChars += value.length;
        return {status:'read', value:value, length:value.length};
    }
    function metadata(gr) {
        var result = {fields:[], limit_reached:false};
        var elements = gr.getElements();
        var count = elements.size();
        result.limit_reached = count > MAX_FIELDS;
        for (var i = 0; i < count && i < MAX_FIELDS; i++) {
            var element = elements.get(i);
            var name = String(element.getName());
            var type = String(element.getED().getInternalType());
            if (/^[A-Za-z][A-Za-z0-9_]{0,79}$/.test(name) && /^[A-Za-z][A-Za-z0-9_]{0,79}$/.test(type))
                result.fields.push({name:name, internal_type:type});
            else result.fields.push({status:'unrecognized_metadata_format'});
        }
        return result;
    }

    if (!gs.hasRole('admin')) {
        report.reason = 'Administrator role required; no records read.';
        gs.print('[SCC CONFIG READ ONLY] ' + JSON.stringify(report));
        return;
    }
    for (var n = 0; n < specs.length; n++) {
        var spec = specs[n];
        var row = {table:spec.table, sys_id:spec.id, purpose:spec.purpose,
            known_fields:{}, unknown_fields:spec.unknown};
        report.records.push(row);
        try {
            var gr = new GlideRecord(spec.table);
            if (!gr.isValid() || !gr.get(spec.id)) {
                row.status = 'missing_or_inaccessible';
                continue;
            }
            if (spec.expectedAgent) {
                if (!gr.isValidField('agent') || !gr.isValidField('tool') ||
                        String(gr.getValue('agent')) !== spec.expectedAgent || String(gr.getValue('tool')) !== ORDER_TOOL) {
                    row.status = 'binding_reference_mismatch; remaining values not read';
                    continue;
                }
            }
            var fields = ['sys_updated_on','sys_mod_count'].concat(spec.fields);
            for (var f = 0; f < fields.length; f++) row.known_fields[fields[f]] = readField(gr, fields[f]);
            row.field_metadata = metadata(gr);
            row.status = 'read';
        } catch (error) {
            // Do not print platform exception bodies or serialize Glide objects.
            row.status = 'read_failed';
        }
    }
    report.total_value_chars = valueChars;
    gs.print('[SCC CONFIG READ ONLY] ' + JSON.stringify(report));
})();
