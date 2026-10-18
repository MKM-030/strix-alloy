// READ ONLY: SCC scripts and message settings; no tool execution or updates.
// Paste this complete block into Scripts - Background, scope Global.
(function () {
    var chat = 'a4a9438393738354e7f2b9fa6aba101d';
    var voice = 'a6337ddf93f787105c8132d47aba1058';
    var order = '8b5c4f0393b38354e7f2b9fa6aba10f7';
    var context = '15ebcb8f93738354e7f2b9fa6aba1072';
    var agentFields = 'name,agent_type,strategy,processing_message,post_processing_message,required_translations';
    var bindingFields = 'name,agent,tool,active,execution_mode,max_auto_executions,pre_run,timeout,pre_message,post_message,display_output,requires_text_refined_message,should_display_refined_message,requires_widget_transformation,output_transformation_strategy,transformation_instructions,post_processing_script';
    var specs = [
        ['sn_aia_tool', order, 'name,active,type,script'],
        ['sn_aia_tool', context, 'name,active,type,script'],
        ['sn_aia_agent', chat, agentFields],
        ['sn_aia_agent', voice, agentFields],
        ['sn_aia_agent_tool_m2m', '835c4f0393b38354e7f2b9fa6aba10f9', bindingFields, chat, order],
        ['sn_aia_agent_tool_m2m', '55ebcb8f93738354e7f2b9fa6aba107b', bindingFields, chat, context],
        ['sn_aia_agent_tool_m2m', '0ed4b19b933b87105c8132d47aba1030', bindingFields, voice, order],
        ['sn_aia_agent_tool_m2m', 'f1d4319b933b87105c8132d47aba10ff', bindingFields, voice, context]
    ];
    var totalChars = 0;
    if (!gs.hasRole('admin')) {
        gs.print('[SCC DETAILS] Administrator role required; nothing read.');
        return;
    }
    for (var i = 0; i < specs.length; i++) {
        var spec = specs[i];
        var result = {read_only:true, table:spec[0], sys_id:spec[1], fields:{}};
        try {
            var gr = new GlideRecord(spec[0]);
            if (!gr.isValid() || !gr.get(spec[1])) {
                result.status = 'missing_or_inaccessible';
            } else if (spec[3] && (!gr.isValidField('agent') || !gr.isValidField('tool') ||
                    String(gr.getValue('agent')) !== spec[3] || String(gr.getValue('tool')) !== spec[4])) {
                result.status = 'binding_reference_mismatch';
            } else {
                var fields = ('sys_scope,sys_mod_count,sys_updated_on,' + spec[2]).split(',');
                for (var j = 0; j < fields.length; j++) {
                    var field = fields[j];
                    if (!gr.isValidField(field)) {
                        result.fields[field] = {status:'missing'};
                        continue;
                    }
                    var value = String(gr.getValue(field) || '');
                    if (value.length > 16000 || totalChars + value.length > 48000) {
                        result.fields[field] = {status:'omitted_limit', length:value.length};
                        continue;
                    }
                    if (/-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|\bBearer\s+[A-Za-z0-9._~+\/-]{12,}/i.test(value) ||
                            /["'](?:password|client_secret|api_key|access_token|refresh_token|auth_token|private_key|shared_secret)["']\s*:\s*["'][^"'\s][^"']*["']/i.test(value)) {
                        result.fields[field] = {status:'omitted_sensitive_literal'};
                        continue;
                    }
                    totalChars += value.length;
                    result.fields[field] = {status:'read', value:value, length:value.length};
                }
                result.status = 'read';
            }
        } catch (error) {
            result.status = 'read_failed';
        }
        gs.print('[SCC DETAILS] ' + JSON.stringify(result));
    }
})();
