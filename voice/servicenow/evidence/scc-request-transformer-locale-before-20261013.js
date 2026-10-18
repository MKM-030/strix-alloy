(function(inputs) {
    var p = inputs && inputs.prompt_data;
    if (!p || p.prompt === null || typeof p.prompt === "undefined") {
        throw new Error("Strix Alloy: inputs.prompt_data.prompt fehlt.");
    }
    var prompt = String(p.prompt);
    if (!prompt.replace(/\s/g, "")) {
        throw new Error("Strix Alloy: Der Prompt ist leer.");
    }
    var model = p.model ? String(p.model) : "halogen-v2";
    var maxTokens = parseInt(p.max_tokens, 10);
    if (!isFinite(maxTokens) || maxTokens < 1) { maxTokens = 1024; }
    maxTokens = Math.min(maxTokens, 2048);
    var temperature = parseFloat(p.temperature);
    if (!isFinite(temperature)) { temperature = 0; }
    temperature = Math.max(0, Math.min(temperature, 2));
    var body = {model:model,messages:[{role:"user",content:prompt}],max_tokens:maxTokens,temperature:temperature,stream:false};
    // ReAct V3 expects an object; keep other skills and older array templates unchanged.
    if (String(p.aiConfig) === "4780c7e193f747d0e7f2b9fa6aba1030") { body.response_format = {type:"json_object"}; }
    return {body:body,headers:{}};
})(inputs);