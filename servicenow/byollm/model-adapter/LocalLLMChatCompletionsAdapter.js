/* Pure ES5 Chat Completions transport adapter. No record reads, locale or skill policy. */
var LocalLLMChatCompletionsAdapter = Class.create();
LocalLLMChatCompletionsAdapter.prototype = {
    initialize: function() {},
    transformJSON: function(requestText, profileText) {
        'use strict';
        if(typeof requestText!=='string'||typeof profileText!=='string'||requestText.length>16777216||profileText.length>65536)throw new Error('Custom LLM: JSON transport text required');
        var request,profile;
        try { request=JSON.parse(requestText);profile=JSON.parse(profileText); }
        catch(error) { throw new Error('Custom LLM: Invalid JSON transport text'); }
        return JSON.stringify(this.transform(request,profile));
    },
    transform: function(inputs, profile) {
        'use strict';
        var own = Object.prototype.hasOwnProperty;
        function has(o,k) { return own.call(o,k); }
        function fail(s) { throw new Error('Custom LLM: '+s); }
        function object(v) { return v!==null && Object.prototype.toString.call(v)==='[object Object]'; }
        function empty(v) { return v===null || typeof v==='undefined' || v===''; }
        function text(v) { return typeof v==='string' && /\S/.test(v); }
        function clone(v) { return JSON.parse(JSON.stringify(v)); }
        function number(v,k,min,max,integer) {
            if((typeof v!=='string' && typeof v!=='number') || !/^[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?$/.test(String(v).replace(/^\s+|\s+$/g,'')))fail(k+' is not numeric');
            var n=Number(v);
            if(!isFinite(n)||n<min||n>max||(integer&&Math.floor(n)!==n))fail(k+' is outside its supported range');
            return n;
        }
        function bool(v,k) {
            if(v===true||v==='true'||v==='1'||v===1)return true;
            if(v===false||v==='false'||v==='0'||v===0)return false;
            fail(k+' is not boolean');
        }
        function jsonObject(v,k,max) {
            if(typeof v==='string') {
                if(v.length>max)fail(k+' size');
                try { v=JSON.parse(v); } catch(e) { fail(k+' JSON'); }
            }
            if(!object(v))fail(k+' must be an object');
            return v;
        }
        function listed(v,list,k) {
            if(!Array.isArray(list)||list.indexOf(v)<0)fail(k+' is not configured as supported by this model adapter');
            return v;
        }
        if(!object(profile)||profile.version!==1||!object(profile.numberParameters)||!object(profile.aliases)||!object(profile.defaults))fail('Model adapter profile unavailable');
        var protectedNames=['model','messages','prompt','headers','tools','tool_choice','stream','temperature','max_tokens','thinking_tokens','enable_thinking','chat_template_kwargs','reasoning_effort','reasoning_format','response_format','stop','logit_bias'];
        var numericNames=Object.keys(profile.numberParameters);
        for(var ni=0;ni<numericNames.length;ni++)if(protectedNames.indexOf(numericNames[ni])>=0||!/^[a-z][a-z0-9_]*$/.test(numericNames[ni]))fail('Model numeric parameter profile has a protected field');
        var p=inputs&&inputs.prompt_data;
        if(!object(p)||!text(p.model))fail('An explicit model identifier is required');
        var prompt=p.prompt,messages=[],i,m,keys;
        if(Array.isArray(prompt)&&prompt.length===1&&typeof prompt[0]==='string')prompt=prompt[0];
        if(typeof prompt==='string'&&/^\s*\[/.test(prompt)) {
            var decoded=null,looksLikeMessages=false;
            try { decoded=JSON.parse(prompt); } catch(e) { decoded=null; }
            if(Array.isArray(decoded))for(i=0;i<decoded.length;i++)if(object(decoded[i])&&(has(decoded[i],'role')||has(decoded[i],'content')))looksLikeMessages=true;
            if(looksLikeMessages)prompt=decoded;
        }
        if(typeof prompt==='string') {
            if(!text(prompt))fail('Prompt is empty');
            var role=empty(p.promptRole)?'user':p.promptRole;
            if(['user','system','assistant'].indexOf(role)<0)fail('Prompt role is unsupported');
            messages.push({role:role,content:prompt});
        } else if(Array.isArray(prompt)&&prompt.length) {
            for(i=0;i<prompt.length;i++) {
                m=prompt[i];keys=object(m)?Object.keys(m).sort().join(','):'';
                if(keys!=='content,role'||['user','system','assistant'].indexOf(m.role)<0||!text(m.content))fail('Expected text messages with role and content');
                messages.push({role:m.role,content:m.content});
            }
        } else fail('Expected prompt text or a nonempty text-message array');
        if(!empty(p.systemPromptArray)&&(!Array.isArray(p.systemPromptArray)||p.systemPromptArray.length))fail('Separate systemPromptArray requires a verified model adapter');
        if(!empty(p.functionCallRequest)&&!(object(p.functionCallRequest)&&Object.keys(p.functionCallRequest).length===0))fail('Native function calling requires a verified model adapter');
        if(!empty(p.previous_response_id))fail('previous_response_id is not configured as supported by this model adapter');
        if(!empty(p.cuaConfig)&&!(object(p.cuaConfig)&&Object.keys(p.cuaConfig).length===0))fail('cuaConfig is not configured as supported by this model adapter');
        for(i=0;i<messages.length;i++)if(messages[i].content.indexOf('<!-- LocalLLM native Voice Assistant reference v2 -->')>=0)fail('Unresolved native assistant reference; check assistant request validator');
        var body={model:p.model,messages:messages,stream:false};
        var cfg=empty(p.additional_configurations)?{}:jsonObject(p.additional_configurations,'Additional configurations',65536);
        var values={},nativeMetadata={capability_definition:1,capability_id:1,capability:1,prompt_template:1,skill_config_id:1,json_format_supported:1,table:1,skill_name:1,activity_types:1,priority:1,llmTranslated:1,VISION_CAPABILITY:1,exclude_error_output:1,exclude_prompt_transformation:1};
        function metadata(k) { return has(nativeMetadata,k)||/_template$/.test(k)||/^config_filters_/.test(k); }
        function put(k,v) {
            if(has(values,k)&&JSON.stringify(values[k])!==JSON.stringify(v))fail(k+' conflict between configured values');
            values[k]=v;
        }
        function format(v) {
            v=jsonObject(v,'response_format',32768);
            listed(v.type,profile.responseFormats,'response_format');
            if(v.type==='json_schema'&&(!object(v.json_schema)||!object(v.json_schema.schema)||!text(v.json_schema.name)))fail('Invalid response schema');
            return clone(v);
        }
        function stop(v) {
            if(profile.stop!==true)fail('stop is not configured as supported by this model adapter');
            if(typeof v==='string'&&/^\s*\[/.test(v)) {
                try { var decodedStop=JSON.parse(v);if(Array.isArray(decodedStop))v=decodedStop; } catch(e) { /* Literal bracket text remains a valid stop string. */ }
            }
            if(typeof v==='string') {
                if(!v.length||v.length>4096)fail('stop is outside its supported range');
                return v;
            }
            if(!Array.isArray(v)||!v.length||v.length>16)fail('stop must be a string or nonempty string array');
            for(var j=0;j<v.length;j++)if(typeof v[j]!=='string'||!v[j].length||v[j].length>4096)fail('stop must contain bounded nonempty strings');
            return clone(v);
        }
        function bias(v) {
            if(profile.logitBias!==true)fail('logit_bias is not configured as supported by this model adapter');
            v=jsonObject(v,'logit_bias',32768);
            var result={},names=Object.keys(v);
            if(names.length>1024)fail('logit_bias size');
            for(var j=0;j<names.length;j++) {
                var name=names[j];
                if(!/^(0|[1-9][0-9]*)$/.test(name)||Number(name)>4294967295)fail('logit_bias token keys are invalid');
                result[name]=number(v[name],'logit_bias',-100,100,false);
            }
            return result;
        }
        function normalize(k,v) {
            if(k==='temperature')return number(v,k,0,2,false);
            if(k==='max_tokens'||k==='thinking_tokens')return number(v,k,0,2147483647,true);
            if(has(profile.numberParameters,k)) {
                var range=profile.numberParameters[k];
                if(!Array.isArray(range)||range.length!==3||typeof range[0]!=='number'||typeof range[1]!=='number'||typeof range[2]!=='boolean')fail('Model numeric parameter profile invalid');
                return number(v,k,range[0],range[1],range[2]);
            }
            if(k==='response_format')return format(v);
            if(k==='stop')return stop(v);
            if(k==='logit_bias')return bias(v);
            if(k==='reasoning_effort')return listed(v,profile.reasoningEfforts,k);
            if(k==='reasoning_format')return listed(v,profile.reasoningFormats,k);
            if(k==='enable_thinking')return listed(bool(v,k),profile.thinkingValues,k);
            if(k==='chat_template_kwargs') {
                v=jsonObject(v,k,32768);keys=Object.keys(v);
                if(keys.length!==1||keys[0]!=='enable_thinking')fail('chat_template_kwargs keys are not configured as supported');
                return {enable_thinking:listed(bool(v.enable_thinking,'enable_thinking'),profile.thinkingValues,'enable_thinking')};
            }
            fail(k+' is not configured as supported by this model adapter');
        }
        var cfgKeys=Object.keys(cfg);
        for(i=0;i<cfgKeys.length;i++) {
            var key=cfgKeys[i],canonical=has(profile.aliases,key)?profile.aliases[key]:(key==='effort'?'reasoning_effort':key);
            if(key==='__proto__'||key==='constructor'||key==='prototype')fail('Reserved configuration key');
            if(metadata(key)) {
                if(key==='VISION_CAPABILITY'&&!empty(cfg[key])&&bool(cfg[key],key))fail('Typed content is not configured as supported by this model adapter');
                continue;
            }
            put(canonical,normalize(canonical,cfg[key]));
        }
        if(!empty(p.max_tokens))put('max_tokens',number(p.max_tokens,'max_tokens',0,2147483647,true));
        if(!empty(p.temperature))put('temperature',number(p.temperature,'temperature',0,2,false));
        if(has(values,'enable_thinking')&&has(values,'chat_template_kwargs')&&values.enable_thinking!==values.chat_template_kwargs.enable_thinking)fail('enable_thinking conflict between configured values');
        var explicitEffort=has(values,'reasoning_effort');
        var explicitThinking=has(values,'enable_thinking')||has(values,'chat_template_kwargs');
        var thinking=explicitThinking?(has(values,'enable_thinking')?values.enable_thinking:values.chat_template_kwargs.enable_thinking):null;
        // Native thinking_enabled is model capability, not prompt request intent.
        if(!empty(p.thinking_enabled))bool(p.thinking_enabled,'thinking_enabled');
        if(explicitEffort&&values.reasoning_effort==='none'&&thinking===true)fail('reasoning_effort conflict with enabled thinking');
        var nativeBudget=empty(p.thinking_tokens)?0:number(p.thinking_tokens,'thinking_tokens',0,2147483647,true);
        var budget=has(values,'thinking_tokens')?values.thinking_tokens:nativeBudget;
        if(has(values,'thinking_tokens')&&nativeBudget>0&&values.thinking_tokens!==nativeBudget)fail('thinking_tokens conflict between configured values');
        if(budget>0) {
            if((explicitEffort&&values.reasoning_effort==='none')||thinking===false)fail('thinking_tokens conflict with disabled reasoning');
            if(typeof profile.thinkingTokenParameter!=='string'||!/^[a-z][a-z0-9_]*$/.test(profile.thinkingTokenParameter)||protectedNames.indexOf(profile.thinkingTokenParameter)>=0||has(profile.numberParameters,profile.thinkingTokenParameter))fail('thinking_tokens is not configured as supported by this model adapter');
            body[profile.thinkingTokenParameter]=budget;
        }
        if(typeof profile.contextTokens!=='number'||profile.contextTokens<1||Math.floor(profile.contextTokens)!==profile.contextTokens||typeof profile.outputTokensMax!=='number'||profile.outputTokensMax<1||Math.floor(profile.outputTokensMax)!==profile.outputTokensMax||profile.outputTokensMax>profile.contextTokens)fail('Declared model token capacities are invalid');
        if(has(values,'max_tokens')&&(values.max_tokens>profile.contextTokens||values.max_tokens>profile.outputTokensMax))fail('max_tokens exceeds the declared model context or output capacity');
        if(budget>profile.contextTokens)fail('thinking_tokens exceeds the declared model context capacity');
        var valueKeys=Object.keys(values);
        for(i=0;i<valueKeys.length;i++) {
            var name=valueKeys[i];
            if(name==='thinking_tokens'||name==='enable_thinking'||name==='chat_template_kwargs')continue;
            if(name==='max_tokens'&&values[name]===0)continue;
            body[name]=clone(values[name]);
        }
        if(thinking!==null)body.chat_template_kwargs={enable_thinking:thinking};
        if(!explicitEffort&&thinking!==true&&budget===0&&has(profile.defaults,'reasoning_effort'))body.reasoning_effort=listed(profile.defaults.reasoning_effort,profile.reasoningEfforts,'reasoning_effort');
        if(!explicitThinking&&!explicitEffort&&budget===0&&has(profile.defaults,'chat_template_kwargs'))body.chat_template_kwargs=normalize('chat_template_kwargs',profile.defaults.chat_template_kwargs);
        if(!has(values,'reasoning_format')&&has(profile.defaults,'reasoning_format'))body.reasoning_format=listed(profile.defaults.reasoning_format,profile.reasoningFormats,'reasoning_format');
        return {body:body,headers:{}};
    },
    type: 'LocalLLMChatCompletionsAdapter'
};
