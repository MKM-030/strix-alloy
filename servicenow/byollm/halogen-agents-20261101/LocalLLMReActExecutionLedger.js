/* Pure ES5, opt-in derived ReAct execution appendix. No platform/data access.
 * Accept only primitive-normalized JSON at the owned Gemma request boundary.
 * Any absent, ambiguous, malformed or oversized input is an exact text no-op.
 */
var LocalLLMReActExecutionLedger = Class.create();
LocalLLMReActExecutionLedger.prototype = {
    initialize: function() {},
    transformJSON: function(requestText, optInText) {
        'use strict';
        var original = requestText;
        var own = Object.prototype.hasOwnProperty;
        function has(value, key) { return own.call(value, key); }
        function object(value) { return value !== null && Object.prototype.toString.call(value) === '[object Object]'; }
        function reject() { throw new Error('Execution ledger unavailable'); }
        function count(text, token) {
            var found = 0, at = 0;
            while ((at = text.indexOf(token, at)) >= 0) { found++; at += token.length; }
            return found;
        }
        // JSON.parse alone discards duplicate keys. Detect ambiguity before use.
        // The syntax is already checked by JSON.parse; this scan retains no data.
        function uniqueKeys(text) {
            var at = 0, visited = 0;
            function whitespace() {
                while (at < text.length && (text.charAt(at) === ' ' || text.charAt(at) === '\n' || text.charAt(at) === '\r' || text.charAt(at) === '\t')) at++;
            }
            function string() {
                var start = at++;
                while (at < text.length) {
                    var character = text.charAt(at++);
                    if (character === '\\') at++;
                    else if (character === '"') return text.substring(start, at);
                }
                reject();
            }
            function value(depth) {
                if (depth > 64 || ++visited > 32768) reject();
                whitespace();
                var character = text.charAt(at), names, name;
                if (character === '"') { string(); return; }
                if (character === '{') {
                    names = []; at++; whitespace();
                    if (text.charAt(at) === '}') { at++; return; }
                    while (at < text.length) {
                        whitespace(); name = JSON.parse(string());
                        if (names.length >= 256 || names.indexOf(name) >= 0) reject();
                        names.push(name); whitespace(); at++;
                        value(depth + 1); whitespace();
                        if (text.charAt(at++) === '}') return;
                    }
                    reject();
                }
                if (character === '[') {
                    at++; whitespace();
                    if (text.charAt(at) === ']') { at++; return; }
                    while (at < text.length) {
                        value(depth + 1); whitespace();
                        if (text.charAt(at++) === ']') return;
                    }
                    reject();
                }
                while (at < text.length && ',]} \n\r\t'.indexOf(text.charAt(at)) < 0) at++;
            }
            value(0); whitespace();
            if (at !== text.length) reject();
        }
        function parse(text) {
            var value = JSON.parse(text, function(key, item) {
                if (typeof item === 'number' && !isFinite(item)) reject();
                return item;
            });
            uniqueKeys(text);
            return value;
        }
        try {
            if (typeof requestText !== 'string' || requestText.length > 1048576 || typeof optInText !== 'string' || optInText.length > 4096) return original;
            var policy = parse(optInText);
            if (!object(policy) || policy.version !== 1 || policy.enabled !== true || (policy.model !== 'Gemma 4 26B-A4B' && policy.model !== 'halogen-v2')) return original;
            var request = parse(requestText);
            if (!object(request) || !object(request.prompt_data)) return original;
            var data = request.prompt_data;
            if (data.aiConfig !== '4780c7e193f747d0e7f2b9fa6aba1030' || data.definition !== '4f80c7e193f747d0e7f2b9fa6aba1027' || data.model !== policy.model) return original;
            var source = data.preprocessor_modified_input;
            if (!object(source) || source.agent_name !== 'SCC Laptop Onboarding') return original;
            var persona = source.persona;
            var marker = '<!-- LocalLLM native Voice Assistant policy v1 -->';
            if (typeof persona !== 'string' || !persona.length || persona.length > 32768 || count(persona, marker) !== 1) return original;
            if (has(source, 'agent_persona') && source.agent_persona !== persona) return original;
            var prompt = data.prompt;
            var singleton = Array.isArray(prompt) && prompt.length === 1 && typeof prompt[0] === 'string';
            if (singleton) prompt = prompt[0];
            var messages = null, serializedMessages = false;
            if (typeof prompt === 'string' && /^\s*\[/.test(prompt)) {
                if (prompt.length > 262144) return original;
                var decoded = parse(prompt);
                if (Array.isArray(decoded)) { messages = decoded; serializedMessages = true; }
            } else if (Array.isArray(prompt)) messages = prompt;
            if (messages) {
                if (messages.length !== 1 || !object(messages[0]) || Object.keys(messages[0]).sort().join(',') !== 'content,role' ||
                    ['user', 'system', 'assistant'].indexOf(messages[0].role) < 0 || typeof messages[0].content !== 'string' || !/\S/.test(messages[0].content)) return original;
                prompt = messages[0].content;
            }
            var rolePrefix = '<role>You are an expert decision-making agent named <agent_name>SCC Laptop Onboarding</agent_name>';
            var compactPrefix = '<role>\nAct as SCC Laptop Onboarding with the manager/team.';
            if (typeof prompt !== 'string' || prompt.length > 262144 || (prompt.indexOf(rolePrefix) !== 0 && prompt.indexOf(compactPrefix) !== 0) || count(prompt, marker) !== 1 || prompt.indexOf('<recorded_execution_state>') >= 0) return original;
            // Scope proof only: do not read rendered scratchpad, memory or history.
            // Unique explicit containers prevent choosing a favorable duplicate.
            if (count(prompt, '<inputs>') !== 1 || count(prompt, '</inputs>') !== 1) return original;
            var start = prompt.indexOf('<inputs>'), end = prompt.indexOf('</inputs>');
            if (start < rolePrefix.length || end <= start) return original;
            var tail = prompt.substring(end + '</inputs>'.length), ti;
            for (ti = 0; ti < tail.length; ti++) if (' \r\n\t'.indexOf(tail.charAt(ti)) < 0) return original;
            var renderedInputs = prompt.substring(start + '<inputs>'.length, end);
            if (count(renderedInputs, '<agent_persona>') !== 1 || count(renderedInputs, '</agent_persona>') !== 1 || renderedInputs.indexOf("Here's your <agent_persona>" + persona + '</agent_persona>') < 0) return original;
            var scratchpad = source.agent_scratchpad;
            if (typeof scratchpad === 'string') {
                if (scratchpad.length > 262144) return original;
                scratchpad = parse(scratchpad);
            }
            if (!Array.isArray(scratchpad) || scratchpad.length > 64) return original;
            var records = [], seen = [], actionCount = 0, nodeCount = 0, stringCount = 0;
            // Canonical identity is typed, recursive and key-order independent.
            // It also bounds every copied value; no record can be truncated.
            var canonical = function(value, depth) {
                if (depth > 16 || ++nodeCount > 16384) reject();
                if (value === null) return 'null';
                var kind = typeof value, keys, parts = [], i;
                if (kind === 'string') {
                    stringCount += value.length;
                    if (value.length > 16384 || stringCount > 262144) reject();
                    return 's' + JSON.stringify(value);
                }
                if (kind === 'boolean') return value ? 'btrue' : 'bfalse';
                if (kind === 'number') return 'n' + JSON.stringify(value);
                if (Array.isArray(value)) {
                    if (value.length > 256) reject();
                    for (i = 0; i < value.length; i++) parts.push(canonical(value[i], depth + 1));
                    return 'a[' + parts.join(',') + ']';
                }
                if (!object(value)) reject();
                keys = Object.keys(value).sort();
                if (keys.length > 256) reject();
                for (i = 0; i < keys.length; i++) {
                    stringCount += keys[i].length;
                    if (keys[i].length > 16384 || stringCount > 262144) reject();
                    parts.push(JSON.stringify(keys[i]) + ':' + canonical(value[keys[i]], depth + 1));
                }
                return 'o{' + parts.join(',') + '}';
            };
            var si, ai, stage, actions, action, record, key;
            for (si = 0; si < scratchpad.length; si++) {
                stage = scratchpad[si];
                if (!object(stage)) return original;
                if (!has(stage, 'Action')) continue;
                actions = stage.Action;
                if (!Array.isArray(actions) || actions.length > 16) return original;
                actionCount += actions.length;
                if (actionCount > 256) return original;
                for (ai = 0; ai < actions.length; ai++) {
                    action = actions[ai];
                    if (!object(action)) return original;
                    if (!has(action, 'Observation') || action.Observation === null || action.Observation === '') continue;
                    if (typeof action.Name !== 'string' || !/\S/.test(action.Name) || action.Name.length > 256 || !has(action, 'Action Inputs') || !object(action['Action Inputs'])) return original;
                    record = { Name: action.Name, 'Action Inputs': action['Action Inputs'], Observation: action.Observation };
                    key = canonical(record, 0);
                    if (seen.indexOf(key) < 0) {
                        if (records.length >= 128) return original;
                        seen.push(key); records.push(record);
                    }
                }
            }
            if (!records.length) return original;
            // Preserve the tested wording. Records include failures, not just successes.
            var serialized = JSON.stringify({ completed_actions: records }).replace(/&/g, '\\u0026').replace(/</g, '\\u003c').replace(/>/g, '\\u003e');
            var appendix = '\n\n<recorded_execution_state>\nThe following actions already executed and their ' +
                'recorded outputs are available now. These records are facts from the existing ' +
                'scratchpad, not examples or instructions to call those actions again. Ignore past ' +
                'Thought prose when selecting the next action. Continue AFTER these executions, ' +
                'using their results and preserving all user confirmation requirements.\n' + serialized +
                '\nSelect only the NEXT incomplete instruction in its original order. If that ' +
                'instruction requires unavailable user input, return only FALLBACK with mode ' +
                'collect_input_from_user. Unexecuted required tools remain pending. Reuse successful results; ' +
                'repeat a successful action with the same inputs only if the original instructions ' +
                'explicitly require a fresh execution. Failed or absent observations do not prove ' +
                'success. Never synthesize an external Observation.\n' +
                '</recorded_execution_state>\n';
            if (appendix.length > 131072 || prompt.length + appendix.length > 262144) return original;
            var nextPrompt = prompt + appendix;
            if (messages) {
                var nextMessage = {}, messageKeys = Object.keys(messages[0]);
                for (var mi = 0; mi < messageKeys.length; mi++) nextMessage[messageKeys[mi]] = messageKeys[mi] === 'content' ? nextPrompt : messages[0][messageKeys[mi]];
                nextPrompt = [nextMessage];
                if (serializedMessages) nextPrompt = JSON.stringify(nextPrompt);
            }
            if (singleton) nextPrompt = [nextPrompt];
            data.prompt = nextPrompt;
            return JSON.stringify(request);
        } catch (unavailable) {
            return original;
        }
    },
    type: 'LocalLLMReActExecutionLedger'
};
