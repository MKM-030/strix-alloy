/* Shared by eight server-only after insert/update rules. See descriptors.
 * Previous routing links make reparenting visible without copying skills.
 */
(function executeRule(current, previous) {
    if (current.operation() !== 'insert' && current.operation() !== 'update') { return; }
    var prior = null, fields = ['definition', 'definition_table', 'document_id', 'document_table', 'ai_config', 'capability', 'validator', 'api', 'api_type'], i, element;
    if (current.operation() === 'update' && previous !== null && typeof previous !== 'undefined') {
        prior = {sys_id: String(previous.getUniqueValue())};
        for (i = 0; i < fields.length; i++) {
            if (previous.isValidField(fields[i])) {
                element = previous.getElement(fields[i]);
                if (element !== null && typeof element !== 'undefined' && element.canRead()) { prior[fields[i]] = String(previous.getValue(fields[i]) || ''); }
            }
        }
    }
    try {
        var result = new global.CustomLLMPromptMirror().onSourceChange(String(current.getTableName()), String(current.getUniqueValue()), prior);
        if (['Applied', 'Processed', 'NoOp', 'Ignored', 'AutomationDisabled'].indexOf(result.status) === -1) {
            gs.warn('Custom LLM prompt mirror: ' + result.status + ' for ' + String(current.getTableName()) + ':' + String(current.getUniqueValue()) + '; ' + JSON.stringify(result.issues || result.results || []));
        }
    } catch (e) { gs.warn('Custom LLM prompt mirror: source prompt reconciliation stopped: ' + String(e.message || e)); }
})(current, previous);
