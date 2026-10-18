/* PROPOSAL, NOT APPLIED: replace only the custom Unified Planner's validator
 * reference with the existing OOTB third-party validator. Global Background UI;
 * leave native Record for rollback enabled. No model call or order is executed.
 * No provider definition, OOTB binding, source script, current application or
 * current update set is changed. Set APPLY=true only after root review.
 */
(function () {
    var APPLY = true;
    var SCOPE = '32808450431302106c3603295bb8f245';
    var DEFINITION = '8f80c7e193f747d0e7f2b9fa6aba109a';
    var BINDING = '1f147a53933bc754e7f2b9fa6aba10d1';
    var CAPABILITY = '1857ce78ff322210022dffffffffffa1';
    var OLD = '41501fe93b43e210cc49e0d024e45ae4';
    var NEW = '6a15e304ffd432109694ffffffffff59';
    var OLD_HASH = '0a821ad7d95eb186a609814826d1ffd4dcfde6b44d12eee6e6dcabb21228f497';
    var NEW_HASH = '5c238a01b9bc063f31cd3af88ecf6d4679633b570c450e60d94cb1c01c05e8c7';
    var receipt = {status:'preflight', target:BINDING, definition:DEFINITION,
        field:'validator', before:OLD, after:NEW, attempted:false, verified:false};
    var stage = 'authorization';
    function need(ok, why) { if (!ok) throw new Error(why); }
    function value(g, field) {
        need(g.isValidField(field) && g.getElement(field).canRead(), 'read_access:' + field);
        return String(g.getValue(field) || '');
    }
    function load(table, id) {
        var g = new GlideRecordSecure(table);
        need(g.get(id) && g.canRead(), 'record_read:' + table + ':' + id);
        return g;
    }
    function fields(g, expected) {
        for (var field in expected) if (expected.hasOwnProperty(field))
            need(value(g, field) === expected[field], 'drift:' + g.getUniqueValue() + ':' + field);
    }
    function validator(id, name, hash) {
        var g = load('sys_generative_ai_validator', id);
        fields(g, {name:name, sys_scope:SCOPE});
        need(String(new GlideDigest().getSHA256Hex(value(g, 'validator_script'))).toLowerCase() === hash,
            'validator_source_drift:' + id);
    }
    function preflight() {
        var d = load('sys_one_extend_capability_definition', DEFINITION);
        fields(d, {name:'AIA Unified Planner (Custom LLM Provider)', capability:CAPABILITY,
            api:'af9702d0c3110210b0939bc8a840dd2c', api_type:'sys_hub_flow',
            filter_properties:'{"azure_openai":"true","provider":"Custom LLMcustom_api"}',
            order:'0', sys_scope:SCOPE, sys_mod_count:'0', sys_updated_on:'2026-10-08 05:01:40'});
        validator(OLD, 'AIA Unified Planner NowLLM Validator', OLD_HASH);
        validator(NEW, 'AIA Unified Planner 3P LLM Validator', NEW_HASH);
        var compatible = load('sys_generative_ai_response_validator', 'f1c7ebc4ffd432109694ffffffffff71');
        fields(compatible, {definition:'02fb4ef0fff22210022dffffffffff4b',
            definition_table:'sys_one_extend_capability_definition', validator:NEW, active:'1'});
        fields(load('sys_one_extend_capability_definition', value(compatible, 'definition')),
            {capability:CAPABILITY, name:'AIA Unified Planner (Azure OpenAI Chat Completions)'});
        var all = new GlideRecordSecure('sys_generative_ai_response_validator');
        all.addQuery('definition', DEFINITION); all.setLimit(11); all.query();
        var count = 0;
        while (all.next()) {
            count++;
            need(String(all.getUniqueValue()) === BINDING, 'extra_custom_binding');
        }
        need(count === 1, 'custom_binding_count');
        var b = load('sys_generative_ai_response_validator', BINDING);
        fields(b, {definition:DEFINITION, definition_table:'sys_one_extend_capability_definition',
            active:'1', order:'1', sys_scope:SCOPE});
        var current = value(b, 'validator');
        need(current === OLD || current === NEW, 'concurrent_validator_drift');
        if (current === OLD) fields(b, {sys_mod_count:'0', sys_updated_on:'2026-10-13 14:35:09'});
        need(b.canWrite() && b.getElement('validator').canWrite(), 'validator_write_access');
        return b;
    }
    try {
        receipt.execution_scope = String(gs.getCurrentScopeName());
        need(gs.hasRole('admin'), 'admin_required');
        need(receipt.execution_scope === 'global' || receipt.execution_scope === 'rhino.global',
            'global_scope_required');
        stage = 'preflight';
        var first = preflight();
        if (value(first, 'validator') === NEW) { receipt.status='already_applied'; receipt.verified=true; }
        else if (!APPLY) receipt.status='dry_run';
        else {
            stage = 'immediate_recheck';
            var target = preflight();
            need(value(target, 'validator') === OLD, 'concurrent_change_before_update');
            stage = 'update'; target.setValue('validator', NEW); receipt.attempted=true;
            need(String(target.update() || '') === BINDING, 'update_failed');
            stage = 'fresh_readback';
            var check = preflight();
            need(value(check, 'validator') === NEW, 'readback_failed');
            receipt.verified=true; receipt.status='applied';
        }
    } catch (e) {
        receipt.status = receipt.attempted ? 'partial_or_uncertain' : 'aborted';
        receipt.stage = stage; receipt.error = String(e.message || e).substring(0,240);
    }
    gs.info('[SCC UNIFIED VALIDATOR PATCH] ' + JSON.stringify(receipt));
})();
