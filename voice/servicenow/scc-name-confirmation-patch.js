/* PREPARED metadata patch; no business operation. Default is dry-run.
 * Root must supply SCC_NAME_CONFIRMATION_BINDING from a fresh authenticated read
 * and explicitly select SCC_NAME_CONFIRMATION_MODE: apply or rollback.
 * Accepted states are exact original or exact original+this one addendum only.
 * Run complete script in Global with intended update set / Record for rollback.
 * Normal workflows stay enabled. Multiple record updates are NOT transactional;
 * failures report partial_or_uncertain, with no automatic retry or rollback.
 */
(function () {
    var IDS = ['a4a9438393738354e7f2b9fa6aba101d', 'a6337ddf93f787105c8132d47aba1058'];
    var SCOPE = '7cc4ec81533121106b38ddeeff7b12ee';
    var MARKER = 'scc_name_confirmation_20261024';
    var ADDENDUM = '<' + MARKER + '>\n' +
        'Zusätzliche verbindliche Namensprüfung für das Sprachgespräch; alle bisherigen Regeln zu Anforderer, Vorgesetztenprüfung, vollständiger Bestellzusammenfassung, ausdrücklicher Bestellbestätigung, einmaligem Absenden und unklarem Ergebnis bleiben erhalten. Die Namensprüfung gilt auch dann, wenn der Name bereits genannt und deshalb nicht mehr fehlend ist. Ein neu erkannter Mitarbeitername gilt für den nächsten Bestellkontextaufruf erst nach der Rücklesebestätigung als bekannt; dieser Aufruf bleibt genau einmal pro Unterhaltung zulässig.\n' +
        '1. Lies jeden neu genannten oder korrigierten kritischen Personennamen vor der weiteren fachlichen Verwendung vollständig vor. Frage ausdrücklich: "Ich habe [vollständiger Name] verstanden. Ist der Name genau so richtig?" Verwende ausschließlich die tatsächlich genannten Angaben, ohne einen Namen zu ergänzen oder aus ähnlich klingenden Namen zu erraten. Diese Prüfung betrifft insbesondere den neuen Mitarbeiter und einen ausdrücklich genannten oder korrigierten Vorgesetzten.\n' +
        '2. Bei Ablehnung, unsicherer Erkennung, mehrdeutiger Schreibweise oder unklarer Antwort bitte um Buchstabieren, bei Bedarf Vorname und Nachname einzeln. Übernimm die genannten Buchstaben einschließlich ausdrücklich genannter Umlaute, ß, Bindestriche, Apostrophe und Leerzeichen. Ist ein Buchstabe unklar, frage gezielt nach. Erfinde keine Buchstaben und ersetze keine Schreibweise stillschweigend. Lies die vollständige daraus verstandene Schreibweise erneut vor und frage ausdrücklich, ob genau diese Schreibweise richtig ist.\n' +
        '3. Fahre mit der geprüften Namensangabe erst fort, wenn eine ausdrückliche eindeutige Zustimmung auf genau diese aktuelle Namensfrage vorliegt. Ein unsicheres, verneintes, bedingtes oder auf eine andere Frage bezogenes Ja bestätigt den Namen nicht. Wird die Frage unterbrochen oder ist der Bezug unklar, stelle sie erneut. Jede Korrektur macht die vorherige Namensbestätigung ungültig und verlangt eine neue Rücklesefrage. Übernimm keine Bestätigung aus einem früheren Anruf.\n' +
        '4. Bewahre die Originalaussagen und Buchstabierangaben im Gespräch unverändert. Trenne die vorgeschlagene von der ausdrücklich bestätigten Schreibweise; stelle eine normalisierte Interpretation niemals als wörtliche frühere Nutzeraussage dar. Die Namensbestätigung bestätigt keine Identität oder Berechtigung. Ein neuer Mitarbeiter muss noch keinen Verzeichniseintrag haben. Die vorhandene autorisierte Anforderer- und Vorgesetztensuche einschließlich ihrer Mehrdeutigkeitsprüfung bleibt verbindlich.\n' +
        '5. Ein Ja zur Namensfrage ist ausschließlich die Namensbestätigung und niemals eine Bestellbestätigung. Es darf dadurch keine Bestellung abgesendet werden. Stelle danach, sobald alle übrigen Angaben vorliegen, weiterhin die vollständige aktuelle Bestellzusammenfassung mit einer getrennten ausdrücklichen Bestellfrage. Warte auf deren eigene eindeutige Zustimmung. Änderungen verlangen weiterhin eine neue vollständige Zusammenfassung und Bestätigung. Sende ausschließlich über das bestehende Bestellwerkzeug genau einmal; bei Fehler oder unklarem Ergebnis niemals automatisch erneut bestellen.\n' +
        '</' + MARKER + '>';
    var receipt = {version:1,status:'preflight',mode:'',execution_scope:'',planned:[],attempted:[],verified:[]};
    var stage = 'authorization';
    function need(ok, label) { if (!ok) throw new Error(label); }
    function hash(value) { return String(new GlideDigest().getSHA256Hex(String(value))).toLowerCase(); }
    function text(value, limit) { return typeof value === 'string' && value.length > 0 && value.length <= limit; }
    function exactKeys(value, keys) {
        if (!value || typeof value !== 'object' || Object.prototype.toString.call(value) === '[object Array]') return false;
        var actual = Object.keys(value).sort(), expected = keys.slice().sort();
        return JSON.stringify(actual) === JSON.stringify(expected);
    }
    function field(gr, name) {
        need(gr.isValidField(name), 'missing_field:' + name);
        var value = gr.getValue(name); return value === null ? '' : String(value);
    }
    function load(row) {
        var gr = new GlideRecord('sn_aia_agent');
        need(gr.get(row.sys_id), 'missing_record:' + row.sys_id);
        need(field(gr,'sys_scope') === SCOPE, 'record_scope:' + row.sys_id);
        need(field(gr,'name') === row.name, 'name_drift:' + row.sys_id);
        need(field(gr,'role') === row.role, 'role_drift:' + row.sys_id);
        need(gr.canWrite() && gr.getElement('instructions').canWrite(), 'write_access:' + row.sys_id);
        return gr;
    }
    function inspect(plan) {
        var gr = load(plan.row), current = field(gr,'instructions'), digest = hash(current);
        var capacity = Number(gr.getElement('instructions').getED().getLength());
        need(isFinite(capacity) && capacity >= plan.desired.length, 'field_length:' + plan.row.sys_id);
        need(current === plan.original || current === plan.appended, 'source_drift:' + plan.row.sys_id);
        need(digest === (current === plan.original ? plan.originalHash : plan.appendedHash), 'source_hash:' + plan.row.sys_id);
        return {gr:gr,current:current};
    }
    try {
        receipt.execution_scope = String(gs.getCurrentScopeName());
        need(gs.hasRole('admin'), 'admin_required');
        need(receipt.execution_scope === 'global' || receipt.execution_scope === 'rhino.global', 'global_scope_required');
        var mode = typeof SCC_NAME_CONFIRMATION_MODE === 'undefined' ? 'dry_run' : SCC_NAME_CONFIRMATION_MODE;
        need(mode === 'apply' || mode === 'rollback' || mode === 'dry_run' || mode === 'rollback_dry_run', 'invalid_mode');
        receipt.mode = mode;
        var rollback = mode === 'rollback' || mode === 'rollback_dry_run';
        stage = 'binding';
        var binding = typeof SCC_NAME_CONFIRMATION_BINDING === 'undefined' ? null : SCC_NAME_CONFIRMATION_BINDING;
        need(exactKeys(binding,['version','source','captured_at','records']), 'fresh_binding_required');
        need(binding.version === 1 && binding.source === 'fresh_authenticated_ui_read', 'fresh_binding_provenance');
        need(typeof binding.captured_at === 'string' && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?(?:Z|[+-]\d{2}:\d{2})$/.test(binding.captured_at) && isFinite(Date.parse(binding.captured_at.replace(/(\.\d{3})\d+/, '$1'))), 'binding_timestamp');
        need(Object.prototype.toString.call(binding.records) === '[object Array]' && binding.records.length === IDS.length, 'binding_targets');
        receipt.binding_captured_at = binding.captured_at;
        var plans = [], seen = {};
        for (var i = 0; i < binding.records.length; i++) {
            var row = binding.records[i];
            need(exactKeys(row,['table','sys_id','sys_scope','name','role','instructions','instructions_sha256']), 'binding_record_fields');
            need(row.table === 'sn_aia_agent' && IDS.indexOf(row.sys_id) !== -1 && !seen[row.sys_id] && row.sys_scope === SCOPE, 'binding_target');
            seen[row.sys_id] = true;
            need(text(row.name,256) && text(row.role,32000) && text(row.instructions,60000), 'binding_text');
            need(row.instructions.indexOf(MARKER) === -1, 'before_already_marked');
            need(typeof row.instructions_sha256 === 'string' && /^[a-f0-9]{64}$/.test(row.instructions_sha256) && hash(row.instructions) === row.instructions_sha256, 'binding_before_hash');
            var appended = row.instructions + '\n\n' + ADDENDUM;
            need(appended.length <= 65535, 'desired_too_long');
            plans.push({row:row,original:row.instructions,appended:appended,originalHash:row.instructions_sha256,appendedHash:hash(appended),desired:rollback?row.instructions:appended});
        }
        // Stable order, independent of fresh export order.
        plans.sort(function(a,b){return IDS.indexOf(a.row.sys_id)-IDS.indexOf(b.row.sys_id);});
        stage = 'preflight_all';
        for (var p = 0; p < plans.length; p++) {
            var plan = plans[p], observation = inspect(plan);
            plan.before = observation.current;
            receipt.planned.push({table:'sn_aia_agent',id:plan.row.sys_id,field:'instructions',before:hash(plan.before),after:hash(plan.desired),changed:plan.before !== plan.desired});
        }
        if (mode === 'dry_run' || mode === 'rollback_dry_run') {
            receipt.status = 'dry_run';
        } else {
            // Recheck the entire target set after preflight and before any write.
            stage = 'recheck_all';
            for (var r = 0; r < plans.length; r++) need(inspect(plans[r]).current === plans[r].before, 'concurrent_drift:' + plans[r].row.sys_id);
            for (var w = 0; w < plans.length; w++) {
                var change = plans[w];
                if (change.before === change.desired) continue;
                stage = 'update:' + change.row.sys_id;
                var target = inspect(change);
                need(target.current === change.before, 'concurrent_drift:' + change.row.sys_id);
                target.gr.setValue('instructions',change.desired);
                receipt.attempted.push(change.row.sys_id);
                need(String(target.gr.update() || '') === change.row.sys_id, 'update_failed:' + change.row.sys_id);
                need(inspect(change).current === change.desired, 'readback_failed:' + change.row.sys_id);
                receipt.verified.push(change.row.sys_id);
            }
            stage = 'final_readback';
            for (var f = 0; f < plans.length; f++) need(inspect(plans[f]).current === plans[f].desired, 'final_drift:' + plans[f].row.sys_id);
            receipt.status = receipt.attempted.length ? (rollback?'rolled_back':'applied') : (rollback?'already_rolled_back':'already_applied');
        }
    } catch (error) {
        receipt.status = receipt.attempted.length ? 'partial_or_uncertain' : 'aborted';
        receipt.stage = stage;
        receipt.error = String(error.message || error).substring(0,240);
    }
    gs.info('[SCC NAME PATCH] ' + JSON.stringify(receipt));
})();
