/* Exact own SCC tool mappings only. Normal GlideRecordSecure ACLs/workflow.
 * Does not invoke the order tool, a model, or change current app/update set.
 * Review the false APPLY preflight and source before authorizing the two updates.
 */
(function () {
    var APPLY = false;
    var SCOPE = '7cc4ec81533121106b38ddeeff7b12ee';
    var TOOL = '8b5c4f0393b38354e7f2b9fa6aba10f7';
    var TOOL_HASH = '79f7a17ccc0887ade5004cf10bb12df4a78012ba583590474f84f6cb443f7ffe';
    var SCRIPT = "/* Native AIAgentConstants.POST_SCRIPT_TEMPLATE contract:\n * output = raw tool output; context = additional context.\n * Return { processed_output: primitive or JSON }.\n * No database reads, writes, model calls, or order execution.\n */\n(function (output, context) {\n    var uncertain = 'Das Bestellergebnis ist unklar; bitte pr\\u00fcfen Sie die Anforderungen und bestellen Sie nicht erneut.';\n    function result(text) { return { processed_output: text }; }\n    function parse(value) {\n        return typeof value === 'string' ? JSON.parse(value) : value;\n    }\n    function text(value, max) {\n        if (typeof value !== 'string') return '';\n        var clean = value.replace(/^\\s+|\\s+$/g, '');\n        return clean && clean.length <= max && !/[<>\\r\\n]/.test(clean) ? clean : '';\n    }\n    try {\n        var data = parse(output);\n        if (data && typeof data === 'object' && Object.prototype.hasOwnProperty.call(data, 'tool_response'))\n            data = parse(data.tool_response);\n        if (!data || typeof data !== 'object' || data.ok !== true ||\n                data.demo_only !== true || typeof data.reused !== 'boolean' ||\n                data.catalog_item_id !== '401b878b93738354e7f2b9fa6aba102f')\n            return result(uncertain);\n        var employee = text(data.employee_name, 100);\n        var catalog = text(data.catalog_item_name, 200);\n        if (!employee || !catalog || !/^REQ[0-9]{7}$/.test(data.request_number) ||\n                !/^RITM[0-9]{7}$/.test(data.requested_item_number) ||\n                !/^[0-9a-f]{32}$/.test(data.request_id) ||\n                !/^[0-9a-f]{32}$/.test(data.requested_item_id))\n            return result(uncertain);\n        var state = data.reused ? 'ist bereits vorhanden' : 'wurde angelegt';\n        return result('Die Demo-Anforderung f\\u00fcr ' + employee + ' mit Artikel ' + catalog + ' ' + state +\n            ': ' + data.request_number + ', Position ' + data.requested_item_number + '.');\n    } catch (error) {\n        return result(uncertain);\n    }\n})(output, context);\n";
    var SCRIPT_HASH = '3fd0f87f40274a70a34a3ad894fadcb21a590518b7a616ddae07d612952048d6';
    var specs = [
        { id:'835c4f0393b38354e7f2b9fa6aba10f9', agent:'a4a9438393738354e7f2b9fa6aba101d', updated:'2026-10-13 05:24:31' },
        { id:'0ed4b19b933b87105c8132d47aba1030', agent:'a6337ddf93f787105c8132d47aba1058', updated:'2026-10-13 10:05:57' }
    ];
    var r = { apply:APPLY, normalWorkflow:true, scope:String(gs.getCurrentScopeName()), planned:[], attempted:[], verified:[], captures:[] };
    function need(ok, label) { if (!ok) throw new Error(label); }
    function hash(value) { return String(new GlideDigest().getSHA256Hex(value)).toLowerCase(); }
    function get(table, id) {
        var g = new GlideRecordSecure(table);
        need(g.get(id) && g.canRead(), 'record_unreadable:' + id);
        return g;
    }
    function value(g, field) {
        need(g.isValidField(field), 'invalid_field:' + field);
        var e = g.getElement(field);
        need(e !== null && typeof e !== 'undefined' && e.canRead(), 'field_unreadable:' + field);
        return String(g.getValue(field) || '');
    }
    function guardTool() {
        var t = get('sn_aia_tool', TOOL);
        need(value(t, 'sys_scope') === SCOPE, 'tool_scope_drift');
        need(hash(value(t, 'script')) === TOOL_HASH, 'tool_source_drift');
    }
    function guard(spec) {
        guardTool();
        var g = get('sn_aia_agent_tool_m2m', spec.id);
        var expected = { agent:spec.agent, tool:TOOL, active:'1', sys_scope:SCOPE,
            sys_mod_count:'1', sys_updated_on:spec.updated, display_output:'0',
            requires_widget_transformation:'1', requires_text_refined_message:'0',
            should_display_refined_message:'0', output_transformation_strategy:'none', post_processing_script:'' };
        for (var field in expected) if (Object.prototype.hasOwnProperty.call(expected, field))
            need(value(g, field) === expected[field], 'before_drift:' + spec.id + ':' + field);
        need(g.canWrite(), 'record_write_denied:' + spec.id);
        var edits = ['display_output', 'requires_widget_transformation', 'post_processing_script'];
        for (var i = 0; i < edits.length; i++)
            need(g.getElement(edits[i]).canWrite(), 'field_write_denied:' + edits[i]);
        return g;
    }
    function readAfter(spec) {
        var a = get('sn_aia_agent_tool_m2m', spec.id);
        var fields = ['agent','tool','active','sys_scope','sys_mod_count','sys_updated_on','display_output',
            'requires_widget_transformation','requires_text_refined_message','should_display_refined_message','output_transformation_strategy'];
        var row = { id:spec.id, postScriptHash:hash(value(a, 'post_processing_script')) };
        for (var i = 0; i < fields.length; i++) row[fields[i]] = value(a, fields[i]);
        need(row.agent === spec.agent && row.tool === TOOL && row.active === '1' && row.sys_scope === SCOPE, 'reference_readback_drift');
        need(row.display_output === '1' && row.requires_widget_transformation === '0' && row.postScriptHash === SCRIPT_HASH, 'edited_readback_mismatch');
        need(row.requires_text_refined_message === '0' && row.should_display_refined_message === '0' && row.output_transformation_strategy === 'none', 'preserved_readback_mismatch');
        return row;
    }
    try {
        need(r.scope === 'global' || r.scope === 'rhino.global', 'execution_scope');
        need(hash(SCRIPT) === SCRIPT_HASH, 'prepared_formatter_hash');
        for (var p = 0; p < specs.length; p++) {
            guard(specs[p]);
            r.planned.push({ id:specs[p].id, agent:specs[p].agent, beforeMod:'1', beforeUpdated:specs[p].updated,
                beforePostScriptHash:hash(''), afterPostScriptHash:SCRIPT_HASH, display_output:'0->1', requires_widget_transformation:'1->0' });
        }
        if (APPLY) {
            for (var w = 0; w < specs.length; w++) {
                var spec = specs[w], g = guard(spec);
                g.setValue('display_output', '1');
                g.setValue('requires_widget_transformation', '0');
                g.setValue('post_processing_script', SCRIPT);
                r.attempted.push(spec.id);
                need(String(g.update() || '') === spec.id, 'save_failed:' + spec.id);
                r.verified.push(readAfter(spec));
            }
            guardTool();
            for (var f = 0; f < specs.length; f++) readAfter(specs[f]);
            for (var c = 0; c < specs.length; c++) {
                var u = new GlideRecordSecure('sys_update_xml');
                u.addQuery('name', 'sn_aia_agent_tool_m2m_' + specs[c].id);
                u.orderByDesc('sys_updated_on'); u.setLimit(1); u.query();
                if (u.next() && u.canRead()) {
                    var payload = value(u, 'payload');
                    r.captures.push({ id:String(u.getUniqueValue()), target:specs[c].id, updateSet:value(u, 'update_set'),
                        containsOwnId:payload.indexOf(specs[c].id) >= 0, containsFormatter:payload.indexOf('processed_output') >= 0 });
                }
            }
        }
        r.status = APPLY ? 'applied_verified' : 'preflight_passed_no_writes';
    } catch (error) {
        r.status = r.attempted.length ? 'partial_or_uncertain' : 'aborted_no_writes';
        r.error = String(error.message || error);
    }
    gs.print('[SCC_SPOKEN_RESULT_BINDING] ' + JSON.stringify(r));
})();
