/*
 * ServiceNow > Scripts - Background > Global.
 * Defaults to a read-only plan. Set DRY_RUN=false to apply ACTION.
 * ACTION: 'apply' or 'rollback'. The original provider prompt is never changed.
 *
 * The generic connector sends the rendered prompt. The copied ReAct v3 system
 * prompt omitted the current question, scratchpad and conversation memory.
 * These placeholders add that context through normal prompt rendering instead
 * of appending raw request_data in the shared custom-LLM transformer.
 *
 * This patch is specific to the reviewed instance records. It changes only the
 * owned prompt field, preserves the original prompt byte-for-byte, and refuses
 * a write if either prompt no longer has the expected relationship.
 */
(function () {
    var DRY_RUN = true;
    var ACTION = 'apply';
    var TABLE = 'sys_generative_ai_config';
    var TARGET_ID = '4780c7e193f747d0e7f2b9fa6aba1030';
    var SOURCE_ID = 'ef46ebab935cbe105c21b7cd1dba10ab';
    var MARKER = '<!-- SCC custom connector: rendered conversation context -->';
    var ADDITION = '\n\n' + MARKER + '\n' +
        'Here is your <mission>{{question}}</mission>\n' +
        'Here is your <scratchpad>{{agent_scratchpad}}</scratchpad>\n' +
        'Here is your <memory>{{short_term_memory}}</memory>\n' +
        'Here is your <session_archive>{{previous_scratchpad}}</session_archive>\n' +
        '</inputs>\n';
    var result = {ok: false, action: ACTION, dryRun: DRY_RUN,
        table: TABLE, sys_id: TARGET_ID, writes: 0};

    try {
        if (ACTION !== 'apply' && ACTION !== 'rollback')
            throw new Error("ACTION must be 'apply' or 'rollback'.");

        var source = new GlideRecord(TABLE);
        var target = new GlideRecord(TABLE);
        if (!source.get(SOURCE_ID) || !target.get(TARGET_ID))
            throw new Error('Reviewed source or target record is missing.');

        var original = String(source.getValue('prompt') || '');
        var current = String(target.getValue('prompt') || '');
        if (!original || original.indexOf(MARKER) !== -1)
            throw new Error('Source prompt is empty or already contains the custom marker.');

        var patched = original + ADDITION;
        if (current !== original && current !== patched)
            throw new Error('Prompt changed: exact original or exact reviewed addition required. No write.');

        var desired = ACTION === 'apply' ? patched : original;
        result.changed = current !== desired;
        result.beforeLength = current.length;
        result.afterLength = desired.length;

        if (result.changed && !DRY_RUN) {
            target.setWorkflow(false);
            target.setValue('prompt', desired);
            if (!target.update())
                throw new Error('Prompt update failed.');
            result.writes = 1;
        }

        result.ok = true;
        gs.info('[SCC ReAct Context] ' + JSON.stringify(result));
    } catch (error) {
        result.error = String(error.message || error);
        gs.error('[SCC ReAct Context] ' + JSON.stringify(result));
    }
})();
