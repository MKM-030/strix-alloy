/* ADDITIONAL approval-required admin Scripts - Background maintenance variant.
 * Secure reads/guards/capture remain mandatory. Only the frozen 68 source
 * updates use ordinary native GlideRecord, with normal Business Rules. This is
 * not a persistent endpoint or a role/ACL/security-property modification.
 * Execute once in Global only after separate approval, with SDK rollback recording.
 * No runtime/model/business/session operation is performed.
 * A failure after the first write is reported for review, never silently retried.
 */
(function () {
    var PLAN = /*__FROZEN_PLAN__*/;
    var out = {ok:false,status:'aborted',stage:'preflight',authority_mode:PLAN.authorityMode || '',ui_write_restricted_count:0,ui_write_restricted_ids:[],verified:0,captured:0,source_writes:0,set_writes:0,set_attempts:0,attempted:[],customer_update_ids:[]};
    var original = String(gs.getPreference('sys_update_set') || ''), selectionChanged = false;
    var snapshots = {}, finalSnapshots = {}, companionSnapshots = {}, names = {}, children = {}, batch = '', desiredCount = 0;
    var metadata = {sys_updated_on:1,sys_updated_by:1,sys_mod_count:1,request_tokens:1};
    try {
        need(gs.hasRole('admin'), 'admin_required');
        need(PLAN.authorityMode === 'approved_admin_maintenance','approved_admin_maintenance_mode_required');
        need(original, 'original_update_set_required');
        need(PLAN.schema === 1 && PLAN.targets.length === 68 && PLAN.targetCount === 68 && PLAN.promptCount === 66, 'invalid_frozen_plan');
        var seen = {}, promptCount = 0, i, t, gr, current, desired;
        for (i = 0; i < PLAN.targets.length; i++) {
            t = PLAN.targets[i];
            need(!seen[t.id] && /^[0-9a-f]{32}$/.test(t.id), 'duplicate_or_invalid_target'); seen[t.id] = true;
            need((t.table === 'sys_generative_ai_config' && t.field === 'model' && t.scope === PLAN.aiaScope && t.desired === 'halogen-v2') ||
                (t.table === 'sys_script_include' && t.field === 'script' && t.scope === 'global') ||
                (t.table === 'sys_generative_ai_custom_llm_transformer' && t.field === 'request_transformer' && t.scope === 'global'), 'unapproved_target_shape');
            if (t.table === 'sys_generative_ai_config') { promptCount++; need(t.before.active === 'true' && t.before.state === 'published' && t.before.model === 'Gemma 4 26B-A4B', 'unapproved_prompt_preimage'); }
            need(own(t.before,t.field) && t.desired !== t.before[t.field], 'missing_or_unchanged_target_field');
            gr = read(t.table,t.id);
            need(value(gr,'sys_policy') === '', 'source_policy_protected:' + t.id);
            if (!(gr.canWrite() && gr.getElement(t.field).canWrite())) { out.ui_write_restricted_ids.push(t.id); out.ui_write_restricted_count++; }
            need(value(gr,'sys_scope') === t.scope, 'target_scope_drift:' + t.id);
            current = snapshot(gr); snapshots[t.id] = current;
            desired = contractMatches(current,t.before,t.field,t.desired,true);
            if (desired) desiredCount++;
            else need(contractMatches(current,t.before,'','',false), 'frozen_preimage_drift:' + t.id);
            names[t.id] = (gr.isValidField('sys_update_name') ? value(gr,'sys_update_name') : '') || t.table + '_' + t.id;
        }
        need(promptCount === 66, 'prompt_count_mismatch');
        need(desiredCount === 0 || desiredCount === 68, 'mixed_partial_source_state_requires_review');
        preflightCompanions();
        checkGuards();
        var existing = inspectExistingBatch();
        if (existing) {
            need(desiredCount === 68, 'existing_batch_requires_fully_desired_sources');
            finalSnapshots = snapshots;
            auditBatch();
            out.ok = true; out.status = 'already_applied'; out.verified = 68;
        } else {
            need(desiredCount === 0,'already_desired_without_verified_batch');
            // All 68 frozen source checks, guards and existing-batch checks have
            // completed before this first database mutation.
            out.stage = 'create_delta_sets';
            batch = createSet(PLAN.name,'global','');
            children.global = createSet(PLAN.name + ' / Global','global',batch);
            children[PLAN.aiaScope] = createSet(PLAN.name + ' / AI Agents',PLAN.aiaScope,batch);
            checkGuards();
            for (i = 0; i < PLAN.targets.length; i++) need(sameSnapshot(snapshot(read(PLAN.targets[i].table,PLAN.targets[i].id)),snapshots[PLAN.targets[i].id],false), 'source_drift_before_first_update:' + PLAN.targets[i].id);
            for (i = 0; i < PLAN.targets.length; i++) {
                t = PLAN.targets[i]; out.stage = 'apply:' + t.id;
                select(children[t.scope]); checkGuards();
                gr = read(t.table,t.id); current = snapshot(gr);
                need(sameSnapshot(current,snapshots[t.id],false), 'source_drift_before_update:' + t.id);
                if (desiredCount === 0) {
                    // Explicit admin maintenance authority applies only to this
                    // single frozen assignment. Ordinary records cannot supply
                    // snapshots, guards, field values or capture inputs.
                    var writer = new GlideRecord(t.table);
                    need(writer.get(t.id) && String(writer.getUniqueValue()) === t.id,'maintenance_target_unavailable:' + t.id);
                    need(sameSnapshot(snapshot(read(t.table,t.id)),snapshots[t.id],false),'source_drift_before_maintenance_update:' + t.id);
                    writer.setValue(t.field,t.desired); out.attempted.push(t.id);
                    need(String(writer.update() || '') === t.id, 'source_update_failed:' + t.id); out.source_writes++;
                }
                current = snapshot(read(t.table,t.id));
                var expected = copy(snapshots[t.id]); expected[t.field] = t.desired;
                need(sameSnapshot(current,expected,true), 'source_contract_changed:' + t.id);
                finalSnapshots[t.id] = current; out.verified++;
                out.stage = 'capture:' + t.id;
                new GlideUpdateManager2().saveRecord(read(t.table,t.id));
                var capturedId = verifyCapture(t); out.customer_update_ids.push(capturedId); out.captured++;
            }
            out.stage = 'final_audit'; auditBatch(); checkGuards();
            out.ok = true; out.status = 'applied';
        }
    } catch (error) {
        out.ok = false; out.error = String(error.message || error).substring(0,280);
        out.status = out.source_writes || out.attempted.length || out.set_attempts ? 'partial_or_uncertain' : 'aborted';
    } finally {
        if (selectionChanged || String(gs.getPreference('sys_update_set') || '') !== original) {
            try { new GlideUpdateSet().set(original); need(String(gs.getPreference('sys_update_set') || '') === original,'original_update_set_restore_failed'); }
            catch (restoreError) { out.ok = false; out.status = 'partial_or_uncertain'; out.restore_error = String(restoreError.message || restoreError).substring(0,180); }
        }
        out.batch = batch; out.children = children; out.original_update_set = original;
        out.restored_update_set = String(gs.getPreference('sys_update_set') || '');
        gs.info('[HALOGEN_AGENT_DELTA_ADMIN_MAINTENANCE] ' + JSON.stringify(out));
    }
    function own(o,k) { return Object.prototype.hasOwnProperty.call(o,k); }
    function need(ok,message) { if (!ok) throw new Error(message); }
    function open(table) { var r = new GlideRecordSecure(table); need(r.isValid(),'invalid_table:' + table); return r; }
    function read(table,id) { var r = open(table); need(r.get(id) && String(r.getUniqueValue()) === id && String(r.getRecordClassName()) === table && r.canRead(),'record_unavailable:' + table + ':' + id); return r; }
    function value(r,f) { need(r.isValidField(f) && r.getElement(f).canRead(),'field_unavailable:' + f); return typedValue(r,f,r.getElement(f)); }
    function typedValue(r,f,element) {
        var raw = r.getValue(f), type = String(element.getED().getInternalType());
        // Native GlideRecord getValue uses 0/1 for booleans; SDK snapshots and
        // native XML use true/false. String property values are never coerced.
        if (type === 'boolean') {
            if (raw === '1' || raw === 'true' || raw === 1 || raw === true) return 'true';
            if (raw === '0' || raw === 'false' || raw === 0 || raw === false) return 'false';
            need(false,'invalid_boolean:' + f);
        }
        return raw === null || typeof raw === 'undefined' ? '' : String(raw);
    }
    function copy(o) { var c = {}, k; for (k in o) if (own(o,k)) c[k] = o[k]; return c; }
    function snapshot(r) { var o = {}, elements = r.getElements(), i, e, f; for (i = 0; i < elements.size(); i++) { e = elements.get(i); f = String(e.getName()); if (e.canRead()) o[f] = typedValue(r,f,e); } return o; }
    function contractMatches(actual,before,field,desired,ignoreMetadata) {
        var k; for (k in before) if (own(before,k) && !(ignoreMetadata && metadata[k])) {
            if (!own(actual,k) || actual[k] !== (k === field ? desired : before[k])) return false;
        } return true;
    }
    function sameSnapshot(actual,expected,ignoreMetadata) {
        var k; if (!contractMatches(actual,expected,'','',ignoreMetadata)) return false;
        for (k in actual) if (own(actual,k) && !(ignoreMetadata && metadata[k]) && !own(expected,k) && actual[k] !== '') return false;
        return true;
    }
    function checkGuards() {
        var i,g,r,namesSeen={},modelFound=false;
        for (i = 0; i < PLAN.guards.length; i++) {
            g = PLAN.guards[i]; r = read(g.table,g.id);
            need(contractMatches(snapshot(r),g.before,'','',false),'guard_drift:' + g.table + ':' + g.id);
            if (g.table === 'sys_properties' && /^custom_llm\.prompt_mirror\./.test(g.before.name || '')) { need(value(r,'value') === 'false','mirror_gate_enabled'); namesSeen[g.before.name] = true; }
            if (g.table === 'sys_generative_ai_model_config' && g.id === 'ff74fcef93a70350e7f2b9fa6aba10ea') {
                need(value(r,'model') === 'halogen-v2' && value(r,'active') === 'true' && value(r,'lifecycle_state') === 'active' && value(r,'provider') === '07ca9d94c3550210b0939bc8a840ddeb' && value(r,'connection') === '7040f46393a70350e7f2b9fa6aba1083','halogen_model_contract_drift'); modelFound = true;
            }
        }
        need(modelFound && namesSeen['custom_llm.prompt_mirror.automation_enabled'] && namesSeen['custom_llm.prompt_mirror.apply_enabled'] && namesSeen['custom_llm.prompt_mirror.serialized_execution_verified'],'required_guards_missing');
        checkCompanions();
    }
    function preflightCompanions() {
        var i,c,owner,seen = {};
        need(Array.isArray(PLAN.companions),'frozen_es_inventory_required');
        for (i = 0; i < PLAN.companions.length; i++) {
            c = PLAN.companions[i]; owner = null;
            for (var j = 0; j < PLAN.targets.length; j++) if (PLAN.targets[j].id === c.owner) owner = PLAN.targets[j];
            need(c.table === 'sys_es_latest_script' && owner && owner.scope === 'global' && !seen[c.owner] && c.before.id === c.owner && c.before.table === owner.table,'unexpected_es_companion'); seen[c.owner] = true;
            var current = snapshot(read(c.table,c.id)); need(contractMatches(current,c.before,'','',false),'es_companion_preimage_drift:' + c.id); companionSnapshots[c.id] = current;
        }
        checkCompanions();
    }
    function checkCompanions() {
        var owners = [], expected = {}, i,c,q,count = 0;
        for (i = 0; i < PLAN.targets.length; i++) if (PLAN.targets[i].scope === 'global') owners.push(PLAN.targets[i].id);
        for (i = 0; i < PLAN.companions.length; i++) { c = PLAN.companions[i]; expected[c.id] = true; need(sameSnapshot(snapshot(read(c.table,c.id)),companionSnapshots[c.id],false),'es_companion_contract_drift:' + c.id); }
        q = open('sys_es_latest_script'); q.addQuery('id','IN',owners.join(',')); q.query();
        while (q.next()) { need(expected[String(q.getUniqueValue())],'unexpected_es_companion_inventory'); count++; }
        need(count === PLAN.companions.length,'es_companion_inventory_count');
    }
    function findSet(name,scope,parent) {
        var q = open('sys_update_set'); q.addQuery('name',name); q.setLimit(2); q.query();
        if (!q.next()) return '';
        var id = String(q.getUniqueValue());
        need(value(q,'application') === scope && value(q,'parent') === parent && value(q,'state') === 'in progress' && value(q,'description') === description(),'unexpected_existing_batch:' + name);
        need(!q.next(),'duplicate_existing_batch:' + name); return id;
    }
    function inspectExistingBatch() {
        batch = findSet(PLAN.name,'global','');
        var global = findSet(PLAN.name + ' / Global','global',batch), aia = findSet(PLAN.name + ' / AI Agents',PLAN.aiaScope,batch);
        need(batch || (!global && !aia),'orphan_existing_children');
        if (!batch) return false;
        need(global && aia,'partial_existing_batch_requires_review'); children.global = global; children[PLAN.aiaScope] = aia;
        return true;
    }
    function description() { return PLAN.marker + '\nStandalone WIP delta; baseline ' + PLAN.baseline + ' remains unchanged. Exact 68 reviewed INSERT_OR_UPDATE identities; no deletes; no runtime execution.'; }
    function createSet(name,scope,parent) {
        var r = open('sys_update_set'); r.initialize(); r.setValue('name',name); r.setValue('application',scope); r.setValue('parent',parent); r.setValue('state','in progress'); r.setValue('description',description());
        out.set_attempts++; var id = String(r.insert() || ''); need(/^[0-9a-f]{32}$/.test(id),'set_insert_failed'); out.set_writes++; return id;
    }
    function select(id) { selectionChanged = true; new GlideUpdateSet().set(id); need(String(gs.getPreference('sys_update_set') || '') === id,'update_set_selection_failed'); }
    function verifyCapture(t) {
        var q = open('sys_update_xml'); q.addQuery('update_set',children[t.scope]); q.addQuery('name',names[t.id]); q.setLimit(2); q.query(); need(q.next(),'capture_missing:' + t.id);
        var id = String(q.getUniqueValue()); need(value(q,'application') === t.scope && value(q,'action') === 'INSERT_OR_UPDATE','capture_scope_or_action:' + t.id);
        var payload = value(q,'payload');
        // Strip text nodes which can legitimately contain example XML. Only
        // actual transport markup is inspected for destructive serializer actions.
        var markup = payload.replace(/<!\[CDATA\[[\s\S]*?\]\]>/g,'').replace(/<!--[\s\S]*?-->/g,'');
        need(!/<!DOCTYPE|<!ENTITY|\baction\s*=\s*(["'])\s*delete(?:_multiple)?\s*\1|<\s*\/?\s*delete(?:_multiple)?\b/i.test(markup),'embedded_delete_or_unsafe_xml:' + t.id);
        var doc = new XMLDocument2(); doc.parseXML(payload); var root = doc.getDocumentElement();
        need(root && String(root.getAttribute('table')) === t.table,'capture_root_mismatch:' + t.id);
        var current = finalSnapshots[t.id], k, companion = null;
        for (var c = 0; c < PLAN.companions.length; c++) if (PLAN.companions[c].owner === t.id) companion = PLAN.companions[c];
        verifyTransportShape(markup,t,current,companion);
        for (k in current) if (own(current,k) && !metadata[k]) need(String(doc.getNodeText('//' + t.table + '/' + k) || '') === current[k],'captured_contract_mismatch:' + t.id + ':' + k);
        for (k in {sys_id:1,sys_updated_on:1,sys_mod_count:1}) need(String(doc.getNodeText('//' + t.table + '/' + k) || '') === current[k],'captured_revision_mismatch:' + t.id + ':' + k);
        if (companion) for (k in companionSnapshots[companion.id]) if (own(companionSnapshots[companion.id],k)) need(String(doc.getNodeText('//sys_es_latest_script/' + k) || '') === companionSnapshots[companion.id][k],'captured_companion_contract:' + companion.id + ':' + k);
        need(!q.next(),'duplicate_capture:' + t.id); return id;
    }
    function verifyTransportShape(markup,t,current,companion) {
        // Flat metadata plus at most the explicitly frozen native ES-language
        // companion. No arbitrary related records, new fields or encoded actions.
        var tokens = markup.match(/<[^>]+>/g) || [], stack = [], rootSeen = false, recordSeen = false, companionSeen = false, fieldsSeen = {}, allowed = {}, i, token, match, tag, closing, selfClosing, depth;
        for (i = 0; i < tokens.length; i++) {
            token = tokens[i]; if (/^<\?xml\s[^?]*\?>$/.test(token)) continue;
            match = /^<(\/?)([A-Za-z_][A-Za-z0-9_.:-]*)(?:\s[^<>]*?)?\s*(\/?)>$/.exec(token); need(match,'invalid_transport_markup:' + t.id);
            closing = match[1] === '/'; tag = match[2]; selfClosing = match[3] === '/'; depth = stack.length;
            if (closing) { need(!selfClosing && stack.pop() === tag,'invalid_transport_nesting:' + t.id); continue; }
            if (depth === 0) { need(!rootSeen && tag === 'record_update','extra_transport_record:' + t.id); rootSeen = true; }
            else if (depth === 1) {
                if (!recordSeen && tag === t.table) { recordSeen = true; allowed = current; }
                else if (companion && recordSeen && !companionSeen && tag === 'sys_es_latest_script') { companionSeen = true; allowed = companionSnapshots[companion.id]; }
                else need(false,'extra_transport_record:' + t.id);
                fieldsSeen = {};
                need((token.match(/\baction\s*=/g) || []).length === 1 && /\saction\s*=\s*(["'])INSERT_OR_UPDATE\1(?:\s|\/?>)/.test(token),'transport_record_action:' + t.id);
            } else if (depth === 2) {
                need(own(allowed,tag) && !fieldsSeen[tag] && !/\baction\s*=/.test(token),'unexpected_transport_field:' + t.id + ':' + tag); fieldsSeen[tag] = true;
            } else need(false,'nested_transport_field:' + t.id);
            if (!selfClosing) stack.push(tag);
        }
        need(rootSeen && recordSeen && companionSeen === !!companion && stack.length === 0,'incomplete_transport_record:' + t.id);
    }
    function auditBatch() {
        var ids = [batch,children.global,children[PLAN.aiaScope]], i,t,q,expected={},seen={},count=0;
        need(ids[0] && ids[1] && ids[2] && ids[0] !== ids[1] && ids[1] !== ids[2] && ids[0] !== ids[2],'invalid_batch_identity');
        need(findSet(PLAN.name,'global','') === batch && findSet(PLAN.name + ' / Global','global',batch) === children.global && findSet(PLAN.name + ' / AI Agents',PLAN.aiaScope,batch) === children[PLAN.aiaScope],'batch_header_drift');
        q = open('sys_update_set'); q.addQuery('parent','IN',ids.join(',')); q.query(); while (q.next()) need((String(q.getUniqueValue()) === children.global || String(q.getUniqueValue()) === children[PLAN.aiaScope]) && value(q,'parent') === batch,'unexpected_batch_descendant');
        for (i = 0; i < PLAN.targets.length; i++) {
            t = PLAN.targets[i]; need(sameSnapshot(snapshot(read(t.table,t.id)),finalSnapshots[t.id],false),'final_source_drift:' + t.id);
            var captureId = verifyCapture(t); need(!expected[captureId],'duplicate_capture_identity'); expected[captureId] = true;
        }
        q = open('sys_update_xml'); q.addQuery('update_set','IN',ids.join(',')); q.query();
        while (q.next()) { var id = String(q.getUniqueValue()); need(expected[id] && !seen[id],'unexpected_capture_membership'); seen[id] = true; count++; }
        need(count === 68,'capture_count_mismatch'); out.captured = count;
        if (!out.customer_update_ids.length) for (var capturedId in expected) if (own(expected,capturedId)) out.customer_update_ids.push(capturedId);
    }
})();
