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

    var body = {
        model: model,
        messages: [{ role: "user", content: prompt }],
        max_tokens: maxTokens,
        temperature: temperature,
        stream: false
    };

    // Nur diese ReAct-V3-Konfiguration erwartet ein JSON-Objekt.
    // Andere Skills und aeltere ReAct-Array-Templates behalten ihr Format.
    if (String(p.aiConfig) === "4780c7e193f747d0e7f2b9fa6aba1030") {
        body.response_format = { type: "json_object" };
    }

    return { body: body, headers: {} };
})(inputs);
