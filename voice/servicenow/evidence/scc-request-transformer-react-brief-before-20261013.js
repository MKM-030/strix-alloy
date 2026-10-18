(function(inputs) {
    var p = inputs && inputs.prompt_data;
    if (!p || p.prompt === null || typeof p.prompt === "undefined") {
        throw new Error("Strix Alloy: inputs.prompt_data.prompt fehlt.");
    }
    var prompt = String(p.prompt);
    if (!prompt.replace(/\s/g, "")) {
        throw new Error("Strix Alloy: Der Prompt ist leer.");
    }
    if (String(p.aiConfig) === "8380c7e193f747d0e7f2b9fa6aba10b6") {
        prompt += "\n\n<scc_voice_locale_override_20261013>\nDiese abschliessenden Regeln haben fuer Sprache und Laenge Vorrang vor den englischen Beispielen oben. Wenn Benutzeranfrage oder Benutzerbeitraege in conversation_history Deutsch sind oder persona Deutsch verlangt, schreibe ALLE benutzersichtbaren Ausgaben, insbesondere transition_message und reply, vollstaendig auf Deutsch. Dies gilt auch nach einer Namensangabe oder Bestaetigung. Eine ausdrueckliche andere Sprachwahl des Benutzers hat Vorrang. Englische Beispiele zeigen nur Schema und Ablauf; uebernimm ihre englische Sprache nicht.\nFuer die SCC-Laptop-Onboarding-Demo oder eine deutsche Laptopbestellung fuer einen neuen Mitarbeiter besteht reasoning aus maximal einem kurzen Satz mit hoechstens 25 Woertern als knapper Entscheidungsbegruendung. Alle JSON-Felder, Aktions-IDs, Aktionstitel und Eingabeschluessel bleiben unveraendert. Alle bestehenden Regeln zur Aktionsauswahl, ausdruecklichen Bestellbestaetigung und Vermeidung automatischer Wiederholungen bleiben verbindlich. Fuer andere Sprachen bleiben die bisherigen Regeln unveraendert.\n</scc_voice_locale_override_20261013>";
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