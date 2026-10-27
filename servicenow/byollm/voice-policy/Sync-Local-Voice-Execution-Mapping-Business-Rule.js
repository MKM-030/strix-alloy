/* Synchronous administrative mapping projection. Configuration and backups
 * are captured only to the configured instance-private LOCAL ONLY Update Set.
 */
(function executeRule(current, previous) {
    var operation = String(current.operation() || '');
    var mapped = String(current.getValue('u_local_llm_execution_profile') || '');
    var oldProfile = previous ? String(previous.getValue('u_local_llm_execution_profile') || '') : '';
    var changed = operation === 'delete' || operation === 'insert' && !!mapped;
    if (operation === 'update') changed = current.u_local_llm_execution_profile.changes() ||
        current.now_assist_deployment.changes() || current.context_profile.changes();
    if (!changed || !mapped && !oldProfile) return;
    var serviceId = String(current.getValue('now_assist_deployment') || '');
    if (!/^[0-9a-f]{32}$/.test(serviceId)) throw new Error('VOICE_ASSISTANT_PERSONA_SYNC_UNAVAILABLE');
    var service = new GlideRecordSecure('sys_now_assist_deployment');
    if (!service.get(serviceId) || !service.canRead()) throw new Error('VOICE_ASSISTANT_PERSONA_SYNC_UNAVAILABLE');
    if (String(service.getValue('assistant_type') || '') !== 'voice') return;
    try {
        new global.LocalLLMVoicePersonaRouteSync().syncService(serviceId,oldProfile,
            operation === 'delete',String(current.getUniqueValue() || ''));
    } catch (error) {
        gs.error('VOICE_ASSISTANT_PERSONA_SYNC_UNAVAILABLE');
        gs.addErrorMessage('The local Voice execution mapping could not be synchronized. Select the configured instance-private LOCAL ONLY Update Set in the Voice application and retry the mapping change. Voice sessions remain unavailable until the mapping is synchronized.');
        throw new Error('VOICE_ASSISTANT_PERSONA_SYNC_UNAVAILABLE');
    }
})(current, previous);
