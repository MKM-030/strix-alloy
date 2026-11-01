/* Model-bound Chat Completions transport; preserves the existing SCC Vision entry. ES5. */
(function(inputs) {
    'use strict';
    var own = Object.prototype.hasOwnProperty;
    function fail(s) { throw new Error('Custom LLM: ' + s); }
    function object(v) { return v !== null && Object.prototype.toString.call(v) === '[object Object]'; }
    function text(v) { return typeof v === 'string' && /\S/.test(v); }
    function empty(v) { return v === null || typeof v === 'undefined' || v === ''; }
    function number(v, field, min, max, integer) {
        if ((typeof v !== 'string' && typeof v !== 'number') || !/\S/.test(String(v))) fail(field + ' is not numeric.');
        var n = Number(v);
        if (!isFinite(n) || n < min || n > max || (integer && Math.floor(n) !== n)) fail(field + ' is outside its supported range.');
        return n;
    }
    function messageContent(content) {
        if (text(content)) return content;
        if (!Array.isArray(content) || !content.length) fail('Expected text messages with role and content.');
        var result = [], j, part, partKeys, image, imageKeys, match, base64, normalized;
        for (j = 0; j < content.length; j++) {
            part = content[j];
            partKeys = object(part) ? Object.keys(part).sort().join(',') : '';
            if (partKeys === 'text,type' && part.type === 'text' && typeof part.text === 'string') {
                result.push({type:'text',text:part.text});
                continue;
            }
            if (partKeys !== 'image_url,type' || part.type !== 'image_url' || !object(part.image_url)) {
                fail('Only text and image_url content blocks are supported.');
            }
            image = part.image_url;
            imageKeys = Object.keys(image).sort().join(',');
            if (imageKeys !== 'url' && imageKeys !== 'detail,url') fail('Unsupported image_url fields.');
            match = typeof image.url === 'string' ? image.url.match(/^data:image\/(png|jpeg|webp|gif);base64,/) : null;
            base64 = match ? image.url.substring(match[0].length) : '';
            if (!match || !base64.length || base64.length % 4 !== 0 || !/^[A-Za-z0-9+/]+={0,2}$/.test(base64)) {
                fail('Image content requires a PNG, JPEG, WebP or GIF base64 data URL; URLs, attachment IDs and bare base64 are not accepted.');
            }
            normalized = {url:image.url};
            if (own.call(image, 'detail') && image.detail !== '') {
                if (['auto','low','high'].indexOf(image.detail) < 0) fail('Unsupported image detail.');
                normalized.detail = image.detail;
            }
            result.push({type:'image_url',image_url:normalized});
        }
        return result;
    }
    var p = inputs && inputs.prompt_data;
    if (object(p) && String(p.aiConfig) === 'cb5533db937f0b54e7f2b9fa6aba1055') {
        if (p.model !== 'halogen-v2') throw new Error('SCC Vision: this historical route requires the selected model halogen-v2.');
        var sccConfig = p.additional_configurations;
        if (empty(sccConfig)) sccConfig = {};
        else if (typeof sccConfig === 'string') {
            try { sccConfig = JSON.parse(sccConfig); }
            catch (sccConfigError) { throw new Error('SCC Vision: additional configurations must be valid JSON.'); }
        }
        if (!object(sccConfig)) throw new Error('SCC Vision: additional configurations must be an object.');
        if (own.call(sccConfig, 'VISION_CAPABILITY') &&
                (sccConfig.VISION_CAPABILITY === true || sccConfig.VISION_CAPABILITY === 'true' ||
                 sccConfig.VISION_CAPABILITY === 1 || sccConfig.VISION_CAPABILITY === '1')) {
            throw new Error('SCC Vision: native Vision and the historical attachment route cannot be combined.');
        }
        if (!empty(p.systemPromptArray) && (!Array.isArray(p.systemPromptArray) || p.systemPromptArray.length)) fail('Separate systemPromptArray requires an explicit model adapter.');
        if (!empty(p.functionCallRequest) && !(object(p.functionCallRequest) && Object.keys(p.functionCallRequest).length === 0)) fail('Native function calling requires a verified model adapter.');
        return (function(inputs) {
            var p = inputs && inputs.prompt_data;
            var prompt = p && p.prompt;
            if (Array.isArray(prompt)) {
                for (var typedIndex = 0; typedIndex < prompt.length; typedIndex++) {
                    if (object(prompt[typedIndex]) && Array.isArray(prompt[typedIndex].content)) {
                        throw new Error('SCC Vision: native Vision content and the historical attachment route cannot be combined.');
                    }
                }
                if (prompt.length !== 1 || typeof prompt[0] !== 'string') {
                    throw new Error('SCC Vision: prompt array must contain exactly one string.');
                }
                prompt = prompt[0];
            }
            if (typeof prompt !== 'string' || !prompt.replace(/\s/g, '')) {
                throw new Error('SCC Vision: inputs.prompt_data.prompt must be a nonempty string.');
            }
            var messages;
            var trimmed = prompt.replace(/^\s+|\s+$/g, '');
            if (/^[\[{]/.test(trimmed)) {
                try {
                    messages = JSON.parse(trimmed, function(key, value) {
                        if (key === '__proto__' || key === 'constructor' || key === 'prototype') {
                            throw new Error('Unsafe serialized message key.');
                        }
                        return value;
                    });
                } catch (parseError) {
                    throw new Error('SCC Vision: serialized messages are malformed or unsafe.');
                }
                if (!Array.isArray(messages) || messages.length === 0) {
                    throw new Error('SCC Vision: serialized messages must be a nonempty array.');
                }
                for (var i = 0; i < messages.length; i += 1) {
                    var message = messages[i];
                    if (object(message) && Array.isArray(message.content)) {
                        throw new Error('SCC Vision: native Vision content and the historical attachment route cannot be combined.');
                    }
                    if (!message || Object.prototype.toString.call(message) !== '[object Object]' ||
                            Object.keys(message).length !== 2 ||
                            !Object.prototype.hasOwnProperty.call(message, 'role') ||
                            !Object.prototype.hasOwnProperty.call(message, 'content') ||
                            ['system', 'user', 'assistant'].indexOf(message.role) === -1 ||
                            typeof message.content !== 'string') {
                        throw new Error('SCC Vision: serialized messages require only role and string content.');
                    }
                }
            } else {
                messages = [{role: 'user', content: prompt}];
            }
            return new global.SCCVisionRequestTransformer().build(JSON.stringify({
                body: {
                    model: 'halogen-v2',
                    messages: messages
                },
                headers: {}
            }));
        })(inputs);
    }
    if (!object(p) || !text(p.model)) fail('An explicit model identifier is required.');
    var prompt = p.prompt, messages, i, m, keys;
    if (Array.isArray(prompt) && prompt.length === 1 && typeof prompt[0] === 'string') prompt = prompt[0];
    // Native ChatCompletionsTextGenerationPromptTransformationUtil serializes messages.
    if (typeof prompt === 'string' && /^\s*\[/.test(prompt)) {
        try { prompt = JSON.parse(prompt); } catch (error) { fail('Serialized messages are not JSON.'); }
    }
    if (typeof prompt === 'string') {
        if (!text(prompt)) fail('Prompt is empty.');
        var role = empty(p.promptRole) ? 'user' : p.promptRole;
        if (['user','system','assistant'].indexOf(role) < 0) fail('Prompt role is unsupported.');
        messages = [{role:role,content:prompt}];
    } else if (Array.isArray(prompt) && prompt.length) {
        messages = [];
        for (i = 0; i < prompt.length; i++) {
            m = prompt[i]; keys = object(m) ? Object.keys(m).sort().join(',') : '';
            if (keys !== 'content,role' || ['user','system','assistant'].indexOf(m.role) < 0) fail('Expected text messages with role and content.');
            messages.push({role:m.role,content:messageContent(m.content)});
        }
    } else fail('Expected prompt text or a nonempty text-message array.');
    if (!empty(p.systemPromptArray) && (!Array.isArray(p.systemPromptArray) || p.systemPromptArray.length)) fail('Separate systemPromptArray requires an explicit model adapter.');
    var fc = p.functionCallRequest;
    if (!empty(fc) && !(object(fc) && Object.keys(fc).length === 0)) fail('Native function calling requires a verified model adapter.');
    var body = {model:p.model,messages:messages,stream:false};
    if (!empty(p.max_tokens)) {
        var budget = number(p.max_tokens, 'max_tokens', 0, 2147483647, true);
        if (budget) body.max_tokens = budget;
    }
    if (!empty(p.temperature)) body.temperature = number(p.temperature, 'temperature', 0, 2, false);
    var cfg = p.additional_configurations;
    if (empty(cfg)) cfg = {};
    else if (typeof cfg === 'string') {
        try { cfg = JSON.parse(cfg); } catch (error) { fail('Additional configurations are not JSON.'); }
    }
    if (!object(cfg)) fail('Additional configurations must be an object.');
    if (own.call(cfg, 'response_format')) {
        var format = cfg.response_format;
        if (!object(format) || ['text','json_object','json_schema'].indexOf(format.type) < 0) fail('Unsupported response_format.');
        if (format.type === 'json_schema' && (!object(format.json_schema) || !object(format.json_schema.schema) || !text(format.json_schema.name))) fail('Invalid response schema.');
        body.response_format = JSON.parse(JSON.stringify(format));
    }
    return {body:body,headers:{}};
})(inputs);
