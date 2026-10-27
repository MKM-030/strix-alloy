/* Protect instance-specific mapping fields from public Update Set capture.
 * The AFTER rule derives private prompt route attributes only after this guard.
 */
(function executeRule(current, previous) {
    var operation = String(current.operation() || '');
    var mapped = String(current.getValue('u_local_llm_execution_profile') || '');
    var oldProfile = previous ? String(previous.getValue('u_local_llm_execution_profile') || '') : '';
    var changed = operation === 'delete' || operation === 'insert' && !!mapped;
    if (operation === 'update') changed = current.u_local_llm_execution_profile.changes() ||
        current.now_assist_deployment.changes() || current.context_profile.changes();
    if (!changed || !mapped && !oldProfile) return;
    try {
        var serviceId = String(current.getValue('now_assist_deployment') || '');
        if (!/^[0-9a-f]{32}$/.test(serviceId)) throw new Error('VOICE_ASSISTANT_PERSONA_SYNC_UNAVAILABLE');
        var service = new GlideRecordSecure('sys_now_assist_deployment');
        if (!service.get(serviceId) || !service.canRead()) throw new Error('VOICE_ASSISTANT_PERSONA_SYNC_UNAVAILABLE');
        var voiceSource = String(service.getValue('assistant_type') || '') === 'voice';
        // A source reparented away from Voice still contains the old private mapping.
        // Check the previous deployment before deciding the change is unrelated.
        var oldServiceId = previous ? String(previous.getValue('now_assist_deployment') || '') : '';
        if (!voiceSource && oldServiceId && oldServiceId !== serviceId) {
            if (!/^[0-9a-f]{32}$/.test(oldServiceId)) throw new Error('VOICE_ASSISTANT_PERSONA_SYNC_UNAVAILABLE');
            var oldService = new GlideRecordSecure('sys_now_assist_deployment');
            if (!oldService.get(oldServiceId) || !oldService.canRead()) throw new Error('VOICE_ASSISTANT_PERSONA_SYNC_UNAVAILABLE');
            voiceSource = String(oldService.getValue('assistant_type') || '') === 'voice';
        }
        if (!voiceSource) return;
        new global.LocalLLMVoicePersonaRouteSync().assertPrivateContext();
    } catch (error) {
        current.setAbortAction(true);
        gs.error('VOICE_ASSISTANT_PERSONA_SYNC_UNAVAILABLE');
        gs.addErrorMessage('The local Voice execution mapping is instance-specific. Select the configured LOCAL ONLY Update Set in the Voice application before changing this mapping. No mapping changes were saved.');
    }
})(current, previous);
