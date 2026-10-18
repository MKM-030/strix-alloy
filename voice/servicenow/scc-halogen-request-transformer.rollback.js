(function(inputs) {
    var p = inputs && inputs.prompt_data;
    if (!p || p.prompt === null || typeof p.prompt === "undefined") {
        throw new Error("Strix Alloy: inputs.prompt_data.prompt fehlt.");
    }
    var prompt = String(p.prompt);
    if (!prompt.replace(/\s/g, "")) {
        throw new Error("Strix Alloy: Der Prompt ist leer.");
    }
    // In ServiceNow als Modellname die technische API-Modell-ID verwenden.
    var model = p.model ? String(p.model) : "halogen-v2";
    // Antwortbudget, NICHT die gesamte Kontextkapazitaet.
    var maxTokens = parseInt(p.max_tokens, 10);
    if (!isFinite(maxTokens) || maxTokens < 1) {
        maxTokens = 1024;
    }
    maxTokens = Math.min(maxTokens, 2048);
    // Startkonfiguration
    var temperature = parseFloat(p.temperature);
    if (!isFinite(temperature)) {
        temperature = 0;
    }
    temperature = Math.max(0, Math.min(temperature, 2));
    return {
        body: {
            model: model,
            messages: [{ role: "user", content: prompt }],
            max_tokens: maxTokens,
            temperature: temperature,
            stream: false
        },
        headers: {}
    };
})(inputs);
