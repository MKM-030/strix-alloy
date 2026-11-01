(function(promptObj, configGrSysId, payload, promptTemplateRole, childPrompts) {
    var configGr = new GlideRecordSecure('sys_generative_ai_config');
    if (!configGr.isValid() || !configGr.get(configGrSysId) || !configGr.canRead() ||
        !configGr.isValidField('additional_configurations')) {
        throw new Error('Custom LLM prompt configuration unavailable or unreadable.');
    }
    var declaration = configGr.getElement('additional_configurations');
    if (declaration === null || typeof declaration === 'undefined' || !declaration.canRead()) {
        throw new Error('Custom LLM prompt configuration declaration is unreadable.');
    }
    var rawConfig = configGr.getValue('additional_configurations');
    var additionalConfig = {};
    if (rawConfig !== null && rawConfig !== '') {
        try {
            additionalConfig = JSON.parse(rawConfig);
        } catch (e) {
            throw new Error('Custom LLM additional configuration must be valid JSON.');
        }
        if (Object.prototype.toString.call(additionalConfig) !== '[object Object]') {
            throw new Error('Custom LLM additional configuration must be a JSON object.');
        }
    }
    if (promptTemplateRole === null || promptTemplateRole === undefined || promptTemplateRole === '') {
        promptTemplateRole = 'user';
    }
    if (Object.prototype.hasOwnProperty.call(additionalConfig, 'VISION_CAPABILITY') &&
        (additionalConfig.VISION_CAPABILITY === true || additionalConfig.VISION_CAPABILITY === 'true')) {
        var definitionFields = ['definition_table', 'definition'];
        for (var i = 0; i < definitionFields.length; i++) {
            if (!configGr.isValidField(definitionFields[i])) {
                throw new Error('Custom LLM Vision definition field is unavailable.');
            }
            var definitionField = configGr.getElement(definitionFields[i]);
            if (definitionField === null || typeof definitionField === 'undefined' || !definitionField.canRead()) {
                throw new Error('Custom LLM Vision definition field is unreadable.');
            }
        }
        if (String(configGr.getValue('definition_table')) !== 'sys_one_extend_capability_definition') {
            throw new Error('Custom LLM Vision requires a OneExtend capability definition.');
        }
        var definitionId = String(configGr.getValue('definition'));
        if (!/^[0-9a-f]{32}$/.test(definitionId)) {
            throw new Error('Custom LLM Vision definition identifier is invalid.');
        }
        var definitionGr = new GlideRecordSecure('sys_one_extend_capability_definition');
        if (!definitionGr.isValid() || !definitionGr.get(definitionId) || !definitionGr.canRead() ||
            !definitionGr.isValidField('capability')) {
            throw new Error('Custom LLM Vision capability definition is unavailable or unreadable.');
        }
        var capabilityField = definitionGr.getElement('capability');
        if (capabilityField === null || typeof capabilityField === 'undefined' || !capabilityField.canRead()) {
            throw new Error('Custom LLM Vision capability field is unreadable.');
        }
        var resolvedCapabilityId = String(definitionGr.getValue('capability'));
        if (!/^[0-9a-f]{32}$/.test(resolvedCapabilityId)) {
            throw new Error('Custom LLM Vision capability identifier is invalid.');
        }
        if (typeof ChatCompletionsVisionPromptTransformationUtil !== 'function') {
            throw new Error('Custom LLM native Vision prompt transformation utility is unavailable.');
        }
        return new ChatCompletionsVisionPromptTransformationUtil().transformPrompt(
            promptObj, configGrSysId, payload, promptTemplateRole, childPrompts, resolvedCapabilityId);
    }
    if (typeof ChatCompletionsTextGenerationPromptTransformationUtil !== 'function') {
        throw new Error('Custom LLM native text prompt transformation utility is unavailable.');
    }
    return new ChatCompletionsTextGenerationPromptTransformationUtil().transformPrompt(
        promptObj, configGrSysId, payload, promptTemplateRole, childPrompts);
})(promptObj, configGrSysId, payload, promptTemplateRole, childPrompts);
