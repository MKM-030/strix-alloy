/* Model-bound Chat Completions envelope. Do not rewrite model output or validators. */
(function(inputs) {
    'use strict';
    function fail(s) { throw new Error('Custom LLM: ' + s); }
    var raw = inputs && inputs.response_body, response;
    if (raw === null || typeof raw === 'undefined' || raw === '') fail('No response body received.');
    try { response = JSON.parse(String(raw)); }
    catch (error) { fail('Response is not JSON; check endpoint and non-streaming mode.'); }
    if (!response || Object.prototype.toString.call(response) !== '[object Object]') fail('Unexpected response envelope.');
    if (response.error) fail('Provider API error; check connection status.');
    if (!Array.isArray(response.choices) || response.choices.length !== 1 || !response.choices[0]) fail('Expected exactly one response choice.');
    var choice = response.choices[0], message = choice.message;
    if (choice.finish_reason === 'length') fail('Response was truncated; check response budget and context.');
    if (choice.finish_reason === 'content_filter') fail('Provider filtered the response.');
    if (!message || message.refusal) fail('Provider returned no usable text response.');
    if (message.tool_calls && (!Array.isArray(message.tool_calls) || message.tool_calls.length)) fail('Native function calling requires a verified model adapter.');
    if (message.function_call) fail('Native function calling requires a verified model adapter.');
    if (typeof message.content !== 'string' || !/\S/.test(message.content)) fail('Response contains no message text.');
    return [message.content];
})(inputs);
