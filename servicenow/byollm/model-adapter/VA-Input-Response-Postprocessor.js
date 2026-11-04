(function(outputs) {
    function fail(code) { throw new Error('Custom VA Input Response Generation: ' + code); }
    function parse(value, code) {
        try { return JSON.parse(value); }
        catch (error) { fail(code); }
    }
    function object(value) {
        return value !== null && Object.prototype.toString.call(value) === '[object Object]';
    }
    function text(value, code) {
        if (typeof value !== 'string' || !/\S/.test(value)) fail(code);
        value = value.replace(/^\s+|\s+$/g, '');
        var fence = /^```(?:json)?\s*([\s\S]*?)\s*```$/i.exec(value);
        return fence ? fence[1] : value;
    }

    outputs = parse(String(outputs), 'invalid provider output envelope JSON');
    if (!object(outputs) || !object(outputs.result)) fail('missing provider result');
    var response = parse(text(outputs.result.response, 'empty provider response'), 'invalid provider response JSON');
    if (!object(response)) fail('provider response must be a JSON object');
    var parsedModelOutput = response;
    if (Object.prototype.hasOwnProperty.call(response, 'model_output')) {
        parsedModelOutput = parse(text(response.model_output, 'empty legacy model_output'), 'invalid legacy model_output JSON');
    }
    if (!object(parsedModelOutput) || typeof parsedModelOutput.classification !== 'string' || !/\S/.test(parsedModelOutput.classification)) {
        fail('missing classifier JSON object or classification');
    }
    if (Object.prototype.hasOwnProperty.call(parsedModelOutput, 'changed_field_values') && !Array.isArray(parsedModelOutput.changed_field_values)) {
        fail('changed_field_values must be an array');
    }
    var skipResponse = parsedModelOutput.skip || parsedModelOutput.trying_to_skip;
    parsedModelOutput.trying_to_skip = skipResponse === true || skipResponse === 'true';
    outputs.result.response = JSON.stringify(parsedModelOutput);
    return outputs;
})(outputs);
