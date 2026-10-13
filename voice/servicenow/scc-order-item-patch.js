/* WRITE PATCH: SCC order item identity + instruction 6 only. Prepared, not applied.
 * Run the COMPLETE file as admin in Global scope; target record scopes are verified.
 * Select the intended update set and native "Record for rollback" before running.
 * No order is executed. Normal workflows remain enabled. Updates are NOT atomic;
 * a failed readback/update may leave partial changes. Inspect the printed receipt.
 */
(function () {
    var APPLY = true;
    var SCOPE = '7cc4ec81533121106b38ddeeff7b12ee';
    var TOOL = '8b5c4f0393b38354e7f2b9fa6aba10f7';
    var AGENTS = ['a4a9438393738354e7f2b9fa6aba101d', 'a6337ddf93f787105c8132d47aba1058'];
    var BINDINGS = ['835c4f0393b38354e7f2b9fa6aba10f9', '0ed4b19b933b87105c8132d47aba1030'];
    var TOOL_BEFORE = '206b8913a40211d1b8078b2b032bbd8d0d367d8174335c1647e230c44bf82150', TOOL_AFTER = '79f7a17ccc0887ade5004cf10bb12df4a78012ba583590474f84f6cb443f7ffe';
    var TEXT_BEFORE = '9b8790d369fe48cb52d00d2906d8b338e745b5ad7636b1b6b38e42d951985290', TEXT_AFTER = '1084884fc7c7a70e58d887562053828a443ee7d30974ce3d425990824f5d61c7';
    var OLD_STEP = "6. Antworte nach dem Tool-Ergebnis in höchstens zwei kurzen deutschen Sätzen, ohne die bereits bestätigten Angaben erneut aufzuzählen. Nenne ausschließlich die tatsächlich zurückgegebenen REQ- und RITM-Nummern. Bei reused=true sage, dass die passende Anforderung bereits vorhanden ist; sonst bestätige die Anlage. Behaupte keine reale Hardware-Lieferung.";
    var NEW_STEP = "6. Antworte nach dem Tool-Ergebnis in höchstens zwei kurzen deutschen Sätzen, ohne die bereits bestätigten Mitarbeiterangaben erneut aufzuzählen. Bei ok=true nenne den tatsächlich zurückgegebenen Artikelnamen aus catalog_item_name und die echten Nummern aus request_number und requested_item_number. Bei reused=true sage, dass die passende Anforderung bereits vorhanden ist; sonst bestätige die Anlage. Fehlt catalog_item_name, sage, dass der genaue Artikelname im Ergebnis fehlt; erfinde ihn nicht und bestelle deshalb nicht erneut. Nenne ein Modell nur, wenn es ausdrücklich im Tool-Ergebnis steht. Bei ok=false erkläre nur den zurückgegebenen Fehlerstatus. Behaupte keine reale Hardware-Lieferung oder Lieferzusage.";
    var receipt = {status:'preflight', execution_scope:'', planned:[], attempted:[], verified:[]};
    var stage = 'authorization';
    function need(ok, label) { if (!ok) throw new Error(label); }
    function hash(value) { return String(new GlideDigest().getSHA256Hex(String(value))).toLowerCase(); }
    function value(gr, field) {
        need(gr.isValidField(field), 'missing_field:' + field);
        var v = gr.getValue(field); return v === null ? '' : String(v);
    }
    function load(table, id) {
        var gr = new GlideRecord(table); need(gr.get(id), 'missing_record:' + id);
        need(value(gr, 'sys_scope') === SCOPE, 'record_scope:' + id); return gr;
    }
    function binding(index) {
        var gr = load('sn_aia_agent_tool_m2m', BINDINGS[index]);
        var expected = {agent:AGENTS[index], tool:TOOL, active:'1', post_processing_script:'',
            output_transformation_strategy:'none', transformation_instructions:'',
            requires_text_refined_message:'0', should_display_refined_message:'0', requires_widget_transformation:'1'};
        for (var field in expected) if (expected.hasOwnProperty(field))
            need(value(gr, field) === expected[field], 'binding_drift:' + BINDINGS[index] + ':' + field);
    }
    function prepare(table, id, field, beforeHash, afterHash, oldText, newText) {
        var gr = load(table, id), current = value(gr, field), currentHash = hash(current), desired = current;
        need(gr.canWrite() && gr.getElement(field).canWrite(), 'write_access:' + id + ':' + field);
        need(currentHash === beforeHash || currentHash === afterHash, 'source_drift:' + id);
        if (currentHash === beforeHash) {
            need(current.split(oldText).length === 2, 'replacement_count:' + id);
            desired = current.replace(oldText, newText);
        }
        need(hash(desired) === afterHash, 'desired_hash:' + id);
        var item = {table:table, id:id, field:field, before:currentHash, after:afterHash, changed:current !== desired};
        receipt.planned.push(item); return {info:item, desired:desired};
    }
    try {
        receipt.execution_scope = String(gs.getCurrentScopeName());
        need(gs.hasRole('admin'), 'admin_required');
        need(receipt.execution_scope === 'global' || receipt.execution_scope === 'rhino.global', 'global_scope_required');
        stage = 'bindings'; binding(0); binding(1);
        stage = 'prepare_all_three';
        var anchor = 'requested_item_id:r.getUniqueValue(),requested_item_number:';
        var inserted = "requested_item_id:r.getUniqueValue(),catalog_item_id:r.getValue('cat_item'),catalog_item_name:r.getDisplayValue('cat_item'),requested_item_number:";
        var plans = [prepare('sn_aia_tool', TOOL, 'script', TOOL_BEFORE, TOOL_AFTER, anchor, inserted),
            prepare('sn_aia_agent', AGENTS[0], 'instructions', TEXT_BEFORE, TEXT_AFTER, OLD_STEP, NEW_STEP),
            prepare('sn_aia_agent', AGENTS[1], 'instructions', TEXT_BEFORE, TEXT_AFTER, OLD_STEP, NEW_STEP)];
        if (!APPLY) { receipt.status = 'dry_run'; gs.info('[SCC ITEM PATCH] ' + JSON.stringify(receipt)); return; }
        for (var i = 0; i < plans.length; i++) {
            var plan = plans[i], info = plan.info;
            if (!info.changed) continue;
            stage = 'update:' + info.id;
            var target = load(info.table, info.id);
            need(hash(value(target, info.field)) === info.before, 'concurrent_drift:' + info.id);
            need(target.canWrite() && target.getElement(info.field).canWrite(), 'write_access:' + info.id);
            target.setValue(info.field, plan.desired); receipt.attempted.push(info.id);
            need(String(target.update() || '') === info.id, 'update_failed:' + info.id);
            var check = load(info.table, info.id);
            need(hash(value(check, info.field)) === info.after, 'readback_failed:' + info.id);
            receipt.verified.push(info.id);
        }
        stage = 'final_readback';
        for (var j = 0; j < plans.length; j++) {
            var finalInfo = plans[j].info, finalRecord = load(finalInfo.table, finalInfo.id);
            need(hash(value(finalRecord, finalInfo.field)) === finalInfo.after, 'final_drift:' + finalInfo.id);
        }
        receipt.status = receipt.attempted.length ? 'applied' : 'already_applied';
    } catch (error) {
        receipt.status = receipt.attempted.length ? 'partial_or_uncertain' : 'aborted';
        receipt.stage = stage; receipt.error = String(error.message || error).substring(0, 240);
    }
    gs.info('[SCC ITEM PATCH] ' + JSON.stringify(receipt));
})();
