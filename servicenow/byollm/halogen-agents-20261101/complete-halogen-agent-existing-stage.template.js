/* OFFLINE-PREPARED REUSE-ONLY CONTINUATION, SEPARATE APPROVAL REQUIRED. Run once in Global with SDK
 * rollback recording only after reviewing this exact rendered script/hash.
 * Reuses one exact existing stage; no insert, rename or parent write is allowed.
 * No retry/resume path. Normal native Business Rules and security stay enabled.
 * Secure supplies every read, precondition, snapshot and capture input. Ordinary
 * records have bounded assignments only. The 67 applied sources are read-only.
 */
(function () {
    var PLAN = /*__EXISTING_STAGE_PLAN__*/;
    var out = {ok:false,status:'aborted',stage:'preflight',source_writes:0,captures:0,header_writes:0,cu_moves:0,write_attempts:0,readonly_sources_verified:0,original_execution_history:PLAN.originalExecutionHistoryId,original_rollback_context:PLAN.originalRollbackContextId,prior_compact_execution_history:PLAN.priorCompactExecutionHistoryId,prior_compact_rollback_context:PLAN.priorCompactRollbackContextId};
    var original = String(gs.getPreference('sys_update_set') || ''), selectionChanged = false;
    var sources = {}, guardSnapshots = {}, companions = {}, wrappers = {}, headers = {}, names = {}, stageId = '', stageSnapshot = null, ledger = null;
    var revision = {sys_mod_count:1,sys_updated_on:1,sys_updated_by:1}, sourceMetadata = {sys_mod_count:1,sys_updated_on:1,sys_updated_by:1,request_tokens:1};
    try {
        need(gs.hasRole('admin'),'admin_required');
        need(PLAN.schema === 1 && PLAN.authorityMode === 'separately_approved_existing_stage_completion','separate_completion_authority_required');
        need(original,'original_update_set_required');
        need(PLAN.targets.length === 68 && PLAN.guards.length === 21 && PLAN.companions.length === 2 && PLAN.headers.length === 4 && PLAN.cus.length === 68,'invalid_completion_inventory');
        var seen = {}, i,t,r,current;
        for (i = 0; i < PLAN.targets.length; i++) {
            t = PLAN.targets[i]; need(!seen[t.id] && /^[0-9a-f]{32}$/.test(t.id),'duplicate_target'); seen[t.id] = true;
            need((t.table === 'sys_generative_ai_config' && t.field === 'model' && t.scope === PLAN.aiaScope && t.desired === 'halogen-v2') || (t.id === PLAN.ids.transformer && t.table === 'sys_generative_ai_custom_llm_transformer' && t.field === 'request_transformer' && t.scope === 'global') || (t.id === PLAN.ids.ledger && t.table === 'sys_script_include' && t.field === 'script' && t.scope === 'global'),'unapproved_source_shape');
            r = read(t.table,t.id); need(value(r,'sys_policy') === '','source_policy_protected:' + t.id);
            current = snapshot(r); need(same(current,t.current),'source_preimage_drift:' + t.id); sources[t.id] = current;
            names[t.id] = (r.isValidField('sys_update_name') ? value(r,'sys_update_name') : '') || t.table + '_' + t.id;
            if (t.id === PLAN.ids.ledger) { need(!ledger && matches(current,t.before),'ledger_original_preimage_required'); ledger = t; }
            else need(current[t.field] === t.desired,'applied_source_not_exact:' + t.id);
        }
        need(ledger && PLAN.targets.filter(function (x) { return x.table === 'sys_generative_ai_config'; }).length === 66,'target_count_or_ledger');
        for (i = 0; i < PLAN.companions.length; i++) { var c = PLAN.companions[i]; current = snapshot(read(c.table,c.id)); need(matches(current,c.before),'companion_preimage_drift:' + c.id); companions[c.id] = current; }
        checkGuards(); checkCompanions();
        for (i = 0; i < PLAN.headers.length; i++) { var h = PLAN.headers[i]; current = snapshot(read('sys_update_set',h.sys_id)); need(same(current,h),'header_preimage_drift:' + h.sys_id); headers[h.sys_id] = current; }
        for (i = 0; i < PLAN.cus.length; i++) { var cu = PLAN.cus[i]; current = snapshot(read('sys_update_xml',cu.sys_id)); need(same(current,cu),'cu_preimage_drift:' + cu.sys_id); wrappers[cu.sys_id] = current; }
        inspectTopology(); inspectMembership(false); requireExistingStage();
        for (i = 0; i < PLAN.targets.length; i++) if (PLAN.targets[i].id !== PLAN.ids.ledger) verifyCapture(PLAN.targets[i],wrappers[PLAN.targets[i].capture],false);
        verifyFlag(wrappers[PLAN.ids.flag],false);
        // Recheck every frozen source, guard, companion, header, CU revision and
        // topology immediately before the first write. No partial state accepted.
        checkSources(false); checkGuards(); checkCompanions(); checkWrappers(); checkHeaders(); inspectTopology(); inspectMembership(false); requireExistingStage();

        // The confirmed parent correction and existing native-created stage are
        // frozen inputs. This continuation cannot create, rename or repair them.
        out.stage = 'bind_frozen_existing_stage';
        requireEmpty(PLAN.ids.parent); stageId = PLAN.existingStageId; stageSnapshot = headers[stageId]; out.staging_header = stageId;
        requireExistingStage(); checkHeaders(); inspectTopology(); inspectMembership(false);
        out.stage = 'evacuate_children_with_native_scope_checks';
        for (i = 0; i < PLAN.cus.length; i++) { cu = PLAN.cus[i]; move(cu.sys_id,cu.application === PLAN.aiaScope ? stageId : PLAN.ids.parent); }
        requireEmpty(PLAN.ids.global); requireEmpty(PLAN.ids.aia);
        out.stage = 'correct_empty_child_applications';
        changeHeader(PLAN.ids.global,'application','global'); changeHeader(PLAN.ids.aia,'application',PLAN.aiaScope);
        out.stage = 'restore_original_cu_identities_to_correct_children';
        for (i = 0; i < PLAN.cus.length; i++) { cu = PLAN.cus[i]; move(cu.sys_id,cu.application === PLAN.aiaScope ? PLAN.ids.aia : PLAN.ids.global); }
        requireEmpty(stageId); requireEmpty(PLAN.ids.parent); requireNoDescendants(stageId);
        out.stage = 'ignore_empty_external_staging_header'; changeStageToIgnore();
        checkSources(false); checkGuards(); checkCompanions(); checkWrappers(); checkHeaders(); inspectTopology(); inspectMembership(false);
        out.stage = 'assign_only_frozen_ledger_script';
        selectionChanged = true; new GlideUpdateSet().set(PLAN.ids.global);
        need(String(gs.getPreference('sys_update_set') || '') === PLAN.ids.global,'global_update_set_selection_failed');
        r = read(ledger.table,ledger.id); need(value(r,'sys_policy') === '' && same(snapshot(r),sources[ledger.id]),'ledger_drift_before_only_source_write');
        var writer = new GlideRecord(ledger.table);
        need(writer.get(ledger.id) && String(writer.getUniqueValue()) === ledger.id,'ledger_writer_unavailable');
        need(same(snapshot(read(ledger.table,ledger.id)),sources[ledger.id]),'ledger_drift_before_ordinary_assignment');
        writer.setValue(ledger.field,ledger.desired); out.write_attempts++;
        need(String(writer.update() || '') === ledger.id,'ledger_update_failed'); out.source_writes++;
        current = snapshot(read(ledger.table,ledger.id)); var expected = copy(sources[ledger.id]); expected[ledger.field] = ledger.desired;
        need(same(current,expected,sourceMetadata),'ledger_source_contract_changed'); requireIncrement(current,sources[ledger.id],'ledger'); sources[ledger.id] = current;
        out.stage = 'native_capture_only_ledger';
        out.write_attempts++; new GlideUpdateManager2().saveRecord(read(ledger.table,ledger.id)); out.captures++;
        var captured = open('sys_update_xml'); captured.addQuery('name',names[ledger.id]); captured.addQuery('update_set',PLAN.ids.global); captured.setLimit(2); captured.query(); need(captured.next(),'ledger_capture_missing');
        var ledgerCU = snapshot(captured); need(!captured.next() && !own(wrappers,ledgerCU.sys_id),'duplicate_ledger_capture'); wrappers[ledgerCU.sys_id] = ledgerCU; ledger.capture = ledgerCU.sys_id;
        verifyCapture(ledger,ledgerCU,true); out.ledger_customer_update = ledgerCU.sys_id;
        out.stage = 'final_audit'; checkSources(true); checkGuards(); checkCompanions(); checkWrappers(); checkHeaders(); inspectTopology(); inspectMembership(true);
        for (i = 0; i < PLAN.targets.length; i++) { t = PLAN.targets[i]; verifyCapture(t,wrappers[t.capture],true); }
        verifyFlag(wrappers[PLAN.ids.flag],true); requireEmpty(stageId); requireNoDescendants(stageId);
        need(stageSnapshot.state === 'ignore' && value(read('sys_update_set',stageId),'state') === 'ignore','staging_not_ignored');
        need(out.source_writes === 1 && out.captures === 1 && out.header_writes === 3 && out.cu_moves === 136,'unexpected_write_counts');
        out.ok = true; out.status = 'completed'; out.verified_sources = 68; out.verified_customer_updates = 69;
    } catch (error) {
        out.ok = false; out.error = String(error.message || error).substring(0,300); out.status = out.write_attempts ? 'partial_or_uncertain' : 'aborted';
    } finally {
        if (selectionChanged || String(gs.getPreference('sys_update_set') || '') !== original) {
            try { new GlideUpdateSet().set(original); need(String(gs.getPreference('sys_update_set') || '') === original,'preference_restore_failed'); }
            catch (restoreError) { out.ok = false; out.status = 'partial_or_uncertain'; out.restore_error = String(restoreError.message || restoreError).substring(0,180); }
        }
        out.original_update_set = original; out.restored_update_set = String(gs.getPreference('sys_update_set') || ''); out.batch = PLAN.ids.parent; out.global_child = PLAN.ids.global; out.aia_child = PLAN.ids.aia;
        gs.info('[HALOGEN_AGENT_EXISTING_STAGE_COMPLETION] ' + JSON.stringify(out));
    }
    function own(o,k) { return Object.prototype.hasOwnProperty.call(o,k); }
    function need(ok,message) { if (!ok) throw new Error(message); }
    function copy(o) { var result = {}, k; for (k in o) if (own(o,k)) result[k] = o[k]; return result; }
    function open(table) { var r = new GlideRecordSecure(table); need(r.isValid(),'invalid_table:' + table); return r; }
    function read(table,id) { var r = open(table); need(r.get(id) && String(r.getUniqueValue()) === id && String(r.getRecordClassName()) === table && r.canRead(),'record_unavailable:' + table + ':' + id); return r; }
    function typed(r,f,e) {
        var raw = r.getValue(f), type = String(e.getED().getInternalType());
        if (type === 'boolean') {
            if (raw === '1' || raw === 'true' || raw === 1 || raw === true) return 'true';
            if (raw === '0' || raw === 'false' || raw === 0 || raw === false) return 'false';
            need(false,'invalid_boolean:' + f);
        }
        return raw === null || typeof raw === 'undefined' ? '' : String(raw);
    }
    function value(r,f) { need(r.isValidField(f) && r.getElement(f).canRead(),'field_unavailable:' + f); return typed(r,f,r.getElement(f)); }
    function snapshot(r) { var result = {}, es = r.getElements(), i,e,f; for (i = 0; i < es.size(); i++) { e = es.get(i); f = String(e.getName()); if (e.canRead()) result[f] = typed(r,f,e); } return result; }
    function matches(actual,expected,ignored) { var k; for (k in expected) if (own(expected,k) && !(ignored && ignored[k]) && (!own(actual,k) || actual[k] !== expected[k])) return false; return true; }
    function same(actual,expected,ignored) { var k; if (!matches(actual,expected,ignored)) return false; for (k in actual) if (own(actual,k) && !(ignored && ignored[k]) && !own(expected,k) && actual[k] !== '') return false; return true; }
    function requireIncrement(after,before,label) { need(/^\d+$/.test(before.sys_mod_count) && after.sys_mod_count === String(Number(before.sys_mod_count) + 1),'unexpected_revision_increment:' + label); }
    function checkSources(completed) { var i,t; for (i = 0; i < PLAN.targets.length; i++) { t = PLAN.targets[i]; need(same(snapshot(read(t.table,t.id)),sources[t.id]),'source_revision_or_contract_drift:' + t.id); need(sources[t.id][t.field] === (t.id === PLAN.ids.ledger && !completed ? t.before[t.field] : t.desired),'source_value_drift:' + t.id); } out.readonly_sources_verified = 67; }
    function checkGuards() { var i,g,current,key; for (i = 0; i < PLAN.guards.length; i++) { g = PLAN.guards[i]; key = g.table + ':' + g.id; current = snapshot(read(g.table,g.id)); need(matches(current,g.before),'guard_drift:' + key); if (own(guardSnapshots,key)) need(same(current,guardSnapshots[key]),'guard_full_snapshot_drift:' + key); else guardSnapshots[key] = current; } }
    function checkCompanions() {
        var expected = {}, owners = [], i,c,q,count = 0;
        for (i = 0; i < PLAN.targets.length; i++) if (PLAN.targets[i].scope === 'global') owners.push(PLAN.targets[i].id);
        for (i = 0; i < PLAN.companions.length; i++) { c = PLAN.companions[i]; expected[c.id] = true; need(same(snapshot(read(c.table,c.id)),companions[c.id]),'companion_drift:' + c.id); }
        q = open('sys_es_latest_script'); q.addQuery('id','IN',owners.join(',')); q.query(); while (q.next()) { need(expected[String(q.getUniqueValue())],'unexpected_companion'); count++; } need(count === 2,'companion_inventory_drift');
    }
    function checkWrappers() { var id; for (id in wrappers) if (own(wrappers,id)) need(same(snapshot(read('sys_update_xml',id)),wrappers[id]),'cu_contract_or_revision_drift:' + id); }
    function checkHeaders() { var id; for (id in headers) if (own(headers,id)) need(same(snapshot(read('sys_update_set',id)),headers[id]),'header_contract_or_revision_drift:' + id); if (stageId) need(same(snapshot(read('sys_update_set',stageId)),stageSnapshot),'staging_header_drift'); }
    function requireEmpty(id) { var q = open('sys_update_xml'); q.addQuery('update_set',id); q.setLimit(1); q.query(); need(!q.next(),'set_must_be_empty:' + id); }
    function requireNoDescendants(id) { var q = open('sys_update_set'); q.addQuery('parent',id); q.setLimit(1); q.query(); need(!q.next(),'unexpected_staging_descendant'); if (id === PLAN.existingStageId) { q = open('sys_update_set'); q.addQuery('base_update_set',id); q.setLimit(1); q.query(); need(!q.next(),'unexpected_staging_base_member'); } }
    function requireExistingStage() {
        var id = PLAN.existingStageId, frozen = headers[id], record = read('sys_update_set',id), actual = snapshot(record);
        need(frozen && same(actual,frozen),'existing_stage_snapshot_drift');
        need(actual.name === PLAN.stagingName && actual.description === PLAN.stagingDescription && actual.application === PLAN.aiaScope && actual.state === 'in progress' && actual.is_default === 'false' && actual.parent === '' && actual.base_update_set === '','existing_stage_contract');
        need(PLAN.headerFieldLimits.name === 80 && PLAN.headerFieldLimits.description === 4000 && value(record,'name').length === 80 && value(record,'description').length <= 4000 && PLAN.stagingDescription.indexOf(PLAN.priorCompletionMarker + '\n') === 0,'existing_stage_owned_identity');
        checkStageUniqueOwnership(); requireEmpty(id); requireNoDescendants(id);
    }
    function checkStageUniqueOwnership() {
        var id = PLAN.existingStageId, q = open('sys_update_set'); q.addQuery('name',PLAN.stagingName); q.setLimit(2); q.query();
        need(q.next() && String(q.getUniqueValue()) === id && !q.next(),'existing_stage_name_not_unique');
        q = open('sys_update_set'); q.addQuery('description','STARTSWITH',PLAN.priorCompletionMarker + '\n'); q.setLimit(2); q.query();
        need(q.next() && String(q.getUniqueValue()) === id && !q.next(),'existing_stage_owner_marker_not_unique');
    }
    function inspectTopology() {
        var ids = [PLAN.ids.parent,PLAN.ids.global,PLAN.ids.aia], q = open('sys_update_set'), count = 0; q.addQuery('parent','IN',ids.join(',')); q.query();
        while (q.next()) { var id = String(q.getUniqueValue()); need((id === PLAN.ids.global || id === PLAN.ids.aia) && value(q,'parent') === PLAN.ids.parent,'unexpected_batch_descendant'); count++; } need(count === 2,'batch_children_inventory');
        // Native batch completion enumerates base_update_set, independently of
        // the parent tree. An orphan with the same base would join the batch.
        q = open('sys_update_set'); q.addQuery('base_update_set',PLAN.ids.parent); q.query(); var baseSeen = {}, baseCount = 0;
        while (q.next()) { id = String(q.getUniqueValue()); need(own(headers,id) && !baseSeen[id] && value(q,'base_update_set') === PLAN.ids.parent && value(q,'parent') === (id === PLAN.ids.parent ? '' : PLAN.ids.parent),'unexpected_base_batch_member'); baseSeen[id] = true; baseCount++; }
        need(baseCount === 3 && baseSeen[PLAN.ids.parent] && baseSeen[PLAN.ids.global] && baseSeen[PLAN.ids.aia],'base_batch_membership_inventory');
        var i,h; for (i = 0; i < PLAN.headers.length; i++) { h = PLAN.headers[i]; q = open('sys_update_set'); q.addQuery('name',h.name); q.setLimit(2); q.query(); need(q.next() && String(q.getUniqueValue()) === h.sys_id && !q.next(),'duplicate_or_missing_batch_name'); }
        checkStageUniqueOwnership();
        if (stageId) { requireNoDescendants(stageId); need(stageSnapshot.parent === '' && (stageSnapshot.base_update_set === '' || stageSnapshot.base_update_set === stageId),'staging_joined_batch'); }
    }
    function inspectMembership(completed) {
        var ids = [PLAN.ids.parent,PLAN.ids.global,PLAN.ids.aia], q = open('sys_update_xml'), seen = {}, count = 0; if (stageId) ids.push(stageId);
        q.addQuery('update_set','IN',ids.join(',')); q.query();
        while (q.next()) { var id = String(q.getUniqueValue()); need(own(wrappers,id) && !seen[id],'unexpected_cu_membership'); seen[id] = true; count++; need(same(snapshot(q),wrappers[id]),'membership_snapshot_drift:' + id); }
        need(count === (completed ? 69 : 68),'cu_membership_count');
        var key; for (key in wrappers) if (own(wrappers,key)) need(seen[key],'missing_cu_member:' + key);
    }
    function changeHeader(id,field,desired) {
        need(field === 'application' && (id === PLAN.ids.global || id === PLAN.ids.aia) && own(PLAN.headerScopes,id) && desired === PLAN.headerScopes[id],'unbounded_header_assignment'); requireEmpty(id);
        var before = headers[id]; need(same(snapshot(read('sys_update_set',id)),before),'header_drift_before_assignment');
        var w = new GlideRecord('sys_update_set'); need(w.get(id) && String(w.getUniqueValue()) === id,'header_writer_unavailable'); w.setValue(field,desired); out.write_attempts++;
        need(String(w.update() || '') === id,'header_update_failed:' + id); out.header_writes++;
        var after = snapshot(read('sys_update_set',id)), expected = copy(before); expected[field] = desired;
        need(same(after,expected,revision),'header_changed_other_fields:' + id); requireIncrement(after,before,'header:' + id); headers[id] = after;
    }
    function move(id,destination) {
        var before = wrappers[id]; need(before && before.update_set !== destination,'invalid_cu_move');
        need((destination === stageId && before.application === PLAN.aiaScope) || (destination === PLAN.ids.parent && before.application === 'global') || (destination === PLAN.ids.aia && before.application === PLAN.aiaScope) || (destination === PLAN.ids.global && before.application === 'global'),'unbounded_cu_destination');
        var destinationSnapshot = destination === stageId ? stageSnapshot : headers[destination], sourceSnapshot = before.update_set === stageId ? stageSnapshot : headers[before.update_set];
        need(destinationSnapshot && sourceSnapshot && same(snapshot(read('sys_update_set',destination)),destinationSnapshot) && same(snapshot(read('sys_update_set',before.update_set)),sourceSnapshot),'move_header_contract_or_revision_drift');
        need(destinationSnapshot.application === before.application && destinationSnapshot.state === 'in progress','destination_scope_or_state_mismatch');
        need(same(snapshot(read('sys_update_xml',id)),before),'cu_drift_before_move:' + id);
        var w = new GlideRecord('sys_update_xml'); need(w.get(id) && String(w.getUniqueValue()) === id,'cu_writer_unavailable'); w.setValue('update_set',destination); out.write_attempts++;
        need(String(w.update() || '') === id,'native_cu_move_failed:' + id); out.cu_moves++;
        var after = snapshot(read('sys_update_xml',id)), expected = copy(before); expected.update_set = destination;
        need(same(after,expected,revision),'cu_nonwrapper_contract_changed:' + id); requireIncrement(after,before,'cu:' + id); wrappers[id] = after;
        // Normal native BR also moves matching sys_update_version associations.
        // No direct version-record assignment, origin edit or payload edit.
    }
    function changeStageToIgnore() {
        requireEmpty(stageId); requireNoDescendants(stageId); need(same(snapshot(read('sys_update_set',stageId)),stageSnapshot),'staging_drift_before_ignore');
        var w = new GlideRecord('sys_update_set'); need(w.get(stageId) && String(w.getUniqueValue()) === stageId,'staging_writer_unavailable'); w.setValue('state','ignore'); out.write_attempts++;
        need(String(w.update() || '') === stageId,'staging_ignore_failed'); out.header_writes++;
        var after = snapshot(read('sys_update_set',stageId)), expected = copy(stageSnapshot); expected.state = 'ignore';
        need(same(after,expected,revision),'staging_ignore_changed_other_fields'); requireIncrement(after,stageSnapshot,'staging'); stageSnapshot = after; headers[stageId] = after;
    }
    function parseCapture(cu,t,expected,companion) {
        need(cu.action === 'INSERT_OR_UPDATE' && cu.application === t.scope && cu.name === names[t.id],'capture_identity_scope_action:' + t.id);
        var payload = cu.payload, markup = payload.replace(/<!\[CDATA\[[\s\S]*?\]\]>/g,'').replace(/<!--[\s\S]*?-->/g,'');
        need(!/<!DOCTYPE|<!ENTITY|\baction\s*=\s*(["'])\s*delete(?:_multiple)?\s*\1|<\s*\/?\s*delete(?:_multiple)?\b/i.test(markup),'unsafe_capture_xml:' + t.id);
        var doc = new XMLDocument2(); doc.parseXML(payload); var root = doc.getDocumentElement(); need(root && String(root.getAttribute('table')) === t.table,'capture_root:' + t.id);
        verifyTransportShape(markup,t,expected,companion);
        var k,actual;
        for (k in expected) if (own(expected,k) && k !== 'request_tokens' && k !== 'sys_updated_by') {
            actual = String(doc.getNodeText('//' + t.table + '/' + k) || '');
            // The allowance is only these TWO exact frozen JavaScript fields.
            // It never changes source comparison or any other XML field.
            var code = ((t.id === PLAN.ids.transformer && k === 'request_transformer') || (t.id === PLAN.ids.ledger && k === 'script')) && expected[k] === t.desired;
            need(actual === expected[k] || (code && actual === t.desired.replace(/\r/g,'')),'captured_contract_mismatch:' + t.id + ':' + k);
        }
        if (companion) for (k in companions[companion.id]) if (own(companions[companion.id],k)) need(String(doc.getNodeText('//sys_es_latest_script/' + k) || '') === companions[companion.id][k],'captured_companion_drift:' + companion.id + ':' + k);
    }
    function verifyCapture(t,cu,completed) {
        need(cu && cu.sys_id === t.capture,'capture_identity_missing:' + t.id);
        if (completed || stageId) need(cu.update_set === (t.scope === 'global' ? PLAN.ids.global : PLAN.ids.aia),'capture_final_wrapper:' + t.id);
        var companion = null; for (var i = 0; i < PLAN.companions.length; i++) if (PLAN.companions[i].owner === t.id) companion = PLAN.companions[i];
        parseCapture(cu,t,sources[t.id],companion);
    }
    function verifyFlag(cu,completed) {
        var frozen = null; for (var i = 0; i < PLAN.cus.length; i++) if (PLAN.cus[i].sys_id === PLAN.ids.flag) frozen = PLAN.cus[i];
        need(frozen && cu && cu.sys_id === frozen.sys_id && cu.name === frozen.name && cu.application === 'global' && cu.action === 'INSERT_OR_UPDATE' && cu.payload === frozen.payload,'native_flag_cu_payload_or_identity_changed');
        if (completed || stageId) need(cu.update_set === PLAN.ids.global,'native_flag_cu_wrapper');
        var markup = cu.payload.replace(/<!\[CDATA\[[\s\S]*?\]\]>/g,'').replace(/<!--[\s\S]*?-->/g,''); need(!/<!DOCTYPE|<!ENTITY|\baction\s*=\s*(["'])\s*delete(?:_multiple)?\s*\1/i.test(markup),'unsafe_native_flag_xml');
        var doc = new XMLDocument2(); doc.parseXML(cu.payload); var root = doc.getDocumentElement(); need(root && String(root.getAttribute('table')) === 'sys_gen_ai_control_setting_data' && String(doc.getNodeText('//sys_gen_ai_control_setting_data/sys_id') || '') === '32ee2ed0fff53210c3fcffffffffff09','native_flag_payload_identity');
        // Its live source is deliberately volatile. No read-modify-write, old
        // source-value guard or capture is performed for this native flag.
    }
    function verifyTransportShape(markup,t,current,companion) {
        var tokens = markup.match(/<[^>]+>/g) || [], stack = [], rootSeen = false, recordSeen = false, companionSeen = false, fields = {}, allowed = {}, i,token,m,tag,closing,selfClosing,depth;
        for (i = 0; i < tokens.length; i++) {
            token = tokens[i]; if (/^<\?xml\s[^?]*\?>$/.test(token)) continue;
            m = /^<(\/?)([A-Za-z_][A-Za-z0-9_.:-]*)(?:\s[^<>]*?)?\s*(\/?)>$/.exec(token); need(m,'invalid_transport_markup:' + t.id);
            closing = m[1] === '/'; tag = m[2]; selfClosing = m[3] === '/'; depth = stack.length;
            if (closing) { need(!selfClosing && stack.pop() === tag,'invalid_transport_nesting:' + t.id); continue; }
            if (depth === 0) { need(!rootSeen && tag === 'record_update','extra_transport_root:' + t.id); rootSeen = true; }
            else if (depth === 1) {
                if (!recordSeen && tag === t.table) { recordSeen = true; allowed = current; }
                else if (companion && recordSeen && !companionSeen && tag === 'sys_es_latest_script') { companionSeen = true; allowed = companions[companion.id]; }
                else need(false,'extra_transport_record:' + t.id);
                fields = {}; need((token.match(/\baction\s*=/g) || []).length === 1 && /\saction\s*=\s*(["'])INSERT_OR_UPDATE\1(?:\s|\/?>)/.test(token),'transport_record_action:' + t.id);
            } else if (depth === 2) { need(own(allowed,tag) && !fields[tag] && !/\baction\s*=/.test(token),'unexpected_transport_field:' + t.id + ':' + tag); fields[tag] = true; }
            else need(false,'nested_transport_field:' + t.id);
            if (!selfClosing) stack.push(tag);
        }
        need(rootSeen && recordSeen && companionSeen === !!companion && stack.length === 0,'incomplete_transport_record:' + t.id);
    }
})();
